"""Official Drive v3 adapter. Fixed folders, bounded files, durable recovery.

No rclone credentials are imported. A private, user-authorized OAuth client is
required. SDK retries are disabled; cooldown is shared by videos and social jobs.
"""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import time

from .drive import DriveError, MAX_BYTES, safe_name
from .transport_state import TransportState

SCOPE = 'https://www.googleapis.com/auth/drive'
FIELDS = 'id,name,size,mimeType,modifiedTime,parents,trashed,version'


def private_write(path, raw):
    path = Path(path); path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd, temp = tempfile.mkstemp(prefix='.oauth-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def private_json(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise DriveError('OAuth: archivo debe ser privado (chmod 600), sin symlinks',category='drive_config')
    if path.stat().st_size>65536:raise DriveError('Archivo OAuth demasiado grande',category='drive_config')
    doc=json.loads(path.read_bytes())
    if not isinstance(doc,dict):raise DriveError('JSON OAuth debe ser un objeto',category='drive_config')
    return doc


def client_settings(path):
    doc = private_json(path)
    c = doc.get('installed',{})
    if (not isinstance(c,dict) or any(not isinstance(c.get(k),str) or not c[k] for k in ('client_id','client_secret'))
            or c.get('auth_uri') != 'https://accounts.google.com/o/oauth2/auth'
            or c.get('token_uri') != 'https://oauth2.googleapis.com/token'):
        raise DriveError('OAuth: se requiere JSON de cliente Desktop de Google',category='drive_config')
    return c


def classify_error(exc):
    """Read only status/reason, never expose URLs, bodies, credentials or SDK text."""
    from googleapiclient.errors import HttpError
    from google.auth.exceptions import RefreshError
    if isinstance(exc,RefreshError):return 'drive_auth',None
    if isinstance(exc,HttpError):
        status = int(exc.resp.status)
        try:
            body = json.loads(exc.content).get('error',{})
            reasons = {e.get('reason') for e in body.get('errors',[]) if isinstance(e,dict)}
            reasons.update(d.get('reason') for d in body.get('details',[]) if isinstance(d,dict))
        except (ValueError,TypeError,AttributeError):reasons=set()
        if status==429 or reasons & {'rateLimitExceeded','userRateLimitExceeded','quotaExceeded','dailyLimitExceeded','RATE_LIMIT_EXCEEDED','RESOURCE_EXHAUSTED'}:
            return 'drive_quota',status
        if status==401:return 'drive_auth',status
        if status==403:return 'drive_permission',status
        if status==404:return 'drive_missing',status
        if status==409:return 'drive_conflict',status
        if status==410:return 'drive_cursor',status
        if status>=500:return 'drive_transient',status
        return 'drive_request',status
    from google.auth.exceptions import TransportError
    import httplib2
    if isinstance(exc,(OSError,TimeoutError,TransportError,httplib2.HttpLib2Error)):
        return 'drive_transient',None
    return 'drive_request',None


class GoogleDrive:
    def __init__(self, *, folders, state_path, client_file, token_file,
                 service=None, clock=time.time, sleep=time.sleep, interval=1.0):
        self.folders=set(folders)
        if not self.folders or any(not re.fullmatch(r'[A-Za-z0-9_-]+',f) for f in self.folders):
            raise ValueError('Carpetas de Drive inválidas')
        self.state=TransportState(state_path)
        self.client_file,self.token_file=Path(client_file),Path(token_file)
        self.service,self.clock,self.sleep,self.interval=service,clock,sleep,interval
        self.synced=False

    def _folder(self, folder):
        if folder not in self.folders:raise DriveError('Carpeta fuera del catálogo autorizado',category='drive_permission')

    def _pause(self, category, status):
        at=self.clock()
        failures=self.state.get('failures',0)+1
        wait = min(3600,900*2**min(failures-1,2)) if category=='drive_quota' else (
            min(900,60*2**min(failures-1,4)) if category=='drive_transient' else 0)
        until=at+wait if wait else None
        self.state.put('failures',failures)
        self.state.put('last_error',{'category':category,'http_status':status,'at':at})
        if until:self.state.put('pause_until',until)
        return DriveError(f'Google Drive: {category}'+(f' (HTTP {status})' if status else ''),
                          category=category,status=status,retry_at=until)

    def _guard(self):
        until=self.state.get('pause_until',0) or 0
        if self.clock()<until:
            last=self.state.get('last_error',{})
            raise DriveError('Google Drive: pausa persistente '+last.get('category','drive_quota'),
                             category=last.get('category','drive_quota'),retry_at=until)
        if self.state.get('auth_blocked'):
            raise DriveError('Google Drive: drive_auth; renovar autorización',category='drive_auth')

    def _call(self, function, *, missing_ok=False, cursor_ok=False, conflict_ok=False):
        self._guard()
        delay=self.state.get('last_request',0)+self.interval-self.clock()
        if delay>0:self.sleep(delay)
        at=self.clock()
        self.state.put('last_request',at)
        day=datetime.fromtimestamp(at,timezone.utc).date().isoformat()
        counts=self.state.get('requests',{})
        counts[day]=counts.get(day,0)+1
        self.state.put('requests',dict(sorted(counts.items())[-8:]))
        try:
            result=function()
        except DriveError:raise
        except Exception as exc:
            category,status=classify_error(exc)
            if ((category=='drive_missing' and missing_ok) or (category=='drive_cursor' and cursor_ok)
                    or (category=='drive_conflict' and conflict_ok)):
                raise DriveError('Google Drive: '+category,category=category,status=status) from None
            if category=='drive_auth':self.state.put('auth_blocked',True)
            raise self._pause(category,status) from None
        self.state.put('last_success',self.clock())
        self.state.put('pause_until',0)
        self.state.put('failures',0)
        self.state.put('last_error',None)
        return result

    def _service(self):
        if self.service is not None:return self.service
        self._guard()
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from google_auth_httplib2 import AuthorizedHttp
            from googleapiclient.discovery import build
            import httplib2
            settings=client_settings(self.client_file)
            token=private_json(self.token_file)
            if (token.get('client_id')!=settings['client_id'] or token.get('client_secret')!=settings['client_secret']
                    or token.get('token_uri')!='https://oauth2.googleapis.com/token'
                    or not token.get('refresh_token') or SCOPE not in token.get('scopes',[])):
                raise DriveError('OAuth: token no corresponde al cliente o alcance requerido',category='drive_config')
            fingerprint=hashlib.sha256(settings['client_id'].encode()).hexdigest()
            old=self.state.get('client_fingerprint')
            if old and old!=fingerprint:
                raise DriveError('OAuth: usar un estado nuevo al cambiar de cliente',category='drive_config')
            self.state.put('client_fingerprint',fingerprint)
            creds=Credentials.from_authorized_user_info(token,scopes=[SCOPE])
            if not creds.valid:
                from google.auth.exceptions import RefreshError
                try:creds.refresh(Request())
                except RefreshError:
                    self.state.put('auth_blocked',True)
                    raise DriveError('Google Drive: drive_auth; renovar autorización',category='drive_auth') from None
                if private_json(self.token_file)!=token:
                    raise DriveError('OAuth cambió durante la renovación; reintentar con la autorización actual',category='drive_config')
                private_write(self.token_file,creds.to_json().encode())
            http=AuthorizedHttp(creds,http=httplib2.Http(timeout=25))
            service=build('drive','v3',http=http,cache_discovery=False,static_discovery=True)
            # Bind snapshots to the actual Google identity, not just the OAuth app.
            user=self._execute(service.about().get(fields='user(permissionId)'))['user']['permissionId']
            previous=self.state.get('account_id')
            if previous and previous!=user:
                self.service=None
                raise DriveError('Cuenta Google diferente; usar un estado de transporte independiente',category='drive_config')
            self.state.put('account_id',user)
            self.credentials=creds
            self.service=service
            return self.service
        except DriveError:raise
        except (OSError,ValueError,KeyError,TypeError):
            raise DriveError('OAuth propio incompleto; configurar cliente y autorización',category='drive_config') from None

    def _execute(self, request, **options):
        return self._call(lambda:request.execute(num_retries=0),**options)

    @staticmethod
    def _item(meta):
        return {'ID':meta['id'],'Name':meta['name'],'Size':int(meta.get('size',-1)),
                'ModTime':meta.get('modifiedTime'),'Version':meta.get('version'),
                'MimeType':meta.get('mimeType'),'IsDir':False}

    def _get(self, identifier, **options):
        if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',identifier):
            raise DriveError('ID de Drive inválido',category='drive_request')
        fields=FIELDS+',capabilities(canListChildren,canAddChildren)'
        return self._execute(self._service().files().get(fileId=identifier,fields=fields,supportsAllDrives=True),**options)

    def check_folder(self, folder, *, write=False):
        self._folder(folder)
        meta=self._get(folder)
        caps=meta.get('capabilities',{})
        if (meta.get('trashed') or meta.get('mimeType')!='application/vnd.google-apps.folder'
                or not caps.get('canListChildren') or (write and not caps.get('canAddChildren'))):
            raise DriveError('Carpeta inaccesible o sin permisos requeridos',category='drive_permission')

    def begin_cycle(self):
        self.synced=False

    def _checked(self, folder, meta, name=None):
        if (meta.get('trashed') or folder not in meta.get('parents',[]) or meta.get('name')!=name
                or meta.get('mimeType','').startswith('application/vnd.google-apps.')):
            raise DriveError('Archivo movido, sustituido o de tipo no admitido',category='drive_conflict')
        safe_name(meta['name'])
        size=int(meta.get('size',-1))
        if not 0<=size<=MAX_BYTES:raise DriveError('Archivo fuera del límite de 2 MB',category='drive_request')

    def _scan(self, folder, name=None):
        query=f"'{folder}' in parents and trashed = false"
        if name is not None:query+=f" and name = '{safe_name(name)}'"
        files=[]; token=None; seen=set()
        for _ in range(100):
            kwargs=dict(q=query,fields=f'nextPageToken,incompleteSearch,files({FIELDS})',pageSize=1000,
                        spaces='drive',supportsAllDrives=True,includeItemsFromAllDrives=True)
            if token:kwargs['pageToken']=token
            page=self._execute(self._service().files().list(**kwargs))
            if page.get('incompleteSearch'):raise DriveError('Listado incompleto de Drive',category='drive_incomplete')
            files.extend(f for f in page.get('files',[]) if folder in f.get('parents',[]) and not f.get('trashed')
                         and not f.get('mimeType','').startswith('application/vnd.google-apps.'))
            token=page.get('nextPageToken')
            if not token:return files
            if token in seen:break
            seen.add(token)
        raise DriveError('Paginación de Drive incompleta o repetida',category='drive_incomplete')

    def _sync(self):
        if self.synced:return
        service=self._service()
        token=self.state.get('changes_token')
        if token:
            for _ in range(20):
                try:
                    page=self._execute(service.changes().list(pageToken=token,pageSize=1000,spaces='drive',
                        includeRemoved=True,supportsAllDrives=True,includeItemsFromAllDrives=True,
                        fields=f'nextPageToken,newStartPageToken,changes(fileId,removed,file({FIELDS}))'),cursor_ok=True)
                except DriveError as exc:
                    if exc.category!='drive_cursor':raise
                    token=None;break
                following=page.get('nextPageToken') or page.get('newStartPageToken')
                if not following or (page.get('nextPageToken') and following==token):raise DriveError('Cursor de cambios inválido',category='drive_incomplete')
                # Apply only metadata belonging to authorized folder snapshots.
                with self.state.db:
                    for folder in self.folders:
                        snapshot=self.state.get('snapshot:'+folder)
                        if snapshot is None:continue
                        by_id={f['id']:f for f in snapshot}
                        for change in page.get('changes',[]):
                            by_id.pop(change['fileId'],None)
                            f=change.get('file') or {}
                            if (not change.get('removed') and not f.get('trashed') and folder in f.get('parents',[])
                                    and not f.get('mimeType','').startswith('application/vnd.google-apps.')):
                                by_id[f['id']]=f
                        self.state._put('snapshot:'+folder,list(by_id.values()))
                    self.state._put('changes_token',following)
                token=following
                if not page.get('nextPageToken'):
                    self.synced=True;return
            else:raise DriveError('Cambios pendientes; continuar en el siguiente ciclo',category='drive_incomplete')
        if not token:
            start=self._execute(service.changes().getStartPageToken(fields='startPageToken'))['startPageToken']
            with self.state.db:
                for folder in self.folders:self.state.db.execute('DELETE FROM kv WHERE key=?',('snapshot:'+folder,))
                self.state._put('changes_token',start)
            self.synced=True

    def list(self, folder):
        self._folder(folder);self._sync()
        snapshot=self.state.get('snapshot:'+folder)
        if snapshot is None:
            snapshot=self._scan(folder)
            self.state.put('snapshot:'+folder,snapshot)
        return [self._item(m) for m in snapshot]

    def read(self, folder, item):
        self._folder(folder)
        meta=self._get(item['ID'])
        self._checked(folder,meta,item['Name'])
        if item.get('Version') is not None and str(item['Version'])!=str(meta.get('version')):
            raise DriveError('Archivo cambió después del listado; volver a sincronizar',category='drive_conflict')
        from googleapiclient.http import MediaIoBaseDownload
        stream=io.BytesIO()
        download=MediaIoBaseDownload(stream,self._service().files().get_media(fileId=meta['id'],supportsAllDrives=True),chunksize=256*1024)
        done=False
        while not done:
            _,done=self._call(lambda:download.next_chunk(num_retries=0))
            if stream.tell()>MAX_BYTES:raise DriveError('Descarga supera 2 MB',category='drive_request')
        after=self._get(item['ID'])
        self._checked(folder,after,item['Name'])
        raw=stream.getvalue()
        if len(raw)!=int(after['size']) or str(meta.get('version'))!=str(after.get('version')):
            raise DriveError('Archivo cambió durante la lectura',category='drive_conflict')
        return raw

    def _remember(self, folder, meta):
        snapshot=self.state.get('snapshot:'+folder)
        if snapshot is not None:
            self.state.put('snapshot:'+folder,[m for m in snapshot if m['id']!=meta['id']]+[meta])

    def write(self, folder, name, data, *, replace=False):
        self._folder(folder);safe_name(name)
        if not isinstance(data,bytes) or len(data)>MAX_BYTES:raise DriveError('Carga fuera del límite',category='drive_request')
        # Fresh exact-name lookup even when folder snapshots are cached.
        matches=self._scan(folder,name)
        if len(matches)>1:raise DriveError('Nombre duplicado en Drive',category='drive_conflict')
        sha=hashlib.sha256(data).hexdigest()
        if matches:
            meta=matches[0];self._checked(folder,meta,name)
            if self.read(folder,self._item(meta))==data:
                self.state.uploaded(folder,name,meta['id'],sha);self._remember(folder,meta);return
            if not replace:raise DriveError('Archivo inmutable diferente en Drive',category='drive_conflict')
            identifier=meta['id']
        else:
            pending=self.state.upload(folder,name)
            if pending:
                if pending['sha256']!=sha and not replace:raise DriveError('Carga pendiente de otra versión',category='drive_conflict')
                identifier=pending['file_id']
                # A disappeared confirmed file is not silently recreated at a new ID.
                if pending['state']=='confirmed':raise DriveError('Archivo confirmado ya no está en la carpeta',category='drive_conflict')
            else:
                ids=self._execute(self._service().files().generateIds(count=1,space='drive',type='files',fields='ids'))
                identifier=self.state.reserve_upload(folder,name,ids['ids'][0],sha)['file_id']
        from googleapiclient.http import MediaIoBaseUpload
        mime='application/json' if name.endswith(('.json','.semantic')) else 'text/markdown' if name.endswith('.md') else 'application/octet-stream'
        media=MediaIoBaseUpload(io.BytesIO(data),mimetype=mime,resumable=False)
        if matches:
            request=self._service().files().update(fileId=identifier,media_body=media,fields=FIELDS,supportsAllDrives=True)
        else:
            request=self._service().files().create(body={'id':identifier,'name':name,'parents':[folder],'mimeType':mime},
                        media_body=media,fields=FIELDS,supportsAllDrives=True)
        try:self._execute(request,conflict_ok=True)
        except DriveError as exc:
            if exc.category!='drive_conflict':raise
        # An HTTP success or a duplicate-ID response is never enough to confirm.
        # A just-uploaded file can settle to a new version before confirmation.
        # Reconcile at most once by reading; never repeat the remote mutation.
        for attempt in range(2):
            meta=self._get(identifier);self._checked(folder,meta,name)
            try:
                confirmed=self.read(folder,self._item(meta))
            except DriveError as exc:
                if exc.category=='drive_conflict' and attempt==0:continue
                raise
            if confirmed!=data:raise DriveError('No se confirmó contenido subido',category='drive_conflict')
            break
        self.state.uploaded(folder,name,identifier,sha);self._remember(folder,meta)

    def health(self):
        return {'backend':'google-api','oauth_files_present':self.client_file.is_file() and self.token_file.is_file(),
                'last_success':self.state.get('last_success'),'last_error':self.state.get('last_error'),
                'pause_until':self.state.get('pause_until'), 'auth_blocked':self.state.get('auth_blocked',False),
                'drive_api_requests_by_day':self.state.get('requests',{})}

    def close(self):self.state.close()

"""Exercise the real Google SDK against an in-memory HTTP server, never the network."""
from copy import deepcopy
from email import policy
from email.parser import BytesParser
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit

import httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from crbridge.drive import DriveError,MAX_BYTES
from crbridge.google_drive import GoogleDrive,classify_error,client_settings,private_write
from crbridge.transport import make_drive


class Clock:
    def __init__(self):self.value=1800000000.0
    def __call__(self):return self.value
    def sleep(self,seconds):self.value+=seconds


class MemoryHTTP:
    def __init__(self):
        self.files={};self.events=[];self.calls=[];self.serial=0;self.page_size=1000
        self.fail=None;self.lose_create=False;self.hide_once=False
        self.incomplete=False;self.cursor_error=False;self.mutate_download=False;self.settle_upload=False

    def add(self,name='job.json',raw=b'{"hello":"world"}',folder='control',identifier=None):
        identifier=identifier or 'id'+str(len(self.files)+1)
        meta={'id':identifier,'name':name,'size':str(len(raw)),'mimeType':'application/json',
              'modifiedTime':'2026-10-14T00:00:00Z','parents':[folder],'trashed':False,'version':'1'}
        self.files[identifier]=(meta,raw)
        self.events.append({'fileId':identifier,'file':deepcopy(meta)})
        return deepcopy(meta)

    def error(self,status,reason):
        return httplib2.Response({'status':str(status),'content-type':'application/json'}),json.dumps(
            {'error':{'code':status,'message':'private message must not be logged','errors':[{'reason':reason}]}}).encode()

    def request(self,uri,method='GET',body=None,headers=None,**kwargs):
        self.calls.append((method,uri))
        if self.fail:
            status,reason=self.fail;return self.error(status,reason)
        u=urlsplit(uri);q=parse_qs(u.query);headers={k.lower():v for k,v in (headers or {}).items()}
        def response(obj):return httplib2.Response({'status':'200','content-type':'application/json'}),json.dumps(obj).encode()
        if u.path.endswith('/changes/startPageToken'):return response({'startPageToken':'t'+str(len(self.events))})
        if u.path.endswith('/changes'):
            if self.cursor_error:self.cursor_error=False;return self.error(410,'gone')
            i=int(q['pageToken'][0][1:])
            return response({'newStartPageToken':'t'+str(len(self.events)),'changes':self.events[i:]})
        if u.path.endswith('/files/generateIds'):
            self.serial+=1;return response({'ids':['allocated'+str(self.serial)]})
        if method=='GET' and u.path.endswith('/files'):
            query=q['q'][0];folder=re.search(r"'([^']+)' in parents",query)[1]
            name=re.search(r"name = '([^']+)'",query)
            rows=[deepcopy(m) for m,_ in self.files.values() if folder in m['parents'] and not m['trashed'] and (not name or m['name']==name[1])]
            if name and self.hide_once:self.hide_once=False;rows=[]
            start=int(q.get('pageToken',['0'])[0]);end=start+self.page_size
            result={'files':rows[start:end],'incompleteSearch':self.incomplete}
            if end<len(rows):result['nextPageToken']=str(end)
            if self.settle_upload:
                self.settle_upload=False;self.mutate_download=True
            return response(result)
        if method in ('POST','PATCH') and '/upload/drive/v3/files' in u.path:
            if isinstance(body,str):body=body.encode()
            if q.get('uploadType')==['multipart']:
                message=BytesParser(policy=policy.default).parsebytes(('Content-Type: '+headers['content-type']+'\r\n\r\n').encode()+body)
                parts=list(message.iter_parts());meta=json.loads(parts[0].get_payload(decode=True));raw=parts[1].get_payload(decode=True)
            else:meta={};raw=body
            if method=='POST':
                identifier=meta['id']
                if identifier in self.files:return self.error(409,'conflict')
                result=self.add(meta['name'],raw,meta['parents'][0],identifier)
            else:
                identifier=u.path.rsplit('/',1)[1]
                old,_=self.files[identifier];old=deepcopy(old);old['size']=str(len(raw));old['version']=str(int(old['version'])+1)
                self.files[identifier]=(old,raw);self.events.append({'fileId':identifier,'file':deepcopy(old)});result=old
            if method=='POST' and self.lose_create:self.lose_create=False;raise TimeoutError('lost response with secret URL')
            return response(result)
        identifier=u.path.rsplit('/',1)[1]
        if method=='GET' and identifier in self.files:
            meta,raw=self.files[identifier]
            if q.get('alt')==['media']:
                match=re.search(r'bytes=(\d+)-(\d+)',headers.get('range',''))
                a,b=map(int,match.groups()) if match else (0,len(raw)-1)
                end=min(b+1,len(raw));chunk=raw[a:end]
                if self.mutate_download:
                    self.mutate_download=False;meta['version']=str(int(meta['version'])+1)
                return httplib2.Response({'status':'206','content-type':'application/json',
                    'content-range':f'bytes {a}-{end-1}/{len(raw)}','content-length':str(len(chunk))}),chunk
            return response(meta)
        if method=='GET' and '/files/' in u.path:return self.error(404,'notFound')
        raise AssertionError('Unexpected SDK request '+method+' '+u.path)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.http=MemoryHTTP();self.clock=Clock()
        self.network=patch('socket.socket.connect',side_effect=AssertionError('Real network forbidden'))
        self.network.start();self.addCleanup(self.network.stop)
        self.drive=self.open();self.addCleanup(lambda:self.drive.close())

    def open(self):
        service=build('drive','v3',http=self.http,static_discovery=True,cache_discovery=False)
        return GoogleDrive(folders=['control','results'],state_path=self.root/'transport.sqlite',
            client_file=self.root/'client.json',token_file=self.root/'token.json',service=service,
            clock=self.clock,sleep=self.clock.sleep)

    def test_full_listing_pagination_and_bounded_read(self):
        self.http.page_size=1;self.http.add();self.http.add('other.json')
        rows=self.drive.list('control');self.assertEqual(len(rows),2)
        self.assertEqual(self.drive.read('control',rows[0]),b'{"hello":"world"}')

    def test_unchanged_cycle_uses_cursor_without_relisting(self):
        self.http.add();self.drive.list('control');self.drive.close();self.drive=self.open()
        before=len(self.http.calls);self.assertEqual(len(self.drive.list('control')),1)
        calls=self.http.calls[before:]
        self.assertEqual(len(calls),1);self.assertIn('/changes?',calls[0][1])

    def test_change_feed_updates_edits_moves_and_ignores_unrelated_metadata(self):
        m=self.http.add();self.drive.list('control');self.drive.list('results')
        changed=deepcopy(m);changed.update(parents=['results'],version='2')
        self.http.files[m['id']]=(changed,b'{"hello":"world"}')
        self.http.events.append({'fileId':m['id'],'file':changed})
        self.http.add('private-other-folder.json',folder='personal')
        self.drive.close();self.drive=self.open()
        self.assertEqual(self.drive.list('control'),[])
        self.assertEqual(len(self.drive.list('results')),1)
        stored=self.drive.state.get('snapshot:results')
        self.assertNotIn('private-other-folder',json.dumps(stored))

    def test_incomplete_listing_not_persisted_as_complete(self):
        self.http.incomplete=True
        with self.assertRaises(DriveError):self.drive.list('control')
        self.assertIsNone(self.drive.state.get('snapshot:control'))

    def test_invalid_cursor_rebuilds_snapshot(self):
        self.http.add();self.drive.list('control');self.drive.close();self.drive=self.open()
        self.http.cursor_error=True
        self.assertEqual(len(self.drive.list('control')),1)

    def test_quota_pause_survives_restart_and_is_shared_between_components(self):
        self.http.fail=(403,'rateLimitExceeded')
        with self.assertRaises(DriveError) as e:self.drive.list('control')
        self.assertEqual(e.exception.category,'drive_quota')
        self.assertNotIn('private message',str(e.exception))
        calls=len(self.http.calls);self.drive.close();self.drive=self.open();self.http.fail=None
        with self.assertRaises(DriveError):self.drive.list('results')
        self.assertEqual(len(self.http.calls),calls)
        self.clock.sleep(901)
        self.assertEqual(self.drive.list('results'),[])

    def test_permission_denial_is_not_misclassified_as_quota(self):
        self.http.fail=(403,'insufficientFilePermissions')
        with self.assertRaises(DriveError) as e:self.drive.list('control')
        self.assertEqual(e.exception.category,'drive_permission')
        self.assertIsNone(e.exception.retry_at)

    def test_auth_failure_latches_until_explicit_renewal(self):
        self.http.fail=(401,'authError')
        with self.assertRaises(DriveError):self.drive.list('control')
        calls=len(self.http.calls);self.clock.sleep(10000);self.http.fail=None
        with self.assertRaises(DriveError):self.drive.list('results')
        self.assertEqual(len(self.http.calls),calls)

    def test_forbidden_folder_and_invalid_name_never_issue_request(self):
        for action in [lambda:self.drive.list('personal'),lambda:self.drive.write('control','../secret',b'x')]:
            with self.assertRaises(DriveError):action()
        self.assertEqual(self.http.calls,[])

    def test_relocated_oversize_and_native_files_are_not_downloaded(self):
        m=self.http.add();row=self.drive._item(m)
        for change in [{'parents':['personal']},{'size':str(MAX_BYTES+1)},{'mimeType':'application/vnd.google-apps.shortcut'}]:
            self.http.files[m['id']]=(dict(m,**change),b'body')
            with self.assertRaises(DriveError):self.drive.read('control',row)
        self.assertFalse(any('alt=media' in u for _,u in self.http.calls))

    def test_version_change_during_read_rejected(self):
        m=self.http.add();self.http.mutate_download=True
        with self.assertRaises(DriveError):self.drive.read('control',self.drive._item(m))

    def test_immutable_write_and_no_change_rewrite(self):
        self.drive.list('control')
        self.drive.write('control','job.json',b'{"x":1}')
        self.drive.write('control','job.json',b'{"x":1}')
        self.assertEqual(len(self.http.files),1)
        self.assertEqual(sum(m=='POST' for m,_ in self.http.calls),1)
        with self.assertRaises(DriveError):self.drive.write('control','job.json',b'{"x":2}')
        self.drive.write('control','job.json',b'{"x":2}',replace=True)
        self.assertEqual(len(self.http.files),1)
        self.assertEqual(self.drive.read('control',self.drive.list('control')[0]),b'{"x":2}')

    def test_upload_confirmation_reconciles_one_version_change_without_reupload(self):
        self.http.settle_upload=True
        self.drive.write('control','job.json',b'{"x":1}')
        self.assertEqual(sum(m=='POST' for m,_ in self.http.calls),1)
        self.assertEqual(self.drive.state.upload('control','job.json')['state'],'confirmed')
        self.assertEqual(self.drive.read('control',self.drive.list('control')[0]),b'{"x":1}')

    def test_confirmation_never_accepts_changed_content_or_unbounded_conflicts(self):
        for responses in ([DriveError('changed',category='drive_conflict'),b'other'],
                          [DriveError('changed',category='drive_conflict')]*2):
            name='job'+str(self.http.serial)+'.json'
            with patch.object(self.drive,'read',side_effect=responses) as read:
                with self.assertRaises(DriveError):self.drive.write('control',name,b'expected')
                self.assertEqual(read.call_count,2)
            self.assertEqual(self.drive.state.upload('control',name)['state'],'pending')

    def test_uncertain_upload_reuses_preallocated_id_even_when_listing_lags(self):
        self.http.lose_create=True
        with self.assertRaises(DriveError):self.drive.write('control','job.json',b'payload')
        pending=self.drive.state.upload('control','job.json');self.assertEqual(pending['state'],'pending')
        self.clock.sleep(61);self.drive.close();self.drive=self.open();self.http.hide_once=True
        self.drive.write('control','job.json',b'payload')
        self.assertEqual(len(self.http.files),1)
        self.assertEqual(self.http.serial,1)
        self.assertEqual(self.drive.state.upload('control','job.json')['file_id'],pending['file_id'])

    def test_duplicate_names_fail_without_modification(self):
        self.http.add();self.http.add()
        with self.assertRaises(DriveError):self.drive.write('control','job.json',b'x',replace=True)
        self.assertFalse(any(m in ('POST','PATCH') for m,_ in self.http.calls))

    def test_bridge_roundtrip_preserves_contract_and_detects_new_results_on_next_cycle(self):
        from datetime import timedelta
        from unittest.mock import Mock
        from crbridge.core import Bridge,encoded,make_job,now
        from cranalysis.request import load_prompt,load_schema
        fixtures=Path(__file__).resolve().parents[2]/'analysis/tests/fixtures'
        doc=json.loads((fixtures/'entrada-sintetica.json').read_text())['documento']
        doc['video'].update(duration_s=8,published_at=(now()-timedelta(hours=1)).isoformat())
        source=self.root/'transcripts/ejemplo/2026-10-13_ejemplo-sintetico.json'
        source.parent.mkdir(parents=True);source.write_bytes(encoded(doc))
        self.http.add('narrative-analysis.system.md',load_prompt().encode())
        self.http.add('narrative-analysis.schema.json',encoded(load_schema()))
        folders={k:k for k in ('control','pendientes','resultados','ejecuciones')}
        adapter=GoogleDrive(folders=folders.values(),state_path=self.root/'pipeline-transport.sqlite',
            client_file=self.root/'client.json',token_file=self.root/'token.json',service=self.drive.service,
            clock=self.clock,sleep=self.clock.sleep)
        self.addCleanup(adapter.close)
        publish=Mock();bridge=Bridge(self.root,folders,adapter,channels=['ejemplo'],publish=publish)
        self.addCleanup(bridge.close)
        self.assertEqual(bridge.cycle()['errors'],[])
        job=make_job(source,load_prompt(),load_schema())
        analysis=json.loads((fixtures/'salida-sintetica-valida.json').read_text());at=now().isoformat()
        analysis['video'].update(publicado_en=doc['video']['published_at'],analizado_en=at)
        result=dict(job_id=job['job_id'],meta=dict(job['meta'],provider='chatgpt-scheduled',
            analyzed_at=at,status='pendiente_validacion',model=None),analysis=analysis)
        self.http.add(job['job_id']+'.json',encoded(result),folder='resultados')
        report=bridge.cycle()
        self.assertEqual(report['errors'],[])
        self.assertEqual(report['jobs'].get('imported'),1)
        self.assertTrue((self.root/'analysis/ejemplo'/source.name).exists())
        publish.assert_called_once()

    def test_folder_verification_checks_real_permissions_not_empty_list(self):
        m=self.http.add('Control',b'',folder='root',identifier='control')
        m.update(mimeType='application/vnd.google-apps.folder',capabilities={'canListChildren':True,'canAddChildren':False})
        self.http.files['control']=(m,b'')
        self.drive.check_folder('control')
        with self.assertRaises(DriveError):self.drive.check_folder('control',write=True)


class ConfigurationTests(unittest.TestCase):
    def test_factory_keeps_legacy_until_verified_and_never_falls_back_from_bad_marker(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'CR_DRIVE_TRANSPORT':'auto'},clear=True):
            self.assertEqual(type(make_drive(tmp,{'control':'control'})).__name__,'RcloneDrive')
            marker=Path(tmp)/'bridge/drive-transport.json';private_write(marker,b'{"version":1,"backend":"google-api","client_sha256":"bad"}')
            with self.assertRaises(DriveError):make_drive(tmp,{'control':'control'})

    def test_oauth_files_private_and_trusted_endpoints_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'client.json'
            client={'installed':{'client_id':'test','client_secret':'test-secret',
                                'auth_uri':'https://accounts.google.com/o/oauth2/auth',
                                'token_uri':'https://oauth2.googleapis.com/token'}}
            private_write(path,json.dumps(client).encode());self.assertEqual(client_settings(path)['client_id'],'test')
            path.chmod(0o644)
            with self.assertRaises(DriveError):client_settings(path)
            client['installed']['token_uri']='https://evil.test/token'
            private_write(path,json.dumps(client).encode())
            with self.assertRaises(DriveError):client_settings(path)

    def test_failed_verification_does_not_activate_backend(self):
        import contextlib
        from crbridge.oauth import main
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'CR_DATA_DIR':tmp},clear=True),patch(
                'sys.argv',['oauth','activate']),patch('crbridge.oauth.verify',side_effect=DriveError('not ready')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(),1)
            self.assertFalse((Path(tmp)/'bridge/drive-transport.json').exists())

    def test_verified_activation_selects_api_for_future_processes_without_network(self):
        import contextlib
        from crbridge.oauth import main
        with tempfile.TemporaryDirectory() as tmp:
            client=Path(tmp)/'client.json';private_write(client,b'{"installed":{}}')
            with patch.dict('os.environ',{'CR_DATA_DIR':tmp,'CR_DRIVE_CLIENT_FILE':str(client)},clear=True),patch(
                    'sys.argv',['oauth','activate']),patch('crbridge.oauth.verify',return_value={'read_verified':True,'write_verified':True}),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(),0)
                drive=make_drive(tmp,{'control':'control'})
                try:self.assertIsInstance(drive,GoogleDrive)
                finally:drive.close()

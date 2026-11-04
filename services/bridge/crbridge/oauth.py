"""python -m crbridge.oauth authorize|check|activate|status.

One-time Desktop OAuth uses a localhost callback, never a public app route.
Neither credentials nor access/refresh tokens are printed.
"""
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys

from .drive import DriveError
from .google_drive import SCOPE,client_settings,private_write
from .transport import api_drive,paths

REPO=Path(__file__).resolve().parents[3]


def authorize(data,port):
    from google_auth_oauthlib.flow import InstalledAppFlow
    cfg=paths(data)
    settings=client_settings(cfg['client_file'])
    # Construct only trusted endpoints from the validated local Desktop document.
    flow=InstalledAppFlow.from_client_config({'installed':dict(settings,redirect_uris=['http://localhost'])},[SCOPE])
    creds=flow.run_local_server(host='127.0.0.1',port=port,open_browser=False,timeout_seconds=300,
            authorization_prompt_message='Abre esta URL en tu navegador con el túnel local preparado:\n{url}',
            success_message='CryptoReport: autorización recibida. Puedes cerrar esta ventana.',
            access_type='offline',prompt='consent')
    if not creds.refresh_token:raise DriveError('Google no entregó autorización renovable',category='drive_auth')
    private_write(cfg['token_file'],creds.to_json().encode())
    # A fresh explicit consent may clear a previously latched invalid_grant.
    from .transport_state import TransportState
    state=TransportState(cfg['state_path'])
    try:
        state.put('auth_blocked',False);state.put('pause_until',0)
    finally:state.close()
    print(json.dumps({'status':'authorized','token_saved':True,'backend_activated':False}))


def verify(data,folders,write_probe=False):
    drive=api_drive(data,folders)
    try:
        for key in ('control','pendientes','resultados','ejecuciones'):
            drive.check_folder(folders[key],write=key in ('control','pendientes'))
        counts={k:len(drive.list(v)) for k,v in folders.items() if k in ('control','pendientes','resultados','ejecuciones')}
        prompt_name='narrative-analysis.system.md'
        matches=[x for x in drive.list(folders['control']) if x['Name']==prompt_name]
        if len(matches)!=1:raise DriveError('Control: prompt ausente o duplicado',category='drive_conflict')
        # Use the actual canonical prompt loader, never assume a copied path.
        sys.path.insert(0,str(REPO/'services/analysis'))
        from cranalysis.request import load_prompt
        if drive.read(folders['control'],matches[0])!=load_prompt().encode():
            raise DriveError('Control: prompt remoto no coincide con el repo',category='drive_conflict')
        if write_probe:
            # A single managed file in Control; idempotent, not a video/result job.
            raw=json.dumps({'protocol':'drive-api-probe-1','purpose':'Verificación de transporte sin inferencia'},ensure_ascii=False,sort_keys=True).encode()
            drive.write(folders['control'],'transport-api-probe.json',raw)
            found=[i for i in drive.list(folders['control']) if i['Name']=='transport-api-probe.json']
            if len(found)!=1 or drive.read(folders['control'],found[0])!=raw:
                raise DriveError('Prueba de escritura no confirmada',category='drive_conflict')
        return {'status':'ok','backend':'google-api','folders':counts,'read_verified':True,'write_verified':write_probe}
    finally:drive.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['authorize','check','activate','status'])
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--write-probe',action='store_true')
    args=p.parse_args()
    data=Path(os.environ.get('CR_DATA_DIR','/var/lib/cryptoreport-transcripts'))
    folders=json.loads((REPO/'docs/automatizacion-drive/manifest.json').read_text())['folders']
    try:
        if args.command=='status':
            from .transport import make_drive
            cfg=paths(data);selected=make_drive(data,folders)
            try:
                print(json.dumps({'backend':'google-api' if hasattr(selected,'health') else 'rclone',
                    'client_present':cfg['client_file'].is_file(),'token_present':cfg['token_file'].is_file(),
                    'model_api_enabled':False}))
            finally:
                if hasattr(selected,'close'):selected.close()
            return 0
        if args.command=='authorize':
            if not 1024<=args.port<=65535:p.error('Puerto entre 1024 y 65535')
            authorize(data,args.port);return 0
        # Verification/activation cannot race the publisher or extraction.
        data.mkdir(parents=True,exist_ok=True)
        with (data/'run.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                print(json.dumps({'status':'busy','action':'Reintentar al terminar extracción/sincronización'}));return 1
            result=verify(data,folders,write_probe=args.write_probe or args.command=='activate')
            if args.command=='activate':
                # Only switch future cycles after read + write + readback succeed.
                cfg=paths(data)
                marker={'version':1,'backend':'google-api','verified_at':datetime.now(timezone.utc).isoformat(),
                        'client_sha256':hashlib.sha256(cfg['client_file'].read_bytes()).hexdigest()}
                private_write(data/'bridge/drive-transport.json',json.dumps(marker).encode())
                result['activated']=True
                sys.path.insert(0,str(REPO/"services/transcripts"))
                from crtranscripts.observability import record
                record(data,"transport.activated",component="drive",detail={"backend":"google-api"})
            print(json.dumps(result,ensure_ascii=False));return 0
    except Exception as exc:
        print(json.dumps({'status':'error','category':getattr(exc,'category','drive_config'),
            'action':'Revisar OAuth/estado; no se cambió el transporte activo','detail':str(exc) if isinstance(exc,DriveError) else type(exc).__name__}));return 1


if __name__=='__main__':raise SystemExit(main())

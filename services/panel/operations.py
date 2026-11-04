"""Read-only live operations and historical event reconstruction for the panel."""
import fcntl
import json
import sqlite3
import subprocess
import time
from pathlib import Path
from datetime import datetime,timezone
import content
from crtranscripts.observability import read,record,digest


def runtime():
    units=['cryptoreport-transcripts.service','cryptoreport-bridge.service','cryptoreport-bridge.timer',
           'cryptoreport-social.service','cryptoreport-social.timer','cryptoreport-social-maintenance.timer','cron.service']
    fields=['Id','ActiveState','SubState','Result','ExecMainStartTimestamp','ExecMainExitTimestamp','NextElapseUSecRealtime','ExecMainStartTimestampMonotonic']
    try:
        r=subprocess.run(['systemctl','show',*units,*['-p'+x for x in fields]],capture_output=True,text=True,timeout=3)
        services={}
        if r.returncode:raise OSError('systemctl failed')
        for block in r.stdout.strip().split('\n\n'):
            values=dict(line.split('=',1) for line in block.splitlines() if '=' in line)
            if values.get('Id') in units:
                started=int(values.get('ExecMainStartTimestampMonotonic') or 0)
                values['running_for_s']=round(max(0,time.monotonic()-started/1e6)) if started and values.get('ActiveState')=='activating' else None
                services[values.pop('Id')]=values
    except (OSError,subprocess.TimeoutExpired): services={}
    locked=None
    try:
        with (content.DATA/'run.lock').open('r') as handle:
            try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB); locked=False
            except BlockingIOError:locked=True
    except OSError:pass
    extractor=services.get(units[0],{}); bridge=services.get(units[1],{})
    owner='extractor' if locked and extractor.get('ActiveState')=='activating' else 'bridge' if locked and bridge.get('ActiveState')=='activating' else 'unknown' if locked else None
    return {'observed_at':datetime.now(timezone.utc).isoformat(),'services':services,
            'social_scheduler':{'type':'cron','installed':Path('/etc/cron.d/cryptoreport-social').is_file(),'dispatch_minutes':15},
            'pipeline_locked':locked,'probable_owner':owner,
            'bridge_waiting':bool(locked and owner=='extractor'),'live_available':bool(services)}


def transport(status):
    result=dict(status.get('drive_transport') or {'backend':'unknown'})
    target=content.DATA/'bridge/transport.sqlite'
    if result.get('backend')=='google-api' and target.exists():
        conn=None
        try:
            conn=sqlite3.connect('file:'+str(target)+'?mode=ro',uri=True,timeout=3)
            keys={'last_success','last_error','pause_until','auth_blocked','requests'}
            for key,raw in conn.execute('SELECT key,value FROM kv'):
                if key in keys:result['drive_api_requests_by_day' if key=='requests' else key]=json.loads(raw)
            result['journal_read_at']=datetime.now(timezone.utc).isoformat()
        except (OSError,sqlite3.Error,ValueError):result['journal_unavailable']=True
        finally:
            if conn:conn.close()
    result['cycle_report_at']=status.get('generated_at')
    return result


def social_status(name='status.json'):
    """Read current sidecar reports even when the video bridge is waiting."""
    path=content.DATA/'social'/name
    try:
        if path.stat().st_size>2_000_000:raise ValueError()
        doc=json.loads(path.read_bytes())
        if not isinstance(doc,dict):raise ValueError()
        return doc
    except (OSError,ValueError):return {}


def seed_history():
    """Explicit migration; no invented queue times or historical publication dates."""
    for v in content.videos():
        vid=v['id'];a=v.get('analysis') or {};tr=v.get('transcript') or {};job=v.get('job') or {}
        entries=[('video.discovered',v.get('first_seen_at'),{}),
                 ('transcript.available',tr.get('fetched_at'),{'transcript_sha256':tr.get('sha256')}),
                 ('analysis.generated',a.get('analyzed_at'),{'file_id':a.get('source_drive_file_id')}),
                 ('result.validated',a.get('validated_at'),{'error_count':0}),
                 ('analysis.imported',a.get('imported_at'),{'file_id':a.get('source_drive_file_id')}),
                 ('job.'+str(job.get('state')),job.get('updated_at'),{'reason':job.get('detail')})]
        for event,at,detail in entries:
            if not at:continue
            record(content.DATA,event,component='history',video_id=vid,job_id=job.get('job_id'),at=at,
                   detail=detail,provenance='reconstructed',dedupe='history:'+digest([vid,event,at,detail]))
        for destination,key,version_key in (('site','site_analysis','site_analysis_sha256'),('urania','urania_analysis','urania_analysis_sha256')):
            if v['published'].get(key):
                version=v['published'][version_key]
                record(content.DATA,'publication.confirmed',component='publication',video_id=vid,job_id=job.get('job_id'),
                       detail={'destination':destination,'analysis_sha256':version,'source':'existing_export','historical_publish_time':'unknown'},
                       dedupe='baseline:'+destination+':'+vid+':'+version)
    with content.ro(content.DATA/'state.sqlite') as db:
        for attempt in db.execute('SELECT id,video_id,provider,outcome,requests,elapsed_s,at FROM attempts ORDER BY id'):
            record(content.DATA,'transcript.attempt',component='history',video_id=attempt['video_id'],at=attempt['at'],
                   outcome=attempt['outcome'],provenance='reconstructed',dedupe='history:attempt:'+str(attempt['id']),
                   detail={k:attempt[k] for k in ('provider','requests','elapsed_s')})
    jobs={}
    job_db=content.DATA/'bridge/state.sqlite'
    if job_db.exists():
        with content.ro(job_db) as db:
            jobs={r['id']:json.loads(r['payload'])['meta']['video_id'] for r in db.execute('SELECT id,payload FROM jobs')}
    seen=set()
    for artifact in sorted((content.DATA/'bridge/cache').glob('*.bin')):
        try:receipt=json.loads(artifact.read_bytes())
        except (ValueError,OSError):continue
        if not isinstance(receipt,dict) or not all(k in receipt for k in ('run_id','started_at','finished_at','attempted_job_ids','uploaded_job_ids')):continue
        if receipt['run_id'] in seen:continue
        seen.add(receipt['run_id'])
        for job_id in receipt['attempted_job_ids']:
            for event,key in (('schedule.started','started_at'),('schedule.finished','finished_at')):
                record(content.DATA,event,component='schedule',video_id=jobs.get(job_id),job_id=job_id,run_id=receipt['run_id'],
                       at=receipt[key],provenance='reported',outcome='ok' if job_id in receipt['uploaded_job_ids'] else 'error',
                       detail={'declared_status':receipt.get('status'),'uploaded':job_id in receipt['uploaded_job_ids'],
                               'errors':receipt.get('errors',[]),'source':'server_receipt_cache'},
                       dedupe=event+':'+receipt['run_id']+':'+job_id)
    marker=content.DATA/'bridge/drive-transport.json'
    if marker.exists():
        m=json.loads(marker.read_text())
        if m.get('verified_at'):record(content.DATA,'transport.activated',component='drive',at=m['verified_at'],
            provenance='reconstructed',detail={'backend':m.get('backend')},dedupe='history:drive-activation:'+m['verified_at'])


def event_page(video_id=None,before=None):
    return read(content.DATA,video_id=video_id,before=before,limit=100)

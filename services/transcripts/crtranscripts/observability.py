"""Local append-only operational events; no source text, credentials or model calls."""
from __future__ import annotations
import contextvars
RUN_ID=contextvars.ContextVar("pipeline_run_id",default=None)

import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items() if not re.search(r'token|secret|password|credential|authorization|cookie',str(k),re.I)}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value[:100]]
    if isinstance(value, str):
        value = re.sub(r'https?://\S+', '[URL omitida]', value)
        value = re.sub(r'(?i)(bearer\s+|ya29\.|1//)[A-Za-z0-9._~+/=-]+', '[secreto omitido]', value)
        return value[:1000]
    return value


def path(data):
    return Path(data)/'observability'/'events.sqlite'


def connect(data):
    target=path(data); target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    conn=sqlite3.connect(target,timeout=10); conn.row_factory=sqlite3.Row
    os.chmod(target,0o600)
    conn.executescript('''PRAGMA journal_mode=WAL;
      CREATE TABLE IF NOT EXISTS events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
        at TEXT NOT NULL, recorded_at TEXT NOT NULL, component TEXT NOT NULL, event TEXT NOT NULL,
        video_id TEXT, job_id TEXT, run_id TEXT, outcome TEXT NOT NULL, provenance TEXT NOT NULL,
        detail TEXT NOT NULL, dedupe TEXT UNIQUE);
      CREATE INDEX IF NOT EXISTS events_video ON events(video_id,seq);
      CREATE TABLE IF NOT EXISTS publications (destination TEXT, video_id TEXT, hash TEXT,
        PRIMARY KEY(destination,video_id));''')
    return conn


def record(data, event, *, component='bridge', video_id=None, job_id=None, run_id=None,
           outcome='ok', detail=None, at=None, provenance='observed', dedupe=None):
    """Idempotent when a source identity is supplied; never fabricate missing dates."""
    try:
        at=at or stamp()
        run_id=run_id or RUN_ID.get() or os.environ.get("CR_OBSERVABILITY_RUN_ID")
        parsed=datetime.fromisoformat(at.replace('Z','+00:00'))
        if parsed.tzinfo is None: raise ValueError('timestamp must include timezone')
        at=parsed.astimezone(timezone.utc).isoformat()
        with connect(data) as conn:
            conn.execute('INSERT OR IGNORE INTO events VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (uuid.uuid4().hex,at,stamp(),component,event,video_id,job_id,run_id,outcome,
                          provenance,json.dumps(clean(detail or {}),ensure_ascii=False,allow_nan=False),dedupe))
        conn.close()
        return True
    except (OSError,sqlite3.Error,ValueError,TypeError):
        print('[observability] event persistence failed',file=sys.stderr)
        return False


def read(data, *, video_id=None, before=None, limit=100):
    target=path(data)
    if not target.exists(): return {'events':[], 'next_before':None, 'available':False}
    limit=max(1,min(int(limit),200)); clauses=[];args=[]
    if video_id is not None: clauses.append('video_id=?');args.append(video_id)
    if before is not None: clauses.append('seq<?');args.append(int(before))
    where=' WHERE '+' AND '.join(clauses) if clauses else ''
    conn=sqlite3.connect('file:'+str(target)+'?mode=ro',uri=True,timeout=5);conn.row_factory=sqlite3.Row
    try: rows=conn.execute('SELECT * FROM events'+where+' ORDER BY seq DESC LIMIT ?',(*args,limit+1)).fetchall()
    finally:conn.close()
    more=len(rows)>limit; result=[]
    for row in rows[:limit]:
        item=dict(row);item['detail']=json.loads(item['detail']);item.pop('dedupe');result.append(item)
    return {'events':result,'next_before':result[-1]['seq'] if more else None,'available':True}


def published(data, destination, versions, *, at=None, provenance='observed'):
    """Called only AFTER atomic export. One event per changed visible analysis version."""
    try:
        conn=connect(data)
        try:
            with conn:
                old={r['video_id']:r['hash'] for r in conn.execute('SELECT video_id,hash FROM publications WHERE destination=?',(destination,))}
                for vid in set(old)|set(versions):
                    version=versions.get(vid)
                    if old.get(vid)==version:continue
                    event='analysis.published' if version else 'analysis.unpublished'
                    # Same transaction as the cursor; a crash cannot lose the event.
                    conn.execute('INSERT INTO events VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?,NULL)',
                       (uuid.uuid4().hex,at or stamp(),stamp(),'publication',event,vid,None,RUN_ID.get() or os.environ.get('CR_OBSERVABILITY_RUN_ID'),'ok',provenance,
                        json.dumps({'destination':destination,'analysis_sha256':version})))
                    if version:conn.execute('INSERT OR REPLACE INTO publications VALUES(?,?,?)',(destination,vid,version))
                    else:conn.execute('DELETE FROM publications WHERE destination=? AND video_id=?',(destination,vid))
        finally:conn.close()
    except (OSError,sqlite3.Error,ValueError,TypeError):
        print('[observability] publication event persistence failed',file=sys.stderr)


def progress(data):
    target=path(data)
    if not target.exists():return {}
    conn=sqlite3.connect('file:'+str(target)+'?mode=ro',uri=True,timeout=5)
    try:
        result={}
        for job,event,at,outcome in conn.execute("SELECT job_id,event,at,outcome FROM events WHERE job_id IS NOT NULL AND event IN ('result.detected','result.received','result.validated','result.rejected','analysis.imported') ORDER BY seq"):
            result[job]={'event':event,'at':at,'outcome':outcome}
        return result
    finally:conn.close()

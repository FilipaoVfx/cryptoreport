"""Narrative analysis via subscription CLIs (Claude Code or Codex); never an API key."""
import argparse
from datetime import datetime,timedelta,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import uuid

from .request import load_prompt,load_schema,build_payload,sha256
from .config import PROMPT_VERSION
from .validate import validate,_norm
from .openai_client import openai_schema

REPO=Path(__file__).resolve().parents[3]
DATA=Path('/var/lib/cryptoreport-transcripts')
MODEL='gpt-6-luna'
CLAUDE_MODEL='claude-sonnet-5'
MAX_OUTPUT_TOKENS=64000
CLI_TIMEOUT=2700
DEFAULT_EXECUTOR='codex'
DAILY_LIMIT=16


def retryable(entry):
    error=entry.get('error','')
    return entry.get('status')=='blocked' and error.startswith(('quota','rate','executor','TimeoutExpired','OSError','daily_limit'))


def health(data=DATA):
    """Read-only health for the pipeline monitor; never includes source text."""
    path=data/'analysis-plan/status.json'
    if not path.exists():return {'available':False,'autonomous':False,'warnings':[]}
    try:
        state=json.loads(path.read_text());recent=candidates(data);queued=candidates(data,backlog=True);accepted=set()
        for id,source,raw in queued:
            target=data/'analysis'/Path(source).parent.name/Path(source).name
            if not target.exists():continue
            meta=json.loads(target.read_text()).get('meta',{});expected=json.loads(raw).get('meta',{})
            if meta.get('job_id')==id and meta.get('validation',{}).get('ok') and meta.get('transcript_sha256')==expected.get('transcript_sha256'):accepted.add(id)
        pending={r[0] for r in queued}-accepted;recent_count=sum(r[0] not in accepted for r in recent)
        day=now().astimezone(timezone(timedelta(hours=-5))).date().isoformat()
        attempts=state.get('daily',{}).get(day,0)
        review=[id for id,e in state.get('jobs',{}).items() if id in pending and
                (e.get('status')=='invalid' or e.get('status')=='blocked' and e.get('attempts',0)>=min(e.get('attempt_limit',2),3))]
        recent_ids={r[0] for r in recent}
        review_recent=sum(id in recent_ids for id in review)
        warnings=[];status=state.get('status');last=state.get('last_dispatch_at')
        autonomous=state.get('scheduler')=='systemd'
        if autonomous:
            if state.get('paused_by_user'):warnings.append('Análisis pausado por el usuario')
            elif status in ('auth_blocked','paused'):warnings.append('Analista del plan detenido: '+str(state.get('last_error') or status))
            if pending and attempts>=DAILY_LIMIT:warnings.append('Analista del plan alcanzó el límite diario de intentos')
            active=state.get('active_attempt') or {}
            active_until=(datetime.fromisoformat(active['started_at'])+timedelta(seconds=active.get('timeout_seconds',2700)+300)) if active.get('started_at') else None
            running_on_time=status=='running' and active_until and now()<=active_until
            if pending and not running_on_time and (not last or now()-datetime.fromisoformat(last)>timedelta(minutes=40)):
                warnings.append('Analista del plan sin despacho reciente (40 min)')
            if review:warnings.append(f'{len(review)} análisis pendientes requieren revisión tras agotar intentos')
        return {'available':True,'autonomous':autonomous,'status':status,'executor':state.get('executor') or DEFAULT_EXECUTOR,
                'model_requested':state.get('model_requested') or MODEL,'effort':'max',
                'billing':state.get('billing') or EXECUTORS[DEFAULT_EXECUTOR]['billing'],'api_fallback':False,
                'last_dispatch_at':last,'finished_at':state.get('finished_at'),
                'pause_until':state.get('pause_until'),'providers':state.get('providers',{}),
                'last_failover':state.get('last_failover'),'last_validated_at':state.get('last_validated_at'),'pending_48h':recent_count,'pending_backlog':len(pending)-recent_count,
                'stored_waiting_sync':len(accepted),'requires_review':len(review),
                'requires_review_48h':review_recent,'scope':state.get('scope','backlog'),
                'attempts_today':attempts,'daily_limit':DAILY_LIMIT,'warnings':warnings}
    except (OSError,ValueError,sqlite3.Error,TypeError):
        return {'available':False,'autonomous':False,'warnings':['No se pudo leer el estado del analista del plan']}


def now():return datetime.now(timezone.utc)


def atomic(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.plan-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(obj,stream,ensure_ascii=False,allow_nan=False);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def private_env():
    # Do not inherit model/extraction/Drive credentials from the worker's parent.
    names={'HOME','PATH','LANG','LC_ALL','TZ','USER','LOGNAME','CODEX_HOME','CLAUDE_CONFIG_DIR','SSL_CERT_FILE','SSL_CERT_DIR','HTTPS_PROXY','HTTP_PROXY','ALL_PROXY','NO_PROXY'}
    return {k:v for k,v in os.environ.items() if k in names}


def controls(analysis,payload,schema):
    errors=validate(analysis,payload,schema)
    if errors:return errors
    video=payload['documento']['video'];out=analysis['video']
    if out['titulo']!=video['title'] or out['publicado_en']!=video['published_at'] or out['analizado_en']!=payload['analizado_en']:
        errors.append('Identidad, fecha o título no coincide')
    segments=payload['documento']['transcript']['segments']
    for e in analysis['evidencias']:
        if e['origen']!='transcripcion':continue
        m=re.fullmatch(r'segments\[(\d+):(\d+)\]',e.get('localizador') or '')
        if not m:errors.append(e['id']+': usa localizador segments[i:j]');continue
        i,j=map(int,m.groups())
        if not 0<=i<j<=len(segments):errors.append(e['id']+': rango fuera del material');continue
        a,b=segments[i]['start'],segments[j-1]['start']+segments[j-1]['dur']
        if (e['inicio_s'] is None or e['fin_s'] is None or abs(e['inicio_s']-a)>.05 or abs(e['fin_s']-b)>.05
                or not e['cita'] or _norm(e['cita']) not in _norm(' '.join(s['text'] for s in segments[i:j]))):
            errors.append(e['id']+': cita/tiempos no coinciden con rango exacto')
    return errors


def bind_citations(analysis,payload):
    """Derive indices/times from literal text; never rewrite a quotation.

    An already matching explicit range is an anchor even for repeated text.
    Otherwise require exactly one occurrence in the entire transcript.
    Ambiguous or nonliteral quotes remain untouched for strict validation.
    """
    segments=payload['documento']['transcript']['segments']
    parts=[];bounds=[];offset=0
    for i,seg in enumerate(segments):
        text=_norm(seg['text'])
        if not text:continue
        parts.append(text);bounds.append((offset,offset+len(text),i));offset+=len(text)+1
    text=' '.join(parts);repairs=[]
    for evidence in analysis.get('evidencias',[]):
        if evidence.get('origen')!='transcripcion' or not evidence.get('cita'):continue
        quote=_norm(evidence['cita']);m=re.fullmatch(r'segments\[(\d+):(\d+)\]',evidence.get('localizador') or '')
        span=None
        if m:
            i,j=map(int,m.groups())
            chunks=[s.strip() for s in re.split(r'\.{3}|…',quote)]
            # Restore omitted source words only inside the model's bounded
            # anchor, with each chunk literal, unique, and in original order.
            # The final validator still requires a contiguous literal quote.
            if 0<=i<j<=len(segments) and j-i<=20 and len(chunks)>1 and all(len(c)>=12 for c in chunks):
                original=' '.join(s['text'] for s in segments[i:j]);window=_norm(original);cursor=0;matches=True
                for chunk in chunks:
                    hit=window.find(chunk)
                    if hit<cursor or hit<0 or window.find(chunk,hit+1)>=0:matches=False;break
                    cursor=hit+len(chunk)
                if matches:
                    repairs.append({'evidencia_id':evidence.get('id'),'before':{'cita':evidence['cita']},'after':{'cita':original},'method':'restore_literal_omission_in_anchored_segments'})
                    evidence['cita']=original;quote=_norm(original)
            if 0<=i<j<=len(segments) and quote in _norm(' '.join(s['text'] for s in segments[i:j])):span=(i,j)
        if span is None:
            hit=text.find(quote)
            if hit<0 or text.find(quote,hit+1)>=0:continue
            left=next((i for a,b,i in bounds if a<=hit<b),None)
            right=next((i for a,b,i in bounds if a<hit+len(quote)<=b),None)
            if left is None or right is None:continue
            span=(left,right+1)
        i,j=span
        fields={'localizador':f'segments[{i}:{j}]','inicio_s':segments[i]['start'],'fin_s':segments[j-1]['start']+segments[j-1]['dur']}
        before={k:evidence.get(k) for k in fields}
        if before!=fields:
            evidence.update(fields);repairs.append({'evidencia_id':evidence.get('id'),'before':before,'after':fields,'method':'literal_transcript_span'})
    return repairs


def invoke(prompt,schema,work,system_prompt):
    schema_path=work/'schema.json';schema_path.write_text(json.dumps(openai_schema(schema)))
    output=work/'analysis.json'
    args=['/root/.local/bin/codex','exec','--ignore-user-config','--ephemeral','--skip-git-repo-check',
          '--sandbox','read-only','--disable','shell_tool','--disable','multi_agent','--disable','skill_search',
          '-c','forced_login_method="chatgpt"','-c','model_reasoning_effort="max"',
          '-c','developer_instructions='+json.dumps(system_prompt,ensure_ascii=False),
          '--model',MODEL,'--cd',str(work),'--output-schema',str(schema_path),'--output-last-message',str(output),'--json','-']
    result=subprocess.run(args,input=prompt,text=True,capture_output=True,timeout=900,env=private_env())
    usage=None; failure=None
    for line in result.stdout.splitlines():
        try:event=json.loads(line)
        except ValueError:continue
        if event.get('type')=='turn.completed':usage=event.get('usage')
        if event.get('type') in ('error','turn.failed'):
            failure=event.get('message') or event.get('error',{}).get('message')
    if result.returncode or not output.exists():
        message=(result.stderr+result.stdout).lower()
        kind='quota' if any(w in message for w in ('usage limit','rate limit','quota','try again at')) else 'executor'
        # Error text is operational evidence, never a dump of the environment.
        raise RuntimeError(kind+(': '+str(failure)[:600] if failure else ''))
    return json.loads(output.read_text()),usage


def codex_auth():
    """ChatGPT session of the Codex CLI; an API key must never pay for an analysis."""
    try:auth=subprocess.run(['/root/.local/bin/codex','login','status'],capture_output=True,text=True,timeout=15,env=private_env())
    except (OSError,subprocess.TimeoutExpired):return False,'No se pudo comprobar la sesión de Codex'
    if auth.returncode or 'using ChatGPT' not in auth.stdout+auth.stderr:
        return False,'Se requiere sesión ChatGPT; no se admite autenticación API'
    return True,'sesión ChatGPT'


def claude_auth():
    """Claude Code subscription session, checked on disk: no call, no quota spent."""
    if os.environ.get('ANTHROPIC_API_KEY'):return False,'Hay ANTHROPIC_API_KEY en el entorno; el análisis solo usa la suscripción'
    home=Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path(os.environ.get('HOME','/root'))/'.claude')
    try:session=(json.loads((home/'.credentials.json').read_text()) or {}).get('claudeAiOauth') or {}
    except (OSError,ValueError):return False,'Se requiere sesión de Claude Code; no se admite autenticación API'
    if not session.get('subscriptionType') or 'user:inference' not in (session.get('scopes') or []):
        return False,'La sesión de Claude Code no habilita inferencia por suscripción'
    expiry=session.get('refreshTokenExpiresAt')
    try:expired=bool(expiry) and float(expiry)/1000<=now().timestamp()
    except (TypeError,ValueError):expired=False
    if expired:return False,'La sesión de Claude Code caducó; vuelve a iniciarla'
    return True,'suscripción '+str(session['subscriptionType'])


def cli_timeout():
    """Seconds per model turn. A max-effort analysis of a long video takes
    twenty to thirty minutes, so the bound protects against a hung CLI, not
    against slowness; the service window must stay above limit x attempts."""
    try:value=int(os.environ.get('CR_ANALYSIS_CLI_TIMEOUT') or CLI_TIMEOUT)
    except ValueError:return CLI_TIMEOUT
    return min(max(value,600),5400)


def claude_stream(stdout):
    """Rebuild the answer from the event stream and keep the final envelope.

    A long analysis can arrive split across several assistant messages: only
    their concatenation is the complete document, so the last message alone is
    not a valid output.
    """
    parts=[];envelope={}
    for line in stdout.splitlines():
        try:event=json.loads(line)
        except ValueError:continue
        if not isinstance(event,dict):continue
        if event.get('type')=='assistant':
            parts+=[block.get('text') or '' for block in (event.get('message') or {}).get('content') or []
                    if isinstance(block,dict) and block.get('type')=='text']
        elif event.get('type')=='result':envelope=event
    return ''.join(parts) or (envelope.get('result') or ''),envelope,len(parts)


def invoke_claude(prompt,schema,work,system_prompt):
    """Claude Code CLI on the user's subscription: no tools, no API key, strict JSON."""
    system=(system_prompt+'\n\n## Formato de salida de esta ejecución\n'
            'Responde ÚNICAMENTE con el objeto JSON del análisis: sin texto antes o después, sin bloques de código '
            'y sin comentarios. Debe cumplir exactamente este esquema, con todas sus claves obligatorias:\n'
            +json.dumps(schema,ensure_ascii=False))
    args=['/usr/bin/claude','--print','--model',CLAUDE_MODEL,'--effort','max','--output-format','stream-json','--verbose',
          '--system-prompt',system,'--exclude-dynamic-system-prompt-sections','--allowed-tools','',
          '--setting-sources','','--strict-mcp-config','--disable-slash-commands','--no-session-persistence']
    result=subprocess.run(args,input=prompt,text=True,capture_output=True,timeout=cli_timeout(),cwd=str(work),
                          env=dict(private_env(),CLAUDE_CODE_MAX_OUTPUT_TOKENS=str(MAX_OUTPUT_TOKENS)))  # noqa: E501
    text,envelope,messages=claude_stream(result.stdout)
    body=text[text.find('{'):text.rfind('}')+1] if '{' in text else ''
    analysis=None
    if body:
        try:analysis=json.loads(body)
        except ValueError:analysis=None
    if result.returncode or not isinstance(analysis,dict):
        failure=envelope.get('api_error_status') or (text[:300] if envelope.get('is_error') else '')
        message=(str(failure)+result.stderr+text[:300]).lower()
        # Un rechazo del proveedor (429/529) no es lo mismo que agotar la cuota del
        # plan: espera corta en el primero, larga en el segundo, y en ninguno de los
        # dos hubo inferencia que cobrarle al trabajo.
        if any(w in message for w in ('usage limit','quota','try again at')):kind='quota'
        elif any(w in message for w in ('429','529','rate limit','overloaded')):kind='rate'
        else:kind='executor'
        # Operational evidence only: sizes and status, never the source material.
        detail=str(failure)[:200] if failure else f'salida sin JSON completo ({len(text)} caracteres en {messages} mensajes)'
        raise RuntimeError(kind+': '+detail)
    reported=envelope.get('usage') or {}
    usage={k:reported[k] for k in ('input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens') if k in reported}
    return analysis,usage or None


# Subscription executors only; the registry never includes a paid model API.
EXECUTORS={'codex':{'model':MODEL,'provider':'codex-chatgpt-plan','billing':'chatgpt_plan',
                    'auth':lambda:codex_auth(),'invoke':lambda *args:invoke(*args)},
           'claude':{'model':CLAUDE_MODEL,'provider':'claude-code-plan','billing':'claude_plan',
                     'auth':lambda:claude_auth(),'invoke':lambda *args:invoke_claude(*args)}}


def executors():
    """Configured order; the first executor with a live subscription session runs."""
    raw=os.environ.get('CR_ANALYSIS_EXECUTOR') or DEFAULT_EXECUTOR
    names=[name for name in (part.strip() for part in raw.split(',')) if name in EXECUTORS]
    return names or [DEFAULT_EXECUTOR]


def select_executor(state, excluded=()):
    """Only authenticated subscription CLIs outside their own cooldown."""
    refused=[];cooldowns=[]
    for name in dict.fromkeys(executors()):
        if name in excluded:continue
        provider=state.get('providers',{}).get(name,{})
        until=provider.get('pause_until')
        if until and datetime.fromisoformat(until)>now():
            cooldowns.append(until);continue
        allowed,detail=EXECUTORS[name]['auth']()
        if allowed:return name,refused,cooldowns
        refused.append(name+': '+detail)
    return None,refused,cooldowns


def invoke_available(state,state_path,request,schema,work,prompt):
    """Fail over only explicit provider rejections, never invalid evidence.

    Rejections produce no result and consume no job attempt. Each provider is
    tried at most once here; cooldowns survive crashes and subsequent dispatches.
    """
    tried=set()
    while True:
        name=state['executor'];tried.add(name)
        state['active_attempt']={'executor':name,'started_at':now().isoformat(),
                                 'timeout_seconds':cli_timeout() if name=='claude' else 900}
        atomic(state_path,state)
        try:
            result=EXECUTORS[name]['invoke'](request,schema,work,prompt)
        except RuntimeError as exc:
            kind=str(exc).split(':',1)[0]
            if kind not in ('rate','quota'):raise
            provider=state.setdefault('providers',{}).setdefault(name,{})
            failures=provider.get('consecutive_failures',0)+1
            minutes=360 if kind=='quota' else min(120,30*2**min(failures-1,2))
            provider.update(consecutive_failures=failures,last_error=str(exc)[:300],
                            failed_at=now().isoformat(),pause_until=(now()+timedelta(minutes=minutes)).isoformat())
            atomic(state_path,state)
            chosen,_,_=select_executor(state,tried)
            if not chosen:raise
            runner=EXECUTORS[chosen]
            state.update(executor=chosen,model_requested=runner['model'],billing=runner['billing'],
                         last_failover={'from':name,'to':chosen,'at':now().isoformat(),'reason':kind})
            atomic(state_path,state)
            continue
        state.setdefault('providers',{})[name]={'consecutive_failures':0,'pause_until':None,'last_success_at':now().isoformat()}
        atomic(state_path,state)
        return result


def authorized_retry(data,job_id,entry):
    """Operator authorization (crbridge retry) clears one bounded local refusal."""
    if entry.get('status') not in ('invalid','blocked','cancelled_by_user'):return False
    db=sqlite3.connect('file:'+str(data/'bridge/state.sqlite')+'?mode=ro',uri=True)
    try:row=db.execute("SELECT value FROM kv WHERE key='retry_authorizations'").fetchone()
    except sqlite3.Error:return False
    finally:db.close()
    if not row:return False
    try:grant=(json.loads(row[0]) or {}).get(job_id)
    except ValueError:return False
    if not grant or not grant.get('authorized_at'):return False
    finished=entry.get('finished_at')
    try:return not finished or datetime.fromisoformat(grant['authorized_at'])>datetime.fromisoformat(finished)
    except (TypeError,ValueError):return False


def candidates(data,today=False,backlog=False):
    cutoff=now().astimezone(timezone(timedelta(hours=-5))).replace(hour=0,minute=0,second=0,microsecond=0) if today else now()-timedelta(hours=48)
    db=sqlite3.connect('file:'+str(data/'bridge/state.sqlite')+'?mode=ro',uri=True)
    try:
        rows=db.execute("SELECT id,source,payload,published_at FROM jobs WHERE state IN ('uploaded','queued')").fetchall()
        date=lambda r:datetime.fromisoformat(r[3].replace('Z','+00:00'))
        rows=sorted((r for r in rows if date(r)<=now() and (date(r)>=cutoff or backlog and not today)),key=lambda r:(date(r)<cutoff,date(r)))
        rows=[r[:3] for r in rows]
    finally:db.close()
    return rows


def promote(data,ready_path):
    from crtranscripts.observability import record
    with (data/'run.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return False
        result=json.loads(ready_path.read_text());meta=result['meta'];source=Path(meta['transcript_file']).resolve()
        if not source.is_relative_to((data/'transcripts').resolve()) or hashlib.sha256(source.read_bytes()).hexdigest()!=meta['transcript_sha256']:
            ready_path.rename(ready_path.with_suffix('.superseded'));return False
        row=None
        with sqlite3.connect(data/'bridge/state.sqlite') as db:
            row=db.execute('SELECT payload,state FROM jobs WHERE id=?',(meta['job_id'],)).fetchone()
        if not row or row[1]=='superseded':
            ready_path.rename(ready_path.with_suffix('.superseded'));return False
        job=json.loads(row[0])
        if (any(meta.get(k)!=v for k,v in job['meta'].items())
                or meta.get('prompt_sha256')!=sha256(load_prompt())
                or meta.get('schema_sha256')!=sha256(json.dumps(load_schema(),sort_keys=True))
                or controls(result['analysis'],build_payload(json.loads(source.read_text()),meta['analyzed_at']),load_schema())):
            raise ValueError('Resultado preparado no supera los controles de procedencia o citas')
        target=data/'analysis'/meta['channel']/source.name
        if target.exists():
            old=json.loads(target.read_text())
            if old!=result:raise ValueError('No se sobrescribe un análisis existente distinto')
        # Same shared lock as the bridge. Persist the publication intent before
        # removing ready: a restart can safely finish this handoff.
        with sqlite3.connect(data/'bridge/state.sqlite') as db:
            db.execute("INSERT OR REPLACE INTO kv(key,value) VALUES ('publish_dirty','true')")
        if not target.exists():atomic(target,result)
        record(data,'analysis.generated',component='analysis_plan',video_id=meta['video_id'],detail={'provider':meta['provider'],'model_requested':meta.get('model_requested') or MODEL,'billing':meta.get('billing') or EXECUTORS[DEFAULT_EXECUTOR]['billing']})
        ready_path.unlink();return True


def reconcile_ready(data,state):
    """Finish a handoff delayed by extraction/Drive holding the shared lock."""
    promoted=0
    for ready in (data/'analysis-plan').glob('*.ready.json'):
        result=json.loads(ready.read_text());job_id=result['meta']['job_id']
        if promote(data,ready) and job_id in state.get('jobs',{}):
            state['jobs'][job_id].update(status='ok',finished_at=now().isoformat())
            promoted+=1
    # A separately invoked promoter may already have finished the handoff.
    for job_id,entry in state.get('jobs',{}).items():
        if entry.get('status')!='ready':continue
        db=sqlite3.connect('file:'+str(data/'bridge/state.sqlite')+'?mode=ro',uri=True)
        try:row=db.execute('SELECT source FROM jobs WHERE id=?',(job_id,)).fetchone()
        finally:db.close()
        if not row:continue
        source=Path(row[0]);target=data/'analysis'/source.parent.name/source.name
        if not target.exists():continue
        saved=json.loads(target.read_text());meta=saved.get('meta',{})
        if meta.get('job_id')==job_id and meta.get('validation',{}).get('ok'):
            entry.update(status='ok',finished_at=entry.get('finished_at') or now().isoformat())
    return promoted


def request_publication():
    # The durable publish_dirty flag is the source of truth, not this hint.
    # Failure to start the bridge must not invalidate a generated analysis.
    try:return subprocess.run(['/usr/bin/systemctl','start','--no-block','cryptoreport-bridge.service'],capture_output=True,timeout=15).returncode==0
    except (OSError,subprocess.TimeoutExpired):return False


def run(data=DATA,limit=2,today=False,resume=False,backlog=False):
    sys.path.insert(0,str(REPO/'services/transcripts'))
    from crtranscripts.quality import assess
    from crtranscripts.observability import record as event
    root=data/'analysis-plan';root.mkdir(parents=True,exist_ok=True)
    with (root/'run.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'status':'busy'}
        state_path=root/'status.json'
        state=json.loads(state_path.read_text()) if state_path.exists() else {'version':1,'daily':{},'jobs':{}}
        if resume:
            state.update(paused_by_user=False,status='idle',pause_until=None,last_error=None,resumed_at=now().isoformat())
            atomic(state_path,state)
        if state.get('paused_by_user'):return {'status':'paused_by_user','billing':EXECUTORS[executors()[0]]['billing'],'api_fallback':False}
        run_id=uuid.uuid4().hex
        state['last_dispatch_at']=now().isoformat();state['effort']='max';state['api_fallback']=False
        state['scope']='today' if today else 'backlog' if backlog else '48h'
        state['finished_at']=None
        if os.environ.get('CR_ANALYSIS_SCHEDULER')=='systemd':state['scheduler']='systemd'
        atomic(state_path,state)
        # Stored, validated work can be published even if the model session expired.
        if reconcile_ready(data,state):request_publication()
        # Migrate the old global provider pause without lifting its cooldown.
        if not state.get('providers') and state.get('pause_until') and str(state.get('last_error','')).startswith(('rate','quota')):
            old=state.get('executor',executors()[0])
            state['providers']={old:{'pause_until':state['pause_until'],'last_error':state['last_error'],'consecutive_failures':1}}
        chosen,refused,cooldowns=select_executor(state)
        if not chosen:
            state.update(status='paused' if cooldowns else 'auth_blocked',
                         pause_until=min(cooldowns) if cooldowns else None,finished_at=now().isoformat())
            if not cooldowns:state['last_error']='; '.join(refused) or 'Sin ejecutor de suscripción disponible'
            atomic(state_path,state);request_publication()
            return state
        # Non-provider pauses (technical failure/daily limits) retain their bounds.
        if state.get('pause_until') and datetime.fromisoformat(state['pause_until'])>now() and not str(state.get('last_error','')).startswith(('rate','quota')):
            state['finished_at']=now().isoformat();atomic(state_path,state);request_publication()
            return state
        runner=EXECUTORS[chosen]
        state.update(executor=chosen,model_requested=runner['model'],billing=runner['billing']);atomic(state_path,state)
        event(data,'analysis.dispatch_started',component='analysis_plan',run_id=run_id,detail={'executor':chosen,'model_requested':runner['model'],'effort':'max','limit':limit,'billing':runner['billing']})
        state.update(status='idle',pause_until=None)
        count=0;attempted=0;prompt=load_prompt();schema=load_schema()
        for job_id,path,raw in candidates(data,today,backlog):
            if attempted>=limit:break
            day=now().astimezone(timezone(timedelta(hours=-5))).date().isoformat()
            if state['daily'].get(day,0)>=DAILY_LIMIT:state['status']='daily_limit';break
            previous=state['jobs'].get(job_id,{})
            if authorized_retry(data,job_id,previous):
                # Keep the provenance of the refusal that the operator reopened.
                previous=dict(previous,status='authorized_retry',attempts=0,
                              previous_error=previous.get('error'),previous_status=previous.get('status'))
                previous.pop('error',None);state['jobs'][job_id]=previous
            attempt_limit=min(previous.get('attempt_limit',2),3)
            if previous.get('attempts',0)>=attempt_limit or previous.get('status') in ('ok','invalid'):continue
            if previous.get('status')=='blocked' and not retryable(previous):continue
            source=Path(path).resolve()
            if not source.is_relative_to((data/'transcripts').resolve()):continue
            source_bytes=source.read_bytes();document=json.loads(source_bytes)
            if not assess(document)['valid']:continue
            target=data/'analysis'/document['video']['channel']['slug']/source.name
            if target.exists():continue
            job=json.loads(raw);at=now().isoformat();payload=build_payload(document,at)
            source_hash=hashlib.sha256(source_bytes).hexdigest()
            if (job['meta']['transcript_sha256']!=source_hash or job['meta']['prompt_sha256']!=sha256(prompt)
                    or job['meta']['schema_sha256']!=sha256(json.dumps(schema,sort_keys=True))):continue
            attempted+=1
            record=dict(previous,status='running',started_at=at,attempts=previous.get('attempts',0),attempt_limit=attempt_limit)
            if record.get('errors'):record['previous_validation_errors']=record.pop('errors')
            state['jobs'][job_id]=record;state.update(status='running',last_error=None);atomic(state_path,state)
            event(data,'analysis.started',component='analysis_plan',run_id=run_id,job_id=job_id,video_id=job['meta']['video_id'],detail={'executor':chosen,'model_requested':runner['model'],'effort':'max'})
            request='Analiza la siguiente entrada según tu rol y el esquema. En esta ejecución no tienes herramientas de consulta externa; declara ese límite y no simules verificaciones.\nENTRADA:\n'+json.dumps(payload,ensure_ascii=False)
            try:
                with tempfile.TemporaryDirectory(prefix='cryptoreport-plan-') as temp:
                    work=Path(temp)
                    for attempt in range(attempt_limit-record['attempts']):
                        day=now().astimezone(timezone(timedelta(hours=-5))).date().isoformat()
                        if state['daily'].get(day,0)>=DAILY_LIMIT:raise RuntimeError('daily_limit')
                        record['attempts']+=1;state['daily'][day]=state['daily'].get(day,0)+1;atomic(state_path,state)
                        event(data,'analysis.attempt_started',component='analysis_plan',run_id=run_id,job_id=job_id,video_id=job['meta']['video_id'],detail={'attempt':record['attempts']})
                        analysis,usage=invoke_available(state,state_path,request,schema,work,prompt)
                        chosen=state['executor'];runner=EXECUTORS[chosen]
                        atomic(root/'attempts'/(job_id+f'-{record["attempts"]}.json'),{'analysis':analysis,'usage':usage,'analyzed_at':at})
                        repairs=bind_citations(analysis,payload)
                        record.setdefault('usage_by_attempt',[]).append({'attempt':record['attempts'],'executor':chosen,'usage':usage})
                        errors=controls(analysis,payload,schema)
                        if not errors:break
                        event(data,'analysis.validation_rejected',component='analysis_plan',run_id=run_id,job_id=job_id,video_id=job['meta']['video_id'],outcome='error',detail={'attempt':record['attempts'],'error_count':len(errors),'errors':errors[:20]})
                        request+='\nCORRECCIÓN DEL MISMO TRABAJO. Corrige únicamente estos errores conservando todos los puntos materiales. Copia citas contiguas exactamente del texto original: NO combines fragmentos mediante puntos suspensivos, no corrijas la gramática de la transcripción ni la escritura de las marcas. Los tiempos se derivan de segmentos originales.\n'+json.dumps(errors,ensure_ascii=False)+'\nSALIDA PREVIA:\n'+json.dumps(analysis,ensure_ascii=False)
                    if errors:
                        atomic(root/'rejected'/(job_id+'.json'),{'job_id':job_id,'analysis':analysis,'errors':errors,'usage':usage})
                        record.update(status='invalid',errors=errors[:20],finished_at=now().isoformat());continue
                meta=dict(job['meta'],job_id=job_id,transcript_file=str(source),provider=runner['provider'],model=None,model_requested=runner['model'],effort='max',
                          analyzed_at=at,usage=usage,usage_by_attempt=record['usage_by_attempt'],citation_locator_repairs=repairs,
                          cost_usd_estimate=None,billing=runner['billing'],status='ok',validation={'ok':True,'errors':[]})
                ready=root/(job_id+'.ready.json');atomic(ready,{'meta':meta,'analysis':analysis})
                state['last_validated_at']=now().isoformat()
                published=promote(data,ready);record.update(status='ok' if published else 'ready',finished_at=now().isoformat())
                if published:request_publication()
                event(data,'analysis.validated',component='analysis_plan',run_id=run_id,job_id=job_id,video_id=job['meta']['video_id'],detail={'stored':published,'citation_locator_repairs':len(repairs)})
                count+=1
            except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:
                kind=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
                if kind.startswith(('quota','rate')) and record['attempts']>previous.get('attempts',0):
                    # El proveedor rechazó la petición: sin inferencia no se le cobra
                    # el intento al trabajo ni al presupuesto del día.
                    record['attempts']-=1
                    rejected=now().astimezone(timezone(timedelta(hours=-5))).date().isoformat()
                    state['daily'][rejected]=max(0,state['daily'].get(rejected,0)-1)
                record.update(status='blocked',error=kind,finished_at=now().isoformat());state.update(status='daily_limit' if kind=='daily_limit' else 'paused',last_error=kind,pause_until=(now()+timedelta(hours=6 if kind.startswith('quota') else .5)).isoformat())
                if kind.startswith(('rate','quota')):
                    waits=[p['pause_until'] for p in state.get('providers',{}).values() if p.get('pause_until') and datetime.fromisoformat(p['pause_until'])>now()]
                    if waits:state['pause_until']=min(waits)
                event(data,'analysis.blocked',component='analysis_plan',run_id=run_id,job_id=job_id,video_id=job['meta']['video_id'],outcome='error',detail={'reason':kind,'pause_until':state['pause_until']});break
            finally:
                state.pop('active_attempt',None)
                atomic(state_path,state)
        reconcile_ready(data,state)
        if state.get('status')=='running':state['status']='idle'
        state['finished_at']=now().isoformat();atomic(state_path,state)
        event(data,'analysis.dispatch_finished',component='analysis_plan',run_id=run_id,detail={'completed':count,'attempted_jobs':attempted,'status':state['status']})
        request_publication()
        return {'status':state['status'],'completed':count,'executor':state['executor'],'model_requested':state['model_requested'],'billing':state['billing'],'api_fallback':False,'last_error':state.get('last_error')}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=2);parser.add_argument('--today',action='store_true');parser.add_argument('--backlog',action='store_true',help='Priorizar últimas48h y recuperar después pendientes antiguos');parser.add_argument('--resume',action='store_true',help='Reanudar únicamente por instrucción explícita del usuario');args=parser.parse_args()
    if not 1<=args.limit<=5:parser.error('--limit debe estar entre 1 y 5')
    print(json.dumps(run(limit=args.limit,today=args.today,resume=args.resume,backlog=args.backlog),ensure_ascii=False))

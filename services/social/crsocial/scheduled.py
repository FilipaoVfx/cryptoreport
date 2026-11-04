"""Hash-pinned semantic jobs for Drive/Schedule; no inference client is constructed.

Semantic jobs live in Control. Results use .semantic so the video bridge does not
mistake them for narrative-analysis results. Original analyses remain immutable.
"""
import json
import os
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
import sys

from .config import REPO
from .feed import atomic, instant, now_utc
from .quality import classify, VERSION as QUALITY_VERSION
from .semantic import prepare_video, digest, match, SELECT_SCHEMA, JUDGE_SCHEMA
from .semantic_prompts import VERSION, SELECT, JUDGE, AUDIT
from .model_api import ModelError

sys.path.insert(0, str(REPO / 'services/transcripts'))
from crtranscripts.quality import analysis_matches, assess

PROTOCOL = 'scheduled-semantic-1'


def drive_enabled():
    """La pata de Drive existía para ChatGPT Scheduled; cortada por defecto.

    El cruce se resuelve en el servidor (`crsocial semantic-solve`), así que
    subir trabajos a Control y sondear Resultados solo gastaría cuota de Drive.
    `CR_SEMANTIC_DRIVE=true` la reactiva sin tocar código.
    """
    return os.environ.get('CR_SEMANTIC_DRIVE', '').strip().lower() == 'true'


def read_json(raw):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError('Clave repetida')
            result[k] = v
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Número no finito')))


def valid_analyses(data):
    result = {}
    for path in sorted((data / 'analysis').glob('*/*.json')):
        if path.parent.name.startswith('_'):
            continue
        try:
            doc = read_json(path.read_bytes())
            raw = (data / 'transcripts' / path.parent.name / path.name).read_bytes()
            if analysis_matches(doc, raw) and assess(read_json(raw))['valid']:
                result[doc['analysis']['video']['video_id']] = doc
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return result


def current_posts(feed, at):
    feed.prune(at)
    return {p['id']: dict(p, quality=classify(p)) for p in feed.state['posts'].values()}


def make_jobs(analyses, posts, accounts, at, valid_days=3, batch_size=30):
    """Every eligible post is partitioned; never claim an unseen page was evaluated."""
    eligible = sorted((p for p in posts.values() if p['quality']['semantic_eligible']
                       and instant(p['expires_at'])>at+timedelta(hours=6)), key=lambda p:p['id'])
    jobs = []
    for video_id, doc in sorted(analyses.items(), key=lambda kv:kv[1]['analysis']['video']['publicado_en'], reverse=True):
        try:
            prepared = prepare_video(doc, valid_days, at)
        except ValueError:
            continue
        if not prepared['claims']:
            continue
        for offset in range(0, len(eligible), batch_size):
            batch = eligible[offset:offset+batch_size]
            # Fetch time/avatar changes must not restart expensive editorial work.
            fields=('id','text','published_at','author_id','author_handle','expires_at','content_hash',
                    'conversation_id','links','is_reply','is_repost','is_quote','text_completeness')
            corpus = {'status':'partial', 'posts':[dict({k:p.get(k) for k in fields},
                          belongs_to_requested_account=True,
                          media=['multimedia_no_leida'] if p['has_media'] else []) for p in batch]}
            expires = min([instant(prepared['expires_at'])]+[instant(p['expires_at']) for p in batch])
            # Near-expiry work cannot realistically survive a six-hour Schedule.
            if expires <= at + timedelta(hours=6):
                continue
            payload = {'protocol':PROTOCOL, 'prompt_version':VERSION, 'quality_version':QUALITY_VERSION,
                       'prompts':{'select_candidates':SELECT,'judge_pairs':JUDGE,'audit_pairs':AUDIT},
                       'schemas':{'selection':SELECT_SCHEMA,'decision':JUDGE_SCHEMA},
                       'prepared':prepared, 'corpus':corpus, 'accounts':accounts,
                       'page':offset//batch_size+1, 'pages':(len(eligible)+batch_size-1)//batch_size,
                       'expires_at':expires.isoformat(), 'batch_size':batch_size, 'judge_batch':5}
            job_id = 'semantic-' + digest(payload)
            jobs.append(dict(payload, job_id=job_id))
    return jobs


class RecordedModel:
    """Replay declared stages through the same strict selector/judge/auditor gates."""
    def __init__(self, responses):
        if not isinstance(responses, list) or len(responses)>500:
            raise ValueError('Respuestas inválidas')
        self.responses, self.calls, self.records = responses, 0, []

    def ask(self, stage, prompt, schema, payload):
        if self.calls >= len(self.responses) or self.responses[self.calls].get('stage') != stage:
            raise ModelError('Etapa ausente o fuera de orden')
        row = self.responses[self.calls]
        self.calls += 1
        self.records.append({'stage':stage, 'executor':'chatgpt-scheduled', 'api_calls':0})
        return row.get('output')


def validate_output(output, job, analyses, posts, at):
    if not isinstance(output, dict) or set(output)!={'job_id','protocol','responses'}:
        raise ValueError('Sobre incompatible')
    if output['job_id'] != job['job_id'] or output['protocol'] != PROTOCOL or at >= instant(job['expires_at']):
        raise ValueError('Trabajo desconocido o vencido')
    # The file name is not the trust boundary: recompute the complete job contract.
    if job['job_id'] != 'semantic-'+digest({k:v for k,v in job.items() if k!='job_id'}):
        raise ValueError('Trabajo modificado')
    vid = job['prepared']['video']['video_id']
    if vid not in analyses or digest(analyses[vid]) != job['prepared']['analysis_sha256']:
        raise ValueError('Análisis o transcripción reemplazados')
    for old in job['corpus']['posts']:
        current = posts.get(old['id'])
        if not current or current['content_hash'] != old['content_hash'] or not current['quality']['semantic_eligible']:
            raise ValueError('Post editado, vencido o reclasificado')
    model = RecordedModel(output['responses'])
    result = match(job['prepared'],job['corpus'],job['accounts'],model,now=at,
                   batch_size=job['batch_size'],judge_batch=job['judge_batch'])
    if (result['errors'] or model.calls != len(model.responses)
            or result['retrieval_batches_completed'] != result['retrieval_batches_expected']
            or result['pending_pairs'] or result.get('preliminary_accepted',0)!=result.get('audit_completed',0)):
        raise ValueError('Selección/evaluación/revisión incompletas')
    result.update(job_id=job['job_id'],expires_at=job['expires_at'],executor='chatgpt-scheduled',model_api_calls=0)
    return result


def durable(root, reviewed, posts, analyses, at):
    """Conexiones aceptadas que siguen valiendo, sin volver a preguntar al modelo.

    Los trabajos están fijados al corpus: un post nuevo o uno que caduca cambia
    todos los `job_id`, y hasta ahora eso borraba el sobre y dejaba la
    publicación en cero. Una conexión se conserva mientras su post exista con el
    mismo contenido, sin caducar y aún elegible, y el análisis citado conserve su
    hash. Son los mismos invariantes que exige la revisión, así que conservarla
    no afirma nada que no se haya comprobado.
    """
    store = root / 'connections.json'
    try:
        kept = read_json(store.read_bytes())
    except (OSError, ValueError):
        kept = []
    merged = {}
    for item in (kept if isinstance(kept, list) else []) + reviewed:
        if isinstance(item, dict):
            # Lo recién revisado sustituye a la versión guardada del mismo par.
            merged[(item.get('video_id'), item.get('claim_id'), item.get('post_id'))] = item
    live = []
    for item in merged.values():
        post, doc = posts.get(item.get('post_id')), analyses.get(item.get('video_id'))
        try:
            if (not post or not doc or not post['quality']['semantic_eligible']
                    or post.get('content_hash') != item.get('post_content_hash')
                    or digest(doc) != item.get('analysis_sha256')
                    or instant(item['expires_at']) <= at):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        live.append(item)
    live.sort(key=lambda c: (c.get('post_published_at') or '', str(c.get('post_id'))))
    atomic(store, live)
    return live


def run(feed, drive=None, folders=None, at=None):
    at = at or now_utc()
    root = feed.config.data / 'semantic'
    root.mkdir(parents=True,exist_ok=True)
    data = feed.config.data.parent
    analyses = valid_analyses(data)
    posts = current_posts(feed,at)
    jobs = make_jobs(analyses,posts,feed.config.accounts,at)
    for job in jobs:
        if not (root / (job['job_id']+'.json')).exists():
            atomic(root / (job['job_id']+'.json'),job)
    report = {'version':PROTOCOL,'generated_at':at.isoformat(),
              'status':'pending_schedule' if drive is not None else 'pendiente_local','drive_leg':drive is not None,
              'model_api_enabled':False,'eligible_posts':sum(p['quality']['semantic_eligible'] for p in posts.values()),
              'near_expiry_posts_excluded':sum(p['quality']['semantic_eligible'] and instant(p['expires_at'])<=at+timedelta(hours=6) for p in posts.values()),
              'jobs_available':len(jobs),'jobs_uploaded':0,'jobs_reviewed':0,'jobs_rejected':0,
              'connections':[], 'errors':[], 'rejections':[], 'video_valid_days':3}
    active = {j['job_id']:j for j in jobs}
    # Ephemeral corpus, no archive of expired or superseded source texts.
    for path in root.glob('semantic-*'):
        if path.suffix in ('.json','.semantic') and path.stem not in active and not path.is_symlink():
            path.unlink()
    if drive is not None:
        try:
            control = defaultdict(list)
            for item in drive.list(folders['control']):
                control[item['Name']].append(item)
            results = defaultdict(list)
            for item in drive.list(folders['resultados']):
                if item['Name'].startswith('semantic-') and item['Name'].endswith('.semantic'):
                    results[item['Name']].append(item)
            for job in jobs:
                name = job['job_id']+'.semantic'
                if len(results[name])>1:
                    report['errors'].append('resultado_duplicado:'+job['job_id']);continue
                if results[name] and not (root / name).exists():
                    # Store the supplied envelope, never a model's publication status.
                    try:
                        atomic(root/name,read_json(drive.read(folders['resultados'],results[name][0])))
                    except (ValueError, TypeError):
                        report['errors'].append('resultado_ilegible:'+job['job_id'])
            outstanding=sum(bool(control[j['job_id']+'.json']) and not results[j['job_id']+'.semantic'] for j in jobs)
            slots=max(0,4-outstanding)
            for job in jobs:
                name=job['job_id']+'.json'
                if len(control[name])>1:
                    report['errors'].append('trabajo_duplicado:'+job['job_id']);continue
                if not control[name] and slots:
                    drive.write(folders['control'],name,json.dumps(job,ensure_ascii=False,allow_nan=False).encode())
                    slots-=1
            # Read back metadata before advertising a job as uploaded.
            uploaded = defaultdict(list)
            for item in drive.list(folders['control']):
                uploaded[item['Name']].append(item)
            queue = [j for j in jobs if len(uploaded[j['job_id']+'.json'])==1 and not results[j['job_id']+'.semantic']]
            report['jobs_uploaded']=sum(len(uploaded[j['job_id']+'.json'])==1 for j in jobs)
            index={'version':PROTOCOL,'generated_at':at.isoformat(), 'jobs':[
                {k:j[k] for k in ('job_id','expires_at','page','pages')} | {'file':j['job_id']+'.json','video_id':j['prepared']['video']['video_id']} for j in queue]}
            index_name='social-semantic-index.json'
            existing=uploaded[index_name]
            if len(existing)>1:raise ValueError('Índice semántico duplicado')
            previous=read_json(drive.read(folders['control'],existing[0])) if existing else None
            # generated_at marks a changed index, not a heartbeat on every poll.
            expected={k:v for k,v in index.items() if k!='generated_at'}
            if not isinstance(previous,dict) or {k:v for k,v in previous.items() if k!='generated_at'}!=expected:
                drive.write(folders['control'],index_name,json.dumps(index).encode(),replace=True)
            instructions=REPO/'docs/automatizacion-drive/semantic-scheduled.md'
            content=instructions.read_bytes();existing=uploaded['semantic-scheduled.md']
            if len(existing)>1:raise ValueError('Instrucciones semánticas duplicadas')
            if not existing or drive.read(folders['control'],existing[0])!=content:
                drive.write(folders['control'],'semantic-scheduled.md',content,replace=True)
        except Exception as exc:
            # Isolated from video ingestion; no inference fallback, no retry loop.
            report['status']='drive_error'
            report['errors'].append('drive_sync:'+getattr(exc,'category',type(exc).__name__))
            if getattr(exc,'retry_at',None):report['next_drive_attempt_at']=exc.retry_at
    for path in root.glob('semantic-*.semantic'):
        if path.stem not in active:
            continue
        job = active[path.stem]
        try:
            checked = validate_output(read_json(path.read_bytes()),job,analyses,posts,at)
            report['jobs_reviewed']+=1
            for c in checked['connections']:
                report['connections'].append(dict(c,video_id=checked['video_id'],
                    analysis_sha256=checked['analysis_sha256'],
                    video_title=job['prepared']['video'].get('titulo'),expires_at=checked['expires_at'],
                    post_content_hash=posts[c['post_id']]['content_hash']))
        except (ValueError,KeyError,TypeError,ModelError) as exc:
            report['jobs_rejected']+=1
            report['rejections'].append({'job_id':job['job_id'],'reason':str(exc) if isinstance(exc,(ValueError,ModelError)) else type(exc).__name__})
    # Publicación durable: sobrevive al cambio de corpus que invalida los job_id.
    report['connections'] = durable(root, report['connections'], posts, analyses, at)
    report['connections_published'] = len(report['connections'])
    if (report['jobs_reviewed'] or report['connections']) and not report['errors']:
        report['status'] = 'ok'
    report['coverage_complete']=bool(jobs) and report['jobs_reviewed']==len(jobs) and not report['errors']
    atomic(feed.config.public/'social-connections.json',report)
    atomic(root/'status.json',{k:v for k,v in report.items() if k!='connections'})
    return report

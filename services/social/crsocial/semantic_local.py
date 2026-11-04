"""Resuelve trabajos semánticos en el servidor con la suscripción, sin Drive.

Escribe el mismo sobre `<job_id>.semantic` que subía ChatGPT Scheduled, con el
transcript declarado de cada etapa. El ciclo del puente lo vuelve a validar con
`scheduled.validate_output`, que reproduce las etapas y recompone las puertas:
este ejecutor no puede declarar una conexión aceptada por su cuenta.
"""
import json

from .feed import atomic, instant, now_utc
from .model_api import ModelError
from .scheduled import PROTOCOL, current_posts, make_jobs, valid_analyses
from .scheduled import run as review_cycle
from .semantic import match
from .subscription import CodexSubscriptionModel as SubscriptionModel

EXECUTOR = 'codex-chatgpt-plan'
LEDGER = 'solved.json'


def ledger(root):
    """Último momento en que se juzgó cada vídeo, para repartir los turnos.

    Los sobres se purgan en cuanto cambia el corpus, así que «sin sobre» no
    distingue un vídeo nunca juzgado de uno juzgado hace diez minutos: sin este
    registro, el trabajo que caduca antes gana siempre y el mismo vídeo
    consumiría todas las ejecuciones.
    """
    try:
        history = json.loads((root / LEDGER).read_text())
    except (OSError, ValueError):
        return {}
    return history if isinstance(history, dict) else {}


def incomplete(result):
    """Mismas condiciones que exige el servidor al importar un resultado."""
    return bool(result['errors'] or result['pending_pairs']
                or result['retrieval_batches_completed'] != result['retrieval_batches_expected']
                or result.get('preliminary_accepted', 0) != result.get('audit_completed', 0))


def run(feed, at=None, limit=1, max_calls=12, model=None, progress=None):
    at = at or now_utc()
    root = feed.config.data / 'semantic'
    root.mkdir(parents=True, exist_ok=True)
    analyses = valid_analyses(feed.config.data.parent)
    posts = current_posts(feed, at)
    jobs = make_jobs(analyses, posts, feed.config.accounts, at)
    report = {'version': PROTOCOL, 'generated_at': at.isoformat(), 'executor': EXECUTOR,
              'status': 'sin_pendientes', 'jobs_available': len(jobs), 'jobs_solved': 0,
              'jobs_failed': 0, 'model_calls': 0, 'api_calls': 0, 'results': [], 'errors': [], 'model_records': []}
    history = ledger(root)
    pending = sorted((j for j in jobs if not (root / (j['job_id'] + '.semantic')).exists()),
                     key=lambda j: (history.get(j['prepared']['video']['video_id']) or '',
                                    instant(j['expires_at'])))
    for job in pending[:max(0, limit)]:
        worker = None
        try:
            # Una sesión ausente o un presupuesto agotado detienen el lote aquí.
            worker = model or SubscriptionModel(max_calls=max_calls, progress=progress)
            result = match(job['prepared'], job['corpus'], job['accounts'], worker,
                           now=at, batch_size=job['batch_size'], judge_batch=job['judge_batch'])
        except (ModelError, ValueError, KeyError, TypeError) as error:
            report['jobs_failed'] += 1
            report['errors'].append({'job_id': job['job_id'], 'stage': 'ejecucion', 'detail': str(error)[:200]})
            report['model_calls'] += worker.calls if worker else 0
            report['model_records'].extend(worker.records if worker else [])
            break
        report['model_calls'] += worker.calls
        report['model_records'].extend(worker.records)
        if incomplete(result):
            report['jobs_failed'] += 1
            report['errors'].append({'job_id': job['job_id'], 'stage': 'controles',
                                     'detail': 'selección, evaluación o revisión incompletas',
                                     'stage_errors': result['errors']})
            continue
        atomic(root / (job['job_id'] + '.semantic'),
               {'job_id': job['job_id'], 'protocol': PROTOCOL, 'responses': worker.responses})
        report['jobs_solved'] += 1
        history[job['prepared']['video']['video_id']] = at.isoformat()
        atomic(root / LEDGER, history)
        report['results'].append({'job_id': job['job_id'], 'video_id': job['prepared']['video']['video_id'],
                                  'preliminary_connections': len(result['connections']),
                                  'model_calls': worker.calls, 'expires_at': job['expires_at']})
    if report['jobs_solved']:
        report['status'] = 'resuelto'
        # Revisar en la MISMA instantánea: los trabajos están fijados al corpus y
        # un post nuevo o caducado invalidaría el sobre antes del ciclo del
        # puente. La revisión recompone las puertas por su cuenta.
        review = review_cycle(feed, None, None, at)
        report['review'] = {k: review.get(k) for k in
                            ('status', 'jobs_reviewed', 'jobs_rejected', 'connections_published', 'rejections')}
    elif report['jobs_failed']:
        report['status'] = 'error'
    atomic(root / 'local-status.json', report)
    return report

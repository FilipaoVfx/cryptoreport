"""Semantic claim/post linking, isolated and expiration-aware. No lexical matcher."""
import argparse
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .collector import handle, timestamp
from .config import load_accounts
from .model_api import ModelError, ResponsesModel, api_key, object_schema, validate_shape
from .semantic_prompts import AUDIT, COMMON, JUDGE, SELECT, VERSION

STRING = {'type': 'string'}
BOOL = {'type': 'boolean'}
SCORE = {'type': 'integer', 'enum': [0, 1, 2, 3]}
GATES = ('interpretacion_fiel', 'contexto_suficiente', 'alcance_compatible',
         'temporalidad_clara', 'sin_saltos_no_sustentados', 'aporte_material')
THRESHOLDS = {'fidelidad': 3, 'relacion': 3, 'trazabilidad': 3, 'compatibilidad': 3, 'aporte': 2}
PAIR = object_schema({'claim_id': STRING, 'post_id': STRING})
SELECT_SCHEMA = object_schema({'candidates': {'type': 'array', 'items': PAIR}})
DECISION = object_schema({
    'claim_id': STRING, 'post_id': STRING,
    'decision': {'type': 'string', 'enum': ['proponer', 'descartar', 'evidencia_insuficiente']},
    'relation': {'type': 'string', 'enum': ['apoyo_declarado', 'contrapunto', 'actualizacion', 'contexto', 'ninguna']},
    'gates': object_schema({gate: BOOL for gate in GATES}),
    'scores': object_schema({name: SCORE for name in THRESHOLDS}),
    'evidence_id': STRING, 'video_quote': STRING, 'post_quote': STRING,
    'explanation': STRING, 'limitations': STRING,
    'posterior_al_video': BOOL, 'old_post_relevance': {'type': ['string', 'null']},
})
JUDGE_SCHEMA = object_schema({'decisions': {'type': 'array', 'items': DECISION}})


def date(value):
    normalized = timestamp(value)
    if normalized is None:
        raise ValueError('Fecha inválida o sin zona horaria')
    return datetime.fromisoformat(normalized)


def prepare_video(document, valid_days, now):
    if type(valid_days) is not int or not 1 <= valid_days <= 30:
        raise ValueError('Vigencia de vídeo inválida')
    analysis = document.get('analysis', document)
    video = analysis['video']
    video_id = video['video_id']
    if not isinstance(video_id, str) or not video_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in video_id):
        raise ValueError('ID de vídeo inválido')
    published = date(video['publicado_en'])
    expires = published + timedelta(days=valid_days)
    if not published <= now < expires:
        raise ValueError('Vídeo vencido o con fecha futura; no se evalúa ni se envía al modelo')
    evidence = {e['id']: e for e in analysis['evidencias']}
    if len(evidence) != len(analysis['evidencias']):
        raise ValueError('Evidencias duplicadas')
    claims, skipped, seen = [], [], set()
    for claim in analysis['afirmaciones']:
        if claim['id'] in seen:
            raise ValueError('Afirmación duplicada')
        seen.add(claim['id'])
        items = [evidence[e] for e in claim['evidencia_ids'] if e in evidence and
                 isinstance(evidence[e].get('cita'), str) and evidence[e]['cita'].strip()]
        if not items or claim.get('confianza_extraccion') == 'baja':
            skipped.append({'claim_id': claim['id'], 'status': 'evidencia_insuficiente'})
            continue
        claims.append({'id': claim['id'], 'enunciado': claim['enunciado'], 'tipo': claim['tipo'],
                       'emisor': claim.get('emisor'), 'mercado': claim.get('mercado'),
                       'verification_limits': claim.get('justificacion_verificacion'),
                       'extraction_limits': claim.get('motivo_confianza'),
                       'confianza_extraccion': claim.get('confianza_extraccion'), 'evidence': items})
    return {'analysis_sha256': digest(document), 'video': video, 'expires_at': expires.isoformat(), 'valid_days': valid_days,
            'claims': claims, 'skipped': skipped, 'original_analysis_state': analysis.get('estado')}


def eligible_posts(corpus, accounts, now):
    windows = {a['handle']: a['lookback_days'] for a in accounts}
    posts, excluded = {}, []
    for post in corpus['posts']:
        reason = None
        try:
            author = handle(post.get('author_handle') or '')
            published = date(post.get('published_at'))
            if author not in windows or post.get('belongs_to_requested_account') is not True:
                reason = 'autor_no_autorizado_o_no_verificado'
            elif not now - timedelta(days=windows[author]) <= published < now:
                reason = 'fuera_de_ventana'
            elif not isinstance(post.get('text'), str) or not post['text'].strip():
                reason = 'texto_insuficiente'
            elif not isinstance(post.get('id'), str) or not post['id'].isdigit():
                reason = 'id_invalido'
        except (ValueError, TypeError):
            reason = 'metadatos_invalidos'
        if reason:
            excluded.append({'post_id': post.get('id'), 'reason': reason})
            continue
        if post['id'] in posts and posts[post['id']]['text'] != post['text']:
            raise ValueError('Versiones conflictivas del mismo post')
        # Preserve context indicators; do not expose followers/engagement to the evaluator.
        posts[post['id']] = {k: post.get(k) for k in
                            ('id', 'text', 'published_at', 'author_handle', 'conversation_id',
                             'links', 'media', 'is_reply', 'is_repost', 'is_quote', 'text_completeness')}
    return list(posts.values()), excluded


def gate_decision(decision, claim, post, video, now):
    """Deterministic acceptance, independent of the model's recommendation."""
    validate_shape(decision, DECISION)
    if decision['claim_id'] != claim['id'] or decision['post_id'] != post['id']:
        raise ModelError('IDs de decisión no coinciden')
    result = dict(decision)
    errors = []
    if decision['decision'] != 'proponer':
        result.update(status='descartado' if decision['decision'] == 'descartar' else 'evidencia_insuficiente',
                      validation_errors=[])
        return result
    for gate in GATES:
        if decision['gates'][gate] is not True:
            errors.append(f'puerta:{gate}')
    for key, threshold in THRESHOLDS.items():
        if decision['scores'][key] < threshold:
            errors.append(f'umbral:{key}')
    evidence = next((e for e in claim['evidence'] if e['id'] == decision['evidence_id']), None)
    if not evidence or not decision['video_quote'].strip() or decision['video_quote'] not in evidence['cita']:
        errors.append('cita_video_no_literal')
    if not decision['post_quote'].strip() or decision['post_quote'] not in post['text']:
        errors.append('cita_post_no_literal')
    if not decision['explanation'].strip() or not decision['limitations'].strip():
        errors.append('explicacion_o_limites_ausentes')
    posterior = date(post['published_at']) > date(video['publicado_en'])
    if decision['posterior_al_video'] is not posterior:
        errors.append('temporalidad_incorrecta')
    if decision['relation'] == 'ninguna':
        errors.append('sin_relacion')
    if decision['relation'] == 'actualizacion' and not posterior:
        errors.append('actualizacion_no_posterior')
    if (now-date(post['published_at'])).total_seconds() > 4*86400 and not (
            isinstance(decision['old_post_relevance'], str) and decision['old_post_relevance'].strip()):
        errors.append('post_antiguo_sin_justificacion')
    result.update(status='aceptado' if not errors else 'evidencia_insuficiente', validation_errors=errors,
                  post_url=f'https://x.com/i/web/status/{post["id"]}',
                  source_account=post['author_handle'], post_published_at=post['published_at'],
                  video_locator={k: evidence.get(k) if evidence else None for k in
                                 ('origen', 'inicio_s', 'fin_s', 'localizador')},
                  externally_verified=False)
    return result


def match(prepared, corpus, accounts, model, *, now, batch_size=50, judge_batch=5):
    if not 1 <= batch_size <= 100 or not 1 <= judge_batch <= 10:
        raise ValueError('Tamaño de lote inválido')
    if not date(prepared['video']['publicado_en']) <= now < date(prepared['expires_at']):
        raise ValueError('Vídeo no vigente')
    posts, excluded = eligible_posts(corpus, accounts, now)
    claims = {c['id']: c for c in prepared['claims']}
    post_map = {p['id']: p for p in posts}
    result = {'analysis_sha256': prepared.get('analysis_sha256'), 'corpus_sha256': digest(corpus), 'version': VERSION, 'created_at': now.isoformat(), 'expires_at': prepared['expires_at'],
              'video_id': prepared['video']['video_id'], 'status': 'ok', 'calibrated': False,
              'thresholds': THRESHOLDS, 'eligible_posts': len(posts), 'excluded_posts': excluded,
              'claims_evaluated': len(claims), 'skipped_claims': prepared['skipped'],
              'retrieval_batches_expected': math.ceil(len(posts)/batch_size) if claims else 0,
              'retrieval_batches_completed': 0, 'candidate_pairs': 0, 'decisions': [],
              'connections': [], 'errors': [], 'model_calls': 0,
              'source_ingestion_status': corpus.get('status', 'unknown')}
    candidates, seen = [], set()
    common = {'video': prepared['video'], 'analysis_state': prepared['original_analysis_state'],
              'as_of': now.isoformat(), 'expires_at': prepared['expires_at']}
    if corpus.get('status') != 'ok' or prepared['skipped']:
        result['status'] = 'partial'
    for offset in range(0, len(posts) if claims else 0, batch_size):
        batch = posts[offset:offset+batch_size]
        allowed_posts = {p['id'] for p in batch}
        try:
            output = model.ask('select_candidates', SELECT, SELECT_SCHEMA,
                               common | {'claims': list(claims.values()), 'posts': batch})
            validate_shape(output, SELECT_SCHEMA)
            if any(p['claim_id'] not in claims or p['post_id'] not in allowed_posts for p in output['candidates']):
                raise ModelError('Recuperación devolvió IDs inexistentes o de otro lote')
            for pair in output['candidates']:
                key = (pair['claim_id'], pair['post_id'])
                if key not in seen:
                    seen.add(key)
                    candidates.append(pair)
            result['retrieval_batches_completed'] += 1
        except ModelError as error:
            result['errors'].append({'stage': 'selection', 'batch': offset//batch_size, 'detail': str(error)})
            result['status'] = 'partial'
            break
    result['candidate_pairs'] = len(candidates)
    for offset in range(0, len(candidates), judge_batch):
        batch = candidates[offset:offset+judge_batch]
        expected = {(p['claim_id'], p['post_id']) for p in batch}
        try:
            output = model.ask('judge_pairs', JUDGE, JUDGE_SCHEMA, common | {
                'pairs': [{'claim': claims[p['claim_id']], 'post': post_map[p['post_id']]} for p in batch]})
            validate_shape(output, JUDGE_SCHEMA)
            actual = [(d['claim_id'], d['post_id']) for d in output['decisions']]
            if set(actual) != expected or len(actual) != len(expected):
                raise ModelError('Evaluación no cubre exactamente los pares del lote')
            decisions = [gate_decision(d, claims[d['claim_id']], post_map[d['post_id']],
                                       prepared['video'], now) for d in output['decisions']]
            result['decisions'].extend(decisions)
        except ModelError as error:
            result['errors'].append({'stage': 'judgment', 'batch': offset//judge_batch, 'detail': str(error)})
            result['status'] = 'partial'
            break
    audit_result(result, prepared, posts, model, now, judge_batch)
    decided = {(d['claim_id'], d['post_id']) for d in result['decisions']}
    result['pending_pairs'] = [p for p in candidates if (p['claim_id'], p['post_id']) not in decided]
    for claim_id in claims:
        # No candidate is a retrieval abstention, never a proof of no possible relationship.
        if not any(p['claim_id'] == claim_id for p in candidates):
            result.setdefault('without_candidates', []).append(claim_id)
    result['model_calls'] = model.calls
    result['model_records'] = model.records
    return result


def audit_result(result, prepared, posts, model, now, batch_size=5):
    """Final acceptance requires both judgments; missing/failed audit never publishes."""
    claims = {c['id']: c for c in prepared['claims']}
    post_map = {p['id']: p for p in posts}
    # Revalidate the original payload too: a current audit cannot rehabilitate stale quotes.
    for original in result['decisions']:
        if original['status'] != 'aceptado':
            continue
        key, post_id = original['claim_id'], original['post_id']
        if key not in claims or post_id not in post_map:
            original['status'] = 'evidencia_insuficiente'
            continue
        clean = {key: original[key] for key in DECISION['properties']}
        checked = gate_decision(clean, claims[key], post_map[post_id], prepared['video'], now)
        if checked['status'] != 'aceptado':
            original.update(checked)
    provisional = [d for d in result['decisions'] if d['status'] == 'aceptado']
    result['preliminary_accepted'] = len(provisional)
    result['audit_completed'] = 0
    for d in provisional:
        d['status'] = 'pendiente_auditoria'
    for offset in range(0, len(provisional), batch_size):
        batch = provisional[offset:offset+batch_size]
        try:
            if any(d['claim_id'] not in claims or d['post_id'] not in post_map for d in batch):
                raise ModelError('Par de auditoría no elegible en las fuentes actuales')
            output = model.ask('audit_pairs', AUDIT, JUDGE_SCHEMA, {
                'video': prepared['video'], 'as_of': now.isoformat(),
                'pairs': [{'claim': claims[d['claim_id']], 'post': post_map[d['post_id']]} for d in batch]})
            validate_shape(output, JUDGE_SCHEMA)
            expected = {(d['claim_id'], d['post_id']) for d in batch}
            actual = [(d['claim_id'], d['post_id']) for d in output['decisions']]
            if set(actual) != expected or len(actual) != len(expected):
                raise ModelError('Auditoría no cubre exactamente los pares esperados')
            by_id = {(d['claim_id'], d['post_id']): d for d in output['decisions']}
            for original in batch:
                reviewed = gate_decision(by_id[(original['claim_id'], original['post_id'])],
                                         claims[original['claim_id']], post_map[original['post_id']],
                                         prepared['video'], now)
                original['audit'] = reviewed
                # Relation disagreement is uncertainty, not a reason to swap labels and accept.
                if reviewed['status'] == 'aceptado' and reviewed['relation'] == original['relation']:
                    original.update(reviewed)
                    original['audit'] = dict(reviewed)
                else:
                    original['status'] = 'descartado_en_auditoria'
                result['audit_completed'] += 1
        except ModelError as error:
            result['errors'].append({'stage': 'audit', 'batch': offset//batch_size, 'detail': str(error)})
            result['status'] = 'partial'
            break
    result['connections'] = [d for d in result['decisions'] if d['status'] == 'aceptado']
    result['model_calls'] = model.calls
    result['model_records'] = model.records


def purge(workspace, now):
    """Only deletes this module's managed matches.json; never source analyses or arbitrary files."""
    removed = 0
    workspace = Path(workspace)
    if workspace.is_symlink():
        raise ValueError('El workspace no puede ser symlink')
    for file in workspace.glob('*/matches.json'):
        if file.is_symlink() or file.parent.is_symlink():
            continue
        data = json.loads(file.read_text())
        if str(data.get('version', '')).startswith('semantic-links-') and date(data['expires_at']) <= now:
            file.unlink()
            removed += 1
    return removed



def digest(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def reaudit(result, prepared, corpus, accounts, model, now):
    """Only the exact pinned sources may be re-audited; edits require a new job."""
    if (not isinstance(prepared.get('analysis_sha256'),str) or len(prepared['analysis_sha256'])!=64
            or result.get('analysis_sha256') != prepared.get('analysis_sha256')
            or result.get('corpus_sha256') != digest(corpus)
            or result.get('video_id') != prepared['video']['video_id']
            or result.get('expires_at') != prepared['expires_at']):
        raise ValueError('Fuentes reemplazadas: regenerar trabajo de enriquecimiento')
    if now >= date(prepared['expires_at']):
        raise ValueError('Vídeo vencido')
    posts, _ = eligible_posts(corpus, accounts, now)
    audit_result(result, prepared, posts, model, now)
    return result

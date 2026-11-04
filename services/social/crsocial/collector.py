"""Isolated Scraper.tech X collector. Python standard library; no CryptoReport imports."""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE = 'https://api.scraper.tech/'


class CollectionError(Exception):
    def __init__(self, kind, detail, *, code=None, retry_after=None, http=None):
        self.kind, self.code, self.retry_after, self.http = kind, code, retry_after, http
        super().__init__(detail)

    def public(self):
        result={'kind':self.kind,'detail':str(self)}
        result.update({k:v for k,v in {'code':self.code,'retry_after':self.retry_after,'http':self.http}.items() if v is not None})
        return result


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def credential(env_file=None):
    key = os.environ.get('SCRAPER_TECH_KEY', '').strip()
    if not key and env_file:
        # Read only the named binding; never execute/source shell syntax.
        for line in Path(env_file).read_text().splitlines():
            if line.startswith('SCRAPER_TECH_KEY='):
                key = line.split('=', 1)[1].strip().strip('"\'')
                break
    if not key:
        raise CollectionError('auth', 'Falta SCRAPER_TECH_KEY; usa entorno o --env-file.')
    return key


def handle(value):
    value = value.strip()
    if value.startswith(('https://', 'http://')):
        parsed = urllib.parse.urlsplit(value)
        if parsed.hostname not in ('x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'):
            raise ValueError('URL de cuenta inválida')
        value = parsed.path.strip('/')
    value = value.removeprefix('@')
    if not re.fullmatch(r'[A-Za-z0-9_]{1,15}', value):
        raise ValueError('Handle inválido')
    return value.lower()


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value) if str(value).isdigit() else None
    except (ValueError, TypeError):
        return None


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (ValueError, TypeError):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc).isoformat()


def normalize(item, profile, requested_handle, fetched_at):
    if not isinstance(item, dict):
        raise CollectionError('schema', 'Post no es objeto')
    post_id = item.get('tweet_id')
    # JSON numeric IDs can already have lost precision in other runtimes.
    if not isinstance(post_id, str) or not post_id.isdigit():
        raise CollectionError('schema', 'tweet_id debe ser string numérico')
    text = item.get('text')
    if not isinstance(text, str) or not text.strip():
        raise CollectionError('schema', f'Post {post_id} sin texto válido')
    date = timestamp(item.get('created_at'))
    if date is None:
        raise CollectionError('schema', f'Post {post_id} sin fecha válida')
    author = item.get('author') or item.get('user_info') or {}
    if not isinstance(author, dict):
        raise CollectionError('schema', f'Post {post_id} con autor inválido')
    author_id = author.get('rest_id') or author.get('id')
    profile_id = profile.get('rest_id') or profile.get('id')
    own = author_id is not None and profile_id is not None and str(author_id) == str(profile_id)
    author_handle = author.get('screen_name') or item.get('screen_name')
    if author_handle is not None and not isinstance(author_handle, str):
        raise CollectionError('schema', f'Post {post_id} con handle inválido')
    provenance = 'post' if author_handle else None
    if not author_handle and own and str(profile.get('profile', '')).lower() == requested_handle:
        author_handle = profile['profile']
        provenance = 'profile_matched_by_id'
    entities = item.get('entities')
    urls = entities.get('urls', []) if isinstance(entities, dict) else []
    if not isinstance(urls, list):
        raise CollectionError('schema', f'Post {post_id} con urls inválidas')
    return {
        'id': post_id, 'url': f'https://x.com/i/web/status/{post_id}',
        'text': text, 'published_at': date, 'fetched_at': fetched_at,
        'author_id': str(author_id) if author_id is not None else None,
        'author_handle': author_handle, 'author_handle_source': provenance,
        'avatar_url': author.get('avatar') or (profile.get('avatar') if own else None),
        'belongs_to_requested_account': own if author_id and profile_id else
                                        (author_handle.lower() == requested_handle if author_handle else None),
        'language': item.get('lang'), 'conversation_id': item.get('conversation_id'),
        'metrics': {name: number(item.get(raw)) for name, raw in
                    [('likes', 'favorites'), ('reposts', 'retweets'), ('replies', 'replies'),
                     ('quotes', 'quotes'), ('views', 'views'), ('bookmarks', 'bookmarks')]},
        'links': [u.get('expanded_url') or u.get('url') for u in urls if isinstance(u, dict)],
        'media': item.get('media'),
        # Missing flags mean unknown, never silently "original post".
        'is_reply': item.get('is_reply') if isinstance(item.get('is_reply'), bool) else None,
        'is_repost': item.get('is_retweet') if isinstance(item.get('is_retweet'), bool) else None,
        'is_quote': item.get('is_quote') if isinstance(item.get('is_quote'), bool) else None,
        'text_completeness': 'unverified',
    }


def http_transport(endpoint, params, key, timeout):
    url = BASE + endpoint + '?' + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={'Scraper-Key': key, 'Accept': 'application/json'})
    # Never forward the credential across redirects, even to another provider host.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect())
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read(10_000_001)
        if len(body) > 10_000_000:
            raise CollectionError('schema', 'Respuesta supera 10 MB')
        return response.code, body.decode('utf-8', errors='replace'), {
            k: v for k, v in response.headers.items()
            if any(word in k.lower() for word in ('ratelimit', 'quota', 'credit', 'retry-after'))}


class Client:
    def __init__(self, key, *, max_calls=5, timeout=45, transport=http_transport):
        if not key or not 1 <= max_calls <= 100 or not 0 < timeout <= 120:
            raise ValueError('Clave, presupuesto o timeout inválido')
        self.key, self.max_calls, self.timeout, self.transport = key, max_calls, timeout, transport
        self.calls = 0
        self.evidence = []

    def request(self, endpoint, params):
        if self.calls >= self.max_calls:
            raise CollectionError('budget', 'Presupuesto de llamadas agotado')
        self.calls += 1
        started = time.monotonic()
        record = {'endpoint': endpoint, 'params': dict(params), 'at': utcnow(), 'call': self.calls}
        self.evidence.append(record)
        try:
            status, raw, headers = self.transport(endpoint, params, self.key, self.timeout)
        except (OSError, TimeoutError) as error:
            record.update(error='network', duration_s=round(time.monotonic()-started, 3))
            raise CollectionError('network', 'Fallo de red o timeout; sin reintento automático') from error
        finally:
            record['duration_s'] = round(time.monotonic()-started, 3)
        # Redact even if a remote service echoes the credential.
        raw = raw.replace(self.key, '[REDACTED]')
        record.update(http=status, headers={k: str(v).replace(self.key, '[REDACTED]') for k, v in headers.items()}, body=raw)
        if status in (401, 403):
            raise CollectionError('auth', f'HTTP {status}: credencial o acceso denegado', http=status, code='access_denied')
        if status in (402, 429):
            retry=None
            value=next((v for k,v in headers.items() if k.lower()=='retry-after'),None)
            if value:
                try:retry=max(0,int(value))
                except (ValueError,TypeError):
                    try:retry=max(0,int((parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds()))
                    except (ValueError,TypeError):pass
            expired=status==402 and any(s in raw.lower() for s in ('tariff ended','plan expired','subscription expired'))
            code='plan_expired' if expired else 'rate_limited' if status==429 else 'payment_required'
            detail='HTTP 402: plan del proveedor vencido' if expired else f'HTTP {status}: cuota o límite; ejecución detenida'
            raise CollectionError('quota', detail, code=code, retry_after=retry, http=status)
        if status != 200:
            raise CollectionError('http', f'HTTP {status}', http=status)
        try:
            payload = json.loads(raw)
        except ValueError as error:
            raise CollectionError('schema', 'Respuesta no JSON') from error
        if not isinstance(payload, dict):
            raise CollectionError('schema', 'Respuesta no es objeto')
        if payload.get('error') or payload.get('status') not in (None, 'ok', 'success'):
            message = str(payload.get('error') or payload.get('status')).lower()
            kind = 'quota' if any(w in message for w in ('quota', 'limit', 'subscription', 'credit', 'upgrade')) else 'provider'
            if any(w in message for w in ('access denied', 'invalid key', 'unauthorized', 'forbidden')):
                kind = 'auth'
            raise CollectionError(kind, f'Error del proveedor dentro de HTTP 200 ({kind}); ver evidencia')
        return payload

    def collect(self, account='beincrypto_es', *, max_pages=3, cursor=None,
                since_id=None, mode='timeline', since=None, until=None,
                since_at=None, until_at=None):
        calls_at_start = self.calls
        account = handle(account)
        if mode not in ('timeline', 'search') or not 1 <= max_pages <= 100:
            raise ValueError('Modo o máximo de páginas inválido')
        if since_id is not None and not re.fullmatch(r'\d+', since_id):
            raise ValueError('since_id inválido')
        for date in (since, until):
            if date:
                datetime.strptime(date, '%Y-%m-%d')
        if (since or until) and mode != 'search':
            raise ValueError('Fechas requieren --mode search')
        if since and until and since >= until:
            raise ValueError('until debe ser posterior a since')
        if (since_at is None) != (until_at is None):
            raise ValueError('since_at y until_at deben usarse juntos')
        if since_at is not None:
            if mode != 'search' or since or until:
                raise ValueError('Ventana exacta requiere search sin fechas diarias')
            if not all(isinstance(v, datetime) and v.tzinfo is not None for v in (since_at, until_at)):
                raise ValueError('Ventana exacta requiere datetime con zona horaria')
            if since_at >= until_at:
                raise ValueError('Ventana exacta inválida')
        result = {'account': account, 'started_at': utcnow(), 'mode': mode, 'posts': [],
                  'pages': 0, 'duplicates': 0, 'excluded_by_since_id': 0, 'rejected': [],
                  'out_of_window': [],
                  'next_cursor': cursor, 'stop_reason': 'page_limit', 'error': None,
                  'coverage_complete': False, 'requests_used': 0}
        seen, cursors = set(), {cursor} if cursor else set()
        for _ in range(max_pages):
            if mode == 'timeline':
                endpoint, params = 'timeline.php', {'screenname': account}
            else:
                query = f'from:{account}'
                if since:
                    query += f' since:{since}'
                if until:
                    query += f' until:{until}'
                if since_at is not None:
                    query += f' since_time:{int(since_at.timestamp())} until_time:{int(until_at.timestamp())}'
                endpoint, params = 'search.php', {'query': query, 'search_type': 'Latest'}
            if cursor:
                params['cursor'] = cursor
            try:
                page = self.request(endpoint, params)
                items = page.get('timeline')
                if not isinstance(items, list):
                    raise CollectionError('schema', 'Falta timeline como array; no se interpreta como cero posts')
                profile = page.get('user') or {}
                if not isinstance(profile, dict):
                    raise CollectionError('schema', 'user no es objeto')
                if profile.get('profile') and str(profile['profile']).lower() != account:
                    raise CollectionError('schema', 'Perfil devuelto no coincide con la cuenta solicitada')
                next_cursor = page.get('next_cursor')
                if next_cursor is not None and not isinstance(next_cursor, str):
                    raise CollectionError('schema', 'Cursor inválido')
                result['pages'] += 1
                for item in items:
                    try:
                        post = normalize(item, profile, account, utcnow())
                    except CollectionError as error:
                        result['rejected'].append(str(error))
                        continue
                    if post['id'] in seen:
                        result['duplicates'] += 1
                        continue
                    seen.add(post['id'])
                    # The live historical probe returned a post beyond until.
                    # Enforce UTC boundaries locally; retain violations as evidence.
                    date = post['published_at'][:10]
                    exact_outside = since_at is not None and not since_at <= datetime.fromisoformat(post['published_at']) < until_at
                    if exact_outside or (since and date < since) or (until and date >= until):
                        result['out_of_window'].append({'id': post['id'], 'published_at': post['published_at']})
                        continue
                    if since_id and int(post['id']) <= int(since_id):
                        result['excluded_by_since_id'] += 1
                        continue
                    result['posts'].append(post)
                result['next_cursor'] = next_cursor
                if not items:
                    result['stop_reason'] = 'empty_page'
                    break
                if not next_cursor:
                    result['stop_reason'] = 'cursor_exhausted'
                    break
                if next_cursor in cursors:
                    result['stop_reason'] = 'cursor_loop'
                    break
                cursors.add(next_cursor)
                cursor = next_cursor
            except CollectionError as error:
                result.update(stop_reason='error', error=error.public())
                break
        result['posts'].sort(key=lambda p: (p['published_at'], int(p['id'])), reverse=True)
        result['requests_used'] = self.calls - calls_at_start
        result['finished_at'] = utcnow()
        return result


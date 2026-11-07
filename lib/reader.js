const { createHash } = require('node:crypto');

const PATHS = /^(?:(?:index|pipeline-status|social-feed|social-connections)\.json|g\/[a-f0-9]{16,64}\/(?:v\/[A-Za-z0-9_-]{11}|a\/[a-z0-9]{1,32}|t\/[a-z0-9-]{1,160})\.json)$/;
const MAX_BYTES = 4_000_000; // Under Vercel's function response limit, before edge compression.

function reply(res, status, value, headers = {}) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Cache-Control', 'no-store');
  for (const [key, val] of Object.entries(headers)) res.setHeader(key, val);
  res.end(value == null ? undefined : typeof value === 'string' || Buffer.isBuffer(value) ? value : JSON.stringify(value));
}

module.exports = function createReader({ originEnv = 'CR_DATA_ORIGIN', authEnv = 'CR_DATA_AUTHORIZATION', internal = false } = {}) {
  return async function handler(req, res) {
  if (!['GET', 'HEAD'].includes(req.method)) return reply(res, 405, { error: 'method_not_allowed' }, { Allow: 'GET, HEAD' });
  const values = req.query?.path ?? new URL(req.url, 'http://localhost').searchParams.getAll('path');
  const path = typeof values === 'string' ? values : Array.isArray(values) && values.length === 1 ? values[0] : null;
  if (typeof path !== 'string' || !PATHS.test(path)) return reply(res, 400, { error: 'invalid_data_path' });
  let target;
  try {
    const origin = new URL(process.env[originEnv] || '');
    if (origin.username || origin.password || origin.search || origin.hash || (!internal && !origin.pathname.endsWith('/'))) throw Error('invalid_origin');
    if (origin.protocol !== 'https:' && !(origin.protocol === 'http:' && (internal || ['127.0.0.1', 'localhost', '[::1]'].includes(origin.hostname)))) throw Error('invalid_origin');
    if (internal) {
      origin.pathname = origin.pathname.replace(/\/?$/, '/');
      target = new URL('api/data', origin);
      target.searchParams.set('path', path);
    } else target = new URL(path, origin);
  } catch {
    return reply(res, 503, { error: internal ? 'data_service_not_configured' : 'data_origin_not_configured' });
  }
  try {
    const headers = { Accept: 'application/json' };
    if (authEnv && process.env[authEnv]) headers.Authorization = process.env[authEnv];
    const upstream = await fetch(target, { headers, redirect: 'manual', signal: AbortSignal.timeout(internal ? 12_000 : 10_000) });
    if (internal && [503, 504].includes(upstream.status)) {
      await upstream.body?.cancel();
      return reply(res, upstream.status, { error: upstream.status === 503 ? 'data_origin_not_configured' : 'data_origin_timeout' });
    }
    if (upstream.status === 404) { await upstream.body?.cancel(); return reply(res, 404, { error: 'data_not_found' }); }
    if (!upstream.ok || !/application\/(?:json|[a-z0-9.-]+\+json)\b/i.test(upstream.headers.get('content-type') || '')) {
      await upstream.body?.cancel();
      return reply(res, 502, { error: 'data_origin_unavailable' });
    }
    if (+upstream.headers.get('content-length') > MAX_BYTES) {
      await upstream.body?.cancel();
      return reply(res, 502, { error: 'data_response_too_large' });
    }
    const reader = upstream.body.getReader(), chunks = [];
    let length = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > MAX_BYTES) { await reader.cancel(); return reply(res, 502, { error: 'data_response_too_large' }); }
      chunks.push(value);
    }
    const body = Buffer.concat(chunks, length);
    const json = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(body));
    if (!json || typeof json !== 'object' || Array.isArray(json)) throw Error('invalid_json');
    if (path === 'index.json' && (!Array.isArray(json.videos) || !Array.isArray(json.channels) || !Array.isArray(json.topics))) throw Error('invalid_index');
    const etag = '"' + createHash('sha256').update(body).digest('hex') + '"';
    const cache = path.startsWith('g/') ? 'public, max-age=31536000, immutable' : 'public, max-age=0, s-maxage=30, stale-while-revalidate=60';
    const responseHeaders = { ETag: etag, 'Cache-Control': cache };
    const tags = String(req.headers['if-none-match'] || '').split(',').map(t => t.trim());
    if (tags.includes(etag) || tags.includes('*')) return reply(res, 304, null, responseHeaders);
    return reply(res, 200, req.method === 'HEAD' ? null : body, responseHeaders);
  } catch (error) {
    const timeout = ['TimeoutError', 'AbortError'].includes(error.name);
    return reply(res, timeout ? 504 : 502, { error: timeout ? 'data_origin_timeout' : 'data_origin_unavailable' });
  }
  };
};

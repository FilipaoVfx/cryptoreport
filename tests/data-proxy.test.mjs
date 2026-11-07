// Value: protects=read-only proxy rejects arbitrary destinations and invalid origin responses; fails_when=path or response guards are removed; why_new=no Vercel adapter existed; seam=none; no_claim=production origin reachability.
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import handler from '../services/data/api/data.js';

test('data proxy enforces its real HTTP boundary without forwarding client credentials', async t => {
  let upstreamMode = 'ok', seen = [], authorization = '';
  const payload = { videos: [], channels: [], topics: [], generation: 'test' };
  const upstream = http.createServer((req, res) => {
    seen.push(req.url); authorization = req.headers.authorization || '';
    if (upstreamMode === 'redirect') { res.writeHead(302, { Location: 'https://example.com/private' }); return res.end(); }
    if (upstreamMode === 'html') { res.setHeader('Content-Type', 'text/html'); return res.end('<h1>Login</h1>'); }
    if (upstreamMode === 'malformed') { res.setHeader('Content-Type', 'application/json'); return res.end('{'); }
    if (upstreamMode === 'oversize') { res.setHeader('Content-Type', 'application/json'); res.setHeader('Content-Length', '4000001'); return res.end(); }
    if (upstreamMode === 'oversize-stream') { res.setHeader('Content-Type', 'application/json'); res.write(' '.repeat(4000001)); return res.end(); }
    if (upstreamMode === 'notfound') { res.writeHead(404); return res.end(); }
    if (upstreamMode === 'hanging') { res.setHeader('Content-Type', 'application/json'); res.flushHeaders(); return; }
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify(upstreamMode === 'invalid-index' ? {} : payload));
  });
  const server = http.createServer(handler);
  await Promise.all([new Promise(resolve => upstream.listen(0, '127.0.0.1', resolve)), new Promise(resolve => server.listen(0, '127.0.0.1', resolve))]);
  const original = { origin: process.env.CR_DATA_ORIGIN, auth: process.env.CR_DATA_AUTHORIZATION };
  t.after(() => { upstream.close(); server.close(); server.closeAllConnections(); upstream.closeAllConnections(); for (const [name, value] of Object.entries({ CR_DATA_ORIGIN: original.origin, CR_DATA_AUTHORIZATION: original.auth })) { if (value == null) delete process.env[name]; else process.env[name] = value; } });
  process.env.CR_DATA_ORIGIN = `http://127.0.0.1:${upstream.address().port}/data/`;
  process.env.CR_DATA_AUTHORIZATION = 'Bearer fixture-server-only';
  const url = path => `http://127.0.0.1:${server.address().port}/api/data?path=${encodeURIComponent(path)}`;
  await t.test('index is JSON, supports validators, and never copies incoming authorization', async () => {
    const response = await fetch(url('index.json'), { headers: { Authorization: 'Bearer incoming-client', Cookie: 'private=client' } });
    assert.equal(response.status, 200); assert.deepEqual(await response.json(), payload);
    assert.equal(authorization, 'Bearer fixture-server-only');
    assert.equal(seen.at(-1), '/data/index.json');
    assert.equal(response.headers.get('set-cookie'), null);
    assert.match(response.headers.get('cache-control'), /s-maxage=30/);
    assert.equal((await fetch(url('index.json'), { headers: { 'If-None-Match': response.headers.get('etag') } })).status, 304);
    assert.equal(await (await fetch(url('index.json'), { method: 'HEAD' })).text(), '');
  });
  await t.test('immutable generation documents remain addressable', async () => {
    const response = await fetch(url('g/' + 'a'.repeat(32) + '/v/abcdefghijk.json'));
    assert.equal(response.status, 200); assert.match(response.headers.get('cache-control'), /immutable/);
  });
  await t.test('published thesis documents remain addressable', async () => {
    const response = await fetch(url('g/' + 'a'.repeat(32) + '/t/btc-corrige-antes-de-subir.json'));
    assert.equal(response.status, 200); assert.match(response.headers.get('cache-control'), /immutable/);
  });
  await t.test('path traversal, arbitrary URLs, duplicate paths and unsupported methods cannot contact upstream', async () => {
    const count = seen.length;
    for (const path of ['../.env', 'https://example.com/private', 'g/' + 'a'.repeat(32) + '/v/../../../config.json', 'state.sqlite', 'index.json?token=x']) assert.equal((await fetch(url(path))).status, 400);
    assert.equal((await fetch(url('index.json') + '&path=social-feed.json')).status, 400);
    assert.equal((await fetch(url('index.json'), { method: 'POST' })).status, 405);
    assert.equal(seen.length, count);
  });
  await t.test('origin redirects, login HTML, malformed JSON and excessive payloads are rejected, never cached', async () => {
    for (const mode of ['redirect', 'html', 'malformed', 'oversize', 'oversize-stream', 'invalid-index']) {
      upstreamMode = mode;
      const response = await fetch(url('index.json'));
      assert.equal(response.status, 502, mode); assert.equal(response.headers.get('cache-control'), 'no-store');
      assert.ok(!(await response.text()).includes('fixture-server-only'));
    }
  });
  await t.test('missing documents retain their 404 outcome', async () => {
    upstreamMode = 'notfound';
    const response = await fetch(url('index.json'));
    assert.equal(response.status, 404); assert.deepEqual(await response.json(), { error: 'data_not_found' });
    assert.equal(response.headers.get('cache-control'), 'no-store');
  });
  await t.test('a stalled body times out rather than exhausting function duration', { timeout: 15000 }, async () => {
    upstreamMode = 'hanging';
    const response = await fetch(url('index.json'));
    assert.equal(response.status, 504); assert.deepEqual(await response.json(), { error: 'data_origin_timeout' });
  });
  await t.test('missing or insecure origin fails explicitly', async () => {
    for (const value of ['', 'http://example.com/data/', 'https://user:pass@example.com/data/', 'https://example.com/data/?k=secret']) {
      process.env.CR_DATA_ORIGIN = value;
      const response = await fetch(url('index.json')); assert.equal(response.status, 503);
      assert.deepEqual(await response.json(), { error: 'data_origin_not_configured' });
    }
  });
});

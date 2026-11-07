// Protects the public gateway -> private reader -> published origin boundary over real HTTP.
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import gateway from '../apps/web/api/data.js';
import reader from '../services/data/api/data.js';

test('binding routes published JSON without forwarding browser credentials or using an origin fallback', async t => {
  const saved = Object.fromEntries(['DATA_SERVICE_URL', 'CR_DATA_ORIGIN', 'CR_DATA_AUTHORIZATION'].map(k => [k, process.env[k]]));
  const seen = { private: [], origin: [] };
  const document = { videos: [], channels: [], topics: [] };
  const origin = http.createServer((req, res) => {
    seen.origin.push({ url: req.url, authorization: req.headers.authorization, cookie: req.headers.cookie });
    res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(document));
  });
  const backend = http.createServer((req, res) => {
    seen.private.push({ url: req.url, authorization: req.headers.authorization, cookie: req.headers.cookie });
    return reader(req, res);
  });
  const web = http.createServer(gateway);
  const servers = [origin, backend, web];
  t.after(() => {
    for (const server of servers) { server.closeAllConnections(); server.close(); }
    for (const [key, value] of Object.entries(saved)) { if (value == null) delete process.env[key]; else process.env[key] = value; }
  });
  for (const server of servers) await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  process.env.DATA_SERVICE_URL = `http://127.0.0.1:${backend.address().port}`; // Fake binding, only inside this test.
  process.env.CR_DATA_ORIGIN = `http://127.0.0.1:${origin.address().port}/data/`;
  process.env.CR_DATA_AUTHORIZATION = 'Bearer origin-only';
  const url = `http://127.0.0.1:${web.address().port}/api/data?path=index.json`;
  const response = await fetch(url, { headers: { Authorization: 'Bearer browser', Cookie: 'session=browser' } });
  assert.equal(response.status, 200); assert.deepEqual(await response.json(), document);
  assert.deepEqual(seen.private[0], { url: '/api/data?path=index.json', authorization: undefined, cookie: undefined });
  assert.deepEqual(seen.origin[0], { url: '/data/index.json', authorization: 'Bearer origin-only', cookie: undefined });
  assert.match(response.headers.get('cache-control'), /s-maxage=30/);
  assert.equal((await fetch(url, { headers: { 'If-None-Match': response.headers.get('etag') } })).status, 304);
  assert.equal(await (await fetch(url, { method: 'HEAD' })).text(), '');
  const count = seen.private.length;
  assert.equal((await fetch(url + '&path=social-feed.json')).status, 400);
  assert.equal((await fetch(url, { method: 'POST' })).status, 405);
  assert.equal(seen.private.length, count);
  delete process.env.CR_DATA_ORIGIN;
  const unconfiguredOrigin = await fetch(url);
  assert.equal(unconfiguredOrigin.status, 503);
  assert.deepEqual(await unconfiguredOrigin.json(), { error: 'data_origin_not_configured' });
  process.env.CR_DATA_ORIGIN = `http://127.0.0.1:${origin.address().port}/data/`;
  delete process.env.DATA_SERVICE_URL;
  const missingBinding = await fetch(url);
  assert.equal(missingBinding.status, 503);
  assert.deepEqual(await missingBinding.json(), { error: 'data_service_not_configured' });
  assert.equal(seen.private.length, count + 1, 'missing binding must not contact either service or external origin');
});

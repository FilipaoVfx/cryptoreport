// Value: protects=concurrent refreshes retain the latest connectivity status and evidence; fails_when=an older cache write overtakes a newer fallback; seam=service-worker platform APIs; no_claim=physical device behavior.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

test('a newer failed refresh cannot be overtaken by an older successful cache write', async () => {
  const origin = 'https://app.example', url = origin + '/data/index.json';
  const index = { generation: 'a'.repeat(32), generatedAt: '2026-11-03T00:00:00Z', videos: [], channels: [], topics: [] };
  const json = value => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
  const stored = new Map([[url, json(index)]]), messages = [], handlers = new Map();
  let releaseWrite, writeStarted, calls = 0, held = false;
  const writeGate = new Promise(resolve => { releaseWrite = resolve; });
  const enteredWrite = new Promise(resolve => { writeStarted = resolve; });
  const address = key => typeof key === 'string' ? new URL(key, origin).href : key.url || key.href;
  const cache = {
    async match(key) { return stored.get(address(key))?.clone(); },
    async keys() { return [...stored.keys()].map(key => new Request(key)); },
    async delete(key) { return stored.delete(address(key)); },
    async put(key, response) {
      const name = address(key);
      if (name === url && !held) { held = true; writeStarted(); await writeGate; }
      stored.set(name, response.clone());
    }
  };
  const sandbox = {
    URL, Request, Response, Headers, TextDecoder,
    caches: { open: async () => cache },
    fetch: async () => ++calls === 1 ? json(index) : new Response('{}', { status: 503 }),
    self: { location: { origin }, clients: { matchAll: async () => [{ postMessage: message => messages.push(message) }], get: async () => ({ url: origin + '/b4-urania/#/diario' }) }, addEventListener: (name, handler) => handlers.set(name, handler) }
  };
  vm.runInNewContext('const VERSION = "test", PRECACHE = [];\n' + await readFile('web/sw.js', 'utf8'), sandbox);
  const read = () => {
    let response;
    handlers.get('fetch')({ request: new Request(url), clientId: 'reader', respondWith: promise => { response = promise; } });
    return response;
  };
  const older = read();
  await enteredWrite;
  const newer = read();
  try {
    const first = await Promise.race([newer.then(() => 'newer-returned'), new Promise(resolve => setImmediate(() => resolve('write-still-pending')))]);
    assert.equal(first, 'write-still-pending', 'the newer fallback must await the preceding cache write');
  } finally { releaseWrite(); }
  const responses = await Promise.all([older, newer]);
  assert.deepEqual(await Promise.all(responses.map(response => response.json())), [index, index]);
  assert.equal(calls, 2);
  assert.equal(messages.at(-1).type, 'DATA_FALLBACK', 'the latest failed refresh must retain the stale-data notice');
});

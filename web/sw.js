/* VERSION and PRECACHE are injected by the reproducible build. */
const SHELL = 'cryptoreport-shell-' + VERSION;
const DATA = 'cryptoreport-data-v1';
const MAX_ENTRIES = 64, MAX_TOTAL_BYTES = 32 * 1024 * 1024, MAX_ITEM_BYTES = 4_000_000;
const ASSETS = new Set(PRECACHE);
const dataReads = new Map();

self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL).then(cache => cache.addAll(PRECACHE)));
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) if (name.startsWith('cryptoreport-shell-') && name !== SHELL) await caches.delete(name);
    await self.clients.claim();
  })());
});
self.addEventListener('message', event => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
});

async function remember(cache, request, response) {
  if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) return;
  const body = await response.clone().arrayBuffer();
  if (body.byteLength > MAX_ITEM_BYTES) return;
  const headers = new Headers(response.headers);
  headers.set('X-CryptoReport-Bytes', String(body.byteLength));
  let generation = null;
  if (new URL(request.url).pathname === '/data/index.json') {
    const index = JSON.parse(new TextDecoder().decode(body));
    if (/^[a-f0-9]{16,64}$/.test(index.generation)) {
      generation = index.generation;
      headers.set('X-CryptoReport-Generation', generation);
      if (Number.isFinite(Date.parse(index.generatedAt))) headers.set('X-CryptoReport-Generated-At', new Date(index.generatedAt).toISOString());
    }
  }
  headers.delete('Content-Encoding');
  headers.delete('Content-Length');
  await cache.put(request, new Response(body, { status: 200, headers }));
  if (generation) await cache.put(new URL('/__pwa_snapshot__/' + generation + '/index.json', self.location.origin), new Response(body, { status: 200, headers }));
  const keys = await cache.keys();
  const rows = await Promise.all(keys.map(async key => {
    const stored = await cache.match(key);
    return { key, path: new URL(key.url).pathname, generation: stored.headers.get('X-CryptoReport-Generation'), size: +stored.headers.get('X-CryptoReport-Bytes') || 0, removed: false };
  }));
  let total = rows.reduce((n, row) => n + row.size, 0), count = rows.length;
  while (count > MAX_ENTRIES || total > MAX_TOTAL_BYTES) {
    const row = rows.find(candidate => !candidate.removed && candidate.path !== '/data/index.json' &&
      !(candidate.path.startsWith('/__pwa_snapshot__/') && rows.some(detail => !detail.removed && detail.path.startsWith('/data/g/' + candidate.generation + '/'))));
    if (!row) break;
    await cache.delete(row.key); row.removed = true; count--; total -= row.size;
  }
}

async function offlineIndex(cache, request, clientId) {
  const current = await cache.match(request, { ignoreSearch: true });
  const keys = await cache.keys(), visited = new Map(), candidates = [];
  let wanted = null;
  try { wanted = (await self.clients.get(clientId))?.url.match(/#\/v\/([A-Za-z0-9_-]{11})(?:[?/]|$)/)?.[1] || null; } catch { /* The client may have closed. */ }
  for (const key of keys) {
    const match = new URL(key.url).pathname.match(/^\/data\/g\/([a-f0-9]{16,64})\/v\/([A-Za-z0-9_-]{11})\.json$/);
    if (match) { if (!visited.has(match[1])) visited.set(match[1], new Set()); visited.get(match[1]).add(match[2]); }
  }
  const indexes = keys.filter(key => new URL(key.url).pathname.startsWith('/__pwa_snapshot__/'));
  if (current) candidates.push(current);
  for (const key of indexes) candidates.push(await cache.match(key));
  const compatible = candidates.filter(response => {
    const generation = response?.headers.get('X-CryptoReport-Generation');
    return wanted ? visited.get(generation)?.has(wanted) : visited.has(generation);
  });
  compatible.sort((a, b) => (b.headers.get('X-CryptoReport-Generated-At') || '').localeCompare(a.headers.get('X-CryptoReport-Generated-At') || ''));
  return compatible[0] || current;
}

async function cachedData(request, clientId) {
  const cache = await caches.open(DATA);
  const existing = await cache.match(request, { ignoreSearch: true });
  if (new URL(request.url).pathname.startsWith('/data/g/') && existing) return existing;
  let response;
  try {
    const headers = new Headers(request.headers);
    if (existing?.headers.get('ETag')) headers.set('If-None-Match', existing.headers.get('ETag'));
    // The worker owns stale fallback. The browser's HTTP stale-while-revalidate
    // must not make an unavailable origin look like a fresh index.
    response = await fetch(request, { headers, cache: 'no-store' });
  } catch { /* An offline read can use an already visited document. */ }
  if (response?.status === 304 && existing) {
    for (const client of await self.clients.matchAll({ type: 'window' })) client.postMessage({ type: 'DATA_FRESH', path: new URL(request.url).pathname });
    return existing;
  }
  if (response && response.status < 500) {
    if (response.ok) {
      try { await remember(cache, request, response); } catch { /* Storage quota cannot break online reading. */ }
      for (const client of await self.clients.matchAll({ type: 'window' })) client.postMessage({ type: 'DATA_FRESH', path: new URL(request.url).pathname });
    }
    return response;
  }
  const cached = new URL(request.url).pathname === '/data/index.json' ? await offlineIndex(cache, request, clientId) : await cache.match(request, { ignoreSearch: true });
  if (cached) {
    for (const client of await self.clients.matchAll({ type: 'window' })) client.postMessage({ type: 'DATA_FALLBACK', path: new URL(request.url).pathname });
    return cached;
  }
  return response || new Response(JSON.stringify({ error: 'not_available_offline' }), { status: 503, headers: { 'Content-Type': 'application/json' } });
}

function orderedData(request, clientId) {
  // Serialize reads of the same document, including its cache write and status.
  // An older refresh must finish before a newer fallback can use that document.
  const key = new URL(request.url).pathname;
  const pending = (dataReads.get(key) || Promise.resolve()).catch(() => {}).then(() => cachedData(request, clientId));
  dataReads.set(key, pending);
  pending.finally(() => { if (dataReads.get(key) === pending) dataReads.delete(key); }).catch(() => {});
  return pending;
}

self.addEventListener('fetch', event => {
  const request = event.request, url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/data/')) { event.respondWith(orderedData(request, event.clientId)); return; }
  if (request.mode === 'navigate' && url.pathname.startsWith('/b4-urania')) {
    event.respondWith(caches.open(SHELL).then(async cache => await cache.match('/b4-urania/') || fetch(request)));
    return;
  }
  if (ASSETS.has(url.pathname)) event.respondWith(caches.open(SHELL).then(async cache => await cache.match(url.pathname) || fetch(request)));
});

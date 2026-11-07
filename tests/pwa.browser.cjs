// Value: protects=installed shell, visited evidence and update consent survive real navigation/offline; fails_when=worker install, cache routes or update activation break; why_new=existing browser checks do not exercise service workers; seam=none; no_claim=physical iOS installation or offline YouTube playback.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const http = require('node:http');
const { spawn } = require('node:child_process');
let base = process.env.BASE;
const output = process.env.CAPTURE_DIR || '/tmp/cryptoreport-pwa-check';

(async () => {
  await fs.mkdir(output, { recursive: true });
  let dataServer = null, fixtureServer = null, appServer = null, publication = null, browser = null, originalWorker = null;
  const failures = new Set();
  const results = [], swPath = path.resolve(__dirname, '../dist/sw.js');
  async function startApp(port = '0') {
    const child = appServer = spawn(process.execPath, ['scripts/dev.mjs'], { cwd: path.resolve(__dirname, '..'), env: { ...process.env, PORT: String(port), DATA_SERVICE_URL: `http://127.0.0.1:${dataServer.address().port}/` }, stdio: ['ignore', 'pipe', 'pipe'] });
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(Error('Dev server readiness timed out')), 15000);
      child.stdout.on('data', chunk => { const match = String(chunk).match(/http:\/\/127\.0\.0\.1:\d+\/b4-urania\//); if (match) { clearTimeout(timeout); resolve(match[0]); } });
      child.on('error', reject);
      child.on('exit', code => { clearTimeout(timeout); reject(Error('Dev server exited: ' + code)); });
    });
  }
  async function stopApp() {
    const child = appServer;
    if (child && child.exitCode == null) { const exited = new Promise(resolve => child.once('exit', resolve)); child.kill('SIGTERM'); await exited; }
    if (appServer === child) appServer = null;
  }
  try {
  if (!base) {
    const data = publication = require('./fixtures/pwa.cjs')();
    fixtureServer = http.createServer((req, res) => {
      const name = new URL(req.url, 'http://localhost').pathname;
      const cacheFixture = /\/v\/(cache|large)\d{6}\.json$/.exec(name);
      const doc = data[name] || (cacheFixture ? { fixture: name, text: 'x'.repeat(cacheFixture[1] === 'large' ? 3_000_000 : 10) } : null);
      res.setHeader('Content-Type', 'application/json');
      res.statusCode = failures.has(name) ? 503 : doc ? 200 : 404;
      res.end(JSON.stringify(res.statusCode === 200 ? doc : { error: 'fixture_unavailable' }));
    });
    await new Promise(resolve => fixtureServer.listen(0, '127.0.0.1', resolve));
    process.env.CR_DATA_ORIGIN = `http://127.0.0.1:${fixtureServer.address().port}/data/`;
    delete process.env.CR_DATA_AUTHORIZATION;
    dataServer = http.createServer(require('../services/data/api/data.js'));
    await new Promise(resolve => dataServer.listen(0, '127.0.0.1', resolve));
    base = await startApp();
  }
  browser = await chromium.launch({ args: ['--no-sandbox'] });
  originalWorker = await fs.readFile(swPath, 'utf8');
    for (const width of [390, 360, 1280]) {
      const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 800 }, isMobile: width < 500, hasTouch: width < 500, reducedMotion: 'reduce' });
      await context.route('https://**/*', route => route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aO9sAAAAASUVORK5CYII=', 'base64') }));
      context.setDefaultTimeout(20000);
      context.setDefaultNavigationTimeout(20000);
      const page = await context.newPage(), errors = [], policyErrors = [];
      page.on('pageerror', e => errors.push(e.message));
      page.on('console', message => { if (message.type() === 'error' && /Content Security Policy|Refused to/.test(message.text())) policyErrors.push(message.text()); });
      await page.goto(new URL('/', base).href, { waitUntil: 'domcontentloaded' });
      await page.waitForFunction(() => !!window.CR?.idx);
      await page.waitForFunction(() => !!navigator.serviceWorker.controller);
      await page.evaluate(() => document.fonts.ready);
      const manifest = await (await context.request.get(new URL('/manifest.webmanifest', base).href)).json();
      assert.equal(manifest.display, 'standalone');
      assert.equal(manifest.start_url, '/b4-urania/#/diario');
      const cdp = await context.newCDPSession(page);
      const appManifest = await cdp.send('Page.getAppManifest');
      assert.equal(appManifest.errors.length, 0);
      for (const route of ['diario', 'feed', 'buscar']) {
        await page.goto(`${base}#/${route}`);
        await page.waitForFunction(() => !!window.CR?.idx);
        await page.locator('#page h1,#page .empty,#page .feed-page,.fr-feed').first().waitFor({ timeout: 15000 });
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `overflow at ${route}/${width}`);
      }
      await page.goto(`${base}#/diario`);
      await page.waitForFunction(() => !!window.CR?.idx);
      await page.locator('#page a[href^="#/v/"]').first().waitFor();
      if (width === 390) {
        await page.screenshot({ path: path.join(output, 'diario-mobile.png') });
        const installability = await cdp.send('Page.getInstallabilityErrors');
        assert.deepEqual(installability.installabilityErrors, []);
        results.push({ installability: 'PASS', manifestErrors: 0 });
      }
      if (width === 1280) await page.screenshot({ path: path.join(output, 'diario-desktop.png') });
      await page.locator('#page a[href^="#/v/"]').first().click();
      await page.waitForFunction(() => !document.getElementById('nb').hidden && document.getElementById('nb-body').textContent.length > 40);
      const before = await page.locator('#nb-body').innerText();
      await page.waitForFunction(async () => (await (await caches.open('cryptoreport-data-v1')).keys()).some(r => /\/v\/[^/]+\.json$/.test(new URL(r.url).pathname)));
      await context.setOffline(true);
      if (fixtureServer) await stopApp(); // No public HTTP server remains available to the worker.
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.waitForFunction(() => !!window.CR?.idx);
      await page.waitForFunction(() => !document.getElementById('nb').hidden && document.getElementById('nb-body').textContent.length > 40);
      assert.equal(await page.locator('#nb-body').innerText(), before);
      // Chromium's request emulation can report onLine=true after an offline reload.
      // Both states must disclose that data is cached, according to the actual browser signal.
      const reportedOnline = await page.evaluate(() => navigator.onLine);
      assert.match(await page.locator('.pwa-status').innerText(), reportedOnline ? /Sin actualización/ : /Sin conexión/);
      assert.ok(await page.evaluate(() => document.fonts.check('16px Urbanist')));
      await page.locator('#topbar [data-act="back"]').click();
      await page.locator('#page a[href^="#/v/"]').first().waitFor();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      if (width === 390) await page.screenshot({ path: path.join(output, 'diario-offline-mobile.png') });
      const miss = await page.evaluate(async () => { const response = await fetch('/data/g/' + 'f'.repeat(32) + '/v/neveropened.json'); return { status: response.status, body: await response.json() }; });
      assert.equal(miss.status, 503); assert.equal(miss.body.error, 'not_available_offline');
      await context.setOffline(false);
      if (fixtureServer) await startApp(new URL(base).port);
      if (width === 390 && publication) {
        const old = publication['/data/index.json'];
        await page.evaluate(async () => {
          const cache = await caches.open('cryptoreport-data-v1'), count = (await cache.keys()).length;
          for (let n = count; n < 64; n++) await (await fetch('/data/g/' + 'a'.repeat(32) + '/v/cache' + String(n).padStart(6, '0') + '.json')).text();
        });
        const id = old.videos[0].id, generation = 'b'.repeat(32);
        publication['/data/index.json'] = { ...old, generation, detailBase: `g/${generation}/v/`, generatedAt: new Date(Date.now() + 1000).toISOString() };
        await page.evaluate(() => CR.checkForUpdate());
        assert.equal(await page.evaluate(() => CR.idx.generation), generation);
        await context.setOffline(true);
        await stopApp();
        await page.goto(`${base}#/v/${id}`);
        await page.locator('[data-act="retry-video"]').click();
        await page.waitForFunction(() => !!window.CR?.idx);
        const restored = await page.evaluate(async () => ({ generation: CR.idx.generation, rows: await Promise.all((await (await caches.open('cryptoreport-data-v1')).keys()).map(async request => ({ path: new URL(request.url).pathname, generation: (await (await caches.open('cryptoreport-data-v1')).match(request)).headers.get('X-CryptoReport-Generation') }))) }));
        assert.equal(restored.generation, old.generation, 'offline reading must use the index matching visited evidence: ' + JSON.stringify(restored));
        await page.waitForFunction(() => !document.getElementById('nb').hidden && document.getElementById('nb-body').textContent.length > 40);
        assert.equal(await page.locator('#nb-body').innerText(), before);
        publication['/data/index.json'] = old;
        await startApp(new URL(base).port);
        await context.setOffline(false);
        results.push({ generationChangePreservesVisitedEvidence: 'PASS', mixedGenerations: false });
      }
      assert.deepEqual(errors, []); assert.deepEqual(policyErrors, []);
      results.push({ width, routes: 'PASS', offlineReload: 'PASS', evidencePreserved: 'PASS', appErrors: 0, cspViolations: 0 });
      await context.close();
    }
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await context.route('https://**/*', route => route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aO9sAAAAASUVORK5CYII=', 'base64') }));
    context.setDefaultTimeout(20000);
    context.setDefaultNavigationTimeout(20000);
    const page = await context.newPage();
    await page.goto(base); await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await page.waitForFunction(async () => !!await (await caches.open('cryptoreport-data-v1')).match('/data/index.json'));
    if (fixtureServer) {
      await page.evaluate(() => { window.fixtureMessages = []; navigator.serviceWorker.addEventListener('message', event => window.fixtureMessages.push(event.data)); });
      failures.add('/data/index.json');
      const outageProbe = await page.evaluate(async () => { const response = await fetch('/data/index.json', { cache: 'no-store' }); return { status: response.status, cached: response.headers.get('X-CryptoReport-Bytes'), controlled: !!navigator.serviceWorker.controller }; });
      try { await page.waitForFunction(() => document.querySelector('.pwa-status').textContent.includes('Sin actualización')); }
      catch (error) { console.log('RECOVERY_DIAGNOSTIC', outageProbe, await page.evaluate(() => ({ online: navigator.onLine, messages: window.fixtureMessages, banner: document.querySelector('.pwa-status').textContent }))); throw error; }
      await page.evaluate(() => fetch('/data/social-feed.json', { cache: 'no-store' }));
      assert.match(await page.locator('.pwa-status').innerText(), /Sin actualización/, 'a fresh unrelated response cannot clear a stale index');
      failures.delete('/data/index.json');
      await page.evaluate(() => fetch('/data/index.json', { cache: 'no-store' }));
      await page.locator('.pwa-status').waitFor({ state: 'hidden' });
      results.push({ originRecoveryWhileOnline: 'PASS', recoveryTracksEachPath: 'PASS' });
      const cacheLimits = await page.evaluate(async () => {
        const base = '/data/g/' + 'a'.repeat(32) + '/v/';
        for (let n = 0; n < 65; n++) await (await fetch(base + 'cache' + String(n).padStart(6, '0') + '.json')).text();
        const cache = await caches.open('cryptoreport-data-v1');
        const entryCount = (await cache.keys()).length;
        for (let n = 0; n < 12; n++) await (await fetch(base + 'large' + String(n).padStart(6, '0') + '.json')).text();
        const rows = await Promise.all((await cache.keys()).map(async key => +(await cache.match(key)).headers.get('X-CryptoReport-Bytes')));
        return { entryCount, bytes: rows.reduce((a, b) => a + b, 0), indexRetained: !!await cache.match('/data/index.json') };
      });
      assert.ok(cacheLimits.entryCount <= 64); assert.ok(cacheLimits.bytes <= 32 * 1024 * 1024); assert.ok(cacheLimits.indexRetained);
      const worker = context.serviceWorkers()[0];
      await worker.evaluate(() => { self.fixturePutCalls = 0; self.fixtureOriginalPut = Cache.prototype.put; Cache.prototype.put = async () => { self.fixturePutCalls++; throw new DOMException('Fixture storage limit', 'QuotaExceededError'); }; });
      try {
        assert.equal(await page.evaluate(async () => (await fetch('/data/g/' + 'a'.repeat(32) + '/v/cache999999.json', { cache: 'no-store' })).status), 200);
        assert.ok(await worker.evaluate(() => self.fixturePutCalls > 0));
      }
      finally { await worker.evaluate(() => { Cache.prototype.put = self.fixtureOriginalPut; delete self.fixtureOriginalPut; }); }
      results.push({ cacheEntryLimit: 'PASS', cacheByteLimit: 'PASS', indexRetained: 'PASS', storageQuotaDoesNotBreakOnlineReading: 'PASS' });
    }
    await page.evaluate(() => {
      window.fixtureInstallCalls = 0;
      const event = new Event('beforeinstallprompt', { cancelable: true });
      event.prompt = async () => { window.fixtureInstallCalls++; };
      event.userChoice = Promise.resolve({ outcome: 'dismissed' });
      dispatchEvent(event);
    });
    await page.locator('[data-pwa-install]').click();
    assert.equal(await page.evaluate(() => window.fixtureInstallCalls), 1);
    assert.equal(await page.locator('[data-pwa-install]').isVisible(), false);
    results.push({ installButtonDismissal: 'PASS', installPrompt: 'synthetic event; OS installation not automated' });
    await fs.writeFile(swPath, originalWorker.replace(/const VERSION = "[a-f0-9]+";/, 'const VERSION = "browser-update-fixture";'));
    await page.evaluate(async () => (await navigator.serviceWorker.getRegistration()).update());
    await page.locator('.pwa-status button').waitFor({ state: 'visible' });
    assert.match(await page.locator('.pwa-status').innerText(), /versión nueva/);
    await Promise.all([page.waitForEvent('load'), page.locator('.pwa-status button').click()]);
    await page.waitForFunction(async () => (await caches.keys()).includes('cryptoreport-shell-browser-update-fixture'));
    results.push({ updateRequiresUserAction: 'PASS', updateActivation: 'PASS' });
    await context.close();
    console.log(JSON.stringify(results, null, 2));
    await fs.writeFile(path.join(output, 'pwa-results.json'), JSON.stringify(results, null, 2));
  } finally {
    if (originalWorker) await fs.writeFile(swPath, originalWorker);
    if (browser) await browser.close();
    await stopApp();
    if (dataServer?.listening) { dataServer.closeAllConnections(); await new Promise(resolve => dataServer.close(resolve)); }
    if (fixtureServer?.listening) { fixtureServer.closeAllConnections(); await new Promise(resolve => fixtureServer.close(resolve)); }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });

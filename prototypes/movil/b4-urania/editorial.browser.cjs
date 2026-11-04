// Regression checks on real data. Run with the app server already running.
// NODE_PATH=/path/to/node_modules BASE=http://127.0.0.1:8741/b4-urania/ node editorial.browser.cjs
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.BASE || 'http://127.0.0.1:8741/b4-urania/';
const out = process.env.CAPTURE_DIR;
if (out) fs.mkdirSync(out, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const results = [];
  try {
    for (const width of [390, 360, 1280]) {
      const height = width === 390 ? 844 : 800;
      const context = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' });
      const page = await context.newPage(), errors = [], youtube = [];
      page.on('pageerror', e => errors.push(e.message));
      page.on('request', r => { if (/youtube.*iframe_api|youtube.*embed\//.test(r.url())) youtube.push(r.url()); });
      async function open(hash) {
        await page.goto(`${base}?sim=1${hash}`);
        await page.waitForFunction(() => document.getElementById('page').querySelector('h1,.empty') || document.querySelector('.syn-lead'), { timeout: 15000 });
      }
      async function snap(name) { if (out) await page.screenshot({ path: path.join(out, `${name}-${width}.png`) }); }
      async function noOverflow() {
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'horizontal overflow');
      }
      await open('#/diario');
      await page.locator('.entry-card').first().waitFor();
      const cards = await page.locator('.entry-card').evaluateAll(es => es.slice(0, 2).map(e => ({ bottom: e.getBoundingClientRect().bottom, height: e.getBoundingClientRect().height })));
      assert.ok(cards.length === 2 && cards[1].bottom < height - 80, 'two full cards above the dock');
      assert.equal(await page.locator('.entry-thesis,.entry-card .pulse-row,.entry-card .track').count(), 0);
      await noOverflow(); await snap('diario');
      await open('#/v/pcBbfvFmkY0?lens=sintesis');
      await page.locator('.syn-lead').waitFor();
      assert.match(await page.locator('.syn-condition').innerText(), /«80»/);
      assert.equal(await page.locator('#stage').getAttribute('data-mode'), 'none');
      assert.equal(await page.locator('iframe').count(), 0);
      assert.deepEqual(youtube, [], 'reading must not request YouTube');
      const body = await page.locator('#nb-body').evaluate(e => ({ height: e.clientHeight, scroll: e.scrollHeight }));
      assert.ok(body.height > height * .7, 'reading area gets most of viewport');
      await noOverflow(); await snap('sintesis');
      const evidence = page.locator('.syn-sec:not([hidden]) details').filter({ has: page.locator('summary', { hasText: 'Argumento completo' }) });
      await evidence.locator('summary').click();
      assert.match(await evidence.innerText(), /dominancia fiscal/);
      await page.locator('#reading-source summary').click();
      assert.match(await page.locator('#source-meta').innerText(), /Bitcoin No Cayó/);
      await page.locator('#reading-source summary').click();
      await page.locator('[data-tab="escenarios"]').click();
      assert.equal(await page.locator('#syn-h-esc').isVisible(), true);
      assert.equal(await page.locator('#syn-h-vig').isVisible(), false);
      await noOverflow(); await snap('escenarios');
      await page.locator('[data-tab="vigilar"]').click();
      const watch = page.locator('.syn-watch').first();
      await watch.locator('summary').click();
      await watch.locator('[data-act="goto-scn"]').first().click();
      assert.equal(await page.locator('#syn-h-esc').isVisible(), true);
      await page.locator('[data-tab="vigilar"]').click();
      await snap('vigilar');
      await page.locator('[data-act="lens"][data-lens="transcripcion"]').click();
      await page.locator('.doc-row').first().waitFor();
      await page.locator('[data-act="lens"][data-lens="analisis"]').click();
      await page.locator('.card-page').waitFor();
      await open('#/v/pcBbfvFmkY0?t=42&n=A1');
      await page.locator('.doc-row').first().waitFor();
      assert.equal(await page.locator('#stage').getAttribute('data-mode'), 'none');
      await open('#/?s=altcoins&tab=ranking&c=todos&p=todo&m=conversacion');
      await page.locator('.intent-row').first().waitFor();
      assert.equal(await page.locator('#f-m').count(), 0, 'ranking has no order selector');
      const ranked = await page.locator('.intent-row').evaluateAll(es => es.map(e => ({
        id: e.dataset.asset,
        videos: Number(e.querySelector('.intent-videos b').textContent),
        up: Number(e.querySelector('.intent-sides .t-up b').textContent),
        down: Number(e.querySelector('.intent-sides .t-down b').textContent),
      })));
      const source = await page.evaluate(() => fetch('../data/index.json').then(r => r.json()));
      const expected = source.topics.filter(t => t.section === 'altcoins' && t.videos.length)
        .sort((a,b) => b.videos.length-a.videos.length || b.n-a.n || a.id.localeCompare(b.id))
        .map(t => ({ id:t.id, videos:t.videos.length, up:t.sent.alcista, down:t.sent.bajista }));
      assert.deepEqual(ranked, expected, 'video order and both directions must match source data');
      assert.equal(await page.locator('.ex-filters').isVisible(), false);
      assert.equal(await page.locator('#f-q').isVisible(), false);
      assert.ok(await page.locator('.ex-tools').evaluate(e => e.getBoundingClientRect().height <= 48));
      for (const t of source.topics.filter(t => t.section === 'altcoins' && t.videos.length)) {
        const text = await page.locator(`.intent-row[data-asset="${t.id}"] .intent-context`).innerText();
        assert.doesNotMatch(text, /mixta|neutral/i);
        const other = t.sent.mixta + t.sent.neutra;
        if (other) assert.ok(text.includes(`${other} sin dirección clara`));
      }
      assert.equal(await page.locator('#stage').getAttribute('data-mode'), 'none');
      await noOverflow(); await snap('ranking');
      if (width === 390) {
        await page.locator('.ex-filter-menu > summary').click();
        await page.locator('#f-c').selectOption('nacho');
        await page.locator('.ex-filter-context').filter({ hasText: 'Nacho' }).waitFor();
        assert.equal(await page.locator('.ex-filters').isVisible(), false);
        await page.locator('.ex-filter-menu > summary').click();
        await page.locator('#f-p').selectOption('2d');
        await page.locator('.ex-filter-context').filter({ hasText: '48 h' }).waitFor();
        assert.equal(await page.locator('.ex-filter-badge').innerText(), '2');
        await noOverflow(); await snap('ranking-filtrado');
        await open('#/?s=altcoins&tab=ranking&c=todos&p=todo');
        await page.locator('.intent-row').first().waitFor();
        await page.locator('.ex-search-menu > summary').click();
        await page.locator('#f-q').fill('ETH');
        await page.waitForFunction(() => document.querySelectorAll('.intent-row').length === 1);
        assert.equal(await page.locator('.intent-row').getAttribute('data-asset'), 'eth');
        await page.keyboard.press('Escape');
        assert.equal(await page.locator('#f-q').isVisible(), false);
        assert.equal(await page.locator('#f-q-term').innerText(), 'ETH');
        await page.locator('.ex-search-menu > summary').click();
        await page.locator('#f-q').fill('');
        await page.waitForFunction(() => document.querySelectorAll('.intent-row').length > 1);
        await page.locator('h1').click();
        assert.equal(await page.locator('#f-q').isVisible(), false);
      }
      await open('#/f/eth?c=todos&p=todo');
      await page.locator('.fx-participant').first().waitFor();
      const ids = await page.locator('.fx-thesis').first().locator('.fx-participant').evaluateAll(es => es.map(e => e.dataset.creator));
      assert.equal(ids.length, new Set(ids).size, 'one participation row per creator');
      assert.ok(ids.length >= 2);
      assert.equal(await page.getByText('Coinciden 1 creador', { exact: true }).count(), 0);
      assert.equal(await page.getByText('No se pudo cargar el detalle', { exact: false }).count(), 0);
      await noOverflow(); await snap('ficha');
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#ficha').isHidden(), true);
      await open('#/feed');
      await page.waitForFunction(() => document.body.dataset.screen === 'feed' && document.querySelector('#page').innerText.includes('Feed'));
      assert.equal(await page.locator('#stage').getAttribute('data-mode'), 'none');
      await noOverflow(); await snap('feed');
      // Video and PiP are explicit actions; simulator only avoids dependence on YouTube availability.
      await open('#/v/pcBbfvFmkY0?lens=sintesis');
      await page.locator('.syn-lead').waitFor();
      await page.locator('#video-toggle').click();
      assert.equal(await page.locator('#stage').getAttribute('data-mode'), 'top');
      await page.locator('#video-pin').click();
      await page.evaluate(() => { location.hash = '#/feed'; });
      await page.waitForFunction(() => document.querySelector('#stage').dataset.mode === 'pip');
      await page.locator('[data-act="pip-close"]').click();
      assert.equal(await page.locator('#stage').getAttribute('data-mode'), 'none');
      assert.deepEqual(errors, []);
      results.push({ width, cards, reading: body, exceptions: errors.length, checks: 'PASS' });
      await context.close();
    }
    console.log(JSON.stringify(results, null, 2));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });

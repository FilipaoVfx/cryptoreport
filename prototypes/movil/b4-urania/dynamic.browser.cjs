// Real browser, deterministic delayed responses; no collection or inference.
// Set NODE_PATH to the installed Playwright node_modules directory if needed.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.BASE || 'http://127.0.0.1:8741/b4-urania/';
(async () => {
  const browser = await chromium.launch({args:['--no-sandbox']});
  let failed = 0;
  try {
    for (const [name, check] of [
      ['navigation while index loads', async page => {
        let release, started;
        const gate = new Promise(r => release = r), waiting = new Promise(r => started = r);
        await page.route('**/data/index.json', async route => { started(); await gate; await route.continue(); });
        await page.goto(base, {waitUntil:'domcontentloaded'});
        await waiting;
        await page.evaluate(() => CR.go(['feed']));
        await page.locator('#feed-quality').waitFor({state:'attached'});
        release();
        await page.waitForFunction(() => !!CR.idx);
        await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
        assert.equal(await page.locator('body').getAttribute('data-screen'), 'feed');
        assert.equal(await page.locator('#feed-quality').count(), 1, 'latest route must keep Feed');
      }],
      ['new generation invalidates video details', async page => {
        await page.goto(base, {waitUntil:'domcontentloaded'});
        await page.waitForFunction(() => !!CR.idx);
        const result = await page.evaluate(async () => {
          const id = CR.idx.videos[0].id;
          const old = await CR.loadVideo(id);
          const real = window.fetch;
          window.fetch = async (url, opts) => {
            if (String(url).endsWith('/index.json')) {
              const data = await (await real(url, opts)).json(); data.generation += '-test';
              return new Response(JSON.stringify(data));
            }
            const response = await real(url, opts);
            if (String(url).endsWith('/' + id + '.json')) {
              const data = await response.json(); data.auditMarker = 'fresh';
              return new Response(JSON.stringify(data));
            }
            return response;
          };
          await CR.checkForUpdate();
          const fresh = await CR.loadVideo(id);
          return {same: old === fresh, marker: fresh.auditMarker};
        });
        assert.equal(result.same, false); assert.equal(result.marker, 'fresh');
      }],
    ]) {
      const page = await browser.newPage({viewport:{width:390,height:844}});
      try { await check(page); console.log('PASS', name); }
      catch (error) { failed++; console.error('FAIL', name, error.message); }
      finally { await page.close(); }
    }
  } finally { await browser.close(); }
  process.exitCode = failed ? 1 : 0;
})();

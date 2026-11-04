// Real-browser regression checks; feed responses are synthetic, no collection or inference.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.BASE || 'http://127.0.0.1:8741/b4-urania/';
const out = process.env.CAPTURE_DIR;
if (out) fs.mkdirSync(out, { recursive: true });
(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const results = [];
  try {
    for (const width of [390, 360]) {
      const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 800 }, hasTouch: true, isMobile: true, reducedMotion: 'no-preference' });
      const page = await context.newPage(), errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.goto(`${base}?sim=1#/v/pcBbfvFmkY0?lens=sintesis`);
      await page.locator('.syn-lead').waitFor();
      assert.equal(await page.locator('#signal-trigger').getAttribute('aria-pressed'), 'false');
      assert.equal(await page.locator('#signal-panel').isVisible(), false);
      assert.equal(await page.locator('iframe').count(), 0);
      await page.locator('#signal-trigger').click();
      await page.locator('#signal-panel').waitFor();
      assert.equal(await page.locator('#stage').getAttribute('data-mode'), 'top');
      assert.equal(await page.locator('#signal-trigger').getAttribute('aria-pressed'), 'true');
      assert.ok(await page.locator('#nb-pulse .wv-up').count());
      assert.ok(await page.locator('#nb-pulse .wv-down').count());
      assert.equal(await page.locator('#signal-panel').evaluate(e => getComputedStyle(e).animationName), 'signal-reveal');
      // Wait for the notebook's intentional 200ms transition to finish before measuring.
      await page.waitForFunction(() => document.getElementById('signal-panel').getBoundingClientRect().top >= document.getElementById('stage').getBoundingClientRect().bottom);
      const duration = Number(await page.locator('#signal-seek').getAttribute('max'));
      const wave = await page.locator('#nb-pulse svg').boundingBox();
      await page.mouse.click(wave.x + wave.width * .6, wave.y + wave.height * .5);
      await page.waitForFunction(d => Math.abs(Number(document.getElementById('signal-seek').value) - d*.6) < 2, duration);
      const slider = page.locator('#signal-seek');
      assert.equal(await slider.evaluate(e => getComputedStyle(e).appearance), 'none');
      const track = await slider.boundingBox();
      assert.ok(track.height >= 44, 'thin visual track retains a mobile touch target');
      await page.mouse.move(track.x + track.width*.25, track.y + track.height/2);
      await page.mouse.down();
      await page.mouse.move(track.x + track.width*.75, track.y + track.height/2, {steps: 6});
      assert.equal(await page.locator('#signal-scrubber').getAttribute('data-seeking'), 'true');
      await page.waitForFunction(() => Number(getComputedStyle(document.getElementById('signal-preview')).opacity) > .99);
      const dragTarget = Number(await slider.inputValue());
      assert.ok(dragTarget > duration*.7 && dragTarget < duration*.8);
      await page.mouse.up();
      await page.waitForFunction(t => Math.abs(Number(document.getElementById('signal-seek').value)-t)<2, dragTarget);
      assert.equal(await page.locator('#signal-scrubber').getAttribute('data-seeking'), null);
      await slider.focus(); await slider.press('Home'); await slider.press('ArrowRight');
      assert.equal(Number(await slider.inputValue()), 1, 'keyboard can navigate the video');
      // Keep focus on the range: playback must still move the thumb after a seek.
      await page.waitForFunction(() => Number(document.getElementById('signal-seek').value) >= 2);
      assert.match(await slider.getAttribute('aria-valuetext'), /de 2:56/);
      await page.touchscreen.tap(track.x + track.width*.5, track.y + track.height/2);
      await page.waitForFunction(d => Math.abs(Number(document.getElementById('signal-seek').value)-d*.5)<3, duration);
      if (out) await page.screenshot({ path: path.join(out, `signal-${width}.png`) });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.locator('#signal-trigger').click();
      assert.equal(await page.locator('#signal-panel').isVisible(), false);
      assert.equal(await page.locator('#stage').getAttribute('data-mode'), 'none');
      await page.waitForFunction(() => document.getElementById('nb-body').clientHeight > innerHeight*.7);
      await page.locator('#signal-trigger').click();
      await page.locator('#video-toggle').click();
      assert.equal(await page.locator('#signal-trigger').getAttribute('aria-pressed'), 'false');
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.locator('#signal-trigger').click();
      assert.equal(await page.locator('#signal-panel').evaluate(e => getComputedStyle(e).animationName), 'none');
      assert.deepEqual(errors, []);
      results.push({ signalWidth: width, status: 'PASS' });
      await context.close();
    }
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
    const page = await context.newPage(), errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const now = Date.now();
    await page.clock.install({ time: new Date(now) });
    function post(id, expires = now + 86400000) {
      return { id, text: `Bitcoin: escenario de liquidez ${id}. Este es un post de prueba para comprobar la actualización automática del Feed.`,
        author_handle: 'one', author_id: '10', content_hash: id, published_at: new Date(now-3600000).toISOString(),
        expires_at: new Date(expires).toISOString(), quality: { visibility: 'relevante', length: 'medio', assets: ['BTC'], narratives: [] } };
    }
    let data = { version: 1, status: 'partial', last_error: { kind: 'quota' }, posts: [post('111', now+120000), post('222')],
      accounts: [{ handle: 'one', author_id: '10', name: 'Cuenta de prueba', lookback_days: 3, last_success: new Date(now).toISOString() }] };
    await page.route('**/data/social-feed.json', route => route.fulfill({ json: data }));
    await page.route('**/data/social-connections.json', route => route.fulfill({ json: { status: 'pending_schedule', connections: [] } }));
    await page.goto(`${base}#/feed`);
    await page.locator('[data-post="111"]').waitFor();
    assert.match(await page.locator('#feed-health').innerText(), /cuota/);
    await page.locator('[data-post="111"]').click();
    await page.locator('.fr-post-x').waitFor();
    await page.clock.fastForward(121000);
    await page.waitForFunction(() => document.getElementById('ficha').hidden);
    assert.equal(await page.locator('[data-post="111"]').count(), 0, 'expired posts and their open modal disappear');
    data = { ...data, status: 'ok', last_error: null, posts: [post('333')],
      accounts: data.accounts.map(a => ({ ...a, last_success: new Date(now+300000).toISOString() })) };
    await page.clock.fastForward(300001);
    await page.locator('[data-post="333"]').waitFor();
    assert.equal(await page.locator('[data-post="222"]').count(), 0);
    assert.equal(await page.locator('#feed-quality').inputValue(), 'relevante');
    data = { ...data, posts: [post('444')] };
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.locator('[data-post="444"]').waitFor();
    assert.equal(await page.locator('[data-post="333"]').count(), 0);
    assert.deepEqual(errors, []);
    results.push({ feed: 'expiry, open modal, automatic fetch, return to tab, filters', status: 'PASS' });
    await context.close();
    console.log(JSON.stringify(results, null, 2));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });

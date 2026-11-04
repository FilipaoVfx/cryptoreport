// Value: protects=reproducible installable deployment excludes repository and runtime data; fails_when=allowlist or PWA assembly breaks; why_new=no deployment build existed; seam=none; no_claim=cloud platform deployment completion.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir, stat } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';

test('deployment bundle contains an installable self-hosted shell and excludes private source/data', async () => {
  const first = JSON.parse(execFileSync(process.execPath, ['scripts/build.mjs'], { encoding: 'utf8' }));
  const second = JSON.parse(execFileSync(process.execPath, ['scripts/build.mjs'], { encoding: 'utf8' }));
  assert.equal(first.version, second.version, 'identical source produces the same cache version');
  const names = await readdir('dist');
  for (const name of ['docs', 'services', 'data', '.env', 'tests', 'serve.py']) assert.ok(!names.includes(name), name);
  const html = await readFile('dist/b4-urania/index.html', 'utf8');
  assert.ok(!html.includes('fonts.googleapis.com')); assert.ok(!html.includes('Propuestas</a>'));
  assert.match(html, /rel="manifest"/); assert.match(html, /apple-touch-icon/); assert.match(html, /pwa\.js/);
  const manifest = JSON.parse(await readFile('dist/manifest.webmanifest'));
  assert.equal(manifest.display, 'standalone'); assert.equal(manifest.scope, '/b4-urania/');
  assert.equal(manifest.start_url, '/b4-urania/#/diario');
  for (const icon of manifest.icons) {
    const bytes = await readFile('dist' + icon.src);
    const [width, height] = icon.sizes.split('x').map(Number);
    assert.equal(bytes.readUInt32BE(16), width); assert.equal(bytes.readUInt32BE(20), height);
  }
  const sw = await readFile('dist/sw.js', 'utf8');
  const precache = JSON.parse(sw.split('\n')[1].slice('const PRECACHE = '.length, -1));
  assert.ok(precache.includes('/b4-urania/')); assert.ok(precache.includes('/shared/core.js'));
  assert.ok(precache.every(url => url.startsWith('/') && !url.startsWith('/data/') && !url.startsWith('/api/')));
  for (const url of precache) if (!url.endsWith('/')) await stat('dist' + url);
  assert.ok(!sw.includes('fixture-server-only')); assert.ok(!sw.includes('CR_DATA_ORIGIN'));
});

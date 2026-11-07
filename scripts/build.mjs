import { createHash } from 'node:crypto';
import { cp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.join(root, 'dist');
const source = path.join(root, 'prototypes/movil');
// Only this owned generated directory is replaced. Never copy docs, runtime data or services.
await rm(out, { recursive: true, force: true });
await mkdir(path.join(out, 'b4-urania'), { recursive: true });
for (const name of ['index.html', 'app.css', 'app.js', 'radar.js', 'theses.js', 'feed.js', 'editorial.js']) {
  await cp(path.join(source, 'b4-urania', name), path.join(out, 'b4-urania', name));
}
await mkdir(path.join(out, 'shared'), { recursive: true });
for (const name of ['core.js', 'player.js']) await cp(path.join(source, 'shared', name), path.join(out, 'shared', name));
await cp(path.join(source, 'media'), path.join(out, 'media'), { recursive: true });
await cp(path.join(root, 'web'), out, { recursive: true });
let html = await readFile(path.join(out, 'b4-urania/index.html'), 'utf8');
html = html.replace(/<link[^>]+(?:fonts\.googleapis\.com|fonts\.gstatic\.com)[^>]*>\n?/g, '');
html = html.replace('</head>', `<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="CryptoReport">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
<link rel="icon" href="/icons/icon-192.png" type="image/png">
<link rel="stylesheet" href="/fonts.css">
<link rel="stylesheet" href="/pwa.css">
<script src="/pwa.js" defer></script>
</head>`);
html = html.replace('<a class="nh-link" href="../index.html">Propuestas</a>', '<button class="nh-link pwa-install" type="button" data-pwa-install hidden>Instalar</button>');
await writeFile(path.join(out, 'b4-urania/index.html'), html);
await writeFile(path.join(out, 'robots.txt'), 'User-agent: *\nDisallow: /\n');
await writeFile(path.join(out, 'index.html'), '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=/b4-urania/"><a href="/b4-urania/">Abrir CryptoReport</a>');

async function files(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const nested = await Promise.all(entries.map(async entry => entry.isDirectory() ? files(path.join(dir, entry.name)) : [path.join(dir, entry.name)]));
  return nested.flat();
}
const assets = (await files(out)).filter(file => !['sw.js', 'robots.txt', 'source.svg', 'OFL.txt', 'SOURCES.md'].includes(path.basename(file))).sort();
const hash = createHash('sha256');
for (const file of assets) { hash.update(path.relative(out, file)); hash.update(await readFile(file)); }
const swSource = await readFile(path.join(out, 'sw.js'), 'utf8');
hash.update(swSource);
const version = hash.digest('hex').slice(0, 16);
const urls = assets.map(file => '/' + path.relative(out, file).split(path.sep).join('/'));
urls.push('/b4-urania/');
await writeFile(path.join(out, 'sw.js'), 'const VERSION = ' + JSON.stringify(version) + ';\nconst PRECACHE = ' + JSON.stringify(urls) + ';\n' + swSource);
console.log(JSON.stringify({ build: 'ok', output: 'dist', version, precacheAssets: urls.length }));

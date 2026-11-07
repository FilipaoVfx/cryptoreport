import http from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import handler from '../apps/web/api/data.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), process.argv.includes('--service') ? '../apps/web/dist' : '../dist');
const config = JSON.parse(await readFile(new URL('../vercel.json', import.meta.url)));
const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.webmanifest': 'application/manifest+json', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.md': 'text/plain' };
const server = http.createServer(async (req, res) => {
  for (const item of config.headers[0].headers) res.setHeader(item.key, item.value);
  try {
    const url = new URL(req.url, 'http://localhost');
    // Deny repository paths that reach this static development server.
    if (/^\/(?:services|apps|docs|scripts|tests)(?:\/|$)/.test(url.pathname)) { res.writeHead(403); return res.end(); }
    if (url.pathname.startsWith('/data/')) {
      const rewritten = new URL('/api/data', url);
      for (const [key, value] of url.searchParams) rewritten.searchParams.append(key, value);
      rewritten.searchParams.append('path', url.pathname.slice(6));
      req.url = rewritten.pathname + rewritten.search;
      return await handler(req, res);
    }
    if (url.pathname === '/api/data') return await handler(req, res);
    if (['/', '/index.html'].includes(url.pathname)) { res.writeHead(307, { Location: '/b4-urania/' }); return res.end(); }
    const rel = decodeURIComponent(url.pathname);
    const file = path.resolve(root, '.' + rel + (rel.endsWith('/') ? 'index.html' : ''));
    if (!file.startsWith(root + path.sep) || rel.split('/').some(part => part.startsWith('.'))) throw Error('not_found');
    const body = await readFile(file);
    res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.end(req.method === 'HEAD' ? undefined : body);
  } catch { res.writeHead(404); res.end('No existe'); }
});
const port = Number(process.env.PORT || 8830);
server.listen(port, '127.0.0.1', () => console.log(`CryptoReport: http://127.0.0.1:${server.address().port}/b4-urania/`));

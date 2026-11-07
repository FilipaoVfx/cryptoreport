import http from 'node:http';
import handler from './api/data.js';
http.createServer((req, res) => {
  if (new URL(req.url, 'http://localhost').pathname !== '/api/data') {
    res.writeHead(404); res.end(); return;
  }
  return handler(req, res);
}).listen(Number(process.env.PORT || 8831), '127.0.0.1');

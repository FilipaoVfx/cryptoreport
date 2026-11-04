"""Servidor estático de los prototipos móviles, pensado para publicarse con un túnel de Cloudflare.

    python3 prototypes/movil/serve.py [PUERTO]

La URL pública funciona sin claves ni cookies, también en dispositivos nuevos.
"""
from __future__ import annotations

import gzip
import sys
from email.utils import formatdate, parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
         ".woff2": "font/woff2", ".ico": "image/x-icon", ".webp": "image/webp", ".webmanifest": "application/manifest+json"}
COMPRESSIBLE = {".html", ".js", ".css", ".json", ".svg"}



class Handler(BaseHTTPRequestHandler):
    server_version = "propuestas"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    def send_common(self):
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("X-Content-Type-Options", "nosniff")
        # Con «no-referrer» YouTube rechaza el reproductor incrustado; así solo viaja el origen.
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")

    def do_HEAD(self):
        self.do_GET(head=True)

    def do_GET(self, head: bool = False):
        url = urlparse(self.path)
        rel = url.path.lstrip("/") or "index.html"
        if rel.endswith("/"):
            rel += "index.html"
        target = (ROOT / rel).resolve()
        if target.is_dir():
            target = target / "index.html"
        bad = (not target.is_relative_to(ROOT) or any(p.startswith(".") for p in target.relative_to(ROOT).parts)
               or target.suffix not in TYPES or not target.is_file())
        if bad:
            self.send_response(404)
            self.send_common()
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", "9")
            self.end_headers()
            if not head:
                self.wfile.write(b"No existe")
            return
        # Validadores: con «no-cache» el navegador revalida y, si el archivo no cambió, recibe un 304 sin cuerpo.
        # Así la app puede comprobar a menudo si hay datos nuevos sin volver a descargar el índice entero.
        st = target.stat()
        etag = f'W/"{st.st_mtime_ns:x}-{st.st_size:x}"'
        inm = self.headers.get("If-None-Match")
        ims = self.headers.get("If-Modified-Since")
        fresh = False
        if inm:
            fresh = any(tag.strip().removeprefix("W/") == etag.removeprefix("W/") for tag in inm.split(","))
        elif ims:
            try:
                fresh = int(st.st_mtime) <= parsedate_to_datetime(ims).timestamp()
            except (TypeError, ValueError):
                fresh = False
        if fresh:
            self.send_response(304)
            self.send_common()
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return
        body = target.read_bytes()
        encoding = None
        if target.suffix in COMPRESSIBLE and len(body) > 1024 and "gzip" in (self.headers.get("Accept-Encoding") or ""):
            body, encoding = gzip.compress(body, 6), "gzip"
        self.send_response(200)
        self.send_common()
        self.send_header("Content-Type", TYPES[target.suffix])
        self.send_header("Cache-Control", "no-cache")
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", formatdate(st.st_mtime, usegmt=True))
        if encoding:
            self.send_header("Content-Encoding", encoding)
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8741
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Propuestas en http://127.0.0.1:{port}/ — acceso público sin cookies", flush=True)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())

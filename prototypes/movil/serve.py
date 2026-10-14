"""Servidor estático de los prototipos móviles, pensado para publicarse con un túnel de Cloudflare.

    python3 prototypes/movil/serve.py [PUERTO]

El enlace lleva una clave (?k=…): la primera visita la guarda en una cookie y redirige a la URL limpia.
Sin clave, quien llegue por el túnel ve un aviso; desde 127.0.0.1 (pruebas locales) no se pide.
Las transcripciones son de vídeos públicos, pero el sitio principal también está protegido: aquí igual.
"""
from __future__ import annotations

import gzip
import hmac
import os
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

ROOT = Path(__file__).resolve().parent
TOKEN_FILE = Path(os.environ.get("CR_PROTO_TOKEN_FILE", Path.home() / ".cryptoreport-propuestas-token"))
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
         ".woff2": "font/woff2", ".ico": "image/x-icon", ".webp": "image/webp", ".webmanifest": "application/manifest+json"}
COMPRESSIBLE = {".html", ".js", ".css", ".json", ".svg"}
COOKIE = "crk"


def load_token() -> str:
    if TOKEN_FILE.is_file():
        return TOKEN_FILE.read_text().strip()
    token = secrets.token_urlsafe(18)
    TOKEN_FILE.write_text(token + "\n")
    TOKEN_FILE.chmod(0o600)
    return token


TOKEN = load_token()
DENIED = """<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Enlace incompleto</title><body style="font:16px/1.5 system-ui,sans-serif;margin:0;min-height:100vh;display:grid;place-items:center;background:#f4f3ef;color:#1d1d1f">
<main style="max-width:32ch;padding:24px"><h1 style="font-size:20px;margin:0 0 8px">Enlace incompleto</h1>
<p style="margin:0;color:#55565b">Abre el enlace completo que recibiste: incluye la clave de acceso a las propuestas.</p></main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "propuestas"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    def via_tunnel(self) -> bool:
        return bool(self.headers.get("Cf-Connecting-Ip") or self.headers.get("X-Forwarded-For"))

    def authorized(self, query: dict) -> str:
        if not self.via_tunnel():
            return "ok"
        given = (query.get("k") or [""])[0]
        if given and hmac.compare_digest(given, TOKEN):
            return "set"
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE and hmac.compare_digest(value, TOKEN):
                return "ok"
        return "no"

    def send_common(self):
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("X-Content-Type-Options", "nosniff")
        # Con «no-referrer» YouTube rechaza el reproductor incrustado; así solo viaja el origen.
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")

    def do_HEAD(self):
        self.do_GET(head=True)

    def do_GET(self, head: bool = False):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        auth = self.authorized(query)
        if auth == "no":
            body = DENIED.encode()
            self.send_response(401)
            self.send_common()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head:
                self.wfile.write(body)
            return
        if auth == "set":
            rest = {k: v for k, v in query.items() if k != "k"}
            clean = url.path + (("?" + urlencode(rest, doseq=True)) if rest else "")
            self.send_response(303)
            self.send_common()
            self.send_header("Set-Cookie", f"{COOKIE}={TOKEN}; Path=/; Max-Age=2592000; HttpOnly; Secure; SameSite=Lax")
            self.send_header("Location", clean or "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

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
        body = target.read_bytes()
        encoding = None
        if target.suffix in COMPRESSIBLE and len(body) > 1024 and "gzip" in (self.headers.get("Accept-Encoding") or ""):
            body, encoding = gzip.compress(body, 6), "gzip"
        self.send_response(200)
        self.send_common()
        self.send_header("Content-Type", TYPES[target.suffix])
        self.send_header("Cache-Control", "no-cache")
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
    print(f"Propuestas en http://127.0.0.1:{port}/ (clave en {TOKEN_FILE})", flush=True)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Cliente HTTP mínimo sobre la biblioteca estándar (el núcleo no necesita dependencias externas)."""
from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


@dataclass
class Response:
    status: int
    body: bytes
    location: str = ""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - firma de urllib
        return None


_follow = urllib.request.build_opener()
_no_follow = urllib.request.build_opener(_NoRedirect)


def request(method: str, url: str, *, headers: dict | None = None, timeout: float = 30,
            follow_redirects: bool = True) -> Response:
    """Devuelve también las respuestas 4xx/5xx; solo los errores de red lanzan excepción (OSError)."""
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, **(headers or {})})
    opener = _follow if follow_redirects else _no_follow
    try:
        with opener.open(req, timeout=timeout) as resp:
            return Response(resp.status, resp.read())
    except urllib.error.HTTPError as err:
        return Response(err.code, err.read() or b"", err.headers.get("Location", "") if err.headers else "")

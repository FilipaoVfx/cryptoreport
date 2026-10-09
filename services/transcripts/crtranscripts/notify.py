"""Avisos por Telegram (opcionales). Sin token o chat solo escribe en stdout, que queda en el journal.
Un aviso que no se puede enviar nunca debe tumbar la ejecución que lo dispara."""
from __future__ import annotations

import json
import sys
import urllib.request


class Notifier:
    def __init__(self, token: str, chat_id: str, label: str = "Crypto Report · transcripciones"):
        self.token = token
        self.chat_id = chat_id
        self.label = label

    def send(self, text: str) -> bool:
        body = f"📼 {self.label}\n{text}"
        if not self.token or not self.chat_id:
            print(f"[aviso] {body}", flush=True)
            return False
        payload = json.dumps({"chat_id": self.chat_id, "text": body[:4000], "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{self.token}/sendMessage", data=payload,
                                     headers={"content-type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                ok = json.loads(resp.read()).get("ok", False)
        except Exception as err:  # noqa: BLE001 - cualquier fallo del aviso se registra y se ignora
            print(f"[aviso] no se pudo enviar a Telegram: {type(err).__name__}", file=sys.stderr, flush=True)
            return False
        if not ok:
            print("[aviso] Telegram rechazó el mensaje", file=sys.stderr, flush=True)
        return ok

"""Transporte acotado a carpetas conocidas usando el OAuth de rclone.

Una subida incierta NO se reintenta dentro del ciclo. El siguiente ciclo vuelve
a listar y leer antes de crear; nunca usamos sync, delete ni dedupe.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

MAX_BYTES = 2_000_000


class DriveError(RuntimeError):
    pass


def safe_name(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", name) or name in {".", ".."}:
        raise DriveError("Nombre de archivo no permitido")
    return name


class RcloneDrive:
    def __init__(self, remote="gdrive", config=None):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", remote):
            raise ValueError("Remote inválido")
        self.remote, self.config = remote, config

    def _run(self, folder, args):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", folder):
            raise ValueError("ID de carpeta inválido")
        cmd = ["rclone", *args, "--drive-root-folder-id", folder,
               "--retries", "1", "--low-level-retries", "1", "--contimeout", "10s",
               "--timeout", "30s", "--log-level", "ERROR"]
        if self.config:
            cmd += ["--config", str(self.config)]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=90, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DriveError(f"rclone {args[0]}: {type(exc).__name__}; se reconciliará en el siguiente ciclo") from None
        if result.returncode:
            # No imprimir stderr: puede incluir URLs autenticadas o contenido remoto.
            raise DriveError(f"rclone {args[0]} falló ({result.returncode}); revisar conexión/cuota")
        return result.stdout

    def list(self, folder):
        rows = json.loads(self._run(folder, ["lsjson", f"{self.remote}:", "--max-depth", "1"]))
        return [r for r in rows if not r.get("IsDir")]

    def read(self, folder, item):
        name = safe_name(item["Name"])
        if item.get("Size", -1) < 0 or item["Size"] > MAX_BYTES:
            raise DriveError("Archivo fuera del límite de 2 MB")
        data = self._run(folder, ["cat", f"{self.remote}:{name}", "--count", str(MAX_BYTES + 1)])
        if len(data) > MAX_BYTES:
            raise DriveError("Archivo demasiado grande")
        return data

    def write(self, folder, name, data, *, replace=False):
        safe_name(name)
        if len(data) > MAX_BYTES:
            raise DriveError("Archivo demasiado grande")
        with tempfile.TemporaryDirectory(prefix="crbridge-") as tmp:
            path = Path(tmp) / name
            path.write_bytes(data)
            args = ["copyto", str(path), f"{self.remote}:{name}"]
            args += ["--ignore-times"] if replace else ["--immutable"]
            self._run(folder, args)

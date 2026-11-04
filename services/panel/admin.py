"""Acciones de administración del panel. Todo cambio queda en la auditoría con hash encadenado.

Escribe solo en: panel/editorial.json, panel/audit.jsonl, el drop-in de systemd del extractor
(zz-panel.conf), channels.json y la copia de las instrucciones de Scheduled. Las acciones operativas usan
argv fijos (systemctl y los CLI existentes), nunca un shell.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import content

DATA = content.DATA
PANEL_DIR = DATA / "panel"
AUDIT = PANEL_DIR / "audit.jsonl"
REPO = content.REPO
DROPIN = Path("/etc/systemd/system/cryptoreport-transcripts.service.d/zz-panel.conf")
UNIT = "cryptoreport-transcripts.service"
CATALOG = REPO / "docs/observabilidad/contratos/registros/parametros.json"
INSTRUCTIONS = REPO / "docs/automatizacion-drive/scheduled-instructions.md"
_lock = threading.Lock()


class ActionError(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def atomic_write(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, mode)
    os.replace(tmp, path)


# ----------------------------------------------------------------------------------------- auditoría
def audit(action: str, target: str, outcome: str = "success", detail: dict | None = None) -> dict:
    """Evento append-only: hash = sha256(prev_hash + "\\n" + JSON canónico sin hash)."""
    with _lock:
        prev, seq = "0" * 64, 0
        if AUDIT.exists():
            lines = AUDIT.read_text(encoding="utf-8").splitlines()
            if lines:
                last = json.loads(lines[-1])
                prev, seq = last["hash"], last["seq"]
        event = {"seq": seq + 1, "event_id": str(uuid.uuid4()), "at": now(), "actor": {"kind": "user", "id": "admin"},
                 "action": action, "target": target, "outcome": outcome, "detail": detail or {}, "prev_hash": prev}
        event["hash"] = hashlib.sha256((prev + "\n").encode() + canonical(event)).hexdigest()
        AUDIT.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event


def audit_log(limit: int = 200) -> dict:
    events = [json.loads(line) for line in AUDIT.read_text(encoding="utf-8").splitlines()] if AUDIT.exists() else []
    prev, broken = "0" * 64, None
    for ev in events:
        body = {k: v for k, v in ev.items() if k != "hash"}
        if ev["prev_hash"] != prev or hashlib.sha256((prev + "\n").encode() + canonical(body)).hexdigest() != ev["hash"]:
            broken = ev["seq"]
            break
        prev = ev["hash"]
    return {"intact": broken is None, "first_bad_seq": broken, "count": len(events), "events": events[-limit:][::-1]}


# ----------------------------------------------------------------------------------------- editorial
def set_editorial(video_id: str, field: str, value) -> dict:
    if field not in ("hidden", "featured", "notes"):
        raise ActionError("Campo editorial desconocido")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ActionError("video_id inválido")
    with _lock:
        data = json.loads(content.EDITORIAL.read_text(encoding="utf-8")) if content.EDITORIAL.exists() else {}
        bucket = data.setdefault(field, {})
        if value in (None, "", False):
            bucket.pop(video_id, None)
        else:
            bucket[video_id] = {"at": now(), "value": value if field == "notes" else True}
        atomic_write(content.EDITORIAL, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    action = {"hidden": "asset.quarantine" if value else "asset.release", "featured": "editorial.feature", "notes": "editorial.note"}[field]
    audit(action, f"video:{video_id}", detail={"field": field, "value": value})
    return {"ok": True, "message": "Guardado. Se refleja en el sitio y en Urania en la próxima publicación (≤ 15 min o «Ejecutar extracción ahora»)."}


# ----------------------------------------------------------------------------------------- parámetros
ADMIN_LIMITS = {"providers.supadata.monthly_credits": {"min": 0, "max": 100}}  # plan Free: 100 créditos/mes
EDITABLE_EXTRA = {"providers.supadata.generate"}  # de pago: el administrador puede activarlo con confirmación


def _effective_env() -> dict[str, str]:
    out = subprocess.run(["systemctl", "show", UNIT, "-p", "Environment", "--value"], capture_output=True, text=True, timeout=10).stdout
    env = {}
    for token in re.findall(r'"[^"]*"|\S+', out):
        token = token.strip('"')
        if "=" in token:
            k, v = token.split("=", 1)
            env[k] = v
    return env


def _panel_overrides() -> dict[str, str]:
    if not DROPIN.exists():
        return {}
    return dict(re.findall(r'^Environment="?([A-Z0-9_]+)=(.*?)"?$', DROPIN.read_text(encoding="utf-8"), re.M))


def parameters() -> list[dict]:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["parameters"]
    env, overrides = _effective_env(), _panel_overrides()
    out = []
    for p in catalog:
        name = p["origin"].get("name")
        editable = (p["service"] == "cr-extractor" and p["origin"]["kind"] in ("env", "systemd") and name
                    and (p["status"] == "active" or p["key"] in EDITABLE_EXTRA))
        value = env.get(name) if name else None
        item = {"key": p["key"], "title": p["title"], "description": p["description"], "category": p["category"], "type": p["type"],
                "enum": p.get("enum"), "unit": p.get("unit"), "bounds": ADMIN_LIMITS.get(p["key"], p.get("bounds")), "risk": p["risk"],
                "apply": p["apply"], "status": p["status"], "service": p["service"], "env": name, "editable": bool(editable),
                "note": p.get("note"), "overridden": name in overrides if name else False,
                "value": value if value is not None else p.get("current"), "source": "systemd" if value is not None else "código/registro"}
        out.append(item)
    return out


def _coerce(param: dict, raw) -> str:
    kind, bounds = param["type"], param.get("bounds") or {}
    if kind == "boolean":
        if str(raw).lower() not in ("true", "false"):
            raise ActionError("Debe ser true o false")
        return str(raw).lower()
    if kind in ("integer", "number"):
        try:
            num = int(raw) if kind == "integer" else float(raw)
        except (TypeError, ValueError):
            raise ActionError("Debe ser un número") from None
        if "min" in bounds and num < bounds["min"] or "max" in bounds and num > bounds["max"]:
            raise ActionError(f"Fuera del rango permitido {bounds.get('min')}–{bounds.get('max')}")
        return str(num)
    if kind == "string_list":
        items = [x.strip() for x in str(raw).split(",") if x.strip()]
        allowed = {"scrapertech", "ytdlp", "supadata"}
        if not items or set(items) - allowed or len(items) != len(set(items)):
            raise ActionError("Lista de proveedores válidos sin repetir: scrapertech, ytdlp, supadata")
        if "supadata" in items and any(items.index("supadata") < items.index(f) for f in ("scrapertech", "ytdlp") if f in items):
            raise ActionError("El proveedor de pago (supadata) va después de los gratuitos (guarda G-03)")
        return ",".join(items)
    text = str(raw).strip()
    if re.search(r'["\n\\]', text):
        raise ActionError("Caracteres no permitidos")
    return text


def set_parameter(key: str, raw, reset: bool = False) -> dict:
    param = next((p for p in parameters() if p["key"] == key), None)
    if not param or not param["editable"]:
        raise ActionError("Este parámetro no se puede editar desde el panel")
    with _lock:
        overrides = _panel_overrides()
        before = param["value"]
        if reset:
            overrides.pop(param["env"], None)
            after = None
        else:
            after = _coerce(param, raw)
            overrides[param["env"]] = after
        if overrides:
            lines = ["# Generado por el panel de administración (services/panel). No editar a mano: se sobrescribe.", "[Service]"]
            lines += [f'Environment="{k}={v}"' for k, v in sorted(overrides.items())]
            atomic_write(DROPIN, "\n".join(lines) + "\n")
        elif DROPIN.exists():
            DROPIN.unlink()
        subprocess.run(["systemctl", "daemon-reload"], check=True, timeout=30)
    audit("config.apply", f"parameter:{key}", detail={"env": param["env"], "before": before, "after": after, "reset": reset})
    return {"ok": True, "message": "Aplicado: el extractor lo usa desde su próximo ciclo (≤ 15 min)."}


# ----------------------------------------------------------------------------------------- acciones
BRIDGE_ENV = {"CR_DATA_DIR": str(DATA), "CR_SITE_DIR": "/var/www/cryptoreport", "CR_DRIVE_REMOTE": "gdrive",
              "CRA_ALLOW_API_ANALYSIS": "false", "PYTHONUNBUFFERED": "1"}
JOBS: dict[str, dict] = {}


def _run_background(name: str, argv: list[str], cwd: str, env: dict | None, target: str) -> str:
    job = uuid.uuid4().hex[:8]
    JOBS[job] = {"name": name, "state": "running", "started_at": now(), "target": target}

    def work():
        try:
            res = subprocess.run(argv, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True, timeout=900)
            JOBS[job].update(state="ok" if res.returncode == 0 else "failed", exit_code=res.returncode,
                             output=(res.stdout + res.stderr)[-1500:], finished_at=now())
        except subprocess.TimeoutExpired:
            JOBS[job].update(state="failed", exit_code=None, output="Tiempo agotado (900 s)", finished_at=now())
        audit("intervention.execute", target, "success" if JOBS[job]["state"] == "ok" else "failure",
              {"intervention": name, "exit_code": JOBS[job].get("exit_code")})

    threading.Thread(target=work, daemon=True).start()
    return job


def intervene(kind: str, params: dict) -> dict:
    reason = str(params.get("reason", "")).strip()
    if kind == "run_extractor_now":
        subprocess.run(["systemctl", "start", "--no-block", UNIT], check=True, timeout=30)
        audit("intervention.execute", "run:extractor", detail={"intervention": kind})
        return {"ok": True, "message": "Extracción en marcha: descubre, transcribe y publica sitio y Urania (1–3 min)."}
    if kind == "run_bridge_now":
        subprocess.run(["systemctl", "start", "--no-block", "cryptoreport-bridge.service"], check=True, timeout=30)
        audit("intervention.execute", "run:bridge", detail={"intervention": kind})
        return {"ok": True, "message": "Puente en marcha: sincroniza Drive, importa análisis y publica."}
    bridge = [str(REPO / "services/bridge/.venv/bin/python"), "-m", "crbridge"]
    if kind == "retry_job":
        vid = str(params.get("video_id", ""))
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid) or len(reason) < 5:
            raise ActionError("Indica el video y un motivo (mínimo 5 caracteres)")
        job = _run_background(kind, bridge + ["retry", "--video-id", vid, "--reason", reason[:200]], str(REPO / "services/bridge"), BRIDGE_ENV, f"video:{vid}")
        return {"ok": True, "job": job, "message": "Reintento autorizado; el puente lo vuelve a poner en cola."}
    if kind == "backfill":
        job = _run_background(kind, bridge + ["backfill"], str(REPO / "services/bridge"), BRIDGE_ENV, "queue:backfill")
        return {"ok": True, "job": job, "message": "Backfill pedido: el puente admite transcripciones fuera de la ventana de 48 h."}
    raise ActionError("Acción desconocida")


# ----------------------------------------------------------------------------------------- creadores
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"


def resolve_channel(ref: str) -> dict:
    ref = ref.strip()
    m = re.search(r"(UC[0-9A-Za-z_-]{22})", ref)
    handle = re.search(r"@([A-Za-z0-9._-]{3,30})", ref)
    if m:
        url = f"https://www.youtube.com/channel/{m.group(1)}?hl=es"
    elif handle:
        url = f"https://www.youtube.com/@{handle.group(1)}?hl=es"
    else:
        raise ActionError("Pega la URL del canal, su @handle o su ID (UC…)")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9"})
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - solo youtube.com
        html = resp.read().decode("utf-8", "replace")
    cid = re.search(r'"externalId":"(UC[0-9A-Za-z_-]{22})"', html)
    title = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    if not cid or not title:
        raise ActionError("No se pudo leer el canal en YouTube")
    import html as htmlmod
    return {"channel_id": cid.group(1), "name": htmlmod.unescape(title.group(1)), "handle": handle.group(1) if handle else None}


def preview_creator(ref: str) -> dict:
    info = resolve_channel(ref)
    import sys
    sys.path.insert(0, str(REPO / "services/transcripts"))
    from crtranscripts import channel_pages, feeds
    try:
        entries = feeds.fetch_feed(info["channel_id"], pauses=(2, 4))
    except Exception:  # noqa: BLE001 - mismo respaldo que el extractor: páginas del canal
        try:
            found = channel_pages.fetch_channel_pages(info["channel_id"], set())
            entries = found[0] if isinstance(found, tuple) else found
        except Exception as err:  # noqa: BLE001
            entries, info["feed_error"] = [], str(err)[:200]
    info["recent"] = [{"id": e.video_id, "title": e.title, "published_at": str(e.published_at)} for e in entries[:5]]
    info["exists"] = any(c["channel_id"] == info["channel_id"] for c in content.channels())
    return info


def add_creator(ref: str, slug: str, initials: str) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,31}", slug):
        raise ActionError("Identificador: minúsculas, números y guiones (2–32)")
    if not re.fullmatch(r"[A-Z]{2,3}", initials):
        raise ActionError("Iniciales: 2 o 3 mayúsculas")
    info = resolve_channel(ref)
    with _lock:
        chans = content.channels()
        if any(c["slug"] == slug or c["channel_id"] == info["channel_id"] for c in chans):
            raise ActionError("Ese canal o identificador ya existe")
        chans.append({"slug": slug, "name": info["name"], "channel_id": info["channel_id"], "initials": initials})
        atomic_write(content.CHANNELS_FILE, "[\n" + ",\n".join("  " + json.dumps(c, ensure_ascii=False) for c in chans) + "\n]\n")
        authorized = _authorize_in_instructions(slug, info.get("handle"))
    audit("creator.add", f"channel:{slug}", detail={"name": info["name"], "channel_id": info["channel_id"], "instructions_updated": authorized})
    msg = "Creador añadido: entra en el próximo ciclo (≤ 15 min) con su contenido de las últimas 48 h."
    if authorized:
        msg += " Autorizado en la copia del repo de scheduled-instructions.md: sincroniza la copia de Drive desde «Creadores»."
    return {"ok": True, "message": msg}


def remove_creator(slug: str) -> dict:
    with _lock:
        chans = content.channels()
        keep = [c for c in chans if c["slug"] != slug]
        if len(keep) == len(chans):
            raise ActionError("No existe ese creador")
        if not keep:
            raise ActionError("Debe quedar al menos un creador")
        atomic_write(content.CHANNELS_FILE, "[\n" + ",\n".join("  " + json.dumps(c, ensure_ascii=False) for c in keep) + "\n]\n")
    audit("creator.remove", f"channel:{slug}")
    return {"ok": True, "message": "Creador retirado de la vigilancia. Sus transcripciones y análisis se conservan."}


def _authorize_in_instructions(slug: str, handle: str | None) -> bool:
    text = INSTRUCTIONS.read_text(encoding="utf-8")
    m = re.search(r"La cola corresponde a (.+?)\. Los identificadores internos autorizados son (.+?)\.", text)
    if not m or re.search(rf"\b{re.escape(slug)}\b", m.group(2)):
        return False
    def add(listing: str, item: str) -> str:
        parts = re.split(r", | y ", listing)
        parts.append(item)
        return ", ".join(parts[:-1]) + " y " + parts[-1]
    handles = add(m.group(1), f"@{handle}") if handle else m.group(1)
    new = f"La cola corresponde a {handles}. Los identificadores internos autorizados son {add(m.group(2), slug)}."
    atomic_write(INSTRUCTIONS, text.replace(m.group(0), new))
    return True


def sync_instructions() -> dict:
    """Sube la copia del repo a Drive (mismo archivo, mismo ID) con rclone acotado a la carpeta de control."""
    import sys
    sys.path.insert(0, str(REPO / "services/bridge"))
    from crbridge.drive import DriveError, RcloneDrive
    control = json.loads((REPO / "docs/automatizacion-drive/manifest.json").read_text())["folders"]["control"]
    drive, local = RcloneDrive("gdrive"), INSTRUCTIONS.read_bytes()
    try:
        entry = next((i for i in drive.list(control) if i.get("Name") == INSTRUCTIONS.name), None)
        if entry and drive.read(control, entry) == local:
            return {"ok": True, "message": "Drive ya tiene esta versión."}
        res = subprocess.run(["rclone", "copyto", str(INSTRUCTIONS), f"gdrive:{INSTRUCTIONS.name}", "--drive-root-folder-id", control,
                              "--retries", "1", "--low-level-retries", "1", "--timeout", "30s", "--log-level", "ERROR"],
                             capture_output=True, timeout=120)
        if res.returncode:
            raise ActionError("Drive rechazó la subida (probablemente cuota); reinténtalo en unos minutos")
        after = next((i for i in drive.list(control) if i.get("Name") == INSTRUCTIONS.name), None)
        same = after and drive.read(control, after) == local
    except DriveError as err:
        raise ActionError(f"Drive no disponible: {err}") from None
    audit("instructions.sync", "drive:scheduled-instructions", "success" if same else "failure")
    return {"ok": bool(same), "message": "Instrucciones sincronizadas en Drive." if same else "La relectura no coincide; revisa Drive."}

"""cr-panel: panel de administración y contenidos de Urania/Diario (servidor, sesión y estado agregado).

Lee en solo lectura state.sqlite, bridge/state.sqlite, bridge/status.json, last-run.json y los comprobantes
de Scheduled en bridge/cache. No escribe nada ni ejecuta intervenciones. Solo biblioteca estándar.

    python3 services/panel/crpanel.py --port 8750 --token <secreto>
Rutas: /<token>/ (tablero) y /<token>/api/health (informe con la forma de health-report.schema.json).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA = Path("/var/lib/cryptoreport-transcripts")
REPO = Path(__file__).resolve().parents[2]
JOB_LIMIT = 2  # scheduled-instructions.md, revisión 1.3
NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/FilipaoVfx/cryptoreport/docs/observabilidad#scheduled-run")


def now() -> datetime:
    return datetime.now(timezone.utc)


def ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def ro(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def receipts() -> list[dict]:
    """Comprobantes únicos de Scheduled que el puente ya leyó de Drive."""
    found = {}
    for path in (DATA / "bridge" / "cache").glob("*.bin"):
        try:
            doc = json.loads(path.read_bytes())
        except (ValueError, OSError):
            continue
        if isinstance(doc, dict) and "run_id" in doc and "attempted_job_ids" in doc:
            found[doc["run_id"]] = doc
    return sorted(found.values(), key=lambda r: r["started_at"], reverse=True)


def level(value, warning=None, critical=None, lower_is_bad=False) -> str:
    if value is None:
        return "not_measured"
    bad = (lambda v, t: v < t) if lower_is_bad else (lambda v, t: v > t)
    if critical is not None and bad(value, critical):
        return "critical"
    if warning is not None and bad(value, warning):
        return "warning"
    return "ok"


WORST = ["ok", "not_measured", "warning", "critical"]


def worst(levels: list[str]) -> str:
    status = max(levels, key=WORST.index) if levels else "unknown"
    return {"ok": "ok", "warning": "degraded", "critical": "critical", "not_measured": "unknown", "unknown":"unknown"}[status]


def collect() -> dict:
    t = now()
    channels = json.loads((REPO / "services/transcripts/channels.json").read_text())
    status = json.loads((DATA / "bridge" / "status.json").read_text())
    last = json.loads((DATA / "last-run.json").read_text())
    with ro(DATA / "state.sqlite") as db:
        runs = [dict(r) for r in db.execute("SELECT started_at, finished_at, feeds, transcribed, pending, errors FROM runs ORDER BY id DESC LIMIT 48")]
        videos = [dict(r) for r in db.execute("SELECT video_id, channel_slug, title, published_at, status, provider, coverage, is_short FROM videos ORDER BY published_at DESC")]
        durations = sorted((ts(r["finished_at"]) - ts(r["started_at"])).total_seconds()
                           for r in db.execute("SELECT started_at, finished_at FROM runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 672"))
    with ro(DATA / "bridge" / "state.sqlite") as db:
        jobs = {r["id"]: r["state"] for r in db.execute("SELECT id, state FROM jobs")}
    rec = receipts()
    week = [r for r in rec if t - ts(r["started_at"]) <= timedelta(days=7)]
    attempted = {j for r in week for j in r["attempted_job_ids"]}
    gcr = (sum(jobs.get(j) == "imported" for j in attempted) / len(attempted)) if attempted else None
    ok_runs = (sum(r["status"] != "error" for r in week) / len(week)) if week else None
    over_limit = [r for r in week if len(r["attempted_job_ids"]) > JOB_LIMIT]

    extractor_age = (t - ts(runs[0]["finished_at"])).total_seconds() if runs and runs[0]["finished_at"] else None
    p95 = durations[int(len(durations) * 0.95) - 1] if durations else None
    sync_age = (t - ts(status["last_sync_at"])).total_seconds() if status.get("last_sync_at") else None
    receipt_age = (t - ts(status["last_receipt_at"])).total_seconds() if status.get("last_receipt_at") else None
    site = Path("/var/www/cryptoreport/data.json")  # el sitio se exporta en cada ciclo; last_published_at solo al importar
    published = [x for x in (ts(json.loads(site.read_text()).get("generatedAt")) if site.exists() else None, ts(status.get("last_published_at"))) if x]
    publish_age = (t - max(published)).total_seconds() if published else None
    review = sum(status["jobs"].get(k, 0) for k in ("rejected", "conflict", "blocked", "upload_uncertain", "needs_transcript"))
    active = sum(status["jobs"].get(k, 0) for k in ("queued", "uploaded", "upload_uncertain"))
    feeds_now = json.loads(runs[0]["feeds"]) if runs else {}
    channel_fail = sum(not str(feeds_now.get(c["slug"], "")).startswith("ok") for c in channels)
    sd_used, st_used = last.get("supadata_credits_month", 0), last.get("scrapertech_requests_month", 0)

    sig = lambda tid, obs, lvl: {"threshold_id": tid, "observed": obs, "level": lvl}  # noqa: E731
    components = [
        {"id": "extractor", "summary": f"Último ciclo hace {int(extractor_age // 60)} min · {len(channels) - channel_fail}/{len(channels)} canales" if extractor_age is not None else "Sin ciclos",
         "signals": [sig("SH-01", round(extractor_age or 0), level(extractor_age, 2700, 5400)), sig("SH-03", p95, level(p95, 300, 900)),
                     sig("SH-16", channel_fail, level(channel_fail, 0, 2))]},
        {"id": "bridge", "summary": "; ".join(status["errors"]) or "Sincroniza sin errores",
         "signals": [sig("SH-04", round(sync_age or 0), level(sync_age, 2700, 7200)), sig("SH-14", review, level(review, 0)),
                     sig("SH-05", len(status["errors"]), level(len(status["errors"]), 0))]},
        {"id": "scheduled_agent", "summary": f"Último comprobante {status.get('last_receipt_status') or '—'} · GCR 7 d {gcr:.3f}" if gcr is not None else "Sin comprobantes en 7 días",
         "signals": [sig("SH-12", round(receipt_age or 0), level(receipt_age if active else 0, 28800, 86400)),
                     sig("AP-01", round(gcr, 3) if gcr is not None else None, level(gcr, 0.9, 0.75, lower_is_bad=True)),
                     sig("AP-03", round(ok_runs, 3) if ok_runs is not None else None, level(ok_runs, 0.8, 0.5, lower_is_bad=True)),
                     sig("AP-04", len(over_limit), level(len(over_limit), 0, 0 if any(len(r["attempted_job_ids"]) > 5 for r in over_limit) else None))]},
        {"id": "publication", "summary": f"Publicado hace {int(publish_age // 60)} min" if publish_age is not None else "Sin publicación",
         "signals": [sig("SH-11", round(publish_age or 0), level(publish_age, 2700, 7200))]},
        {"id": "analysis_api", "status": "disabled", "summary": "Guarda G-01 cerrada; sin gasto de API", "signals": [sig("CO-03", 0, "ok")]},
        {"id": "telemetry", "status": "unknown", "summary": "Pila OTel pendiente (Fase 1)", "signals": [sig("SH-15", None, "not_measured")]},
    ]
    transport=operations.transport(status)
    live=operations.runtime()
    semantic=operations.social_status('semantic/status.json') or status.get("social_semantic") or {}
    social=operations.social_status()
    social_health=social.get('health') or {}
    paused=(transport.get("pause_until") or 0)>t.timestamp()
    drive_bad=bool(transport.get("auth_blocked") or paused or transport.get("last_error"))
    components.extend([
      {"id":"social_feed","status":social_health.get('status','unknown'),
       "summary":f"{sum(a.get('fresh',False) for a in social_health.get('accounts',[]))}/{len(social_health.get('accounts',[]))} cuentas consultadas recientemente · {len(social_health.get('alerts',[]))} avisos · modelos desactivados","signals":[]},
      {"id":"drive_transport","status":"degraded" if drive_bad else "ok" if transport.get("backend")!="unknown" else "unknown",
       "summary":str(transport.get("backend"))+" · "+("renovar autorización" if transport.get("auth_blocked") else "pausa por error/cuota" if paused else "sin pausa registrada"),"signals":[]},
      {"id":"semantic","status":"degraded" if semantic.get("errors") else "ok" if semantic else "unknown",
       "summary":str(semantic.get("status","sin datos"))+f" · {semantic.get('jobs_uploaded',0)} subidos / {semantic.get('jobs_available',0)} disponibles · {semantic.get('jobs_reviewed',0)} revisados","signals":[]},
      {"id":"runtime","status":"ok" if live["live_available"] else "unknown",
       "summary":"Puente esperando a extracción; reintento al terminar o próximo timer" if live["bridge_waiting"] else "Acceso compartido ocupado: "+str(live["probable_owner"]) if live["pipeline_locked"] else "Acceso compartido libre" if live["pipeline_locked"] is False else "Estado del bloqueo no disponible","signals":[]},
    ])
    for comp in components:
        comp.setdefault("status", worst([s["level"] for s in comp["signals"]]))
    budgets = [{"name": "supadata_credits", "used": sd_used, "limit": 20, "unit": "{credit}"},
               {"name": "scrapertech_requests", "used": st_used, "limit": 1000, "unit": "{request}"},
               {"name": "social_operations", "used":social.get('budget',{}).get('monthly_used',0),"limit":social.get('budget',{}).get('monthly_limit',400),"unit":"{operation}"},
               {"name": "model_api_usd", "used": 0, "limit": 0, "unit": "{USD}"}]
    budget_levels = [level(sd_used / 20, 0.8 - 1e-9, 1.0 - 1e-9), level(st_used / 1000, 0.8 - 1e-9, 0.95 - 1e-9)]
    alerts = [dict(s, component=c["id"]) for c in components for s in c["signals"] if s["level"] in ("warning", "critical")]
    alerts += [{"threshold_id": tid, "observed": obs, "level": lvl, "component": "budget"}
               for tid, obs, lvl in (("CO-01", sd_used, budget_levels[0]), ("CO-02", st_used, budget_levels[1])) if lvl != "ok"]
    if drive_bad:alerts.append({"threshold_id":"DRIVE","observed":transport.get("last_error"),"level":"warning","component":"drive_transport"})
    if semantic.get("errors"):alerts.append({"threshold_id":"SEMANTIC","observed":len(semantic["errors"]),"level":"warning","component":"semantic"})
    if social_health.get('alerts'):alerts.append({"threshold_id":"SOCIAL","observed":len(social_health['alerts']),"level":"warning","component":"social_feed"})
    status_overall = {"critical": "critical", "degraded": "degraded"}.get(worst([a["level"] for a in alerts] or ["ok"]), "ok")
    health = {"generated_at": iso(t), "status": status_overall, "components": components, "slos": [], "alerts_firing": len(alerts), "budgets": budgets}

    per_channel = []
    for c in channels:
        vs = [v for v in videos if v["channel_slug"] == c["slug"]]
        per_channel.append({"slug": c["slug"], "name": c["name"], "feed": feeds_now.get(c["slug"], "—"), "videos": len(vs),
                            "last": vs[0]["published_at"] if vs else None})
    feed_state = lambda v: ("fb" if "páginas" in v else "ok") if v.startswith("ok") else "error"  # noqa: E731
    cycles = [{"t": r["started_at"], "ok": {s: feed_state(str(v)) for s, v in json.loads(r["feeds"]).items()},
               "transcribed": r["transcribed"], "errors": r["errors"]} for r in reversed(runs)]
    return {"drive_transport":transport,"runtime":live,"social_semantic":semantic,"social_feed":social,
            "source_report_at":status.get("generated_at"),"events":operations.event_page(),
            "health": health, "alerts": alerts, "jobs": status["jobs"], "warnings": status["warnings"], "errors": status["errors"],
            "channels": per_channel, "cycles": cycles,
            "recent": [{k: v[k] for k in ("video_id", "channel_slug", "title", "published_at", "status", "provider", "is_short")} for v in videos[:12]],
            "receipts": [{"run": str(uuid.uuid5(NS, f"{r['run_id']}|{r['started_at']}"))[:8],
                          "run_id":r["run_id"],"started_at":r["started_at"],"finished_at":r["finished_at"],
                          "duration_s":(ts(r["finished_at"])-ts(r["started_at"])).total_seconds(),
                          "status":r["status"],"attempted":len(r["attempted_job_ids"]),"uploaded":len(r["uploaded_job_ids"]),
                          "attempted_job_ids":r["attempted_job_ids"],"uploaded_job_ids":r["uploaded_job_ids"],
                          "errors":r.get("errors",[]),"over_limit":len(r["attempted_job_ids"])>JOB_LIMIT}
                         for r in rec[:10]]}



# ----------------------------------------------------------------------------------------- servidor
import hmac  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import secrets  # noqa: E402
import time  # noqa: E402
from urllib.parse import unquote  # noqa: E402

import admin  # noqa: E402
import content  # noqa: E402
import operations  # noqa: E402
import social_accounts  # noqa: E402

HERE = Path(__file__).resolve().parent
AUTH_FILE = Path("/root/.cryptoreport-panel-auth")
SESSION_TTL = 12 * 3600
SESSIONS: dict[str, float] = {}
FAILS: dict[str, list[float]] = {}


def hash_password(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1).hex()


def check_password(password: str) -> bool:
    data = json.loads(AUTH_FILE.read_text())
    return hmac.compare_digest(hash_password(password, bytes.fromhex(data["salt"])), data["hash"])


def set_password(password: str) -> None:
    salt = secrets.token_bytes(16)
    AUTH_FILE.write_text(json.dumps({"salt": salt.hex(), "hash": hash_password(password, salt)}))
    os.chmod(AUTH_FILE, 0o600)


class Handler(BaseHTTPRequestHandler):
    token = ""

    def log_message(self, *args):  # sin logs de acceso: la URL contiene el token
        pass

    # --------------------------------------------------------------- utilidades
    def send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data: https://i.ytimg.com; frame-ancestors 'none'; form-action 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def json(self, code: int, obj, extra: dict | None = None):
        self.send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8", extra)

    def client_ip(self) -> str:
        return self.headers.get("CF-Connecting-IP") or self.client_address[0]

    def session_ok(self) -> bool:
        m = re.search(r"crp_session=([A-Za-z0-9_-]{20,})", self.headers.get("Cookie", ""))
        exp = SESSIONS.get(m.group(1)) if m else None
        if exp and exp > time.time():
            SESSIONS[m.group(1)] = time.time() + SESSION_TTL
            return True
        return False

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 100_000:
            raise admin.ActionError("Cuerpo demasiado grande")
        return json.loads(self.rfile.read(length) or b"{}")

    def route(self) -> str | None:
        path = unquote(self.path.split("?")[0])
        base = f"/{self.token}"
        if path == base:
            return "redirect"
        return path[len(base):] if path.startswith(base + "/") else None

    # --------------------------------------------------------------- GET
    def do_GET(self):
        sub = self.route()
        if sub is None:
            return self.send(404, b"No encontrado", "text/plain; charset=utf-8")
        if sub == "redirect":
            return self.send(301, b"", "text/plain", {"Location": f"/{self.token}/"})
        if sub == "/":
            return self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if not sub.startswith("/api/"):
            return self.send(404, b"No encontrado", "text/plain; charset=utf-8")
        if sub == "/api/session":
            return self.json(200, {"authenticated": self.session_ok()})
        if not self.session_ok():
            return self.json(401, {"error": "Inicia sesión"})
        try:
            if sub == "/api/health":
                return self.json(200, collect())
            if sub == "/api/events":
                from urllib.parse import parse_qs,urlsplit
                query=parse_qs(urlsplit(self.path).query)
                before=query.get("before",[None])[0];vid=query.get("video_id",[None])[0]
                if before is not None and (not before.isdigit() or len(before)>18):return self.json(400,{"error":"Cursor inválido"})
                if vid is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",vid):return self.json(400,{"error":"Video inválido"})
                return self.json(200,operations.event_page(video_id=vid,before=before))
            if sub == "/api/videos":
                return self.json(200, content.videos())
            if sub.startswith("/api/videos/"):
                detail = content.video_detail(sub.rsplit("/", 1)[1])
                return self.json(200, detail) if detail else self.json(404, {"error": "No existe"})
            if sub == "/api/creators":
                return self.json(200, content.creators())
            if sub == "/api/social/accounts":
                return self.json(200,social_accounts.listing())
            if sub == "/api/parameters":
                return self.json(200, admin.parameters())
            if sub == "/api/audit":
                return self.json(200, admin.audit_log())
            if sub.startswith("/api/jobs/"):
                return self.json(200, admin.JOBS.get(sub.rsplit("/", 1)[1], {"state": "desconocido"}))
        except social_accounts.SocialError as err:
            return self.json(err.http,{'error':str(err)})
        except Exception as err:  # noqa: BLE001 - el panel informa en vez de caer
            return self.json(500, {"error": f"{type(err).__name__}: {err}"})
        return self.json(404, {"error": "No existe"})

    # --------------------------------------------------------------- POST
    def do_POST(self):
        sub = self.route()
        if sub is None or not sub.startswith("/api/"):
            return self.send(404, b"No encontrado", "text/plain; charset=utf-8")
        if self.headers.get("X-Panel") != "1":  # CSRF: solo fetch del propio panel (junto con SameSite=Strict)
            return self.json(403, {"error": "Petición no permitida"})
        try:
            data = self.body()
        except (ValueError, admin.ActionError) as err:
            return self.json(400, {"error": str(err)})
        if sub == "/api/login":
            ip, now_t = self.client_ip(), time.time()
            recent = [t for t in FAILS.get(ip, []) if now_t - t < 60]
            if len(recent) >= 5:
                return self.json(429, {"error": "Demasiados intentos; espera un minuto"})
            if not check_password(str(data.get("password", "")).strip()):
                FAILS[ip] = recent + [now_t]
                admin.audit("session.login_failed", "session:admin", "denied")
                return self.json(401, {"error": "Contraseña incorrecta"})
            sid = secrets.token_urlsafe(32)
            SESSIONS[sid] = now_t + SESSION_TTL
            admin.audit("session.login", "session:admin")
            cookie = f"crp_session={sid}; Path=/{self.token}/; HttpOnly; Secure; SameSite=Strict; Max-Age={SESSION_TTL}"
            return self.json(200, {"ok": True}, {"Set-Cookie": cookie})
        if not self.session_ok():
            return self.json(401, {"error": "Inicia sesión"})
        try:
            if sub == "/api/social/accounts/preview":
                return self.json(200,social_accounts.preview(str(data.get('ref',''))))
            if sub == "/api/social/accounts":
                return self.json(200,social_accounts.save(data))
            if sub == "/api/logout":
                m = re.search(r"crp_session=([A-Za-z0-9_-]+)", self.headers.get("Cookie", ""))
                if m:
                    SESSIONS.pop(m.group(1), None)
                return self.json(200, {"ok": True}, {"Set-Cookie": f"crp_session=; Path=/{self.token}/; Max-Age=0"})
            if sub == "/api/editorial":
                return self.json(200, admin.set_editorial(str(data["video_id"]), str(data["field"]), data.get("value")))
            if sub == "/api/parameters":
                return self.json(200, admin.set_parameter(str(data["key"]), data.get("value"), bool(data.get("reset"))))
            if sub == "/api/actions":
                return self.json(200, admin.intervene(str(data["kind"]), data.get("params") or {}))
            if sub == "/api/creators/preview":
                return self.json(200, admin.preview_creator(str(data["ref"])))
            if sub == "/api/creators":
                return self.json(200, admin.add_creator(str(data["ref"]), str(data["slug"]), str(data["initials"])))
            if sub == "/api/creators/remove":
                return self.json(200, admin.remove_creator(str(data["slug"])))
            if sub == "/api/instructions/sync":
                return self.json(200, admin.sync_instructions())
        except social_accounts.SocialError as err:
            return self.json(err.http,{'error':str(err)})
        except (admin.ActionError, KeyError) as err:
            return self.json(422, {"error": str(err) if isinstance(err, admin.ActionError) else f"Falta el campo {err}"})
        except Exception as err:  # noqa: BLE001
            return self.json(500, {"error": f"{type(err).__name__}: {err}"})
        return self.json(404, {"error": "No existe"})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8750)
    parser.add_argument("--token")
    parser.add_argument("--set-password", action="store_true", help="genera una contraseña nueva y la guarda en /root/.cryptoreport-panel-password")
    args = parser.parse_args()
    if args.set_password:
        password = secrets.token_urlsafe(15)
        set_password(password)
        path = Path("/root/.cryptoreport-panel-password")
        path.write_text(password + "\n")
        os.chmod(path, 0o600)
        print(f"Contraseña nueva guardada en {path}")
        return 0
    if not args.token or not AUTH_FILE.exists():
        parser.error("hacen falta --token y una contraseña (--set-password)")
    Handler.token = args.token
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Cola durable, reconciliación idempotente y frontera de confianza de Scheduled."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cranalysis.config import PROMPT_VERSION
from cranalysis.request import build_payload, load_prompt, load_schema, sha256
from cranalysis.validate import validate, _norm
from crtranscripts.quality import assess

from .drive import DriveError, safe_name


def now():
    return datetime.now(timezone.utc)


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Fecha sin zona horaria")
    return parsed


def encoded(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def parse(raw):
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise ValueError("Clave JSON repetida")
            obj[k] = v
        return obj
    def invalid(value):
        raise ValueError("Número JSON no finito")
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def atomic(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".bridge-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o644)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def make_job(path, prompt, schema):
    raw = path.read_bytes()
    doc = parse(raw)
    v = doc["video"]
    safe_name(v["video_id"])
    safe_name(v["channel"]["slug"])
    instant(v["published_at"])
    meta = {"video_id": v["video_id"], "channel": v["channel"]["slug"],
            "transcript_sha256": hashlib.sha256(raw).hexdigest(), "prompt_version": PROMPT_VERSION,
            "prompt_sha256": sha256(prompt), "schema_sha256": sha256(json.dumps(schema, sort_keys=True))}
    job_id = meta["video_id"] + "__" + sha256(json.dumps(meta, sort_keys=True))
    return {"job_id": job_id, "meta": meta, "payload": build_payload(doc, None)}


def result_errors(result, job, schema):
    """No confiar en status, rutas, hashes ni afirmaciones de validación externas."""
    if not isinstance(result, dict) or not isinstance(result.get("meta"), dict):
        return ["Resultado sin objeto meta"]
    meta = result["meta"]
    errors = [f"meta.{key} no coincide" for key, value in job["meta"].items() if meta.get(key) != value]
    if result.get("job_id") != job["job_id"]:
        errors.append("job_id no coincide")
    if meta.get("provider") != "chatgpt-scheduled":
        errors.append("provider no permitido")
    if meta.get("status") not in {"pendiente_validacion", "ok"}:
        errors.append("status no permitido")
    try:
        at = instant(meta["analyzed_at"])
        if at > now() + timedelta(minutes=5):
            errors.append("analyzed_at futuro")
    except (KeyError, TypeError, ValueError, AttributeError):
        return errors + ["analyzed_at inválido"]
    payload = dict(job["payload"], analizado_en=meta["analyzed_at"])
    analysis = result.get("analysis")
    try:
        problems = validate(analysis, payload, schema)
    except (TypeError, ValueError, KeyError, IndexError):
        return errors + ["Estructura o rango de evidencia inválido"]
    if problems:
        return errors + problems
    v = payload["documento"]["video"]
    if analysis["video"]["analizado_en"] != meta["analyzed_at"]:
        errors.append("analizado_en no coincide")
    if analysis["video"]["titulo"] != v["title"] or analysis["video"]["publicado_en"] != v["published_at"]:
        errors.append("Título o fecha de publicación no coincide")
    # Si el resultado declara un rango programático, exigir exactamente ese rango,
    # sin el margen de segmentos del validador histórico. Los primeros resultados
    # del piloto pueden tener localizadores descriptivos; conservan validación base.
    segments = payload["documento"]["transcript"]["segments"]
    for ev in analysis["evidencias"]:
        if ev["origen"] != "transcripcion":
            continue
        loc = ev.get("localizador") or ""
        match = re.search(r"segments\[(\d+):(\d+)\]", loc)
        single = re.search(r"segments\[(\d+)\]", loc)
        if "segments[" in loc and not match and not single:
            errors.append(f"{ev['id']}: localizador inválido")
        if match or single:
            i, j = map(int, match.groups()) if match else (int(single[1]), int(single[1]) + 1)
            if not 0 <= i < j <= len(segments):
                errors.append(f"{ev['id']}: rango fuera de transcripción")
                continue
            a, b = segments[i]["start"], segments[j-1]["start"] + segments[j-1]["dur"]
            quote = " ".join(s["text"] for s in segments[i:j])
            if (ev["inicio_s"] is None or ev["fin_s"] is None or abs(ev["inicio_s"] - a) > .05
                    or abs(ev["fin_s"] - b) > .05 or not ev["cita"] or _norm(ev["cita"]) not in _norm(quote)):
                errors.append(f"{ev['id']}: cita/tiempos no coinciden con localizador")
    return errors


class Bridge:
    def __init__(self, data_dir, folders, drive, *, channels, publish=lambda: None, lookback=48):
        self.data, self.folders, self.drive = Path(data_dir), folders, drive
        self.root = self.data / "bridge"
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "state.sqlite", timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, source TEXT NOT NULL, payload TEXT NOT NULL,
            published_at TEXT NOT NULL, state TEXT NOT NULL, remote_id TEXT,
            detail TEXT, updated_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        self.prompt, self.schema = load_prompt(), load_schema()
        self.channels, self.publish, self.lookback = set(channels), publish, lookback
        self.errors = []

    def close(self):
        self.db.close()

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, json.dumps(value)))

    def state(self, job_id, state, detail=None, remote_id=None):
        old = self.db.execute("SELECT state,detail,remote_id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if old and old[0] == state and old[1] == detail and (remote_id is None or old[2] == remote_id):
            return
        with self.db:
            self.db.execute("UPDATE jobs SET state=?, detail=?, remote_id=COALESCE(?,remote_id), updated_at=? WHERE id=?",
                            (state, detail, remote_id, now().isoformat(), job_id))

    def listing(self, folder):
        groups = defaultdict(list)
        for item in self.drive.list(self.folders[folder]):
            try:
                safe_name(item["Name"])
                groups[item["Name"]].append(item)
            except (KeyError, DriveError):
                self.errors.append(f"{folder}: nombre no permitido")
        return groups

    def read(self, folder, item):
        fingerprint = sha256(json.dumps([item["ID"], item.get("ModTime"), item.get("Size")]))
        cache = self.root / "cache" / f"{fingerprint}.bin"
        if not cache.exists():
            atomic(cache, self.drive.read(self.folders[folder], item))
        return cache.read_bytes()

    def discover(self, pending):
        cutoff = now() - timedelta(hours=self.lookback)
        for path in sorted((self.data / "transcripts").glob("*/*.json")):
            if path.parent.name not in self.channels:
                continue
            try:
                job = make_job(path, self.prompt, self.schema)
                if path.parent.name != job["meta"]["channel"]:
                    raise ValueError("Canal de ruta distinto")
                known = self.db.execute("SELECT 1 FROM jobs WHERE id=?", (job["job_id"],)).fetchone()
                previous = self.db.execute("SELECT id FROM jobs WHERE source=? AND id<>?", (str(path),job["job_id"])).fetchall()
                video = job["payload"]["documento"]["video"]
                if not known and not previous and not self.get("backfill_requested") and instant(video["published_at"]) < cutoff and job["job_id"] + ".json" not in pending:
                    continue
                if not known:
                    with self.db:
                        self.db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,NULL,NULL,?)",
                                        (job["job_id"], str(path), json.dumps(job), video["published_at"], "queued", now().isoformat()))
                # Reconciliar también en reinicios posteriores: un corte entre
                # insertar y superseder no debe dejar una versión vieja elegible.
                for old in previous:
                    self.state(old[0], "superseded", "Transcripción reemplazada; conservar trazabilidad")
                quality = assess(job["payload"]["documento"])
                if not quality["valid"]:
                    self.state(job["job_id"], "needs_transcript", ", ".join(quality["reasons"]))
                    continue
                # Nunca consumir otra vez análisis válidos ya importados.
                saved = self.data / "analysis" / path.parent.name / path.name
                if saved.exists():
                    local = parse(saved.read_bytes())
                    lm = local.get("meta", {})
                    if any(lm.get(k) and lm[k] != job["meta"][k] for k in ("transcript_sha256", "prompt_sha256", "schema_sha256")):
                        self.put("publish_dirty", True)
                        archive = self.data / "analysis-versions" / path.parent.name / (sha256(saved.read_text()) + ".json")
                        archive.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(saved, archive)
                        continue
                    provenance = dict(job["meta"])
                    # Análisis locales anteriores al puente no guardaban hash de
                    # transcripción. Reutilizar solo con ruta local e identidad
                    # conocidas y nueva validación de sus evidencias.
                    if ("transcript_sha256" not in lm and lm.get("provider") != "chatgpt-scheduled"
                            and lm.get("transcript_file") == str(path)):
                        provenance.pop("transcript_sha256")
                    if (lm.get("status") == "ok" and lm.get("validation", {}).get("ok")
                            and all(lm.get(k) == v for k, v in provenance.items())
                            and not validate(local["analysis"], build_payload(job["payload"]["documento"], lm["analyzed_at"]), self.schema)):
                        state = self.db.execute("SELECT state FROM jobs WHERE id=?", (job["job_id"],)).fetchone()[0]
                        if state != "imported":
                            self.state(job["job_id"], "imported")
            except (ValueError, KeyError, TypeError, OSError):
                self.errors.append(f"transcripción local inválida: {path.name}")
        self.put("backfill_requested", False)

    def check_control(self):
        files = self.listing("control")
        for name, expected in (("narrative-analysis.system.md", sha256(self.prompt)),
                               ("narrative-analysis.schema.json", sha256(json.dumps(self.schema, sort_keys=True)))):
            matches = files.get(name, [])
            if len(matches) != 1:
                raise DriveError(f"Control {name}: ausente o duplicado")
            raw = self.read("control", matches[0])
            actual = sha256(json.dumps(parse(raw), sort_keys=True)) if name.endswith(".json") else hashlib.sha256(raw).hexdigest()
            if actual != expected:
                raise DriveError(f"Control {name}: hash diferente; pausar trabajos nuevos")

    def results(self, listing):
        candidates = defaultdict(list)
        for name, items in listing.items():
            if not name.endswith(".json"):
                continue
            if len(items) != 1:
                self.errors.append(f"Resultados: nombre duplicado {name}")
                self.state(name[:-5], "conflict", "Nombres duplicados en Drive")
                continue
            item = items[0]
            try:
                raw = self.read("resultados", item)
                result = parse(raw)
                if not isinstance(result, dict) or not isinstance(result.get("job_id"), str):
                    raise ValueError("sin job_id")
                candidates[result["job_id"]].append((item, raw, result))
            except (ValueError, KeyError, TypeError, DriveError):
                self.errors.append(f"Resultado ilegible: {name}")
                self.state(name[:-5], "rejected", "Resultado ilegible; requiere revisión")
        for job_id, items in candidates.items():
            row = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                self.errors.append("Resultado sin trabajo local conocido")
                continue
            if row["state"] == "superseded":
                continue
            if len(items) != 1:
                self.state(job_id, "conflict", "Varios resultados para el mismo job_id")
                self.errors.append(f"Resultado duplicado: {job_id}")
                continue
            item, raw, result = items[0]
            job = json.loads(row["payload"])
            # La transcripción original pudo cambiar tras subir el trabajo.
            source = Path(row["source"])
            problems = []
            if not assess(job["payload"]["documento"])["valid"]:
                problems.append("Transcripción no válida para publicación")
            if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest() != job["meta"]["transcript_sha256"]:
                problems.append("Transcripción local modificada desde el encolado")
            problems += result_errors(result, job, self.schema)
            if problems:
                digest = hashlib.sha256(raw).hexdigest()
                atomic(self.root / "rejected" / f"{digest}.json", encoded({"source_id": item["ID"], "errors": problems, "result": result}))
                # Un resultado remoto defectuoso no invalida un análisis local
                # previamente revisado y aceptado desde otra fuente trazable.
                accepted = self.data / "analysis" / source.parent.name / source.name
                if accepted.exists():
                    local = parse(accepted.read_bytes())
                    lm = local.get("meta", {})
                    if (lm.get("status") == "ok" and lm.get("validation", {}).get("ok")
                            and lm.get("job_id") == job_id
                            and not result_errors(dict(job_id=job_id, meta=lm, analysis=local.get("analysis")), job, self.schema)):
                        self.state(job_id, "imported", "Resultado remoto rechazado; análisis local revisado conservado")
                        self.put(f"resolved_rejection:{job_id}", {"rejected_source_id": item["ID"],
                                 "accepted_source_id": lm.get("source_drive_file_id"), "errors": problems})
                        continue
                self.state(job_id, "rejected", "; ".join(problems[:5]), item["ID"])
                self.errors.append(f"Resultado rechazado: {job_id}")
                continue
            target = self.data / "analysis" / source.parent.name / source.name
            if target.exists():
                existing = parse(target.read_bytes())
                if existing.get("analysis") != result["analysis"]:
                    self.state(job_id, "conflict", "Conservar análisis existente distinto; revisión manual", item["ID"])
                    self.errors.append(f"Análisis local distinto: {job_id}")
                    continue
            else:
                # Persistir dirty ANTES del archivo: un reinicio no pierde publicación.
                self.put("publish_dirty", True)
                meta = dict(job["meta"], provider="chatgpt-scheduled", model=result["meta"].get("model"),
                            analyzed_at=result["meta"]["analyzed_at"], status="ok", job_id=job_id,
                            usage=result["meta"].get("usage"), cost_usd_estimate=result["meta"].get("cost_usd_estimate"),
                            validation={"ok": True, "errors": [], "validated_at": now().isoformat()},
                            transcript_file=str(source), source_drive_file_id=item["ID"],
                            imported_at=now().isoformat(), import_mode="automatic")
                atomic(target, encoded({"meta": meta, "analysis": result["analysis"]}))
            self.state(job_id, "imported", remote_id=item["ID"])
        return set(candidates)

    def receipts(self):
        latest = self.get("last_receipt_at")
        for name, items in self.listing("ejecuciones").items():
            if not name.endswith(".json"):
                continue
            try:
                if len(items) != 1:
                    raise ValueError("Duplicado")
                rec = parse(self.read("ejecuciones", items[0]))
                finish, start = instant(rec["finished_at"]), instant(rec["started_at"])
                if not start <= finish <= now() + timedelta(minutes=5):
                    raise ValueError("Fechas inválidas")
                if rec["status"] not in {"resultados_subidos", "sin_pendientes", "error"}:
                    raise ValueError("Estado desconocido")
                attempted, uploaded = rec["attempted_job_ids"], rec["uploaded_job_ids"]
                if not isinstance(attempted, list) or not isinstance(uploaded, list) or not set(uploaded) <= set(attempted):
                    raise ValueError("IDs inválidos")
                if not latest or finish > instant(latest):
                    latest = finish.isoformat()
                    self.put("last_receipt_status", rec["status"])
                # Un intento fallido del modelo no se repite automáticamente.
                for job_id in set(attempted) - set(uploaded):
                    authorized = self.get("retry_authorizations", {}).get(job_id)
                    if authorized and instant(authorized["authorized_at"]) > finish:
                        continue
                    row = self.db.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
                    if row and row[0] in {"queued", "uploaded", "upload_uncertain"}:
                        self.state(job_id, "blocked", "Scheduled registró un intento sin resultado")
                        self.put(f"recovery:{job_id}", {"requested_at": finish.isoformat(), "reason": "Scheduled solicita revisión de material"})
            except (ValueError, KeyError, TypeError, AttributeError, DriveError):
                self.errors.append(f"Comprobante inválido: {name}")
        if latest:
            self.put("last_receipt_at", latest)

    def import_reviewed(self, result, source_id):
        """Entrada operativa explícita para un resultado ya revisado; nunca reemplaza otro análisis."""
        row = self.db.execute("SELECT * FROM jobs WHERE id=?", (result.get("job_id"),)).fetchone()
        if not row:
            raise ValueError("Trabajo desconocido; descubrir antes de importar")
        job = json.loads(row["payload"])
        source = Path(row["source"])
        problems = result_errors(result, job, self.schema)
        if hashlib.sha256(source.read_bytes()).hexdigest() != job["meta"]["transcript_sha256"]:
            problems.append("Transcripción modificada")
        if not assess(job["payload"]["documento"])["valid"]:
            problems.append("Transcripción inválida")
        if problems:
            raise ValueError("; ".join(problems[:5]))
        target = self.data / "analysis" / source.parent.name / source.name
        if target.exists():
            if parse(target.read_bytes()).get("analysis") != result["analysis"]:
                raise ValueError("Ya hay un análisis distinto; no sobrescribir")
            return
        self.put("publish_dirty", True)
        meta = dict(job["meta"], provider="chatgpt-scheduled", model=result["meta"].get("model"),
                    analyzed_at=result["meta"]["analyzed_at"], status="ok", job_id=job["job_id"],
                    usage=None, cost_usd_estimate=None, transcript_file=str(source),
                    source_drive_file_id=source_id, imported_at=now().isoformat(), import_mode="reviewed",
                    validation={"ok": True, "errors": [], "validated_at": now().isoformat()})
        atomic(target, encoded({"meta": meta, "analysis": result["analysis"]}))
        self.state(job["job_id"], "imported", "Importación explícita de resultado revisado", source_id)

    def upload(self, listing, result_ids):
        for row in self.db.execute("SELECT * FROM jobs ORDER BY published_at, id").fetchall():
            if row["state"] not in {"queued", "uploaded", "upload_uncertain"} or row["id"] in result_ids:
                continue
            name, job = row["id"] + ".json", json.loads(row["payload"])
            try:
                items = listing.get(name, [])
                if len(items) > 1:
                    self.state(row["id"], "conflict", "Pendiente duplicado")
                    self.errors.append(f"Pendiente duplicado: {name}")
                    continue
                if not items:
                    if row["state"] == "upload_uncertain":
                        # Evitar duplicar una creación cuya confirmación se perdió.
                        self.errors.append(f"Subida incierta requiere revisión: {name}")
                        continue
                    self.state(row["id"], "upload_uncertain", "Verificar antes de reintentar")
                    self.drive.write(self.folders["pendientes"], name, encoded(job))
                    items = self.listing("pendientes").get(name, [])
                if len(items) != 1 or parse(self.read("pendientes", items[0])) != job:
                    self.state(row["id"], "conflict", "Pendiente remoto diferente o duplicado")
                    self.errors.append(f"Conflicto de pendiente: {name}")
                    continue
                self.state(row["id"], "uploaded", remote_id=items[0]["ID"])
            except (DriveError, ValueError, KeyError, TypeError) as exc:
                self.errors.append(f"No se confirmó subida: {name}")
                if isinstance(exc, DriveError) and any(k in str(exc) for k in ("drive_quota", "drive_auth")):
                    self.errors.append(str(exc))
                    break

    def index(self):
        # Incluir antiguos pendientes: envejecer fuera de 48 h no elimina la cola.
        pending = self.listing("pendientes")
        jobs = []
        for row in self.db.execute("SELECT * FROM jobs ORDER BY published_at, id"):
            matches = pending.get(row["id"] + ".json", [])
            if len(matches) != 1:
                continue
            video = json.loads(row["payload"])["payload"]["documento"]["video"]
            jobs.append(dict(job_id=row["id"], file_id=matches[0]["ID"],
                             video_id=video["video_id"], channel=video["channel"]["slug"],
                             published_at=video["published_at"], duration_s=video.get("duration_s"),
                             is_short=video.get("is_short"), title=video["title"],
                             server_state=row["state"], updated_at=row["updated_at"]))
        control = self.listing("control")
        items = control.get("queue-index.json", [])
        if len(items) > 1:
            raise DriveError("Índice de cola duplicado")
        authorizations = self.get("retry_authorizations", {})
        if items and parse(self.read("control", items[0])).get("jobs") == jobs and parse(self.read("control", items[0])).get("retry_authorizations", {}) == authorizations:
            return
        obj = {"index_version": "1.0.0", "prepared_at": now().isoformat(),
               "purpose": "Localización y estado declarado por el servidor; contrastar con carpetas.", "jobs": jobs,
               "retry_authorizations": authorizations}
        self.drive.write(self.folders["control"], "queue-index.json", encoded(obj), replace=True)
        check = self.listing("control").get("queue-index.json", [])
        if len(check) != 1 or parse(self.read("control", check[0])) != obj:
            raise DriveError("No se confirmó actualización del índice")

    def health(self):
        rows = self.db.execute("SELECT * FROM jobs").fetchall()
        counts = Counter(row["state"] for row in rows)
        active = [r for r in rows if r["state"] in {"queued", "uploaded", "upload_uncertain"}]
        oldest = min((r["published_at"] for r in active), default=None)
        receipt = self.get("last_receipt_at")
        sync = self.get("last_sync_at")
        warnings = []
        if not sync or now() - instant(sync) > timedelta(minutes=45):
            warnings.append("Sin sincronización correcta en 45 minutos")
        if active and (not receipt or now() - instant(receipt) > timedelta(hours=8)):
            warnings.append("Cola pendiente sin comprobante reciente de Scheduled (8 h)")
        if oldest and now() - instant(oldest) > timedelta(hours=48):
            warnings.append("Hay trabajos pendientes con más de 48 horas")
        if self.get("last_receipt_status") == "error":
            warnings.append("Última ejecución de Scheduled reportó error")
        if any(counts[k] for k in ("rejected", "conflict", "blocked", "upload_uncertain", "needs_transcript")):
            warnings.append("Hay trabajos que requieren revisión")
        if self.get("publish_dirty"):
            warnings.append("Publicación pendiente de reintento")
        errors = self.get("last_errors", [])
        extraction = {"last_finished_at": None, "channels": {}, "pending": None}
        source_db = self.data / "state.sqlite"
        if source_db.exists():
            conn = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
            try:
                run = conn.execute("SELECT finished_at, feeds, pending FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
                if run:
                    extraction = {"last_finished_at": run[0], "channels": json.loads(run[1]), "pending": run[2]}
                if not run or not run[0] or now() - instant(run[0]) > timedelta(minutes=45):
                    warnings.append("La extracción no termina un ciclo desde hace 45 minutos")
                if run and any(not extraction["channels"].get(ch, "").startswith("ok") for ch in self.channels):
                    warnings.append("Algún canal no se pudo comprobar en el último ciclo")
            except (sqlite3.Error, ValueError, TypeError):
                warnings.append("No se pudo leer el estado de extracción")
            finally:
                conn.close()
        else:
            warnings.append("No se ha registrado el estado de extracción")
        return {"generated_at": now().isoformat(), "status": "degraded" if warnings or errors else "ok",
                "last_sync_at": sync, "last_published_at": self.get("last_published_at"),
                "last_receipt_at": receipt, "last_receipt_status": self.get("last_receipt_status"),
                "jobs": dict(counts), "oldest_pending_at": oldest,
                "warnings": warnings, "errors": errors, "extraction": extraction, "model_api_enabled": False}

    def recovery_requests(self):
        """Scheduled comunica material dudoso; el servidor conserva responsabilidad técnica."""
        target = self.data / "recovery-requests.json"
        requests = []
        for row in self.db.execute("SELECT * FROM jobs WHERE state IN ('needs_transcript','blocked')"):
            job = json.loads(row["payload"])
            requests.append({"job_id": row["id"], "video_id": job["meta"]["video_id"],
                             "channel": job["meta"]["channel"], "transcript_sha256": job["meta"]["transcript_sha256"],
                             "reason": row["detail"], "state": row["state"]})
        atomic(target, encoded({"generated_at": now().isoformat(), "requests": requests}))
        events = [dict(job_id=r["id"], channel=json.loads(r["payload"])["meta"]["channel"],
                       video_id=json.loads(r["payload"])["meta"]["video_id"], state=r["state"],
                       detail=r["detail"], updated_at=r["updated_at"]) for r in self.db.execute("SELECT * FROM jobs")]
        atomic(self.root / "jobs.json", encoded({"generated_at": now().isoformat(), "jobs": events}))

    def cycle(self):
        self.errors = []
        try:
            pending = self.listing("pendientes")
            self.discover(pending)
            self.check_control()
            result_ids = self.results(self.listing("resultados"))
            self.receipts()
            self.upload(pending, result_ids)
            self.index()
            self.put("last_sync_at", now().isoformat())
        except (DriveError, ValueError, KeyError, TypeError, OSError) as exc:
            self.errors.append(str(exc) if isinstance(exc, DriveError) else "Ciclo incompleto: " + type(exc).__name__)
        # Publicar también después de caída de Drive, si ya hay válidos importados.
        if self.get("publish_dirty"):
            try:
                self.publish()
                self.put("publish_dirty", False)
                self.put("last_published_at", now().isoformat())
            except Exception as exc:
                self.errors.append(f"Publicación falló: {type(exc).__name__}; se reintentará")
        self.put("last_errors", self.errors)
        self.recovery_requests()
        status = self.health()
        atomic(self.root / "status.json", encoded(status))
        # Copia consistente de SQLite; no copiar el .db vivo ignorando su WAL.
        backup = sqlite3.connect(self.root / "state-backup.sqlite")
        try:
            self.db.backup(backup)
        finally:
            backup.close()
        return status

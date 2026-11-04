"""Validador de los contratos de observabilidad y del panel de Urania/Diario.

Ejecuta los protocolos de validación automatizados que se pueden comprobar sin red ni servicios:

    PV-01 esquemas · PV-02 ejemplos · PV-03 OpenAPI · PV-04 registro de nombres · PV-05 documento al día
    PV-06 anclas de código · PV-10 referencias a pruebas · PV-11 cadenas de auditoría · PV-15 secretos
    PV-16 deriva de umbrales de tono · trazabilidad de requisitos

Uso:
    python3 docs/observabilidad/herramientas/validate_contracts.py               # todo (CI)
    python3 docs/observabilidad/herramientas/validate_contracts.py --write       # regenera las tablas del documento
    python3 docs/observabilidad/herramientas/validate_contracts.py --datos-reales /var/lib/cryptoreport-transcripts  # PV-07
    python3 docs/observabilidad/herramientas/validate_contracts.py --spans export.jsonl                               # PV-08

Dependencias: jsonschema >= 4.18 (con referencing) y PyYAML. Sale con 1 si hay errores.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sqlite3
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent
CONTRACTS = DOCS / "contratos"
REPO = DOCS.parents[1]
SCHEMAS = CONTRACTS / "esquemas"
EXAMPLES = CONTRACTS / "ejemplos"
DRAFT = "https://json-schema.org/draft/2020-12/schema"

sys.path.insert(0, str(HERE))
import trajectory_metrics  # noqa: E402  (módulo hermano, sin dependencias)

ROLE_GRANTS = {
    "viewer": {"viewer"},
    "reviewer": {"viewer", "reviewer"},
    "operator": {"viewer", "reviewer", "operator"},
    "admin": {"viewer", "reviewer", "operator", "admin", "auditor"},
    "auditor": {"viewer", "auditor"},
}
MUTATING = {"post", "put", "patch", "delete"}
HTTP_METHODS = MUTATING | {"get", "head", "options"}
MEDIA_TYPES = {"application/json", "application/problem+json", "text/event-stream", "text/markdown"}
# Atributos OTel aceptables en métricas (cardinalidad baja); el resto solo en spans y logs.
METRIC_SAFE_OTEL = {"gen_ai.operation.name", "gen_ai.provider.name", "gen_ai.request.model", "gen_ai.response.model",
                    "gen_ai.token.modality", "gen_ai.agent.name", "gen_ai.workflow.name", "gen_ai.evaluation.name",
                    "error.type", "server.address"}
LEDGER_RECORDS = {"run_record": "run-record", "job": "job", "feedback": "feedback",
                  "vector_index_status": "vector-index-status", "intervention": "intervention"}
SECRET_PATTERNS = [
    ("clave de OpenAI", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("clave de Supadata", re.compile(r"\bsd_[0-9a-f]{24,}\b")),
    ("clave privada", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("clave de AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("token de GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("token de Slack", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("clave de Google", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("token de bot de Telegram", re.compile(r"\b[0-9]{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("cabecera Bearer", re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{24,}=*")),
]


# ------------------------------------------------------------------------------------------- utilidades
@dataclass
class Report:
    errors: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[tuple[str, str]] = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)

    def error(self, section: str, message: str) -> None:
        self.errors.append((section, message))

    def warn(self, section: str, message: str) -> None:
        self.warnings.append((section, message))

    def ok(self, section: str, n: int = 1) -> None:
        self.counts[section] += n

    def print(self) -> None:
        for section in sorted(self.counts):
            print(f"  ✓ {section}: {self.counts[section]}")
        for section, message in self.warnings:
            print(f"  ! [{section}] {message}")
        for section, message in self.errors:
            print(f"  ✗ [{section}] {message}")
        print(f"{len(self.errors)} errores, {len(self.warnings)} avisos")


def _reject_constant(value: str):
    raise ValueError(f"constante no admitida en JSON: {value}")


def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"clave duplicada: {key}")
        out[key] = value
    return out


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicates, parse_constant=_reject_constant)


def load_yaml(path: Path) -> Any:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    json.dumps(data, allow_nan=False)  # falla si YAML produjo fechas u otros tipos no JSON
    return data


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pointer(path) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in path)


def resolve_pointer(doc: Any, ptr: str) -> Any:
    if ptr in ("", "#"):
        return doc
    cur = doc
    for raw in ptr.lstrip("#").lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, list):
            cur = cur[int(token)]
        elif isinstance(cur, dict):
            cur = cur[token]
        else:
            raise KeyError(ptr)
    return cur


_SELECTOR = re.compile(r"^\[([A-Za-z_]+)=(.*)\]$")


def _step(cur: Any, token: str) -> tuple[Any, Any]:
    """Avanza un segmento de ruta; devuelve (clave concreta, nodo siguiente o None si no existe)."""
    match = _SELECTOR.match(token)
    if match:
        key, value = match.groups()
        index = next((i for i, item in enumerate(cur or []) if isinstance(item, dict) and str(item.get(key)) == value), None)
        if index is None:
            raise KeyError(f"no hay elemento con {key}={value}")
        return index, cur[index]
    token = token.replace("~1", "/").replace("~0", "~")
    if isinstance(cur, list):
        if token == "-":
            return token, None
        index = int(token)
        return index, cur[index] if index < len(cur) else None
    return token, cur.get(token) if isinstance(cur, dict) else None


def concrete_path(instance: Any, path: str) -> str:
    """Traduce /lista/[clave=valor]/campo a un puntero JSON con el índice real."""
    tokens, cur = [], instance
    for raw in ([] if path == "" else path.lstrip("/").split("/")):
        token, cur = _step(cur, raw)
        tokens.append(token)
    return pointer(tokens)


def apply_patch(doc: Any, ops: list[dict]) -> Any:
    """Subconjunto de RFC 6902 (add, replace, remove) con selectores [clave=valor]."""
    out = copy.deepcopy(doc)
    for op in ops:
        parts = op["path"].lstrip("/").split("/")
        parent = resolve_pointer(out, concrete_path(out, "/" + "/".join(parts[:-1]))) if len(parts) > 1 else out
        last, _ = _step(parent, parts[-1])
        if op["op"] == "remove":
            del parent[last]
        elif op["op"] == "replace":
            parent[last] = op["value"]
        elif op["op"] == "add" and isinstance(parent, list) and last == "-":
            parent.append(op["value"])
        elif op["op"] == "add" and isinstance(parent, list):
            parent.insert(last, op["value"])
        elif op["op"] == "add":
            parent[last] = op["value"]
        else:
            raise ValueError(f"operación de parche no soportada: {op['op']}")
    return out


def doc_anchors(text: str) -> set[str]:
    return set(re.findall(r'<a id="([a-z0-9-]+)"></a>', text))


# Espacio de nombres de los run_id reconstruidos: UUIDv5(NS, "<run_id del comprobante>|<started_at>") es estable
# aunque el puente relea el mismo comprobante en cada ciclo.
SCHEDULED_RUN_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/FilipaoVfx/cryptoreport/docs/observabilidad#scheduled-run")


def reconstructed_run_id(agent_run_id: str, started_at: str) -> str:
    return str(uuid.uuid5(SCHEDULED_RUN_NS, f"{agent_run_id}|{started_at}"))


# ------------------------------------------------------------------------------------------- contratos
class Contracts:
    def __init__(self, root: Path = CONTRACTS):
        self.root = root
        self.manifest = load_json(root / "manifest.json")
        self.schemas: dict[str, dict] = {p.name: load_json(p) for p in sorted((root / "esquemas").glob("*.json"))}
        resources = [((root / "esquemas" / name).resolve().as_uri(), Resource.from_contents(doc))
                     for name, doc in self.schemas.items()]
        self.registry = Registry().with_resources(resources)
        self.registries = {rel: load_json(root / rel) for rel in self.manifest["registries"]}
        self.semconv = self.registries["registros/semconv.json"]
        self.thresholds = {t["id"]: t for t in self.registries["registros/umbrales.json"]["thresholds"]}
        self.parameters = {p["key"]: p for p in self.registries["registros/parametros.json"]["parameters"]}
        self.tools = {t["id"]: t for t in self.registries["registros/herramientas.json"]["tools"]}
        self.guardrails = {g["id"]: g for g in self.registries["registros/guardrails.json"]["guardrails"]}
        self.interventions = {i["id"]: i for i in self.registries["registros/intervenciones.json"]["interventions"]}
        self.trace = self.registries["registros/trazabilidad.json"]
        snapshot_rel = self.semconv["pinned"]["snapshot_file"]
        self.snapshot = load_json(root / snapshot_rel)
        self.cr_attributes = {a["name"]: a for a in self.semconv["attributes"]}
        self.spans = self.semconv["spans"]
        self.metrics = {m["name"]: m for m in self.semconv["metrics"]}
        self.event_names = {e["name"] for e in self.semconv["events"]}

    def validator(self, schema_file: str, definition: str | None = None) -> Draft202012Validator:
        uri = (self.root / "esquemas" / schema_file).resolve().as_uri()
        ref = uri + (f"#/$defs/{definition}" if definition else "")
        return Draft202012Validator({"$schema": DRAFT, "$ref": ref}, registry=self.registry)

    def attribute_known(self, name: str) -> bool:
        return name in self.cr_attributes if name.startswith("cr.") else name in self.snapshot["attributes"]


def schema_errors(validator: Draft202012Validator, instance: Any) -> list[tuple[str, str, str]]:
    out = []
    for err in validator.iter_errors(instance):
        out.append((err.validator if err.validator is not None else "false", pointer(err.absolute_path), err.message))
    return out


# ------------------------------------------------------------------------------- comprobaciones semánticas
def _span_template_regex(template: str) -> re.Pattern:
    parts = re.split(r"(\{[^}]+\})", template)
    return re.compile("^" + "".join("(?P<p%d>.+)" % i if p.startswith("{") else re.escape(p) for i, p in enumerate(parts)) + "$")


def span_definition(c: Contracts, name: str) -> dict | None:
    for span in c.spans:
        if _span_template_regex(span["name"]).match(name):
            return span
    return None


def check_span(c: Contracts, span: dict) -> list[tuple[str, str]]:
    problems = []
    if _ts(span["end_time"]) < _ts(span["start_time"]):
        problems.append(("/end_time", "end_time anterior a start_time"))
    definition = span_definition(c, span["name"])
    if definition is None:
        return problems + [("/name", f"span desconocido en el registro: {span['name']}")]
    attrs = span.get("attributes", {})
    expected_name = definition["name"]
    for placeholder in re.findall(r"\{([^}]+)\}", definition["name"]):
        expected_name = expected_name.replace("{" + placeholder + "}", str(attrs.get(placeholder, "{" + placeholder + "}")))
    if expected_name != span["name"]:
        problems.append(("/name", f"el nombre debería ser «{expected_name}» según la plantilla {definition['name']}"))
    if span["kind"] != definition["kind"]:
        problems.append(("/kind", f"{definition['name']} es {definition['kind']}"))
    service = span["resource"]["service.name"]
    if service not in definition["services"]:
        problems.append(("/resource/service.name", f"{service} no emite {definition['name']}"))
    for name in definition["required_attributes"]:
        if name not in attrs:
            problems.append((f"/attributes/{name}", f"falta el atributo obligatorio {name}"))
    for name, value in definition.get("fixed_values", {}).items():
        if name in attrs and attrs[name] != value:
            problems.append((f"/attributes/{name}", f"{name} debe valer {value!r}"))
    allowed = set(definition["required_attributes"]) | set(definition.get("recommended_attributes", []))
    for name, value in attrs.items():
        if not c.attribute_known(name):
            problems.append((f"/attributes/{name}", f"atributo fuera del registro y de la instantánea: {name}"))
            continue
        if name not in allowed:
            problems.append((f"/attributes/{name}", f"{name} no está previsto en {definition['name']}"))
        spec = c.cr_attributes.get(name)
        if spec and "enum" in spec:
            values = value if isinstance(value, list) else [value]
            for v in values:
                if v not in spec["enum"]:
                    problems.append((f"/attributes/{name}", f"{v!r} no es un valor de {name}"))
        snap = c.snapshot["attributes"].get(name)
        if snap and snap.get("members") and name.startswith("gen_ai.") and isinstance(value, str) and value not in snap["members"]:
            problems.append((f"/attributes/{name}", f"{value!r} no es un valor conocido de {name} en la instantánea"))
    for i, event in enumerate(span.get("events", [])):
        if event["name"] not in c.event_names:
            problems.append((f"/events/{i}/name", f"evento desconocido: {event['name']}"))
        elif event["name"] not in definition.get("events", []):
            problems.append((f"/events/{i}/name", f"{event['name']} no está previsto en {definition['name']}"))
    return problems


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def check_run(c: Contracts, run: dict) -> list[tuple[str, str]]:
    problems = []
    if run["trace_id"] != run["run_id"].replace("-", ""):
        problems.append(("/trace_id", "trace_id debe ser el run_id sin guiones"))
    ext = run.get("external")
    if ext and not set(ext["uploaded_job_ids"]) <= set(ext["attempted_job_ids"]):
        problems.append(("/external/uploaded_job_ids", "hay trabajos subidos que no se intentaron"))
    if run.get("finished_at") and _ts(run["finished_at"]) < _ts(run["started_at"]):
        problems.append(("/finished_at", "finished_at anterior a started_at"))
    return problems


def check_alert(c: Contracts, alert: dict) -> list[tuple[str, str]]:
    threshold = c.thresholds.get(alert["threshold_id"])
    if threshold is None:
        return [("/threshold_id", f"umbral inexistente: {alert['threshold_id']}")]
    problems = []
    if threshold.get("alert") and threshold["alert"]["runbook"] != alert["runbook"]:
        problems.append(("/runbook", f"{alert['threshold_id']} usa {threshold['alert']['runbook']}"))
    if alert["severity"] not in threshold.get("levels", {}) and "rule" not in threshold:
        problems.append(("/severity", f"{alert['threshold_id']} no define el nivel {alert['severity']}"))
    return problems


def check_quality_report(c: Contracts, report: dict) -> list[tuple[str, str]]:
    return [(f"/checks/{i}/threshold_id", f"umbral inexistente: {chk['threshold_id']}")
            for i, chk in enumerate(report["checks"]) if chk["threshold_id"] not in c.thresholds]


def check_config_version(c: Contracts, version: dict) -> list[tuple[str, str]]:
    problems = []
    if hashlib.sha256(canonical(version["parameters"])).hexdigest() != version["digest"]:
        problems.append(("/digest", "digest no coincide con el JSON canónico de parameters"))
    for key in version["parameters"]:
        if key not in c.parameters:
            problems.append((f"/parameters/{key}", f"parámetro fuera del catálogo: {key}"))
    return problems


def check_config_change(c: Contracts, change: dict) -> list[tuple[str, str]]:
    problems = []
    for i, approval in enumerate(change["approvals"]):
        if approval["by"]["id"] == change["created_by"]["id"]:
            problems.append((f"/approvals/{i}/by", "quien propone no puede aprobar su propio cambio"))
    for i, item in enumerate(change["changes"]):
        if item["key"] not in c.parameters:
            problems.append((f"/changes/{i}/key", f"parámetro fuera del catálogo: {item['key']}"))
        clamp = item.get("clamped")
        if clamp and clamp["guardrail"] not in c.guardrails:
            problems.append((f"/changes/{i}/clamped/guardrail", f"guarda inexistente: {clamp['guardrail']}"))
    return problems


def check_intervention(c: Contracts, item: dict) -> list[tuple[str, str]]:
    kind = c.interventions.get(item["type"])
    if kind is None:
        return [("/type", f"tipo fuera del catálogo: {item['type']}")]
    problems = []
    if kind["approval"] == "second_person":
        for i, approval in enumerate(item["approvals"]):
            if approval["by"]["id"] == item["requested_by"]["id"]:
                problems.append((f"/approvals/{i}/by", "la segunda persona no puede ser quien solicitó"))
    return problems


def check_evaluation(c: Contracts, item: dict) -> list[tuple[str, str]]:
    traj = item.get("trajectory")
    if not traj or not item["name"].startswith("cr.trajectory."):
        return []
    metric = item["name"].removeprefix("cr.trajectory.")
    computed = trajectory_metrics.evaluate(traj["expected"], traj["observed"])[metric]
    value = float(computed) if not isinstance(computed, bool) else (1.0 if computed else 0.0)
    if item["score"]["value"] is None or not math.isclose(item["score"]["value"], value, abs_tol=1e-4):
        return [("/score/value", f"{item['name']} calculado = {value:.4f}")]
    return []


def check_log(c: Contracts, line: dict) -> list[tuple[str, str]]:
    problems = []
    if "event" in line and line["event"] not in c.event_names:
        problems.append(("/event", f"evento fuera del registro: {line['event']}"))
    for name in line.get("attributes", {}):
        if not c.attribute_known(name):
            problems.append((f"/attributes/{name}", f"atributo fuera del registro y de la instantánea: {name}"))
    if "run_id" in line and "trace_id" in line and line["trace_id"] != line["run_id"].replace("-", ""):
        problems.append(("/trace_id", "trace_id debe ser el run_id sin guiones"))
    return problems


def check_audit_event(c: Contracts, event: dict) -> list[tuple[str, str]]:
    body = {k: v for k, v in event.items() if k != "hash"}
    expected = hashlib.sha256((event["prev_hash"] + "\n").encode("utf-8") + canonical(body)).hexdigest()
    return [] if expected == event["hash"] else [("/hash", "hash no coincide con prev_hash + evento canónico")]


SEMANTIC: dict[str, Callable[[Contracts, dict], list[tuple[str, str]]]] = {
    "span-record": check_span, "run-record": check_run, "alert": check_alert, "quality-report": check_quality_report,
    "config-version": check_config_version, "config-change": check_config_change, "intervention": check_intervention,
    "evaluation-result": check_evaluation, "audit-event": check_audit_event, "log-record": check_log,
}


def verify_chain(events: list[dict]) -> int | None:
    """Devuelve el primer seq roto o None si la cadena es íntegra."""
    prev = "0" * 64
    for event in events:
        body = {k: v for k, v in event.items() if k != "hash"}
        if event["prev_hash"] != prev:
            return event["seq"]
        if hashlib.sha256((prev + "\n").encode("utf-8") + canonical(body)).hexdigest() != event["hash"]:
            return event["seq"]
        prev = event["hash"]
    return None


# ------------------------------------------------------------------------------------------- secciones
def check_manifest_and_schemas(c: Contracts, r: Report) -> None:
    section = "PV-01 esquemas"
    listed = set(c.manifest["schemas"])
    present = set(c.schemas)
    for name in sorted(present - listed):
        r.error(section, f"{name} no figura en manifest.json")
    for name in sorted(listed - present):
        r.error(section, f"manifest.json cita {name}, que no existe")
    for name, doc in c.schemas.items():
        if doc.get("$schema") != DRAFT:
            r.error(section, f"{name}: $schema debe ser {DRAFT}")
        try:
            Draft202012Validator.check_schema(doc)
            r.ok(section)
        except Exception as err:  # noqa: BLE001 - se informa cualquier fallo del metaesquema
            r.error(section, f"{name}: {err}")
    for rel, meta in c.manifest["vendor"].items():
        if sha256_file(c.root / rel) != meta["sha256"]:
            r.error(section, f"{rel}: el SHA-256 no coincide con manifest.json (copia alterada)")
        else:
            r.ok("vendor íntegro")


def check_registries(c: Contracts, r: Report) -> None:
    section = "registros"
    for rel, schema in c.manifest["registries"].items():
        errors = schema_errors(c.validator(Path(schema).name), c.registries[rel])
        for kw, path, msg in errors:
            r.error(section, f"{rel}{path}: {msg} [{kw}]")
        if not errors:
            r.ok(section)


def _example_target(stem: str, filename: str) -> tuple[str, str | None]:
    schema_file = f"{stem}.schema.json"
    parts = filename[:-5].split(".")
    definition = parts[0] if len(parts) > 1 and parts[0][:1].isupper() else None
    return schema_file, definition


def check_examples(c: Contracts, r: Report) -> None:
    section = "PV-02 ejemplos"
    covered_valid, covered_invalid = set(), set()
    for path in sorted((EXAMPLES / "validos").glob("*/*.json")):
        stem = path.parent.name
        schema_file, definition = _example_target(stem, path.name)
        if schema_file not in c.schemas:
            r.error(section, f"{path.relative_to(EXAMPLES)}: no existe {schema_file}")
            continue
        instance = load_json(path)
        errors = schema_errors(c.validator(schema_file, definition), instance)
        semantic = SEMANTIC[stem](c, instance) if (stem in SEMANTIC and not definition and not errors) else []
        for kw, ptr, msg in errors:
            r.error(section, f"{path.relative_to(EXAMPLES)}{ptr}: {msg} [{kw}]")
        for ptr, msg in semantic:
            r.error(section, f"{path.relative_to(EXAMPLES)}{ptr}: {msg} [semántica]")
        if not errors and not semantic:
            r.ok(section)
            covered_valid.add(stem)
    for path in sorted((EXAMPLES / "invalidos").glob("*/*.json")):
        stem = path.parent.name
        schema_file, definition = _example_target(stem, path.name)
        rel = path.relative_to(EXAMPLES)
        if schema_file not in c.schemas:
            r.error(section, f"{rel}: no existe {schema_file}")
            continue
        case = load_json(path)
        base = load_json(c.root / case["base"]) if "base" in case else None
        instance = apply_patch(base, case["parche"]) if base is not None else case["instancia"]
        expected_kw = case["error_esperado"]["keyword"]
        expected_path = None
        for doc in (instance, base):  # el selector puede apuntar a un valor que el propio parche cambia
            try:
                expected_path = concrete_path(doc, case["error_esperado"]["ruta"])
                break
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        if expected_path is None:
            r.error(section, f"{rel}: ruta esperada no resoluble ({case['error_esperado']['ruta']})")
            continue
        errors = schema_errors(c.validator(schema_file, definition), instance)
        if expected_kw in ("semantic", "registry"):
            if errors:
                r.error(section, f"{rel}: debía pasar el esquema y fallar en la semántica, pero el esquema falla: {errors[0][2]}")
                continue
            found = SEMANTIC[stem](c, instance) if stem in SEMANTIC else []
            if any(ptr == expected_path for ptr, _ in found):
                r.ok(section)
                covered_invalid.add(stem)
            else:
                r.error(section, f"{rel}: se esperaba un error semántico en {expected_path!r}; obtenido {found or 'ninguno'}")
            continue
        if not errors:
            r.error(section, f"{rel}: el ejemplo inválido valida")
            continue
        hit = any(kw == expected_kw and ptr == expected_path for kw, ptr, _ in errors)
        stray = [(kw, ptr) for kw, ptr, _ in errors if not (ptr == expected_path or ptr.startswith(expected_path + "/"))]
        if hit and not stray:
            r.ok(section)
            covered_invalid.add(stem)
        else:
            r.error(section, f"{rel}: se esperaba {expected_kw} en {expected_path!r}; obtenido {[(kw, ptr) for kw, ptr, _ in errors]}")
    registry_schemas = {Path(s).name.removesuffix(".schema.json") for s in c.manifest["registries"].values()}
    for name in c.schemas:
        stem = name.removesuffix(".schema.json")
        if stem not in covered_invalid:
            r.error(section, f"{name}: falta al menos un ejemplo inválido que falle por el motivo declarado")
        if stem not in covered_valid and stem not in registry_schemas:
            r.error(section, f"{name}: falta al menos un ejemplo válido")
    chains = EXAMPLES / "cadenas"
    valid_chain = load_json(chains / "auditoria-valida.json")
    tampered = load_json(chains / "auditoria-manipulada.json")
    validator = c.validator("audit-event.schema.json")
    for event in valid_chain:
        for kw, ptr, msg in schema_errors(validator, event):
            r.error("PV-11 auditoría", f"auditoria-valida.json seq {event['seq']}{ptr}: {msg}")
    if verify_chain(valid_chain) is not None:
        r.error("PV-11 auditoría", "la cadena válida no verifica")
    elif verify_chain(tampered) != 2:
        r.error("PV-11 auditoría", f"la cadena manipulada debía romperse en seq 2 y se rompe en {verify_chain(tampered)}")
    else:
        r.ok("PV-11 auditoría", 2)


def _collect_refs(node: Any, path: str = "") -> list[tuple[str, str]]:
    refs = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.append((path, value))
            else:
                refs.extend(_collect_refs(value, f"{path}/{key}"))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            refs.extend(_collect_refs(value, f"{path}/{i}"))
    return refs


def check_openapi(c: Contracts, r: Report, spec: dict | None = None) -> dict:
    section = "PV-03 OpenAPI"
    spec_rel = c.manifest["openapi"]["file"]
    if spec is None:
        try:
            spec = load_yaml(c.root / spec_rel)
        except (ValueError, TypeError, yaml.YAMLError) as err:
            r.error(section, f"{spec_rel}: no es YAML compatible con JSON ({err})")
            return {}
    oas = load_json(c.root / c.manifest["openapi"]["oas_schema"])
    for err in Draft202012Validator(oas).iter_errors(spec):
        r.error(section, f"{pointer(err.absolute_path)}: {err.message[:200]}")
    for where, ref in _collect_refs(spec):
        target, _, frag = ref.partition("#")
        try:
            doc = spec if not target else load_json((c.root / target).resolve())
            resolve_pointer(doc, frag)
        except (OSError, KeyError, IndexError, ValueError):
            r.error(section, f"{where}: $ref sin resolver {ref}")
    audit_actions = set(c.schemas["audit-event.schema.json"]["properties"]["action"]["enum"])
    tags = {t["name"] for t in spec.get("tags", [])}
    params = spec.get("components", {}).get("parameters", {})
    seen_ids: Counter = Counter()
    for route, item in spec.get("paths", {}).items():
        template = set(re.findall(r"\{([^}]+)\}", route))
        shared = item.get("parameters", [])
        for method, op in item.items():
            if method not in HTTP_METHODS:
                continue
            where = f"{method.upper()} {route}"
            seen_ids[op.get("operationId")] += 1
            declared = []
            for p in shared + op.get("parameters", []):
                p = resolve_pointer(spec, p["$ref"].partition("#")[2]) if "$ref" in p else p
                declared.append(p)
            path_params = {p["name"] for p in declared if p["in"] == "path"}
            if path_params != template:
                r.error(section, f"{where}: parámetros de ruta {sorted(path_params)} ≠ plantilla {sorted(template)}")
            for p in declared:
                if p["in"] == "path" and p.get("required") is not True:
                    r.error(section, f"{where}: el parámetro de ruta {p['name']} debe ser required")
            for tag in op.get("tags", []):
                if tag not in tags:
                    r.error(section, f"{where}: etiqueta no declarada {tag}")
            public = op.get("security") == []
            role = op.get("x-cr-min-role")
            if not public and role not in ROLE_GRANTS:
                r.error(section, f"{where}: x-cr-min-role ausente o inválido ({role})")
            if not isinstance(op.get("x-cr-phase"), int):
                r.error(section, f"{where}: falta x-cr-phase")
            audit = op.get("x-cr-audit")
            if audit is not None and audit not in audit_actions:
                r.error(section, f"{where}: x-cr-audit {audit} no es una acción de audit-event")
            if method in MUTATING and not op.get("x-cr-read-only"):
                if audit is None:
                    r.error(section, f"{where}: una operación que cambia estado declara x-cr-audit")
                names = {p["name"] for p in declared}
                if not public and not {"Idempotency-Key", "X-CSRF-Token"} <= names:
                    r.error(section, f"{where}: exige Idempotency-Key y X-CSRF-Token")
            if method == "get" and "requestBody" in op:
                r.error(section, f"{where}: GET no admite cuerpo")
            responses = op.get("responses", {})
            if not any(code.startswith("2") for code in responses):
                r.error(section, f"{where}: sin respuesta 2xx")
            if not public and not {"401", "403"} <= set(responses):
                r.error(section, f"{where}: una operación protegida declara 401 y 403")
            if op.get("requestBody", {}).get("required") and not {"400", "422"} & set(responses):
                r.error(section, f"{where}: con cuerpo obligatorio declara 400 o 422")
            for code, resp in responses.items():
                resp = resolve_pointer(spec, resp["$ref"].partition("#")[2]) if "$ref" in resp else resp
                for media in resp.get("content", {}):
                    if media not in MEDIA_TYPES:
                        r.error(section, f"{where} {code}: tipo de contenido no admitido {media}")
            r.ok(section)
    for op_id, n in seen_ids.items():
        if not op_id or n > 1:
            r.error(section, f"operationId ausente o repetido: {op_id}")
    for name, p in params.items():
        if p.get("in") == "path" and p.get("required") is not True:
            r.error(section, f"components.parameters.{name}: parámetro de ruta sin required")
    return spec


def check_semconv(c: Contracts, r: Report) -> None:
    section = "PV-04 registro de nombres"
    pin, src = c.semconv["pinned"], c.snapshot["source"]
    if pin["genai_commit"] != src["genai"]["commit"] or pin["core_tag"] != src["core"]["tag"] or pin["schema_url"] != src["genai"]["schema_url"]:
        r.error(section, "pinned no coincide con la instantánea vendor (commit, etiqueta o schema_url)")
    names = Counter(a["name"] for a in c.semconv["attributes"])
    for name, n in names.items():
        if n > 1:
            r.error(section, f"atributo duplicado: {name}")
        if not name.startswith("cr."):
            r.error(section, f"atributo propio sin prefijo cr.: {name}")
    for name in c.semconv["content_capture"]["opt_in_attributes"]:
        if name not in c.snapshot["attributes"]:
            r.error(section, f"atributo opt-in inexistente en la instantánea: {name}")
    for attr in c.semconv["resource_attributes"]:
        if not c.attribute_known(attr["name"]):
            r.error(section, f"atributo de recurso desconocido: {attr['name']}")
    span_names = Counter(s["name"] for s in c.spans)
    for span in c.spans:
        where = f"span {span['name']}"
        if span_names[span["name"]] > 1:
            r.error(section, f"{where}: duplicado")
        if span["origin"] == "otel-genai":
            snap = c.snapshot["span_types"].get(span["otel_span_type"])
            if not snap:
                r.error(section, f"{where}: tipo {span['otel_span_type']} inexistente en la instantánea")
            elif snap["kind"].upper() != span["kind"]:
                r.error(section, f"{where}: la instantánea define kind {snap['kind']}")
            op = span.get("fixed_values", {}).get("gen_ai.operation.name")
            if op and op not in c.snapshot["operation_names"]:
                r.error(section, f"{where}: operación {op} desconocida")
        required = set(span["required_attributes"])
        for name in required | set(span.get("recommended_attributes", [])):
            if not c.attribute_known(name):
                r.error(section, f"{where}: atributo desconocido {name}")
        for placeholder in re.findall(r"\{([^}]+)\}", span["name"]):
            if placeholder not in required:
                r.error(section, f"{where}: el marcador {placeholder} debe ser atributo obligatorio")
            spec = c.cr_attributes.get(placeholder)
            if spec and spec["cardinality"] != "low":
                r.error(section, f"{where}: el marcador {placeholder} no es de cardinalidad baja")
        for name in span.get("fixed_values", {}):
            if name not in required | set(span.get("recommended_attributes", [])):
                r.error(section, f"{where}: valor fijo para un atributo no declarado ({name})")
        for event in span.get("events", []):
            if event not in c.event_names:
                r.error(section, f"{where}: evento no registrado {event}")
        r.ok(section)
    for event in c.semconv["events"]:
        if event["origin"] == "otel-genai" and event["name"] not in c.snapshot["events"]:
            r.error(section, f"evento {event['name']}: no existe en la instantánea")
        for name in event["attributes"]:
            if not c.attribute_known(name):
                r.error(section, f"evento {event['name']}: atributo desconocido {name}")
    for metric in c.semconv["metrics"]:
        where = f"métrica {metric['name']}"
        snap = c.snapshot["metrics"].get(metric["name"])
        if metric["origin"] == "otel-genai":
            if not snap:
                r.error(section, f"{where}: no existe en la instantánea")
            elif (snap["instrument"], snap["unit"]) != (metric["instrument"], metric["unit"]):
                r.error(section, f"{where}: la instantánea define {snap['instrument']} en {snap['unit']}")
        elif snap or metric["name"].startswith("gen_ai."):
            r.error(section, f"{where}: un nombre propio no puede invadir el espacio gen_ai.")
        for name in metric["attributes"]:
            spec = c.cr_attributes.get(name)
            if name.startswith("cr."):
                if not spec:
                    r.error(section, f"{where}: atributo no definido {name}")
                elif spec["cardinality"] != "low":
                    r.error(section, f"{where}: {name} tiene cardinalidad {spec['cardinality']} y no puede ir en métricas")
            elif name not in METRIC_SAFE_OTEL or name not in c.snapshot["attributes"]:
                r.error(section, f"{where}: {name} no es un atributo OTel de cardinalidad baja aceptado")
        r.ok(section)


def _anchor(r: Report, section: str, where: str, path: str | None, anchor: str | None) -> None:
    if not path or not anchor:
        return
    target = REPO / path
    if not target.is_file():
        r.error(section, f"{where}: no existe {path}")
    elif anchor not in target.read_text(encoding="utf-8", errors="replace"):
        r.error(section, f"{where}: «{anchor}» ya no aparece en {path}")
    else:
        r.ok(section)


def check_anchors(c: Contracts, r: Report) -> None:
    section = "PV-06 anclas"
    for t in c.thresholds.values():
        _anchor(r, section, f"umbral {t['id']}", t["source"].get("path"), t["source"].get("anchor"))
    for p in c.parameters.values():
        _anchor(r, section, f"parámetro {p['key']}", p["origin"]["path"], p["origin"]["anchor"])
    for t in c.tools.values():
        _anchor(r, section, f"herramienta {t['id']}", t["code"]["path"], t["code"]["anchor"])
        for key in t["limits"].get("parameters", []):
            if key not in c.parameters:
                r.error(section, f"herramienta {t['id']}: parámetro inexistente {key}")
        if t["kind"] != "agent" and t["id"] not in c.cr_attributes["cr.provider.name"]["enum"]:
            r.error(section, f"herramienta {t['id']}: falta en el enum de cr.provider.name")
    for chain in c.registries["registros/enrutamiento.json"]["chains"]:
        _anchor(r, section, f"cadena {chain['id']}", chain.get("code", {}).get("path"), chain.get("code", {}).get("anchor"))
        for step in chain["steps"]:
            if step["tool"] not in c.tools:
                r.error(section, f"cadena {chain['id']}: herramienta inexistente {step['tool']}")
        for gid in chain.get("guardrails", []) + ([chain["disabled_by"]] if "disabled_by" in chain else []):
            if gid not in c.guardrails:
                r.error(section, f"cadena {chain['id']}: guarda inexistente {gid}")
    for g in c.guardrails.values():
        _anchor(r, section, f"guarda {g['id']}", g["enforcement"].get("path"), g["enforcement"].get("anchor"))
        for test in g["tests"]:
            file, _, func = test.partition("::")
            target = REPO / file
            if not target.is_file() or f"def {func}(" not in target.read_text(encoding="utf-8"):
                r.error("PV-10 pruebas citadas", f"guarda {g['id']}: no existe {test}")
            else:
                r.ok("PV-10 pruebas citadas")
        for tid in g.get("thresholds", []):
            if tid not in c.thresholds:
                r.error(section, f"guarda {g['id']}: umbral inexistente {tid}")
        for key in g.get("parameters", []):
            if key not in c.parameters:
                r.error(section, f"guarda {g['id']}: parámetro inexistente {key}")
    for i in c.interventions.values():
        ex = i["executor"]
        _anchor(r, section, f"intervención {i['id']}", ex.get("anchor_path"), ex.get("anchor"))
        if i.get("undo") and i["undo"] not in c.interventions:
            r.error(section, f"intervención {i['id']}: undo inexistente {i['undo']}")
        if ex["kind"] == "cli":
            placeholders = set(re.findall(r"\{([a-z_]+)\}", " ".join(ex["argv"])))
            declared = {p["name"] for p in i.get("parameters", [])}
            if placeholders != declared:
                r.error(section, f"intervención {i['id']}: argv usa {sorted(placeholders)} y declara {sorted(declared)}")


def check_cross_references(c: Contracts, r: Report, docs: dict[str, str]) -> None:
    section = "trazabilidad"
    eval_names = set(c.schemas["evaluation-result.schema.json"]["$defs"]["EvaluationName"]["enum"])
    reasons = set(c.cr_attributes["cr.quality.reason"]["enum"])
    runbooks = set(re.findall(r"^#{2,4} (RB-[0-9]{2})\b", docs.get("01-manifiesto-observabilidad.md", ""), re.M))
    for t in c.thresholds.values():
        where = f"umbral {t['id']}"
        kind, _, rest = t["signal"].partition(":")
        if kind == "metric":
            name = rest.split("{")[0]
            if name not in c.metrics:
                r.error(section, f"{where}: métrica fuera del registro {name}")
        elif kind == "ledger":
            record, _, fieldname = rest.partition(".")
            stem = LEDGER_RECORDS.get(record)
            if not stem or fieldname not in c.schemas[f"{stem}.schema.json"].get("properties", {}):
                r.error(section, f"{where}: {rest} no es un campo de un registro del libro")
        elif kind == "eval" and rest not in eval_names:
            r.error(section, f"{where}: evaluación no registrada {rest}")
        elif kind == "check" and rest.startswith("quality.assess:") and rest.split(":", 1)[1] not in reasons:
            r.error(section, f"{where}: motivo de assess desconocido {rest}")
        alert = t.get("alert")
        if alert:
            if alert["runbook"] not in runbooks:
                r.error(section, f"{where}: el runbook {alert['runbook']} no tiene sección en el manifiesto")
            if alert.get("intervention") and alert["intervention"] not in c.interventions:
                r.error(section, f"{where}: intervención inexistente {alert['intervention']}")
        r.ok(section)
    anchors = {name: doc_anchors(text) for name, text in docs.items()}
    protocols = {p["id"] for p in c.trace["protocols"]}
    cited = set()
    for req in c.trace["requirements"]:
        for ref in req["sections"]:
            file, _, anchor = ref.partition("#")
            if anchor not in anchors.get(file, set()):
                r.error(section, f"{req['id']}: no existe la sección {ref}")
        for contract in req["contracts"]:
            if not (c.root / contract).is_file():
                r.error(section, f"{req['id']}: no existe el contrato {contract}")
        for pv in req["protocols"]:
            cited.add(pv)
            if pv not in protocols:
                r.error(section, f"{req['id']}: protocolo inexistente {pv}")
    for pv in sorted(protocols - cited):
        r.warn(section, f"{pv} no cubre ningún requisito")
    parts = Counter(req["part"] for req in c.trace["requirements"])
    for part in range(1, 6):
        if not parts[part]:
            r.error(section, f"la parte {part} del encargo no tiene requisitos trazados")


def check_secrets(r: Report) -> None:
    section = "PV-15 secretos"
    drive_ids = set()
    manifest = REPO / "docs/automatizacion-drive/manifest.json"
    if manifest.is_file():
        data = load_json(manifest)
        drive_ids = {v for v in data.get("folders", {}).values() if isinstance(v, str) and len(v) > 20}
        if isinstance(data.get("queue_index_file_id"), str):
            drive_ids.add(data["queue_index_file_id"])
    for path in sorted(DOCS.rglob("*")):
        if not path.is_file() or path.suffix not in {".md", ".json", ".yaml", ".yml", ".py", ".txt"} or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                r.error(section, f"{path.relative_to(REPO)}: posible {label} ({match.group(0)[:12]}…)")
        for drive_id in drive_ids:
            if drive_id in text:
                r.error(section, f"{path.relative_to(REPO)}: contiene un ID de Drive del manifiesto")
        r.ok(section)


def scan_secrets(text: str) -> list[str]:
    return [label for label, pattern in SECRET_PATTERNS if pattern.search(text)]


TONE_PY = {
    "min_mass": r"def label\(bull: float, bear: float, min_mass: float = ([0-9.]+)\)",
    "label_up": r"if net >= ([0-9.]+):\n\s+return \"alcista\"",
    "label_down": r"if net <= -([0-9.]+):\n\s+return \"bajista\"",
    "strength_high": r"return 3 if net >= ([0-9.]+) else 2 if net >= [0-9.]+ else 1",
    "strength_mid": r"return 3 if net >= [0-9.]+ else 2 if net >= ([0-9.]+) else 1",
}
TONE_JS = {
    "min_mass": r"CR\.toneLabel = \(bull, bear, minMass = ([0-9.]+)\)",
    "label_up": r"net >= ([0-9.]+) \? 'alcista'",
    "label_down": r"net <= -([0-9.]+) \? 'bajista'",
    "strength_high": r"n >= ([0-9.]+) \? 3 : n >= [0-9.]+ \? 2 : 1",
    "strength_mid": r"n >= [0-9.]+ \? 3 : n >= ([0-9.]+) \? 2 : 1",
}


def tone_values(text: str, patterns: dict[str, str]) -> dict[str, float | None]:
    out = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        out[key] = float(match.group(1)) if match else None
    return out


def check_tone(c: Contracts, r: Report) -> None:
    section = "PV-16 tono"
    py_file, js_file = REPO / "prototypes/movil/tono.py", REPO / "prototypes/movil/shared/core.js"
    if not py_file.is_file() or not js_file.is_file():
        r.error(section, "faltan tono.py o shared/core.js")
        return
    py, js = tone_values(py_file.read_text(encoding="utf-8"), TONE_PY), tone_values(js_file.read_text(encoding="utf-8"), TONE_JS)
    expected = {"min_mass": c.parameters["tone.min_mass"]["current"], "label_up": c.parameters["tone.label_threshold"]["current"],
                "label_down": c.parameters["tone.label_threshold"]["current"],
                "strength_mid": c.parameters["tone.strength_cutoffs"]["current"][0], "strength_high": c.parameters["tone.strength_cutoffs"]["current"][1]}
    for key, value in expected.items():
        if py[key] is None or js[key] is None:
            r.error(section, f"{key}: el patrón ya no encuentra el umbral en {'tono.py' if py[key] is None else 'core.js'}; actualiza la comprobación")
        elif not (py[key] == js[key] == float(value)):
            r.error(section, f"{key}: tono.py={py[key]} core.js={js[key]} catálogo={value}")
        else:
            r.ok(section)


# ------------------------------------------------------------------------------- bloques generados
def _md(text: str) -> str:
    """Texto libre seguro en una celda: sin etiquetas HTML accidentales ni barras que rompan la tabla."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("\n", " ")


def _code(text: Any) -> str:
    return f"`{text}`"


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, float):
        text = f"{value:,.4f}".rstrip("0").rstrip(".")
        return text.replace(",", "\u202f").replace(".", ",")
    if isinstance(value, int):
        return f"{value:,}".replace(",", "\u202f")
    if isinstance(value, list):
        return ", ".join(_cell(v) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}: {_cell(v)}" for k, v in value.items())
    return _md(value)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    """Las celdas str ya llegan formateadas (Markdown); el resto se formatea con _cell."""
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(v if isinstance(v, str) else _cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


OPS = {"lt": "<", "lte": "≤", "gt": ">", "gte": "≥", "eq": "=", "neq": "≠"}
MODE_ES = {"enforce": "bloquea", "alert": "alerta", "monitor": "monitor", "proposed": "propuesto"}
WINDOW_ES = {"instant": "instante", "per_item": "por elemento", "per_run": "por ejecución", "1h": "1 h", "24h": "24 h",
             "7d": "7 días", "30d": "30 días", "calendar_month": "mes natural"}
AGGREGATION_ES = {"per_item": "por elemento", "per_run": "por ejecución", "last": "último valor", "age": "antigüedad", "max": "máximo",
                  "sum": "suma", "count": "recuento", "ratio": "proporción", "mean": "media", "p50": "p50", "p90": "p90", "p95": "p95",
                  "consecutive": "consecutivos", "kappa": "kappa"}
SOURCE_ES = {"code": "código", "existing_rule": "regla actual", "measurement": "medición", "proposal": "propuesta", "contract": "contrato"}
UNIT_ES = {"1": "", "s": "s", "By": "B", "{USD}": "USD", "{run}": "ejecuciones", "{job}": "trabajos", "{span}": "spans", "{video}": "videos",
           "{chunk}": "chunks", "{vector}": "vectores", "{step}": "pasos", "{feedback}": "valoraciones", "{threshold}": "umbrales",
           "{word}/min": "palabras/min", "{cpu}": "vCPU", "{unit}": "unidades", "{token}": "tokens", "{credit}": "créditos", "{request}": "peticiones",
           "h": "h", "{transition}": "transiciones", "{verdict}": "veredictos", "{error}": "errores", "{check}": "comprobaciones",
           "{rating}": "valoraciones", "{intervention}": "intervenciones"}
GIB = 1024 ** 3


SINGULAR_ES = {"ejecuciones": "ejecución", "trabajos": "trabajo", "videos": "video", "spans": "span", "chunks": "chunk", "vectores": "vector",
               "pasos": "paso", "valoraciones": "valoración", "umbrales": "umbral", "tokens": "token", "créditos": "crédito", "peticiones": "petición"}


def _quantity(value: Any, unit: str) -> str:
    if unit == "By" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{_cell(round(value / GIB, 2))} GiB"
    shown = UNIT_ES.get(unit, unit)
    if value == 1 and shown in SINGULAR_ES:
        shown = SINGULAR_ES[shown]
    return f"{_cell(value)} {shown}".strip()


def _level(level: dict | None, unit: str) -> str:
    if not level:
        return "—"
    value = level["value"]
    if level["op"] == "outside":
        low, high = (_quantity(float(v), unit) for v in value)
        return f"fuera de [{low.split(' ')[0]}, {high}]"
    if isinstance(value, bool):
        return "si ocurre" if (level["op"] == "eq") == value else "si no ocurre"
    return f"{OPS[level['op']]} {_quantity(value, unit)}"


def render_thresholds(c: Contracts, domain: str | None = None, category: str | None = None) -> str:
    rows = []
    for t in c.thresholds.values():
        if (domain and t["domain"] != domain) or (category and t["category"] != category):
            continue
        levels = t.get("levels", {})
        critical = _level(levels.get("critical"), t["unit"])
        if t.get("rule"):
            critical = (critical + "; " if critical != "—" else "") + _md(t["rule"])
        baseline = t.get("baseline")
        if not baseline:
            base_text = "—"
        elif baseline["value"] is None or isinstance(baseline["value"], str):
            base_text = _md(baseline["note"])
        else:
            base_text = f"{_quantity(baseline['value'], t['unit'])} · {_md(baseline['note'])}"
        source = t["source"]
        origin = _code(source["path"]) if source.get("path") else SOURCE_ES[source["kind"]]
        mode = MODE_ES[t["mode"]] + (f" (fase {t['phase']})" if t.get("phase") is not None and t["mode"] == "proposed" else "")
        aggregation = AGGREGATION_ES[t["aggregation"]]
        window = WINDOW_ES[t["window"]]
        when = aggregation if aggregation == window else f"{aggregation} · {window}"
        rows.append([f"**{t['id']}**", _md(t["name"]), _code(t["signal"]), when, _level(levels.get("warning"), t["unit"]), critical, mode, base_text, origin])
    return _table(["ID", "Umbral", "Señal", "Agregación · ventana", "Aviso", "Crítico", "Modo", "Línea base (14-oct)", "Origen"], rows)


def render_spans(c: Contracts) -> str:
    rows = [[_code(s["name"]), _code(s["kind"]), ", ".join(s["services"]), s["origin"] + (f" ({_code(s['otel_span_type'])})" if s.get("otel_span_type") else ""),
             ", ".join(_code(a) for a in s["required_attributes"]), _md(s.get("error_rule", "—"))] for s in c.spans]
    return _table(["Span", "Kind", "Servicios", "Origen", "Atributos obligatorios", "Cuándo es ERROR"], rows)


def render_metrics(c: Contracts) -> str:
    rows = [[_code(m["name"]), m["instrument"], _code(m["unit"]), ", ".join(_code(a) for a in m["attributes"]), ", ".join(m["emitted_by"]), _md(m["description"])]
            for m in c.semconv["metrics"]]
    return _table(["Métrica", "Instrumento", "Unidad", "Atributos", "Emisores", "Descripción"], rows)


def render_attributes(c: Contracts) -> str:
    rows = [[_code(a["name"]), a["type"], a["cardinality"], ", ".join(_code(v) for v in a.get("enum", [])) or "—", _md(a["description"])] for a in c.semconv["attributes"]]
    return _table(["Atributo", "Tipo", "Cardinalidad", "Valores", "Descripción"], rows)


CATEGORY_ES = {"prompt": "Prompts e instrucciones", "model": "Modelos", "routing": "Enrutamiento", "tool_registry": "Herramientas",
               "guardrail": "Guardas", "retry_fallback": "Reintentos y fallback", "budget": "Presupuestos", "quality_gate": "Puertas de calidad",
               "scheduling": "Calendario", "tone": "Motor de tono", "alerting": "Avisos"}


def _parameter_value(p: dict) -> str:
    current = p["current"]
    if isinstance(current, dict) and "version" in current:
        return f"{_code(current['version'])} · `{current['sha256'][:12]}…`"
    if isinstance(current, dict) and "canonical_sha256" in current:
        return f"hash canónico `{current['canonical_sha256'][:12]}…`"
    if isinstance(current, list):
        return ", ".join(_code(v) if isinstance(v, str) else _cell(v) for v in current) + (f" {UNIT_ES.get(p['unit'], p['unit'])}" if p.get("unit") else "")
    if isinstance(current, str):
        return _code(current) if current else "(vacío)"
    if current is None or isinstance(current, bool):
        return _cell(current)
    return _quantity(current, p.get("unit", "1"))


def render_parameters(c: Contracts) -> str:
    out = []
    for category, title in CATEGORY_ES.items():
        rows = []
        for p in c.parameters.values():
            if p["category"] != category:
                continue
            bounds = p.get("bounds", {})
            parts = []
            if "min" in bounds and "max" in bounds:
                parts.append(f"{_cell(bounds['min'])}–{_cell(bounds['max'])}")
            if "max_items" in bounds:
                parts.append(f"≤ {bounds['max_items']} elementos")
            ceiling = p.get("host_ceiling")
            ceiling_text = (_code(ceiling["value"]) if isinstance(ceiling["value"], (str, bool)) else _cell(ceiling["value"])) if ceiling else "—"
            if ceiling and isinstance(ceiling["value"], bool):
                ceiling_text = _code(str(ceiling["value"]).lower())
            role = _code(p["min_role"]) + (" + 2.ª persona" if p["approval"] == "second_person" else "")
            rows.append([_code(p["key"]), _parameter_value(p), " ".join(parts) or "—", ceiling_text, _code(p["apply"]), _code(p["risk"]), role,
                         _code(p["status"]), _code(p["origin"].get("name") or p["origin"]["path"].rsplit("/", 1)[-1])])
        if rows:
            out.append(f"**{title}**\n\n" + _table(["Parámetro", "Vigente", "Sobre del panel", "Techo del host", "Aplicación", "Riesgo", "Rol", "Estado", "Origen"], rows))
    return "\n\n".join(out)


COST_MODEL_ES = {"free": "gratis", "per_request": "por petición", "per_credit": "por crédito", "per_token": "por token", "subscription": "suscripción"}
LIMIT_ES = {"timeout_s": "timeout {} s", "tries": "{} intentos", "monthly_quota": "cuota {} al mes"}


def render_tools(c: Contracts) -> str:
    rows = []
    for t in c.tools.values():
        cost = COST_MODEL_ES[t["cost"]["model"]] + (f" ({_code(t['cost']['budget'])})" if t["cost"].get("budget") else "")
        limits = ", ".join(LIMIT_ES[k].format(_cell(v)) for k, v in t["limits"].items() if k in LIMIT_ES) or "—"
        rows.append([_code(t["id"]), _code(t["kind"]), _code(t["lifecycle"]), ", ".join(_code(x) for x in t["capabilities"]), cost, limits,
                     _md(t["health_source"]), _md(" ".join(t.get("known_issues", []))) or "—"])
    return _table(["Herramienta", "Tipo", "Ciclo de vida", "Capacidades", "Coste", "Límites", "Fuente de salud", "Problemas conocidos"], rows)


RETRY_ES = {"per_call_tries": "{} intentos por llamada", "backoff_base_s": "backoff base {} s", "backoff_cap_s": "backoff máximo {} s",
            "max_attempts": "{} intentos máximos", "give_up_hours": "abandono a las {} h"}


def render_routing(c: Contracts) -> str:
    out = []
    for chain in c.registries["registros/enrutamiento.json"]["chains"]:
        state = "activa" if chain["enabled"] else f"apagada por {chain['disabled_by']}"
        steps = []
        for n, step in enumerate(chain["steps"], 1):
            label = f"{n}. {_code(step['tool'])}" + "".join(f" · {_code(step[k])}" for k in ("operation", "model") if step.get(k)) + (f" · modo {_code(step['mode'])}" if step.get("mode") else "")
            if step.get("skip_if"):
                label += " — se salta si: " + "; ".join(_md(s) for s in step["skip_if"])
            if step.get("advance_on"):
                label += " — pasa al siguiente con: " + ", ".join(_code(s) for s in step["advance_on"])
            steps.append(label)
        retry = chain["retry"]
        parts = [RETRY_ES[k].format(_cell(v)) for k, v in retry.items() if k in RETRY_ES]
        parts.append("automáticos" if retry.get("automatic") else "solo manuales")
        text = f"**{_code(chain['id'])}** ({chain['service']}, {state}). {_md(chain['purpose'])}\n\n" + "\n".join(steps)
        text += f"\n\n*Parada:* {_md(chain['stop_rule'])} *Reintentos:* {', '.join(parts)}."
        if retry.get("note"):
            text += f" {_md(retry['note'])}"
        if chain.get("cooldown"):
            cd = chain["cooldown"]
            text += f" *Cooldown:* {_cell(cd['duration_s'])} s tras {cd['after_consecutive_errors']} errores seguidos o con {', '.join(_code(o) for o in cd['on_outcomes'])}."
        if chain.get("guardrails"):
            text += f" *Guardas:* {', '.join(chain['guardrails'])}."
        out.append(text)
    return "\n\n".join(out)


POINT_ES = {"code": "código", "systemd": "systemd", "instructions": "instrucciones", "panel": "panel", "collector": "Collector", "ci": "CI"}
FAILURE_ES = {"fail_closed": "bloquea", "fail_open": "deja pasar"}
GUARD_MODE_ES = {"enforce": "en vigor", "monitor": "vigilada", "proposed": "propuesta"}


def render_guardrails(c: Contracts) -> str:
    rows = []
    for g in c.guardrails.values():
        enf = g["enforcement"]
        point = POINT_ES[enf["point"]] + (f" · {_code(enf['path'])}" if enf.get("path") else "")
        tests = ", ".join(_code(t.split("::")[1]) for t in g["tests"]) or _md(g.get("gap") or "—")
        mode = GUARD_MODE_ES[g["mode"]] + (f" (fase {g['phase']})" if g.get("phase") is not None else "")
        change = _code(g["change"]["min_role"]) + (" + 2.ª persona" if g["change"]["approval"] == "second_person" else "") + "; " + "; ".join(_md(x) for x in g["change"]["requires"])
        rows.append([f"**{g['id']}**", _md(g["title"]), point, mode, FAILURE_ES[g["failure_mode"]], tests, change])
    return _table(["ID", "Guarda", "Dónde se aplica", "Modo", "Ante la duda", "Pruebas (o hueco)", "Cambiarla exige"], rows)


def _operations(spec: dict) -> list[tuple[str, str, dict]]:
    return [(method.upper(), route, op) for route, item in spec.get("paths", {}).items() for method, op in item.items() if method in HTTP_METHODS]


def render_api(spec: dict) -> str:
    rows = [[m, _code(route), _code(op["operationId"]), _code(op["x-cr-min-role"]) if op.get("x-cr-min-role") else "público",
             _code(op["x-cr-audit"]) if op.get("x-cr-audit") else "—", op.get("x-cr-phase")] for m, route, op in _operations(spec)]
    return _table(["Método", "Ruta (/api/v1)", "Operación", "Rol mínimo", "Auditoría", "Fase"], rows)


def render_rbac(spec: dict) -> str:
    roles = ["viewer", "reviewer", "operator", "admin", "auditor"]
    rows = []
    for m, route, op in _operations(spec):
        if m == "GET" and not op.get("x-cr-audit") and op.get("x-cr-min-role") in ("viewer", None):
            continue
        needed = op.get("x-cr-min-role")
        marks = ["✓" if needed is None or needed in ROLE_GRANTS[role] else "·" for role in roles]
        rows.append([_code(op["operationId"]), *marks, _code(op["x-cr-audit"]) if op.get("x-cr-audit") else "—"])
    return _table(["Operación", *(_code(r) for r in roles), "Acción auditada"], rows)


COST_ES = {"none": "ninguno", "credits": "créditos", "paid_api": "API de pago", "subscription_quota": "cuota de ChatGPT"}


def render_interventions(c: Contracts) -> str:
    rows = []
    for i in c.interventions.values():
        ex = i["executor"]
        if ex.get("argv"):
            shown = ex["argv"][2:] if ex["kind"] == "cli" else ex["argv"][1:]
            executor = f"{ex['kind']} · {_code(' '.join(shown))}"
        elif ex.get("file"):
            executor = f"{ex['kind']} · {_code(ex['file'])}"
        else:
            executor = ex["kind"]
        rows.append([_code(i["id"]), _md(i["title"]), _code(i["target_kind"]), _code(i["min_role"]), "sí" if i["approval"] == "second_person" else "no",
                     _code(i["risk"]), f"sí ({_code(i['undo'])})" if i["reversible"] else "no", COST_ES[i["cost"]], executor, i["phase"]])
    return _table(["Tipo", "Intervención", "Objetivo", "Rol", "2.ª persona", "Riesgo", "Reversible", "Coste", "Ejecutor", "Fase"], rows)


WHEN_ES = {"ci": "CI", "pre_deploy": "antes de desplegar", "daily": "diario", "weekly": "semanal", "monthly": "mensual", "on_change": "en cada cambio", "on_demand": "a demanda"}


def render_protocols(c: Contracts) -> str:
    rows = [[f"**{p['id']}**", _md(p["title"]), _md(p["what"]), _code(p["how"]) if p["how"].startswith(("python3", "validate_contracts")) else _md(p["how"]),
             WHEN_ES[p["when"]], _md(p["pass"]), "implementado" if p["implemented"] else f"fase {p['phase']}"] for p in c.trace["protocols"]]
    return _table(["ID", "Protocolo", "Qué comprueba", "Cómo", "Cuándo", "Criterio de aprobación", "Estado"], rows)


STATUS_ES = {"covered": "cubierto", "partial": "parcial", "planned": "planificado"}


def render_traceability(c: Contracts) -> str:
    rows = []
    for req in c.trace["requirements"]:
        sections = ", ".join(f"[{s.split('#')[1]}]({s})" for s in req["sections"])
        contracts = ", ".join(f"[{_code(Path(x).name)}](contratos/{x})" for x in req["contracts"]) or "—"
        status = STATUS_ES[req["status"]] + (f": {_md(req['note'])}" if req.get("note") else "")
        rows.append([f"**{req['id']}**", req["part"], _md(req["text"]), sections, contracts, ", ".join(req["protocols"]), status])
    return _table(["Req.", "Parte", "Requisito", "Secciones", "Contratos", "Protocolos", "Estado"], rows)


def render_contract_inventory(c: Contracts) -> str:
    rows = []
    for name, title in c.manifest["schemas"].items():
        stem = name.removesuffix(".schema.json")
        valid = len(list((EXAMPLES / "validos" / stem).glob("*.json")))
        invalid_n = len(list((EXAMPLES / "invalidos" / stem).glob("*.json")))
        registry = next((rel for rel, schema in c.manifest["registries"].items() if schema.endswith(name)), None)
        rows.append([f"[{_code(name)}](esquemas/{name})", _md(title), f"[{_code(Path(registry).name)}]({registry})" if registry else "—", valid, invalid_n])
    return _table(["Esquema", "Contrato", "Instancia real", "Ejemplos válidos", "Ejemplos inválidos"], rows)


def renderers(c: Contracts, spec: dict) -> dict[str, Callable[[], str]]:
    return {
        "semconv-spans": lambda: render_spans(c),
        "semconv-metricas": lambda: render_metrics(c),
        "semconv-atributos": lambda: render_attributes(c),
        "umbrales-salud": lambda: render_thresholds(c, "system_health"),
        "umbrales-coste": lambda: render_thresholds(c, "cost"),
        "umbrales-agentes": lambda: render_thresholds(c, "agent_performance"),
        "umbrales-video": lambda: render_thresholds(c, "data_quality", "video_metadata"),
        "umbrales-transcripcion": lambda: render_thresholds(c, "data_quality", "transcript"),
        "umbrales-chunking": lambda: render_thresholds(c, "data_quality", "chunking"),
        "umbrales-embeddings": lambda: render_thresholds(c, "data_quality", "embeddings"),
        "umbrales-etiquetado": lambda: render_thresholds(c, "data_quality", "tagging"),
        "umbrales-analisis": lambda: render_thresholds(c, "data_quality", "analysis"),
        "umbrales-recursos": lambda: render_thresholds(c, "resources"),
        "parametros": lambda: render_parameters(c),
        "herramientas": lambda: render_tools(c),
        "enrutamiento": lambda: render_routing(c),
        "guardrails": lambda: render_guardrails(c),
        "api-resumen": lambda: render_api(spec),
        "rbac": lambda: render_rbac(spec),
        "intervenciones": lambda: render_interventions(c),
        "protocolos": lambda: render_protocols(c),
        "trazabilidad": lambda: render_traceability(c),
        "inventario-contratos": lambda: render_contract_inventory(c),
    }


BLOCK = re.compile(r"(<!-- generado:inicio (?P<id>[a-z0-9-]+) -->\n)(?P<body>.*?)(\n<!-- generado:fin (?P=id) -->)", re.S)


def check_generated(c: Contracts, r: Report, spec: dict, write: bool) -> None:
    section = "PV-05 documento al día"
    available = renderers(c, spec)
    used = Counter()
    for path in sorted([*DOCS.glob("*.md"), *(CONTRACTS.glob("*.md"))]):
        text = path.read_text(encoding="utf-8")

        def replace(match: re.Match) -> str:
            block_id = match.group("id")
            used[block_id] += 1
            if block_id not in available:
                r.error(section, f"{path.name}: bloque desconocido {block_id}")
                return match.group(0)
            fresh = available[block_id]()
            if match.group("body") != fresh:
                if write:
                    r.ok("bloques regenerados")
                else:
                    r.error(section, f"{path.name}: el bloque {block_id} no coincide con los registros (ejecuta --write)")
                return match.group(1) + fresh + match.group(4)
            r.ok(section)
            return match.group(0)

        updated = BLOCK.sub(replace, text)
        if write and updated != text:
            path.write_text(updated, encoding="utf-8")
    for block_id in available:
        if used[block_id] == 0:
            r.error(section, f"ningún documento incluye el bloque {block_id}")
        elif used[block_id] > 1:
            r.error(section, f"el bloque {block_id} aparece {used[block_id]} veces")


LINK = re.compile(r"\]\(([^)\s]+)\)")


def check_links(r: Report) -> None:
    """Enlaces relativos de los Markdown del paquete: el archivo existe y, si lleva #ancla, la ancla también."""
    section = "PV-05 enlaces"
    for path in sorted([*DOCS.glob("*.md"), *CONTRACTS.glob("*.md")]):
        text = path.read_text(encoding="utf-8")
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            file_part, _, anchor = target.partition("#")
            dest = (path.parent / file_part).resolve() if file_part else path
            if not dest.exists():
                r.error(section, f"{path.name}: enlace roto {target}")
                continue
            if anchor and dest.suffix == ".md" and anchor not in doc_anchors(dest.read_text(encoding="utf-8")):
                r.error(section, f"{path.name}: ancla inexistente {target}")
                continue
            r.ok(section)


# ------------------------------------------------------------------------------- datos reales (PV-07)
def _quality_module():
    sys.dont_write_bytecode = True  # no dejar __pycache__ en el código de los servicios
    sys.path.insert(0, str(REPO / "services/transcripts"))
    from crtranscripts import quality  # noqa: PLC0415 - import diferido, solo con --datos-reales
    return quality


def check_real_data(c: Contracts, r: Report, data_dir: Path) -> None:
    section = "PV-07 datos reales"
    status_file = data_dir / "bridge" / "status.json"
    if status_file.is_file():
        for kw, ptr, msg in schema_errors(c.validator("pipeline-status.schema.json"), load_json(status_file)):
            r.error(section, f"bridge/status.json{ptr}: {msg} [{kw}]")
        r.ok(section)
    quality = _quality_module()
    asset_validator = c.validator("asset.schema.json")
    transcripts = {}
    for path in sorted((data_dir / "transcripts").glob("*/*.json")):
        raw = path.read_bytes()
        doc = json.loads(raw)
        video, tr = doc["video"], doc["transcript"]
        verdict = quality.assess(doc)
        transcripts[(path.parent.name, path.name)] = hashlib.sha256(raw).hexdigest()
        asset = {"asset_id": f"transcript:{video['video_id']}", "kind": "transcript", "title": video["title"][:300], "video_id": video["video_id"],
                 "channel": video["channel"]["slug"], "created_at": tr["fetched_at"], "current_version": transcripts[(path.parent.name, path.name)],
                 "versions": [{"version": transcripts[(path.parent.name, path.name)], "created_at": tr["fetched_at"], "created_by": {"kind": "service", "id": "cr-extractor"},
                               "status": "current", "storage": {"mode": "local", "uri": path.resolve().as_uri(), "bytes": len(raw), "media_type": "application/json"},
                               "quality": {"verdict": "invalid" if not verdict["valid"] else ("warning" if verdict["warnings"] else "valid"), "reasons": verdict["reasons"] + verdict["warnings"]},
                               "provenance": {"source": tr["provider"], "language": tr["language"], "track_kind": tr["track_kind"], "fetched_at": tr["fetched_at"]}}],
                 "lineage": [{"relation": "derived_from", "asset_id": f"video:{video['video_id']}"}],
                 "access": {"visibility": "internal", "retention": {"policy": "keep_all"}}}
        errors = schema_errors(asset_validator, asset)
        for kw, ptr, msg in errors:
            r.error(section, f"{path.relative_to(data_dir)} → asset{ptr}: {msg} [{kw}]")
        if not verdict["valid"]:
            r.warn(section, f"{path.relative_to(data_dir)}: la puerta de calidad la rechaza ({', '.join(verdict['reasons'])})")
        if not errors:
            r.ok(section)
    for path in sorted((data_dir / "analysis").glob("*/*.json")):
        if path.parent.name.startswith("_"):
            continue
        raw = path.read_bytes()
        doc = json.loads(raw)
        meta = doc["meta"]
        tr_sha = transcripts.get((path.parent.name, path.name))
        provider = meta.get("provider") if meta.get("provider") in ("chatgpt-scheduled", "openai", "anthropic") else "panel"
        prov = {"source": provider, "model": meta.get("model"), "model_verified": provider != "chatgpt-scheduled",
                "prompt_version": meta.get("prompt_version"), "prompt_sha256": meta.get("prompt_sha256"), "schema_sha256": meta.get("schema_sha256"),
                "transcript_sha256": meta.get("transcript_sha256"), "import_mode": meta.get("import_mode") or ("api" if provider in ("openai", "anthropic") else None)}
        if meta.get("job_id"):
            prov["job_id"] = meta["job_id"]
        prov = {k: v for k, v in prov.items() if v is not None or k in ("model", "import_mode")}
        matches = bool(tr_sha) and meta.get("transcript_sha256") == tr_sha and meta.get("status") == "ok" and (meta.get("validation") or {}).get("ok")
        asset = {"asset_id": f"analysis:{meta['video_id']}", "kind": "analysis", "title": f"Análisis de narrativas · {meta['video_id']}", "video_id": meta["video_id"],
                 "channel": meta["channel"], "created_at": meta["analyzed_at"], "current_version": hashlib.sha256(raw).hexdigest(),
                 "versions": [{"version": hashlib.sha256(raw).hexdigest(), "created_at": meta["analyzed_at"], "created_by": {"kind": "service", "id": "cr-bridge" if provider == "chatgpt-scheduled" else "cr-analysis"},
                               "status": "current", "storage": {"mode": "local", "uri": path.resolve().as_uri(), "bytes": len(raw), "media_type": "application/json"},
                               "quality": {"verdict": "valid" if matches else "invalid"}, "provenance": prov}],
                 "lineage": [{"relation": "derived_from", "asset_id": f"transcript:{meta['video_id']}", **({"version": tr_sha} if tr_sha else {})}],
                 "access": {"visibility": "internal", "retention": {"policy": "keep_all"}}}
        errors = schema_errors(asset_validator, asset)
        for kw, ptr, msg in errors:
            r.error(section, f"{path.relative_to(data_dir)} → asset{ptr}: {msg} [{kw}]")
        if not matches:
            r.warn(section, f"{path.relative_to(data_dir)}: no coincide con la transcripción vigente o no está validado (no se publicaría)")
        if not errors:
            r.ok(section)
    bridge_db = data_dir / "bridge" / "state.sqlite"
    if bridge_db.is_file():
        job_validator = c.validator("job.schema.json")
        conn = sqlite3.connect(f"file:{bridge_db}?mode=ro", uri=True)
        try:
            for job_id, state, detail, updated_at, published_at, payload in conn.execute(
                    "SELECT id, state, detail, updated_at, published_at, payload FROM jobs"):
                meta = json.loads(payload)["meta"]
                job = {"job_id": job_id, "video_id": meta["video_id"], "channel": meta["channel"], "state": state, "detail": detail,
                       "updated_at": updated_at, "published_at": published_at,
                       "hashes": {k: meta[k] for k in ("transcript_sha256", "prompt_sha256", "schema_sha256", "prompt_version")}}
                for kw, ptr, msg in schema_errors(job_validator, job):
                    r.error(section, f"bridge job {job_id[:11]}{ptr}: {msg} [{kw}]")
                r.ok(section)
        finally:
            conn.close()
    run_validator = c.validator("run-record.schema.json")
    limit = c.parameters["scheduled.jobs_per_run"]["current"]
    seen = set()
    for path in sorted((data_dir / "bridge" / "cache").glob("*.bin")):
        raw = path.read_bytes()
        try:
            receipt = json.loads(raw)
        except ValueError:
            continue
        if not (isinstance(receipt, dict) and "run_id" in receipt and "attempted_job_ids" in receipt) or receipt["run_id"] in seen:
            continue
        seen.add(receipt["run_id"])
        run_id = reconstructed_run_id(receipt["run_id"], receipt["started_at"])
        run = {"run_id": run_id, "service": "cr-scheduled-agent", "trigger": "external_schedule", "started_at": receipt["started_at"],
               "finished_at": receipt["finished_at"], "outcome": "failed" if receipt["status"] == "error" else "ok", "exit_code": None,
               "trace_id": run_id.replace("-", ""), "code": {"version": "instructions", "digest": hashlib.sha256(b"instructions").hexdigest()},
               "external": {"agent": "chatgpt_scheduled", "agent_run_id": receipt["run_id"], "receipt_status": receipt["status"],
                            "protocol_version": receipt.get("protocol_version", "1.0.0"), "attempted_job_ids": receipt["attempted_job_ids"],
                            "uploaded_job_ids": receipt["uploaded_job_ids"], "remaining_count": receipt.get("remaining_count"),
                            "errors": [str(e)[:500] for e in receipt.get("errors", [])], "receipt_sha256": hashlib.sha256(raw).hexdigest()}}
        errors = schema_errors(run_validator, run) + [("semantic", p, m) for p, m in check_run(c, run)]
        for kw, ptr, msg in errors:
            r.error(section, f"comprobante {receipt['run_id'][:8]}{ptr}: {msg} [{kw}]")
        if len(receipt["attempted_job_ids"]) > limit:
            r.warn(section, f"comprobante {receipt['run_id'][:8]} ({receipt['started_at']}): {len(receipt['attempted_job_ids'])} trabajos intentados, límite {limit} (AP-04)")
        if not errors:
            r.ok(section)


# ------------------------------------------------------------------------------- spans exportados (PV-08)
def _otlp_value(value: dict) -> Any:
    for key in ("stringValue", "boolValue", "intValue", "doubleValue"):
        if key in value:
            return int(value[key]) if key == "intValue" else value[key]
    if "arrayValue" in value:
        return [_otlp_value(v) for v in value["arrayValue"].get("values", [])]
    return None


def _otlp_attrs(items: list[dict]) -> dict:
    return {item["key"]: _otlp_value(item["value"]) for item in items or []}


def _otlp_time(nanos: str) -> str:
    seconds, rest = divmod(int(nanos), 1_000_000_000)
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + f".{rest:09d}Z"


KINDS = {1: "INTERNAL", 2: "SERVER", 3: "CLIENT", 4: "PRODUCER", 5: "CONSUMER", "SPAN_KIND_INTERNAL": "INTERNAL", "SPAN_KIND_SERVER": "SERVER",
         "SPAN_KIND_CLIENT": "CLIENT", "SPAN_KIND_PRODUCER": "PRODUCER", "SPAN_KIND_CONSUMER": "CONSUMER"}
STATUS = {0: "UNSET", 1: "OK", 2: "ERROR", "STATUS_CODE_UNSET": "UNSET", "STATUS_CODE_OK": "OK", "STATUS_CODE_ERROR": "ERROR"}


def otlp_to_span_records(batch: dict) -> list[dict]:
    """Convierte una línea del exportador file del Collector (OTLP/JSON) a registros span-record."""
    out = []
    for rs in batch.get("resourceSpans", []):
        resource = _otlp_attrs(rs.get("resource", {}).get("attributes", []))
        for scope in rs.get("scopeSpans", []):
            for s in scope.get("spans", []):
                record = {"trace_id": s["traceId"].lower(), "span_id": s["spanId"].lower(), "name": s["name"], "kind": KINDS.get(s.get("kind", 1), "INTERNAL"),
                          "start_time": _otlp_time(s["startTimeUnixNano"]), "end_time": _otlp_time(s["endTimeUnixNano"]),
                          "status": {"code": STATUS.get(s.get("status", {}).get("code", 0), "UNSET")}, "resource": resource,
                          "attributes": _otlp_attrs(s.get("attributes", []))}
                if s.get("parentSpanId"):
                    record["parent_span_id"] = s["parentSpanId"].lower()
                if s.get("status", {}).get("message"):
                    record["status"]["message"] = s["status"]["message"][:300]
                if s.get("events"):
                    record["events"] = [{"name": e["name"], "time": _otlp_time(e["timeUnixNano"]), "attributes": _otlp_attrs(e.get("attributes", []))} for e in s["events"]]
                if s.get("links"):
                    record["links"] = [{"trace_id": link["traceId"].lower(), "span_id": link["spanId"].lower()} for link in s["links"]]
                out.append(record)
    return out


def check_spans_file(c: Contracts, r: Report, path: Path) -> None:
    section = "PV-08 spans exportados"
    validator = c.validator("span-record.schema.json")
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        obj = json.loads(line)
        records = otlp_to_span_records(obj) if "resourceSpans" in obj else [obj]
        for record in records:
            problems = [(ptr, f"{msg} [{kw}]") for kw, ptr, msg in schema_errors(validator, record)]
            if not problems:
                problems = check_span(c, record)
            for ptr, msg in problems:
                r.error(section, f"línea {n} span {record.get('name')}{ptr}: {msg}")
            if not problems:
                r.ok(section)


# ------------------------------------------------------------------------------------------- principal
def run(write: bool = False, real_data: Path | None = None, spans: Path | None = None) -> Report:
    r = Report()
    c = Contracts()
    docs = {p.name: p.read_text(encoding="utf-8") for p in DOCS.glob("*.md")}
    check_manifest_and_schemas(c, r)
    check_registries(c, r)
    check_examples(c, r)
    spec = check_openapi(c, r)
    check_semconv(c, r)
    check_anchors(c, r)
    check_cross_references(c, r, docs)
    check_generated(c, r, spec, write)
    check_links(r)
    check_tone(c, r)
    check_secrets(r)
    if real_data:
        check_real_data(c, r, real_data)
    if spans:
        check_spans_file(c, r, spans)
    return r


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida los contratos de observabilidad de Urania/Diario.")
    parser.add_argument("--write", action="store_true", help="regenera las tablas generadas del documento")
    parser.add_argument("--datos-reales", type=Path, metavar="DIR", help="valida datos vivos (p. ej. /var/lib/cryptoreport-transcripts)")
    parser.add_argument("--spans", type=Path, metavar="JSONL", help="valida spans exportados (span-record u OTLP/JSON por línea)")
    args = parser.parse_args(argv)
    report = run(write=args.write, real_data=args.datos_reales, spans=args.spans)
    report.print()
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

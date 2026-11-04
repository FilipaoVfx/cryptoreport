"""Extrae una instantánea fijada de las convenciones semánticas de OpenTelemetry que usa el registro.

Solo se ejecuta a mano, al mover la versión fijada; el CI nunca descarga nada. Genera un JSON compacto
(nombres, estabilidad, tipos, instrumentos y unidades) con el SHA-256 de cada YAML de origen, para que
`validate_contracts.py` compruebe sin red que todo nombre `gen_ai.*` o estándar del registro existe.

Uso:
    python3 docs/observabilidad/herramientas/extract_semconv.py \
        --genai-commit 07794021bfe46e1c241408b6f55cb4354bd28318 --core-tag v1.44.0 \
        --out docs/observabilidad/contratos/vendor/otel-semconv-genai-0779402.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

import yaml

GENAI_REPO = "open-telemetry/semantic-conventions-genai"
CORE_REPO = "open-telemetry/semantic-conventions"
GENAI_FILES = (
    "model/manifest.yaml",
    "model/gen-ai/registry.yaml",
    "model/gen-ai/spans.yaml",
    "model/gen-ai/metrics.yaml",
    "model/gen-ai/token-metrics.yaml",
    "model/gen-ai/events.yaml",
    "model/openai/registry.yaml",
)
# Solo los espacios de nombres estándar que el registro de Urania/Diario usa.
CORE_FILES = tuple(f"model/{ns}/registry.yaml" for ns in
                   ("error", "server", "http", "service", "deployment", "host", "url", "exceptions"))


def fetch(repo: str, ref: str, path: str) -> bytes:
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 (URL fija de GitHub)
        return resp.read()


def attribute_items(doc: dict) -> list[dict]:
    """Admite los dos formatos de Weaver: `definition/2` (attributes[].key) y el clásico (groups[].attributes[].id)."""
    if "attributes" in doc:
        return [dict(item, _key=item["key"]) for item in doc["attributes"]]
    items = []
    for group in doc.get("groups", []):
        for item in group.get("attributes") or []:
            if "id" in item:
                items.append(dict(item, _key=item["id"]))
    return items


def describe_attribute(item: dict, origin: str) -> dict:
    kind = item.get("type")
    entry = {"stability": item.get("stability"), "origin": origin}
    if isinstance(kind, dict):
        entry["type"] = "enum"
        entry["members"] = [m.get("value") for m in kind.get("members", [])]
    else:
        entry["type"] = kind
    if item.get("deprecated"):
        entry["deprecated"] = True
    return entry


def extract(genai: dict[str, bytes], core: dict[str, bytes], genai_commit: str, core_tag: str) -> dict:
    manifest = yaml.safe_load(genai["model/manifest.yaml"])
    attributes: dict[str, dict] = {}
    for path in ("model/gen-ai/registry.yaml", "model/openai/registry.yaml"):
        for item in attribute_items(yaml.safe_load(genai[path])):
            attributes[item["_key"]] = describe_attribute(item, "genai")
    for path, raw in core.items():
        for item in attribute_items(yaml.safe_load(raw)):
            attributes.setdefault(item["_key"], describe_attribute(item, "core"))

    metrics = {}
    for path in ("model/gen-ai/metrics.yaml", "model/gen-ai/token-metrics.yaml"):
        for item in yaml.safe_load(genai[path]).get("metrics", []):
            metrics[item["name"]] = {"instrument": item.get("instrument"), "unit": item.get("unit"),
                                     "stability": item.get("stability")}
    events = {item["name"]: {"stability": item.get("stability")}
              for item in yaml.safe_load(genai["model/gen-ai/events.yaml"]).get("events", [])}
    spans = {item["type"]: {"kind": item.get("kind"), "stability": item.get("stability")}
             for item in yaml.safe_load(genai["model/gen-ai/spans.yaml"]).get("spans", [])}
    operation = attributes.get("gen_ai.operation.name", {})
    return {
        "source": {
            "genai": {"repository": GENAI_REPO, "commit": genai_commit, "schema_url": manifest.get("schema_url"),
                      "stability": manifest.get("stability"),
                      "files": {p: hashlib.sha256(genai[p]).hexdigest() for p in GENAI_FILES}},
            "core": {"repository": CORE_REPO, "tag": core_tag,
                     "files": {p: hashlib.sha256(core[p]).hexdigest() for p in CORE_FILES}},
        },
        "operation_names": operation.get("members", []),
        "attributes": dict(sorted(attributes.items())),
        "metrics": dict(sorted(metrics.items())),
        "events": dict(sorted(events.items())),
        "span_types": dict(sorted(spans.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--genai-commit", required=True, help="SHA completo de semantic-conventions-genai")
    parser.add_argument("--core-tag", required=True, help="etiqueta de semantic-conventions, p. ej. v1.44.0")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if len(args.genai_commit) != 40:
        parser.error("--genai-commit debe ser un SHA completo de 40 caracteres: una rama no es una versión fijada")
    genai = {p: fetch(GENAI_REPO, args.genai_commit, p) for p in GENAI_FILES}
    core = {p: fetch(CORE_REPO, args.core_tag, p) for p in CORE_FILES}
    snapshot = extract(genai, core, args.genai_commit, args.core_tag)
    args.out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{args.out}: {len(snapshot['attributes'])} atributos, {len(snapshot['metrics'])} métricas, "
          f"{len(snapshot['events'])} eventos, {len(snapshot['span_types'])} tipos de span", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

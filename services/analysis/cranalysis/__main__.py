"""CLI del análisis de narrativas.

    python -m cranalysis pending [--limit 20]          # transcripciones sin análisis
    python -m cranalysis dry-run VIDEO_ID              # arma la petición y muestra tamaños, sin llamar a la API
    python -m cranalysis run VIDEO_ID [--force]        # analiza, valida y guarda
    python -m cranalysis run --pending --limit 3       # las N transcripciones más nuevas sin análisis
    python -m cranalysis validate RUTA_ANALISIS.json   # vuelve a validar un análisis guardado

Solo se guarda como `ok` un análisis que pasa el schema y el validador; si no, queda guardado como
`rechazado` con sus errores, para revisarlo, y no debe publicarse.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import PROMPT_VERSION, load_config
from .request import api_schema, build_payload, build_request, load_prompt, load_schema, sha256
from .store import find_transcript, now_iso, output_path, pending, rejected_path, save
from .validate import validate


def _prepare(config, transcript: Path):
    prompt, schema = load_prompt(), load_schema()
    document = json.loads(transcript.read_text(encoding="utf-8"))
    payload = build_payload(document, now_iso())
    if config.provider == "openai":
        from .openai_client import build_openai_request
        return prompt, schema, document, payload, build_openai_request(config, prompt, schema, payload)
    return prompt, schema, document, payload, build_request(config, prompt, schema, payload)


def _client_and_runner(config):
    if config.provider == "openai":
        from openai import OpenAI

        from .openai_client import run_openai
        # Un análisis largo con razonamiento alto puede tardar minutos: margen de 15 min por petición.
        return OpenAI(timeout=900.0, max_retries=2), run_openai
    import anthropic

    from .client import run_analysis
    return anthropic.Anthropic(), run_analysis


def cmd_dry_run(config, ref: str) -> int:
    transcript = find_transcript(config.transcripts_dir, ref)
    prompt, schema, document, payload, request = _prepare(config, transcript)
    if config.provider == "openai":
        user, effort, limit = request["input"], request["reasoning"]["effort"], request["max_output_tokens"]
    else:
        user, effort, limit = request["messages"][0]["content"], request["output_config"]["effort"], request["max_tokens"]
    schema_text = json.dumps(api_schema(schema), ensure_ascii=False)
    print(f"transcripción: {transcript}")
    print(f"proveedor: {config.provider} · modelo: {request['model']} · effort: {effort} · límite de salida: {limit}")
    # Aproximación de ~3,5 caracteres por token en español; para el número exacto, count_tokens con la API.
    for name, text in (("system (cacheado)", prompt), ("mensaje de usuario", user), ("schema", schema_text)):
        print(f"  {name:<20} {len(text):>8} caracteres  ≈ {len(text) / 3.5:>7.0f} tokens")
    print(f"segmentos: {document['transcript']['segment_count']} · cobertura: {document['transcript'].get('coverage')}")
    return 0


def analyze_one(config, client, runner, transcript: Path, force: bool = False) -> str:
    from .client import AnalysisError, estimate_cost

    target = output_path(config.output_dir, transcript)
    if target.exists() and not force:
        print(f"ya analizado: {target} (usa --force para repetir)")
        return "skipped"
    prompt, schema, document, payload, request = _prepare(config, transcript)
    meta = {"video_id": document["video"]["video_id"], "channel": document["video"]["channel"]["slug"],
            "transcript_file": str(transcript), "prompt_version": PROMPT_VERSION, "prompt_sha256": sha256(prompt),
            "schema_sha256": sha256(json.dumps(schema, sort_keys=True)), "provider": config.provider,
            "model_requested": config.model,
            "effort": config.effort, "analyzed_at": payload["analizado_en"]}
    try:
        result = runner(client, request)
    except AnalysisError as err:
        print(f"ERROR {meta['video_id']}: {err}", file=sys.stderr)
        return "error"
    errors = validate(result.analysis, payload, schema)
    meta |= {"model": result.model, "request_id": result.request_id, "fallback_used": result.fallback_used,
             "usage": result.usage, "cost_usd_estimate": estimate_cost(result.model, result.usage),
             "validation": {"ok": not errors, "errors": errors}, "status": "ok" if not errors else "rechazado"}
    if errors:
        target = rejected_path(config.output_dir, transcript)  # el válido anterior, si existe, se conserva
    save(target, meta, result.analysis)
    print(f"{meta['status'].upper()} {meta['video_id']} · {result.model} · ${meta['cost_usd_estimate']} · {target}")
    for err in errors[:10]:
        print(f"   ↳ {err}")
    return meta["status"]


def cmd_run(config, args) -> int:
    client, runner = _client_and_runner(config)
    targets = (pending(config.transcripts_dir, config.output_dir, config.include_shorts)[: args.limit] if args.pending
               else [find_transcript(config.transcripts_dir, args.ref)])
    if not targets:
        print("No hay transcripciones pendientes de análisis.")
        return 0
    statuses = [analyze_one(config, client, runner, t, args.force) for t in targets]
    return 0 if all(s in ("ok", "skipped") for s in statuses) else 1


def cmd_validate(config, path: str) -> int:
    """Revalida un análisis guardado. Si estaba rechazado y ahora pasa (p. ej. tras corregir el validador),
    se promueve a la carpeta de válidos sin volver a llamar al modelo."""
    source = Path(path)
    stored = json.loads(source.read_text(encoding="utf-8"))
    transcript = Path(stored["meta"]["transcript_file"])
    document = json.loads(transcript.read_text(encoding="utf-8"))
    payload = build_payload(document, stored["meta"]["analyzed_at"])
    errors = validate(stored["analysis"], payload, load_schema())
    if errors:
        print("\n".join(errors))
        return 1
    print("válido")
    if stored["meta"].get("status") == "rechazado":
        stored["meta"] |= {"status": "ok", "validation": {"ok": True, "errors": [], "revalidated_at": now_iso()}}
        target = save(output_path(config.output_dir, transcript), stored["meta"], stored["analysis"])
        if source.resolve() != target.resolve():
            source.unlink()
        print(f"promovido a {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cranalysis")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pending")
    p.add_argument("--limit", type=int, default=20)
    d = sub.add_parser("dry-run")
    d.add_argument("ref", help="video_id o ruta al JSON de transcripción")
    r = sub.add_parser("run")
    r.add_argument("ref", nargs="?", help="video_id o ruta al JSON de transcripción")
    r.add_argument("--pending", action="store_true", help="analizar las transcripciones más nuevas sin análisis")
    r.add_argument("--limit", type=int, default=1)
    r.add_argument("--force", action="store_true")
    v = sub.add_parser("validate")
    v.add_argument("path")
    args = parser.parse_args(argv)

    config = load_config()
    if args.command == "pending":
        for t in pending(config.transcripts_dir, config.output_dir, config.include_shorts)[: args.limit]:
            print(t)
        return 0
    if args.command == "dry-run":
        return cmd_dry_run(config, args.ref)
    if args.command == "validate":
        return cmd_validate(config, args.path)
    if not args.pending and not args.ref:
        parser.error("run necesita un video_id/ruta o --pending")
    return cmd_run(config, args)


if __name__ == "__main__":
    sys.exit(main())

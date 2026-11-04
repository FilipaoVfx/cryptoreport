"""Proyección determinista de tesis aceptadas para Urania. Sin inferencia ni red.

    python3 prototypes/movil/theses.py check     # valida metadata/theses.json contra los datos publicados
    python3 prototypes/movil/theses.py accept TESIS VIDEO:AFIRMACION --evidence E3 --excerpt "…" \
        --relation apoyo --dimension momento --justification "…"    # registra una membresía revisada

Una tesis es una proposición contrastable con alcance y horizonte. Un tema, una mención o el tono no son tesis.
Las definiciones y las membresías son editoriales y viven en metadata/theses.json. Este módulo no agrupa
afirmaciones por su cuenta: solo publica las membresías aceptadas cuya evidencia sigue intacta.

Una membresía cuenta solo si se cumplen todas estas condiciones:
- su `thesis_definition_sha256` coincide con la definición vigente;
- los hashes de análisis y transcripción siguen siendo los publicados;
- la afirmación existe y la atribuye al creador del vídeo;
- el extracto es literal en la evidencia citada.
En cualquier otro caso queda pendiente o excluida, visible en el diagnóstico, sin hacer fallar la exportación.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "theses-1.0"
ROOT = Path(__file__).resolve().parent
METADATA = Path(os.environ.get("CR_THESES_FILE", str(ROOT / "metadata" / "theses.json")))
RELATIONS = {"apoyo": "Apoya", "objecion": "Objeta", "matiz": "Matiza"}
DIMENSIONS = {"direccion": "dirección", "momento": "momento", "alcance": "alcance", "mecanismo": "mecanismo",
              "beneficiario": "activo beneficiario", "condicion": "condición"}
SEMANTIC = ("proposition", "topic_id", "markets", "assets", "scope", "horizon", "conditions")
THESIS_REQUIRED = ("id", "version", "definition_sha256", "label", "proposition", "markets", "assets", "scope", "horizon",
                   "conditions", "provenance")
MEMBER_REQUIRED = ("thesis_id", "thesis_definition_sha256", "video_id", "claim_id", "creator_id", "relation", "dimension",
                   "evidence_id", "excerpt", "justification", "status", "accepted_by", "accepted_at", "analysis_sha256",
                   "transcript_sha256")


class MetadataError(ValueError):
    """metadata/theses.json no se puede usar: JSON mal formado o estructura inválida."""


def canonical(obj) -> bytes:
    """Serialización canónica única: claves ordenadas, UTF-8, sin espacios y sin valores no finitos."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def definition_object(thesis: dict) -> dict:
    """Solo los campos semánticos; el rótulo y la procedencia no cambian lo que se afirma."""
    return {
        "proposition": thesis["proposition"],
        "topic_id": thesis.get("topic_id"),
        "markets": sorted(set(thesis.get("markets") or [])),
        "assets": sorted(set(thesis.get("assets") or [])),
        "scope": thesis.get("scope"),
        "horizon": thesis.get("horizon"),
        "conditions": sorted(set(thesis.get("conditions") or [])),
    }


def definition_sha256(thesis: dict) -> str:
    return hashlib.sha256(canonical(definition_object(thesis))).hexdigest()


def load(path: Path = None) -> dict:
    path = Path(path or METADATA)
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": 1, "theses": [], "memberships": []}
    except (OSError, ValueError) as exc:
        raise MetadataError(f"{path.name}: {exc}") from exc
    if not isinstance(meta, dict) or not isinstance(meta.get("theses"), list) or not isinstance(meta.get("memberships"), list):
        raise MetadataError(f"{path.name}: se esperan las listas «theses» y «memberships»")
    return meta


def validate(meta: dict) -> list[str]:
    """Errores de estructura: campos, enumerados, IDs y versiones declaradas. No mira los datos publicados."""
    errors, seen = [], set()
    for t in meta["theses"]:
        missing = [k for k in THESIS_REQUIRED if k not in t]
        if missing:
            errors.append(f"tesis {t.get('id', '?')}: faltan {', '.join(missing)}")
            continue
        if t["id"] in seen:
            errors.append(f"tesis {t['id']}: id repetido")
        seen.add(t["id"])
        if not isinstance(t["version"], int) or t["version"] < 1:
            errors.append(f"tesis {t['id']}: version debe ser un entero >= 1")
        if t["definition_sha256"] != definition_sha256(t):
            errors.append(f"tesis {t['id']}: la definición semántica cambió; incrementa «version» y registra "
                          f"definition_sha256={definition_sha256(t)} (las membresías anteriores quedan pendientes)")
    for i, m in enumerate(meta["memberships"]):
        missing = [k for k in MEMBER_REQUIRED if k not in m]
        if missing:
            errors.append(f"membresía {i}: faltan {', '.join(missing)}")
            continue
        if m["thesis_id"] not in seen:
            errors.append(f"membresía {i}: tesis desconocida {m['thesis_id']}")
        if m["relation"] not in RELATIONS:
            errors.append(f"membresía {i}: relación «{m['relation']}» no es {sorted(RELATIONS)}")
        if m["dimension"] not in DIMENSIONS:
            errors.append(f"membresía {i}: dimensión «{m['dimension']}» no es {sorted(DIMENSIONS)}")
        if m["status"] not in ("aceptada", "rechazada", "retirada"):
            errors.append(f"membresía {i}: estado «{m['status']}» no válido")
        if not str(m["excerpt"]).strip() or not str(m["justification"]).strip():
            errors.append(f"membresía {i}: extracto y justificación son obligatorios")
    return errors


def _evidence(analysis: dict, claim_id: str, evidence_id: str):
    claim = next((c for c in analysis.get("afirmaciones", []) if c["id"] == claim_id), None)
    if not claim or evidence_id not in claim.get("evidencia_ids", []):
        return claim, None
    return claim, next((e for e in analysis.get("evidencias", []) if e["id"] == evidence_id), None)


def member_state(m: dict, defs: dict, videos: dict, claims: dict, analyses: dict) -> tuple[str, str | None]:
    """(estado, motivo). «vigente» es el único estado que suma a contadores, escenarios y relaciones heredadas."""
    if m["status"] != "aceptada":
        return "historial", m["status"]
    thesis = defs.get(m["thesis_id"])
    if not thesis:
        return "error", "tesis_desconocida"
    if m["thesis_definition_sha256"] != thesis["computed_sha256"]:
        return "pendiente", "definicion_cambiada"
    video = videos.get(m["video_id"])
    if not video or not video.get("analysis_sha256") or m["video_id"] not in analyses:
        return "excluida", "sin_analisis_valido"
    if m["analysis_sha256"] != video["analysis_sha256"]:
        return "pendiente", "analisis_reemplazado"
    claim = claims.get(f"{m['video_id']}:{m['claim_id']}")
    if not claim:
        return "error", "afirmacion_inexistente"
    if m["transcript_sha256"] != (claim.get("radar") or {}).get("transcript_hash"):
        return "pendiente", "transcripcion_reemplazada"
    if m["creator_id"] != video["ch"]:
        return "error", "identidad_no_coincide"
    if (claim.get("radar") or {}).get("speaker_role") != "creador":
        return "excluida", "atribucion_no_del_creador"
    _, evidence = _evidence(analyses[m["video_id"]]["analysis"], m["claim_id"], m["evidence_id"])
    if not evidence or m["excerpt"] not in (evidence.get("cita") or ""):
        return "error", "extracto_no_literal"
    return "vigente", None


def project(meta: dict, videos: list[dict], claims: list[dict], analyses: dict, generation: str) -> tuple[dict, dict]:
    """Devuelve (bloque ligero para index.json, {thesis_id: detalle diferido}). Orden estable."""
    defs = {t["id"]: dict(t, computed_sha256=definition_sha256(t)) for t in meta["theses"]}
    by_video = {v["id"]: v for v in videos}
    by_claim = {f"{c['v']}:{c['id']}": c for c in claims}
    members, diagnostics, details = [], [], {tid: [] for tid in defs}
    for m in sorted(meta["memberships"], key=lambda x: (x["thesis_id"], x["video_id"], x["claim_id"], x["evidence_id"])):
        state, reason = member_state(m, defs, by_video, by_claim, analyses)
        if state != "vigente":
            diagnostics.append({"thesis": m["thesis_id"], "v": m["video_id"], "c": m["claim_id"], "state": state, "reason": reason})
            continue
        claim = by_claim[f"{m['video_id']}:{m['claim_id']}"]
        evidence = _evidence(analyses[m["video_id"]]["analysis"], m["claim_id"], m["evidence_id"])[1]
        members.append({"t": m["thesis_id"], "v": m["video_id"], "c": m["claim_id"], "ch": m["creator_id"],
                        "rel": m["relation"], "dim": m["dimension"], "why": m["justification"], "e": m["evidence_id"],
                        "x": m["excerpt"], "at": evidence.get("inicio_s")})
        a = analyses[m["video_id"]]["analysis"]
        raw = next(c for c in a["afirmaciones"] if c["id"] == m["claim_id"])
        market = raw.get("mercado") or {}
        details[m["thesis_id"]].append({
            "v": m["video_id"], "c": m["claim_id"], "quote": evidence.get("cita"), "claim": claim["text"],
            "posture": market.get("postura"), "condition": market.get("condicion"), "invalidation": market.get("invalidacion"),
            "horizon": market.get("horizonte_literal"),
            "scenarios": [{"id": s["id"], "name": s["nombre"], "origin": s["origen"], "mechanism": s["mecanismo"],
                           "horizon": s.get("horizonte"), "invalidation": s.get("invalidacion")}
                          for s in a["escenarios"] if m["claim_id"] in s.get("afirmacion_ids", [])],
            "watch": [{"what": w["que_observar"], "criterion": w["criterio"], "origin": w["origen_criterio"], "term": w.get("plazo")}
                      for w in a["seguimiento"] if m["claim_id"] in w.get("afirmacion_ids", [])],
        })
    items = []
    for tid in sorted(defs):
        t = defs[tid]
        items.append({k: t.get(k) for k in ("id", "version", "label", "proposition", "topic_id", "markets", "assets", "scope",
                                              "horizon", "conditions", "provenance")}
                     | {"definition_sha256": t["computed_sha256"], "detail": f"g/{generation}/t/{tid}.json"})
    block = {
        "version": VERSION, "status": "ok", "items": items, "members": members, "diagnostics": diagnostics,
        "coverage": {"theses": len(items), "accepted": len(members),
                     "pending": sum(d["state"] == "pendiente" for d in diagnostics),
                     "excluded": sum(d["state"] == "excluida" for d in diagnostics),
                     "errors": sum(d["state"] == "error" for d in diagnostics),
                     "classifiedClaims": len({(m["v"], m["c"]) for m in members})},
        "method": "Tesis y membresías editoriales revisadas a mano sobre afirmaciones del creador con cita literal. "
                  "Un tema, una mención o el tono no cuentan como tesis. La clasificación es parcial: las afirmaciones "
                  "no clasificadas siguen accesibles.",
    }
    detail = {tid: {"generation": generation, "id": tid, "members": rows} for tid, rows in details.items()}
    return block, detail


def unavailable(reason: str) -> dict:
    """Bloque publicado cuando la proyección no se puede construir: cobertura desconocida, no cero tesis."""
    return {"version": VERSION, "status": "error", "items": [], "members": [], "diagnostics": [], "coverage": None, "error": reason}


# ---------- línea de órdenes: comprobar y aceptar ----------

def _published():
    sys.path.insert(0, str(ROOT))
    data_dir = Path(os.environ.get("CR_MOBILE_DATA_DIR", str(ROOT / "data")))
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    analyses = {}
    for v in index["videos"]:
        if not v.get("analysis_sha256"):
            continue
        detail = json.loads((data_dir / index["detailBase"] / f"{v['id']}.json").read_text(encoding="utf-8"))
        analyses[v["id"]] = {"analysis": detail["analysis"]}
    return index, analyses


def cmd_check(args) -> int:
    try:
        meta = load(args.file)
    except MetadataError as exc:
        print(f"ERROR {exc}")
        return 1
    errors = validate(meta)
    for e in errors:
        print(f"ERROR {e}")
    index, analyses = _published()
    block, _ = project(meta, index["videos"], index["claims"], analyses, index["generation"])
    print(f"tesis: {block['coverage']['theses']} · membresías vigentes: {block['coverage']['accepted']} · "
          f"pendientes: {block['coverage']['pending']} · excluidas: {block['coverage']['excluded']} · errores: {block['coverage']['errors']}")
    for d in block["diagnostics"]:
        print(f"  {d['state']:<10} {d['thesis']} {d['v']}:{d['c']} · {d['reason']}")
    return 1 if errors or block["coverage"]["errors"] else 0


def cmd_accept(args) -> int:
    meta = load(args.file)
    defs = {t["id"]: t for t in meta["theses"]}
    if args.thesis not in defs:
        print(f"ERROR tesis desconocida {args.thesis}")
        return 1
    video_id, claim_id = args.claim.split(":", 1)
    index, analyses = _published()
    video = next((v for v in index["videos"] if v["id"] == video_id), None)
    claim = next((c for c in index["claims"] if c["v"] == video_id and c["id"] == claim_id), None)
    if not video or not claim or video_id not in analyses:
        print("ERROR la afirmación no está publicada con un análisis válido")
        return 1
    member = {"thesis_id": args.thesis, "thesis_definition_sha256": definition_sha256(defs[args.thesis]),
              "video_id": video_id, "claim_id": claim_id, "creator_id": video["ch"], "relation": args.relation,
              "dimension": args.dimension, "evidence_id": args.evidence, "excerpt": args.excerpt,
              "justification": args.justification, "status": "aceptada", "accepted_by": args.by,
              "accepted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "analysis_sha256": video["analysis_sha256"], "transcript_sha256": claim["radar"]["transcript_hash"]}
    defs_c = {t["id"]: dict(t, computed_sha256=definition_sha256(t)) for t in meta["theses"]}
    state, reason = member_state(member, defs_c, {v["id"]: v for v in index["videos"]},
                                 {f"{c['v']}:{c['id']}": c for c in index["claims"]}, analyses)
    if state != "vigente":
        print(f"ERROR la membresía no sería vigente: {reason}")
        return 1
    key = (args.thesis, video_id, claim_id)
    meta["memberships"] = [m for m in meta["memberships"] if (m["thesis_id"], m["video_id"], m["claim_id"]) != key or m["status"] != "aceptada"]
    meta["memberships"].append(member)
    Path(args.file).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"aceptada {args.thesis} ← {video_id}:{claim_id} ({args.relation}, {args.dimension})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--file", default=str(METADATA))
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    acc = sub.add_parser("accept")
    acc.add_argument("thesis")
    acc.add_argument("claim", help="VIDEO_ID:CLAIM_ID")
    acc.add_argument("--evidence", required=True)
    acc.add_argument("--excerpt", required=True, help="fragmento literal de la cita de esa evidencia")
    acc.add_argument("--relation", required=True, choices=sorted(RELATIONS))
    acc.add_argument("--dimension", required=True, choices=sorted(DIMENSIONS))
    acc.add_argument("--justification", required=True)
    acc.add_argument("--by", default="revisión editorial")
    args = parser.parse_args()
    return cmd_check(args) if args.cmd == "check" else cmd_accept(args)


if __name__ == "__main__":
    sys.exit(main())

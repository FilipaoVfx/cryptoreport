"""Localiza transcripciones y guarda cada análisis con sus metadatos de trazabilidad."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def find_transcript(transcripts_dir: Path, ref: str) -> Path:
    """Acepta una ruta a un JSON o un video_id (busca <canal>/<fecha>_<id>.json)."""
    path = Path(ref)
    if path.suffix == ".json" and path.is_file():
        return path
    matches = sorted(transcripts_dir.glob(f"*/*_{ref}.json"))
    if not matches:
        raise FileNotFoundError(f"no hay transcripción para {ref!r} en {transcripts_dir}")
    return matches[-1]


def output_path(output_dir: Path, transcript: Path) -> Path:
    return output_dir / transcript.parent.name / transcript.name


def pending(transcripts_dir: Path, output_dir: Path, include_shorts: bool = True) -> list[Path]:
    """Transcripciones sin análisis guardado, de la más nueva a la más vieja por fecha de publicación."""
    result = []
    for transcript in transcripts_dir.glob("*/*.json"):
        if output_path(output_dir, transcript).exists():
            continue
        video = json.loads(transcript.read_text(encoding="utf-8"))["video"]
        if include_shorts or not video.get("is_short"):
            result.append((video.get("published_at") or "", transcript))
    return [t for _, t in sorted(result, reverse=True)]


def save(path: Path, meta: dict, analysis: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"meta": meta, "analysis": analysis}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
    return path

"""Configuración del análisis de narrativas: entorno y `.env` opcional junto al servicio."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent.parent
PROMPT_PATH = SERVICE_DIR / "prompts" / "narrative-analysis.system.md"
SCHEMA_PATH = SERVICE_DIR / "schema" / "narrative-analysis.schema.json"
PROMPT_VERSION = "1.0.0"
EFFORTS = ("low", "medium", "high", "xhigh", "max")


def load_dotenv(path: Path) -> None:
    """KEY=VALUE sin pisar variables ya definidas (systemd o shell tienen prioridad)."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Config:
    model: str
    effort: str
    max_tokens: int
    fallbacks: bool
    transcripts_dir: Path
    output_dir: Path
    include_shorts: bool


def load_config() -> Config:
    load_dotenv(SERVICE_DIR / ".env")  # ANTHROPIC_API_KEY lo lee el SDK directamente del entorno
    effort = os.environ.get("CRA_EFFORT", "high")
    if effort not in EFFORTS:
        raise ValueError(f"CRA_EFFORT debe ser uno de {EFFORTS}, no {effort!r}")
    data = Path(os.environ.get("CRA_DATA_DIR", "/var/lib/cryptoreport-transcripts"))
    return Config(
        model=os.environ.get("CRA_MODEL", "claude-opus-5-5"),
        effort=effort,
        # Con streaming no hay riesgo de timeout HTTP; el contrato es grande y el razonamiento cuenta como salida.
        max_tokens=int(os.environ.get("CRA_MAX_TOKENS", "64000")),
        fallbacks=os.environ.get("CRA_FALLBACKS", "true").lower() in {"1", "true", "yes", "si", "sí"},
        transcripts_dir=Path(os.environ.get("CRA_TRANSCRIPTS_DIR", data / "transcripts")),
        output_dir=Path(os.environ.get("CRA_OUTPUT_DIR", data / "analysis")),
        include_shorts=os.environ.get("CRA_INCLUDE_SHORTS", "true").lower() in {"1", "true", "yes", "si", "sí"},
    )

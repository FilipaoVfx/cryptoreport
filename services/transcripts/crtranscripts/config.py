"""Configuración del servicio a partir del entorno y de un `.env` opcional junto al servicio."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = Path("/var/lib/cryptoreport-transcripts")


def load_dotenv(path: Path) -> None:
    """Carga KEY=VALUE sin pisar variables ya definidas (systemd o shell tienen prioridad)."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Channel:
    slug: str
    name: str
    channel_id: str


@dataclass(frozen=True)
class Config:
    data_dir: Path
    channels: tuple[Channel, ...]
    providers: tuple[str, ...]
    language: str
    lookback_hours: float
    give_up_hours: float
    max_attempts: int
    max_videos_per_run: int
    include_shorts: bool
    scraper_tech_key: str
    ytdlp_bin: str
    ytdlp_proxy: str
    ytdlp_cookies: str
    telegram_token: str
    telegram_chat_id: str
    notify_success: bool
    scrapertech_monthly_quota: int

    @property
    def db_path(self) -> Path:
        return self.data_dir / "state.sqlite"

    @property
    def transcripts_dir(self) -> Path:
        return self.data_dir / "transcripts"


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def load_config() -> Config:
    load_dotenv(SERVICE_DIR / ".env")
    channels_file = Path(os.environ.get("CR_CHANNELS_FILE", SERVICE_DIR / "channels.json"))
    channels = tuple(Channel(**item) for item in json.loads(channels_file.read_text(encoding="utf-8")))
    # systemd define STATE_DIRECTORY con StateDirectory=; así las ejecuciones manuales y las del timer comparten datos.
    data_dir = Path(os.environ.get("CR_DATA_DIR") or os.environ.get("STATE_DIRECTORY") or DEFAULT_DATA_DIR)
    providers = tuple(p.strip() for p in os.environ.get("CR_PROVIDERS", "scrapertech,ytdlp").split(",") if p.strip())
    return Config(
        data_dir=data_dir,
        channels=channels,
        providers=providers,
        language=os.environ.get("CR_LANGUAGE", "es"),
        lookback_hours=float(os.environ.get("CR_LOOKBACK_HOURS", "72")),
        give_up_hours=float(os.environ.get("CR_GIVE_UP_HOURS", "72")),
        max_attempts=int(os.environ.get("CR_MAX_ATTEMPTS", "8")),
        max_videos_per_run=int(os.environ.get("CR_MAX_VIDEOS_PER_RUN", "20")),
        include_shorts=_flag("CR_INCLUDE_SHORTS", True),
        scraper_tech_key=os.environ.get("SCRAPER_TECH_KEY", ""),
        ytdlp_bin=os.environ.get("CR_YTDLP_BIN", str(SERVICE_DIR / ".venv" / "bin" / "yt-dlp")),
        ytdlp_proxy=os.environ.get("CR_YTDLP_PROXY", ""),
        ytdlp_cookies=os.environ.get("CR_YTDLP_COOKIES", ""),
        telegram_token=os.environ.get("CR_TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("CR_TELEGRAM_CHAT_ID", ""),
        notify_success=_flag("CR_NOTIFY_SUCCESS", True),
        scrapertech_monthly_quota=int(os.environ.get("CR_SCRAPERTECH_MONTHLY_QUOTA", "1000")),
    )

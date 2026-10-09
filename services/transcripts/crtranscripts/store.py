"""Estado en SQLite y transcripciones en disco (JSON completo + Markdown legible con enlaces por minuto)."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id          TEXT PRIMARY KEY,
    channel_slug      TEXT NOT NULL,
    title             TEXT NOT NULL,
    published_at      TEXT NOT NULL,
    first_seen_at     TEXT NOT NULL,
    is_short          INTEGER,
    status            TEXT NOT NULL DEFAULT 'queued',
    attempts          INTEGER NOT NULL DEFAULT 0,
    next_attempt_at   TEXT,
    last_error        TEXT,
    provider          TEXT,
    language          TEXT,
    segment_count     INTEGER,
    duration_s        REAL,
    last_caption_end_s REAL,
    coverage          REAL,
    transcript_path   TEXT,
    fetched_at        TEXT,
    notified_status   TEXT,
    supadata_job      TEXT,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS videos_due ON videos(status, next_attempt_at);
CREATE TABLE IF NOT EXISTS attempts (
    id         INTEGER PRIMARY KEY,
    video_id   TEXT NOT NULL,
    provider   TEXT NOT NULL,
    outcome    TEXT NOT NULL,
    detail     TEXT,
    requests   INTEGER NOT NULL DEFAULT 0,
    elapsed_s  REAL,
    at         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

# Estados de un video: queued → ok | pending (reintenta con espera creciente) → no_captions | unavailable | failed
RETRYABLE = ("queued", "pending", "error")


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


class Store:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(videos)")}
        if "supadata_job" not in columns:  # añadida con Supadata (2026-10-09)
            self.db.execute("ALTER TABLE videos ADD COLUMN supadata_job TEXT")
            self.db.commit()

    def close(self) -> None:
        self.db.close()

    def upsert_seen(self, video_id: str, channel_slug: str, title: str, published_at: datetime,
                    is_short: bool | None) -> bool:
        """Registra un video del RSS. Devuelve True si es nuevo. El título se actualiza (los creadores lo cambian)."""
        stamp = iso(now_utc())
        cur = self.db.execute(
            "INSERT INTO videos (video_id, channel_slug, title, published_at, first_seen_at, is_short, next_attempt_at,"
            " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(video_id) DO NOTHING",
            (video_id, channel_slug, title, iso(published_at), stamp, None if is_short is None else int(is_short),
             stamp, stamp))
        if cur.rowcount == 0:
            self.db.execute("UPDATE videos SET title = ? WHERE video_id = ? AND title != ?", (title, video_id, title))
        self.db.commit()
        return cur.rowcount == 1

    def known(self, video_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM videos WHERE video_id = ?", (video_id,)).fetchone() is not None

    def get(self, video_id: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()

    def due(self, limit: int) -> list[sqlite3.Row]:
        marks = ",".join("?" * len(RETRYABLE))
        return self.db.execute(
            f"SELECT * FROM videos WHERE status IN ({marks}) AND (next_attempt_at IS NULL OR next_attempt_at <= ?)"
            " ORDER BY published_at DESC LIMIT ?", (*RETRYABLE, iso(now_utc()), limit)).fetchall()

    def log_attempt(self, video_id: str, provider: str, outcome: str, detail: str, requests: int,
                    elapsed_s: float) -> None:
        self.db.execute("INSERT INTO attempts (video_id, provider, outcome, detail, requests, elapsed_s, at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (video_id, provider, outcome, detail, requests, elapsed_s, iso(now_utc())))
        self.db.commit()

    def update(self, video_id: str, **fields) -> None:
        fields["updated_at"] = iso(now_utc())
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(f"UPDATE videos SET {cols} WHERE video_id = ?", (*fields.values(), video_id))
        self.db.commit()

    def requests_since(self, since: datetime, provider: str) -> int:
        """Solicitudes (Scraper.Tech) o créditos (Supadata, incluida la generación) registrados desde `since`."""
        row = self.db.execute("SELECT COALESCE(SUM(requests), 0) FROM attempts WHERE (provider = ? OR provider LIKE ?)"
                              " AND at >= ?", (provider, f"{provider}-%", iso(since))).fetchone()
        return int(row[0])

    def recent(self, limit: int = 30) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM videos ORDER BY published_at DESC LIMIT ?", (limit,)).fetchall()

    def kv_get(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def kv_set(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (key, value))
        self.db.commit()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def fmt_ts(seconds: float) -> str:
    total = int(seconds)
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def group_blocks(segments: list[dict], target_s: float = 30, max_s: float = 45) -> list[dict]:
    """Agrupa segmentos en bloques legibles de ~30 s, cortando en fin de frase cuando se puede.
    Es una vista derivada: el JSON conserva siempre los segmentos originales para citar con precisión."""
    blocks, current = [], []
    for seg in segments:
        current.append(seg)
        span = seg["start"] - current[0]["start"]
        ends_sentence = seg["text"].rstrip().endswith((".", "?", "!", "…"))
        if (span >= target_s and ends_sentence) or span >= max_s:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return [{"start": b[0]["start"], "text": " ".join(s["text"] for s in b)} for b in blocks]


def write_transcript(transcripts_dir: Path, *, channel, video_id: str, title: str, published_at: str,
                     is_short: bool | None, duration_s: float | None, provider: str, language: str,
                     track_kind: str, segments: list[dict], fetched_at: str) -> Path:
    last_end = max(s["start"] + s["dur"] for s in segments)
    coverage = round(min(last_end / duration_s, 1.0), 3) if duration_s else None
    base = transcripts_dir / channel.slug / f"{published_at[:10]}_{video_id}"
    url = f"https://www.youtube.com/watch?v={video_id}"
    document = {
        "schema_version": 1,
        "video": {"video_id": video_id, "url": url, "title": title, "published_at": published_at,
                  "is_short": is_short, "duration_s": duration_s,
                  "channel": {"slug": channel.slug, "name": channel.name, "channel_id": channel.channel_id}},
        "transcript": {"provider": provider, "language": language, "track_kind": track_kind,
                       "fetched_at": fetched_at, "segment_count": len(segments),
                       "first_start_s": segments[0]["start"], "last_end_s": round(last_end, 3),
                       "coverage": coverage, "segments": segments},
    }
    _atomic_write(base.with_suffix(".json"), json.dumps(document, ensure_ascii=False, indent=1) + "\n")

    lines = [f"# {title}", "",
             f"- Canal: {channel.name}",
             f"- Video: {url}",
             f"- Publicado: {published_at}",
             f"- Duración: {fmt_ts(duration_s) if duration_s else 'desconocida'}"
             f"{' · short' if is_short else ''}",
             f"- Transcripción: {provider}, idioma `{language}`, {len(segments)} segmentos, "
             f"hasta {fmt_ts(last_end)}" + (f" ({coverage:.0%} del video)" if coverage is not None else ""),
             f"- Obtenida: {fetched_at}", ""]
    for block in group_blocks(segments):
        start = int(block["start"])
        lines.append(f"[{fmt_ts(start)}](https://youtu.be/{video_id}?t={start}) {block['text']}")
        lines.append("")
    _atomic_write(base.with_suffix(".md"), "\n".join(lines))
    return base.with_suffix(".json")

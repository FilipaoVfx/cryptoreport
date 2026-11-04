"""Refresh approved public identity sources, at most weekly, without API keys.

Run directly to refresh now. build_data calls refresh_if_due; failures preserve
cached identities and initials remain usable. Source URLs are never taken from
video content. Images are cached locally with content-addressed names.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "metadata" / "identities.json"
MEDIA = ROOT / "media" / "identities"
MAX_BYTES = 1_500_000
ALLOWED = {"raw.githubusercontent.com", "www.youtube.com", "yt3.googleusercontent.com", "yt3.ggpht.com"}
CRYPTO = "btc eth xrp sol bnb dot atom link ada avax pol sui apt rune".split()
COMPANIES = {"nvda": "nvidia", "googl": "google", "aapl": "apple", "amzn": "amazon", "msft": "microsoft", "tsla": "tesla", "tsm": "tsmc"}
CHAINS = {"sui": "sui", "apt": "aptos", "pol": "polygon", "hype": "hyperliquid", "sonic": "sonic"}


class ApprovedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        approve(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def approve(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Unapproved identity origin")


def fetch(url, html=False):
    approve(url)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 CryptoReport identity cache"})
    with urllib.request.build_opener(ApprovedRedirect()).open(req, timeout=5) as response:
        approve(response.url)
        content_type = response.headers.get_content_type()
        body = response.read((3_000_000 if html else MAX_BYTES) + 1)
    if len(body) > (3_000_000 if html else MAX_BYTES):
        raise ValueError("Identity response too large")
    if html:
        if content_type != "text/html":
            raise ValueError("Expected channel HTML")
    elif content_type not in ("image/png", "image/jpeg", "image/webp", "image/svg+xml", "text/plain"):
        raise ValueError("Unexpected image type")
    return body


def avatar_url(page, channel_id):
    match = re.search(r"(?:var\s+)?ytInitialData\s*=\s*", page)
    if not match:
        raise ValueError("No public channel metadata")
    data, _ = json.JSONDecoder().raw_decode(page[match.end():])
    channel = data.get("metadata", {}).get("channelMetadataRenderer", {})
    if channel.get("externalId") != channel_id:
        raise ValueError("Channel identity mismatch")
    thumbs = channel.get("avatar", {}).get("thumbnails", [])
    if not thumbs:
        raise ValueError("No channel avatar")
    original = min(thumbs, key=lambda t: t.get("width", 9999))["url"]
    # Use an exact returned thumbnail URL of this avatar, not the channel banner.
    base = original.split("=")[0]
    candidates = []

    def visit(node):
        if isinstance(node, dict):
            url = node.get("url")
            if isinstance(url, str) and url.split("=")[0] == base and 72 <= node.get("width", 0) <= 160:
                candidates.append(node)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(data.get("header", {}))
    return min(candidates, key=lambda t: abs(t["width"] - 120))["url"] if candidates else original


def cache_image(kind, key, url, source):
    body = fetch(url)
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        suffix = ".png"
    elif body.startswith(b"\xff\xd8\xff"):
        suffix = ".jpg"
    elif body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        suffix = ".webp"
    elif b"<svg" in body[:500] and urlparse(url).hostname == "raw.githubusercontent.com":
        # Only approved static icon repositories; reject active SVG payloads.
        if re.search(rb"<script|on\w+\s*=|(?:href|src)\s*=|<!ENTITY|<foreignObject", body, re.I):
            raise ValueError("Active SVG")
        suffix = ".svg"
    else:
        raise ValueError("Not a supported image")
    digest = hashlib.sha256(body).hexdigest()[:16]
    MEDIA.mkdir(parents=True, exist_ok=True)
    name = f"{kind}-{key}-{digest}{suffix}"
    target = MEDIA / name
    if not target.exists():
        temp = MEDIA / (name + ".tmp")
        temp.write_bytes(body)
        temp.replace(target)
    return {"path": f"../media/identities/{name}", "source_url": url, "source": source,
            "verified_at": datetime.now(timezone.utc).isoformat()}


def refresh_if_due(force=False):
    try:
        catalog = json.loads(CATALOG.read_text())
    except (OSError, ValueError):
        catalog = {"assets": {}, "creators": {}}
    stamp = catalog.get("checked_at")
    if not force and stamp and (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds() < 7 * 86400:
        return catalog
    channels = json.loads((ROOT.parents[1] / "services/transcripts/channels.json").read_text())
    jobs = [("assets", key, f"https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/{key}.png", "cryptocurrency-icons · CC0") for key in CRYPTO]
    jobs += [("assets", key, f"https://raw.githubusercontent.com/simple-icons/simple-icons/11.15.0/icons/{name}.svg", "Simple Icons · CC0; marcas de sus titulares") for key, name in COMPANIES.items()]
    jobs += [("assets", key, f"https://raw.githubusercontent.com/trustwallet/assets/master/blockchains/{chain}/info/logo.png", "Trust Wallet Assets · MIT; marcas de sus titulares") for key, chain in CHAINS.items()]
    jobs += [("creators", c["slug"], c["channel_id"], "YouTube · avatar público del canal") for c in channels]

    def run(job):
        kind, key, url, source = job
        try:
            if kind == "creators":
                page = fetch(f"https://www.youtube.com/channel/{url}/about", html=True).decode()
                url = avatar_url(page, url)
            return kind, key, cache_image(kind, key, url, source)
        except (OSError, ValueError, KeyError, TypeError):
            return kind, key, None

    with ThreadPoolExecutor(max_workers=4) as pool:
        for kind, key, value in pool.map(run, jobs):
            if value:
                catalog[kind][key] = value
    catalog["checked_at"] = datetime.now(timezone.utc).isoformat()
    catalog["attribution"] = {
        "crypto": "https://github.com/spothq/cryptocurrency-icons/blob/master/LICENSE.md",
        "companies": "https://github.com/simple-icons/simple-icons/blob/develop/LICENSE.md",
        "chains": "https://github.com/trustwallet/assets/blob/master/LICENSE",
        "creators": "Avatares públicos asociados al ID del canal; identidad y derechos de sus titulares.",
    }
    try:
        CATALOG.parent.mkdir(parents=True, exist_ok=True)
        temporary = CATALOG.with_suffix(".tmp")
        temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(CATALOG)
        active = {Path(image["path"]).name for kind in ("assets", "creators") for image in catalog[kind].values()}
        for old in MEDIA.glob("*"):
            if old.is_file() and old.name not in active and re.fullmatch(r"(?:assets|creators)-[a-z0-9]+-[a-f0-9]{16}\.(png|jpg|webp|svg)", old.name) and time.time() - old.stat().st_mtime > 14 * 86400:
                old.unlink()
    except OSError:
        pass  # Cosmetic metadata must not block publishing valid analysis.
    return catalog


if __name__ == "__main__":
    catalog = refresh_if_due(force=True)
    print(f"Identidades: {len(catalog['assets'])} activos, {len(catalog['creators'])} creadores")

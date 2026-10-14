"""Genera los datos de los prototipos móviles a partir de las transcripciones y los análisis reales.

    python3 prototypes/movil/build_data.py            # escribe prototypes/movil/data/
    python3 prototypes/movil/build_data.py --check    # además muestra el contexto de cada mención dudosa

No llama a ningún modelo: reutiliza los análisis válidos ya guardados y cuenta menciones literales en las
transcripciones. Lo que sale de aquí es una foto fija; la carpeta data/ no se versiona (el repo es público).
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tono  # noqa: E402  (reglas de tono alcista/bajista, sin modelos)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/transcripts"))
from crtranscripts.quality import assess, analysis_matches

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("CR_DATA_DIR", "/var/lib/cryptoreport-transcripts"))
OUT = Path(os.environ.get("CR_MOBILE_DATA_DIR", str(ROOT / "data")))

# Léxico de menciones. Cada patrón se probó contra el archivo real: "link" casi siempre es un enlace
# ("el link que les dejo abajo"), por eso Chainlink exige mayúscula y ningún artículo delante; "hype" en este
# archivo es el token de Hyperliquid, pero queda marcado como ambiguo; "Estereum" es un error del subtitulado.
I, CS = re.I, 0
TOPICS = [
    # id, nombre, símbolo, sección, [(patrón, flags)], nota de ambigüedad
    ("btc", "Bitcoin", "BTC", "bitcoin", [(r"bitcoin|btc", I)], None),
    ("eth", "Ethereum", "ETH", "altcoins", [(r"ethereum|estereum|ether", I)], None),
    ("hype", "Hyperliquid", "HYPE", "altcoins", [(r"hyperliquid|hype", I)], "«hype» también es una palabra coloquial"),
    ("xrp", "XRP", "XRP", "altcoins", [(r"xrp|ripple", I)], None),
    ("sol", "Solana", "SOL", "altcoins", [(r"solana", I)], None),
    ("bnb", "BNB", "BNB", "altcoins", [(r"bnb", I)], None),
    ("dot", "Polkadot", "DOT", "altcoins", [(r"polkadot|polcadot", I)], None),
    ("atom", "Cosmos", "ATOM", "altcoins", [(r"cosmos|atom", I)], None),
    ("link", "Chainlink", "LINK", "altcoins", [(r"chainlink", I), (r"(?<!el )(?<!un )(?<!del )(?<!al )(?<!este )(?<!ese )(?<!mi )(?<!tu )(?<!su )Link", CS)], "«link» suele ser un enlace: solo cuenta «Link» con mayúscula"),
    ("ada", "Cardano", "ADA", "altcoins", [(r"cardano", I)], None),
    ("avax", "Avalanche", "AVAX", "altcoins", [(r"avalanche|avax", I)], None),
    ("pol", "Polygon", "POL", "altcoins", [(r"polygon|matic", I)], None),
    ("sui", "Sui", "SUI", "altcoins", [(r"Sui", CS)], None),
    ("apt", "Aptos", "APT", "altcoins", [(r"aptos", I)], None),
    ("sonic", "Sonic", "S", "altcoins", [(r"Sonic", CS)], None),
    ("rune", "THORChain", "RUNE", "altcoins", [(r"thorchain", I), (r"Rune", CS)], None),
    ("aero", "Aerodrome", "AERO", "altcoins", [(r"aerodrome", I)], None),
    ("meme", "Memecoins", None, "altcoins", [(r"meme ?coins?", I)], "categoría, no un activo concreto"),
    ("liquidez", "Liquidez", None, "macro", [(r"liquidez", I)], None),
    ("bonos", "Bonos y rendimientos", None, "macro", [(r"bonos?|rendimientos? de (?:los )?bonos", I)], None),
    ("oro", "Oro", None, "macro", [(r"oro", I)], None),
    ("dolar", "Dólar", "DXY", "macro", [(r"dólar|dolar|dxy", I)], None),
    ("tipos", "Tipos de interés y Fed", None, "macro", [(r"tipos de interés|reunión de tipos|(?:subida|bajada|recorte) de tipos|tasas de interés|reserva federal|powell|fed", I)], None),
    ("inflacion", "Inflación", None, "macro", [(r"inflación|inflacion|ipc|cpi", I)], None),
    ("move", "Volatilidad de bonos (MOVE)", "MOVE", "macro", [(r"MOVE|Move(?= no| contin| est)|el move", CS)], None),
    ("petroleo", "Petróleo", None, "macro", [(r"petróleo|petroleo", I)], None),
    ("politica", "Política y geopolítica", None, "macro", [(r"elecciones|midterm|aranceles?|trump|guerra", I)], None),
    ("sp500", "S&P 500", "SPX", "bolsa", [(r"s&p(?: ?500)?|sp ?500", I)], None),
    ("nasdaq", "Nasdaq", "NDX", "bolsa", [(r"nasdaq", I)], None),
    ("nvda", "Nvidia", "NVDA", "bolsa", [(r"nvidia|acciones de envidia", I)], "«envidia» es un error del subtitulado"),
    ("tsm", "TSMC", "TSM", "bolsa", [(r"tsmc|tsm", I)], None),
    ("googl", "Google", "GOOGL", "bolsa", [(r"google|alphabet", I)], None),
    ("aapl", "Apple", "AAPL", "bolsa", [(r"apple", I)], None),
    ("amzn", "Amazon", "AMZN", "bolsa", [(r"amazon", I)], None),
    ("msft", "Microsoft", "MSFT", "bolsa", [(r"microsoft", I)], None),
    ("tsla", "Tesla", "TSLA", "bolsa", [(r"tesla", I)], None),
    ("mstr", "MicroStrategy", "MSTR", "bolsa", [(r"microstrategy", I)], None),
    ("lcid", "Lucid", "LCID", "bolsa", [(r"lucid", I)], None),
    ("etf", "ETFs y ETCs", None, "bolsa", [(r"etfs?|etcs?", I)], None),
]
SECTIONS = {"bitcoin": "Bitcoin", "altcoins": "Altcoins", "macro": "Macro", "bolsa": "Bolsa"}
GENERIC_BOLSA = re.compile(r"(?<!\w)(?:acciones|bolsa|índices?|dividendos)(?!\w)", re.I)


def atomic_json(path, obj):
    """Publicar cada JSON completo; el índice se reemplaza después de los detalles."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".build-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(obj, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o644)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def compile_topics():
    compiled = []
    for tid, name, sym, section, pats, note in TOPICS:
        regs = [re.compile(r"(?<!\w)(?:" + p + r")(?!\w)", flags) for p, flags in pats]
        compiled.append({"id": tid, "name": name, "sym": sym, "section": section, "regs": regs, "note": note})
    return compiled


def find_topics(text: str, topics) -> list[str]:
    return [t["id"] for t in topics if any(r.search(text or "") for r in t["regs"])]


# Dirección de una postura extraída por el análisis. Solo se usa para emparejar coincidencias y cambios; la
# interfaz muestra siempre la postura literal del análisis, nunca esta etiqueta sola.
BEAR = re.compile(r"bajista|short|caída|corrección|correcci|vender|venta|evitar|negativ|desfavorable|retroceso|ruptura del soporte", re.I)
BULL = re.compile(r"alcista|long|largo|subida|comprar|compra|favorable|rebote|recuperaci|positiv", re.I)


def direction(text: str) -> str:
    # «Transición de shorts a longs»: cuenta la posición final, no las dos palabras.
    final = re.search(r"\ba (longs?|largos?|shorts?|cortos?)\b", text or "", re.I)
    if final:
        return "alcista" if final.group(1).lower().startswith(("long", "larg")) else "bajista"
    bear, bull = bool(BEAR.search(text or "")), bool(BULL.search(text or ""))
    if bear and bull:
        return "mixta"
    return "bajista" if bear else "alcista" if bull else "descriptiva"


def horizon(text: str) -> str:
    t = (text or "").lower()
    if re.search(r"hoy|ayer|horas|corto|días|dias|miércoles|semana|dentro de poquito|viernes|mañana", t):
        return "corto"
    if re.search(r"medio|noviembre|octubre|diciembre|mes", t):
        return "medio"
    if re.search(r"largo|años|año", t):
        return "largo"
    return "sin plazo"


def iso(dt: str | None) -> str | None:
    return dt


def load_transcripts():
    docs = {}
    for f in sorted((DATA_DIR / "transcripts").glob("*/*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if assess(d)["valid"]:
                docs[d["video"]["video_id"]] = d
        except (OSError, ValueError, KeyError):
            continue
    return docs


def load_analyses():
    found = {}
    for f in sorted((DATA_DIR / "analysis").glob("*/*.json")):
        if f.parent.name.startswith("_"):
            continue
        doc = json.loads(f.read_text(encoding="utf-8"))
        meta = doc.get("meta") or {}
        if meta.get("status") == "ok" and (meta.get("validation") or {}).get("ok"):
            transcript = DATA_DIR / "transcripts" / f.parent.name / f.name
            try:
                if analysis_matches(doc, transcript.read_bytes()):
                    found[meta["video_id"]] = doc
            except OSError:
                continue
    return found


def claim_record(vid: str, a: dict, c: dict, topics) -> dict:
    evs = {e["id"]: e for e in a["evidencias"]}
    m = c.get("mercado") or {}
    ev = [evs[e] for e in c["evidencia_ids"] if e in evs]
    timed = [e for e in ev if e.get("inicio_s") is not None]
    first = timed[0] if timed else (ev[0] if ev else None)
    asset_text = " ".join(filter(None, [m.get("activo_normalizado"), m.get("activo_literal")]))
    assets = find_topics(asset_text, topics) or find_topics(c["enunciado"] + " " + (m.get("postura") or ""), topics)
    postura = m.get("postura") or ""
    return {
        "v": vid, "id": c["id"], "text": c["enunciado"], "tipo": c["tipo"], "verif": c["estado_verificacion"],
        "conv": c["conviccion_creador"], "conf": c["confianza_extraccion"], "emisor": c["emisor"],
        "t": first.get("inicio_s") if first else None,
        "quote": first.get("cita") if first else None, "origen": first.get("origen") if first else None,
        "assets": assets, "postura": postura or None, "plazo": m.get("horizonte_literal"),
        "dir": direction(postura) if postura else None,
        "hz": horizon(" ".join(filter(None, [m.get("horizonte_literal"), postura]))),
        "own": bool(m.get("operacion_propia_declarada")),
        **claim_tone(c, postura, first),
    }


def claim_tone(c: dict, postura: str, first: dict | None) -> dict:
    """Tono de una afirmación: la postura extraída manda; si no hay, el enunciado. La cita aparte."""
    base = tono.describe(f"{postura}. {c['enunciado']}" if postura else c["enunciado"])
    quote = tono.describe(first.get("cita") or "") if first and first.get("cita") else {"pol": "neutra", "str": 0, "why": []}
    insinua = c["tipo"] == "insinuacion" or any("contrario" in w for w in base["why"])
    return {"pol": base["pol"], "polStr": base["str"], "polWhy": base["why"][:4], "qPol": quote["pol"], "insinua": insinua}


def analysis_tone(a: dict) -> dict:
    """Tono de cada pieza del análisis, para colorear resumen, cadena y escenarios."""
    d = lambda text: tono.describe(text or "")["pol"]
    r = a["resumen"]
    return {
        "resumen": {k: d(r.get(k)) for k in ("tesis_principal", "mensaje_explicito", "narrativa_sugerida", "respaldo_demostrable", "conclusion_provisional")},
        "cadena": [d(f"{ch['premisa']} {ch['conclusion']}") for ch in a["cadena_narrativa"]],
        "escenarios": [d(f"{e['nombre']}. {e['mecanismo']}") for e in a["escenarios"]],
    }


def mentions(doc: dict, topics, check: bool):
    """Menciones literales por tema: ocurrencias y hasta 3 fragmentos con su tiempo."""
    segs = doc["transcript"]["segments"]
    out = {}
    for t in topics:
        count, frags = 0, []
        sent = {"alcista": 0, "bajista": 0, "mixta": 0, "neutra": 0}
        for i, seg in enumerate(segs):
            hits = sum(len(r.findall(seg["text"])) for r in t["regs"])
            if not hits:
                continue
            count += hits
            context = " ".join(s["text"] for s in segs[max(0, i - 1): i + 2])
            tone = tono.describe(context)
            sent[tone["pol"]] += hits
            if len(frags) < 3 and (not frags or seg["start"] - frags[-1]["t"] > 20):
                frags.append({"t": round(seg["start"], 2), "text": context, "pol": tone["pol"], "why": tone["why"][:3]})
        if count:
            out[t["id"]] = {"n": count, "frags": frags, "sent": sent}
            if check and t["note"]:
                for fr in frags:
                    print(f"  [{t['id']}] {doc['video']['video_id']} {fr['t']:>7.1f}s  {fr['text'][:120]}")
    return out


THEMES = [
    {
        "id": "btc-corto", "title": "¿Corrige Bitcoin antes de volver a subir?",
        "short": "Bitcoin a corto plazo",
        "about": "Qué esperan los creadores para Bitcoin en los próximos días: niveles, cortos y largos declarados.",
        "claims": lambda c: "btc" in c["assets"] and c["hz"] == "corto" and c["tipo"] in ("prediccion", "hipotesis", "opinion", "hecho_verificable") and (c["dir"] in ("alcista", "bajista", "mixta") or c["own"]),
        "words": re.compile(r"bitcoin[^.]{0,80}(?:corrección|caída|bajar|subida|rebote|soporte|liquidac)", re.I),
        "titles": re.compile(r"bitcoin", re.I),
    },
    {
        "id": "fin-octubre", "title": "¿Qué pasa a partir del 28 de octubre?",
        "short": "La fecha del 28 de octubre",
        "about": "Fechas que se repiten como punto de giro: reunión de tipos, elecciones y el arranque de noviembre.",
        "claims": lambda c: bool(re.search(r"28|noviembre|finales de octubre", " ".join(filter(None, [c["text"], c["plazo"] or ""])))),
        "words": re.compile(r"(?:28 de octubre|el día 28|el 28|4 de noviembre|noviembre)", re.I),
        "titles": None,
    },
    {
        "id": "liquidaciones", "title": "¿Cuánto mandan las liquidaciones sobre el precio?",
        "short": "Liquidaciones",
        "about": "La idea de que el precio va a buscar zonas de liquidaciones antes de moverse.",
        "claims": lambda c: bool(re.search(r"liquida", c["text"] + " " + (c["postura"] or ""), re.I)),
        "words": re.compile(r"liquidaci", re.I),
        "titles": re.compile(r"liquidando", re.I),
    },
    {
        "id": "macro-alivio", "title": "¿Llega el alivio del dólar y los bonos?",
        "short": "Dólar, bonos y tipos",
        "about": "Cómo se conectan dólar, rendimientos, volatilidad de bonos y tipos con Bitcoin y la bolsa.",
        "claims": lambda c: bool(set(c["assets"]) & {"dolar", "bonos", "move", "tipos", "liquidez", "inflacion"}) or bool(re.search(r"dólar|bonos|rendimiento|MOVE|tipos|liquidez", c["text"])),
        "words": re.compile(r"(?:dólar|bonos?|rendimientos?|MOVE|tipos de interés|reunión de tipos)", re.I),
        "titles": re.compile(r"bonos|dato|crisis", re.I),
    },
    {
        "id": "altcoins", "title": "¿Hay sitio para las altcoins ahora mismo?",
        "short": "Altcoins",
        "about": "Qué altcoins aparecen, con qué intención y quién las menciona.",
        "claims": lambda c: any(a in ALT_IDS for a in c["assets"]) or bool(re.search(r"altcoin|aptos|atom|polkadot|hype", c["text"] + " " + (c["postura"] or ""), re.I)),
        "words": re.compile(r"altcoins?|meme ?coins?|ethereum|solana|xrp|hyperliquid|polcadot|polkadot|cardano|aptos", re.I),
        "titles": re.compile(r"altcoins|meme coins|cripto", re.I),
    },
    {
        "id": "bolsa", "title": "¿Marca la bolsa el camino a Bitcoin?",
        "short": "Bolsa y S&P 500",
        "about": "El S&P 500, Nvidia y las acciones como termómetro o como alternativa a las criptomonedas.",
        "claims": lambda c: any(a in BOLSA_IDS for a in c["assets"]) or bool(re.search(r"acciones|bolsa|S&P|ETF", c["text"] + " " + (c["postura"] or ""))),
        "words": re.compile(r"s&p ?500|sp ?500|nasdaq|nvidia|tsmc?\b|broadcom", re.I),
        "titles": re.compile(r"s&p|sp500|nvidia", re.I),
    },
]
ALT_IDS = {t[0] for t in TOPICS if t[3] == "altcoins"}
# Un «activo» se puede comprar o vender; liquidez, tipos o inflación son temas macro, no activos.
ASSET_LIKE = {t[0] for t in TOPICS if t[3] in ("bitcoin", "altcoins", "bolsa") and t[0] != "meme"} | {"oro", "dolar", "petroleo"}
BOLSA_IDS = {t[0] for t in TOPICS if t[3] == "bolsa"}


def build(check: bool = False) -> dict:
    topics = compile_topics()
    docs = load_transcripts()
    analyses = load_analyses()
    (OUT / "v").mkdir(parents=True, exist_ok=True)

    videos, all_claims = [], []
    topic_rows = {t["id"]: {"id": t["id"], "name": t["name"], "sym": t["sym"], "section": t["section"], "note": t["note"],
                            "videos": [], "n": 0, "claims": [], "sent": {"alcista": 0, "bajista": 0, "mixta": 0, "neutra": 0}} for t in topics}
    if check:
        print("Menciones con alias ambiguos (revisar a mano):")
    for vid, doc in docs.items():
        v, tr = doc["video"], doc["transcript"]
        segs = tr["segments"]
        seg_tone, seg_why = [], {}
        bull = bear = 0.0
        for i, sg in enumerate(segs):
            r = tono.score(sg["text"], segs[i - 1]["text"] if i else "")
            seg_tone.append(round(r["s"], 1))
            bull += r["bull"]; bear += r["bear"]
            if r["why"]:
                seg_why[i] = [[w["w"], 1 if w["v"] > 0 else -1] for w in r["why"]][:4]
        dur = v.get("duration_s") or (segs[-1]["start"] + segs[-1]["dur"] if segs else 0) or 1
        n_win = 48 if dur > 120 else 16
        wave = [0.0] * n_win
        for sg, sc in zip(segs, seg_tone):
            wave[min(n_win - 1, int(sg["start"] / dur * n_win))] += sc
        peak = max(1.0, max(abs(x) for x in wave))
        title_tone = tono.describe(v["title"], title=True)
        # Frase más alcista y más bajista del vídeo (ventana de tres segmentos), con su minuto.
        peaks = {}
        for sign, key in ((1, "up"), (-1, "down")):
            best, best_i = 0.0, None
            for i in range(len(segs)):
                w = sum(seg_tone[max(0, i - 1): i + 2]) * sign
                if w > best:
                    best, best_i = w, i
            if best_i is not None and best >= 1.5:
                ctx = " ".join(x["text"] for x in segs[max(0, best_i - 1): best_i + 2])
                peaks[key] = {"t": round(segs[max(0, best_i - 1)]["start"], 2), "text": ctx, "why": tono.describe(ctx)["why"][:3]}
        video_tone = {"label": tono.label(bull, bear, 1.5), "bull": round(bull, 1), "bear": round(bear, 1),
                      "share": round(bull / (bull + bear), 3) if bull + bear else None, "str": tono.strength(bull / 6, bear / 6),
                      "wave": [round(x / peak * 9) for x in wave],
                      "title": {"pol": title_tone["pol"], "str": title_tone["str"], "why": title_tone["why"][:3]}}
        ment = mentions(doc, topics, check)
        full_text = " ".join(s["text"] for s in segs)
        doc_analysis = analyses.get(vid)
        claims = []
        record = None
        if doc_analysis:
            a = doc_analysis["analysis"]
            claims = [claim_record(vid, a, c, topics) for c in a["afirmaciones"]]
            all_claims.extend(claims)
            meta = doc_analysis["meta"]
            record = {
                "estado": a["estado"], "claims": len(claims), "evidences": len(a["evidencias"]),
                "thesis": a["resumen"]["tesis_principal"], "at": meta["analyzed_at"], "model": meta.get("model"),
                "types": {k: sum(c["tipo"] == k for c in claims) for k in ("hecho_verificable", "opinion", "hipotesis", "prediccion", "insinuacion")},
                "assets": sorted({x for c in claims for x in c["assets"] if x in ASSET_LIKE}),
                "topics": sorted({x for c in claims for x in c["assets"]}),
                "scenarios": len(a["escenarios"]), "chains": len(a["cadena_narrativa"]),
                "pending": len(a["verificaciones_pendientes"]),
                "external": a["alcance"]["verificacion_externa"],
            }
        sections = defaultdict(int)
        for tid, m in ment.items():
            sections[topic_rows[tid]["section"]] += m["n"]
        sections["bolsa"] += len(GENERIC_BOLSA.findall(full_text))
        videos.append({
            "id": vid, "ch": v["channel"]["slug"], "title": v["title"], "pub": v["published_at"], "short": bool(v.get("is_short")),
            "dur": v.get("duration_s"), "segs": tr["segment_count"], "cov": tr.get("coverage"), "prov": tr.get("provider"),
            "fetched": tr.get("fetched_at"), "state": "analizado" if record else "transcrito", "analysis": record,
            "topics": {tid: m["n"] for tid, m in sorted(ment.items(), key=lambda kv: -kv[1]["n"])},
            "tone": video_tone,
            "peaks": peaks,
            "sections": {k: n for k, n in sections.items() if n >= 2},
        })
        for tid, m in ment.items():
            topic_rows[tid]["videos"].append({"v": vid, "n": m["n"], "frags": m["frags"], "sent": m["sent"]})
            topic_rows[tid]["n"] += m["n"]
            for k, n in m["sent"].items():
                topic_rows[tid]["sent"][k] += n
        atomic_json(OUT / "v" / f"{vid}.json", {
            "id": vid,
            "segments": [[round(s["start"], 2), round(s["dur"], 2), s["text"], st] for s, st in zip(segs, seg_tone)],
            "segWhy": seg_why,
            "aTone": analysis_tone(doc_analysis["analysis"]) if doc_analysis else None,
            "analysis": doc_analysis["analysis"] if doc_analysis else None,
            "meta": {k: doc_analysis["meta"].get(k) for k in ("model", "analyzed_at", "prompt_version", "cost_usd_estimate")} if doc_analysis else None,
            "claims": claims,
        })

    by_id = {v["id"]: v for v in videos}
    for c in all_claims:
        for a in c["assets"]:
            topic_rows[a]["claims"].append({"v": c["v"], "id": c["id"]})
    for row in topic_rows.values():
        row["videos"].sort(key=lambda x: by_id[x["v"]]["pub"], reverse=True)
        row["vc"] = len(row["videos"])
        row["cc"] = len({by_id[x["v"]]["ch"] for x in row["videos"]})
    ranked = sorted((r for r in topic_rows.values() if r["vc"]), key=lambda r: (-r["vc"], -r["n"], r["name"]))

    # Coincidencias y cambios entre vídeos analizados: mismo activo y horizonte; dirección igual o distinta.
    pairs = []
    analyzed = sorted({c["v"] for c in all_claims}, key=lambda x: by_id[x]["pub"])
    for i, va in enumerate(analyzed):
        for vb in analyzed[i + 1:]:
            # Solo posturas: una descripción de lo que ya pasó no contradice una predicción.
            stance = lambda c: c["dir"] in ("alcista", "bajista") and (c["own"] or c["tipo"] in ("prediccion", "hipotesis", "opinion"))
            ca = [c for c in all_claims if c["v"] == va and stance(c)]
            cb = [c for c in all_claims if c["v"] == vb and stance(c)]
            for x in ca:
                for y in cb:
                    shared = set(x["assets"]) & set(y["assets"])
                    if not shared or x["hz"] != y["hz"] or x["hz"] == "sin plazo":
                        continue
                    kind = "cambio" if x["dir"] != y["dir"] else "coincidencia"
                    same_creator = by_id[va]["ch"] == by_id[vb]["ch"]
                    weight = (2 if x["own"] or y["own"] else 0) + (1 if x["tipo"] == y["tipo"] else 0)
                    pairs.append({"kind": kind, "asset": sorted(shared)[0], "hz": x["hz"], "a": {"v": va, "id": x["id"]},
                                  "b": {"v": vb, "id": y["id"]}, "sameCreator": same_creator, "w": weight})
    pairs.sort(key=lambda p: (-p["w"], p["kind"] != "cambio"))
    seen, contrasts = set(), []
    for p in pairs:
        key = (p["asset"], p["hz"])  # un par por activo y horizonte: el de más peso (operativa declarada primero)
        if key in seen:
            continue
        seen.add(key)
        contrasts.append(p)

    themes = []
    for th in THEMES:
        claims = [c for c in all_claims if th["claims"](c)]
        src = defaultdict(lambda: {"claims": [], "frags": [], "title": False})
        for c in claims:
            src[c["v"]]["claims"].append(c["id"])
        for vid, doc in docs.items():
            if vid in src and src[vid]["claims"]:
                continue
            segs = doc["transcript"]["segments"]
            if th["titles"] is not None and th["titles"].search(doc["video"]["title"]) and th["words"].search(" ".join(s["text"] for s in segs)):
                src[vid]["title"] = True
            for i, seg in enumerate(segs):
                if th["words"].search(seg["text"]) and len(src[vid]["frags"]) < 2:
                    if not src[vid]["frags"] or seg["start"] - src[vid]["frags"][-1]["t"] > 30:
                        context = " ".join(s["text"] for s in segs[max(0, i - 1): i + 2])
                        tone = tono.describe(context)
                        src[vid]["frags"].append({"t": round(seg["start"], 2), "text": context, "pol": tone["pol"], "why": tone["why"][:3]})
        sources = [{"v": vid, **s} for vid, s in src.items() if s["claims"] or s["frags"]]
        sources.sort(key=lambda s: (not s["claims"], by_id[s["v"]]["pub"]), reverse=False)
        sources.sort(key=lambda s: by_id[s["v"]]["pub"], reverse=True)
        theme_assets = {a for c in claims for a in c["assets"]}
        theme_contrasts = [i for i, p in enumerate(contrasts) if p["a"]["id"] in {c["id"] for c in claims if c["v"] == p["a"]["v"]}
                           or p["b"]["id"] in {c["id"] for c in claims if c["v"] == p["b"]["v"]}]
        sent = {"alcista": 0, "bajista": 0, "mixta": 0, "neutra": 0}
        for c in claims:
            sent[c["pol"]] += 1
        for s_ in sources:
            if not s_["claims"]:
                for fr in s_["frags"]:
                    sent[fr["pol"]] += 1
        themes.append({
            "id": th["id"], "title": th["title"], "short": th["short"], "about": th["about"], "sent": sent,
            "sources": sources, "videoCount": len(sources), "creators": sorted({by_id[s["v"]]["ch"] for s in sources}),
            "analyzedCount": sum(bool(s["claims"]) for s in sources), "claimCount": len(claims),
            "assets": sorted(theme_assets), "contrasts": theme_contrasts,
        })

    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    videos.sort(key=lambda v: v["pub"], reverse=True)
    index = {
        "generatedAt": stamp,
        "period": {"from": videos[-1]["pub"] if videos else None, "to": videos[0]["pub"] if videos else None},
        "channels": [{"slug": c["slug"], "name": c["name"],
                      "initials": {"nacho": "NI", "kmanu": "KM", "cava": "JC", "criptoniano": "CR", "healthy": "HP"}.get(c["slug"], c["slug"][:2].upper())}
                     for c in json.loads((ROOT.parents[1] / "services/transcripts/channels.json").read_text())],
        "sections": SECTIONS,
        "videos": videos,
        "topics": ranked,
        "claims": all_claims,
        "contrasts": contrasts,
        "themes": themes,
        "method": {
            "mentions": "Coincidencias literales de un léxico revisado a mano sobre las transcripciones. Una mención acredita que se nombró, no que se analizó ni que sea cierto.",
            "contrasts": "Pares de afirmaciones de vídeos analizados con el mismo activo y el mismo horizonte; «cambio» si la postura extraída va en sentido contrario. Detectado por reglas: revisa los fragmentos.",
            "themes": "Temas definidos por palabras clave sobre afirmaciones analizadas y transcripciones. El título en forma de pregunta lo redacta el sistema.",
            "external": "Ningún análisis consultó fuentes externas: nada aparece como verificado.",
            "tone": "El tono alcista o bajista lo marca un léxico de mercado revisado a mano, con reglas de negación, condicional e indicadores inversos (si sube el dólar o los bonos se lee bajista). Señala la connotación del texto, no si acierta.",
        },
    }
    atomic_json(OUT / "index.json", index)
    return index


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    index = build(args.check)
    print(f"vídeos: {len(index['videos'])} · analizados: {sum(v['state'] == 'analizado' for v in index['videos'])}"
          f" · afirmaciones: {len(index['claims'])} · temas: {len(index['topics'])} · pares: {len(index['contrasts'])}")
    for section in ("altcoins", "macro", "bolsa"):
        rows = [r for r in index["topics"] if r["section"] == section]
        print(f"  {section}: " + ", ".join(f"{r['name']} {r['vc']}v/{r['n']}m" for r in rows[:8]))
    for p in index["contrasts"][:12]:
        print(f"  {p['kind']:<12} {p['asset']:<6} {p['hz']:<6} {p['a']['v']}:{p['a']['id']} ↔ {p['b']['v']}:{p['b']['id']} w={p['w']}")
    for t in index["themes"]:
        print(f"  tema {t['id']:<14} vídeos={t['videoCount']:>2} analizados={t['analyzedCount']} afirmaciones={t['claimCount']:>2} creadores={t['creators']} contrastes={t['contrasts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

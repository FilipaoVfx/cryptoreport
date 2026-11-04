"""Conservative projection of stored analysis. No inference or network calls.

Position side, thesis direction and lexical tone intentionally remain separate.
"""
from __future__ import annotations

import re
import unicodedata

VERSION = "radar-1.0"


def norm(value):
    return "".join(c for c in unicodedata.normalize("NFD", value or "") if not unicodedata.combining(c)).lower()


def semantic_direction(posture):
    text = norm(posture)
    if re.search(r"ambigu|no resuelt|no (?:se )?(?:puede|permite)|sin direccion|inciert", text):
        return "neutra"
    if re.search(r"\bno (?:se declara |plantear nuevos |comprar|compra|abrir|entrar)|\bpasad[oa]|\bobservad[oa]|atribuida", text):
        return "neutra"
    # Buying a dip expresses accumulation, not a short position.
    if re.search(r"acumul|compras? (?:propias?|en retrocesos)|comprar (?:en |las )?(?:caidas|retrocesos)", text):
        return "alcista"
    if re.search(r"transicion.*(?:a |construir )(?:long|larg)|cierre de cortos.*(?:larga|long)", text):
        return "alcista"
    if re.search(r"cerrad|cierre|cancelad|no operar", text):
        return "neutra"
    # A catalyst moving the other way is not the direction of the target asset.
    if re.match(r"alcista condicionad[oa] a (?:una |la )?(?:caida|bajada)", text):
        return "alcista"
    text = re.sub(r"caida dificil|no (?:es |se declara )?(?:alcista|bajista|favorable|desfavorable)", "", text)
    text = re.sub(r"\b(?:corto|medio|largo)\s*plazo\b", "", text)
    bull = bool(re.search(r"\balcist|\blongs?\b|\blong(?=\d)|\blarg[oa]s?\b|\bsubida|\brebote|\brecuperaci|\bfavorable|\bcomprar|\bcompra|\bpositiv", text))
    bear = bool(re.search(r"\bbajist|\bshorts?\b|\bcortos?\b|\bcaida|\bcorrecci|\bvender|\bventa|\bevitar|\bnegativ|\bdesfavorable|\bretroceso", text))
    return "mixta" if bull and bear else "alcista" if bull else "bajista" if bear else "neutra"


def project(claim, market, evidence, meta, creator_name):
    posture = market.get("postura") or ""
    text = norm(posture)
    quote = evidence.get("cita") or "" if evidence else ""
    speaker = norm(claim.get("emisor"))
    creator = norm(creator_name)
    is_creator = bool(creator and (creator in speaker or re.search(r"\bcreador\b", speaker)))
    if re.search(r"segun|atribu|analista|interpretacion|titulo", speaker):
        is_creator = False
    sourced = bool(quote and evidence and evidence.get("origen") == "transcripcion")
    direction = semantic_direction(posture)
    side, status = None, "desconocida"
    # An own-operation flag alone says neither side, time, asset nor execution.
    if market.get("operacion_propia_declarada") and is_creator and sourced:
        if re.search(r"cerrad|cierre|cancelad|dej[ao].*cort|se han acabado", text):
            status = "cerrada"  # transitions can still contain an open new side
        if re.search(r"cobertura|longs?\s*[/y]+\s*shorts?|cortos?\s*y\s*largos?", text):
            status = "cobertura"
        elif re.search(r"simul|ejemplo|hipotetic|educativ|\bbot|grilla", norm(posture + " " + claim.get("enunciado", ""))):
            status = "estrategia"
        elif re.search(r"\bsi\b|condicion|esperando|empezara|abriria", text):
            status = "condicional"
        elif status != "cerrada":
            # Require side in the extracted posture AND a literal first-person declaration.
            q = norm(quote)
            for label, terms in (("long", r"longs?|largos?"), ("short", r"shorts?|cortos?")):
                declared = re.search(r"(?:estoy|estamos|sigo|abri|tengo|construir|exposicion)\s+(?:en\s+)?(?:un\s+)?(?:" + terms + r")\b", q)
                if re.search(r"\b(?:" + terms + r")\b", text) and declared:
                    # Negated declarations do not confirm exposure.
                    if not re.search(r"(?:no|dejado de)\s+(?:estoy|estamos|estar|hacer|abrir)\s+(?:en\s+)?(?:" + terms + r")", q):
                        side, status = label, "declarada"
        if status == "desconocida" and re.search(r"acumul|compra|invertid|exposicion larga", text):
            status = "exposicion"  # spot / investment does not establish a trading long
    eligible = sourced and is_creator and bool(posture) and claim.get("tipo") in ("prediccion", "hipotesis", "opinion")
    if market.get("operacion_propia_declarada") and sourced and is_creator:
        eligible = True
    return {
        "direction": direction, "eligible": eligible,
        "position_side": side, "position_status": status,
        "speaker_role": "creador" if is_creator else "tercero_o_no_identificado",
        "horizon": market.get("horizonte_literal"), "conditions": market.get("condicion"),
        "invalidation": market.get("invalidacion"),
        "transcript_hash": meta.get("transcript_sha256"),
        "analysis_version": meta.get("prompt_version"), "classifier_version": VERSION,
    }

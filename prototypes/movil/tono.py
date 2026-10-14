"""Tono alcista / bajista de un texto en español sobre mercados, con reglas legibles.

No es un modelo: es un léxico revisado a mano sobre el archivo real, con cuatro ajustes de contexto
(negación, condicional, intensidad e indicadores inversos). Cada resultado devuelve las palabras que lo
dispararon, para que la interfaz pueda enseñar por qué marca algo como alcista o bajista.
"""
from __future__ import annotations

import re
import unicodedata

# (patrón, peso). Positivo = alcista para el activo del que se habla; negativo = bajista.
# Las frases van antes que las palabras sueltas: si una frase casa, sus palabras no se vuelven a contar.
PHRASES = [
    (r"tendencia alcista o bajista|alcista o bajista|hacia arriba o hacia abajo|arriba o abajo|al alza o a la baja", 0.0),
    (r"(?:[ií]ndice de )?miedo y codicia|advertencias? de crisis", 0.0),
    (r"trampas? bajistas?", 2.5), (r"trampas? alcistas?", -2.5),
    (r"divergencias? alcistas?", 2.0), (r"divergencias? bajistas?", -2.0),
    (r"reacci[oó]n alcista", 2.0), (r"manipulaci[oó]n bajista", -1.5),
    (r"canal bajista \w* ?(?:finaliza|termina|acaba)\w*", 1.5),
    (r"(?:dejad?o?|dejo|deja) de hacer (?:cortos|shorts)", 2.5), (r"(?:los )?(?:cortos|shorts),? (?:los shorts )?se (?:han )?acaba(?:do|n)", 2.0),
    (r"construir largos", 2.0), (r"(?:abrir|abro|abriendo) (?:bots? de )?longs?", 1.5),
    (r"se cancelan los shorts", 1.5), (r"cerr\w+ (?:el|los) shorts?", 0.5),
    (r"(?:estoy|estamos|me pongo|ponerme) (?:en )?short", -2.0), (r"(?:he|hemos) hecho shorts", -1.5),
    (r"(?:estoy|estamos) (?:en )?long", 2.0), (r"(?:he|hemos) hecho longs", 1.5),
    (r"short propio", -1.8), (r"longs? propios?|compras propias", 1.5),
    (r"(?:estoy|voy|sigo|seguimos) (?:100% )?alcistas?", 2.0), (r"(?:estoy|sigo|seguimos) bajistas?", -2.0),
    (r"(?:he|hemos) comprado|(?:estoy|estamos) comprando|compr[eé] ", 1.5), (r"(?:he|hemos) vendido|(?:estoy|estamos) vendiendo", -1.2),
    (r"romper? (?:los )?m[aá]ximos|rompe m[aá]ximos|nuevos? m[aá]ximos|m[aá]ximos? hist[oó]ricos?|ath\b", 1.5),
    (r"doble techo", -1.5), (r"perder (?:el|este|ese|los) (?:soporte|m[ií]nimo|punto)", -1.2),
    (r"buen noviembre|petardazo arriba|hacia arriba|para arriba", 1.2), (r"hacia abajo|para abajo", -1.0),
    (r"no hay (?:ninguna |absolutamente ninguna )?crisis", 2.0), (r"no hay (?:ninguna )?burbuja", 1.5),
    (r"(?:el )?p[aá]nico ya (?:ha )?pas\w+", 1.2),
    (r"mega ?pump\w*|ultra vol[oó]", 1.8), (r"zona de compras?", 1.0), (r"zona m[aá]s barata", 1.2),
    (r"(?:el )?mercado dice lo contrario|dice lo contrario", 2.0), (r"al l[ií]mite|zona cr[ií]tica", -1.0),
    (r"no inviertas", -1.0), (r"buen momento para comprar", 1.2), (r"no llegas tarde", 1.5),
    (r"menos sobrecalentad\w+|menor sobrecalentamiento", 1.0),
    (r"favorable al riesgo|apetito por el riesgo|risk[- ]on", 1.5), (r"aversi[oó]n al riesgo|risk[- ]off", -1.5),
    (r"favorable (?:a|para) (?:comprar|acumular|aprovechar|una construcci\w+)", 1.0), (r"favorable a vender|desfavorable", -1.0),
    (r"exposici[oó]n larga|posici[oó]n larga|invertid[ií]simo|muy invertido", 1.5),
    (r"valoraci[oó]n (?:empresarial )?negativa", -1.2), (r"valoraci[oó]n favorable", 1.0),
    (r"evitar la compra|no (?:os )?met[aá]is", -1.2),
    (r"(?:contraste con un )?supuesto clima bajista|consenso bajista", 1.5),
]
WORDS = [
    (r"alcistas?|bullish|bull ?run|bull market|prebull|altseason", 2.0),
    (r"bajistas?|bearish|bear market", -2.0),
    (r"subidas?|subir|sube|suba|suban|subiendo|subir[aá]|repunt\w+|despeg\w+", 1.0),
    (r"bajadas?|bajar|baja|baje|bajen|bajando|bajar[aá]", -1.0),
    (r"ca[ií]das?|caer|cae|caiga|caigan|cayendo|cay[oó]|caer[aá]", -1.2),
    (r"correcci[oó]n(?:es)?|corregir|corrige|corrigiendo|corrija", -1.0),
    (r"rebot\w+|recuper\w+|remont\w+", 1.0),
    (r"desplom\w+|hund\w+|derrumb\w+|crash\w*", -2.0),
    (r"rally|petardazo|pump\w*|vol(?:ar|ando|ar[aá]|[oó]|uela|uelan)|explot\w+|disparar?\w*", 1.4),
    (r"dump\w*|capitulaci\w+|liquidaci[oó]n(?:es)?|liquidar|liquidando", -0.6),
    (r"diluci[oó]n", -0.8), (r"p[eé]rdidas", -0.6),
    (r"gasolina|alivio|oportunidad(?:es)?|barat[oa]s?|acumular|fortaleza|fuerza", 0.8),
    (r"crisis|peligro|cuidado|miedo|p[aá]nico|burbuja|riesgo|debilidad|sobrecalentad\w+", -0.8),
    (r"m[aá]ximos?", 0.6), (r"techo", -0.6), (r"suelo|piso", 0.5),
    (r"verde|positiv[oa]s?", 0.5), (r"rojo|negativ[oa]s?", -0.5),
    (r"comprar|compra|compras|compro|comprado|long|longs", 0.6), (r"vender|venta|ventas|vendo|short|shorts", -0.6),
    (r"perder|pierde|perdemos|perdiendo|perdido", -0.6),
    (r"rechaz\w+", -0.4),
]
# Si el sujeto es un indicador «de miedo» (dólar, bonos, volatilidad, inflación…), que suba es malo para
# el riesgo y que baje es bueno: los verbos de movimiento se leen al revés.
INVERSE = re.compile(r"(?<!\w)(?:d[oó]lar|dxy|bonos?|rendimientos?|move|vix|hig|inflaci[oó]n|ipc|cpi|tipos|tasas|petr[oó]leo)(?!\w)", re.I)
MOVEMENT = re.compile(r"(?<!\w)(?:subidas?|subir|sube|suba|suban|subiendo|bajadas?|bajar|baja|baje|bajen|bajando|ca[ií]das?|caer|cae|cayendo|repunt\w+)(?!\w)", re.I)
NEGATION = re.compile(r"(?<!\w)(?:no|nunca|ni|tampoco|sin|dejado de|dejo de)(?!\w)", re.I)
CONDITIONAL = re.compile(r"(?<!\w)(?:si|cuando)(?!\w)", re.I)
INTENSIFIER = re.compile(r"(?<!\w)(?:mega|ultra|muy|mucho|much[ií]simo|brutal\w*|explosiv\w+|inminente|fuerte\w*|tremend\w+)(?!\w)", re.I)
# Encuadre contrario: «¿ya están todos bajistas?» insinúa lo opuesto de lo que nombra.
CONTRARIAN = [(re.compile(r"todos (?:est[aáeé]n )?bajistas|todo el mundo (?:est[aá] )?bajista", re.I), 2.0, "encuadre contrario: «todos bajistas» sugiere lo opuesto"),
              (re.compile(r"todos (?:est[aá]n )?alcistas|todo el mundo (?:est[aá] )?alcista", re.I), -2.0, "encuadre contrario: «todos alcistas» sugiere lo opuesto")]
NOT_POSITION = re.compile(r"(?<!\w)(?:corto|largo|medio) plazo|pasar? de largo|a lo largo|(?:parte|zona) (?:baja|alta)", re.I)

_PH = [(re.compile(r"(?<!\w)(?:" + p + r")(?!\w)", re.I), w) for p, w in PHRASES]
_CT = [(rx, w, why) for rx, w, why in CONTRARIAN]
_WD = [(re.compile(r"(?<!\w)(?:" + p + r")(?!\w)", re.I), w) for p, w in WORDS]


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def score(text: str, context_before: str = "") -> dict:
    """Puntuación de un texto. `context_before` (el segmento anterior) solo sirve para ver negaciones,
    condicionales o un indicador inverso que empieza antes del texto."""
    text = _norm(text)
    if not text.strip():
        return {"s": 0.0, "bull": 0.0, "bear": 0.0, "why": []}
    masked = NOT_POSITION.sub(lambda m: " " * len(m.group(0)), text)
    taken = [False] * len(masked)
    hits = []
    for rx, w, why in _CT:
        for m in rx.finditer(masked):
            if any(taken[m.start():m.end()]):
                continue
            for k in range(m.start(), m.end()):
                taken[k] = True
            hits.append((m.start(), m.end(), w, "contrario:" + why))
    for rx, w in _PH + _WD:
        for m in rx.finditer(masked):
            if any(taken[m.start():m.end()]):
                continue
            for k in range(m.start(), m.end()):
                taken[k] = True
            hits.append((m.start(), m.end(), w, m.group(0)))
    hits.sort()
    bull = bear = 0.0
    why = []
    full = (context_before[-60:] + " " + masked) if context_before else masked
    offset = len(full) - len(masked)
    for start, end, w, word in hits:
        if w == 0:
            continue
        before = full[max(0, offset + start - 34): offset + start]
        factor = 1.0
        tags = []
        if word.startswith("contrario:"):
            bull += w
            why.append({"w": word.split(":", 1)[1], "v": w, "t": ["contrario"]})
            continue
        if MOVEMENT.fullmatch(word) and INVERSE.search(full[max(0, offset + start - 48): offset + end + 24]):
            factor *= -1.0
            tags.append("inverso")
        last_words = re.findall(r"\w+", before.lower())[-3:]
        if any(NEGATION.fullmatch(t) for t in last_words) and not word.lower().startswith(("no hay", "dejad", "dejo")):
            factor *= -0.7
            tags.append("negado")
        if any(CONDITIONAL.fullmatch(t) for t in last_words):
            factor *= 0.6
            tags.append("condicional")
        if INTENSIFIER.search(before[-18:]):
            factor *= 1.4
        v = w * factor
        if v > 0:
            bull += v
        else:
            bear += -v
        why.append({"w": word.strip().lower()[:40], "v": round(v, 2), "t": tags})
    return {"s": round(bull - bear, 2), "bull": round(bull, 2), "bear": round(bear, 2), "why": why}


def label(bull: float, bear: float, min_mass: float = 0.75) -> str:
    """alcista | bajista | mixta | neutra, según el peso de cada lado."""
    total = bull + bear
    if total < min_mass:
        return "neutra"
    net = (bull - bear) / total
    if net >= 0.3:
        return "alcista"
    if net <= -0.3:
        return "bajista"
    return "mixta"


def strength(bull: float, bear: float) -> int:
    """1 débil · 2 moderada · 3 fuerte (según el peso neto)."""
    net = abs(bull - bear)
    return 3 if net >= 3.5 else 2 if net >= 1.6 else 1


def describe(text: str, context_before: str = "", title: bool = False) -> dict:
    r = score(text, context_before)
    if title:
        r["bull"], r["bear"] = r["bull"] * 1.5, r["bear"] * 1.5
    lab = label(r["bull"], r["bear"])
    return {"pol": lab, "str": strength(r["bull"], r["bear"]) if lab != "neutra" else 0, "s": r["s"],
            "why": [w["w"] for w in r["why"]][:5]}

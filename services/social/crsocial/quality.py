"""Explainable, local editorial triage. Signals are not truth or semantic evidence."""
import re
import unicodedata

VERSION = 'post-quality-1.0.0'


def normal(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c))


ASSETS = {
    'BTC': r'\$btc\b|\bbitcoin\b', 'ETH': r'\$eth\b|\bethereum\b|\bether\b',
    'SOL': r'\$sol\b|\bsolana\b', 'XRP': r'\$xrp\b|\bxrp\b|\bripple\b',
    'BNB': r'\$bnb\b|\bbinance coin\b', 'ADA': r'\$ada\b|\bcardano\b',
    'DOGE': r'\$doge\b|\bdogecoin\b', 'LINK': r'\$link\b|\bchainlink\b',
    'AVAX': r'\$avax\b|\bavalanche\b', 'SUI': r'\$sui\b|\bsui network\b',
    'AAVE': r'\$aave\b|\baave\b', 'NVDA': r'\$nvda\b|\bnvidia\b',
    'TSLA': r'\$tsla\b|\btesla\b', 'SPX': r'\bs&p\s*500\b|\bsp500\b',
}
NARRATIVES = {
    'politica_monetaria': r'\bfed\b|\btipos de interes\b|\btasas? de interes\b|\brate cuts?\b|\bmonetary\b',
    'inflacion': r'\binflacion\b|\binflation\b|\bipc\b|\bcpi\b',
    'flujos_institucionales': r'\betfs?\b|\binstitucional\w*\b|\binstitutional\w*\b|\bblackrock\b',
    'seguridad': r'\bhack\w*\b|\bwallet\w*\b|\bfirmware\b|\bcoldcard\b|\btrezor\b|\bledger\b|\bexploit\w*\b|\bseguridad\b|\bsecurity\b|\brobar\w*\b',
    'escalabilidad': r'\brollups?\b|\blayer.?2\b|\bscaling\b|\bescalabilidad\b|\bzk\w*\b|\bevm\b|\bgas\b',
    'consenso': r'\bvalidators?\b|\bvalidadores?\b|\bstaking\b|\bconsensus\b|\bconsenso\b',
    'defi': r'\bdefi\b|\bdex\b|\bliquidity\b|\bliquidez\b|\bprestamos\b',
    'regulacion': r'\bsec\b|\bregulacion\b|\bregulation\b|\bmica\b',
    'geopolitica': r'\bguerra\b|\bwar\b|\barancel\w*\b|\btariffs?\b|\bsanciones\b',
    'mercado': r'\btrading\b|\bsoporte\b|\bresistencia\b|\bvolatilidad\b|\bvolatility\b|\bbull\w*\b|\bbear\w*\b|\bprecio\b|\bprice\b',
    'inteligencia_artificial': r'\binteligencia artificial\b|\bartificial intelligence\b|\bllms?\b|\bopenai\b',
}


def classify(post):
    text = post.get('text', '')
    # URLs, author mentions and repeated whitespace do not count as information.
    clean = re.sub(r'https?://\S+|@[A-Za-z0-9_]+', ' ', text)
    clean = ' '.join(clean.split())
    norm = normal(clean)
    words = re.findall(r'\b[\w]+\b', norm)
    assets = [k for k, pattern in ASSETS.items() if re.search(pattern, norm)]
    narratives = [k for k, pattern in NARRATIVES.items() if re.search(pattern, norm)]
    # Explicit cashtags are mentions, including new assets outside the alias table.
    assets = sorted(set(assets + re.findall(r'\$([A-Z][A-Z0-9]{1,9})\b', text)))
    length = 'micro' if len(words) < 12 else 'breve' if len(words) < 45 else 'medio' if len(words) < 120 else 'largo'
    reply = post.get('is_reply') is True or bool(re.match(r'^\s*@\w+', text))
    promo = bool(re.search(r'\b(?:referido|referidos|codigo de descuento|affiliate|promo code|suscribete|curso de pago)\b', norm))
    deictic = bool(re.search(r'\b(?:mira esto|mirad esto|vean esto|look at this|this chart|este grafico|en la imagen)\b', norm))
    topical = bool(assets or narratives)
    reasons = []
    if len(words) < 7:
        reasons.append('texto_minimo')
    if not topical:
        reasons.append('sin_senales_tematicas')
    if reply:
        reasons.append('respuesta_contexto_no_recuperado')
    if deictic and (post.get('has_media') or post.get('links')):
        reasons.append('dependencia_multimedia_o_enlace')
    if promo:
        reasons.append('promocion_explicita')
    # Length alone never establishes quality: short specific news can pass, long
    # unclassified content remains available in All, without a false low-quality claim.
    relevant = topical and len(words) >= 7 and not promo and not (deictic and len(words) < 25)
    if reply and len(words) < 25:
        relevant = False
    kind = 'promocion' if promo else 'conversacion' if reply or (not topical and len(words) < 20) else 'comentario_tematico' if topical else 'sin_clasificar'
    return {'version': VERSION, 'content_hash': post.get('content_hash'),
            'characters': len(clean), 'words': len(words), 'length': length,
            'assets': assets, 'narratives': narratives, 'kind': kind,
            'visibility': 'relevante' if relevant else 'secundario',
            'semantic_eligible': relevant and not reply and not deictic,
            'reasons': reasons, 'method': 'reglas_locales', 'externally_verified': False}

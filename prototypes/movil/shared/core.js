/* Núcleo compartido de los prototipos móviles: datos reales, formato, guardados, rutas e iconos.
   Cada prototipo dibuja su propia interfaz; aquí solo vive lo que no debe diferir entre ellos. */
(function () {
  'use strict';

  const SCRIPT_URL = document.currentScript ? document.currentScript.src : location.href;
  const DATA = new URL('../data/', SCRIPT_URL).href;
  const CR = (window.CR = {});

  /* ---------- texto y formato ---------- */
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  CR.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ESC[c]);
  CR.attr = CR.esc;

  CR.fmtT = (sec) => {
    if (sec == null || isNaN(sec)) return '—';
    const s = Math.max(0, Math.floor(sec));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    return h ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`;
  };
  CR.fmtDur = (sec) => {
    if (!sec) return '';
    if (sec < 90) return `${Math.round(sec)} s`;
    const m = Math.round(sec / 60);
    return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
  };
  const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const DAYS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  CR.date = (iso) => new Date(iso);
  CR.fmtDate = (iso, opts = {}) => {
    if (!iso) return '';
    const d = new Date(iso);
    let out = `${d.getDate()} ${MONTHS[d.getMonth()]}`;
    if (opts.weekday) out = `${DAYS[d.getDay()]} ${out}`;
    if (opts.time) out += `, ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
    return out;
  };
  CR.dayKey = (iso) => { const d = new Date(iso); return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`; };
  CR.dayLabel = (iso, now = new Date()) => {
    const d = new Date(iso);
    const start = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const diff = Math.round((start(now) - start(d)) / 86400000);
    if (diff === 0) return 'Hoy';
    if (diff === 1) return 'Ayer';
    const w = DAYS[d.getDay()];
    return `${w.charAt(0).toUpperCase() + w.slice(1)} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
  };
  CR.rel = (iso, now = Date.now()) => {
    const min = Math.round((now - new Date(iso).getTime()) / 60000);
    if (min < 1) return 'ahora';
    if (min < 60) return `hace ${min} min`;
    const h = Math.round(min / 60);
    if (h < 24) return `hace ${h} h`;
    const d = Math.round(h / 24);
    return d === 1 ? 'ayer' : `hace ${d} días`;
  };
  CR.plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  CR.clip = (s, n) => (s && s.length > n ? s.slice(0, n - 1).replace(/[\s,;:.]+\S*$/, '') + '…' : s || '');
  CR.cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
  /* Los títulos de YouTube llegan con emojis y mayúsculas de reclamo; en listas se muestran tal cual,
     pero sin emojis para que no compitan con los iconos del sistema. */
  CR.cleanTitle = (s) => String(s || '').replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{200D}]/gu, '').replace(/\s{2,}/g, ' ').trim();

  CR.thumb = (id, q = 'mq') => `https://i.ytimg.com/vi/${id}/${q}default.jpg`;
  CR.yt = (id, t) => `https://www.youtube.com/watch?v=${id}${t ? `&t=${Math.floor(t)}s` : ''}`;

  /* ---------- vocabulario del análisis ---------- */
  CR.L = {
    tipo: { hecho_verificable: 'Hecho verificable', opinion: 'Opinión', hipotesis: 'Hipótesis', prediccion: 'Predicción', insinuacion: 'Insinuación' },
    tipoPl: { hecho_verificable: 'Hechos verificables', opinion: 'Opiniones', hipotesis: 'Hipótesis', prediccion: 'Predicciones', insinuacion: 'Insinuaciones' },
    verif: { no_verificada: 'Sin verificar', no_verificable: 'No verificable', respaldada: 'Respaldada por la fuente citada', parcialmente_respaldada: 'Respaldada en parte', contradicha: 'Contradicha por la fuente citada' },
    verifHelp: {
      no_verificada: 'Se podría comprobar con datos externos, pero no se consultaron.',
      no_verificable: 'Tal como está formulada no se puede comprobar.',
    },
    nivel: { alta: 'Alta', media: 'Media', baja: 'Baja' },
    estado: { completo: 'Análisis completo', parcial: 'Análisis parcial', insuficiente: 'Material insuficiente' },
    plaus: { limitada: 'Plausibilidad limitada', plausible: 'Plausible', bien_sustentada: 'Bien sustentado' },
    origen: { transcripcion: 'Transcripción', titulo: 'Título', descripcion: 'Descripción', audio: 'Audio', miniatura: 'Miniatura', fotograma: 'Fotograma' },
    vinculo: { explicito: 'Lo dice el creador', inferido: 'Lo infiere el sistema' },
    origenEsc: { creador: 'Planteado por el creador', analista: 'Añadido por el sistema' },
    prioridad: { alta: 'Prioridad alta', media: 'Prioridad media', baja: 'Prioridad baja' },
    dir: { alcista: 'Al alza', bajista: 'A la baja', mixta: 'Mixta', descriptiva: 'Descriptiva' },
    hz: { corto: 'Corto plazo', medio: 'Medio plazo', largo: 'Largo plazo', 'sin plazo': 'Sin plazo' },
    aspectos: { intencion: 'Intención', lenguaje: 'Lenguaje', emociones: 'Emociones', pruebas: 'Pruebas', saltos_logicos: 'Saltos lógicos', omisiones: 'Omisiones', audiovisual: 'Audiovisual', incentivos: 'Incentivos' },
    section: { bitcoin: 'Bitcoin', altcoins: 'Altcoins', macro: 'Macro', bolsa: 'Bolsa' },
  };
  /* La convicción del creador puede venir vacía (null) cuando el vídeo no permite juzgarla. */
  CR.nivel = (v) => (v && CR.L.nivel[v]) || 'Sin indicar';
  CR.ORDER_TIPO = ['prediccion', 'hipotesis', 'opinion', 'insinuacion', 'hecho_verificable'];

  /* ---------- datos ---------- */
  let indexPromise = null;
  const videoCache = new Map();

  async function getJSON(url) {
    const res = await fetch(url, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`HTTP ${res.status} en ${url}`);
    return res.json();
  }

  CR.load = () => {
    if (!indexPromise) {
      indexPromise = getJSON(DATA + 'index.json').then((idx) => {
        idx.channelsBySlug = Object.fromEntries(idx.channels.map((c) => [c.slug, c]));
        idx.videosById = Object.fromEntries(idx.videos.map((v) => [v.id, v]));
        idx.videos.forEach((v) => { v.channel = idx.channelsBySlug[v.ch]; v.cleanTitle = CR.cleanTitle(v.title); });
        idx.topicsById = Object.fromEntries(idx.topics.map((t) => [t.id, t]));
        idx.claimsByKey = Object.fromEntries(idx.claims.map((c) => [`${c.v}:${c.id}`, c]));
        idx.themesById = Object.fromEntries(idx.themes.map((t) => [t.id, t]));
        idx.analyzed = idx.videos.filter((v) => v.analysis);
        CR.idx = idx;
        return idx;
      });
      indexPromise.catch(() => { indexPromise = null; });
    }
    return indexPromise;
  };

  CR.loadVideo = (id) => {
    if (!videoCache.has(id)) {
      const p = getJSON(`${DATA}v/${encodeURIComponent(id)}.json`).then((doc) => {
        doc.segments = doc.segments.map(([start, dur, text, tone]) => ({ start, dur, text, s: tone || 0 }));
        doc.segWhy = doc.segWhy || {};
        const a = doc.analysis;
        doc.claimsById = Object.fromEntries((doc.claims || []).map((c) => [c.id, c]));
        if (a) {
          doc.evidenceById = Object.fromEntries(a.evidencias.map((e) => [e.id, e]));
          doc.claimsRaw = Object.fromEntries(a.afirmaciones.map((c) => [c.id, c]));
          doc.scenariosById = Object.fromEntries(a.escenarios.map((s) => [s.id, s]));
        }
        return doc;
      });
      p.catch(() => videoCache.delete(id));
      videoCache.set(id, p);
    }
    return videoCache.get(id);
  };

  /** Afirmación lista para pintar: lo que dijo el creador, lo que interpreta el sistema y sus pruebas. */
  CR.claim = (doc, id) => {
    const c = doc.claimsById[id], raw = doc.claimsRaw && doc.claimsRaw[id];
    if (!c || !raw) return null;
    const evidences = raw.evidencia_ids.map((e) => doc.evidenceById[e]).filter(Boolean);
    return Object.assign({}, c, {
      raw, evidences,
      literal: evidences.find((e) => e.cita && (e.origen === 'transcripcion' || e.origen === 'titulo')) || null,
      motivo: raw.motivo_confianza, justificacion: raw.justificacion_verificacion, mercado: raw.mercado,
    });
  };

  CR.segAt = (segments, t) => {
    let lo = 0, hi = segments.length - 1, ans = 0;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (segments[mid].start <= t + 0.05) { ans = mid; lo = mid + 1; } else hi = mid - 1;
    }
    return ans;
  };

  /** Agrupa los subtítulos en párrafos legibles: cortes por pausa o cada ~30 s en un final de frase. */
  CR.blocks = (segments, maxSpan = 30) => {
    const out = [];
    let cur = null;
    segments.forEach((s, i) => {
      const prev = segments[i - 1];
      const gap = prev ? s.start - (prev.start + prev.dur) : 0;
      const sentenceEnd = cur && /[.?!]$/.test(cur.text.trim());
      if (!cur || gap > 2.5 || (s.start - cur.start > maxSpan && sentenceEnd) || s.start - cur.start > maxSpan * 2) {
        cur = { start: s.start, end: s.start + s.dur, i0: i, i1: i, text: s.text };
        out.push(cur);
      } else {
        cur.text += ' ' + s.text;
        cur.i1 = i;
        cur.end = s.start + s.dur;
      }
    });
    return out;
  };

  /** Afirmaciones cuyo primer fragmento está cerca del instante t (para cintas y «ahora»). */
  CR.claimsAround = (claims, t, before = 25, after = 8) =>
    claims.filter((c) => c.t != null && c.t <= t + after && c.t >= t - before).sort((a, b) => b.t - a.t);

  CR.topicName = (id) => (CR.idx && CR.idx.topicsById[id] ? CR.idx.topicsById[id].name : id);

  /** Búsqueda en títulos, afirmaciones, temas y activos (las transcripciones se buscan bajo demanda). */
  CR.search = (q) => {
    const idx = CR.idx;
    const norm = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const n = norm(q).trim();
    if (!n) return { videos: [], claims: [], topics: [], themes: [] };
    const has = (s) => norm(s).includes(n);
    return {
      videos: idx.videos.filter((v) => has(v.title) || has(v.channel.name)),
      claims: idx.claims.filter((c) => has(c.text) || has(c.quote) || has(c.postura)),
      topics: idx.topics.filter((t) => has(t.name) || has(t.sym)),
      themes: idx.themes.filter((t) => has(t.title) || has(t.short)),
    };
  };
  CR.searchTranscripts = async (q, limit = 40) => {
    const idx = await CR.load();
    const norm = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const n = norm(q).trim();
    if (n.length < 3) return [];
    const docs = await Promise.all(idx.videos.map((v) => CR.loadVideo(v.id).catch(() => null)));
    const hits = [];
    docs.forEach((doc, k) => {
      if (!doc) return;
      doc.segments.forEach((s, i) => {
        if (hits.length < limit && norm(s.text).includes(n)) {
          const ctx = doc.segments.slice(Math.max(0, i - 1), i + 2).map((x) => x.text).join(' ');
          hits.push({ v: idx.videos[k].id, t: s.start, text: ctx });
        }
      });
    });
    return hits;
  };

  /* ---------- tono alcista / bajista ----------
     Cada texto lleva una connotación. El color nunca va solo: siempre con flecha y palabra. */
  CR.TONE = {
    alcista: { label: 'Alcista', short: 'Al alza', icon: 'trend-up', cls: 'up' },
    bajista: { label: 'Bajista', short: 'A la baja', icon: 'trend-down', cls: 'down' },
    mixta: { label: 'Mixta', short: 'Mixta', icon: 'updown', cls: 'mix' },
    neutra: { label: 'Neutra', short: 'Neutra', icon: 'minus', cls: 'flat' },
  };
  CR.toneLabel = (bull, bear, minMass = 0.75) => {
    const total = bull + bear;
    if (total < minMass) return 'neutra';
    const net = (bull - bear) / total;
    return net >= 0.3 ? 'alcista' : net <= -0.3 ? 'bajista' : 'mixta';
  };
  CR.toneStrength = (bull, bear) => { const n = Math.abs(bull - bear); return n >= 3.5 ? 3 : n >= 1.6 ? 2 : 1; };
  /** Tono de un tramo de subtítulos (i0..i1) a partir de la puntuación de cada segmento. */
  CR.blockTone = (doc, i0, i1) => {
    let bull = 0, bear = 0;
    const why = [];
    for (let i = i0; i <= i1; i++) {
      const s = doc.segments[i].s || 0;
      if (s > 0) bull += s; else bear -= s;
      (doc.segWhy[i] || []).forEach(([w]) => { if (why.length < 4 && !why.includes(w)) why.push(w); });
    }
    const pol = CR.toneLabel(bull, bear);
    return { pol, bull, bear, str: pol === 'neutra' ? 0 : CR.toneStrength(bull, bear), why };
  };
  /** Tono en una ventana de segundos alrededor de t (para «cómo suena ahora»). */
  CR.toneAround = (doc, t, before = 45, after = 5) => {
    let bull = 0, bear = 0;
    doc.segments.forEach((sg) => {
      if (sg.start >= t - before && sg.start <= t + after) { if (sg.s > 0) bull += sg.s; else bear -= sg.s; }
    });
    return { pol: CR.toneLabel(bull, bear), bull, bear, net: bull + bear ? (bull - bear) / (bull + bear) : 0 };
  };
  CR.toneChip = (pol, opts = {}) => {
    const T = CR.TONE[pol] || CR.TONE.neutra;
    const dots = opts.str ? `<span class="tone-str" aria-hidden="true">${[1, 2, 3].map((k) => `<i class="${k <= opts.str ? 'on' : ''}"></i>`).join('')}</span>` : '';
    const text = opts.short ? T.short : T.label;
    const pre = opts.prefix ? `${CR.esc(opts.prefix)} ` : '';
    const strTxt = opts.str ? `, intensidad ${['', 'débil', 'moderada', 'fuerte'][opts.str]}` : '';
    return `<span class="tone tone-${T.cls}${opts.insinua ? ' is-ins' : ''}${opts.cls ? ' ' + opts.cls : ''}" title="${CR.esc((opts.insinua ? 'Insinuación ' : '') + T.label.toLowerCase() + strTxt)}">${CR.icon(T.icon, 'tone-i')}<span>${pre}${opts.insinua ? `${text} insinuada` : text}</span>${dots}</span>`;
  };
  CR.markTriggers = (html, pairs) => {
    if (!pairs || !pairs.length) return html;
    let out = html;
    pairs.forEach(([w, sign]) => {
      const rx = new RegExp(`(^|[^\\wáéíóúñü])(${CR.esc(w).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})(?![\\wáéíóúñü])`, 'gi');
      out = out.replace(/(<[^>]+>)|([^<]+)/g, (m, tag, txt) => (tag ? m : txt.replace(rx, `$1<span class="tw tw-${sign > 0 ? 'up' : 'down'}">$2</span>`)));
    });
    return out;
  };
  /** ¿El título vende un tono y el contenido suena a otro? Devuelve ambos o null. */
  CR.titleGap = (v) => {
    const t = v.tone && v.tone.title ? v.tone.title.pol : 'neutra';
    const c = v.tone ? v.tone.label : 'neutra';
    const sh = v.tone ? v.tone.share : null;
    if (t === 'neutra' || t === 'mixta' || c === 'neutra') return null;
    if ((t === 'alcista' && c === 'bajista') || (t === 'bajista' && c === 'alcista')) return { title: t, content: c };
    if (c === 'mixta' && sh != null && ((t === 'alcista' && sh < 0.45) || (t === 'bajista' && sh > 0.55))) return { title: t, content: c };
    return null;
  };
  CR.toneWhy = (why) => (why && why.length ? `por ${why.slice(0, 3).map((w) => `«${CR.esc(w)}»`).join(', ')}` : '');
  /** Barra divergente: bajista a la izquierda, alcista a la derecha, mixta y neutra al centro. */
  CR.sentBar = (sent, opts = {}) => {
    const up = sent.alcista || 0, down = sent.bajista || 0, mix = sent.mixta || 0, flat = sent.neutra || 0;
    const total = Math.max(1, up + down + mix + (opts.withNeutral ? flat : 0));
    const pct = (n) => `${(n / total) * 100}%`;
    return `<span class="sbar" role="img" aria-label="${up} al alza, ${down} a la baja, ${mix} mixtas${opts.withNeutral ? `, ${flat} neutras` : ''}"><span class="sb-down" style="width:${pct(down)}"></span><span class="sb-mix" style="width:${pct(mix)}"></span>${opts.withNeutral ? `<span class="sb-flat" style="width:${pct(flat)}"></span>` : ''}<span class="sb-up" style="width:${pct(up)}"></span></span>`;
  };
  CR.netSent = (sent) => {
    const up = sent.alcista || 0, down = sent.bajista || 0;
    const pol = up + down === 0 ? ((sent.mixta || 0) ? 'mixta' : 'neutra') : CR.toneLabel(up, down, 1);
    return { pol, up, down, mix: sent.mixta || 0, flat: sent.neutra || 0, net: up + down ? (up - down) / (up + down) : 0 };
  };
  /** Sismógrafo del tono a lo largo del vídeo: barras verdes hacia arriba y rojas hacia abajo. */
  CR.waveSvg = (wave, opts = {}) => {
    const n = wave.length, w = opts.w || 320, h = opts.h || 56, mid = h / 2, gap = opts.gap == null ? 1.5 : opts.gap;
    const bw = w / n - gap;
    const bars = wave.map((v, i) => {
      if (!v) return `<rect class="wv-0" x="${(i * w) / n}" y="${mid - 0.75}" width="${bw}" height="1.5"/>`;
      const bh = Math.max(2, (Math.abs(v) / 9) * (mid - 2));
      return `<rect class="${v > 0 ? 'wv-up' : 'wv-down'}" x="${(i * w) / n}" y="${v > 0 ? mid - bh : mid}" width="${bw}" height="${bh}" rx="1"/>`;
    }).join('');
    const marks = (opts.marks || []).map((m) => `<circle class="wv-mark wv-${m.cls}" cx="${(m.x * w).toFixed(1)}" cy="${m.cls === 'up' ? 3 : m.cls === 'down' ? h - 3 : mid}" r="2.6"/>`).join('');
    return `<svg class="wave" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="${CR.esc(opts.label || 'Tono a lo largo del vídeo')}"><line class="wv-axis" x1="0" y1="${mid}" x2="${w}" y2="${mid}"/>${bars}${marks}${opts.playhead != null ? `<line class="wv-head" x1="${opts.playhead * w}" y1="0" x2="${opts.playhead * w}" y2="${h}"/>` : ''}</svg>`;
  };

  /* ---------- almacenamiento local (nunca imprescindible) ---------- */
  CR.store = (app) => ({
    get(key, def) {
      try { const raw = localStorage.getItem(`cr:${app}:${key}`); return raw == null ? def : JSON.parse(raw); } catch (e) { return def; }
    },
    set(key, val) {
      try { localStorage.setItem(`cr:${app}:${key}`, JSON.stringify(val)); } catch (e) { /* modo privado */ }
    },
  });

  CR.saved = (app) => {
    const st = CR.store(app);
    const listeners = new Set();
    const all = () => st.get('saved', []);
    return {
      all,
      has: (key) => all().some((x) => x.key === key),
      toggle(item) {
        const list = all();
        const i = list.findIndex((x) => x.key === item.key);
        if (i >= 0) list.splice(i, 1); else list.unshift(Object.assign({ at: new Date().toISOString() }, item));
        st.set('saved', list);
        listeners.forEach((fn) => fn(list));
        return i < 0;
      },
      remove(key) { st.set('saved', all().filter((x) => x.key !== key)); listeners.forEach((fn) => fn(all())); },
      onChange: (fn) => listeners.add(fn),
    };
  };

  /* ---------- compartir un hallazgo con su contexto ---------- */
  CR.share = async ({ title, text, url }) => {
    try {
      if (navigator.share) { await navigator.share({ title, text, url }); return 'shared'; }
    } catch (e) {
      if (e && e.name === 'AbortError') return 'cancelled';
    }
    try { await navigator.clipboard.writeText(url); return 'copied'; } catch (e) { /* sin permiso */ }
    const ta = document.createElement('textarea');
    ta.value = url; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    ta.remove();
    return ok ? 'copied' : 'failed';
  };
  CR.linkTo = (hash) => `${location.origin}${location.pathname}${location.search}${hash}`;

  let toastTimer = null;
  CR.toast = (msg, opts = {}) => {
    let el = document.querySelector('.toast');
    if (!el) {
      el = document.createElement('div');
      el.className = 'toast';
      el.setAttribute('role', 'status');
      el.setAttribute('aria-live', 'polite');
      document.body.appendChild(el);
    }
    el.innerHTML = CR.esc(msg) + (opts.action ? ` <button type="button" class="toast-action">${CR.esc(opts.action)}</button>` : '');
    if (opts.action && opts.onAction) el.querySelector('.toast-action').onclick = () => { opts.onAction(); el.classList.remove('is-on'); };
    el.classList.add('is-on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('is-on'), opts.ms || 2600);
  };

  /* ---------- rutas por hash ---------- */
  CR.parseHash = (hash = location.hash) => {
    const raw = hash.replace(/^#\/?/, '');
    const [path, query = ''] = raw.split('?');
    return { parts: path ? path.split('/').map(decodeURIComponent) : [], q: Object.fromEntries(new URLSearchParams(query)) };
  };
  CR.hash = (parts, q) => {
    const qs = q ? new URLSearchParams(Object.entries(q).filter(([, v]) => v != null && v !== '')).toString() : '';
    return '#/' + parts.map(encodeURIComponent).join('/') + (qs ? `?${qs}` : '');
  };
  /* Cada entrada propia del historial lleva su profundidad: así «Atrás» sabe si puede volver dentro de la
     app o si el usuario llegó por un enlace directo (entonces va al inicio en vez de salir). */
  CR.depth = () => (history.state && history.state.crDepth) || 0;
  CR.go = (parts, q, { replace = false } = {}) => {
    const h = typeof parts === 'string' ? parts : CR.hash(parts, q);
    if (replace) history.replaceState(history.state, '', h);
    else history.pushState({ crDepth: CR.depth() + 1 }, '', h);
    window.dispatchEvent(new Event('cr:route'));
  };
  CR.back = (fallback = '#/') => {
    if (CR.depth() > 0) history.back(); else CR.go(fallback, null, { replace: true });
  };
  document.addEventListener('click', (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest('a[href^="#/"]');
    if (!a || a.target) return;
    e.preventDefault();
    const href = a.getAttribute('href');
    if (href === location.hash) { window.dispatchEvent(new Event('cr:route')); return; }
    CR.go(href);
  });
  CR.onRoute = (fn) => {
    // Cambiar location.hash dispara popstate y hashchange: se atiende una sola vez por cambio.
    let last = '', at = 0;
    const run = (e) => {
      const h = location.hash;
      if (e && h === last && Date.now() - at < 120) return;
      last = h; at = Date.now();
      fn(CR.parseHash());
    };
    window.addEventListener('hashchange', run);
    window.addEventListener('popstate', run);
    window.addEventListener('cr:route', run);
    return run;
  };

  /* ---------- utilidades ---------- */
  CR.reduced = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  CR.debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  CR.$ = (sel, root = document) => root.querySelector(sel);
  CR.$$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  CR.on = (root, type, sel, fn) => root.addEventListener(type, (e) => {
    const el = e.target.closest(sel);
    if (el && root.contains(el)) fn(e, el);
  });

  /* Estados del producto que el archivo real no contiene ahora mismo: se muestran como ejemplos rotulados. */
  CR.STATES = [
    { id: 'pendiente', chip: 'Detectado', title: 'Vídeo detectado', body: 'Publicado hace 4 min. El canal se revisa cada 15 min y la transcripción suele llegar en unos 13 min.', action: 'Avisarme cuando esté', real: false },
    { id: 'parcial', chip: 'Análisis pendiente', title: 'Transcripción lista, análisis pendiente', body: 'Puedes leer, buscar y saltar a cualquier minuto. Las afirmaciones aparecerán cuando termine el análisis.', action: 'Leer la transcripción', real: true },
    { id: 'listo', chip: 'Análisis listo', title: 'Análisis listo', body: 'Afirmaciones con su minuto, pruebas citadas y escenarios. Ninguna fuente externa consultada todavía.', action: 'Abrir el análisis', real: true },
    { id: 'sin', chip: 'Sin transcripción', title: 'Transcripción no disponible', body: 'YouTube no ofreció subtítulos y la transcripción alternativa falló durante 72 h. Quedan el título y la miniatura.', action: 'Ver en YouTube', real: false },
    { id: 'inaccesible', chip: 'Inaccesible', title: 'Vídeo inaccesible', body: 'El vídeo es privado o se retiró. Se conservan la transcripción y el análisis guardados.', action: 'Leer lo guardado', real: false },
    { id: 'error', chip: 'Error de carga', title: 'No se pudo cargar', body: 'Falló la conexión al pedir el análisis. Lo que ya estaba en pantalla sigue disponible.', action: 'Reintentar', real: false },
  ];

  /* ---------- iconos (SVG propio, trazo uniforme) ---------- */
  const P = {
    play: '<path d="M8 5.6v12.8a.6.6 0 0 0 .9.5l10.2-6.4a.6.6 0 0 0 0-1L8.9 5.1a.6.6 0 0 0-.9.5z" fill="currentColor" stroke="none"/>',
    pause: '<rect x="6.5" y="5" width="3.6" height="14" rx="1" fill="currentColor" stroke="none"/><rect x="13.9" y="5" width="3.6" height="14" rx="1" fill="currentColor" stroke="none"/>',
    'arrow-left': '<path d="M19 12H5"/><path d="m11 6-6 6 6 6"/>',
    'arrow-right': '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
    'arrow-up-right': '<path d="M7 17 17 7"/><path d="M8 7h9v9"/>',
    'chevron-left': '<path d="m15 5-7 7 7 7"/>',
    'chevron-right': '<path d="m9 5 7 7-7 7"/>',
    'chevron-down': '<path d="m5 9 7 7 7-7"/>',
    'chevron-up': '<path d="m5 15 7-7 7 7"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    bookmark: '<path d="M7 4h10a1 1 0 0 1 1 1v15l-6-4-6 4V5a1 1 0 0 1 1-1z"/>',
    'bookmark-fill': '<path d="M7 4h10a1 1 0 0 1 1 1v15l-6-4-6 4V5a1 1 0 0 1 1-1z" fill="currentColor"/>',
    share: '<path d="M12 15V4"/><path d="m8 8 4-4 4 4"/><path d="M6 12v7a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-7"/>',
    external: '<path d="M14 5h5v5"/><path d="m19 5-8 8"/><path d="M17 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h4"/>',
    clock: '<circle cx="12" cy="12" r="8"/><path d="M12 8v4.5l3 2"/>',
    list: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01" stroke-width="2.6"/>',
    text: '<path d="M5 6h14M5 10h14M5 14h9M5 18h11"/>',
    layers: '<path d="m12 4 8 4-8 4-8-4 8-4z"/><path d="m4 12 8 4 8-4"/><path d="m4 16 8 4 8-4"/>',
    flask: '<path d="M9 3.5h6"/><path d="M10 3.5v5.2l-4.6 8.6A2 2 0 0 0 7.2 20h9.6a2 2 0 0 0 1.8-2.7L14 8.7V3.5"/><path d="M7.6 14.5h8.8"/>',
    quote: '<path d="M10 7H6.5A1.5 1.5 0 0 0 5 8.5V12h4v1c0 1.7-1 3-3 3.5"/><path d="M19 7h-3.5A1.5 1.5 0 0 0 14 8.5V12h4v1c0 1.7-1 3-3 3.5"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/>',
    user: '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c1-4 4-6 7-6s6 2 7 6"/>',
    users: '<circle cx="9" cy="8.5" r="3"/><path d="M3.5 19c.8-3.4 3-5 5.5-5s4.7 1.6 5.5 5"/><path d="M15.5 5.8a3 3 0 0 1 0 5.4"/><path d="M17.5 14.3c1.5.6 2.6 2 3 4.7"/>',
    filter: '<path d="M4 6h16M7 12h10M10 18h4"/>',
    sort: '<path d="M7 4v16"/><path d="m4 17 3 3 3-3"/><path d="M17 20V4"/><path d="m14 7 3-3 3 3"/>',
    grid: '<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>',
    orbit: '<circle cx="12" cy="12" r="2.6"/><ellipse cx="12" cy="12" rx="9.5" ry="4.6" transform="rotate(-28 12 12)"/><circle cx="19.2" cy="7.6" r="1.1" fill="currentColor"/>',
    scale: '<path d="M12 4v16M8 20h8M5 7.5h14"/><path d="m5 7.5-2.6 6.3a3 3 0 0 0 5.2 0L5 7.5zM19 7.5l-2.6 6.3a3 3 0 0 0 5.2 0L19 7.5z"/>',
    help: '<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.4a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.7"/><path d="M12 17h.01" stroke-width="2.4"/>',
    alert: '<path d="M10.3 4.6 3.2 17a2 2 0 0 0 1.7 3h14.2a2 2 0 0 0 1.7-3L13.7 4.6a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4"/><path d="M12 16.8h.01" stroke-width="2.4"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4.5V11h-6.5"/>',
    more: '<path d="M5.5 12h.01M12 12h.01M18.5 12h.01" stroke-width="2.8"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    sun: '<circle cx="12" cy="12" r="3.8"/><path d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6"/>',
    moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
    back10: '<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3"/><path d="M4.5 4.5v4h4"/><path d="M10 10v5M13 10h2a.9.9 0 0 1 .9.9v3.2a.9.9 0 0 1-.9.9h-2v-5z"/>',
    fwd10: '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4h-4"/><path d="M8.5 10v5M11.5 10h2a.9.9 0 0 1 .9.9v3.2a.9.9 0 0 1-.9.9h-2v-5z"/>',
    expand: '<path d="M14 4h6v6M10 20H4v-6"/><path d="m20 4-6.5 6.5M4 20l6.5-6.5"/>',
    shrink: '<path d="M20 10h-6V4M4 14h6v6"/><path d="m14 10 6.5-6.5M10 14l-6.5 6.5"/>',
    pip: '<rect x="3" y="5" width="18" height="14" rx="2"/><rect x="11.5" y="11.5" width="7" height="5" rx="1" fill="currentColor" stroke="none"/>',
    target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.5"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
    flag: '<path d="M5 21V4.5"/><path d="M5 4.5h11l-2 4 2 4H5"/>',
    calendar: '<rect x="4" y="5.5" width="16" height="14.5" rx="2"/><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4"/>',
    note: '<path d="M14.5 4.5 19.5 9.5 9 20H4v-5z"/><path d="m12.5 6.5 5 5"/>',
    branch: '<circle cx="6" cy="6" r="2.2"/><circle cx="18" cy="6" r="2.2"/><circle cx="12" cy="18.5" r="2.2"/><path d="m7.3 7.8 3.6 8.6M16.7 7.8l-3.6 8.6"/>',
    coin: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/>',
    'trend-up': '<path d="m3.5 16.5 6-6 4 4 7-7.5"/><path d="M15 7h5.5v5.5"/>',
    'trend-down': '<path d="m3.5 7.5 6 6 4-4 7 7.5"/><path d="M15 17h5.5v-5.5"/>',
    film: '<rect x="4" y="3.5" width="16" height="17" rx="2"/><path d="M8 3.5v17M16 3.5v17M4 8h4M4 12h4M4 16h4M16 8h4M16 12h4M16 16h4"/>',
    news: '<path d="M5 5h11v14H6a1 1 0 0 1-1-1V5z"/><path d="M16 9h3v9a1 1 0 0 1-2 0V9"/><path d="M8 9h5M8 12h5M8 15h3"/>',
    book: '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5z"/><path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H13v16h5.5a1.5 1.5 0 0 0 1.5-1.5z"/>',
    home: '<path d="M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5.5h-5V20H5a1 1 0 0 1-1-1z"/>',
    wave: '<path d="M3 12h2M7 8v8M11 5v14M15 9v6M19 7v10M21 12h.01"/>',
    hash: '<path d="M9 4 7 20M17 4l-2 16M4.5 9h16M3.5 15h16"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    minus: '<path d="M5 12h14"/>',
    dot: '<circle cx="12" cy="12" r="3.2" fill="currentColor" stroke="none"/>',
    split: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M12 4.5v15"/>',
    stack: '<rect x="5" y="9" width="14" height="11" rx="2"/><path d="M7.5 6.2h9M10 3.5h4"/>',
    route: '<circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="6" r="2.2"/><path d="M8 18h7.5a3.5 3.5 0 0 0 0-7h-7a3.5 3.5 0 0 1 0-7H16"/>',
    updown: '<path d="M8 19.5V5"/><path d="m4.5 8.5 3.5-3.5 3.5 3.5"/><path d="M16 4.5V19"/><path d="m12.5 15.5 3.5 3.5 3.5-3.5"/>',
    gauge: '<path d="M4.5 16.5a7.5 7.5 0 1 1 15 0"/><path d="m12 16.5 4-5"/><circle cx="12" cy="16.5" r="1.3" fill="currentColor"/>',
  };
  CR.ICON_NAMES = Object.keys(P);
  CR.icon = (name, cls = '') => `<svg class="i ${cls}" aria-hidden="true" focusable="false"><use href="#i-${name}"></use></svg>`;
  CR.injectIcons = () => {
    if (document.getElementById('cr-icons')) return;
    const sprite = Object.entries(P).map(([k, v]) => `<symbol id="i-${k}" viewBox="0 0 24 24">${v}</symbol>`).join('');
    const holder = document.createElement('div');
    holder.innerHTML = `<svg id="cr-icons" xmlns="http://www.w3.org/2000/svg" style="position:absolute;width:0;height:0;overflow:hidden" aria-hidden="true">${sprite}</svg>`;
    document.body.prepend(holder.firstChild);
  };
  if (document.body) CR.injectIcons(); else document.addEventListener('DOMContentLoaded', CR.injectIcons);
})();

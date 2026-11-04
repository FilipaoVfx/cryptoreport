/* Línea · línea minimalista: portada con el titular del día, el ranking y la bitácora; cuaderno del vídeo. */
(() => {
  'use strict';
  const { esc, fmtT, fmtDate, icon, L } = CR;
  const APP = 'm2';
  const store = CR.store(APP);
  const saved = CR.saved(APP);
  const page = document.getElementById('page');
  const stage = document.getElementById('stage');
  const nb = document.getElementById('nb');
  const nbBody = document.getElementById('nb-body');
  const nowEl = document.getElementById('now');
  const lensesEl = document.getElementById('lenses');
  const indexEl = { hidden: true };
  const ficha = document.getElementById('ficha');
  const scrim = document.getElementById('scrim');

  let idx = null;
  let player = null;
  let screen = null;
  let pipClosed = false;
  const scrolls = new Map();
  const cur = { id: null, video: null, doc: null, lens: 'destilado', blocks: [], nowBlock: -1, open: new Set(), gaps: new Set(), card: 0, notesAt: new Map() };
  const ui = { rc: store.get('rc', 'todos'), filter: store.get('filter', 'todo'), section: store.get('section', 'altcoins'), follow: true, txq: '' };
  const BASE_FILTERS = { todo: 'Todo el archivo', alcistas: 'Tono alcista', bajistas: 'Tono bajista o mixto a la baja', contraste: 'El título no cuadra con el vídeo', analizados: 'Solo con análisis', largos: 'Vídeos largos', shorts: 'Shorts' };
  let FILTERS = BASE_FILTERS;
  /* Creadores con vídeos en el archivo, del que más publica al que menos. */
  let CREATORS = [];
  const SECTIONS = ['bitcoin', 'altcoins', 'macro', 'bolsa'];
  const chip = (pol, o) => CR.toneChip(pol, o);
  const pct = (v) => (v.tone.share == null ? 'sin señales de tono' : `${Math.round(v.tone.share * 100)} % de las señales al alza`);

  const lowerFirst = (s) => (s ? s.charAt(0).toLowerCase() + s.slice(1) : s);
  const kc = (tipo) => `style="--kc: var(--k-${tipo})"`;
  const topicNames = (v, n) => Object.keys(v.topics).filter((t) => idx.topicsById[t]).slice(0, n).map((t) => idx.topicsById[t].name);
  const joinEs = (a) => (a.length <= 1 ? a.join('') : `${a.slice(0, -1).join(', ')} y ${a[a.length - 1]}`);
  const hhmm = (iso) => { const d = new Date(iso); return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`; };

  /* ---------- línea minimalista: una marca de tono, títulos sin gritar y el titular de cada día ---------- */
  /** Marca de tono: una sola forma con su color (triángulo arriba o abajo, rombo, punto) y su nombre para lectores de pantalla. */
  const mark = (pol) => { const T = CR.TONE[pol] || CR.TONE.neutra; return `<span class="mk mk-${T.cls}" role="img" aria-label="${T.label}" title="${T.label}"></span>`; };
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  /* Títulos sin gritar: fuera los hashtags y las MAYÚSCULAS de reclamo; las siglas se respetan. El original completo se ve en el vídeo. */
  const KEEP_CAPS = new Set(['BTC', 'ETH', 'SOL', 'XRP', 'BNB', 'ADA', 'DOT', 'ETF', 'ETFS', 'FED', 'BCE', 'IPC', 'CPI', 'PIB', 'USA', 'EEUU', 'IA', 'AI', 'ATH', 'DXY', 'NFT', 'MSTR', 'NVDA', 'TSM', 'HYPE', 'OTAN', 'ONU', 'FOMC', 'MOVE', 'VIX', 'USD', 'EUR', 'SEC', 'S&P']);
  /* Palabras cortas de reclamo («NO», «YA») que también bajan a minúscula. */
  const SHOUT2 = new Set(['NO', 'SI', 'SÍ', 'YA', 'YO', 'EL', 'LA', 'LO', 'LE', 'MI', 'TU', 'SU', 'DE', 'EN', 'ES', 'UN', 'AL', 'NI', 'HA', 'VA', 'SE', 'TE', 'ME']);
  let PROPER = new Map();
  function calm(title) {
    const s = String(title || '').replace(/#[\p{L}\p{N}_]+/gu, '').replace(/\s{2,}/g, ' ').replace(/[\s|·:–—-]+$/u, '').trim()
      .replace(/[\p{L}\p{N}&]+/gu, (w) => {
        if (SHOUT2.has(w)) return w.toLowerCase();
        if (w.length < 3 || /\d/.test(w) || w !== w.toUpperCase() || !/\p{Lu}/u.test(w) || KEEP_CAPS.has(w)) return w;
        const low = w.toLowerCase();
        return PROPER.get(low) || low;
      });
    return s.charAt(0).toUpperCase() + s.slice(1);
  }
  const WEEKDAY = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  const MONTH = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  const dayLong = (iso) => { const d = new Date(iso); return `${CR.cap(WEEKDAY[d.getDay()])} ${d.getDate()} de ${MONTH[d.getMonth()]}`; };
  function groupDays(list) {
    const days = [];
    list.forEach((v) => { const k = CR.dayKey(v.pub); if (!days.length || days[days.length - 1].k !== k) days.push({ k, iso: v.pub, items: [] }); days[days.length - 1].items.push(v); });
    return days;
  }
  /** Proporción de señales al alza de un grupo de vídeos (peso del léxico, no recuento de vídeos). */
  const upShare = (vs) => { let b = 0, r = 0; vs.forEach((v) => { b += v.tone.bull || 0; r += v.tone.bear || 0; }); return b + r ? b / (b + r) : null; };
  const leanOf = (s) => (s == null ? 'neutra' : s >= 0.6 ? 'alcista' : s <= 0.4 ? 'bajista' : 'mixta');
  const LEAN = { alcista: 'alcista', bajista: 'bajista', mixta: 'mixto', neutra: 'sin señales' };
  function refDay(prevIso, curIso) {
    const p = new Date(prevIso), c = new Date(curIso);
    const adjacent = CR.dayKey(new Date(c.getFullYear(), c.getMonth(), c.getDate() - 1)) === CR.dayKey(p);
    if (adjacent && CR.dayKey(c) === CR.dayKey(new Date())) return 'ayer';
    return adjacent ? `el ${WEEKDAY[p.getDay()]}` : `el ${WEEKDAY[p.getDay()]} ${p.getDate()}`;
  }
  /** Titular de un día frente al anterior con vídeos. Lo calcula el propio archivo, sin modelos. */
  function dayHeadline(days, i) {
    const d = days[i], prev = days.slice(i + 1).find((x) => upShare(x.items) != null);
    const s = upShare(d.items), lean = leanOf(s);
    if (s == null) return { text: 'Sin señales de tono', lean, changed: false };
    if (!prev) return { text: `Tono ${LEAN[lean]}`, lean, changed: false };
    const ps = upShare(prev.items), ref = refDay(prev.iso, d.iso), delta = s - ps;
    const text = delta >= 0.1 ? `Más alcista que ${ref}` : delta <= -0.1 ? `Más bajista que ${ref}` : `Tono ${LEAN[lean]}, como ${ref}`;
    return { text, lean, changed: lean !== leanOf(ps) && lean !== 'mixta' && leanOf(ps) !== 'mixta', delta };
  }
  const countLabels = (vs) => { const n = { alcista: 0, bajista: 0, mixta: 0, neutra: 0 }; vs.forEach((v) => { n[v.tone.label] += 1; }); return n; };

  /* ---------- reproductor ---------- */
  function ensurePlayer() {
    if (player) return player;
    player = new CR.Player(document.getElementById('player'));
    player.on('time', onTime);
    player.on('state', (s) => {
      const playing = s === 'playing';
      document.getElementById('pip-toggle').innerHTML = icon(playing ? 'pause' : 'play');
      const np = document.getElementById('now-play');
      if (np) { np.innerHTML = icon(playing ? 'pause' : 'play'); np.setAttribute('aria-label', playing ? 'Pausar' : 'Reproducir'); }
      if (s === 'needs-tap') CR.toast('Toca el vídeo para empezar a reproducir');
      if (s === 'paused' && cur.id) store.set('session', { v: cur.id, t: player.time() });
    });
    return player;
  }
  let lastSave = 0;
  function onTime(t) {
    if (!cur.video) return;
    if (Date.now() - lastSave > 3000) { lastSave = Date.now(); store.set('session', { v: cur.id, t }); }
    if (screen === `v:${cur.id}`) { renderNow(t); syncDoc(t); movePlayhead(t); }
  }
  function setStage() {
    const onVideo = screen && screen.startsWith('v:');
    let mode = 'none';
    if (cur.id && onVideo) mode = nb.dataset.snap === 'full' ? 'pip' : 'top';
    else if (cur.id && !pipClosed) mode = 'pip';
    stage.dataset.mode = mode;
  }

  /* ---------- cuaderno: alturas y arrastre ---------- */
  const SNAP_LABEL = { peek: 'Cuaderno recogido. Pulsa para abrirlo a media altura.', half: 'Cuaderno a media altura. Pulsa para ampliarlo.', full: 'Cuaderno ampliado. Pulsa para reducirlo.' };
  function setSnap(snap) {
    nb.dataset.snap = snap;
    nb.style.top = '';
    document.getElementById('nb-grip').setAttribute('aria-label', SNAP_LABEL[snap]);
    store.set('snap', snap);
    setStage();
    renderNow(player ? player.time() : 0);
  }
  function snapTops() {
    const top = 48;
    const ph = Math.min(window.innerWidth, 460) * 0.5625;
    return { full: top, half: top + Math.min(ph, window.innerHeight * 0.36) + 6, peek: window.innerHeight - 128 };
  }
  (function bindDrag() {
    const handle = document.getElementById('nb-handle');
    let startY = 0, startTop = 0, dragging = false, moved = 0, lastY = 0, lastT = 0, vel = 0;
    handle.addEventListener('pointerdown', (e) => {
      if (e.target.closest('button:not(.nb-grip), a, [role="radio"]')) return;
      dragging = true; moved = 0;
      startY = lastY = e.clientY; lastT = performance.now();
      startTop = nb.getBoundingClientRect().top;
      nb.classList.add('is-dragging');
      handle.setPointerCapture(e.pointerId);
    });
    handle.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      const dy = e.clientY - startY;
      moved = Math.max(moved, Math.abs(dy));
      const tops = snapTops();
      nb.style.top = `${Math.min(tops.peek + 40, Math.max(tops.full, startTop + dy))}px`;
      const now = performance.now();
      vel = (e.clientY - lastY) / Math.max(1, now - lastT);
      lastY = e.clientY; lastT = now;
    });
    const end = () => {
      if (!dragging) return;
      dragging = false;
      nb.classList.remove('is-dragging');
      if (moved < 6) { nb.style.top = ''; return; } // fue un toque: lo resuelve el botón
      const top = nb.getBoundingClientRect().top;
      const tops = snapTops();
      let snap = Object.entries(tops).sort((a, b) => Math.abs(a[1] - top) - Math.abs(b[1] - top))[0][0];
      if (vel > 0.6) snap = top < tops.half ? 'half' : 'peek';
      if (vel < -0.6) snap = top > tops.half ? 'half' : 'full';
      setSnap(snap);
    };
    handle.addEventListener('pointerup', end);
    handle.addEventListener('pointercancel', end);
  })();

  function setCreators() {
    CREATORS = idx.channels.map((c) => Object.assign({ n: idx.videos.filter((v) => v.ch === c.slug).length }, c)).filter((c) => c.n).sort((a, b) => b.n - a.n);
    FILTERS = Object.assign({}, BASE_FILTERS, Object.fromEntries(CREATORS.map((c) => [c.slug, c.name])));
    PROPER = new Map(idx.topics.filter((t) => ['bitcoin', 'altcoins', 'bolsa'].includes(t.section) && !/\s/.test(t.name)).map((t) => [t.name.toLowerCase(), t.name]));
  }

  /* ---------- rutas ---------- */
  function saveScroll() {
    if (!screen) return;
    scrolls.set(screen, screen.startsWith('v:') ? nbBody.scrollTop : window.scrollY);
  }
  const DOCK = { '': 'home', diario: 'home', v: 'home', activos: 'activos', f: 'activos', n: 'activos', guardados: 'guardados' };
  async function route(r) {
    const [a = '', b] = r.parts;
    if (a === 'diario') { CR.go('#/', null, { replace: true }); return; }
    const key = a === 'v' ? `v:${b}` : a === 'f' || a === 'activos' ? 'activos' : a === '' ? 'home' : `${a}${b ? ':' + b : ''}`;
    if (a !== 'f') closeFicha(true);
    if (screen === key) {
      if (a === 'v') applyVideoQuery(r.q);
      else if (key === 'activos') { if (a === 'f') openFicha(b); else renderRanking(r.q, true); }
      else if (key === 'home') renderHome(r.q, true);
      return;
    }
    saveScroll();
    screen = key;
    document.body.dataset.screen = a === 'v' ? 'video' : key;
    const cap = document.getElementById('ln-cap');
    if (cap && key !== 'home') cap.hidden = true;
    nb.hidden = a !== 'v';
    CR.$$('.dock a').forEach((el) => { if (el.dataset.d === DOCK[a]) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current'); });
    if (!idx) {
      page.innerHTML = '<div class="pad"><div class="skel" style="height:44px;margin-top:12px"></div><div class="skel" style="height:200px;margin-top:18px"></div><div class="skel" style="height:64px;margin-top:12px"></div></div>';
      try { idx = await CR.load(); setCreators(); } catch (e) {
        page.innerHTML = `<div class="err" role="alert"><h3>No se pudo abrir el archivo</h3><p>Falló la carga de los datos. Revisa la conexión y vuelve a intentarlo.</p><button class="pill" type="button" data-act="reload">${icon('refresh')} Reintentar</button></div>`;
        return;
      }
    }
    if (a === 'v') await renderVideo(b, r.q);
    else if (a === 'n') renderThread(b);
    else if (a === '') renderHome(r.q);
    else if (a === 'guardados') renderSaved();
    else if (a === 'buscar') renderSearch(r.q.q || '');
    else if (a === 'estados') renderStates();
    else if (a === 'datos') renderAbout();
    else { renderRanking(a === 'f' ? {} : r.q); if (a === 'f') openFicha(b); }
    setStage();
    if (a !== 'v') window.scrollTo(0, scrolls.get(key) || 0);
  }

  /* ---------- explorar: secciones, filtros y ranking con tono (de la Nébula) ---------- */
  const SEC_TITLE = { bitcoin: 'Bitcoin en conversación', altcoins: 'Altcoins mencionadas', macro: 'Macro en conversación', bolsa: 'Bolsa en conversación' };
  const SEC_THEMES = { bitcoin: ['btc-corto', 'liquidaciones', 'fin-octubre'], altcoins: ['altcoins', 'liquidaciones'], macro: ['macro-alivio', 'fin-octubre'], bolsa: ['bolsa'] };
  function exState(q) {
    const st = Object.assign({ s: 'todo', tab: 'ranking', c: 'todos', p: 'todo', m: 'videos' }, store.get('ex', {}), q || {});
    store.set('ex', { s: st.s, tab: st.tab, c: st.c, p: st.p, m: st.m });
    return st;
  }
  const exHash = (st, patch) => CR.hash(['activos'], Object.assign({ s: st.s, tab: st.tab, c: st.c, p: st.p, m: st.m }, patch));
  function inWindow(v, st) {
    if (st.c !== 'todos' && v.ch !== st.c) return false;
    if (st.p === 'todo') return true;
    const days = st.p === '3d' ? 3 : 1;
    return (new Date(idx.period.to) - new Date(v.pub)) / 86400000 < days;
  }
  function rankRows(st) {
    return idx.topics.filter((t) => st.s === 'todo' || t.section === st.s).map((t) => {
      const vids = t.videos.filter((m) => inWindow(idx.videosById[m.v], st));
      const sent = { alcista: 0, bajista: 0, mixta: 0, neutra: 0 };
      vids.forEach((m) => Object.keys(sent).forEach((k) => { sent[k] += (m.sent || {})[k] || 0; }));
      const frags = vids.flatMap((m) => m.frags.map((f) => Object.assign({ v: m.v }, f)));
      return { t, vids, vc: vids.length, n: vids.reduce((a, m) => a + m.n, 0), cc: new Set(vids.map((m) => idx.videosById[m.v].ch)).size, sent, net: CR.netSent(sent), frags };
    }).filter((r) => r.vc > 0).sort((a, b) => {
      if (st.m === 'menciones') return b.n - a.n || b.vc - a.vc;
      if (st.m === 'alza') return (b.net.up - b.net.down) - (a.net.up - a.net.down) || b.vc - a.vc;
      if (st.m === 'baja') return (b.net.down - b.net.up) - (a.net.down - a.net.up) || b.vc - a.vc;
      return b.vc - a.vc || b.n - a.n;
    });
  }
  /* Símbolo o, si no lo hay, iniciales legibles: «Política y geopolítica» → PG, «Liquidez» → LIQ. */
  const symOf = (t) => { if (t.sym) return t.sym.slice(0, 4); const w = t.name.split(/\s+/).filter((x) => x.length > 2); return (w.length > 1 ? w.map((x) => x[0]).join('').slice(0, 3) : t.name.slice(0, 3)).toUpperCase(); };
  const symAv = (t) => `<span class="sym-av" aria-hidden="true">${esc(symOf(t))}</span>`;
  /* Las primeras tres afirmaciones a la vista; el resto, plegado. */
  const claimsBlock = (list, fn) => list.slice(0, 3).map(fn).join('') + (list.length > 3 ? `<details class="f-more"><summary>${icon('chevron-down', 'i-s')}Ver ${list.length - 3} más</summary>${list.slice(3).map(fn).join('')}</details>` : '');
  const peak = (frags, pol) => frags.filter((f) => f.pol === pol).sort((a, b) => b.text.length - a.text.length)[0];
  /* ---------- ranking mínimo: posición, nombre, marca y una cifra ---------- */
  const countOf = (r, m) => (m === 'menciones' ? r.n : m === 'alza' ? r.sent.alcista : m === 'baja' ? r.sent.bajista : r.vc);
  const COUNT_LABEL = { videos: 'vídeos', menciones: 'menciones', alza: 'al alza', baja: 'a la baja' };
  function rankTable(rows, st, limit, extra) {
    if (!rows.length) return '<p class="empty-line">Sin menciones con estos filtros.</p>';
    const list = limit ? rows.slice(0, limit) : rows;
    return `<ol class="mrank"><li class="mr-head" aria-hidden="true"><span></span><span></span><span></span><span>${COUNT_LABEL[st.m] || 'vídeos'}</span></li>${list.map((r, i) => `<li><a class="mr" href="#/f/${r.t.id}"><span class="mr-n">${i + 1}</span><span class="mr-name">${esc(r.t.name)}${extra ? extra(r) : ''}</span>${mark(r.net.pol)}<span class="mr-c">${countOf(r, st.m)}<span class="sr"> ${COUNT_LABEL[st.m] || 'vídeos'}</span></span></a></li>`).join('')}</ol>`;
  }
  function renderRanking(q, keep) {
    const st = exState(q);
    const rows = rankRows(st);
    const y = keep ? window.scrollY : 0;
    const secs = [['todo', 'Todo']].concat(SECTIONS.map((k) => [k, L.section[k]]));
    const sel = (id, label, opts, val) => `<label class="sel"><span class="sr">${label}</span><select id="${id}">${opts.map(([k, l]) => `<option value="${k}"${k === val ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>${icon('chevron-down', 'i-s')}</label>`;
    page.innerHTML = `<div class="pad rk-page">
      <h1 class="pg-h1">Activos</h1>
      <nav class="txt-tabs" aria-label="Sección">${secs.map(([k, l]) => `<a href="${exHash(st, { s: k })}"${k === st.s ? ' aria-current="page"' : ''}>${l}</a>`).join('')}</nav>
      <div class="sels">${sel('f-m', 'Ordenar', [['videos', 'Por vídeos'], ['menciones', 'Por menciones'], ['alza', 'Más al alza'], ['baja', 'Más a la baja']], st.m)}${sel('f-c', 'Creador', [['todos', 'Todos']].concat(CREATORS.map((c) => [c.slug, c.name])), st.c)}${sel('f-p', 'Periodo', [['todo', 'Todo el archivo'], ['3d', 'Últimos 3 días'], ['1d', 'Último día']], st.p)}</div>
      ${rankTable(rows, st, 0, typeof rankExtra === 'function' ? rankExtra : null)}
    </div>`;
    const go = (patch) => CR.go(exHash(st, patch), null, { replace: true });
    ['m', 'c', 'p'].forEach((k) => document.getElementById(`f-${k}`).addEventListener('change', (e) => go({ [k]: e.target.value })));
    if (keep) window.scrollTo(0, y);
  }

  /* ---------- ficha de un activo: cifras, balance y lo que se dijo, día a día ---------- */
  function openFicha(id) {
    const t = idx.topicsById[id];
    if (!t) { CR.go('#/activos', null, { replace: true }); return; }
    const st = exState({});
    const r = rankRows(Object.assign({}, st, { s: t.section })).find((x) => x.t.id === id) || rankRows(Object.assign({}, st, { s: t.section, c: 'todos', p: 'todo' })).find((x) => x.t.id === id);
    if (!r) return;
    const claims = t.claims.map((k) => idx.claimsByKey[`${k.v}:${k.id}`]).filter(Boolean);
    const frags = r.frags.slice().sort((a, b) => idx.videosById[b.v].pub.localeCompare(idx.videosById[a.v].pub) || a.t - b.t);
    const dayKeys = [...new Set(frags.map((f) => CR.dayKey(idx.videosById[f.v].pub)))];
    const s = r.sent;
    const fr = (f) => { const v = idx.videosById[f.v]; return `<a class="fr" href="#/v/${v.id}?t=${Math.floor(f.t)}&lens=transcripcion">${mark(f.pol)}<span class="fr-q">«${esc(f.text)}»</span><span class="fr-m">${esc(v.channel.name)} · ${fmtT(f.t)}</span></a>`; };
    const cl = (c) => { const v = idx.videosById[c.v]; return `<a class="fr" href="#/v/${v.id}?t=${Math.floor(c.t || 0)}&n=${c.id}">${mark(c.pol)}<span class="fr-q">${esc(c.text)}</span><span class="fr-m">${L.tipo[c.tipo]} · ${esc(v.channel.name)} · ${fmtDate(v.pub)}</span></a>`; };
    document.getElementById('ficha-title').textContent = t.name;
    document.getElementById('ficha-body').innerHTML = `
      <p class="f-line">${esc(t.sym ? `${t.sym} · ` : '')}${esc(L.section[t.section])} · ${CR.plural(r.vc, 'vídeo', 'vídeos')} · ${CR.plural(r.n, 'mención', 'menciones')}</p>
      <p class="f-bal"><span>${mark('alcista')}${s.alcista}</span><span>${mark('bajista')}${s.bajista}</span><span>${mark('mixta')}${s.mixta}</span><span class="f-flat">${s.neutra} sin tono</span></p>
      <span class="bal" role="img" aria-label="${s.alcista} menciones alcistas, ${s.bajista} bajistas y ${s.mixta} mixtas"><i class="bal-down" style="flex:${s.bajista}"></i><i class="bal-mix" style="flex:${s.mixta}"></i><i class="bal-up" style="flex:${s.alcista}"></i></span>
      <button class="pill f-save" type="button" data-act="save-asset" data-id="${t.id}" aria-pressed="${saved.has(`a:${t.id}`)}">${icon(saved.has(`a:${t.id}`) ? 'bookmark-fill' : 'bookmark')} ${saved.has(`a:${t.id}`) ? 'Guardado' : 'Guardar'}</button>
      ${dayKeys.map((k) => { const fs = frags.filter((f) => CR.dayKey(idx.videosById[f.v].pub) === k); return `<section><h4 class="tl-h">${esc(CR.dayLabel(idx.videosById[fs[0].v].pub))}</h4>${fs.map(fr).join('')}</section>`; }).join('')}
      ${claims.length ? `<p class="f-h">Lo que se analizó · ${claims.length}</p>${claimsBlock(claims, cl)}` : ''}`;
    ficha.hidden = false; scrim.hidden = false;
    document.getElementById('ficha-body').scrollTop = 0;
    ficha.querySelector('[data-act="ficha-close"]').focus({ preventScroll: true });
  }
  function closeFicha(silent) {
    if (ficha.hidden) return;
    ficha.hidden = true; scrim.hidden = true;
    if (!silent) CR.back('#/activos');
  }

  function closeIndex() { /* sin índice: la navegación vive en la cápsula inferior */ }

  /* ---------- portada de la Línea: una sola línea vertical ----------
     Cada punto es un vídeo (o un activo, en el modo ranking): a la derecha de la línea si empuja al alza,
     a la izquierda si empuja a la baja, tanto más lejos cuanto más claro. Solo el punto que pasa por la
     retícula muestra su texto, abajo. */
  const LN_STEP = 60, LN_DAY = 46, RET = 0.4;
  let lnItems = [], lnFocus = -1, lnRaf = 0, lnQ = {};
  function renderHome(q, keep) {
    lnQ = q || {};
    const mode = ['videos', 'ranking'].includes(lnQ.m) ? lnQ.m : store.get('lm', 'videos');
    const sec = ['todo'].concat(SECTIONS).includes(lnQ.s) ? lnQ.s : store.get('ls', 'todo');
    store.set('lm', mode); store.set('ls', sec);
    const y0 = keep ? window.scrollY : 0;
    const W = Math.min(window.innerWidth, 460), half = W / 2 - 40;
    const days = groupDays(idx.videos);
    const head = dayHeadline(days, 0);
    let y = 34;
    const labels = [];
    lnItems = [];
    if (mode === 'videos') {
      days.forEach((d, i) => {
        labels.push(`<p class="ln-day" style="top:${y}px"><b>${esc(CR.dayLabel(d.iso))}</b>${i ? `<span>${esc(lowerFirst(dayHeadline(days, i).text))}</span>` : ''}</p>`);
        y += LN_DAY;
        d.items.forEach((v) => { lnItems.push({ kind: 'v', v, y, x: v.tone.share == null ? 0 : (v.tone.share - 0.5) * 2, pol: v.tone.label }); y += LN_STEP; });
      });
    } else {
      const st = Object.assign({}, exState({}), { s: sec, c: 'todos', p: 'todo', m: 'videos' });
      rankRows(st).forEach((r, i) => {
        labels.push(`<span class="ln-rk" style="top:${y}px" aria-hidden="true">${i + 1}</span>`);
        lnItems.push({ kind: 'a', r, rank: i + 1, y, x: r.net.net, pol: r.net.pol });
        y += LN_STEP;
      });
    }
    lnItems.forEach((it) => { it.cx = W / 2 + it.x * half; });
    const trace = lnItems.map((it, i) => { if (!i) return `M${it.cx.toFixed(1)} ${it.y}`; const p = lnItems[i - 1], m = (p.y + it.y) / 2; return `C${p.cx.toFixed(1)} ${m} ${it.cx.toFixed(1)} ${m} ${it.cx.toFixed(1)} ${it.y}`; }).join(' ');
    const dots = lnItems.map((it, i) => {
      const size = it.kind === 'v' ? (it.v.short ? 9 : 13) : Math.round(8 + Math.min(14, Math.sqrt(it.r.vc) * 3));
      const label = it.kind === 'v' ? `${hhmm(it.v.pub)}, ${calm(it.v.cleanTitle)}, ${CR.TONE[it.pol].label.toLowerCase()}` : `${it.rank}. ${it.r.t.name}, ${CR.TONE[it.pol].label.toLowerCase()}`;
      return `<button class="ln-dot ln-${CR.TONE[it.pol].cls}" type="button" data-act="ln" data-i="${i}" style="left:${it.cx.toFixed(1)}px;top:${it.y}px;--s:${size}px" aria-label="${esc(label)}"></button>`;
    }).join('');
    const tabs = (items, cur) => items.map(([k, l, h]) => `<a href="${h}"${k === cur ? ' aria-current="page"' : ''}>${l}</a>`).join('');
    page.innerHTML = `
      <header class="ln-head pad"><p class="ln-date">${esc(dayLong(days[0].iso))}</p><h1 class="ln-h1">${esc(head.text)}.</h1>
        <nav class="txt-tabs ln-modes" aria-label="Qué recorre la línea">${tabs([['videos', 'Vídeos', CR.hash([], { m: 'videos' })], ['ranking', 'Ranking', CR.hash([], { m: 'ranking', s: sec })]], mode)}</nav>
        ${mode === 'ranking' ? `<nav class="txt-tabs ln-secs" aria-label="Sección del ranking">${tabs([['todo', 'Todo']].concat(SECTIONS.map((k) => [k, L.section[k]])).map(([k, l]) => [k, l, CR.hash([], { m: 'ranking', s: k })]), sec)}</nav>` : ''}
      </header>
      <div class="ln-wrap"><div class="ln-track" style="height:${y}px">
        <span class="ln-axis" aria-hidden="true"></span><span class="ln-side ln-side-down" aria-hidden="true">a la baja</span><span class="ln-side ln-side-up" aria-hidden="true">al alza</span>
        <svg class="ln-trace" width="${W}" height="${y}" viewBox="0 0 ${W} ${y}" aria-hidden="true"><path d="${trace}"/></svg>
        ${labels.join('')}${dots}
      </div>
      ${mode === 'ranking' ? `<p class="ln-list pad"><a class="more" href="${exHash(Object.assign({}, exState({}), { s: sec }), {})}">Ver el ranking como lista</a></p>` : ''}</div>`;
    lnFocus = -1;
    window.scrollTo(0, y0);
    lnUpdate();
  }
  function lnUpdate() {
    const cap = document.getElementById('ln-cap');
    const track = document.querySelector('.ln-track');
    if (screen !== 'home' || !track || !lnItems.length) { cap.hidden = true; return; }
    const top = track.getBoundingClientRect().top, ret = window.innerHeight * RET;
    let best = 0, bd = Infinity;
    lnItems.forEach((it, i) => { const dd = Math.abs(top + it.y - ret); if (dd < bd) { bd = dd; best = i; } });
    cap.hidden = false;
    if (best !== lnFocus) { lnFocus = best; lnCaption(best); }
  }
  function lnCaption(i) {
    CR.$$('.ln-dot.is-focus').forEach((d) => d.classList.remove('is-focus'));
    const dot = document.querySelector(`.ln-dot[data-i="${i}"]`);
    if (dot) dot.classList.add('is-focus');
    const it = lnItems[i], cap = document.getElementById('ln-cap');
    if (it.kind === 'v') {
      const v = it.v;
      cap.innerHTML = `<a class="ln-cap-in" href="#/v/${v.id}"><span class="ln-cap-meta">${hhmm(v.pub)} · ${esc(v.channel.name)}${v.short ? ' · Short' : ''}</span><span class="ln-cap-title">${esc(calm(v.cleanTitle))}</span><span class="ln-cap-tone">${mark(v.tone.label)}${esc(CR.TONE[v.tone.label].label)}${v.tone.share != null ? ` · ${Math.round(v.tone.share * 100)} % al alza` : ''}${icon('arrow-right', 'i-s')}</span></a>`;
    } else {
      const r = it.r;
      cap.innerHTML = `<a class="ln-cap-in" href="#/f/${r.t.id}"><span class="ln-cap-meta">${it.rank}.º · ${esc(L.section[r.t.section])}</span><span class="ln-cap-title">${esc(r.t.name)}</span><span class="ln-cap-tone">${mark(r.net.pol)}${esc(CR.TONE[r.net.pol].label)} · ${CR.plural(r.vc, 'vídeo', 'vídeos')} · ${CR.plural(r.n, 'mención', 'menciones')}${icon('arrow-right', 'i-s')}</span></a>`;
    }
  }
  window.addEventListener('scroll', () => { if (!lnRaf) lnRaf = requestAnimationFrame(() => { lnRaf = 0; lnUpdate(); }); }, { passive: true });
  window.addEventListener('resize', CR.debounce(() => { if (screen === 'home' && idx) renderHome(lnQ, true); }, 200));

  /* ---------- ficha del vídeo + cuaderno ---------- */
  async function renderVideo(id, q) {
    const v = idx.videosById[id];
    if (!v) { nb.hidden = true; page.innerHTML = `<div class="empty"><h3>Este vídeo no está en el archivo</h3><a class="pill" href="#/">Ver el rollo</a></div>`; return; }
    document.getElementById('topbar-title').textContent = v.cleanTitle;
    ensurePlayer();
    pipClosed = false;
    const s = store.get('session', null);
    const start = q.t != null ? Number(q.t) : cur.id === id ? player.time() : s && s.v === id ? s.t : 0;
    if (cur.id !== id) {
      Object.assign(cur, { id, video: v, doc: null, blocks: [], nowBlock: -1, open: new Set(), gaps: new Set(), card: 0 });
      ui.txq = ''; ui.follow = true;
      player.load(v, { start });
    } else if (q.t != null) player.seek(Number(q.t), { play: false });
    cur.lens = q.lens || (v.analysis ? store.get('lens', 'destilado') : 'transcripcion');
    page.innerHTML = videoInfo(v);
    setSnap(q.snap || (store.get('snap', 'half') === 'peek' ? 'half' : store.get('snap', 'half')));
    renderLenses();
    nbBody.innerHTML = '<div class="pad"><div class="skel" style="height:22px;margin-top:16px"></div><div class="skel" style="height:110px;margin-top:12px"></div></div>';
    try { cur.doc = await CR.loadVideo(id); } catch (e) {
      if (screen !== `v:${id}`) return;
      nbBody.innerHTML = `<div class="err" role="alert"><h3>No se pudo abrir el cuaderno</h3><p>El vídeo sigue disponible. Reintenta para cargar la transcripción y las notas.</p><button class="pill" type="button" data-act="retry-video">${icon('refresh')} Reintentar</button></div>`;
      return;
    }
    if (screen !== `v:${id}`) return;
    renderNotebook();
    applyVideoQuery(q);
  }
  function videoInfo(v) {
    const t = v.tone;
    const pk = ['up', 'down'].filter((k) => v.peaks && v.peaks[k]);
    const gap = CR.titleGap(v);
    return `<section class="vinfo">
      <p class="vinfo-who">${esc(v.channel.name)} · ${fmtDate(v.pub, { weekday: true, time: true })}</p>
      <h1 class="vinfo-title">${esc(v.cleanTitle)}</h1>
      <p class="vtone-line">${mark(t.label)}<span>${CR.TONE[t.label].label}${t.share != null ? ` · ${Math.round(t.share * 100)} % al alza` : ''}</span>${gap ? `<span class="vt-gap">· el título suena ${esc(CR.TONE[gap.title].label.toLowerCase())}</span>` : ''}</p>
      ${t.share != null ? `<div class="pulse-wave big">${CR.waveSvg(t.wave, { w: 360, h: 40, gap: 1.5, label: 'Tono a lo largo del vídeo: arriba alcista, abajo bajista' })}</div>` : ''}
      ${pk.map((k) => `<button class="peak" type="button" data-act="seek" data-t="${v.peaks[k].t}">${mark(k === 'up' ? 'alcista' : 'bajista')}<span><b>${fmtT(v.peaks[k].t)}</b>«${esc(CR.clip(v.peaks[k].text, 120))}»</span></button>`).join('')}
    </section>
    <div class="vinfo-actions">
      <button class="pill pill-solid" type="button" data-act="snap" data-snap="half">${icon('book')} Cuaderno</button>
      <button class="pill" type="button" data-act="save-video">${icon(saved.has(`v:${v.id}`) ? 'bookmark-fill' : 'bookmark')} ${saved.has(`v:${v.id}`) ? 'Marcado' : 'Marcar'}</button>
      <a class="pill" href="${CR.yt(v.id)}" target="_blank" rel="noopener">${icon('external')} YouTube</a>
    </div>`;
  }
  function renderLenses() {
    const lenses = [['destilado', 'Destilado'], ['transcripcion', 'Texto'], ['analisis', 'Análisis']];
    lensesEl.innerHTML = lenses.map(([k, label]) => `<button class="lens" type="button" role="radio" aria-checked="${cur.lens === k}" data-act="lens" data-lens="${k}">${label}</button>`).join('');
  }
  function renderNow(t) {
    const v = cur.video;
    if (!v) return;
    const playing = player && player.playing;
    let text = '';
    let go = '';
    const tn = cur.doc ? mark(CR.toneAround(cur.doc, t).pol) : '';
    if (cur.doc && cur.doc.claims && cur.doc.claims.length) {
      const before = cur.doc.claims.filter((c) => c.t != null && c.t <= t + 1).sort((a, b) => b.t - a.t)[0];
      const next = cur.doc.claims.filter((c) => c.t != null && c.t > t + 1).sort((a, b) => a.t - b.t)[0];
      const c = before && t - before.t < 90 ? before : next;
      if (c) {
        text = `<b>${fmtT(c === before ? t : c.t)}</b>${tn}<span class="now-claim">${esc(c.text)}</span>`;
        go = `<button class="ib now-go" type="button" data-act="goto-note" data-c="${c.id}" aria-label="Ir a la nota de las ${fmtT(c.t)}">${icon('arrow-right')}</button>`;
      }
    } else if (cur.doc) {
      const seg = cur.doc.segments[CR.segAt(cur.doc.segments, t)];
      text = `<b>${fmtT(t)}</b>${tn}<span class="now-claim">${esc(seg ? seg.text : '')}</span>`;
    }
    if (!text) text = `<b>${fmtT(t)}</b><span class="now-claim">${esc(calm(v.cleanTitle))}</span>`;
    const snapBtn = nb.dataset.snap === 'peek'
      ? `<button class="ib" type="button" data-act="snap" data-snap="half" aria-label="Subir el cuaderno">${icon('chevron-up')}</button>`
      : `<button class="ib" type="button" data-act="snap" data-snap="peek" aria-label="Bajar el cuaderno y ver la ficha">${icon('chevron-down')}</button>`;
    nowEl.innerHTML = `<button class="now-play" id="now-play" type="button" data-act="toggle" aria-label="${playing ? 'Pausar' : 'Reproducir'}">${icon(playing ? 'pause' : 'play')}</button><p class="now-text">${text}</p><span class="now-acts">${go}${snapBtn}</span>`;
  }

  /* Documento anotado: párrafos del creador, lo extraído subrayado y notas del sistema al margen. */
  function placeNotes() {
    const doc = cur.doc;
    const blocks = CR.blocks(doc.segments, 24);
    cur.blocks = blocks;
    cur.notesAt = new Map();
    const quotes = new Map();
    (doc.claims || []).forEach((c) => {
      if (c.t == null) return;
      const si = CR.segAt(doc.segments, c.t);
      const bi = blocks.findIndex((b) => si >= b.i0 && si <= b.i1);
      if (bi < 0) return;
      cur.notesAt.set(bi, (cur.notesAt.get(bi) || []).concat(c));
      const full = CR.claim(doc, c.id);
      (full ? full.evidences : []).filter((e) => e.origen === 'transcripcion' && e.cita).forEach((e) => {
        const eb = blocks.findIndex((b) => { const s = CR.segAt(doc.segments, e.inicio_s); return s >= b.i0 && s <= b.i1; });
        if (eb >= 0) quotes.set(eb, (quotes.get(eb) || []).concat({ cita: e.cita, c: c.id }));
      });
    });
    cur.quotesAt = quotes;
  }
  function pulseStrip() {
    const el = document.getElementById('nb-pulse');
    if (!el || !cur.video || !cur.video.tone.wave) return;
    const dur = cur.video.dur || 1;
    const marks = (cur.doc && cur.doc.claims ? cur.doc.claims : []).filter((c) => c.t != null && c.pol !== 'neutra').map((c) => ({ x: c.t / dur, cls: CR.TONE[c.pol].cls }));
    el.innerHTML = `${CR.waveSvg(cur.video.tone.wave, { w: 300, h: 30, gap: 1, marks, playhead: (player ? player.time() : 0) / dur })}`;
  }
  function movePlayhead(t) {
    const line = document.querySelector('#nb-pulse .wv-head');
    if (!line || !cur.video) return;
    const x = (t / (cur.video.dur || 1)) * 300;
    line.setAttribute('x1', x); line.setAttribute('x2', x);
  }
  function markText(text, bi) {
    let html = esc(text);
    const qs = (cur.quotesAt.get(bi) || []).slice().sort((a, b) => b.cita.length - a.cita.length);
    const used = new Set();
    qs.forEach(({ cita, c }) => {
      if (used.has(c)) return;
      const needle = esc(cita.replace(/\s+/g, ' ').trim());
      const probe = [needle, needle.slice(0, 60)].find((n) => n.length > 12 && html.toLowerCase().includes(n.toLowerCase()));
      if (!probe) return;
      const i = html.toLowerCase().indexOf(probe.toLowerCase());
      if (html.slice(0, i).lastIndexOf('<mark') > html.slice(0, i).lastIndexOf('</mark>')) return;
      const cl = cur.doc.claimsById[c];
      const tc = CR.TONE[cl ? cl.pol : 'neutra'].cls;
      html = `${html.slice(0, i)}<mark class="hl hl-${tc}" data-act="goto-note" data-c="${c}" title="Ver la nota: lectura ${esc(CR.TONE[cl ? cl.pol : 'neutra'].label.toLowerCase())}">${html.slice(i, i + probe.length)}</mark>${html.slice(i + probe.length)}`;
      used.add(c);
    });
    const b = cur.blocks[bi];
    if (b) {
      const pairs = [];
      for (let k = b.i0; k <= b.i1; k++) (cur.doc.segWhy[k] || []).forEach((pr) => { if (!pairs.some((x) => x[0] === pr[0])) pairs.push(pr); });
      html = CR.markTriggers(html, pairs);
    }
    if (ui.txq) {
      const n = ui.txq.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      html = html.replace(/(<[^>]+>)|([^<]+)/g, (m, tag, txt) => (tag ? tag : txt.replace(new RegExp(`(${esc(n)})`, 'gi'), '<mark class="q">$1</mark>')));
    }
    return html;
  }
  function noteHtml(c) {
    const full = CR.claim(cur.doc, c.id);
    const open = cur.open.has(c.id);
    const key = `c:${cur.id}:${c.id}`;
    let more = '';
    if (open && full) {
      const a = cur.doc.analysis;
      const m = full.mercado;
      const chains = a.cadena_narrativa.filter((ch) => ch.afirmacion_ids.includes(c.id));
      const scen = a.escenarios.filter((s) => s.afirmacion_ids.includes(c.id));
      const pend = a.verificaciones_pendientes.filter((p) => p.afirmacion_ids.includes(c.id));
      const kv = (k, val) => (val ? `<dt>${k}</dt><dd>${esc(val)}</dd>` : '');
      more = `<div class="note-more">
        <p class="small muted">${L.verif[c.verif]} · convicción ${CR.nivel(c.conv).toLowerCase()}${c.pol !== 'neutra' && c.polWhy.length ? ` · se lee ${esc(CR.TONE[c.pol].label.toLowerCase())} ${CR.toneWhy(c.polWhy)}` : ''}</p>
        ${c.assets.length ? `<p class="note-assets">${c.assets.map((a) => `<button class="note-chip" type="button" data-act="asset" data-id="${a}">${esc(CR.topicName(a))}</button>`).join('')}</p>` : ''}
        <div><h5>Lo que dice ${esc(cur.video.channel.name)}</h5>${full.evidences.map((e) => `<blockquote>«${esc(e.cita || e.observacion || '')}»</blockquote><p class="small muted">${e.origen === 'titulo' ? 'Título del vídeo' : `${L.origen[e.origen]}${e.inicio_s != null ? ` · ${fmtT(e.inicio_s)}` : ''}`}${e.observacion && e.cita ? ` · Nota: ${esc(e.observacion)}` : ''}</p>`).join('')}</div>
        ${m ? `<div><h5>Extraído por el sistema</h5><dl>${kv('Activo', m.activo_normalizado || m.activo_literal)}${kv('Postura', m.postura)}${kv('Plazo', m.horizonte_literal)}${kv('Condición', m.condicion)}${kv('Objetivo', m.objetivo)}${kv('Invalidación', m.invalidacion)}${kv('Catalizador', m.catalizador)}</dl></div>` : ''}
        <div><h5>Por qué «${L.verif[c.verif].toLowerCase()}»</h5><p>${esc(full.justificacion)}</p></div>
        ${chains.map((ch) => `<div><h5>En el argumento · ${L.vinculo[ch.vinculo].toLowerCase()}</h5><p>${esc(ch.premisa)} → <b>${esc(ch.conclusion)}</b></p>${ch.supuesto ? `<p class="small" style="color:var(--pen)">Supuesto: ${esc(ch.supuesto)}</p>` : ''}</div>`).join('')}
        ${scen.length ? `<div><h5>Escenarios que la usan</h5>${scen.map((s) => `<p>${esc(s.nombre)} <span class="small muted">· ${L.plaus[s.plausibilidad].toLowerCase()}</span></p>`).join('')}</div>` : ''}
        ${pend.length ? `<div><h5>Pendiente de verificar</h5>${pend.map((p) => `<p>${esc(p.pregunta)}</p>`).join('')}</div>` : ''}
        <p class="note-ext">${icon('alert')}<span>Sin fuentes externas consultadas: que el vídeo no lo pruebe no lo hace falso.</span></p>
        <div class="note-actions"><button class="textbtn" type="button" data-act="share-note" data-c="${c.id}">${icon('share')} Compartir esta nota</button></div>
      </div>`;
    }
    return `<div class="note" id="note-${c.id}" ${kc(c.tipo)}>
      <p class="note-h">${mark(c.pol)}<span class="note-k">${L.tipo[c.tipo]}</span>${c.insinua ? '<span class="note-ins">insinuado</span>' : ''}</p>
      <p class="note-text">${esc(c.text)}</p>
      <div class="note-actions">
        ${c.t != null ? `<button class="textbtn" type="button" data-act="seek" data-t="${c.t}">${icon('play', 'i-s')} ${fmtT(c.t)}</button>` : ''}
        <button class="textbtn" type="button" data-act="expand" data-c="${c.id}" aria-expanded="${open}">${open ? 'Menos' : 'Más'} ${icon(open ? 'chevron-up' : 'chevron-down')}</button>
        <button class="ib note-save" type="button" data-act="save-note" data-c="${c.id}" aria-label="${saved.has(key) ? 'Quitar la marca' : 'Marcar esta nota'}">${icon(saved.has(key) ? 'bookmark-fill' : 'bookmark', 'i-s')}</button>
      </div>
      ${more}
    </div>`;
  }
  function rowHtml(b, i, withNotes) {
    const notes = cur.notesAt.get(i) || [];
    const bt = CR.blockTone(cur.doc, b.i0, b.i1);
    const T = CR.TONE[bt.pol];
    return `<div class="doc-row tone-row-${T.cls}" data-i="${i}">
      <button class="doc-t" type="button" data-act="seek" data-t="${b.start}" aria-label="Escuchar desde ${fmtT(b.start)}. Tramo ${T.label.toLowerCase()}">${fmtT(b.start)}${bt.pol !== 'neutra' ? mark(bt.pol) : ''}</button>
      <div class="doc-main"><p class="doc-text">${markText(b.text, i)}</p>
        ${withNotes ? notes.map(noteHtml).join('') : notes.map((c) => (cur.open.has(c.id) ? noteHtml(c) : `<button class="marker" type="button" data-act="expand" data-c="${c.id}" ${kc(c.tipo)}>${mark(c.pol)}${L.tipo[c.tipo]}</button>`)).join('')}
      </div>
    </div>`;
  }
  function destiladoHtml() {
    const out = [];
    let gap = [];
    const flush = () => {
      if (!gap.length) return;
      const first = cur.blocks[gap[0]], last = cur.blocks[gap[gap.length - 1]];
      const secs = Math.max(1, Math.round(last.end - first.start));
      out.push(`<div class="gap"><button type="button" data-act="open-gap" data-from="${gap[0]}" data-to="${gap[gap.length - 1]}">${CR.fmtDur(secs)} sin hallazgos · mostrar el texto</button></div>`);
      gap = [];
    };
    cur.blocks.forEach((b, i) => {
      if ((cur.notesAt.get(i) || []).length || cur.gaps.has(i)) { flush(); out.push(rowHtml(b, i, true)); } else gap.push(i);
    });
    flush();
    return out.join('');
  }
  const CARDS = ['Resumen', 'Cadena del argumento', 'Escenarios', 'Qué vigilar', 'Preguntas abiertas', 'Técnicas narrativas', 'Ocho aspectos', 'Alcance y límites'];
  function cardHtml(n) {
    const a = cur.doc.analysis;
    const tchips = (ids) => `<div class="tchips">${ids.map((e) => cur.doc.evidenceById[e]).filter((e) => e && e.inicio_s != null).map((e) => `<button class="tchip" type="button" data-act="seek" data-t="${e.inicio_s}">${icon('play', 'i-s')}${fmtT(e.inicio_s)}</button>`).join('')}</div>`;
    const r = a.resumen;
    const at = cur.doc.aTone || { resumen: {}, cadena: [], escenarios: [] };
    const tt = (k) => (at.resumen[k] && at.resumen[k] !== 'neutra' ? chip(at.resumen[k], { short: true }) : '');
    const bodies = [
      () => `<div class="layer"><h4>Tesis ${tt('tesis_principal')}</h4><p>${esc(r.tesis_principal)}</p></div>
        <div class="layer c"><h4>Lo que dice el creador ${tt('mensaje_explicito')}</h4><p>${esc(r.mensaje_explicito)}</p></div>
        <div class="layer s"><h4>Lo que intenta hacer pensar (interpretación) ${tt('narrativa_sugerida')}</h4><p>${esc(r.narrativa_sugerida)}</p></div>
        <div class="layer e"><h4>Lo que se puede demostrar con lo recibido</h4><p>${esc(r.respaldo_demostrable)}</p></div>
        <div class="layer"><h4>Conclusión provisional</h4><p>${esc(r.conclusion_provisional)}</p></div>`,
      () => a.cadena_narrativa.map((ch, k) => `<div class="item flow">${at.cadena[k] && at.cadena[k] !== 'neutra' ? chip(at.cadena[k], { short: true }) : ''}<p>${esc(ch.premisa)}</p><p class="arrow">${icon('arrow-right', 'i-s')} ${L.vinculo[ch.vinculo]}</p><p><b>${esc(ch.conclusion)}</b></p>${ch.supuesto ? `<small class="pen">Supuesto: ${esc(ch.supuesto)}</small>` : ''}${tchips(ch.evidencia_ids)}</div>`).join(''),
      () => a.escenarios.map((s, k) => `<div class="item"><p>${at.escenarios[k] ? chip(at.escenarios[k], { short: true }) : ''} <span class="${s.origen === 'analista' ? 'tag-pen' : 'tag-ink'}">${L.origenEsc[s.origen]}</span> <span class="tag-ink">${L.plaus[s.plausibilidad]}</span></p><p style="margin-top:8px"><b>${esc(s.nombre)}</b></p><p class="small" style="margin-top:4px;color:var(--ink-2)">${esc(s.mecanismo)}</p><small>A favor: ${esc(s.senales_a_favor.join(' · '))}</small><small>En contra: ${esc(s.senales_en_contra.join(' · '))}</small><small>Invalidación: ${esc(s.invalidacion)}</small><small>${s.probabilidad == null ? 'Sin probabilidad numérica: no hay método que la respalde.' : `Probabilidad ${s.probabilidad}`}</small></div>`).join(''),
      () => a.seguimiento.map((s) => `<div class="item"><p>${esc(s.que_observar)}</p><small>${esc(s.criterio)}</small>${s.plazo ? `<small>Plazo: ${esc(s.plazo)}</small>` : ''}</div>`).join(''),
      () => a.verificaciones_pendientes.map((p) => `<div class="item"><p>${esc(p.pregunta)}</p><small>${L.prioridad[p.prioridad]} · ${esc(p.fuente_o_dato_buscado)}</small></div>`).join(''),
      () => a.tecnicas_narrativas.map((t) => `<div class="item"><p><b>${esc(t.tecnica)}</b></p><p class="small" style="color:var(--ink-2);margin-top:4px">${esc(t.mecanismo)}</p><small class="pen">Otra lectura: ${esc(t.explicacion_alternativa)}</small>${tchips(t.evidencia_ids)}</div>`).join(''),
      () => Object.entries(a.ocho_aspectos).map(([k, v]) => `<div class="item"><p><b>${L.aspectos[k]}</b> <span class="small muted">· ${v.estado === 'evaluado' ? 'evaluado' : v.estado === 'parcial' ? 'parcial' : 'no evaluable'}</span></p>${v.hallazgos.map((h) => `<p class="small" style="margin-top:6px">${esc(h.observacion)}</p><small class="pen">${esc(h.interpretacion)}</small>`).join('')}</div>`).join(''),
      () => `<ul>${a.alcance.limitaciones.map((x) => `<li class="item"><p class="small">${esc(x)}</p></li>`).join('')}</ul><p class="small muted" style="margin-top:8px">${esc(a.alcance.alcance_verificacion)}</p>`,
    ];
    return `<article class="card-page" aria-live="polite"><p class="card-n">Ficha ${n + 1} de ${CARDS.length}</p><h3>${CARDS[n]}</h3>${bodies[n]()}</article>`;
  }
  function renderNotebook() {
    const { doc, video } = cur;
    renderLenses();
    if (!doc) return;
    placeNotes();
    pulseStrip();
    cur.nowBlock = -1;
    let html = '';
    if (cur.lens === 'analisis') {
      html = doc.analysis
        ? `<div class="cards-nav"><button class="ib" type="button" data-act="card" data-d="-1" aria-label="Ficha anterior"${cur.card === 0 ? ' disabled' : ''}>${icon('chevron-left')}</button>
            <label class="sr" for="card-sel">Ir a la ficha</label><select id="card-sel">${CARDS.map((c, i) => `<option value="${i}"${i === cur.card ? ' selected' : ''}>${i + 1}. ${c}</option>`).join('')}</select>
            <button class="ib" type="button" data-act="card" data-d="1" aria-label="Ficha siguiente"${cur.card === CARDS.length - 1 ? ' disabled' : ''}>${icon('chevron-right')}</button></div>${cardHtml(cur.card)}`
        : pendingNb(video);
    } else if (cur.lens === 'transcripcion') {
      html = `<div class="nb-tools"><label class="field">${icon('search')}<span class="sr">Buscar en el texto</span><input id="txq" type="search" placeholder="Buscar en el texto" value="${esc(ui.txq)}" autocomplete="off" enterkeyhint="search"></label></div>
        ${cur.blocks.map((b, i) => rowHtml(b, i, false)).join('')}`;
    } else {
      html = doc.analysis ? destiladoHtml() : pendingNb(video);
    }
    nbBody.innerHTML = html + (cur.lens !== 'analisis' ? `<button class="pill follow-btn" type="button" data-act="follow" id="follow" hidden>${icon('target')} Volver al minuto actual</button>` : '');
    const sel = document.getElementById('card-sel');
    if (sel) sel.addEventListener('change', () => { cur.card = Number(sel.value); renderNotebook(); });
    const input = document.getElementById('txq');
    if (input) input.addEventListener('input', CR.debounce(() => {
      ui.txq = input.value.trim();
      CR.$$('.doc-row', nbBody).forEach((row) => { const i = Number(row.dataset.i); row.querySelector('.doc-text').innerHTML = markText(cur.blocks[i].text, i); });
      const first = nbBody.querySelector('mark.q');
      if (first) { ui.follow = false; first.scrollIntoView({ block: 'center' }); }
    }, 220));
    if (player) { syncDoc(player.time(), true); renderNow(player.time()); }
  }
  function pendingNb(v) {
    const names = topicNames(v, 4);
    return `<div class="nb-pending"><h3>Aún sin notas</h3><p>Este vídeo no se ha analizado: no hay afirmaciones ni interpretaciones. El texto completo está en la lente «Texto»${names.length ? `, y en él se nombra ${esc(joinEs(names))}` : ''}.</p>
      <div style="margin-top:12px"><button class="pill pill-solid" type="button" data-act="lens" data-lens="transcripcion">${icon('text')} Leer el texto</button></div></div>`;
  }
  let autoScrolling = false;
  function syncDoc(t, force) {
    if (!cur.blocks.length || cur.lens === 'analisis') return;
    const si = CR.segAt(cur.doc.segments, t);
    const bi = cur.blocks.findIndex((b) => si >= b.i0 && si <= b.i1);
    if (bi === cur.nowBlock && !force) return;
    cur.nowBlock = bi;
    CR.$$('.doc-row.is-now', nbBody).forEach((el) => el.classList.remove('is-now'));
    const row = nbBody.querySelector(`.doc-row[data-i="${bi}"]`);
    if (row) {
      row.classList.add('is-now');
      if (ui.follow && player && player.playing && nb.dataset.snap !== 'peek') {
        autoScrolling = true;
        row.scrollIntoView({ block: 'center', behavior: CR.reduced() ? 'auto' : 'smooth' });
        setTimeout(() => { autoScrolling = false; }, 700);
      }
    }
  }
  const stopFollow = () => {
    if (autoScrolling || !screen || !screen.startsWith('v:')) return;
    ui.follow = false;
    const b = document.getElementById('follow');
    if (b) b.hidden = false;
  };
  nbBody.addEventListener('wheel', stopFollow, { passive: true });
  nbBody.addEventListener('touchmove', stopFollow, { passive: true });

  function gotoNote(id) {
    if (cur.lens === 'analisis' || (cur.lens === 'transcripcion' && !cur.open.has(id))) {
      cur.open.add(id);
      if (cur.lens === 'analisis') cur.lens = 'destilado';
      renderNotebook();
    }
    if (nb.dataset.snap === 'peek') setSnap('half');
    const el = document.getElementById(`note-${id}`);
    if (el) { ui.follow = false; const f = document.getElementById('follow'); if (f) f.hidden = false; el.scrollIntoView({ block: 'center', behavior: CR.reduced() ? 'auto' : 'smooth' }); }
  }
  function applyVideoQuery(q) {
    if (q.lens && q.lens !== cur.lens) { cur.lens = q.lens; renderNotebook(); }
    if (q.n && cur.doc && cur.doc.claimsById[q.n]) {
      cur.open.add(q.n);
      renderNotebook();
      requestAnimationFrame(() => gotoNote(q.n));
    }
  }

  /* ---------- hilos ---------- */
  function axisHtml(th) {
    const from = new Date(idx.period.from).getTime(), to = new Date(idx.period.to).getTime();
    const pos = (iso) => ((new Date(iso).getTime() - from) / Math.max(1, to - from)) * 100;
    return `<div class="axis" aria-hidden="true">${th.sources.map((s) => { const v = idx.videosById[s.v]; return `<i class="${s.claims.length ? 'full' : ''} ax-${CR.TONE[v.tone.label].cls}" style="left:${pos(v.pub)}%" title="${esc(v.channel.name)}, ${fmtDate(v.pub)}: tono ${CR.TONE[v.tone.label].label.toLowerCase()}"></i>`; }).join('')}<span class="first" style="left:0">${fmtDate(idx.period.from)}</span><span class="last" style="left:100%">${fmtDate(idx.period.to)}</span></div>`;
  }
  function forkHtml(p) {
    const A = idx.claimsByKey[`${p.a.v}:${p.a.id}`], B = idx.claimsByKey[`${p.b.v}:${p.b.id}`];
    const va = idx.videosById[p.a.v], vb = idx.videosById[p.b.v];
    const title = p.kind === 'cambio' ? `Aquí cambia la postura sobre ${CR.topicName(p.asset)}` : `Aquí se repite la idea sobre ${CR.topicName(p.asset)}`;
    return `<div class="fork"><h4>${esc(title)} · ${L.hz[p.hz].toLowerCase()}</h4>
      <p>${p.kind === 'cambio' ? 'Detectado por reglas: mismo activo y plazo, postura contraria. El sistema no decide quién acierta.' : 'Lo repite el mismo creador: es repetición, no una prueba independiente.'}</p>
      <div class="sides">
        <div class="side side-${CR.TONE[A.pol].cls}"><b>Antes · ${fmtDate(va.pub)} · ${fmtT(A.t)}</b>${chip(A.pol, { short: true })}<blockquote>«${esc(CR.clip(A.quote || A.text, 140))}»</blockquote><a class="textbtn" href="#/v/${va.id}?t=${Math.floor(A.t || 0)}&n=${A.id}">${icon('play')} Escuchar</a></div>
        <div class="side side-${CR.TONE[B.pol].cls}"><b>Después · ${fmtDate(vb.pub)} · ${fmtT(B.t)}</b>${chip(B.pol, { short: true })}<blockquote>«${esc(CR.clip(B.quote || B.text, 140))}»</blockquote><a class="textbtn" href="#/v/${vb.id}?t=${Math.floor(B.t || 0)}&n=${B.id}">${icon('play')} Escuchar</a></div>
      </div></div>`;
  }
  function renderThread(id) {
    const th = idx.themesById[id];
    if (!th) { page.innerHTML = `<div class="empty"><h3>Narrativa no encontrada</h3><a class="pill" href="#/activos?tab=narrativas">Ver narrativas</a></div>`; return; }
    const sources = th.sources.slice().sort((a, b) => idx.videosById[a.v].pub.localeCompare(idx.videosById[b.v].pub));
    const forksAfter = new Map();
    th.contrasts.forEach((i) => { const p = idx.contrasts[i]; forksAfter.set(p.b.v, (forksAfter.get(p.b.v) || []).concat(p)); });
    page.innerHTML = `
      <div class="pad"><a class="textbtn" href="#/activos?tab=narrativas">${icon('arrow-left')} Narrativas</a>
        <h1 class="title-xl" style="margin-top:4px">${esc(th.title)}</h1><p class="lede">${esc(th.about)}</p>
        <p class="note-ext" style="margin-top:12px">${icon('alert')}<span>${CR.plural(th.videoCount, 'vídeo lo trata', 'vídeos lo tratan')}; ninguna fuente externa lo respalda todavía. Repetir una idea no la prueba.</span></p></div>
      <div class="thread" style="margin-top:14px">
        ${sources.map((s) => {
          const v = idx.videosById[s.v];
          const claims = s.claims.map((c) => idx.claimsByKey[`${s.v}:${c}`]).filter(Boolean);
          return `<div class="t-entry${claims.length ? ' full' : ''}">
            <p class="meta">${fmtDate(v.pub, { time: true })} · ${esc(v.channel.name)} · ${claims.length ? 'analizado' : 'solo transcripción'}</p>
            <h4><a href="#/v/${v.id}">${esc(v.cleanTitle)}</a></h4>
            ${claims.slice(0, 3).map((c) => `<div class="t-frag">${chip(c.pol, { short: true, insinua: c.insinua })}${c.quote ? `<blockquote class="q-${CR.TONE[c.qPol].cls}">«${esc(c.quote)}»</blockquote>` : ''}<p class="pen">${L.tipo[c.tipo]}: ${esc(c.text)}</p><a class="textbtn" href="#/v/${v.id}?t=${Math.floor(c.t || 0)}&n=${c.id}">${icon('play')} ${c.t != null ? fmtT(c.t) : 'Título'}</a></div>`).join('')}
            ${claims.length > 3 ? `<p class="small muted" style="margin-top:6px">${CR.plural(claims.length - 3, 'nota más', 'notas más')} en el cuaderno del vídeo.</p>` : ''}
            ${!claims.length ? s.frags.map((f) => `<div class="t-frag">${chip(f.pol, { short: true })}<blockquote class="q-${CR.TONE[f.pol].cls}">«${esc(f.text)}»</blockquote><a class="textbtn" href="#/v/${v.id}?t=${Math.floor(f.t)}">${icon('play')} ${fmtT(f.t)}</a></div>`).join('') : ''}
          </div>${(forksAfter.get(s.v) || []).map(forkHtml).join('')}`;
        }).join('')}
      </div>`;
  }

  /* ---------- marcadores con nota propia ---------- */
  function renderSaved() {
    const list = saved.all();
    const notes = store.get('notes', {});
    page.innerHTML = `
      <div class="pad"><h1 class="title-xl">Marcadores</h1><p class="lede">Vuelve al segundo exacto y apunta lo que piensas. Todo se queda en este dispositivo.</p></div>
      ${list.length ? list.map((s) => `<article class="saved">
        <p class="small muted">${s.pol ? mark(s.pol) + ' ' : ''}${esc(s.kind)} · ${esc(s.sub || '')}</p>
        ${s.quote ? `<blockquote>«${esc(CR.clip(s.quote, 180))}»</blockquote>` : ''}
        <p style="margin-top:6px;${s.quote ? 'color:var(--pen)' : 'font-family:var(--serif);font-size:17px'}">${esc(s.title)}</p>
        <label class="sr" for="n-${esc(s.key)}">Tu nota</label>
        <textarea id="n-${esc(s.key)}" data-note="${esc(s.key)}" placeholder="Tu nota: qué te convence, qué falta comprobar…">${esc(notes[s.key] || '')}</textarea>
        <div class="saved-foot"><a class="textbtn" href="${esc(s.href)}">${icon('play')} Volver a este punto</a><button class="textbtn" type="button" data-act="unsave" data-key="${esc(s.key)}" style="color:var(--muted)">Quitar</button></div>
      </article>`).join('') : `<div class="empty"><h3>Sin marcadores</h3><p>En cualquier nota del cuaderno pulsa «Marcar». Aquí podrás volver a ese segundo y escribir tu propia nota.</p><a class="pill" href="#/v/${idx.analyzed[0].id}">${icon('book')} Abrir el último cuaderno</a></div>`}`;
    CR.$$('textarea[data-note]', page).forEach((ta) => ta.addEventListener('input', CR.debounce(() => {
      const all = store.get('notes', {});
      all[ta.dataset.note] = ta.value;
      store.set('notes', all);
    }, 300)));
  }

  /* ---------- búsqueda, estados, datos ---------- */
  function renderSearch(q) {
    page.innerHTML = `<div class="search-box"><a class="ib" href="#/" aria-label="Volver a la bitácora">${icon('arrow-left')}</a><label class="field">${icon('search')}<span class="sr">Buscar</span><input id="q" type="search" placeholder="Vídeos, notas, activos, hilos…" value="${esc(q)}" autocomplete="off" enterkeyhint="search"></label></div><div id="res"></div>`;
    const input = document.getElementById('q');
    const run = () => {
      const val = input.value.trim();
      CR.go(['buscar'], { q: val }, { replace: true });
      const out = document.getElementById('res');
      if (!val) { out.innerHTML = `<div class="empty"><h3>¿Qué buscas?</h3><p>Prueba «trampa», «Ethereum» o «28 de octubre».</p></div>`; return; }
      const r = CR.search(val);
      const grp = (t, items) => (items.length ? `<h2 class="res-h">${t}</h2>${items.join('')}` : '');
      out.innerHTML = grp('Vídeos', r.videos.slice(0, 8).map((v) => `<a class="res" href="#/v/${v.id}"><p style="font-family:var(--serif)">${esc(calm(v.cleanTitle))}</p><small>${mark(v.tone.label)} ${esc(v.channel.name)} · ${fmtDate(v.pub)}</small></a>`))
        + grp('Notas del análisis', r.claims.slice(0, 10).map((c) => { const v = idx.videosById[c.v]; return `<a class="res" href="#/v/${v.id}?t=${Math.floor(c.t || 0)}&n=${c.id}"><p style="color:var(--pen)">${esc(c.text)}</p><small>${mark(c.pol)} ${L.tipo[c.tipo]} · ${esc(v.channel.name)} · ${fmtT(c.t)}</small></a>`; }))
        + grp('Activos', r.topics.slice(0, 8).map((t) => `<a class="res" href="#/f/${t.id}"><p>${esc(t.name)}</p><small>${L.section[t.section]} · ${CR.plural(t.vc, 'vídeo', 'vídeos')}</small></a>`))
        + grp('Hilos', r.themes.map((t) => `<a class="res" href="#/n/${t.id}"><p>${esc(t.title)}</p></a>`))
        + `<div class="pad" style="margin-top:18px"><button class="pill" type="button" data-act="search-tx" style="width:100%">${icon('text')} Buscar también en las transcripciones</button></div><div id="txres"></div>`;
    };
    input.addEventListener('input', CR.debounce(run, 200));
    run();
    input.focus();
  }
  async function searchTx() {
    const val = (document.getElementById('q') || {}).value || '';
    const out = document.getElementById('txres');
    out.innerHTML = '<div class="pad"><div class="skel" style="height:64px;margin-top:12px"></div></div>';
    const hits = await CR.searchTranscripts(val);
    out.innerHTML = hits.length ? `<h2 class="res-h">En las transcripciones</h2>${hits.map((h) => { const v = idx.videosById[h.v]; return `<a class="res" href="#/v/${v.id}?t=${Math.floor(h.t)}&lens=transcripcion"><blockquote>«${esc(h.text)}»</blockquote><small>${esc(v.channel.name)} · ${fmtT(h.t)} · ${esc(CR.clip(v.cleanTitle, 44))}</small></a>`; }).join('')}` : `<p class="pad small muted" style="margin-top:12px">Ninguna transcripción contiene «${esc(val)}».</p>`;
  }
  function renderStates() {
    page.innerHTML = `<div class="pad"><a class="textbtn" href="#/datos">${icon('arrow-left')} Cómo leer esto</a><h1 class="title-xl" style="margin-top:4px">Estados</h1><p class="lede">Cómo aparece cada vídeo según lo que el sistema haya podido hacer. «Ejemplo» indica que ahora mismo no hay ninguno así.</p></div>
      ${CR.STATES.map((s, i) => `<article class="state-row"><h3>${esc(s.title)}<span class="tag-s">${s.real ? 'Real' : 'Ejemplo'}</span></h3><p>${esc(s.body)}</p>
        <div class="entry-who"><span class="dots" aria-hidden="true">${[0, 1, 2, 3].map((k) => `<i class="${k < [0, 1, 4, 0, 4, 2][i] ? 'on' : ''}"></i>`).join('')}</span><span>${esc(s.chip)}</span></div>
        <button class="pill" type="button" data-act="demo" style="margin-top:10px">${esc(s.action)}</button></article>`).join('')}`;
  }
  function renderAbout() {
    const a = idx.analyzed;
    page.innerHTML = `<div class="pad about">
      <h1 class="pg-h1">Cómo leer esto</h1>
      <ul class="legend">
        <li>${mark('alcista')}<span><b>Alcista.</b> El discurso empuja al alza.</span></li>
        <li>${mark('bajista')}<span><b>Bajista.</b> Empuja a la baja.</span></li>
        <li>${mark('mixta')}<span><b>Mixto.</b> Hay señales en los dos sentidos.</span></li>
        <li>${mark('neutra')}<span><b>Sin tono.</b> No hay señales claras.</span></li>
      </ul>
      <p class="lede">El titular de cada día compara su proporción de señales al alza con la del día anterior que tuvo vídeos.</p>
      <p class="lede">${esc(idx.method.tone)}</p>
      <p class="lede">${idx.videos.length} vídeos del ${fmtDate(idx.period.from)} al ${fmtDate(idx.period.to)}; ${a.length} con análisis. ${esc(idx.method.external)}</p>
      <nav class="about-links"><a href="#/estados">Estados del procesamiento</a><a href="../index.html">Tablero de propuestas</a></nav>
      <p class="small muted" style="margin-top:16px">Foto de los datos: ${fmtDate(idx.generatedAt, { time: true })}.</p></div>`;
  }

  /* ---------- acciones ---------- */
  async function share(url, title, text) {
    const r = await CR.share({ title, text, url });
    if (r === 'copied') CR.toast('Enlace copiado');
    if (r === 'failed') CR.toast('No se pudo copiar el enlace');
  }
  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-act]');
    if (!el) {
      const menu = document.getElementById('filter-menu');
      if (menu && !menu.hidden && !e.target.closest('#filter-menu')) menu.hidden = true;
      return;
    }
    const act = el.dataset.act;
    switch (act) {
      case 'pip-close': if (player) player.pause(); pipClosed = true; setStage(); break;
      case 'index-close': closeIndex(); break;
      case 'back': CR.back('#/'); break;
      case 'snap': if (screen && screen.startsWith('v:')) setSnap(el.dataset.snap); else if (cur.id) CR.go(['v', cur.id]); break;
      case 'cycle': setSnap(nb.dataset.snap === 'half' ? 'full' : 'half'); break;
      case 'pulse': {
        const svg = el.querySelector('svg');
        if (!svg || !player || !cur.video) break;
        const r = svg.getBoundingClientRect();
        const ratio = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
        player.seek(ratio * (cur.video.dur || 0), { play: true });
        break;
      }
      case 'toggle': case 'pip-toggle': if (player) player.toggle(); break;
      case 'lens': cur.lens = el.dataset.lens; store.set('lens', cur.lens); renderNotebook(); nbBody.scrollTop = 0; break;
      case 'seek': if (player && screen && screen.startsWith('v:')) player.seek(Number(el.dataset.t), { play: true }); break;
      case 'expand': { const id = el.dataset.c; if (cur.open.has(id)) cur.open.delete(id); else cur.open.add(id); const top = nbBody.scrollTop; renderNotebook(); nbBody.scrollTop = top; break; }
      case 'goto-note': gotoNote(el.dataset.c); break;
      case 'open-gap': { for (let i = Number(el.dataset.from); i <= Number(el.dataset.to); i++) cur.gaps.add(i); const top = nbBody.scrollTop; renderNotebook(); nbBody.scrollTop = top; break; }
      case 'card': cur.card = Math.max(0, Math.min(CARDS.length - 1, cur.card + Number(el.dataset.d))); renderNotebook(); nbBody.scrollTop = 0; break;
      case 'follow': ui.follow = true; el.hidden = true; syncDoc(player.time(), true); { const row = nbBody.querySelector('.doc-row.is-now'); if (row) row.scrollIntoView({ block: 'center' }); } break;
      case 'asset': CR.go(['f', el.dataset.id]); break;
      case 'ln': {
        const i = Number(el.dataset.i), it = lnItems[i];
        if (!it) break;
        if (i === lnFocus) { CR.go(it.kind === 'v' ? ['v', it.v.id] : ['f', it.r.t.id]); break; }
        const track = document.querySelector('.ln-track');
        window.scrollTo({ top: track.getBoundingClientRect().top + window.scrollY + it.y - window.innerHeight * RET, behavior: reduced() ? 'auto' : 'smooth' });
        break;
      }
      case 'ficha-close': closeFicha(); break;
      case 'save-asset': {
        const t = idx.topicsById[el.dataset.id];
        const on = saved.toggle({ key: `a:${t.id}`, kind: 'Activo', sub: `${L.section[t.section]} · ${CR.plural(t.vc, 'vídeo', 'vídeos')}`, title: t.name, pol: CR.netSent(t.sent).pol, href: `#/f/${t.id}` });
        CR.toast(on ? `${t.name} guardado en tu colección` : 'Quitado de tu colección');
        CR.$$(`[data-act="save-asset"][data-id="${t.id}"]`).forEach((b) => { b.setAttribute('aria-pressed', String(on)); b.innerHTML = b.classList.contains('f-save') ? `${icon(on ? 'bookmark-fill' : 'bookmark')} ${on ? 'En tu colección' : 'Guardar en mi colección'}` : icon(on ? 'bookmark-fill' : 'bookmark'); });
        break;
      }
      case 'save-note': {
        const c = CR.claim(cur.doc, el.dataset.c);
        const on = saved.toggle({ key: `c:${cur.id}:${c.id}`, pol: c.pol, kind: `Nota · ${L.tipo[c.tipo]}`, sub: `${cur.video.channel.name} · ${fmtT(c.t)}`, title: c.text, quote: c.literal ? c.literal.cita : '', href: `#/v/${cur.id}?t=${Math.floor(c.t || 0)}&n=${c.id}` });
        CR.toast(on ? 'Nota marcada' : 'Marcador quitado', on ? { action: 'Ver', onAction: () => CR.go('#/guardados') } : {});
        const top = nbBody.scrollTop; renderNotebook(); nbBody.scrollTop = top;
        break;
      }
      case 'save-video': {
        const v = cur.video;
        const on = saved.toggle({ key: `v:${v.id}`, kind: 'Vídeo', sub: `${v.channel.name} · ${fmtDate(v.pub)}`, title: v.cleanTitle, href: `#/v/${v.id}` });
        CR.toast(on ? 'Vídeo marcado' : 'Marcador quitado');
        el.innerHTML = `${icon(on ? 'bookmark-fill' : 'bookmark')} ${on ? 'Marcado' : 'Marcar'}`;
        break;
      }
      case 'share-note': { const c = CR.claim(cur.doc, el.dataset.c); share(CR.linkTo(CR.hash(['v', cur.id], { t: Math.floor(c.t || 0), n: c.id })), cur.video.cleanTitle, `${L.tipo[c.tipo]} en ${fmtT(c.t)}: ${c.text}`); break; }
      case 'share-video': share(CR.linkTo(CR.hash(['v', cur.id], { t: Math.floor(player.time()) })), cur.video.cleanTitle, cur.video.cleanTitle); break;
      case 'unsave': saved.remove(el.dataset.key); renderSaved(); break;
      case 'search-tx': searchTx(); break;
      case 'demo': CR.toast('Ejemplo de estado: en el producto llevaría a esta acción.'); break;
      case 'reload': location.reload(); break;
      case 'retry-video': screen = null; route(CR.parseHash()); break;
      default: break;
    }
  });
  scrim.addEventListener('click', () => closeFicha());
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !ficha.hidden) { closeFicha(); return; }
    if (e.key !== 'Escape') return;
    if (!indexEl.hidden) closeIndex();
    const m = document.getElementById('filter-menu');
    if (m && !m.hidden) m.hidden = true;
  });

  const run = CR.onRoute(route);
  run();
})();

/* 1B · Bitácora — diario de vídeos, cuaderno arrastrable con transcripción anotada y vídeo flotante. */
(() => {
  'use strict';
  const { esc, fmtT, fmtDate, icon, L } = CR;
  const Radar = window.UraniaRadar;
  const Theses = window.UraniaTheses;
  const APP = 'b4';
  const store = CR.store(APP);
  const page = document.getElementById('page');
  const stage = document.getElementById('stage');
  const nb = document.getElementById('nb');
  const nbBody = document.getElementById('nb-body');
  const nowEl = document.getElementById('now');
  const lensesEl = document.getElementById('lenses');
  const indexEl = { hidden: true };
  const ficha = document.getElementById('ficha');
  const drawer = document.getElementById('drawer');
  const dscrim = document.getElementById('dscrim');
  const scrim = document.getElementById('scrim');

  let searchRouteKey = null;
  let idx = null;
  let player = null;
  let screen = null;
  let pipClosed = true;
  let videoOpen = false;
  let videoPinned = false;
  let signalMode = false, lastSignalSecond = -1;
  let playbackLoading = null, playbackRequest = 0;
  const scrolls = new Map();
  const cur = { id: null, video: null, doc: null, lens: 'sintesis', synthesisTab: 'conclusion', start: 0, blocks: [], nowBlock: -1, open: new Set(), gaps: new Set(), card: 0, notesAt: new Map() };
  const ui = { filter: store.get('filter', 'todo'), section: store.get('section', 'altcoins'), follow: true, txq: '', txmode: 'notas' };
  const FILTERS = { todo: 'Todo el archivo', alcistas: 'Tono alcista', bajistas: 'Tono bajista o mixto a la baja', contraste: 'El título no cuadra con el vídeo', analizados: 'Solo con análisis', largos: 'Vídeos largos', shorts: 'Shorts' };
  // Un filtro por creador de index.json: ningún canal queda fijado en el código.
  const filters = () => Object.assign({}, FILTERS, Object.fromEntries(idx.channels.map((c) => [c.slug, c.name])));
  const listNames = (names) => (names.length > 1 ? `${names.slice(0, -1).join(', ')} y ${names[names.length - 1]}` : names.join(''));
  const chip = (pol, o) => CR.toneChip(pol, o);
  const pct = (v) => (v.tone.share == null ? 'sin señales de tono' : `${Math.round(v.tone.share * 100)} % de las señales al alza`);

  const lowerFirst = (s) => (s ? s.charAt(0).toLowerCase() + s.slice(1) : s);
  const kc = (tipo) => `style="--kc: var(--k-${tipo})"`;
  const topicNames = (v, n) => Object.keys(v.topics).filter((t) => idx.topicsById[t]).slice(0, n).map((t) => idx.topicsById[t].name);
  const joinEs = (a) => (a.length <= 1 ? a.join('') : `${a.slice(0, -1).join(', ')} y ${a[a.length - 1]}`);
  const hhmm = (iso) => { const d = new Date(iso); return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`; };

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
      renderNow(player.time());
      if (s === 'paused' && cur.id && player.video?.id === cur.id) store.set('session', { v: cur.id, t: player.time() });
    });
    return player;
  }
  let lastSave = 0;
  function onTime(t) {
    if (!cur.video || player?.video?.id !== cur.id) return;
    if (Date.now() - lastSave > 3000) { lastSave = Date.now(); store.set('session', { v: cur.id, t }); }
    if (screen === `v:${cur.id}`) { renderNow(t); syncDoc(t); movePlayhead(t); }
  }
  function setStage() {
    const onVideo = screen && screen.startsWith('v:');
    stage.dataset.mode = cur.id && videoOpen && onVideo ? 'top' : cur.id && videoPinned && !pipClosed ? 'pip' : 'none';
    document.body.dataset.videoOpen = String(!!(onVideo && videoOpen));
    const signalOn = !!(onVideo && videoOpen && signalMode);
    document.body.dataset.signalMode = String(signalOn);
    const trigger = document.getElementById('signal-trigger');
    trigger.setAttribute('aria-pressed', String(signalOn));
    trigger.setAttribute('aria-label', signalOn ? 'Desactivar Signal mode y volver a lectura' : 'Activar Signal mode');
    const toggle = document.getElementById('video-toggle');
    if (toggle) { toggle.innerHTML = icon(videoOpen ? 'close' : 'play', 'i-s') + (videoOpen ? 'Cerrar video' : 'Ver video'); toggle.setAttribute('aria-expanded', String(videoOpen)); }
    const pin = document.getElementById('video-pin');
    if (pin) { pin.hidden = !videoOpen; pin.setAttribute('aria-pressed', String(videoPinned)); pin.textContent = videoPinned ? 'Desfijar' : 'Fijar al salir'; }
  }
  async function openPlayback(t = cur.start || 0, play = true) {
    const id = cur.id, v = cur.video, request = ++playbackRequest;
    if (!v) return;
    videoOpen = true; pipClosed = false; setSnap('half');
    const p = ensurePlayer();
    if (!p.video || p.video.id !== id) playbackLoading = p.load(v, { start: t });
    if (playbackLoading) await playbackLoading;
    if (request !== playbackRequest || cur.id !== id || screen !== `v:${id}` || !videoOpen) return;
    p.seek(t, { play });
  }

  /* ---------- cuaderno: alturas y arrastre ---------- */
  const SNAP_LABEL = { peek: 'Cuaderno recogido. Pulsa para abrirlo a media altura.', half: 'Cuaderno a media altura. Pulsa para ampliarlo.', full: 'Cuaderno ampliado. Pulsa para reducirlo.' };
  function setSnap(snap) {
    if (!videoOpen) snap = 'full';
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
      if (e.target.closest('button:not(.nb-grip), a, [role="radio"], details, input, select')) return;
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

  /* ---------- rutas ---------- */
  function saveScroll() {
    if (!screen) return;
    scrolls.set(screen, screen.startsWith('v:') ? nbBody.scrollTop : window.scrollY);
  }
  const DOCK = { '': 'explorar', f: 'explorar', n: 'explorar', diario: 'diario', v: 'diario', feed: 'feed' };
  let routeRequest = 0;
  async function route(r) {
    const request = ++routeRequest;
    const [a = '', b] = r.parts;
    if (a === 'guardados' || a === 'marcadores') { CR.go(['feed'], r.q, {replace:true}); return; }
    const key = a === 'v' ? `v:${b}` : a === 'f' || a === '' ? 'explorar' : a ? `${a}${b ? ':' + b : ''}` : 'explorar';
    if (a !== 'f') closeFicha(true);
    closeDrawer();
    if (screen === key) {
      if (a === 'feed' && feedRouteKey !== JSON.stringify(feedFilters(r.q))) renderFeed(r.q);
      if (a === 'v') applyVideoQuery(r.q);
      else if (key === 'explorar') { if (a === 'f') openFicha(b, r.q); else renderExplore(r.q, true); }
      else if (a === 'buscar' && searchRouteKey !== JSON.stringify({q:r.q.q || '',...radarFilters(r.q),literal:r.q.literal === '1'?'1':'0'})) renderSearch(r.q.q || '');
      return;
    }
    saveScroll();
    if (screen && screen.startsWith('v:') && a !== 'v' && !videoPinned && player) player.pause();
    screen = key;
    document.body.dataset.screen = a === 'v' ? 'video' : key === 'explorar' ? 'explorar' : a;
    nb.hidden = a !== 'v';
    CR.$$('.dock a').forEach((el) => { if (el.dataset.d === DOCK[a]) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current'); });
    if (a === 'feed') { await renderFeed(r.q); if (request !== routeRequest) return; setStage(); window.scrollTo(0,scrolls.get(key)||0); return; }
    if (!idx) {
      page.innerHTML = '<div class="pad"><div class="skel" style="height:44px;margin-top:12px"></div><div class="skel" style="height:200px;margin-top:18px"></div><div class="skel" style="height:64px;margin-top:12px"></div></div>';
      try { idx = await CR.load(); } catch (e) {
        if (request !== routeRequest) return;
        page.innerHTML = `<div class="err" role="alert"><h3>No se pudo abrir el archivo</h3><p>Falló la carga de los datos. Revisa la conexión y vuelve a intentarlo.</p><button class="pill" type="button" data-act="reload">${icon('refresh')} Reintentar</button></div>`;
        return;
      }
    }
    if (request !== routeRequest) return;
    if (a === 'v') await renderVideo(b, r.q);
    else if (a === 'n') renderThread(b);
    else if (a === 'diario') renderLog();
    else if (a === 'buscar') renderSearch(r.q.q || '');
    else if (a === 'estados') renderStates();
    else if (a === 'datos') renderAbout();
    else { renderExplore(a === 'f' ? {} : r.q); if (a === 'f') openFicha(b, r.q); }
    setStage();
    if (a !== 'v') window.scrollTo(0, scrolls.get(key) || 0);
  }

  /* Termómetro divergente: fuego hacia la izquierda (bajista), urania hacia la derecha (alcista).
     La aguja marca el neto en la misma escala que las barras: si solo hay fuego, queda en su punta. */
  function termo(sent, opts = {}) {
    const up = sent.alcista || 0, down = sent.bajista || 0, mix = sent.mixta || 0;
    const tot = up + down + mix;
    const pu = tot ? up / tot : 0, pd = tot ? down / tot : 0;
    const fmt = (n) => (Number.isInteger(n) ? n : n.toFixed(1));
    return `<span class="termo${opts.big ? ' big' : ''}${tot ? '' : ' is-empty'}" role="img" aria-label="${fmt(up)} señales alcistas y ${fmt(down)} bajistas${mix ? `, ${fmt(mix)} mixtas` : ''}" style="--pu:${pu.toFixed(3)};--pd:${pd.toFixed(3)};--net:${(0.5 + (pu - pd) / 2).toFixed(3)}">
      <span class="termo-tube"><span class="termo-fire"></span><span class="termo-urania"></span><span class="termo-zero"></span></span>${opts.needle && tot ? '<span class="termo-needle"></span>' : ''}${opts.bulbs ? `<span class="termo-bulb b-fire${pd > pu ? ' on' : ''}"></span><span class="termo-bulb b-urania${pu > pd ? ' on' : ''}"></span>` : ''}</span>`;
  }
  /* «5 alcistas · 1 bajista · 2 mixtas · 10 sin tono», con las mixtas solo si las hay. */
  function sentLine(s, words = ['alcista', 'alcistas', 'bajista', 'bajistas', 'mixta', 'mixtas']) {
    const n = (k) => s[k] || 0;
    return `<span class="t-up">${CR.plural(n('alcista'), words[0], words[1])}</span> · <span class="t-down">${CR.plural(n('bajista'), words[2], words[3])}</span>${n('mixta') ? ` · <span class="t-mix">${CR.plural(n('mixta'), words[4], words[5])}</span>` : ''} · ${n('neutra')} sin tono`;
  }
  function windowTone(vs) {
    let b = 0, r = 0;
    vs.forEach((v) => { b += v.tone.bull; r += v.tone.bear; });
    return { net: b + r ? (b - r) / (b + r) : 0, share: b + r ? b / (b + r) : null, pol: CR.toneLabel(b, r, 1.5), bull: b, bear: r };
  }
  function gaugeSvg() {
    const R = 78, cx = 100, cy = 98;
    const pt = (deg) => [cx + R * Math.cos((deg * Math.PI) / 180), cy - R * Math.sin((deg * Math.PI) / 180)];
    const arc = (a1, a2) => { const [x1, y1] = pt(a1), [x2, y2] = pt(a2); return `M${x1.toFixed(1)},${y1.toFixed(1)} A${R},${R} 0 0 1 ${x2.toFixed(1)},${y2.toFixed(1)}`; };
    return `<svg class="gauge" viewBox="0 0 200 112" aria-hidden="true"><path class="g-down" d="${arc(180, 121)}"/><path class="g-mix" d="${arc(119, 61)}"/><path class="g-up" d="${arc(59, 0)}"/><g class="g-needle-g"><line class="g-needle" x1="${cx}" y1="${cy}" x2="${cx}" y2="${cy - 64}"/></g><circle class="g-hub" cx="${cx}" cy="${cy}" r="6.5"/></svg>`;
  }
  function openDrawer() {
    if (!idx) return;
    const lastDay = new Date(idx.period.to);
    const recent = idx.videos.filter((v) => (lastDay - new Date(v.pub)) / 86400000 < 3);
    const w = windowTone(recent);
    const latest = idx.videos.filter((v) => v.tone.share != null).slice(0, 8);
    const tick = latest.map((v) => `<a class="tk" href="#/v/${v.id}"><span class="tk-wave">${CR.waveSvg(v.tone.wave, { w: 132, h: 34, gap: 1, label: `Sismógrafo de ${v.cleanTitle}` })}</span><span class="tk-meta"><b>${esc(v.channel.initials)}</b> ${fmtDate(v.pub)} ${chip(v.tone.label, { short: true })}</span></a>`).join('');
    document.getElementById('drawer-body').innerHTML = `
      <section class="d-card d-gauge" aria-label="Aguja del archivo">
        <p class="d-k">Aguja del archivo · últimos 3 días</p>
        ${gaugeSvg()}
        <p class="d-ends"><span class="t-down">Bajista</span><span class="t-up">Alcista</span></p>
        <p class="d-read">${chip(w.pol, w.pol === 'alcista' || w.pol === 'bajista' ? { str: CR.toneStrength(w.bull / 8, w.bear / 8) } : {})}<span>${w.share != null ? `${Math.round(w.share * 100)} % de las señales al alza` : 'Sin señales'} · ${CR.plural(recent.length, 'vídeo', 'vídeos')}</span></p>
      </section>
      <section class="d-card" aria-label="Termómetros por creador">
        <p class="d-k">Por creador</p>
        ${idx.channels.map((c) => { const cw = windowTone(recent.filter((v) => v.ch === c.slug)); return `<div class="d-row"><span class="d-name">${esc(c.name)}</span>${termo({ alcista: cw.bull, bajista: cw.bear }, { needle: true })}<span class="d-pct">${cw.share != null ? `${Math.round(cw.share * 100)} %` : '—'}</span></div>`; }).join('')}
      </section>
      <section class="d-card" aria-label="Sismógrafos de los últimos vídeos">
        <div class="d-k-row"><p class="d-k">En directo del archivo</p><button class="tk-toggle" type="button" data-act="ticker" aria-pressed="false">${icon('pause', 'i-s')}<span>Pausar</span></button></div>
        <div class="ticker" data-scroll-x><div class="ticker-track">${tick}<span class="ticker-dup" aria-hidden="true">${tick}</span></div></div>
      </section>`;
    drawer.hidden = false; dscrim.hidden = false;
    const g = drawer.querySelector('.g-needle-g');
    if (g) { g.style.transform = 'rotate(-90deg)'; requestAnimationFrame(() => requestAnimationFrame(() => { g.style.transform = `rotate(${(Math.max(-1, Math.min(1, w.net)) * 90).toFixed(1)}deg)`; })); }
    drawer.querySelector('[data-act="drawer-close"]').focus({ preventScroll: true });
  }
  function closeDrawer() { if (drawer.hidden) return; drawer.hidden = true; dscrim.hidden = true; }
  (function edgeSwipe() {
    let sx = null, sy = null;
    document.addEventListener('pointerdown', (e) => {
      const left = (window.innerWidth - Math.min(window.innerWidth, 480)) / 2;
      sx = drawer.hidden && screen && !screen.startsWith('v:') && e.clientX - left < 22 ? e.clientX : null;
      sy = e.clientY;
    });
    document.addEventListener('pointerup', (e) => {
      if (sx != null && e.clientX - sx > 64 && Math.abs(e.clientY - sy) < 50) openDrawer();
      sx = null;
    });
  })();

  /* ---------- explorar: secciones, filtros y ranking con tono (de la Nébula) ---------- */
  const SEC_TITLE = { altcoins: 'Altcoins mencionadas', macro: 'Macro en conversación', bolsa: 'Bolsa en conversación' };
  const SEC_THEMES = { altcoins: ['altcoins', 'btc-corto', 'liquidaciones'], macro: ['macro-alivio', 'fin-octubre'], bolsa: ['bolsa'] };
  function exState(q) {
    const st = Object.assign({ s: 'altcoins', tab: 'ranking', c: 'todos', p: 'todo', m: 'videos' }, store.get('ex2', {}), q || {});
    // Ranking fijo por vídeos. Migrar también preferencias y enlaces de versiones anteriores.
    st.m = 'videos';
    if (st.tab === 'narrativas') st.tab = 'tesis'; // enlaces antiguos: misma vista, con el nombre nuevo
    if (st.tab === 'insights') st.tab = 'ranking'; // Insights se retiró: su contenido útil vive en ranking, vídeo y método
    if (!['ranking', 'tesis'].includes(st.tab)) st.tab = 'ranking';
    store.set('ex2', { s: st.s, tab: st.tab, c: st.c, p: st.p, m: st.m });
    return st;
  }
  const exHash = (st, patch) => CR.hash([], Object.assign({ s: st.s, tab: st.tab, c: st.c, p: st.p, m: st.m }, patch));
  function inWindow(v, st) {
    return Radar.inWindow(v, st);
  }
  function rankRows(st) {
    return idx.topics.filter((t) => t.section === st.s).map((t) => {
      const vids = t.videos.filter((m) => inWindow(idx.videosById[m.v], st));
      const sent = { alcista: 0, bajista: 0, mixta: 0, neutra: 0 };
      vids.forEach((m) => Object.keys(sent).forEach((k) => { sent[k] += (m.sent || {})[k] || 0; }));
      const frags = vids.flatMap((m) => m.frags.map((f) => Object.assign({ v: m.v }, f)));
      return { t, vids, vc: vids.length, n: vids.reduce((a, m) => a + m.n, 0), cc: new Set(vids.map((m) => idx.videosById[m.v].ch)).size, sent, net: CR.netSent(sent), frags };
    }).filter((r) => r.vc > 0).sort((a, b) => {
      return b.vc - a.vc || b.n - a.n || a.t.id.localeCompare(b.t.id);
    });
  }
  function identity(image, fallback, cls = '') {
    const path = image && /^\.\.\/media\/identities\/[a-z0-9-]+\.(png|jpg|webp|svg)$/.test(image.path) ? image.path : null;
    return `<span class="identity ${cls}" aria-hidden="true"><span>${esc(fallback)}</span>${path ? `<img src="${esc(path)}" alt="" width="40" height="40" loading="lazy" decoding="async">` : ''}</span>`;
  }
  const symAv = (t) => identity(t.image, ({oro:'Au',dolar:'$',petroleo:'Oil',sp500:'S&P',nasdaq:'NDX',liquidez:'≈',bonos:'BND',tipos:'%',inflacion:'IPC',politica:'◎',etf:'ETF',meme:'◉'})[t.id] || (t.sym || t.name).slice(0, 4), 'sym-av');
  const creatorAv = (c) => identity(c.image, c.initials, 'creator-av');
  document.addEventListener('error', (e) => { if (e.target.matches && e.target.matches('.identity img, .post-avatar img')) e.target.remove(); }, true);
  const peak = (frags, pol) => frags.filter((f) => f.pol === pol).sort((a, b) => b.text.length - a.text.length)[0];
  function heroCard(r, st) {
    const up = peak(r.frags, 'alcista'), down = peak(r.frags, 'bajista');
    const pk = (f, k) => (f ? `<span class="pk pk-${k}">${icon(k === 'up' ? 'trend-up' : 'trend-down', 'i-s')}<span>«${esc(CR.clip(f.text, 110))}»</span><small>${esc(idx.videosById[f.v].channel.name)} · ${fmtT(f.t)}</small></span>` : '');
    return `<a class="hero" data-pol="${r.net.pol}" href="#/f/${r.t.id}">
      <span class="hero-top"><span class="hero-n">01</span>${symAv(r.t)}<span class="hero-name"><b>${esc(r.t.name)}</b><small>${esc(r.t.sym || L.section[r.t.section])} · ${CR.plural(r.cc, 'creador', 'creadores')}</small></span>${icon('arrow-up-right')}</span>
      <span class="hero-stats"><span><b>${r.vc}</b> ${r.vc === 1 ? 'vídeo' : 'vídeos'}</span><span><b>${r.n}</b> ${r.n === 1 ? 'mención' : 'menciones'}</span></span>
      <span class="hero-tone">${chip(r.net.pol)}${termo(r.sent, { big: true, needle: true, bulbs: true })}<small>${sentLine(r.sent)}</small></span>
      ${up || down ? `<span class="hero-peaks">${pk(up, 'up')}${pk(down, 'down')}</span>` : ''}
    </a>`;
  }
  function rkCount(r, st) {
    return `<span class="rk-count"><b>${r.vc}</b><small>${r.vc === 1 ? 'vídeo' : 'vídeos'}</small></span>`;
  }
  function rankList(rows, st) {
    if (!rows.length) return `<div class="empty"><h3>Sin menciones con estos filtros</h3><p>Prueba con todo el archivo o con todos los creadores.</p><a class="pill" href="${exHash(st, { c: 'todos', p: 'todo' })}">Quitar filtros</a></div>`;
    if (st.s === 'altcoins') return `<ol class="intent-list" aria-label="Altcoins por número de videos">${rows.map((r,i)=>`
      <li><a class="intent-row" data-asset="${esc(r.t.id)}" href="${fichaHref(r.t.id,st)}">
        <span class="rk-n">${String(i+1).padStart(2,'0')}</span>${symAv(r.t)}
        <span class="intent-name"><b>${esc(r.t.name)}</b><small>${esc(r.t.sym || '')}${r.t.sym ? ' · ' : ''}${CR.plural(r.cc,'creador','creadores')}</small></span>
        <span class="intent-videos"><b>${r.vc}</b><small>${r.vc===1?'video':'videos'}</small></span>
        <span class="intent-sides"><span class="t-up">${icon('trend-up','i-s')}<b>${r.sent.alcista}</b> ${r.sent.alcista===1?'alcista':'alcistas'}</span><span class="t-down">${icon('trend-down','i-s')}<b>${r.sent.bajista}</b> ${r.sent.bajista===1?'bajista':'bajistas'}</span></span>
        <span class="intent-meter">${termo({...r.sent,mixta:0},{needle:true})}</span>
        <small class="intent-context">${CR.plural(r.n,'mención','menciones')}${r.sent.mixta+r.sent.neutra ? ` · ${r.sent.mixta+r.sent.neutra} sin dirección clara` : ''}</small>
      </a></li>`).join('')}</ol>`;
    return `${heroCard(rows[0], st)}<ol class="rk-list">${rows.slice(1).map((r, i) => `<li class="rk-li">
      <a class="rk-row" href="#/f/${r.t.id}"><span class="rk-n">${String(i + 2).padStart(2, '0')}</span>${symAv(r.t)}
        <span class="rk-name"><b>${esc(r.t.name)}</b><small>${esc(r.t.sym || '')}${r.t.sym ? ' · ' : ''}${CR.plural(r.cc, 'creador', 'creadores')}</small><span class="rk-tone">${CR.icon(CR.TONE[r.net.pol].icon, 'rk-ti t-' + CR.TONE[r.net.pol].cls)}${termo(r.sent)}<span class="mini-n"><span class="t-up">${r.sent.alcista}</span>/<span class="t-down">${r.sent.bajista}</span></span></span></span>
        ${rkCount(r, st)}</a>
    </li>`).join('')}</ol>`;
  }
  /* Ranking por conversación analizada: creadores únicos con afirmaciones del creador → tesis aceptadas. */
  const fichaHref = (id, st, extra) => CR.hash(['f', id], Object.assign({ c: st.c, p: st.p }, extra || {}));
  function convRow(r, i, st) {
    const count = r.coverageKnown ? (r.theses.length ? CR.plural(r.theses.length, 'tesis', 'tesis') : 'Sin clasificar') : 'Tesis: —';
    return `<li class="cv-li${i === 0 ? ' is-top' : ''}"><a class="cv-row" href="${fichaHref(r.t.id, st)}">
      <span class="rk-n">${String(i + 1).padStart(2, '0')}</span>${symAv(r.t)}
      <span class="cv-name"><b>${esc(r.t.name)}</b><small>${esc(r.t.sym || '')}</small><span class="cv-stats"><span><b>${r.creators}</b> ${r.creators === 1 ? 'creador' : 'creadores'}</span><span class="${r.theses.length ? 'has-theses' : 'no-theses'}">${count}</span></span></span>${icon('chevron-right')}</a></li>`;
  }

  function convList(st, needle = '') {
    const rows = Theses.rankAssets(idx, st.s, st, Date.now()).filter((r) => !needle || r.t.name.toLowerCase().includes(needle) || (r.t.sym || '').toLowerCase().includes(needle));
    const known = !!(idx.theses && idx.theses.status === 'ok');
    const claims = rows.reduce((n, r) => n + r.claims.length, 0), classified = rows.reduce((n, r) => n + r.classifiedClaims, 0);
    const creators = new Set(rows.flatMap((r) => r.claims.map((c) => idx.videosById[c.v].ch))).size;
    const btc = st.s === 'altcoins' && idx.topicsById.btc ? Theses.rankAssets(idx, 'bitcoin', st, Date.now())[0] : null;
    return `<p class="cv-coverage">${CR.plural(creators, 'creador', 'creadores')} con análisis en estos filtros · ${known ? `clasificación de tesis parcial: ${classified} de ${CR.plural(claims, 'afirmación relevante', 'afirmaciones relevantes')}` : 'clasificación de tesis no disponible'}</p>
      ${btc ? `<a class="cv-btc" href="${fichaHref('btc', st)}">${symAv(btc.t)}<span><b>Bitcoin</b> se consulta aparte: ${CR.plural(btc.creators, 'creador', 'creadores')} · ${btc.theses.length ? CR.plural(btc.theses.length, 'tesis aceptada', 'tesis aceptadas') : 'tesis sin clasificar'}</span>${icon('chevron-right')}</a>` : ''}
      ${rows.length ? `<ol class="cv-list">${rows.map((r, i) => convRow(r, i, st)).join('')}</ol>` : `<div class="empty"><h3>Sin conversación analizada con estos filtros</h3><p>No hay afirmaciones del creador con cita en este periodo o creador. No se amplía el filtro por su cuenta.</p><a class="pill" href="${exHash(st, { c: 'todos', p: 'todo' })}">Quitar filtros</a></div>`}`;
  }
  /* Pestaña Tesis: tesis aceptadas del mercado; los temas antiguos quedan aparte y nombrados como temas. */
  function thesisCard(t, st) {
    const stt = Theses.thesisStats(idx, t.id, st, Date.now());
    const assets = [...Theses.linkedAssets(idx, t, st, Date.now())].filter((a) => idx.topicsById[a]);
    const target = (t.assets && t.assets[0]) || assets.find((a) => idx.topicsById[a].section === st.s) || assets[0];
    const n = (k) => stt.creatorsBy[k].size;
    return `<a class="th-card" href="${target ? fichaHref(target, st, { tesis: t.id }) : '#/'}">
      <p class="th-k">Tesis aceptada · ${CR.plural(stt.creators.size, 'creador', 'creadores')}</p>
      <h3>${esc(t.label)}</h3>
      <p class="th-rel"><span class="r-apoyo">${n('apoyo')} ${n('apoyo') === 1 ? 'apoya' : 'apoyan'}</span><span class="r-objecion">${n('objecion')} ${n('objecion') === 1 ? 'objeta' : 'objetan'}</span><span class="r-matiz">${n('matiz')} ${n('matiz') === 1 ? 'matiza' : 'matizan'}</span></p>
      <p class="th-meta">${esc(t.horizon)}${assets.length ? ` · ${esc(joinEs(assets.map((a) => idx.topicsById[a].name)))}` : ''}</p></a>`;
  }
  function thesesTab(st) {
    const known = idx.theses && idx.theses.status === 'ok';
    const list = known ? idx.theses.items.filter((t) => {
      if (!Theses.thesisStats(idx, t.id, st, Date.now()).members.length) return false;
      const assets = [...Theses.linkedAssets(idx, t, st, Date.now())];
      return (t.markets || []).includes(st.s) || assets.some((a) => idx.topicsById[a] && idx.topicsById[a].section === st.s) || (st.s === 'altcoins' && (t.markets || []).includes('bitcoin'));
    }) : [];
    const themes = (SEC_THEMES[st.s] || []).map((id) => idx.themesById[id]).filter(Boolean);
    return `${known ? `<p class="cv-coverage">${CR.plural(list.length, 'tesis aceptada', 'tesis aceptadas')} con membresías en estos filtros. La clasificación es parcial y editorial: lo no clasificado sigue en el ranking y en cada vídeo.</p>` : '<p class="cv-coverage">Clasificación de tesis no disponible en esta versión de los datos.</p>'}
      ${list.map((t) => thesisCard(t, st)).join('') || (known ? '<div class="empty"><h3>Sin tesis aceptadas con estos filtros</h3><p>Cobertura parcial: no significa que nadie sostenga una tesis.</p></div>' : '')}
      <details class="th-themes"><summary>Temas del archivo (agrupaciones por palabras, no tesis)</summary>${themes.map(themeCard).join('')}<p class="small muted">${esc(idx.method.themes)}</p></details>`;
  }
  function themeCard(th) {
    const net = CR.netSent(th.sent);
    return `<a class="g-card" href="#/n/${th.id}"><span class="g-tone">${chip(net.pol)}${termo(th.sent)}</span><h3>${esc(th.title)}</h3><p>${esc(th.about)}</p>
      <span class="g-thumbs">${th.sources.slice(0, 5).map((x) => `<img src="${CR.thumb(x.v)}" alt="" loading="lazy">`).join('')}</span>
      <small>${CR.plural(th.videoCount, 'vídeo', 'vídeos')} · ${th.analyzedCount} con análisis · ${listNames(th.creators.map((c) => idx.channelsBySlug[c].name))}${th.contrasts.length ? ` · <span class="t-mix">${CR.plural(th.contrasts.length, 'cruce', 'cruces')}</span>` : ''}</small></a>`;
  }
  /* Tono de las menciones de la sección: contexto secundario y plegado. Cuenta frases, no aciertos ni apoyos. */
  function toneContext(rows, st) {
    const sum = { alcista: 0, bajista: 0, mixta: 0, neutra: 0 };
    rows.forEach((r) => Object.keys(sum).forEach((k) => { sum[k] += r.sent[k]; }));
    const toned = sum.alcista + sum.bajista;
    if (!toned) return '';
    return `<details class="tone-ctx"><summary>Tono de las menciones en ${esc(L.section[st.s].toLowerCase())} (contexto)</summary>
      ${termo({...sum,mixta:0}, { big: true, needle: true, bulbs: true })}<p class="small">De ${toned} menciones con dirección clara, <span class="t-up">${Math.round((sum.alcista / toned) * 100)} % suenan alcistas</span> y <span class="t-down">${Math.round((sum.bajista / toned) * 100)} % bajistas</span>; ${sum.neutra+sum.mixta} no tienen una dirección clara. Cuenta frases del texto: describe el ambiente, no si aciertan ni quién apoya qué.</p></details>`;
  }
  function renderExplore(q, keep) {
    const st = exState(q);
    const rows = rankRows(st);
    const vids = idx.videos.filter((v) => inWindow(v, st));
    const y = keep ? window.scrollY : 0;
    const thesesReady = !!(idx.theses && idx.theses.status === 'ok' && idx.theses.items.length);
    const tabs = [['ranking', 'Ranking'], ['tesis', thesesReady ? 'Tesis' : 'Narrativas']];
    let body = '';
    if (st.tab === 'tesis') {
      body = thesesReady ? thesesTab(st) : (SEC_THEMES[st.s] || []).map((id) => idx.themesById[id]).filter(Boolean).map(themeCard).join('');
    } else {
      body = `<div class="rk-head"><span>Ranking por videos</span><small>Alcistas vs bajistas</small></div>
        <div id="rk">${rankList(rows, st)}</div>
        ${toneContext(rows, st)}
        <details class="method"><summary>Cómo se calcula</summary><span>Orden por número de videos; en empate, por menciones. Las tesis no cambian la posición. ${st.s === 'macro' ? 'En macro el tono se lee al revés: si suben el dólar, los bonos, el MOVE o la inflación, el sistema lo marca bajista para el riesgo; si bajan, alcista. ' : ''}${esc(idx.method.mentions)} ${esc(idx.method.tone)}</span></details>`;
    }
    const first = vids.length ? vids[vids.length - 1].pub : idx.period.from;
    const last = vids.length ? vids[0].pub : idx.period.to;
    const activeFilters = (st.c!=='todos'?1:0)+(st.p!=='todo'?1:0);
    const filterContext = [st.c!=='todos' ? idx.channelsBySlug[st.c]?.name : '', st.p!=='todo' ? ({'3d':'3 días','2d':'48 h','1d':'24 h'}[st.p]||'') : ''].filter(Boolean).join(' · ');
    page.innerHTML = `
      <section class="ex-head">
        <div class="seg-pill" role="tablist" aria-label="Secciones">${['altcoins', 'macro', 'bolsa'].map((k) => `<a role="tab" href="${exHash(st, { s: k })}" aria-selected="${k === st.s}">${L.section[k]}</a>`).join('')}</div>
        <h1 class="ex-title">${SEC_TITLE[st.s]}</h1>
        <p class="ex-sub">${fmtDate(first)} – ${fmtDate(last)} · ${CR.plural(new Set(vids.map((v) => v.ch)).size, 'creador', 'creadores')} · ${CR.plural(vids.length, 'vídeo', 'vídeos')}</p>
        <div class="ex-tools">
          <details class="ex-filter-menu"><summary>${icon('filter','i-s')} Filtros${activeFilters ? `<span class="ex-filter-badge">${activeFilters}</span>` : ''}</summary><div class="ex-filters">
            <label><span>Creador</span><select id="f-c">${[['todos', 'Todos los creadores'], ...idx.channels.map((c) => [c.slug, c.name])].map(([k, l]) => `<option value="${k}"${k === st.c ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
            <label><span>Periodo</span><select id="f-p">${[['todo', 'Archivo completo'], ['3d', 'Últimos 3 días'], ['2d', 'Últimas 48 h'], ['1d', 'Último día']].map(([k, l]) => `<option value="${k}"${k === st.p ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
          </div></details>
          ${filterContext ? `<small class="ex-filter-context">${esc(filterContext)}</small>` : ''}
          ${st.tab === 'ranking' ? `<details class="ex-search-menu"><summary aria-label="Buscar activo">${icon('search','i-s')}<span class="ex-search-term" id="f-q-term" hidden></span></summary><label class="ex-search">${icon('search', 'i-s')}<span class="sr">Buscar activo</span><input id="f-q" type="search" placeholder="Buscar activo o símbolo…" autocomplete="off"></label></details>` : ''}
        </div>
        <div class="tabs3" role="tablist" aria-label="Vistas">${tabs.map(([k, l]) => `<a role="tab" href="${exHash(st, { tab: k })}" aria-selected="${k === st.tab}">${l}</a>`).join('')}</div>
      </section>
      <section class="ex-body">${body}</section>`;
    const go = (patch) => CR.go(exHash(st, patch), null, { replace: true });
    const tools=page.querySelector('.ex-tools');
    tools.querySelectorAll('details').forEach(d=>d.addEventListener('toggle',()=>{if(d.open)tools.querySelectorAll('details').forEach(other=>{if(other!==d)other.open=false;});}));
    document.getElementById('f-c').addEventListener('change', (e) => go({ c: e.target.value }));
    document.getElementById('f-p').addEventListener('change', (e) => go({ p: e.target.value }));
    const fq = document.getElementById('f-q');
    if (fq) fq.addEventListener('input', CR.debounce(() => {
      const n = fq.value.trim().toLowerCase();
      const term=document.getElementById('f-q-term');term.textContent=fq.value.trim();term.hidden=!n;
      tools.querySelector('.ex-search-menu > summary').setAttribute('aria-label',n?`Buscar activo: ${fq.value.trim()}`:'Buscar activo');
      document.getElementById('rk').innerHTML = rankList(n ? rows.filter((r) => r.t.name.toLowerCase().includes(n) || (r.t.sym || '').toLowerCase().includes(n)) : rows, st);
    }, 150));
    if (keep) window.scrollTo(0, y);
  }

  /* ---------- ficha de menciones (hoja inferior) ---------- */
  let fichaRequest = 0, fichaReturnFocus = null;
  const DIRECTION_LABEL = { alcista: 'Alcistas', bajista: 'Bajistas', mixta: 'Direcciones combinadas', neutra: 'Sin dirección expresada' };
  function evidenceHtml(f) {
    const v = idx.videosById[f.v];
    const stance = f.radar;
    const position = stance && stance.position_side && stance.position_status === 'declarada' ? `<span class="position-tag">Declaró ${esc(stance.position_side)} · ${fmtDate(v.pub)}</span>` : '';
    const href = CR.hash(['v', v.id], { ...(f.t != null ? { t: Math.floor(f.t) } : {}), ...(f.id ? { n: f.id } : { lens: 'transcripcion' }) });
    return `<article class="f-frag evidence" data-polarity="${f.pol}" data-kind="${f.kind}">
      <div class="evidence-label">${chip(f.pol, { short: true })}<small>${f.kind === 'analysis' ? 'Afirmación analizada' : 'Fragmento detectado · tono léxico'}</small></div>${position}
      <blockquote class="f-q">«${esc(f.text)}»</blockquote>
      ${f.summary ? `<p class="f-sys">${esc(f.summary)}</p>` : ''}
      ${stance && stance.horizon ? `<p class="small muted">Horizonte: ${esc(stance.horizon)}</p>` : ''}
      ${stance && stance.conditions ? `<p class="small muted">Condición: ${esc(stance.conditions)}</p>` : ''}
      ${f.kind === 'analysis' ? `<p class="small muted">Invalidación: ${esc(stance && stance.invalidation || 'No especificada en esta afirmación.')}</p>` : ''}
      <div class="source-person">${creatorAv(v.channel)}<p class="f-meta">${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${f.t != null ? fmtT(f.t) : 'Sin marca temporal'}${f.emisor && stance && stance.speaker_role !== 'creador' ? `<br>Emisor atribuido: ${esc(f.emisor)}` : ''}</p></div>
      <div class="f-acts"><a class="pill" href="${href}">${icon('book')} Ver contexto</a><a class="textbtn" href="${CR.yt(v.id, f.t)}" target="_blank" rel="noopener">Escuchar la fuente ${icon('external', 'i-s')}</a></div>
    </article>`;
  }
  /* ---------- ficha del activo: tesis y contraste primero, luego todas las citas ---------- */
  const thesisCache = new Map();
  function loadThesis(id) {
    const t = idx.theses && idx.theses.items.find((x) => x.id === id);
    if (!t || !/^g\/[a-f0-9]{32}\/t\/[a-z0-9-]+\.json$/.test(t.detail)) return Promise.reject(new Error('Detalle no disponible'));
    if (!thesisCache.has(id)) {
      const p = fetch(`../data/${t.detail}`, { cache: 'force-cache' }).then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .then((d) => { if (d.generation !== idx.generation || d.id !== id) throw new Error('Versión de datos distinta'); return d; });
      p.catch(() => thesisCache.delete(id));
      thesisCache.set(id, p);
    }
    return thesisCache.get(id);
  }
  let socialPromise = null;
  function loadSocial() {
    if (!socialPromise) {
      socialPromise = Promise.all(['social-feed', 'social-connections'].map((n) => fetch(`../data/${n}.json`, { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).catch(() => null)))
        .then(([feed, links]) => ({ feed, links, posts: feed ? new Map(window.UraniaFeed.select(feed, { account: 'todos', period: 'cuenta', q: '' }).map((p) => [p.id, p])) : new Map() }));
    }
    return socialPromise;
  }
  const chName = (slug) => (idx.channelsBySlug[slug] ? idx.channelsBySlug[slug].name : slug);
  const fichaScroll = new Map();
  function memberCard(m, row) {
    const v = idx.videosById[m.v];
    return `<div class="fx-src" data-rel="${m.rel}">
      <p class="fx-src-h"><span>${fmtDate(v.pub)}</span><span class="fx-dim">${esc(Theses.DIM[m.dim])}</span></p>
      <blockquote>«${esc(m.x)}»</blockquote>
      <p class="fx-why">${esc(m.why)}</p>
      ${row ? `<dl class="fx-kv">${row.posture ? `<dt>Postura</dt><dd>${esc(row.posture)}</dd>` : ''}${row.condition ? `<dt>Condición</dt><dd>${esc(row.condition)}</dd>` : ''}${row.horizon ? `<dt>Plazo</dt><dd>${esc(row.horizon)}</dd>` : ''}${row.invalidation ? `<dt>Invalidación</dt><dd>${esc(row.invalidation)}</dd>` : ''}</dl>
        <details class="syn-more"><summary>Cita completa</summary><p>«${esc(row.quote)}»</p></details>` : ''}
      <a class="textbtn" href="${CR.hash(['v', m.v], { t: Math.floor(m.at || 0), n: m.c })}">${icon('play', 'i-s')} Ver en el vídeo${m.at != null ? ` · ${fmtT(m.at)}` : ''}</a>
    </div>`;
  }
  function thesisBlock(t, stt, open, asset) {
    return `<article class="fx-thesis" id="thesis-${esc(t.id)}" data-thesis="${esc(t.id)}">
      <p class="th-k">Tesis aceptada · ${CR.plural(stt.creators.size, 'creador', 'creadores')}</p>
      <h4>${esc(t.label)}</h4>
      <p class="th-rel">${Object.keys(Theses.REL_GROUP).map((rel) => `<span class="r-${rel}">${stt.creatorsBy[rel].size} ${rel === 'apoyo' ? (stt.creatorsBy[rel].size === 1 ? 'apoya' : 'apoyan') : rel === 'objecion' ? (stt.creatorsBy[rel].size === 1 ? 'objeta' : 'objetan') : (stt.creatorsBy[rel].size === 1 ? 'matiza' : 'matizan')}</span>`).join('')}</p>

      <details class="fx-detail" data-thesis="${esc(t.id)}"${open ? ' open' : ''}><summary>Fuentes por creador</summary>
        <div class="fx-body"><p class="small muted">Cargando las fuentes…</p></div>
      </details>
      <details class="syn-more"><summary>Formulación y alcance</summary><p class="fx-prop">${esc(t.proposition)}</p><p class="th-meta">Formulación editorial · ${esc(t.horizon)}${(t.conditions || []).length ? ` · Condición: ${esc(t.conditions.join('; '))}` : ''}</p><p class="small muted">El total cuenta autores únicos; un autor puede apoyar la dirección y matizar el momento.</p></details>
      ${idx.topicsById[asset].sym ? `<a class="textbtn fx-feed" href="${CR.hash(['feed'], { asset: idx.topicsById[asset].sym.toUpperCase(), cf: asset, ct: t.id, cn: t.label })}">${icon('list', 'i-s')} Publicaciones de X que mencionan ${esc(idx.topicsById[asset].sym)} (contexto)</a>` : ''}
    </article>`;
  }
  function participantCards(stt, rows) {
    const people = new Map();
    stt.members.forEach((m) => { if (!people.has(m.ch)) people.set(m.ch, []); people.get(m.ch).push(m); });
    const priority = (ms) => Math.min(...ms.map((m) => ['apoyo','objecion','matiz'].indexOf(m.rel)));
    return [...people.values()].sort((a,b) => priority(a)-priority(b)).map((ms) => {
      const v = idx.videosById[ms[0].v];
      const relations = [...new Set(ms.map((m) => m.rel))];
      const conditions = [...new Set(ms.map((m) => rows.get(`${m.v}:${m.c}`)?.condition).filter(Boolean))];
      return `<article class="fx-participant" data-creator="${esc(ms[0].ch)}"><p class="fx-src-h">${creatorAv(v.channel)}<b>${esc(v.channel.name)}</b></p><p class="th-rel">${relations.map((r) => `<span class="r-${r}">${Theses.REL[r]}</span>`).join('')}</p>
        ${conditions.length === 1 ? `<p class="fx-condition"><b>Condición:</b> ${esc(conditions[0])}</p>` : conditions.length ? `<p class="small muted">${conditions.length} condiciones según la afirmación; consultar las fuentes.</p>` : ''}
        <details class="syn-more"><summary>${CR.plural(ms.length, 'fuente y condición', 'fuentes y condiciones')}</summary>${ms.map((m) => memberCard(m, rows.get(`${m.v}:${m.c}`))).join('')}</details></article>`;
    }).join('');
  }
  async function fillThesis(el, t, st) {
    const body = el.querySelector('.fx-body');
    const stt = Theses.thesisStats(idx, t.id, st, Date.now());
    let rows = new Map(), detailOk = true;
    try { const d = await loadThesis(t.id); rows = new Map(d.members.map((r) => [`${r.v}:${r.c}`, r])); } catch (_) { detailOk = false; }
    const social = await loadSocial();
    const links = Theses.xConnections(idx, social.links, social.posts, t.id, st, Date.now());
    const scenarios = new Map(), watch = new Map();
    stt.members.forEach((m) => { const r = rows.get(`${m.v}:${m.c}`); (r ? r.scenarios : []).forEach((s) => { const k = `${m.v}:${s.id}`, prev = scenarios.get(k); scenarios.set(k, { ...s, v: m.v, rels: [...new Set([...(prev ? prev.rels : []), m.rel])] }); }); (r ? r.watch : []).forEach((w) => watch.set(`${m.v}:${w.what}`, { ...w, v: m.v })); });
    body.innerHTML = `${detailOk ? '' : '<p class="small muted">No se pudo cargar el detalle; se muestran los extractos aceptados.</p>'}
      ${participantCards(stt, rows)}
      ${scenarios.size ? (() => { const card = (s) => `<div class="fx-scn"><p class="syn-tags"><span class="syn-tag ${s.origin === 'creador' ? 'is-creator' : 'is-analyst'}">${SCN_ORIGIN[s.origin] || esc(s.origin)}</span><span class="syn-tag">${esc(chName(idx.videosById[s.v].ch))}</span>${s.rels.map((r) => `<span class="syn-tag r-${r}">Fuente que ${esc(Theses.REL[r].toLowerCase())}</span>`).join('')}</p><p><b>${esc(s.name)}</b></p><p class="small">${esc(s.mechanism)}</p>${s.invalidation ? `<p class="small"><b>Lo invalidaría:</b> ${esc(s.invalidation)}</p>` : ''}<a class="textbtn" href="${CR.hash(['v', s.v], { lens: 'sintesis' })}">Leer la síntesis del vídeo</a></div>`;
        const all = [...scenarios.values()].sort((a, b) => ['apoyo', 'objecion', 'matiz'].indexOf(a.rels[0]) - ['apoyo', 'objecion', 'matiz'].indexOf(b.rels[0]));
        return `<details class="fx-group syn-more"><summary>Escenarios de estas fuentes · ${scenarios.size}</summary>${all.slice(0, 3).map(card).join('')}${all.length > 3 ? `<details class="syn-rest"><summary>Ver los otros ${all.length - 3} escenarios</summary>${all.slice(3).map(card).join('')}</details>` : ''}</details>`; })() : ''}
      ${watch.size ? (() => { const li = (w) => `<li class="syn-watch"><p class="syn-what">${esc(w.what)}</p><p class="syn-crit">${esc(w.criterion)}</p><p class="syn-meta">${w.term ? `<span>Plazo: ${esc(w.term)}</span>` : ''}<span>Criterio ${w.origin === 'creador' ? 'del creador' : 'del analista'} · ${esc(chName(idx.videosById[w.v].ch))}</span></p></li>`;
        const all = [...watch.values()];
        return `<details class="fx-group syn-more"><summary>Qué vigilar · ${watch.size}</summary><ul class="syn-watch-list">${all.slice(0, 3).map(li).join('')}</ul>${all.length > 3 ? `<details class="syn-rest"><summary>Ver todas (${all.length - 3} más)</summary><ul class="syn-watch-list">${all.slice(3).map(li).join('')}</ul></details>` : ''}</details>`; })() : ''}
      <section class="fx-group"><h5>Publicaciones de X conectadas a esta tesis</h5>${links.length ? links.map((x) => `<blockquote class="syn-x"><b>${esc(Theses.X_REL[x.relation] || x.relation)}</b> · @${esc(x.source_account)}: «${esc(x.post_quote)}»<br><small>${esc(x.limitations)}</small></blockquote>`).join('') : '<p class="syn-empty">Sin conexiones aceptadas y vigentes con estas afirmaciones. Un mismo ticker no se cuenta como apoyo.</p>'}</section>`;
  }
  async function openFicha(id, query = {}) {
    const t = idx.topicsById[id];
    if (!t) { CR.go('#/', null, { replace: true }); return; }
    const request = ++fichaRequest;
    fichaReturnFocus = document.activeElement; feedPostOpen = false;
    document.getElementById('ficha-title').textContent = 'Ficha del activo';
    const fromRadar = query.from === 'radar';
    const ex = exState({});
    // Periodo y creador vienen en la URL cuando se abre desde el ranking o el radar; si no, los del ranking.
    const st = { c: query.c || (fromRadar ? 'todos' : ex.c), p: query.p || (fromRadar ? 'todo' : ex.p) };
    const key = `${id}:${JSON.stringify(query)}`;
    const r = rankRows({ ...st, s: t.section, m: 'videos' }).find((x) => x.t.id === id);
    const known = !!(idx.theses && idx.theses.status === 'ok');
    const claims = Theses.relevantClaims(idx, id, st, Date.now());
    const classified = new Set(Theses.members(idx, st, Date.now()).map((m) => `${m.v}:${m.c}`));
    const theses = known ? Theses.thesesForAsset(idx, id, st, Date.now()).map((x) => ({ t: x, stt: Theses.thesisStats(idx, x.id, st, Date.now()) }))
      .sort((a, b) => (b.t.id === query.tesis) - (a.t.id === query.tesis) || (b.t.assets || []).includes(id) - (a.t.assets || []).includes(id) || b.stt.creators.size - a.stt.creators.size || a.t.id.localeCompare(b.t.id)) : [];
    const creators = new Set(claims.map((c) => idx.videosById[c.v].ch)).size;
    const body = document.getElementById('ficha-body');
    body.innerHTML = `<div class="asset-heading">${symAv(t)}<div><span class="tag-sec">${esc(L.section[t.section])}</span><h3 class="f-name">${esc(t.name)}</h3><p class="f-sym">${esc(t.sym || '')}</p></div></div>
      <p class="small muted">${st.c === 'todos' ? 'Todos los creadores' : esc(idx.channelsBySlug[st.c]?.name || st.c)} · ${st.p === 'todo' ? 'Archivo completo' : `Últimas ${{'1d':24,'2d':48,'3d':72}[st.p] || 24} h`}</p>
      <div class="f-stats"><span><b>${creators}</b><small>creadores con análisis</small></span><span><b>${known ? theses.length : '—'}</b><small>tesis aceptadas</small></span><span><b>${r ? r.n : 0}</b><small>menciones en texto</small></span></div>
      <p class="cv-coverage">${known ? `${claims.filter((c) => classified.has(`${c.v}:${c.id}`)).length} de ${CR.plural(claims.length, 'afirmación del creador', 'afirmaciones del creador')} clasificadas en tesis: cobertura parcial.` : 'Clasificación de tesis no disponible.'}${t.note ? ` Ojo: ${esc(t.note)}.` : ''}</p>
      <section class="fx-sec" aria-labelledby="fx-h-tesis"><h4 class="syn-k" id="fx-h-tesis">Tesis y contraste</h4>
        ${theses.length ? theses.slice(0, 3).map((x, i) => thesisBlock(x.t, x.stt, x.t.id === query.tesis || (!query.tesis && i === 0), id)).join('')
          + (theses.length > 3 ? `<details class="syn-rest"><summary>Ver las otras ${theses.length - 3} tesis</summary>${theses.slice(3).map((x) => thesisBlock(x.t, x.stt, false, id)).join('')}</details>` : '')
          : `<p class="syn-empty">${known ? `Sin tesis aceptadas para ${esc(t.name)} con estos filtros. Es cobertura parcial, no ausencia de tesis: sus ${CR.plural(claims.length, 'afirmación', 'afirmaciones')} del creador siguen abajo, sin clasificar.` : 'Clasificación de tesis no disponible en esta versión de los datos.'}</p>`}
      </section>
      <section class="fx-sec" aria-labelledby="fx-h-x"><h4 class="syn-k" id="fx-h-x">Publicaciones de X</h4><div id="fx-x"><p class="small muted">Cargando…</p></div></section>
      <section class="fx-sec" aria-labelledby="fx-h-all"><h4 class="syn-k" id="fx-h-all">Todas las citas y menciones</h4>
        <p class="f-note">Las direcciones agrupan argumentos; no acreditan posiciones abiertas. Los fragmentos detectados solo tienen clasificación léxica. Orden: alcistas, bajistas, mixtas y neutrales.</p>
        <div id="f-evidences" aria-live="polite"><p class="small muted">Cargando citas…</p></div></section>`;
    ficha.hidden = false; scrim.hidden = false;
    document.querySelectorAll('#page, .dock, #nh, #stage').forEach((el) => { el.inert = true; });
    document.body.style.overflow = 'hidden';
    body.scrollTop = 0;
    ficha.querySelector('[data-act="ficha-close"]').focus({ preventScroll: true });
    body.onscroll = CR.debounce(() => { if (!ficha.hidden) fichaScroll.set(key, body.scrollTop); }, 120);
    body.querySelectorAll('.fx-detail').forEach((d) => {
      const th = theses.find((x) => x.t.id === d.dataset.thesis);
      const fill = () => { if (!d.dataset.filled) { d.dataset.filled = '1'; fillThesis(d, th.t, st); } };
      if (d.open) fill();
      d.addEventListener('toggle', () => { if (d.open) fill(); });
    });
    loadSocial().then((social) => {
      if (request !== fichaRequest || ficha.hidden) return;
      const out = document.getElementById('fx-x');
      const keys = new Set(claims.map((c) => `${c.v}:${c.id}`));
      const accepted = (social.links && social.links.connections || []).filter((x) => x.status === 'aceptado' && keys.has(`${x.video_id}:${x.claim_id}`)
        && x.analysis_sha256 === idx.videosById[x.video_id].analysis_sha256 && Date.parse(x.expires_at) > Date.now() && social.posts.get(x.post_id)?.content_hash === x.post_content_hash);
      const sym = (t.sym || '').toUpperCase();
      const context = Theses.assetContext([...social.posts.values()], sym);
      out.innerHTML = `${accepted.length ? accepted.map((x) => `<blockquote class="syn-x"><b>${esc(Theses.X_REL[x.relation] || x.relation)}</b> · @${esc(x.source_account)}: «${esc(x.post_quote)}»</blockquote>`).join('') : `<p class="syn-empty">Sin conexiones aceptadas y vigentes con afirmaciones de ${esc(t.name)}${social.links && social.links.status ? ` (estado del cruce: ${esc(social.links.status.replaceAll('_', ' '))})` : ''}.</p>`}
        ${sym ? `<div class="fx-context"><p class="syn-sub">Mencionan ${esc(sym)} · contexto, no suma apoyos</p>${context.slice(0, 2).map((p) => `<p class="fx-post"><b>@${esc(p.author_handle)}</b> · ${esc(CR.clip(p.text, 140))}</p>`).join('') || '<p class="syn-empty">Ninguna publicación vigente lo menciona.</p>'}
          ${context.length ? `<a class="textbtn" href="${CR.hash(['feed'], { asset: sym, cf: id, cn: t.name })}">${icon('list', 'i-s')} Ver ${CR.plural(context.length, 'publicación', 'publicaciones')} en el Feed</a>` : ''}</div>` : ''}`;
    });
    if (fichaScroll.has(key)) requestAnimationFrame(() => { body.scrollTop = fichaScroll.get(key); });
    else if (query.tesis) requestAnimationFrame(() => { const el = document.getElementById(`thesis-${query.tesis}`); if (el) body.scrollTop = el.offsetTop - body.offsetTop - 8; });
    let frags = r ? r.frags : [], complete = false;
    try { const detail = await CR.loadAsset(id); frags = detail.frags; complete = true; }
    catch (_) { /* Preview stays useful; the UI explicitly labels incomplete coverage. */ }
    if (request !== fichaRequest || ficha.hidden) return;
    const items = Radar.evidence(idx, t, frags, st);
    const out = document.getElementById('f-evidences');
    const limits = Object.fromEntries(Radar.order.map((pol) => [pol, 6]));
    const paint = () => {
      out.innerHTML = `<p class="small muted evidence-count">${items.length} pasajes ${complete ? 'disponibles' : 'en la muestra disponible'} con estos filtros. ${complete ? '' : 'No se pudo cargar el detalle completo.'}</p>` + (items.length ? Radar.order.map((pol) => {
        const group = items.filter((x) => x.pol === pol);
        return group.length ? `<section class="evidence-group" data-group="${pol}" id="quotes-${pol}"><h4>${esc(DIRECTION_LABEL[pol])}<span>${group.length}</span></h4>${group.slice(0, limits[pol]).map(evidenceHtml).join('')}${group.length > limits[pol] ? `<button class="pill more-quotes" type="button" data-more="${pol}">Ver más ${DIRECTION_LABEL[pol].toLowerCase()} (${group.length - limits[pol]})</button>` : ''}</section>` : '';
      }).join('') : `<div class="empty"><h3>Sin citas con estos filtros</h3><p>Amplía el período o incluye a todos los creadores.</p><a class="pill" href="${CR.hash(['f', id], { from:'radar', c:'todos', p:'todo' })}">Ver todo el archivo</a></div>`);
      out.querySelectorAll('[data-more]').forEach((button) => button.addEventListener('click', () => {
        const pol = button.dataset.more, before = limits[pol]; limits[pol] += 6; paint();
        const target = out.querySelectorAll(`[data-group="${pol}"] .evidence`)[before];
        if (target) { target.tabIndex = -1; target.focus({ preventScroll:true }); target.scrollIntoView({ block:'nearest' }); }
      }));
    };
    paint();
    if (!fichaScroll.has(key) && fromRadar && ['alcista','bajista'].includes(query.direction)) {
      const target = document.getElementById(`quotes-${query.direction}`);
      if (target) body.scrollTop = target.offsetTop - body.offsetTop;
    }
  }
  function closeFicha(silent) {
    if (ficha.hidden) return;
    ++fichaRequest;
    ficha.hidden = true; scrim.hidden = true;
    document.querySelectorAll('#page, .dock, #nh, #stage').forEach((el) => { el.inert = false; });
    document.body.style.overflow = '';
    const fromFeed = feedPostOpen; feedPostOpen = false;
    if (!silent && fromFeed) {
      requestAnimationFrame(() => { if (fichaReturnFocus && fichaReturnFocus.isConnected) fichaReturnFocus.focus({ preventScroll:true }); });
    } else if (!silent) {
      CR.back('#/');
      requestAnimationFrame(() => {
        const target = fichaReturnFocus && fichaReturnFocus.isConnected ? fichaReturnFocus : document.querySelector('#q, .ex-search, a[href="#/buscar"], #page a');
        if (target) target.focus({ preventScroll:true });
      });
    }
  }

  /* ---------- índice ---------- */
  function openIndex() {
    const here = (screen || '').split(':')[0];
    const items = [
      ['#/', 'Bitácora', `${idx.videos.length} vídeos, del más nuevo al más viejo`, idx.videos.length, ['log', 'v']],
      ['#/hilos', 'Hilos', 'Ideas que se repiten entre vídeos', idx.themes.length, ['hilos', 'h']],
      ['#/activos', 'Activos', 'Altcoins, macro y bolsa por día', idx.topics.length, ['activos', 'a']],
      ['#/feed', 'Feed', 'Publicaciones de las cuentas de X', 'X', ['feed']],
    ];
    const n = { alcista: 0, bajista: 0, mixta: 0, neutra: 0 };
    idx.videos.forEach((v) => { n[v.tone.label] += 1; });
    document.getElementById('index-list').innerHTML = `<div class="ix-pulse">${termo(n, { big: true, needle: true, bulbs: true })}<p class="small">${sentLine(n, ['alcista', 'alcistas', 'bajista', 'bajistas', 'mixto', 'mixtos'])}</p></div>` + items.map(([href, name, sub, n, keys]) => `
      <a class="ix" href="${href}"${keys.includes(here) ? ' aria-current="page"' : ''}><span class="ix-name">${name}<span class="ix-sub">${sub}</span></span><span class="ix-n">${n}</span></a>`).join('')
      + `<div class="ix-minor"><a href="#/estados">Estados del procesamiento ${icon('chevron-right')}</a><a href="#/datos">Sobre estos datos ${icon('chevron-right')}</a><a href="../index.html">Volver al tablero de propuestas ${icon('chevron-right')}</a></div>`;
    indexEl.hidden = false;
    indexEl.querySelector('[data-act="index-close"]').focus();
  }
  function closeIndex() { /* sin índice: la navegación vive en la cápsula inferior */ }

  /* ---------- bitácora (inicio) ---------- */
  function filterVideos(f) {
    const vs = idx.videos;
    if (f === 'analizados') return vs.filter((v) => v.analysis);
    if (f === 'alcistas') return vs.filter((v) => v.tone.label === 'alcista');
    if (f === 'bajistas') return vs.filter((v) => v.tone.label === 'bajista' || (v.tone.label === 'mixta' && v.tone.share < 0.5));
    if (f === 'contraste') return vs.filter((v) => CR.titleGap(v));
    if (f === 'largos') return vs.filter((v) => !v.short);
    if (f === 'shorts') return vs.filter((v) => v.short);
    if (idx.channels.some((c) => c.slug === f)) return vs.filter((v) => v.ch === f);
    return vs;
  }
  function pulseRow(v) {
    const t = v.tone;
    const gap = CR.titleGap(v);
    return `<div class="pulse-row">${chip(t.label, { str: t.str })}<span class="pulse-pct">${pct(v)}</span></div>
      ${t.share != null ? `<div class="pulse-wave">${CR.waveSvg(t.wave, { w: 260, h: 22, gap: 1, label: 'Tono a lo largo del vídeo: arriba alcista, abajo bajista' })}</div>` : ''}
      ${gap ? `<p class="gap-note">${icon('alert', 'i-s')}<span>El título suena ${CR.TONE[gap.title].label.toLowerCase()}; el vídeo, ${CR.TONE[gap.content].label.toLowerCase()}.</span></p>` : ''}`;
  }
  const tally = (items) => {
    const n = { alcista: 0, bajista: 0, mixta: 0, neutra: 0 };
    items.forEach((v) => { n[v.tone.label] += 1; });
    return `<span class="tally" aria-label="${n.alcista} alcistas, ${n.bajista} bajistas, ${n.mixta} mixtos">${n.alcista ? `<span class="t-up">${icon('trend-up', 'i-s')}${n.alcista}</span>` : ''}${n.bajista ? `<span class="t-down">${icon('trend-down', 'i-s')}${n.bajista}</span>` : ''}${n.mixta ? `<span class="t-mix">${icon('updown', 'i-s')}${n.mixta}</span>` : ''}</span>`;
  };
  // Diario: cada tarjeta dice qué aporta el vídeo (su tesis y activos, si hay análisis válido), no su volumen.
  function entryVitals(v) {
    const tone = v.tone || {};
    if (!Array.isArray(tone.wave) || !tone.wave.length) return '';
    const label = { alcista: 'alcista', bajista: 'bajista', mixta: 'mixto', neutra: 'neutro' }[tone.label] || 'neutro';
    return `<div class="entry-vitals" title="Pulso léxico de la transcripción">
      <div class="entry-wave">${CR.waveSvg(tone.wave, { w: 240, h: 28, gap: 1, label: 'Pulso del texto a lo largo del video: verde al alza, rojo a la baja' })}</div>
      <span class="entry-pulse-label tone-${CR.TONE[tone.label]?.cls || 'flat'}">${icon(CR.TONE[tone.label]?.icon || 'minus', 'i-s')}<span>Pulso ${label}</span></span>
    </div>`;
  }
  function entryHtml(v) {
    const a = v.analysis;
    const assets = a ? a.assets.filter((x) => idx.topicsById[x]).slice(0, 4) : [];
    return `<li class="entry${a ? ' is-analyzed' : ''}" data-tone="${esc(v.tone.label)}">
      <time class="entry-time" datetime="${esc(v.pub)}">${hhmm(v.pub)}</time><span class="entry-dot" aria-hidden="true"></span>
      <a class="entry-card" href="#/v/${v.id}${a ? '?lens=sintesis' : '?lens=transcripcion'}">
        <p class="entry-who">${creatorAv(v.channel)}<span>${esc(v.channel.name)}</span>${v.short ? '<span class="tag-s">Short</span>' : ''}</p>
        <div class="entry-media"><p class="entry-title">${esc(window.UraniaEditorial.listTitle(v.cleanTitle))}</p><div class="entry-thumb"><img src="${CR.thumb(v.id)}" alt="" loading="lazy" decoding="async"></div></div>
        ${entryVitals(v)}
        <div class="entry-foot"><span class="entry-assets">${a ? esc(assets.map((x) => idx.topicsById[x].sym || idx.topicsById[x].name).join(' · ')) : 'Sin análisis'}</span><span class="entry-go">${a ? 'Leer síntesis' : 'Leer texto'} ${icon('chevron-right', 'i-s')}</span></div>
      </a>
    </li>`;
  }
  function archivePulse() {
    const n = { alcista: 0, bajista: 0, mixta: 0, neutra: 0 };
    idx.videos.forEach((v) => { n[v.tone.label] += 1; });
    const gaps = idx.videos.filter((v) => CR.titleGap(v)).length;
    return `<div class="archive-pulse pad"><div class="ap-bar">${termo(n, { big: true, needle: true, bulbs: true })}</div>
      <p class="small"><span class="t-up">${icon('trend-up', 'i-s')}${n.alcista} alcistas</span> · <span class="t-down">${icon('trend-down', 'i-s')}${n.bajista} bajistas</span> · <span class="t-mix">${icon('updown', 'i-s')}${n.mixta} mixtos</span> · ${n.neutra} sin tono${gaps ? ` · <button class="linkish" type="button" data-act="filter" data-f="contraste">${gaps} con título que no cuadra</button>` : ''}</p></div>`;
  }
  function renderLog() {
    const list = filterVideos(ui.filter);
    const days = [];
    list.forEach((v) => { const k = CR.dayKey(v.pub); if (!days.length || days[days.length - 1].k !== k) days.push({ k, iso: v.pub, items: [] }); days[days.length - 1].items.push(v); });
    page.innerHTML = `
      <div class="log-toolbar pad"><div><h1 class="title-xl">Diario</h1><p class="small muted">${list.length} videos · ${esc(filters()[ui.filter] || FILTERS.todo)}</p></div>
        <button class="filter-btn" type="button" data-act="filter-menu" aria-haspopup="menu" aria-expanded="false" aria-controls="filter-menu">${icon('filter')} Filtrar</button>
        <div class="menu" id="filter-menu" role="menu" hidden>
          ${Object.entries(filters()).map(([k, label]) => `<button type="button" role="menuitemradio" aria-checked="${ui.filter === k}" data-act="filter" data-f="${k}">${label}<span class="n">${filterVideos(k).length}</span></button>`).join('')}
        </div>
      </div>
      <p class="log-legend pad">Pulso del texto <span class="t-up">↑ Al alza</span><span class="t-down">↓ A la baja</span></p>
      ${days.map((d) => `<section class="day"><h2 class="day-h">${esc(CR.dayLabel(d.iso))}<small>${CR.plural(d.items.length, 'vídeo', 'vídeos')} ${tally(d.items)}</small></h2><ol class="entries">${d.items.map(entryHtml).join('')}</ol></section>`).join('')
      || `<div class="empty"><h3>Nada con este filtro</h3><p>Prueba con todo el archivo.</p><button class="pill" type="button" data-act="filter" data-f="todo">Ver todo</button></div>`}`;
  }

  /* ---------- ficha del vídeo + cuaderno ---------- */
  async function renderVideo(id, q) {
    const v = idx.videosById[id];
    if (!v) { nb.hidden = true; page.innerHTML = `<div class="empty"><h3>Este vídeo no está en la bitácora</h3><a class="pill" href="#/">Ver la bitácora</a></div>`; return; }
    if (signalMode) { signalMode = false; videoOpen = false; videoPinned = false; }
    document.getElementById('topbar-title').textContent = v.cleanTitle;
    document.getElementById('reading-source').open = false;
    document.getElementById('source-meta').innerHTML = `<p class="small muted">${esc(v.channel.name)} · ${esc(fmtDate(v.pub))}</p><p class="source-title">${esc(v.cleanTitle)}</p><p class="small muted">${v.analysis ? `Análisis guardado ${esc(fmtDate(v.analysis.at))}; sin fuentes externas consultadas.` : 'Sin análisis · transcripción disponible.'}</p><a class="textbtn" href="${CR.yt(v.id)}" target="_blank" rel="noopener">Abrir en YouTube ${icon('external', 'i-s')}</a>`;

    ensurePlayer();
    const s = store.get('session', null);
    const start = q.t != null ? Number(q.t) : cur.id === id ? (player.video && player.video.id === id ? player.time() : cur.start) : s && s.v === id ? s.t : 0;
    if (cur.id !== id) {
      Object.assign(cur, { id, video: v, doc: null, blocks: [], nowBlock: -1, open: new Set(), gaps: new Set(), card: 0, synthesisTab: 'conclusion', start });
      videoOpen = false; videoPinned = false; pipClosed = true;
      ui.txq = ''; ui.follow = true;
      player.pause();
    } else if (q.t != null) { cur.start = Number(q.t); if (player.video && player.video.id === id) player.seek(cur.start, { play: false }); }
    cur.synthesisTab = 'conclusion';
    cur.lens = lensOf(q.lens) || (!v.analysis ? 'transcripcion' : q.n ? 'transcripcion' : 'sintesis');
    // Enlaces antiguos al texto (búsqueda en transcripciones) abren el texto completo; una nota, sus pasajes.
    if (cur.lens === 'transcripcion') ui.txmode = q.n ? 'notas' : q.lens === 'transcripcion' ? 'completo' : ui.txmode;
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
    loadVideoConnections(id, cur.doc.analysis_sha256);
  }
  async function loadVideoConnections(id, hash) {
    cur.semantic = [];
    if (!hash) return;
    try {
      const [links,feed] = await Promise.all(['social-connections','social-feed'].map(async name=>{
        const r=await fetch(`../data/${name}.json`,{cache:'no-store'});if(!r.ok)throw Error('Sin datos');return r.json();
      }));
      if(screen!==`v:${id}`||cur.doc?.analysis_sha256!==hash)return;
      const posts=new Map(window.UraniaFeed.select(feed,{account:'todos',period:'cuenta',q:''}).map(p=>[p.id,p]));
      cur.semantic=(links.connections||[]).filter(c=>c.video_id===id&&c.analysis_sha256===hash&&Date.parse(c.expires_at)>Date.now()&&posts.get(c.post_id)?.content_hash===c.post_content_hash);
      if(cur.semantic.length){const top=nbBody.scrollTop;renderNotebook();nbBody.scrollTop=top;}
    } catch (_) { /* Narrative reading remains available independently. */ }
  }
  function videoInfo(v) {
    const a = v.analysis;
    const step = (ok, label, small) => `<li><span class="${ok ? 'ok' : 'wait'}">${icon(ok ? 'check' : 'clock')}</span><span>${label}</span><small>${small}</small></li>`;
    return `
      <section class="vinfo">
        <p class="vinfo-who">${creatorAv(v.channel)}${esc(v.channel.name)} · ${fmtDate(v.pub, { weekday: true, time: true })}</p>
        <h1 class="vinfo-title">${esc(v.cleanTitle)}</h1>
        <div class="vtone">
          <div class="pulse-row">${chip(v.tone.label, { str: v.tone.str })}<span class="pulse-pct">${pct(v)}</span></div>
          ${v.tone.share != null ? `<div class="pulse-wave big">${CR.waveSvg(v.tone.wave, { w: 360, h: 44, gap: 1.5 })}</div>` : ''}
          <p class="small muted" style="margin-top:6px">Título: ${chip(v.tone.title.pol, { short: true })} ${v.tone.title.why.length ? CR.toneWhy(v.tone.title.why) : ''}</p>
          ${CR.titleGap(v) ? `<p class="gap-note">${icon('alert', 'i-s')}<span>El título insinúa ${CR.TONE[v.tone.title.pol].label.toLowerCase()}, pero el discurso suena ${CR.TONE[v.tone.label].label.toLowerCase()}.</span></p>` : ''}
          ${['up', 'down'].filter((k) => v.peaks && v.peaks[k]).map((k) => `<button class="peak peak-${k}" type="button" data-act="seek" data-t="${v.peaks[k].t}">${icon(k === 'up' ? 'trend-up' : 'trend-down', 'i-s')}<span><b>${k === 'up' ? 'Lo más alcista' : 'Lo más bajista'} · ${fmtT(v.peaks[k].t)}</b>«${esc(CR.clip(v.peaks[k].text, 130))}»</span></button>`).join('')}
        </div>
      </section>
      <ol class="process" aria-label="Estado del procesamiento">
        ${step(true, 'Transcripción disponible', `${v.segs} líneas`)}
        ${step(!!a, 'Afirmaciones extraídas', a ? a.claims : 'pendiente')}
        ${step(!!a, 'Activos vinculados', a ? esc(CR.clip(joinEs(a.assets.map((x) => CR.topicName(x))), 34)) || 'ninguno' : 'pendiente')}
        ${step(!!a, 'Análisis disponible', a ? `${a.estado === 'completo' ? 'completo' : 'parcial'} · ${fmtDate(a.at)}` : 'aún no pedido')}
      </ol>
      <div class="vinfo-actions">
        <button class="pill pill-solid" type="button" data-act="snap" data-snap="half">${icon('book')} Abrir el cuaderno</button>
        <a class="pill" href="${CR.yt(v.id)}" target="_blank" rel="noopener">${icon('external')} YouTube</a>
      </div>`;
  }
  function renderLenses() {
    const lenses = [['sintesis', 'Síntesis', 'flask'], ['transcripcion', 'Fuentes', 'text'], ['analisis', 'Análisis', 'book']];
    lensesEl.innerHTML = lenses.map(([k, label, ic]) => `<button class="lens" type="button" role="radio" aria-checked="${cur.lens === k}" data-act="lens" data-lens="${k}">${icon(ic)}${label}</button>`).join('');
  }
  function renderNow(t) {
    const v = cur.video;
    if (!v) return;
    const playing = player && player.playing;
    let text = '';
    let go = '';
    if (cur.doc && cur.doc.claims && cur.doc.claims.length) {
      const before = cur.doc.claims.filter((c) => c.t != null && c.t <= t + 1).sort((a, b) => b.t - a.t)[0];
      const next = cur.doc.claims.filter((c) => c.t != null && c.t > t + 1).sort((a, b) => a.t - b.t)[0];
      const c = before && t - before.t < 90 ? before : next;
      if (c) {
        text = `<b>${c === before ? 'Nota' : `A las ${fmtT(c.t)}`}</b> · ${L.tipo[c.tipo]}<span class="now-claim">${esc(c.text)}</span>`;
        go = `<button class="now-go" type="button" data-act="goto-note" data-c="${c.id}">Ir a la nota</button>`;
      }
    } else if (cur.doc) {
      const seg = cur.doc.segments[CR.segAt(cur.doc.segments, t)];
      text = `<b>${fmtT(t)}</b> · sin análisis<span class="now-claim">«${esc(seg ? seg.text : '')}»</span>`;
    }
    if (!text) text = `<b>${fmtT(t)}</b> · ${esc(v.channel.name)}<span class="now-claim">${esc(v.cleanTitle)}</span>`;
    if (cur.doc) {
      const tn = CR.toneAround(cur.doc, t);
      text = `<span class="now-tone">Ahora suena ${chip(tn.pol, { short: true })}</span>${text}`;
    }
    const snapBtn = nb.dataset.snap === 'peek'
      ? `<button class="ib" type="button" data-act="snap" data-snap="half" aria-label="Subir el cuaderno">${icon('chevron-up')}</button>`
      : `<button class="ib" type="button" data-act="snap" data-snap="peek" aria-label="Bajar el cuaderno y ver la ficha">${icon('chevron-down')}</button>`;
    nowEl.innerHTML = `<button class="now-play" id="now-play" type="button" data-act="toggle" aria-label="${playing ? 'Pausar' : 'Reproducir'}">${icon(playing ? 'pause' : 'play')}</button><p class="now-text">${text}</p><span style="display:flex;align-items:center">${go}${snapBtn}</span>`;
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
    const t = player?.video?.id === cur.id ? player.time() : cur.start || 0;
    el.innerHTML = CR.waveSvg(cur.video.tone.wave, { w: 300, h: 44, gap: 1, marks, playhead: t / dur,
      label: 'Tono del texto: verde al alza y rojo a la baja, de principio a fin del video' });
    document.getElementById('signal-seek').max = String(Math.floor(dur));
    document.getElementById('signal-duration').textContent = fmtT(dur);
    lastSignalSecond = -1;
    movePlayhead(t);
  }
  function movePlayhead(t) {
    if (signalScrubbing) return;
    paintSignalPosition(t);
  }
  function paintSignalPosition(t) {
    const line = document.querySelector('#nb-pulse .wv-head');
    if (!line || !cur.video) return;
    t = Math.max(0, Math.min(Number(t) || 0, cur.video.dur || 0));
    const fraction = t / (cur.video.dur || 1);
    const x = fraction * 300;
    line.setAttribute('x1', x); line.setAttribute('x2', x);
    const seek = document.getElementById('signal-seek');
    seek.value = String(Math.floor(t));
    document.getElementById('signal-scrubber').style.setProperty('--seek', `${fraction * 100}%`);
    document.getElementById('signal-preview').textContent = fmtT(t);
    seek.setAttribute('aria-valuetext', `${fmtT(t)} de ${fmtT(cur.video.dur || 0)}`);
    document.getElementById('signal-time').textContent = fmtT(t);
    if (cur.doc && Math.floor(t) !== lastSignalSecond) {
      lastSignalSecond = Math.floor(t);
      const tone = CR.toneAround(cur.doc, t);
      document.getElementById('signal-tone').innerHTML = chip(tone.pol, { short: true, prefix: 'Ahora' });
    }
  }
  const signalSeek = document.getElementById('signal-seek');
  let signalScrubbing = false;
  const signalScrubber = document.getElementById('signal-scrubber');
  signalSeek.addEventListener('pointerdown', () => {
    signalScrubbing = true;
    signalScrubber.dataset.seeking = 'true';
  });
  signalSeek.addEventListener('input', () => {
    signalScrubbing = true;
    paintSignalPosition(Number(signalSeek.value));
  });
  signalSeek.addEventListener('change', () => {
    signalScrubbing = false;
    if (signalMode && screen === `v:${cur.id}`) openPlayback(Number(signalSeek.value), true);
  });
  function finishSignalScrub(e) {
    signalScrubbing = false;
    delete signalScrubber.dataset.seeking;
    // Native range commits `change` after pointerup; keep its target until then.
    if (e.type !== 'pointerup' && player?.video?.id === cur.id) movePlayhead(player.time());
  }
  signalSeek.addEventListener('pointerup', finishSignalScrub);
  signalSeek.addEventListener('pointercancel', finishSignalScrub);
  signalSeek.addEventListener('blur', finishSignalScrub);
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
        <div><h5>Lo que dice ${esc(cur.video.channel.name)}</h5>${full.evidences.map((e) => `<blockquote>«${esc(e.cita || e.observacion || '')}»</blockquote><p class="small muted">${e.origen === 'titulo' ? 'Título del vídeo' : `${L.origen[e.origen]}${e.inicio_s != null ? ` · ${fmtT(e.inicio_s)}` : ''}`}${e.observacion && e.cita ? ` · Nota: ${esc(e.observacion)}` : ''}</p>`).join('')}</div>
        ${m ? `<div><h5>Extraído por el sistema</h5><dl>${kv('Activo', m.activo_normalizado || m.activo_literal)}${kv('Postura', m.postura)}${kv('Plazo', m.horizonte_literal)}${kv('Condición', m.condicion)}${kv('Objetivo', m.objetivo)}${kv('Invalidación', m.invalidacion)}${kv('Catalizador', m.catalizador)}</dl></div>` : ''}
        <div><h5>Por qué «${L.verif[c.verif].toLowerCase()}»</h5><p>${esc(full.justificacion)}</p></div>
        ${chains.map((ch) => `<div><h5>En el argumento · ${L.vinculo[ch.vinculo].toLowerCase()}</h5><p>${esc(ch.premisa)} → <b>${esc(ch.conclusion)}</b></p>${ch.supuesto ? `<p class="small" style="color:var(--pen)">Supuesto: ${esc(ch.supuesto)}</p>` : ''}</div>`).join('')}
        ${scen.length ? `<div><h5>Escenarios que la usan</h5>${scen.map((s) => `<p>${esc(s.nombre)} <span class="small muted">· ${L.plaus[s.plausibilidad].toLowerCase()}</span></p>`).join('')}</div>` : ''}
        ${pend.length ? `<div><h5>Pendiente de verificar</h5>${pend.map((p) => `<p>${esc(p.pregunta)}</p>`).join('')}</div>` : ''}
        ${(cur.semantic||[]).filter(x=>x.video_id===cur.id&&x.analysis_sha256===cur.doc.analysis_sha256&&x.claim_id===c.id&&Date.parse(x.expires_at)>Date.now()).map(x=>`<section class="post-semantic"><h5>Cruce con X · ${esc(REL_LABEL[x.relation] || x.relation.replaceAll('_',' '))}</h5><blockquote>«${esc(x.post_quote)}»</blockquote><p>${esc(x.explanation)}</p><p class="small muted">${esc(x.limitations)}</p><a href="https://x.com/i/web/status/${esc(x.post_id)}" target="_blank" rel="noopener noreferrer">@${esc(x.source_account)} · ${esc(fmtDate(x.post_published_at))} ↗</a><small>Declaración atribuida; no verifica por sí sola la tesis.</small></section>`).join('')}
        <p class="note-ext">${icon('alert')}<span>Sin fuentes externas consultadas: que el vídeo no lo pruebe no lo hace falso.</span></p>
        <div class="note-actions"><button class="textbtn" type="button" data-act="share-note" data-c="${c.id}">${icon('share')} Compartir esta nota</button></div>
      </div>`;
    }
    return `<div class="note" id="note-${c.id}" ${kc(c.tipo)}>
      <p class="note-h">${chip(c.pol, { str: c.polStr, insinua: c.insinua })}<span class="note-k">${L.tipo[c.tipo]}</span><span class="sep">·</span><span>${L.verif[c.verif]}</span><span class="sep">·</span><span>convicción ${CR.nivel(c.conv).toLowerCase()}</span></p>
      <p class="note-text">${esc(c.text)}</p>
      ${c.pol !== 'neutra' && c.polWhy.length ? `<p class="note-why">Se lee ${esc(CR.TONE[c.pol].label.toLowerCase())} ${CR.toneWhy(c.polWhy)}${c.qPol !== 'neutra' && c.qPol !== c.pol ? `; la cita, en cambio, suena ${esc(CR.TONE[c.qPol].label.toLowerCase())}` : ''}.</p>` : ''}
      <div class="note-actions">
        ${c.t != null ? `<button class="textbtn" type="button" data-act="seek" data-t="${c.t}">${icon('play')} Escuchar ${fmtT(c.t)}</button>` : ''}
        <button class="textbtn" type="button" data-act="expand" data-c="${c.id}" aria-expanded="${open}">${open ? 'Cerrar' : 'Examinar'} ${icon(open ? 'chevron-up' : 'chevron-down')}</button>
        ${c.assets.map((a) => `<button class="note-chip" type="button" data-act="asset" data-id="${a}">${esc(CR.topicName(a))}</button>`).join('')}
      </div>
      ${more}
    </div>`;
  }
  function rowHtml(b, i, withNotes) {
    const notes = cur.notesAt.get(i) || [];
    const bt = CR.blockTone(cur.doc, b.i0, b.i1);
    const T = CR.TONE[bt.pol];
    return `<div class="doc-row tone-row-${T.cls}" data-i="${i}">
      <button class="doc-t" type="button" data-act="seek" data-t="${b.start}" aria-label="Escuchar desde ${fmtT(b.start)}. Tramo ${T.label.toLowerCase()}">${fmtT(b.start)}${bt.pol !== 'neutra' ? `<span class="doc-tone tone-${T.cls}" title="Tramo ${T.label.toLowerCase()} ${esc(CR.toneWhy(bt.why))}">${icon(T.icon, 'i-s')}</span>` : ''}</button>
      <div class="doc-main"><p class="doc-text">${markText(b.text, i)}</p>
        ${withNotes ? notes.map(noteHtml).join('') : notes.map((c) => (cur.open.has(c.id) ? noteHtml(c) : `<button class="marker" type="button" data-act="expand" data-c="${c.id}" ${kc(c.tipo)}>${icon(CR.TONE[c.pol].icon, 'i-s')}${L.tipo[c.tipo]} · ${CR.TONE[c.pol].label.toLowerCase()}</button>`)).join('')}
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
  /* ---------- Síntesis: primera lectura de un vídeo analizado ----------
     Reutiliza campos guardados del análisis (resumen, escenarios, seguimiento). No genera texto nuevo ni recorta
     frases: lo que no cabe en la vista inicial queda en desplegables con el texto completo. */
  const REL_LABEL = { apoyo_declarado: 'Apoya', contrapunto: 'Cuestiona', actualizacion: 'Actualiza; no implica confirmar', contexto: 'Contexto; no suma respaldo' };
  const SCN_ORIGIN = { creador: 'Planteado por el creador', analista: 'Escenario del analista, no del creador' };
  const LENSES = ['sintesis', 'transcripcion', 'analisis'];
  // Enlaces antiguos: «destilado» abre la Síntesis; lo desconocido no se interpreta.
  const lensOf = (l) => (l === 'destilado' ? 'sintesis' : LENSES.includes(l) ? l : null);
  function timeChips(ids, max = 3) {
    const seen = new Set();
    const evs = ids.flatMap((id) => { const c = CR.claim(cur.doc, id); return c ? c.evidences : []; })
      .filter((e) => e.inicio_s != null && e.origen === 'transcripcion' && !seen.has(e.id) && seen.add(e.id))
      .sort((a, b) => a.inicio_s - b.inicio_s).slice(0, max);
    return evs.length ? `<p class="syn-chips">${evs.map((e) => `<button class="tchip" type="button" data-act="seek" data-t="${e.inicio_s}" aria-label="Escuchar la fuente en ${fmtT(e.inicio_s)}">${icon('play', 'i-s')}${fmtT(e.inicio_s)}</button>`).join('')}</p>` : '';
  }
  const claimAssets = (ids) => [...new Set(ids.flatMap((id) => (cur.doc.claimsById[id] || {}).assets || []))];
  function scenarioHtml(s) {
    const list = (title, items) => (items && items.length ? `<p class="syn-sub">${title}</p><ul>${items.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : '');
    return `<article class="syn-scn" id="scn-${esc(s.id)}" data-origin="${esc(s.origen)}" tabindex="-1">
      <p class="syn-tags"><span class="syn-tag ${s.origen === 'creador' ? 'is-creator' : 'is-analyst'}">${SCN_ORIGIN[s.origen] || esc(s.origen)}</span><span class="syn-tag">${esc(L.plaus[s.plausibilidad] || s.plausibilidad)}</span></p>
      <h4>${esc(s.nombre)}</h4>
      ${s.horizonte ? `<p class="syn-meta">${esc(s.horizonte)}</p>` : ''}
      <p>${esc(s.mecanismo)}</p>
      <details class="syn-more"><summary>Condiciones y evidencia</summary>
        ${s.invalidacion ? `<p class="syn-inv"><b>Lo invalidaría:</b> ${esc(s.invalidacion)}</p>` : ''}
        ${list('Señales a favor', s.senales_a_favor)}${list('Señales en contra', s.senales_en_contra)}${list('Supuestos', s.supuestos)}${list('Catalizadores', s.catalizadores)}${list('Evidencia que falta', s.evidencia_faltante)}
        <p class="small muted">${s.probabilidad == null ? 'Sin probabilidad numérica: no hay método que la respalde.' : `Probabilidad ${esc(s.probabilidad)}`}</p>
      </details>
      ${timeChips(s.afirmacion_ids)}
    </article>`;
  }
  function watchHtml(w, scenarios) {
    const assets = claimAssets(w.afirmacion_ids).filter((x) => idx.topicsById[x]);
    const linked = scenarios.filter((s) => s.afirmacion_ids.some((id) => w.afirmacion_ids.includes(id)));
    return `<li class="syn-watch">
      <p class="syn-what">${esc(w.que_observar)}</p>
      <p class="syn-crit">${esc(w.criterio)}</p>
      <p class="syn-meta">${w.plazo ? `<span>${esc(w.plazo)}</span>` : ''}<span>Criterio ${w.origen_criterio === 'creador' ? 'del creador' : 'del analista'}</span></p>
      <details class="syn-more"><summary>Fuente${linked.length ? ` · ${linked.length} escenarios vinculados` : ''}</summary>
        ${assets.length ? `<p>${esc(joinEs(assets.map((x) => CR.topicName(x))))}</p>` : ''}
        ${w.dato_o_fuente_necesaria ? `<p>${esc(w.dato_o_fuente_necesaria)}</p>` : ''}
        ${linked.map((s) => `<button class="textbtn syn-goto" type="button" data-act="goto-scn" data-s="${esc(s.id)}">${esc(s.nombre)} ${icon('chevron-right', 'i-s')}</button>`).join('')}
        ${timeChips(w.afirmacion_ids, 2)}
      </details>
    </li>`;
  }
  function sintesisHtml() {
    const a = cur.doc.analysis, v = cur.video, r = a.resumen;
    // Primero los escenarios del creador; los del analista conservan su atribución. Orden estable.
    const scenarios = a.escenarios.map((s, i) => ({ s, i })).sort((x, y) => (x.s.origen === 'creador' ? 0 : 1) - (y.s.origen === 'creador' ? 0 : 1) || x.i - y.i).map((x) => x.s);
    const watch = a.seguimiento;
    const assets = (v.analysis.assets || []).filter((x) => idx.topicsById[x]);
    const links = (cur.semantic || []).filter((x) => x.video_id === cur.id && x.analysis_sha256 === cur.doc.analysis_sha256 && Date.parse(x.expires_at) > Date.now());
    const theses = window.UraniaTheses && idx.theses ? window.UraniaTheses.forVideo(idx, cur.id) : [];
    const rest = (items, n, label, render) => (items.length > n ? `<details class="syn-rest"><summary>${label(items.length - n)}</summary>${items.slice(n).map(render).join('')}</details>` : '');
    const brief = window.UraniaEditorial.brief(cur.id, cur.doc.analysis_sha256);
    const tab = cur.synthesisTab || 'conclusion';
    return `<div class="syn" aria-label="Síntesis del análisis">
      <nav class="syn-nav" aria-label="Secciones de síntesis">${[['conclusion','Conclusión'],['escenarios',`Escenarios ${scenarios.length}`],['vigilar',`Vigilar ${watch.length}`],['contraste','Contraste']].map(([key,label]) => `<button type="button" data-act="synthesis-tab" data-tab="${key}" aria-pressed="${tab === key}">${label}</button>`).join('')}</nav>
      <section class="syn-sec" aria-labelledby="syn-h-plantea"${tab !== 'conclusion' ? ' hidden' : ''}>
        <p class="syn-byline">${creatorAv(v.channel)}${esc(v.channel.name)} · ${esc(fmtDate(v.pub))}</p>
        <h3 class="syn-k" id="syn-h-plantea">Su tesis</h3>
        <p class="syn-lead">${esc(brief ? brief.thesis : r.tesis_principal)}</p>
        ${brief ? `<p class="syn-condition"><b>Condiciones y límites</b>${esc(brief.condition)}</p>` : ''}

        <details class="syn-more"><summary>Argumento completo y evidencia</summary>
          ${brief ? `<p><b>Tesis original.</b> ${esc(r.tesis_principal)}</p>` : ''}
          <p><b>Mensaje explícito.</b> ${esc(r.mensaje_explicito)}</p><p><b>Respaldo demostrable con lo recibido.</b> ${esc(r.respaldo_demostrable)}</p>
        </details>

      </section>
      <section class="syn-sec" aria-labelledby="syn-h-esc"${tab !== 'escenarios' ? ' hidden' : ''}>
        <h3 class="syn-k" id="syn-h-esc">Escenarios <small>${scenarios.length}</small></h3>
        ${scenarios.length ? scenarios.slice(0, 2).map(scenarioHtml).join('') + rest(scenarios, 2, (n) => `Ver ${n === 1 ? 'el otro escenario' : `los otros ${n} escenarios`}`, scenarioHtml) : '<p class="syn-empty">El análisis no recoge escenarios para este vídeo.</p>'}
      </section>
      <section class="syn-sec" aria-labelledby="syn-h-vig"${tab !== 'vigilar' ? ' hidden' : ''}>
        <h3 class="syn-k" id="syn-h-vig">Qué vigilar <small>${watch.length}</small></h3>
        ${watch.length ? `<ul class="syn-watch-list">${watch.slice(0, 3).map((w) => watchHtml(w, scenarios)).join('')}</ul>${rest(watch, 3, (n) => `Ver todas (${n} más)`, (w) => `<ul class="syn-watch-list">${watchHtml(w, scenarios)}</ul>`)}` : '<p class="syn-empty">El análisis no deja señales de seguimiento para este vídeo.</p>'}
      </section>
      <section class="syn-sec" aria-labelledby="syn-h-con"${tab !== 'contraste' ? ' hidden' : ''}>
        <h3 class="syn-k" id="syn-h-con">Contrastar esta tesis</h3>
        ${theses.length ? `<p class="syn-sub">Tesis aceptadas en las que participa</p><ul class="syn-theses">${theses.map((t) => `<li><a href="${t.assets.length ? CR.hash(['f', t.assets.includes('btc') ? 'btc' : t.assets[0]], { tesis: t.id }) : '#/'}"><b>${esc(t.label)}</b><small>${esc(t.relationLabel)} · ${CR.plural(t.creators, 'creador', 'creadores')} en esta tesis</small></a></li>`).join('')}</ul>` : ''}
        ${assets.length ? `<p class="syn-sub">Activos tratados en el análisis</p><p class="syn-assets">${assets.map((x) => `<a class="note-chip" href="#/f/${esc(x)}">${esc(CR.topicName(x))}</a>`).join('')}</p>` : ''}
        ${links.length ? `<p class="syn-sub">Publicaciones de X conectadas</p>${links.slice(0, 2).map((x) => `<blockquote class="syn-x"><b>${esc(REL_LABEL[x.relation] || x.relation)}</b> · @${esc(x.source_account)}: «${esc(x.post_quote)}»</blockquote>`).join('')}` : '<p class="syn-empty">Sin conexiones aceptadas con publicaciones de X para este análisis. Un mismo ticker no se cuenta como apoyo.</p>'}
        ${!theses.length ? '<p class="syn-empty">Este vídeo aún no está clasificado en ninguna tesis aceptada; sus afirmaciones siguen disponibles en «Fuentes y texto».</p>' : ''}
      </section>

    </div>`;
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
    setStage();
    cur.nowBlock = -1;
    let html = '';
    if (cur.lens === 'analisis') {
      html = doc.analysis
        ? `<div class="cards-nav"><button class="ib" type="button" data-act="card" data-d="-1" aria-label="Ficha anterior"${cur.card === 0 ? ' disabled' : ''}>${icon('chevron-left')}</button>
            <label class="sr" for="card-sel">Ir a la ficha</label><select id="card-sel">${CARDS.map((c, i) => `<option value="${i}"${i === cur.card ? ' selected' : ''}>${i + 1}. ${c}</option>`).join('')}</select>
            <button class="ib" type="button" data-act="card" data-d="1" aria-label="Ficha siguiente"${cur.card === CARDS.length - 1 ? ' disabled' : ''}>${icon('chevron-right')}</button></div>${cardHtml(cur.card)}`
        : pendingNb(video);
    } else if (cur.lens === 'transcripcion') {
      // «Fuentes y texto»: pasajes con notas (lo que antes era Destilado) o el texto completo con buscador.
      const mode = doc.analysis && !ui.txq ? ui.txmode : 'completo';
      html = `<div class="nb-tools">${doc.analysis ? `<div class="tx-mode" role="radiogroup" aria-label="Qué texto mostrar"><button type="button" role="radio" data-act="txmode" data-m="notas" aria-checked="${mode === 'notas'}">Pasajes con notas</button><button type="button" role="radio" data-act="txmode" data-m="completo" aria-checked="${mode === 'completo'}">Texto completo</button></div>` : ''}<label class="field">${icon('search')}<span class="sr">Buscar en el texto</span><input id="txq" type="search" placeholder="Buscar en el texto" value="${esc(ui.txq)}" autocomplete="off" enterkeyhint="search"></label></div>
        ${mode === 'notas' ? destiladoHtml() : cur.blocks.map((b, i) => rowHtml(b, i, false)).join('')}`;
    } else {
      html = doc.analysis ? sintesisHtml() : pendingNb(video);
    }
    nbBody.innerHTML = html + (cur.lens === 'transcripcion' ? `<button class="pill follow-btn" type="button" data-act="follow" id="follow" hidden>${icon('target')} Volver al minuto actual</button>` : '');
    const sel = document.getElementById('card-sel');
    if (sel) sel.addEventListener('change', () => { cur.card = Number(sel.value); renderNotebook(); });
    const input = document.getElementById('txq');
    if (input) input.addEventListener('input', CR.debounce(() => {
      const wasEmpty = !ui.txq;
      ui.txq = input.value.trim();
      if (wasEmpty && ui.txq && ui.txmode === 'notas' && cur.doc.analysis) { const pos = input.selectionStart; renderNotebook(); const again = document.getElementById('txq'); if (again) { again.focus(); again.setSelectionRange(pos, pos); } return; }
      CR.$$('.doc-row', nbBody).forEach((row) => { const i = Number(row.dataset.i); row.querySelector('.doc-text').innerHTML = markText(cur.blocks[i].text, i); });
      const first = nbBody.querySelector('mark.q');
      if (first) { ui.follow = false; first.scrollIntoView({ block: 'center' }); }
    }, 220));
    if (player) { syncDoc(player.time(), true); renderNow(player.time()); }
  }
  function pendingNb(v) {
    const names = topicNames(v, 4);
    return `<div class="nb-pending"><h3>Aún sin notas</h3><p>Este vídeo no se ha analizado: no hay afirmaciones ni interpretaciones. El texto completo está en «Fuentes y texto»${names.length ? `, y en él se nombra ${esc(joinEs(names))}` : ''}.</p>
      <div style="margin-top:12px"><button class="pill pill-solid" type="button" data-act="lens" data-lens="transcripcion">${icon('text')} Leer el texto</button></div></div>`;
  }
  let autoScrolling = false;
  function syncDoc(t, force) {
    if (!cur.blocks.length || cur.lens !== 'transcripcion') return;
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
    if (cur.lens !== 'transcripcion' || !cur.open.has(id)) {
      cur.open.add(id);
      if (cur.lens !== 'transcripcion') { cur.lens = 'transcripcion'; ui.txmode = 'notas'; }
      renderNotebook();
    }
    if (nb.dataset.snap === 'peek') setSnap('half');
    const el = document.getElementById(`note-${id}`);
    if (el) { ui.follow = false; const f = document.getElementById('follow'); if (f) f.hidden = false; el.scrollIntoView({ block: 'center', behavior: CR.reduced() ? 'auto' : 'smooth' }); }
  }
  function applyVideoQuery(q) {
    const lens = lensOf(q.lens);
    if (lens === 'transcripcion' && !q.n) ui.txmode = 'completo';
    if (lens && lens !== cur.lens) { cur.lens = lens; renderNotebook(); }
    if (q.n && cur.doc && cur.doc.claimsById[q.n]) {
      cur.open.add(q.n);
      renderNotebook();
      requestAnimationFrame(() => gotoNote(q.n));
    }
  }

  /* ---------- activos: mapa de calor ---------- */
  function dayRange() {
    const start = new Date(idx.period.from), end = new Date(idx.period.to);
    const days = [];
    for (let d = new Date(start.getFullYear(), start.getMonth(), start.getDate()); d <= end; d.setDate(d.getDate() + 1)) days.push(new Date(d));
    return days;
  }
  function renderAssets(section, order) {
    const s = section || ui.section;
    ui.section = s; store.set('section', s);
    const o = order || ui.order || 'videos';
    ui.order = o;
    const net = (t) => CR.netSent(t.sent).net;
    const rows = idx.topics.filter((t) => t.section === s).sort((a, b) => (o === 'alza' ? net(b) - net(a) || b.vc - a.vc : o === 'baja' ? net(a) - net(b) || b.vc - a.vc : b.vc - a.vc || b.n - a.n));
    const days = dayRange();
    const keyOf = (d) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    const cellsOf = (t) => days.map((d) => {
      const ms = t.videos.filter((m) => CR.dayKey(idx.videosById[m.v].pub) === keyOf(d));
      const sent = { alcista: 0, bajista: 0, mixta: 0, neutra: 0 };
      ms.forEach((m) => Object.keys(sent).forEach((k) => { sent[k] += (m.sent || {})[k] || 0; }));
      return { n: ms.reduce((acc, m) => acc + m.n, 0), pol: CR.netSent(sent).pol, sent };
    });
    const cells = rows.map(cellsOf);
    const matrix = cells.map((r) => r.map((c) => c.n));
    const max = Math.max(1, ...matrix.flat());
    const level = (n) => (n === 0 ? 0 : Math.min(4, Math.ceil((n / max) * 4)));
    const LETTER = ['D', 'L', 'M', 'X', 'J', 'V', 'S'];
    const btc = idx.topicsById.btc;
    page.innerHTML = `
      <div class="pad"><h1 class="title-xl">Activos</h1><p class="lede">Cuántas veces se nombra cada uno y con qué tono, día por día: verde si la frase empuja al alza, rojo si empuja a la baja.</p></div>
      <nav class="switch" aria-label="Secciones">${['altcoins', 'macro', 'bolsa'].map((k) => `<a href="#/?s=${k}&o=${o}"${k === s ? ' aria-current="page"' : ''}>${L.section[k]}</a>`).join('')}</nav>
      <div class="order pad" role="group" aria-label="Ordenar">${[['videos', 'Más vídeos'], ['alza', 'Más alcista'], ['baja', 'Más bajista']].map(([k, l]) => `<a href="#/?s=${s}&o=${k}"${k === o ? ' aria-current="true"' : ''}>${l}</a>`).join('')}</div>
      ${s === 'altcoins' ? `<a class="btc-strip" href="#/f/btc"><span><b>Bitcoin</b> queda fuera del ranking: aparece en ${btc.vc} de ${idx.videos.length} vídeos y ${btc.claims.length} afirmaciones analizadas.</span>${icon('chevron-right')}</a>` : ''}
      <div class="heat" style="--days:${days.length}" role="table" aria-label="Menciones por día">
        <div class="heat-head" role="row"><span role="columnheader">${o === 'videos' ? 'Ranking por vídeos' : o === 'alza' ? 'Del más alcista' : 'Del más bajista'}</span>${days.map((d) => `<span role="columnheader">${LETTER[d.getDay()]}<br>${d.getDate()}</span>`).join('')}</div>
        ${rows.map((t, i) => `<a class="heat-row" role="row" href="#/f/${t.id}">
          <span class="heat-name" role="cell"><b>${i + 1}. ${esc(t.name)}${t.claims.length ? `<i class="an-dot" title="Tiene afirmaciones analizadas"></i><span class="sr"> (con afirmaciones analizadas)</span>` : ''}</b><small>${termo(t.sent)}<span class="mini-n"><span class="t-up">${t.sent.alcista}</span>/<span class="t-down">${t.sent.bajista}</span></span></small></span>
          ${cells[i].map((c, j) => `<span class="cell" role="cell" data-l="${level(c.n)}" data-t="${CR.TONE[c.pol].cls}" aria-label="${days[j].getDate()} oct: ${c.n} menciones, tono ${CR.TONE[c.pol].label.toLowerCase()}">${c.n || ''}</span>`).join('')}
        </a>`).join('')}
      </div>
      <div class="heat-legend"><span class="cell" data-l="3" data-t="up"></span><span>alcista</span><span class="cell" data-l="3" data-t="down"></span><span>bajista</span><span class="cell" data-l="3" data-t="mix"></span><span>mixto</span><span class="cell" data-l="3" data-t="flat"></span><span>sin tono</span><span>· más intenso = más menciones</span><i class="an-dot"></i><span>con afirmaciones analizadas</span></div>
      <p class="pad small muted" style="margin-top:10px">Bajo cada nombre: menciones en frases alcistas / bajistas. ${esc(idx.method.tone)}</p>
      <p class="pad small muted" style="margin-top:14px">${esc(idx.method.mentions)}</p>`;
  }
  function renderAsset(id, day) {
    const t = idx.topicsById[id];
    if (!t) { page.innerHTML = `<div class="empty"><h3>Activo no encontrado</h3><a class="pill" href="#/">Ver activos</a></div>`; return; }
    const claims = t.claims.map((k) => idx.claimsByKey[`${k.v}:${k.id}`]).filter(Boolean);
    const byDay = [];
    t.videos.forEach((m) => { const v = idx.videosById[m.v]; const k = CR.dayKey(v.pub); if (!byDay.length || byDay[byDay.length - 1].k !== k) byDay.push({ k, iso: v.pub, items: [] }); byDay[byDay.length - 1].items.push(m); });
    page.innerHTML = `
      <div class="pad"><a class="textbtn" href="#/?s=${t.section === 'bitcoin' ? 'altcoins' : t.section}">${icon('arrow-left')} Activos</a>
        <h1 class="title-xl" style="margin-top:4px">${esc(t.name)}</h1>
        <p class="lede">${L.section[t.section]} · ${CR.plural(t.vc, 'vídeo', 'vídeos')} · ${CR.plural(t.n, 'mención', 'menciones')} · ${CR.plural(t.cc, 'creador', 'creadores')}${t.note ? `. Ojo: ${esc(t.note)}` : ''}.</p>
        <div class="asset-tone">${chip(CR.netSent(t.sent).pol)}<div class="ap-bar">${termo(t.sent, { big: true, needle: true, bulbs: true })}</div>
          <p class="small"><span class="t-up">${icon('trend-up', 'i-s')}${t.sent.alcista} en frases alcistas</span> · <span class="t-down">${icon('trend-down', 'i-s')}${t.sent.bajista} bajistas</span> · <span class="t-mix">${t.sent.mixta} mixtas</span> · ${t.sent.neutra} sin tono</p></div></div>
      ${claims.length ? `<div class="pad" style="margin-top:18px"><h2 class="title-l">Notas del análisis</h2>${claims.map((c) => { const v = idx.videosById[c.v]; return `<div style="margin-top:12px">${c.quote ? `<p class="small muted">${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${fmtT(c.t)}</p><blockquote style="margin:4px 0 0;font-family:var(--serif);font-size:16px">«${esc(c.quote)}»</blockquote>` : ''}<div class="note" ${kc(c.tipo)}><p class="note-h">${chip(c.pol, { str: c.polStr, insinua: c.insinua })}<span class="note-k">${L.tipo[c.tipo]}</span><span class="sep">·</span><span>${L.verif[c.verif]}</span></p><p class="note-text">${esc(c.text)}</p><div class="note-actions"><a class="textbtn" href="#/v/${v.id}?t=${Math.floor(c.t || 0)}&n=${c.id}">${icon('play')} Abrir en el cuaderno</a></div></div></div>`; }).join('')}</div>`
        : `<div class="nb-pending"><h3>Sin notas del análisis</h3><p>Se nombra en las transcripciones, pero los ${idx.analyzed.length} vídeos analizados no lo tratan como afirmación.</p></div>`}
      <div class="pad" style="margin-top:22px"><h2 class="title-l">Menciones, día a día</h2></div>
      ${byDay.map((d) => `<section class="day" id="d-${d.k}"><h3 class="day-h">${esc(CR.dayLabel(d.iso))}<small>${CR.plural(d.items.length, 'vídeo', 'vídeos')}</small></h3>
        <div class="thread">${d.items.map((m) => { const v = idx.videosById[m.v]; return `<div class="t-entry${v.analysis ? ' full' : ''}"><p class="meta">${esc(v.channel.name)} · ${CR.plural(m.n, 'mención', 'menciones')} ${termo(m.sent || {})}</p><h4><a href="#/v/${v.id}">${esc(v.cleanTitle)}</a></h4>${m.frags.map((f) => `<div class="t-frag">${chip(f.pol, { short: true })}<blockquote class="q-${CR.TONE[f.pol].cls}">«${esc(f.text)}»</blockquote><a class="textbtn" href="#/v/${v.id}?t=${Math.floor(f.t)}">${icon('play')} ${fmtT(f.t)}</a></div>`).join('')}</div>`; }).join('')}</div></section>`).join('')}`;
    if (day) {
      const d = new Date(day);
      const el = document.getElementById(`d-${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`);
      if (el) requestAnimationFrame(() => el.scrollIntoView());
    }
  }

  /* ---------- hilos ---------- */
  function axisHtml(th) {
    const from = new Date(idx.period.from).getTime(), to = new Date(idx.period.to).getTime();
    const pos = (iso) => ((new Date(iso).getTime() - from) / Math.max(1, to - from)) * 100;
    return `<div class="axis" aria-hidden="true">${th.sources.map((s) => { const v = idx.videosById[s.v]; return `<i class="${s.claims.length ? 'full' : ''} ax-${CR.TONE[v.tone.label].cls}" style="left:${pos(v.pub)}%" title="${esc(v.channel.name)}, ${fmtDate(v.pub)}: tono ${CR.TONE[v.tone.label].label.toLowerCase()}"></i>`; }).join('')}<span class="first" style="left:0">${fmtDate(idx.period.from)}</span><span class="last" style="left:100%">${fmtDate(idx.period.to)}</span></div>`;
  }
  function renderThreads() {
    page.innerHTML = `
      <div class="pad"><h1 class="title-xl">Hilos</h1><p class="lede">Ideas que aparecen en varios vídeos, en orden de publicación. Cada punto lleva el color del tono de su vídeo; relleno si está analizado.</p></div>
      ${idx.themes.map((th) => `<a class="thread-card" href="#/n/${th.id}"><div class="tc-tone">${chip(CR.netSent(th.sent).pol)}${termo(th.sent)}</div><h3>${esc(th.title)}</h3><p>${esc(th.about)}</p>${axisHtml(th)}<p class="small muted" style="margin-top:14px">${CR.plural(th.videoCount, 'vídeo', 'vídeos')} · ${th.analyzedCount} con análisis${th.contrasts.length ? ` · ${CR.plural(th.contrasts.length, 'cruce', 'cruces')} detectado${th.contrasts.length > 1 ? 's' : ''}` : ''}</p></a>`).join('')}
      <p class="pad small muted" style="margin-top:16px">${esc(idx.method.themes)}</p>`;
  }
  function forkHtml(p) {
    const A = idx.claimsByKey[`${p.a.v}:${p.a.id}`], B = idx.claimsByKey[`${p.b.v}:${p.b.id}`];
    const va = idx.videosById[p.a.v], vb = idx.videosById[p.b.v];
    const title = `${Theses.contrastLabel(p)} sobre ${CR.topicName(p.asset)}`;
    const why = p.kind === 'cambio'
      ? (p.sameCreator ? 'Detectado por reglas: mismo creador, activo y plazo, postura contraria. El sistema no decide quién acierta.' : 'Detectado por reglas: autores distintos, mismo activo y plazo, posturas contrarias. No es un cambio de postura de nadie.')
      : (p.sameCreator ? 'Lo repite el mismo creador: es repetición, no una prueba independiente.' : 'Coinciden fuentes distintas; no se ha comprobado que sean independientes.');
    return `<div class="fork"><h4>${esc(title)} · ${L.hz[p.hz].toLowerCase()}</h4>
      <p>${why}</p>
      <div class="sides">
        <div class="side side-${CR.TONE[A.pol].cls}"><b>${p.sameCreator ? 'Antes' : esc(va.channel.name)} · ${fmtDate(va.pub)} · ${fmtT(A.t)}</b>${chip(A.pol, { short: true })}<blockquote>«${esc(CR.clip(A.quote || A.text, 140))}»</blockquote><a class="textbtn" href="#/v/${va.id}?t=${Math.floor(A.t || 0)}&n=${A.id}">${icon('play')} Escuchar</a></div>
        <div class="side side-${CR.TONE[B.pol].cls}"><b>${p.sameCreator ? 'Después' : esc(vb.channel.name)} · ${fmtDate(vb.pub)} · ${fmtT(B.t)}</b>${chip(B.pol, { short: true })}<blockquote>«${esc(CR.clip(B.quote || B.text, 140))}»</blockquote><a class="textbtn" href="#/v/${vb.id}?t=${Math.floor(B.t || 0)}&n=${B.id}">${icon('play')} Escuchar</a></div>
      </div></div>`;
  }
  function renderThread(id) {
    const th = idx.themesById[id];
    if (!th) { page.innerHTML = `<div class="empty"><h3>Tema no encontrado</h3><a class="pill" href="#/?tab=tesis">Ver tesis y temas</a></div>`; return; }
    const related = idx.theses && idx.theses.status === 'ok' ? idx.theses.items.filter((t) => t.topic_id === th.id && Theses.thesisStats(idx, t.id).members.length) : [];
    const sources = th.sources.slice().sort((a, b) => idx.videosById[a.v].pub.localeCompare(idx.videosById[b.v].pub));
    const forksAfter = new Map();
    th.contrasts.forEach((i) => { const p = idx.contrasts[i]; forksAfter.set(p.b.v, (forksAfter.get(p.b.v) || []).concat(p)); });
    page.innerHTML = `
      <div class="pad"><a class="textbtn" href="#/?tab=tesis">${icon('arrow-left')} Tesis y temas</a>
        <p class="th-k" style="margin-top:6px">Tema del archivo · agrupación por palabras clave, no una tesis</p>
        <h1 class="title-xl" style="margin-top:4px">${esc(th.title)}</h1><p class="lede">${esc(th.about)}</p>
        ${related.length ? `<div class="th-related"><p class="syn-sub">Tesis aceptadas sobre este tema</p>${related.map((t) => `<a class="note-chip" href="${CR.hash(['f', [...Theses.linkedAssets(idx, t)].find((x) => idx.topicsById[x]) || 'btc'], { tesis: t.id })}">${esc(t.label)}</a>`).join('')}</div>` : ''}
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

  /* ---------- feed de X (radar + bento) ---------- */
  let feedRouteKey = null, feedRequest = 0, feedRefresh = null;
  function feedFilters(q = {}) {
    const ctx = /^[a-z0-9]{1,20}$/.test(q.cf || '') ? { cf: q.cf, ct: /^[a-z0-9-]{1,60}$/.test(q.ct || '') ? q.ct : '', cn: String(q.cn || '').slice(0, 120) } : { cf: '', ct: '', cn: '' };
    return {...ctx, account: /^[a-z0-9_]{1,15}$/.test(q.account || '') ? q.account : 'todos', period:q.period === '48h' ? '48h' : 'cuenta', quality:['todos','secundario'].includes(q.quality)?q.quality:'relevante', length:['micro','breve','medio','largo'].includes(q.length)?q.length:'todos', narrative:/^[a-z_]{1,40}$/.test(q.narrative||'')?q.narrative:'todas', asset:/^[A-Z0-9]{1,12}$/.test(q.asset||'')?q.asset:'', q:String(q.q || '').slice(0,200)};
  }
  const FEED_TONES = ['#a6f136', '#b69cff', '#7fb2ff', '#ff9d7a', '#5fe3c8', '#f6c65b', '#ff8fc4', '#9fe6ff'];
  const FEED_PAGE = 24;
  const RADAR_SPOTS = [[50, 50], [23, 31], [77, 29], [21, 73], [79, 71], [50, 15], [50, 86]];
  /* Pieza del bento según el largo: L ancho y alto, M media columna alta, S media columna, W cita ancha. */
  function feedSize(p) {
    const n = p.text.length;
    if (n > 320) return 'L';
    if (n < 70 && !/https?:\/\//.test(p.text)) return 'W';
    return n > 160 ? 'M' : 'S';
  }
  let feedPostOpen = false;
  async function renderFeed(query = {}, incoming = null) {
    const token=++feedRequest, filters=feedFilters(query);
    feedRouteKey=JSON.stringify(filters);
    if(!incoming)page.innerHTML=`<section class="social-feed fr"><div id="feed-main" aria-live="polite"><p class="feed-status">Cargando publicaciones…</p></div></section>`;
    let data;
    try {
      if(incoming)data=incoming.data;
      else {const response=await fetch('../data/social-feed.json',{cache:'no-store'});
        if(!response.ok)throw Error('Feed no disponible');
        data=await response.json();}
      if(data.version!==1||!Array.isArray(data.posts)||!Array.isArray(data.accounts))throw Error('Formato inválido');
    } catch (_) {
      if(token!==feedRequest||screen!=='feed')return;
      document.getElementById('feed-main').innerHTML='<div class="empty"><h2>No pudimos cargar el Feed</h2><p>Los videos y análisis siguen disponibles. Puedes volver a intentarlo.</p><button class="pill" type="button" id="feed-retry">Reintentar</button></div>';
      feedRefresh=async()=>{if(token===feedRequest&&screen==='feed')await renderFeed(filters);};
      document.getElementById('feed-retry').addEventListener('click',()=>renderFeed(filters));
      setTimeout(()=>{if(document.visibilityState==='visible')feedRefresh?.();},60000);return;
    }
    if(token!==feedRequest||screen!=='feed')return;
    let semantic=incoming?.semantic||{connections:[],status:'pendiente'};
    if(!incoming)try{const r=await fetch('../data/social-connections.json',{cache:'no-store'});if(r.ok)semantic=await r.json();}catch(_){}
    if(token!==feedRequest||screen!=='feed')return;
    const connectionsOf=p=>(semantic.connections||[]).filter(c=>c.post_id===p.id&&c.post_content_hash===p.content_hash&&Date.parse(c.expires_at)>Date.now());
    const accounts=new Map(data.accounts.map((a,i)=>[a.handle,{...a,tone:FEED_TONES[i%FEED_TONES.length],avatar:window.UraniaFeed.safeURL((data.posts.find(p=>p.author_handle===a.handle&&p.avatar_url)||{}).avatar_url,true)}]));
    const initials=a=>esc((a.name||a.handle).split(/\s+/).map(w=>w[0]).slice(0,2).join('').toUpperCase());
    const avatarHTML=(a,size)=>`<span class="fd-av" style="--ac:${a.tone}" aria-hidden="true"><span>${initials(a)}</span>${a.avatar?`<img src="${esc(a.avatar)}" alt="" width="${size}" height="${size}" loading="lazy" decoding="async">`:''}</span>`;
    const compact=t=>t.replace(/\n\s*\n+/g,'\n').trim();
    const narratives=[...new Set(data.posts.flatMap(p=>p.quality?.narratives||[]))].sort();
    const sel=(id,label,opts,value)=>`<label><span>${label}</span><select id="${id}">${opts.map(([v,l])=>`<option value="${esc(v)}"${value===v?' selected':''}>${esc(l)}</option>`).join('')}</select></label>`;
    let limit=incoming?.limit||FEED_PAGE;
    const main=document.getElementById('feed-main');
    const ctxBar=filters.cf?`<nav class="fd-ctx" aria-label="Contexto de origen"><p><span>${filters.ct?'Desde la tesis':'Desde la ficha'}</span><b>${esc(filters.cn||filters.cf)}</b></p><p class="fd-ctx-note">${filters.asset?`Publicaciones que mencionan ${esc(filters.asset)}: contexto por activo. No suman apoyo a la tesis.`:'Contexto de origen.'}</p><div class="fd-ctx-acts"><a class="pill" href="${CR.hash(['f',filters.cf],filters.ct?{tesis:filters.ct}:{})}">${icon('arrow-left','i-s')} Volver</a><a class="pill" href="#/feed">Ver el Feed completo</a></div></nav>`:'';
    main.innerHTML=`${ctxBar}<header class="fd-head"><div><p class="radar-eyebrow">EL PULSO DE X</p><h1>En sus propias palabras</h1></div><button class="fd-filter-btn" id="feed-filters" type="button" aria-expanded="false" aria-controls="feed-sheet">${icon('filter','i-s')}<span>Filtros</span><b id="feed-filter-count" hidden></b></button></header>
      <p class="feed-status" id="feed-health" role="status"></p>
      <label class="fd-search">${icon('search','i-s')}<span class="sr">Buscar en los posts</span><input id="feed-q" type="search" autocomplete="off" placeholder="Buscar posts, activos o noticias…" value="${esc(filters.q)}"></label>
      <div class="fd-rail" id="feed-rail" role="group" aria-label="Cuentas"></div>
      <div class="fd-sheet" id="feed-sheet" hidden><div class="fd-selects">${sel('feed-period','Período',[['cuenta','Por cuenta'],['48h','Últimas 48 h']],filters.period)}${sel('feed-quality','Contenido',[['relevante','Relevantes'],['todos','Todos'],['secundario','Conversaciones y otros']],filters.quality)}${sel('feed-length','Extensión',[['todos','Todas'],['micro','Micro'],['breve','Breve'],['medio','Medio'],['largo','Largo']],filters.length)}${sel('feed-narrative','Narrativa',[['todas','Todas'],...narratives.map(v=>[v,v.replaceAll('_',' ')])],filters.narrative)}</div><div class="feed-status" id="feed-status"></div></div>
      <section class="fr-radar" id="feed-radar" aria-label="Activos más mencionados"><div class="fr-rings" aria-hidden="true"></div><p class="fr-legend" id="feed-radar-legend"></p></section>
      <div class="fr-bento" id="feed-posts"></div>
      <div class="feed-bottom"><button class="pill" id="feed-more" type="button">Ver más publicaciones</button><p class="fd-note">Texto tal como lo publicó cada cuenta, sin verificación externa. Las etiquetas salen de reglas locales.</p><button class="textbtn" id="feed-refresh" type="button">${icon('refresh','i-s')} Actualizar Feed</button></div>`;
    if(!data.accounts.some(a=>a.handle===filters.account))filters.account='todos';

    const postTile=(p,size,i)=>{
      const a=accounts.get(p.author_handle), news=/noticia/i.test(a.label||''), linked=connectionsOf(p).length;
      return `<article class="fr-b fr-${size}${news?' is-news':''}" role="button" tabindex="0" data-post="${esc(p.id)}" style="--ac:${a.tone};--d:${(i%12)*40}ms" aria-label="${esc((a.name||a.handle)+': '+compact(p.text).slice(0,90))}">
        <span class="fr-bh">${avatarHTML(a,24)}<b>${esc(a.name||a.handle)}</b>${news?'<em>Noticia</em>':''}<time datetime="${esc(p.published_at)}">${esc(CR.rel(p.published_at))}</time></span>
        <span class="fr-bx">${window.UraniaFeed.textHTML(compact(p.text),esc)}</span>
        ${(p.quality?.assets||[]).length||linked?`<span class="fr-bf">${(p.quality?.assets||[]).slice(0,3).map(s=>`<span>$${esc(s)}</span>`).join('')}${linked?`<span class="is-link">${icon('link','i-s')} video</span>`:''}</span>`:''}</article>`;
    };
    /* Piezas de datos intercaladas: cuenta más activa y ritmo de las últimas 24 h. */
    const dataTiles=list=>{
      const out=[],by=new Map();
      for(const p of list)by.set(p.author_handle,(by.get(p.author_handle)||0)+1);
      const lead=[...by].sort((x,y)=>y[1]-x[1])[0];
      if(lead&&list.length>=4){const a=accounts.get(lead[0]);
        out.push(`<div class="fr-b fr-S fr-data" style="--ac:${a.tone}"><span class="fr-k">Más activo · ventana</span><span class="fr-v">${lead[1]}<small> posts</small></span><span class="fr-bh">${avatarHTML(a,24)}<b>${esc(a.name||a.handle)}</b></span></div>`);}
      const slots=Array(12).fill(0);
      for(const p of list){const h=Math.floor((Date.now()-Date.parse(p.published_at))/7200000);if(h<12)slots[11-h]++;}
      const total=slots.reduce((x,y)=>x+y,0),mx=Math.max(1,...slots);
      if(total)out.push(`<div class="fr-b fr-S fr-data"><span class="fr-k">Ritmo · 24 h</span><span class="fr-v">${total}<small> posts</small></span><span class="fr-spark" aria-hidden="true">${slots.map(n=>`<i style="height:${Math.max(8,Math.round(n/mx*100))}%"></i>`).join('')}</span></div>`);
      return out;
    };
    const radarHTML=list=>{
      const counts=new Map();
      for(const p of list)for(const s of p.quality?.assets||[])counts.set(s,(counts.get(s)||0)+1);
      const top=[...counts].sort((x,y)=>y[1]-x[1]).slice(0,RADAR_SPOTS.length);
      if(filters.asset&&!top.some(([s])=>s===filters.asset))top.splice(top.length?top.length-1:0,top.length?1:0,[filters.asset,counts.get(filters.asset)||0]);
      const max=Math.max(1,...top.map(([,n])=>n));
      document.getElementById('feed-radar-legend').textContent=top.length?(filters.asset?`Filtrando por $${filters.asset} · toca de nuevo para quitarlo`:'Tamaño = menciones · toca para filtrar'):'Sin activos mencionados con estos filtros';
      return top.map(([s,n],i)=>`<button type="button" class="fr-bub" data-asset="${esc(s)}" aria-pressed="${filters.asset===s}" aria-label="$${esc(s)}: ${n} menciones" style="--s:${44+Math.round(68*Math.sqrt(n/max))}px;--x:${RADAR_SPOTS[i][0]}%;--y:${RADAR_SPOTS[i][1]}%;--heat:${Math.round(14+46*n/max)}%;--dl:${-i*0.9}s">$${esc(s)}<small>${n}</small></button>`).join('');
    };
    let lastVisible='';
    const paint=()=>{
      if(screen!=='feed'||token!==feedRequest)return;
      const all=window.UraniaFeed.select(data,{account:'todos',period:'cuenta',q:''}),base=window.UraniaFeed.select(data,filters);
      const posts=filters.asset?base.filter(p=>p.quality?.assets?.includes(filters.asset)):base;
      const railBase=window.UraniaFeed.select(data,{...filters,account:'todos'}).filter(p=>!filters.asset||p.quality?.assets?.includes(filters.asset));
      lastVisible=posts.map(p=>p.id).join(',');
      const latest=data.accounts.map(a=>a.last_success).filter(Boolean).sort().reverse()[0];
      const stale=data.health?.accounts?data.health.accounts.some(a=>!a.fresh):data.accounts.some(a=>!a.last_success||Date.now()-Date.parse(a.last_success)>26*3600000);
      const providerError=data.last_error||data.accounts.find(a=>a.last_error)?.last_error;
      document.getElementById('feed-health').textContent=providerError?.code==='plan_expired'
        ? 'La actualización está pausada. Se muestran las publicaciones vigentes de la última consulta.'
        : providerError?.kind==='quota'
        ? 'La extracción de X está limitada por la cuota del proveedor. Se conservan solo los posts vigentes.'
        : providerError ? 'Hay una fuente pendiente de actualización. Los posts vencidos se retiran automáticamente.'
        : stale ? 'Hay cuentas pendientes de actualización. Consulta el estado de las fuentes.'
        : latest ? `Última extracción: ${fmtDate(latest,{time:true})} · actualización automática` : 'Esperando la primera extracción.';
      document.getElementById('feed-rail').innerHTML=[['todos',null,railBase.length],...data.accounts.map(a=>[a.handle,accounts.get(a.handle),railBase.filter(p=>p.author_handle===a.handle).length])]
        .map(([h,a,n])=>`<button type="button" class="fd-chip" data-account="${esc(h)}" aria-pressed="${filters.account===h}"${a?` style="--ac:${a.tone}"`:''}>${a?avatarHTML(a,22):''}<span>${a?esc(a.name||a.handle):'Todas'}</span><small>${n}</small></button>`).join('');
      const custom=['period','quality','length','narrative'].filter(k=>filters[k]!==feedFilters({})[k]).length;
      const badge=document.getElementById('feed-filter-count');badge.hidden=!custom;badge.textContent=custom;
      document.getElementById('feed-status').innerHTML=`<span>${posts.length} publicaciones con estos filtros · ${all.length} disponibles · ${all.filter(p=>p.quality?.visibility==='secundario').length} en segundo plano</span><small>${latest?`Última consulta: ${fmtDate(latest,{time:true})}`:'Aún no hay consultas completadas.'}</small><small>${(semantic.connections||[]).some(c=>Date.parse(c.expires_at)>Date.now())?'Conexiones con videos: resultados revisados disponibles.':semantic.status==='drive_error'?'Conexiones con videos: sincronización pendiente.':'Conexiones con videos: pendientes de revisión.'}</small><details class="feed-coverage"><summary>${stale?'Fuentes pendientes de actualización':data.status==='partial'?'Cobertura parcial':'Estado de las fuentes'} ${icon('chevron-down','i-s')}</summary><p>Ventanas móviles por cuenta; el proveedor no garantiza cobertura completa. La fecha corresponde a una consulta correcta, no a la limpieza del Feed.</p>${data.accounts.map(a=>`<p><b>@${esc(a.handle)}</b> · ${a.lookback_days} días · ${a.last_success?fmtDate(a.last_success,{time:true}):'Sin consulta completada'}${a.last_error?' · Consulta pendiente por error':a.status==='partial'?' · Paginación pendiente':''}</p>`).join('')}</details>`;
      const radar=document.getElementById('feed-radar');
      radar.querySelectorAll('.fr-bub').forEach(b=>b.remove());
      radar.insertAdjacentHTML('beforeend',radarHTML(base));
      const tiles=[],extra=filters.q?[]:dataTiles(posts);
      posts.slice(0,limit).forEach((p,i)=>{tiles.push(postTile(p,feedSize(p),i));if(i===2&&extra[0])tiles.push(extra[0]);if(i===6&&extra[1])tiles.push(extra[1]);});
      document.getElementById('feed-posts').innerHTML=posts.length?tiles.join(''):'<div class="empty fr-empty"><h2>Sin publicaciones con estos filtros</h2><p>Prueba otra cuenta, quita el activo o cambia la búsqueda.</p></div>';
      const more=document.getElementById('feed-more');more.hidden=posts.length<=limit;more.textContent=`Ver más (${Math.max(0,posts.length-limit)} restantes)`;
    };
    const update=()=>{
      if(screen!=='feed'||token!==feedRequest)return;
      feedRouteKey=JSON.stringify(filters);CR.go(['feed'],filters,{replace:true});limit=FEED_PAGE;paint();
    };
    /* La publicación completa se abre en la hoja inferior de Urania (la misma de las fichas). */
    let openedPostId=null;
    const openPost=p=>{
      openedPostId=p.id;
      const a=accounts.get(p.author_handle), links=connectionsOf(p), q=p.quality||{};
      const kind=p.is_reply===true?'Respuesta':p.is_quote===true?'Cita':p.is_repost===true?'Repost':'';
      fichaReturnFocus=document.activeElement; feedPostOpen=true;
      document.getElementById('ficha-title').textContent='Publicación';
      const body=document.getElementById('ficha-body');
      body.innerHTML=`<div class="fr-post-h">${avatarHTML(a,44)}<div><b>${esc(a.name||a.handle)}</b><a href="https://x.com/${esc(p.author_handle)}" target="_blank" rel="noopener noreferrer">@${esc(p.author_handle)}</a></div><time datetime="${esc(p.published_at)}">${esc(fmtDate(p.published_at,{time:true}))}</time></div>
        ${kind||/noticia/i.test(a.label||'')?`<p class="fr-post-kind">${esc([a.label,kind].filter(Boolean).join(' · '))}</p>`:''}
        <div class="fr-post-x">${window.UraniaFeed.textHTML(p.text,esc)}</div>
        ${(q.assets||[]).length?`<div class="fr-post-tags">${q.assets.map(s=>`<button type="button" class="fd-asset" data-feed-asset="${esc(s)}">$${esc(s)}</button>`).join('')}</div>`:''}
        ${(q.narratives||[]).length?`<p class="fd-narr">${q.narratives.map(n=>`<span>${esc(n.replaceAll('_',' '))}</span>`).join('')}</p>`:''}
        ${links.length?`<section class="post-semantic"><h3>Conexiones con narrativas</h3>${links.map(c=>`<div><a href="#/v/${encodeURIComponent(c.video_id)}?n=${encodeURIComponent(c.claim_id)}">${esc(c.relation.replaceAll('_',' '))} · ${esc(c.video_title||c.video_id)}</a><p>${esc(c.explanation)}</p><blockquote>«${esc(c.post_quote)}»</blockquote><small>${esc(c.limitations)}</small></div>`).join('')}</section>`:''}
        ${p.has_media?'<p class="small muted">Incluye multimedia: puedes verla en X.</p>':''}
        <a class="pill fr-post-open" href="https://x.com/i/web/status/${encodeURIComponent(p.id)}" target="_blank" rel="noopener noreferrer">Abrir en X ${icon('arrow-up-right','i-s')}</a>
        <p class="fd-note">Texto tal como lo publicó la cuenta, sin verificación externa.</p>`;
      body.querySelectorAll('[data-feed-asset]').forEach(b=>b.addEventListener('click',()=>{filters.asset=b.dataset.feedAsset;closeFicha();update();window.scrollTo({top:0,behavior:'smooth'});}));
      ficha.hidden=false; scrim.hidden=false;
      document.querySelectorAll('#page, .dock, #nh, #stage').forEach(el=>{el.inert=true;});
      document.body.style.overflow='hidden';
      body.scrollTop=0;
      ficha.querySelector('[data-act="ficha-close"]').focus({preventScroll:true});
    };
    const qInput=document.getElementById('feed-q');
    qInput.addEventListener('input',CR.debounce(e=>{filters.q=e.target.value.slice(0,200);update();},180));
    for(const key of ['period','quality','length','narrative'])document.getElementById('feed-'+key).addEventListener('change',e=>{filters[key]=e.target.value;update();});
    const sheetBtn=document.getElementById('feed-filters'),sheet=document.getElementById('feed-sheet');
    if(incoming?.sheetOpen){sheet.hidden=false;sheetBtn.setAttribute('aria-expanded','true');}
    sheetBtn.addEventListener('click',()=>{sheet.hidden=!sheet.hidden;sheetBtn.setAttribute('aria-expanded',String(!sheet.hidden));});
    document.getElementById('feed-rail').addEventListener('click',e=>{const b=e.target.closest('[data-account]');if(!b)return;filters.account=filters.account===b.dataset.account?'todos':b.dataset.account;update();});
    document.getElementById('feed-radar').addEventListener('click',e=>{const b=e.target.closest('[data-asset]');if(!b)return;filters.asset=filters.asset===b.dataset.asset?'':b.dataset.asset;update();});
    const bento=document.getElementById('feed-posts');
    bento.addEventListener('click',e=>{if(e.target.closest('a'))return;const t=e.target.closest('[data-post]');if(t)openPost(data.posts.find(p=>p.id===t.dataset.post));});
    bento.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.dataset?.post){e.preventDefault();openPost(data.posts.find(p=>p.id===e.target.dataset.post));}});
    const moreBtn=document.getElementById('feed-more');
    moreBtn.addEventListener('click',()=>{const y=window.scrollY;limit+=FEED_PAGE;paint();window.scrollTo(0,y);});
    if('IntersectionObserver' in window){
      const io=new IntersectionObserver(entries=>{
        if(screen!=='feed'||token!==feedRequest){io.disconnect();return;}
        if(entries.some(en=>en.isIntersecting)&&!moreBtn.hidden){const y=window.scrollY;limit+=FEED_PAGE;paint();window.scrollTo(0,y);}
      },{rootMargin:'600px 0px'});
      io.observe(moreBtn);
    }
    document.getElementById('feed-refresh').addEventListener('click',()=>renderFeed(filters));
    let checkingFeed=false,lastRemoteCheck=Date.now();
    const signature=(d,s)=>JSON.stringify([d.posts.map(p=>[p.id,p.content_hash,p.expires_at,p.quality]),
      d.accounts.map(a=>[a.handle,a.lookback_days,a.last_success,a.status,a.last_error]),d.last_error,s.status,s.connections]);
    const loadedSignature=signature(data,semantic);
    feedRefresh=async(force=false)=>{
      if(checkingFeed||screen!=='feed'||token!==feedRequest||document.visibilityState!=='visible'
        ||(!force&&Date.now()-lastRemoteCheck<5*60000)||!ficha.hidden
        ||document.activeElement?.matches('input,select,textarea'))return;
      checkingFeed=true;lastRemoteCheck=Date.now();
      try{
        const r=await fetch('../data/social-feed.json',{cache:'no-store'});if(!r.ok)return;
        const fresh=await r.json();if(fresh.version!==1||!Array.isArray(fresh.posts)||!Array.isArray(fresh.accounts))return;
        let links=semantic;
        try{const sr=await fetch('../data/social-connections.json',{cache:'no-store'});if(sr.ok)links=await sr.json();}catch(_){}
        if(token!==feedRequest||screen!=='feed'||!ficha.hidden||document.activeElement?.matches('input,select,textarea'))return;
        if(signature(fresh,links)!==loadedSignature){
          socialPromise=null;
          const y=window.scrollY;
          await renderFeed(filters,{data:fresh,semantic:links,limit,sheetOpen:!sheet.hidden});
          if(screen==='feed')window.scrollTo(0,y);
        }
      }catch(_){/* Keep the valid cache and retry on the next tick. */}
      finally{checkingFeed=false;}
    };
    const expireTimer=setInterval(()=>{
      if(screen!=='feed'||token!==feedRequest){clearInterval(expireTimer);return;}
      if(feedPostOpen&&openedPostId&&!window.UraniaFeed.select(data,{account:'todos',period:'cuenta',q:''}).some(p=>p.id===openedPostId)){
        closeFicha();openedPostId=null;
      }
      const current=window.UraniaFeed.select(data,filters).filter(p=>!filters.asset||p.quality?.assets?.includes(filters.asset)).map(p=>p.id).join(',');
      if(current!==lastVisible){paint();lastVisible=current;}
      feedRefresh?.();
    },60000);

    paint();
  }


  /* ---------- búsqueda, estados, datos ---------- */
  function radarFilters(q = {}) {
    const ex = exState({});
    const defaults = { c: ex.c, p: ex.p, s: 'todo', own: '0' };
    const value = { ...defaults, ...q };
    return {
      c: value.c === 'todos' || idx.channelsBySlug[value.c] ? value.c : 'todos',
      p: ['todo','1d','2d','3d'].includes(value.p) ? value.p : 'todo',
      s: ['todo','bitcoin','altcoins','macro','bolsa'].includes(value.s) ? value.s : 'todo',
      own: value.own === '1' ? '1' : '0',
    };
  }
  function radarHtml(intent, filters, query, filtersOpen = false) {
    const rows = Radar.rows(idx, intent, filters);
    const scopeTopics = idx.topics.filter((t) => (!intent.asset || t.id === intent.asset) && (filters.s === 'todo' || t.section === filters.s));
    const scopeVideos = new Set(scopeTopics.flatMap((t) => [...t.videos.map((m) => m.v), ...t.claims.map((c) => c.v)]));
    const all = idx.videos.filter((v) => scopeVideos.has(v.id) && Radar.inWindow(v, filters));
    const analyzed = all.filter((v) => v.analysis);
    const up = intent.direction === 'alcista';
    const select = (id, label, values, value) => `<label><span>${label}</span><select id="${id}">${values.map(([key,name]) => `<option value="${esc(key)}"${key === value ? ' selected' : ''}>${esc(name)}</option>`).join('')}</select></label>`;
    return `<section class="radar" aria-labelledby="radar-title" data-direction="${intent.direction}">
      <header class="radar-header"><p class="radar-eyebrow">RADAR DE POSTURAS <span>Archivo analizado</span></p><h1 id="radar-title">${up ? 'Dónde miran<br>hacia arriba.' : 'Dónde ven<br>presión bajista.'}</h1><p>Quién sostiene la tesis, qué la respalda y qué la invalidaría.</p>
        <div class="radar-switch" role="group" aria-label="Dirección de las tesis"><button type="button" data-direction="alcista" aria-pressed="${up}">${icon('trend-up')} Alcistas</button><button type="button" data-direction="bajista" aria-pressed="${!up}">${icon('trend-down')} Bajistas</button></div>
        <p class="radar-scope">${intent.asset ? `${esc(idx.topicsById[intent.asset].name)} · ` : ''}${filters.own === '1' ? 'Posiciones declaradas en la fuente' : 'Tesis y declaraciones · no implica una posición abierta'}</p>
      </header>
      <details class="radar-controls"${filtersOpen ? ' open' : ''}><summary>Filtros<span>${filters.s === 'todo' ? 'Todos los mercados' : esc(L.section[filters.s])} · ${filters.c === 'todos' ? 'Todos los creadores' : esc(idx.channelsBySlug[filters.c].name)} · ${filters.p === 'todo' ? 'Archivo completo' : 'Últimas '+({'1d':24,'2d':48,'3d':72}[filters.p])+' h'}</span>${icon('chevron-down','i-s')}</summary><div class="radar-filters">
        ${select('radar-section','Mercado',[['todo','Todos'],['bitcoin','Bitcoin'],['altcoins','Altcoins'],['macro','Macro'],['bolsa','Bolsa']],filters.s)}
        ${select('radar-creator','Creador',[['todos','Todos'],...idx.channels.map((c) => [c.slug,c.name])],filters.c)}
        ${select('radar-period','Período',[['todo','Archivo completo'],['2d','Últimas 48 h'],['3d','Últimas 72 h'],['1d','Últimas 24 h']],filters.p)}
        ${select('radar-own','Evidencias',[['0','Todas las tesis'],['1','Solo posiciones declaradas']],filters.own)}
      </div></details>
      <div class="radar-coverage"><span>${analyzed.length} / ${all.length} videos con análisis en estos filtros</span><small>Actualización: ${fmtDate(idx.generatedAt, {time:true})} · Fuente más reciente: ${fmtDate(idx.period.to, {time:true})}</small></div>
      ${intent.unresolved ? `<div class="empty"><h2>No identificamos «${esc(intent.term)}»</h2><p>Usa un activo del catálogo, por ejemplo ETH, BTC o Solana.</p></div>` : ''}
      <div class="radar-results-head"><h2>${rows.length} ${rows.length === 1 ? 'activo o tema' : 'activos y temas'}</h2><small>Orden: creadores → videos → fecha</small></div>
      ${!rows.length && !intent.unresolved ? `<div class="empty"><h3>No hay tesis con estos filtros</h3><p>Esto indica falta de evidencia disponible, no ausencia de esa postura en el mercado.</p><button class="pill" type="button" data-radar-reset>Ampliar al archivo completo</button></div>` : ''}
      ${rows.map((r,i) => {
        const c = r.claims[0], v = idx.videosById[c.v];
        const own = r.claims.filter((x) => x.radar.position_side && x.radar.position_status === 'declarada');
        const creators = [...new Set(r.claims.map((x) => idx.videosById[x.v].ch))];
        const href = CR.hash(['f',r.t.id], { from:'radar', q:query, direction:intent.direction, ...filters });
        return `<article class="radar-card" data-asset="${r.t.id}">
          <div class="radar-card-head"><span class="radar-number">${String(i+1).padStart(2,'0')}</span>${symAv(r.t)}<div><h3>${esc(r.t.name)}</h3><small>${esc(r.t.sym || L.section[r.t.section])}</small></div>${chip(intent.direction,{short:true})}</div>
          <div class="radar-metrics"><span><b>${r.creators}</b> ${r.creators === 1 ? 'creador' : 'creadores'}</span><span><b>${r.videos}</b> ${r.videos === 1 ? 'video' : 'videos'}</span><span>${fmtDate(r.last)}</span></div>
          <p class="radar-thesis">${esc(c.text)}</p>
          <div class="radar-people">${creators.slice(0,4).map((slug) => `<span title="${esc(idx.channelsBySlug[slug].name)}">${creatorAv(idx.channelsBySlug[slug])}</span>`).join('')}<small>${esc(creators.slice(0,2).map((slug) => idx.channelsBySlug[slug].name).join(' · '))}${creators.length>2 ? ` +${creators.length-2}` : ''}</small></div>
          ${own.length ? `<p class="position-tag">Incluye declaración ${up ? 'long' : 'short'} · fechada, sin confirmar vigencia</p>` : ''}
          <details class="radar-details"><summary>Desplegar argumentos ${icon('chevron-down','i-s')}</summary>
            ${v.analysis?.narrative ? `<div class="radar-narrative"><h4>Narrativa del video fuente</h4><p>${esc(v.analysis.narrative)}</p></div>` : ''}
            ${v.analysis?.insight ? `<div class="radar-insight"><h4>Insight del análisis</h4><p>${esc(v.analysis.insight)}</p></div>` : ''}
            <p class="small muted">Las citas siguientes sostienen la tesis seleccionada. La ficha incluye también argumentos contrarios y neutrales.</p>
            ${r.claims.slice(0,3).map((claim) => evidenceHtml({...claim, text:claim.quote, summary:claim.text, pol:claim.radar.direction, kind:'analysis'})).join('')}
            ${r.claims.length>3 ? `<p class="small muted">Mostrando 3 de ${r.claims.length} afirmaciones compatibles.</p>` : ''}
          </details>
          <a class="radar-open" href="${href}">Ver citas y contraste ${icon('arrow-up-right','i-s')}</a>
        </article>`;
      }).join('')}
      <p class="radar-method">Clasificación local de las fuentes guardadas. Presencia de una tesis entre creadores no equivale a probabilidad de acierto. <button type="button" class="textbtn" data-radar-text>Buscar estas palabras literalmente</button></p>
    </section>`;
  }
  function renderSearch(q) {
    let filters = radarFilters(CR.parseHash().q), literal = CR.parseHash().q.literal === '1', filtersOpen = false;
    page.innerHTML = `<form class="search-box" id="search-form" role="search"><a class="ib" href="#/" aria-label="Volver a explorar">${icon('arrow-left')}</a><label class="field">${icon('search')}<span class="sr">Buscar posturas, activos o videos</span><input id="q" type="search" placeholder="Prueba short ETH o long…" value="${esc(q)}" autocomplete="off" enterkeyhint="search"></label><button class="ib" type="submit" aria-label="Buscar">${icon('arrow-right')}</button></form><div id="res"></div>`;
    const input = document.getElementById('q');
    const run = () => {
      const val = input.value.trim();
      searchRouteKey = JSON.stringify({q:val,...filters,literal:literal?'1':'0'});
      CR.go(['buscar'], { q:val, ...filters, literal:literal?'1':'0' }, { replace:true });
      const out = document.getElementById('res');
      if (!val) {
        out.innerHTML = `<div class="radar-intro"><p class="radar-eyebrow">DE LA NARRATIVA A LA EVIDENCIA</p><h1>Una palabra.<br>Distintas posturas.</h1><p>Explora tesis, identifica a sus autores y contrasta las citas.</p><div class="radar-examples">${['short','long','short ETH'].map((x) => `<button class="pill" type="button" data-query="${x}">${esc(x)} ${icon('arrow-up-right','i-s')}</button>`).join('')}</div><p class="small muted">También puedes buscar videos, activos y notas del análisis.</p></div>`;
        out.querySelectorAll('[data-query]').forEach((button) => button.addEventListener('click', () => { input.value=button.dataset.query; literal=false; run(); input.blur(); }));
        return;
      }
      const intent = Radar.parse(val,idx.topics);
      if (intent && !literal) {
        out.innerHTML = radarHtml(intent,filters,val,filtersOpen);
        out.querySelector('.radar-controls').addEventListener('toggle',(event) => { filtersOpen=event.target.open; });
        out.querySelectorAll('[data-direction]').forEach((button) => {
          if (button.tagName !== 'BUTTON') return;
          button.addEventListener('click', () => { input.value=`${button.dataset.direction === 'alcista' ? 'long' : 'short'}${intent.term ? ' '+intent.term : ''}`; run(); document.querySelector(`button[data-direction="${button.dataset.direction}"]`)?.focus({preventScroll:true}); });
        });
        for (const [id,key] of [['radar-section','s'],['radar-creator','c'],['radar-period','p'],['radar-own','own']]) {
          document.getElementById(id).addEventListener('change',(event) => { filters[key]=event.target.value; filtersOpen=true; run(); document.getElementById(id).focus({preventScroll:true}); });
        }
        out.querySelector('[data-radar-reset]')?.addEventListener('click',() => { filters={c:'todos',p:'todo',s:'todo',own:'0'}; run(); });
        out.querySelector('[data-radar-text]').addEventListener('click',() => { literal=true; run(); });
        return;
      }
      const r = CR.search(val);
      const grp = (t, items) => (items.length ? `<h2 class="res-h">${t}</h2>${items.join('')}` : '');
      out.innerHTML = (intent ? `<div class="pad"><button class="pill" type="button" id="use-radar">Abrir Radar de posturas</button></div>` : '')
        + (!r.videos.length && !r.claims.length && !r.topics.length && !r.themes.length ? '<p class="pad muted">Sin coincidencias en el índice. Puedes buscar en las transcripciones.</p>' : '')
        + grp('Vídeos', r.videos.slice(0, 8).map((v) => `<a class="res" href="#/v/${v.id}"><p style="font-family:var(--serif)">${esc(v.cleanTitle)}</p><small class="source-person">${creatorAv(v.channel)} ${esc(v.channel.name)} · ${fmtDate(v.pub)}</small></a>`))
        + grp('Notas del análisis', r.claims.slice(0, 10).map((c) => { const v = idx.videosById[c.v]; return `<a class="res" href="#/v/${v.id}?t=${Math.floor(c.t || 0)}&n=${c.id}"><p style="color:var(--pen)">${esc(c.text)}</p><small>${chip(c.pol, { short: true })} ${L.tipo[c.tipo]} · ${esc(v.channel.name)} · ${fmtT(c.t)}</small></a>`; }))
        + grp('Activos', r.topics.slice(0, 8).map((t) => `<a class="res asset-heading" href="#/f/${t.id}">${symAv(t)}<div><p>${esc(t.name)}</p><small>${L.section[t.section]} · ${CR.plural(t.vc, 'vídeo', 'vídeos')}</small></div></a>`))
        + grp('Temas', r.themes.map((t) => `<a class="res" href="#/n/${t.id}"><p>${esc(t.title)}</p><small>Tema del archivo, no una tesis</small></a>`))
        + `<div class="pad" style="margin-top:18px"><button class="pill" type="button" data-act="search-tx" style="width:100%">${icon('text')} Buscar también en las transcripciones</button></div><div id="txres"></div>`;
      document.getElementById('use-radar')?.addEventListener('click',() => { literal=false; run(); });
    };
    input.addEventListener('input',CR.debounce(() => { literal=false; run(); },200));
    document.getElementById('search-form').addEventListener('submit',(event) => { event.preventDefault(); run(); input.blur(); });
    run();
  }

  async function searchTx() {
    const val = (document.getElementById('q') || {}).value || '';
    const out = document.getElementById('txres');
    out.innerHTML = '<div class="pad"><div class="skel" style="height:64px;margin-top:12px"></div></div>';
    const hits = await CR.searchTranscripts(val);
    out.innerHTML = hits.length ? `<h2 class="res-h">En las transcripciones</h2>${hits.map((h) => { const v = idx.videosById[h.v]; return `<a class="res" href="#/v/${v.id}?t=${Math.floor(h.t)}&lens=transcripcion"><blockquote>«${esc(h.text)}»</blockquote><small>${esc(v.channel.name)} · ${fmtT(h.t)} · ${esc(CR.clip(v.cleanTitle, 44))}</small></a>`; }).join('')}` : `<p class="pad small muted" style="margin-top:12px">Ninguna transcripción contiene «${esc(val)}».</p>`;
  }
  function renderStates() {
    page.innerHTML = `<div class="pad"><a class="textbtn" href="#/">${icon('arrow-left')} Bitácora</a><h1 class="title-xl" style="margin-top:4px">Estados</h1><p class="lede">Cómo aparece cada vídeo según lo que el sistema haya podido hacer. «Ejemplo» indica que ahora mismo no hay ninguno así.</p></div>
      ${CR.STATES.map((s, i) => `<article class="state-row"><h3>${esc(s.title)}<span class="tag-s">${s.real ? 'Real' : 'Ejemplo'}</span></h3><p>${esc(s.body)}</p>
        <div class="entry-who"><span class="dots" aria-hidden="true">${[0, 1, 2, 3].map((k) => `<i class="${k < [0, 1, 4, 0, 4, 2][i] ? 'on' : ''}"></i>`).join('')}</span><span>${esc(s.chip)}</span></div>
        <button class="pill" type="button" data-act="demo" style="margin-top:10px">${esc(s.action)}</button></article>`).join('')}`;
  }
  function renderAbout() {
    const a = idx.analyzed;
    page.innerHTML = `<div class="pad"><a class="textbtn" href="#/">${icon('arrow-left')} Bitácora</a><h1 class="title-xl" style="margin-top:4px">Sobre estos datos</h1>
      <p class="lede">${idx.videos.length} vídeos publicados entre el ${fmtDate(idx.period.from)} y el ${fmtDate(idx.period.to)}. Todos tienen transcripción; ${a.length} tienen análisis (${a.map((v) => fmtDate(v.pub)).join(' y ')}).</p>
      <p class="lede">${esc(idx.method.external)}</p><p class="lede">${esc(idx.method.mentions)}</p><p class="lede">${esc(idx.method.contrasts)}</p>
      <p class="small muted" style="margin-top:16px">Foto de los datos: ${fmtDate(idx.generatedAt, { time: true })}.</p></div>`;
  }

  /* ---------- acciones ---------- */
  async function share(url, title, text) {
    const r = await CR.share({ title, text, url });
    if (r === 'copied') CR.toast('Enlace copiado');
    if (r === 'failed') CR.toast('No se pudo copiar el enlace');
  }
  document.addEventListener('click', (e) => {
    if(!e.target.closest('.ex-tools'))document.querySelectorAll('.ex-tools details[open]').forEach(d=>{d.open=false;});
    const el = e.target.closest('[data-act]');
    if (!el) {
      const menu = document.getElementById('filter-menu');
      if (menu && !menu.hidden && !e.target.closest('#filter-menu')) menu.hidden = true;
      return;
    }
    const act = el.dataset.act;
    switch (act) {
      case 'index': if (idx) openIndex(); break;
      case 'pip-close': if (player) player.pause(); pipClosed = true; videoPinned = false; setStage(); break;
      case 'video-toggle': if (videoOpen) { cur.start = player.video?.id === cur.id ? player.time() : cur.start; player.pause(); videoOpen = false; videoPinned = false; signalMode = false; setSnap('full'); } else openPlayback(player.video?.id === cur.id ? player.time() : cur.start, false); break;
      case 'signal-mode': {
        if (signalMode) {
          cur.start = player?.video?.id === cur.id ? player.time() : cur.start;
          player?.pause(); signalMode = false; videoOpen = false; videoPinned = false; setSnap('full');
        } else {
          signalMode = true; pulseStrip();
          openPlayback(player?.video?.id === cur.id ? player.time() : cur.start, false);
        }
        break;
      }
      case 'video-pin': videoPinned = !videoPinned; pipClosed = false; setStage(); break;
      case 'synthesis-tab': if (['conclusion','escenarios','vigilar','contraste'].includes(el.dataset.tab)) { cur.synthesisTab = el.dataset.tab; renderNotebook(); nbBody.scrollTop = 0; } break;
      case 'index-close': closeIndex(); break;
      case 'filter-menu': { const m = document.getElementById('filter-menu'); m.hidden = !m.hidden; el.setAttribute('aria-expanded', String(!m.hidden)); if (!m.hidden) m.querySelector('[aria-checked="true"]').focus(); break; }
      case 'filter': ui.filter = el.dataset.f; store.set('filter', ui.filter); renderLog(); break;
      case 'back': CR.back('#/diario'); break;
      case 'snap': if (screen && screen.startsWith('v:')) setSnap(el.dataset.snap); else if (cur.id) CR.go(['v', cur.id]); break;
      case 'cycle': setSnap(nb.dataset.snap === 'half' ? 'full' : 'half'); break;
      case 'pulse': {
        const svg = el.querySelector('svg');
        if (!svg || !player || !cur.video) break;
        const r = svg.getBoundingClientRect();
        const ratio = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
        openPlayback(e.detail === 0 ? player.time() : ratio * (cur.video.dur || 0), true);
        break;
      }
      case 'toggle': case 'pip-toggle': if (player && player.video && player.video.id === cur.id) player.toggle(); else openPlayback(); break;
      case 'lens': cur.lens = lensOf(el.dataset.lens) || 'sintesis'; renderNotebook(); nbBody.scrollTop = 0; if (nb.dataset.snap === 'peek') setSnap('half'); break;
      case 'txmode': ui.txmode = el.dataset.m === 'completo' ? 'completo' : 'notas'; renderNotebook(); nbBody.scrollTop = 0; break;
      case 'goto-scn': { cur.synthesisTab = 'escenarios'; renderNotebook(); const target = document.getElementById(`scn-${el.dataset.s}`); if (target) { const box = target.closest('details'); if (box) box.open = true; target.scrollIntoView({ block: 'start', behavior: CR.reduced() ? 'auto' : 'smooth' }); target.focus({ preventScroll: true }); } break; }
      case 'seek': if (screen && screen.startsWith('v:')) openPlayback(Number(el.dataset.t), true); break;
      case 'expand': { const id = el.dataset.c; if (cur.open.has(id)) cur.open.delete(id); else cur.open.add(id); const top = nbBody.scrollTop; renderNotebook(); nbBody.scrollTop = top; break; }
      case 'goto-note': gotoNote(el.dataset.c); break;
      case 'open-gap': { for (let i = Number(el.dataset.from); i <= Number(el.dataset.to); i++) cur.gaps.add(i); const top = nbBody.scrollTop; renderNotebook(); nbBody.scrollTop = top; break; }
      case 'card': cur.card = Math.max(0, Math.min(CARDS.length - 1, cur.card + Number(el.dataset.d))); renderNotebook(); nbBody.scrollTop = 0; break;
      case 'follow': ui.follow = true; el.hidden = true; syncDoc(player.time(), true); { const row = nbBody.querySelector('.doc-row.is-now'); if (row) row.scrollIntoView({ block: 'center' }); } break;
      case 'asset': CR.go(['f', el.dataset.id]); break;
      case 'ficha-close': closeFicha(); break;
      case 'drawer': openDrawer(); break;
      case 'ticker': {
        const paused = el.getAttribute('aria-pressed') !== 'true';
        el.setAttribute('aria-pressed', String(paused));
        el.innerHTML = `${icon(paused ? 'play' : 'pause', 'i-s')}<span>${paused ? 'Seguir' : 'Pausar'}</span>`;
        drawer.querySelector('.ticker').classList.toggle('is-paused', paused);
        break;
      }
      case 'drawer-close': closeDrawer(); break;
      case 'share-note': { const c = CR.claim(cur.doc, el.dataset.c); share(CR.linkTo(CR.hash(['v', cur.id], { t: Math.floor(c.t || 0), n: c.id })), cur.video.cleanTitle, `${L.tipo[c.tipo]} en ${fmtT(c.t)}: ${c.text}`); break; }
      case 'share-video': share(CR.linkTo(CR.hash(['v', cur.id], { t: Math.floor(player.video && player.video.id === cur.id ? player.time() : cur.start || 0) })), cur.video.cleanTitle, cur.video.cleanTitle); break;
      case 'search-tx': searchTx(); break;
      case 'demo': CR.toast('Ejemplo de estado: en el producto llevaría a esta acción.'); break;
      case 'reload': location.reload(); break;
      case 'retry-video': screen = null; route(CR.parseHash()); break;
      default: break;
    }
  });
  scrim.addEventListener('click', () => closeFicha());
  dscrim.addEventListener('click', closeDrawer);
  drawer.addEventListener('click', (e) => { if (e.target.closest('a[href]')) closeDrawer(); });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Tab' && !ficha.hidden) {
      const controls = [...ficha.querySelectorAll('a[href],button:not([disabled]),[tabindex="0"]')].filter((el) => el.getClientRects().length);
      const first = controls[0], last = controls[controls.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
    if (e.key === 'Escape' && !drawer.hidden) { closeDrawer(); return; }
    if (e.key === 'Escape' && !ficha.hidden) { closeFicha(); return; }
    if (e.key !== 'Escape') return;
    const exploreMenu=document.querySelector('.ex-tools details[open]');
    if(exploreMenu){e.preventDefault();exploreMenu.open=false;exploreMenu.querySelector('summary').focus();return;}
    if (!indexEl.hidden) closeIndex();
    const m = document.getElementById('filter-menu');
    if (m && !m.hidden) m.hidden = true;
  });

  /* ---------- datos frescos ----------
     Una pestaña abierta durante horas (habitual en el móvil) se quedaba con el índice con el que se abrió.
     Al volver a la pestaña y cada 5 minutos se revalida el índice; si se publicó otro, se refresca. */
  let lastDataCheck = Date.now(), checkingData = false;
  async function refreshData(force) {
    if (checkingData || !idx || (!force && Date.now() - lastDataCheck < 60000)) return;
    checkingData = true; lastDataCheck = Date.now();
    try {
      const fresh = await CR.checkForUpdate();
      if (!fresh) return;
      idx = fresh;
      thesisCache.clear();
      socialPromise = null;
      const here = CR.parseHash().parts[0] || '';
      const calm = ['', 'diario', 'buscar', 'estados', 'datos'].includes(here) && ficha.hidden && drawer.hidden && !document.activeElement?.matches('input, select, textarea');
      const apply = async () => { const y = window.scrollY; screen = null; await route(CR.parseHash()); window.scrollTo(0, y); };
      if (calm) { await apply(); CR.toast('Datos actualizados: hay contenido nuevo'); }
      else CR.toast('Hay datos nuevos publicados', { action: 'Actualizar', ms: 12000, onAction: () => { closeFicha(true); apply(); } });
    } catch (_) { /* sin red: se reintenta en la siguiente comprobación */ } finally { checkingData = false; }
  }
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') { refreshData(); if(screen==='feed')feedRefresh?.(true); } });
  window.addEventListener('pageshow', (e) => { if (e.persisted) { refreshData(true); if(screen==='feed')feedRefresh?.(true); } });
  setInterval(() => { if (document.visibilityState === 'visible') refreshData(); }, 5 * 60000);

  const run = CR.onRoute(route);
  run();
})();

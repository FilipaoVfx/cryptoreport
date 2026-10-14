/* 1A · Libreta — vídeo con cuaderno de análisis (pestañas inferiores, reproductor fijo, hojas inferiores). */
(() => {
  'use strict';
  const { esc, fmtT, fmtDate, icon, L } = CR;
  const APP = '1a';
  const store = CR.store(APP);
  const saved = CR.saved(APP);
  const view = document.getElementById('view');
  const dock = document.getElementById('dock');
  const sheet = document.getElementById('sheet');
  const scrim = document.getElementById('scrim');

  let idx = null;
  let player = null;
  let screen = null;
  let dockClosed = false;
  const cur = { id: null, video: null, doc: null, tab: 'destilado', blocks: [], nowBlock: -1, nowClaim: null };
  const scrolls = new Map();
  const ui = {
    filter: store.get('filter', 'todos'),
    section: store.get('section', 'altcoins'),
    sort: store.get('sort', 'videos'),
    showAll: false,
    kind: 'todos',
    follow: true,
    txQuery: '',
  };

  /* ---------- utilidades de pintado ---------- */
  const kindStyle = (tipo) => `style="--kc: var(--t-${tipo})"`;
  const assetChip = (id) => {
    const t = idx.topicsById[id];
    if (!t) return '';
    return `<button class="asset-chip" type="button" data-act="asset" data-id="${esc(id)}">${esc(t.name)}${t.sym && t.sym !== t.name ? `<span class="sym">${esc(t.sym)}</span>` : ''}</button>`;
  };
  const thumb = (v, cls = 'vthumb') => `<div class="${cls}"><img src="${CR.thumb(v.id)}" alt="" loading="lazy" decoding="async">${v.dur ? `<span class="vdur">${fmtT(v.dur)}</span>` : ''}</div>`;
  const topNames = (v, n = 2) => Object.keys(v.topics).filter((t) => idx.topicsById[t]).slice(0, n).map((t) => idx.topicsById[t].name);
  const lowerFirst = (s) => (s ? s.charAt(0).toLowerCase() + s.slice(1) : s);
  const joinEs = (arr) => (arr.length <= 1 ? arr.join('') : `${arr.slice(0, -1).join(', ')} y ${arr[arr.length - 1]}`);
  const hintFor = (v) => {
    if (v.analysis) {
      const a = v.analysis;
      return `<span class="state state-ok"><span class="state-dot"></span>Análisis listo</span><span>${CR.plural(a.claims, 'afirmación', 'afirmaciones')} · ${CR.plural(a.assets.length, 'activo', 'activos')}</span>`;
    }
    const names = topNames(v);
    return `<span class="state state-wait">Análisis pendiente</span><span>${names.length ? `Menciona ${esc(joinEs(names))}` : 'Transcripción lista'}</span>`;
  };
  const videoRow = (v) => `
    <a class="vrow" href="#/v/${v.id}">
      ${thumb(v)}
      <div>
        <p class="vtitle">${esc(v.cleanTitle)}</p>
        <p class="vmeta">${esc(v.channel.name)} · ${fmtDate(v.pub, { time: true })}${v.short ? ' · <span class="short-tag">Short</span>' : ''}</p>
        <p class="vhint">${hintFor(v)}</p>
      </div>
    </a>`;
  const skeletonRows = (n = 5) => Array.from({ length: n }, () => `
    <div class="skel-row"><div class="skel skel-thumb"></div><div><div class="skel skel-line" style="width:92%"></div><div class="skel skel-line" style="width:64%"></div><div class="skel skel-line" style="width:40%"></div></div></div>`).join('');
  const errorBox = (title, body, act = 'retry') => `
    <div class="error-box" role="alert"><h3>${esc(title)}</h3><p>${esc(body)}</p><button class="btn" type="button" data-act="${act}">${icon('refresh')} Reintentar</button></div>`;

  /* ---------- reproductor y minirreproductor ---------- */
  function ensurePlayer() {
    if (player) return player;
    player = new CR.Player(document.getElementById('player'));
    player.on('time', onTime);
    player.on('state', onState);
    return player;
  }
  let lastSave = 0;
  function onTime(t) {
    if (!cur.video) return;
    const dur = cur.video.dur || 0;
    document.getElementById('dock-time').textContent = `${fmtT(t)} / ${fmtT(dur)}`;
    document.getElementById('dock-bar').style.width = dur ? `${Math.min(100, (t / dur) * 100)}%` : '0';
    const now = Date.now();
    if (now - lastSave > 3000) {
      lastSave = now;
      store.set('session', { v: cur.id, t, at: new Date().toISOString() });
    }
    if (screen === `v:${cur.id}`) syncNow(t);
  }
  function onState(state) {
    const playing = state === 'playing';
    const btn = document.getElementById('dock-toggle');
    btn.innerHTML = icon(playing ? 'pause' : 'play');
    btn.setAttribute('aria-label', playing ? 'Pausar' : 'Reproducir');
    if (state === 'needs-tap') CR.toast('Toca el vídeo para empezar a reproducir');
    if (state === 'paused' && cur.id) store.set('session', { v: cur.id, t: player.time(), at: new Date().toISOString() });
  }
  function setDock() {
    const onVideo = screen && screen.startsWith('v:');
    const mode = onVideo ? 'full' : cur.id && !dockClosed ? 'mini' : 'none';
    dock.dataset.mode = mode;
    document.body.classList.toggle('has-mini', mode === 'mini');
    if (cur.video) {
      document.getElementById('dock-title').textContent = cur.video.cleanTitle;
      document.getElementById('dock-meta').href = `#/v/${cur.id}`;
    }
  }

  /* Marca el hallazgo y el párrafo que corresponden al segundo actual. */
  function syncNow(t) {
    if (cur.blocks.length) {
      const segI = CR.segAt(cur.doc.segments, t);
      const bi = cur.blocks.findIndex((b) => segI >= b.i0 && segI <= b.i1);
      if (bi !== cur.nowBlock) {
        cur.nowBlock = bi;
        CR.$$('.tx-block.is-now', view).forEach((el) => el.classList.remove('is-now'));
        const el = view.querySelector(`.tx-block[data-i="${bi}"]`);
        if (el) {
          el.classList.add('is-now');
          if (ui.follow && cur.tab === 'transcripcion' && player.playing) autoScroll(el);
        }
      }
    }
    if (cur.doc && cur.doc.claims) {
      const near = cur.doc.claims.filter((c) => c.t != null && c.t <= t + 1 && c.t > t - 60).sort((a, b) => b.t - a.t)[0];
      const id = near ? near.id : null;
      if (id !== cur.nowClaim) {
        cur.nowClaim = id;
        CR.$$('.find.is-now', view).forEach((el) => el.classList.remove('is-now'));
        if (id) CR.$$(`.find[data-claim="${id}"]`, view).forEach((el) => el.classList.add('is-now'));
      }
    }
  }
  let autoScrolling = false;
  function autoScroll(el) {
    autoScrolling = true;
    el.scrollIntoView({ block: 'center', behavior: CR.reduced() ? 'auto' : 'smooth' });
    setTimeout(() => { autoScrolling = false; }, 700);
  }
  const stopFollow = () => {
    if (autoScrolling || cur.tab !== 'transcripcion' || !screen || !screen.startsWith('v:')) return;
    if (ui.follow) {
      ui.follow = false;
      const b = document.getElementById('follow');
      if (b) b.hidden = false;
    }
  };
  window.addEventListener('wheel', stopFollow, { passive: true });
  window.addEventListener('touchmove', stopFollow, { passive: true });

  /* ---------- rutas ---------- */
  const TAB_OF = { '': 'home', v: 'home', narrativas: 'narrativas', n: 'narrativas', activos: 'activos', a: 'activos', guardados: 'guardados', estados: 'guardados' };
  function saveScroll() { if (screen) scrolls.set(screen, window.scrollY); }
  function restoreScroll(key) { window.scrollTo(0, scrolls.get(key) || 0); }

  async function route(r) {
    const [a = '', b] = r.parts;
    const key = a === 'v' ? `v:${b}` : a === 'activos' ? `activos:${r.q.s || ui.section}` : a ? `${a}${b ? ':' + b : ''}` : 'home';
    if (screen === key) { if (a === 'v') applyVideoParams(r.q); return; }
    saveScroll();
    closeSheet(true);
    screen = key;
    document.body.dataset.screen = a === 'v' ? 'video' : a || 'home';
    CR.$$('.tabbar a').forEach((el) => {
      if (el.dataset.tab === TAB_OF[a]) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
    });
    setDock();
    if (!idx) {
      view.innerHTML = a === 'v' ? '' : `<div class="section"><div class="skel" style="height:28px;width:50%"></div></div>${skeletonRows()}`;
      try { idx = await CR.load(); } catch (e) {
        view.innerHTML = errorBox('No se pudieron cargar los vídeos', 'Revisa la conexión. Lo que ya habías visto sigue guardado en este dispositivo.');
        return;
      }
    }
    if (a === 'v') await renderVideo(b, r.q);
    else if (a === 'narrativas') renderThemes();
    else if (a === 'n') renderTheme(b);
    else if (a === 'activos') renderAssets(r.q.s);
    else if (a === 'a') renderAsset(b);
    else if (a === 'guardados') renderSaved();
    else if (a === 'buscar') renderSearch(r.q.q || '');
    else if (a === 'estados') renderStates();
    else renderHome();
    setDock();
    if (a !== 'v') restoreScroll(key);
    if (a === 'buscar') { const inp = document.getElementById('q'); if (inp) inp.focus(); }
  }

  /* ---------- inicio: vídeos ---------- */
  function filterVideos(f) {
    const vs = idx.videos;
    if (f === 'analizados') return vs.filter((v) => v.analysis);
    if (f === 'shorts') return vs.filter((v) => v.short);
    if (f === 'nacho' || f === 'kmanu') return vs.filter((v) => v.ch === f);
    return vs;
  }
  function continueCard() {
    const session = store.get('session', null);
    const sv = session && idx.videosById[session.v];
    const v = sv || idx.analyzed[0] || idx.videos[0];
    const t = sv ? session.t : 0;
    const pct = v.dur ? Math.min(100, (t / v.dur) * 100) : 0;
    const label = sv ? 'Continuar viendo' : 'Último análisis';
    const hint = v.analysis
      ? `${CR.plural(v.analysis.claims, 'afirmación detectada', 'afirmaciones detectadas')} · ${CR.plural(v.analysis.assets.length, 'activo mencionado', 'activos mencionados')}`
      : 'Transcripción lista · análisis pendiente';
    return `
      <article class="continue">
        <a class="continue-media" href="#/v/${v.id}${sv ? `?t=${Math.floor(t)}` : ''}" aria-label="${esc(label)}: ${esc(v.cleanTitle)}">
          <img src="${CR.thumb(v.id, 'hq')}" alt="" decoding="async">
          ${sv ? `<span class="continue-progress"><span style="width:${pct}%"></span></span>` : ''}
        </a>
        <div class="continue-body">
          <p class="continue-label">${label}${sv ? ` · te quedaste en ${fmtT(t)} de ${fmtT(v.dur)}` : ` · ${esc(v.channel.name)}, ${fmtDate(v.pub)}`}</p>
          <h2 class="continue-title">${esc(v.cleanTitle)}</h2>
          <p class="continue-hint">${hint}</p>
          <div class="continue-actions">
            <a class="btn btn-primary" href="#/v/${v.id}${sv ? `?t=${Math.floor(t)}` : ''}">${icon('play')} ${sv ? 'Continuar' : 'Abrir el cuaderno'}</a>
          </div>
        </div>
      </article>`;
  }
  function renderHome() {
    const count = (f) => filterVideos(f).length;
    const filters = [['todos', 'Todos'], ['analizados', 'Con análisis'], ['nacho', 'Nacho IC'], ['kmanu', 'KManuS88'], ['shorts', 'Shorts']];
    const list = filterVideos(ui.filter);
    let lastDay = null;
    const rows = list.map((v) => {
      const day = CR.dayKey(v.pub);
      const head = day !== lastDay ? `<h3 class="day">${esc(CR.dayLabel(v.pub))}</h3>` : '';
      lastDay = day;
      return head + videoRow(v);
    }).join('');
    view.innerHTML = `
      ${continueCard()}
      <div class="block-head"><h2 class="h2">Vídeos</h2><span class="meta">${idx.videos.length} · datos ${CR.rel(idx.generatedAt)}</span></div>
      <div class="chips" role="toolbar" aria-label="Filtrar vídeos">
        ${filters.map(([k, label]) => `<button class="chip" type="button" data-act="filter" data-f="${k}" aria-pressed="${ui.filter === k}">${label}<span class="count">${count(k)}</span></button>`).join('')}
      </div>
      ${rows || `<div class="empty">${icon('filter')}<h3>Ningún vídeo con este filtro</h3><p>Prueba con «Todos».</p></div>`}`;
  }

  /* ---------- ficha del vídeo ---------- */
  function resumeTime(id) {
    const s = store.get('session', null);
    return s && s.v === id ? s.t : 0;
  }
  async function renderVideo(id, q) {
    const video = idx.videosById[id];
    if (!video) {
      view.innerHTML = `<div class="empty">${icon('alert')}<h3>Este vídeo no está en el archivo</h3><p>Puede que el enlace sea de otra versión de los datos.</p><a class="btn" href="#/">Ver vídeos</a></div>`;
      return;
    }
    document.getElementById('videobar-title').textContent = video.cleanTitle;
    updateSaveVideoBtn(video);
    ensurePlayer();
    dockClosed = false;
    const start = q.t != null ? Number(q.t) : cur.id === id ? player.time() : resumeTime(id);
    if (cur.id !== id) {
      Object.assign(cur, { id, video, doc: null, blocks: [], nowBlock: -1, nowClaim: null });
      ui.showAll = false; ui.kind = 'todos'; ui.txQuery = ''; ui.follow = true;
      player.load(video, { start });
    } else if (q.t != null) {
      player.seek(Number(q.t), { play: false });
    }
    setDock();
    view.innerHTML = videoHead(video, null) + `<div class="finds">${'<div class="skel" style="height:180px;margin-top:12px"></div>'.repeat(2)}</div>`;
    let doc;
    try { doc = await CR.loadVideo(id); } catch (e) {
      if (screen !== `v:${id}`) return;
      view.innerHTML = videoHead(video, null) + errorBox('No se pudo cargar el cuaderno', 'El vídeo sigue disponible arriba. Reintenta para ver transcripción y análisis.', 'retry-video');
      return;
    }
    if (screen !== `v:${id}`) return;
    cur.doc = doc;
    cur.tab = q.tab || store.get(`tab:${id}`, video.analysis ? 'destilado' : 'transcripcion');
    view.innerHTML = videoHead(video, doc) + segControl(video) + '<div id="tab-body"></div>';
    renderTab();
    window.scrollTo(0, 0);
    applyVideoParams(q);
  }

  function distillSteps(video, doc) {
    const a = video.analysis;
    const steps = [
      { k: 'Transcripción', s: `${video.segs} líneas`, st: 'done' },
      { k: 'Afirmaciones', s: a ? `${a.claims} extraídas` : 'Pendiente', st: a ? 'done' : '' },
      { k: 'Activos', s: a ? (a.assets.length ? CR.plural(a.assets.length, 'vinculado', 'vinculados') : 'Ninguno') : 'Pendiente', st: a ? 'done' : '' },
      { k: 'Análisis', s: a ? (a.estado === 'completo' ? 'Completo' : 'Parcial') : 'Pendiente', st: a ? (a.estado === 'completo' ? 'done' : 'partial') : '' },
    ];
    const note = a
      ? `Recorrido completo. El análisis es <b>${a.estado}</b>: ${doc && doc.analysis ? esc(lowerFirst(CR.clip(doc.analysis.alcance.limitaciones[0] || '', 150))) : 'trabajó solo con la transcripción y el título.'}`
      : `La transcripción ya se puede leer y buscar. Este vídeo todavía no se ha enviado a analizar, así que no hay afirmaciones ni activos vinculados.`;
    return `
      <section class="distill" aria-label="Estado del procesamiento">
        <ol class="distill-steps">
          ${steps.map((s) => `<li class="dstep ${s.st}"><span class="dstep-dot">${s.st === 'done' ? icon('check') : s.st === 'partial' ? icon('dot') : ''}</span><b>${s.k}</b><small>${s.s}</small></li>`).join('')}
        </ol>
        <p class="distill-note">${note}</p>
      </section>`;
  }
  function videoHead(video, doc) {
    return `
      <section class="vhead">
        <div class="byline"><span class="avatar">${esc(video.channel.initials)}</span><div><p style="font-weight:650;font-size:15px">${esc(video.channel.name)}</p><p class="meta">${fmtDate(video.pub, { weekday: true, time: true })} · ${video.short ? 'Short' : CR.fmtDur(video.dur)}</p></div></div>
        <h1 class="vh-title">${esc(video.cleanTitle)}</h1>
        <div class="vh-actions">
          <a class="btn" href="${CR.yt(video.id)}" target="_blank" rel="noopener">${icon('external')} YouTube</a>
          ${video.analysis ? `<button class="btn" type="button" data-act="tab" data-tab="analisis">${icon('book')} Leer el análisis</button>` : ''}
        </div>
      </section>
      ${distillSteps(video, doc)}`;
  }
  function segControl(video) {
    const a = video.analysis;
    const tabs = [['destilado', 'Destilado', a ? a.claims : null], ['transcripcion', 'Transcripción', null], ['analisis', 'Análisis', null]];
    return `<div class="seg-wrap"><div class="seg" role="tablist" aria-label="Vistas del cuaderno">
      ${tabs.map(([k, label, n]) => `<button type="button" role="tab" data-act="tab" data-tab="${k}" aria-selected="${cur.tab === k}">${label}${n ? ` <span class="count">${n}</span>` : ''}</button>`).join('')}
    </div></div>`;
  }
  function setTab(tab) {
    cur.tab = tab;
    store.set(`tab:${cur.id}`, tab);
    CR.$$('.seg [role="tab"]', view).forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
    renderTab();
    const seg = view.querySelector('.seg-wrap');
    if (seg) {
      const top = seg.getBoundingClientRect().top + window.scrollY - (document.querySelector('.videobar').offsetHeight + dock.offsetHeight);
      if (window.scrollY > top) window.scrollTo(0, top);
    }
    const q = CR.parseHash().q;
    CR.go(['v', cur.id], Object.assign({}, q, { tab, c: q.c }), { replace: true });
  }
  function renderTab() {
    const body = document.getElementById('tab-body');
    if (!body) return;
    cur.blocks = [];
    cur.nowBlock = -1;
    cur.nowClaim = null;
    if (cur.tab === 'transcripcion') body.innerHTML = transcriptHtml();
    else if (cur.tab === 'analisis') body.innerHTML = analysisHtml();
    else body.innerHTML = destiladoHtml();
    if (cur.tab === 'transcripcion') bindTranscript();
    if (player) syncNow(player.time());
  }

  /* Destilado: primero los hallazgos principales; el resto se despliega. */
  const SCORE = { prediccion: 5, hipotesis: 4, opinion: 3, insinuacion: 3, hecho_verificable: 1 };
  function mainFindings(all) {
    const score = (c) => (SCORE[c.tipo] || 0) + (c.conv === 'alta' ? 1 : 0) + (c.assets.length ? 1 : 0) + (c.own ? 2 : 0);
    return all.slice().sort((a, b) => score(b) - score(a) || (a.t || 0) - (b.t || 0)).slice(0, 5).sort((a, b) => (a.t == null ? -1 : a.t) - (b.t == null ? -1 : b.t));
  }
  function findCard(c, video) {
    const lit = c.literal;
    const fromTitle = lit && lit.origen === 'titulo';
    const tBtn = fromTitle || c.t == null
      ? `<span class="tchip is-title">${icon('text', 'i-s')} Título</span>`
      : `<button class="tchip" type="button" data-act="seek" data-t="${c.t}" aria-label="Ir al minuto ${fmtT(c.t)}">${icon('play', 'i-s')}${fmtT(c.t)}</button>`;
    return `
      <article class="find" data-claim="${c.id}" ${kindStyle(c.tipo)}>
        <header class="find-h">${tBtn}<span class="kind">${L.tipo[c.tipo]}</span><span class="verif">${L.verif[c.verif]}</span></header>
        ${lit ? `<div class="voice"><p class="voice-label">${fromTitle ? 'Lo que dice el título' : `Lo que dice ${esc(video.channel.name)}`}</p><blockquote class="quote">${esc(lit.cita)}</blockquote></div>` : ''}
        <div class="voice"><p class="voice-label sys">Interpretación del sistema</p><p class="interp">${esc(c.text)}</p></div>
        ${c.assets.length ? `<div class="find-assets">${c.assets.map(assetChip).join('')}</div>` : ''}
        <footer class="find-f">
          ${c.t != null && !fromTitle ? `<button class="btn-text" type="button" data-act="seek" data-t="${c.t}">${icon('play')} Ver fragmento</button>` : '<span></span>'}
          <button class="btn-text" type="button" data-act="claim" data-c="${c.id}">Examinar argumento ${icon('chevron-right')}</button>
        </footer>
      </article>`;
  }
  function pendingHtml(video) {
    const names = topNames(video, 4);
    return `
      <div class="pending">
        <h3>Este vídeo aún no tiene destilado</h3>
        <p>Las afirmaciones aparecen cuando termina el análisis. Mientras tanto puedes leer la transcripción completa y saltar a cualquier minuto.</p>
        ${names.length ? `<p>En la transcripción se nombra ${esc(joinEs(names))}.</p><div class="find-assets">${Object.keys(video.topics).filter((t) => idx.topicsById[t]).slice(0, 4).map(assetChip).join('')}</div>` : ''}
        <button class="btn btn-primary" type="button" data-act="tab" data-tab="transcripcion">${icon('text')} Leer la transcripción</button>
      </div>`;
  }
  function destiladoHtml() {
    const { video, doc } = cur;
    if (!doc.analysis) return pendingHtml(video);
    const all = doc.claims.map((c) => CR.claim(doc, c.id)).filter(Boolean);
    const main = mainFindings(all);
    let rest = '';
    if (ui.showAll) {
      const kinds = CR.ORDER_TIPO.filter((k) => all.some((c) => c.tipo === k));
      const list = all.filter((c) => ui.kind === 'todos' || c.tipo === ui.kind).sort((a, b) => (a.t == null ? -1 : a.t) - (b.t == null ? -1 : b.t));
      rest = `
        <div class="subhead"><h3>Todos los hallazgos, en orden del vídeo</h3><span class="meta">${list.length}</span></div>
        <div class="chips" role="toolbar" aria-label="Filtrar por tipo">
          <button class="chip" type="button" data-act="kind" data-k="todos" aria-pressed="${ui.kind === 'todos'}">Todos<span class="count">${all.length}</span></button>
          ${kinds.map((k) => `<button class="chip" type="button" data-act="kind" data-k="${k}" aria-pressed="${ui.kind === k}">${L.tipoPl[k]}<span class="count">${all.filter((c) => c.tipo === k).length}</span></button>`).join('')}
        </div>
        <div class="finds" style="margin-top:8px">${list.map((c) => findCard(c, video)).join('')}</div>`;
    }
    return `
      <div class="subhead"><h3>Hallazgos principales</h3><span class="meta">${main.length} de ${all.length}</span></div>
      <div class="finds">${main.map((c) => findCard(c, video)).join('')}</div>
      ${ui.showAll ? rest : `<button class="btn more-finds" type="button" data-act="show-all">${icon('list')} Ver los ${all.length} hallazgos</button>`}`;
  }

  /* Transcripción sincronizada con búsqueda. */
  function highlight(text, q) {
    const safe = esc(text);
    if (!q) return safe;
    const norm = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return safe.replace(new RegExp(`(${esc(norm)})`, 'gi'), '<mark>$1</mark>');
  }
  function transcriptHtml() {
    const { doc } = cur;
    const blocks = CR.blocks(doc.segments);
    cur.blocks = blocks;
    const claimsAt = new Map();
    (doc.claims || []).forEach((c) => {
      if (c.t == null) return;
      const si = CR.segAt(doc.segments, c.t);
      const bi = blocks.findIndex((b) => si >= b.i0 && si <= b.i1);
      if (bi >= 0) claimsAt.set(bi, (claimsAt.get(bi) || []).concat(c));
    });
    return `
      <div class="tx-tools">
        <label class="field">${icon('search')}<span class="sr">Buscar en la transcripción</span><input id="tx-q" type="search" placeholder="Buscar en la transcripción" value="${esc(ui.txQuery)}" autocomplete="off" enterkeyhint="search"></label>
        <span class="tx-count" id="tx-count" aria-live="polite"></span>
      </div>
      <div class="tx" id="tx">
        ${blocks.map((b, i) => `
          <div class="tx-block" data-i="${i}">
            <button class="tx-time" type="button" data-act="seek" data-t="${b.start}" aria-label="Reproducir desde ${fmtT(b.start)}">${fmtT(b.start)}</button>
            <div>
              <p class="tx-text">${highlight(b.text, ui.txQuery)}</p>
              ${(claimsAt.get(i) || []).length ? `<div class="tx-claims">${claimsAt.get(i).map((c) => `<button class="tx-claim" type="button" data-act="claim" data-c="${c.id}" ${kindStyle(c.tipo)}>${L.tipo[c.tipo]} · ${esc(CR.clip(c.text, 46))}</button>`).join('')}</div>` : ''}
            </div>
          </div>`).join('')}
      </div>
      <button class="btn follow" id="follow" type="button" data-act="follow" hidden>${icon('target')} Volver al minuto actual</button>`;
  }
  function bindTranscript() {
    const input = document.getElementById('tx-q');
    const count = document.getElementById('tx-count');
    const run = CR.debounce(() => {
      ui.txQuery = input.value.trim();
      CR.$$('.tx-block', view).forEach((el) => {
        const b = cur.blocks[Number(el.dataset.i)];
        el.querySelector('.tx-text').innerHTML = highlight(b.text, ui.txQuery);
      });
      const hits = CR.$$('.tx-text mark', view);
      count.textContent = ui.txQuery ? (hits.length ? CR.plural(hits.length, 'coincidencia', 'coincidencias') : 'Sin coincidencias') : '';
      if (hits[0]) { ui.follow = false; document.getElementById('follow').hidden = false; hits[0].scrollIntoView({ block: 'center' }); }
    }, 220);
    input.addEventListener('input', run);
    if (ui.txQuery) run();
  }

  /* Análisis completo: tres capas (dice / sugiere / se puede demostrar) y el resto plegado. */
  const evChips = (ids, doc) => ids.map((e) => doc.evidenceById[e]).filter((e) => e && e.inicio_s != null)
    .map((e) => `<button class="mini-t" type="button" data-act="seek" data-t="${e.inicio_s}">${fmtT(e.inicio_s)}</button>`).join('');
  const fold = (title, count, body, open = false) => `
    <details class="fold"${open ? ' open' : ''}><summary><span>${title}</span>${count != null ? `<span class="count">${count}</span>` : ''}${icon('chevron-down')}</summary><div class="fold-body">${body}</div></details>`;
  function chainHtml(ch, doc) {
    return `<div class="chain">
      <div class="chain-row">${icon('dot')}<p>${esc(ch.premisa)}</p></div>
      <div class="chain-row">${icon('arrow-right')}<p><b>${esc(ch.conclusion)}</b></p></div>
      ${ch.supuesto ? `<p class="assume"><b>Supuesto:</b> ${esc(ch.supuesto)}</p>` : ''}
      <div class="chain-meta"><span class="tag ${ch.vinculo === 'inferido' ? 'sys' : ''}">${L.vinculo[ch.vinculo]}</span>${evChips(ch.evidencia_ids, doc)}</div>
    </div>`;
  }
  function scenarioHtml(s) {
    return `<div class="scen">
      <div class="row" style="gap:8px;flex-wrap:wrap"><span class="tag ${s.origen === 'analista' ? 'sys' : ''}">${L.origenEsc[s.origen]}</span><span class="tag">${L.plaus[s.plausibilidad]}</span></div>
      <h4 style="margin-top:8px">${esc(s.nombre)}</h4>
      <p>${esc(s.mecanismo)}</p>
      <div class="two">
        <div><h5>Señales a favor</h5><ul>${s.senales_a_favor.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>
        <div><h5>Señales en contra</h5><ul>${s.senales_en_contra.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>
      </div>
      <p><b>Invalidación:</b> ${esc(s.invalidacion)}</p>
      ${s.evidencia_faltante.length ? `<p><b>Falta:</b> ${esc(s.evidencia_faltante.join(' · '))}</p>` : ''}
      <p class="meta">${s.probabilidad == null ? 'Sin probabilidad: no hay un método que la respalde.' : `Probabilidad ${s.probabilidad} · ${esc(s.metodo_probabilidad)}`}</p>
    </div>`;
  }
  function analysisHtml() {
    const { video, doc } = cur;
    if (!doc.analysis) return pendingHtml(video);
    const a = doc.analysis;
    const r = a.resumen;
    const aspects = Object.entries(a.ocho_aspectos).map(([k, v]) => `
      <div class="aspect"><h4>${L.aspectos[k]} <span class="tag">${v.estado === 'evaluado' ? 'Evaluado' : v.estado === 'parcial' ? 'Parcial' : 'No evaluable'}</span></h4>
        ${v.hallazgos.map((h) => `<p class="obs">${esc(h.observacion)}</p><p class="int">${esc(h.interpretacion)}</p><p class="lim">Límite: ${esc(h.limite)}</p><div class="chain-meta" style="margin-left:0">${evChips(h.evidencia_ids, doc)}</div>`).join('')}
        ${v.limitaciones.map((x) => `<p class="lim">${esc(x)}</p>`).join('')}
      </div>`).join('');
    return `
      <div class="an">
        <div class="an-state">
          <h3>${L.estado[a.estado]} · ${fmtDate(cur.doc.meta.analyzed_at, { time: true })}</h3>
          <p>Verificación externa: no realizada. Las afirmaciones se comprobaron contra la transcripción, no contra el mercado.</p>
        </div>
        <div class="layers">
          <div class="layer creator"><p class="layer-k">Lo que dice el creador</p><p>${esc(r.mensaje_explicito)}</p></div>
          <div class="layer sys"><p class="layer-k">Lo que intenta hacer pensar · interpretación</p><p>${esc(r.narrativa_sugerida)}</p></div>
          <div class="layer ext"><p class="layer-k">Lo que se puede demostrar con lo recibido</p><p>${esc(r.respaldo_demostrable)}</p></div>
          <div class="layer"><p class="layer-k">Conclusión provisional</p><p>${esc(r.conclusion_provisional)}</p></div>
        </div>
        ${fold('Cadena del argumento', a.cadena_narrativa.length, a.cadena_narrativa.map((ch) => chainHtml(ch, doc)).join(''), true)}
        ${fold('Escenarios', a.escenarios.length, a.escenarios.map(scenarioHtml).join(''))}
        ${fold('Qué vigilar', a.seguimiento.length, a.seguimiento.map((s) => `<div class="watch"><p>${esc(s.que_observar)}</p><small>${esc(s.criterio)}${s.plazo ? ` · Plazo: ${esc(s.plazo)}` : ''}</small></div>`).join(''))}
        ${fold('Preguntas abiertas', a.verificaciones_pendientes.length, a.verificaciones_pendientes.map((p) => `<div class="watch"><p>${esc(p.pregunta)}</p><small>${L.prioridad[p.prioridad]} · Buscar: ${esc(p.fuente_o_dato_buscado)}</small></div>`).join(''))}
        ${fold('Técnicas narrativas', a.tecnicas_narrativas.length, a.tecnicas_narrativas.map((t) => `<div class="watch"><p><b>${esc(t.tecnica)}</b> · confianza ${CR.nivel(t.confianza).toLowerCase()}</p><small>${esc(t.mecanismo)}</small><small>Otra explicación posible: ${esc(t.explicacion_alternativa)}</small><div class="chain-meta" style="margin-left:0">${evChips(t.evidencia_ids, doc)}</div></div>`).join(''))}
        ${fold('Ocho aspectos', 8, aspects)}
        ${fold('Alcance y límites', a.alcance.limitaciones.length, `<ul class="bul">${a.alcance.limitaciones.map((x) => `<li>${esc(x)}</li>`).join('')}</ul><p class="meta" style="margin-top:10px">${esc(a.alcance.alcance_verificacion)}</p>`)}
      </div>`;
  }

  /* ---------- hojas: argumento y activo ---------- */
  function openSheet(title, html, foot = '') {
    document.getElementById('sheet-title').textContent = title;
    document.getElementById('sheet-body').innerHTML = html;
    document.getElementById('sheet-foot').innerHTML = foot;
    document.getElementById('sheet-body').scrollTop = 0;
    sheet.hidden = false;
    scrim.hidden = false;
    sheet.querySelector('[data-act="sheet-close"]').focus({ preventScroll: true });
  }
  /* La hoja de un argumento vive en la URL (?c=A4): se puede compartir y el botón Atrás la cierra. */
  let sheetPushed = false;
  function closeSheet(silent) {
    if (sheet.hidden) return;
    sheet.hidden = true;
    scrim.hidden = true;
    if (silent) { sheetPushed = false; return; }
    const r = CR.parseHash();
    if (r.parts[0] === 'v' && r.q.c) {
      if (sheetPushed) { sheetPushed = false; history.back(); return; }
      const q = Object.assign({}, r.q);
      delete q.c;
      CR.go(['v', r.parts[1]], q, { replace: true });
    }
  }
  const kv = (k, v) => (v ? `<dt>${k}</dt><dd>${esc(v)}</dd>` : '');
  function evidenceHtml(e, video) {
    const label = e.origen === 'titulo' ? 'Título del vídeo' : `${L.origen[e.origen]}${e.inicio_s != null ? ` · ${fmtT(e.inicio_s)}` : ''}`;
    return `<div class="ev">
      <div class="between"><span class="voice-label">${label}</span>${e.inicio_s != null ? `<button class="btn-text" type="button" data-act="seek" data-t="${e.inicio_s}">${icon('play')} Escuchar</button>` : ''}</div>
      ${e.cita ? `<blockquote class="quote">${esc(e.cita)}</blockquote>` : ''}
      ${e.observacion ? `<p class="ev-obs">Nota del sistema: ${esc(e.observacion)}</p>` : ''}
    </div>`;
  }
  function openClaim(id) {
    const { video, doc } = cur;
    if (!doc || !doc.analysis) return;
    const c = CR.claim(doc, id);
    if (!c) return;
    const a = doc.analysis;
    const chains = a.cadena_narrativa.filter((ch) => ch.afirmacion_ids.includes(id));
    const scen = a.escenarios.filter((s) => s.afirmacion_ids.includes(id));
    const watch = a.seguimiento.filter((s) => s.afirmacion_ids.includes(id));
    const pend = a.verificaciones_pendientes.filter((p) => p.afirmacion_ids.includes(id));
    const m = c.mercado;
    const key = `c:${video.id}:${id}`;
    openSheet(`${L.tipo[c.tipo]}${c.t != null ? ` · ${fmtT(c.t)}` : ''}`, `
      <div class="row" style="flex-wrap:wrap;gap:6px"><span class="tag">${L.verif[c.verif]}</span><span class="tag">Convicción del creador: ${CR.nivel(c.conv).toLowerCase()}</span><span class="tag">${esc(c.emisor)}</span></div>
      <section class="sheet-sec"><h3>Lo que dice ${esc(video.channel.name)}</h3>${c.evidences.map((e) => evidenceHtml(e, video)).join('')}</section>
      <section class="sheet-sec"><h3 style="color:var(--sys)">Lo que interpreta el sistema</h3>
        <p style="font-size:16px;line-height:1.5">${esc(c.text)}</p>
        ${m ? `<dl class="kv">${kv('Activo', m.activo_normalizado || m.activo_literal)}${kv('Postura', m.postura)}${kv('Plazo citado', m.horizonte_literal)}${kv('Condición', m.condicion)}${kv('Entrada', m.entrada)}${kv('Objetivo', m.objetivo)}${kv('Invalidación', m.invalidacion)}${kv('Catalizador', m.catalizador)}</dl>` : ''}
        <p class="meta" style="margin-top:10px">Confianza de la extracción: ${CR.nivel(c.conf).toLowerCase()}. ${esc(c.motivo)}</p>
        ${c.assets.length ? `<div class="find-assets">${c.assets.map(assetChip).join('')}</div>` : ''}
      </section>
      <section class="sheet-sec"><h3>Por qué figura como «${L.verif[c.verif].toLowerCase()}»</h3>
        <p style="font-size:15px;color:var(--ink-2)">${esc(c.justificacion)}</p>
        <div class="note-ext">${icon('alert')}<span>No se consultó ninguna fuente externa. Que el vídeo no aporte pruebas no demuestra que la afirmación sea falsa.</span></div>
      </section>
      ${chains.length ? `<section class="sheet-sec"><h3>Dónde encaja en el argumento</h3>${chains.map((ch) => chainHtml(ch, doc)).join('')}</section>` : ''}
      ${scen.length ? `<section class="sheet-sec"><h3>Escenarios que la usan</h3>${scen.map((s) => `<div class="watch"><p><b>${esc(s.nombre)}</b></p><small>${L.origenEsc[s.origen]} · ${L.plaus[s.plausibilidad]}</small></div>`).join('')}</section>` : ''}
      ${watch.length ? `<section class="sheet-sec"><h3>Qué vigilar</h3>${watch.map((s) => `<div class="watch"><p>${esc(s.que_observar)}</p><small>${esc(s.criterio)}${s.plazo ? ` · ${esc(s.plazo)}` : ''}</small></div>`).join('')}</section>` : ''}
      ${pend.length ? `<section class="sheet-sec"><h3>Pendiente de verificar</h3>${pend.map((p) => `<div class="watch"><p>${esc(p.pregunta)}</p><small>${L.prioridad[p.prioridad]}</small></div>`).join('')}</section>` : ''}`,
    `<button class="btn" type="button" data-act="save-claim" data-c="${id}">${icon(saved.has(key) ? 'bookmark-fill' : 'bookmark')} ${saved.has(key) ? 'Guardado' : 'Guardar'}</button>
     <button class="btn btn-primary" type="button" data-act="share-claim" data-c="${id}">${icon('share')} Compartir</button>`);
  }
  function openAsset(id) {
    const t = idx.topicsById[id];
    if (!t) return;
    const analyzed = t.claims.map((k) => idx.claimsByKey[`${k.v}:${k.id}`]).filter(Boolean);
    const here = cur.id ? analyzed.filter((c) => c.v === cur.id) : [];
    const mentions = t.videos.slice(0, 4);
    openSheet(t.name, `
      <p class="meta">${L.section[t.section]} · ${CR.plural(t.vc, 'vídeo', 'vídeos')} · ${CR.plural(t.n, 'mención', 'menciones')} · ${CR.plural(t.cc, 'creador', 'creadores')}</p>
      ${here.length ? `<section class="sheet-sec"><h3>En este vídeo</h3>${here.map((c) => `<div class="watch"><p>${esc(c.text)}</p><small>${L.tipo[c.tipo]}${c.t != null ? ` · ${fmtT(c.t)}` : ''}${c.postura ? ` · ${esc(c.postura)}` : ''}</small></div>`).join('')}</section>` : ''}
      <section class="sheet-sec"><h3>Otros vídeos que lo mencionan</h3>
        ${mentions.map((m) => { const v = idx.videosById[m.v]; return `<a class="res" style="margin:0 calc(-1 * var(--gutter))" href="#/v/${v.id}?t=${Math.floor(m.frags[0] ? m.frags[0].t : 0)}"><p>${esc(v.cleanTitle)}</p><small>${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${CR.plural(m.n, 'mención', 'menciones')}${m.frags[0] ? ` · desde ${fmtT(m.frags[0].t)}` : ''}</small></a>`; }).join('')}
      </section>`, `<a class="btn btn-primary" href="#/a/${id}">Abrir la ficha de ${esc(t.name)} ${icon('arrow-right')}</a>`);
  }
  function applyVideoParams(q) {
    if (q.tab && q.tab !== cur.tab && cur.doc) setTab(q.tab);
    if (q.c && cur.doc) openClaim(q.c); else closeSheet(true);
  }

  /* ---------- activos ---------- */
  function rankRow(t, i, max, by) {
    const val = by === 'videos' ? t.vc : t.n;
    return `<li><a class="rank-row" href="#/a/${t.id}">
      <span class="rank-n">${i + 1}</span>
      <span class="rank-main"><span class="rank-name">${esc(t.name)}${t.sym && t.sym !== t.name ? `<span class="sym">${esc(t.sym)}</span>` : ''}</span>
        <span class="rank-sub">${CR.plural(t.vc, 'vídeo', 'vídeos')} · ${CR.plural(t.n, 'mención', 'menciones')} · ${CR.plural(t.cc, 'creador', 'creadores')}</span>
        <span class="bar"><span style="width:${Math.max(6, (val / max) * 100)}%"></span></span></span>
      ${t.claims.length ? `<span class="rank-flag">${CR.plural(t.claims.length, 'afirmación', 'afirmaciones')}</span>` : '<span></span>'}
    </a></li>`;
  }
  function renderAssets(section) {
    const s = section || ui.section;
    ui.section = s;
    store.set('section', s);
    const by = ui.sort;
    const rows = idx.topics.filter((t) => t.section === s).sort((a, b) => (by === 'videos' ? b.vc - a.vc || b.n - a.n : b.n - a.n || b.vc - a.vc));
    const max = Math.max(...rows.map((t) => (by === 'videos' ? t.vc : t.n)), 1);
    const btc = idx.topicsById.btc;
    view.innerHTML = `
      <div class="section"><h1 class="h1">Activos</h1><p class="lede">Lo que se nombra en los ${idx.videos.length} vídeos y dónde. Toca un activo para ir a los fragmentos.</p></div>
      <div class="seg-top"><div class="seg" role="tablist" aria-label="Secciones de activos">
        ${['altcoins', 'macro', 'bolsa'].map((k) => `<button type="button" role="tab" data-act="section" data-s="${k}" aria-selected="${k === s}">${L.section[k]}</button>`).join('')}
      </div></div>
      ${s === 'altcoins' && btc ? `<a class="btc-card" href="#/a/btc"><div><p class="h3">Bitcoin, el activo central</p><p>Aparece en ${btc.vc} de ${idx.videos.length} vídeos y en ${btc.claims.length} afirmaciones analizadas. Queda fuera del ranking de altcoins.</p></div>${icon('chevron-right')}</a>` : ''}
      <div class="between" style="margin:20px var(--gutter) 6px"><h2 class="h3">Ranking por ${by === 'videos' ? 'vídeos' : 'menciones'}</h2><button class="link" type="button" data-act="sort">Ordenar por ${by === 'videos' ? 'menciones' : 'vídeos'}</button></div>
      <ol class="rank">${rows.map((t, i) => rankRow(t, i, max, by)).join('')}</ol>
      <p class="method">${icon('help')}<span>${esc(idx.method.mentions)}</span></p>`;
  }
  function renderAsset(id) {
    const t = idx.topicsById[id];
    if (!t) { view.innerHTML = `<div class="empty">${icon('alert')}<h3>Activo no encontrado</h3><a class="btn" href="#/activos">Ver activos</a></div>`; return; }
    const claims = t.claims.map((k) => idx.claimsByKey[`${k.v}:${k.id}`]).filter(Boolean).sort((a, b) => idx.videosById[b.v].pub.localeCompare(idx.videosById[a.v].pub) || (a.t || 0) - (b.t || 0));
    const claimRow = (c) => {
      const v = idx.videosById[c.v];
      return `<article class="find" style="margin:12px var(--gutter) 0;--kc:var(--t-${c.tipo})">
        <header class="find-h"><a class="tchip" href="#/v/${v.id}?t=${Math.floor(c.t || 0)}&c=${c.id}">${icon('play', 'i-s')}${c.t != null ? fmtT(c.t) : 'Título'}</a><span class="kind">${L.tipo[c.tipo]}</span><span class="verif">${fmtDate(v.pub)}</span></header>
        ${c.quote ? `<div class="voice"><p class="voice-label">Lo que dice ${esc(v.channel.name)}</p><blockquote class="quote">${esc(c.quote)}</blockquote></div>` : ''}
        <div class="voice"><p class="voice-label sys">Interpretación del sistema</p><p class="interp">${esc(c.text)}</p>${c.postura ? `<p class="meta" style="margin-top:6px">Postura extraída: ${esc(c.postura)}</p>` : ''}</div>
        <footer class="find-f"><a class="btn-text" href="#/v/${v.id}?t=${Math.floor(c.t || 0)}&c=${c.id}">Examinar en el vídeo ${icon('chevron-right')}</a></footer>
      </article>`;
    };
    view.innerHTML = `
      <div class="section"><a class="btn-text" href="#/activos?s=${t.section === 'bitcoin' ? 'altcoins' : t.section}">${icon('arrow-left')} Activos</a>
        <h1 class="h1" style="margin-top:4px">${esc(t.name)}</h1>
        <p class="lede">${L.section[t.section]} · ${CR.plural(t.vc, 'vídeo', 'vídeos')} · ${CR.plural(t.n, 'mención', 'menciones')} · ${CR.plural(t.cc, 'creador', 'creadores')}</p>
        ${t.note ? `<p class="meta" style="margin-top:6px">Ojo: ${esc(t.note)}.</p>` : ''}
      </div>
      <div class="block-head"><h2 class="h2">Lo que se analizó</h2><span class="meta">${claims.length}</span></div>
      ${claims.length ? claims.map(claimRow).join('') : `<div class="pending"><h3>Sin afirmaciones analizadas</h3><p>Se nombra en las transcripciones, pero ninguno de los ${idx.analyzed.length} vídeos analizados lo trata como afirmación.</p></div>`}
      <div class="block-head"><h2 class="h2">Dónde se menciona</h2><span class="meta">${t.vc} vídeos</span></div>
      ${t.videos.map((m) => {
        const v = idx.videosById[m.v];
        return `<article class="src">
          <a class="src-head" href="#/v/${v.id}">${thumb(v)}<div><p class="src-title">${esc(v.cleanTitle)}</p><p class="meta">${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${CR.plural(m.n, 'mención', 'menciones')}</p></div></a>
          ${m.frags.map((f) => `<div class="frag"><div class="between"><span class="voice-label">Transcripción · ${fmtT(f.t)}</span><a class="btn-text" href="#/v/${v.id}?t=${Math.floor(f.t)}">${icon('play')} Escuchar</a></div><blockquote class="quote">${esc(f.text)}</blockquote></div>`).join('')}
        </article>`;
      }).join('')}
      <p class="method">${icon('help')}<span>${esc(idx.method.mentions)}</span></p>`;
  }

  /* ---------- narrativas ---------- */
  function renderThemes() {
    view.innerHTML = `
      <div class="section"><h1 class="h1">Narrativas</h1><p class="lede">Ideas que se repiten entre vídeos. Que varios vídeos repitan algo no lo convierte en evidencia.</p></div>
      ${idx.themes.map((th) => {
        const vids = th.sources.map((s) => idx.videosById[s.v]);
        return `<a class="theme-card" href="#/n/${th.id}">
          <h3>${esc(th.title)}</h3>
          <p>${esc(th.about)}</p>
          <div class="thumbs">${vids.slice(0, 5).map((v) => `<img src="${CR.thumb(v.id)}" alt="" loading="lazy">`).join('')}${vids.length > 5 ? `<span class="more">+${vids.length - 5}</span>` : ''}</div>
          <p class="theme-foot">Explora los argumentos de ${CR.plural(th.videoCount, 'vídeo', 'vídeos')} · ${th.analyzedCount} con análisis · ${CR.plural(th.creators.length, 'creador', 'creadores')}</p>
          <span class="theme-cta">Abrir vídeos y argumentos ${icon('arrow-right')}</span>
        </a>`;
      }).join('')}
      <p class="method">${icon('help')}<span>${esc(idx.method.themes)}</span></p>`;
  }
  function contrastHtml(p) {
    const A = idx.claimsByKey[`${p.a.v}:${p.a.id}`], B = idx.claimsByKey[`${p.b.v}:${p.b.id}`];
    const va = idx.videosById[p.a.v], vb = idx.videosById[p.b.v];
    const side = (c, v) => `<div class="contrast-side">
      <div class="between"><span class="voice-label">${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${fmtT(c.t)}</span><a class="btn-text" href="#/v/${v.id}?t=${Math.floor(c.t || 0)}&c=${c.id}">${icon('play')} Escuchar</a></div>
      ${c.quote ? `<blockquote class="quote">${esc(c.quote)}</blockquote>` : ''}
      <p class="interp" style="margin-top:6px"><span class="voice-label sys">Postura extraída:</span> ${esc(c.postura || c.text)}</p>
    </div>`;
    const title = p.kind === 'cambio'
      ? `${p.sameCreator ? 'Cambio de postura' : 'Posturas opuestas'} sobre ${CR.topicName(p.asset)} · ${L.hz[p.hz].toLowerCase()}`
      : `Misma idea repetida sobre ${CR.topicName(p.asset)} · ${L.hz[p.hz].toLowerCase()}`;
    return `<article class="contrast">
      <div class="contrast-head"><h3>${esc(title)}</h3></div>
      ${side(A, va)}${side(B, vb)}
      <p class="contrast-foot">${p.kind === 'cambio' ? 'Detectado por reglas: mismo activo y plazo, postura en sentido contrario. El sistema no decide cuál acierta.' : `La repite ${p.sameCreator ? 'el mismo creador' : 'más de un creador'}: es repetición, no una prueba independiente.`}</p>
    </article>`;
  }
  function renderTheme(id) {
    const th = idx.themesById[id];
    if (!th) { view.innerHTML = `<div class="empty">${icon('alert')}<h3>Narrativa no encontrada</h3><a class="btn" href="#/narrativas">Ver narrativas</a></div>`; return; }
    const sources = th.sources.map((s) => {
      const v = idx.videosById[s.v];
      const claims = s.claims.map((cid) => idx.claimsByKey[`${s.v}:${cid}`]).filter(Boolean);
      return `<article class="src">
        <a class="src-head" href="#/v/${v.id}">${thumb(v)}<div><p class="src-title">${esc(v.cleanTitle)}</p><p class="meta">${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${v.analysis ? 'con análisis' : 'solo transcripción'}</p></div></a>
        ${claims.slice(0, 3).map((c) => `<div class="frag"><div class="between"><span class="voice-label">${L.tipo[c.tipo]}${c.t != null ? ` · ${fmtT(c.t)}` : ''}</span><a class="btn-text" href="#/v/${v.id}?t=${Math.floor(c.t || 0)}&c=${c.id}">Examinar ${icon('chevron-right')}</a></div>${c.quote ? `<blockquote class="quote">${esc(c.quote)}</blockquote>` : ''}<p class="interp" style="margin-top:6px">${esc(c.text)}</p></div>`).join('')}
        ${claims.length > 3 ? `<p class="meta" style="padding:6px 0 10px">Y ${CR.plural(claims.length - 3, 'afirmación más', 'afirmaciones más')} en el vídeo.</p>` : ''}
        ${!claims.length ? s.frags.map((f) => `<div class="frag"><div class="between"><span class="voice-label">Transcripción · ${fmtT(f.t)}</span><a class="btn-text" href="#/v/${v.id}?t=${Math.floor(f.t)}">${icon('play')} Escuchar</a></div><blockquote class="quote">${esc(f.text)}</blockquote></div>`).join('') : ''}
      </article>`;
    }).join('');
    view.innerHTML = `
      <div class="section"><a class="btn-text" href="#/narrativas">${icon('arrow-left')} Narrativas</a>
        <h1 class="h1" style="margin-top:4px">${esc(th.title)}</h1><p class="lede">${esc(th.about)}</p>
        <p class="meta" style="margin-top:8px">${CR.plural(th.videoCount, 'vídeo', 'vídeos')} · ${th.analyzedCount} con análisis · ${CR.plural(th.claimCount, 'afirmación', 'afirmaciones')} · ${th.creators.map((c) => idx.channelsBySlug[c].name).join(' y ')}</p>
        <div class="note-ext">${icon('alert')}<span>Ninguna fuente externa respalda todavía estas ideas. Contar vídeos indica cuántas veces se dijo, no si es cierto.</span></div>
      </div>
      ${th.contrasts.length ? `<div class="block-head"><h2 class="h2">Coincidencias y cambios</h2></div>${th.contrasts.map((i) => contrastHtml(idx.contrasts[i])).join('')}` : ''}
      <div class="block-head"><h2 class="h2">Vídeos y argumentos</h2><span class="meta">${th.videoCount}</span></div>
      ${sources}`;
  }

  /* ---------- guardados, estados, búsqueda ---------- */
  function renderSaved() {
    const list = saved.all();
    const rows = list.map((s) => `
      <div class="saved-row">
        <a href="${esc(s.href)}"><p class="voice-label">${esc(s.kind)} · ${esc(s.sub || '')}</p>${s.quote ? `<blockquote class="quote">${esc(CR.clip(s.quote, 160))}</blockquote>` : ''}<p style="font-size:15px;margin-top:4px">${esc(s.title)}</p></a>
        <button class="icon-btn" type="button" data-act="unsave" data-key="${esc(s.key)}" aria-label="Quitar de guardados">${icon('close')}</button>
      </div>`).join('');
    view.innerHTML = `
      <div class="section"><h1 class="h1">Guardados</h1><p class="lede">Hallazgos y vídeos para volver a su minuto exacto. Se guardan solo en este dispositivo.</p></div>
      ${list.length ? `<div style="margin-top:12px">${rows}</div>` : `<div class="empty">${icon('bookmark')}<h3>Todavía no has guardado nada</h3><p>En un hallazgo, pulsa «Examinar argumento» y luego «Guardar». Volverás al segundo en que se dijo.</p><a class="btn" href="#/v/${idx.analyzed[0].id}">Abrir el último análisis</a></div>`}
      <div class="block-head"><h2 class="h2">Sobre estos datos</h2></div>
      <div class="section"><p class="lede">${idx.videos.length} vídeos de ${idx.channels.map((c) => c.name).join(' y ')} entre el ${fmtDate(idx.period.from)} y el ${fmtDate(idx.period.to)}. ${idx.analyzed.length} tienen análisis; el resto, solo transcripción. ${esc(idx.method.external)}</p>
        <p style="margin-top:12px"><a class="link" href="#/estados">Ver cómo se ve cada estado del procesamiento</a></p></div>`;
  }
  function renderStates() {
    view.innerHTML = `
      <div class="section"><a class="btn-text" href="#/guardados">${icon('arrow-left')} Guardados</a><h1 class="h1" style="margin-top:4px">Estados del procesamiento</h1>
        <p class="lede">Cómo se ve un vídeo en cada momento. Los marcados como ejemplo no existen ahora mismo en el archivo.</p></div>
      ${CR.STATES.map((s) => `<article class="state-demo ${s.id === 'error' ? 'err' : ''}">
        <div class="between"><h3>${esc(s.title)}</h3><span class="tag">${s.real ? 'Real' : 'Ejemplo'}</span></div>
        <p>${esc(s.body)}</p>
        <div class="row"><span class="state ${s.id === 'listo' ? 'state-ok' : 'state-wait'}"><span class="state-dot"></span>${esc(s.chip)}</span><button class="btn" type="button" data-act="demo-action">${esc(s.action)}</button></div>
      </article>`).join('')}`;
  }
  function renderSearch(q) {
    view.innerHTML = `
      <div class="search-top"><label class="field">${icon('search')}<span class="sr">Buscar</span><input id="q" type="search" placeholder="Vídeos, afirmaciones, activos…" value="${esc(q)}" autocomplete="off" enterkeyhint="search"></label></div>
      <div id="results"></div>`;
    const input = document.getElementById('q');
    const run = () => {
      const val = input.value.trim();
      CR.go(['buscar'], { q: val }, { replace: true });
      const out = document.getElementById('results');
      if (!val) { out.innerHTML = `<div class="empty">${icon('search')}<h3>Busca en el archivo</h3><p>Prueba con «liquidaciones», «Hyperliquid» o «28 de octubre».</p></div>`; return; }
      const r = CR.search(val);
      const group = (title, items) => (items.length ? `<section class="res-group"><h3>${title}</h3>${items.join('')}</section>` : '');
      out.innerHTML = group('Vídeos', r.videos.slice(0, 8).map((v) => `<a class="res" href="#/v/${v.id}"><p>${esc(v.cleanTitle)}</p><small>${esc(v.channel.name)} · ${fmtDate(v.pub)}</small></a>`))
        + group('Afirmaciones', r.claims.slice(0, 10).map((c) => { const v = idx.videosById[c.v]; return `<a class="res" href="#/v/${v.id}?t=${Math.floor(c.t || 0)}&c=${c.id}"><p>${esc(c.text)}</p><small>${L.tipo[c.tipo]} · ${esc(v.channel.name)} · ${fmtT(c.t)}</small></a>`; }))
        + group('Activos', r.topics.slice(0, 8).map((t) => `<a class="res" href="#/a/${t.id}"><p>${esc(t.name)}</p><small>${CR.plural(t.vc, 'vídeo', 'vídeos')} · ${L.section[t.section]}</small></a>`))
        + group('Narrativas', r.themes.map((t) => `<a class="res" href="#/n/${t.id}"><p>${esc(t.title)}</p><small>${CR.plural(t.videoCount, 'vídeo', 'vídeos')}</small></a>`))
        + `<div class="section" style="margin-top:16px"><button class="btn" type="button" data-act="search-tx" style="width:100%">${icon('text')} Buscar también en las transcripciones</button><div id="tx-results"></div></div>`;
    };
    input.addEventListener('input', CR.debounce(run, 200));
    run();
  }
  async function searchTranscripts() {
    const val = (document.getElementById('q') || {}).value || '';
    const out = document.getElementById('tx-results');
    out.innerHTML = '<div class="skel" style="height:60px;margin-top:12px"></div>';
    const hits = await CR.searchTranscripts(val);
    out.innerHTML = hits.length ? hits.map((h) => { const v = idx.videosById[h.v]; return `<a class="res" style="margin:0 calc(-1 * var(--gutter))" href="#/v/${v.id}?t=${Math.floor(h.t)}"><blockquote class="quote" style="font-size:16px">${esc(h.text)}</blockquote><small>${esc(v.channel.name)} · ${esc(CR.clip(v.cleanTitle, 48))} · ${fmtT(h.t)}</small></a>`; }).join('')
      : `<p class="meta" style="margin-top:12px">Ninguna transcripción contiene «${esc(val)}».</p>`;
  }

  /* ---------- guardar y compartir ---------- */
  function updateSaveVideoBtn(video) {
    const on = saved.has(`v:${video.id}`);
    const b = document.getElementById('vb-save');
    b.innerHTML = icon(on ? 'bookmark-fill' : 'bookmark');
    b.classList.toggle('is-on', on);
    b.setAttribute('aria-label', on ? 'Quitar vídeo de guardados' : 'Guardar vídeo');
  }
  function toggleSaveClaim(id) {
    const c = CR.claim(cur.doc, id);
    const v = cur.video;
    const on = saved.toggle({
      key: `c:${v.id}:${id}`, kind: L.tipo[c.tipo], sub: `${v.channel.name} · ${fmtT(c.t)}`, title: c.text,
      quote: c.literal ? c.literal.cita : '', href: `#/v/${v.id}?t=${Math.floor(c.t || 0)}&c=${id}`,
    });
    CR.toast(on ? 'Hallazgo guardado' : 'Quitado de guardados', on ? { action: 'Ver', onAction: () => CR.go('#/guardados') } : {});
    openClaim(id);
  }
  async function shareClaim(id) {
    const c = CR.claim(cur.doc, id);
    const url = CR.linkTo(CR.hash(['v', cur.id], { t: Math.floor(c.t || 0), c: id }));
    const res = await CR.share({ title: cur.video.cleanTitle, text: `${L.tipo[c.tipo]} en ${fmtT(c.t)}: ${c.text}`, url });
    if (res === 'copied') CR.toast('Enlace al hallazgo copiado');
    if (res === 'failed') CR.toast('No se pudo copiar el enlace');
  }

  /* ---------- eventos ---------- */
  document.addEventListener('click', async (e) => {
    const el = e.target.closest('[data-act]');
    if (!el) return;
    const act = el.dataset.act;
    switch (act) {
      case 'filter': ui.filter = el.dataset.f; store.set('filter', ui.filter); renderHome(); break;
      case 'tab': setTab(el.dataset.tab); break;
      case 'seek': {
        const t = Number(el.dataset.t);
        if (screen && screen.startsWith('v:')) { player.seek(t, { play: true }); }
        break;
      }
      case 'claim': {
        const q = CR.parseHash().q;
        if (q.c) CR.go(['v', cur.id], Object.assign({}, q, { c: el.dataset.c }), { replace: true });
        else { sheetPushed = true; CR.go(['v', cur.id], Object.assign({}, q, { c: el.dataset.c })); }
        break;
      }
      case 'asset': openAsset(el.dataset.id); break;
      case 'show-all': ui.showAll = true; renderTab(); break;
      case 'kind': ui.kind = el.dataset.k; renderTab(); break;
      case 'follow': {
        ui.follow = true; el.hidden = true;
        const now = view.querySelector('.tx-block.is-now');
        if (now) autoScroll(now);
        break;
      }
      case 'sheet-close': closeSheet(); break;
      case 'save-claim': toggleSaveClaim(el.dataset.c); break;
      case 'share-claim': shareClaim(el.dataset.c); break;
      case 'save-video': {
        const v = cur.video;
        const on = saved.toggle({ key: `v:${v.id}`, kind: 'Vídeo', sub: `${v.channel.name} · ${fmtDate(v.pub)}`, title: v.cleanTitle, href: `#/v/${v.id}` });
        updateSaveVideoBtn(v);
        CR.toast(on ? 'Vídeo guardado' : 'Quitado de guardados');
        break;
      }
      case 'share-video': {
        const res = await CR.share({ title: cur.video.cleanTitle, text: cur.video.cleanTitle, url: CR.linkTo(CR.hash(['v', cur.id], { t: Math.floor(player.time()) })) });
        if (res === 'copied') CR.toast('Enlace copiado con el minuto actual');
        break;
      }
      case 'unsave': saved.remove(el.dataset.key); renderSaved(); break;
      case 'section': ui.section = el.dataset.s; CR.go(['activos'], { s: el.dataset.s }, { replace: true }); break;
      case 'sort': ui.sort = ui.sort === 'videos' ? 'menciones' : 'videos'; store.set('sort', ui.sort); renderAssets(ui.section); break;
      case 'back': CR.back('#/'); break;
      case 'dock-toggle': player && player.toggle(); break;
      case 'dock-close': if (player) player.pause(); dockClosed = true; setDock(); break;
      case 'search-tx': searchTranscripts(); break;
      case 'retry': location.reload(); break;
      case 'retry-video': screen = null; route(CR.parseHash()); break;
      case 'demo-action': CR.toast('Es un ejemplo del estado; en el producto llevaría a su acción.'); break;
      default: break;
    }
  });
  scrim.addEventListener('click', () => closeSheet());
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !sheet.hidden) closeSheet(); });
  window.addEventListener('scroll', () => document.body.classList.toggle('scrolled', window.scrollY > 4), { passive: true });

  const run = CR.onRoute(route);
  run();
})();

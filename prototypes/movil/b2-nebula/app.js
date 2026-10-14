/* 1B · Bitácora — diario de vídeos, cuaderno arrastrable con transcripción anotada y vídeo flotante. */
(() => {
  'use strict';
  const { esc, fmtT, fmtDate, icon, L } = CR;
  const APP = 'b2';
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
  const ui = { filter: store.get('filter', 'todo'), section: store.get('section', 'altcoins'), follow: true, txq: '' };
  const FILTERS = { todo: 'Todo el archivo', alcistas: 'Tono alcista', bajistas: 'Tono bajista o mixto a la baja', contraste: 'El título no cuadra con el vídeo', analizados: 'Solo con análisis', largos: 'Vídeos largos', shorts: 'Shorts', nacho: 'Nacho IC', kmanu: 'KManuS88' };
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

  /* ---------- rutas ---------- */
  function saveScroll() {
    if (!screen) return;
    scrolls.set(screen, screen.startsWith('v:') ? nbBody.scrollTop : window.scrollY);
  }
  const DOCK = { '': 'explorar', f: 'explorar', n: 'explorar', diario: 'diario', v: 'diario', guardados: 'guardados' };
  async function route(r) {
    const [a = '', b] = r.parts;
    const key = a === 'v' ? `v:${b}` : a === 'f' || a === '' ? 'explorar' : a ? `${a}${b ? ':' + b : ''}` : 'explorar';
    if (a !== 'f') closeFicha(true);
    if (screen === key) {
      if (a === 'v') applyVideoQuery(r.q);
      else if (key === 'explorar') { if (a === 'f') openFicha(b); else renderExplore(r.q, true); }
      return;
    }
    saveScroll();
    screen = key;
    document.body.dataset.screen = a === 'v' ? 'video' : key === 'explorar' ? 'explorar' : a;
    nb.hidden = a !== 'v';
    CR.$$('.dock a').forEach((el) => { if (el.dataset.d === DOCK[a]) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current'); });
    if (!idx) {
      page.innerHTML = '<div class="pad"><div class="skel" style="height:44px;margin-top:12px"></div><div class="skel" style="height:200px;margin-top:18px"></div><div class="skel" style="height:64px;margin-top:12px"></div></div>';
      try { idx = await CR.load(); } catch (e) {
        page.innerHTML = `<div class="err" role="alert"><h3>No se pudo abrir el archivo</h3><p>Falló la carga de los datos. Revisa la conexión y vuelve a intentarlo.</p><button class="pill" type="button" data-act="reload">${icon('refresh')} Reintentar</button></div>`;
        return;
      }
    }
    if (a === 'v') await renderVideo(b, r.q);
    else if (a === 'n') renderThread(b);
    else if (a === 'diario') renderLog();
    else if (a === 'guardados') renderSaved();
    else if (a === 'buscar') renderSearch(r.q.q || '');
    else if (a === 'estados') renderStates();
    else if (a === 'datos') renderAbout();
    else { renderExplore(a === 'f' ? {} : r.q); if (a === 'f') openFicha(b); }
    setStage();
    if (a !== 'v') window.scrollTo(0, scrolls.get(key) || 0);
  }

  /* ---------- explorar: secciones, filtros y ranking con tono (de la Nébula) ---------- */
  const SEC_TITLE = { altcoins: 'Altcoins mencionadas', macro: 'Macro en conversación', bolsa: 'Bolsa en conversación' };
  const SEC_THEMES = { altcoins: ['altcoins', 'btc-corto', 'liquidaciones'], macro: ['macro-alivio', 'fin-octubre'], bolsa: ['bolsa'] };
  function exState(q) {
    const st = Object.assign({ s: 'altcoins', tab: 'ranking', c: 'todos', p: 'todo', m: 'videos' }, store.get('ex', {}), q || {});
    store.set('ex', { s: st.s, tab: st.tab, c: st.c, p: st.p, m: st.m });
    return st;
  }
  const exHash = (st, patch) => CR.hash([], Object.assign({ s: st.s, tab: st.tab, c: st.c, p: st.p, m: st.m }, patch));
  function inWindow(v, st) {
    if (st.c !== 'todos' && v.ch !== st.c) return false;
    if (st.p === 'todo') return true;
    const days = st.p === '3d' ? 3 : 1;
    return (new Date(idx.period.to) - new Date(v.pub)) / 86400000 < days;
  }
  function rankRows(st) {
    return idx.topics.filter((t) => t.section === st.s).map((t) => {
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
  const symAv = (t) => `<span class="sym-av" aria-hidden="true">${esc((t.sym || t.name).slice(0, 4))}</span>`;
  const peak = (frags, pol) => frags.filter((f) => f.pol === pol).sort((a, b) => b.text.length - a.text.length)[0];
  function heroCard(r, st) {
    const up = peak(r.frags, 'alcista'), down = peak(r.frags, 'bajista');
    const pk = (f, k) => (f ? `<span class="pk pk-${k}">${icon(k === 'up' ? 'trend-up' : 'trend-down', 'i-s')}<span>«${esc(CR.clip(f.text, 110))}»</span><small>${esc(idx.videosById[f.v].channel.name)} · ${fmtT(f.t)}</small></span>` : '');
    return `<a class="hero" href="#/f/${r.t.id}">
      <span class="hero-top"><span class="hero-n">01</span>${symAv(r.t)}<span class="hero-name"><b>${esc(r.t.name)}</b><small>${esc(r.t.sym || L.section[r.t.section])} · ${CR.plural(r.cc, 'creador', 'creadores')}</small></span>${icon('arrow-up-right')}</span>
      <span class="hero-stats"><span><b>${r.vc}</b> ${r.vc === 1 ? 'vídeo' : 'vídeos'}</span><span><b>${r.n}</b> ${r.n === 1 ? 'mención' : 'menciones'}</span></span>
      <span class="hero-tone">${chip(r.net.pol)}<span class="ap-bar">${CR.sentBar(r.sent, { withNeutral: true })}</span><small><span class="t-up">${r.sent.alcista} alcistas</span> · <span class="t-down">${r.sent.bajista} bajistas</span> · ${r.sent.neutra} sin tono</small></span>
      ${up || down ? `<span class="hero-peaks">${pk(up, 'up')}${pk(down, 'down')}</span>` : ''}
    </a>`;
  }
  function rankList(rows, st) {
    if (!rows.length) return `<div class="empty"><h3>Sin menciones con estos filtros</h3><p>Prueba con todo el archivo o con ambos creadores.</p><a class="pill" href="${exHash(st, { c: 'todos', p: 'todo' })}">Quitar filtros</a></div>`;
    return `${heroCard(rows[0], st)}<ol class="rk-list">${rows.slice(1).map((r, i) => `<li class="rk-li">
      <a class="rk-row" href="#/f/${r.t.id}"><span class="rk-n">${String(i + 2).padStart(2, '0')}</span>${symAv(r.t)}
        <span class="rk-name"><b>${esc(r.t.name)}</b><small>${esc(r.t.sym || '')}${r.t.sym ? ' · ' : ''}${CR.plural(r.cc, 'creador', 'creadores')}</small><span class="rk-tone">${CR.icon(CR.TONE[r.net.pol].icon, 'rk-ti t-' + CR.TONE[r.net.pol].cls)}${CR.sentBar(r.sent)}<span class="mini-n"><span class="t-up">${r.sent.alcista}</span>/<span class="t-down">${r.sent.bajista}</span></span></span></span>
        <span class="rk-count"><b>${st.m === 'menciones' ? r.n : st.m === 'alza' ? r.sent.alcista : st.m === 'baja' ? r.sent.bajista : r.vc}</b><small>${st.m === 'menciones' ? 'menciones' : st.m === 'alza' ? 'alcistas' : st.m === 'baja' ? 'bajistas' : 'vídeos'}</small></span></a>
      <button class="rk-save" type="button" data-act="save-asset" data-id="${r.t.id}" aria-pressed="${saved.has(`a:${r.t.id}`)}" aria-label="Guardar ${esc(r.t.name)}">${icon(saved.has(`a:${r.t.id}`) ? 'bookmark-fill' : 'bookmark')}</button>
    </li>`).join('')}</ol>`;
  }
  function themeCard(th) {
    const net = CR.netSent(th.sent);
    return `<a class="g-card" href="#/n/${th.id}"><span class="g-tone">${chip(net.pol)}${CR.sentBar(th.sent)}</span><h3>${esc(th.title)}</h3><p>${esc(th.about)}</p>
      <span class="g-thumbs">${th.sources.slice(0, 5).map((x) => `<img src="${CR.thumb(x.v)}" alt="" loading="lazy">`).join('')}</span>
      <small>${CR.plural(th.videoCount, 'vídeo', 'vídeos')} · ${th.analyzedCount} con análisis · ${th.creators.map((c) => idx.channelsBySlug[c].name).join(' y ')}${th.contrasts.length ? ` · <span class="t-mix">${CR.plural(th.contrasts.length, 'cruce', 'cruces')}</span>` : ''}</small></a>`;
  }
  function insightsHtml(rows, st) {
    const cards = [];
    const sum = { alcista: 0, bajista: 0, mixta: 0, neutra: 0 };
    rows.forEach((r) => Object.keys(sum).forEach((k) => { sum[k] += r.sent[k]; }));
    const toned = sum.alcista + sum.bajista + sum.mixta;
    if (toned) {
      const net = CR.netSent(sum);
      cards.push(`<article class="g-card ins"><span class="g-tone">${chip(net.pol)}</span><h3>El tono de ${esc(L.section[st.s].toLowerCase())}</h3>
        <p>De ${toned} menciones con tono, <span class="t-up">${Math.round((sum.alcista / toned) * 100)} % suenan alcistas</span> y <span class="t-down">${Math.round((sum.bajista / toned) * 100)} % bajistas</span>. ${sum.neutra} más se nombran sin carga.</p>
        <span class="ap-bar">${CR.sentBar(sum)}</span><p class="ins-k">Observación: cuenta frases. Interpretación: el ambiente, no si aciertan.</p></article>`);
    }
    const scored = rows.filter((r) => r.sent.alcista + r.sent.bajista >= 2);
    const best = scored.slice().sort((a, b) => b.net.net - a.net.net || b.sent.alcista - a.sent.alcista)[0];
    const worst = scored.slice().sort((a, b) => a.net.net - b.net.net || b.sent.bajista - a.sent.bajista)[0];
    const pkLine = (r, pol) => { const f = peak(r.frags, pol); return f ? `<a class="ins-q q-${pol === 'alcista' ? 'up' : 'down'}" href="#/v/${f.v}?t=${Math.floor(f.t)}">«${esc(CR.clip(f.text, 140))}» <small>${esc(idx.videosById[f.v].channel.name)} · ${fmtT(f.t)}</small></a>` : ''; };
    if (best && best.net.net > 0) cards.push(`<article class="g-card ins"><span class="g-tone">${chip('alcista')}</span><h3>Lo más alcista: ${esc(best.t.name)}</h3><p>${best.sent.alcista} de sus ${best.n} menciones van en frases alcistas; ${best.sent.bajista} en bajistas.</p>${pkLine(best, 'alcista')}</article>`);
    if (worst && worst.net.net < 0 && worst !== best) cards.push(`<article class="g-card ins"><span class="g-tone">${chip('bajista')}</span><h3>Lo más bajista: ${esc(worst.t.name)}</h3><p>${worst.sent.bajista} de sus ${worst.n} menciones van en frases bajistas; ${worst.sent.alcista} en alcistas.</p>${pkLine(worst, 'bajista')}</article>`);
    const gaps = idx.videos.filter((v) => inWindow(v, st) && CR.titleGap(v));
    if (gaps.length) cards.push(`<article class="g-card ins"><span class="g-tone">${chip('mixta')}</span><h3>Títulos que no cuadran con el vídeo</h3><p>El título vende un tono y el discurso suena a otro. Es una insinuación, no un error.</p>
      ${gaps.map((v) => `<a class="ins-row" href="#/v/${v.id}"><b>${esc(v.cleanTitle)}</b><small>Título ${chip(v.tone.title.pol, { short: true })} · vídeo ${chip(v.tone.label, { short: true })}</small></a>`).join('')}</article>`);
    idx.contrasts.filter((p) => p.kind === 'cambio' && (st.s !== 'altcoins' || ['btc'].concat(rows.map((r) => r.t.id)).includes(p.asset))).forEach((p) => {
      const A = idx.claimsByKey[`${p.a.v}:${p.a.id}`], B = idx.claimsByKey[`${p.b.v}:${p.b.id}`];
      cards.push(`<article class="g-card ins"><span class="g-tone">${chip(A.pol, { short: true })}${icon('arrow-right', 'i-s')}${chip(B.pol, { short: true })}</span><h3>Cambio de postura sobre ${esc(CR.topicName(p.asset))}</h3>
        <p>${fmtDate(idx.videosById[p.a.v].pub)}: «${esc(CR.clip(A.quote || A.text, 90))}» → ${fmtDate(idx.videosById[p.b.v].pub)}: «${esc(CR.clip(B.quote || B.text, 90))}»</p>
        <p class="ins-k">Detectado por reglas: mismo activo y plazo, postura contraria. No decide quién acierta.</p><a class="pill" href="#/v/${p.b.v}?t=${Math.floor(B.t || 0)}&n=${B.id}">${icon('play')} Escuchar el cambio</a></article>`);
    });
    if (st.s === 'macro') cards.push(`<article class="g-card ins"><span class="g-tone">${chip('mixta')}</span><h3>La macro se lee al revés</h3><p>Si suben el dólar, los bonos, el MOVE o la inflación, el sistema lo marca bajista para el riesgo; si bajan, alcista. «Si el MOVE continúa bajando… es gasolina para Bitcoin».</p><p class="ins-k">Regla del sistema, visible en cada fragmento.</p></article>`);
    return cards.join('') || `<div class="empty"><h3>Sin insights con estos filtros</h3><p>Amplía el periodo o incluye a ambos creadores.</p></div>`;
  }
  function renderExplore(q, keep) {
    const st = exState(q);
    const rows = rankRows(st);
    const vids = idx.videos.filter((v) => inWindow(v, st));
    const y = keep ? window.scrollY : 0;
    const tabs = [['ranking', 'Ranking'], ['narrativas', 'Narrativas'], ['insights', 'Insights']];
    const modes = [['videos', 'Vídeos'], ['menciones', 'Menciones'], ['alza', 'Alcista'], ['baja', 'Bajista']];
    let body = '';
    if (st.tab === 'narrativas') {
      const mine = (SEC_THEMES[st.s] || []).map((id) => idx.themesById[id]).filter(Boolean);
      const rest = idx.themes.filter((th) => !mine.includes(th));
      body = `${mine.map(themeCard).join('')}<p class="sub-h">Otras narrativas del archivo</p>${rest.map(themeCard).join('')}`;
    } else if (st.tab === 'insights') {
      body = insightsHtml(rows, st);
    } else {
      body = `<div class="rk-head"><span>Ranking de menciones</span><div class="rk-mode" role="group" aria-label="Ordenar el ranking">${modes.map(([k, l]) => `<a href="${exHash(st, { m: k })}"${k === st.m ? ' aria-current="true"' : ''}>${l}</a>`).join('')}</div></div>
        <div id="rk">${rankList(rows, st)}</div>
        <p class="method">${icon('help', 'i-s')}<span>${esc(idx.method.mentions)} ${esc(idx.method.tone)}</span></p>`;
    }
    const first = vids.length ? vids[vids.length - 1].pub : idx.period.from;
    const last = vids.length ? vids[0].pub : idx.period.to;
    page.innerHTML = `
      <section class="ex-head">
        <div class="seg-pill" role="tablist" aria-label="Secciones">${['altcoins', 'macro', 'bolsa'].map((k) => `<a role="tab" href="${exHash(st, { s: k })}" aria-selected="${k === st.s}">${L.section[k]}</a>`).join('')}</div>
        <h1 class="ex-title">${SEC_TITLE[st.s]}</h1>
        <p class="ex-sub">${fmtDate(first)} – ${fmtDate(last)} · ${CR.plural(new Set(vids.map((v) => v.ch)).size, 'creador', 'creadores')} · ${CR.plural(vids.length, 'vídeo', 'vídeos')}</p>
        <div class="ex-filters">
          <label><span class="sr">Creador</span><select id="f-c">${[['todos', 'Todos los creadores'], ['nacho', 'Nacho IC'], ['kmanu', 'KManuS88']].map(([k, l]) => `<option value="${k}"${k === st.c ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
          <label><span class="sr">Periodo</span><select id="f-p">${[['todo', 'Archivo completo'], ['3d', 'Últimos 3 días'], ['1d', 'Último día']].map(([k, l]) => `<option value="${k}"${k === st.p ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
        </div>
        ${st.tab === 'ranking' ? `<label class="ex-search">${icon('search', 'i-s')}<span class="sr">Buscar activo</span><input id="f-q" type="search" placeholder="Buscar activo o símbolo…" autocomplete="off"></label>` : ''}
        <div class="tabs3" role="tablist" aria-label="Vistas">${tabs.map(([k, l]) => `<a role="tab" href="${exHash(st, { tab: k })}" aria-selected="${k === st.tab}">${l}</a>`).join('')}</div>
      </section>
      <section class="ex-body">${body}</section>`;
    const go = (patch) => CR.go(exHash(st, patch), null, { replace: true });
    document.getElementById('f-c').addEventListener('change', (e) => go({ c: e.target.value }));
    document.getElementById('f-p').addEventListener('change', (e) => go({ p: e.target.value }));
    const fq = document.getElementById('f-q');
    if (fq) fq.addEventListener('input', CR.debounce(() => {
      const n = fq.value.trim().toLowerCase();
      document.getElementById('rk').innerHTML = rankList(n ? rows.filter((r) => r.t.name.toLowerCase().includes(n) || (r.t.sym || '').toLowerCase().includes(n)) : rows, st);
    }, 150));
    if (keep) window.scrollTo(0, y);
  }

  /* ---------- ficha de menciones (hoja inferior) ---------- */
  function openFicha(id) {
    const t = idx.topicsById[id];
    if (!t) { CR.go('#/', null, { replace: true }); return; }
    const st = exState({});
    const r = rankRows(Object.assign({}, st, { s: t.section, m: 'videos' })).find((x) => x.t.id === id) || rankRows(Object.assign({}, st, { s: t.section, c: 'todos', p: 'todo' })).find((x) => x.t.id === id);
    if (!r) return;
    const claims = t.claims.map((k) => idx.claimsByKey[`${k.v}:${k.id}`]).filter(Boolean);
    const frags = r.frags.slice().sort((a, b) => idx.videosById[b.v].pub.localeCompare(idx.videosById[a.v].pub) || a.t - b.t);
    document.getElementById('ficha-body').innerHTML = `
      <span class="tag-sec">${esc(L.section[t.section])}</span>
      <h3 class="f-name">${esc(t.name)}</h3><p class="f-sym">${esc(t.sym || '')}</p>
      <div class="f-stats"><span><b>${r.vc}</b><small>vídeos únicos</small></span><span><b>${r.n}</b><small>menciones</small></span><span><b>${r.cc}</b><small>${r.cc === 1 ? 'creador' : 'creadores'}</small></span></div>
      <div class="f-tone">${chip(r.net.pol)}<span class="ap-bar">${CR.sentBar(r.sent, { withNeutral: true })}</span><p><span class="t-up">${icon('trend-up', 'i-s')}${r.sent.alcista} en frases alcistas</span> · <span class="t-down">${icon('trend-down', 'i-s')}${r.sent.bajista} bajistas</span> · <span class="t-mix">${r.sent.mixta} mixtas</span> · ${r.sent.neutra} sin tono</p></div>
      <button class="pill f-save" type="button" data-act="save-asset" data-id="${t.id}" aria-pressed="${saved.has(`a:${t.id}`)}">${icon(saved.has(`a:${t.id}`) ? 'bookmark-fill' : 'bookmark')} ${saved.has(`a:${t.id}`) ? 'En tu colección' : 'Guardar en mi colección'}</button>
      ${t.note ? `<p class="f-note"><b>Lectura del registro.</b> ${esc(CR.cap(t.note))}. Revisa el contexto de cada fragmento.</p>` : ''}
      ${claims.length ? `<p class="f-h">Lo que se analizó · ${claims.length}</p>${claims.map((c) => { const v = idx.videosById[c.v]; return `<div class="f-frag">${chip(c.pol, { str: c.polStr, insinua: c.insinua })}${c.quote ? `<p class="f-q">«${esc(c.quote)}»</p>` : ''}<p class="f-sys">${esc(c.text)}</p><p class="f-meta">${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${fmtT(c.t)}</p><div class="f-acts"><a class="pill" href="#/v/${v.id}?t=${Math.floor(c.t || 0)}&n=${c.id}">${icon('book')} Abrir en la bitácora</a></div></div>`; }).join('')}` : ''}
      <p class="f-h">${CR.plural(frags.length, 'fragmento', 'fragmentos')} con estos filtros</p>
      ${frags.map((f) => { const v = idx.videosById[f.v]; return `<div class="f-frag">${chip(f.pol, { short: true })}<p class="f-q">«${esc(f.text)}»</p><p class="f-meta">${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${fmtT(f.t)}${f.why && f.why.length ? ` · ${CR.toneWhy(f.why)}` : ''}</p><div class="f-acts"><a class="pill" href="#/v/${v.id}?t=${Math.floor(f.t)}&lens=transcripcion">${icon('play')} Ver fragmento</a><a class="textbtn" href="${CR.yt(v.id, f.t)}" target="_blank" rel="noopener">YouTube ${icon('external', 'i-s')}</a></div></div>`; }).join('')}`;
    ficha.hidden = false; scrim.hidden = false;
    document.getElementById('ficha-body').scrollTop = 0;
    ficha.querySelector('[data-act="ficha-close"]').focus({ preventScroll: true });
  }
  function closeFicha(silent) {
    if (ficha.hidden) return;
    ficha.hidden = true; scrim.hidden = true;
    if (!silent) CR.back('#/');
  }

  /* ---------- índice ---------- */
  function openIndex() {
    const here = (screen || '').split(':')[0];
    const items = [
      ['#/', 'Bitácora', `${idx.videos.length} vídeos, del más nuevo al más viejo`, idx.videos.length, ['log', 'v']],
      ['#/hilos', 'Hilos', 'Ideas que se repiten entre vídeos', idx.themes.length, ['hilos', 'h']],
      ['#/activos', 'Activos', 'Altcoins, macro y bolsa por día', idx.topics.length, ['activos', 'a']],
      ['#/marcadores', 'Marcadores', 'Lo que guardaste, con tus notas', saved.all().length, ['marcadores']],
    ];
    const n = { alcista: 0, bajista: 0, mixta: 0, neutra: 0 };
    idx.videos.forEach((v) => { n[v.tone.label] += 1; });
    document.getElementById('index-list').innerHTML = `<div class="ix-pulse">${CR.sentBar(n)}<p class="small"><span class="t-up">${n.alcista} alcistas</span> · <span class="t-down">${n.bajista} bajistas</span> · <span class="t-mix">${n.mixta} mixtos</span> · ${n.neutra} sin tono</p></div>` + items.map(([href, name, sub, n, keys]) => `
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
    if (f === 'nacho' || f === 'kmanu') return vs.filter((v) => v.ch === f);
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
  function entryHtml(v) {
    const a = v.analysis;
    const stages = a ? 4 : 1;
    const hint = a
      ? `${CR.plural(a.claims, 'afirmación', 'afirmaciones')} · ${CR.plural(a.assets.length, 'activo', 'activos')}`
      : (() => { const n = topicNames(v, 2); return n.length ? `Sin analizar · menciona ${esc(joinEs(n))}` : 'Sin analizar · transcripción lista'; })();
    return `<li class="entry${a ? ' is-analyzed' : ''}">
      <span class="entry-time">${hhmm(v.pub)}</span><span class="entry-dot" aria-hidden="true"></span>
      <a class="entry-card" href="#/v/${v.id}">
        <div class="entry-media">
          <div><p class="entry-who">${esc(v.channel.name)}${v.short ? ' <span class="tag-s">Short</span>' : ` <span>${CR.fmtDur(v.dur)}</span>`}</p><p class="entry-title">${esc(v.cleanTitle)}</p></div>
          <div class="entry-thumb"><img src="${CR.thumb(v.id)}" alt="" loading="lazy" decoding="async"></div>
        </div>
        ${pulseRow(v)}
        <div class="track"><span class="dots" aria-hidden="true">${[0, 1, 2, 3].map((i) => `<i class="${i < stages ? 'on' : ''}"></i>`).join('')}</span><span class="sr">Procesamiento: ${stages} de 4 etapas.</span><span>${hint}</span></div>
      </a>
    </li>`;
  }
  function archivePulse() {
    const n = { alcista: 0, bajista: 0, mixta: 0, neutra: 0 };
    idx.videos.forEach((v) => { n[v.tone.label] += 1; });
    const gaps = idx.videos.filter((v) => CR.titleGap(v)).length;
    return `<div class="archive-pulse pad"><div class="ap-bar">${CR.sentBar(n)}</div>
      <p class="small"><span class="t-up">${icon('trend-up', 'i-s')}${n.alcista} alcistas</span> · <span class="t-down">${icon('trend-down', 'i-s')}${n.bajista} bajistas</span> · <span class="t-mix">${icon('updown', 'i-s')}${n.mixta} mixtos</span> · ${n.neutra} sin tono${gaps ? ` · <button class="linkish" type="button" data-act="filter" data-f="contraste">${gaps} con título que no cuadra</button>` : ''}</p></div>`;
  }
  function renderLog() {
    const list = filterVideos(ui.filter);
    const days = [];
    list.forEach((v) => { const k = CR.dayKey(v.pub); if (!days.length || days[days.length - 1].k !== k) days.push({ k, iso: v.pub, items: [] }); days[days.length - 1].items.push(v); });
    const s = store.get('session', null);
    const sv = s && idx.videosById[s.v];
    const mark = sv ? `
      <a class="mark" href="#/v/${sv.id}?t=${Math.floor(s.t)}"><span class="mark-ribbon"></span><span class="mark-body">
        <span class="mark-k">Marcapáginas · ${fmtT(s.t)} de ${fmtT(sv.dur)}</span><span class="mark-t">${esc(sv.cleanTitle)}</span>
        <span class="pill pill-solid mark-go">${icon('play')} Seguir</span></span></a>` : `
      <a class="mark" href="#/v/${idx.analyzed[0].id}"><span class="mark-ribbon"></span><span class="mark-body">
        <span class="mark-k">Empieza por el último análisis</span><span class="mark-t">${esc(idx.analyzed[0].cleanTitle)}</span>
        <span class="pill pill-solid mark-go">${icon('book')} Abrir</span></span></a>`;
    page.innerHTML = `
      <div class="pad"><h1 class="title-xl">Diario</h1><p class="lede">Lo que publicaron ${idx.channels.map((c) => c.name).join(' y ')}, día a día, con su pulso: verde cuando el discurso empuja al alza, rojo cuando empuja a la baja.</p></div>
      ${archivePulse()}
      ${mark}
      <div class="pad" style="position:relative;display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:14px">
        <p class="small muted">Mostrando: <b style="color:var(--ink)">${FILTERS[ui.filter]}</b> · ${list.length}</p>
        <button class="filter-btn" type="button" data-act="filter-menu" aria-haspopup="menu" aria-expanded="false" aria-controls="filter-menu">${icon('filter')} Filtrar</button>
        <div class="menu" id="filter-menu" role="menu" hidden>
          ${Object.entries(FILTERS).map(([k, label]) => `<button type="button" role="menuitemradio" aria-checked="${ui.filter === k}" data-act="filter" data-f="${k}">${label}<span class="n">${filterVideos(k).length}</span></button>`).join('')}
        </div>
      </div>
      ${days.map((d) => `<section class="day"><h2 class="day-h">${esc(CR.dayLabel(d.iso))}<small>${CR.plural(d.items.length, 'vídeo', 'vídeos')} ${tally(d.items)}</small></h2><ol class="entries">${d.items.map(entryHtml).join('')}</ol></section>`).join('')
      || `<div class="empty"><h3>Nada con este filtro</h3><p>Prueba con todo el archivo.</p><button class="pill" type="button" data-act="filter" data-f="todo">Ver todo</button></div>`}`;
  }

  /* ---------- ficha del vídeo + cuaderno ---------- */
  async function renderVideo(id, q) {
    const v = idx.videosById[id];
    if (!v) { nb.hidden = true; page.innerHTML = `<div class="empty"><h3>Este vídeo no está en la bitácora</h3><a class="pill" href="#/">Ver la bitácora</a></div>`; return; }
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
    const a = v.analysis;
    const step = (ok, label, small) => `<li><span class="${ok ? 'ok' : 'wait'}">${icon(ok ? 'check' : 'clock')}</span><span>${label}</span><small>${small}</small></li>`;
    return `
      <section class="vinfo">
        <p class="vinfo-who">${esc(v.channel.name)} · ${fmtDate(v.pub, { weekday: true, time: true })}</p>
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
        <button class="pill" type="button" data-act="save-video">${icon(saved.has(`v:${v.id}`) ? 'bookmark-fill' : 'bookmark')} ${saved.has(`v:${v.id}`) ? 'Marcado' : 'Marcar'}</button>
        <a class="pill" href="${CR.yt(v.id)}" target="_blank" rel="noopener">${icon('external')} YouTube</a>
      </div>`;
  }
  function renderLenses() {
    const lenses = [['destilado', 'Destilado', 'flask'], ['transcripcion', 'Texto', 'text'], ['analisis', 'Análisis', 'book']];
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
    el.innerHTML = `<span class="pulse-k">Pulso</span>${CR.waveSvg(cur.video.tone.wave, { w: 300, h: 30, gap: 1, marks, playhead: (player ? player.time() : 0) / dur })}`;
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
      <p class="note-h">${chip(c.pol, { str: c.polStr, insinua: c.insinua })}<span class="note-k">${L.tipo[c.tipo]}</span><span class="sep">·</span><span>${L.verif[c.verif]}</span><span class="sep">·</span><span>convicción ${CR.nivel(c.conv).toLowerCase()}</span></p>
      <p class="note-text">${esc(c.text)}</p>
      ${c.pol !== 'neutra' && c.polWhy.length ? `<p class="note-why">Se lee ${esc(CR.TONE[c.pol].label.toLowerCase())} ${CR.toneWhy(c.polWhy)}${c.qPol !== 'neutra' && c.qPol !== c.pol ? `; la cita, en cambio, suena ${esc(CR.TONE[c.qPol].label.toLowerCase())}` : ''}.</p>` : ''}
      <div class="note-actions">
        ${c.t != null ? `<button class="textbtn" type="button" data-act="seek" data-t="${c.t}">${icon('play')} Escuchar ${fmtT(c.t)}</button>` : ''}
        <button class="textbtn" type="button" data-act="expand" data-c="${c.id}" aria-expanded="${open}">${open ? 'Cerrar' : 'Examinar'} ${icon(open ? 'chevron-up' : 'chevron-down')}</button>
        <button class="textbtn" type="button" data-act="save-note" data-c="${c.id}">${icon(saved.has(key) ? 'bookmark-fill' : 'bookmark')} ${saved.has(key) ? 'Marcada' : 'Marcar'}</button>
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
          <span class="heat-name" role="cell"><b>${i + 1}. ${esc(t.name)}${t.claims.length ? `<i class="an-dot" title="Tiene afirmaciones analizadas"></i><span class="sr"> (con afirmaciones analizadas)</span>` : ''}</b><small>${CR.sentBar(t.sent)}<span class="mini-n"><span class="t-up">${t.sent.alcista}</span>/<span class="t-down">${t.sent.bajista}</span></span></small></span>
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
        <div class="asset-tone">${chip(CR.netSent(t.sent).pol)}<div class="ap-bar">${CR.sentBar(t.sent, { withNeutral: true })}</div>
          <p class="small"><span class="t-up">${icon('trend-up', 'i-s')}${t.sent.alcista} en frases alcistas</span> · <span class="t-down">${icon('trend-down', 'i-s')}${t.sent.bajista} bajistas</span> · <span class="t-mix">${t.sent.mixta} mixtas</span> · ${t.sent.neutra} sin tono</p></div></div>
      ${claims.length ? `<div class="pad" style="margin-top:18px"><h2 class="title-l">Notas del análisis</h2>${claims.map((c) => { const v = idx.videosById[c.v]; return `<div style="margin-top:12px">${c.quote ? `<p class="small muted">${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${fmtT(c.t)}</p><blockquote style="margin:4px 0 0;font-family:var(--serif);font-size:16px">«${esc(c.quote)}»</blockquote>` : ''}<div class="note" ${kc(c.tipo)}><p class="note-h">${chip(c.pol, { str: c.polStr, insinua: c.insinua })}<span class="note-k">${L.tipo[c.tipo]}</span><span class="sep">·</span><span>${L.verif[c.verif]}</span></p><p class="note-text">${esc(c.text)}</p><div class="note-actions"><a class="textbtn" href="#/v/${v.id}?t=${Math.floor(c.t || 0)}&n=${c.id}">${icon('play')} Abrir en el cuaderno</a></div></div></div>`; }).join('')}</div>`
        : `<div class="nb-pending"><h3>Sin notas del análisis</h3><p>Se nombra en las transcripciones, pero los ${idx.analyzed.length} vídeos analizados no lo tratan como afirmación.</p></div>`}
      <div class="pad" style="margin-top:22px"><h2 class="title-l">Menciones, día a día</h2></div>
      ${byDay.map((d) => `<section class="day" id="d-${d.k}"><h3 class="day-h">${esc(CR.dayLabel(d.iso))}<small>${CR.plural(d.items.length, 'vídeo', 'vídeos')}</small></h3>
        <div class="thread">${d.items.map((m) => { const v = idx.videosById[m.v]; return `<div class="t-entry${v.analysis ? ' full' : ''}"><p class="meta">${esc(v.channel.name)} · ${CR.plural(m.n, 'mención', 'menciones')} ${CR.sentBar(m.sent || {})}</p><h4><a href="#/v/${v.id}">${esc(v.cleanTitle)}</a></h4>${m.frags.map((f) => `<div class="t-frag">${chip(f.pol, { short: true })}<blockquote class="q-${CR.TONE[f.pol].cls}">«${esc(f.text)}»</blockquote><a class="textbtn" href="#/v/${v.id}?t=${Math.floor(f.t)}">${icon('play')} ${fmtT(f.t)}</a></div>`).join('')}</div>`; }).join('')}</div></section>`).join('')}`;
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
      ${idx.themes.map((th) => `<a class="thread-card" href="#/n/${th.id}"><div class="tc-tone">${chip(CR.netSent(th.sent).pol)}${CR.sentBar(th.sent)}</div><h3>${esc(th.title)}</h3><p>${esc(th.about)}</p>${axisHtml(th)}<p class="small muted" style="margin-top:14px">${CR.plural(th.videoCount, 'vídeo', 'vídeos')} · ${th.analyzedCount} con análisis${th.contrasts.length ? ` · ${CR.plural(th.contrasts.length, 'cruce', 'cruces')} detectado${th.contrasts.length > 1 ? 's' : ''}` : ''}</p></a>`).join('')}
      <p class="pad small muted" style="margin-top:16px">${esc(idx.method.themes)}</p>`;
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
    if (!th) { page.innerHTML = `<div class="empty"><h3>Narrativa no encontrada</h3><a class="pill" href="#/?tab=narrativas">Ver narrativas</a></div>`; return; }
    const sources = th.sources.slice().sort((a, b) => idx.videosById[a.v].pub.localeCompare(idx.videosById[b.v].pub));
    const forksAfter = new Map();
    th.contrasts.forEach((i) => { const p = idx.contrasts[i]; forksAfter.set(p.b.v, (forksAfter.get(p.b.v) || []).concat(p)); });
    page.innerHTML = `
      <div class="pad"><a class="textbtn" href="#/?tab=narrativas">${icon('arrow-left')} Narrativas</a>
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
        <p class="small muted">${s.pol ? chip(s.pol, { short: true }) + ' ' : ''}${esc(s.kind)} · ${esc(s.sub || '')}</p>
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
      out.innerHTML = grp('Vídeos', r.videos.slice(0, 8).map((v) => `<a class="res" href="#/v/${v.id}"><p style="font-family:var(--serif)">${esc(v.cleanTitle)}</p><small>${chip(v.tone.label, { short: true })} ${esc(v.channel.name)} · ${fmtDate(v.pub)}</small></a>`))
        + grp('Notas del análisis', r.claims.slice(0, 10).map((c) => { const v = idx.videosById[c.v]; return `<a class="res" href="#/v/${v.id}?t=${Math.floor(c.t || 0)}&n=${c.id}"><p style="color:var(--pen)">${esc(c.text)}</p><small>${chip(c.pol, { short: true })} ${L.tipo[c.tipo]} · ${esc(v.channel.name)} · ${fmtT(c.t)}</small></a>`; }))
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
    const el = e.target.closest('[data-act]');
    if (!el) {
      const menu = document.getElementById('filter-menu');
      if (menu && !menu.hidden && !e.target.closest('#filter-menu')) menu.hidden = true;
      return;
    }
    const act = el.dataset.act;
    switch (act) {
      case 'index': if (idx) openIndex(); break;
      case 'pip-close': if (player) player.pause(); pipClosed = true; setStage(); break;
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

/* 3B · Alambique — feed vertical de vídeos; destilar abre una columna que gotea capa a capa. */
(() => {
  'use strict';
  const { esc, fmtT, fmtDate, icon, L } = CR;
  const APP = '3b';
  const store = CR.store(APP);
  const saved = CR.saved(APP);
  const feed = document.getElementById('feed');
  const layer = document.getElementById('layer');

  let idx = null;
  let player = null;
  let observer = null;
  let activeIndex = -1;
  let pendingStart = null;
  const docs = new Map();
  const ui = { tab: 'videos', sec: 'altcoins', openTheme: null };
  const STEPS = ['Frase escuchada', 'Afirmación aislada', 'Supuestos', 'Conexiones', 'Lectura crítica'];
  const noDot = (s) => String(s || '').replace(/[.\s]+$/, '');
  const activeVideo = () => (activeIndex >= 0 ? idx.videos[activeIndex] : null);

  /* ---------- feed ---------- */
  function cardHtml(v, i) {
    return `<article class="card${v.short ? ' is-short' : ''}" data-i="${i}" aria-label="${esc(v.channel.name)}: ${esc(v.cleanTitle)}">
      <div class="card-bg" style="background-image:url('${CR.thumb(v.id)}')" aria-hidden="true"></div>
      <div class="media" id="media-${i}">${posterHtml(v, i)}</div>
      <div class="card-info">
        <div class="drip" id="drip-${i}"><span class="drip-t">${v.analysis ? '' : '—'}</span><p>${v.analysis ? 'Reproduce el vídeo: aquí gotea lo que se afirma en cada momento.' : 'Sin análisis: verás lo que se escucha, sin interpretación.'}</p></div>
        <p class="who">${esc(v.channel.name)} · ${fmtDate(v.pub)} <span class="chip${v.analysis ? ' ok' : ''}">${v.analysis ? `${v.analysis.claims} afirmaciones` : 'sin analizar'}</span></p>
        <h2 class="title">${esc(v.cleanTitle)}</h2>
      </div>
      <div class="rail" role="group" aria-label="Acciones del vídeo">
        <button class="rail-btn main" type="button" data-act="distill" data-i="${i}"><span>${icon('flask')}</span>Destilar</button>
        <button class="rail-btn" type="button" data-act="save" data-i="${i}" aria-pressed="${saved.has(`v:${v.id}`)}"><span>${icon(saved.has(`v:${v.id}`) ? 'bookmark-fill' : 'bookmark')}</span>Guardar</button>
        <a class="rail-btn" href="#/lista/${v.id}"><span>${icon('list')}</span>Lista</a>
        <button class="rail-btn" type="button" data-act="share" data-i="${i}"><span>${icon('share')}</span>Compartir</button>
      </div>
      <div class="nav-btns"><button type="button" data-act="nav" data-d="-1" aria-label="Vídeo anterior"${i === 0 ? ' disabled' : ''}>${icon('chevron-up')}</button><button type="button" data-act="nav" data-d="1" aria-label="Vídeo siguiente"${i === idx.videos.length - 1 ? ' disabled' : ''}>${icon('chevron-down')}</button></div>
    </article>`;
  }
  const posterHtml = (v, i) => `<div class="poster"><img src="${CR.thumb(v.id, 'hq')}" alt="" loading="${i < 2 ? 'eager' : 'lazy'}" decoding="async"><div class="poster-play" aria-hidden="true"><span>${icon('play')}</span></div></div>`;
  function buildFeed() {
    feed.innerHTML = idx.videos.map(cardHtml).join('');
    observer = new IntersectionObserver((entries) => {
      entries.forEach((en) => { if (en.isIntersecting) activate(Number(en.target.dataset.i)); });
    }, { root: feed, threshold: 0.6 });
    CR.$$('.card', feed).forEach((c) => observer.observe(c));
  }
  async function activate(i) {
    if (i === activeIndex) return;
    if (player) {
      const prev = idx.videos[activeIndex];
      store.set('session', { v: prev.id, t: player.time() });
      player.destroy();
      document.getElementById(`media-${activeIndex}`).innerHTML = posterHtml(prev, activeIndex);
      player = null;
    }
    activeIndex = i;
    const v = idx.videos[i];
    document.getElementById('feed-pos').textContent = `${i + 1} / ${idx.videos.length}`;
    const host = document.getElementById(`media-${i}`);
    host.innerHTML = '<div class="crp-host" style="position:absolute;inset:0"></div>';
    player = new CR.Player(host.firstChild);
    const s = store.get('session', null);
    const start = pendingStart != null ? pendingStart : s && s.v === v.id ? s.t : 0;
    pendingStart = null;
    let last = 0;
    player.on('time', (t) => {
      if (Date.now() - last > 3000) { last = Date.now(); store.set('session', { v: v.id, t }); }
      updateDrip(i, t);
    });
    player.on('state', (st) => { if (st === 'needs-tap') CR.toast('Toca el vídeo para empezar a reproducir'); });
    player.load(v, { start });
    if (layer.hidden) history.replaceState(history.state, '', CR.hash(['f', v.id]));
    const doc = await getDoc(v.id);
    if (activeIndex === i && doc) updateDrip(i, start);
  }
  async function getDoc(id) {
    if (!docs.has(id)) { try { docs.set(id, await CR.loadVideo(id)); } catch (e) { return null; } }
    return docs.get(id);
  }
  function nowClaim(doc, t) {
    if (!doc || !doc.claims || !doc.claims.length) return null;
    const timed = doc.claims.filter((c) => c.t != null).sort((a, b) => a.t - b.t);
    const before = timed.filter((c) => c.t <= t + 1).pop();
    if (before && t - before.t < 60) return before;
    return timed.find((c) => c.t > t) || before || null;
  }
  function updateDrip(i, t) {
    const v = idx.videos[i];
    const doc = docs.get(v.id);
    const el = document.getElementById(`drip-${i}`);
    if (!el || !doc) return;
    const c = nowClaim(doc, t);
    if (c) {
      const key = `${c.id}`;
      if (el.dataset.k === key) return;
      el.dataset.k = key;
      el.innerHTML = `<span class="drip-t">${fmtT(c.t)}</span><p>${c.quote ? `<span class="quote">${esc(c.quote)}</span>` : esc(c.text)}</p>`;
    } else {
      const seg = doc.segments[CR.segAt(doc.segments, t)];
      const key = `s${seg ? seg.start : 0}`;
      if (el.dataset.k === key) return;
      el.dataset.k = key;
      el.innerHTML = `<span class="drip-t">${fmtT(seg ? seg.start : t)}</span><p><span class="quote">${esc(seg ? seg.text : '')}</span></p>`;
    }
  }
  function scrollToVideo(id, t) {
    const i = idx.videos.findIndex((v) => v.id === id);
    if (i < 0) return;
    if (i === activeIndex) {
      if (t != null && player) { player.seek(t, { play: false }); updateDrip(i, t); }
      return;
    }
    pendingStart = t;
    feed.querySelector(`.card[data-i="${i}"]`).scrollIntoView({ block: 'start' });
  }

  /* ---------- rutas ---------- */
  async function route(r) {
    if (!idx) {
      feed.innerHTML = '<div class="skel" style="height:40vh;margin:30vh 18px 0"></div>';
      try { idx = await CR.load(); } catch (e) {
        feed.innerHTML = `<div class="err" role="alert"><h3>No se pudo encender el alambique</h3><p>Fallaron los datos. Vuelve a intentarlo.</p><button class="btn" type="button" data-act="reload" style="margin-top:12px">${icon('refresh')} Reintentar</button></div>`;
        return;
      }
      const s = store.get('session', null);
      const startId = r.parts[0] === 'f' && idx.videosById[r.parts[1]] ? r.parts[1] : s && idx.videosById[s.v] ? s.v : idx.analyzed[0].id;
      buildFeed();
      const i = idx.videos.findIndex((v) => v.id === startId);
      pendingStart = r.q.t != null ? Number(r.q.t) : null;
      feed.querySelector(`.card[data-i="${i}"]`).scrollIntoView({ block: 'start' });
      activate(i);
    }
    const [a, b, c] = r.parts;
    if (!a || a === 'f') {
      layer.hidden = true;
      layer.innerHTML = '';
      if (b && idx.videosById[b]) scrollToVideo(b, r.q.t != null ? Number(r.q.t) : null);
      feed.focus({ preventScroll: true });
      return;
    }
    if (player) player.pause();
    layer.hidden = false;
    layer.scrollTop = 0;
    if (a === 'd') await renderStill(b, c, r.q);
    else if (a === 'o') renderOrbit(b, r.q);
    else if (a === 'h') renderReading(b);
    else if (a === 'explorar') renderExplore(r.q);
    else if (a === 'lista') await renderList(b);
    else { layer.hidden = true; }
  }
  const topBar = (backLabel, crumb) => `<div class="l-top"><button class="back-pill" type="button" data-act="back">${icon('arrow-left')} ${backLabel}</button><p class="crumb">${crumb}</p></div>`;
  const backToVideo = () => { const v = activeVideo(); return `Vídeo <span class="num">${fmtT(player ? player.time() : 0)}</span>`; };

  /* ---------- alambique: la columna de destilación ---------- */
  function connections(doc, c) {
    const a = doc.analysis;
    const chains = a.cadena_narrativa.filter((ch) => ch.afirmacion_ids.includes(c.id));
    const scens = a.escenarios.filter((s) => s.afirmacion_ids.includes(c.id));
    const themes = idx.themes.filter((th) => th.sources.some((s) => s.v === doc.id && s.claims.includes(c.id)));
    const assets = c.assets.map((x) => idx.topicsById[x]).filter(Boolean);
    return { chains, scens, themes, assets };
  }
  async function renderStill(vid, cid, q) {
    const v = idx.videosById[vid];
    if (!v) { layer.hidden = true; return; }
    layer.innerHTML = `${topBar(backToVideo(), 'Vídeo › <b>Afirmación</b>')}<div class="l-body"><div class="skel" style="height:160px"></div></div>`;
    const doc = await getDoc(vid);
    if (!doc) { layer.querySelector('.l-body').innerHTML = `<div class="err" style="margin:0" role="alert"><h3>No se pudo destilar</h3><p>Falló la carga del análisis. Vuelve al vídeo e inténtalo de nuevo.</p></div>`; return; }
    const c = cid !== 'frase' && doc.analysis ? CR.claim(doc, cid) : null;
    if (!c) {
      const t = q.t != null ? Number(q.t) : 0;
      const seg = doc.segments[CR.segAt(doc.segments, t)];
      layer.innerHTML = `${topBar(backToVideo(), 'Vídeo › <b>Frase</b>')}<div class="l-body">
        <p class="sec-k">${icon('flask', 'i-s')} ${STEPS[0]}</p>
        <div class="flask"><p class="quote">${esc(seg ? seg.text : '')}</p><div class="flask-foot"><span>${esc(v.channel.name)} · <span class="num">${fmtT(seg ? seg.start : t)}</span></span><button class="btn" type="button" data-act="listen" data-v="${v.id}" data-t="${seg ? seg.start : t}" style="min-height:38px">${icon('play')} Escuchar</button></div></div>
        <div class="drop" aria-hidden="true"></div>
        <div class="empty" style="margin-top:0">Este vídeo no está analizado: la destilación se detiene en la frase. El sistema no crea conexiones que no ha identificado.</div>
        <div class="row-btns"><a class="btn" href="#/lista/${v.id}">${icon('list')} Leer en lista</a><button class="btn btn-copper" type="button" data-act="back">${icon('play')} Volver al vídeo</button></div></div>`;
      return;
    }
    const con = connections(doc, c);
    const pend = doc.analysis.verificaciones_pendientes.find((p) => p.afirmacion_ids.includes(c.id));
    const supuestos = con.chains.filter((ch) => ch.supuesto).map((ch) => ({ k: `En el argumento · ${L.vinculo[ch.vinculo].toLowerCase()}`, t: ch.supuesto }))
      .concat(con.scens.flatMap((s) => s.supuestos.slice(0, 2).map((u) => ({ k: `Escenario: ${s.nombre}`, t: u }))));
    const key = `c:${v.id}:${c.id}`;
    const link = (k, label, ic, text, ok) => `<button class="link-chip${ok ? '' : ' none'}" type="button" data-act="branch" data-k="${k}" aria-expanded="false"><b>${icon(ic)}${label}</b><span>${esc(text)}</span></button>`;
    layer.innerHTML = `${topBar(backToVideo(), 'Vídeo › <b>Afirmación</b>')}
      <div class="l-body"><div class="still">
        <nav class="still-rail" aria-label="Capas de la destilación">${STEPS.map((s, i) => `${i ? '<i aria-hidden="true"></i>' : ''}<button type="button" data-act="goto" data-s="${i + 1}" aria-label="${s}">${i + 1}</button>`).join('')}</nav>
        <div>
          <section class="stage-sec" id="s1"><p class="sec-k">${icon('wave', 'i-s')} ${STEPS[0]}</p>
            <div class="flask"><p class="quote">${esc(c.literal ? c.literal.cita : c.text)}</p>
              <div class="flask-foot"><span>${c.literal && c.literal.origen === 'titulo' ? 'Título del vídeo' : esc(v.channel.name)} · <span class="num">${fmtT(c.t)}</span></span>${c.t != null ? `<button class="btn" type="button" data-act="listen" data-v="${v.id}" data-t="${c.t}" style="min-height:38px">${icon('play')} Escuchar</button>` : ''}</div></div></section>
          <div class="drop" aria-hidden="true"></div>
          <section class="stage-sec" id="s2"><p class="sec-k">${icon('flask', 'i-s')} ${STEPS[1]}</p>
            <div class="distilled"><p>${esc(c.text)}</p><small>${L.tipo[c.tipo]} · ${L.verif[c.verif]} · convicción del creador ${CR.nivel(c.conv).toLowerCase()} · extracción con confianza ${CR.nivel(c.conf).toLowerCase()}</small></div></section>
          <div class="drop" aria-hidden="true"></div>
          <section class="stage-sec" id="s3"><p class="sec-k">${icon('branch', 'i-s')} ${STEPS[2]}</p>
            ${supuestos.length ? `<ul class="assume">${supuestos.slice(0, 4).map((s) => `<li><b>${esc(s.k)}</b>${esc(s.t)}</li>`).join('')}</ul>` : '<div class="empty" style="margin-top:8px">El análisis no explicita supuestos para esta frase.</div>'}</section>
          <div class="drop" aria-hidden="true"></div>
          <section class="stage-sec" id="s4"><p class="sec-k">${icon('target', 'i-s')} ${STEPS[3]}</p>
            <div class="links">
              ${link('a', 'Activo', 'coin', con.assets.length ? con.assets.map((x) => x.name).join(', ') : 'No identificado', con.assets.length)}
              ${link('s', 'Supuesto', 'branch', supuestos[0] ? supuestos[0].t : 'No explícito', supuestos.length)}
              ${link('e', 'Evidencia citada', 'quote', `${CR.plural(c.evidences.length, 'fragmento', 'fragmentos')} · sin fuente externa`, true)}
              ${link('n', 'Narrativa', 'route', con.themes.length ? con.themes[0].short : 'Ninguna compartida', con.themes.length)}
            </div>
            <div id="branch"></div></section>
          <div class="drop" aria-hidden="true"></div>
          <section class="stage-sec" id="s5"><p class="sec-k">${icon('scale', 'i-s')} ${STEPS[4]}</p>
            <div class="critical"><p class="q">${esc(pend ? pend.pregunta : `¿Qué haría falta para comprobar que «${CR.clip(noDot(c.text), 90)}»?`)}</p>
              <p class="ev"><b>Evidencia en este fragmento:</b> ${esc(c.justificacion)}</p>
              <p class="ext">${icon('alert', 'i-s')}<span>Ninguna fuente externa consultada. Que el vídeo no lo pruebe no lo vuelve falso.</span></p></div>
            <div class="row-btns"><button class="btn" type="button" data-act="save-claim" data-v="${v.id}" data-c="${c.id}">${icon(saved.has(key) ? 'bookmark-fill' : 'bookmark')} ${saved.has(key) ? 'Guardado' : 'Guardar'}</button><button class="btn" type="button" data-act="share-claim" data-v="${v.id}" data-c="${c.id}">${icon('share')} Compartir</button></div>
            <div class="row-btns" style="margin-top:8px"><button class="btn btn-copper" type="button" data-act="listen" data-v="${v.id}" data-t="${c.t || 0}">${icon('play')} Volver al vídeo en ${fmtT(c.t)}</button></div></section>
        </div></div></div>`;
    layer._ctx = { v, c, con, supuestos, doc };
    const rail = CR.$$('.still-rail button', layer);
    const links = CR.$$('.still-rail i', layer);
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (!en.isIntersecting) return;
        const n = Number(en.target.id.slice(1));
        rail.forEach((b, k) => b.classList.toggle('on', k < n));
        links.forEach((l, k) => l.classList.toggle('on', k < n - 1));
      });
    }, { root: layer, rootMargin: '-40% 0px -50% 0px' });
    CR.$$('.stage-sec', layer).forEach((s) => io.observe(s));
    rail[0].classList.add('on');
  }
  function openBranch(k, btn) {
    const { v, c, con, supuestos } = layer._ctx;
    const was = btn.getAttribute('aria-expanded') === 'true';
    CR.$$('.link-chip', layer).forEach((b) => b.setAttribute('aria-expanded', 'false'));
    const box = document.getElementById('branch');
    if (was) { box.innerHTML = ''; return; }
    btn.setAttribute('aria-expanded', 'true');
    let html = '';
    if (k === 'a') {
      html = con.assets.length ? `<h4>Activo</h4>${con.assets.map((t) => `<p><b>${esc(t.name)}</b> · ${CR.plural(t.vc, 'vídeo', 'vídeos')} · ${CR.plural(t.n, 'mención', 'menciones')}</p>`).join('')}${c.postura ? `<p>Postura extraída: ${esc(c.postura)}</p>` : ''}<div class="acts"><a class="btn btn-copper" href="#/o/${con.assets[0].id}?from=${v.id}">${icon('orbit')} Órbita de vídeos</a></div>`
        : '<h4>Activo</h4><p>El análisis no vinculó un activo concreto a esta frase.</p>';
    } else if (k === 's') {
      html = supuestos.length ? `<h4>Supuestos que necesita</h4>${supuestos.map((s) => `<p><b>${esc(s.k)}:</b> ${esc(s.t)}</p>`).join('')}` : '<h4>Supuestos</h4><p>No explícitos en el análisis.</p>';
    } else if (k === 'e') {
      html = `<h4>Evidencia citada · ${L.verif[c.verif].toLowerCase()}</h4>${c.evidences.map((e) => `<span class="quote">${esc(e.cita || e.observacion || '')}</span><p>${e.origen === 'titulo' ? 'Título del vídeo' : `${L.origen[e.origen]} · ${fmtT(e.inicio_s)}`}${e.observacion && e.cita ? ` · ${esc(e.observacion)}` : ''}</p>`).join('')}<p style="color:var(--sky)">Fuente externa: ninguna consultada.</p>`;
    } else if (k === 'n') {
      if (con.themes.length) {
        const th = con.themes[0];
        const other = th.sources.find((s) => s.v !== v.id);
        const ov = other && idx.videosById[other.v];
        const ot = other ? (other.claims.length ? (idx.claimsByKey[`${other.v}:${other.claims[0]}`] || {}).t : other.frags[0] ? other.frags[0].t : 0) : 0;
        html = `<h4>Narrativa</h4><p>${esc(th.title)}</p><p>${CR.plural(th.videoCount, 'vídeo la trata', 'vídeos la tratan')}; repetirla no la prueba.</p>${ov ? `<div class="acts"><a class="btn btn-copper" href="#/f/${ov.id}?t=${Math.floor(ot || 0)}">${icon('arrow-right')} Saltar a ${esc(ov.channel.name)}, ${fmtDate(ov.pub)}</a></div>` : ''}`;
      } else html = '<h4>Narrativa</h4><p>Esta frase no forma parte de ninguna narrativa compartida entre vídeos.</p>';
    }
    box.innerHTML = `<div class="branch">${html}</div>`;
  }

  /* ---------- órbita como carrusel ---------- */
  function renderOrbit(aid, q) {
    const t = idx.topicsById[aid];
    if (!t) { layer.hidden = true; return; }
    const sort = q.orden || 'fecha';
    let items = t.videos.map((m) => ({ v: idx.videosById[m.v], m, c: t.claims.map((k) => idx.claimsByKey[`${k.v}:${k.id}`]).find((x) => x && x.v === m.v) }));
    if (sort === 'fecha') items.sort((a, b) => a.v.pub.localeCompare(b.v.pub));
    if (sort === 'argumento') items.sort((a, b) => (b.c ? 1 : 0) - (a.c ? 1 : 0) || b.m.n - a.m.n);
    if (sort === 'creador') items.sort((a, b) => a.v.ch.localeCompare(b.v.ch) || a.v.pub.localeCompare(b.v.pub));
    const from = q.from || (activeVideo() || {}).id;
    layer.innerHTML = `${topBar(backToVideo(), 'Vídeo › Afirmación › <b>Activo</b>')}<div class="l-body">
      <h1 class="l-h">Órbita de ${esc(t.name)}</h1><p class="l-sub">${CR.plural(t.vc, 'vídeo', 'vídeos')} lo nombran. Desliza, elige un fragmento y llévalo al centro.</p>
      <div class="seg" role="group" aria-label="Ordenar">${[['fecha', 'Fecha'], ['argumento', 'Argumento'], ['creador', 'Creador']].map(([k, l]) => `<a href="#/o/${aid}?from=${from || ''}&orden=${k}" aria-pressed="${k === sort}">${l}</a>`).join('')}</div>
      <div class="coverflow" id="cover" data-scroll-x>${items.map((x, i) => { const tt = x.c ? x.c.t : x.m.frags[0] ? x.m.frags[0].t : 0; return `<article class="frag" data-i="${i}"><img src="${CR.thumb(x.v.id)}" alt="" loading="lazy"><p class="meta"><span>${esc(x.v.channel.name)} · ${fmtDate(x.v.pub)}</span><span class="num">${fmtT(tt)}</span></p><span class="quote">${esc(x.c && x.c.quote ? x.c.quote : x.m.frags[0] ? x.m.frags[0].text : '')}</span>${x.c ? `<p class="mint">${esc(x.c.text)}</p>` : '<p class="mint" style="color:var(--muted)">Mención literal; sin análisis.</p>'}<a class="btn btn-copper" href="#/f/${x.v.id}?t=${Math.floor(tt || 0)}">${icon('target')} Llevar al centro</a></article>`; }).join('')}</div>
      <div class="dots" id="cover-dots" aria-hidden="true">${items.map((_, i) => `<i${i === 0 ? ' class="on"' : ''}></i>`).join('')}</div>
      <div class="row-btns"><a class="btn" href="#/h/${aid}">${icon('book')} Hoja de lectura</a></div></div>`;
    const cover = document.getElementById('cover');
    const mark = () => {
      const mid = cover.getBoundingClientRect().left + cover.clientWidth / 2;
      let best = 0, dist = Infinity;
      CR.$$('.frag', cover).forEach((f, i) => { const r = f.getBoundingClientRect(); const d = Math.abs(r.left + r.width / 2 - mid); if (d < dist) { dist = d; best = i; } });
      CR.$$('.frag', cover).forEach((f, i) => f.classList.toggle('is-center', i === best));
      CR.$$('#cover-dots i', layer).forEach((d, i) => d.classList.toggle('on', i === best));
    };
    cover.addEventListener('scroll', CR.debounce(mark, 60), { passive: true });
    const start = items.findIndex((x) => x.v.id === from);
    if (start > 0) cover.querySelector(`.frag[data-i="${start}"]`).scrollIntoView({ inline: 'center', block: 'nearest' });
    requestAnimationFrame(mark);
  }
  function renderReading(aid) {
    const t = idx.topicsById[aid];
    if (!t) { layer.hidden = true; return; }
    const claims = t.claims.map((k) => idx.claimsByKey[`${k.v}:${k.id}`]).filter(Boolean);
    const changes = idx.contrasts.filter((p) => p.asset === aid);
    layer.innerHTML = `${topBar('Órbita', `Hoja de lectura · <b>${esc(t.name)}</b>`)}<div class="l-body reading">
      <h1 class="l-h">${esc(t.name)}</h1><p class="l-sub">${L.section[t.section]} · ${CR.plural(t.vc, 'vídeo', 'vídeos')} · ${CR.plural(t.n, 'mención', 'menciones')} · ${CR.plural(claims.length, 'afirmación analizada', 'afirmaciones analizadas')}.${t.note ? ` Ojo: ${esc(t.note)}.` : ''}</p>
      <h2>Lo que se analizó</h2>${claims.map((c) => { const v = idx.videosById[c.v]; return `<div class="r">${c.quote ? `<span class="quote">${esc(c.quote)}</span>` : ''}<p>${esc(c.text)}</p><small>${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${fmtT(c.t)} · ${L.tipo[c.tipo]} · ${L.verif[c.verif]}</small></div>`; }).join('') || '<p class="l-sub">Ninguno de los vídeos analizados lo trata como afirmación.</p>'}
      <h2>Cambios del discurso</h2>${changes.map((p) => { const A = idx.claimsByKey[`${p.a.v}:${p.a.id}`], B = idx.claimsByKey[`${p.b.v}:${p.b.id}`]; return `<div class="r"><p>${p.kind === 'cambio' ? 'Cambio de postura' : 'Idea repetida'} · ${L.hz[p.hz].toLowerCase()}: «${esc(noDot(A.postura))}» → «${esc(noDot(B.postura))}»</p><small>${fmtDate(idx.videosById[p.a.v].pub)} → ${fmtDate(idx.videosById[p.b.v].pub)} · detectado por reglas</small></div>`; }).join('') || '<p class="l-sub">No se detectaron cambios entre vídeos analizados.</p>'}
      <h2>Menciones en todos los vídeos</h2>${t.videos.map((m) => { const v = idx.videosById[m.v]; return `<div class="r"><span class="quote">${esc(m.frags[0] ? m.frags[0].text : '')}</span><small>${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${CR.plural(m.n, 'mención', 'menciones')}</small></div>`; }).join('')}
      <p class="l-sub" style="margin-top:16px;font-size:13px">${esc(idx.method.mentions)} ${esc(idx.method.external)}</p></div>`;
  }

  /* ---------- explorar y lista ---------- */
  function renderExplore(q) {
    const tab = q.tab || ui.tab;
    ui.tab = tab;
    const tabs = [['videos', 'Vídeos'], ['narrativas', 'Narrativas'], ['activos', 'Activos'], ['guardados', 'Guardados'], ['estados', 'Estados']];
    let body = '';
    if (tab === 'videos') body = `<div class="grid">${idx.videos.map((v) => `<a href="#/f/${v.id}"><img src="${CR.thumb(v.id)}" alt="" loading="lazy"><b>${esc(v.cleanTitle)}</b><small>${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${v.analysis ? 'analizado' : 'transcripción'}</small></a>`).join('')}</div>`;
    else if (tab === 'narrativas') body = `<div class="rows" style="margin-top:8px">${idx.themes.map((th) => `<button type="button" data-act="theme" data-th="${th.id}" aria-expanded="${ui.openTheme === th.id}"><span><b>${esc(th.title)}</b><small>${CR.plural(th.videoCount, 'vídeo', 'vídeos')} · ${th.analyzedCount} analizados</small></span>${icon(ui.openTheme === th.id ? 'chevron-up' : 'chevron-down')}</button>${ui.openTheme === th.id ? th.sources.map((s) => { const v = idx.videosById[s.v]; const t = s.claims.length ? (idx.claimsByKey[`${s.v}:${s.claims[0]}`] || {}).t : s.frags[0] ? s.frags[0].t : 0; return `<a href="#/f/${v.id}?t=${Math.floor(t || 0)}" style="padding-left:14px"><span><b style="font-size:15px">${esc(v.cleanTitle)}</b><small>${esc(v.channel.name)} · ${fmtDate(v.pub)} · desde ${fmtT(t)}</small></span>${icon('play')}</a>`; }).join('') : ''}`).join('')}</div>`;
    else if (tab === 'activos') {
      const s = q.s || ui.sec;
      ui.sec = s;
      const rows = idx.topics.filter((t) => t.section === s).sort((a, b) => b.vc - a.vc || b.n - a.n);
      body = `<div class="seg" role="group" aria-label="Sección">${['altcoins', 'macro', 'bolsa'].map((k) => `<a href="#/explorar?tab=activos&s=${k}" aria-pressed="${k === s}">${L.section[k]}</a>`).join('')}</div>
        <div class="rows" style="margin-top:8px">${s === 'altcoins' ? `<a href="#/o/btc"><span><b>Bitcoin</b><small>Fuera del ranking · ${idx.topicsById.btc.vc} vídeos</small></span>${icon('orbit')}</a>` : ''}${rows.map((t, i) => `<a href="#/o/${t.id}"><span><b>${i + 1}. ${esc(t.name)}</b><small>${CR.plural(t.vc, 'vídeo', 'vídeos')} · ${CR.plural(t.n, 'mención', 'menciones')}${t.claims.length ? ` · ${t.claims.length} analizada${t.claims.length > 1 ? 's' : ''}` : ''}</small></span><span class="n">${t.vc}</span></a>`).join('')}</div>`;
    } else if (tab === 'guardados') {
      const list = saved.all();
      body = list.length ? `<div class="rows" style="margin-top:8px">${list.map((x) => `<a href="${esc(x.href)}"><span><b style="font-size:15px">${esc(x.title)}</b><small>${esc(x.sub)}</small></span>${icon('flask')}</a>`).join('')}</div>` : '<div class="empty">Nada guardado todavía. En una destilación, pulsa «Guardar»; en el feed, el marcador guarda el vídeo.</div>';
    } else {
      body = CR.STATES.map((s) => `<div class="lin"><p class="meta"><span>${esc(s.title)}</span><span>${s.real ? 'Real' : 'Ejemplo'}</span></p><p style="color:var(--text-2)">${esc(s.body)}</p><div class="row-btns"><button class="btn" type="button" data-act="demo">${esc(s.action)}</button></div></div>`).join('');
    }
    layer.innerHTML = `${topBar(backToVideo(), '<b>Explorar</b>')}<div class="l-body"><h1 class="l-h">Explorar</h1><p class="l-sub">Todo el archivo fuera del vídeo: vídeos, narrativas, activos y lo que guardaste.</p>
      <div class="tabs" data-scroll-x>${tabs.map(([k, l]) => `<a href="#/explorar?tab=${k}"${k === tab ? ' aria-current="page"' : ''}>${l}</a>`).join('')}</div>${body}
      <p class="l-sub" style="margin-top:20px;font-size:13px"><a href="../index.html" style="text-decoration:underline">Volver al tablero de propuestas</a></p></div>`;
  }
  async function renderList(vid) {
    const v = idx.videosById[vid];
    if (!v) { layer.hidden = true; return; }
    layer.innerHTML = `${topBar(backToVideo(), 'Vídeo › <b>Lista</b>')}<div class="l-body"><div class="skel" style="height:120px"></div></div>`;
    const doc = await getDoc(vid);
    if (!doc) return;
    let body = '';
    if (!doc.analysis) {
      body = CR.blocks(doc.segments, 40).map((b) => `<div class="lin"><p class="meta"><span class="num">${fmtT(b.start)}</span><span>transcripción</span></p><span class="quote">${esc(b.text)}</span><div class="row-btns"><button class="btn" type="button" data-act="listen" data-v="${v.id}" data-t="${b.start}">${icon('play')} Escuchar</button></div></div>`).join('');
    } else {
      body = doc.claims.map((x) => CR.claim(doc, x.id)).filter(Boolean).sort((a, b) => (a.t == null ? -1 : a.t) - (b.t == null ? -1 : b.t)).map((c) => {
        const con = connections(doc, c);
        const sup = con.chains.find((ch) => ch.supuesto);
        return `<article class="lin"><p class="meta"><span><span class="num">${c.t != null ? fmtT(c.t) : 'título'}</span> · ${L.tipo[c.tipo]}</span><span>${L.verif[c.verif]}</span></p>${c.literal ? `<span class="quote">${esc(c.literal.cita)}</span>` : ''}<p>${esc(c.text)}</p>
          <dl><dt>Activo</dt><dd>${esc(con.assets.map((x) => x.name).join(', ') || 'No identificado')}</dd><dt>Supuesto</dt><dd>${esc(sup ? sup.supuesto : 'No explícito')}</dd><dt>Evidencia</dt><dd>${CR.plural(c.evidences.length, 'fragmento', 'fragmentos')} · sin fuente externa</dd><dt>Narrativa</dt><dd>${esc(con.themes[0] ? con.themes[0].short : 'Ninguna compartida')}</dd></dl>
          <div class="row-btns">${c.t != null ? `<button class="btn" type="button" data-act="listen" data-v="${v.id}" data-t="${c.t}">${icon('play')} Escuchar</button>` : ''}<a class="btn" href="#/d/${v.id}/${c.id}">${icon('flask')} Destilar</a></div></article>`;
      }).join('');
    }
    layer.innerHTML = `${topBar(backToVideo(), 'Vídeo › <b>Lista</b>')}<div class="l-body"><h1 class="l-h" style="font-size:22px">${esc(v.cleanTitle)}</h1><p class="l-sub">${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${doc.analysis ? `${doc.claims.length} afirmaciones en orden, con sus conexiones en texto` : 'sin análisis: transcripción por tramos'}</p>${body}</div>`;
  }

  /* ---------- acciones ---------- */
  document.addEventListener('click', async (e) => {
    const el = e.target.closest('[data-act]');
    if (!el) return;
    const v = el.dataset.i != null ? idx.videos[Number(el.dataset.i)] : null;
    switch (el.dataset.act) {
      case 'distill': {
        if (player) player.pause();
        const t = player ? player.time() : 0;
        const doc = await getDoc(v.id);
        const c = nowClaim(doc, t);
        CR.go(c ? ['d', v.id, c.id] : ['d', v.id, 'frase'], c ? null : { t: Math.floor(t) });
        break;
      }
      case 'save': {
        const on = saved.toggle({ key: `v:${v.id}`, sub: `${v.channel.name} · ${fmtDate(v.pub)}`, title: v.cleanTitle, href: `#/f/${v.id}` });
        el.setAttribute('aria-pressed', String(on));
        el.firstElementChild.innerHTML = icon(on ? 'bookmark-fill' : 'bookmark');
        CR.toast(on ? 'Vídeo guardado' : 'Quitado de guardados');
        break;
      }
      case 'share': {
        const r = await CR.share({ title: v.cleanTitle, text: v.cleanTitle, url: CR.linkTo(CR.hash(['f', v.id], { t: Math.floor(player ? player.time() : 0) })) });
        if (r === 'copied') CR.toast('Enlace copiado con el segundo actual');
        break;
      }
      case 'nav': {
        const next = activeIndex + Number(el.dataset.d);
        const card = feed.querySelector(`.card[data-i="${next}"]`);
        if (card) card.scrollIntoView({ block: 'start', behavior: CR.reduced() ? 'auto' : 'smooth' });
        break;
      }
      case 'back': CR.back(`#/f/${(activeVideo() || idx.videos[0]).id}`); break;
      case 'goto': { const s = document.getElementById(`s${el.dataset.s}`); if (s) s.scrollIntoView({ behavior: CR.reduced() ? 'auto' : 'smooth', block: 'start' }); break; }
      case 'branch': openBranch(el.dataset.k, el); break;
      case 'listen': {
        const t = Number(el.dataset.t);
        CR.go(['f', el.dataset.v], { t: Math.floor(t) });
        setTimeout(() => { if (player && activeVideo() && activeVideo().id === el.dataset.v) player.seek(t, { play: true }); }, 400);
        break;
      }
      case 'save-claim': {
        const vv = idx.videosById[el.dataset.v];
        const c = idx.claimsByKey[`${vv.id}:${el.dataset.c}`];
        const on = saved.toggle({ key: `c:${vv.id}:${c.id}`, sub: `${vv.channel.name} · ${fmtDate(vv.pub)} · ${fmtT(c.t)}`, title: c.text, href: `#/d/${vv.id}/${c.id}` });
        el.innerHTML = `${icon(on ? 'bookmark-fill' : 'bookmark')} ${on ? 'Guardado' : 'Guardar'}`;
        CR.toast(on ? 'Guardado en Explorar › Guardados' : 'Quitado de guardados');
        break;
      }
      case 'share-claim': {
        const vv = idx.videosById[el.dataset.v];
        const c = idx.claimsByKey[`${vv.id}:${el.dataset.c}`];
        const r = await CR.share({ title: vv.cleanTitle, text: `${L.tipo[c.tipo]} en ${fmtT(c.t)}: ${c.text}`, url: CR.linkTo(CR.hash(['d', vv.id, c.id])) });
        if (r === 'copied') CR.toast('Enlace a la destilación copiado');
        break;
      }
      case 'theme': ui.openTheme = ui.openTheme === el.dataset.th ? null : el.dataset.th; renderExplore({ tab: 'narrativas' }); break;
      case 'demo': CR.toast('Ejemplo: en el producto esta acción haría su trabajo.'); break;
      case 'reload': location.reload(); break;
      default: break;
    }
  });
  document.addEventListener('keydown', (e) => {
    if (!layer.hidden && e.key === 'Escape') CR.back(`#/f/${(activeVideo() || idx.videos[0]).id}`);
    if (layer.hidden && idx && (e.key === 'ArrowDown' || e.key === 'ArrowUp') && document.activeElement === feed) {
      e.preventDefault();
      const card = feed.querySelector(`.card[data-i="${activeIndex + (e.key === 'ArrowDown' ? 1 : -1)}"]`);
      if (card) card.scrollIntoView({ block: 'start', behavior: CR.reduced() ? 'auto' : 'smooth' });
    }
  });
  window.addEventListener('pagehide', () => { if (player && activeVideo()) store.set('session', { v: activeVideo().id, t: player.time() }); });

  const run = CR.onRoute(route);
  run();
})();

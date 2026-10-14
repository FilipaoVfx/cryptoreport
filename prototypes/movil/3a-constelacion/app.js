/* 3A · Constelación — se entra en un vídeo; «Destilar» convierte la frase en una escena de conexiones. */
(() => {
  'use strict';
  const { esc, fmtT, fmtDate, icon, L } = CR;
  const APP = '3a';
  const store = CR.store(APP);
  const saved = CR.saved(APP);
  const stage = document.getElementById('stage');
  const tray = document.getElementById('tray');
  const scrim = document.getElementById('scrim');
  const reader = document.getElementById('reader');

  let idx = null;
  let player = null;
  const cur = { v: null, doc: null, nowClaim: null, ribbonTouched: 0, level: 'video', route: null };
  const STEPS = ['Frase escuchada', 'Afirmación aislada', 'Supuestos', 'Conexiones', 'Lectura crítica'];
  const ui = { trayTab: 'videos', assetSec: 'altcoins', openTheme: null };

  const noDot = (s) => String(s || '').replace(/[.\s]+$/, '');

  /* ---------- reproductor persistente ---------- */
  function ensurePlayer() {
    if (player) return;
    player = new CR.Player(document.getElementById('player'));
    let last = 0;
    player.on('time', (t) => {
      updateScrub(t);
      if (Date.now() - last > 3000 && cur.v) { last = Date.now(); store.set('session', { v: cur.v.id, t }); }
      if (cur.level === 'video') syncRibbon(t);
    });
    player.on('state', (s) => {
      const b = document.getElementById('ctl-play');
      b.innerHTML = icon(s === 'playing' ? 'pause' : 'play');
      b.setAttribute('aria-label', s === 'playing' ? 'Pausar' : 'Reproducir');
      if (s === 'needs-tap') CR.toast('Toca el vídeo para empezar a reproducir');
      if (cur.level === 'video') renderDistillLabel();
    });
  }
  function updateScrub(t) {
    const dur = (cur.v && cur.v.dur) || 1;
    document.getElementById('scrub-fill').style.width = `${Math.min(100, (t / dur) * 100)}%`;
    document.getElementById('time').textContent = fmtT(t);
    const s = document.getElementById('scrub');
    s.setAttribute('aria-valuenow', String(Math.floor(t)));
    s.setAttribute('aria-valuetext', `${fmtT(t)} de ${fmtT(dur)}`);
    const near = nowClaim(t);
    CR.$$('.tick', document.getElementById('ticks')).forEach((el) => el.classList.toggle('is-now', near && el.dataset.c === near.id));
  }
  function drawTicks() {
    const box = document.getElementById('ticks');
    const dur = cur.v.dur || 1;
    box.innerHTML = (cur.doc && cur.doc.claims ? cur.doc.claims : []).filter((c) => c.t != null).map((c) => `<span class="tick" data-c="${c.id}" style="left:${(c.t / dur) * 100}%"></span>`).join('');
    document.getElementById('scrub').setAttribute('aria-valuemax', String(Math.floor(dur)));
  }
  (function bindScrub() {
    const s = document.getElementById('scrub');
    const seekAt = (x) => {
      const r = s.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (x - r.left) / r.width));
      if (player && cur.v) player.seek(ratio * (cur.v.dur || 0), { play: player.playing });
    };
    let down = false;
    s.addEventListener('pointerdown', (e) => { down = true; s.setPointerCapture(e.pointerId); seekAt(e.clientX); });
    s.addEventListener('pointermove', (e) => { if (down) seekAt(e.clientX); });
    s.addEventListener('pointerup', () => { down = false; });
    s.addEventListener('keydown', (e) => {
      if (!player) return;
      if (e.key === 'ArrowRight') { player.skip(5); e.preventDefault(); }
      if (e.key === 'ArrowLeft') { player.skip(-5); e.preventDefault(); }
    });
  })();
  function nowClaim(t) {
    if (!cur.doc || !cur.doc.claims) return null;
    const timed = cur.doc.claims.filter((c) => c.t != null).sort((a, b) => a.t - b.t);
    const before = timed.filter((c) => c.t <= t + 1).pop();
    if (before && t - before.t < 60) return before;
    return timed.find((c) => c.t > t) || before || null;
  }

  /* ---------- rutas: vídeo › afirmación › activo ---------- */
  /* Ruta corta «Vídeo › Afirmación › Activo» encima del escenario; «Volver al vídeo» siempre a mano. */
  let crumbs = '';
  function setCrumbs(parts) {
    const id = cur.v ? cur.v.id : '';
    const items = [['Vídeo', `#/v/${id}`]];
    if (parts[2] === 'c') items.push(['Afirmación', `#/v/${id}/c/${parts[3]}`]);
    if (parts[2] === 'lista') items.push(['Lista', null]);
    if (parts[4] === 'a' || parts[2] === 'a') items.push(['Activo', null]);
    crumbs = items.length < 2 ? '' : `<nav class="crumbs" aria-label="Dónde estás">${items.map(([label, href], i) => {
      const last = i === items.length - 1;
      return `${i ? '<span class="sep" aria-hidden="true">›</span>' : ''}${last ? `<span aria-current="step">${label}</span>` : `<button type="button" data-go="${href}">${label}</button>`}`;
    }).join('')}<button class="back-video" type="button" data-go="#/v/${id}">${icon('play', 'i-s')} Volver al vídeo</button></nav>`;
    document.getElementById('list-btn').setAttribute('aria-pressed', String(parts[2] === 'lista'));
  }
  async function route(r) {
    closeTray();
    reader.hidden = true;
    if (!idx) {
      stage.innerHTML = '<div class="skel" style="height:150px"></div><div class="skel" style="height:64px;margin-top:16px"></div>';
      try { idx = await CR.load(); } catch (e) {
        stage.innerHTML = `<div class="err" role="alert"><h3>No se pudo encender el reactor</h3><p>Fallaron los datos. Reintenta en un momento.</p><button class="btn" type="button" data-act="reload" style="margin-top:12px">${icon('refresh')} Reintentar</button></div>`;
        return;
      }
    }
    const p = r.parts;
    if (p[0] !== 'v' || !idx.videosById[p[1]]) {
      const s = store.get('session', null);
      const id = s && idx.videosById[s.v] ? s.v : idx.analyzed[0].id;
      CR.go(['v', id], s && s.v === id ? { t: Math.floor(s.t) } : null, { replace: true });
      return;
    }
    const v = idx.videosById[p[1]];
    ensurePlayer();
    if (!cur.v || cur.v.id !== v.id) {
      const s = store.get('session', null);
      const start = r.q.t != null ? Number(r.q.t) : s && s.v === v.id ? s.t : 0;
      cur.v = v; cur.doc = null; cur.nowClaim = null;
      document.body.dataset.short = v.short ? '1' : '0';
      document.getElementById('ambient').style.backgroundImage = `url("${CR.thumb(v.id, 'hq')}")`;
      player.load(v, { start });
      updateScrub(start);
      cur.docPromise = CR.loadVideo(v.id);
      try { cur.doc = await cur.docPromise; } catch (e) {
        stage.innerHTML = `<div class="err" role="alert"><h3>No se pudo cargar este vídeo</h3><p>El reproductor sigue disponible. Reintenta para ver sus afirmaciones.</p><button class="btn" type="button" data-act="retry" style="margin-top:12px">${icon('refresh')} Reintentar</button></div>`;
        return;
      }
      if (cur.v !== v) return;
      drawTicks();
    } else {
      if (!cur.doc && cur.docPromise) { try { cur.doc = await cur.docPromise; } catch (e) { return; } }
      if (r.q.t != null && p.length === 2) player.seek(Number(r.q.t), { play: false });
    }
    setCrumbs(p);
    if (p[2] === 'lista') { cur.level = 'list'; renderList(); }
    else if (p[2] === 'c' && p[4] === 'a') { cur.level = 'orbit'; await renderOrbit(p[5], r.q, p[3]); }
    else if (p[2] === 'a') { cur.level = 'orbit'; await renderOrbit(p[3], r.q, null); }
    else if (p[2] === 'c') { cur.level = 'scene'; renderScene(p[3], Number(r.q.paso || 1), r.q); }
    else { cur.level = 'video'; renderVideo(); }
    document.body.dataset.level = cur.level;
    if (crumbs) stage.insertAdjacentHTML('afterbegin', crumbs);
    stage.scrollTop = 0;
  }

  /* ---------- nivel vídeo ---------- */
  function renderVideo() {
    const v = cur.v, doc = cur.doc;
    const claims = doc.claims && doc.claims.length ? doc.claims.slice().filter((c) => c.t != null).sort((a, b) => a.t - b.t) : [];
    const ribbon = claims.length
      ? claims.map((c) => `<button class="rib" type="button" data-act="open-claim" data-c="${c.id}" data-t="${c.t}"><span class="rib-h"><span class="tc">${fmtT(c.t)}</span><span class="k">${L.tipo[c.tipo]}</span></span>${c.quote ? `<q>${esc(c.quote)}</q>` : ''}<p>${esc(c.text)}</p></button>`).join('')
      : CR.blocks(doc.segments, 30).map((b) => `<button class="rib" type="button" data-act="seek" data-t="${b.start}" data-seg="${b.start}"><span class="rib-h"><span class="tc">${fmtT(b.start)}</span><span>Se escucha</span></span><q>${esc(CR.clip(b.text, 140))}</q></button>`).join('');
    stage.innerHTML = `
      <div class="ribbon-head"><span>${claims.length ? 'Lo que se afirma ahora' : 'Lo que se escucha ahora'}</span><span>${claims.length ? CR.plural(claims.length, 'afirmación', 'afirmaciones') : 'sin análisis'}</span></div>
      <div class="ribbon" id="ribbon" data-scroll-x>${ribbon}</div>
      <button class="distill-btn" type="button" data-act="distill" id="distill">${icon('flask')}<span><span id="distill-label">Destilar</span><small id="distill-sub"></small></span></button>
      <p class="hint">Destilar pausa el vídeo y aísla la frase del momento. Los gestos son atajos: todo tiene botón.</p>
      ${!claims.length ? `<p class="noan">Este vídeo no está analizado. Puedes aislar una frase, pero el sistema no mostrará conexiones que no ha identificado.</p>` : ''}
      <p class="vtitle"><b>${esc(v.channel.name)}</b> · ${fmtDate(v.pub, { time: true })} · ${esc(v.cleanTitle)}</p>`;
    const rib = document.getElementById('ribbon');
    ['pointerdown', 'wheel', 'touchstart'].forEach((ev) => rib.addEventListener(ev, () => { cur.ribbonTouched = Date.now(); }, { passive: true }));
    cur.nowClaim = undefined;
    syncRibbon(player ? player.time() : 0);
    renderDistillLabel();
  }
  function syncRibbon(t) {
    const rib = document.getElementById('ribbon');
    if (!rib || !cur.doc) return;
    let target = null;
    if (cur.doc.claims && cur.doc.claims.length) {
      const c = nowClaim(t);
      target = c ? rib.querySelector(`[data-c="${c.id}"]`) : null;
    } else {
      const chips = CR.$$('[data-seg]', rib);
      target = chips.filter((el) => Number(el.dataset.seg) <= t + 0.5).pop() || chips[0];
    }
    if (target && !target.classList.contains('is-now')) {
      CR.$$('.rib.is-now', rib).forEach((el) => el.classList.remove('is-now'));
      target.classList.add('is-now');
      if (Date.now() - cur.ribbonTouched > 4000) rib.scrollTo({ left: target.offsetLeft - rib.offsetLeft, behavior: CR.reduced() ? 'auto' : 'smooth' });
      renderDistillLabel();
    }
  }
  function renderDistillLabel() {
    const sub = document.getElementById('distill-sub');
    if (!sub || !player) return;
    const c = nowClaim(player.time());
    sub.textContent = c ? `${fmtT(c.t)} · ${L.tipo[c.tipo]}` : 'Aislar la frase de este momento';
  }

  /* ---------- escena ---------- */
  function connections(c) {
    const doc = cur.doc, a = doc.analysis;
    const chain = a.cadena_narrativa.find((ch) => ch.afirmacion_ids.includes(c.id));
    const scen = a.escenarios.find((s) => s.afirmacion_ids.includes(c.id));
    const themes = idx.themes.filter((th) => th.sources.some((s) => s.v === cur.v.id && s.claims.includes(c.id)));
    const asset = c.assets.map((x) => idx.topicsById[x]).filter(Boolean);
    return {
      a: asset.length ? { title: asset[0].name + (asset.length > 1 ? ` y ${asset.length - 1} más` : ''), list: asset } : null,
      s: chain && chain.supuesto ? { title: chain.supuesto, chain } : scen ? { title: scen.supuestos[0], scen } : null,
      e: { title: `${CR.plural(c.evidences.length, 'fragmento', 'fragmentos')} · sin fuente externa`, list: c.evidences },
      n: themes.length ? { title: themes[0].short, themes } : null,
    };
  }
  function renderScene(cid, paso, q) {
    const v = cur.v, doc = cur.doc;
    if (cid === 'frase' || !doc.analysis) {
      const t = q.t != null ? Number(q.t) : player.time();
      const seg = doc.segments[CR.segAt(doc.segments, t)];
      stage.innerHTML = `
        <div class="steps">${STEPS.map((s, i) => `<span class="step${i === 0 ? ' on' : ''}"></span>`).join('')}</div>
        <p class="step-label"><span>Paso 1 de 5 · <b>${STEPS[0]}</b></span></p>
        <div class="scene" style="grid-template-areas:'p p'"><div class="phrase"><q>${esc(seg ? seg.text : '')}</q><p class="who"><span>${esc(v.channel.name)} · <span class="tc">${fmtT(seg ? seg.start : t)}</span></span><button type="button" data-act="seek" data-t="${seg ? seg.start : t}">${icon('play', 'i-s')} Escuchar</button></p></div></div>
        <p class="noan">Sin análisis, la destilación se detiene aquí: no hay afirmación aislada ni conexiones. El sistema no crea conexiones que no ha identificado.</p>
        <div class="next-row"><button class="btn" type="button" data-go="#/v/${v.id}">${icon('arrow-left')} Volver al vídeo</button><button class="btn" type="button" data-go="#/v/${v.id}/lista">${icon('list')} Leer en lista</button></div>`;
      return;
    }
    const c = CR.claim(doc, cid);
    if (!c) { CR.go(['v', v.id], null, { replace: true }); return; }
    const step = Math.max(1, Math.min(5, paso));
    const con = connections(c);
    const lit = { a: step >= 4, s: step >= 3, e: step >= 4, n: step >= 4 };
    const node = (k, label, ic) => {
      const d = con[k];
      return `<button class="node${lit[k] ? ' lit' : ''}${d ? '' : ' empty'}" type="button" data-k="${k}" data-act="node" aria-expanded="false"${lit[k] ? '' : ' disabled aria-disabled="true"'}><b>${icon(ic)}${label}</b><span>${lit[k] ? esc(d ? CR.clip(d.title, 70) : 'No identificado') : '…'}</span></button>`;
    };
    const lit5 = step >= 5;
    const pend = doc.analysis.verificaciones_pendientes.find((p) => p.afirmacion_ids.includes(c.id));
    const evNote = c.evidences.map((e) => e.observacion).filter(Boolean)[0];
    const key = `c:${v.id}:${c.id}`;
    stage.innerHTML = `
      <div class="steps" aria-hidden="true">${STEPS.map((s, i) => `<span class="step${i < step ? ' on' : ''}"></span>`).join('')}</div>
      <p class="step-label"><span>Paso ${step} de 5 · <b>${STEPS[step - 1]}</b></span><span class="tc">${fmtT(c.t)}</span></p>
      <div class="scene" id="scene">
        <svg aria-hidden="true"><defs><filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs><g id="lines"></g></svg>
        ${node('a', 'Activo', 'coin')}${node('s', 'Supuesto', 'branch')}
        <div class="phrase">
          <q>${esc(c.literal ? c.literal.cita : c.text)}</q>
          <p class="who"><span>${c.literal && c.literal.origen === 'titulo' ? 'Título del vídeo' : esc(v.channel.name)} · <span class="tc">${fmtT(c.t)}</span></span>${c.t != null ? `<button type="button" data-act="seek" data-t="${c.t}">${icon('play', 'i-s')} Escuchar</button>` : ''}</p>
          ${step >= 2 ? `<p class="claim-line"><b>Afirmación aislada por el sistema · ${L.tipo[c.tipo].toLowerCase()}</b>${esc(c.text)}</p>` : ''}
        </div>
        ${node('e', 'Evidencia citada', 'quote')}${node('n', 'Narrativa', 'route')}
      </div>
      <div id="detail"></div>
      ${lit5 ? `<section class="critical"><h3>Lectura crítica</h3><p class="q">${esc(pend ? pend.pregunta : `¿Qué haría falta para comprobar que «${CR.clip(noDot(c.text), 90)}»?`)}</p>
        <p class="ev"><b>Evidencia en este fragmento:</b> ${esc(c.justificacion)}${evNote ? ` ${esc(evNote)}` : ''}</p>
        <p class="ext">${icon('alert', 'i-s')}<span>${L.verif[c.verif]}. Ninguna fuente externa consultada: que falte aquí no prueba que sea falso.</span></p></section>` : ''}
      <div class="next-row">
        ${step > 1 ? `<button class="btn" type="button" data-act="paso" data-p="${step - 1}" aria-label="Paso anterior">${icon('chevron-left')}</button>` : `<button class="btn" type="button" data-go="#/v/${v.id}">${icon('arrow-left')} Vídeo</button>`}
        ${step < 5 ? `<button class="btn btn-solid" type="button" data-act="paso" data-p="${step + 1}" style="flex:1">${STEPS[step]} ${icon('arrow-right')}</button>` : `<button class="btn btn-solid" type="button" data-go="#/v/${v.id}" style="flex:1">${icon('play')} Volver al vídeo en ${fmtT(c.t)}</button>`}
      </div>
      <div class="next-row"><button class="btn" type="button" data-act="save" data-c="${c.id}" style="flex:1">${icon(saved.has(key) ? 'bookmark-fill' : 'bookmark')} ${saved.has(key) ? 'Guardado' : 'Guardar'}</button><button class="btn" type="button" data-act="share" data-c="${c.id}" style="flex:1">${icon('share')} Compartir</button></div>`;
    cur.scene = { c, con, step };
    requestAnimationFrame(() => drawLines(lit));
  }
  function drawLines(lit) {
    const scene = document.getElementById('scene');
    if (!scene) return;
    const B = scene.getBoundingClientRect();
    const ph = scene.querySelector('.phrase').getBoundingClientRect();
    const out = [];
    ['a', 's', 'e', 'n'].forEach((k) => {
      if (!lit[k]) return;
      const n = scene.querySelector(`.node[data-k="${k}"]`).getBoundingClientRect();
      const top = k === 'a' || k === 's';
      const x1 = n.left - B.left + n.width / 2, y1 = top ? n.bottom - B.top : n.top - B.top;
      const x2 = ph.left - B.left + ph.width * (k === 'a' || k === 'e' ? 0.3 : 0.7), y2 = top ? ph.top - B.top : ph.bottom - B.top;
      out.push(`<line class="${CR.reduced() ? '' : 'draw'}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`);
    });
    document.getElementById('lines').innerHTML = out.join('');
  }
  function openNode(k, btn) {
    const { c, con } = cur.scene;
    const d = con[k];
    const v = cur.v;
    const already = btn.getAttribute('aria-expanded') === 'true';
    CR.$$('.node', stage).forEach((n) => n.setAttribute('aria-expanded', 'false'));
    const box = document.getElementById('detail');
    if (already) { box.innerHTML = ''; return; }
    btn.setAttribute('aria-expanded', 'true');
    let html = '';
    if (!d) {
      html = `<div class="detail"><h3>${{ a: 'Activo', s: 'Supuesto', n: 'Narrativa' }[k]}</h3><p>El análisis no identificó ${{ a: 'un activo concreto', s: 'un supuesto explícito', n: 'una narrativa compartida' }[k]} para esta afirmación. No se rellena con suposiciones.</p></div>`;
    } else if (k === 'a') {
      const t = d.list[0];
      html = `<div class="detail"><h3>Activo · ${esc(L.section[t.section])}</h3><p>${esc(d.list.map((x) => x.name).join(', '))}</p>
        <p class="meta">${esc(t.name)} aparece en ${CR.plural(t.vc, 'vídeo', 'vídeos')} (${CR.plural(t.n, 'mención', 'menciones')}). ${c.postura ? `Postura extraída: ${esc(c.postura)}` : ''}</p>
        <div class="acts"><button class="btn btn-solid" type="button" data-go="#/v/${v.id}/c/${c.id}/a/${t.id}">${icon('orbit')} Abrir su órbita de vídeos</button></div></div>`;
    } else if (k === 's') {
      html = d.chain
        ? `<div class="detail"><h3>Supuesto · ${esc(L.vinculo[d.chain.vinculo].toLowerCase())}</h3><p>${esc(d.chain.supuesto)}</p><p class="meta">Encadena: ${esc(d.chain.premisa)} → ${esc(d.chain.conclusion)}</p></div>`
        : `<div class="detail"><h3>Supuestos del escenario · ${esc(L.origenEsc[d.scen.origen].toLowerCase())}</h3><p>${esc(d.scen.nombre)}</p>${d.scen.supuestos.map((u) => `<p class="meta">— ${esc(u)}</p>`).join('')}</div>`;
    } else if (k === 'e') {
      html = `<div class="detail"><h3>Evidencia citada · ${L.verif[c.verif].toLowerCase()}</h3>${d.list.map((e) => `<q>${esc(e.cita || e.observacion || '')}</q><p class="meta">${e.origen === 'titulo' ? 'Título del vídeo' : `${L.origen[e.origen]} · ${fmtT(e.inicio_s)}`}${e.observacion && e.cita ? ` · ${esc(e.observacion)}` : ''}</p>`).join('')}
        <p class="meta" style="color:var(--green)">Fuente externa: ninguna consultada.</p>
        ${d.list[0] && d.list[0].inicio_s != null ? `<div class="acts"><button class="btn" type="button" data-act="seek" data-t="${d.list[0].inicio_s}">${icon('play')} Reproducir el fragmento</button></div>` : ''}</div>`;
    } else if (k === 'n') {
      const th = d.themes[0];
      const other = th.sources.find((s) => s.v !== v.id && (s.claims.length || s.frags.length));
      const ov = other && idx.videosById[other.v];
      const ot = other ? (other.claims.length ? (idx.claimsByKey[`${other.v}:${other.claims[0]}`] || {}).t : other.frags[0].t) : 0;
      html = `<div class="detail"><h3>Narrativa</h3><p>${esc(th.title)}</p><p class="meta">${CR.plural(th.videoCount, 'vídeo la trata', 'vídeos la tratan')}; repetirla no la prueba.</p>
        ${ov ? `<div class="acts"><button class="btn btn-solid" type="button" data-go="#/v/${ov.id}?t=${Math.floor(ot || 0)}">${icon('arrow-right')} Saltar a ${esc(ov.channel.name)}, ${fmtDate(ov.pub)}</button></div>` : ''}</div>`;
    }
    box.innerHTML = html;
    box.scrollIntoView({ block: 'nearest', behavior: CR.reduced() ? 'auto' : 'smooth' });
  }

  /* ---------- órbita de vídeos de un activo ---------- */
  async function renderOrbit(aid, q, fromClaim) {
    const t = idx.topicsById[aid];
    if (!t) { CR.go(['v', cur.v.id], null, { replace: true }); return; }
    const sort = q.orden || 'fecha';
    let sats = t.videos.map((m) => {
      const v = idx.videosById[m.v];
      const claim = t.claims.map((k) => idx.claimsByKey[`${k.v}:${k.id}`]).find((c) => c && c.v === m.v);
      return { v, m, claim };
    });
    if (sort === 'fecha') sats.sort((a, b) => a.v.pub.localeCompare(b.v.pub));
    if (sort === 'argumento') sats.sort((a, b) => (b.claim ? 1 : 0) - (a.claim ? 1 : 0) || (a.claim && b.claim ? a.claim.dir.localeCompare(b.claim.dir) : 0) || b.m.n - a.m.n);
    if (sort === 'creador') sats.sort((a, b) => a.v.ch.localeCompare(b.v.ch) || a.v.pub.localeCompare(b.v.pub));
    const shown = sats.slice(0, 10);
    const sel = shown.find((s) => s.v.id === q.sel) || shown.find((s) => s.v.id === cur.v.id) || shown[0];
    const n = shown.length;
    const base = fromClaim ? `#/v/${cur.v.id}/c/${fromClaim}/a/${aid}` : `#/v/${cur.v.id}/a/${aid}`;
    const pos = (i, r) => { const ang = (-90 + (i * 360) / n) * (Math.PI / 180); return { x: 50 + r * Math.cos(ang), y: 50 + r * Math.sin(ang) }; };
    const selT = sel.claim ? sel.claim.t : sel.m.frags[0] ? sel.m.frags[0].t : 0;
    stage.innerHTML = `
      <div class="sortbar" role="group" aria-label="Ordenar la órbita">${[['fecha', 'Fecha'], ['argumento', 'Argumento'], ['creador', 'Creador']].map(([k, l]) => `<button type="button" data-go="${base}?orden=${k}&sel=${sel.v.id}" aria-pressed="${k === sort}">${l}</button>`).join('')}</div>
      <div class="orbit" role="group" aria-label="Órbita de ${esc(t.name)}">
        <span class="orbit-ring"></span><span class="orbit-ring inner"></span>
        <div class="orbit-core"><span><b>${esc(t.name)}</b><small>${CR.plural(t.vc, 'vídeo', 'vídeos')}</small></span></div>
        ${shown.map((s, i) => { const p = pos(i, 41); const d = pos(i, 50.5); return `<button class="sat${s.claim ? ' analyzed' : ''}" type="button" style="left:${p.x}%;top:${p.y}%" data-go="${base}?orden=${sort}&sel=${s.v.id}" aria-pressed="${s === sel}" aria-label="${esc(s.v.channel.name)}, ${fmtDate(s.v.pub)}: ${esc(s.v.cleanTitle)}"><img src="${CR.thumb(s.v.id)}" alt="" loading="lazy"></button><span class="sat-date" style="left:${d.x}%;top:calc(${d.y}% - 6px)">${fmtDate(s.v.pub)}</span>`; }).join('')}
      </div>
      ${sats.length > n ? `<p class="hint">Y ${CR.plural(sats.length - n, 'vídeo más', 'vídeos más')} en la hoja de lectura.</p>` : ''}
      <article class="sat-card"><p class="meta"><span>${esc(sel.v.channel.name)} · ${fmtDate(sel.v.pub)} · <span class="tc">${fmtT(selT)}</span></span><span>${sel.claim ? 'analizado' : 'solo transcripción'}</span></p>
        <q>${esc(sel.claim && sel.claim.quote ? sel.claim.quote : sel.m.frags[0] ? sel.m.frags[0].text : sel.v.cleanTitle)}</q>
        ${sel.claim ? `<p>${esc(sel.claim.text)}</p>` : '<p style="color:var(--muted)">Mención literal; este vídeo no tiene análisis.</p>'}
        <div class="acts"><button class="btn btn-solid" type="button" data-go="#/v/${sel.v.id}?t=${Math.floor(selT || 0)}">${icon('target')} Llevar al centro</button><button class="btn" type="button" data-act="reader" data-a="${aid}">${icon('book')} Hoja de lectura</button></div></article>
      <div class="next-row"><button class="btn" type="button" data-go="#/v/${cur.v.id}" style="flex:1">${icon('arrow-left')} Volver al vídeo</button></div>`;
  }
  async function openReader(aid) {
    const t = idx.topicsById[aid];
    const claims = t.claims.map((k) => idx.claimsByKey[`${k.v}:${k.id}`]).filter(Boolean);
    const docs = await Promise.all([...new Set(claims.map((c) => c.v))].map((v) => CR.loadVideo(v).catch(() => null)));
    const pend = [];
    docs.filter(Boolean).forEach((d) => d.analysis && d.analysis.verificaciones_pendientes.forEach((p) => { if (p.afirmacion_ids.some((x) => claims.some((c) => c.v === d.id && c.id === x)) && !pend.includes(p.pregunta)) pend.push(p.pregunta); }));
    const changes = idx.contrasts.filter((p) => p.asset === aid);
    document.getElementById('reader-body').innerHTML = `
      <h1 id="reader-title">${esc(t.name)}</h1>
      <p class="lead">${L.section[t.section]} · ${CR.plural(t.vc, 'vídeo', 'vídeos')} · ${CR.plural(t.n, 'mención', 'menciones')} · ${CR.plural(t.cc, 'creador', 'creadores')}. ${CR.plural(claims.length, 'afirmación analizada', 'afirmaciones analizadas')}.${t.note ? ` Ojo: ${esc(t.note)}.` : ''}</p>
      <h2>Lo que se analizó</h2>${claims.map((c) => { const v = idx.videosById[c.v]; return `<div class="r-item">${c.quote ? `<q>${esc(c.quote)}</q>` : ''}<p>${esc(c.text)}</p><small>${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${fmtT(c.t)} · ${L.tipo[c.tipo]} · ${L.verif[c.verif]}</small></div>`; }).join('') || '<p class="r-note">Ninguno de los vídeos analizados lo trata como afirmación.</p>'}
      <h2>Cambios del discurso</h2>${changes.map((p) => { const A = idx.claimsByKey[`${p.a.v}:${p.a.id}`], B = idx.claimsByKey[`${p.b.v}:${p.b.id}`]; return `<div class="r-item"><p>${p.kind === 'cambio' ? 'Cambio de postura' : 'Idea repetida'} (${L.hz[p.hz].toLowerCase()}): «${esc(noDot(A.postura))}» → «${esc(noDot(B.postura))}»</p><small>${fmtDate(idx.videosById[p.a.v].pub)} → ${fmtDate(idx.videosById[p.b.v].pub)} · detectado por reglas</small></div>`; }).join('') || '<p class="r-note">No se detectaron cambios entre vídeos analizados.</p>'}
      <h2>Preguntas abiertas</h2>${pend.map((p) => `<div class="r-item"><p style="color:var(--text)">${esc(p)}</p></div>`).join('') || '<p class="r-note">Sin preguntas registradas para estas afirmaciones.</p>'}
      <h2>Menciones en todos los vídeos</h2>${t.videos.map((m) => { const v = idx.videosById[m.v]; return `<div class="r-item"><q>${esc(m.frags[0] ? m.frags[0].text : '')}</q><small>${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${CR.plural(m.n, 'mención', 'menciones')} · ${esc(CR.clip(v.cleanTitle, 60))}</small></div>`; }).join('')}
      <p class="r-note">${esc(idx.method.mentions)} ${esc(idx.method.external)}</p>`;
    reader.hidden = false;
    reader.scrollTop = 0;
    reader.querySelector('.pill-back').focus();
  }

  /* ---------- modo lista ---------- */
  function renderList() {
    const v = cur.v, doc = cur.doc;
    if (!doc.analysis) {
      stage.innerHTML = `<section class="linear"><h2>Transcripción en lista</h2><p>${esc(v.channel.name)} · ${fmtDate(v.pub)} · sin análisis</p>${CR.blocks(doc.segments, 40).map((b) => `<div class="lin"><p class="lin-h"><span class="tc">${fmtT(b.start)}</span><button class="btn" type="button" data-act="seek" data-t="${b.start}" style="min-height:34px">${icon('play', 'i-s')} Escuchar</button></p><q>${esc(b.text)}</q></div>`).join('')}</section>`;
      return;
    }
    const claims = doc.claims.map((c) => CR.claim(doc, c.id)).filter(Boolean).sort((a, b) => (a.t == null ? -1 : a.t) - (b.t == null ? -1 : b.t));
    stage.innerHTML = `<section class="linear"><h2>Las ${claims.length} afirmaciones, en orden</h2><p>El mismo contenido de la escena, en lectura lineal.</p>
      ${claims.map((c) => { const con = connections(c); return `<article class="lin"><p class="lin-h"><span><span class="tc">${c.t != null ? fmtT(c.t) : 'título'}</span> · ${L.tipo[c.tipo]}</span><span>${L.verif[c.verif]}</span></p>${c.literal ? `<q>${esc(c.literal.cita)}</q>` : ''}<p>${esc(c.text)}</p>
        <dl><dt>Activo</dt><dd>${esc(con.a ? con.a.title : 'No identificado')}</dd><dt>Supuesto</dt><dd>${esc(con.s ? con.s.title : 'No explícito')}</dd><dt>Evidencia</dt><dd>${esc(con.e.title)}</dd><dt>Narrativa</dt><dd>${esc(con.n ? con.n.title : 'Ninguna compartida')}</dd></dl>
        <div class="acts">${c.t != null ? `<button class="btn" type="button" data-act="seek" data-t="${c.t}">${icon('play')} Escuchar</button>` : ''}<button class="btn" type="button" data-go="#/v/${v.id}/c/${c.id}?paso=5">${icon('flask')} Ver destilado</button></div></article>`; }).join('')}</section>`;
  }

  /* ---------- bandejas ---------- */
  function openTray(kind) {
    tray.hidden = false; scrim.hidden = false;
    renderTray(kind);
  }
  function closeTray() { tray.hidden = true; scrim.hidden = true; }
  function renderTray(kind) {
    const title = document.getElementById('tray-title');
    const body = document.getElementById('tray-body');
    if (kind === 'fuentes') {
      title.textContent = 'Fuentes';
      body.innerHTML = `<div class="strip" data-scroll-x>${idx.videos.map((v) => `<button type="button" data-go="#/v/${v.id}"${cur.v && cur.v.id === v.id ? ' aria-current="true"' : ''}><img src="${CR.thumb(v.id)}" alt="" loading="lazy"><b>${esc(v.cleanTitle)}</b><small>${esc(v.channel.name)} · ${fmtDate(v.pub)}${v.analysis ? ' · analizado' : ''}</small></button>`).join('')}</div>`;
      return;
    }
    title.textContent = 'Explorar';
    const tabs = [['videos', 'Vídeos'], ['narrativas', 'Narrativas'], ['activos', 'Activos'], ['guardados', 'Guardados']];
    let list = '';
    if (ui.trayTab === 'videos') {
      list = idx.videos.map((v) => `<button class="trow${cur.v && cur.v.id === v.id ? ' is-cur' : ''}" type="button" data-go="#/v/${v.id}"><img src="${CR.thumb(v.id)}" alt="" loading="lazy"><span><b>${esc(v.cleanTitle)}</b><small>${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${v.analysis ? `${v.analysis.claims} afirmaciones` : 'sin analizar'}</small></span></button>`).join('');
    } else if (ui.trayTab === 'narrativas') {
      list = idx.themes.map((th) => `<button class="trow trow-plain" type="button" data-act="tray-theme" data-th="${th.id}"><span><b>${esc(th.title)}</b><small>${CR.plural(th.videoCount, 'vídeo', 'vídeos')} · ${th.analyzedCount} analizados</small></span>${icon(ui.openTheme === th.id ? 'chevron-up' : 'chevron-down')}</button>${ui.openTheme === th.id ? th.sources.map((s) => { const v = idx.videosById[s.v]; const t = s.claims.length ? (idx.claimsByKey[`${s.v}:${s.claims[0]}`] || {}).t : s.frags[0] ? s.frags[0].t : 0; return `<button class="trow" type="button" data-go="#/v/${v.id}?t=${Math.floor(t || 0)}" style="padding-left:12px"><img src="${CR.thumb(v.id)}" alt="" loading="lazy"><span><b>${esc(v.cleanTitle)}</b><small>${esc(v.channel.name)} · ${fmtDate(v.pub)} · desde ${fmtT(t)}</small></span></button>`; }).join('') : ''}`).join('');
    } else if (ui.trayTab === 'activos') {
      const rows = idx.topics.filter((t) => t.section === ui.assetSec).sort((a, b) => b.vc - a.vc || b.n - a.n);
      list = `<div class="tabs" data-scroll-x>${['altcoins', 'macro', 'bolsa'].map((s) => `<button type="button" data-act="tray-sec" data-s="${s}" aria-pressed="${ui.assetSec === s}">${L.section[s]}</button>`).join('')}</div>`
        + (ui.assetSec === 'altcoins' ? `<button class="trow trow-plain" type="button" data-go="#/v/${cur.v.id}/a/btc"><span><b>Bitcoin</b><small>Fuera del ranking · ${idx.topicsById.btc.vc} vídeos</small></span>${icon('orbit')}</button>` : '')
        + rows.map((t, i) => `<button class="trow trow-plain" type="button" data-go="#/v/${cur.v.id}/a/${t.id}"><span><b>${i + 1}. ${esc(t.name)}</b><small>${CR.plural(t.vc, 'vídeo', 'vídeos')} · ${CR.plural(t.n, 'mención', 'menciones')}${t.claims.length ? ` · ${t.claims.length} analizada${t.claims.length > 1 ? 's' : ''}` : ''}</small></span>${icon('orbit')}</button>`).join('');
    } else {
      const s = saved.all();
      list = s.length ? s.map((x) => `<button class="trow trow-plain" type="button" data-go="${esc(x.href)}"><span><b>${esc(x.title)}</b><small>${esc(x.sub)}</small></span>${icon('flask')}</button>`).join('') : '<p class="empty">Aún no has guardado nada. En una escena destilada pulsa «Guardar».</p>';
    }
    body.innerHTML = `<div class="tabs" data-scroll-x role="group" aria-label="Secciones">${tabs.map(([k, l]) => `<button type="button" data-act="tray-tab" data-t="${k}" aria-pressed="${ui.trayTab === k}">${l}</button>`).join('')}</div>${list}
      <p class="hint" style="text-align:left"><a href="../index.html" style="text-decoration:underline">Volver al tablero de propuestas</a></p>`;
  }

  /* ---------- acciones ---------- */
  document.addEventListener('click', async (e) => {
    const go = e.target.closest('[data-go]');
    if (go) { CR.go(go.dataset.go); return; }
    const el = e.target.closest('[data-act]');
    if (!el) return;
    switch (el.dataset.act) {
      case 'toggle': if (player) player.toggle(); break;
      case 'skip': if (player) player.skip(Number(el.dataset.d)); break;
      case 'seek': if (player) player.seek(Number(el.dataset.t), { play: true }); break;
      case 'open-claim': if (player) player.pause(); CR.go(['v', cur.v.id, 'c', el.dataset.c], { paso: 1 }); break;
      case 'distill': {
        if (player) player.pause();
        const t = player ? player.time() : 0;
        const c = nowClaim(t);
        if (c && cur.doc.analysis) CR.go(['v', cur.v.id, 'c', c.id], { paso: 1 });
        else CR.go(['v', cur.v.id, 'c', 'frase'], { t: Math.floor(t) });
        break;
      }
      case 'paso': { const r = CR.parseHash(); CR.go(r.parts, { paso: el.dataset.p }, { replace: true }); break; }
      case 'node': if (!el.disabled) openNode(el.dataset.k, el); break;
      case 'save': {
        const c = CR.claim(cur.doc, el.dataset.c);
        const on = saved.toggle({ key: `c:${cur.v.id}:${c.id}`, sub: `${cur.v.channel.name} · ${fmtDate(cur.v.pub)} · ${fmtT(c.t)}`, title: c.text, href: `#/v/${cur.v.id}/c/${c.id}?paso=5` });
        el.innerHTML = `${icon(on ? 'bookmark-fill' : 'bookmark')} ${on ? 'Guardado' : 'Guardar'}`;
        CR.toast(on ? 'Guardado en Explorar › Guardados' : 'Quitado de guardados');
        break;
      }
      case 'share': {
        const c = CR.claim(cur.doc, el.dataset.c);
        const r = await CR.share({ title: cur.v.cleanTitle, text: `${L.tipo[c.tipo]} en ${fmtT(c.t)}: ${c.text}`, url: CR.linkTo(CR.hash(['v', cur.v.id, 'c', c.id], { paso: 5 })) });
        if (r === 'copied') CR.toast('Enlace a la escena copiado');
        break;
      }
      case 'list': CR.go(CR.parseHash().parts[2] === 'lista' ? ['v', cur.v.id] : ['v', cur.v.id, 'lista']); break;
      case 'tray': openTray(el.dataset.tray); break;
      case 'tray-close': closeTray(); break;
      case 'tray-tab': ui.trayTab = el.dataset.t; renderTray('explorar'); break;
      case 'tray-sec': ui.assetSec = el.dataset.s; renderTray('explorar'); break;
      case 'tray-theme': ui.openTheme = ui.openTheme === el.dataset.th ? null : el.dataset.th; renderTray('explorar'); break;
      case 'reader': openReader(el.dataset.a); break;
      case 'reader-close': reader.hidden = true; break;
      case 'reload': location.reload(); break;
      case 'retry': cur.v = null; route(CR.parseHash()); break;
      default: break;
    }
  });
  scrim.addEventListener('click', closeTray);
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (!reader.hidden) reader.hidden = true;
    else if (!tray.hidden) closeTray();
  });
  window.addEventListener('resize', CR.debounce(() => { if (cur.level === 'scene' && cur.scene) drawLines({ a: cur.scene.step >= 4, s: cur.scene.step >= 3, e: cur.scene.step >= 4, n: cur.scene.step >= 4 }); }, 150));
  window.addEventListener('pagehide', () => { if (player && cur.v) store.set('session', { v: cur.v.id, t: player.time() }); });

  const run = CR.onRoute(route);
  run();
})();

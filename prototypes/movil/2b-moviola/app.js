/* 2B · Moviola — mesa de montaje: visor, línea de tiempo por creador, planos y fichas. */
(() => {
  'use strict';
  const { esc, fmtT, fmtDate, icon, L } = CR;
  const APP = '2b';
  const store = CR.store(APP);
  const saved = CR.saved(APP);
  const desk = document.getElementById('desk');
  const lib = document.getElementById('library');
  const scrim = document.getElementById('scrim');

  let idx = null;
  let screen = null;
  let player = null;
  let playerVideo = null;
  const scrolls = new Map();
  const mesa = { th: null, s: null, v: null, doc: null, p: 0 };
  const ui = { binMode: store.get('binMode', 'creador'), fs: store.get('fs', 'altcoins'), open: null };
  const PLATES = ['Qué plantea este creador', 'Qué evidencia aporta', 'Qué supuestos necesita', 'Qué dicen otros vídeos', 'Qué preguntas quedan abiertas', 'Síntesis interpretativa'];

  const track = (ch) => `var(--${ch})`;
  const noDot = (s) => String(s || '').replace(/[.\s]+$/, '');
  const lowerFirst = (s) => (s ? s.charAt(0).toLowerCase() + s.slice(1) : s);
  const joinEs = (a) => (a.length <= 1 ? a.join('') : `${a.slice(0, -1).join(', ')} y ${a[a.length - 1]}`);
  const claimOf = (v, id) => idx.claimsByKey[`${v}:${id}`];
  const score = (th) => th.analyzedCount * 10 + th.claimCount + Math.min(th.videoCount, 6) + th.contrasts.reduce((a, i) => a + (idx.contrasts[i].kind === 'cambio' ? 14 : 4), 0);

  /* ---------- reproductor del visor ---------- */
  function unmount() {
    if (player) { if (playerVideo) store.set('session', { v: playerVideo.id, t: player.time() }); player.destroy(); }
    player = null; playerVideo = null;
  }
  function mount(host, v, start, onTime) {
    unmount();
    player = new CR.Player(host);
    playerVideo = v;
    let last = 0;
    player.on('time', (t) => {
      const b = document.getElementById('visor-tc');
      if (b) b.textContent = `${fmtT(t)} / ${fmtT(v.dur)}`;
      if (Date.now() - last > 3000) { last = Date.now(); store.set('session', { v: v.id, t }); if (screen && screen.startsWith('mesa:')) store.set('mesa', { th: mesa.th.id, v: v.id, p: mesa.p, t }); }
      if (onTime) onTime(t);
    });
    player.on('state', (s) => { if (s === 'needs-tap') CR.toast('Toca el visor para empezar a reproducir'); });
    player.load(v, { start });
  }

  /* ---------- consola y biblioteca ---------- */
  function updateConsole(a) {
    const m = store.get('mesa', null);
    const th = (m && idx.themesById[m.th]) || idx.themes.slice().sort((x, y) => score(y) - score(x))[0];
    const main = document.getElementById('c-main');
    main.href = m && idx.themesById[m.th] ? `#/mesa/${m.th}?v=${m.v}&p=${m.p || 0}` : `#/mesa/${th.id}`;
    document.getElementById('c-label').textContent = th.short;
    main.setAttribute('aria-label', `Montaje: ${th.short}`);
    CR.$$('.console [data-c]').forEach((el) => el.removeAttribute('aria-current'));
    const cur = a === 'mesa' ? 'mesa' : a === '' ? 'sala' : ['fuentes', 'fuente', 'fichas', 'ficha', 'guardados', 'estados', 'marcas'].includes(a) ? 'biblioteca' : null;
    if (cur) { const el = document.querySelector(`.console [data-c="${cur}"]`); if (el) el.setAttribute('aria-current', 'page'); }
  }
  function openLibrary() {
    const items = [
      ['#/fuentes', 'film', 'Fuentes', 'Los vídeos, en cubetas por creador', idx.videos.length],
      ['#/fichas', 'stack', 'Fichas', 'Activos: altcoins, macro y bolsa', idx.topics.length],
      ['#/marcas', 'scale', 'Marcas en rojo', 'Cambios de postura y repeticiones', idx.contrasts.length],
      ['#/guardados', 'bookmark', 'Clips guardados', 'Lo que apartaste para volver', saved.all().length],
      ['#/estados', 'clock', 'Estados del procesamiento', 'Cómo se ve cada caso', CR.STATES.length],
      ['../index.html', 'arrow-left', 'Tablero de propuestas', 'Volver a las seis interfaces', ''],
    ];
    document.getElementById('lib-list').innerHTML = items.map(([href, ic, name, sub, n]) => `<a href="${href}">${icon(ic)}<span><b>${name}</b><small>${sub}</small></span><span class="n">${n}</span></a>`).join('');
    lib.hidden = false; scrim.hidden = false;
    lib.querySelector('a').focus();
  }
  function closeLibrary() { lib.hidden = true; scrim.hidden = true; }

  /* ---------- rutas ---------- */
  async function route(r) {
    const [a = '', b] = r.parts;
    const key = a ? `${a}${b ? ':' + b : ''}` : 'sala';
    closeLibrary();
    if (screen === key && a === 'mesa') { await renderMesa(b, r.q, true); return; }
    if (screen === key && (a === 'buscar' || a === 'ficha' || a === 'fichas')) { if (a !== 'buscar') rerender(a, b, r.q); return; }
    if (screen) scrolls.set(screen, window.scrollY);
    screen = key;
    unmount();
    document.body.dataset.screen = a || 'sala';
    if (!idx) {
      desk.innerHTML = '<div class="pad"><div class="skel" style="height:34px;margin-top:20px"></div><div class="skel" style="height:180px;margin-top:16px"></div></div>';
      try { idx = await CR.load(); } catch (e) {
        desk.innerHTML = `<div class="err" role="alert"><h3>No se pudo abrir la sala</h3><p>Fallaron los datos. Reintenta en un momento.</p><button class="btn-d" type="button" data-act="reload">${icon('refresh')} Reintentar</button></div>`;
        return;
      }
    }
    updateConsole(a);
    rerender(a, b, r.q);
    if (a !== 'mesa' && a !== 'fuente') window.scrollTo(0, scrolls.get(key) || 0); else window.scrollTo(0, 0);
  }
  async function rerender(a, b, q) {
    const where = document.getElementById('bar-where');
    where.textContent = { '': 'Sala de montaje', mesa: 'Mesa', fuentes: 'Fuentes', fuente: 'Visor de fuente', fichas: 'Fichas', ficha: 'Ficha', guardados: 'Clips guardados', buscar: 'Búsqueda', estados: 'Estados', marcas: 'Marcas en rojo' }[a] || '';
    if (a === 'mesa') await renderMesa(b, q);
    else if (a === 'fuentes') renderBins();
    else if (a === 'fuente') await renderSource(b, q);
    else if (a === 'fichas') renderDeck(q.s);
    else if (a === 'ficha') renderFicha(b, q.tab);
    else if (a === 'guardados') renderSaved();
    else if (a === 'buscar') renderSearch(q.q || '');
    else if (a === 'estados') renderStates();
    else if (a === 'marcas') renderMarks();
    else renderSala();
  }

  /* ---------- sala ---------- */
  function markCard(p) {
    const A = claimOf(p.a.v, p.a.id), B = claimOf(p.b.v, p.b.id);
    const va = idx.videosById[p.a.v], vb = idx.videosById[p.b.v];
    const th = idx.themes.find((t) => t.contrasts.includes(idx.contrasts.indexOf(p)));
    const title = p.kind === 'cambio' ? `${va.channel.name} cambia de postura sobre ${CR.topicName(p.asset)}` : `${va.channel.name} repite una idea sobre ${CR.topicName(p.asset)}`;
    return `<a class="mark-card paper" href="#/mesa/${th ? th.id : idx.themes[0].id}?v=${vb.id}&p=3">
      <h3>${p.kind === 'cambio' ? `<span class="pencil">${esc(title)}</span>` : esc(title)}</h3>
      <p><span class="tc">${fmtDate(va.pub)} ${fmtT(A.t)}</span> «${esc(lowerFirst(noDot(A.postura)))}» → <span class="tc">${fmtDate(vb.pub)} ${fmtT(B.t)}</span> «${esc(lowerFirst(noDot(B.postura)))}»</p>
    </a>`;
  }
  function renderSala() {
    const themes = idx.themes.slice().sort((a, b) => score(b) - score(a));
    const m = store.get('mesa', null);
    const mth = m && idx.themesById[m.th];
    const mv = m && idx.videosById[m.v];
    desk.innerHTML = `
      <div class="pad" style="padding-top:16px"><h1 class="h-desk">Sala de montaje</h1><p class="sub-desk">Cada mesa reúne los vídeos que tratan una pregunta. Monta la comparación clip a clip.</p></div>
      ${mth && mv ? `<a class="resume" href="#/mesa/${mth.id}?v=${mv.id}&p=${m.p || 0}"><img src="${CR.thumb(mv.id)}" alt="" loading="lazy"><span><b>${esc(mth.short)}</b><small>Seguir montando · plano ${(m.p || 0) + 1} · <span class="tc">${fmtT(m.t || 0)}</span></small></span>${icon('chevron-right')}</a>` : ''}
      <div class="sec-head"><h2>Mesas abiertas</h2><span>${themes.length}</span></div>
      <div class="tiles">${themes.map((th) => `<a class="tile paper" href="#/mesa/${th.id}"><h3>${esc(th.title)}</h3><div class="tile-foot"><span>${CR.plural(th.videoCount, 'fuente', 'fuentes')} · ${th.analyzedCount} analiz.</span><span class="dots">${th.creators.map((c) => `<i style="background:${track(c)}" title="${esc(idx.channelsBySlug[c].name)}"></i>`).join('')}</span></div>${th.contrasts.some((i) => idx.contrasts[i].kind === 'cambio') ? '<span class="tile-foot"><span class="red-mark">Marca roja: cambio de postura</span></span>' : ''}</a>`).join('')}</div>
      <div class="sec-head"><h2>Últimos clips</h2><a href="#/fuentes">Todas las fuentes</a></div>
      <div class="strip" data-scroll-x>${idx.videos.slice(0, 10).map((v) => `<a class="frame" href="#/fuente/${v.id}"><span class="frame-img"><img src="${CR.thumb(v.id)}" alt="" loading="lazy"><span class="tc">${fmtT(v.dur)}</span></span><span class="frame-track" style="display:block;background:${track(v.ch)}"></span><b>${esc(v.cleanTitle)}</b><small>${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${v.analysis ? 'analizado' : 'transcripción'}</small></a>`).join('')}</div>
      <div class="sec-head"><h2>Marcas en rojo</h2><a href="#/marcas">Todas</a></div>
      ${idx.contrasts.filter((p) => p.kind === 'cambio').map(markCard).join('')}
      <p class="pad" style="margin-top:20px;font-size:13px;color:var(--muted-d)">${esc(idx.method.external)} <a href="#/estados" style="text-decoration:underline">Estados del procesamiento</a></p>`;
  }

  /* ---------- mesa ---------- */
  function dayRange() {
    const s = new Date(idx.period.from), e = new Date(idx.period.to);
    const out = [];
    for (let d = new Date(s.getFullYear(), s.getMonth(), s.getDate()); d <= e; d.setDate(d.getDate() + 1)) out.push(new Date(d));
    return out;
  }
  function timelineHtml(th, activeId) {
    const days = dayRange();
    const LET = ['D', 'L', 'M', 'X', 'J', 'V', 'S'];
    const k = (d) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    const rows = idx.channels.filter((c) => th.sources.some((s) => idx.videosById[s.v].ch === c.slug));
    return `<section class="timeline" id="timeline" style="--days:${days.length}" aria-label="Línea de tiempo de fuentes">
      <div class="tl-days"><span>Pistas</span>${days.map((d) => `<span>${LET[d.getDay()]} ${d.getDate()}</span>`).join('')}</div>
      ${rows.map((c) => `<div class="tl-track"><span class="tl-name"><i style="background:${track(c.slug)}"></i>${esc(c.name.split(' ')[0])}</span>${days.map((d) => {
        const clips = th.sources.filter((s) => { const v = idx.videosById[s.v]; return v.ch === c.slug && CR.dayKey(v.pub) === k(d); }).sort((x, y) => idx.videosById[x.v].pub.localeCompare(idx.videosById[y.v].pub));
        return `<span class="tl-cell">${clips.map((s) => { const v = idx.videosById[s.v]; return `<button class="clip${s.claims.length ? ' is-analyzed' : ''}" type="button" style="--track:${track(v.ch)}" data-act="clip" data-v="${v.id}" aria-pressed="${v.id === activeId}" aria-label="${esc(v.channel.name)}, ${fmtDate(v.pub)}${s.claims.length ? ', con análisis' : ''}: ${esc(v.cleanTitle)}"><img src="${CR.thumb(v.id)}" alt="" loading="lazy"></button>`; }).join('')}</span>`;
      }).join('')}</div>`).join('')}
      <svg class="tl-marks" id="tl-marks" aria-hidden="true"></svg>
    </section>
    <div class="tl-legend"><span><i class="an"></i>con análisis</span><span><i class="rl"></i>marca roja: cambio de postura</span><span>${CR.plural(th.videoCount, 'clip', 'clips')} en ${CR.plural(rows.length, 'pista', 'pistas')}</span></div>`;
  }
  function drawMarks(th) {
    const svg = document.getElementById('tl-marks');
    const box = document.getElementById('timeline');
    if (!svg || !box) return;
    const B = box.getBoundingClientRect();
    svg.setAttribute('viewBox', `0 0 ${B.width} ${B.height}`);
    svg.innerHTML = th.contrasts.map((i) => {
      const p = idx.contrasts[i];
      const a = box.querySelector(`.clip[data-v="${p.a.v}"]`), b = box.querySelector(`.clip[data-v="${p.b.v}"]`);
      if (!a || !b) return '';
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      const x1 = ra.left - B.left + ra.width / 2, y1 = ra.bottom - B.top + 2;
      const x2 = rb.left - B.left + rb.width / 2, y2 = rb.bottom - B.top + 2;
      const cy = Math.max(y1, y2) + 18;
      const dash = p.kind === 'cambio' ? '' : ' stroke-dasharray="4 4"';
      return `<path d="M${x1},${y1} Q${(x1 + x2) / 2},${cy + 10} ${x2},${y2}"${dash}/><text x="${(x1 + x2) / 2}" y="${cy + 14}" text-anchor="middle">${p.kind === 'cambio' ? 'cambio' : 'repite'}</text>`;
    }).join('');
    box.style.paddingBottom = th.contrasts.length ? '30px' : '6px';
  }
  function takeClaim(c, v, doc) {
    const full = doc ? CR.claim(doc, c.id) : null;
    const quote = full && full.literal ? full.literal.cita : c.quote;
    const key = `c:${v.id}:${c.id}`;
    return `<div class="take">
      <p class="take-h"><span><span class="tc">${c.t != null ? fmtT(c.t) : 'título'}</span> · ${L.tipo[c.tipo]} · ${L.verif[c.verif]}</span><button class="btn-line" type="button" data-act="seek" data-t="${c.t || 0}">${icon('play')} Escuchar</button></p>
      ${quote ? `<p class="quote">${esc(quote)}</p>` : ''}
      <p class="lbl sys" style="margin-top:8px">Lectura del sistema</p><p class="reading">${esc(c.text)}</p>
      <button class="btn-line" type="button" data-act="keep" data-v="${v.id}" data-c="${c.id}" style="color:var(--ink-2)">${icon(saved.has(key) ? 'bookmark-fill' : 'bookmark')} ${saved.has(key) ? 'Clip guardado' : 'Guardar clip'}</button>
    </div>`;
  }
  function plateHtml(p) {
    const { th, s, v, doc } = mesa;
    const a = doc.analysis;
    const ids = new Set(s.claims);
    const touch = (list) => list.some((x) => ids.has(x));
    const claims = s.claims.map((id) => claimOf(v.id, id)).filter(Boolean).sort((x, y) => (x.t || 0) - (y.t || 0));
    const full = a ? s.claims.map((id) => CR.claim(doc, id)).filter(Boolean) : [];
    const evs = [];
    full.forEach((c) => c.evidences.forEach((e) => { if (!evs.find((x) => x.id === e.id)) evs.push(e); }));
    const noA = `<p class="pending-p">Este clip no está analizado: solo hay lo que dice, sin lectura del sistema.</p>`;
    const contrasts = th.contrasts.map((i) => idx.contrasts[i]);
    let body = '';
    let sub = '';
    if (p === 0) {
      sub = `${v.channel.name} · ${fmtDate(v.pub)}`;
      body = a ? `<p class="lbl" style="margin-top:12px">Resumen del sistema de lo que dice</p><p style="font-size:15.5px;margin-top:2px">${esc(a.resumen.mensaje_explicito)}</p>${claims.map((c) => takeClaim(c, v, doc)).join('')}<p class="built">fragmentos ${evs.length} → afirmaciones ${claims.length}</p>`
        : `${noA}${s.frags.map((f) => `<div class="take"><p class="take-h"><span class="tc">${fmtT(f.t)}</span><button class="btn-line" type="button" data-act="seek" data-t="${f.t}">${icon('play')} Escuchar</button></p><p class="quote">${esc(f.text)}</p></div>`).join('')}<p class="built">fragmentos ${s.frags.length} (por palabras clave) → afirmaciones 0</p>`;
    } else if (p === 1) {
      sub = a ? CR.plural(evs.length, 'fragmento citado', 'fragmentos citados') : 'Sin análisis';
      body = a ? `${evs.map((e) => `<div class="take"><p class="take-h"><span>${e.origen === 'titulo' ? 'Título del vídeo' : `<span class="tc">${fmtT(e.inicio_s)}</span> · ${L.origen[e.origen]}`}</span>${e.inicio_s != null ? `<button class="btn-line" type="button" data-act="seek" data-t="${e.inicio_s}">${icon('play')} Escuchar</button>` : ''}</p>${e.cita ? `<p class="quote">${esc(e.cita)}</p>` : ''}${e.observacion ? `<p style="font-size:13.5px;color:var(--muted-p);margin-top:4px">Nota del sistema: ${esc(e.observacion)}</p>` : ''}</div>`).join('')}
          <p class="lbl sys" style="margin-top:12px">Lo que se puede demostrar con lo recibido</p><p class="reading">${esc(a.resumen.respaldo_demostrable)}</p>
          <p class="ext-none">${icon('alert')}<span><b>Fuentes externas: 0.</b> Un fragmento prueba que se dijo, no que sea cierto.</span></p>`
        : `${noA}<p class="ext-none">${icon('alert')}<span>Sin análisis no se identificaron pruebas.</span></p>`;
    } else if (p === 2) {
      const chains = a ? a.cadena_narrativa.filter((ch) => touch(ch.afirmacion_ids)) : [];
      const scen = a ? a.escenarios.filter((x) => touch(x.afirmacion_ids)) : [];
      sub = a ? `${CR.plural(chains.length, 'paso', 'pasos')} · ${CR.plural(scen.length, 'escenario', 'escenarios')}` : 'Sin análisis';
      body = a ? `${chains.map((ch) => `<div class="take"><p style="font-size:15px">${esc(ch.premisa)}</p><p style="font-size:15px;margin-top:4px"><b>→ ${esc(ch.conclusion)}</b></p>${ch.supuesto ? `<p class="lbl sys" style="margin-top:8px">Supuesto · ${L.vinculo[ch.vinculo].toLowerCase()}</p><p class="reading">${esc(ch.supuesto)}</p>` : ''}</div>`).join('')}${scen.map((x) => `<div class="take"><p class="lbl">${L.origenEsc[x.origen]} · ${L.plaus[x.plausibilidad].toLowerCase()}</p><p style="font-weight:700;margin-top:4px">${esc(x.nombre)}</p><ul style="margin-top:6px;display:grid;gap:4px;font-size:14px;color:var(--ink-2)">${x.supuestos.map((u) => `<li>— ${esc(u)}</li>`).join('')}</ul></div>`).join('') || '<p class="pending-p">El análisis no ligó estas afirmaciones a supuestos explícitos.</p>'}` : noA;
    } else if (p === 3) {
      const others = th.sources.filter((x) => x.v !== v.id);
      sub = `${CR.plural(others.length, 'fuente más', 'fuentes más')}${contrasts.length ? ` · ${CR.plural(contrasts.length, 'marca', 'marcas')}` : ''}`;
      body = `${contrasts.map((c) => {
        const A = claimOf(c.a.v, c.a.id), B2 = claimOf(c.b.v, c.b.id);
        const va = idx.videosById[c.a.v], vb = idx.videosById[c.b.v];
        return `<div class="vs"><p class="vs-h">${c.kind === 'cambio' ? `<span class="pencil">Cambio de postura sobre ${esc(CR.topicName(c.asset))}</span>` : `Idea repetida sobre ${esc(CR.topicName(c.asset))}`}</p>
          ${[[A, va], [B2, vb]].map(([cl, vv]) => `<div class="vs-card"><p class="take-h"><span class="tc">${fmtDate(vv.pub)} · ${fmtT(cl.t)}</span><button class="btn-line" type="button" data-act="jump" data-v="${vv.id}" data-t="${cl.t || 0}">${icon('play')} ${vv.id === v.id ? 'Escuchar' : 'Ir al clip'}</button></p>${cl.quote ? `<p class="quote" style="font-size:16.5px">${esc(cl.quote)}</p>` : ''}<p class="reading" style="margin-top:4px">Postura extraída: ${esc(noDot(cl.postura || cl.text))}.</p></div>`).join('')}
          <p style="font-size:13px;color:var(--muted-p);margin-top:6px">${c.kind === 'cambio' ? 'Marcado por reglas: mismo activo y plazo, postura contraria. No decide quién acierta.' : 'La repite el mismo creador: repetición, no una prueba independiente.'}</p></div>`;
      }).join('')}
      ${others.map((x) => { const ov = idx.videosById[x.v]; const cl = x.claims.map((id) => claimOf(ov.id, id)).filter(Boolean)[0]; const fr = x.frags[0]; return `<div class="take"><p class="take-h"><span><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${track(ov.ch)};margin-right:6px"></i>${esc(ov.channel.name)} · ${fmtDate(ov.pub)} · ${x.claims.length ? 'analizado' : 'transcripción'}</span><button class="btn-line" type="button" data-act="clip" data-v="${ov.id}">Ir al clip ${icon('arrow-right')}</button></p>${cl ? `${cl.quote ? `<p class="quote" style="font-size:16px">${esc(cl.quote)}</p>` : ''}<p class="reading" style="margin-top:4px">${esc(cl.text)}</p>` : fr ? `<p class="quote" style="font-size:16px">${esc(fr.text)}</p><p style="font-size:13px;color:var(--muted-p);margin-top:4px">Literal en ${fmtT(fr.t)}; sin análisis.</p>` : ''}</div>`; }).join('')}
      <p class="ext-none">${icon('users')}<span>${CR.plural(th.videoCount, 'vídeo', 'vídeos')} de ${CR.plural(th.creators.length, 'creador', 'creadores')} tratan la idea; <b>0 fuentes externas</b> la respaldan.</span></p>
      <p class="built">clips ${th.videoCount} → cambios ${contrasts.filter((c) => c.kind === 'cambio').length} · repeticiones ${contrasts.filter((c) => c.kind !== 'cambio').length}</p>`;
    } else if (p === 4) {
      const pend = a ? a.verificaciones_pendientes.filter((x) => touch(x.afirmacion_ids)) : [];
      const watch = a ? a.seguimiento.filter((x) => touch(x.afirmacion_ids)) : [];
      sub = a ? CR.plural(pend.length + watch.length, 'pendiente', 'pendientes') : 'Falta el análisis';
      body = a ? `${pend.map((x) => `<div class="take"><p class="lbl red">${L.prioridad[x.prioridad]}</p><p style="font-size:15.5px;margin-top:2px">${esc(x.pregunta)}</p><p style="font-size:13px;color:var(--muted-p);margin-top:4px">Buscar: ${esc(x.fuente_o_dato_buscado)}</p></div>`).join('')}${watch.map((w) => `<div class="take"><p class="lbl sys">Qué vigilar</p><p style="font-size:15.5px;margin-top:2px">${esc(w.que_observar)}</p><p style="font-size:13px;color:var(--muted-p);margin-top:4px">${esc(w.criterio)}${w.plazo ? ` · ${esc(w.plazo)}` : ''}</p></div>`).join('') || '<p class="pending-p">Sin preguntas abiertas sobre estas afirmaciones.</p>'}`
        : `<p class="pending-p">La pregunta abierta es el propio clip: no se ha analizado.</p><button class="btn-p" type="button" data-act="demo" style="margin-top:12px">${icon('flask')} Pedir el análisis</button>`;
    } else {
      const vids = th.sources.map((x) => idx.videosById[x.v]).sort((x, y) => x.pub.localeCompare(y.pub));
      sub = 'Redactada con los datos de la mesa';
      const jump = (c) => `<button class="btn-line" type="button" data-act="jump" data-v="${c.v}" data-t="${c.t || 0}" style="min-height:0;display:inline"><span class="tc">${fmtDate(idx.videosById[c.v].pub)} ${fmtT(c.t)}</span></button>`;
      let txt = `La pregunta aparece en ${CR.plural(th.videoCount, 'vídeo', 'vídeos')} de ${esc(joinEs(th.creators.map((c) => idx.channelsBySlug[c].name)))} entre el ${fmtDate(vids[0].pub)} y el ${fmtDate(vids[vids.length - 1].pub)}; ${th.analyzedCount === 1 ? 'uno está analizado' : `${th.analyzedCount} están analizados`}.`;
      contrasts.forEach((c) => {
        const A = claimOf(c.a.v, c.a.id), B2 = claimOf(c.b.v, c.b.id);
        txt += c.kind === 'cambio'
          ? ` Sobre ${esc(CR.topicName(c.asset))} la postura cambia: «${esc(lowerFirst(noDot(A.postura)))}» (${jump(A)}) y después «${esc(lowerFirst(noDot(B2.postura)))}» (${jump(B2)}).`
          : ` Se repite una idea sobre ${esc(CR.topicName(c.asset))}: «${esc(lowerFirst(noDot(A.postura)))}» (${jump(A)}) y «${esc(lowerFirst(noDot(B2.postura)))}» (${jump(B2)}).`;
      });
      body = `<p style="font-size:16.5px;line-height:1.6;margin-top:12px">${txt} Ninguna fuente externa la respalda ni la contradice: es una lectura de lo dicho, no una conclusión.</p>
        <p class="built">clips ${th.videoCount} → afirmaciones ${th.claimCount} → marcas ${contrasts.length} → síntesis</p>`;
    }
    return `<article class="plate paper" id="plate" aria-live="polite"><p class="plate-n">PLANO ${p + 1}/${PLATES.length}</p><h2>${PLATES[p]}</h2><p class="plate-sub">${esc(sub)}</p>${body}</article>`;
  }
  function platesNav(p) {
    const hasRed = mesa.th.contrasts.some((i) => idx.contrasts[i].kind === 'cambio');
    return `<div class="plates-nav"><button class="nav-arrow" type="button" data-act="plate" data-d="-1" aria-label="Plano anterior"${p === 0 ? ' disabled' : ''}>${icon('chevron-left')}</button>
      <div class="plate-dots" role="group" aria-label="Planos">${PLATES.map((t, i) => `<button class="plate-dot${i === 3 && hasRed ? ' has-red' : ''}" type="button" data-act="plate-go" data-p="${i}"${i === p ? ' aria-current="step"' : ''} aria-label="Plano ${i + 1}: ${t}">${i === 5 ? 'S' : i + 1}</button>`).join('')}</div>
      <button class="nav-arrow" type="button" data-act="plate" data-d="1" aria-label="Plano siguiente"${p === PLATES.length - 1 ? ' disabled' : ''}>${icon('chevron-right')}</button></div>`;
  }
  function setPlate(p) {
    mesa.p = Math.max(0, Math.min(PLATES.length - 1, p));
    document.getElementById('plates').innerHTML = platesNav(mesa.p) + plateHtml(mesa.p);
    history.replaceState(history.state, '', CR.hash(['mesa', mesa.th.id], { v: mesa.v.id, p: mesa.p }));
    store.set('mesa', { th: mesa.th.id, v: mesa.v.id, p: mesa.p, t: player ? player.time() : 0 });
    bindSwipe();
  }
  function bindSwipe() {
    const el = document.getElementById('plate');
    if (!el) return;
    let x0 = null, y0 = null;
    el.addEventListener('pointerdown', (e) => { x0 = e.clientX; y0 = e.clientY; });
    el.addEventListener('pointerup', (e) => {
      if (x0 == null) return;
      const dx = e.clientX - x0, dy = e.clientY - y0;
      x0 = null;
      if (Math.abs(dx) > 70 && Math.abs(dx) > Math.abs(dy) * 1.6) setPlate(mesa.p + (dx < 0 ? 1 : -1));
    });
  }
  async function renderMesa(id, q, same) {
    const th = idx.themesById[id];
    if (!th) { desk.innerHTML = `<div class="empty"><h3>Esta mesa no existe</h3><p><a href="#/" style="text-decoration:underline">Volver a la sala</a></p></div>`; return; }
    const s = th.sources.find((x) => x.v === q.v) || th.sources.find((x) => x.claims.length) || th.sources[0];
    const v = idx.videosById[s.v];
    const keepY = same ? window.scrollY : 0;
    if (!same) desk.innerHTML = '<div class="pad"><div class="skel" style="height:30px;margin-top:16px"></div></div><div class="skel" style="aspect-ratio:16/9;margin-top:12px;border-radius:0"></div>';
    let doc;
    try { doc = await CR.loadVideo(v.id); } catch (e) {
      desk.innerHTML = `<div class="err" role="alert"><h3>No se pudo cargar el clip</h3><p>Prueba con otro clip de la línea de tiempo o reintenta.</p><button class="btn-d" type="button" data-act="retry">${icon('refresh')} Reintentar</button></div>`;
      return;
    }
    if (screen !== `mesa:${id}`) return;
    const videoChanged = !mesa.v || mesa.v.id !== v.id || !player;
    Object.assign(mesa, { th, s, v, doc, p: q.p != null ? Number(q.p) : same ? mesa.p : 0 });
    const sess = store.get('session', null);
    const first = (() => { const ts = s.claims.map((cid) => doc.claimsById[cid]).filter((c) => c && c.t != null).map((c) => c.t); return ts.length ? Math.min(...ts) : s.frags.length ? s.frags[0].t : 0; })();
    const start = q.t != null ? Number(q.t) : sess && sess.v === v.id ? sess.t : first;
    if (videoChanged) {
      desk.innerHTML = `
        <div class="mesa-head"><p class="label-d">Mesa · ${CR.plural(th.videoCount, 'clip', 'clips')}</p><h1 class="h-desk" style="font-size:26px;margin-top:2px">${esc(th.title)}</h1></div>
        <div class="visor${v.short ? ' is-short' : ''}"><span class="visor-tc tc" id="visor-tc">${fmtT(start)} / ${fmtT(v.dur)}</span><div id="visor" style="position:absolute;inset:0"></div></div>
        <div class="visor-meta" id="visor-meta"></div>
        <div id="tl-wrap"></div>
        <div id="plates"></div>`;
      mount(document.getElementById('visor'), v, start);
    } else if (q.t != null) {
      player.seek(Number(q.t), { play: true });
    }
    document.getElementById('visor-meta').innerHTML = `<span><b style="color:${track(v.ch)}">●</b> <b>${esc(v.channel.name)}</b> · ${fmtDate(v.pub, { time: true })} · ${v.analysis ? 'analizado' : 'solo transcripción'}</span><a class="btn-line" href="#/fuente/${v.id}">Visor de fuente ${icon('arrow-up-right')}</a>`;
    document.getElementById('tl-wrap').innerHTML = timelineHtml(th, v.id);
    requestAnimationFrame(() => drawMarks(th));
    document.getElementById('plates').innerHTML = platesNav(mesa.p) + plateHtml(mesa.p);
    bindSwipe();
    store.set('mesa', { th: th.id, v: v.id, p: mesa.p, t: start });
    updateConsole('mesa');
    if (same) window.scrollTo(0, keepY);
  }
  window.addEventListener('resize', CR.debounce(() => { if (mesa.th && screen && screen.startsWith('mesa:')) drawMarks(mesa.th); }, 150));

  /* ---------- fuentes ---------- */
  function binRow(v) {
    return `<a class="bin-row" href="#/fuente/${v.id}"><img src="${CR.thumb(v.id)}" alt="" loading="lazy"><span><b>${esc(v.cleanTitle)}</b><small>${fmtDate(v.pub, { time: true })} · ${v.analysis ? `${v.analysis.claims} afirmaciones` : 'sin analizar'}</small></span><span class="tc">${fmtT(v.dur)}</span></a>`;
  }
  function renderBins() {
    const byDate = ui.binMode === 'fecha';
    const groups = byDate
      ? [...new Set(idx.videos.map((v) => CR.dayKey(v.pub)))].map((k) => ({ name: CR.dayLabel(idx.videos.find((v) => CR.dayKey(v.pub) === k).pub), color: null, list: idx.videos.filter((v) => CR.dayKey(v.pub) === k) }))
      : idx.channels.map((c) => ({ name: c.name, color: track(c.slug), list: idx.videos.filter((v) => v.ch === c.slug) }));
    desk.innerHTML = `<div class="pad" style="padding-top:16px"><h1 class="h-desk">Fuentes</h1><p class="sub-desk">Todos los clips del archivo. Ábrelos en el visor o llévalos a una mesa.</p></div>
      <div class="seg-d" role="tablist" aria-label="Agrupar"><button type="button" role="tab" data-act="bins" data-m="creador" aria-selected="${!byDate}">Por creador</button><button type="button" role="tab" data-act="bins" data-m="fecha" aria-selected="${byDate}">Por día</button></div>
      <div class="bins" style="margin-top:14px">${groups.map((g) => `<section class="bin"><h2 class="bin-h"><span>${g.color ? `<i style="background:${g.color}"></i>` : icon('calendar', 'i-s')}${esc(g.name)}</span><span class="tc" style="color:var(--muted-d);font-size:13px">${g.list.length}</span></h2>${g.list.map(binRow).join('')}</section>`).join('')}</div>`;
  }
  async function renderSource(id, q) {
    const v = idx.videosById[id];
    if (!v) { desk.innerHTML = `<div class="empty"><h3>Clip no encontrado</h3></div>`; return; }
    desk.innerHTML = '<div class="skel" style="aspect-ratio:16/9;border-radius:0"></div>';
    let doc;
    try { doc = await CR.loadVideo(id); } catch (e) {
      desk.innerHTML = `<div class="err" role="alert"><h3>No se pudo abrir el clip</h3><button class="btn-d" type="button" data-act="retry">${icon('refresh')} Reintentar</button></div>`;
      return;
    }
    if (screen !== `fuente:${id}`) return;
    const sess = store.get('session', null);
    const start = q.t != null ? Number(q.t) : sess && sess.v === id ? sess.t : 0;
    const claims = (doc.claims || []).slice().sort((a, b) => (a.t == null ? -1 : a.t) - (b.t == null ? -1 : b.t));
    const rows = claims.length ? claims.map((c) => ({ t: c.t, kind: L.tipo[c.tipo], text: c.text, c })) : CR.blocks(doc.segments, 40).map((b) => ({ t: b.start, kind: 'Transcripción', text: b.text }));
    const themes = idx.themes.filter((th) => th.sources.some((s) => s.v === id));
    desk.innerHTML = `
      <div class="visor${v.short ? ' is-short' : ''}"><span class="visor-tc tc" id="visor-tc">${fmtT(start)} / ${fmtT(v.dur)}</span><div id="visor" style="position:absolute;inset:0"></div></div>
      <div class="pad" style="padding-top:14px"><p class="label-d"><b style="color:${track(v.ch)}">●</b> ${esc(v.channel.name)} · ${fmtDate(v.pub, { time: true })} · ${v.analysis ? 'analizado' : 'solo transcripción'}</p><h1 class="h-desk" style="font-size:24px;margin-top:6px">${esc(v.cleanTitle)}</h1>
        ${themes.length ? `<p style="margin-top:10px;font-size:14px;color:var(--on-desk-2)">En las mesas: ${themes.map((th) => `<a href="#/mesa/${th.id}?v=${id}" style="text-decoration:underline;text-underline-offset:3px">${esc(th.short)}</a>`).join(' · ')}</p>` : ''}</div>
      <div class="sec-head"><h2>${claims.length ? 'Lista de planos' : 'Transcripción por tramos'}</h2><span>${rows.length}</span></div>
      <div class="edl" id="edl">${rows.map((r, i) => `<div class="edl-item" data-i="${i}"><button class="edl-row" type="button" data-act="edl" data-i="${i}" aria-expanded="false"><span class="tc">${r.t != null ? fmtT(r.t) : '—'}</span><span><b>${esc(r.kind)}</b><p>${esc(CR.clip(r.text, 150))}</p></span></button></div>`).join('')}</div>`;
    mount(document.getElementById('visor'), v, start, (t) => {
      let now = -1;
      rows.forEach((r, i) => { if (r.t != null && r.t <= t + 0.5) now = i; });
      CR.$$('.edl-row', desk).forEach((el) => el.classList.toggle('is-now', Number(el.dataset.i) === now));
    });
    ui.rows = rows; ui.doc = doc; ui.video = v;
  }
  function toggleEdl(btn) {
    const i = Number(btn.dataset.i);
    const r = ui.rows[i];
    const open = btn.getAttribute('aria-expanded') === 'true';
    CR.$$('.edl-row[aria-expanded="true"]', desk).forEach((el) => { el.setAttribute('aria-expanded', 'false'); el.classList.remove('is-open'); });
    CR.$$('.edl-detail', desk).forEach((d) => d.remove());
    if (player) player.seek(r.t || 0, { play: true });
    if (open || !r.c) return;
    const full = CR.claim(ui.doc, r.c.id);
    btn.setAttribute('aria-expanded', 'true');
    btn.classList.add('is-open');
    const key = `c:${ui.video.id}:${r.c.id}`;
    btn.insertAdjacentHTML('afterend', `<div class="edl-detail paper">${full.literal ? `<p class="quote">${esc(full.literal.cita)}</p>` : ''}<p class="lbl sys" style="margin-top:8px">Lectura del sistema · ${L.verif[r.c.verif]}</p><p class="reading">${esc(full.justificacion)}</p>${full.mercado && full.mercado.postura ? `<p style="margin-top:6px;font-size:13.5px;color:var(--ink-2)">Postura extraída: ${esc(full.mercado.postura)}</p>` : ''}<button class="btn-line" type="button" data-act="keep" data-v="${ui.video.id}" data-c="${r.c.id}" style="color:var(--ink-2)">${icon(saved.has(key) ? 'bookmark-fill' : 'bookmark')} ${saved.has(key) ? 'Clip guardado' : 'Guardar clip'}</button></div>`);
  }

  /* ---------- fichas ---------- */
  function renderDeck(sec) {
    const s = sec || ui.fs;
    ui.fs = s; store.set('fs', s);
    const rows = idx.topics.filter((t) => t.section === s).sort((a, b) => b.vc - a.vc || b.n - a.n);
    const cards = (s === 'altcoins' ? [idx.topicsById.btc] : []).concat(rows);
    const card = (t, i) => {
      const fr = t.videos[0] && t.videos[0].frags[0];
      const cl = t.claims[0] && claimOf(t.claims[0].v, t.claims[0].id);
      return `<article class="card paper"><p class="card-n">${t.id === 'btc' ? 'FUERA DE RANKING' : `Nº ${String(i).padStart(2, '0')}`}</p><h3>${esc(t.name)}</h3>${t.sym ? `<span class="sym">${esc(t.sym)}</span>` : ''}
        <div class="card-stats"><span><b>${t.vc}</b><small>vídeos</small></span><span><b>${t.n}</b><small>menciones</small></span><span><b>${t.claims.length}</b><small>analizadas</small></span></div>
        ${cl && cl.quote ? `<p class="quote">${esc(cl.quote)}</p>` : fr ? `<p class="quote">${esc(fr.text)}</p>` : ''}
        <a class="btn-p" href="#/ficha/${t.id}">Abrir ficha ${icon('arrow-right')}</a></article>`;
    };
    desk.innerHTML = `<div class="pad" style="padding-top:16px"><h1 class="h-desk">Fichas</h1><p class="sub-desk">Una ficha por activo, ordenadas por número de vídeos que lo nombran. Desliza la baraja.</p></div>
      <div class="seg-d" role="tablist" aria-label="Secciones">${['altcoins', 'macro', 'bolsa'].map((k) => `<a role="tab" href="#/fichas?s=${k}" aria-selected="${k === s}">${L.section[k]}</a>`).join('')}</div>
      <div class="deck" data-scroll-x>${cards.map((t) => card(t, rows.indexOf(t) + 1)).join('')}</div>
      <p class="deck-hint">${cards.length} fichas · ${esc(idx.method.mentions)}</p>
      <div class="sec-head"><h2>Ranking completo</h2><span>${L.section[s]}</span></div>
      <div class="bins"><section class="bin">${rows.map((t, i) => `<a class="bin-row" href="#/ficha/${t.id}" style="grid-template-columns:34px 1fr auto"><span class="tc" style="font-size:14px">${String(i + 1).padStart(2, '0')}</span><span><b>${esc(t.name)}</b><small>${CR.plural(t.vc, 'vídeo', 'vídeos')} · ${CR.plural(t.cc, 'creador', 'creadores')}${t.claims.length ? ` · ${t.claims.length} analizada${t.claims.length > 1 ? 's' : ''}` : ''}</small></span><span class="tc">${t.n}</span></a>`).join('')}</section></div>`;
  }
  function renderFicha(id, tab = 'videos') {
    const t = idx.topicsById[id];
    if (!t) { desk.innerHTML = `<div class="empty"><h3>Ficha no encontrada</h3></div>`; return; }
    const claims = t.claims.map((k) => claimOf(k.v, k.id)).filter(Boolean);
    const stance = (c) => c.own || ['prediccion', 'hipotesis', 'opinion'].includes(c.tipo);
    const TABS = [['videos', 'Vídeos'], ['argumentos', 'Argumentos'], ['fechas', 'Fechas'], ['cambios', 'Cambios'], ['evidencia', 'Evidencia']];
    const cl = (c) => { const v = idx.videosById[c.v]; return `<div class="take"><p class="take-h"><span class="tc">${fmtDate(v.pub)} · ${fmtT(c.t)}</span><a class="btn-line" href="#/fuente/${v.id}?t=${Math.floor(c.t || 0)}">${icon('play')} Escuchar</a></p>${c.quote ? `<p class="quote" style="font-size:16.5px">${esc(c.quote)}</p>` : ''}<p class="reading" style="margin-top:4px">${esc(c.text)}</p></div>`; };
    let body = '';
    if (tab === 'videos') body = `<h3>Vídeos que la mencionan</h3>${t.videos.map((m) => { const v = idx.videosById[m.v]; return `<a class="vrow" href="#/fuente/${v.id}?t=${Math.floor(m.frags[0] ? m.frags[0].t : 0)}"><img src="${CR.thumb(v.id)}" alt="" loading="lazy"><span><b>${esc(v.cleanTitle)}</b><small>${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${CR.plural(m.n, 'mención', 'menciones')}</small></span></a>`; }).join('')}`;
    else if (tab === 'argumentos') {
      const fav = claims.filter((c) => stance(c) && c.dir === 'alcista');
      const con = claims.filter((c) => stance(c) && (c.dir === 'bajista' || c.dir === 'mixta'));
      body = `<h3>A favor · ${fav.length}</h3>${fav.map(cl).join('') || '<p class="pending-p">Ninguna postura analizada a favor.</p>'}<h3 style="margin-top:18px">Objeciones o a la baja · ${con.length}</h3>${con.map(cl).join('') || '<p class="pending-p">Ninguna postura analizada en contra.</p>'}<p class="built">clasificación por la postura extraída</p>`;
    } else if (tab === 'fechas') {
      const dated = claims.filter((c) => c.plazo);
      body = `<h3>Catalizadores y plazos citados</h3>${dated.map((c) => `<div class="take"><p class="lbl red">${esc(c.plazo)}</p>${cl(c).replace('<div class="take">', '<div>')}</div>`).join('') || '<p class="pending-p">Ninguna afirmación analizada cita un plazo.</p>'}`;
    } else if (tab === 'cambios') {
      const ch = idx.contrasts.filter((p) => p.asset === id);
      body = `<h3>Cambios del discurso</h3>${ch.map((p) => { const A = claimOf(p.a.v, p.a.id), B = claimOf(p.b.v, p.b.id); return `<div class="vs"><p class="vs-h">${p.kind === 'cambio' ? '<span class="pencil">Cambio de postura</span>' : 'Idea repetida'} · ${L.hz[p.hz].toLowerCase()}</p>${[A, B].map((c) => `<div class="vs-card">${cl(c).replace('<div class="take">', '<div>')}</div>`).join('')}</div>`; }).join('') || `<p class="pending-p">No hay cambios detectados${claims.length < 2 ? ': hace falta más de un vídeo analizado que hable de esto' : ''}.</p>`}`;
    } else {
      body = `<h3>Evidencia aportada y datos que faltan</h3>${claims.length ? `<p style="margin-top:8px;font-size:14.5px">${Object.entries(claims.reduce((acc, c) => { acc[L.verif[c.verif]] = (acc[L.verif[c.verif]] || 0) + 1; return acc; }, {})).map(([k, n]) => `${n} ${k.toLowerCase()}`).join(' · ')}</p>` : ''}
        <p class="ext-none">${icon('alert')}<span><b>Fuentes externas consultadas: 0.</b> Para verificar haría falta precio fechado, calendarios oficiales y los gráficos citados.</span></p>`;
    }
    desk.innerHTML = `<div class="pad" style="padding-top:14px"><a class="btn-line" href="#/fichas?s=${t.section === 'bitcoin' ? 'altcoins' : t.section}" style="color:var(--on-desk-2)">${icon('arrow-left')} Fichas</a><h1 class="h-desk" style="margin-top:4px;font-size:36px">${esc(t.name)}</h1><p class="sub-desk">${L.section[t.section]} · ${CR.plural(t.vc, 'vídeo', 'vídeos')} · ${CR.plural(t.n, 'mención', 'menciones')} · ${CR.plural(claims.length, 'afirmación analizada', 'afirmaciones analizadas')}${t.note ? `. Ojo: ${esc(t.note)}` : ''}</p></div>
      <div class="ficha-tabs"><div class="seg-d" role="tablist" aria-label="Apartados de la ficha" data-scroll-x>${TABS.map(([k, l]) => `<a role="tab" href="#/ficha/${id}?tab=${k}" aria-selected="${k === tab}">${l}</a>`).join('')}</div></div>
      <article class="ficha-body paper">${body}</article>`;
  }

  /* ---------- marcas, guardados, búsqueda, estados ---------- */
  function renderMarks() {
    desk.innerHTML = `<div class="pad" style="padding-top:16px"><h1 class="h-desk">Marcas en rojo</h1><p class="sub-desk">Donde una postura cambia o se repite entre vídeos. Cada marca abre la mesa en el plano 4.</p></div><div style="margin-top:16px">${idx.contrasts.map(markCard).join('')}</div><p class="pad" style="font-size:13px;color:var(--muted-d)">${esc(idx.method.contrasts)}</p>`;
  }
  function renderSaved() {
    const list = saved.all();
    desk.innerHTML = `<div class="pad" style="padding-top:16px"><h1 class="h-desk">Clips guardados</h1><p class="sub-desk">Citas apartadas para el montaje, con su segundo exacto.</p></div>
      ${list.length ? list.map((s) => `<article class="saved-card paper"><p class="lbl">${esc(s.sub)}</p>${s.quote ? `<p class="quote" style="margin-top:4px">${esc(s.quote)}</p>` : ''}<p class="reading" style="margin-top:6px">${esc(s.title)}</p><div class="saved-foot"><a class="btn-line" href="${esc(s.href)}">${icon('play')} Volver al clip</a><button class="btn-line" type="button" data-act="unkeep" data-key="${esc(s.key)}" style="color:var(--muted-p)">Quitar</button></div></article>`).join('')
        : `<div class="empty"><h3>Sin clips guardados</h3><p>En cualquier plano pulsa «Guardar clip» para apartar una cita y volver luego a su segundo.</p><a class="btn-d" href="${document.getElementById('c-main').getAttribute('href')}">${icon('film')} Ir al montaje</a></div>`}`;
  }
  function renderSearch(q) {
    desk.innerHTML = `<label class="search">${icon('search')}<span class="sr">Buscar</span><input id="q" type="search" value="${esc(q)}" placeholder="Mesas, clips, activos, citas…" autocomplete="off" enterkeyhint="search"></label><div id="res"></div>`;
    const input = document.getElementById('q');
    const run = () => {
      const val = input.value.trim();
      CR.go(['buscar'], { q: val }, { replace: true });
      const out = document.getElementById('res');
      if (!val) { out.innerHTML = '<p class="pad" style="margin-top:16px;color:var(--muted-d)">Prueba con «largos», «Cosmos» o «inflación».</p>'; return; }
      const r = CR.search(val);
      const g = (h, items) => (items.length ? `<h2 class="res-h">${h}</h2>${items.join('')}` : '');
      out.innerHTML = g('Mesas', r.themes.map((t) => `<a class="res" href="#/mesa/${t.id}"><p>${esc(t.title)}</p></a>`))
        + g('Citas analizadas', r.claims.slice(0, 10).map((c) => { const v = idx.videosById[c.v]; return `<a class="res" href="#/fuente/${v.id}?t=${Math.floor(c.t || 0)}"><p>${esc(c.text)}</p><small>${esc(v.channel.name)} · <span class="tc">${fmtT(c.t)}</span></small></a>`; }))
        + g('Fichas', r.topics.slice(0, 8).map((t) => `<a class="res" href="#/ficha/${t.id}"><p>${esc(t.name)}</p><small>${CR.plural(t.vc, 'vídeo', 'vídeos')}</small></a>`))
        + g('Clips', r.videos.slice(0, 8).map((v) => `<a class="res" href="#/fuente/${v.id}"><p>${esc(v.cleanTitle)}</p><small>${esc(v.channel.name)} · ${fmtDate(v.pub)}</small></a>`))
        + `<div class="pad" style="margin-top:16px"><button class="btn-d" type="button" data-act="search-tx" style="width:100%">${icon('text')} Buscar también en las transcripciones</button></div><div id="txr"></div>`;
    };
    input.addEventListener('input', CR.debounce(run, 200));
    run();
    input.focus();
  }
  async function searchTx() {
    const val = document.getElementById('q').value;
    const out = document.getElementById('txr');
    out.innerHTML = '<div class="pad"><div class="skel" style="height:60px;margin-top:12px"></div></div>';
    const hits = await CR.searchTranscripts(val);
    out.innerHTML = hits.length ? `<h2 class="res-h">En las transcripciones</h2>${hits.map((h) => { const v = idx.videosById[h.v]; return `<a class="res" href="#/fuente/${v.id}?t=${Math.floor(h.t)}"><p>«${esc(h.text)}»</p><small>${esc(v.channel.name)} · <span class="tc">${fmtT(h.t)}</span></small></a>`; }).join('')}` : `<p class="pad" style="margin-top:12px;color:var(--muted-d)">Ninguna transcripción contiene «${esc(val)}».</p>`;
  }
  function renderStates() {
    desk.innerHTML = `<div class="pad" style="padding-top:16px"><h1 class="h-desk">Estados</h1><p class="sub-desk">Cómo llega cada clip a la mesa según lo que el sistema pudo hacer.</p></div>
      ${CR.STATES.map((s) => `<article class="state paper"><h3>${esc(s.title)}<span>${s.real ? 'REAL' : 'EJEMPLO'}</span></h3><p>${esc(s.body)}</p><button class="btn-p" type="button" data-act="demo" style="margin-top:10px">${esc(s.action)}</button></article>`).join('')}`;
  }

  /* ---------- acciones ---------- */
  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-act]');
    if (!el) return;
    const act = el.dataset.act;
    switch (act) {
      case 'library': openLibrary(); break;
      case 'clip': CR.go(['mesa', mesa.th.id], { v: el.dataset.v, p: mesa.p }, { replace: true }); break;
      case 'jump': {
        if (mesa.v && mesa.v.id === el.dataset.v && player) player.seek(Number(el.dataset.t), { play: true });
        else CR.go(['mesa', mesa.th.id], { v: el.dataset.v, p: mesa.p, t: Math.floor(Number(el.dataset.t)) }, { replace: true });
        const vis = desk.querySelector('.visor'); if (vis) vis.scrollIntoView({ block: 'start', behavior: CR.reduced() ? 'auto' : 'smooth' });
        break;
      }
      case 'seek': {
        if (player) player.seek(Number(el.dataset.t), { play: true });
        const vis = desk.querySelector('.visor'); if (vis && vis.getBoundingClientRect().bottom < 60) vis.scrollIntoView({ block: 'start', behavior: CR.reduced() ? 'auto' : 'smooth' });
        break;
      }
      case 'plate': setPlate(mesa.p + Number(el.dataset.d)); break;
      case 'plate-go': setPlate(Number(el.dataset.p)); break;
      case 'edl': toggleEdl(el); break;
      case 'keep': {
        e.stopPropagation();
        const v = idx.videosById[el.dataset.v];
        const c = claimOf(v.id, el.dataset.c);
        const on = saved.toggle({ key: `c:${v.id}:${c.id}`, sub: `${v.channel.name} · ${fmtDate(v.pub)} · ${fmtT(c.t)}`, title: c.text, quote: c.quote, href: `#/fuente/${v.id}?t=${Math.floor(c.t || 0)}` });
        el.innerHTML = `${icon(on ? 'bookmark-fill' : 'bookmark')} ${on ? 'Clip guardado' : 'Guardar clip'}`;
        CR.toast(on ? 'Clip guardado' : 'Clip quitado', on ? { action: 'Ver', onAction: () => CR.go('#/guardados') } : {});
        break;
      }
      case 'unkeep': saved.remove(el.dataset.key); renderSaved(); break;
      case 'bins': ui.binMode = el.dataset.m; store.set('binMode', ui.binMode); renderBins(); break;
      case 'search-tx': searchTx(); break;
      case 'demo': CR.toast('Es un ejemplo: en el producto esta acción haría su trabajo.'); break;
      case 'reload': location.reload(); break;
      case 'retry': screen = null; route(CR.parseHash()); break;
      default: break;
    }
  });
  scrim.addEventListener('click', closeLibrary);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !lib.hidden) closeLibrary(); });
  window.addEventListener('pagehide', () => { if (player && playerVideo) store.set('session', { v: playerVideo.id, t: player.time() }); });

  const run = CR.onRoute(route);
  run();
})();

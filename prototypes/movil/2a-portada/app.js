/* 2A · Portada — sala editorial como diario: portada, narrativas con capítulos, desacuerdos y dossiers. */
(() => {
  'use strict';
  const { esc, fmtT, fmtDate, icon, L } = CR;
  const APP = '2a';
  const store = CR.store(APP);
  const saved = CR.saved(APP);
  const ed = document.getElementById('edicion');
  const nowbar = document.getElementById('nowbar');
  const resume = document.getElementById('resume');

  let idx = null;
  let screen = null;
  let player = null;
  let playerVideo = null;
  let observer = null;
  const scrolls = new Map();
  const ui = { caps: new Set(store.get('caps', [1])), vf: store.get('vf', 'todos'), ds: store.get('ds', 'altcoins') };

  const joinEs = (a) => (a.length <= 1 ? a.join('') : `${a.slice(0, -1).join(', ')} y ${a[a.length - 1]}`);
  const lowerFirst = (s) => (s ? s.charAt(0).toLowerCase() + s.slice(1) : s);
  const noDot = (s) => String(s || '').replace(/[.\s]+$/, '');
  const claimOf = (v, id) => idx.claimsByKey[`${v}:${id}`];
  const status = (v) => (v.analysis ? `<span class="status ok">Con análisis</span>` : `<span class="status wait">Solo transcripción</span>`);
  const byline = (v) => `<p class="byline"><b>${esc(v.channel.name)}</b><span>${fmtDate(v.pub, { time: true })}</span><span>${v.short ? 'Short' : CR.fmtDur(v.dur)}</span>${status(v)}</p>`;
  const sessionGet = () => store.get('session', null);

  /* ---------- reproductor en la página (se recrea por pantalla y retoma el segundo) ---------- */
  function unmountPlayer() {
    if (observer) { observer.disconnect(); observer = null; }
    if (player) {
      if (playerVideo) store.set('session', { v: playerVideo.id, t: player.time() });
      player.destroy();
    }
    player = null; playerVideo = null;
    nowbar.hidden = true;
  }
  function mountPlayer(host, v, start) {
    unmountPlayer();
    player = new CR.Player(host);
    playerVideo = v;
    let last = 0;
    player.on('time', (t) => {
      if (Date.now() - last > 3000) { last = Date.now(); store.set('session', { v: v.id, t }); }
      document.getElementById('np-text').textContent = `${fmtT(t)} · ${v.channel.name} · ${v.cleanTitle}`;
    });
    player.on('state', (s) => {
      const btn = document.getElementById('np-toggle');
      btn.innerHTML = icon(s === 'playing' ? 'pause' : 'play');
      btn.setAttribute('aria-label', s === 'playing' ? 'Pausar' : 'Reproducir');
      if (s === 'needs-tap') CR.toast('Toca el vídeo para empezar a reproducir');
    });
    player.load(v, { start });
    document.getElementById('np-text').textContent = `${fmtT(start)} · ${v.channel.name} · ${v.cleanTitle}`;
    observer = new IntersectionObserver(([entry]) => { nowbar.hidden = entry.isIntersecting; }, { rootMargin: '-100px 0px 0px 0px' });
    observer.observe(host);
  }
  function seek(t, play = true) {
    if (!player) return;
    player.seek(t, { play });
    const host = ed.querySelector('.player');
    if (host && host.getBoundingClientRect().bottom < 110) host.scrollIntoView({ block: 'center', behavior: CR.reduced() ? 'auto' : 'smooth' });
  }
  function updateResume() {
    const s = sessionGet();
    const v = s && idx && idx.videosById[s.v];
    const show = v && !player && !['buscar'].includes(screen);
    resume.hidden = !show;
    if (show) {
      resume.href = `#/video/${v.id}?t=${Math.floor(s.t)}`;
      resume.innerHTML = `<span class="dot">${icon('play')}</span><span>Seguir viendo · ${fmtT(s.t)} · ${esc(v.cleanTitle)}</span>`;
    }
  }

  /* ---------- rutas ---------- */
  const NAV = { '': 'portada', narrativas: 'narrativas', explorar: 'narrativas', desacuerdos: 'desacuerdos', dossiers: 'dossiers', dossier: 'dossiers', videos: 'videos', video: 'videos', recortes: 'recortes' };
  async function route(r) {
    const [a = '', b] = r.parts;
    const key = a ? `${a}${b ? ':' + b : ''}` : 'portada';
    if (screen === key && a === 'explorar') { await renderExplore(b, r.q, true); return; }
    if (screen === key && a === 'buscar') return;
    if (screen) scrolls.set(screen, window.scrollY);
    screen = key;
    unmountPlayer();
    document.body.dataset.screen = a || 'portada';
    CR.$$('.sections-scroll a').forEach((el) => { if (el.dataset.s === NAV[a]) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current'); });
    if (!idx) {
      ed.innerHTML = '<div class="wrap"><div class="skel" style="height:40px;margin-top:20px"></div><div class="skel" style="height:220px;margin-top:16px"></div></div>';
      try { idx = await CR.load(); } catch (e) {
        ed.innerHTML = `<div class="err" role="alert"><h3>No se pudo cargar la edición</h3><p>Falló la conexión con los datos. Vuelve a intentarlo en un momento.</p><button class="cta" type="button" data-act="reload">${icon('refresh')} Reintentar</button></div>`;
        return;
      }
      document.getElementById('mast-line').textContent = `${CR.cap(CR.fmtDate(idx.videos[0].pub, { weekday: true }))} · ${idx.videos.length} vídeos · ${idx.analyzed.length} análisis · ${idx.channels.map((c) => c.name).join(' y ')}`;
    }
    if (a === 'narrativas') renderNarratives();
    else if (a === 'explorar') await renderExplore(b, r.q);
    else if (a === 'desacuerdos') renderDisagreements();
    else if (a === 'dossiers') renderDossiers(r.q.s);
    else if (a === 'dossier') renderDossier(b);
    else if (a === 'videos') renderVideos();
    else if (a === 'video') await renderVideo(b, r.q);
    else if (a === 'recortes') renderClips();
    else if (a === 'buscar') renderSearch(r.q.q || '');
    else if (a === 'estados') renderStates();
    else renderFront();
    updateResume();
    if (!['explorar', 'video'].includes(a)) window.scrollTo(0, scrolls.get(key) || 0); else if (!r.q.keep) window.scrollTo(0, 0);
  }

  /* ---------- portada ---------- */
  // Abre la edición la narrativa con más material analizado y algún cambio de postura; el volumen de menciones pesa poco.
  const leadScore = (th) => th.analyzedCount * 10 + th.claimCount + Math.min(th.videoCount, 6)
    + th.contrasts.reduce((acc, i) => acc + (idx.contrasts[i].kind === 'cambio' ? 14 : 4), 0);
  function vsBlock(p, opts = {}) {
    const A = claimOf(p.a.v, p.a.id), B = claimOf(p.b.v, p.b.id);
    const va = idx.videosById[p.a.v], vb = idx.videosById[p.b.v];
    const asset = CR.topicName(p.asset);
    const head = p.kind === 'cambio'
      ? (p.sameCreator ? `${va.channel.name} cambia de postura sobre ${asset}` : `${va.channel.name} y ${vb.channel.name} chocan sobre ${asset}`)
      : `${p.sameCreator ? va.channel.name + ' repite' : 'Dos creadores repiten'} la misma idea sobre ${asset}`;
    const theme = idx.themes.find((t) => t.contrasts.includes(idx.contrasts.indexOf(p)));
    const card = (c, v) => `<div class="vs-card">
      <p class="vs-when"><span>${fmtDate(v.pub)} · ${fmtT(c.t)} · ${esc(L.hz[p.hz].toLowerCase())}</span><a href="#/video/${v.id}?t=${Math.floor(c.t || 0)}">${icon('play', 'i-s')} Escuchar</a></p>
      ${c.quote ? `<blockquote class="quote">${esc(c.quote)}</blockquote>` : ''}
      <p class="reading"><b>Lectura del sistema:</b> ${esc(noDot(c.postura || c.text))}.</p>
    </div>`;
    return `<article class="vs">
      <h3 class="vs-h">${esc(head)}</h3>
      ${card(A, va)}${card(B, vb)}
      <p class="vs-foot">${p.kind === 'cambio' ? 'Detectado por reglas: mismo activo y plazo, postura contraria. No decide quién acierta.' : 'Repetición del mismo creador: no es una prueba independiente.'}${theme && !opts.noLink ? ` <a class="sans" style="color:var(--sys);font-weight:600" href="#/explorar/${theme.id}?v=${vb.id}&cap=4">Comparar en la sala →</a>` : ''}</p>
    </article>`;
  }
  function renderFront() {
    const themes = idx.themes.slice().sort((a, b) => leadScore(b) - leadScore(a));
    const lead = themes[0];
    const leadVideos = lead.sources.map((s) => idx.videosById[s.v]);
    const hero = leadVideos.find((v) => v.analysis) || leadVideos[0];
    const s = sessionGet();
    const sv = s && idx.videosById[s.v];
    const changes = idx.contrasts.filter((p) => p.kind === 'cambio');
    ed.innerHTML = `
      ${sv ? `<a class="continue" href="#/video/${sv.id}?t=${Math.floor(s.t)}"><img src="${CR.thumb(sv.id)}" alt="" loading="lazy"><div><p>Continuar viendo · ${fmtT(s.t)}</p><h3>${esc(sv.cleanTitle)}</h3></div></a>` : ''}
      <article class="lead">
        <h1 class="lead-h"><a href="#/explorar/${lead.id}">${esc(lead.title)}</a></h1>
        <p class="lead-dek">${esc(lead.about)}</p>
        <figure class="lead-fig"><a href="#/explorar/${lead.id}?v=${hero.id}"><img src="${CR.thumb(hero.id, 'hq')}" alt="Miniatura del vídeo «${esc(hero.cleanTitle)}»" decoding="async"></a>
          <figcaption>${esc(hero.channel.name)}, ${fmtDate(hero.pub)} · «${esc(hero.cleanTitle)}», uno de los ${lead.videoCount} vídeos que sustentan esta narrativa.</figcaption></figure>
        <p class="lead-meta">Explora los argumentos de ${CR.plural(lead.videoCount, 'vídeo', 'vídeos')}: ${lead.analyzedCount} con análisis, ${CR.plural(lead.claimCount, 'afirmación', 'afirmaciones')}${lead.contrasts.length ? ` y ${CR.plural(lead.contrasts.length, 'cambio de postura', 'cambios de postura')}` : ''}.</p>
        <a class="cta" href="#/explorar/${lead.id}">Abrir vídeos y argumentos ${icon('arrow-right')}</a>
        <p class="fine">El número cuenta fuentes examinadas; no demuestra que la narrativa sea correcta.</p>
      </article>

      <section class="sec"><div class="sec-h"><h2>Vídeos recientes</h2><a href="#/videos">Hemeroteca</a></div>
        ${idx.videos.filter((v) => !v.short).slice(0, 3).map((v) => `<a class="story" href="#/video/${v.id}"><img class="story-img" src="${CR.thumb(v.id, 'hq')}" alt="" loading="lazy"><h3 class="story-h">${esc(v.cleanTitle)}</h3>${v.analysis ? `<p class="story-dek">${esc(CR.clip(v.analysis.thesis, 170))}</p>` : ''}${byline(v)}</a>`).join('')}
      </section>

      <section class="sec"><div class="sec-h"><h2>Narrativas en discusión</h2><a href="#/narrativas">Todas</a></div>
        ${themes.slice(1).map((th) => `<a class="narr" href="#/explorar/${th.id}"><h3>${esc(th.title)}</h3><p>Explora los argumentos de ${CR.plural(th.videoCount, 'vídeo', 'vídeos')} · ${th.analyzedCount} con análisis.</p>
          <div class="thumbs">${th.sources.slice(0, 6).map((s) => `<img src="${CR.thumb(s.v)}" alt="" loading="lazy">`).join('')}</div><span class="go">Abrir vídeos y argumentos ${icon('arrow-right', 'i-s')}</span></a>`).join('')}
      </section>

      <section class="sec"><div class="sec-h"><h2>Desacuerdos detectados</h2><a href="#/desacuerdos">Ver todos</a></div>
        ${changes.length ? changes.map((p) => vsBlock(p)).join('') : '<p class="wrap fine">No se detectaron posturas contrarias entre los vídeos analizados.</p>'}
      </section>

      <section class="sec"><div class="sec-h"><h2>Cómo se hace esta edición</h2></div>
        <div class="wrap"><p class="fine" style="font-size:14px">${esc(idx.method.themes)} ${esc(idx.method.external)} Datos al ${fmtDate(idx.generatedAt, { time: true })}.</p>
        <p style="margin-top:10px"><a class="sans" style="color:var(--sys);font-weight:600;font-size:14px" href="#/estados">Así se ve cada estado del procesamiento →</a></p>
        <p style="margin-top:6px"><a class="sans" style="color:var(--muted);font-weight:600;font-size:14px" href="../index.html">Volver al tablero de propuestas</a></p></div>
      </section>`;
  }

  /* ---------- narrativas ---------- */
  function renderNarratives() {
    ed.innerHTML = `<div class="wrap" style="padding-top:16px"><h1 class="lead-h" style="font-size:30px">Narrativas</h1><p class="lead-dek">Preguntas que atraviesan varios vídeos. Cada una se abre como una sala con sus fuentes.</p></div>
      <div style="margin-top:12px;border-top:1px solid var(--rule-ink)">${idx.themes.map((th) => `<a class="narr" href="#/explorar/${th.id}"><h3>${esc(th.title)}</h3><p>${esc(th.about)}</p><div class="thumbs">${th.sources.slice(0, 6).map((s) => `<img src="${CR.thumb(s.v)}" alt="" loading="lazy">`).join('')}</div>
        <p class="byline">${CR.plural(th.videoCount, 'vídeo', 'vídeos')} · ${th.analyzedCount} con análisis · ${th.creators.map((c) => idx.channelsBySlug[c].name).join(' y ')}${th.contrasts.length ? ` · <span style="color:var(--red);font-weight:600">${CR.plural(th.contrasts.length, 'cruce', 'cruces')}</span>` : ''}</p></a>`).join('')}</div>`;
  }

  /* ---------- sala de exploración ---------- */
  function firstMoment(s, doc) {
    const ts = s.claims.map((id) => doc.claimsById[id]).filter((c) => c && c.t != null).map((c) => c.t);
    if (ts.length) return Math.min(...ts);
    return s.frags.length ? s.frags[0].t : 0;
  }
  function synthesisHtml(th) {
    const vids = th.sources.map((s) => idx.videosById[s.v]).sort((a, b) => a.pub.localeCompare(b.pub));
    const creators = th.creators.map((c) => idx.channelsBySlug[c].name);
    const jump = (c) => `<button class="chipt" type="button" data-act="jump" data-v="${c.v}" data-t="${c.t || 0}">${fmtDate(idx.videosById[c.v].pub)}, ${fmtT(c.t)}</button>`;
    let txt = `Esta pregunta aparece en ${CR.plural(th.videoCount, 'vídeo', 'vídeos')} de ${esc(joinEs(creators))} entre el ${fmtDate(vids[0].pub)} y el ${fmtDate(vids[vids.length - 1].pub)}; ${th.analyzedCount === 1 ? 'uno tiene' : `${th.analyzedCount} tienen`} análisis.`;
    th.contrasts.forEach((i) => {
      const p = idx.contrasts[i];
      const A = claimOf(p.a.v, p.a.id), B = claimOf(p.b.v, p.b.id);
      txt += p.kind === 'cambio'
        ? ` Sobre ${esc(CR.topicName(p.asset))} a ${esc(L.hz[p.hz].toLowerCase())} la postura cambia: «${esc(lowerFirst(noDot(A.postura)))}» (${jump(A)}) frente a «${esc(lowerFirst(noDot(B.postura)))}» (${jump(B)}).`
        : ` Se repite una idea sobre ${esc(CR.topicName(p.asset))}: «${esc(lowerFirst(noDot(A.postura)))}» (${jump(A)}) y «${esc(lowerFirst(noDot(B.postura)))}» (${jump(B)}).`;
    });
    txt += ' Ninguna fuente externa la respalda ni la contradice todavía.';
    return `<section class="synth" aria-label="Síntesis"><h3>Síntesis del sistema</h3><p>${txt}</p><p class="fine">Redactada a partir de las afirmaciones y los cruces detectados; cada fecha lleva a su fragmento.</p></section>`;
  }
  function itemClaim(c, v) {
    const key = `c:${v.id}:${c.id}`;
    return `<div class="item">
      <p class="when"><span>${L.tipo[c.tipo]} · ${c.t != null ? fmtT(c.t) : 'título'} · ${L.verif[c.verif]}</span><button type="button" data-act="seek" data-t="${c.t || 0}">${icon('play', 'i-s')} Escuchar</button></p>
      ${c.literal || c.quote ? `<blockquote class="quote">${esc(c.literal ? c.literal.cita : c.quote)}</blockquote>` : ''}
      <p class="lbl sys">Lectura del sistema</p><p class="reading" style="margin-top:2px">${esc(c.text)}</p>
      <button class="save" type="button" data-act="clip" data-v="${v.id}" data-c="${c.id}">${icon(saved.has(key) ? 'bookmark-fill' : 'bookmark')} ${saved.has(key) ? 'Recortado' : 'Recortar'}</button>
    </div>`;
  }
  function otherSources(th, active) {
    return th.sources.filter((s) => s.v !== active).map((s) => {
      const v = idx.videosById[s.v];
      const claims = s.claims.map((id) => claimOf(s.v, id)).filter(Boolean).slice(0, 2);
      return `<div class="item">
        <p class="when"><span>${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${v.analysis ? 'con análisis' : 'solo transcripción'}</span><button type="button" data-act="source" data-v="${v.id}">Ver esta fuente ${icon('arrow-right', 'i-s')}</button></p>
        <p style="font-weight:600">${esc(v.cleanTitle)}</p>
        ${claims.length ? claims.map((c) => `${c.quote ? `<blockquote class="quote" style="font-size:15.5px">${esc(c.quote)}</blockquote>` : ''}<p class="reading">${esc(c.text)}</p>`).join('') : s.frags.slice(0, 1).map((f) => `<blockquote class="quote" style="font-size:15.5px">${esc(f.text)}</blockquote><p class="fine">Fragmento literal en ${fmtT(f.t)}; sin análisis.</p>`).join('')}
      </div>`;
    }).join('');
  }
  const built = (parts) => `<p class="built">Cómo se construyó: ${parts.map(([n, label]) => `<b>${n}</b> ${label}`).join(' → ')}</p>`;
  function chapters(th, s, v, doc) {
    const a = doc.analysis;
    const claimsFull = a ? s.claims.map((id) => CR.claim(doc, id)).filter(Boolean).sort((x, y) => (x.t || 0) - (y.t || 0)) : [];
    const ids = new Set(s.claims);
    const touches = (list) => list.some((x) => ids.has(x));
    const contrastsHere = th.contrasts.map((i) => idx.contrasts[i]);
    const evs = [];
    claimsFull.forEach((c) => c.evidences.forEach((e) => { if (!evs.find((x) => x.id === e.id)) evs.push(e); }));
    const chains = a ? a.cadena_narrativa.filter((ch) => touches(ch.afirmacion_ids)) : [];
    const scen = a ? a.escenarios.filter((x) => touches(x.afirmacion_ids)) : [];
    const pend = a ? a.verificaciones_pendientes.filter((x) => touches(x.afirmacion_ids)) : [];
    const watch = a ? a.seguimiento.filter((x) => touches(x.afirmacion_ids)) : [];
    const others = th.sources.length - 1;
    const noAnalysis = '<p class="pending">Este vídeo no está analizado: aquí solo aparece lo que dice, sin interpretación del sistema.</p>';
    const caps = [
      ['Qué plantea este creador', `${esc(v.channel.name)} · ${fmtDate(v.pub)}`,
        a ? `<div class="item"><p class="lbl">Resumen del sistema de lo que dice</p><p>${esc(a.resumen.mensaje_explicito)}</p></div>${claimsFull.map((c) => itemClaim(c, v)).join('')}${built([[claimsFull.length, 'afirmaciones del tema'], [evs.length, 'fragmentos citados']])}`
          : `${noAnalysis}${s.frags.map((f) => `<div class="item"><p class="when"><span>Transcripción · ${fmtT(f.t)}</span><button type="button" data-act="seek" data-t="${f.t}">${icon('play', 'i-s')} Escuchar</button></p><blockquote class="quote">${esc(f.text)}</blockquote></div>`).join('')}${built([[s.frags.length, 'fragmentos seleccionados por palabras clave'], [0, 'afirmaciones']])}`],
      ['Qué evidencia aporta', a ? CR.plural(evs.length, 'fragmento citado', 'fragmentos citados') : 'Sin análisis',
        a ? `${evs.map((e) => `<div class="item"><p class="when"><span>${e.origen === 'titulo' ? 'Título del vídeo' : `${L.origen[e.origen]} · ${fmtT(e.inicio_s)}`}</span>${e.inicio_s != null ? `<button type="button" data-act="seek" data-t="${e.inicio_s}">${icon('play', 'i-s')} Escuchar</button>` : ''}</p>${e.cita ? `<blockquote class="quote">${esc(e.cita)}</blockquote>` : ''}${e.observacion ? `<p class="fine">Nota del sistema: ${esc(e.observacion)}</p>` : ''}</div>`).join('')}
            <div class="item"><p class="lbl sys">Lo que se puede demostrar con lo recibido</p><p>${esc(a.resumen.respaldo_demostrable)}</p></div>
            <p class="ext-none">${icon('alert')}<span><b>Fuentes externas: ninguna.</b> Los fragmentos muestran lo que el creador dijo, no que sea cierto.</span></p>${built([[evs.length, 'fragmentos'], [0, 'fuentes externas']])}`
          : `${noAnalysis}<p class="ext-none">${icon('alert')}<span>Sin análisis no se identificaron pruebas. Los fragmentos del capítulo 1 son literales.</span></p>`],
      ['Qué supuestos necesita', a ? `${CR.plural(chains.length, 'paso', 'pasos')} del argumento · ${CR.plural(scen.length, 'escenario', 'escenarios')}` : 'Sin análisis',
        a && (chains.length || scen.length) ? `${chains.map((ch) => `<div class="item"><p>${esc(ch.premisa)}</p><p style="margin-top:4px"><b>→ ${esc(ch.conclusion)}</b></p>${ch.supuesto ? `<p class="lbl sys">Supuesto que necesita · ${esc(L.vinculo[ch.vinculo].toLowerCase())}</p><p class="reading" style="margin-top:2px">${esc(ch.supuesto)}</p>` : ''}</div>`).join('')}
            ${scen.map((x) => `<div class="item"><p class="lbl">${esc(L.origenEsc[x.origen])} · ${esc(L.plaus[x.plausibilidad].toLowerCase())}</p><p style="font-weight:600">${esc(x.nombre)}</p><ul class="sans" style="margin-top:6px;font-size:14.5px;color:var(--ink-2);display:grid;gap:4px">${x.supuestos.map((u) => `<li>· ${esc(u)}</li>`).join('')}</ul></div>`).join('')}${built([[chains.length, 'pasos encadenados'], [scen.length, 'escenarios']])}`
          : a ? '<p class="fine">El análisis no encadenó estas afirmaciones con supuestos explícitos.</p>' : noAnalysis],
      ['Qué dicen otros vídeos', `${CR.plural(others, 'fuente más', 'fuentes más')}${contrastsHere.length ? ` · ${CR.plural(contrastsHere.length, 'cruce', 'cruces')}` : ''}`,
        `${contrastsHere.map((p) => vsBlock(p, { noLink: true }).replace('class="vs"', 'class="vs" style="margin:0 0 14px"')).join('')}
         ${otherSources(th, s.v)}
         <p class="ext-none">${icon('users')}<span><b>${CR.plural(th.videoCount, 'vídeo', 'vídeos')} de ${CR.plural(th.creators.length, 'creador', 'creadores')}</b> tratan la idea. Que se repita no equivale a evidencia externa: <b>0 fuentes</b> la respaldan.</span></p>
         ${built([[others, 'vídeos comparados'], [contrastsHere.filter((p) => p.kind === 'cambio').length, 'cambios'], [contrastsHere.filter((p) => p.kind !== 'cambio').length, 'coincidencias']])}`],
      ['Qué preguntas quedan abiertas', a ? CR.plural(pend.length + watch.length, 'pendiente', 'pendientes') : 'Pedir el análisis',
        a ? `${pend.map((p) => `<div class="item"><p class="lbl red">${L.prioridad[p.prioridad]}</p><p>${esc(p.pregunta)}</p><p class="fine">Buscar: ${esc(p.fuente_o_dato_buscado)}</p></div>`).join('')}${watch.map((w) => `<div class="item"><p class="lbl sys">Qué vigilar${w.plazo ? ` · ${esc(CR.clip(w.plazo, 60))}` : ''}</p><p>${esc(w.que_observar)}</p><p class="fine">${esc(w.criterio)}</p></div>`).join('')}${pend.length + watch.length ? '' : '<p class="fine">El análisis no dejó preguntas abiertas sobre estas afirmaciones.</p>'}`
          : `<p class="pending">La primera pregunta abierta es este mismo vídeo: no se ha analizado. En el producto, este botón lo pondría en la cola.</p><button class="cta cta-ghost" type="button" data-act="demo">${icon('flask')} Pedir el análisis</button>`],
    ];
    return `<div class="chapters">${caps.map(([title, sub, body], i) => `<details class="chap" data-cap="${i + 1}"${ui.caps.has(i + 1) ? ' open' : ''}><summary><span class="chap-n">${i + 1}</span><span><span class="chap-t">${title}</span><span class="chap-s">${sub}</span></span>${icon('chevron-down')}</summary><div class="chap-body">${body}</div></details>`).join('')}</div>`;
  }
  async function renderExplore(id, q, same) {
    const th = idx.themesById[id];
    if (!th) { ed.innerHTML = `<div class="empty"><h3>Esa narrativa no está en la edición</h3><p><a href="#/narrativas" style="color:var(--sys)">Ver narrativas</a></p></div>`; return; }
    const sources = th.sources;
    const s = sources.find((x) => x.v === q.v) || sources.find((x) => x.claims.length) || sources[0];
    const v = idx.videosById[s.v];
    if (q.cap) { ui.caps.add(Number(q.cap)); store.set('caps', [...ui.caps]); }
    const keepY = same ? window.scrollY : 0;
    if (!same) ed.innerHTML = '<div class="wrap"><div class="skel" style="height:30px;margin-top:20px"></div><div class="skel" style="height:220px;margin-top:16px"></div></div>';
    let doc;
    try { doc = await CR.loadVideo(v.id); } catch (e) {
      ed.innerHTML = `<div class="err" role="alert"><h3>No se pudo abrir esta fuente</h3><p>Prueba con otra fuente o vuelve a intentarlo.</p><button class="cta" type="button" data-act="retry">${icon('refresh')} Reintentar</button></div>`;
      return;
    }
    if (screen !== `explorar:${id}`) return;
    const sess = sessionGet();
    const start = q.t != null ? Number(q.t) : sess && sess.v === v.id ? sess.t : firstMoment(s, doc);
    ed.innerHTML = `
      <div class="explore-top"><a class="back" href="#/narrativas">${icon('arrow-left', 'i-s')} Narrativas</a><h1 class="ex-h">${esc(th.title)}</h1></div>
      <div class="player${v.short ? ' is-short' : ''}" id="player"></div>
      <p class="caption"><b>${esc(v.channel.name)}</b>, ${fmtDate(v.pub, { time: true })} · «${esc(v.cleanTitle)}» · ${v.analysis ? 'con análisis' : 'solo transcripción'}</p>
      <section class="sources" aria-label="Selector de fuentes"><p class="sources-h">Fuentes de esta narrativa <span>${sources.indexOf(s) + 1} de ${sources.length}</span></p>
        <div class="sources-row" data-scroll-x>${sources.map((x) => { const sv = idx.videosById[x.v]; return `<button class="src" type="button" data-act="source" data-v="${sv.id}" aria-pressed="${sv.id === v.id}"><img src="${CR.thumb(sv.id)}" alt="" loading="lazy"><b>${esc(sv.cleanTitle)}</b><small>${esc(sv.channel.name)} · ${fmtDate(sv.pub)} · ${x.claims.length ? CR.plural(x.claims.length, 'afirmación', 'afirmaciones') : 'transcripción'}</small></button>`; }).join('')}</div>
      </section>
      ${synthesisHtml(th)}
      ${chapters(th, s, v, doc)}`;
    mountPlayer(document.getElementById('player'), v, start);
    CR.$$('.chap', ed).forEach((d) => d.addEventListener('toggle', () => {
      const n = Number(d.dataset.cap);
      if (d.open) ui.caps.add(n); else ui.caps.delete(n);
      store.set('caps', [...ui.caps]);
    }));
    const sel = ed.querySelector('.src[aria-pressed="true"]');
    if (sel) sel.scrollIntoView({ block: 'nearest', inline: 'center' });
    if (same) window.scrollTo(0, keepY);
    if (q.cap && !same) { const c = ed.querySelector(`.chap[data-cap="${q.cap}"]`); if (c) requestAnimationFrame(() => c.scrollIntoView({ block: 'start' })); }
  }

  /* ---------- desacuerdos ---------- */
  function renderDisagreements() {
    const ch = idx.contrasts.filter((p) => p.kind === 'cambio');
    const co = idx.contrasts.filter((p) => p.kind !== 'cambio');
    ed.innerHTML = `<div class="wrap" style="padding-top:16px"><h1 class="lead-h" style="font-size:30px">Desacuerdos</h1><p class="lead-dek">Fragmentos enfrentados, uno detrás de otro. El sistema señala el cruce; la conclusión es tuya.</p></div>
      <section class="sec"><div class="sec-h"><h2>Cambios de postura</h2><span>${ch.length}</span></div>${ch.map((p) => vsBlock(p)).join('')}</section>
      <section class="sec"><div class="sec-h"><h2>Ideas que se repiten</h2><span>${co.length}</span></div>${co.map((p) => vsBlock(p)).join('')}</section>
      <p class="wrap fine" style="margin-top:18px">${esc(idx.method.contrasts)}</p>`;
  }

  /* ---------- dossiers ---------- */
  function renderDossiers(sec) {
    const s = sec || ui.ds;
    ui.ds = s; store.set('ds', s);
    const rows = idx.topics.filter((t) => t.section === s).sort((a, b) => b.vc - a.vc || b.n - a.n);
    const btc = idx.topicsById.btc;
    ed.innerHTML = `<div class="wrap" style="padding-top:16px"><h1 class="lead-h" style="font-size:30px">Dossiers</h1><p class="lead-dek">Cada activo, con sus vídeos, argumentos, fechas y lo que falta por comprobar.</p></div>
      <div class="filters" data-scroll-x role="tablist" aria-label="Secciones">${['altcoins', 'macro', 'bolsa'].map((k) => `<a class="fbtn" role="tab" href="#/dossiers?s=${k}" aria-pressed="${k === s}" aria-selected="${k === s}">${L.section[k]}</a>`).join('')}</div>
      ${s === 'altcoins' ? `<a class="story" href="#/dossier/btc"><h3 class="story-h">Bitcoin, el activo que lo atraviesa todo</h3><p class="story-dek">${btc.vc} de ${idx.videos.length} vídeos y ${btc.claims.length} afirmaciones analizadas. No entra en el ranking de altcoins.</p></a>` : ''}
      <section class="sec"><div class="sec-h"><h2>Ranking de menciones</h2><span>por vídeos</span></div>
        <ol>${rows.map((t, i) => `<li><a class="story" href="#/dossier/${t.id}" style="display:grid;grid-template-columns:34px 1fr;gap:6px"><span class="chap-n" style="font-size:24px">${i + 1}</span><span><span class="story-h" style="font-size:19px">${esc(t.name)}${t.sym && t.sym !== t.name ? ` <span class="sans" style="font-size:13px;color:var(--muted)">${esc(t.sym)}</span>` : ''}</span><span class="byline" style="display:flex">${CR.plural(t.vc, 'vídeo', 'vídeos')} · ${CR.plural(t.n, 'mención', 'menciones')} · ${CR.plural(t.cc, 'creador', 'creadores')}${t.claims.length ? ` · <b style="color:var(--sys)">${CR.plural(t.claims.length, 'afirmación analizada', 'afirmaciones analizadas')}</b>` : ''}</span></span></a></li>`).join('')}</ol>
      </section>
      <p class="wrap fine" style="margin-top:14px">${esc(idx.method.mentions)}</p>`;
  }
  function renderDossier(id) {
    const t = idx.topicsById[id];
    if (!t) { ed.innerHTML = `<div class="empty"><h3>Dossier no encontrado</h3></div>`; return; }
    const claims = t.claims.map((k) => claimOf(k.v, k.id)).filter(Boolean);
    // Solo cuentan como argumento las posturas (predicción, hipótesis, opinión u operativa declarada).
    const stance = (c) => c.own || ['prediccion', 'hipotesis', 'opinion'].includes(c.tipo);
    const favor = claims.filter((c) => stance(c) && c.dir === 'alcista');
    const contra = claims.filter((c) => stance(c) && (c.dir === 'bajista' || c.dir === 'mixta'));
    const neutral = claims.filter((c) => !favor.includes(c) && !contra.includes(c));
    const changes = idx.contrasts.filter((p) => p.asset === id);
    const argItem = (c) => { const v = idx.videosById[c.v]; return `<div class="arg"><p class="when sans" style="font-size:12.5px;color:var(--muted);font-weight:600;display:flex;justify-content:space-between;gap:8px;align-items:center"><span>${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${fmtT(c.t)}</span><a style="color:var(--sys);min-height:36px;display:inline-flex;align-items:center;gap:4px" href="#/video/${v.id}?t=${Math.floor(c.t || 0)}">${icon('play', 'i-s')} Escuchar</a></p>${c.quote ? `<blockquote class="quote" style="font-size:16px">${esc(c.quote)}</blockquote>` : ''}<p class="reading">${esc(c.text)}</p>${c.postura ? `<p class="fine">Postura extraída: ${esc(c.postura)}</p>` : ''}</div>`; };
    const catalysts = [];
    claims.forEach((c) => {
      const v = idx.videosById[c.v];
      if (c.plazo || c.postura) catalysts.push({ when: c.plazo || L.hz[c.hz], v, c });
    });
    ed.innerHTML = `
      <div class="explore-top"><a class="back" href="#/dossiers?s=${t.section === 'bitcoin' ? 'altcoins' : t.section}">${icon('arrow-left', 'i-s')} Dossiers</a>
        <h1 class="dossier-h">${esc(t.name)}</h1><p class="dek">${CR.plural(t.vc, 'vídeo lo menciona', 'vídeos lo mencionan')}, ${CR.plural(t.n, 'vez', 'veces')}, ${CR.plural(t.cc, 'creador', 'creadores')}. ${claims.length ? `${CR.plural(claims.length, 'afirmación analizada', 'afirmaciones analizadas')}.` : 'Ninguna afirmación analizada.'}${t.note ? ` Ojo: ${esc(t.note)}.` : ''}</p></div>
      <nav class="toc" aria-label="Contenido del dossier"><h2>En este dossier</h2><ol>
        <li><a href="#d1" data-anchor="d1">Vídeos que lo mencionan</a></li><li><a href="#d2" data-anchor="d2">Argumentos a favor y objeciones</a></li>
        <li><a href="#d3" data-anchor="d3">Catalizadores y fechas citadas</a></li><li><a href="#d4" data-anchor="d4">Cambios del discurso</a></li><li><a href="#d5" data-anchor="d5">Evidencia aportada y datos que faltan</a></li></ol></nav>
      <section class="dsec" id="d1"><h2>Vídeos que lo mencionan</h2><div class="vlist">${t.videos.map((m) => { const v = idx.videosById[m.v]; return `<a href="#/video/${v.id}?t=${Math.floor(m.frags[0] ? m.frags[0].t : 0)}"><img src="${CR.thumb(v.id)}" alt="" loading="lazy"><span><b>${esc(v.cleanTitle)}</b><small>${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${CR.plural(m.n, 'mención', 'menciones')}${m.frags[0] ? ` · primera en ${fmtT(m.frags[0].t)}` : ''}</small></span></a>`; }).join('')}</div></section>
      <section class="dsec" id="d2"><h2>Argumentos a favor y objeciones</h2><p class="fine">Clasificación del sistema según la postura extraída de cada afirmación.</p>
        <div class="args">
          <div class="arg-col"><h3>${icon('trend-up')} A favor · ${favor.length}</h3>${favor.map(argItem).join('') || '<p class="fine">Ninguna afirmación analizada a favor.</p>'}</div>
          <div class="arg-col"><h3>${icon('trend-down')} Objeciones o a la baja · ${contra.length}</h3>${contra.map(argItem).join('') || '<p class="fine">Ninguna afirmación analizada en contra.</p>'}</div>
          ${neutral.length ? `<div class="arg-col"><h3>${icon('minus')} Hechos y descripciones · ${neutral.length}</h3>${neutral.map(argItem).join('')}</div>` : ''}
        </div></section>
      <section class="dsec" id="d3"><h2>Catalizadores y fechas citadas</h2>${catalysts.length ? `<ul class="cal">${catalysts.map((x) => `<li><span class="d">${esc(CR.clip(x.when, 40))}</span><p>${esc(x.c.text)} <a class="sans" style="color:var(--sys);font-size:13px;font-weight:600" href="#/video/${x.v.id}?t=${Math.floor(x.c.t || 0)}">${fmtDate(x.v.pub)} · ${fmtT(x.c.t)}</a></p></li>`).join('')}</ul>` : '<p class="fine" style="margin-top:8px">Sin plazos ni catalizadores en afirmaciones analizadas.</p>'}</section>
      <section class="dsec" id="d4"><h2>Cambios del discurso</h2>${changes.length ? changes.map((p) => vsBlock(p).replace('class="vs"', 'class="vs" style="margin:10px 0 0"')).join('') : `<p class="fine" style="margin-top:8px">No se detectaron cambios entre publicaciones analizadas${claims.length < 2 ? ': hace falta más de un vídeo analizado que lo trate' : ''}.</p>`}</section>
      <section class="dsec" id="d5"><h2>Evidencia aportada y datos que faltan</h2>
        ${claims.length ? `<p class="fine">Estado de cada afirmación: ${Object.entries(claims.reduce((acc, c) => { acc[L.verif[c.verif]] = (acc[L.verif[c.verif]] || 0) + 1; return acc; }, {})).map(([k, n]) => `${n} ${k.toLowerCase()}`).join(', ')}.</p>` : ''}
        <p class="ext-none">${icon('alert')}<span><b>Fuentes externas consultadas: ninguna.</b> Para comprobar estas afirmaciones harían falta precios fechados, calendarios oficiales y los gráficos que citan los creadores.</span></p></section>`;
  }

  /* ---------- hemeroteca y vídeo como artículo ---------- */
  function renderVideos() {
    const F = { todos: 'Todos', analizados: 'Con análisis', nacho: 'Nacho IC', kmanu: 'KManuS88', shorts: 'Shorts' };
    const list = idx.videos.filter((v) => ui.vf === 'todos' || (ui.vf === 'analizados' ? v.analysis : ui.vf === 'shorts' ? v.short : v.ch === ui.vf));
    let last = null;
    ed.innerHTML = `<div class="wrap" style="padding-top:16px"><h1 class="lead-h" style="font-size:30px">Hemeroteca</h1><p class="lead-dek">Todos los vídeos del archivo, por día.</p></div>
      <div class="filters" data-scroll-x>${Object.entries(F).map(([k, l]) => `<button class="fbtn" type="button" data-act="vf" data-f="${k}" aria-pressed="${ui.vf === k}">${l}</button>`).join('')}</div>
      <div class="grid2">${list.map((v) => { const k = CR.dayKey(v.pub); const h = k !== last ? `<h2 class="day-h">${esc(CR.dayLabel(v.pub))}</h2>` : ''; last = k; return `${h}<a href="#/video/${v.id}"><img src="${CR.thumb(v.id)}" alt="" loading="lazy"><h3>${esc(v.cleanTitle)}</h3><p class="byline">${esc(v.channel.name)} · ${v.analysis ? '<b style="color:var(--sys)">análisis</b>' : 'transcripción'}</p></a>`; }).join('') || '<p class="fine">Ningún vídeo con este filtro.</p>'}</div>`;
  }
  async function renderVideo(id, q) {
    const v = idx.videosById[id];
    if (!v) { ed.innerHTML = `<div class="empty"><h3>Este vídeo no está en la edición</h3></div>`; return; }
    ed.innerHTML = '<div class="wrap"><div class="skel" style="height:220px;margin-top:16px"></div></div>';
    let doc;
    try { doc = await CR.loadVideo(id); } catch (e) {
      ed.innerHTML = `<div class="err" role="alert"><h3>No se pudo abrir el vídeo</h3><p>Vuelve a intentarlo.</p><button class="cta" type="button" data-act="retry">${icon('refresh')} Reintentar</button></div>`;
      return;
    }
    if (screen !== `video:${id}`) return;
    const a = doc.analysis;
    const sess = sessionGet();
    const start = q.t != null ? Number(q.t) : sess && sess.v === id ? sess.t : 0;
    const themes = idx.themes.filter((th) => th.sources.some((s) => s.v === id));
    const claims = (doc.claims || []).map((c) => CR.claim(doc, c.id)).filter(Boolean).sort((x, y) => (x.t || 0) - (y.t || 0));
    const blocks = CR.blocks(doc.segments, 40);
    ed.innerHTML = `
      <div class="explore-top"><a class="back" href="#/videos">${icon('arrow-left', 'i-s')} Hemeroteca</a></div>
      <div class="player${v.short ? ' is-short' : ''}" id="player"></div>
      <div class="wrap"><h1 class="art-h">${esc(v.cleanTitle)}</h1>${byline(v)}
        ${a ? `<p class="art-p">${esc(a.resumen.mensaje_explicito)}</p><p class="lbl sys" style="margin-top:14px">Lo que intenta hacer pensar, según el sistema</p><p class="reading" style="font-size:16px">${esc(a.resumen.narrativa_sugerida)}</p><p class="lbl ext" style="margin-top:14px">Lo que se puede demostrar con lo recibido</p><p style="font-size:16px">${esc(a.resumen.respaldo_demostrable)}</p>`
          : `<p class="pending" style="margin-top:14px">Este vídeo todavía no tiene análisis. Puedes leer la transcripción completa más abajo y saltar a cualquier minuto.</p>`}
        ${themes.length ? `<p class="lbl" style="margin-top:18px">Aparece en estas narrativas</p>${themes.map((th) => `<p><a class="sans" style="color:var(--sys);font-weight:600;font-size:15px" href="#/explorar/${th.id}?v=${id}">${esc(th.title)} →</a></p>`).join('')}` : ''}
      </div>
      ${claims.length ? `<section class="sec"><div class="sec-h"><h2>Afirmaciones</h2><span>${claims.length}</span></div><div class="wrap claim-list">${claims.map((c) => itemClaim(c, v)).join('')}</div></section>` : ''}
      <div class="wrap"><details class="more"${a ? '' : ' open'}><summary>Transcripción íntegra ${icon('chevron-down')}</summary><div class="tx">${blocks.map((b) => `<p><button type="button" data-act="seek" data-t="${b.start}">${fmtT(b.start)}</button>${esc(b.text)}</p>`).join('')}</div></details></div>`;
    mountPlayer(document.getElementById('player'), v, start);
  }

  /* ---------- recortes, búsqueda, estados ---------- */
  function renderClips() {
    const list = saved.all();
    ed.innerHTML = `<div class="wrap" style="padding-top:16px"><h1 class="lead-h" style="font-size:30px">Recortes</h1><p class="lead-dek">Las citas que guardaste, con su vídeo y su segundo.</p></div>
      ${list.length ? list.map((s) => `<article class="clip"><p class="byline" style="margin-top:0">${esc(s.sub)}</p>${s.quote ? `<blockquote class="quote">${esc(s.quote)}</blockquote>` : ''}<p class="reading">${esc(s.title)}</p><div class="clip-foot"><a href="${esc(s.href)}">${icon('play', 'i-s')} Volver a la cita</a><button type="button" data-act="unclip" data-key="${esc(s.key)}">Quitar</button></div></article>`).join('')
        : `<div class="empty"><h3>Aún no hay recortes</h3><p>En cualquier afirmación pulsa «Recortar» y aparecerá aquí, lista para volver a escucharla.</p><p style="margin-top:12px"><a class="cta" href="#/explorar/${idx.themes[0].id}">Abrir una narrativa</a></p></div>`}`;
  }
  function renderSearch(q) {
    ed.innerHTML = `<label class="search-box">${icon('search')}<span class="sr">Buscar</span><input id="q" type="search" value="${esc(q)}" placeholder="Narrativas, citas, activos…" autocomplete="off" enterkeyhint="search"></label><div id="res"></div>`;
    const input = document.getElementById('q');
    const run = () => {
      const val = input.value.trim();
      CR.go(['buscar'], { q: val }, { replace: true });
      const out = document.getElementById('res');
      if (!val) { out.innerHTML = '<p class="wrap fine" style="margin-top:16px">Prueba con «short», «Hyperliquid» o «liquidez».</p>'; return; }
      const r = CR.search(val);
      const g = (h, items) => (items.length ? `<h2 class="res-h">${h}</h2>${items.join('')}` : '');
      out.innerHTML = g('Narrativas', r.themes.map((t) => `<a class="res" href="#/explorar/${t.id}"><p>${esc(t.title)}</p></a>`))
        + g('Afirmaciones', r.claims.slice(0, 10).map((c) => { const v = idx.videosById[c.v]; return `<a class="res" href="#/video/${v.id}?t=${Math.floor(c.t || 0)}"><p>${esc(c.text)}</p><small>${esc(v.channel.name)} · ${fmtDate(v.pub)} · ${fmtT(c.t)}</small></a>`; }))
        + g('Dossiers', r.topics.slice(0, 8).map((t) => `<a class="res" href="#/dossier/${t.id}"><p>${esc(t.name)}</p><small>${CR.plural(t.vc, 'vídeo', 'vídeos')}</small></a>`))
        + g('Vídeos', r.videos.slice(0, 8).map((v) => `<a class="res" href="#/video/${v.id}"><p>${esc(v.cleanTitle)}</p><small>${esc(v.channel.name)} · ${fmtDate(v.pub)}</small></a>`))
        + `<div class="wrap" style="margin-top:16px"><button class="cta cta-ghost" type="button" data-act="search-tx" style="width:100%;justify-content:center">${icon('text')} Buscar también en las transcripciones</button></div><div id="txr"></div>`;
    };
    input.addEventListener('input', CR.debounce(run, 200));
    run();
    input.focus();
  }
  async function searchTx() {
    const val = document.getElementById('q').value;
    const out = document.getElementById('txr');
    out.innerHTML = '<div class="wrap"><div class="skel" style="height:60px;margin-top:12px"></div></div>';
    const hits = await CR.searchTranscripts(val);
    out.innerHTML = hits.length ? `<h2 class="res-h">En las transcripciones</h2>${hits.map((h) => { const v = idx.videosById[h.v]; return `<a class="res" href="#/video/${v.id}?t=${Math.floor(h.t)}"><blockquote class="quote" style="font-size:15.5px">${esc(h.text)}</blockquote><small>${esc(v.channel.name)} · ${fmtT(h.t)}</small></a>`; }).join('')}` : `<p class="wrap fine" style="margin-top:12px">Ninguna transcripción contiene «${esc(val)}».</p>`;
  }
  function renderStates() {
    ed.innerHTML = `<div class="wrap" style="padding-top:16px"><h1 class="lead-h" style="font-size:30px">Estados del procesamiento</h1><p class="lead-dek">Lo que verá el lector según lo que el sistema haya podido hacer con cada vídeo.</p></div>
      <div style="margin-top:14px;border-top:3px solid var(--rule-ink)">${CR.STATES.map((s) => `<article class="state"><h3>${esc(s.title)}<span>${s.real ? 'Real en el archivo' : 'Ejemplo'}</span></h3><p>${esc(s.body)}</p><button class="cta cta-ghost" type="button" data-act="demo" style="margin-top:10px">${esc(s.action)}</button></article>`).join('')}</div>`;
  }

  /* ---------- acciones ---------- */
  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-act], [data-anchor]');
    if (!el) return;
    if (el.dataset.anchor) { e.preventDefault(); const t = document.getElementById(el.dataset.anchor); if (t) t.scrollIntoView({ behavior: CR.reduced() ? 'auto' : 'smooth' }); return; }
    const act = el.dataset.act;
    switch (act) {
      case 'seek': seek(Number(el.dataset.t)); break;
      case 'source': {
        const r = CR.parseHash();
        CR.go(['explorar', r.parts[1]], { v: el.dataset.v }, { replace: true });
        break;
      }
      case 'jump': {
        const r = CR.parseHash();
        if (playerVideo && playerVideo.id === el.dataset.v) seek(Number(el.dataset.t));
        else CR.go(['explorar', r.parts[1]], { v: el.dataset.v, t: Math.floor(Number(el.dataset.t)) }, { replace: true });
        break;
      }
      case 'clip': {
        const v = idx.videosById[el.dataset.v];
        const c = claimOf(v.id, el.dataset.c);
        const on = saved.toggle({ key: `c:${v.id}:${c.id}`, sub: `${v.channel.name} · ${fmtDate(v.pub)} · ${fmtT(c.t)}`, title: c.text, quote: c.quote, href: `#/video/${v.id}?t=${Math.floor(c.t || 0)}` });
        el.innerHTML = `${icon(on ? 'bookmark-fill' : 'bookmark')} ${on ? 'Recortado' : 'Recortar'}`;
        CR.toast(on ? 'Cita recortada' : 'Recorte quitado', on ? { action: 'Ver recortes', onAction: () => CR.go('#/recortes') } : {});
        break;
      }
      case 'unclip': saved.remove(el.dataset.key); renderClips(); break;
      case 'vf': ui.vf = el.dataset.f; store.set('vf', ui.vf); renderVideos(); break;
      case 'np-toggle': if (player) player.toggle(); break;
      case 'np-top': { const p = ed.querySelector('.player'); if (p) p.scrollIntoView({ block: 'center', behavior: CR.reduced() ? 'auto' : 'smooth' }); break; }
      case 'search-tx': searchTx(); break;
      case 'demo': CR.toast('Ejemplo: en el producto esta acción haría su trabajo.'); break;
      case 'reload': location.reload(); break;
      case 'retry': screen = null; route(CR.parseHash()); break;
      default: break;
    }
  });
  window.addEventListener('pagehide', () => { if (player && playerVideo) store.set('session', { v: playerVideo.id, t: player.time() }); });

  const run = CR.onRoute(route);
  run();
})();

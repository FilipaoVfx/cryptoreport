/* Selectores puros de tesis, ranking y contraste. Los usan ranking, ficha, Síntesis y Feed con los mismos filtros.
   No infieren nada: cuentan membresías aceptadas y vigentes publicadas en index.theses y afirmaciones del creador. */
(function (root) {
  'use strict';
  const Radar = typeof module !== 'undefined' && module.exports ? require('./radar.js') : root.UraniaRadar;
  const REL = { apoyo: 'Apoya', objecion: 'Objeta', matiz: 'Matiza' };
  const REL_GROUP = { apoyo: 'Apoyos', objecion: 'Objeciones', matiz: 'Matices' };
  const DIM = { direccion: 'dirección', momento: 'momento', alcance: 'alcance', mecanismo: 'mecanismo', beneficiario: 'activo beneficiario', condicion: 'condición' };
  // Relaciones semánticas con X: solo una conexión aceptada y vigente permite decir «apoya» o «cuestiona».
  const X_REL = { apoyo_declarado: 'Apoya', contrapunto: 'Cuestiona', actualizacion: 'Actualiza; no implica confirmar', contexto: 'Contexto; no suma respaldo' };
  const X_COUNTS = { apoyo_declarado: true, contrapunto: true, actualizacion: false, contexto: false };

  const block = (index) => (index && index.theses && index.theses.status === 'ok' ? index.theses : null);
  const video = (index, id) => (index.videosById ? index.videosById[id] : index.videos.find((v) => v.id === id));
  const claim = (index, v, c) => (index.claimsByKey ? index.claimsByKey[`${v}:${c}`] : index.claims.find((x) => x.v === v && x.id === c));

  /** Membresías vigentes dentro de los filtros de creador y periodo. */
  function members(index, filters = {}, now = Date.now()) {
    const b = block(index);
    if (!b) return [];
    return b.members.filter((m) => Radar.inWindow(video(index, m.v), filters, now));
  }
  /** Activos de una tesis: los de su definición. Solo una tesis de grupo (sin activos propios) se vincula a los activos
      que nombra explícitamente una afirmación miembro; así una tesis sobre BTC no se cuelga de otro activo citado de paso. */
  function linkedAssets(index, thesis, filters = {}, now = Date.now()) {
    const out = new Set(thesis.assets || []);
    if (out.size) return out;
    for (const m of members(index, filters, now)) {
      if (m.t !== thesis.id) continue;
      const c = claim(index, m.v, m.c);
      (c ? c.assets : []).forEach((a) => out.add(a));
    }
    return out;
  }
  /** Estadísticas de una tesis con los filtros dados: creadores como unión de identidades, nunca suma de columnas. */
  function thesisStats(index, thesisId, filters = {}, now = Date.now()) {
    const ms = members(index, filters, now).filter((m) => m.t === thesisId);
    const groups = { apoyo: [], objecion: [], matiz: [] };
    ms.forEach((m) => groups[m.rel].push(m));
    const sides = new Map();
    ms.forEach((m) => sides.set(m.ch, (sides.get(m.ch) || new Set()).add(m.rel)));
    return {
      members: ms, groups, creators: new Set(ms.map((m) => m.ch)),
      creatorsBy: Object.fromEntries(Object.entries(groups).map(([k, list]) => [k, new Set(list.map((m) => m.ch))])),
      // Un creador en varios lados (por fecha u horizonte) se marca; no es una contradicción automática.
      multiSide: [...sides].filter(([, rels]) => rels.size > 1).map(([ch, rels]) => ({ ch, rels: [...rels] })),
      last: ms.map((m) => video(index, m.v).pub).sort().reverse()[0] || '',
    };
  }
  /** Afirmaciones relevantes para un activo: activo explícito, atribuidas al creador y con cita de la transcripción. */
  function relevantClaims(index, assetId, filters = {}, now = Date.now()) {
    return index.claims.filter((c) => c.assets.includes(assetId) && c.radar && c.radar.speaker_role === 'creador' && c.quote
      && Radar.inWindow(video(index, c.v), filters, now));
  }
  /** Tesis aceptadas vinculadas a un activo con al menos una membresía vigente en los filtros. */
  function thesesForAsset(index, assetId, filters = {}, now = Date.now()) {
    const b = block(index);
    if (!b) return [];
    return b.items.filter((t) => thesisStats(index, t.id, filters, now).members.length && linkedAssets(index, t, filters, now).has(assetId));
  }
  /** Ranking por conversación analizada: creadores únicos → tesis distintas → evidencia más reciente → id. */
  function rankAssets(index, section, filters = {}, now = Date.now()) {
    const b = block(index);
    const classified = new Set(b ? members(index, filters, now).map((m) => `${m.v}:${m.c}`) : []);
    return index.topics.filter((t) => t.section === section).map((t) => {
      const claims = relevantClaims(index, t.id, filters, now);
      const vids = t.videos.filter((m) => Radar.inWindow(video(index, m.v), filters, now));
      return {
        t, claims, creators: new Set(claims.map((c) => video(index, c.v).ch)).size,
        theses: thesesForAsset(index, t.id, filters, now).map((x) => x.id),
        classifiedClaims: claims.filter((c) => classified.has(`${c.v}:${c.id}`)).length,
        last: claims.map((c) => video(index, c.v).pub).sort().reverse()[0] || '',
        mentions: vids.reduce((n, m) => n + m.n, 0), mentionVideos: vids.length,
        coverageKnown: !!b,
      };
    }).filter((r) => r.creators || r.mentionVideos)
      .sort((a, b2) => b2.creators - a.creators || b2.theses.length - a.theses.length || b2.last.localeCompare(a.last) || a.t.id.localeCompare(b2.t.id));
  }
  /** Tesis en las que participa un vídeo, con su relación. Para la Síntesis. */
  function forVideo(index, videoId) {
    const b = block(index);
    if (!b) return [];
    return b.items.map((t) => {
      const mine = b.members.filter((m) => m.t === t.id && m.v === videoId);
      if (!mine.length) return null;
      const rels = [...new Set(mine.map((m) => m.rel))];
      const assets = [...linkedAssets(index, t)];
      return { id: t.id, label: t.label, assets, relationLabel: rels.map((r) => REL[r]).join(' y '),
        creators: new Set(b.members.filter((m) => m.t === t.id).map((m) => m.ch)).size };
    }).filter(Boolean);
  }
  /** Conexiones con X heredables por una tesis: misma afirmación miembro, mismo hash de análisis, vigente y post intacto. */
  function xConnections(index, links, posts, thesisId, filters = {}, now = Date.now()) {
    const ms = members(index, filters, now).filter((m) => !thesisId || m.t === thesisId);
    const keys = new Set(ms.map((m) => `${m.v}:${m.c}`));
    return (links && links.connections || []).filter((x) => x.status === 'aceptado' && keys.has(`${x.video_id}:${x.claim_id}`)
      && video(index, x.video_id) && x.analysis_sha256 === video(index, x.video_id).analysis_sha256
      && Date.parse(x.expires_at) > now && posts.get(x.post_id) && posts.get(x.post_id).content_hash === x.post_content_hash);
  }
  /** Posts que solo comparten el activo: contexto separado, nunca apoyo. */
  function assetContext(feedPosts, symbol) {
    return symbol ? feedPosts.filter((p) => (p.quality && p.quality.assets || []).includes(symbol)) : [];
  }
  /** Rótulo de un contraste detectado por reglas: un cambio entre autores distintos no es un cambio de postura personal. */
  function contrastLabel(pair) {
    if (pair.kind !== 'cambio') return pair.sameCreator ? 'Repite la idea' : 'Coinciden fuentes distintas';
    return pair.sameCreator ? 'Cambio de postura del mismo creador' : 'Contraste entre fuentes';
  }
  const api = { REL, REL_GROUP, DIM, X_REL, X_COUNTS, members, linkedAssets, thesisStats, relevantClaims, thesesForAsset, rankAssets, forVideo, xConnections, assetContext, contrastLabel };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.UraniaTheses = api;
})(typeof window !== 'undefined' ? window : globalThis);

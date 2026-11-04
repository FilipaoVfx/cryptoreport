/* Pure local query and evidence rules. Kept separate for reproducible checks. */
(function (root) {
  'use strict';
  const normalize = (s) => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
  const order = ['alcista', 'bajista', 'mixta', 'neutra'];
  function parse(query, topics) {
    const q = normalize(query).replace(/\s+/g, ' ');
    const match = q.match(/^(short|long|bajista|alcista)(?:\s+(.+))?$/);
    if (!match) return null;
    const direction = /short|bajista/.test(match[1]) ? 'bajista' : 'alcista';
    const term = (match[2] || '').replace(/^\$/, '');
    const candidates = term ? topics.filter((t) => [t.id, t.name, t.sym].some((x) => normalize(x) === term)) : [];
    return { direction, term, asset: candidates.length === 1 ? candidates[0].id : null, unresolved: !!term && candidates.length !== 1, candidates };
  }
  function inWindow(video, filters, now = Date.now()) {
    if (!video || (filters.c && filters.c !== 'todos' && video.ch !== filters.c)) return false;
    if (!filters.p || filters.p === 'todo') return true;
    const hours = { '1d': 24, '2d': 48, '3d': 72 }[filters.p];
    const age = now - Date.parse(video.pub);
    return !!hours && age >= 0 && age <= hours * 3600000;
  }
  function rows(index, intent, filters, now = Date.now()) {
    if (!intent || intent.unresolved) return [];
    const pool = index.claims.filter((c) => c.radar && c.radar.eligible && c.quote && inWindow(index.videosById[c.v], filters, now)
      && (filters.own !== '1' || (c.radar.position_status === 'declarada' && c.radar.position_side === (intent.direction === 'alcista' ? 'long' : 'short'))));
    return index.topics.filter((t) => (!intent.asset || t.id === intent.asset) && (!filters.s || filters.s === 'todo' || filters.s === t.section)).map((t) => {
      const claims = pool.filter((c) => c.assets.includes(t.id) && (c.radar.asset_directions?.[t.id] || c.radar.direction) === intent.direction).sort((a, b) => index.videosById[b.v].pub.localeCompare(index.videosById[a.v].pub) || (a.t || 0) - (b.t || 0) || a.id.localeCompare(b.id));
      return { t, claims, creators: new Set(claims.map((c) => index.videosById[c.v].ch)).size, videos: new Set(claims.map((c) => c.v)).size, last: claims.length ? index.videosById[claims[0].v].pub : '' };
    }).filter((r) => r.claims.length).sort((a, b) => b.creators - a.creators || b.videos - a.videos || b.last.localeCompare(a.last) || a.t.id.localeCompare(b.t.id));
  }
  function category(claim, assetId) {
    return claim.radar ? claim.radar.asset_directions?.[assetId] || claim.radar.direction : claim.pol || 'neutra';
  }
  function evidence(index, topic, frags, filters) {
    const claims = topic.claims.map((ref) => index.claimsByKey[`${ref.v}:${ref.id}`]).filter((c) => c && inWindow(index.videosById[c.v], filters));
    const normalized = (s) => normalize(s).replace(/[^a-z0-9]/g, '');
    const byPassage = new Map();
    for (const c of claims.filter((x) => x.quote)) {
      const key = `${c.v}:${normalized(c.quote)}`, pol = category(c, topic.id);
      const old = byPassage.get(key);
      if (!old) { byPassage.set(key, { ...c, text:c.quote, summary:c.text, pol, kind:'analysis' }); continue; }
      if (old.pol !== pol) old.pol = old.pol === 'neutra' ? pol : pol === 'neutra' ? old.pol : 'mixta';
      if (!old.summary.includes(c.text)) old.summary += ' · ' + c.text;
      if (old.radar && c.radar) {
        const join = (a,b) => [...new Set([a,b].filter(Boolean))].join(' · ') || null;
        old.radar = {...old.radar, horizon:join(old.radar.horizon,c.radar.horizon), conditions:join(old.radar.conditions,c.radar.conditions), invalidation:join(old.radar.invalidation,c.radar.invalidation)};
      }
    }
    const items = [...byPassage.values()];
    for (const frag of frags) {
      if (!inWindow(index.videosById[frag.v], filters)) continue;
      const duplicate = items.some((x) => x.v === frag.v && (normalized(x.text) === normalized(frag.text)
        || (x.t != null && frag.t != null && Math.abs(x.t - frag.t) < 12 && (normalized(x.text).includes(normalized(frag.text)) || normalized(frag.text).includes(normalized(x.text))))));
      if (!duplicate) items.push({ ...frag, kind: 'transcript' });
    }
    const seen = new Set();
    return items.filter((x) => {
      const key = `${x.v}:${normalized(x.text)}`;
      if (seen.has(key)) return false;
      seen.add(key); return true;
    }).sort((a, b) => order.indexOf(a.pol) - order.indexOf(b.pol) || index.videosById[b.v].pub.localeCompare(index.videosById[a.v].pub) || (a.t || 0) - (b.t || 0) || String(a.id || '').localeCompare(String(b.id || '')));
  }
  const api = { parse, inWindow, rows, evidence, category, order };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.UraniaRadar = api;
})(typeof window !== 'undefined' ? window : globalThis);

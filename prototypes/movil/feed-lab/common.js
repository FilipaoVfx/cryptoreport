/* Laboratorio del Feed de X: utilidades comunes a las 4 propuestas. Usa el filtrado seguro de b4-urania/feed.js. */
(function () {
  'use strict';
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const TONES = ['#c6ff4a', '#b69cff', '#6fd3ff', '#ff9d7a', '#5fe3c8', '#f6c65b', '#ff8fc4', '#9fe6ff'];

  function rel(iso, now = Date.now()) {
    const m = Math.max(0, Math.round((now - Date.parse(iso)) / 60000));
    if (m < 1) return 'ahora';
    if (m < 60) return `${m} min`;
    const h = Math.round(m / 60);
    if (h < 24) return `${h} h`;
    const d = Math.round(h / 24);
    return d === 1 ? 'ayer' : `${d} d`;
  }
  function day(iso) {
    const d = new Date(iso), t = new Date(), y = new Date(); y.setDate(t.getDate() - 1);
    if (d.toDateString() === t.toDateString()) return 'Hoy';
    if (d.toDateString() === y.toDateString()) return 'Ayer';
    return d.toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'short' });
  }
  const compact = (t) => t.replace(/\n\s*\n+/g, '\n').trim();

  async function load() {
    const r = await fetch('../../data/social-feed.json', { cache: 'no-store' });
    if (!r.ok) throw Error('Feed no disponible');
    const data = await r.json();
    if (data.version !== 1 || !Array.isArray(data.posts)) throw Error('Formato inválido');
    const accounts = new Map(data.accounts.map((a, i) => {
      const withAvatar = data.posts.find((p) => p.author_handle === a.handle && p.avatar_url);
      return [a.handle, { ...a, tone: TONES[i % TONES.length], avatar: withAvatar ? window.UraniaFeed.safeURL(withAvatar.avatar_url, true) : null,
        initials: (a.name || a.handle).split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase() }];
    }));
    const pick = (quality) => window.UraniaFeed.select(data, { account: 'todos', period: 'cuenta', quality, length: 'todos', narrative: 'todas', q: '' });
    return { data, accounts, relevant: pick('relevante'), all: pick('todos') };
  }

  function assetCounts(posts) {
    const c = new Map();
    for (const p of posts) for (const s of p.quality?.assets || []) c.set(s, (c.get(s) || 0) + 1);
    return [...c].sort((a, b) => b[1] - a[1]);
  }
  const avatar = (a, cls = 'av') => `<span class="${cls}" style="--ac:${a.tone}" aria-hidden="true"><span>${esc(a.initials)}</span>${a.avatar ? `<img src="${esc(a.avatar)}" alt="" loading="lazy">` : ''}</span>`;
  const text = (p, full = false) => window.UraniaFeed.textHTML(full ? p.text : compact(p.text), esc);
  const xURL = (p) => `https://x.com/i/web/status/${encodeURIComponent(p.id)}`;

  /* Hoja inferior de vidrio con la publicación completa. Cada propuesta la viste con su CSS (.fl-sheet). */
  function sheet(p, a) {
    let el = document.getElementById('fl-sheet');
    if (!el) {
      el = document.createElement('div');
      el.id = 'fl-sheet';
      el.innerHTML = '<div class="fl-scrim" data-close></div><section class="fl-sheet" role="dialog" aria-modal="true" aria-labelledby="fl-sheet-name"><div class="fl-grip" data-close></div><div class="fl-body"></div></section>';
      document.body.append(el);
      el.addEventListener('click', (e) => { if (e.target.closest('[data-close]')) close(); });
      document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
    }
    const assets = (p.quality?.assets || []).map((s) => `<span class="fl-tag">$${esc(s)}</span>`).join('');
    const narr = (p.quality?.narratives || []).map((s) => `<span class="fl-tag soft">${esc(s.replaceAll('_', ' '))}</span>`).join('');
    el.querySelector('.fl-body').innerHTML = `<header class="fl-sh">${avatar(a)}<div><b id="fl-sheet-name">${esc(a.name || a.handle)}</b><small>@${esc(a.handle)} · ${esc(rel(p.published_at))}</small></div><button type="button" class="fl-x" data-close aria-label="Cerrar">✕</button></header>
      <div class="fl-text">${text(p, true)}</div>${assets || narr ? `<p class="fl-tags">${assets}${narr}</p>` : ''}
      <a class="fl-open" href="${xURL(p)}" target="_blank" rel="noopener noreferrer">Abrir en X ↗</a>
      <p class="fl-fine">Texto tal como lo publicó la cuenta, sin verificación externa.</p>`;
    el.hidden = false;
    requestAnimationFrame(() => el.classList.add('open'));
    document.body.style.overflow = 'hidden';
    el.querySelector('.fl-x').focus({ preventScroll: true });
  }
  function close() {
    const el = document.getElementById('fl-sheet');
    if (!el || el.hidden) return;
    el.classList.remove('open');
    document.body.style.overflow = '';
    setTimeout(() => { el.hidden = true; }, 260);
  }

  window.FL = { esc, rel, day, load, assetCounts, avatar, text, xURL, sheet, compact };
})();

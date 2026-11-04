(() => {
  'use strict';
  const banner = document.createElement('aside');
  banner.className = 'pwa-status';
  banner.setAttribute('role', 'status');
  banner.setAttribute('aria-live', 'polite');
  banner.hidden = true;
  const label = document.createElement('span');
  const update = document.createElement('button');
  update.type = 'button'; update.textContent = 'Actualizar'; update.hidden = true;
  banner.append(label, update); document.body.append(banner);
  let waiting = null, reloading = false, prompt = null;
  const stalePaths = new Set();
  function status() {
    banner.hidden = navigator.onLine && !stalePaths.size && !waiting;
    label.textContent = !navigator.onLine ? 'Sin conexión · puedes leer lo que ya abriste.' : stalePaths.size ? 'Sin actualización · mostrando los últimos datos guardados.' : waiting ? 'Hay una versión nueva de CryptoReport.' : '';
    update.hidden = !waiting || !navigator.onLine;
  }
  window.addEventListener('offline', status);
  window.addEventListener('online', () => {
    status();
    for (const path of stalePaths) fetch(path, { cache: 'no-cache' }).catch(() => {});
  });
  update.addEventListener('click', () => waiting?.postMessage({ type: 'SKIP_WAITING' }));
  const install = document.querySelector('[data-pwa-install]');
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault(); prompt = event;
    if (install) install.hidden = matchMedia('(display-mode: standalone)').matches;
  });
  install?.addEventListener('click', async () => {
    if (!prompt) return;
    install.hidden = true;
    try { await prompt.prompt(); await prompt.userChoice; } finally { prompt = null; }
  });
  window.addEventListener('appinstalled', () => { prompt = null; if (install) install.hidden = true; });
  status();
  if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
  let controlled = !!navigator.serviceWorker.controller;
  navigator.serviceWorker.addEventListener('message', event => {
    const data = event.data;
    if (typeof data?.path !== 'string' || !data.path.startsWith('/data/')) return;
    if (data.type === 'DATA_FALLBACK') stalePaths.add(data.path);
    else if (data.type === 'DATA_FRESH') stalePaths.delete(data.path);
    else return;
    status();
  });
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (controlled && !reloading) { reloading = true; location.reload(); }
    controlled = true;
  });
  navigator.serviceWorker.register('/sw.js', { scope: '/', updateViaCache: 'none' }).then(async registration => {
    if (registration.waiting) { waiting = registration.waiting; status(); }
    registration.addEventListener('updatefound', () => {
      const worker = registration.installing;
      worker?.addEventListener('statechange', () => {
        if (worker.state === 'installed' && navigator.serviceWorker.controller) { waiting = registration.waiting; status(); }
      });
    });
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) await new Promise(resolve => navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true }));
    // Warm the index only after the first worker controls the page, even on the first visit.
    if (navigator.onLine) fetch('/data/index.json', { cache: 'no-cache' }).catch(() => {});
  }).catch(() => { /* The application remains usable if a browser disallows service workers. */ });
})();

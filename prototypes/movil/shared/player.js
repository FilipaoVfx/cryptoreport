/* Reproductor compartido: YouTube (IFrame API) con salto a cualquier segundo y reloj sincronizado.
   Si YouTube no carga, el vídeo no permite incrustarse o se pide ?sim=1, pasa a una vista sin vídeo
   cuyo reloj avanza igual: la transcripción y los hallazgos siguen funcionando. El nodo del reproductor
   nunca se mueve en el DOM (moverlo recargaría el iframe): el minirreproductor es solo CSS. */
(function () {
  'use strict';
  const CR = window.CR;
  const FORCE_SIM = new URLSearchParams(location.search).has('sim');
  const YT_STATES = { '-1': 'unstarted', 0: 'ended', 1: 'playing', 2: 'paused', 3: 'buffering', 5: 'cued' };
  const ERRORS = {
    2: 'YouTube rechazó la petición del vídeo.',
    5: 'Este navegador no pudo reproducir el vídeo.',
    100: 'El vídeo ya no está disponible: es privado o se retiró.',
    101: 'El creador no permite reproducir este vídeo fuera de YouTube.',
    150: 'El creador no permite reproducir este vídeo fuera de YouTube.',
  };

  let apiPromise = null;
  function loadApi(timeout = 9000) {
    if (window.YT && window.YT.Player) return Promise.resolve(window.YT);
    if (!apiPromise) {
      apiPromise = new Promise((resolve, reject) => {
        const prev = window.onYouTubeIframeAPIReady;
        window.onYouTubeIframeAPIReady = () => { if (prev) prev(); resolve(window.YT); };
        const s = document.createElement('script');
        s.src = 'https://www.youtube.com/iframe_api';
        s.async = true;
        s.onerror = () => reject(new Error('api'));
        document.head.appendChild(s);
        setTimeout(() => reject(new Error('timeout')), timeout);
      });
      apiPromise.catch(() => { apiPromise = null; });
    }
    return apiPromise;
  }

  class Player {
    constructor(host, opts = {}) {
      this.host = host;
      this.opts = opts;
      this.video = null;
      this.t = 0;
      this.playing = false;
      this.state = 'idle';
      this.mode = 'idle';
      this.reason = '';
      this.listeners = { time: new Set(), state: new Set() };
      host.classList.add('crp');
      host.innerHTML = `
        <div class="crp-frame"><div class="crp-yt"></div></div>
        <div class="crp-sim" hidden>
          <div class="crp-note"><p class="crp-msg"></p><a class="crp-open" target="_blank" rel="noopener">Abrir en YouTube</a></div>
        </div>`;
      this.frame = host.querySelector('.crp-frame');
      this.sim = host.querySelector('.crp-sim');
      this.ticker = setInterval(() => this.tick(), 250);
      this.lastTick = performance.now();
    }

    on(type, fn) { this.listeners[type].add(fn); return () => this.listeners[type].delete(fn); }
    emit(type, value) { this.listeners[type].forEach((fn) => fn(value, this)); }
    setState(state) {
      this.state = state;
      this.playing = state === 'playing';
      this.host.dataset.state = state;
      this.emit('state', state);
    }

    get duration() { return (this.video && this.video.dur) || (this.yt && this.yt.getDuration && this.yt.getDuration()) || 0; }

    async load(video, { start = 0, autoplay = false } = {}) {
      const same = this.video && this.video.id === video.id;
      this.video = video;
      this.t = start;
      this.host.dataset.short = video.short ? '1' : '0';
      this.emit('time', start);
      if (same && this.mode !== 'idle') return this.seek(start, { play: autoplay });
      if (FORCE_SIM) return this.toSim('Vista de prueba sin YouTube: el reloj avanza con la transcripción.', autoplay);
      try {
        const YT = await loadApi();
        if (this.video !== video) return; // cambió de vídeo mientras cargaba la API
        if (!this.yt) {
          await new Promise((resolve) => {
            this.yt = new YT.Player(this.frame.querySelector('.crp-yt'), {
              host: 'https://www.youtube-nocookie.com',
              videoId: video.id,
              width: '100%',
              height: '100%',
              playerVars: { playsinline: 1, rel: 0, modestbranding: 1, iv_load_policy: 3, start: Math.floor(start), autoplay: autoplay ? 1 : 0, origin: location.origin },
              events: {
                onReady: () => resolve(),
                onStateChange: (e) => this.onYTState(e.data),
                onError: (e) => this.toSim(ERRORS[e.data] || 'YouTube no pudo reproducir este vídeo.', false, 'error'),
              },
            });
            setTimeout(resolve, 8000);
          });
        } else if (autoplay) {
          this.yt.loadVideoById({ videoId: video.id, startSeconds: start });
        } else {
          this.yt.cueVideoById({ videoId: video.id, startSeconds: start });
        }
        this.mode = 'youtube';
        this.frame.hidden = false;
        this.sim.hidden = true;
        this.host.dataset.mode = 'youtube';
        if (this.state === 'idle') this.setState('cued');
      } catch (e) {
        this.toSim('No se pudo cargar el reproductor de YouTube. El reloj avanza con la transcripción.', autoplay);
      }
    }

    toSim(message, autoplay, state) {
      this.mode = 'sim';
      this.reason = message;
      this.host.dataset.mode = 'sim';
      this.frame.hidden = true;
      this.sim.hidden = false;
      let img = this.sim.querySelector('.crp-poster');
      if (!img) {
        img = new Image();
        img.className = 'crp-poster';
        img.alt = '';
        img.decoding = 'async';
        this.sim.prepend(img);
      }
      img.src = CR.thumb(this.video.id, 'hq');
      this.sim.querySelector('.crp-msg').textContent = message;
      this.updateOpenLink();
      this.setState(state || 'paused');
      if (autoplay && state !== 'error') this.play();
    }

    updateOpenLink() {
      const a = this.sim.querySelector('.crp-open');
      if (a && this.video) a.href = CR.yt(this.video.id, this.t);
    }

    onYTState(code) {
      const state = YT_STATES[code] || 'unknown';
      this.setState(state);
      if (state === 'playing') clearTimeout(this.tapTimer);
    }

    tick() {
      const now = performance.now();
      const dt = (now - this.lastTick) / 1000;
      this.lastTick = now;
      if (this.mode === 'youtube' && this.yt && this.yt.getCurrentTime && this.playing) {
        const t = this.yt.getCurrentTime();
        if (typeof t === 'number' && Math.abs(t - this.t) > 0.01) { this.t = t; this.emit('time', t); }
      } else if (this.mode === 'sim' && this.playing) {
        this.t = Math.min(this.duration || Infinity, this.t + dt);
        this.emit('time', this.t);
        if (this.duration && this.t >= this.duration) this.setState('ended');
        if (Math.round(this.t) % 5 === 0) this.updateOpenLink();
      }
    }

    watchTap() {
      clearTimeout(this.tapTimer);
      this.tapTimer = setTimeout(() => {
        if (this.mode === 'youtube' && !['playing', 'buffering'].includes(this.state)) this.emit('state', 'needs-tap');
      }, 1600);
    }

    seek(t, { play = true } = {}) {
      const dur = this.duration;
      this.t = Math.max(0, dur ? Math.min(t, dur - 0.5) : t);
      this.emit('time', this.t);
      if (this.mode === 'youtube' && this.yt && this.yt.seekTo) {
        this.yt.seekTo(this.t, true);
        if (play) { this.yt.playVideo(); this.watchTap(); }
      } else if (this.mode === 'sim') {
        this.updateOpenLink();
        if (play) this.setState('playing');
      }
    }

    play() {
      if (this.mode === 'youtube' && this.yt && this.yt.playVideo) { this.yt.playVideo(); this.watchTap(); }
      else if (this.mode === 'sim' && this.state !== 'error') { if (this.duration && this.t >= this.duration - 1) this.t = 0; this.setState('playing'); }
    }

    pause() {
      if (this.mode === 'youtube' && this.yt && this.yt.pauseVideo) this.yt.pauseVideo();
      else if (this.mode === 'sim' && this.state !== 'error') this.setState('paused');
    }

    /** Libera el reproductor (las interfaces que lo recrean por pantalla guardan antes el segundo). */
    destroy() {
      clearInterval(this.ticker);
      clearTimeout(this.tapTimer);
      try { if (this.yt && this.yt.destroy) this.yt.destroy(); } catch (e) { /* ya no existía */ }
      this.yt = null;
      this.listeners.time.clear();
      this.listeners.state.clear();
      this.host.innerHTML = '';
      this.host.classList.remove('crp');
    }

    toggle() { if (this.playing) this.pause(); else this.play(); }
    skip(delta) { this.seek(this.time() + delta, { play: this.playing }); }
    time() {
      if (this.mode === 'youtube' && this.yt && this.yt.getCurrentTime) {
        const t = this.yt.getCurrentTime();
        if (typeof t === 'number') this.t = t;
      }
      return this.t;
    }
  }

  CR.Player = Player;
})();

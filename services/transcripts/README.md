# Servicio de transcripciones

Obtiene de forma autónoma el texto, con sus tiempos, de cada video nuevo de **Nacho IC** y **KManuS88**. Corre en el VPS con un timer de systemd cada 15 minutos.

```
RSS de cada canal ──► videos nuevos (ventana 72 h) ──► 1. Scraper.Tech captions.php (es)   gratis (1.000/mes)
                                                   ├─► 2. yt-dlp local                     gratis (hoy bloqueado)
                                                   ├─► 3. Supadata nativo                  1 crédito, solo si 1 y 2 fallan
                                                   └─► 4. Supadata generate (IA)           2 créditos/min, a las 6 h sin subtítulos
                                                          │
                                       JSON + Markdown en disco · SQLite (estado, intentos, cuota) · aviso Telegram
```

- **Descubrimiento:** se lee el RSS público de cada canal, que trae las últimas 15 publicaciones. Se detecta si cada una es un short con `HEAD /shorts/<id>`, que no consume cuota.
- **Subtítulos:** se pide la pista original en español. Las pistas `ar/en/pt` vienen del doblaje automático y no se usan. Ante `data=null` se hace un reintento inmediato.
- **Supadata (respaldo de pago).** En modo nativo solo se consulta si los proveedores gratuitos fallan, nunca cuando ya se sabe que aún no hay subtítulos, porque su respuesta 206 también se cobra.
- **Generación con IA.** A las 6 h sin subtítulos se genera el texto desde el audio, solo si se cumplen tres condiciones:
  - el video tiene **una sola pista de audio**;
  - se conoce su duración;
  - el costo cabe en el tope mensual (`CR_SUPADATA_MONTHLY_CREDITS`) y en el saldo real que da `/me`.

  Si el trabajo sigue en curso, se guarda su `jobId` y se consulta gratis en el siguiente ciclo, sin volver a pagar. Un resultado en otro idioma se descarta y no se repite.
- **Validación:** `video.php` aporta la duración para calcular la cobertura, es decir, hasta dónde llegan los subtítulos. Con cobertura menor del 85 % el video queda marcado para revisión. Justo después de publicarse, `video.php` a veces no trae la duración (ocurrió el 12 oct). Si falta, cada ciclo la vuelve a pedir para los videos de los últimos 7 días, con un máximo de 3 por ciclo y dos intentos, y reescribe el JSON y el Markdown con la cobertura correcta.
- **Reintentos:** si los subtítulos aún no existen, se reintenta a los 15 min, 30 min, 1 h, 2 h y 4 h, y después cada 6 h. A las 72 h el video pasa a `no_captions` y se avisa. Con errores del proveedor, a los 8 intentos pasa a `failed`.
- **RSS inestable y respaldo.** El 9 de octubre falló el 52 % de las peticiones sueltas, y el 10 de octubre estuvo caído más de una hora seguida. Cada canal se reintenta hasta 6 veces, durante aproximadamente 1 minuto.
  - Si el RSS sigue caído, se leen las páginas **/videos, /streams y /shorts** del canal (`channel_pages.py`), que sí responden desde el VPS. Se piden en español porque con otro idioma YouTube traduce los títulos.
  - Videos y directos traen fecha relativa ("hace 18 h"); entran si están dentro de la ventana de 72 h.
  - Los shorts no traen fecha: solo cuentan los que aparecen por encima del primer short ya conocido.
  - La fecha exacta se corrige con `video.php` al transcribir, o con el RSS cuando vuelva.
  - En la web, esos ciclos salen en ámbar. Se avisa solo si un canal lleva 3 ciclos seguidos sin RSS.
- **Avisos:** se envían en las transiciones (nueva transcripción, fallo definitivo, proveedor caído o recuperado, 80 % de la cuota de Scraper.Tech, falta de saldo en Supadata), no en cada ciclo.

## Salida

En `/var/lib/cryptoreport-transcripts/`:

| Ruta | Contenido |
| --- | --- |
| `transcripts/<canal>/<fecha>_<video_id>.json` | Contrato completo (`schema_version: 1`): metadatos del video, proveedor, idioma, cobertura y **segmentos originales** `{start, dur, text}`. Se conservan las repeticiones y no se recorta nada. |
| `transcripts/<canal>/<fecha>_<video_id>.md` | Vista legible en bloques de unos 30 s, con enlace a cada minuto del video. |
| `state.sqlite` | Tablas `videos` (estado por video), `attempts` (cada llamada, con resultado, latencia y solicitudes) y `kv` (estado de los avisos). |
| `last-run.json` | Resumen del último ciclo. |

## Operación

```sh
cd /root/cryptoreport/services/transcripts
.venv/bin/python -m crtranscripts status                 # últimos videos, estado y cuota del mes
.venv/bin/python -m crtranscripts run                    # un ciclo ahora (lo mismo que hace el timer)
.venv/bin/python -m crtranscripts fetch <id> --channel nacho [--published 2026-09-01T10:00:00+00:00]  # forzar un video (p. ej. histórico)
journalctl -u cryptoreport-transcripts.service -n 50     # registros
python3 -m unittest discover -s tests -t .               # pruebas (sin red)
sudo ops/install.sh                                      # instalar o actualizar las unidades de systemd
```

La configuración está en `.env` (ver `.env.example`, `chmod 600`, no se versiona). La única obligatoria es `SCRAPER_TECH_KEY`, que debe estar suscrita a la **YouTube API general** de Scraper.Tech. Para recibir avisos en Telegram hay que definir `CR_TELEGRAM_BOT_TOKEN` y `CR_TELEGRAM_CHAT_ID`; sin ellas, los avisos quedan en el journal.

## Sitio web

`https://cryptoreport.2-25-233-186.sslip.io` (usuario `crypto`, contraseña en `/root/.cryptoreport-site-password`) muestra el pipeline, los ciclos del RSS y un visor de todas las transcripciones con búsqueda.

- **Se actualiza solo.** Al final de cada ciclo, `run` escribe `data.json` en `/var/www/cryptoreport` (`CR_SITE_DIR`), y la página lo vuelve a leer cada 5 min.
- **Los JSON se sirven directamente** desde `/var/lib/cryptoreport-transcripts/transcripts/` mediante un `alias` de nginx, sin copias. El listado está en `/transcripts/`.
- **El historial de ciclos** se guarda en la tabla `runs` de `state.sqlite`.
- **Código:** `site/index.html`. Tailwind se compila en local, sin CDN, con `site/tailwind.config.js`.
- **nginx:** `ops/nginx-cryptoreport.conf`, con contraseña, HTTPS de Let's Encrypt y cabeceras CSP y `noindex`.
- **Instalar o actualizar:** `sudo ops/install-site.sh`. Si certbot ya añadió HTTPS, no lo pisa.
- **Regenerar `data.json` a mano:** `.venv/bin/python -m crtranscripts site`.

## Costo

En Scraper.Tech, cada video consume **2 solicitudes** (subtítulos y duración), más el reintento ocasional. La carga inicial de 13 videos gastó 30: 26 de base y 4 reintentos.

Supadata solo gasta cuando Scraper.Tech falla: 1 crédito por video en modo nativo, o 2 créditos por minuto si genera. En las pruebas del 9 de octubre se usaron 9 de los 100 créditos del plan Free.

Con unos 130 videos al mes entre los dos canales, el consumo ronda las **300 solicitudes**. El plan Free cubre 1.000 al mes y Basic cuesta $2 por 50.000. El servicio no necesita LLM ni audio.

## Qué se probó (8 y 9 de octubre de 2026, desde este VPS de Hostinger)

| Ruta | Resultado |
| --- | --- |
| HTML de `watch` por HTTP directo | ❌ `LOGIN_REQUIRED` en los 4 videos |
| `youtube-transcript-api` | ❌ `RequestBlocked` en los videos de los canales; ✅ en un video muy popular de control |
| `yt-dlp` 2026.08.19 con 7 clientes (`default`, `android_vr`, `tv_simply`, `web_embedded`, `mweb`, `ios`, `tv`), por IPv4 e IPv6 | ❌ "Sign in to confirm you're not a bot"; ✅ en el video de control. El bloqueo depende del video, no de toda la IP. |
| Scraper.Tech **Youtube Transcript** (`youtube-transcript3`) | ❌ `Some error occured` en 6 de 6 solicitudes ([detalle](../../docs/validaciones/scraper-tech-2026-10-08/README.md)) |
| Scraper.Tech **YouTube API** `captions.php` por **POST** | ✅ **13 de 13 videos**, cobertura del 97,5 al 100 %, incluido un directo de 1 h 08 min. Alrededor del 30 % de las primeras consultas devolvió `data=null` tras 15-20 s y funcionó al repetir. |
| `captions.php` por GET | ❌ `data=null` en la única prueba. Se usa POST, como el playground oficial. |
| **Supadata** `mode=native` | ✅ 4 de 4 videos, en 3,5-5 s y 1 crédito cada uno. Mismos segmentos y tiempos que Scraper.Tech; en 2 segmentos quita comas. |
| **Supadata** `mode=generate` | ⚠️ Transcribe la pista **doblada al árabe**, no el original. Pasó en 2 de 2 llamadas al mismo short y cada una costó 2 créditos. La API no permite elegir la pista de audio. Por eso no se genera en videos con varias pistas de audio (los metadatos de Scraper.Tech las listan) y se rechaza cualquier resultado que no esté en español. |

## Pendiente

- **Videos con doblaje y sin subtítulos.** Supadata `generate` no puede elegir la pista original, así que estos videos terminan en `no_captions` y se avisa. Es un caso poco probable, porque el doblaje automático parte de los subtítulos del original. Si ocurre, la salida sería descargar la pista `es` original con un proxy residencial (`CR_YTDLP_PROXY`) y transcribirla con Groq o whisper.
- **Respaldo gratuito.** `yt-dlp` sigue en la cadena porque no cuesta nada y vuelve a funcionar si YouTube deja de marcar la IP o si se configura un proxy o cookies (`CR_YTDLP_COOKIES`). Hoy siempre devuelve `blocked`.
- **Latencia.** El sondeo cada 15 min más el tiempo que tarda YouTube en generar los subtítulos dejan la demora típica por debajo de 30 min. Con WebSub (PubSubHubbub) se reduciría el primer tramo, pero necesita un endpoint HTTPS público.
- **Histórico.** El ciclo solo encola lo publicado en las últimas 72 h. Para cargar el pasado hay que usar `fetch` con `--published`, o listar la playlist de subidas del canal con `playlist_videos.php`.
- **Integración.** Faltan la extracción de afirmaciones con LLM sobre estos JSON y el volcado a la base del producto (ver `docs/plan-extraccion-datos.md`).

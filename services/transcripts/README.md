# Servicio de transcripciones

Obtiene de forma autónoma el texto, con sus tiempos, de cada video nuevo de **Nacho IC** y **KManuS88**. Corre en el VPS con un timer de systemd cada 15 minutos.

```
RSS de cada canal ──► videos nuevos (ventana 72 h) ──► Scraper.Tech captions.php (es) ──► JSON + Markdown en disco
                                                   └─► respaldo yt-dlp local           └─► SQLite (estado, intentos, cuota)
                                                                                         └─► aviso Telegram (opcional)
```

- **Descubrimiento:** se lee el RSS público de cada canal, que trae las últimas 15 publicaciones. Se detecta si cada una es un short con `HEAD /shorts/<id>`, que no consume cuota.
- **Subtítulos:** se pide la pista original en español. Las pistas `ar/en/pt` vienen del doblaje automático y no se usan. Ante `data=null` se hace un reintento inmediato.
- **Validación:** `video.php` aporta la duración para calcular la cobertura, es decir, hasta dónde llegan los subtítulos. Con cobertura menor del 85 % el video queda marcado para revisión.
- **Reintentos:** si los subtítulos aún no existen, se reintenta a los 15 min, 30 min, 1 h, 2 h y 4 h, y después cada 6 h. A las 72 h el video pasa a `no_captions` y se avisa. Con errores del proveedor, a los 8 intentos pasa a `failed`.
- **Avisos:** se envían en las transiciones (nueva transcripción, fallo definitivo, RSS o proveedor caído y recuperado, 80 % de la cuota mensual), no en cada ciclo.

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

## Costo

Cada video consume **2 solicitudes** (subtítulos y duración), más el reintento ocasional. La carga inicial de 13 videos gastó 30: 26 de base y 4 reintentos.

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

## Pendiente

- **Videos sin subtítulos.** Aún no hay respaldo por audio. Groq Whisper o whisper local necesitan descargar el audio, y esa descarga está igual de bloqueada desde esta IP. Si aparecen casos `no_captions`, el siguiente paso es un proxy residencial (`CR_YTDLP_PROXY`, unos $1/GB; una transcripción ocupa KB) o Supadata en modo `generate`.
- **Respaldo gratuito.** `yt-dlp` sigue en la cadena porque no cuesta nada y vuelve a funcionar si YouTube deja de marcar la IP o si se configura un proxy o cookies (`CR_YTDLP_COOKIES`). Hoy siempre devuelve `blocked`.
- **Latencia.** El sondeo cada 15 min más el tiempo que tarda YouTube en generar los subtítulos dejan la demora típica por debajo de 30 min. Con WebSub (PubSubHubbub) se reduciría el primer tramo, pero necesita un endpoint HTTPS público.
- **Histórico.** El ciclo solo encola lo publicado en las últimas 72 h. Para cargar el pasado hay que usar `fetch` con `--published`, o listar la playlist de subidas del canal con `playlist_videos.php`.
- **Integración.** Faltan la extracción de afirmaciones con LLM sobre estos JSON y el volcado a la base del producto (ver `docs/plan-extraccion-datos.md`).

# Plan de extracción de datos: Nacho IC y KManuS88

Objetivo: sacar toda la data útil de los dos canales y convertirla en información curada para decidir, con la menor latencia y el menor costo posibles. Herramientas: **Trigger.dev** como orquestador, **last30days** para el contexto de la multitud, **Agent-Reach** para explorar a mano, y la API de Claude para la extracción.

Fecha de los precios: octubre de 2026. Todos están marcados como estimación y hay que verificarlos antes de contratar.

---

## 1. Lo que sabemos de las fuentes (medido el 8 oct 2026)

| | Nacho IC | KManuS88 |
|---|---|---|
| Channel ID | `UCZLtNl1TyvNJ9K8OYKT43Cw` | `UC0Ym7ckYtSsgcbZX1VvYMQQ` |
| Suscriptores | 99,1 mil | 1,01 M |
| Videos publicados | ~1.500 | ~3.200 |
| Cadencia actual | 3–4 videos/día | 3–4 videos/semana |
| Duración típica | 16–20 min | 10–25 min |
| Volumen mensual estimado | ~105 videos | ~17 videos |

Hechos que condicionan el diseño:

1. **El RSS público funciona desde la nube y es gratis** (`youtube.com/feeds/videos.xml?channel_id=…`, últimos 15 videos).
2. **Las transcripciones están bloqueadas desde IPs de datacenter.** `yt-dlp` y `youtube-transcript-api` devuelven "Sign in to confirm you're not a bot". Trigger.dev corre en la nube, así que necesita un proveedor de transcripciones o un proxy residencial.
3. **Los títulos se contradicen.** Nacho IC publicó el mismo día "TODOS bajistas", "Estoy alcista, PERO…" y "BITCOIN EN PELIGRO". La postura real hay que sacarla de la transcripción.
4. **Hay contenido patrocinado** (por ejemplo Exness en KManuS88). Hay que detectarlo y marcarlo.

---

## 2. Inventario: toda la data que se puede sacar

| Nivel | Dato | Fuente | Costo | Prioridad |
|---|---|---|---|---|
| Canal | Suscriptores, vistas totales, número de videos (foto diaria) | YouTube Data API `channels.list` (1 unidad) | Gratis | P1 |
| Video | id, título, descripción, tags, fecha, duración, idioma, short/live | Data API `videos.list` (1 unidad por cada 50 ids) | Gratis | P0 |
| Video | **Enlaces de la descripción**: afiliados, códigos de referido, patrocinadores, capítulos | Descripción + regex | Gratis | P0 |
| Video | **Velocidad**: vistas, likes y comentarios a las +1 h, +6 h, +24 h y +7 d | `videos.list` por lotes | Gratis | P1 |
| Video | **Transcripción con marcas de tiempo** | Proveedor (Supadata o ScrapeCreators) o proxy | ~$0,002–0,02 por video | P0 |
| Video | Miniatura: texto y encuadre clickbait | `i.ytimg.com` + visión de Claude en la misma llamada | ~$0,002 por video | P2 |
| Derivado (LLM) | **Afirmaciones**: activo, postura, convicción, horizonte, entrada, objetivo, invalidación, catalizador, narrativas, cita y minuto | Claude con structured outputs | ver §5 | P0 |
| Derivado (LLM) | Índice de clickbait: postura del título frente a la del contenido | Misma llamada | incluido | P1 |
| Derivado (LLM) | Patrocinio y conflicto de interés | Misma llamada + enlaces de la descripción | incluido | P0 |
| Audiencia | Comentarios principales y respuestas: sentimiento, contraargumentos, preguntas | Data API `commentThreads.list` (1 unidad por 100) | Gratis + LLM barato | P2 |
| Mercado | OHLCV en velas de 1 h de cada activo mencionado | Binance/Kraken públicos o CoinGecko Demo (cripto); Stooq (acciones, oro) | Gratis | P0 |
| Multitud | Sentimiento en Reddit, X, HN, Polymarket y YouTube por narrativa | last30days `--emit=json --store` | $0–5/mes | P2 |
| Multitud | Probabilidades de Polymarket en mercados relevantes | Gamma API pública | Gratis | P2 |
| Opcional | Repetición del chat en directos | `yt-dlp` `live_chat` (requiere proxy) | Proxy | P3 |
| Opcional | Posts de comunidad, X y Telegram de los creadores | ScrapeCreators, last30days o Agent-Reach (hay que verificar soporte) | Variable | P3 |
| Opcional | Niveles dibujados en el gráfico del video (fotogramas clave) | Descarga de video + visión | Caro, ver §5 | P3 |

---

## 3. Arquitectura

```
                 ┌─────────────── Detección ───────────────┐
 YouTube WebSub ─┤ push en minutos (callback en Supabase    │
 (gratis)        │ Edge Function → trigger de Trigger.dev)  │
 RSS cada hora ──┤ red de seguridad + conciliación          │
                 └──────────────────┬──────────────────────┘
                                    ▼  idempotencyKey = videoId
 Trigger.dev  process-video ─► metadata (videos.list en lote)
                            ─► transcript (reintentos: 15 min, 1 h, 6 h;
                               wait.for se checkpointa y no cobra cómputo)
                            ─► extract (Claude, structured outputs)
                            ─► price-snapshot (vela 1 h al publicar)
                            ─► upsert en Postgres + aviso si convicción ≥ 4
 Crons (6 de 10 en el plan Free):
   rss-reconcile (cada hora) · websub-renew (diario) · stats-snapshot (cada hora,
   solo videos de menos de 7 días) · evaluate-claims (diario, SQL puro, sin LLM) ·
   crowd-weekly (last30days + Polymarket) · digest (diario)
 Supabase: Postgres (videos, transcripts_meta, claims, prices, outcomes, crowd)
           + Storage (transcripciones .json.gz) + vistas materializadas para el panel
 Frontend: Cabina y Atlas (prototipos en /prototypes) leen JSON estático
           exportado cada noche, o Supabase con clave anónima de solo lectura (RLS)
```

**Por qué así:**
- **WebSub más RSS.** WebSub avisa en minutos sin hacer polling. El RSS cada hora cubre las suscripciones vencidas, que caducan cada pocos días y hay que renovar. YouTube a veces espera la URL de topic con `/xml/feeds/`. Así no hace falta un cron cada pocos minutos, que el plan Free tampoco permite.
- **Una tarea por video con `idempotencyKey`.** Los reintentos no duplican trabajo ni cobran el LLM dos veces.
- **Evaluación en SQL.** Comparar el objetivo y la invalidación con los máximos y mínimos es una consulta. No hay costo de LLM por evaluar.
- **Las esperas no cuestan.** Los subtítulos automáticos pueden tardar horas en aparecer. Con `wait.for`/`wait.until` de más de 5 s Trigger.dev congela la tarea y no cobra cómputo.

---

## 4. Rendimiento

| Técnica | Efecto |
|---|---|
| Push (WebSub) en vez de polling | Latencia de detección de ~1–5 min, sin costo |
| `videos.list` con 50 ids por llamada | La foto de estadísticas de 150 videos cuesta 3 unidades de cuota |
| Transcripción compactada antes del LLM: segmentos unidos en bloques de ~30 s con `[mm:ss]`, sin muletillas ni el descargo repetido de inicio y cierre | **~30–40 % menos tokens de entrada** |
| Prefijo de prompt fijo (instrucciones + esquema + glosario de narrativas) primero y transcripción al final | Caché de prompt: el prefijo se cobra a $0,20/MTok en Opus 5.5 en vez de $4 |
| Structured outputs (`output_config.format` con JSON Schema) | Cero reintentos por JSON inválido |
| Una sola llamada por video: miniatura + título + descripción + transcripción | Sin llamadas redundantes; el índice de clickbait sale gratis |
| `effort: low` para la extracción y subirlo solo si la evaluación muestra margen | Menos tokens de salida y de razonamiento |
| Batch API para el histórico y lo no urgente | **−50 %** en tokens |
| Límite de concurrencia por cola (`concurrencyLimit`) según el rate limit del proveedor | Sin errores 429 ni reintentos en cascada |
| Exportar JSON estático para el frontend | El panel carga desde CDN, sin consultas a la base por visita |
| Vistas materializadas (aciertos por canal, activo y horizonte) refrescadas tras `evaluate-claims` | Consultas del panel en milisegundos |

Objetivos medibles:
- Latencia de la subida del video a la afirmación en el feed: p50 < 30 min, limitada por la llegada de los subtítulos.
- Éxito de transcripción > 97 %.
- 100 % de JSON válido.
- Costo por video < $0,07.

---

## 5. Costos

### 5.1 Supuestos por video

- Unos 18 min de habla en español: ~4.500 tokens de transcripción compactada más ~500 de metadata.
- Prefijo fijo de ~3.000 tokens, cacheado.
- Salida de ~2.000 tokens: el JSON de afirmaciones más el razonamiento con effort `low`.

Son estimaciones. Hay que medirlas con `count_tokens` y con `usage` en los primeros 20 videos.

### 5.2 LLM (precios de la API de Claude, oct 2026)

| Modelo | $/MTok entrada / salida | Por video, en tiempo real | Por video, Batch (−50 %) | Mes (~125 videos) | Histórico completo (~4.700, Batch) | Últimos 12 meses (~1.450, Batch) |
|---|---|---|---|---|---|---|
| **Claude Opus 5.5** (por defecto) | $4 / $20 | ~$0,061 | ~$0,031 | **~$7,6** (o ~$3,9 en Batch) | ~$146 | **~$45** |
| Claude Sonnet 5.5 | $2 / $10 | ~$0,030 | ~$0,015 | ~$3,8 | ~$70 | ~$22 |
| Claude Haiku 5.5 | $0,10 / $0,50 | ~$0,0015 | ~$0,0008 | ~$0,19 | ~$3,5 | ~$1,1 |

**Recomendación.** Empezar con **Claude Opus 5.5 con effort `low`**: lo nuevo en tiempo real y el histórico por Batch. Antes de pasar a un modelo más barato, comparar con un set de evaluación de 30 videos etiquetados a mano (§7). La elección de modelo es tuya: en este volumen la diferencia es de pocos dólares al mes. Lo que más pesa es el histórico.

Las piezas opcionales de LLM son baratas. Los comentarios (100 por video, ~3.000 tokens) suman ~$0,006 por video en Opus con Batch. La miniatura (~1.200 tokens de imagen) suma ~$0,002 por video.

### 5.3 Transcripciones

| Ruta | Costo mensual (~125 videos) | Histórico (~4.700) | Rendimiento y riesgo |
|---|---|---|---|
| **Supadata**: 1 crédito por video con subtítulos; 2 créditos por minuto si los genera con IA | Plan Basic **$5 por 300 créditos** | Plan Mega $47 por 30.000 un mes y luego bajar de plan | Sin mantenimiento; límite de 1 req/s en el plan gratis. **Recomendado** |
| ScrapeCreators | Desde $10 por 5.000 o $47 por 25.000 créditos; los créditos no caducan | Cabe en $47 | Confirmar cuántos créditos cobra el endpoint de transcripción |
| Proxy residencial + `yt-dlp` (solo subtítulos) | ~60 MB/mes → < $1 (a $1–8/GB) | ~2 GB → $2–16 | Hay que mantener `yt-dlp`, cookies y tokens; riesgo de bloqueo |
| Proxy + audio + Whisper (Groq whisper-large-v3-turbo, $0,04/h) | ~1 GB de audio + ~37 h → ~$2–10 | ~1.400 h → ~$56 + proxy | Respaldo para videos sin subtítulos |
| Equipo en casa (IP residencial) que sube a Supabase | $0 | $0 | Depende de que el equipo esté encendido; sirve para el histórico |

### 5.4 Infraestructura y datos

| Pieza | Plan | Costo mensual |
|---|---|---|
| Trigger.dev | Free: $5 de uso, 10 schedules, cron mínimo de 1 h. Uso estimado: ~2.000 runs ($0,05) + ~3 h de cómputo Micro (~$0,20) | **$0** (Hobby $10 si hace falta más) |
| Supabase | Free: 500 MB de base y 1 GB de Storage. Las transcripciones en gzip ocupan ~40 MB en total y las afirmaciones ~50 MB. El cron diario evita que el proyecto se pause | **$0** |
| YouTube Data API | 10.000 unidades/día gratis. Uso estimado < 150/día; el histórico de metadata cuesta ~100 unidades | **$0** |
| Precios de mercado | Binance o Kraken públicos (Binance bloquea IPs de EE. UU.; elegir según la región del worker); CoinGecko Demo (10.000 llamadas/mes) | **$0** |
| last30days | Reddit, HN, Polymarket y GitHub gratis; X necesita clave (xAI o X); TikTok e Instagram van por ScrapeCreators | **$0–5** |
| Agent-Reach | Solo para explorar a mano en tu equipo; en servidor necesita proxy (~$1) | **$0** |

### 5.5 Totales

| Escenario | Mensual | Inicial (una vez) |
|---|---|---|
| **Mínimo**: Supadata Basic, Opus 5.5 por Batch, sin comentarios ni multitud | **~$9** | Histórico de 12 meses: ~$45 de LLM + transcripciones desde casa ($0) |
| **Recomendado**: Supadata Basic, Opus 5.5 en tiempo real, comentarios, miniaturas, last30days semanal | **~$15–25** | 12 meses: ~$50 de LLM + $47 de Supadata Mega |
| **Completo**: más histórico entero, chat en directo y redes cruzadas | ~$30–45 | ~$200 |

---

## 6. Rol de cada herramienta

- **Trigger.dev:** el motor. Tareas por video con reintentos, `idempotencyKey`, colas con límite de concurrencia, esperas checkpointadas y crons. Para Python (`yt-dlp`, last30days) usa la build extension de Python.
- **last30days:** contexto semanal de la multitud por narrativa activa. Correrlo en modo CLI con `--emit=json --store` y quedarse solo con los datos crudos y su puntuación por interacción. La síntesis la hace nuestra propia llamada de extracción, así no se paga dos veces el LLM.
- **Agent-Reach:** solo para investigar a mano desde tu equipo. Sirve para encontrar las cuentas de X y Telegram de los creadores, revisar hilos puntuales y validar narrativas nuevas. No va al pipeline: no guarda datos ni programa ejecuciones, y en servidor choca con el mismo bloqueo de YouTube.
- **Frontend:** los prototipos Cabina y Atlas ya tienen la forma de los datos (afirmaciones, resultados, narrativas, multitud). Hay que sustituir el generador sintético por el JSON exportado. Ojo: los artifacts de claude.ai no pueden hacer fetch a dominios externos, así que la versión con datos reales debe desplegarse en tu propio hosting (Vercel o Cloudflare Pages), o en el artifact con un snapshot JSON incrustado.

---

## 7. Calidad y control de costos

1. **Set de evaluación:** 30 videos (20 de Nacho IC y 10 de KManuS88) etiquetados a mano con sus afirmaciones. Medir precisión y recall de activo, postura, niveles y horizonte.
2. **Comparar configuraciones** con ese set: Opus 5.5 con effort `low` y `medium`, Sonnet 5.5 y Haiku 5.5. Elegir el modelo más barato que mantenga la calidad. La decisión final es tuya.
3. **Registrar `usage` por video** (tokens de entrada, de caché y de salida) en una tabla `llm_costs`. Avisar si el costo por video pasa de $0,10.
4. **Verificar la caché:** `cache_read_input_tokens` debe ser mayor que 0 desde el segundo video del lote. Si es 0, algo del prefijo está cambiando, como una fecha o el orden del esquema.

---

## 8. Fases

| Fase | Contenido | Esfuerzo | Costo |
|---|---|---|---|
| **F0** (días 1–2) | Esquema en Supabase; metadata histórica completa por la Data API; transcripciones de los últimos 90 días (desde casa o Supadata) | Bajo | ~$5 |
| **F1** (semana 1) | Pipeline en tiempo real: WebSub, RSS, transcripción, extracción, precio y aviso; conectar la Cabina a datos reales | Medio | ~$10/mes |
| **F2** (semana 2) | Evaluador de resultados, aciertos y calibración; comentarios y miniaturas; histórico de 12 meses por Batch | Medio | ~$50 una vez |
| **F3** (semanas 3–4) | last30days, Polymarket, datos del Atlas (ciclo de vida, quién lo dijo primero, divergencias) | Medio | +$0–5/mes |
| **F4** (opcional) | Chat en directo, redes cruzadas, visión sobre fotogramas | Alto | Variable |

## 9. Decisiones pendientes (tuyas)

1. **Ruta de transcripción:** Supadata (recomendada), proxy residencial o equipo en casa.
2. **Profundidad del histórico:** 12 meses (~$45–50) o completo (~$150–200).
3. **Modelo:** Opus 5.5 por defecto; Sonnet 5.5 o Haiku 5.5 solo si la evaluación lo respalda.
4. **Hosting del frontend con datos reales:** Vercel o Cloudflare Pages.

## 10. Riesgos

- **Términos de servicio de YouTube.** Usar la API oficial siempre que se pueda. Las transcripciones por terceros son zona gris; mantener el uso personal y no redistribuir el contenido.
- **Cambios en YouTube** que rompan `yt-dlp` o los proveedores. Mitigación: dos proveedores de transcripción con fallback automático.
- **Precios volátiles.** Las cifras de proveedores salen de comparativas, a menudo escritas por competidores. Verificarlas antes de contratar.

### Fuentes de precios y técnicas
- Precios de la API de Claude: referencia oficial de modelos, consultada en oct 2026.
- [Supadata: comparativas de planes](https://transcriptapi.com/blog/transcriptapi-vs-supadata) · [socialcrawl.dev](https://www.socialcrawl.dev/blog/best-youtube-data-apis-2026)
- [ScrapeCreators: transcripción de YouTube](https://scrapecreators.com/tutorials/how-to-scrape-youtube-transcript-with-python) · [precios](https://aisotools.com/pricing/scrape-creators)
- [YouTube Data API: costo de cuota](https://developers.google.com/youtube/v3/determine_quota_cost) · [notificaciones push](https://developers.google.com/youtube/v3/guides/push_notifications?hl=es-419) · [la URL de topic de WebSub](https://kevincox.ca/2021/12/16/youtube-websub/)
- [Groq Whisper Large v3 Turbo](https://groq.com/whisper-large-v3-turbo-now-available-on-groq-combining-speed-quality-for-speech-recognition/)
- [Precios de proxies residenciales 2026](https://dataimpulse.com/blog/residential-proxy-pricing-comparison/) · [databay](https://databay.com/blog/how-much-do-residential-proxies-cost)
- [Trigger.dev: tareas programadas](https://trigger.dev/docs/tasks/scheduled) · [precios (ZenML)](https://www.zenml.io/blog/trigger-dev-pricing)
- [last30days](https://github.com/mvanhorn/last30days-skill) · [Agent-Reach](https://github.com/Panniantong/Agent-Reach)

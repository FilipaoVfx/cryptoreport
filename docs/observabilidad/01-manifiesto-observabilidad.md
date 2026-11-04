# Parte 1 · Manifiesto de observabilidad y estándares de calidad

> Urania/Diario · versión 1.0.0 del contrato · línea base medida el 14 de octubre de 2026 a las 16:05 UTC.
> Las palabras **DEBE**, **NO DEBE**, **DEBERÍA** y **PUEDE** tienen el sentido normativo de RFC 2119.
> Las tablas marcadas como generadas salen de [`contratos/registros/`](contratos/registros) y el CI comprueba que no se desvíen (PV-05).

<a id="alcance"></a>
## 1.1 Alcance: qué se observa

Urania/Diario es la app móvil de lectura de señales: los prototipos `prototypes/movil/b4-urania` a `b7-rollo` y la línea minimalista `m1`–`m3`, con la pantalla «Diario». La app solo lee datos estáticos (`data/index.json` y `data/v/<id>.json`). Lo que hay que observar es la cadena que los produce:

| Ejecutor (`service.name`) | Código | Disparo | Produce | Telemetría hoy |
|---|---|---|---|---|
| `cr-extractor` | `services/transcripts/crtranscripts` | `cryptoreport-transcripts.timer`, cada 15 min | Transcripciones, `state.sqlite`, `last-run.json`, `data.json` del sitio | Una línea JSON por ciclo, líneas `OK`/`FINAL`, tabla `runs` |
| `cr-build-data` | `prototypes/movil/build_data.py` | `ExecStartPost` del extractor y `publish()` del puente | Datos de Urania (`data/`) | Líneas «tema …» en el journal |
| `cr-bridge` | `services/bridge/crbridge` | Timer a :03, :18, :33 y :48 y tras cada extracción | Cola de trabajos, importaciones, `status.json`, `pipeline-status.json` | JSON de salud en el journal |
| `cr-analysis` | `services/analysis/cranalysis` | CLI manual; la guarda G-01 lo mantiene cerrado | Análisis por API | `meta` de cada archivo |
| `cr-scheduled-agent` | ChatGPT Scheduled (externo) | 0, 6, 12 y 18 h (Bogotá), 2 trabajos | Resultados y comprobantes en Drive | Comprobantes |
| `cr-panel` | Nuevo (parte 2) | Servicio permanente | API, UI, intervenciones | — |

Fuera de la cadena quedan el sitio estático y Urania, que solo se observan por la frescura de sus datos (SH-11) y por el feedback que generan (parte 4).

<a id="principios"></a>
## 1.2 Principios

Cada principio dice qué se exige, qué falla hoy y qué protocolo lo comprueba.

**P1 · Toda ejecución tiene identidad.** Cada ciclo, invocación o ejecución reconstruida **DEBE** tener un `run_id`. Es un UUIDv7 si lo genera un servicio propio y un UUIDv5 determinista si se reconstruye desde un comprobante. Su `trace_id` **DEBE** ser el `run_id` sin guiones. Hoy `runs.id` es un autoincremento que nunca se expone, y el puente no tiene ID de ciclo (H-04). Lo comprueban PV-02 y PV-08.

**P2 · Todo artefacto tiene huella.** Transcripciones, análisis, prompts, esquemas, instrucciones y comprobantes se identifican por el SHA-256 de sus bytes. El esquema de análisis usa su hash canónico, `sha256(json.dumps(schema, sort_keys=True))`, que es `7b88e0b7…` y no el del archivo. Ya existe en parte (`transcript_sha256`, `prompt_sha256` y `job_id`); falta en los comprobantes y en el código desplegado (H-01). Lo comprueba PV-07.

**P3 · Un solo vocabulario.** Ningún servicio **DEBE** emitir un nombre de span, atributo, evento o métrica que no esté en [`registros/semconv.json`](contratos/registros/semconv.json). Los nombres `gen_ai.*` se fijan a una instantánea concreta de las convenciones de OpenTelemetry, que están en estado *Development* (§1.5.7). Lo comprueba PV-04.

**P4 · Se trazan decisiones, no pensamientos.** Se registran todos los puntos de decisión con su evidencia: llamadas al modelo, llamadas a herramientas o proveedores, veredictos de puertas y validadores, fallbacks, reintentos, guardas y transiciones. El razonamiento interno del modelo **NO DEBE** pedirse ni guardarse: solo se cuenta (`gen_ai.usage.reasoning.output_tokens`). Prompts y salidas solo se capturan con opt-in explícito (§1.5.4 y §1.5.6). Lo comprueban PV-08 y G-15.

**P5 · Al agente externo se le verifica, no se le cree.** El agente Scheduled entrega `model: null`, así que todo lo suyo lleva `cr.model.verified = false`. Sus resultados se revalidan en el servidor y sus límites se vigilan (AP-04). Lo que no consta en un comprobante no se inventa: no se fabrican duraciones intermedias. Lo comprueba PV-07.

**P6 · El coste se ve antes de gastarse.** Antes de cada llamada de pago se reserva el crédito (G-04). Los presupuestos tienen un techo que fija el host (G-16). Cada inferencia lleva `cr.cost.usd` y el libro mensual alimenta CO-01 a CO-05.

**P7 · El pago y la publicación fallan cerrados; la telemetría falla abierta.** Ante una duda sobre pago o publicación, se bloquea. Un fallo del Collector **NO DEBE** hacer fallar un ciclo: el exportador tiene un timeout de 2 s, una cola acotada y descarta si hace falta. El libro de ejecuciones (SQLite) guarda siempre la verdad mínima.

**P8 · Toda señal es accionable.** Cada umbral en modo *alert* **DEBE** tener un runbook (§1.9) y, si existe, una intervención (parte 4). Un umbral sin acción posible se queda en *monitor*. Lo comprueba la sección de trazabilidad del validador.

**P9 · Nada sensible sale del sistema.** El repositorio es público. No salen claves, IDs de carpetas de Drive, correos ni cuerpos de respuesta de proveedores. Las IP se guardan con hash y sal. Lo comprueba PV-15.

**P10 · La observabilidad cabe en el servidor.** Toda la pila (Collector, backends y panel) usa como máximo 1 GiB de RAM y 0,25 vCPU de media, y 5 GiB de disco (RS-01 a RS-03), en un VPS de 2 vCPU que comparte con otros proyectos. Lo comprueba PV-09.

**P11 · Toda decisión de análisis es reproducible.** Para repetirla bastan estos datos: `transcript_sha256`, `prompt_sha256`, `schema_sha256` canónico, modelo, `effort`, `max_tokens` y versión de código (`service.version` + `cr.code.digest`). Producción ejecuta hoy código sin commit (H-01), así que el hash del código es obligatorio.

<a id="linea-base"></a>
## 1.3 Línea base medida (14 de octubre de 2026)

Datos leídos en solo lectura de `/var/lib/cryptoreport-transcripts` y del estado de systemd. Son la referencia contra la que se fijan los umbrales.

| Ámbito | Medida |
|---|---|
| Videos | 35, todos `ok`: nacho 23, kmanu 7, cava 3, criptoniano 1 y healthy 1. 20 shorts (el más largo, 87 s) y 15 largos (hasta 4104 s). |
| Ciclos del extractor | 552 del 9 al 14 de octubre, todos terminados. p95 de 244 s y máximo de 322 s; 343 ciclos duran menos de 1 s porque no tienen trabajo. |
| Proveedores | Scraper.Tech captions: 37 `ok` (media 10,1 s, máximo 21,1 s) y 6 `error` (media 28,4 s, máximo 65,3 s). yt-dlp: 9 de 9 `blocked`. Supadata: 4 `ok` (4,3 s). |
| Publicación → transcripción | p50 de 31 min. El p90, de 48 h, está sesgado por la carga inicial. |
| Calidad de transcripción | Cobertura mínima 0,911 y media 0,993. Mayor hueco: 46 s. Entre 142 y 227 palabras/min (p50 187). Marcadores no verbales: máximo 2,9 %. |
| Cuotas de octubre | Scraper.Tech: 87 de 1000 peticiones. Supadata: 4 de 20 créditos. |
| Análisis | 32 válidos: 30 de Scheduled y 2 de OpenAI. 27 `parcial` y 5 `completo`. 592 afirmaciones y 452 evidencias. |
| Coste de modelos | Solo se conoce el de los 2 de OpenAI: 0,2816 y 0,358 USD. Los 30 de Scheduled llegan con `model` y `cost_usd_estimate` nulos. |
| Tokens (2 análisis OpenAI) | Entrada: 20 285 y 20 022, con un 36 % leído de caché. Salida: 24 866 y 32 571, que incluyen 6214 y 8804 de razonamiento (39 % y 51 % de `CRA_MAX_TOKENS`). |
| Agente Scheduled | 9 comprobantes entre el 13-oct a las 18:48 y el 14-oct a las 05:18 UTC: 5 `resultados_subidos` y 4 `error`. 30 trabajos únicos intentados y 29 importados (26 automáticos). Duración: mediana de 6,8 min y máximo de 46,6 min. Una ejecución intentó 22 trabajos. |
| Puente | 32 `imported`, 2 `uploaded` y 1 `blocked`. La unidad está en `failed` por `drive_quota` y el estado es `degraded`, con 3 avisos y 1 error. |
| Datos | 7,0 MB en el directorio de datos y 1,7 MB en `/var/www/cryptoreport`. |
| Telemetría | Sin logging estructurado, métricas ni trazas. Sin `run_id` y sin historial de transiciones. |
| Host | 2 vCPU, 7,7 GiB de RAM (4,1 disponibles) y 47 GB libres. Docker 29.8.1 y Python 3.14.4. |

Desde las 17:53 UTC del mismo día se vigilan 7 canales: se añadieron David Battaglia (`battaglia`) y Plan BTC (`planbtc`), que suman unos 0,9 videos al día. El caudal de los siete ronda los 5,4 videos al día, por debajo de los 8 trabajos diarios que admite Scheduled (2 por ejecución, 4 ejecuciones).

<a id="hallazgos"></a>
## 1.4 Hallazgos que motivan el diseño

| ID | Hallazgo | Evidencia | Se resuelve en |
|---|---|---|---|
| H-01 | Producción ejecuta código sin commit: el puente, las guardas, el CI y varias pruebas solo están confirmados en la rama `feat/autonomous-drive-pipeline`. | `git status` de `/root/cryptoreport`; las unidades usan ese árbol | Fase 0 (D-01): `service.version` + `cr.code.digest` |
| H-02 | El puente lleva desde la madrugada del 14-oct en `failed` por `drive_quota` (cliente OAuth compartido). | `systemctl show`, `pipeline-status.json` | RB-05, SH-05 y SH-06 |
| H-03 | Una ejecución de Scheduled intentó y subió 22 trabajos (el límite es 2) y nadie lo detectó: el puente ignora `run_id`, `errors` y `remaining_count`. | Comprobante `aabe58f1…` del 2026-10-14T04:30:15Z | AP-04, G-14, `run-record.external` |
| H-04 | No hay ID de ejecución en el extractor ni historial de transiciones en el puente. | `store.py` (tabla `runs`), tabla `jobs` sin historial | Fase 0 (C-01 y C-02) |
| H-05 | `cranalysis run` no escribe `meta.transcript_sha256`, pero `site.py` lo exige: un análisis nuevo por API quedaría fuera del sitio sin aviso. | `cranalysis/__main__.py` frente a `quality.analysis_matches` | Fase 0 |
| H-06 | `openai` es el proveedor por defecto pero no figura en `services/analysis/requirements.txt`. | `requirements.txt` | Fase 0 |
| H-07 | Los umbrales de tono están duplicados en `tono.py` y `shared/core.js` y no se exportan en `index.json`. | `tono.py` y `core.js` | DQ-M-02 y PV-16 (ya activo en CI) |
| H-08 | `pipeline-status.json` se publica pero nadie lo lee; el «Gasto del mes $0» del sitio está escrito a mano. | `site/index.html`, `crbridge/__main__.py` | Panel W1 (Fase 2) |
| H-09 | Un JSON de análisis malformado aborta todo `build_data.py` (`json.loads` sin `try`). | `build_data.py`, `load_analyses` | Fase 0 |
| H-10 | El túnel de prototipos es público y sin autenticación: expone `data/` con transcripciones, análisis y `pipeline-status.json`. | `serve.py` del árbol de trabajo | Fuera de alcance; se recomienda reponer el token |
| H-11 | La caché de Drive del puente (`bridge/cache`) nunca se limpia. | `core.py`, `read()` | Fase 4 (retención) |
| H-12 | Hay claves de proveedores pegadas en conversaciones. | Memoria del proyecto | Fuera de alcance: rotación por el propietario |
| H-13 | Documentación desfasada: el README habla de 72 h y el perfil vivo usa 48 h; la unidad nombra 2 canales y hay 5. | README y `.service` | Fase 0 |
| H-14 | `remaining_count` llega vacío en 7 de 9 comprobantes y los errores son texto libre. | Comprobantes en `bridge/cache` | Instrucciones 1.4 (Fase 3) |

<a id="modelo-telemetria"></a>
## 1.5 Modelo de telemetría

<a id="identidad-correlacion"></a>
### 1.5.1 Identidad y correlación

- **Ejecución.** Cada proceso crea su `run_id` (UUIDv7) al arrancar: `uuid.uuid7()` en Python 3.14 y una implementación de 10 líneas para 3.12, que sigue en la matriz del CI. Un `IdGenerator` propio del SDK usa `run_id` sin guiones como `trace_id`, de modo que el panel abre la traza de cualquier ejecución sin búsquedas. Los 62 bits finales del UUIDv7 son aleatorios: cumplen el requisito de aleatoriedad de W3C Trace Context para los 7 bytes de la derecha.
- **Extractor → puente.** Justo antes de que `ExecStartPost` arranque el puente, el extractor escribe `<CR_DATA_DIR>/trigger-bridge.json` con `{run_id, trace_id, at}`. Al arrancar, el puente lo consume y lo borra. Así marca `cr.run.trigger = post_extract`, guarda `parent_run_id` y añade un *span link* al ciclo del extractor. Si el archivo no existe, el disparo fue el timer.
- **Frontera asíncrona con el agente (Drive).** No se confía en que el agente propague contexto. Se correlaciona por claves deterministas: `job_id` (`<video_id>__sha256(meta)`), `run_id` del comprobante y `transcript_sha256`. Cada comprobante nuevo genera una traza reconstruida con un `run_id` UUIDv5:

  `run_id = uuid5(444092fd-59cd-5aba-8440-79b657dbb397, "<run_id del comprobante>|<started_at>")`

  El espacio de nombres es `uuid5(NAMESPACE_URL, "https://github.com/FilipaoVfx/cryptoreport/docs/observabilidad#scheduled-run")`. Releer el mismo comprobante en cada ciclo produce el mismo ID, sin duplicados. Si las instrucciones 1.4 añaden un `traceparent` al comprobante, se usa solo como pista.
- **Recurso.** Lo describe [`resource_attributes`](contratos/registros/semconv.json): `service.name`, `service.version` (`git describe --always --dirty`), `deployment.environment.name`, `cr.code.digest`, `cr.contract.version`, `cr.telemetry.origin` y, si la telemetría es reconstruida, `cr.reconstructed_by`.

<a id="arbol-spans"></a>
### 1.5.2 Árbol de spans por flujo

```text
EXTRACTOR (traza = run_id del ciclo)
cr.extractor.cycle                                   trigger timer | manual | backfill
├─ cr.extractor.discover            ×7 canales      source rss | channel_pages
│  └─ cr.provider.call youtube_rss | youtube_pages
├─ cr.extractor.video               ×N (Store.due)  status ok | pending | error | failed …
│  ├─ cr.provider.call scrapertech  captions        outcome ok | pending | error …
│  ├─ cr.provider.call scrapertech  metadata        (video.php)
│  ├─ cr.quality.assess                             verdict valid | warning | invalid
│  ├─ cr.provider.call ytdlp        captions        blocked
│  └─ cr.provider.call supadata     captions        ◂ evento cr.budget.reserved antes de llamar
├─ cr.extractor.repair_durations
├─ cr.extractor.recover
└─ cr.publish site                                  ◂ evento cr.publish.failed si falla

PUENTE (traza propia, link → cr.extractor.cycle si trigger = post_extract)
cr.bridge.cycle
├─ cr.bridge.step list            └─ cr.drive.call list   (pendientes)
├─ cr.bridge.step discover        ◂ eventos cr.job.state_changed
├─ cr.bridge.step check_control   └─ cr.drive.call list | read (control)
├─ cr.bridge.step results         └─ cr.result.validate ×M  ◂ gen_ai.evaluation.result por familia
├─ cr.bridge.step receipts        → crea las trazas reconstruidas del agente
├─ cr.bridge.step upload          └─ cr.drive.call write ×K
├─ cr.bridge.step index
├─ cr.bridge.step publish         ├─ cr.publish site
│                                 └─ cr.publish mobile_data
└─ cr.bridge.step health          └─ cr.publish pipeline_status

AGENTE SCHEDULED (traza reconstruida, service.name = cr-scheduled-agent)
invoke_agent cryptoreport-narrativas      inicio y fin del comprobante · cr.model.verified = false
  ◂ eventos cr.agent.job_attempted ×n
  ⇢ links a cr.drive.call write de cada trabajo subido

ANÁLISIS POR API (solo con G-01 abierta)
cr.analysis.run                           ◂ cr.guardrail.decision block si la guarda está cerrada
└─ invoke_workflow narrative_analysis     ×video
   ├─ chat gpt-6.1-sol                     tokens, effort, finish_reasons, coste
   └─ cr.analysis.validate                 ◂ gen_ai.evaluation.result por familia

PANEL
GET|POST /api/v1/… (SERVER, convenciones HTTP)
└─ cr.panel.intervention <tipo> | cr.panel.config.apply
```

<a id="catalogo-spans"></a>
### 1.5.3 Catálogo de spans y atributos

Tabla generada desde `registros/semconv.json`:

<!-- generado:inicio semconv-spans -->
| Span | Kind | Servicios | Origen | Atributos obligatorios | Cuándo es ERROR |
|---|---|---|---|---|---|
| `cr.extractor.cycle` | `INTERNAL` | cr-extractor | cr | `cr.run.id`, `cr.run.trigger`, `cr.run.outcome` | ERROR si el proceso termina con código distinto de 0 (excepción inesperada). |
| `cr.extractor.discover` | `INTERNAL` | cr-extractor | cr | `cr.channel.slug`, `cr.discovery.source` | ERROR si fallan el RSS y el respaldo de páginas. |
| `cr.extractor.video` | `INTERNAL` | cr-extractor | cr | `cr.video.id`, `cr.channel.slug`, `cr.video.attempt`, `cr.video.status` | ERROR solo si el estado final es failed; pending y no_captions son estados esperados. |
| `cr.provider.call {cr.provider.name}` | `CLIENT` | cr-extractor, cr-bridge | cr | `cr.provider.name`, `cr.provider.operation`, `cr.provider.outcome` | ERROR con error.type para error, auth y quota; pending, unavailable y blocked no son errores del span. |
| `cr.quality.assess` | `INTERNAL` | cr-extractor, cr-bridge, cr-build-data | cr | `cr.quality.verdict` | Nunca ERROR: un veredicto invalid es un resultado, no un fallo. |
| `cr.extractor.repair_durations` | `INTERNAL` | cr-extractor | cr | `cr.repair.candidates`, `cr.repair.fixed` | — |
| `cr.extractor.recover` | `INTERNAL` | cr-extractor | cr | `cr.recover.requests`, `cr.recover.repaired` | — |
| `cr.publish {cr.publish.target}` | `INTERNAL` | cr-extractor, cr-bridge, cr-build-data | cr | `cr.publish.target`, `cr.publish.outcome` | ERROR si outcome = failed. |
| `cr.bridge.cycle` | `INTERNAL` | cr-bridge | cr | `cr.run.id`, `cr.run.trigger`, `cr.run.outcome` | ERROR si errors no está vacío (el proceso sale con 1). |
| `cr.bridge.step {cr.bridge.step}` | `INTERNAL` | cr-bridge | cr | `cr.bridge.step` | ERROR si el paso aborta el ciclo. |
| `cr.drive.call {cr.drive.operation}` | `CLIENT` | cr-bridge | cr | `cr.drive.operation`, `cr.drive.folder`, `cr.drive.outcome` | ERROR con error.type ∈ {drive_quota, drive_auth, drive_transport}. |
| `cr.result.validate` | `INTERNAL` | cr-bridge | cr | `cr.job.id`, `cr.analysis.provider`, `cr.result.decision` | — |
| `invoke_agent {gen_ai.agent.name}` | `CLIENT` | cr-scheduled-agent | otel-genai (`gen_ai.invoke_agent.client`) | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.agent.name`, `cr.agent.run_id`, `cr.agent.receipt.status`, `cr.model.verified` | ERROR si cr.agent.receipt.status = error. |
| `cr.analysis.run` | `INTERNAL` | cr-analysis | cr | `cr.run.id`, `cr.run.trigger`, `cr.run.outcome` | — |
| `invoke_workflow {gen_ai.workflow.name}` | `INTERNAL` | cr-analysis | otel-genai (`gen_ai.invoke_workflow.internal`) | `gen_ai.operation.name`, `gen_ai.workflow.name`, `cr.video.id`, `cr.transcript.sha256` | — |
| `chat {gen_ai.request.model}` | `CLIENT` | cr-analysis | otel-genai (`gen_ai.client.inference`) | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model` | ERROR si la respuesta es incompleta, rechazada o JSON ilegible (AnalysisError), con error.type = clase del error. |
| `cr.analysis.validate` | `INTERNAL` | cr-analysis | cr | `cr.validator.outcome` | — |
| `cr.build_data` | `INTERNAL` | cr-build-data | cr | `cr.run.id`, `cr.run.trigger`, `cr.run.outcome` | — |
| `cr.panel.intervention {cr.intervention.type}` | `INTERNAL` | cr-panel | cr | `cr.intervention.id`, `cr.intervention.type`, `cr.actor.id` | — |
| `cr.panel.config.apply` | `INTERNAL` | cr-panel | cr | `cr.config.version`, `cr.config.change_id`, `cr.actor.id` | — |
| `{http.request.method} {http.route}` | `SERVER` | cr-panel | otel-http | `http.request.method`, `http.route`, `http.response.status_code` | ERROR solo para 5xx; los 4xx son errores del cliente. |
<!-- generado:fin semconv-spans -->

<details>
<summary>Atributos propios <code>cr.*</code> (generado)</summary>

<!-- generado:inicio semconv-atributos -->
| Atributo | Tipo | Cardinalidad | Valores | Descripción |
|---|---|---|---|---|
| `cr.telemetry.origin` | string | low | `native`, `reconstructed` | Procedencia de la telemetría (atributo de recurso). |
| `cr.reconstructed_by` | string | low | — | Servicio que reconstruyó la telemetría de un agente externo. |
| `cr.code.digest` | string | low | — | SHA-256 del código fuente del servicio (atributo de recurso). |
| `cr.contract.version` | string | low | — | Versión del registro de nombres implementada (atributo de recurso). |
| `cr.run.id` | string | high | — | UUIDv7 de la ejecución; lo llevan todos los spans y logs del ciclo. |
| `cr.run.trigger` | string | low | `timer`, `post_extract`, `manual`, `panel`, `backfill`, `retry`, `external_schedule` | Qué disparó la ejecución (timer de systemd, ExecStartPost, CLI, panel, backfill, reintento o calendario del agente externo). |
| `cr.run.outcome` | string | low | `ok`, `degraded`, `failed`, `busy`, `skipped` | Resultado de la ejecución; busy = cerrojo run.lock ocupado, skipped = bloqueado por una guarda. |
| `cr.cycle.videos_due` | int | medium | — | Videos elegibles en el ciclo (Store.due). |
| `cr.cycle.transcribed` | int | medium | — | Transcripciones nuevas guardadas en el ciclo. |
| `cr.cycle.pending` | int | medium | — | Videos que quedan pendientes al cerrar el ciclo. |
| `cr.cycle.errors` | int | medium | — | Errores registrados en el resumen del ciclo. |
| `cr.channel.slug` | string | low | — | Canal (channels.json); 7 valores desde el 14-oct-2026, con battaglia y planbtc. |
| `cr.video.id` | string | high | — | video_id de YouTube. |
| `cr.video.is_short` | boolean | low | — | El video es un short. |
| `cr.video.attempt` | int | medium | — | Número de intento sobre el video (videos.attempts + 1). |
| `cr.video.status` | string | low | `queued`, `pending`, `error`, `ok`, `failed`, `no_captions`, `unavailable`, `skipped` | Estado del video al terminar el intento (tabla videos de state.sqlite). |
| `cr.backfill` | boolean | low | — | El video se descubrió fuera del flujo normal (carga inicial o backfill); se excluye del SLO de latencia. |
| `cr.discovery.source` | string | low | `rss`, `channel_pages` | Fuente del descubrimiento: RSS o respaldo de páginas /videos, /streams y /shorts. |
| `cr.discovery.entries` | int | medium | — | Entradas leídas en la fuente de descubrimiento. |
| `cr.discovery.new_videos` | int | medium | — | Videos nuevos encolados. |
| `cr.provider.name` | string | low | `scrapertech`, `ytdlp`, `supadata`, `youtube_rss`, `youtube_pages`, `rclone_drive`, `telegram`, `openai`, `anthropic` | Proveedor o herramienta externa invocada (registro de herramientas). |
| `cr.provider.operation` | string | low | `captions`, `metadata`, `generate`, `poll`, `account`, `feed`, `channel_pages`, `shorts_probe`, `notify` | Operación del proveedor. |
| `cr.provider.outcome` | string | low | `ok`, `pending`, `unavailable`, `blocked`, `error`, `auth`, `quota`, `running`, `skipped` | Resultado normalizado (crtranscripts/providers.py) más skipped cuando el proveedor está en cooldown. |
| `cr.provider.paid` | boolean | low | — | La llamada consume créditos o dinero. |
| `cr.provider.billed_units` | int | medium | — | Unidades facturables consumidas (peticiones de Scraper.Tech, créditos de Supadata). |
| `cr.provider.health` | string | low | `up`, `cooldown`, `down` | Salud del proveedor según kv health:&lt;proveedor&gt;. |
| `cr.provider.cooldown_until` | string | high | — | Fin del cooldown (RFC 3339). |
| `cr.quality.verdict` | string | low | `valid`, `warning`, `invalid` | Veredicto de la puerta de calidad. |
| `cr.quality.reason` | string | low | `sin_segmentos`, `idioma_no_original`, `segmentos_invalidos`, `duracion_invalida`, `tiempos_fuera_del_video`, `posible_corte_final`, `posible_corte_inicial`, `conteo_segmentos_incorrecto`, `segmentos_duplicados_exactos`, `estructura_invalida`, `duracion_desconocida_completitud_no_medible`, `hueco_largo_revisar_audio` | Un motivo o aviso de crtranscripts.quality.assess (uno por punto de métrica). |
| `cr.quality.reasons` | string[] | medium | — | Lista de motivos de rechazo de assess. |
| `cr.quality.warnings` | string[] | medium | — | Lista de avisos de assess. |
| `cr.transcript.sha256` | string | high | — | SHA-256 de los bytes de la transcripción guardada. |
| `cr.transcript.coverage` | double | medium | — | Fin del último segmento / duración del video. |
| `cr.transcript.segments` | int | medium | — | Número de segmentos. |
| `cr.transcript.language` | string | low | — | Idioma de la pista (es). |
| `cr.transcript.track_kind` | string | low | `unknown`, `asr`, `ai` | Tipo de pista según store.write_transcript. |
| `cr.repair.candidates` | int | medium | — | Videos sin duración elegibles para reparar. |
| `cr.repair.fixed` | int | medium | — | Duraciones reparadas. |
| `cr.recover.requests` | int | medium | — | Solicitudes de recuperación leídas de recovery-requests.json. |
| `cr.recover.repaired` | int | medium | — | Transcripciones reemplazadas por una versión válida. |
| `cr.publish.target` | string | low | `site`, `mobile_data`, `pipeline_status` | Destino de publicación: data.json del sitio, data/ de los prototipos o pipeline-status.json. |
| `cr.publish.outcome` | string | low | `ok`, `failed`, `skipped` | Resultado de la publicación. |
| `cr.publish.items` | int | medium | — | Elementos publicados (videos o análisis). |
| `cr.bridge.step` | string | low | `list`, `discover`, `check_control`, `results`, `receipts`, `upload`, `index`, `publish`, `health`, `recovery_requests`, `backup` | Paso de Bridge.cycle(). |
| `cr.drive.operation` | string | low | `list`, `read`, `write` | Operación de RcloneDrive. |
| `cr.drive.folder` | string | low | `control`, `pendientes`, `resultados`, `ejecuciones` | Carpeta lógica de Drive (nunca el ID real). |
| `cr.drive.outcome` | string | low | `ok`, `error` | Resultado de la operación de Drive; la clase de error va en error.type. |
| `cr.job.id` | string | high | — | job_id determinista del puente. |
| `cr.job.state` | string | low | `queued`, `needs_transcript`, `upload_uncertain`, `uploaded`, `imported`, `rejected`, `conflict`, `blocked`, `superseded` | Estado del trabajo (los 9 que usa crbridge/core.py). |
| `cr.job.previous_state` | string | low | `queued`, `needs_transcript`, `upload_uncertain`, `uploaded`, `imported`, `rejected`, `conflict`, `blocked`, `superseded` | Estado anterior en una transición; se omite si el trabajo es nuevo. |
| `cr.reason` | string | high | — | Motivo en texto corto (≤ 200 caracteres), sin datos sensibles. |
| `cr.analysis.provider` | string | low | `chatgpt-scheduled`, `openai`, `anthropic` | Origen del análisis (meta.provider). |
| `cr.analysis.completeness` | string | low | `completo`, `parcial`, `insuficiente` | analysis.estado del contrato del prompt v1.0.0. |
| `cr.analysis.claims` | int | medium | — | Número de afirmaciones. |
| `cr.analysis.evidences` | int | medium | — | Número de evidencias. |
| `cr.prompt.sha256` | string | low | — | SHA-256 del system prompt usado. |
| `cr.schema.sha256` | string | low | — | SHA-256 del esquema de salida usado. |
| `cr.validator.check` | string | low | `schema`, `identity`, `unique_ids`, `references`, `quotes`, `sources`, `probabilities`, `history`, `metadata`, `ranges`, `transcript_hash` | Familia de comprobaciones del validador (cranalysis/validate.py y crbridge.result_errors). |
| `cr.validator.outcome` | string | low | `pass`, `fail` | Resultado de una familia de comprobaciones. |
| `cr.result.decision` | string | low | `accepted`, `rejected`, `conflict`, `duplicate` | Decisión del puente sobre un resultado del agente. |
| `cr.cost.usd` | double | medium | — | Coste en USD de la operación. |
| `cr.cost.estimated` | boolean | low | — | El coste sale de la tabla PRICES y no de una factura. |
| `cr.budget.name` | string | low | `supadata_credits`, `scrapertech_requests`, `model_api_usd` | Presupuesto afectado. |
| `cr.agent.run_id` | string | high | — | run_id declarado por el agente externo en su comprobante. |
| `cr.agent.receipt.status` | string | low | `resultados_subidos`, `sin_pendientes`, `error` | Estado del comprobante de Scheduled. |
| `cr.agent.jobs.attempted` | int | medium | — | Trabajos intentados según el comprobante. |
| `cr.agent.jobs.uploaded` | int | medium | — | Trabajos subidos según el comprobante. |
| `cr.agent.remaining_count` | int | medium | — | Pendientes declarados por el agente; hoy suele llegar vacío. |
| `cr.agent.job_uploaded` | boolean | low | — | El trabajo intentado figura entre los subidos. |
| `cr.agent.job_outcome` | string | low | `attempted`, `uploaded`, `imported`, `rejected`, `blocked` | Etapa alcanzada por un trabajo del agente. |
| `cr.model.verified` | boolean | low | — | false cuando el modelo es declarado y no verificable (Scheduled entrega model: null). |
| `cr.instructions.revision` | string | low | — | Revisión de scheduled-instructions.md vigente (hoy 1.3). |
| `cr.guardrail.id` | string | low | — | ID de la guarda (registros/guardrails.json). |
| `cr.guardrail.decision` | string | low | `allow`, `block`, `clamp` | Decisión de la guarda: permitir, bloquear o recortar al sobre. |
| `cr.config.version` | int | low | — | Versión de configuración activa que leyó la ejecución. |
| `cr.config.change_id` | string | high | — | Solicitud de cambio aplicada. |
| `cr.intervention.id` | string | high | — | ID de la intervención manual. |
| `cr.intervention.type` | string | low | — | Tipo de intervención (registros/intervenciones.json). |
| `cr.intervention.outcome` | string | low | `succeeded`, `failed`, `rejected`, `cancelled`, `reverted` | Resultado final de la intervención. |
| `cr.actor.id` | string | medium | — | Cuenta del panel que actuó (seudónimo). |
| `cr.feedback.rating` | string | low | `up`, `down` | Valoración 👍/👎. |
| `cr.feedback.target_kind` | string | low | `analysis`, `claim`, `evidence`, `segment`, `tone_label`, `topic_mention`, `transcript` | Tipo de objeto valorado. |
| `cr.eval.kind` | string | low | `validator`, `autorater`, `trajectory`, `human` | Clase de evaluación. |
| `cr.trajectory.step` | string | low | — | Paso de la trayectoria de referencia (catálogo cerrado por agente). |
<!-- generado:fin semconv-atributos -->

</details>

Una regla de cardinalidad separa los atributos de las métricas. Los de cardinalidad `high` (`cr.video.id`, `cr.job.id`, `cr.run.id`…) solo van en spans y logs; en métricas solo entran atributos `low` (PV-04). Así las series de VictoriaMetrics no crecen con cada video.

<a id="pasos-razonamiento"></a>
### 1.5.4 Pasos de razonamiento: qué se traza y qué no

| Paso | Cómo se observa | Contenido |
|---|---|---|
| Llamada al modelo | Span `chat {modelo}`: tokens (incluidos los de razonamiento), `gen_ai.request.reasoning.level`, `finish_reasons`, `response.id` y coste | Prompt y salida solo con opt-in |
| Razonamiento interno | Solo el recuento `gen_ai.usage.reasoning.output_tokens`; la cadena de pensamiento no se pide ni se guarda | — |
| Veredicto del validador | Un `gen_ai.evaluation.result` por familia (`cr.validator.*`): pasa o falla, con explicación | Las citas se nombran por ID, no por texto |
| Fallback de proveedor | Secuencia de spans `cr.provider.call` con `cr.provider.outcome`; evento `cr.provider.health_changed` | — |
| Reintento y backoff | `cr.video.attempt`, `next_attempt_at` en el log del ciclo | — |
| Guarda | Evento `cr.guardrail.decision` (`allow`, `block` o `clamp`) con `cr.guardrail.id` | — |
| Transición de trabajo | Evento `cr.job.state_changed` y fila en el historial (C-02) | — |
| Paso del agente externo | Evento `cr.agent.job_attempted`; con las instrucciones 1.4, pasos con hora en el comprobante (§1.7.2) | — |

Del agente externo solo se observa lo que declara y lo que produce. Su trayectoria se evalúa con los pasos que declara en el comprobante y se contrasta con sus resultados, que se revalidan en el servidor.

<a id="logs"></a>
### 1.5.5 Logs estructurados

Cada servicio escribe una línea JSON por evento en stdout y journald la recoge. El contrato está en [`log-record.schema.json`](contratos/esquemas/log-record.schema.json). Toda línea lleva `run_id` y, si hay un span activo, `trace_id` y `span_id`. Las líneas `ERROR` y `FATAL` llevan `error_type`. El Collector las lee del journal (receptor `journald`) y las envía a VictoriaLogs.

| Salida actual | Evento que la sustituye |
|---|---|
| Línea JSON del resumen de `cmd_run` y líneas `OK …`/`FINAL …` | `cr.run.finished` |
| Líneas `[sitio] …` | `cr.publish.failed` |
| Líneas `[aviso] …` | `cr.notify.sent` o `cr.notify.failed` |
| Traceback impreso | Severidad `FATAL` con `exception` y evento `exception` en el span raíz |
| `RcloneDrive` (stderr descartado) | `cr.drive.error` con `error.type` |

<a id="captura-contenido"></a>
### 1.5.6 Captura de contenido y redacción

- Por defecto la captura está apagada. `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` solo se permite en `cr-analysis`, en sesiones de depuración con fecha de caducidad registrada en la auditoría.
- El Collector borra los atributos opt-in (`gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `gen_ai.tool.call.arguments` y `gen_ai.tool.call.result`) de cualquier span que no venga de un servicio autorizado. El esquema de span los rechaza si `content_capture` no es `true`, con o sin el Collector.
- Las reglas de redacción del registro son obligatorias: sin claves ni cabeceras de autenticación, sin rutas de `.env`, sin IDs de Drive, errores por clase y personas por ID de cuenta.

<a id="instantanea-semconv"></a>
### 1.5.7 Convenciones fijadas y registro aislado

Las convenciones GenAI de OpenTelemetry están en estado *Development* y se trasladaron a un repositorio propio, `open-telemetry/semantic-conventions-genai`. En ese traslado cambiaron nombres: `gen_ai.client.token.usage` pasó a ser `gen_ai.client.inference.usage.*` y el proveedor se expresa con `gen_ai.provider.name`. Para que un cambio externo no rompa el panel:

1. Se fija una instantánea: commit `07794021bfe46e1c241408b6f55cb4354bd28318` (14-oct-2026), `schema_url` `https://opentelemetry.io/schemas/gen-ai-dev/1.42.0-dev` y convenciones base `v1.44.0`. Se extrae con [`herramientas/extract_semconv.py`](herramientas/extract_semconv.py) a [`vendor/otel-semconv-genai-0779402.json`](contratos/vendor/otel-semconv-genai-0779402.json), que contiene 140 atributos, 19 métricas, 3 eventos y 11 tipos de span.
2. Los servicios no escriben nombres a mano: los toman del registro mediante `crtelemetry` (C-04).
3. Para mover la instantánea se ejecuta el extractor con el commit nuevo y el validador señala todo nombre desaparecido o con otro instrumento o unidad. Después se actualiza el registro y se sube `registry_version`: *minor* si solo se añade, *major* si se renombra o se elimina.

**Normalización de tokens.** `meta.usage` guarda la entrada sin caché por separado, como hace Anthropic. Al emitir OTel:

- `gen_ai.usage.input_tokens` = `input_tokens` + `cache_read_input_tokens` + `cache_creation_input_tokens`, según la regla del documento de Anthropic en la instantánea;
- `gen_ai.usage.cache_read.input_tokens` y `gen_ai.usage.cache_write.input_tokens` son los subconjuntos;
- `gen_ai.usage.output_tokens` incluye el razonamiento y `gen_ai.usage.reasoning.output_tokens` es su subconjunto.

El coste es el de `estimate_cost`: `(sin_caché·p_in + escritura·p_in·1,25 + lectura·p_caché + salida·p_out) / 10⁶`, con la tabla `PRICES` de `cranalysis/client.py`, y siempre lleva `cr.cost.estimated = true`.

<a id="metricas-salud"></a>
## 1.6 Métricas de salud del sistema

Latencia, tasas de error, frescura, tokens y costes. Las señales `ledger:` salen del libro de ejecuciones, que existe aunque la telemetría falle. Las `metric:` vienen de VictoriaMetrics y las `external:` de archivos o del host.

**Salud y latencia** (generado):

<!-- generado:inicio umbrales-salud -->
| ID | Umbral | Señal | Agregación · ventana | Aviso | Crítico | Modo | Línea base (14-oct) | Origen |
|---|---|---|---|---|---|---|---|---|
| **SH-01** | Frescura del extractor | `ledger:run_record.finished_at` | antigüedad · instante | > 2 700 s | > 5 400 s | alerta | 259 s · Último ciclo terminado a las 16:00:41 UTC; 552 de 552 ciclos terminados entre el 9 y el 14 de octubre. | `services/bridge/crbridge/core.py` |
| **SH-02** | Ciclos fallidos del extractor | `ledger:run_record.outcome` | proporción · 7 días | > 0,01 | > 0,05 | alerta | 0 · 0 de 552 ciclos con errores registrados (columna errors). | propuesta |
| **SH-03** | Duración p95 del ciclo del extractor | `metric:cr.run.duration{service.name=cr-extractor}` | p95 · 7 días | > 300 s | > 900 s | alerta | 244 s · p95 244 s, máximo 322 s; la mediana es inferior a 1 s porque casi todos los ciclos no tienen trabajo. | medición |
| **SH-04** | Frescura de la sincronización del puente | `external:pipeline_status.last_sync_at` | antigüedad · instante | > 2 700 s | > 7 200 s | alerta | Sincronizó, pero el ciclo terminó con error drive_quota. | `services/bridge/crbridge/core.py` |
| **SH-05** | Ciclos del puente con errores | `ledger:run_record.outcome` | proporción · 7 días | > 0,05 | > 0,25 | alerta | 1 · La unidad sigue en failed: todos los ciclos desde la madrugada del 14-oct terminan con drive_quota. | propuesta |
| **SH-06** | Ciclos seguidos con error de Drive | `metric:cr.drive.errors` | consecutivos · por ejecución | ≥ 1 ejecución | ≥ 4 ejecuciones | alerta | Error vigente en pipeline-status.json. | propuesta |
| **SH-07** | Latencia p95 de Scraper.Tech (captions) | `metric:cr.provider.call.duration{cr.provider.name=scrapertech,cr.provider.operation=captions}` | p95 · 24 h | > 30 s | > 60 s | alerta | 10,1 s · Media de 37 llamadas correctas (máximo 21,1 s); las 6 con error promedian 28,4 s (máximo 65,3 s). | medición |
| **SH-08** | Tasa de error por proveedor | `metric:cr.provider.call.duration` | proporción · 24 h | > 0,2 | > 0,5 | alerta | 0,14 · Scraper.Tech 6 de 43 llamadas de captions (acumulado); Supadata 0 de 4; yt-dlp 9 de 9 blocked. | medición |
| **SH-09** | Publicación → transcripción (p50) | `metric:cr.video.time_to_transcript{cr.backfill=false}` | p50 · 7 días | > 3 600 s | > 10 800 s | alerta | 1 860 s · p50 de 31 min sobre 35 videos (incluye la carga inicial). | medición |
| **SH-10** | Publicación → transcripción (p90) | `metric:cr.video.time_to_transcript{cr.backfill=false}` | p90 · 7 días | > 21 600 s | > 86 400 s | monitor | 173 640 s · p90 de 48 h, sesgado por la carga inicial; no comparable con el umbral. | medición |
| **SH-11** | Frescura de la publicación | `external:pipeline_status.last_published_at` | antigüedad · instante | > 2 700 s | > 7 200 s | alerta | last_published_at en pipeline-status.json. | propuesta |
| **SH-12** | Comprobante de Scheduled con cola activa | `external:pipeline_status.last_receipt_at` | antigüedad · instante | > 28 800 s | > 86 400 s | alerta | Último comprobante, con estado error; aviso activo a las 16:03 UTC. | `services/bridge/crbridge/core.py` |
| **SH-13** | Trabajo pendiente más antiguo | `external:pipeline_status.oldest_pending_at` | antigüedad · instante | > 172 800 s | > 345 600 s | alerta | oldest_pending_at vigente. | `services/bridge/crbridge/core.py` |
| **SH-14** | Trabajos que requieren revisión | `metric:cr.jobs.current` | suma · instante | > 0 trabajos | critical si alguno lleva más de 24 h en ese estado | alerta | 1 trabajo · 1 trabajo blocked. | `services/bridge/crbridge/core.py` |
| **SH-15** | Telemetría descartada | `external:otelcol_exporter_send_failed_spans` | suma · 1 h | > 0 spans | > 100 spans | propuesto (fase 1) | — | propuesta |
| **SH-16** | Canal sin descubrimiento | `ledger:run_record.channels` | consecutivos · por ejecución | ≥ 1 ejecución | ≥ 3 ejecuciones | alerta | 0 ejecuciones · 5 de 5 canales ok por RSS el 14-oct; el 8 y 9 de octubre el RSS falló en el 52 % de las peticiones sueltas. | `services/transcripts/crtranscripts/pipeline.py` |
<!-- generado:fin umbrales-salud -->

**Costes, presupuestos y tokens** (generado):

<!-- generado:inicio umbrales-coste -->
| ID | Umbral | Señal | Agregación · ventana | Aviso | Crítico | Modo | Línea base (14-oct) | Origen |
|---|---|---|---|---|---|---|---|---|
| **CO-01** | Créditos de Supadata del mes | `metric:cr.budget.used{cr.budget.name=supadata_credits}` | proporción · mes natural | ≥ 0,8 | ≥ 1 | alerta | 0,2 · 4 de 20 créditos en octubre. | `services/transcripts/ops/cryptoreport-transcripts-no-paid.conf` |
| **CO-02** | Peticiones de Scraper.Tech del mes | `metric:cr.budget.used{cr.budget.name=scrapertech_requests}` | proporción · mes natural | ≥ 0,8 | ≥ 0,95 | alerta | 0,087 · 87 de 1000 peticiones en octubre. | `services/transcripts/crtranscripts/pipeline.py` |
| **CO-03** | Gasto de API de modelos con la guarda cerrada | `metric:cr.cost.usd{cr.provider.name=openai|anthropic}` | suma · mes natural | — | > 0 USD | alerta | 0 USD · 0 USD desde que existe la guarda; los 0,64 USD de los dos análisis del 12-oct son anteriores. | `services/analysis/cranalysis/config.py` |
| **CO-04** | Coste por análisis API | `metric:cr.cost.usd{cr.provider.name=openai|anthropic}` | por elemento | > 0,5 USD | > 1 USD | monitor | 0,358 USD · 0,2816 y 0,358 USD con gpt-6.1-sol (12-oct). | medición |
| **CO-05** | Presupuesto mensual de API de modelos | `metric:cr.budget.used{cr.budget.name=model_api_usd}` | proporción · mes natural | ≥ 0,8 | ≥ 1 | propuesto (fase 2) | — | propuesta |
| **TK-01** | Salida frente a CRA_MAX_TOKENS | `metric:gen_ai.client.inference.operation.output_tokens` | por elemento | > 0,75 | > 0,9 | monitor | 0,51 · 24 866 y 32 571 tokens de salida (39 % y 51 % de 64 000). | `services/analysis/cranalysis/config.py` |
| **TK-02** | Proporción de entrada leída de caché | `metric:gen_ai.client.inference.usage.cache_read.input_tokens` | proporción · 7 días | < 0,2 | — | monitor | 0,364 · 7392 de 20 285 tokens de entrada en los dos análisis del 12-oct. | medición |
<!-- generado:fin umbrales-coste -->

**SLO.** Solo SH-01 tiene un objetivo formal: el 99 % de las ventanas de 15 min con un ciclo terminado en 30 días, lo que deja un presupuesto de error de unas 7 h al mes. El resto son umbrales de alerta. Un SLO nuevo **DEBE** tener al menos 30 días de línea base.

<a id="catalogo-metricas"></a>
**Catálogo de métricas** (generado):

<!-- generado:inicio semconv-metricas -->
| Métrica | Instrumento | Unidad | Atributos | Emisores | Descripción |
|---|---|---|---|---|---|
| `cr.run.duration` | histogram | `s` | `cr.run.trigger`, `cr.run.outcome` | cr-extractor, cr-bridge, cr-analysis, cr-build-data | Duración de cada ejecución (ciclo de extractor, puente, análisis o build_data). |
| `cr.provider.call.duration` | histogram | `s` | `cr.provider.name`, `cr.provider.operation`, `cr.provider.outcome` | cr-extractor, cr-bridge | Latencia por llamada a proveedor. |
| `cr.provider.billed_units` | counter | `{unit}` | `cr.provider.name`, `cr.budget.name` | cr-extractor | Unidades facturables consumidas por proveedor y presupuesto. |
| `cr.video.discovered` | counter | `{video}` | `cr.channel.slug`, `cr.discovery.source` | cr-extractor | Videos nuevos encolados por canal y fuente. |
| `cr.video.time_to_transcript` | histogram | `s` | `cr.channel.slug`, `cr.video.is_short`, `cr.backfill` | cr-extractor | Tiempo desde la publicación del video hasta guardar una transcripción válida. |
| `cr.transcript.quality` | counter | `{verdict}` | `cr.quality.verdict`, `cr.quality.reason` | cr-extractor, cr-bridge | Veredictos y motivos de la puerta de calidad (un punto por motivo). |
| `cr.transcript.coverage` | histogram | `1` | `cr.channel.slug` | cr-extractor | Cobertura de cada transcripción guardada. |
| `cr.job.transitions` | counter | `{transition}` | `cr.job.previous_state`, `cr.job.state` | cr-bridge | Transiciones de estado de trabajos del puente. |
| `cr.jobs.current` | gauge | `{job}` | `cr.job.state` | cr-bridge | Trabajos por estado al cerrar cada ciclo del puente. |
| `cr.drive.errors` | counter | `{error}` | `error.type`, `cr.drive.operation` | cr-bridge | Errores de Drive por clase y operación. |
| `cr.validator.results` | counter | `{check}` | `cr.validator.check`, `cr.validator.outcome`, `cr.analysis.provider` | cr-bridge, cr-analysis | Resultados del validador por familia de comprobaciones y origen del análisis. |
| `cr.agent.jobs` | counter | `{job}` | `gen_ai.agent.name`, `cr.agent.job_outcome` | cr-bridge | Trabajos del agente externo por etapa alcanzada (base del GCR). |
| `cr.cost.usd` | counter | `{USD}` | `cr.provider.name`, `gen_ai.request.model`, `cr.cost.estimated` | cr-extractor, cr-analysis | Gasto en USD por proveedor y modelo (estimado con PRICES si no hay factura). |
| `cr.budget.used` | gauge | `{unit}` | `cr.budget.name` | cr-extractor, cr-panel | Consumo acumulado del periodo por presupuesto. |
| `cr.budget.limit` | gauge | `{unit}` | `cr.budget.name` | cr-extractor, cr-panel | Límite vigente del periodo por presupuesto. |
| `cr.publish.duration` | histogram | `s` | `cr.publish.target`, `cr.publish.outcome` | cr-extractor, cr-bridge, cr-build-data | Duración de cada publicación. |
| `cr.feedback.ratings` | counter | `{rating}` | `cr.feedback.rating`, `cr.feedback.target_kind` | cr-panel | Valoraciones 👍/👎 por tipo de objeto. |
| `cr.intervention.count` | counter | `{intervention}` | `cr.intervention.type`, `cr.intervention.outcome` | cr-panel | Intervenciones manuales por tipo y resultado. |
| `cr.eval.score` | histogram | `1` | `gen_ai.evaluation.name`, `cr.eval.kind` | cr-bridge, cr-analysis, cr-panel | Puntuaciones normalizadas a [0, 1] por evaluación. |
| `gen_ai.client.inference.duration` | histogram | `s` | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `error.type` | cr-analysis | Duración de cada llamada de inferencia. |
| `gen_ai.client.inference.usage.input_tokens` | counter | `{token}` | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.token.modality` | cr-analysis | Tokens de entrada (incluye caché leída y escrita). |
| `gen_ai.client.inference.usage.output_tokens` | counter | `{token}` | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.token.modality` | cr-analysis | Tokens de salida (incluye razonamiento). |
| `gen_ai.client.inference.usage.cache_read.input_tokens` | counter | `{token}` | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.token.modality` | cr-analysis | Subconjunto de entrada leído de caché. |
| `gen_ai.client.inference.usage.cache_write.input_tokens` | counter | `{token}` | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.token.modality` | cr-analysis | Subconjunto de entrada escrito en caché. |
| `gen_ai.client.inference.usage.reasoning.output_tokens` | counter | `{token}` | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.token.modality` | cr-analysis | Subconjunto de salida dedicado al razonamiento. |
| `gen_ai.client.inference.operation.output_tokens` | histogram | `{token}` | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `error.type` | cr-analysis | Tokens de salida por operación (riesgo de truncado frente a CRA_MAX_TOKENS). |
| `gen_ai.invoke_agent.duration` | histogram | `s` | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.agent.name`, `error.type` | cr-bridge | Duración de cada ejecución del agente Scheduled (desde el comprobante; se registra una vez por run_id). |
| `gen_ai.invoke_workflow.duration` | histogram | `s` | `gen_ai.operation.name`, `gen_ai.workflow.name`, `error.type` | cr-analysis | Duración de cada análisis completo (prompt, modelo, validación, guardado). |
<!-- generado:fin semconv-metricas -->

<a id="metricas-agentes"></a>
## 1.7 Métricas de rendimiento de agentes

<a id="gcr"></a>
### 1.7.1 Goal Completion Rate

Un objetivo se cumple cuando el agente entrega lo que se le pidió, en el formato acordado, validado por el servidor y a tiempo:

- **Scheduled, por trabajo:** `GCR = trabajos intentados que acaban imported y válidos en ≤ 24 h / trabajos intentados`. El intento se toma de `attempted_job_ids` del comprobante y el resultado, del estado del trabajo. La variante **a la primera** cuenta solo las importaciones `automatic`, sin `reviewed` ni `manual`.
- **Scheduled, por ejecución:** comprobantes sin `error` / comprobantes (AP-03).
- **Análisis por API:** videos guardados como `ok` en la primera llamada / videos intentados. Una respuesta truncada, rechazada o ilegible cuenta como fallo.

Línea base: GCR de 0,967 (29 de 30), GCR a la primera de 0,867 (26 de 30) y 0,556 de ejecuciones sin error (5 de 9).

<a id="trayectorias"></a>
### 1.7.2 Evaluación de trayectorias

La trayectoria de referencia sale de `scheduled-instructions.md`, revisión 1.3. Para una ejecución con dos trabajos tiene 18 pasos:

| Fase | Pasos (identificadores) |
|---|---|
| Inicio | `registrar_inicio` → `leer_indice` → `verificar_contrato` → `seleccionar_trabajos` |
| Por trabajo (×2) | `leer_trabajo` → `analizar` → `validar_con_codigo` → `revisar_contenido` → `subir_resultado` → `verificar_subida` |
| Cierre | `escribir_comprobante` → `verificar_comprobante` |
| Prohibidos | `llamar_api_inferencia`, `cambiar_modelo`, `comprar_creditos`, `ejecutar_cranalysis_run`, `resubir_escritura_dudosa`, `reintentar_sin_autorizacion`, `escribir_fuera_de_carpetas`, `trabajo_extra` (cada `leer_trabajo` a partir del tercero) |

Las métricas comparan la trayectoria esperada *E* con la observada *O* contando repeticiones: un paso repetido solo coincide tantas veces como aparece en *E*.

| Métrica | Definición |
|---|---|
| `cr.trajectory.precision` | \|E ∩ O\| / \|O\| |
| `cr.trajectory.recall` | \|E ∩ O\| / \|E\| |
| `cr.trajectory.exact_match` | O = E |
| `cr.trajectory.in_order_match` | E es subsecuencia de O: todos los pasos, en orden, con otros intercalados |
| `cr.trajectory.any_order_match` | conjunto(E) ⊆ conjunto(O) |
| `cr.trajectory.forbidden_steps` | Pasos de O que están en la lista prohibida |

**Ejemplo verificado.** Si el segundo trabajo repite `analizar` y `validar_con_codigo` (la pasada de corrección permitida) y omite `revisar_contenido`, la trayectoria observada tiene 19 pasos y 17 coinciden. Resultado: precisión 17/19 = 0,8947, recall 17/18 = 0,9444, `any_order_match` verdadero e **`in_order_match` falso**, porque falta la revisión antes de subir. Por eso el orden pesa: el conjunto de pasos parece completo y el proceso no lo fue. Estos valores los reproduce [`trajectory_metrics.py`](herramientas/trajectory_metrics.py) y los comprueba PV-17.

**Requisito para medirlo.** Hoy los comprobantes solo dicen qué trabajos se intentaron. Las instrucciones 1.4 deben añadir `pasos: [{paso, at, job_id?}]` y `modo: scheduled | manual` al comprobante; hasta entonces AP-05 a AP-08 son *propuestos*. El límite de trabajos (AP-04) ya se mide con los datos actuales.

<a id="autorater"></a>
### 1.7.3 Autorater (LLM-as-a-Judge)

El validador determinista ya garantiza la forma: citas literales con ±0,05 s, IDs y referencias, y fuentes aportadas. El juez evalúa lo que el código no ve. La rúbrica `rubrica-narrativas@1.0.0` puntúa cada criterio de 1 a 5, con anclas escritas para 1, 3 y 5, y la normalización es `(s − 1) / 4`:

| Criterio (`gen_ai.evaluation.name`) | Pregunta | Caso real que lo motiva |
|---|---|---|
| `cr.autorater.fidelity` | ¿Las citas sostienen lo que se afirma en su contexto, no solo literalmente? | Paráfrasis E8 y E15 en el piloto largo |
| `cr.autorater.coverage` | ¿Falta alguna afirmación de mercado relevante? | Afirmación sobre el SP500 omitida en el piloto |
| `cr.autorater.no_fabrication` | ¿Hay algo en título, tesis o insights que el video no dice? | «URGENTE» inventado en un título |
| `cr.autorater.verification_calibration` | ¿El `estado_verificacion` es coherente con las evidencias y fuentes aportadas? | Negación ambigua resuelta con demasiada firmeza |
| `cr.autorater.insinuation` | ¿Se tipifican bien las insinuaciones alcistas y bajistas? | Requisito de Urania: señales siempre visibles |
| `cr.autorater.scenarios` | ¿Los escenarios tienen supuestos, catalizadores e invalidación? | Contrato del prompt v1.0.0 |

Controles del juez:

- **Familia distinta.** Si el análisis es de GPT-6.1 Sol, el juez es Claude Sonnet 5.5, para reducir la autopreferencia.
- **Prompt versionado.** El prompt del juez se versiona como activo y su SHA-256 viaja en `evaluator.prompt_sha256`.
- **Sin influencia ajena.** El juez no ve la puntuación de otros jueces ni el feedback humano.
- **Calibración.** Antes de que el juez pueda alertar, se forma un conjunto de calibración: al menos 30 análisis, cada uno puntuado por 2 personas. El kappa de Cohen ponderado (cuadrático) entre juez y personas **DEBE** ser ≥ 0,6 (AP-11).
- **Nunca bloquea.** Un autorater **NO DEBE** bloquear publicaciones: el esquema rechaza `mode: gate` para `kind: autorater` en el contrato 1.x.

**Coste.** Con unos 20 000 tokens de entrada y 2000 de salida por análisis y los precios de `PRICES` (2 y 10 USD/MTok), sale a unos 0,06 USD por análisis. A unos 8 análisis al día son alrededor de 15 USD al mes. Requiere presupuesto aprobado: hoy el presupuesto es 0 y la guarda G-01 está cerrada. La alternativa gratuita es un trabajo de juez en Scheduled, pero con la misma familia de modelo y, por tanto, más sesgo.

**Umbrales de agentes** (generado):

<!-- generado:inicio umbrales-agentes -->
| ID | Umbral | Señal | Agregación · ventana | Aviso | Crítico | Modo | Línea base (14-oct) | Origen |
|---|---|---|---|---|---|---|---|---|
| **AP-01** | Goal Completion Rate de Scheduled | `metric:cr.agent.jobs` | proporción · 7 días | < 0,9 | < 0,75 | alerta | 0,967 · 29 de 30 trabajos únicos intentados están importados (13 y 14 de octubre). | medición |
| **AP-02** | GCR a la primera | `metric:cr.agent.jobs` | proporción · 7 días | < 0,8 | < 0,6 | alerta | 0,867 · 26 de 30 (1 manual, 1 reviewed, 1 sin modo, 1 bloqueado). | medición |
| **AP-03** | Ejecuciones del agente sin error | `ledger:run_record.outcome` | proporción · 7 días | < 0,8 | < 0,5 | alerta | 0,556 · 5 resultados_subidos y 4 error (2 revision_material y 2 seleccion). | medición |
| **AP-04** | Límite de trabajos por ejecución | `check:receipt.job_limit` | recuento · 7 días | ≥ 1 ejecución | critical si attempted_job_ids &gt; 5 en una ejecución no declarada como manual | alerta | 1 ejecución · La ejecución del 2026-10-14T04:30:15Z intentó y subió 22 trabajos; el puente no lo detectó. | `docs/automatizacion-drive/scheduled-instructions.md` |
| **AP-05** | Precisión de trayectoria | `eval:cr.trajectory.precision` | media · 7 días | < 0,9 | < 0,75 | propuesto (fase 3) | — | propuesta |
| **AP-06** | Recall de trayectoria | `eval:cr.trajectory.recall` | media · 7 días | < 0,95 | < 0,8 | propuesto (fase 3) | — | propuesta |
| **AP-07** | Coincidencia en orden | `eval:cr.trajectory.in_order_match` | media · 7 días | < 0,95 | < 0,8 | propuesto (fase 3) | — | propuesta |
| **AP-08** | Pasos prohibidos | `eval:cr.trajectory.forbidden_steps` | recuento · por ejecución | — | > 0 pasos | propuesto (fase 3) | — | propuesta |
| **AP-09** | Rechazo del validador sobre resultados del agente | `metric:cr.validator.results{cr.analysis.provider=chatgpt-scheduled}` | proporción · 7 días | > 0,1 | > 0,25 | alerta | 1 rechazo archivado en bridge/rejected; 8 «Resultado ilegible» el 14-oct ya resueltos. Sin denominador histórico hasta la Fase 0. | medición |
| **AP-10** | Puntuación del autorater | `eval:cr.autorater.overall` | media · 7 días | < 0,7 | < 0,6 | propuesto (fase 3) | — | propuesta |
| **AP-11** | Acuerdo juez–humano | `eval:cr.autorater.agreement_kappa` | kappa · 30 días | < 0,6 | < 0,4 | propuesto (fase 3) | — | propuesta |
| **AP-12** | Aprobación humana | `metric:cr.feedback.ratings{cr.feedback.target_kind=analysis}` | proporción · 30 días | < 0,8 | < 0,6 | propuesto (fase 2) | — | propuesta |
| **AP-13** | 👎 bloqueantes sin resolver | `ledger:feedback.severity` | recuento · instante | — | > 0 valoraciones | propuesto (fase 2) | — | propuesta |
| **AP-14** | Cola → importación (p90) | `ledger:job.transitions` | p90 · 7 días | > 86 400 s | > 172 800 s | propuesto (fase 0) | — | propuesta |
<!-- generado:fin umbrales-agentes -->

<a id="calidad-datos"></a>
## 1.8 Umbrales de calidad de datos de medios no estructurados

Cada umbral DQ-* se aplica a una versión concreta de un activo y su resultado se guarda como [`quality-report`](contratos/esquemas/quality-report.schema.json). Los umbrales en modo *bloquea* ya están en el código: la puerta `crtranscripts.quality.assess` es común a la extracción, el puente y la publicación. El validador comprueba en cada CI que las anclas de código siguen existiendo (PV-06).

**Video y metadatos.** El video no se descarga: solo se guardan sus metadatos y la referencia (parte 3).

<!-- generado:inicio umbrales-video -->
| ID | Umbral | Señal | Agregación · ventana | Aviso | Crítico | Modo | Línea base (14-oct) | Origen |
|---|---|---|---|---|---|---|---|---|
| **DQ-V-01** | Duración conocida | `check:video.duration_known` | proporción · 7 días | < 0,99 | < 0,95 | alerta | 1 · 35 de 35 con duración. | `services/transcripts/crtranscripts/pipeline.py` |
| **DQ-V-02** | Shorts con duración imposible | `check:video.short_duration` | recuento · 7 días | > 0 videos | — | monitor | 0 videos · 20 shorts, el más largo de 87 s. | propuesta |
| **DQ-V-03** | Generación con varias pistas de audio | `check:supadata.generate_single_track` | recuento · por elemento | — | > 0 videos | bloquea | 0 videos · Generación desactivada en el perfil sin pago. | `services/transcripts/crtranscripts/pipeline.py` |
| **DQ-V-04** | Fechas aproximadas sin corregir | `check:video.published_at_approx` | recuento · 24 h | > 0 videos | — | propuesto (fase 1) | — | propuesta |
<!-- generado:fin umbrales-video -->

**Transcripción del audio.** La pista es la original en español; las pistas `ar`, `en` y `pt` son doblaje automático.

<!-- generado:inicio umbrales-transcripcion -->
| ID | Umbral | Señal | Agregación · ventana | Aviso | Crítico | Modo | Línea base (14-oct) | Origen |
|---|---|---|---|---|---|---|---|---|
| **DQ-T-01** | Sin segmentos | `check:quality.assess:sin_segmentos` | por elemento | — | si ocurre | bloquea | — | `services/transcripts/crtranscripts/quality.py` |
| **DQ-T-02** | Idioma distinto del original | `check:quality.assess:idioma_no_original` | por elemento | — | si ocurre | bloquea | — | `services/transcripts/crtranscripts/quality.py` |
| **DQ-T-03** | Segmentos inválidos | `check:quality.assess:segmentos_invalidos` | por elemento | — | si ocurre | bloquea | — | `services/transcripts/crtranscripts/quality.py` |
| **DQ-T-04** | Tiempos fuera del video | `check:quality.assess:tiempos_fuera_del_video` | por elemento | — | si ocurre | bloquea | — | `services/transcripts/crtranscripts/quality.py` |
| **DQ-T-05** | Posible corte final | `check:quality.assess:posible_corte_final` | por elemento | — | si ocurre | bloquea | — | `services/transcripts/crtranscripts/quality.py` |
| **DQ-T-06** | Posible corte inicial | `check:quality.assess:posible_corte_inicial` | por elemento | — | si ocurre | bloquea | — | `services/transcripts/crtranscripts/quality.py` |
| **DQ-T-07** | Hueco largo | `check:quality.assess:hueco_largo_revisar_audio` | por elemento | si ocurre | — | monitor | Mayor hueco observado: 46 s. | `services/transcripts/crtranscripts/quality.py` |
| **DQ-T-08** | Segmentos duplicados exactos | `check:quality.assess:segmentos_duplicados_exactos` | por elemento | — | si ocurre | bloquea | — | `services/transcripts/crtranscripts/quality.py` |
| **DQ-T-09** | Conteo de segmentos incoherente | `check:quality.assess:conteo_segmentos_incorrecto` | por elemento | — | si ocurre | bloquea | — | `services/transcripts/crtranscripts/quality.py` |
| **DQ-T-10** | Cobertura baja | `metric:cr.transcript.coverage` | por elemento | < 0,85 | — | monitor | 0,911 · Mínimo 0,911 y media 0,993 sobre 35 transcripciones. | `services/transcripts/crtranscripts/pipeline.py` |
| **DQ-T-11** | Velocidad de habla plausible | `check:transcript.words_per_minute` | por elemento | fuera de [120, 260 palabras/min] | fuera de [60, 320 palabras/min] | monitor | 187 palabras/min · Mínimo 142, p50 187, máximo 227. | medición |
| **DQ-T-12** | Marcadores no verbales | `check:transcript.nonverbal_share` | por elemento | > 0,15 | — | monitor | 0,029 · Máximo 2,9 %, media 0,18 %. | medición |
| **DQ-T-13** | Acuerdo entre proveedores | `check:transcript.provider_agreement` | por elemento | < 0,9 | — | propuesto (fase 1) | — | propuesta |
| **DQ-T-14** | Rechazos de la puerta | `metric:cr.transcript.quality{cr.quality.verdict=invalid}` | proporción · 7 días | > 0,05 | > 0,2 | alerta | 0 · 35 guardadas, 0 inválidas. | propuesta |
<!-- generado:fin umbrales-transcripcion -->

**Chunking semántico.** Estos umbrales entran en vigor con el índice vectorial (Fase 3). Los chunks se forman con ventanas de segmentos: con una mediana de 4,2 s por segmento, un chunk de unos 300 tokens agrupa entre 7 y 28 segmentos.

<!-- generado:inicio umbrales-chunking -->
| ID | Umbral | Señal | Agregación · ventana | Aviso | Crítico | Modo | Línea base (14-oct) | Origen |
|---|---|---|---|---|---|---|---|---|
| **DQ-C-01** | Cobertura de segmentos por chunks | `check:chunking.segment_coverage` | por elemento | — | < 1 | propuesto (fase 3) | — | propuesta |
| **DQ-C-02** | Tamaño de chunk | `check:chunking.token_range` | proporción · por elemento | < 0,95 | — | propuesto (fase 3) | — | propuesta |
| **DQ-C-03** | Duración de chunk | `check:chunking.duration_range` | proporción · por elemento | < 0,95 | — | propuesto (fase 3) | — | propuesta |
| **DQ-C-04** | Solape entre chunks | `check:chunking.overlap_ratio` | máximo · por elemento | > 0,2 | — | propuesto (fase 3) | — | propuesta |
| **DQ-C-05** | Chunks obsoletos | `check:chunking.stale` | recuento · instante | > 0 chunks | — | propuesto (fase 3) | — | propuesta |
| **DQ-C-06** | Chunks duplicados | `check:chunking.duplicates` | recuento · por elemento | > 0 chunks | — | propuesto (fase 3) | — | propuesta |
<!-- generado:fin umbrales-chunking -->

**Embeddings e índice** (Fase 3):

<!-- generado:inicio umbrales-embeddings -->
| ID | Umbral | Señal | Agregación · ventana | Aviso | Crítico | Modo | Línea base (14-oct) | Origen |
|---|---|---|---|---|---|---|---|---|
| **DQ-E-01** | Dimensión del vector | `check:embedding.dimension` | recuento · por elemento | — | > 0 vectores | propuesto (fase 3) | — | propuesta |
| **DQ-E-02** | Normalización del vector | `check:embedding.norm_deviation` | máximo · por elemento | > 0,001 | — | propuesto (fase 3) | — | propuesta |
| **DQ-E-03** | Retraso del índice | `ledger:vector_index_status.freshness` | máximo · instante | > 1 800 s | > 7 200 s | propuesto (fase 3) | — | propuesta |
| **DQ-E-04** | Recall@10 de la búsqueda semántica | `eval:cr.search.recall_at_10` | media · 30 días | < 0,8 | < 0,6 | propuesto (fase 3) | — | propuesta |
| **DQ-E-05** | nDCG@10 de la búsqueda semántica | `eval:cr.search.ndcg_at_10` | media · 30 días | < 0,7 | — | propuesto (fase 3) | — | propuesta |
<!-- generado:fin umbrales-embeddings -->

**Etiquetado de metadatos (menciones y tono).** El léxico de 39 temas y el motor de tono son reglas, sin modelos; su calidad se calibra con personas.

<!-- generado:inicio umbrales-etiquetado -->
| ID | Umbral | Señal | Agregación · ventana | Aviso | Crítico | Modo | Línea base (14-oct) | Origen |
|---|---|---|---|---|---|---|---|---|
| **DQ-M-01** | Precisión de menciones ambiguas | `eval:cr.tagging.mention_precision` | por elemento · 30 días | < 0,9 | — | propuesto (fase 3) | — | propuesta |
| **DQ-M-02** | Deriva de umbrales de tono | `check:tone_threshold_drift` | recuento · por elemento | — | > 0 umbrales | bloquea | 0 umbrales · Hoy coinciden: 0,75 / ±0,3 / 3,5 / 1,6. | `prototypes/movil/tono.py` |
| **DQ-M-03** | Acuerdo humano con la etiqueta de tono | `eval:cr.tagging.tone_kappa` | kappa · 30 días | < 0,6 | — | propuesto (fase 3) | — | propuesta |
<!-- generado:fin umbrales-etiquetado -->

**Análisis:**

<!-- generado:inicio umbrales-analisis -->
| ID | Umbral | Señal | Agregación · ventana | Aviso | Crítico | Modo | Línea base (14-oct) | Origen |
|---|---|---|---|---|---|---|---|---|
| **DQ-A-01** | Publicados que pasan el validador | `check:site.analysis_matches` | proporción · instante | — | < 1 | bloquea | 1 · 32 de 32 análisis válidos. | `services/transcripts/crtranscripts/site.py` |
| **DQ-A-02** | Hash de transcripción del análisis | `check:quality.analysis_matches` | proporción · instante | — | < 1 | bloquea | — | `services/transcripts/crtranscripts/quality.py` |
| **DQ-A-03** | Precisión temporal de citas | `check:validator:quotes` | por elemento | — | > 0,05 s | bloquea | — | `services/analysis/cranalysis/validate.py` |
| **DQ-A-04** | Análisis insuficientes | `metric:cr.validator.results` | proporción · 30 días | > 0,1 | — | monitor | 0 · 27 parcial, 5 completo, 0 insuficiente. | medición |
<!-- generado:fin umbrales-analisis -->

<a id="alertas-runbooks"></a>
## 1.9 Alertas y runbooks

Una alerta nace de un umbral en modo *alert* ([`alert.schema.json`](contratos/esquemas/alert.schema.json)). Se muestra en el panel y, cuando haya bot y chat elegidos, va también a Telegram. Para no repetir avisos, una alerta abierta se agrupa por umbral y objetivo, y solo vuelve a notificar si sube de severidad. Cada runbook dice cómo confirmar y qué hacer. Los comandos son de solo lectura salvo que se indique.

### RB-01 · Extracción detenida o canal sin descubrimiento
- **Señales:** SH-01, SH-03, SH-16.
- **Confirmar:** `systemctl list-timers cryptoreport-transcripts.timer`, `journalctl -u cryptoreport-transcripts -n 50` y la última fila del libro de ejecuciones. Un `busy` repetido indica un ciclo colgado que retiene `run.lock`.
- **Actuar:** intervención `run_extractor_now`. Si el RSS y las páginas fallan en un canal, comprobar desde el VPS que `/videos` responde con `hl=es`.

### RB-02 · Ciclos fallidos del extractor
- **Señales:** SH-02.
- **Confirmar:** el evento `exception` del span raíz y la línea `FATAL` con el mismo `run_id`.
- **Actuar:** corregir el código con su prueba y repetir con `run_extractor_now`. No cambiar parámetros para tapar una excepción.

### RB-03 · Proveedor degradado
- **Señales:** SH-07, SH-08, SH-09.
- **Confirmar:** `cr.provider.call.duration` y `outcome` por proveedor, y `kv health:<proveedor>`. Un `{"error":"Access denied"}` con HTTP 200 es una clave mala (`auth`).
- **Actuar:** esperar el cooldown (30 min). Si la causa está corregida, `end_provider_cooldown` (requiere 2.ª persona). No adelantar Supadata en la cadena (G-03).

### RB-04 · Puente sin sincronizar o con errores
- **Señales:** SH-04, SH-05.
- **Confirmar:** `pipeline-status.json` (`errors` y `warnings`) y el span del paso que abortó el ciclo.
- **Actuar:** si es Drive, seguir RB-05. Si es control (G-07), revisar los hashes de prompt y esquema en la carpeta de control. Después, `run_bridge_now`.

### RB-05 · Cuota o autenticación de Drive
- **Señales:** SH-06.
- **Confirmar:** `cr.drive.errors` por `error.type`.
- **Actuar:** con `drive_quota`, `pause_drive_uploads` mientras dure y pasar a un cliente OAuth propio: es la dependencia D1 y el hallazgo H-02. Con `drive_auth`, renovar la autorización de rclone en el host (fuera del panel). Reanudar con `resume_drive_uploads`.

### RB-06 · Scheduled sin comprobante o con error
- **Señales:** SH-12, AP-03.
- **Confirmar:** los `errors` del último comprobante (`revision_material` o `seleccion`) y si la tarea sigue activa en ChatGPT; el servidor no puede ver esa interfaz.
- **Actuar:** revisar el material señalado (RB-07). Para un trabajo `blocked`, `retry_job` con motivo escrito.

### RB-07 · Trabajos que requieren revisión
- **Señales:** SH-13, SH-14.
- **Confirmar:** la bandeja W3 por estado:
  - `blocked`: intento sin resultado;
  - `rejected`: validador;
  - `conflict`: análisis distinto;
  - `upload_uncertain`: subida dudosa;
  - `needs_transcript`: puerta de calidad.
- **Actuar:**
  - `retry_job`;
  - `import_reviewed` (requiere 2.ª persona);
  - `resolve_upload_uncertain` (requiere 2.ª persona);
  - `request_transcript_recovery`.

### RB-08 · Presupuesto cerca del límite
- **Señales:** CO-01, CO-02.
- **Confirmar:** la proyección de fin de mes en W1.
- **Actuar:** `freeze_paid_providers` (de un solo clic, no necesita aprobación). Subir un techo es un cambio del host, fuera del panel.

### RB-09 · Gasto de API con la guarda cerrada
- **Señales:** CO-03.
- **Es un incidente.** `freeze_model_api` de inmediato. Revisar qué proceso llamó a la API (spans `chat` y el journal), y rotar la clave en el host si hay sospecha de fuga (H-12).

### RB-10 · Publicación atrasada
- **Señales:** SH-11.
- **Confirmar:** eventos `cr.publish.failed` y `publish_dirty` en el puente.
- **Actuar:** `republish`. Si `build_data.py` aborta, buscar el JSON malformado (H-09).

### RB-11 · Calidad de datos degradada
- **Señales:** DQ-V-01, DQ-T-14, DQ-E-03.
- **Confirmar:** distribución de `cr.quality.reason` y el inspector de la transcripción (W8).
- **Actuar:** `request_transcript_recovery` sobre la versión afectada. Si ya se publicó algo con ella, `quarantine_asset`.

### RB-12 · Rendimiento del agente bajo
- **Señales:** AP-01, AP-02, AP-09.
- **Confirmar:** motivos de rechazo por familia (`cr.validator.results`) y los últimos 5 resultados en W4.
- **Actuar:** si el patrón es de contenido, preparar una revisión de las instrucciones (solicitud de cambio, `release`); si es de material, ir a RB-11.

### RB-13 · 👎 bloqueante sin resolver
- **Señales:** AP-13.
- **Actuar:** la intervención `quarantine_asset` ya está solicitada. Revisarla, aprobarla o rechazarla con motivo.

### RB-14 · Telemetría degradada
- **Señales:** SH-15.
- **Confirmar:** `curl -fsS 127.0.0.1:13133` (salud del Collector) y `docker compose ps`.
- **Actuar:** reiniciar el componente caído. Los ciclos siguen funcionando (P7) y el panel muestra «sin datos de traza» en lugar de ceros.

### RB-15 · Recursos del host
- **Señales:** RS-01 a RS-05.
- **Confirmar:** `docker stats --no-stream`, `free -h` y `du -sh` de los volúmenes.
- **Actuar:** recortar la retención (trazas a 14 días) o parar Jaeger, que es el más prescindible. Nunca quitar memoria a los servicios del pipeline.

### RB-16 · Límite de trabajos por ejecución excedido
- **Señales:** AP-04, AP-08.
- **Confirmar:** el comprobante (`attempted_job_ids`) y si fue una ejecución manual de carga, que hoy no se declara.
- **Actuar:** anotar la confirmación en la alerta. Si no fue manual, corregir las instrucciones en ChatGPT y subir de revisión.

<a id="arquitectura-telemetria"></a>
## 1.10 Arquitectura de telemetría en este servidor

```text
 cr-extractor ─┐   OTLP/HTTP 127.0.0.1:4318          ┌─► Jaeger v2 (Badger)        trazas · 30 d   · UI/API 127.0.0.1:16686
 cr-bridge ────┼──────────────────────────► otelcol ──┼─► VictoriaMetrics single    métricas · 400 d · 127.0.0.1:8428
 cr-build-data ┤   (batch 1 s · timeout 2 s ·        └─► VictoriaLogs              logs · 30 d     · 127.0.0.1:9428
 cr-analysis ──┤    cola 2048 · fail-open)     ▲
 cr-panel ─────┘                               └── receptor journald (stdout JSON de todos los servicios)
                                                    processors: memory_limiter · resource · attributes/redact · batch
 cr-panel ── consultas: Jaeger API v3 (/api/v3/traces) · MetricsQL ({__name__="…"}) · LogsQL (cr.run.id)
```

| Componente | Versión de referencia | Función | Límite de memoria | Retención |
|---|---|---|---|---|
| OpenTelemetry Collector Contrib | v0.162.0 (29-sep-2026) | Recibe OTLP y journald, redacta y reparte | 128 MiB (`memory_limiter` a 100 MiB) | — |
| Jaeger v2 (all-in-one, Badger) | v2.22.0 (6-oct-2026) | Trazas; API de consulta v3 estable | 256 MiB | 30 días (TTL de Badger) |
| VictoriaMetrics single-node | v1.154.0 (12-oct-2026) | Métricas OTLP en `/opentelemetry/v1/metrics`, nombres tal cual | 256 MiB | 400 días |
| VictoriaLogs | v1.53.0 (1-oct-2026) | Logs OTLP en `/insert/opentelemetry/v1/logs` | 192 MiB | 30 días |
| `cr-panel` | — | API, UI y SSE | 160 MiB | panel.sqlite sin caducidad |
| **Total** | | | **992 MiB ≤ 1 GiB (RS-01)** | |

Decisiones:

- **Todos los puertos en `127.0.0.1`.** Solo nginx expone el panel.
- **Sin Grafana:** el panel es la interfaz. La UI de Jaeger y VMUI quedan para consultas puntuales por túnel SSH.
- **Métricas sin conversión de nombres.** No se usa `-opentelemetry.usePrometheusNaming`, así que los nombres del registro son los que se consultan, con el selector `{__name__="cr.run.duration"}`, válido en MetricsQL y PromQL.
- **Muestreo del 100 %.** Hay menos de 5000 spans al día: el muestreo no compensa su complejidad.
- **SDK de Python.** `opentelemetry-sdk` y `opentelemetry-exporter-otlp-proto-http` 1.45.1, con `BatchSpanProcessor(schedule_delay_millis=1000, export_timeout_millis=2000, max_queue_size=2048)`. Al terminar cada proceso oneshot, `force_flush(timeout_millis=2000)`. Si el Collector no responde, los spans se descartan y el ciclo sigue: el libro de ejecuciones conserva el resultado.
- **Sin autoinstrumentación GenAI.** `opentelemetry-instrumentation-openai-v2` está en beta (2.4b0) y el paquete `opentelemetry-instrumentation-anthropic` de PyPI no es oficial (es de OpenLLMetry). `crtelemetry` emite los spans GenAI a mano con los nombres del registro.

**Presupuesto de recursos** (generado). PV-09 lo mide a diario desde la Fase 1:

<!-- generado:inicio umbrales-recursos -->
| ID | Umbral | Señal | Agregación · ventana | Aviso | Crítico | Modo | Línea base (14-oct) | Origen |
|---|---|---|---|---|---|---|---|---|
| **RS-01** | Memoria de la pila de observabilidad | `external:cgroup.memory.current` | máximo · 1 h | > 0,8 GiB | > 1 GiB | propuesto (fase 1) | — | propuesta |
| **RS-02** | CPU de la pila de observabilidad | `external:cgroup.cpu.usage` | media · 1 h | > 0,25 vCPU | > 0,5 vCPU | propuesto (fase 1) | — | propuesta |
| **RS-03** | Disco de telemetría | `external:du.telemetry_volumes` | último valor · instante | > 4 GiB | > 5 GiB | propuesto (fase 1) | — | propuesta |
| **RS-04** | Sobrecoste de instrumentación | `derived:p50(cr.run.duration)/p50_previo - 1` | p50 · 7 días | > 0,05 | > 0,15 | propuesto (fase 1) | — | propuesta |
| **RS-05** | Memoria disponible del host | `external:proc.meminfo.MemAvailable` | último valor · instante | < 1,5 GiB | < 0,75 GiB | propuesto (fase 1) | 4,1 GiB · 4,1 GiB disponibles de 7,7 GiB. | medición |
<!-- generado:fin umbrales-recursos -->

<a id="privacidad-retencion"></a>
## 1.11 Privacidad, seguridad y retención

| Dato | Sensibilidad | Retención | Acceso |
|---|---|---|---|
| Metadatos y referencias de video | Públicos en origen | Indefinida | `viewer` |
| Transcripciones y versiones | Internas (contenido público transformado) | Indefinida | `viewer` |
| Análisis | Internos | Indefinida | `viewer`; exportar los `restricted` queda auditado |
| Prompts, esquemas, instrucciones y comprobantes | Restringidos | Indefinida | `reviewer` |
| Trazas | Internas, sin contenido | 30 días | `viewer` |
| Métricas | Internas | 400 días | `viewer` |
| Logs | Internos, sin secretos | 30 días | `viewer` |
| Auditoría | Restringida | Indefinida (append-only) | `auditor` y `admin` |
| Cuentas | Seudónimos, hash argon2id, secreto TOTP cifrado | Mientras la cuenta exista | `admin` |

Ningún dato personal de terceros entra en el sistema: los videos son públicos y los creadores se identifican por canal. Si una persona pide retirar un contenido, se crea una lápida (*tombstone*) auditada en la Biblioteca. El contenido sale de la publicación y la huella se conserva.

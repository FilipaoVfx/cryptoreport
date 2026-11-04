# Parte 2 · Panel de control de parámetros

> Especificación arquitectónica del servicio independiente `cr-panel`: qué se puede ajustar, cómo llega un cambio a los servicios, quién lo aprueba y qué nunca puede hacer el panel.
> Contrato de la API: [`contratos/openapi.yaml`](contratos/openapi.yaml) (OpenAPI 3.1.1, validada con el esquema oficial del 2026-08-03).

<a id="objetivo-limites"></a>
## 2.1 Objetivo y límites

El panel permite vigilar, ajustar y depurar la cadena sin entrar por SSH. Es **independiente**: tiene proceso, usuario de sistema, base de datos, vhost y despliegue propios. Si el panel cae, el pipeline sigue igual; si cae el pipeline, el panel lo muestra.

| El panel **PUEDE** | El panel **NO DEBE** |
|---|---|
| Leer `state.sqlite`, `bridge/state.sqlite`, transcripciones, análisis y `pipeline-status.json` en solo lectura | Escribir en las bases de los servicios o editar código, unidades o `.env` |
| Activar versiones de configuración dentro del sobre de cada parámetro | Superar un techo del host (G-16) ni abrir la API de pago (G-01) |
| Ejecutar intervenciones del catálogo con un argv fijo | Ejecutar comandos libres o interpolar en un shell |
| Crear borradores de prompts y pedir su evaluación | Activar un prompt sin solicitud de cambio, puerta de evaluación (PV-13) y 2.ª persona |
| Marcar activos en cuarentena (lápida reversible) | Borrar contenido de una versión referenciada por feedback o auditoría |
| Mostrar si un secreto está configurado | Leer, mostrar o registrar el valor de un secreto |

<a id="arquitectura-panel"></a>
## 2.2 Arquitectura

```text
                     navegador ── TLS (Let's Encrypt) · cookie de sesión · X-CSRF-Token
                         │
            nginx · vhost panel.2-25-233-186.sslip.io · límite 10 r/s · CSP estricta
                         │ 127.0.0.1:8750
 ┌───────────────────────┴──────────────────────────────── cr-panel (usuario de sistema crpanel) ─┐
 │  API /api/v1 (OpenAPI 3.1.1) · UI renderizada en servidor (Jinja2 + htmx) · SSE /events/stream │
 │  Ejecutor de intervenciones (lista blanca de argv) · Calculador de alertas y SLO (cada 60 s)   │
 │  panel.sqlite (WAL): cuentas · sesiones · config_versions · change_requests · feedback ·       │
 │                      interventions · alerts · evaluations · audit_events · assets (catálogo)    │
 └──┬──────────────┬───────────────┬───────────────────┬─────────────────────────┬────────────────┘
    │ solo lectura │ solo lectura  │ HTTP local        │ escritura acotada       │ polkit
    ▼              ▼               ▼                   ▼                         ▼
 state.sqlite   bridge/        Jaeger API v3      config/active.json          systemctl start de
 transcripts/   state.sqlite   VictoriaMetrics    panel-requests.json         cryptoreport-*.service
 analysis/      status.json    VictoriaLogs       quarantine.json             y stop/start de timers
                                                  panel-recovery-requests.json
```

**Límites de componentes:**

| Componente | Es dueño de | Lee | Escribe | Nunca |
|---|---|---|---|---|
| `cr-panel` | `panel.sqlite`, configuración versionada, auditoría | Estado de los servicios, telemetría | Solo los archivos de control de la columna anterior | Bases de los servicios, `.env`, unidades |
| `cr-extractor` | `state.sqlite`, transcripciones | `config/active.json`, `panel-requests.json`, `panel-recovery-requests.json`, `quarantine.json` | Lo de hoy, más el libro de ejecuciones | Configuración del panel |
| `cr-bridge` | `bridge/state.sqlite`, importaciones | `config/active.json`, `panel-requests.json` | Lo de hoy, más el historial de transiciones | Configuración del panel |
| `cr-build-data` y `site.py` | Datos publicados | `quarantine.json` | `data/`, `data.json` | — |
| Pila de telemetría | Trazas, métricas y logs | OTLP y journald | Sus volúmenes | Nada del pipeline |

**Tecnología.** Es Python 3.14 como el resto del sistema:

- **Servidor:** Starlette 1.8 sobre Uvicorn 0.54 (ASGI, ligero, sin ORM).
- **Base de datos:** `sqlite3` de la biblioteca estándar en modo WAL. Trae FTS5 (SQLite 3.46.1 en el host).
- **Interfaz:** Jinja2 y htmx, sin una SPA que haya que compilar. Tailwind compilado en local, como el sitio actual.
- **Contraseñas:** `argon2-cffi` 25.1.

Grafana se descartó como interfaz: los flujos HITL y la auditoría necesitan pantallas propias, y no cabe en el presupuesto de memoria (P10).

<a id="plano-control"></a>
## 2.3 Plano de control: cómo llega un cambio a los servicios

1. Cada cambio aprobado crea una **versión de configuración inmutable** ([`config-version`](contratos/esquemas/config-version.schema.json)). Se guarda en `/var/lib/cryptoreport-panel/config/v<N>.json` y se publica con un enlace simbólico atómico, `active.json`. El `digest` es el SHA-256 del JSON canónico.
2. Los servicios son *oneshot*: leen `active.json` **al empezar cada ciclo** con un ayudante de 30 líneas (`crconfig.load()`, entregable C-07) y registran `cr.config.version` en el span raíz y en el libro de ejecuciones.
3. Precedencia, de mayor a menor:
   1. **techo del host** (unidad systemd o `.env`), que recorta;
   2. **versión activa**, para parámetros `active` o `planned` ya migrados;
   3. **valor por defecto del código**.

   Un recorte genera `cr.guardrail.decision = clamp` con `cr.guardrail.id = G-16`.
4. Si `active.json` falta o no se puede leer, el servicio usa el entorno y los valores por defecto (el perfil sin pago) y deja un aviso. Un fallo del panel nunca abre un gasto.
5. Modos de aplicación:

| Modo | Cuándo surte efecto | Ejemplos |
|---|---|---|
| `immediate` | En el panel, al aplicar | Presupuesto mensual, umbrales de alerta |
| `next_cycle` | En el siguiente ciclo (≤ 15 min, o al momento con `run_extractor_now`) | Ventana de descubrimiento, orden de proveedores, intentos |
| `restart` | Requiere recargar systemd; lo hace una persona en el host | Calendario de timers, generación de pago |
| `release` | Versión nueva con evaluación y despliegue | Prompt, esquema, instrucciones de Scheduled, constantes de código |

<a id="catalogo-parametros"></a>
## 2.4 Catálogo de parámetros

Generado desde [`registros/parametros.json`](contratos/registros/parametros.json). Cada fila cita el archivo de origen y el validador comprueba en cada CI que el texto de anclaje sigue existiendo (PV-06). Los estados significan:

- `active`: el panel ya lo puede proponer.
- `planned`: hoy es una constante del código y la Fase 2 la lleva a configuración.
- `read_only`: solo se muestra.
- `not_applicable`: el código no lo usa, con el motivo anotado.

<!-- generado:inicio parametros -->
**Prompts e instrucciones**

| Parámetro | Vigente | Sobre del panel | Techo del host | Aplicación | Riesgo | Rol | Estado | Origen |
|---|---|---|---|---|---|---|---|---|
| `analysis.system_prompt` | `1.0.0` · `082e5acbefbb…` | — | — | `release` | `critical` | `admin` + 2.ª persona | `active` | `narrative-analysis.system.md` |
| `analysis.output_schema` | hash canónico `7b88e0b75f8c…` | — | — | `release` | `critical` | `admin` + 2.ª persona | `active` | `narrative-analysis.schema.json` |
| `scheduled.instructions_revision` | `1.3` | — | — | `release` | `high` | `admin` + 2.ª persona | `active` | `manifest.json` |

**Modelos**

| Parámetro | Vigente | Sobre del panel | Techo del host | Aplicación | Riesgo | Rol | Estado | Origen |
|---|---|---|---|---|---|---|---|---|
| `analysis.provider` | `openai` | — | — | `next_cycle` | `high` | `admin` + 2.ª persona | `active` | `CRA_PROVIDER` |
| `analysis.model` | `gpt-6.1-sol` | — | — | `next_cycle` | `high` | `admin` + 2.ª persona | `active` | `CRA_MODEL` |
| `analysis.reasoning_effort` | `high` | — | — | `next_cycle` | `medium` | `operator` | `active` | `CRA_EFFORT` |
| `analysis.temperature` | — | 0–2 | — | `release` | `medium` | `admin` | `not_applicable` | `openai_client.py` |
| `analysis.max_output_tokens` | 64 000 tokens | 16 000–64 000 | 64 000 | `next_cycle` | `medium` | `operator` | `active` | `CRA_MAX_TOKENS` |
| `scheduled.model_declared` | `gpt-6.1-sol` | — | — | `release` | `medium` | `admin` | `read_only` | `manifest.json` |

**Enrutamiento**

| Parámetro | Vigente | Sobre del panel | Techo del host | Aplicación | Riesgo | Rol | Estado | Origen |
|---|---|---|---|---|---|---|---|---|
| `analysis.server_side_fallbacks` | sí | — | — | `next_cycle` | `medium` | `operator` | `active` | `CRA_FALLBACKS` |
| `analysis.include_shorts` | sí | — | — | `next_cycle` | `low` | `operator` | `active` | `CRA_INCLUDE_SHORTS` |
| `extractor.providers_order` | `scrapertech`, `ytdlp`, `supadata` | ≤ 3 elementos | — | `next_cycle` | `high` | `operator` + 2.ª persona | `active` | `CR_PROVIDERS` |
| `extractor.include_shorts` | sí | — | — | `next_cycle` | `low` | `operator` | `active` | `CR_INCLUDE_SHORTS` |
| `extractor.lookback_hours` | 48 h | 6–168 | — | `next_cycle` | `medium` | `operator` | `active` | `CR_LOOKBACK_HOURS` |
| `bridge.lookback_hours` | 48 h | 6–168 | — | `next_cycle` | `medium` | `operator` | `planned` | `core.py` |

**Herramientas**

| Parámetro | Vigente | Sobre del panel | Techo del host | Aplicación | Riesgo | Rol | Estado | Origen |
|---|---|---|---|---|---|---|---|---|
| `providers.scrapertech.timeout_s` | 75 s | 20–120 | — | `next_cycle` | `low` | `operator` | `planned` | `providers.py` |
| `providers.scrapertech.tries` | 2 | 1–3 | — | `next_cycle` | `medium` | `operator` | `planned` | `providers.py` |
| `providers.ytdlp.proxy` | (vacío) | — | — | `next_cycle` | `medium` | `admin` | `active` | `CR_YTDLP_PROXY` |

**Guardas**

| Parámetro | Vigente | Sobre del panel | Techo del host | Aplicación | Riesgo | Rol | Estado | Origen |
|---|---|---|---|---|---|---|---|---|
| `analysis.allow_api` | no | — | `false` | `restart` | `critical` | `admin` + 2.ª persona | `read_only` | `CRA_ALLOW_API_ANALYSIS` |
| `providers.supadata.generate` | no | — | `false` | `restart` | `critical` | `admin` + 2.ª persona | `read_only` | `CR_SUPADATA_GENERATE` |
| `bridge.max_file_bytes` | 0 GiB | 500 000–5 000 000 | — | `release` | `medium` | `admin` | `read_only` | `MAX_BYTES` |

**Reintentos y fallback**

| Parámetro | Vigente | Sobre del panel | Techo del host | Aplicación | Riesgo | Rol | Estado | Origen |
|---|---|---|---|---|---|---|---|---|
| `scheduled.jobs_per_run` | 2 trabajos | 1–2 | — | `release` | `high` | `admin` + 2.ª persona | `active` | `scheduled-instructions.md` |
| `extractor.give_up_hours` | 72 h | 12–168 | — | `next_cycle` | `low` | `operator` | `active` | `CR_GIVE_UP_HOURS` |
| `extractor.max_attempts` | 8 | 1–12 | — | `next_cycle` | `low` | `operator` | `active` | `CR_MAX_ATTEMPTS` |
| `extractor.max_videos_per_run` | 20 | 1–50 | — | `next_cycle` | `low` | `operator` | `active` | `CR_MAX_VIDEOS_PER_RUN` |
| `extractor.backoff_base_s` | 900 s | 300–3 600 | — | `next_cycle` | `low` | `operator` | `planned` | `BACKOFF_BASE` |
| `extractor.backoff_cap_s` | 21 600 s | 3 600–43 200 | — | `next_cycle` | `low` | `operator` | `planned` | `BACKOFF_CAP` |
| `extractor.provider_cooldown_s` | 1 800 s | 600–7 200 | — | `next_cycle` | `medium` | `operator` | `planned` | `pipeline.py` |
| `extractor.provider_failures_to_cooldown` | 3 | 1–6 | — | `next_cycle` | `medium` | `operator` | `planned` | `pipeline.py` |
| `extractor.rss_retry_pauses_s` | 2, 4, 8, 15, 30 s | ≤ 6 elementos | — | `next_cycle` | `low` | `operator` | `planned` | `RETRY_PAUSES_S` |
| `extractor.recovery_per_cycle` | 2 | 0–5 | — | `next_cycle` | `medium` | `operator` | `planned` | `pipeline.py` |
| `extractor.recovery_attempts_per_version` | 2 | 1–3 | — | `next_cycle` | `medium` | `operator` | `planned` | `pipeline.py` |
| `extractor.recovery_wait_s` | 21 600 s | 3 600–86 400 | — | `next_cycle` | `low` | `operator` | `planned` | `pipeline.py` |
| `extractor.repair_per_run` | 3 | 0–10 | — | `next_cycle` | `low` | `operator` | `planned` | `REPAIR_PER_RUN` |
| `providers.supadata.generate_after_hours` | 6 h | 2–48 | — | `next_cycle` | `medium` | `operator` | `active` | `CR_SUPADATA_GENERATE_AFTER_HOURS` |
| `bridge.drive_retries` | 1 | 0–3 | — | `next_cycle` | `low` | `operator` | `planned` | `drive.py` |
| `bridge.drive_process_timeout_s` | 90 s | 30–300 | — | `next_cycle` | `low` | `operator` | `planned` | `drive.py` |

**Presupuestos**

| Parámetro | Vigente | Sobre del panel | Techo del host | Aplicación | Riesgo | Rol | Estado | Origen |
|---|---|---|---|---|---|---|---|---|
| `providers.scrapertech.monthly_quota` | 1 000 peticiones | 100–1 000 | 1 000 | `next_cycle` | `high` | `admin` + 2.ª persona | `active` | `CR_SCRAPERTECH_MONTHLY_QUOTA` |
| `providers.supadata.monthly_credits` | 20 créditos | 0–20 | 20 | `next_cycle` | `high` | `admin` + 2.ª persona | `active` | `CR_SUPADATA_MONTHLY_CREDITS` |
| `providers.supadata.max_generate_attempts` | 2 | 0–2 | — | `next_cycle` | `high` | `admin` + 2.ª persona | `planned` | `MAX_GENERATE_ATTEMPTS` |
| `budget.model_api_monthly_usd` | 0 USD | 0–50 | 0 | `immediate` | `critical` | `admin` + 2.ª persona | `planned` | `config.py` |

**Puertas de calidad**

| Parámetro | Vigente | Sobre del panel | Techo del host | Aplicación | Riesgo | Rol | Estado | Origen |
|---|---|---|---|---|---|---|---|---|
| `extractor.language` | `es` | — | — | `release` | `critical` | `admin` + 2.ª persona | `read_only` | `CR_LANGUAGE` |
| `quality.coverage_warning` | 0,85 | 0,5–0,99 | — | `release` | `medium` | `admin` | `planned` | `pipeline.py` |
| `validator.time_tolerance_s` | 0,05 s | — | — | `release` | `critical` | `admin` + 2.ª persona | `read_only` | `TIME_TOLERANCE_S` |

**Calendario**

| Parámetro | Vigente | Sobre del panel | Techo del host | Aplicación | Riesgo | Rol | Estado | Origen |
|---|---|---|---|---|---|---|---|---|
| `scheduled.cadence` | `every_6_hours` | — | — | `release` | `medium` | `admin` | `read_only` | `manifest.json` |
| `scheduling.extractor_timer` | `*:0/15` | — | — | `restart` | `medium` | `admin` | `read_only` | `cryptoreport-transcripts.timer` |
| `scheduling.bridge_timer` | `*-*-* *:03,18,33,48:00` | — | — | `restart` | `medium` | `admin` | `read_only` | `cryptoreport-bridge.timer` |

**Motor de tono**

| Parámetro | Vigente | Sobre del panel | Techo del host | Aplicación | Riesgo | Rol | Estado | Origen |
|---|---|---|---|---|---|---|---|---|
| `tone.min_mass` | 0,75 | 0,25–3 | — | `release` | `medium` | `operator` | `planned` | `tono.py` |
| `tone.label_threshold` | 0,3 | 0,1–0,6 | — | `release` | `medium` | `operator` | `planned` | `tono.py` |
| `tone.strength_cutoffs` | 1,6, 3,5 | ≤ 2 elementos | — | `release` | `low` | `operator` | `planned` | `tono.py` |
| `tone.video_min_mass` | 1,5 | 0,5–5 | — | `release` | `low` | `operator` | `planned` | `build_data.py` |

**Avisos**

| Parámetro | Vigente | Sobre del panel | Techo del host | Aplicación | Riesgo | Rol | Estado | Origen |
|---|---|---|---|---|---|---|---|---|
| `alerts.telegram_configured` | no | — | — | `restart` | `medium` | `admin` | `read_only` | `CR_TELEGRAM_BOT_TOKEN` |
| `alerts.notify_success` | sí | — | — | `next_cycle` | `low` | `operator` | `active` | `CR_NOTIFY_SUCCESS` |
<!-- generado:fin parametros -->

<a id="prompts"></a>
## 2.5 System prompts e instrucciones del agente

- **Son versiones, no ajustes en caliente.** El prompt entra en el `job_id`: `prompt_sha256` y `schema_sha256` forman parte de los metadatos con hash. Cambiarlo reemplaza (`superseded`) todos los trabajos en cola y obliga a reanalizar. Antes de aprobar, la vista previa del cambio dice cuántos trabajos quedarían invalidados.
- **Flujo:**
  1. Se crea un borrador (`POST /prompts/{name}/versions`, Fase 3) o se elige una versión que ya está en el repositorio.
  2. Puerta de evaluación (PV-13) sobre el conjunto dorado: los 2 análisis reales de OpenAI y 5 de Scheduled con sus transcripciones. Validador al 100 %, sin regresión del autorater (caída < 0,05 en `cr.autorater.overall`) y revisión humana.
  3. Solicitud de cambio de `analysis.system_prompt` con riesgo *critical*: `admin` más una 2.ª persona.
  4. Al aplicarla, el puente sube el prompt y el esquema nuevos a la carpeta de control de Drive. La guarda G-07 impide que el agente trabaje con hashes viejos.
- **Instrucciones de Scheduled.** El panel genera el texto y su SHA-256, pero pegarlo en ChatGPT es un paso manual: el servidor no controla esa interfaz. El cambio se da por aplicado cuando llega un comprobante que declara la revisión nueva. Las instrucciones 1.4 añaden `instructions_revision`, `modo` y `pasos` al comprobante.

<a id="modelos-enrutamiento"></a>
## 2.6 Modelos, temperatura y enrutamiento

**Modelos.** El análisis por API admite los modelos de la tabla `PRICES` (`cranalysis/client.py`): un modelo sin precio no se puede presupuestar (G-06). Con la guarda G-01 cerrada, el análisis efectivo lo hace Scheduled, con GPT-6.1 Sol declarado y no verificable.

**Temperatura.** El código no envía `temperature`. Las llamadas usan razonamiento (`reasoning.effort` en OpenAI y `output_config.effort` con pensamiento adaptativo en Claude) y el control equivalente es `analysis.reasoning_effort`. El catálogo lo declara `not_applicable` con su motivo. Activarla exige un cambio de código revisado y comprobar que el proveedor la admite junto con el razonamiento.

**Enrutamiento, fallback y reintentos** (generado desde [`registros/enrutamiento.json`](contratos/registros/enrutamiento.json)):

<!-- generado:inicio enrutamiento -->
**`discovery.channel`** (cr-extractor, activa). Descubrir videos nuevos de cada canal de channels.json.

1. `youtube_rss` · `feed` — pasa al siguiente con: `error`
2. `youtube_pages` · `channel_pages` — se salta si: El RSS respondió en alguno de sus 6 intentos

*Parada:* La primera fuente que devuelve entradas; si fallan ambas, el canal queda en error en runs.feeds y cuenta para el aviso de 3 ciclos. *Reintentos:* 6 intentos por llamada, automáticos. Pausas de 2, 4, 8, 15 y 30 s dentro del ciclo.

**`transcripts.captions`** (cr-extractor, activa). Obtener la pista original en español de cada video elegible.

1. `scrapertech` · `captions` — pasa al siguiente con: `ok_invalid_quality`, `pending`, `unavailable`, `error`, `auth`, `quota`, `skipped`
2. `ytdlp` · `captions` — pasa al siguiente con: `ok_invalid_quality`, `blocked`, `error`, `skipped`
3. `supadata` · `captions` · modo `native` — se salta si: Otro proveedor devolvió unavailable; Otro proveedor devolvió pending y el video tiene menos de 2 h; Ya hay 2 o más filas de Supadata para el video; Créditos del mes agotados — pasa al siguiente con: `ok_invalid_quality`, `error`, `quota`

*Parada:* El primer resultado ok que además pasa candidate_quality (assess) gana; el resto de la cadena no se llama. *Reintentos:* 2 intentos por llamada, backoff base 900 s, backoff máximo 21 600 s, 8 intentos máximos, abandono a las 72 h, automáticos. Si todos los proveedores están caídos el resultado es skipped y el intento no cuenta. *Cooldown:* 1 800 s tras 3 errores seguidos o con `auth`, `quota`. *Guardas:* G-02, G-03, G-04, G-05, G-11.

**`transcripts.generate`** (cr-extractor, apagada por G-02). Transcripción por IA de pago cuando no hay pista (Supadata generate).

1. `supadata` · `generate` — se salta si: Video con menos de 6 h; Duración desconocida; Más de una pista de audio; Coste mayor que el saldo del mes; 2 intentos pagados ya hechos; kv nogen:&lt;video_id&gt;

*Parada:* Resultado en es: se guarda con track_kind ai; en otro idioma: no_captions. *Reintentos:* 2 intentos máximos, automáticos. Un trabajo RUNNING se consulta gratis en el siguiente ciclo. *Guardas:* G-02, G-04, G-05.

**`analysis.scheduled`** (cr-scheduled-agent, activa). Analizar trabajos de la cola con el agente ChatGPT Scheduled vía Drive, sin inferencia por API.

1. `rclone_drive` · `write` — pasa al siguiente con: `drive_quota`, `drive_auth`
2. `chatgpt_scheduled` · `analysis` · `gpt-6.1-sol`
3. `rclone_drive` · `read`

*Parada:* Resultado válido importado (imported) o estado de revisión (rejected, conflict, blocked). *Reintentos:* solo manuales. Un intento fallido nunca se reintenta solo: crbridge retry --video-id --reason autoriza uno nuevo. *Guardas:* G-07, G-08, G-09, G-10, G-14.

**`analysis.api`** (cr-analysis, apagada por G-01). Analizar por API de pago (OpenAI por defecto, Claude como alternativa).

1. `openai` · `inference` · `gpt-6.1-sol` — pasa al siguiente con: `incomplete`, `refusal`
2. `anthropic` · `inference` · `claude-opus-5-5` — se salta si: CRA_PROVIDER distinto de anthropic: hoy no hay cruce automático entre proveedores

*Parada:* Un análisis que pasa el validador se guarda como ok; si no, como rechazado. Truncado, rechazo o JSON ilegible no se guardan. *Reintentos:* 3 intentos por llamada, solo manuales. SDK de OpenAI con max_retries=2 y timeout de 900 s; con anthropic, fallbacks del lado del servidor si CRA_FALLBACKS=true. *Guardas:* G-01, G-06, G-10.

**`drive.transport`** (cr-bridge, activa). Todas las operaciones de Drive del puente.

1. `rclone_drive` — pasa al siguiente con: `drive_transport`

*Parada:* drive_quota o drive_auth detienen las subidas del ciclo; el siguiente timer reintenta. *Reintentos:* 2 intentos por llamada, automáticos. --retries 1, --low-level-retries 1, contimeout 10 s, timeout 30 s, proceso 90 s. *Guardas:* G-08.
<!-- generado:fin enrutamiento -->

**Pruebas por canal.** `applies_to.channels` permite aplicar una cadena a un solo canal: por ejemplo, probar un proveedor nuevo en `healthy` antes de extenderlo. El panel lo expone como una solicitud de cambio más.

<a id="registro-herramientas"></a>
## 2.7 Registro dinámico de herramientas

El descubrimiento se basa en datos: los servicios leen [`registros/herramientas.json`](contratos/registros/herramientas.json) (desde la Fase 2, servido por el panel) al empezar cada ciclo. Una herramienta nueva sigue este ciclo de vida, y cada paso es una solicitud de cambio:

```text
proposed ──► sandbox ──► shadow ──► active ──► retired
             (solo       (se llama,  │  ▲
              fixtures    el resultado▼  │
              offline)    se descarta) degraded_known ◄─ bloqueo conocido (p. ej. yt-dlp)
                          ↳ DQ-T-13 compara su salida con la activa
```

Su salud sale de `kv health:<proveedor>`, de la tabla `attempts` y de `cr.provider.call.duration`.

<!-- generado:inicio herramientas -->
| Herramienta | Tipo | Ciclo de vida | Capacidades | Coste | Límites | Fuente de salud | Problemas conocidos |
|---|---|---|---|---|---|---|---|
| `youtube_rss` | `discovery_source` | `active` | `feed` | gratis | timeout 20 s, 6 intentos | runs.feeds y kv feed_fails:&lt;canal&gt; | 52 % de 404/500 en peticiones sueltas (8 y 9 de octubre) y una caída de horas el 10 de octubre. |
| `youtube_pages` | `discovery_source` | `active` | `channel_pages`, `shorts_probe` | gratis | timeout 25 s | runs.feeds (marca «vía páginas del canal») | Fechas relativas aproximadas; hay que pedir hl=es para no recibir títulos traducidos. |
| `scrapertech` | `transcript_provider` | `active` | `captions`, `metadata` | por petición (`scrapertech_requests`) | timeout 75 s, 2 intentos, cuota 1 000 al mes | kv health:scrapertech y tabla attempts | Errores dentro de HTTP 200; ≈30 % de data=null que se resuelve al repetir. video.php omite la duración justo tras publicar; la cubre repair_durations. |
| `ytdlp` | `transcript_provider` | `degraded_known` | `captions` | gratis | timeout 120 s | tabla attempts (outcome blocked) | Bot-check de YouTube para la IP del VPS: 9 de 9 intentos blocked. Funcionaría con CR_YTDLP_PROXY (túnel por tablet) o cookies. |
| `supadata` | `transcript_provider` | `active` | `captions`, `generate` | por crédito (`supadata_credits`) | timeout 150 s, cuota 20 al mes | kv health:supadata, attempts (reserved) y /me | generate transcribe la pista doblada al árabe: solo se permite con una única pista de audio. |
| `rclone_drive` | `transport` | `active` | `list`, `read`, `write` | gratis | timeout 90 s, 2 intentos | kv last_errors del puente (drive_quota, drive_auth, drive_transport) | El cliente OAuth compartido agotó su cuota el 13 y el 14 de octubre (drive_quota). |
| `telegram` | `notifier` | `disabled` | `notify` | gratis | — | líneas [aviso] del journal | Sin bot ni chat elegidos: los avisos solo llegan al journal. |
| `openai` | `model_provider` | `disabled` | `inference`, `analysis` | por token (`model_api_usd`) | timeout 900 s, 3 intentos | meta.validation y meta.usage de cada análisis | Proveedor por defecto, pero openai no figura en requirements.txt (H-06). Guarda G-01 cerrada: desactivado por configuración. |
| `anthropic` | `model_provider` | `disabled` | `inference`, `analysis` | por token (`model_api_usd`) | — | meta.validation y meta.usage de cada análisis | Alternativa con CRA_PROVIDER=anthropic; guarda G-01 cerrada. |
| `chatgpt_scheduled` | `agent` | `active` | `analysis` | suscripción | 1 intentos | comprobantes en la carpeta ejecuciones y estados de jobs | Modelo no verificable (model: null). Una ejecución intentó 22 trabajos el 14-oct (AP-04). remaining_count vacío en 7 de 9 comprobantes. |
<!-- generado:fin herramientas -->

<a id="guardrails"></a>
## 2.8 Políticas de guardrails activas

Cada guarda declara dónde se aplica, cómo falla y qué prueba la demuestra. Las que fallan cerradas bloquean ante la duda (pago y publicación); las que fallan abiertas dejan pasar (telemetría y vigilancia del agente externo). Cambiar una guarda en modo *enforce* exige `admin` y una 2.ª persona.

<!-- generado:inicio guardrails -->
| ID | Guarda | Dónde se aplica | Modo | Ante la duda | Pruebas (o hueco) | Cambiarla exige |
|---|---|---|---|---|---|---|
| **G-01** | API de modelos cerrada | código · `services/analysis/cranalysis/__main__.py` | en vigor | bloquea | `test_disabled_run_cannot_create_client` | `admin` + 2.ª persona; Presupuesto budget.model_api_monthly_usd &gt; 0 aprobado; Cambio en el entorno del host, fuera del panel; Pasar la puerta de evaluación del prompt vigente |
| **G-02** | Generación de pago desactivada | systemd · `services/transcripts/ops/cryptoreport-transcripts-no-paid.conf` | en vigor | bloquea | `test_dubbed_video_is_never_generated`, `test_budget_blocks_generation`, `test_failed_generation_is_paid_at_most_twice` | `admin` + 2.ª persona; Cambio del drop-in no-paid.conf en el host; Presupuesto de créditos aprobado |
| **G-03** | Proveedores de pago al final de la cadena | panel | propuesta (fase 2) | bloquea | — | `admin` + 2.ª persona; Justificación de coste por escrito |
| **G-04** | Reserva de crédito antes de pagar | código · `services/transcripts/crtranscripts/pipeline.py` | en vigor | bloquea | `test_uncertain_native_failure_keeps_credit_reservation` | `admin` + 2.ª persona; Cambio de código revisado |
| **G-05** | Tope mensual de Supadata | systemd · `services/transcripts/ops/cryptoreport-transcripts-no-paid.conf` | en vigor | bloquea | `test_monthly_cap_stops_native_calls` | `admin` + 2.ª persona; Subir el techo en el host; el panel solo puede bajarlo |
| **G-06** | Modelo con precio conocido | panel | propuesta (fase 2) | bloquea | — | `admin` + 2.ª persona; Añadir el precio a PRICES en una versión revisada |
| **G-07** | Hash de control de prompt y esquema | código · `services/bridge/crbridge/core.py` | en vigor | bloquea | `test_remote_control_hash_mismatch_stops_upload` | `admin` + 2.ª persona; Publicar prompt y esquema nuevos en control junto con la release |
| **G-08** | Escrituras de Drive solo de creación | código · `services/bridge/crbridge/drive.py` | en vigor | bloquea | `test_upload_response_lost_reconciles_without_duplicate`, `test_unknown_upload_outcome_without_file_requires_review` | `admin` + 2.ª persona; Cambio de código revisado |
| **G-09** | Importación sin sobrescritura | código · `services/bridge/crbridge/core.py` | en vigor | bloquea | `test_invalid_result_never_replaces_valid_existing` | `admin` + 2.ª persona; Cambio de código revisado |
| **G-10** | Validador estricto de análisis | código · `services/analysis/cranalysis/validate.py` | en vigor | bloquea | `test_invented_quote`, `test_dangling_reference`, `test_source_not_provided_in_input`, `test_hallucinated_quote_rejected`, `test_forged_exact_range_rejected` | `admin` + 2.ª persona; Cambio de contrato con el agente y nueva revisión de instrucciones |
| **G-11** | Puerta de calidad compartida | código · `services/transcripts/crtranscripts/quality.py` | en vigor | bloquea | `test_empty_or_wrong_language_cannot_publish`, `test_missing_last_part_requires_recovery`, `test_empty_transcript_cannot_enter_queue` | `admin` + 2.ª persona; Cambio de código revisado y re-evaluación de las transcripciones existentes |
| **G-12** | Publicación solo de análisis coincidentes | código · `services/transcripts/crtranscripts/site.py` | en vigor | bloquea | `test_only_valid_analyses_are_published_and_stale_ones_removed`, `test_changed_transcript_hides_stale_analysis` | `admin` + 2.ª persona; Cambio de código revisado |
| **G-13** | Cerrojo compartido run.lock | código · `services/bridge/crbridge/__main__.py` | en vigor | bloquea | Ninguna prueba cubre el cerrojo ni la salida busy; se añade en la Fase 0 (PV-10). | `admin` + 2.ª persona; Cambio de código revisado |
| **G-14** | Límite de trabajos por ejecución del agente | instrucciones · `docs/automatizacion-drive/scheduled-instructions.md` | vigilada | deja pasar | El puente ignora run_id, errors y remaining_count de los comprobantes; la ejecución de 22 trabajos del 14-oct pasó sin aviso. | `admin` + 2.ª persona; Nueva revisión de instrucciones pegada en ChatGPT |
| **G-15** | Captura de contenido desactivada | Collector | propuesta (fase 1) | bloquea | — | `admin` + 2.ª persona; Justificación de depuración con fecha de caducidad |
| **G-16** | Techos del host | panel | propuesta (fase 2) | bloquea | — | `admin` + 2.ª persona; Cambio en el host, fuera del panel |
| **G-17** | Doble aprobación | panel | propuesta (fase 2) | bloquea | — | `admin` + 2.ª persona; Cambio del contrato del panel |
| **G-18** | Sin secretos en repositorio ni telemetría | CI · `docs/observabilidad/herramientas/validate_contracts.py` | en vigor | bloquea | `test_secret_scan_flags_keys` | `admin` + 2.ª persona; Cambio revisado del validador |
<!-- generado:fin guardrails -->

<a id="fallback-reintentos"></a>
## 2.9 Límites automáticos de fallback y reintentos

| Nivel | Límite | Valor vigente | Parámetro o ancla |
|---|---|---|---|
| RSS | Intentos dentro del ciclo | 6 (pausas de 2, 4, 8, 15 y 30 s) y después páginas del canal | `extractor.rss_retry_pauses_s` |
| Llamada a Scraper.Tech | Intentos por llamada | 2, con 3 s de pausa y 75 s de timeout | `providers.scrapertech.tries` |
| Video | Backoff | 15 min × 2ⁿ, con un máximo de 6 h | `extractor.backoff_base_s`, `extractor.backoff_cap_s` |
| Video | Intentos | 8, y después `failed` | `extractor.max_attempts` |
| Video sin pista | Abandono | 72 h, y después `no_captions` o `unavailable` | `extractor.give_up_hours` |
| Proveedor | Cooldown | 30 min tras `auth`, `quota` o 3 errores seguidos | `extractor.provider_cooldown_s` |
| Supadata | Gasto | 2 consultas nativas por video y 20 créditos al mes | `providers.supadata.monthly_credits` |
| Generación de pago | Intentos | 2 por video (desactivada) | `providers.supadata.max_generate_attempts` |
| Recuperación | Por ciclo y por versión | 2 por ciclo, 2 por versión y 6 h de espera | `extractor.recovery_*` |
| rclone | Reintentos | 1 (90 s por proceso); `drive_quota` o `drive_auth` detienen las subidas | `bridge.drive_retries` |
| Agente Scheduled | Reintentos | Ninguno automático: solo `retry_job` con motivo | G-14, `scheduled.jobs_per_run` |
| API de OpenAI | Reintentos del SDK | `max_retries=2`, timeout de 900 s | `cranalysis/__main__.py` |
| Claude | Fallback | Fallback del servidor si `CRA_FALLBACKS=true` | `analysis.server_side_fallbacks` |

<a id="flujo-cambio"></a>
## 2.10 Flujo de un cambio

```text
 draft ──validate──► validating ──► validation_failed ──(editar)──► draft
                         │
                         ▼
                  pending_approval ──reject──► rejected
                         │ approve (otra persona; 0, 1 o 2 aprobaciones según el riesgo)
                         ▼
                      approved ──apply (If-Match = versión activa)──► applied ──rollback──► rolled_back
                                                                       (crea vN+1)        (crea solicitud
                                                                                            que restaura vK)
```

- **Validaciones automáticas** (`validations[]`):
  - `schema`: tipo y enum del catálogo;
  - `bounds`: el sobre;
  - `host_ceiling`: recorte con G-16;
  - `guardrails`: G-03 y G-06;
  - `offline_tests`: las suites del CI con el valor nuevo, cuando aplica;
  - `eval_gate`: PV-13, solo para prompts;
  - `cost_estimate`: proyección de presupuesto.
- **Aprobaciones:**
  - riesgo `low` y `medium`: 0;
  - `high`: 1;
  - `critical`: 1 de un `admin`.

  Quien propone nunca aprueba (G-17); el panel responde 409 y el validador lo comprueba en los ejemplos.
- **Concurrencia:** `If-Match: "v<N>"`. Si la versión activa cambió desde la propuesta, la respuesta es 412 y hay que revalidar.
- **Reversión:** cualquier versión anterior se restaura con `POST /config/versions/{n}/rollback`, que crea una solicitud ya validada. Revertir a la versión anterior inmediata es de riesgo `low`.
- **Reversión automática:** si en las 2 h siguientes a aplicar un cambio de enrutamiento SH-08 pasa a crítico, el panel propone la reversión y avisa. No la aplica sin una persona.

<a id="api-panel"></a>
## 2.11 API del panel

Convenciones:

- **Base y formato:** prefijo `/api/v1`, JSON y errores RFC 9457 (`application/problem+json`, con `trace_id`).
- **Paginación:** por cursor opaco (`page.next_cursor`).
- **Cabeceras en mutaciones:** `Idempotency-Key` y `X-CSRF-Token`.
- **Concurrencia:** `ETag` e `If-Match` para la configuración.
- **Tiempo real:** SSE con reanudación por `Last-Event-ID`.

Cada operación declara `x-cr-min-role`, `x-cr-audit` y `x-cr-phase`; el validador (PV-03) lo exige.

<!-- generado:inicio api-resumen -->
| Método | Ruta (/api/v1) | Operación | Rol mínimo | Auditoría | Fase |
|---|---|---|---|---|---|
| GET | `/health` | `getHealth` | `viewer` | — | 2 |
| GET | `/pipeline-status` | `getPipelineStatus` | `viewer` | — | 2 |
| GET | `/thresholds` | `getThresholds` | `viewer` | — | 2 |
| GET | `/alerts` | `listAlerts` | `viewer` | — | 2 |
| POST | `/alerts/{alert_id}/acknowledge` | `acknowledgeAlert` | `operator` | `alert.acknowledge` | 2 |
| POST | `/alerts/{alert_id}/silence` | `silenceAlert` | `operator` | `alert.silence` | 2 |
| GET | `/metrics/{metric_name}/series` | `getMetricSeries` | `viewer` | — | 2 |
| GET | `/runs` | `listRuns` | `viewer` | — | 2 |
| GET | `/runs/{run_id}` | `getRun` | `viewer` | — | 2 |
| GET | `/runs/{run_id}/spans` | `getRunSpans` | `viewer` | — | 2 |
| GET | `/runs/{run_id}/logs` | `getRunLogs` | `viewer` | — | 2 |
| GET | `/jobs` | `listJobs` | `viewer` | — | 2 |
| GET | `/jobs/{job_id}` | `getJob` | `viewer` | — | 2 |
| GET | `/agents` | `listAgents` | `viewer` | — | 2 |
| GET | `/agents/{tool_id}/runs` | `listAgentRuns` | `viewer` | — | 2 |
| GET | `/evaluations` | `listEvaluations` | `viewer` | — | 2 |
| GET | `/evaluations/{evaluation_id}` | `getEvaluation` | `viewer` | — | 2 |
| GET | `/feedback` | `listFeedback` | `viewer` | — | 2 |
| POST | `/feedback` | `createFeedback` | `reviewer` | `feedback.create` | 2 |
| GET | `/intervention-types` | `listInterventionTypes` | `viewer` | — | 2 |
| GET | `/interventions` | `listInterventions` | `viewer` | — | 2 |
| POST | `/interventions` | `requestIntervention` | `reviewer` | `intervention.request` | 2 |
| GET | `/interventions/{intervention_id}` | `getIntervention` | `viewer` | — | 2 |
| POST | `/interventions/{intervention_id}/approve` | `approveIntervention` | `reviewer` | `intervention.approve` | 2 |
| POST | `/interventions/{intervention_id}/reject` | `rejectIntervention` | `reviewer` | `intervention.reject` | 2 |
| POST | `/interventions/{intervention_id}/cancel` | `cancelIntervention` | `reviewer` | `intervention.cancel` | 2 |
| POST | `/interventions/{intervention_id}/revert` | `revertIntervention` | `operator` | `intervention.revert` | 2 |
| GET | `/parameters` | `listParameters` | `viewer` | — | 2 |
| GET | `/config/active` | `getActiveConfig` | `viewer` | — | 2 |
| GET | `/config/versions` | `listConfigVersions` | `viewer` | — | 2 |
| GET | `/config/versions/{version}` | `getConfigVersion` | `viewer` | — | 2 |
| POST | `/config/versions/{version}/rollback` | `rollbackConfig` | `operator` | `config.rollback` | 2 |
| GET | `/config/change-requests` | `listConfigChanges` | `viewer` | — | 2 |
| POST | `/config/change-requests` | `proposeConfigChange` | `operator` | `config.propose` | 2 |
| GET | `/config/change-requests/{change_id}` | `getConfigChange` | `viewer` | — | 2 |
| POST | `/config/change-requests/{change_id}/validate` | `validateConfigChange` | `operator` | `config.validate` | 2 |
| POST | `/config/change-requests/{change_id}/approve` | `approveConfigChange` | `operator` | `config.approve` | 2 |
| POST | `/config/change-requests/{change_id}/reject` | `rejectConfigChange` | `operator` | `config.reject` | 2 |
| POST | `/config/change-requests/{change_id}/apply` | `applyConfigChange` | `operator` | `config.apply` | 2 |
| GET | `/prompts` | `listPrompts` | `viewer` | — | 2 |
| POST | `/prompts/{prompt_name}/versions` | `createPromptVersion` | `admin` | `asset.version_create` | 3 |
| GET | `/prompts/{prompt_name}/versions/{version}` | `getPromptVersion` | `reviewer` | — | 2 |
| GET | `/tools` | `listTools` | `viewer` | — | 2 |
| GET | `/tools/{tool_id}` | `getTool` | `viewer` | — | 2 |
| GET | `/routing` | `getRouting` | `viewer` | — | 2 |
| GET | `/guardrails` | `getGuardrails` | `viewer` | — | 2 |
| GET | `/library/assets` | `listAssets` | `viewer` | — | 2 |
| GET | `/library/assets/{asset_id}` | `getAsset` | `viewer` | — | 2 |
| GET | `/library/assets/{asset_id}/versions/{version}/content` | `getAssetContent` | `viewer` | `asset.export` | 2 |
| GET | `/library/assets/{asset_id}/diff` | `diffAssetVersions` | `viewer` | — | 2 |
| GET | `/library/assets/{asset_id}/quality` | `getAssetQuality` | `viewer` | — | 2 |
| POST | `/library/search` | `searchLibrary` | `viewer` | — | 2 |
| GET | `/library/vector-indexes` | `listVectorIndexes` | `viewer` | — | 2 |
| GET | `/library/vector-indexes/{index_id}` | `getVectorIndex` | `viewer` | — | 3 |
| GET | `/audit/events` | `listAuditEvents` | `auditor` | — | 2 |
| GET | `/audit/verify` | `verifyAuditChain` | `auditor` | `audit.verify` | 2 |
| POST | `/session` | `login` | público | `session.login` | 2 |
| DELETE | `/session` | `logout` | `viewer` | `session.logout` | 2 |
| GET | `/me` | `getMe` | `viewer` | — | 2 |
| GET | `/users` | `listUsers` | `admin` | — | 2 |
| POST | `/users` | `createUser` | `admin` | `user.create` | 2 |
| PATCH | `/users/{user_id}` | `updateUser` | `admin` | `user.role_change` | 2 |
| GET | `/events/stream` | `streamEvents` | `viewer` | — | 2 |
<!-- generado:fin api-resumen -->

<a id="seguridad-panel"></a>
## 2.12 Seguridad del panel

- **Identidad:**
  - cuentas locales con contraseña argon2id (mínimo 12 caracteres);
  - TOTP obligatorio para `operator` y `admin`; el esquema `User` lo exige;
  - sesión en cookie `HttpOnly`, `Secure` y `SameSite=Strict`, con 8 h de caducidad deslizante y 24 h absoluta;
  - inicio de sesión limitado a 5 intentos por minuto por IP y por cuenta.
- **Roles** (de menor a mayor alcance):
  - `viewer`: lee;
  - `reviewer`: feedback, reintentos e importaciones revisadas;
  - `operator`: intervenciones operativas y propuestas de configuración;
  - `admin`: cuentas, cambios críticos y kill switch;
  - `auditor`: solo lectura más la cadena de auditoría.

  La matriz completa está en la parte 4 (§4.8).
- **Tokens de servicio:** solo lectura (`viewer`), para un tablero de pared. Nunca mutan.
- **CSRF:** token sincronizado por sesión en `X-CSRF-Token`. GET nunca cambia estado; la búsqueda es POST de solo lectura y lo declara (`x-cr-read-only`).
- **Cabeceras:** CSP sin `unsafe-inline` (htmx sin `hx-on` en línea), `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex` y HSTS.
- **Secretos:** el panel no lee los `.env`. Para «configurada / no configurada» consulta si la variable existe en el entorno de la unidad (`systemctl show -p Environment` filtrado por nombre), nunca su valor.
- **Ejecución:** `cr-panel` corre como el usuario `crpanel`, sin shell, con `NoNewPrivileges`, `ProtectSystem=strict` y `ReadWritePaths` limitado a sus directorios y a los archivos de control. Para arrancar unidades usa una regla de polkit que solo permite `start` de los dos servicios y `start`/`stop` de los dos timers. No necesita sudo.

<a id="despliegue-panel"></a>
## 2.13 Despliegue en este servidor

| Pieza | Forma | Recursos |
|---|---|---|
| `cr-panel` | Unidad systemd `cryptoreport-panel.service` con venv propio, `MemoryMax=160M` y `Nice=5` | 1 proceso Uvicorn asíncrono; SQLite en un pool de hilos |
| Pila de telemetría | `docker compose` con Collector, Jaeger v2, VictoriaMetrics y VictoriaLogs, `mem_limit` por servicio y volúmenes en `/var/lib/cryptoreport-telemetry` | 832 MiB en total (128 + 256 + 256 + 192) |
| nginx | vhost `panel.2-25-233-186.sslip.io`, certificado de Let's Encrypt y `limit_req` 10 r/s | — |
| Copias | `sqlite3 .backup` diario de `panel.sqlite`, `state.sqlite` y `bridge/state.sqlite`, 14 días en local | < 50 MB |

El despliegue se entrega en las fases 1 y 2 (parte 5); este documento fija su forma y sus límites. Antes de desplegar, PV-09 confirma que la pila cabe en RS-01 a RS-05 sin quitar memoria a los proyectos que comparten el VPS.

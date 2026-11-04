# Relevo de las tareas autónomas de Codex (20 de octubre de 2026)

Estado vigente desde el 3 de noviembre: ambas programaciones usan exclusivamente Codex. Véase [relevo a solo Codex](relevo-solo-codex-2026-11-03.md). La configuración de Claude descrita abajo es histórica.

Codex deja de estar disponible en este entorno por un tiempo. Este documento
inventaria lo que ejecutaba de forma autónoma en CryptoReport, qué quedó bajo
el ejecutor de Claude, qué decidió el usuario y qué sigue bloqueado por
terceros. Todo lo afirmado aquí se comprobó en el servidor el 20-oct-2026 entre
las 20:30 y las 02:00 UTC; los mandos de verificación están al final.

## 1. Inventario de tareas autónomas y de mantenimiento

| Tarea | Cadencia | Qué hace | Ejecutor anterior | Estado al cierre del 20-oct |
| --- | --- | --- | --- | --- |
| `cryptoreport-transcripts.timer` | cada 15 min (`:00/:15/:30/:45`) | RSS y páginas de 7 canales, descarga de subtítulos, `build_data.py` y arranque del puente | servidor (sin modelo) | **funcionando con Supadata** tras subir su tope a 100 créditos; Scraper.Tech sigue devolviendo `Tariff ended` y yt-dlp bloqueado |
| `cryptoreport-analysis-plan.timer` | cada 15 min (`:08/:23/:38/:53`) | análisis narrativo de hasta 2 trabajos, validación de citas y promoción | **Codex CLI con sesión ChatGPT** (`gpt-6-luna`, esfuerzo máximo) | **relevado por Claude Code**, `claude-sonnet-5` esfuerzo máximo (§2) |
| `cryptoreport-bridge.timer` | cada 15 min (`:03/:18/:33/:48`) | reconcilia Drive, valida e importa resultados, publica sitio y app, revisa los sobres semánticos | servidor (sin inferencia) | activo; **la pata de Drive del cruce semántico quedó cortada** el 20-oct (`CR_SEMANTIC_DRIVE=true` la reactiva) |
| `cryptoreport-social.service` (cron `/etc/cron.d/cryptoreport-social`) | cada 15 min | recolecta el feed de X con presupuesto acotado, sin modelos | servidor | activo y sano |
| `cryptoreport-social-maintenance.timer` | cada 15 min | caduca y republica el feed vigente, sin red | servidor | activo |
| `cryptoreport-semantic.timer` | cada 2 h (`0/2:40`) | resuelve un cruce semántico vídeo ↔ X por ejecución | **ChatGPT Scheduled** (vía Drive) | **nuevo: relevado por Claude Code** y encendido el 20-oct por instrucción del usuario |
| `cryptoreport-panel.service` | permanente | panel de administración en `127.0.0.1:8750` + túnel | servidor | activo |
| `cryptoreport-urania-web.service` + `-tunnel` | permanente | sirve `prototypes/movil` y el túnel público de Urania | servidor | activos |
| Tarea «CryptoReport — análisis de narrativas» de ChatGPT Scheduled | 4 veces al día | analiza desde Drive con la cuenta ChatGPT del usuario | **cuenta ChatGPT del usuario** | sigue disparándose y su último comprobante es `error`; conviene pausarla |

Fuera de systemd quedan en PM2 tres servidores estáticos de propuestas de
diseño que levantó Codex (`cryptoreport-atlas-design`, `-atlas-videos`,
`-mobile-six`, puertos 18809, 18810 y 18812, con sus túneles). No forman parte
del pipeline: sirven HTML fijo y no tienen tarea periódica.

Las tareas de inferencia eran tres: el analista local vía Codex CLI, la tarea
de ChatGPT Scheduled sobre Drive y el juez del cruce semántico. Ninguna usaba
API de pago: el contrato del proyecto prohíbe el *fallback* por clave API
(`CRA_ALLOW_API_ANALYSIS=false`, claves borradas del entorno hijo).

## 2. Lo que queda bajo Claude

**Análisis narrativo.** `cranalysis.plan` ya no depende de Codex: tiene un
registro de **ejecutores de suscripción** y elige el primero con sesión viva.

- `claude`: `claude --print --model claude-sonnet-5 --effort max`, sin
  herramientas, sin MCP, sin ajustes de usuario (`--setting-sources ''`) y sin
  clave API. Etiquetas `provider=claude-code-plan`, `billing=claude_plan`,
  `cost_usd_estimate=None`.
- `codex`: el camino anterior intacto (`gpt-6-luna`, `forced_login_method=chatgpt`).
- El orden se fija con `CR_ANALYSIS_EXECUTOR`; el servicio usa `claude,codex`
  mediante `/etc/systemd/system/cryptoreport-analysis-plan.service.d/executor.conf`
  (versionado en `services/analysis/ops/analysis-plan-executor.conf`, que
  también sube `MemoryMax` a 1500M y `TimeoutStartSec` a 150 min). Sin ninguna
  sesión válida el estado es `auth_blocked`; nunca se recurre a una API de pago.

La respuesta se **reconstruye desde el flujo de eventos** (`--output-format
stream-json`) concatenando todos los mensajes del asistente, y el tope de
salida se fija en 64.000 tokens (`CLAUDE_CODE_MAX_OUTPUT_TOKENS`). Hizo falta:
con un análisis largo el CLI parte el JSON en varios mensajes y el modo `json`
solo devuelve el último, que empieza a mitad del documento. Los fallos del
ejecutor ahora registran solo evidencia operativa (tamaños y estado), no
fragmentos del material analizado.

**Rechazos del proveedor.** Un `429`/`529` se clasifica como `rate` (espera
corta) frente a `quota` (espera de 6 h), y en ambos casos **no se le cobra el
intento al trabajo** ni al presupuesto del día: sin inferencia no hay nada que
cobrar. Hizo falta porque el despacho de las 21:53 recibió un `429` —la
suscripción estaba agotada— y le gastó un intento a un vídeo que nunca se
analizó.

**Tiempos reales medidos el 20-oct:** un análisis a esfuerzo máximo tarda entre
20 y 30 minutos (23 min para una transcripción de 13 KB, 30 min para una de
16 KB), y las de 48 y 106 KB agotaron el límite de 25 min que había al
principio. El turno se acotó en **45 min** (`CR_ANALYSIS_CLI_TIMEOUT`, entre 10
y 90 min) con una ventana de servicio de 3 h 20, para que el tope proteja de un
CLI colgado y no de la lentitud normal. Un trabajo bloqueado corta el despacho
en curso, así que la cola avanza de dos en dos por ciclo.

Todo lo demás del contrato se conserva: cerrojo propio, 2 trabajos por
despacho, 16 intentos por día de Bogotá, 2 intentos por trabajo con una
corrección, validación de esquema y de citas literales, reparación de
localizadores, promoción atómica y los mismos eventos de observabilidad (ahora
con el campo `executor`).

Además, el ejecutor local honra las **autorizaciones de reintento** del
operador (`crbridge retry`, o el botón del panel): una autorización posterior
al fallo reabre un trabajo `invalid`/`blocked`, igual que ya hacía la tarea de
Drive. Antes solo Drive respetaba ese mecanismo y un trabajo marcado `invalid`
quedaba fuera de la cola para siempre.

**Cruce semántico.** `crsocial semantic-solve` resuelve en el servidor los
trabajos que juzgaba Scheduled: `crsocial/subscription.py` ejecuta cada etapa
(`select_candidates`, `judge_pairs`, `audit_pairs`) como un turno del CLI de
Claude sin herramientas, con la misma interfaz `ask()` que el cliente de API, y
`crsocial/semantic_local.py` escribe el **mismo sobre** `.semantic` que subía
Drive. El puente lo revalida con `scheduled.validate_output`, que reproduce las
etapas y recompone las puertas, así que el ejecutor no puede publicar una
conexión por su cuenta ni dejar sobre de un lote incompleto. Exige
`CR_SOCIAL_EXECUTOR=claude` y una sesión de suscripción; con 12 llamadas de
presupuesto por ejecución y un trabajo cada dos horas.

**La capa de conexiones nunca había publicado nada** (`jobs_reviewed: 0`
histórico) y el 20-oct se encontró el motivo mecánico: el `job_id` es el hash
del lote de 30 posts, así que cada post nuevo o caducado cambia todos los
`job_id`; el ciclo borraba el sobre cuyo trabajo ya no estaba vigente
(«Ephemeral corpus») y reescribía `social-connections.json` solo con lo
revisado en esa vuelta. Con la tarea de Scheduled contestando cada seis horas,
eso no podía cuajar nunca. Dos cambios lo arreglan:

- `semantic_local` revisa el sobre **en la misma instantánea** (`at` idéntico)
  en que lo resolvió, antes de que el corpus se mueva.
- `scheduled.durable()` guarda las conexiones aceptadas en
  `social/semantic/connections.json` y republica las que siguen válidas
  revalidando **sin modelo**: el post existe con el mismo `content_hash`, sigue
  elegible, no ha caducado y el hash del análisis no cambió. Son los mismos
  invariantes que exige la revisión, así que conservarlas no afirma nada que no
  se haya comprobado. El informe trae `connections_published`.

Con el cruce resuelto en el servidor, **la pata de Drive se cortó** por
instrucción del usuario: el ciclo del puente ya no sube trabajos a Control ni
sondea Resultados. Era pura pérdida —ChatGPT Scheduled no consumía la cola, la
carpeta Control acumulaba 815 archivos y cada vuelta devolvía
`drive_conflict`— y además ensuciaba el estado publicado. El informe declara
`drive_leg: false` y el estado inicial es `pendiente_local`;
`CR_SEMANTIC_DRIVE=true` la reactiva sin tocar código. La revisión de los
sobres locales, que es lo que publica, no cambió.

Pruebas: `services/analysis` pasa de 47 a 54 casos (ejecutor Claude con sus
banderas y su tope de salida, reconstrucción de una respuesta partida,
clasificación de cuota, salida truncada sin filtrar material, sesión de
suscripción frente a clave API, orden de ejecutores, relevo y bloqueo sin
sesión, autorización de reintento). Para el cruce semántico hay 6 casos nuevos
en `services/social`: CLI fijado sin herramientas y con etapa partida, rechazo
de clave API y de ejecutor apagado, cuota agotada sin etapa parcial,
presupuesto y lote máximo, sobre replicable por el servidor y auditoría ausente
que nunca llega a publicar. Suites verdes el 20-oct: analysis 54, bridge 48,
transcripts 69, social 74, panel 14.

## 3. Resultados del día

- **Los dos vídeos atascados se analizaron y publicaron.** Estaban bloqueados
  tras agotar intentos con Codex, cada uno por **una sola cita** que no
  coincidía con su rango: `rGh885JAaaY` (criptoniano, error `E16`) y
  `921RyVROMg0` (healthy, error `E3`). Se autorizó su reintento y el ejecutor
  de Claude los cerró a las 21:46 y 22:16 UTC.
- **La extracción revivió.** Con el tope de Supadata en 100 créditos del plan
  Free (antes 20) entraron seis transcripciones nuevas la misma tarde
  (`F69lmoQsxQ0`, `0emfDmB2LWM`, `rKsMbU-PLXM`, `gIY12HdAeO0`, `-aaDP7lyXD8`,
  `WRpuwxkS2Tg`), con 26 créditos consumidos en el mes. `CR_SUPADATA_GENERATE`
  sigue en `false`: nada de generación de audio de pago.
- **Tres trabajos nuevos se reabrieron tras un fallo técnico del ejecutor**
  (una salida partida y un `TimeoutExpired` de 25 min): `F69lmoQsxQ0`,
  `0emfDmB2LWM` y `gIY12HdAeO0`. El material estaba intacto; el defecto era del
  lector de la respuesta y ya está corregido y cubierto por pruebas.

## 4. Lo que sigue en manos del usuario

1. **Scraper.Tech está muerto** (`Tariff ended`, 2.121 peticiones este mes).
   Mientras no se renueve, Supadata es el único proveedor y su plan Free da 100
   créditos al mes: a ~6 vídeos/día no llega a fin de mes. Decisiones posibles:
   renovar Scraper.Tech, pasar Supadata a un plan pagado o levantar el túnel
   SOCKS de la tablet para desbloquear yt-dlp.
2. **La tarea de ChatGPT Scheduled sigue activa** en la cuenta del usuario y su
   último comprobante es `error`. Conviene pausarla: con la pata de Drive del
   cruce cortada ya no encontrará trabajos semánticos, y los de vídeo los está
   resolviendo el ejecutor local. Los 815 archivos de la carpeta Control son
   restos de ese piloto y se pueden limpiar cuando la tarea esté pausada.
3. **Cuota del plan de Claude.** Los análisis (hasta 2 cada 15 min) y el cruce
   semántico (uno cada 2 h) comparten la suscripción **Pro**. Si aparece
   `quota` en el estado, el analista se pausa 6 h por sí solo; bajar el esfuerzo
   o la cadencia son las palancas.

## 5. Verificación

```sh
systemctl list-timers 'cryptoreport-*' --all
systemctl show cryptoreport-analysis-plan.service -p Environment   # CR_ANALYSIS_EXECUTOR
journalctl -u cryptoreport-analysis-plan.service -n 40
journalctl -u cryptoreport-semantic.service -n 20
python3 -c "import json;print(json.load(open('/var/www/cryptoreport/pipeline-status.json'))['analysis_runner'])"
cd services/analysis && PYTHONPATH=.:../transcripts ../bridge/.venv/bin/python -m unittest discover -s tests -t .
```

Estado publicado en `/var/www/cryptoreport/pipeline-status.json`, informe del
cruce en `/var/lib/cryptoreport-transcripts/social/semantic/local-status.json`
y la app en
`https://software-johnston-seed-aimed.trycloudflare.com/b4-urania/#/diario`.

Para volver atrás: borrar el *drop-in* `executor.conf` y `systemctl
daemon-reload` devuelve el analista a Codex; `systemctl disable --now
cryptoreport-semantic.timer` apaga el cruce. El código soporta ambos sin más
cambios.

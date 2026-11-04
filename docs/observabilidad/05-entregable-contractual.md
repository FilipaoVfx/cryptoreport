# Parte 5 · Entregable contractual (Contract-Adhering Deliverable)

> Qué entra, qué no, qué se entrega en cada fase, cómo se acepta y cómo se comprueba automáticamente. Este documento y sus contratos forman la versión **1.0.0** del contrato de observabilidad de Urania/Diario.

<a id="objeto"></a>
## 5.1 Objeto, partes y definiciones

- **Objeto.** Dotar a Urania/Diario de observabilidad de nivel de producción y de un panel independiente para vigilar, ajustar y depurar los flujos de agentes, las cadenas de datos y las interacciones de las personas, dentro de los límites de este servidor.
- **Partes.** Hay dos:
  - **Propietario:** quien aprueba alcance, presupuestos, guardas y cada fase.
  - **Implementación:** quien construye. Puede ser una persona o una sesión de agente, y responde con los protocolos de §5.6.
- **Definiciones:**
  - **Entregable:** artefacto versionado en el repositorio con criterios de aceptación.
  - **Fase:** grupo de entregables con criterios de entrada y salida.
  - **PV:** protocolo de validación automatizado.
  - **Contrato:** los archivos de [`contratos/`](contratos), con versión semántica.
  - **Línea base:** las medidas de la parte 1, §1.3.

<a id="en-alcance"></a>
## 5.2 Alcance incluido (In-Scope)

| ID | Componente | Contenido | Contratos | Fase |
|---|---|---|---|---|
| C-00 | Paquete de planificación | Este documento, contratos, validador, pruebas y CI | Todos | **Entregado** |
| C-01 | Libro de ejecuciones | `run_id` UUIDv7, `run_record` por ejecución de extractor, puente, build_data y análisis; `trigger-bridge.json` | `run-record` | 0 |
| C-02 | Historial de transiciones y comprobantes | Tabla de transiciones del puente; comprobantes de Scheduled convertidos a `run_record` con `external` | `job`, `run-record` | 0 |
| C-03 | Logs estructurados | JSON por línea en stdout con los eventos del registro | `log-record`, `semconv` | 0 |
| C-04 | `crtelemetry` | Envoltorio del SDK OTel 1.45.1: nombres solo del registro, `IdGenerator` con `trace_id = run_id`, exportación que falla abierta y spans reconstruidos | `semconv`, `span-record` | 1 |
| C-05 | Pila de telemetría | `docker compose` con Collector v0.162.0, Jaeger v2.22.0, VictoriaMetrics v1.154.0 y VictoriaLogs v1.53.0; redacción y límites de memoria | `semconv` (redacción) | 1 |
| C-06 | Servicio `cr-panel` | API v1, UI W1–W8, SSE, cálculo de alertas y SLO | `openapi`, `health-report`, `alert` | 2 |
| C-07 | Plano de control | Versiones de configuración, solicitudes de cambio, techos del host y `crconfig.load()` en los servicios | `config-version`, `config-change`, `parametros` | 2 |
| C-08 | Intervenciones | Ejecutor con lista blanca, polkit, `panel-requests.json`, `quarantine.json` y `panel-recovery-requests.json` | `intervention`, `intervenciones` | 2 |
| C-09 | Seguridad y auditoría | Cuentas argon2id con TOTP, RBAC, CSRF y cadena de auditoría con anclaje diario | `audit-event`, `openapi` | 2 |
| C-10 | Biblioteca | Catálogo, inspectores, diferencias y búsqueda léxica (Fase 2); chunks, embeddings locales, `cr-embed` y búsqueda híbrida (Fase 3) | `asset`, `chunk`, `vector-index-status`, `search`, `quality-report` | 2–3 |
| C-11 | Evaluación | Trayectorias (con las instrucciones 1.4), autorater en modo *monitor* con calibración, feedback | `evaluation-result`, `feedback` | 3 |
| C-12 | Endurecimiento | Alertas por Telegram, ensayo de runbooks, copias, simulacro de restauración y retención | `umbrales` | 4 |

<a id="fuera-de-alcance"></a>
## 5.3 Fuera de alcance (Out-of-Scope)

| Exclusión | Motivo |
|---|---|
| Descargar o almacenar video o audio de YouTube | Condiciones de uso, bot-check y URL atadas a la red de origen: la Biblioteca guarda referencias |
| Abrir la API de pago (G-01) o subir techos del host desde el panel | Decisión del propietario: gasto solo con aprobación explícita y fuera del panel |
| Automatizar o controlar la interfaz de ChatGPT Scheduled | El servidor no controla esa interfaz; se trabaja con instrucciones y comprobantes |
| Rediseñar Urania/Diario | Los prototipos siguen su propio proceso. Solo se prevé el contrato de feedback con `surface: urania` |
| Telemetría en SaaS | Decisión: autoalojado y ligero |
| Alta disponibilidad, varios nodos o varios clientes | Un VPS y un equipo pequeño; el volumen es de unos 5000 spans al día |
| Migrar a Supabase o Postgres | `plan-extraccion-datos.md` lo contemplaba; SQLite basta y no se cambia la base de los servicios |
| Rotar las claves expuestas en conversaciones (H-12) | Acción del propietario en los proveedores; el plan solo lo recuerda |
| Resolver la cuota de Drive con un cliente OAuth propio (H-02) | Dependencia D-01; el panel la vigila y RB-05 la documenta |
| Volver a proteger el túnel de prototipos (H-10) | Se recomienda; pertenece al flujo de prototipos |
| Revisión legal del contenido analizado | Fuera de la competencia técnica |

<a id="supuestos"></a>
## 5.4 Supuestos y dependencias

| ID | Supuesto o dependencia | Si no se cumple |
|---|---|---|
| D-01 | El puente tiene un cliente OAuth de Drive propio (sin cuota compartida) | SH-05 y SH-06 siguen en rojo; el panel lo muestra, pero la importación automática se detiene |
| D-02 | El propietario elige bot y chat de Telegram | Las alertas solo se ven en el panel |
| D-03 | Se publican las instrucciones 1.4 (pasos, modo y revisión en el comprobante) | AP-05 a AP-08 quedan como *propuestos* |
| D-04 | Hay presupuesto para el autorater por API (unos 15 USD al mes) | El juez corre vía Scheduled, con más sesgo, o no corre |
| D-05 | El host mantiene al menos 1,5 GiB disponibles (RS-05) | Se recorta la retención o se apaga Jaeger (RB-15) |
| D-06 | El código de producción se confirma en git antes de la Fase 0 (H-01) | `service.version` sigue siendo `-dirty` y solo `cr.code.digest` identifica el código |
| D-07 | El CI mantiene Python 3.12 y 3.14 | `uuid7` necesita la implementación alternativa en 3.12 |
| D-08 | Se decide dónde guardar la copia externa | Las copias solo están en el mismo VPS |

<a id="especificaciones"></a>
## 5.5 Especificaciones de los entregables

| Entregable | Contenido | Criterios de aceptación | Esfuerzo estimado |
|---|---|---|---|
| **D-00** Paquete de planificación (C-00) | `docs/observabilidad/`: 5 partes, 27 esquemas, 8 registros, OpenAPI, 118 ejemplos, validador, pruebas y workflow `observabilidad.yml` | PV-01 a PV-06, PV-10, PV-11 y PV-15 a PV-17 en verde en CI con Python 3.12 y 3.14 | Hecho |
| **D-01** Identidad y libro (C-01, C-03) | `run_id` en los cuatro ejecutores, tabla `run_records`, logs JSON y `trigger-bridge.json`; corrección de H-05, H-06, H-09 y H-13 | PV-07 diario sin errores durante 7 días; SH-01, SH-02, SH-05 y SH-16 calculables desde el libro; suites existentes en verde | 2–3 días |
| **D-02** Historial y comprobantes (C-02) | Transiciones con cuenta y motivo; comprobantes → `run_record` (UUIDv5); detección de AP-04 | Cada transición tiene fila; el comprobante `aabe58f1` de 22 trabajos aparece como aviso AP-04; AP-14 calculable | 1–2 días |
| **D-03** Telemetría (C-04, C-05) | `crtelemetry`, spans del árbol de §1.5.2, métricas del catálogo, pila en `docker compose` | PV-08 al 100 % durante 7 días; PV-09 dentro de RS-01 a RS-03; RS-04 ≤ 5 %; un fallo del Collector no falla ningún ciclo (prueba de caos) | 3–4 días |
| **D-04** Panel v1 (C-06, C-07, C-08, C-09) | API v1 completa de la fase 2, W1–W7, plano de control, intervenciones, auditoría, RBAC, TOTP y SSE | PV-18 al 100 %, PV-14 sin violaciones serias, PV-11 diario, pruebas de usabilidad de §4.10 | 8–12 días |
| **D-05** Biblioteca (C-10) | Catálogo, inspectores, diferencias, búsqueda léxica (fase 2); chunks, `cr-embed`, sqlite-vec y modo híbrido (fase 3) | DQ-C-01 a DQ-C-06 en verde; DQ-E-04 ≥ 0,8 y DQ-E-05 ≥ 0,7 antes de activar la búsqueda semántica | 2 + 3 días |
| **D-06** Evaluación (C-11) | Instrucciones 1.4, trayectorias reales, autorater en modo *monitor*, calibración y bucle de feedback | AP-05 a AP-08 medidos sobre ≥ 20 ejecuciones; κ (AP-11) calculado sobre ≥ 30 análisis; PV-13 operativo | 3–4 días |
| **D-07** Endurecimiento (C-12) | Telegram, runbooks ensayados, copias, PV-12, limpieza de `bridge/cache` y retenciones | Los 16 runbooks ensayados al menos una vez; restauración en menos de 30 min; cero alertas sin runbook | 2–3 días |

Las estimaciones suponen una persona con el código ya conocido y no incluyen esperas por dependencias (D-01 a D-08).

<a id="protocolos"></a>
## 5.6 Protocolos de validación automatizados

Fuente: [`registros/trazabilidad.json`](contratos/registros/trazabilidad.json). Los protocolos implementados se ejecutan así:

```bash
python3 -m pip install -r docs/observabilidad/herramientas/requirements.txt
python3 docs/observabilidad/herramientas/validate_contracts.py                       # PV-01…06, 10, 11, 15, 16
python3 -m unittest discover -s docs/observabilidad/herramientas/tests -t docs/observabilidad/herramientas   # PV-17
python3 docs/observabilidad/herramientas/validate_contracts.py --datos-reales /var/lib/cryptoreport-transcripts  # PV-07 (servidor)
python3 docs/observabilidad/herramientas/validate_contracts.py --spans /var/lib/cryptoreport-telemetry/spans.jsonl  # PV-08 (desde la Fase 1)
```

El workflow [`.github/workflows/observabilidad.yml`](../../.github/workflows/observabilidad.yml) ejecuta los dos primeros en cada push y pull request con Python 3.12 y 3.14.

<!-- generado:inicio protocolos -->
| ID | Protocolo | Qué comprueba | Cómo | Cuándo | Criterio de aprobación | Estado |
|---|---|---|---|---|---|---|
| **PV-01** | Esquemas válidos | Cada JSON Schema cumple el metaesquema Draft 2020-12 y figura en el manifiesto de contratos. | `python3 docs/observabilidad/herramientas/validate_contracts.py` | CI | 0 errores de metaesquema y 0 archivos sin registrar. | implementado |
| **PV-02** | Ejemplos válidos e inválidos | Todo ejemplo válido valida; todo ejemplo inválido falla y por el motivo declarado (palabra clave y ruta). | `validate_contracts.py, sección ejemplos` | CI | 100 % de ejemplos con el resultado esperado. | implementado |
| **PV-03** | OpenAPI conforme | openapi.yaml valida contra el esquema oficial OAS 3.1 (2026-08-03) y cumple las reglas propias: operationId únicos, parámetros de ruta declarados, seguridad, rol mínimo, idempotencia y auditoría en mutaciones, $ref resolubles. | `validate_contracts.py, sección openapi` | CI | 0 errores. | implementado |
| **PV-04** | Registro de nombres coherente | Todo nombre gen_ai.* o estándar existe en la instantánea fijada con el mismo instrumento y unidad; todo cr.* está definido; las métricas solo usan atributos de cardinalidad baja. | `validate_contracts.py, sección semconv` | CI | 0 nombres desconocidos. | implementado |
| **PV-05** | Documento al día | Las tablas generadas del documento coinciden con los registros y la OpenAPI. | `validate_contracts.py (comprueba); --write las regenera` | CI | 0 bloques desactualizados. | implementado |
| **PV-06** | Anclas de código | Parámetros, umbrales, guardas, herramientas, rutas e intervenciones citan texto que existe en el archivo indicado; las pruebas citadas existen. | `validate_contracts.py, sección anclas` | CI | 0 anclas rotas. | implementado |
| **PV-07** | Conformidad con datos reales | pipeline-status.json, transcripciones y análisis vivos encajan en los contratos (estado heredado y adaptadores de activos). | `validate_contracts.py --datos-reales /var/lib/cryptoreport-transcripts` | diario | 0 discrepancias; las nuevas se convierten en cambio de contrato o en hallazgo. | implementado |
| **PV-08** | Spans exportados conformes | Cada span exportado valida contra span-record y el registro; ningún atributo de contenido sin opt-in. | `validate_contracts.py --spans <archivo JSONL del exportador file del Collector>` | diario | 100 % de spans conformes en la muestra diaria. | implementado |
| **PV-09** | Presupuesto de recursos | Memoria, CPU y disco de la pila de observabilidad dentro de RS-01 a RS-03. | docker stats --no-stream y du sobre los volúmenes; resultado al libro de ejecuciones | diario | Sin niveles warning durante 7 días seguidos. | fase 1 |
| **PV-10** | Guardas probadas | Las pruebas citadas por cada guarda pasan en CI; las guardas sin prueba declaran su hueco. | .github/workflows/ci.yml (suites existentes) y validate_contracts.py (referencias) | CI | Todas las suites en verde y 0 referencias rotas. | implementado |
| **PV-11** | Auditoría íntegra | La cadena de hashes de auditoría se recalcula sin discrepancias. | `validate_contracts.py (cadenas de ejemplo); GET /api/v1/audit/verify a diario desde la Fase 2` | diario | first_bad_seq = null. | implementado |
| **PV-12** | Restauración probada | Restaurar state.sqlite, bridge/state.sqlite y panel.sqlite desde copia y verificar recuentos y cadena de auditoría. | Simulacro en un directorio temporal con el runbook RB-15 | mensual | Restauración completa en menos de 30 min y recuentos idénticos. | fase 4 |
| **PV-13** | Puerta de evaluación de prompts | Un prompt o esquema nuevo pasa el conjunto dorado: validador al 100 %, sin regresión del autorater y revisión humana. | Comando del panel sobre el conjunto dorado en modo offline o vía Scheduled | en cada cambio | Validador 100 % y caída del autorater menor de 0,05. | fase 3 |
| **PV-14** | Accesibilidad del panel | WCAG 2.2 AA: axe-core sin violaciones serias o críticas y flujo completo por teclado en W1 a W8. | axe-core en CI del panel y recorrido manual por teclado | CI | 0 violaciones serias o críticas. | fase 2 |
| **PV-15** | Sin secretos | Ningún archivo de docs/observabilidad contiene patrones de claves (sk-, sd_, Bearer, claves privadas). | `validate_contracts.py, sección secretos` | CI | 0 coincidencias. | implementado |
| **PV-16** | Deriva de umbrales de tono | min_mass, ±0,3 y los cortes 1,6 y 3,5 coinciden en tono.py y shared/core.js. | `validate_contracts.py, sección tono` | CI | 0 diferencias. | implementado |
| **PV-17** | Métricas de trayectoria verificadas | La implementación de referencia reproduce los ejemplos numéricos del documento. | `python3 -m unittest discover -s docs/observabilidad/herramientas/tests` | CI | Todas las pruebas en verde. | implementado |
| **PV-18** | Seguridad de la API del panel | Cada operación responde 401 sin sesión y 403 por debajo de su x-cr-min-role; las mutaciones exigen CSRF e Idempotency-Key. | Pruebas de contrato generadas desde openapi.yaml contra el panel | CI | 100 % de operaciones conformes. | fase 2 |
<!-- generado:fin protocolos -->

<a id="hoja-de-ruta"></a>
## 5.7 Hoja de ruta por fases

```text
Fase 0 · Identidad y libro ──► Fase 1 · Telemetría ──► Fase 2 · Panel v1 ──► Fase 3 · Evaluación y búsqueda ──► Fase 4 · Endurecimiento
   D-01, D-02                    D-03                     D-04, D-05 (léxica)     D-05 (semántica), D-06            D-07
   requiere D-06 (commit)        requiere D-05 (RAM)      requiere D-01 (Drive)   requiere D-03, D-04                requiere D-02, D-08
```

| Fase | Entrada | Salida (todos los criterios) |
|---|---|---|
| 0 | Producción confirmada en git (D-06); CI en verde | D-01 y D-02 aceptados; PV-07 diario activo |
| 1 | Fase 0 cerrada; presupuesto de RAM confirmado (RS-05) | D-03 aceptado; umbrales SH-* y TK-* medidos desde métricas |
| 2 | Fase 1 cerrada | D-04 y D-05 (léxica) aceptados; el equipo usa el panel para una semana de guardias |
| 3 | Fase 2 cerrada; D-03 publicado; decisión sobre D-04 | D-05 (semántica) y D-06 aceptados |
| 4 | Fase 3 cerrada | D-07 aceptado; contrato 1.x estable |

Cada fase se entrega en su propia rama con un PR que incluye las pruebas, la actualización de los registros y, si cambia algún contrato, la subida de versión según §5.9.

<a id="aceptacion"></a>
## 5.8 Criterios de aceptación y Definition of Done

Un entregable está **terminado** cuando:

1. Su código y sus contratos están confirmados en git y no hay producción ejecutando código sin commit.
2. Pasan las suites existentes de los tres servicios y las nuevas (CI con Python 3.12 y 3.14).
3. El validador sale con 0 errores: el documento sigue al día, las anclas existen y no hay secretos.
4. Sus protocolos de §5.6 cumplen el criterio de aprobación durante el periodo indicado.
5. Ningún umbral nuevo en modo *alert* queda sin runbook ni intervención (P8).
6. La memoria de la pila sigue dentro de RS-01 y el pipeline no ha perdido ciclos (SH-01) por su causa.
7. El README del servicio y esta documentación describen el comportamiento real.
8. El propietario lo acepta por escrito en el PR.

<a id="cambios-contrato"></a>
## 5.9 Gestión de cambios del contrato

- **Versión semántica** en `contract_version` ([`manifest.json`](contratos/manifest.json)) y en `registry_version` de cada registro:
  - **MAJOR:** quitar o renombrar un campo, un valor de enum, una ruta o un nombre de telemetría, o endurecer una restricción.
  - **MINOR:** añadir un campo opcional, un valor de enum, una ruta, un umbral o un parámetro.
  - **PATCH:** solo descripciones y ejemplos.
- **Deprecación.** Un nombre de telemetría o un campo se marca como deprecado durante al menos una versión *minor* antes de quitarse en la siguiente *major*. El validador avisará de los usos deprecados.
- **Convenciones OTel.** Se mueve la instantánea con `extract_semconv.py` (§1.5.7). Si un nombre `gen_ai.*` desaparece, se trata como un cambio *major* del registro.
- **Aprobación.** Un cambio de contrato *major* exige `admin` y una 2.ª persona, igual que una guarda *critical*.
- **Umbrales.** Solo se cambian con línea base nueva (`measured_at`) y la tabla generada del documento se actualiza en el mismo PR (PV-05).

<a id="riesgos"></a>
## 5.10 Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Las convenciones GenAI de OTel cambian (están en *Development*) | Alta | Medio | Instantánea fijada, registro aislado y validador (§1.5.7) |
| La cuota de Drive sigue bloqueando el puente | Alta | Alto | D-01, `pause_drive_uploads`, RB-05; el panel lo muestra en rojo |
| El modelo de Scheduled no es verificable | Cierta | Medio | `cr.model.verified = false`, revalidación en el servidor, autorater y AP-04 |
| Competencia de memoria con otros proyectos del VPS | Media | Alto | Límites por contenedor, RS-01 a RS-05, Jaeger prescindible (RB-15) |
| La telemetría ralentiza los ciclos | Baja | Medio | Lotes con timeout de 2 s, fail-open y RS-04 ≤ 5 % |
| Se filtra un secreto o un ID de Drive (repo público) | Media | Alto | PV-15 en CI, redacción en el Collector, el panel no lee `.env` |
| El autorater está sesgado o descalibrado | Media | Medio | Familia distinta, κ ≥ 0,6 antes de alertar y nunca bloquea |
| El alcance crece hacia el rediseño de Urania | Media | Medio | §5.3; cualquier ampliación entra como cambio de contrato |
| Las anclas de código se rompen con refactorizaciones | Media | Bajo | PV-06 señala el ancla rota; se actualiza el registro en el mismo PR |
| Una sola persona aprueba todo (equipo pequeño) | Alta | Medio | G-17 exige una 2.ª persona solo en riesgo alto o crítico; la auditoría registra todas las excepciones |

<a id="trazabilidad"></a>
## 5.11 Matriz de trazabilidad

Cada requisito del encargo, con las secciones que lo cubren, sus contratos y sus protocolos (generado; el validador comprueba que todas las secciones y contratos existen):

<!-- generado:inicio trazabilidad -->
| Req. | Parte | Requisito | Secciones | Contratos | Protocolos | Estado |
|---|---|---|---|---|---|---|
| **R-01** | 1 | Manifiesto de observabilidad riguroso y de nivel de producción. | [principios](01-manifiesto-observabilidad.md#principios), [hallazgos](01-manifiesto-observabilidad.md#hallazgos) | [`semconv.json`](contratos/registros/semconv.json) | PV-04 | cubierto |
| **R-02** | 1 | Telemetría OpenTelemetry que traza cada paso interno, cada invocación de API o herramienta y cada interacción entre agentes. | [modelo-telemetria](01-manifiesto-observabilidad.md#modelo-telemetria), [arbol-spans](01-manifiesto-observabilidad.md#arbol-spans), [pasos-razonamiento](01-manifiesto-observabilidad.md#pasos-razonamiento) | [`span-record.schema.json`](contratos/esquemas/span-record.schema.json), [`log-record.schema.json`](contratos/esquemas/log-record.schema.json), [`semconv.json`](contratos/registros/semconv.json) | PV-04, PV-08, PV-15 | cubierto |
| **R-03** | 1 | Métricas de salud del sistema: latencia, tasas de error, uso de tokens y costes. | [metricas-salud](01-manifiesto-observabilidad.md#metricas-salud) | [`umbrales.json`](contratos/registros/umbrales.json), [`semconv.json`](contratos/registros/semconv.json) | PV-05 | cubierto |
| **R-04** | 1 | Rendimiento de agentes: Goal Completion Rate. | [gcr](01-manifiesto-observabilidad.md#gcr) | [`umbrales.json`](contratos/registros/umbrales.json) | PV-05, PV-07 | cubierto |
| **R-05** | 1 | Evaluación de trayectorias con precisión, recall y coincidencia de pasos en orden. | [trayectorias](01-manifiesto-observabilidad.md#trayectorias) | [`evaluation-result.schema.json`](contratos/esquemas/evaluation-result.schema.json) | PV-17 | cubierto: Las fórmulas son ejecutables (trajectory_metrics.py); la medición real necesita pasos en los comprobantes (instrucciones 1.4). |
| **R-06** | 1 | Autoraters LLM-as-a-Judge. | [autorater](01-manifiesto-observabilidad.md#autorater) | [`evaluation-result.schema.json`](contratos/esquemas/evaluation-result.schema.json) | PV-13 | parcial: Rúbrica y calibración definidas; ejecutar el juez exige presupuesto o un trabajo de Scheduled. |
| **R-07** | 1 | Umbrales de calidad de datos para medios no estructurados: video, transcripción de audio, chunking semántico y etiquetado de metadatos. | [calidad-datos](01-manifiesto-observabilidad.md#calidad-datos) | [`umbrales.json`](contratos/registros/umbrales.json), [`quality-report.schema.json`](contratos/esquemas/quality-report.schema.json), [`chunk.schema.json`](contratos/esquemas/chunk.schema.json) | PV-05, PV-06, PV-16 | cubierto |
| **R-08** | 2 | Especificación arquitectónica de un panel de administración independiente. | [objetivo-limites](02-panel-de-parametros.md#objetivo-limites), [arquitectura-panel](02-panel-de-parametros.md#arquitectura-panel), [despliegue-panel](02-panel-de-parametros.md#despliegue-panel) | [`openapi.yaml`](contratos/openapi.yaml) | PV-03, PV-09 | cubierto |
| **R-09** | 2 | Ajuste en tiempo real de system prompts. | [plano-control](02-panel-de-parametros.md#plano-control), [prompts](02-panel-de-parametros.md#prompts) | [`parametros.json`](contratos/registros/parametros.json), [`config-change.schema.json`](contratos/esquemas/config-change.schema.json), [`config-version.schema.json`](contratos/esquemas/config-version.schema.json) | PV-06, PV-13 | cubierto |
| **R-10** | 2 | Ajuste de temperatura. | [modelos-enrutamiento](02-panel-de-parametros.md#modelos-enrutamiento) | [`parametros.json`](contratos/registros/parametros.json) | PV-06 | cubierto: Se declara no aplicable con su motivo: el código usa effort, no temperature. |
| **R-11** | 2 | Lógica de enrutamiento de modelos. | [modelos-enrutamiento](02-panel-de-parametros.md#modelos-enrutamiento) | [`enrutamiento.json`](contratos/registros/enrutamiento.json), [`routing-policy.schema.json`](contratos/esquemas/routing-policy.schema.json) | PV-06 | cubierto |
| **R-12** | 2 | Descubrimiento dinámico de herramientas y registros. | [registro-herramientas](02-panel-de-parametros.md#registro-herramientas) | [`herramientas.json`](contratos/registros/herramientas.json), [`tool-registry.schema.json`](contratos/esquemas/tool-registry.schema.json) | PV-06 | cubierto |
| **R-13** | 2 | Políticas de guardrails activas. | [guardrails](02-panel-de-parametros.md#guardrails) | [`guardrails.json`](contratos/registros/guardrails.json), [`guardrail-policy.schema.json`](contratos/esquemas/guardrail-policy.schema.json) | PV-06, PV-10 | cubierto |
| **R-14** | 2 | Límites automáticos de fallback y reintentos. | [fallback-reintentos](02-panel-de-parametros.md#fallback-reintentos) | [`enrutamiento.json`](contratos/registros/enrutamiento.json), [`parametros.json`](contratos/registros/parametros.json) | PV-06 | cubierto |
| **R-15** | 3 | Biblioteca: almacenamiento de feeds de video crudos y procesados y de transcripciones. | [que-es](03-biblioteca.md#que-es), [modelo-activos](03-biblioteca.md#modelo-activos), [almacenamiento](03-biblioteca.md#almacenamiento) | [`asset.schema.json`](contratos/esquemas/asset.schema.json) | PV-02, PV-07, PV-12 | cubierto |
| **R-16** | 3 | Biblioteca: inspección. | [inspeccion](03-biblioteca.md#inspeccion) | [`openapi.yaml`](contratos/openapi.yaml), [`quality-report.schema.json`](contratos/esquemas/quality-report.schema.json) | PV-03 | cubierto |
| **R-17** | 3 | Biblioteca: búsqueda semántica. | [busqueda](03-biblioteca.md#busqueda) | [`search.schema.json`](contratos/esquemas/search.schema.json), [`chunk.schema.json`](contratos/esquemas/chunk.schema.json) | PV-02 | cubierto |
| **R-18** | 3 | Biblioteca: versionado. | [versionado](03-biblioteca.md#versionado) | [`asset.schema.json`](contratos/esquemas/asset.schema.json) | PV-02, PV-07 | cubierto |
| **R-19** | 3 | Biblioteca: auditoría de activos y estado de los índices vectoriales. | [indice-vectorial](03-biblioteca.md#indice-vectorial), [auditoria-biblioteca](03-biblioteca.md#auditoria-biblioteca) | [`vector-index-status.schema.json`](contratos/esquemas/vector-index-status.schema.json), [`audit-event.schema.json`](contratos/esquemas/audit-event.schema.json) | PV-02, PV-11 | cubierto |
| **R-20** | 4 | Lógica de wireframes UX/UI para trabajadores del conocimiento que gestionan agentes. | [personas](04-hitl-gestores-de-agentes.md#personas), [principios-ux](04-hitl-gestores-de-agentes.md#principios-ux), [wireframes](04-hitl-gestores-de-agentes.md#wireframes) | — | PV-14 | cubierto |
| **R-21** | 4 | Layouts de tablero en tiempo real. | [tablero](04-hitl-gestores-de-agentes.md#tablero) | [`health-report.schema.json`](contratos/esquemas/health-report.schema.json), [`common.schema.json`](contratos/esquemas/common.schema.json) | PV-02, PV-03 | cubierto |
| **R-22** | 4 | Bucles de feedback 👍/👎. | [feedback](04-hitl-gestores-de-agentes.md#feedback) | [`feedback.schema.json`](contratos/esquemas/feedback.schema.json) | PV-02 | cubierto |
| **R-23** | 4 | Disparadores de intervención manual. | [intervenciones](04-hitl-gestores-de-agentes.md#intervenciones) | [`intervenciones.json`](contratos/registros/intervenciones.json), [`intervention.schema.json`](contratos/esquemas/intervention.schema.json) | PV-06 | cubierto |
| **R-24** | 4 | Rastro de auditoría con permisos. | [auditoria](04-hitl-gestores-de-agentes.md#auditoria) | [`audit-event.schema.json`](contratos/esquemas/audit-event.schema.json), [`openapi.yaml`](contratos/openapi.yaml) | PV-11, PV-18 | cubierto |
| **R-25** | 5 | Componentes incluidos (In-Scope). | [en-alcance](05-entregable-contractual.md#en-alcance) | — | PV-05 | cubierto |
| **R-26** | 5 | Límites excluidos (Out-of-Scope). | [fuera-de-alcance](05-entregable-contractual.md#fuera-de-alcance) | — | PV-05 | cubierto |
| **R-27** | 5 | Especificaciones de los entregables. | [especificaciones](05-entregable-contractual.md#especificaciones), [aceptacion](05-entregable-contractual.md#aceptacion) | — | PV-01 | cubierto |
| **R-28** | 5 | Protocolos de validación automatizados. | [protocolos](05-entregable-contractual.md#protocolos) | [`traceability.schema.json`](contratos/esquemas/traceability.schema.json), [`trazabilidad.json`](contratos/registros/trazabilidad.json) | PV-01, PV-02, PV-03, PV-04, PV-05, PV-06 | cubierto |
| **R-29** | 5 | Formato: encabezados jerárquicos, tablas comparativas de métricas y parámetros, esquemas de contratos de API y límites explícitos de componentes. | [arquitectura-panel](02-panel-de-parametros.md#arquitectura-panel), [metricas-salud](01-manifiesto-observabilidad.md#metricas-salud), [api-panel](02-panel-de-parametros.md#api-panel) | [`openapi.yaml`](contratos/openapi.yaml) | PV-03, PV-05 | cubierto |
<!-- generado:fin trazabilidad -->

# Observabilidad y panel de administración de Urania/Diario

**Documento técnico de planificación · contrato 1.0.0 · 14 de octubre de 2026 · estado: propuesta para aprobación**

Urania/Diario es la app móvil que convierte los videos de siete creadores de cripto en señales alcistas y bajistas legibles. Los prototipos están en `prototypes/movil/b4-urania` y siguientes, con la pantalla «Diario». Detrás funcionan cuatro ejecutores en este servidor y un agente externo. Este paquete define cómo observarlos, ajustarlos y depurarlos desde un panel independiente, y deja contratos que el CI valida en cada cambio.

## Cómo leerlo

| Parte | Documento | Responde a |
|---|---|---|
| 1 | [Manifiesto de observabilidad y estándares de calidad](01-manifiesto-observabilidad.md) | Qué se mide, con qué nombres OpenTelemetry, con qué umbrales y qué hacer cuando salta una alerta |
| 2 | [Panel de control de parámetros](02-panel-de-parametros.md) | Qué se puede ajustar (prompts, modelos, enrutamiento, herramientas, guardas, reintentos), cómo llega el cambio y quién lo aprueba |
| 3 | [Biblioteca de medios y activos](03-biblioteca.md) | Qué activos hay, cómo se guardan, versionan, inspeccionan, buscan y auditan |
| 4 | [Usabilidad y flujos HITL](04-hitl-gestores-de-agentes.md) | Cómo trabaja una persona que gestiona agentes: tablero, wireframes, 👍/👎, intervenciones y auditoría |
| 5 | [Entregable contractual](05-entregable-contractual.md) | Qué entra y qué no, entregables, protocolos de validación, hoja de ruta y riesgos |
| — | [Contratos](contratos/README.md) | OpenAPI 3.1.1, 27 JSON Schemas, 8 registros, 118 ejemplos e instantáneas fijadas |

## El sistema que se observa

```text
YouTube (RSS · páginas /videos /streams /shorts)
   │
   ▼
cr-extractor  services/transcripts · timer cada 15 min ─► transcripciones + state.sqlite + data.json del sitio
   │ ExecStartPost
   ├─► cr-build-data  prototypes/movil/build_data.py ─► datos de Urania/Diario
   └─► cr-bridge      services/bridge · también a :03 :18 :33 :48
          │ rclone ─► Drive (control · pendientes · resultados · ejecuciones)
          ▼
       ChatGPT Scheduled (externo; GPT-6.1 Sol declarado, no verificable; cada 6 h, 2 trabajos)
          │ resultados + comprobantes
          ▼
       cr-bridge valida e importa ─► análisis ─► sitio con contraseña + Urania/Diario

cr-analysis  services/analysis · CLI · API de pago cerrada por la guarda G-01
cr-panel     NUEVO · API + UI + intervenciones + auditoría (parte 2)
```

## Línea base en una tabla

| | 14-oct-2026 |
|---|---|
| Videos y transcripciones | 35, todos válidos (cobertura mínima 0,911) |
| Análisis | 32 válidos (30 de Scheduled, 2 de OpenAI) |
| Ciclos del extractor | 552 de 552 terminados; p95 de 244 s |
| Agente Scheduled | GCR 0,967 (29 de 30), 5 de 9 ejecuciones sin error, una ejecución con 22 trabajos (límite: 2) |
| Puente | `failed` por cuota de Drive desde la madrugada del 14-oct |
| Telemetría | Ninguna: sin logs estructurados, métricas, trazas ni ID de ejecución |

Detalle completo en la [parte 1, §1.3](01-manifiesto-observabilidad.md#linea-base). Los 14 hallazgos que motivan el diseño están en [§1.4](01-manifiesto-observabilidad.md#hallazgos).

## Decisiones tomadas

- **Idioma:** español; los términos técnicos se quedan en inglés.
- **Ubicación:** `docs/observabilidad/`, versionado junto al código que describe.
- **Alcance:** el documento más contratos validables (OpenAPI, JSON Schemas, registros y validador ejecutable en CI).
- **Despliegue:** en este servidor, autoalojado y ligero: la pila completa ocupa como máximo 1 GiB de RAM en un VPS de 2 vCPU compartido.

## Cómo validar

```bash
python3 -m pip install -r docs/observabilidad/herramientas/requirements.txt
python3 docs/observabilidad/herramientas/validate_contracts.py
python3 -m unittest discover -s docs/observabilidad/herramientas/tests -t docs/observabilidad/herramientas
```

- `--write` regenera las tablas marcadas como `generado` a partir de los registros.
- `--datos-reales /var/lib/cryptoreport-transcripts` contrasta los contratos con los datos vivos del servidor (PV-07).
- `--spans <archivo>` valida spans exportados por el Collector (PV-08).

El workflow [`.github/workflows/observabilidad.yml`](../../.github/workflows/observabilidad.yml) lo ejecuta en cada push y pull request.

## Glosario

| Término | Significado aquí |
|---|---|
| `run_id` | Identidad de una ejecución: UUIDv7 propio o UUIDv5 reconstruido desde un comprobante; su `trace_id` es el `run_id` sin guiones |
| `job_id` | Trabajo de análisis del puente: `<video_id>__sha256(meta)`; cambia si cambian la transcripción, el prompt o el esquema |
| Span / traza | Unidad y árbol de trabajo de OpenTelemetry; cada ejecución es una traza |
| Registro de nombres | `contratos/registros/semconv.json`: el único vocabulario de telemetría permitido |
| Instantánea fijada | Copia de los nombres OTel GenAI en un commit concreto (0779402), porque las convenciones están en *Development* |
| GCR | Goal Completion Rate: objetivos cumplidos y validados / objetivos intentados |
| Trayectoria | Secuencia de pasos de un agente comparada con la de sus instrucciones (precisión, recall y orden) |
| Autorater | Juez LLM (*LLM-as-a-Judge*) que puntúa con una rúbrica; en el contrato 1.x nunca bloquea |
| HITL | *Human-in-the-loop*: decisiones que exigen una persona |
| Guarda (guardrail) | Regla que permite, bloquea o recorta una acción (G-01 a G-18) |
| Techo del host | Límite fijado en systemd o `.env` que el panel no puede superar |
| Intervención | Acción manual del catálogo con un ejecutor fijo, auditada |
| PV | Protocolo de validación automatizado (PV-01 a PV-18) |

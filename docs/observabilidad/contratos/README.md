# Contratos de observabilidad y del panel

Versión **1.0.0** ([`manifest.json`](manifest.json)). Todo lo que hay aquí lo valida [`../herramientas/validate_contracts.py`](../herramientas/validate_contracts.py) en cada CI.

| Carpeta | Contenido |
|---|---|
| [`openapi.yaml`](openapi.yaml) | API del panel en OpenAPI 3.1.1: 58 rutas y 63 operaciones con `x-cr-min-role`, `x-cr-audit` y `x-cr-phase` |
| [`esquemas/`](esquemas) | JSON Schemas Draft 2020-12, sin `$id`: se referencian entre sí por ruta relativa, como hace la OpenAPI |
| [`registros/`](registros) | Instancias reales que alimentan el panel y las tablas del documento: nombres de telemetría, umbrales, parámetros, herramientas, enrutamiento, guardas, intervenciones y trazabilidad |
| [`ejemplos/`](ejemplos) | `validos/<esquema>/` deben validar, `invalidos/<esquema>/` deben fallar por el motivo declarado y `cadenas/` contiene cadenas de auditoría |
| [`vendor/`](vendor) | Esquema oficial OAS 3.1 (2026-08-03) e instantánea de nombres OTel GenAI (commit 0779402); el manifiesto guarda su SHA-256 |

## Inventario

<!-- generado:inicio inventario-contratos -->
| Esquema | Contrato | Instancia real | Ejemplos válidos | Ejemplos inválidos |
|---|---|---|---|---|
| [`alert.schema.json`](esquemas/alert.schema.json) | Alerta | — | 2 | 3 |
| [`asset.schema.json`](esquemas/asset.schema.json) | Activo de la Biblioteca | — | 4 | 3 |
| [`audit-event.schema.json`](esquemas/audit-event.schema.json) | Evento de auditoría | — | 1 | 2 |
| [`chunk.schema.json`](esquemas/chunk.schema.json) | Chunk semántico de transcripción | — | 1 | 3 |
| [`common.schema.json`](esquemas/common.schema.json) | Definiciones comunes | — | 5 | 3 |
| [`config-change.schema.json`](esquemas/config-change.schema.json) | Solicitud de cambio de configuración | — | 2 | 4 |
| [`config-version.schema.json`](esquemas/config-version.schema.json) | Versión de configuración | — | 2 | 2 |
| [`evaluation-result.schema.json`](esquemas/evaluation-result.schema.json) | Resultado de evaluación | — | 4 | 3 |
| [`feedback.schema.json`](esquemas/feedback.schema.json) | Feedback 👍/👎 | — | 2 | 3 |
| [`guardrail-policy.schema.json`](esquemas/guardrail-policy.schema.json) | Políticas de guardrails activas | [`guardrails.json`](registros/guardrails.json) | 0 | 1 |
| [`health-report.schema.json`](esquemas/health-report.schema.json) | Informe de salud del panel | — | 1 | 1 |
| [`intervention-catalog.schema.json`](esquemas/intervention-catalog.schema.json) | Catálogo de intervenciones manuales | [`intervenciones.json`](registros/intervenciones.json) | 0 | 2 |
| [`intervention.schema.json`](esquemas/intervention.schema.json) | Intervención manual | — | 2 | 4 |
| [`job.schema.json`](esquemas/job.schema.json) | Trabajo del puente | — | 1 | 2 |
| [`log-record.schema.json`](esquemas/log-record.schema.json) | Línea de log estructurado | — | 2 | 2 |
| [`parameter-catalog.schema.json`](esquemas/parameter-catalog.schema.json) | Catálogo de parámetros ajustables | [`parametros.json`](registros/parametros.json) | 0 | 3 |
| [`pipeline-status.schema.json`](esquemas/pipeline-status.schema.json) | pipeline-status.json (contrato v1, tal cual existe) | — | 1 | 2 |
| [`quality-report.schema.json`](esquemas/quality-report.schema.json) | Informe de calidad de datos | — | 2 | 2 |
| [`routing-policy.schema.json`](esquemas/routing-policy.schema.json) | Política de enrutamiento, fallback y reintentos | [`enrutamiento.json`](registros/enrutamiento.json) | 0 | 1 |
| [`run-record.schema.json`](esquemas/run-record.schema.json) | Registro de ejecución | — | 3 | 5 |
| [`search.schema.json`](esquemas/search.schema.json) | Búsqueda en la Biblioteca | — | 2 | 1 |
| [`semconv-registry.schema.json`](esquemas/semconv-registry.schema.json) | Registro de nombres de telemetría | [`semconv.json`](registros/semconv.json) | 0 | 3 |
| [`span-record.schema.json`](esquemas/span-record.schema.json) | Span normalizado | — | 5 | 9 |
| [`thresholds.schema.json`](esquemas/thresholds.schema.json) | Registro de umbrales | [`umbrales.json`](registros/umbrales.json) | 0 | 4 |
| [`tool-registry.schema.json`](esquemas/tool-registry.schema.json) | Registro de herramientas y proveedores | [`herramientas.json`](registros/herramientas.json) | 0 | 1 |
| [`traceability.schema.json`](esquemas/traceability.schema.json) | Trazabilidad de requisitos y protocolos de validación | [`trazabilidad.json`](registros/trazabilidad.json) | 0 | 1 |
| [`vector-index-status.schema.json`](esquemas/vector-index-status.schema.json) | Estado de un índice vectorial | — | 2 | 2 |
<!-- generado:fin inventario-contratos -->

## Convenciones

- **Nombres.** Los campos y los valores de enum están en inglés (son identificadores); títulos y descripciones, en español. Las marcas de tiempo son RFC 3339 con zona.
- **Ejemplo por definición.** Un archivo `Def.caso.json` valida contra `$defs/Def` de su esquema; por ejemplo, `ejemplos/validos/common/User.revisor.json`.
- **Ejemplo inválido:**

  ```json
  {"descripcion": "…", "error_esperado": {"keyword": "required", "ruta": "/attributes"}, "instancia": {…}}
  ```

  - El ejemplo pasa la comprobación solo si falla con esa palabra clave en esa ruta y sin errores fuera de ella.
  - `keyword` puede ser también `registry` o `semantic`: el esquema debe pasar y fallar la comprobación semántica (registro de nombres, umbrales, catálogo, autoaprobación, hashes o métricas de trayectoria).
- **Mutaciones de registros.** En lugar de `instancia`, un ejemplo inválido puede declarar `base` (un archivo de `registros/`) y `parche` (RFC 6902: `add`, `replace` o `remove`). Las rutas admiten selectores `[clave=valor]`; por ejemplo, `/thresholds/[id=SH-01]/source`.
- **Añadir un contrato:**
  1. Crear el esquema en `esquemas/` y registrarlo en `manifest.json`.
  2. Añadir al menos un ejemplo válido y uno inválido.
  3. Si es un registro, añadir la instancia y su par en `manifest.json`.
  4. Ejecutar `validate_contracts.py --write` para regenerar las tablas.
- **Mover la instantánea OTel:**

  ```bash
  python3 ../herramientas/extract_semconv.py --genai-commit <SHA> --core-tag <vX.Y.Z> --out vendor/otel-semconv-genai-<SHA7>.json
  ```

  Después se actualizan `pinned` en `registros/semconv.json` y el SHA-256 en `manifest.json`.

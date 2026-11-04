# Parte 3 · Biblioteca de medios y activos

> La Biblioteca es la sección del panel donde se guardan, inspeccionan, buscan, versionan y auditan todos los activos de la cadena: feeds de video crudos y procesados, transcripciones, análisis, prompts y estado de los índices vectoriales.
> Contratos: [`asset`](contratos/esquemas/asset.schema.json), [`chunk`](contratos/esquemas/chunk.schema.json), [`vector-index-status`](contratos/esquemas/vector-index-status.schema.json), [`quality-report`](contratos/esquemas/quality-report.schema.json) y [`search`](contratos/esquemas/search.schema.json).

<a id="que-es"></a>
## 3.1 Qué guarda y qué no

El «feed de video crudo» del sistema **no es un archivo de video**. YouTube bloquea la IP del VPS con el bot-check, las URL de googlevideo solo sirven en la red que las genera y sus condiciones de uso no permiten descargar. Por eso la Biblioteca modela el video como una **referencia con metadatos versionados**. El contrato admite almacenamiento local u objeto para medios futuros sin romperse; un video de YouTube, en cambio, solo puede ser `reference` (lo exige el esquema).

| Tipo (`kind`) | Qué es | Almacenamiento | Visibilidad | Estado hoy |
|---|---|---|---|---|
| `video` | Referencia a YouTube: título, fecha, duración, short, pistas de audio | `reference` (URL) | `public_source` | 35 videos en `state.sqlite` |
| `audio` | Audio temporal para retranscribir, solo si algún día existe la ruta por proxy | `local`, **≤ 7 días** | `restricted` | No existe |
| `transcript` | Transcripción `es` con segmentos `{start, dur, text}` | `local` (`transcripts/<canal>/<fecha>_<id>.json`) | `internal` | 35, todas válidas |
| `analysis` | Análisis de narrativas validado | `local` (`analysis/<canal>/…`) | `internal` | 32 válidos |
| `chunk_set` | Chunks semánticos de una versión de transcripción | `local` (panel.sqlite) | `internal` | Fase 3 |
| `vector_index` | Índice de embeddings | `local` (sqlite-vec) | `internal` | `not_provisioned` |
| `prompt`, `schema`, `instructions` | Versiones de prompt, esquema e instrucciones de Scheduled | Repositorio o panel | `restricted` | 1 prompt v1.0.0 y 1 esquema; instrucciones 1.3 |
| `receipt` | Comprobantes de ejecución del agente | `local` (copia del puente) | `restricted` | 9 en `bridge/cache` |

La Biblioteca es un **catálogo**: el contenido se queda donde lo escriben los servicios y `panel.sqlite` guarda identidad, versiones, linaje y calidad. No hay copia duplicada que se pueda desincronizar.

<a id="modelo-activos"></a>
## 3.2 Modelo de activos y linaje

- **Identidad estable:** `<tipo>:<clave natural>`; por ejemplo, `transcript:agFTCuv80XE` o `prompt:narrative-analysis`.
- **Versión:** el SHA-256 del contenido, de modo que dos versiones iguales son la misma.
- **Procedencia** de cada versión:
  - proveedor y modelo, con `model_verified`;
  - hashes de prompt, esquema y transcripción;
  - `job_id` y modo de importación;
  - idioma y tipo de pista;
  - commit de código.

```text
video:ID ──derived_from──► transcript:ID@sha ──derived_from──► analysis:ID@sha ──published_as──► sitio /analysis/…
                                 │                                  ▲     ▲
                                 │                                  │     └─ validated_by ── schema:narrative-analysis@7b88e0b7…
                                 │                                  └─ produced_by_job ── job_id = video_id__sha256(meta)
                                 └──► chunk_set:ID@sha ──indexed_in──► vector_index:transcripts-es
prompt:narrative-analysis@082e5acb… ─┐
schema:narrative-analysis@7b88e0b7… ─┴─► entran en meta del trabajo → cambian el job_id si cambian
```

Ejemplos reales validados por el CI:

- [`video-referencia.json`](contratos/ejemplos/validos/asset/video-referencia.json);
- [`transcripcion-local.json`](contratos/ejemplos/validos/asset/transcripcion-local.json), con la versión `fd6c08da…` de `OwrAjFdTQ4s`, obtenida con Supadata;
- [`analisis-api.json`](contratos/ejemplos/validos/asset/analisis-api.json), con el análisis `b580749d…` de gpt-6.1-sol.

<a id="almacenamiento"></a>
## 3.3 Almacenamiento y retención

| Activo | Dónde vive | Tamaño hoy | Crecimiento estimado | Retención |
|---|---|---|---|---|
| Transcripciones y versiones archivadas | `/var/lib/cryptoreport-transcripts/transcripts/`, `transcript-versions/` | 7,0 MB en total con los análisis | ≈ 0,2 MB por video con su análisis; a 5–10 videos al día, menos de 1 GB al año | Todas las versiones |
| Análisis y versiones archivadas | `analysis/`, `analysis-versions/`, `_rechazados/` | (incluido arriba) | (incluido arriba) | Todas las versiones |
| Copia publicada | `/var/www/cryptoreport/analysis/` | 1,7 MB el sitio | Proporcional | La vigente |
| Catálogo, chunks y embeddings | `panel.sqlite` (más sqlite-vec en la Fase 3) | — | 1,5 KB por vector (384 floats); unos 8 chunks por video de media (532 s) y hasta unos 57 en el más largo (4104 s) | Mientras exista la versión |
| Audio temporal (si existiera) | `audio/` | — | ≈ 17 MB por video de 18 min | **7 días máximo** (el esquema lo exige) |

Copias: `sqlite3 .backup` diario de las tres bases y `tar` de `transcripts/` y `analysis/`, 14 días en local. La copia externa queda pendiente de decisión (supuesto D-08). Se ensaya cada mes (PV-12).

<a id="versionado"></a>
## 3.4 Versionado

1. **Inmutabilidad.** Una versión nunca se modifica. Una transcripción recuperada crea una versión nueva y la anterior se archiva en `transcript-versions/<canal>/<id>__<sha>.json` (comportamiento actual de `recover_transcripts`).
2. **Puntero vigente.** `current_version` apunta a una sola versión; las demás quedan `superseded`.
3. **Efecto en cascada.** Una transcripción nueva cambia `transcript_sha256`. El análisis anterior deja de coincidir (`analysis_matches`), sale de la publicación (G-12) y el puente crea un trabajo nuevo; el anterior pasa a `superseded`. La Biblioteca lo muestra como una cadena de linaje rota y pendiente.
4. **Sin sobrescritura.** Un análisis distinto nunca reemplaza a otro válido: el trabajo pasa a `conflict` (G-09) y lo decide una persona.
5. **Lápidas.** «Borrar» es `tombstoned` con motivo, auditado. El contenido sale de la publicación y la huella se conserva. Una versión con feedback o eventos de auditoría que la citen no pierde su huella nunca.
6. **Cuarentena.** `quarantined` es una lápida reversible: `quarantine_asset` y `release_asset`, que requiere 2.ª persona. `site.py` y `build_data.py` leen `quarantine.json` y excluyen esas versiones.

<a id="inspeccion"></a>
## 3.5 Inspección

| Inspector | Qué muestra | Origen |
|---|---|---|
| Transcripción | Línea de tiempo de segmentos con huecos y cobertura; superposición del informe de calidad (DQ-T-*); pista e idioma; proveedor e intentos | Documento, `quality.assess`, tabla `attempts` |
| Análisis | Tesis, afirmaciones por tipo y postura; cada evidencia salta a su segmento (reutiliza el visor del sitio); estado del validador por familia; procedencia completa | Documento, `meta`, evaluaciones |
| Diferencias | Entre dos versiones: por segmentos en transcripciones y por puntero JSON en análisis | `GET /library/assets/{id}/diff` |
| Procedencia | Ficha con proveedor, modelo (verificado o no), prompt, esquema, `job_id`, comprobante y commit | Versión y linaje |
| Comprobante | Trabajos intentados y subidos, errores, duración y conformidad con las instrucciones (AP-04) | `run-record.external` |
| Índice | Estado, recuentos, frescura y calidad (recall@10 y nDCG@10) | `vector-index-status` |

<a id="busqueda"></a>
## 3.6 Búsqueda léxica, semántica e híbrida

| Modo | Motor | Disponible | Notas |
|---|---|---|---|
| `lexical` | SQLite FTS5 (`unicode61 remove_diacritics 2`) sobre segmentos, títulos y afirmaciones | Fase 2 | «dias» encuentra «días». Respuesta en milisegundos con este volumen |
| `semantic` | Embeddings locales `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dimensiones, multilingüe, CPU, ONNX mediante fastembed 0.9.0) y `sqlite-vec` 0.1.9 | Fase 3 | Sin API de pago. El modelo se carga en un trabajo aparte, `cr-embed` (oneshot, `MemoryMax=768M`, `nice 19`), nunca en el proceso del panel |
| `hybrid` | Fusión RRF (k = 60) de los dos rankings | Fase 3 | Modo por defecto cuando el índice está listo |

Reglas del contrato [`search`](contratos/esquemas/search.schema.json):

- Si se pide `semantic` o `hybrid` y el índice no está `ready`, se responde en modo léxico con `degraded_from` y el estado real del índice. La interfaz lo dice («búsqueda por palabras: el índice semántico no está listo»).
- Por defecto se excluyen las versiones en cuarentena y cada resultado muestra su veredicto de calidad.
- La búsqueda semántica no se activa en la interfaz hasta que recall@10 llegue a 0,8 y nDCG@10 a 0,7 sobre un conjunto etiquetado de al menos 30 consultas (DQ-E-04 y DQ-E-05). Se sigue el mismo patrón que la evaluación de búsqueda de botRepos.

<a id="indice-vectorial"></a>
## 3.7 Estado del índice vectorial

```text
not_provisioned ──build──► building ──ok──► ready ──transcripción nueva──► stale ──rebuild──► building
                               │                 └──errores > 0──► degraded
                               └──fallo──► failed ──rebuild──► building
```

Construcción y frescura:

- Chunks con `segment_window` v1.0.0: 300 tokens de objetivo, 512 de máximo y 1 segmento de solape, sin partir segmentos (DQ-C-01 a DQ-C-06).
- Vectores normalizados para distancia coseno (DQ-E-02).
- Reindexado incremental por cambio de `transcript_sha256`, con un retraso máximo de 30 min (DQ-E-03).
- Reconstrucción completa con la intervención `rebuild_vector_index`, ejecutada por `cr-embed` a `nice 19` y fuera de los ciclos del extractor. El índice anterior sirve hasta el cambio atómico.
- El modelo ocupa unos 500 MB mientras corre. Es memoria transitoria, fuera del presupuesto permanente de 1 GiB (RS-01); PV-09 mide su pico.

Hoy el estado es `not_provisioned` ([ejemplo](contratos/ejemplos/validos/vector-index-status/no-provisionado.json)). Al encenderlo, [`listo.json`](contratos/ejemplos/validos/vector-index-status/listo.json) es la forma objetivo.

<a id="auditoria-biblioteca"></a>
## 3.8 Auditoría de la Biblioteca

| Acción | ¿Auditada? | Acción de auditoría |
|---|---|---|
| Leer metadatos y contenido `internal` | No: es contenido público transformado | — |
| Descargar contenido `restricted` (prompts, comprobantes) | Sí | `asset.export` |
| Crear una versión de prompt | Sí, con el hash de antes y de después | `asset.version_create` |
| Poner en cuarentena o liberar | Sí, con motivo | `asset.quarantine`, `asset.release` |
| Lápida | Sí, con motivo | `asset.quarantine` con estado `tombstoned` |
| Reconstruir el índice | Sí, como intervención | `intervention.request` y `intervention.execute` |

Los eventos van a la cadena de auditoría con hash encadenado (parte 4, §4.8): ninguna acción sobre un activo puede borrarse sin romper la cadena.

<a id="api-biblioteca"></a>
## 3.9 Contratos y API

| Operación | Ruta | Rol |
|---|---|---|
| Listar activos (tipo, canal, calidad, estado) | `GET /library/assets` | `viewer` |
| Ficha con versiones y linaje | `GET /library/assets/{asset_id}` | `viewer` |
| Contenido de una versión | `GET /library/assets/{asset_id}/versions/{version}/content` | `viewer`; auditado si es `restricted` |
| Diferencias | `GET /library/assets/{asset_id}/diff?from&to` | `viewer` |
| Informe de calidad | `GET /library/assets/{asset_id}/quality` | `viewer` |
| Búsqueda | `POST /library/search` | `viewer` (solo lectura) |
| Índices vectoriales | `GET /library/vector-indexes[/{index_id}]` | `viewer` |
| Cuarentena, liberación y reconstrucción | `POST /interventions` (`quarantine_asset`, `release_asset`, `rebuild_vector_index`) | Según el catálogo |

# Evaluación de integración del laboratorio de X

Evaluación realizada el 14 de octubre de 2026, hora de Bogotá. Alcance: inspección del código y evidencias locales, pruebas sin red y diseño de integración. No se activó ingesta, inferencia, servicios ni cambios de interfaz.

Actualización posterior autorizada: se implementaron la base operativa, el Feed de Urania y las correcciones de reauditoría. La ruta de modelos y las conexiones automáticas permanecen desactivadas. Estado de entrega y operación en [services/social/README.md](../services/social/README.md). El resto de este documento conserva la evaluación previa a esa implementación.

## Dictamen

**Reutilizar el colector y los criterios editoriales; no incorporar todavía el cruce semántico como servicio automático de producción.** El laboratorio tiene una base útil, pero su ruta de modelos contradice el requisito vigente de no consumir créditos de API, presenta un defecto reproducible de reauditoría y no tiene aún evaluación suficiente sobre relaciones reales.

La ubicación encontrada es `/root/lab/beincrypto-x`. Sus componentes principales son:

| Componente | Función | Decisión |
| --- | --- | --- |
| `collector.py` | Scraper.tech, normalización, paginación, límites y filtros UTC. | Reutilizar con adaptación operativa. |
| `ingest.py`, `accounts.json` | Ingesta de varias cuentas y ventanas por cuenta. | Integrar primero en modo de observación, una vez fijado el presupuesto de extracción. |
| `semantic_prompts.py`, `CRITERIOS-SEMANTICOS.md` | Relación entre una afirmación concreta y un post; abstención y límites. | Conservar como contrato editorial inicial. |
| `semantic.py` | Selección, juicio, auditoría, caducidad y resultados por video. | Corregir y adaptar antes de publicar conexiones. |
| `model_api.py` | Llamadas directas a Responses API. | Mantener desactivado bajo la restricción actual. No copiar sus credenciales. |
| Pruebas y evidencias | Fixtures del proveedor y evaluaciones guardadas. | Incorporar las pruebas pertinentes después de separar fixtures de datos operativos. |

No es todavía una propuesta de interfaz: es principalmente un módulo de extracción y enriquecimiento de afirmaciones. No está conectado al constructor móvil, al puente de Drive ni a un timer.

## Qué comprobé

El corpus `evidence/multi-account-live-network/corpus.json` contiene 186 IDs distintos, obtenidos en una ejecución del 14 de octubre a las 21:54 UTC:

| Cuenta | Ventana configurada | Posts | Solicitudes registradas |
| --- | --- | ---: | ---: |
| `beincrypto_es` | 4 días | 36 | 3 |
| `mattunchi` | 4 días | 37 | 3 |
| `VitalikButerin` | 15 días | 8 | 2 |
| `GranMag0` | 4 días | 105 | 7 |
| Total | Por cuenta | 186 | 15 |

Recalculé la pertenencia a las ventanas y comprobé el indicador de autor de los 186 registros. Es una comprobación del corpus y sus metadatos de proveedor, no una verificación independiente contra X. El propio corpus declara `coverage_complete=false`, correctamente.

Las **42 pruebas locales pasaron** con `socket.socket.connect` bloqueado. No leí archivos de credenciales, consulté endpoints, ejecuté evaluaciones con modelos ni hice nuevas llamadas pagadas.

La prueba real guardada en `work/agFTCuv80XE/matches.json` contiene:

- 25 afirmaciones originales; 24 elegibles y una excluida por evidencia/extracción insuficiente.
- 186 posts elegibles; cuatro lotes de selección y 34 pares candidatos.
- Diez aceptaciones preliminares, todas retiradas en la auditoría final: **cero conexiones publicables**.
- Estado `partial`, sin errores de API registrados; no equivale a una demostración de que no existan relaciones útiles.
- **13 llamadas registradas a `gpt-6.1-sol`, 99.412 tokens de entrada y 52.685 de salida**.
- **1.053,063 segundos acumulados de llamadas**, aproximadamente 17,6 minutos.

Estas cifras corresponden a esa prueba de un video, no a toda la facturación del laboratorio. Hay evaluaciones sintéticas adicionales. Los archivos no demuestran cuánto dinero se descontó ni el saldo restante.

La prueba real combina selección/juicio 1.0 con auditoría 1.1; no es una evaluación completa de recuperación con la versión 1.1. La prueba sintética estricta tuvo una aceptación correcta entre tres positivos esperados. Diez ejemplos no calibran precisión ni recuperación de producción.

## Hallazgos que bloquean la integración completa

### 1. La ruta semántica puede gastar aunque el sistema principal tenga su API desactivada

`model_api.py` lee `OPENAI_API_KEY` y llama directamente al proveedor. No consulta `CRA_ALLOW_API_ANALYSIS`, que protege al analizador principal. Copiar el módulo sin adaptar esa frontera introduciría una vía independiente de gasto.

**Requisito:** el nuevo componente debe respetar la prohibición global y rechazar la ejecución de modelos por API por defecto. Primero integrar ingesta/validación; el cruce requerirá un adaptador de trabajos y resultados al flujo de Drive existente. La capacidad y carga adicional de Scheduled se tendrán que probar por separado, sin quitar capacidad a la cola actual de videos.

### 2. Reauditoría: referencias antiguas pueden terminar aceptadas con fuentes actuales

En [`semantic.py`](/root/lab/beincrypto-x/semantic.py:302), el comando `audit` comprueba ID de video y caducidad, pero no exige que los hashes previos del análisis y corpus correspondan a las fuentes que se van a revisar. Después recalcula y asigna hashes actuales.

En [`audit_result`](/root/lab/beincrypto-x/semantic.py:243), se valida la nueva decisión, pero si coincide la relación se vuelve a aceptar el objeto original. Ese objeto conserva sus citas y explicación anteriores.

Reproducción sin red, con el modelo simulado de las propias pruebas:

1. Resultado anterior: cita de video «La propuesta sigue pendiente.» y cita de post «La decisión sigue pendiente.».
2. Fuentes actuales con los mismos IDs: propuesta aprobada.
3. Auditoría simulada válida: cita actual «Se aprobó la propuesta.» y relación coincidente.
4. Resultado: una conexión con `status=aceptado` que todavía conserva las citas antiguas.
5. Al volver a pasar ese objeto por la validación literal contra las fuentes actuales, falla con `cita_video_no_literal` y `cita_post_no_literal`.

Esto demuestra un caso posible, no que el resultado real guardado contenga conexiones defectuosas: el resultado real tiene cero conexiones.

**Requisito:** fijar hashes antes de evaluar; rechazar o regenerar trabajos ante cambios; validar tanto la aceptación previa como la revisada contra sus fuentes fijadas. Publicar únicamente un objeto final cuyas citas, explicación y límites hayan sido validados conjuntamente. Volver a validar en el importador del sistema principal. Añadir una regresión específica: los 42 tests actuales no detectaron este caso.

### 3. Falta operación incremental y control durable de presupuesto

El colector deduplica dentro de cada ejecución; `ingest.py` reconstruye ventanas completas y el cruce vuelve a examinar el corpus. Los límites de llamadas se reinician al crear otro proceso. No hay presupuesto diario/mensual persistente ni registro durable de qué pares ya se evaluaron.

**Requisito:** almacenar IDs/hashes y cursores de recuperación; descubrir nuevos posts desde la primera página con solapamiento; reevaluar solo fuentes cambiadas o pares nuevos. Un cursor histórico no sustituye el sondeo de novedades. Resolver conflictos de texto/autor antes de sobrescribir un ID.

Registrar cuotas de extracción y de análisis por separado. Quince solicitudes no significan quince créditos ni acceso gratuito: el laboratorio no verificó el descuento real de Scraper.tech. No instalar sondeo cada quince minutos por compartir la frecuencia del puente.

### 4. Falta cerrar publicación, caducidad y correspondencia con la fuente principal

El laboratorio acepta un archivo de análisis como entrada; no sustituye la puerta principal de validación y correspondencia con la transcripción. Escribe `matches.json` directamente, sin publicación atómica, y su limpieza ocurre al ejecutar `run` o `purge`.

**Requisito:** consumir exclusivamente análisis vigentes validados en el sistema principal; enlazar cada resultado a su hash y al de la transcripción; escritura temporal y reemplazo atómico; caducidad comprobada al importar, publicar y mostrar. El vencimiento durante la lectura también debe ocultar las conexiones.

Las ventanas de 3 o 15 días para videos son ejemplos del laboratorio. El catálogo principal de creadores no define esa vigencia: hace falta una configuración explícita, sin asignarla por intuición.

## Integración propuesta con CryptoReport

### Flujo

```text
Cuentas de X configuradas
          ↓
Colector acotado → validación UTC/autor/texto → corpus normalizado
                                                 ↓
Análisis vigente validado → trabajo de enriquecimiento con hashes fijados
                                                 ↓
                           Ejecutor autorizado, independiente de la cola de videos
                                                 ↓
                           Validador de pares + auditoría + caducidad
                                                 ↓
                           Adjuntos efímeros por afirmación
                                                 ↓
                           Urania: contexto externo en la cita correspondiente
```

La API semántica permanece apagada. El adaptador a ejecución sin API es trabajo pendiente, no una capacidad ya instalada o garantizada.

### Dónde encaja cada pieza

1. Crear un servicio acotado, por ejemplo `services/social/`, con colector adaptado, configuración, validación y estado operativo. No hacer que el servicio de transcripciones trate posts como videos o fabrique transcripciones para ellos.
2. Utilizar `/var/lib/cryptoreport-transcripts/social/` para el corpus acotado y los metadatos, si se mantiene el almacenamiento actual. Puede comenzar con JSON y un registro pequeño para deduplicación/cuotas; no requiere una base de datos pesada nueva en el VPS.
3. Extender el puente con un tipo de trabajo separado. ID reproducible a partir de video/afirmación, hashes de análisis/transcripción/corpus, versión editorial y configuración. La cola existente y sus validadores permanecen independientes.
4. El resultado de enriquecimiento se almacena como un adjunto independiente del análisis. **No se modifica el JSON de análisis original, ni sus hashes, ni su estado de verificación.** El esquema principal es cerrado y no acepta directamente el resultado del laboratorio; además, sus relaciones no son idénticas: el laboratorio añade `actualizacion`.
5. Exportar adjuntos actuales fuera de las generaciones históricas `data/g/` del móvil. Un recurso reemplazable por video, con hashes de origen y caducidad, permite evitar versiones históricas de asociaciones. El índice principal puede referenciar su disponibilidad sin copiar las citas externas dentro de cada snapshot.
6. Leer ese adjunto bajo demanda desde la ficha o la afirmación; ocultarlo si no coincide con el análisis que la pantalla está usando. No mezclar una pantalla fijada a un análisis anterior con conexiones calculadas sobre otro.
7. Incorporar estado y contadores al panel de control: última ingesta por cuenta, límites, errores, retrasos, cuentas no consultadas, pares pendientes/rechazados/aceptados y caducidad. Una avería de X no bloquea publicación de videos ni el Radar existente.

### Presentación en Urania

En una afirmación, después de la cita del creador y su interpretación:

- **Apoyo declarado**, **Contrapunto**, **Actualización posterior** o **Contexto**, con texto que delimite la relación.
- Autor y cuenta de X, fecha del post, cita literal y enlace al original.
- Explicación breve del aporte y límites; indicar expresamente cuándo la información es posterior al video.
- Estado de cobertura si el cruce está incompleto. No mostrar un bloque vacío en cada tarjeta por obligación.

Las conexiones pueden complementar narrativas e insights, pero no se incorporan a los contadores de videos ni inflan el ranking de creadores con tesis. Los posts deben tener métricas separadas. La correspondencia entre una persona en YouTube y su cuenta de X requiere una asociación explícita; no contar ambos perfiles como corroboración independiente.

No convertir compartir ticker, tono o dirección de precio en una relación semántica. El Radar local existente no es el motor para establecer estos vínculos. Mantener el criterio editorial del laboratorio: significado y proposición concreta, sin cuotas de conexiones ni equivalencia entre publicación social y verificación factual.

## Secuencia recomendada

| Fase | Entrega | Condición para avanzar |
| --- | --- | --- |
| 1. Preparación | Corregir la reauditoría, unificar prohibición de API y definir contrato/hash/caducidad. | Regresiones nuevas y ningún camino de gasto implícito. |
| 2. Ingesta en observación | Colector incremental, presupuesto durable, corpus y salud por cuenta, sin adjuntos visibles. | Cuota/costo real de extracción conocidos y cobertura observada durante varios días. |
| 3. Piloto editorial | Pares reales vigentes etiquetados y ejecución sin API mediante adaptador validado. | Medición de falsos positivos, falsos negativos, abstención, latencia y carga sobre la cola actual. |
| 4. Integración visual acotada | Adjuntos validados en unas pocas afirmaciones de Urania. | Hashes, citas, fechas y caducidad comprobados; cero errores críticos observados en el conjunto revisado. |
| 5. Automatización | Programación propia, límites durables, alertas y apagado independiente. | Estabilidad operativa y presupuesto sostenible medidos, sin depender de llenar tarjetas. |

La meta editorial del laboratorio de precisión del 95 % sigue siendo una meta. No fijar un umbral de producción usando los diez ejemplos sintéticos ni presentar cero aceptaciones como precisión perfecta.

## Decisión concreta

La extracción sí merece trasladarse al sistema principal después de acotarla operativamente. El criterio editorial también es reutilizable. **La ejecución exhaustiva por API no encaja hoy con el presupuesto ni con la instrucción de no usarla.**

Recomiendo iniciar por las fases 1 y 2 cuando se autorice la implementación. La evaluación actual deja el laboratorio y los servicios principales sin cambios funcionales; solo incorpora este informe al repositorio local.

## Referencias locales

- [Documentación del laboratorio](/root/lab/beincrypto-x/README.md).
- [Resultados de ingesta y evaluaciones](/root/lab/beincrypto-x/RESULTADOS-MODULO.md).
- [Criterios editoriales](/root/lab/beincrypto-x/CRITERIOS-SEMANTICOS.md).
- [Colector](/root/lab/beincrypto-x/collector.py).
- [Cliente de modelos](/root/lab/beincrypto-x/model_api.py:53).
- [Puente principal](/root/cryptoreport/services/bridge/crbridge/core.py:66).
- [Constructor móvil](/root/cryptoreport/prototypes/movil/build_data.py).

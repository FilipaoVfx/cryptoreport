# Plan: Radar de posturas y fichas de menciones en Urania

Fecha: 14 de octubre de 2026. Estado: implementado en Urania y comprobado en la URL pública. [Informe y capturas de validación](validaciones/radar-urania/README.md).

## 1. Resultado que buscamos

Convertir la búsqueda de Urania en una entrada al análisis: al escribir `short`, `long` o una combinación con un activo, la persona descubre quién sostiene cada tesis, qué dijo, qué la respalda y qué podría invalidarla. Las narrativas y los insights conservan el protagonismo; el video es la fuente secundaria que permite comprobarlos.

La misma entrega incluye dos mejoras de las fichas de menciones: citas direccionales antes que neutrales e identidad visual de activos y creadores. Todo se calcula a partir de transcripciones válidas y análisis existentes, sin inferencia pagada al buscar.

## 2. Situación actual y problemas que hay que resolver

La búsqueda de `prototypes/movil/shared/core.js` compara texto; no distingue intención de consulta. Urania la presenta en `prototypes/movil/b4-urania/app.js` mediante `renderSearch`.

El ranking actual mide menciones, videos y autores. No equivale a posiciones de trading. Su ficha, `openFicha`, presenta primero afirmaciones analizadas y después fragmentos, ordenados principalmente por fecha. Hay además una inconsistencia: los fragmentos y las afirmaciones pueden usar filtros distintos, y una ficha sin coincidencias puede ampliar silenciosamente el alcance.

`prototypes/movil/build_data.py` cuenta menciones, pero conserva hasta tres fragmentos iniciales por activo y video. Una cita direccional posterior puede quedar fuera de la interfaz aunque los contadores indiquen que existe. Ordenar solo lo que ya se exporta no resuelve esta pérdida.

Los campos actuales `dir`, `pol`, `qPol` y `own` describen cosas diferentes y pueden discrepar. Hay ejemplos de acumulación en retrocesos con dirección bajista y tono alcista, así como bots largos declarados con tono neutro. No se deben convertir automáticamente en shorts o posiciones abiertas.

El índice inspeccionado durante esta planificación contiene 41 videos, 33 analizados y 630 afirmaciones. Son una fotografía de cobertura, no cantidades que deban fijarse en la interfaz. Los creadores y sus identidades se cargarán desde el catálogo vigente.

## 3. Experiencia móvil propuesta

### Entrada y búsqueda

1. La persona abre la búsqueda existente y escribe una consulta.
2. Un intérprete local reconoce intención, activo y restricciones explícitas. Los resultados pueden actualizarse con el debounce actual; el teclado solo se cierra al enviar o seleccionar un resultado, nunca mientras se escribe.
3. Una cabecera compacta confirma la interpretación: **Tesis bajistas · Todos los activos**, o **Tesis alcistas · Ethereum**. Permite corregirla.
4. Aparece un selector `Alcistas / Bajistas`, junto al período y creador activos. Cambiar de dirección conserva el activo y los filtros. El foco y el historial permiten volver a la vista anterior.
5. Las consultas ordinarias conservan la búsqueda actual. Si la intención o el ticker son ambiguos, se ofrecen opciones y resultados textuales; no se fuerza una postura.

| Consulta | Comportamiento esperado |
| --- | --- |
| `short` | Radar de tesis bajistas; posiciones short declaradas identificadas aparte. |
| `long` | Radar de tesis alcistas; posiciones long declaradas identificadas aparte. |
| `short ETH` | Mismo Radar limitado a Ethereum. |
| `long SOL` | Resolver Solana mediante el catálogo; pedir elección si existe otra coincidencia válida. |
| `shorts` | Búsqueda textual/formato de video; no activar automáticamente tesis bajistas. |
| `largo plazo` | Horizonte temporal; no implica posición long. |
| `cerró su short` | No presentar esa cita como una posición short abierta. |
| `no quiero short` | No activar el Radar por mera coincidencia de la palabra. |

### Tarjeta de activo

Cada tarjeta muestra logo, nombre y ticker; número de creadores con tesis de esa dirección; videos que las sustentan; fecha de la evidencia más reciente; narrativa principal y un insight existente enlazado a su análisis. Los números tienen etiquetas explícitas y no se mezclan con el total de menciones.

Ejemplo de estructura, sin inventar datos de producción:

> ETH · Ethereum  
> Tesis bajista · [N] creadores · [M] videos  
> Narrativa: [síntesis disponible en los análisis]  
> Última evidencia: [fecha]  
> Ver argumentos y fuentes

Al expandirla se muestran tesis, citas, contexto y condiciones de invalidación si constan en el material. Cuando no consten, se indica que no fueron especificadas. El enlace secundario **Escuchar la fuente** abre el video en el instante correspondiente cuando hay una marca temporal válida.

### Orden del Radar

Orden inicial determinista: creadores únicos con evidencia compatible, videos únicos y fecha de publicación más reciente; identificador canónico como desempate estable. La cabecera explica que se ordena por presencia entre las fuentes analizadas. Un creador con diez videos sigue contando como un creador.

Separar visualmente **Tesis direccional** de **Posición declarada**. Ofrecer un filtro de posiciones declaradas sin interpretar que son actuales: usar “Declaró un short el [fecha]”. Una compra spot, una simulación, una estrategia condicional o una posición atribuida a terceros no se etiquetan como un long ejecutado por el creador.

Las tesis opuestas siguen accesibles. Un activo con argumentos alcistas y bajistas no pierde uno de ellos por tener una única etiqueta agregada.

## 4. Ficha de menciones: orden y coherencia

Orden general solicitado, tanto en el ranking existente como en el detalle del Radar:

1. **Alcistas**.
2. **Bajistas**.
3. **Mixtas o condicionadas**, cuando no puedan separarse con fidelidad.
4. **Neutrales o sin dirección identificable**.

El Radar `short` puede abrir directamente la sección bajista, manteniendo el orden general de secciones y una navegación visible hacia los argumentos contrarios. Las neutrales permanecen al final.

Dentro de cada grupo: publicación más reciente, tiempo dentro del video e identificador estable. La categoría procede del significado de la afirmación y su contexto disponible, no solo de palabras aisladas. Una frase sobre caídas puede expresar una oportunidad alcista; el horizonte debe aparecer cuando esté identificado.

Las afirmaciones analizadas y los fragmentos de transcripción se agrupan por dirección conjuntamente. Cada elemento lleva su procedencia: **Afirmación analizada** o **Fragmento detectado**. Así una cita neutral analizada no queda por encima de otra direccional solo por pertenecer a otro bloque.

Reglas obligatorias:

- Aplicar los mismos filtros de activo, creador y período a tarjetas, contadores, afirmaciones y fragmentos.
- No ampliar silenciosamente los filtros ante un resultado vacío. Mostrar el estado vacío y una acción explícita para ampliar.
- Evitar duplicados cuando una afirmación y un fragmento remitan al mismo pasaje. Conservar las referencias necesarias para abrir su contexto.
- Distinguir **menciones totales**, **afirmaciones** y **fragmentos mostrados**. Una muestra no se anuncia como la totalidad.
- Mostrar cita, autor, fecha y procedencia; marcar cuando falte una referencia temporal.
- Ofrecer “Ver más” mediante detalles del activo/video, sin descargar todas las transcripciones al abrir el ranking.

## 5. Contrato de datos y clasificación

Crear una proyección derivada y versionada para el Radar. Mantener los análisis originales y su esquema como fuente; no reescribirlos para adaptar la interfaz.

Cada evidencia derivada necesita:

| Campo | Propósito |
| --- | --- |
| `asset_id`, `creator_id`, `video_id`, `claim_id` | Identidad y trazabilidad. |
| `published_at`, `timestamp`, `segment_ids` | Fecha y localización del pasaje, cuando existan. |
| `thesis_direction` | Alcista, bajista, mixta, neutral o desconocida. |
| `position_side` | Long, short, otra o desconocida, solo con evidencia explícita. |
| `position_status` | Declarada en esa fecha, cerrada, condicional, hipotética o desconocida. |
| `speaker_role` | Creador o tercero citado. |
| `horizon`, `conditions`, `invalidation` | Información presente en el análisis; ausencia explícita cuando falte. |
| `quote`, `source_kind` | Texto literal y procedencia analizada/detectada. |
| `transcript_hash`, `analysis_version`, `classifier_version` | Reproducibilidad y descarte de datos obsoletos. |

No basta con `own=true` ni con un tono bajista para declarar un short. La clasificación local debe ser conservadora: ante ambigüedad, **desconocida**. La confianza de extracción no se convierte en probabilidad de que la tesis se cumpla.

Primero auditar qué campos pueden recuperarse del análisis existente. Si faltan, conservar la limitación; una futura revisión del prompt del Schedule se plantea como tarea separada y versionada, sin exigir reanalizar el histórico para lanzar esta mejora.

### Recuperar citas que hoy se pierden

Modificar el constructor para identificar candidatos en todo el video válido, deduplicar ventanas solapadas y conservar una muestra representativa por dirección. El índice incluye solo resúmenes y unas pocas referencias; los detalles contienen las evidencias adicionales necesarias para “Ver más”. El tamaño de página se fija tras medir con el histórico real.

Todo registro conserva vínculo con la transcripción y su hash. Aplicar las puertas de calidad y correspondencia de análisis existentes antes de generar el Radar. Un video sin transcripción válida no aporta resultados.

### Tiempo y actualización

Unificar la definición de período antes de implementar: filtros como “últimas 48 h” usan la hora actual en UTC y muestran la fecha de corte. Si se ofrece una ventana histórica anclada al último dato disponible, se etiqueta como tal. Evitar que una fecha antigua del índice parezca “hoy”.

Cada reconstrucción del conjunto móvil regenera el índice de posturas y sus detalles con una versión común. Publicar el conjunto completo de forma atómica, o mediante un manifiesto versionado, para evitar mezclar contadores nuevos con citas antiguas. La búsqueda local no depende de que el Schedule esté ejecutándose en ese instante.

## 6. Logos y fotos de perfil

Crear un catálogo de identidad para activos y otro para creadores, con resolución por identificador canónico. Un ticker por sí solo no resuelve colisiones ni palabras comunes.

- Cripto: logo verificado del proyecto y su identificador de catálogo.
- Bolsa: logo de la compañía, con mercado y ticker.
- Índices y macro: símbolo o pictograma adecuado; no asociar un índice al logo de una empresa que lo integra.
- Creadores: avatar asociado al ID verificado del canal de YouTube.

Los recursos oficiales de YouTube exponen miniaturas del canal en `snippet.thumbnails`; su disponibilidad en la integración existente debe comprobarse antes de elegir ese adaptador. Fuente: [documentación de canales de YouTube](https://developers.google.com/youtube/v3/docs/channels).

Para activos, priorizar recursos oficiales o un catálogo cuyas condiciones permitan ese uso. CoinGecko es un adaptador posible, sujeto a cuotas y atribución; no una nueva dependencia obligatoria. Referencias: [metadatos y logos de CoinGecko](https://www.coingecko.com/learn/how-to-fetch-crypto-logos-and-metadata-with-python) y [guía de atribución](https://brand.coingecko.com/resources/attribution-guide).

Cada entrada registra ruta/URL, procedencia, fecha de verificación y requisitos de atribución conocidos. Almacenar o servir copias solo cuando lo permitan las condiciones de la fuente. No generar logos ni rostros con IA.

La obtención y renovación se hacen fuera de la búsqueda. Reutilizar infraestructura y conexiones disponibles; una imagen ausente usa iniciales o un símbolo local. No requiere Supabase ni una nueva API pagada para la primera entrega. Una futura migración de almacenamiento debe conservar este contrato.

Validar HTTPS, origen permitido, tipo de contenido y tamaño al importar imágenes; impedir descargas arbitrarias desde URLs del contenido analizado. Un fallo de imagen nunca bloquea el ranking.

Diseño: activos de 32–40 px, creadores de 24–28 px junto a las citas y avatar ampliado de 48–56 px en su detalle. Reservar dimensiones para evitar saltos; carga diferida fuera de pantalla; texto alternativo útil sin repetir nombres cuando la imagen sea decorativa.

## 7. Lenguaje visual y accesibilidad

Conservar el dark glassmorphism de Urania: capas oscuras translúcidas, bordes suaves y color direccional contenido. Las citas deben leerse sobre una superficie suficientemente opaca. Verde/rojo se acompañan siempre de etiquetas y símbolos.

Una narrativa breve ocupa la jerarquía principal de cada tarjeta; las métricas y el video quedan debajo. Evitar una pared de chips. Las identidades visuales facilitan reconocer activos y autores sin sustituir sus nombres.

Comprobar anchos de 320, 375, 390 y 430 px; objetivos táctiles de al menos 44 px; navegación por teclado, foco al abrir/cerrar fichas, lector de pantalla y reducción de movimiento. No desplazar el foco mientras se actualizan resultados escritos.

Objetivo a medir: resultados locales fluidos tras el debounce, sin nuevas llamadas de modelo; imágenes fuera del camino crítico. Establecer presupuestos de peso y latencia con una medición inicial antes de prometer cifras de rendimiento.

## 8. Secuencia de ejecución

| Fase | Trabajo y entregable | Dependencia / salida verificable |
| --- | --- | --- |
| 1. Auditar datos | Revisar discrepancias de dirección/tono/posición y referencias por activo. Definir reglas y casos límite. | Ejemplos etiquetados y contrato de proyección aprobado técnicamente. |
| 2. Preparar evidencias | Proyección versionada; muestreo por dirección; detalles bajo demanda; actualización coherente. | Citas recuperables y exclusión de transcripciones inválidas. |
| 3. Corregir ficha | Grupos alcistas → bajistas → mixtos → neutrales; filtros consistentes y deduplicación. | Contadores y contenido coinciden en cada filtro. |
| 4. Incorporar identidades | Catálogos, importación permitida, caché y fallback; logos y avatares en tarjetas/citas. | Ficha usable también sin imágenes o con errores de red. |
| 5. Construir Radar | Intérprete local, tarjetas, selector de dirección, rutas y apertura contextual. | Consultas reconocidas y búsqueda ordinaria conviven. |
| 6. Verificar móvil | Pruebas de reglas y recorrido en navegador; rendimiento y accesibilidad. | Evidencia de los escenarios de aceptación. |
| 7. Publicar | Activación acotada a Urania; reconstrucción del conjunto y comprobación en URL pública. | Acceso desde sesión nueva y dispositivo móvil; reversión disponible. |

Las fases 3 y 4 pueden coordinarse después de estabilizar los contratos. El Radar depende de evidencias correctas; no debe adelantarse a ellas. La publicación se limita a Urania en la URL indicada en el informe de validación.

### Archivos previstos

- `prototypes/movil/build_data.py`: exportación de evidencias y proyección, respetando puertas de calidad.
- Un módulo específico de posturas junto al constructor, si la lógica excede una función pequeña; no sobrecargar las reglas de tono.
- Catálogos de identidad en una ubicación versionada del proyecto, con campos documentados.
- `prototypes/movil/shared/core.js`: helpers aditivos de consulta/carga; preservar consumidores existentes.
- `prototypes/movil/b4-urania/app.js` y `app.css`: Radar, ficha y presentación de identidades.
- Pruebas del constructor/intérprete y documentación del contrato y actualización.

Antes de editar, revisar los cambios locales concurrentes: estos archivos ya contienen trabajo en curso. No reemplazarlos íntegramente ni incluir modificaciones ajenas en el commit.

## 9. Criterios de aceptación

1. `short ETH` y `long ETH` encuentran tesis compatibles sin llamadas de inferencia; cambiar dirección conserva activo y filtros.
2. `shorts`, negaciones, posiciones cerradas y referencias a terceros no producen posiciones abiertas falsas.
3. “Acumular en retrocesos” no se convierte en short. Una advertencia de riesgo dentro de un long declarado no cambia por sí sola el lado de esa declaración.
4. Una tesis con caída a corto plazo y subida a largo plazo conserva ambos horizontes, si están documentados.
5. Ninguna cita neutral aparece por encima de los grupos alcista/bajista en la ficha general, aunque esté analizada y las otras sean fragmentos detectados.
6. Los filtros de creador y período afectan por igual a resultados, cifras y evidencias. Un estado vacío no muestra material fuera del filtro.
7. Una cita direccional posterior a los tres primeros fragmentos puede recuperarse. Las muestras y totales están correctamente etiquetados.
8. Una misma fuente no duplica autores ni repite el mismo pasaje como dos citas independientes.
9. Cada conclusión remite a una evidencia identificable; invalidaciones e insights ausentes no se inventan.
10. Las imágenes faltantes, corruptas o lentas dejan una ficha legible sin saltos de disposición.
11. Un análisis obsoleto respecto del hash de su transcripción no participa. Un video sin transcripción válida no aparece como evidencia.
12. Al publicar nuevos análisis, Radar y fichas muestran la misma versión de datos sin reconstrucción manual adicional.
13. Las vistas funcionan en móvil, con teclado y movimiento reducido; las fuentes siguen siendo secundarias pero accesibles.
14. La URL pública de Urania funciona desde una sesión nueva sin depender de cookies de este entorno.

## 10. Costos, alcance y cierre

Buscar, ordenar, filtrar y presentar evidencias consume cómputo local del sistema existente; no consume los USD 5 de créditos de modelos. El análisis de nuevos videos sigue dependiendo del flujo de transcripción, Schedule e importación ya definido. Este cambio no garantiza su cobertura ni sustituye su supervisión.

Las imágenes añaden almacenamiento y transferencia; comenzar con fuentes permitidas y caché acotada, medir el uso y conservar fallback. No introducir servicios de pago para completar esta entrega.

La entrega cubre Radar, fichas e identidades en Urania. El duelo completo de tesis y la bitácora histórica de cambios quedan para una fase posterior. Se considera terminada cuando las pruebas anteriores pasen sobre datos reales, la documentación permita mantener la actualización y la comprobación pública confirme el resultado.

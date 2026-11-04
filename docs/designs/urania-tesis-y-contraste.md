# Urania: menos repetición, más tesis y contraste

> **Ajuste posterior del usuario:** el ranking se ordena por videos, sin selector de orden, y vuelve a destacar menciones alcistas frente a bajistas. Las tesis son contexto secundario y no determinan la posición. Ver [regla vigente](urania-ranking-menciones.md).


Generado mediante gstack office-hours el 15 de octubre de 2026.  
Repositorio: CryptoReport. Rama observada: `ccr-054ca714-2ds4wh`.  
Estado: **premisas aprobadas; propuesta de implementación para Claude**.  
Alcance de esta entrega: planificación. No se implementó esta reorganización.

## 1. Objetivo y evidencia de uso

El usuario quiere obtener una conclusión rápida del contenido que antes consumía
en videos y descubrir convergencias y desacuerdos entre creadores. Explora
especialmente altcoins por el número de creadores y tesis alrededor de ellas.
Los posts de X deben contribuir al contraste.

Recorrido descrito por el propio usuario:

`Diario → elegir video con información → Destilado → Qué vigilar / Escenarios → ranking de altcoins → Feed`.

Destilado empieza con fragmentos de transcripción y se siente ruidoso. Escenarios
y Qué vigilar fueron las secciones identificadas como más útiles. El usuario
percibe duplicidad entre las restantes presentaciones del análisis.

Esto es evidencia de uso del propietario del producto y feedback relatado por él.
No tenemos mediciones de retención, clientes que paguen ni observaciones directas
de otros usuarios. No presentar esta conversación como validación de mercado.

### Premisas aprobadas

1. Descubrir activos que concentran más creadores y tesis diferentes.
2. Comprender rápidamente una tesis, sus escenarios, condiciones y señales.
3. Contrastar apoyos, objeciones y matices de videos y posts con acceso a evidencia.

La frase «infraestructura cripto como ola actual o siguiente» es un ejemplo
aportado por el usuario. No es una tesis que este documento dé por verificada
ni un análisis real atribuido a un creador.

## 2. Alternativas consideradas y recomendación

| Enfoque | Cambios | Ventaja | Límite y riesgo | Esfuerzo orientativo |
|---|---|---|---|---|
| A. Simplificar el detalle de video | Sustituir Destilado por una lectura breve, relegar análisis completo y texto | Menor cambio; mejora pronto el recorrido observado | Mantiene la comparación entre fuentes como trabajo manual; cubre solo parte del objetivo | Equipo humano: 2–4 días; agente: 1–2 sesiones con QA |
| B. Conectar el recorrido actual mediante tesis | Lectura breve, ranking por creadores, ficha del activo por tesis y posts relacionados; mantener Diario y Feed | Conserva hábitos y conecta descubrimiento, comprensión y contraste | Necesita una proyección de tesis explícita y transparente sobre cobertura; riesgo medio | Equipo humano: 1–2 semanas; agente: 4–6 sesiones por etapas con QA |
| C. Portada editorial de pocas tesis | Abrir con un boletín de tesis priorizadas y rutas secundarias hacia archivo y activos | Lectura diaria muy breve | Mayor cambio de hábito; priorización editorial puede ocultar activos que el usuario busca; exige selección recurrente | Equipo humano: 2–3 semanas; agente: 6–8 sesiones y observación de usuarios |

**Recomendación: B, empezando por la mejora de lectura de A.** El usuario ya
encadena Diario, ranking y Feed. Conectar esas entradas tiene más respaldo en su
uso que reemplazarlas por una portada nueva. Las estimaciones son de planificación,
no compromisos de entrega; Claude debe ajustarlas tras inspeccionar el checkout.

La aprobación recibida corresponde a las premisas y a preparar este planning.
No se registra como una aprobación explícita de cada detalle visual o técnico.
No se hizo investigación externa de competidores ni revisión externa mediante API.

## 3. Alcance y límites

- Mantener aplicación móvil, identidad oscura y cristal, imágenes de activos y creadores.
- Mantener las tres entradas existentes: **Explorar, Diario y Feed**.
- Mantener mercados Altcoins, Macro y Bolsa; la prioridad de validación es Altcoins.
- Cambiar jerarquía y conectar información existente. No migrar a otro framework.
- No reanalizar videos ni cambiar el system prompt o su esquema para adaptar la UI.
- No habilitar APIs de inferencia. La autorización excepcional del lote del 15 de octubre ya terminó.
- No ejecutar nuevos análisis semánticos pagados, comprar créditos ni cambiar modelos o Schedule.
- No alterar extracción, proveedores, OAuth, transporte Drive, timers ni funcionamiento del monitor.
- No introducir Supabase, embeddings, vector DB, cuentas de usuario o servicios recurrentes.
- No añadir otra pestaña principal para albergar lo que ya existe en otra.
- Conservar los originales y la trazabilidad; retirar duplicidad de presentación.

El fallo Windows de Schedule es un asunto operativo separado. Este plan no lo
resuelve y no debe depender de resolverlo para mejorar la lectura de los datos
ya publicados.

## 4. Experiencia propuesta

### 4.1 Diario: encontrar contenido por su aporte

Mantener cronología y filtros. Cada tarjeta conserva creador, título, fecha y estado.
Añadir, cuando existan, una frase de tesis y activos relevantes derivados de un
análisis válido. La duración del video y el volumen de palabras no determinan
calidad o prioridad. Una miniatura pequeña es suficiente.

La acción principal es **Leer síntesis**. Un video sin análisis muestra el estado
real y acceso al material disponible; nunca una síntesis fabricada desde el título.
Un video sin transcripción válida permanece excluido del contenido utilizable.

### 4.2 Detalle de video: Síntesis como primera lectura

Reemplazar la entrada predeterminada Destilado por **Síntesis**. Mostrar, en orden:

1. **Qué plantea:** tesis explícita del creador; idealmente dos frases visibles.
2. **Escenarios:** los escenarios existentes, con mecanismo, horizonte y condición.
   Mostrar los del creador primero; los del analista llevan atribución inequívoca.
3. **Qué vigilar:** señales y condiciones existentes con activo, plazo, origen y
   fuente cuando consten. Mostrar inicialmente hasta tres; «Ver todas» conserva el resto.
4. **Contrastar esta tesis:** activos y tesis relacionados, con otros autores o posts
   solo cuando haya vínculos válidos. Si no existen, indicarlo sin inventarlos.

Hasta dos escenarios visibles inicialmente; no descartarlos del archivo por ese
límite. Cada bloque permite ampliar su contenido sin truncar condiciones o negaciones.
Preferir párrafos y listas breves a ocho carruseles de tarjetas equivalentes.

La síntesis reutiliza campos de `analysis.resumen`, `analysis.escenarios` y los
apartados ya usados en Qué vigilar. Si no existe una frase breve segura, mostrar
el texto original con expansión. No generar una conclusión nueva por heurística
ni recortar una frase donde cambie su significado.

Un mismo escenario puede contener sus señales e invalidación. Qué vigilar resume
solo lo necesario para seguirlo y remite al escenario, evitando copiar el bloque
entero. No fusionar condiciones diferentes por compartir palabras.

**Profundización:** «Análisis completo», «Fuentes y texto» y «Escuchar / ver fuente».
Ahí permanecen cadena del argumento, técnicas, ocho aspectos, preguntas abiertas,
límites, citas y transcripción. El reproductor conserva el salto temporal y no
interrumpe la lectura con reproducción automática.

### 4.3 Explorar: ranking por conversación analizada

Mantener ranking y Narrativas, renombrando esta última a **Tesis** únicamente
cuando exista una proyección que cumpla el contrato de la sección 6.
La pestaña global **Insights** deja de ser una tercera vista equivalente.

Orden predeterminado de activos, con idénticos filtros de creador y periodo:

1. Creadores únicos con afirmaciones analizadas relevantes para ese activo, descendente.
2. Tesis distintas aceptadas y vinculadas explícitamente al activo, descendente.
3. Fecha de publicación más reciente de una evidencia elegible.
4. Identificador canónico del activo como desempate estable.

No ordenar primero por cantidad de videos o frases. Conservar esos modos como
opciones secundarias si aportan exploración; explicitar cuál está activo.

Una fila muestra imagen, nombre, símbolo, creadores y tesis con etiquetas claras.
«Tesis sin clasificar» representa cobertura desconocida, no cero tesis. Las
menciones de transcripciones sin análisis pueden aparecer como métrica separada,
sin convertirse en creadores que respaldan una tesis.

Definir relevancia de afirmación con activo explícito y atribución al creador.
No basta detectar un ticker en una cita incidental. Afirmaciones del analista o
citas atribuidas a terceros no se contabilizan como postura del creador sin
evidencia de adhesión. Ante identidad o atribución incierta, excluir del contador
de postura y conservar la fuente como contexto.

No mostrar una puntuación opaca de «confianza», probabilidad de acierto ni una
escala única que convierta popularidad en solidez. La cobertura es parte de la
lectura: «N creadores con análisis; clasificación de tesis parcial», cuando aplique.

### 4.4 Ficha del activo: tesis y contraste primero

La ficha actual de menciones evoluciona, conservando su entrada desde ranking y radar:

1. Identidad del activo, periodo activo y cobertura.
2. Lista breve de tesis aceptadas relacionadas; inicialmente hasta tres.
3. En cada tesis: conclusión atribuida, participantes, punto de coincidencia,
   desacuerdo concreto, escenarios y qué vigilar.
4. Publicaciones de X relacionadas, cuando aporten apoyo, objeción, actualización o contexto.
5. Todas las citas y menciones, accesibles al profundizar.

Los desacuerdos tienen un eje explícito: dirección, momento, alcance, mecanismo,
activo beneficiario o condición. «Infraestructura relevante» y «tokens caros»
pueden coexistir; no etiquetarlos como contradicción automáticamente. Una postura
bajista a corto plazo y alcista a largo plazo tampoco constituye una contradicción.

En el contraste de tesis, agrupar por relación: **Apoyos, Objeciones, Matices**.
Esto convive con la regla previamente solicitada para las citas direccionales:
**alcistas → bajistas → mixtas/condicionadas → neutrales**. Son dimensiones
diferentes; una objeción no es siempre bajista.

Cada tarjeta de fuente conserva autor, fecha, condición y acceso a su cita.
Si un creador participa en varios lados según el horizonte, marcar esa diferencia
y mostrar las evidencias correspondientes. El total de creadores es una unión de
identidades, no la suma de participantes de cada columna.

### 4.5 Feed: conservar entrada global y añadir contexto

Mantener Feed y sus filtros actuales. Desde una tesis o activo, abrir una vista
filtrada conservando un encabezado de contexto y una acción clara para volver al
Feed completo. El botón Atrás recupera posición, selección y filtros anteriores.

Mapear relaciones aceptadas existentes:

| Relación guardada | Presentación |
|---|---|
| `apoyo_declarado` | Apoya |
| `contrapunto` | Cuestiona |
| `actualizacion` | Actualiza; no implica confirmar |
| `contexto` | Contexto; no suma respaldo |

No traducir `contexto` automáticamente a «Matiza». Un matiz requiere una
interpretación aceptada que describa la condición o limitación real.

Solo una conexión semántica aceptada y vigente permite afirmar «apoya» o
«cuestiona». El mismo ticker o una etiqueta local solo permiten «menciona este
activo» o «contenido relacionado», en un bloque separado que no suma apoyos.

Aplicar los hashes y caducidades existentes. Una relación aceptada con una
afirmación no implica respaldo al video completo ni a todas sus tesis. Heredar
la relación a una tesis solo si su membresía validada conserva la misma afirmación,
alcance y posición; en otro caso, dejar la conexión al nivel de la afirmación.

Por defecto mantener publicaciones relevantes. Conservar texto original y fuente.
No convertir un post en verificación externa de una afirmación por estar relacionado.

### 4.6 Qué ocurre con Insights y otras vistas

| Elemento actual | Destino propuesto |
|---|---|
| Tono agregado, más alcista / bajista | Contexto secundario del ranking; evitar repetirlo como hallazgo |
| Diferencia título / contenido | Nota contextual del video, con evidencia y límites de la regla |
| Cambio de postura | Solo si se prueba mismo autor, activo y alcance comparable; caso contrario, contraste entre fuentes |
| Explicación «la macro se lee al revés» | Método accesible desde ayuda; no insight de actualidad |
| Destilado | Síntesis breve como entrada; transcripción anotada dentro de Fuentes y texto |
| Resumen y cadena del argumento | Tesis breve arriba; explicación extensa dentro de Análisis completo |
| Técnicas narrativas, ocho aspectos y límites | Profundización, con acceso a los límites relevantes desde cada afirmación |
| Búsqueda long / short | Conservar comportamiento y condiciones; enlazar al mismo detalle del activo |

No crear un motor nuevo de alertas o cambios temporales en esta fase. En la
inspección existe un contraste `kind=cambio` con `sameCreator=false`: es un caso
de prueba obligatorio para impedir atribuir un cambio personal entre autores distintos.

## 5. Datos actuales y código reutilizable

Base principal: `prototypes/movil/b4-urania/`.

| Archivo o área | Responsabilidad actual / uso en la propuesta |
|---|---|
| `app.js`: `renderLog`, `renderVideo`, `destiladoHtml`, `cardHtml`, `renderNotebook` | Reorganizar lectura y conservar profundización |
| `app.js`: `rankRows`, `rankList`, `heroCard`, `openFicha`, `renderThread` | Reutilizar ranking, ficha, filtros y trazabilidad |
| `app.js`: `renderFeed`, `renderSearch`, `radarHtml` | Mantener Feed y búsqueda, añadiendo contexto compatible |
| `index.html`, `app.css` | Conservar navegación y lenguaje visual; retirar vistas duplicadas |
| `radar.js`, `feed.js` | Reusar selección y filtros; evitar otra interpretación paralela de long/short |
| `../shared/core.js`, `../shared/player.js` | Rutas, carga y salto a fuentes; modificar solo si es necesario y compatible con otros prototipos |
| `prototypes/movil/build_data.py` | Publicación derivada, referencias y versiones; ampliaciones compatibles |
| `prototypes/movil/postures.py` | Atribución, condiciones y direcciones; no confundir tono con posición |
| `services/social/crsocial/semantic.py` y `scheduled.py` | Leer contratos de conexiones aceptadas; no ejecutar inferencia |
| `services/transcripts/crtranscripts/quality.py` | Reutilizar validación de transcripción y correspondencia de hashes |

El índice contiene `topics`, `themes`, `claims`, `contrasts` y `channels`.
Las afirmaciones tienen ID local al video: la clave es **video_id + claim_id**.
Los detalles de video se publican en una generación fijada por `detailBase`.
Los `themes` actuales son agrupaciones de temas: **no equivalen a tesis distintas**.

## 6. Contrato derivado de tesis y significado de los contadores

### 6.1 Separar tema, tesis y postura

- Tema: infraestructura cripto.
- Tesis: una proposición contrastable sobre ese tema, con alcance y horizonte.
- Postura de una fuente: apoya, cuestiona o condiciona esa proposición, con evidencia.
- Mención: aparece un activo; por sí sola no representa una tesis ni una adhesión.

No usar número de afirmaciones, temas o escenarios como número de tesis.
No agrupar tesis solo por palabras o similitud de títulos. Proposiciones que difieran
en condición, beneficiario o horizonte relevante conservan distinción explícita.

### 6.2 Primera versión viable sin nueva inferencia

Crear una capa derivada independiente del esquema de análisis. Nombres sugeridos:

- `prototypes/movil/theses.py`: proyección y validación deterministas.
- `prototypes/movil/metadata/theses.json`: definiciones editoriales y membresías aceptadas.
- `prototypes/movil/b4-urania/theses.js`: selectores puros compartidos por ranking y fichas, si aportan separación útil.

Las definiciones pueden ser reutilizables; aceptar una afirmación en una tesis
requiere una referencia concreta y revisable a su evidencia. Definiciones por
palabras pueden sugerir candidatos, pero esos candidatos no cuentan como tesis
aceptadas ni como apoyos.

Claude debe inspeccionar análisis existentes y preparar un conjunto pequeño de
tesis reales para validar el recorrido, indicando qué membresías son editoriales.
Si el ejemplo de infraestructura no está sustentado, mostrar su ausencia y usar
otro caso real. Los ejemplos sintéticos quedan exclusivamente en tests o laboratorio
identificado. No fabricar participantes para que una pantalla parezca completa.

No introducir mantenimiento manual como dependencia oculta de toda actualización.
Los análisis y rankings básicos siguen actualizándose automáticamente; la cobertura
de tesis aceptadas puede ser parcial. Mostrarla y dejar las afirmaciones no
clasificadas accesibles. No atribuir capacidades de agrupación semántica autónoma
al modo determinista. Automatizar la aceptación mediante Schedule es trabajo
posterior, con contrato y autorización propios; no es prerrequisito de esta entrega.

### 6.3 Campos mínimos de la proyección

| Entidad | Campos / reglas |
|---|---|
| Tesis | `id` estable, `version`, `definition_sha256`, proposición canónica, `topic_id`, mercados y activos explícitos, alcance, horizonte, condiciones y procedencia editorial |
| Membresía | `thesis_id`, `thesis_definition_sha256` revisado al aceptar, `video_id`, `claim_id`, `creator_id`, relación, dimensión del contraste, justificación y estado de aceptación |
| Evidencia | IDs originales, fecha de fuente, timestamp si existe, hash de análisis y hash de transcripción |
| Escenario / señal | ID original y referencia de fuente, origen creador/analista, condición, horizonte y límites; sin precios o plazos inferidos |
| Relación X | ID del post, ID de la conexión aceptada, afirmación destino, hashes y expiración existentes; identidad del autor |
| Cobertura | Analizados elegibles, afirmaciones clasificadas y no clasificadas; tesis aceptadas disponibles; filtros efectivos y fecha de generación |

Recalcular siempre los contadores desde evidencias elegibles bajo los mismos
filtros; no reutilizar un total global cuando la ficha esté filtrada.

Un creador se cuenta una vez por activo y por tesis, aunque tenga diez videos o
muchas afirmaciones. Puede participar en varias tesis. No sumar creadores de
tesis diferentes para obtener el total del activo.

Identidad entre YouTube y X solo con correspondencia explícita verificada.
No inferirla por nombres parecidos. En v1 el contador principal de creadores del
ranking procede de YouTube analizado. Autores de X se muestran aparte como contexto,
sin inflar ese contador. Una extensión multifuente debe explicitar su denominador.

Varias voces con la misma noticia no demuestran evidencia independiente. No
mostrar «fuentes independientes» salvo que se haya comprobado su procedencia.
Convicción del creador y confianza de extracción son campos distintos; ninguna
se transforma en probabilidad de acierto.

### 6.4 Versiones, caducidad y publicación

La aceptación vincula tanto la fuente como la **definición semántica de la tesis**.
Calcular `definition_sha256` desde un objeto con proposición, tema, mercados,
activos, alcance, horizonte y condiciones; ordenar los conjuntos de identificadores
y serializar de forma canónica en el exportador, con claves ordenadas, UTF-8,
sin espacios y sin valores no finitos. Mantener un único cálculo y casos de prueba.
Los rótulos de presentación no reemplazan la proposición canónica.

Cambiar cualquiera de esos campos semánticos exige incrementar la versión y
produce un hash distinto. Toda membresía aceptada conserva el hash de definición
que se revisó: si no coincide con el vigente, pasa a pendiente de revisión y se
excluye de los contadores, escenarios agregados y relaciones X heredadas. Esto
ocurre aunque los hashes de análisis y transcripción sigan intactos. Conservar
la aceptación anterior como historial; no transferirla automáticamente a la nueva
definición. Reincorporarla exige una nueva aceptación editorial con el hash vigente.

Una membresía cuyo hash ya no corresponde se invalida, se excluye de los conteos
y queda visible como pendiente de revisión en el diagnóstico de construcción.
No hacer fallar todo el sitio por una membresía obsoleta; sí rechazar su publicación
como aceptada. Un JSON de metadatos mal formado debe detectarse en el chequeo previo.

Publicar el índice ligero de tesis y los detalles por activo/tesis en la **misma
generación inmutable** que fija `index.json`, o mediante un manifiesto explícito
con hashes igualmente fijado a ella. Cambiar el índice de entrada solo cuando todos
los archivos estén escritos. No mezclar proyecciones de generaciones distintas.
Extender el contrato de manera aditiva para no romper los demás prototipos móviles.

Mantener el índice ligero; cargar texto completo, citas extensas y posts de forma
diferida al abrirlos. Ninguna interacción de lectura dispara extracción o inferencia.

## 7. Rutas, filtros y compatibilidad

- Conservar `#/`, `#/diario`, `#/feed`, `#/v/<id>`, `#/f/<asset>` y búsquedas existentes.
- Añadir una ruta de tesis solo si la ficha existente no permite un enlace estable claro.
- Enlaces antiguos `lens=destilado` abren Síntesis. `lens=transcripcion` sigue abriendo
  el texto; `lens=analisis` conserva acceso al análisis completo.
- Una referencia `?t=...&n=...` debe revelar la evidencia solicitada aunque Síntesis
  sea la nueva entrada. No dejar una nota enfocada dentro de una sección oculta.
- `tab=insights` se redirige a una vista existente con los mismos filtros; no a una página vacía.
- Los antiguos temas `#/n/<id>` conservan una vista temática o redirección explícita.
  Nunca reinterpretar silenciosamente un tema como una tesis aceptada.
- Conservar periodo y creador desde ranking hasta ficha y retorno. El contexto
  de tesis/activo hacia Feed es compartible por URL y no depende solo de memoria local.
- Feed global mantiene su independencia: no descargar el archivo completo de videos
  para abrirlo; el contexto opcional carga únicamente los datos necesarios.
- No ampliar filtros silenciosamente ante un vacío ni usar otras fechas para rellenarlo.
- Mantener accesibilidad de hojas y diálogos: foco, Escape, Atrás, bloqueo de fondo y lector de pantalla.

## 8. Ejecución por etapas y puntos de cierre

### Etapa 0 — Inventario y referencia de comportamiento

1. Leer este documento y el estado Git; preservar cambios de otros agentes.
2. Ejecutar pruebas locales relevantes y guardar una referencia de navegación móvil.
3. Identificar campos exactos que alimentan Escenarios y Qué vigilar, y el contrato
   publicado de relaciones X. No deducirlos solo del nombre de una tarjeta.
4. Preparar casos de datos reales suficientes y marcar dónde falta cobertura.

**Cierre:** mapa breve de campos y rutas; lista de archivos previstos. Sin cambios
de credenciales, proveedores o autorización de modelos.

### Etapa 1 — Lectura breve y profundización

Implementar Síntesis, tarjetas del Diario y accesos a fuentes; conservar lentes
antiguas y enlaces temporales. Reducir repetición sin tocar los análisis guardados.

**Cierre:** desde Diario se entiende la tesis y se consultan Escenarios / Qué vigilar
sin atravesar transcripción. Fuentes y análisis completo siguen accesibles.
Esta etapa puede revisarse independientemente de la clasificación de tesis.

### Etapa 2 — Proyección de tesis y ranking coherente

Implementar contrato, validación de membresías, cobertura y contadores; añadir
exportación compatible y filtros únicos. Preparar tesis reales de muestra con
proveniencia editorial y un estado vacío honesto para activos sin clasificación.

**Cierre:** deduplicación comprobada y orden determinista; ninguna mención o tema
se hace pasar por tesis. La entrada de nuevo contenido no requiere nuevas llamadas API.

### Etapa 3 — Contraste y Feed contextual

Conectar ficha de activo, tesis, escenarios y publicaciones. Reusar relaciones
aceptadas. Cuando no haya cruces, mostrar el vacío y contexto por activo separado.
No esperar nuevas ejecuciones de Schedule ni simular sus resultados.

**Cierre:** un recorrido completo desde Diario hasta activo y post, y otro desde
ranking hasta objeción y cita original. Mismos filtros y retorno correcto.

### Etapa 4 — Retirar duplicidades y verificar

Retirar pestaña Insights, trasladar ayudas al método y activar compatibilidad
de rutas. Revisar jerarquía y densidad en móvil. Ejecutar las pruebas y documentar
casos reales, vacíos y limitaciones. No eliminar código compartido por otras variantes
sin comprobar sus consumidores.

**Cierre:** informe de aceptación, capturas, conteos contrastados y pasos para revisar.
Preparar para el flujo de despliegue existente; este documento no autoriza publicar,
fusionar o reiniciar servicios de producción. No iniciar una nueva infraestructura.

## 9. Criterios de aceptación y pruebas necesarias

| Caso | Resultado exigido |
|---|---|
| Lectura inicial | Síntesis empieza por tesis y escenarios; no por un fragmento de transcripción |
| Diez videos de un creador | Un creador en el contador, conservando las evidencias relevantes |
| Mismo argumento repetido | Una tesis aceptada, varias fuentes; no diez tesis |
| Tema compartido, tesis diferentes | Proposiciones separadas; no fusión por el tema |
| Alcista largo / bajista corto | Matiz temporal visible; no contradicción automática |
| Autores distintos con posturas opuestas | Contraste entre fuentes, no «cambio de postura» personal |
| Creador citado / analista | No suma apoyo del anfitrión sin atribución explícita |
| Conteo filtrado | Filas, ficha, tesis y citas usan el mismo periodo y creador |
| Cero tesis aceptadas | Cobertura no disponible o parcial; no «nadie tiene tesis» |
| Fuente sin análisis | No entra como respaldo analizado; estado real accesible |
| Transcripción inválida o ausente | Contenido excluido del material utilizable |
| Hash reemplazado | Membresía previa excluida; nuevo análisis no hereda una aceptación obsoleta |
| Definición de tesis modificada, fuentes intactas | Hash semántico nuevo; aceptaciones anteriores pendientes y excluidas de conteos y de relaciones X heredadas hasta nueva aceptación |
| Post con ticker coincidente | Contexto por activo; no apoyo semántico |
| Post aceptado vencido | No se muestra como conexión vigente ni cuenta como respaldo |
| Misma persona en X y YouTube | Identidad explícita; sin duplicación de voces |
| Escenario del analista | Atribución visible; no se presenta como postura del creador |
| Condición o negación extensa | Expansión sin alterar el significado por truncamiento |
| Fuente temporal y enlace antiguo | Se abre la evidencia correcta y el botón Atrás restaura contexto |
| Feed global | Mantiene filtros y carga independiente del índice de videos |
| Sin red / datos incompletos | Error recuperable; sin contenido o comparaciones inventadas |
| Interacción de lectura | Cero llamadas de inferencia y cero solicitudes nuevas a proveedores |

Añadir tests significativos de proyección, identidades, conteo, invalidación,
caducidad, filtros y rutas. Reusar `radar.test.cjs`, `feed.test.cjs`, tests de
`postures.py` y la suite del exportador/servidor cuando los cambios los afecten.
Probar el guard de API si se toca su configuración; el resultado normal sigue bloqueado.
No escribir snapshots masivos para texto editorial ni tests que solo dupliquen HTML.

QA visual a 390×844 y 360×800: sin scroll horizontal, acciones alcanzables, foco
visible y texto legible sobre cristal; verificar también el diseño ancho existente.
Probar con teclado y movimiento reducido. Los límites de tarjetas son presentación,
no pérdida de evidencias o fuentes en la exportación.

## 10. Cómo comprobar valor con una persona

Asignación para el propietario: observar a una persona que consuma estos videos,
sin guiarla, en una sesión corta con el mismo conjunto de fuentes antes y después.
Pedir una sola tarea: **encontrar una altcoin debatida, explicar una tesis, identificar
una objeción y señalar una condición que vigilar**, mostrando sus fuentes.

Registrar tiempo, secciones visitadas, retornos por confusión y errores de comprensión.
Metas iniciales de prueba, no promesas validadas:

- En 60 segundos, explicar la tesis de un video analizado y una condición relevante.
- En 3 minutos, comparar dos voces y llegar a una evidencia verificable dentro del archivo.
- En no más de dos acciones desde una ficha con conexiones, acceder a un post relacionado.
- Si los datos no permiten contraste, reconocer ese límite sin confundirlo con consenso.

Comparar contra el recorrido anterior; no usar mayor tiempo de permanencia como éxito.
Cambiar estas metas si la observación muestra que son poco útiles. No generalizar
una sesión como evidencia de retención o disposición a pagar.

## 11. Riesgos, incógnitas y siguientes decisiones

1. **Cobertura de tesis:** la primera clasificación será parcial y editorial. Su
   ampliación automática requiere una fase específica; no prometerla en esta entrega.
2. **Identidades entre plataformas:** falta confirmar qué cuentas de X corresponden
   a los canales. Sin mapa verificado, mantener autores y contadores separados.
3. **Datos insuficientes sobre infraestructura:** no se garantiza que el archivo
   actual sostenga ese ejemplo. La interfaz debe funcionar con un vacío legítimo.
4. **Periodo inicial:** conservar la preferencia existente en esta fase; todos los
   estados muestran el periodo. No asumir tiempo real ni ampliar ventanas sin acción.
5. **Peso:** el ranking mide participación y variedad de tesis clasificadas. La
   solidez del argumento se explica en sus evidencias; no hay un índice validado de credibilidad.
6. **Priorización editorial:** qué fuentes abrir primero se ajustará con observación,
   sin ocultar posiciones contrarias por ser menos populares.

## 12. Señales útiles de la discusión

- «Lo más útil ... Qué vigilar y Escenarios»: la utilidad descrita es seguir una
  interpretación con condiciones, no leer todos los campos del análisis.
- «Volumen de creadores y tesis»: la selección del activo necesita deduplicación
  y diversidad argumental visibles, además de volumen de contenido.
- El recorrido termina en Feed: X pertenece al trabajo de contraste y debe
  conservar una entrada propia, además de conexiones contextuales.

## 13. Instrucción lista para el agente Claude

> Trabaja en CryptoReport y lee íntegramente `docs/designs/urania-tesis-y-contraste.md`.
> Implementa por etapas la propuesta B, empezando por Síntesis y conservando el
> recorrido Diario → ranking → Feed. Antes de editar, inspecciona el estado Git,
> las rutas y los contratos reales; preserva el trabajo existente de otros agentes.
> Reutiliza análisis válidos, posturas y conexiones semánticas aceptadas. Mantén
> los originales; genera proyecciones derivadas con hashes y cobertura explícita.
> No cuentes temas como tesis ni tono como apoyo. No inventes agrupaciones o
> participantes para completar pantallas. Mantén la API de inferencia desactivada
> y no cambies Schedule, credenciales, scraping, timers ni infraestructura.
> Resuelve las decisiones locales dentro de estos límites. Si una conexión no
> puede justificarse con datos, muestra el estado parcial o vacío y documenta el
> límite. Cierra cada etapa con pruebas y evidencia de su comportamiento. Al final
> entrega archivos cambiados, verificaciones, capturas móviles, cobertura de
> clasificación y limitaciones. Prepara los cambios para revisión; no despliegues
> ni publiques en producción como parte de este encargo.

<!-- gstack:office-hours:concerns:start -->
## Reviewer Concerns

Disposition: COMPLETED

Stop: PASS

No unresolved findings.
<!-- gstack:office-hours:concerns:end -->

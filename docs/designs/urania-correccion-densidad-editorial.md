# Urania: corrección de densidad editorial y duplicidad

Fecha de revisión: 15 de octubre de 2026, America/Bogota.  
Alcance: revisión visual de la implementación pública enviada por el usuario.  
Estado de la auditoría original: **hallazgos comprobados y brief de corrección**.

**Corrección posterior integrada:** [implementación, pruebas y capturas](../validaciones/ruido-urania-2026-10-15/correccion-integrada.md).

URL revisada: <https://communist-mature-gravity-deeper.trycloudflare.com/b4-urania/#/diario>.

Este documento precisa el [planning anterior](urania-tesis-y-contraste.md).
Sus límites de presentación sustituyen las indicaciones anteriores que permitían
copiar una tesis completa cuando no existía una versión breve. El análisis original
y sus condiciones siempre se conservan, pero no deben volcarse completos en la lista.

## 1. Diagnóstico

La implementación reorganizó campos y nombres, pero conserva una lectura de
informe extenso dentro de una interfaz móvil estrecha. La misma tesis aparece
en Diario y vuelve a ocupar gran parte de Síntesis. Escenarios y Qué vigilar
siguen repitiendo condiciones, señales y explicaciones de método.

**Premisa editorial: cada bloque de texto debe justificar el espacio que ocupa.**
Debe permitir elegir, comprender una diferencia, identificar una condición o
comprobar una fuente. Un bloque que repite lo leído pasa a profundización o se elimina
de esa vista. Cambiar tamaño de letra o añadir «Ver más» no resuelve por sí solo
una organización repetitiva.

El texto inspeccionado está alineado al inicio (`text-align: start`). El problema
principal observado es extensión, jerarquía y repetición, además de la composición
que deja poco espacio para leer. No se recomienda justificar ambos márgenes en móvil.

## 2. Evidencia comprobada

Recorrido en Chromium: Diario → video de Battaglia → Síntesis → Escenarios → Qué
vigilar → ranking → Feed → ficha de ETH. Capturas a 390×844 y comprobación adicional
de Diario a 360×800.

- La tesis de Battaglia tiene **58 palabras** y aparece completa en Diario y Síntesis.
- En Síntesis, su párrafo se presenta a **19 px**, interlineado **27,55 px** y ocupa
  aproximadamente **303 px**, unas **11 líneas** en el ancho observado.
- El panel de lectura tiene **387 px visibles** para **3.759 px de contenido** en
  el estado medido: unas 9,7 alturas de panel. No equivale a 9,7 pantallas completas
  del teléfono, porque video y controles consumen el resto de la superficie.
- La apertura de Diario dedica espacio a enumerar siete creadores, explicar
  colores, mostrar el balance y recomendar un video que también aparece en la lista.
- Un video sin análisis sobre miniaturas de YouTube aparece primero y muestra
  simultáneamente «Neutra» y «100 % de las señales al alza».
- En Qué vigilar, una señal enlaza por separado tres nombres extensos de escenarios,
  además de repetir criterio, plazo, procedencia y dato necesario.
- En la ficha de ETH se repiten «tesis aceptada», nombres de participantes y avisos
  de cobertura. «2 creadores» y «Coinciden 1 creador» no se explican con claridad.
- Al navegar desde video hacia ranking, el reproductor queda flotando encima de
  la información de Ethereum, aun sin haber iniciado reproducción en este recorrido.
- No se observó desbordamiento horizontal a 390 px. No se detectaron excepciones
  JavaScript en las consultas realizadas; hubo advertencias del reproductor de YouTube.

La versión remota difiere de este checkout en `app.js`, `app.css` e `index.html`.
También carga `theses.js`, que no existe en la carpeta local `b4-urania` inspeccionada.
Las correcciones deben aplicarse al checkout que sirve esa URL; no se afirma haber
corregido la aplicación pública editando otro árbol de archivos.

Tras ampliar la búsqueda se encontró `/root/cryptoreport-urania-tesis/`. Sus cuatro
archivos `app.js`, `app.css`, `index.html` y `theses.js` coinciden byte a byte con
los servidos por la URL durante la comprobación. Esa copia es la referencia de
código para la corrección; la carpeta inspeccionada no tiene un repositorio Git
reconocible. Conservar un respaldo de los archivos antes de editarla y comprobar
el proceso que sirve la URL antes de atribuirle un despliegue. Esta revisión no
modificó esos archivos.

## 3. Hallazgos priorizados

| ID | Impacto | Problema | Corrección exigida |
|---|---|---|---|
| E01 | Alto | Diario antepone explicaciones y un recomendado duplicado a la lista | Cabecera breve, filtros compactos y contenido desde el primer pliegue |
| E02 | Alto | Las tarjetas se convierten en párrafos de análisis | Tarjeta de selección con título, autor y un aporte breve; análisis completo al abrir |
| E03 | Alto | Síntesis vuelve a mostrar la misma tesis como un titular de once líneas | Conclusión breve en cuerpo de lectura; título visual corto y detalles bajo demanda |
| E04 | Alto | Video y controles reducen la lectura a menos de la mitad del alto disponible | Modo lectura con un scroll principal; reproductor a demanda |
| E05 | Alto | Escenarios y Qué vigilar vuelven a explicar las mismas condiciones | Cada condición tiene una ubicación principal; referencias breves entre bloques |
| E06 | Medio | Estados operativos y método aparecen repetidos como contenido | Llevar etapas, conteos de clasificación y explicación del método a estado o ayuda |
| E07 | Alto | «Neutra» y «100 % al alza» ofrecen mensajes incompatibles para la lectura rápida | En contenido sin análisis, estado simple; métricas léxicas solo dentro del método con su alcance |
| E08 | Medio | Participantes y contadores del contraste se repiten y resultan ambiguos | Una fila por autor con su relación y condición; explicar el denominador una vez |

Los hallazgos son de esta revisión enfocada; no representan una auditoría completa
de todas las rutas, casos de datos o interacciones del sistema.

## 4. Contrato editorial para la corrección

### Diario: elegir qué abrir

La tarjeta responde a «qué aporta este contenido». Orden:

1. Autor y hora, compactos.
2. Título legible, sin bloques de hashtags en la vista de lista.
3. Si existe una versión breve fiel, una línea o dos sobre el aporte diferente del título.
4. Activos relacionados y una acción principal para abrir la síntesis.

Objetivos visuales a 390×844:

- Cabecera completa, incluyendo navegación superior: alrededor de 160 px o menos.
- Tarjeta ordinaria: alrededor de 180 px; comprobar con títulos reales largos.
- Ver al menos dos tarjetas completas sin desplazamiento tras cargar Diario.
- Título: hasta dos líneas en lista, con acceso al título íntegro en el detalle.
- Aporte editorial: hasta dos líneas; objetivo de 12–20 palabras, sin recorte mecánico
  que suprima condiciones o negaciones.
- Texto de apoyo: 14–15 px, interlineado de aproximadamente 1,4–1,5 y alineación inicial.
- «Procesamiento: 4 de 4 etapas» no aparece en cada tarjeta. Como máximo, estado
  breve cuando haya algo pendiente o fallido y acceso voluntario a su explicación.

No copiar `resumen.tesis_principal` completo para rellenar el aporte. Si no puede
condensarse con fidelidad, mostrar título y «Ver tesis con condiciones», sin párrafo
duplicado. La ausencia de una versión breve no autoriza generar una mediante API.
Conservar el texto original, los hashtags y los límites dentro del detalle.

La cronología puede conservar contenido pendiente; no debe atribuirle una postura
financiera a partir de indicadores léxicos. Si se separa contenido ajeno a mercados,
hacerlo mediante un filtro explícito y reversible, no borrando materiales.

### Síntesis: comprender y seguir una tesis

Primera pantalla útil:

- Una tesis atribuida, breve y legible.
- Su condición principal, cuando conste.
- Acceso visible a Escenarios y Qué vigilar.
- Acceso secundario a la fuente.

Objetivos:

- La tesis no se convierte en un titular enorme. Usar cuerpo de 15–16 px; reservar
  la serif de mayor tamaño para un título realmente corto.
- La lectura tiene un scroll principal. No obligar a leer dentro de un cuaderno
  que deja visibles simultáneamente video, nota actual, pulso y pestañas de dos líneas.
- El video se abre voluntariamente. Conservar reproducción y salto al minuto; el
  reproductor flotante fuera del detalle requiere una acción explícita de fijarlo.
- La nota «Ahora suena» aparece cuando corresponde a una reproducción en curso,
  no como bloque permanente mientras se está leyendo.
- No repetir en primera lectura título, tesis extensa, mensaje explícito y conclusión
  provisional si expresan la misma idea. La diferencia entre afirmación y evidencia
  permanece accesible y sus límites relevantes se muestran donde afectan la lectura.

### Escenarios: distinguir posibilidades

Cada escenario compacto muestra nombre, autoría, condición y consecuencia. El
horizonte se integra donde ayuda a distinguirlo. Supuestos, mecanismo completo,
evidencia faltante y explicación extensa de invalidación quedan al ampliar.

No mostrar una alternativa del analista como si otro creador estuviera contradiciendo
la tesis. No añadir porcentajes ni sustituir una condición por un objetivo de precio.

### Qué vigilar: señales concretas

Una fila corresponde a una señal: qué observar, condición o nivel literal y plazo
cuando estén definidos. La procedencia y la fuente se consultan al ampliar.

Si la señal pertenece a varios escenarios, usar «Vinculada a 3 escenarios» como
entrada compacta, en lugar de repetir tres títulos completos. Evitar volver a
copiar el mecanismo del escenario en esa fila.

Si el material dice «80» sin aclarar unidad, conservar esa ambigüedad. No transformarlo
silenciosamente en USD 80.000 para obtener una frase más limpia.

### Ranking, contraste y Feed

- Fila de ranking: activo, número de creadores y tesis disponibles. La cobertura
  parcial se explica una vez por vista; el desglose queda disponible al ampliar.
- «Sin clasificar» es estado de cobertura, no el mensaje principal de todas las filas.
- Una participación por autor con su relación: «apoya con condiciones», por ejemplo.
  No repetir su nombre en tres párrafos para explicar esa misma participación.
- El total de participantes de una tesis y el número de apoyos deben llevar
  denominadores comprensibles. No usar «Coinciden 1 creador» como señal de consenso.
- Feed conserva las palabras del autor; no reescribir publicaciones. En un contraste,
  mostrar primero el fragmento pertinente y su relación aceptada, con acceso al post
  completo. Contexto por ticker no se presenta como apoyo o evidencia independiente.
- Los datos de clasificación, trazabilidad y fuentes siguen disponibles. Se cambia
  su jerarquía, sin eliminar condiciones, evidencia ni posiciones contrarias.

## 5. Ejemplo de tarjeta para explicar la intención

Ejemplo editorial basado en el video de Battaglia inspeccionado; no es una nueva
salida de análisis ni una recomendación financiera:

```text
David Battaglia                                      12:46
¿Por qué Bitcoin no cayó con la inflación?
Lectura alcista condicionada a tipos y señales técnicas.
BTC · Petróleo                             Leer síntesis →
```

La tarjeta permite elegir. El objetivo de precio, las condiciones literales y los
límites se consultan al abrir; no deben desaparecer del detalle. La primera vista
de Síntesis debe expresar la tesis y su condición sin repetir el párrafo de 58 palabras.

## 6. Criterios de aceptación antes de entregar otra versión

1. Capturas reales a 360×800 y 390×844, con títulos largos y análisis extensos.
2. En Diario se ven al menos dos tarjetas completas sin desplazamiento inicial.
3. En Síntesis se entiende qué plantea el creador y se encuentra Qué vigilar sin
   atravesar un informe de múltiples alturas de panel.
4. No hay párrafos largos idénticos en lista y detalle. Conservar un mismo titular
   breve por coherencia no equivale a duplicar todo el análisis.
5. Cada bloque responde a una función distinta. El implementador debe justificar
   cualquier párrafo que aparezca en más de una sección.
6. Los escenarios mantienen atribución y condiciones; una versión breve nunca se
   aprueba solo por caber en dos líneas.
7. El video no tapa filas del ranking o posts salvo que se haya fijado explícitamente.
8. Un contenido sin análisis no ofrece una conclusión financiera mediante tono léxico.
9. Sigue siendo posible contrastar apoyos, objeciones y matices y consultar la cita original.
10. Ningún cambio activa inferencia API, reanaliza videos o altera las fuentes guardadas.

Los objetivos geométricos son criterios de diseño de esta corrección; deben probarse
con los casos reales. Cuando cumplirlos altere el significado, reducir lo que se
muestra en la tarjeta y conservar el contenido íntegro detrás de una acción clara.

## 7. Instrucción para el agente que sirve la versión pública

> Lee este documento y trabaja sobre el checkout que sirve la URL auditada.
> Corrige primero Diario y Síntesis. Separa modelo de análisis y composición de
> lectura: no vuelques todos los campos del JSON como tarjetas de igual importancia.
> Presenta las capturas antes/después en 360×800 y 390×844 y comprueba los diez
> criterios anteriores. Conserva las funciones útiles, fuentes, condiciones y datos.
> No habilites API ni cambies el pipeline. No anuncies finalización porque se hayan
> renombrado pestañas o pasado pruebas de datos: demuestra la reducción de ruido en
> el recorrido real Diario → Síntesis → ranking → Feed.

## 8. Capturas de evidencia

- [Diario: primera pantalla](../validaciones/ruido-urania-2026-10-15/diario-mobile.png).
- [Diario: tarjeta extensa](../validaciones/ruido-urania-2026-10-15/diario-tarjetas.png).
- [Síntesis: párrafo repetido y composición](../validaciones/ruido-urania-2026-10-15/sintesis-mobile.png).
- [Escenarios](../validaciones/ruido-urania-2026-10-15/escenarios-mobile.png).
- [Qué vigilar](../validaciones/ruido-urania-2026-10-15/vigilar-mobile.png).
- [Ranking y reproductor superpuesto](../validaciones/ruido-urania-2026-10-15/ranking-mobile.png).
- [Feed](../validaciones/ruido-urania-2026-10-15/feed-mobile.png).
- [Ficha de activo](../validaciones/ruido-urania-2026-10-15/ficha-mobile.png).
- [Diario a 360 px](../validaciones/ruido-urania-2026-10-15/diario-360.png).

Esta auditoría se entregó inicialmente sin modificar la interfaz. La corrección posterior, autorizada por el usuario, está integrada y documentada en el informe enlazado al comienzo.


## Preferencia posterior: conservar signos vitales y timeline

El usuario pide mantener las ondas verdes/rojas y la composición de timeline como identidad del Diario. La reducción de ruido se limita al texto redundante y a los estados operativos; no autoriza retirar estas señales visuales. Restauración y verificación: [timeline y pulso](../validaciones/timeline-pulso-2026-10-15/README.md).

# Corrección editorial integrada en Urania

Fecha: 15 de octubre de 2026, America/Bogota.

La corrección está en `/root/cryptoreport/prototypes/movil`, no solo en el laboratorio.
La URL pública mantiene su dirección y ahora sirve ese mismo repo principal:
https://communist-mature-gravity-deeper.trycloudflare.com/b4-urania/#/diario

## Cambios visibles

- **Diario:** autor y hora, título de dos líneas sin hashtags en la lista, activos y una acción. Se eliminaron el recomendado duplicado, la explicación de colores, las tesis completas y las etapas de procesamiento en cada tarjeta. Sin análisis no se presenta tono financiero.
- **Síntesis:** lectura por defecto con conclusión, escenarios, señales y contraste en vistas distintas. Una sola superficie de desplazamiento. Fuentes y análisis completo siguen disponibles; no se repiten como acciones al pie.
- **Video:** carga a petición. Salir del detalle no crea un flotante salvo que el usuario pulse «Fijar al salir». El enlace a YouTube y el título íntegro están en «Fuente», también para videos sin análisis.
- **Escenarios y señales:** mecanismos y criterios se conservan literalmente. Los supuestos, invalidación extensa y fuentes se consultan al ampliar. Las referencias a tres escenarios quedan en una sola entrada desplegable. Se mantiene la diferencia entre creador y analista.
- **Ranking:** filas compactas por creadores únicos y tesis; explicación de cobertura una vez. Las menciones continúan disponibles en la ficha.
- **Contraste:** una participación por creador, incluyendo sus distintas relaciones y todas las evidencias. Se sustituye el ambiguo «Coinciden 1 creador» por cantidades de apoyos, objeciones y matices; las relaciones pueden solaparse y no se suman como autores independientes.
- **Feed:** se conservan publicaciones, clasificación y conexiones aceptadas. Compartir ticker sigue siendo contexto y no respaldo.

## Integridad y actualización

Se portaron la proyección determinista `theses.py`, su metadata y pruebas desde la implementación revisada. `build_data.py` incorpora las tesis a cada generación y valida los hashes de las fuentes. Por ello, la actualización normal del repo principal ya publica también esta proyección.

La generación comprobada conserva **49 videos, 44 análisis, 834 afirmaciones, 4 tesis y 27 membresías aceptadas**. Los identificadores de videos y los 44 hashes de análisis coinciden con la instantánea previa. No se reanalizó contenido, no se modificaron transcripciones y no se activó inferencia por API.

Los siete análisis del último lote tienen briefs de presentación revisados manualmente, asociados al hash exacto de su análisis en `b4-urania/editorial.js`. Cambiar el análisis invalida el brief anterior. Otros videos muestran la tesis original como cuerpo de lectura, sin recortarla ni inventar una condensación. La lista nunca copia esa tesis. «80» conserva su unidad sin aclarar; no se transformó en USD 80.000.

El servidor del puerto 8742 se cambió de la copia de laboratorio al repo principal. El túnel conserva su origen y su URL; el puerto 8741 también sirve el principal. El laboratorio y el respaldo se conservan. No se incluyeron cambios ajenos en un commit ni se hizo push remoto.

Respaldo previo: `/root/urania-backup-20261015-editorial/`. Los cambios se prepararon y registraron en una copia Git aislada antes de aplicarlos al árbol principal con cambios preexistentes.

## Verificación

- **32 pruebas JavaScript** de ranking, radar, Feed, deduplicación y briefs.
- **15 pruebas Python** de proyección y vigencia de tesis.
- Chromium a **390×844, 360×800 y 1280×800**, con el recorrido Diario → Síntesis → escenarios → señales → fuente → análisis completo → ranking → ficha → Feed.
- Se comprueban título íntegro, tesis original accesible, unidad ambigua preservada, enlaces de señales a escenarios, enlaces antiguos con minuto y afirmación, una fila por creador, Escape en la ficha, ausencia de flotante automático y fijación/cierre voluntarios.
- Cero excepciones JavaScript y cero desbordamientos horizontales en el recorrido probado.
- La lectura inicial no solicita la API de YouTube ni carga iframes. El control de reproducción y PiP se prueba con el simulador existente para evitar depender de la disponibilidad de YouTube. En la URL pública se comprobó la creación del iframe real; YouTube pasó al estado alternativo disponible. No se certifica reproducción audiovisual externa sin errores.
- Los archivos públicos y el índice se cotejaron con los del repo principal.

| Medida | Antes | Después |
|---|---:|---:|
| Tarjeta ordinaria de Diario a 390 px | tesis completa y estados repetidos | aproximadamente 143 px |
| Alto útil de lectura a 390×844 | 387 px | 692 px |
| Alto útil de lectura a 360×800 | no medido en auditoría original | 648 px |
| Tesis de Battaglia presentada como titular | aproximadamente 303 px | dos líneas de cuerpo; condiciones en bloque separado |
| Lectura inicial con video | marco y flotante automáticos | a petición |

Las medidas corresponden a los datos reales y al recorrido de la prueba, no a todos los posibles títulos o futuras transcripciones.

## Evidencia reproducible

- [Medidas y resultado Chromium](despues/qa.json).
- [Diario antes](diario-mobile.png) / [después](despues/diario-390.png).
- [Síntesis antes](sintesis-mobile.png) / [después](despues/sintesis-390.png).
- [Síntesis a 360 px](despues/sintesis-360.png).
- [Escenarios](despues/escenarios-390.png), [qué vigilar](despues/vigilar-390.png), [ranking](despues/ranking-390.png), [contraste](despues/ficha-390.png), [Feed](despues/feed-390.png).
- Capturas de URL pública: [Diario](despues/publico-diario-390.png), [Síntesis](despues/publico-sintesis-390.png).

Para repetir: iniciar el servidor del repo y ejecutar:

```bash
node --test prototypes/movil/b4-urania/*.test.cjs
python3 -m unittest discover -s prototypes/movil -p test_theses.py
# Playwright debe estar disponible en node_modules o NODE_PATH.
BASE=http://127.0.0.1:8741/b4-urania/ node prototypes/movil/b4-urania/editorial.browser.cjs
```

Revisión externa y generación de mockups omitidas; no se emplearon otros modelos ni servicios de inferencia para esta corrección.

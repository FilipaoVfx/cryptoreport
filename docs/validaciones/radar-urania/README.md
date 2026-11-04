# Validación: Radar y fichas de Urania

Verificado el 14 de octubre de 2026, hora de Bogotá.

URL pública: [Radar de Ethereum](https://imports-toolkit-vital-alt.trycloudflare.com/b4-urania/#/buscar?q=short%20ETH).

## Resultado

Implementación guardada en el repositorio local y servida por el túnel existente. No se ha hecho push a GitHub en esta entrega.

- Radar local para `short`, `long` y activo; selector de dirección, filtros de mercado/creador/período y posiciones declaradas.
- Narrativa e insight del análisis almacenado dentro de cada tarjeta desplegable. Los textos del video completo están identificados como tales; las citas sostienen la tesis específica del activo.
- Fichas con orden global alcistas → bajistas → mixtas → neutrales, filtros consistentes, deduplicación y citas adicionales bajo demanda.
- Logos locales para 20 activos y avatares de los 7 creadores. Símbolos o iniciales para el resto.
- Proyección separada de dirección, lado/estado de posición y tono léxico; referencias a análisis, evidencias y hash de transcripción.
- Publicación por generación coherente; repetición del mismo conjunto sin crear otra generación. Renovación semanal de identidades integrada en el constructor existente.

Snapshot publicado: `4bfc11ac47250090e315a770583f1e80`, con 41 videos, 33 analizados, 630 afirmaciones y 80 detalles versionados. No se generaron análisis nuevos. Para ETH la cobertura mostrada es 8 de sus 10 videos; los filtros de cobertura incluyen el activo seleccionado.

## Comprobaciones

**31 pruebas automatizadas aprobadas**: 19 de Python, incluyendo el servidor, y 12 de JavaScript. Cubren negación, temporalidad, acumulación en retrocesos, bots, coberturas, posición futura/cerrada, terceros, excepciones por activo, autores únicos, orden global, deduplicación, citas tardías, rechazo de transcripciones inválidas, hashes obsoletos y versiones reproducibles.

Comandos:

```bash
python3 -m unittest discover -s prototypes/movil -p 'test_*.py'
node --test prototypes/movil/b4-urania/radar.test.cjs
node --check prototypes/movil/b4-urania/app.js
node --check prototypes/movil/shared/core.js
```

**16 comprobaciones funcionales en navegador sobre la URL pública**: resolver ETH, cambiar dirección sin perder el activo, filtrar creador, estado vacío sin ampliación silenciosa, consultas literales, cero fetch durante consultas/filtros, narrativa e insight, orden de citas, aislamiento y ciclo de foco del diálogo, avatares locales, cargar más, cerrar y recuperar contexto.

Durante ese recorrido, buscar y filtrar produjo **cero peticiones fetch**. Abrir la ficha cargó un único JSON local del activo. No hubo llamadas a modelos. Las imágenes se sirven desde el mismo servidor.

Se comprobaron anchos de **320, 375, 390 y 430 px**, sin desbordamiento horizontal. La consola no registró errores de la aplicación. La versión publicada volvió a comprobarse tras la reconstrucción final.

Una petición HTTP nueva, sin cookies ni autenticación, obtuvo 200 para HTML, scripts, CSS, índice y detalle de activo. El índice ocupa aproximadamente **216 KB comprimido** en esta muestra. Los recursos activos de identidad suman aproximadamente **150 KB**; el navegador carga las imágenes diferidas según se necesitan.

El prototipo Bitácora también pudo cargar desde el núcleo compartido un detalle con 38 afirmaciones y 520 segmentos, sin errores en consola.

## Capturas

- [Radar móvil](radar.png).
- [Ficha de menciones](ficha.png).
- [Narrativa e insight desplegados](insight.png).

## Límites y mantenimiento

Las clasificaciones se derivan mediante reglas conservadoras del análisis disponible; no constituyen seguimiento de una cartera ni prueba externa de una tesis. Los videos pendientes siguen pendientes y no se consumieron créditos de modelos para completarlos.

Los cambios de datos se publican mediante el constructor que ya invoca el pipeline. Una pestaña abierta conserva una versión coherente; recargar obtiene el índice publicado más reciente. Las generaciones antiguas caducan después del período documentado.

Las pruebas quedaron añadidas al workflow local de GitHub Actions; esta entrega no afirma que se hayan ejecutado remotamente. Fuentes, licencias, caché y comandos de mantenimiento: [documentación de identidades](../../../prototypes/movil/metadata/README.md).

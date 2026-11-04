# Lote autorizado de análisis con Luna Max · 15 de octubre de 2026

Se completaron y publicaron los siete videos fijados en el inventario de las
**13:46:40 de America/Bogota**. La autorización fue puntual: videos publicados
hoy y ya presentes en ese inventario. No incluye entradas posteriores, videos
anteriores ni análisis semántico de publicaciones de X mediante API.

## Resultado

- Modelo devuelto por la API: `gpt-6-luna`; `reasoning.effort=max`.
- Prompt completo: `services/analysis/prompts/narrative-analysis.system.md`, v1.0.0.
- Siete análisis válidos, con hash de transcripción, prompt y esquema.
- Siete publicados en el sitio y en Urania; se consultaron por HTTP público el
  índice y los siete detalles, comparando sus versiones y el objeto de análisis.
- Diez solicitudes de inferencia, exclusivamente sobre los siete IDs del lote.
- Veintiocho pruebas del módulo de análisis aprobadas. Se comprobó también
  el bloqueo real del CLI sin la habilitación temporal: no creó un cliente API.
- El permiso temporal existió únicamente en los procesos del lote. No se
  cambió `.env`, el modelo predeterminado ni la configuración de los timers.

| Canal | Video | ID | Afirmaciones | Evidencias | Escenarios |
|---|---|---|---:|---:|---:|
| nacho | [🧐💸 ¿Por qué está el S&P500 en MÁXIMOS HISTÓRICOS con los BONOS en ESTADO CRÍTICO?](https://www.youtube.com/watch?v=zQ6nDHqcG7Q) | `zQ6nDHqcG7Q` | 6 | 15 | 2 |
| nacho | [Nadie Quiere Comprar Bitcoin | EXCELENTE SEÑAL (te cuento por qué)](https://www.youtube.com/watch?v=ssdHOY7wVMk) | `ssdHOY7wVMk` | 17 | 29 | 3 |
| nacho | [🧐 El CICLO del DÓLAR y la LIQUIDEZ que se está cumpliendo OTRA VEZ](https://www.youtube.com/watch?v=d53ZVorywvk) | `d53ZVorywvk` | 10 | 16 | 3 |
| cava | [Cuando Falta la Confianza en las Instituciones… Suiza. | José Luis Cava](https://www.youtube.com/watch?v=aW9a3O2XNho) | `aW9a3O2XNho` | 26 | 59 | 3 |
| battaglia | [¿Por Qué Bitcoin No Cayó con la Inflación? 🤔](https://www.youtube.com/watch?v=pcBbfvFmkY0) | `pcBbfvFmkY0` | 26 | 21 | 3 |
| planbtc | [¿Estamos ante la MAYOR TRAMPA de la década en BITCOIN y NASDAQ?](https://www.youtube.com/watch?v=LcJTmXpKM7E) | `LcJTmXpKM7E` | 19 | 32 | 3 |
| healthy | [Comprar Bitcoin en $80,000 Es la Mejor Decisión que Tomarás en tu Vida](https://www.youtube.com/watch?v=40Jh8ABy83o) | `40Jh8ABy83o` | 17 | 46 | 3 |

## Validación y reparaciones

Se aplicó el esquema completo y el validador de referencias, fuentes, citas y
marcas temporales. Cada análisis debe seguir correspondiendo al hash de su
transcripción original para publicarse.

Una evidencia de `ssdHOY7wVMk` y cinco de `LcJTmXpKM7E` no eran citas literales:
contenían omisiones con puntos suspensivos o cambios respecto del subtitulado.
Se reemplazaron por texto copiado de segmentos contiguos del mismo video;
se ajustaron los intervalos de PlanBTC y se repitió la validación completa.
Las reparaciones están registradas en `meta.literal_quote_repairs`. Los
originales y las salidas rechazadas se conservaron. No se alteró la transcripción
ni se relajó el validador. Estas reparaciones no usaron más inferencia.

Cava y PlanBTC tuvieron un segundo intento con un límite de salida de 128.000
tokens, conservando Luna Max. El primer límite era de 64.000 e incluía el
razonamiento. Cava completó su segundo intento con 86.208 tokens de salida.
Las primeras respuestas fallidas no conservan un motivo más específico que
`AnalysisError`; no se atribuye a todas una causa única confirmada.

## Costos y límites de la medición

El costo estimado de las respuestas cuyo uso quedó registrado suma
**USD 0.2125**. No es una cifra final de facturación: tres llamadas fallidas
no conservaron sus métricas de uso. Pueden haber consumido créditos y no se
contabilizan como gratuitas. No se consultó un saldo de facturación actualizado.

## Evidencias operativas

Los originales permanecen fuera del repositorio:

- Inventario cerrado: `/var/lib/cryptoreport-transcripts/api-batches/20261015T184640Z-luna-max/manifest.json`.
- Prueba de publicación: `/var/lib/cryptoreport-transcripts/api-batches/20261015T184640Z-luna-max/publication-proof.json`.
- Resumen final: `/var/lib/cryptoreport-transcripts/api-batches/20261015T184640Z-luna-max/final-summary.json`.
- Intentos, respuestas disponibles, reparaciones, consumo y scripts utilizados:
  el mismo directorio privado.
- Análisis canónicos: `/var/lib/cryptoreport-transcripts/analysis/<canal>/`.

Generación comprobada de Urania: `b8890acc59c185d7786b133e05a64fda`.
Fecha de la exportación consultada: `2026-10-15T19:30:40+00:00`.
La publicación local y la consulta pública de los siete análisis se comprobaron
por separado de la sincronización de Drive. Un aviso posterior del transporte
no invalida por sí solo esas comprobaciones; debe revisarse en el monitor.

## Cierre de autorización

`CRA_ALLOW_API_ANALYSIS` continúa desactivado para el funcionamiento normal.
Los scripts se limitaron a IDs explícitos y tienen marcadores que impiden
repetir accidentalmente el lote. No se instaló un proceso de inferencia
recurrente. Los videos que entren después siguen dependiendo del flujo de
Schedule; usar API para ellos requiere otra autorización del usuario.

[Modelo y niveles de razonamiento documentados por OpenAI](https://developers.openai.com/api/docs/models/gpt-6-luna).

El ciclo final de Drive terminó sin errores de transporte y reconoció los siete
trabajos del lote como `imported`. El estado global puede seguir degradado por
los pendientes anteriores y el último comprobante fallido de Schedule.

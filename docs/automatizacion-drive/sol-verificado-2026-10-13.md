# Verificación independiente de la comparativa identificada como Sol

Se revisó el [nuevo análisis](https://drive.google.com/file/d/1QbKq-KQoLPsHt1mpgarZwRxLY-GM9kyJ/view?usp=drivesdk), el [comprobante](https://drive.google.com/file/d/1BNIN7yKqYXjRyFXGXlcy7Iiu51hfjbBc/view?usp=drivesdk), el JSON de mediciones y el informe de Comparativas. El usuario identifica esta prueba como Sol; el archivo mantiene `model: null`, por lo que no acredita técnicamente la variante, razonamiento o velocidad seleccionados.

## Resultado

La salida original pasa el validador del repositorio contra la transcripción local independiente: **cero errores** de JSON Schema, citas, referencias, estados y procedencia. Coinciden los hashes de transcripción, prompt y esquema y los IDs de análisis/comprobante; los tiempos del análisis son coherentes con la ejecución.

Una comprobación adicional revisó los 47 rangos de transcripción usando los índices explícitos de cada localizador, sin el segmento de margen admitido por el validador: todas las citas están dentro del rango exacto, y sus extremos coinciden con el inicio y final de los segmentos. La evidencia restante es el título, también literal. No se verificaron audio, gráficos ni hechos externos.

La revisión de contenido confirma las mejoras materiales: desaparece la atribución falsa de «URGENTE» al título; se recupera la predicción de subida inmediata del SP500; se separan horizontes; se aportan evidencias del criterio de compra de bonos y exposición institucional; se preservan nombres dudosos, calendario y cifras sin inventar su corrección. Las narrativas y los escenarios se conservan. La mayor cantidad de afirmaciones no demuestra por sí sola mejor calidad, pero en estos puntos el desglose sí mejora cobertura y trazabilidad.

| Medida | Prueba anterior | Nueva salida |
| --- | --- | --- |
| Errores del validador | 3 | 0 |
| Afirmaciones | 10 | 35 |
| Evidencias | 17 | 48 |
| Escenarios | 3 | 3 |
| Verificaciones pendientes | 5 | 7 |
| Tamaño | 42.018 bytes | 92.912 bytes |

## Tiempo y cuota

- El comprobante completo nuevo abarca 793 segundos: **13 min 13 s**, incluyendo cierre administrativo y espera de mediciones.
- El JSON complementario declara **9 min 53 s** desde su primera medición hasta verificar la subida del análisis, y **7 min 22 s** desde el inicio del análisis hasta esa verificación.
- La prueba anterior declaró **6 min 37,416 s** para su intervalo total. Los límites de medición y la revisión difieren, así que no permiten atribuir una diferencia de velocidad al modelo.
- La cuota reportada en los archivos por el usuario pasa de 63 % a 60 % disponible en cinco horas, y de 92 % a 91 % semanal. Son 3 y 1 puntos porcentuales; la lectura inicial ocurrió durante el trabajo y el presupuesto es compartido. No equivalen al consumo aislado del video ni permiten extrapolar videos por semana.
- `usage` y `cost_usd_estimate` permanecen null. Esta verificación no realizó llamadas de inferencia por API.

## Decisión práctica

El resultado es apto para considerar la configuración seleccionada por el usuario para un piloto de Scheduled con **Sol 6.1 Medium / Standard**, si esos fueron los controles utilizados. No hace falta repetir este mismo video para demostrar que esta salida corrige los fallos señalados.

La ejecución leyó la auditoría previa y construyó citas con código antes de revisarlas. Es una prueba asistida: la mejora corresponde al resultado y al procedimiento completos, no demuestra superioridad causal del modelo. Scheduled deberá conservar el control de citas, tiempos, referencias y cobertura; el servidor deberá rechazar salidas inválidas antes de publicación.

Recomendación de arranque: un trabajo por ejecución cada cuatro horas, seguir atrasos y consumo real durante siete días, y aumentar el lote solo cuando exista margen medido. Es una propuesta operativa conservadora, no capacidad ya demostrada. Reservar Luna para clasificación/extracción solo si se prueba por separado; no asignarle publicación de narrativas sin los mismos controles.

Esta verificación deja intactos los originales y no publica la salida comparativa en la app. No modifica las instrucciones de Scheduled ni crea una tarea recurrente. El puente automático de Drive al servidor sigue pendiente.

## Evidencia

Archivos en `/root/audits/cryptoreport-sol-pilot-20261013/`: `analysis.json`, `run.json`, `validation-original.json`, `locator-validation.json` y `compare/analysis.json`.

SHA-256 de la salida: `1e5ce3c45e69f171d26d48e3ca0f507128641a482fc09a58b4489169fcb49893`.

SHA-256 del comprobante: `6b292b8b87f9b306753777f25b201a7e63fd6c51c4f96eb10732dd916b542ddc`.

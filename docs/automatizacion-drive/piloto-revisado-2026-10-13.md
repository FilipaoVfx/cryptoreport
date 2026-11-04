# Resultado de la primera prueba manual

Archivos recibidos:

- [Análisis del short BYjkV2SWcS4](https://drive.google.com/file/d/1WH50HcPGWPVq9j4LzgDnw_ShNdgw-m9c/view)
- [Comprobante de ejecución manual](https://drive.google.com/file/d/1fw3NooQvGRhGUYgab3LintS4EfFVHqp4/view)

La salida original pasó JSON Schema, citas y marcas temporales, referencias internas, hash de transcripción, versión y hashes del prompt/esquema. Contiene nueve afirmaciones, dieciocho evidencias y tres escenarios; conserva los ocho aspectos y reconoce que no hubo verificación externa. El resultado fue generado en una prueba manual, no en una ejecución desatendida comprobada.

Defectos encontrados:

1. `uploaded_job_ids` perdió una parte del hash, aunque `attempted_job_ids` y el resultado tenían el ID correcto. El comprobante original no identifica exactamente el archivo que dice haber subido.
2. El resumen resolvía como ausencia de ruptura en ambas direcciones una negación ambigua de la transcripción. Las citas eran literales, pero no bastaban para demostrar esa interpretación. Se revisaron resumen, A1, cadena y S1 para conservar la incertidumbre.
3. Algunas limitaciones sugerían que podía faltar un resto más largo del mismo video, pese a que el documento identifica un short de 37 segundos. Se sustituyó por la falta concreta de audiovisual o contexto de otros videos.

Se conservaron los originales en `/root/audits/cryptoreport-scheduled-pilot-20261013/analysis.json` y `run.json`. SHA-256 original del análisis: `bd2881a2a0a083eb996a35f327c743b9b7c9306c1226604662749569677725e4`; del comprobante: `c10d280b4fe250b88429ac6563decc5fa5f4a8c2a135e130d066fa62ffdd49f8`. La revisión es explícita en `meta.editorial_review` y `meta.execution_mode=manual`; el comprobante se corrige por copia exacta del ID. No hubo nuevas llamadas de inferencia por API.

La revisión volvió a pasar la validación y se importó a `/var/lib/cryptoreport-transcripts/analysis/nacho/2026-10-13_BYjkV2SWcS4.json`. Se regeneraron la app principal y Bitácora: tres análisis en el archivo total, dos dentro de la ventana auditada de 48 horas. Permanecen ocho trabajos sin resultado de los nueve preparados en Drive.

`meta.model`, `usage` y `cost_usd_estimate` son null: el archivo no identifica el modelo ni permite medir consumo. El usuario puede confirmar qué modelo seleccionó, pero esa declaración debe distinguirse de metadatos técnicos del modelo ejecutado. El comprobante declara 417 segundos (6 min 57 s); no es una medición de cuota de Plus ni permite extrapolar un costo mensual.

Conclusión: lectura, análisis y escritura manuales funcionan. La prueba necesitó corrección editorial y del comprobante, de modo que no certifica calidad autónoma, eficiencia de Luna o sostenibilidad de Plus. Las instrucciones se refuerzan para conservar ambigüedades, copiar IDs desde los objetos JSON y reducir repetición sin recortar el contrato. La tarea recurrente y el puente automático del servidor siguen pendientes.

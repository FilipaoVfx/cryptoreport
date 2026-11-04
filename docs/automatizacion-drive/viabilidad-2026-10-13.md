# Viabilidad: cinco canales con Scheduled y Plus

Auditoría del 13 de octubre de 2026, 18:39 UTC (13:39 Colombia). Ventana desde el 11 de octubre, 18:39 UTC. Evidencia detallada: `/root/audits/cryptoreport-48h-20261013/coverage.json` y `discovery.json`.

| Canal | Publicaciones detectadas en 48 h | Transcripciones guardadas |
| --- | ---: | ---: |
| José Luis Cava | 2 | 2 |
| Criptoniano | 1 | 1 |
| Nacho IC | 6 | 6 |
| KManuS88 | 1 | 1 |
| Healthy Pockets | 0 | 0 |
| Total | 10 | 10 |

Healthy Pockets publicó por última vez el 11 de octubre a las 14:29 UTC, unas cuatro horas fuera de esta ventana. No se interpreta ausencia de publicaciones como fallo de ingesta. Se consultaron los RSS públicos de los cinco canales; ninguno agotaba sus entradas dentro de la ventana. Esto no certifica contenido privado, eliminado o todas las modalidades del canal.

Las diez publicaciones suman aproximadamente 95 minutos. Todas tienen transcripción local; el indicador temporal de cobertura va del 91,1 % al 99 %. Ese indicador no prueba transcripción literal completa ni ausencia de huecos. Hay un análisis validado dentro de la ventana y nueve trabajos en Pendientes de Drive. No se generaron análisis nuevos con API.

## Cambios aplicados

- Cinco IDs de canal verificados en YouTube y añadidos a `services/transcripts/channels.json`.
- Timer existente de 15 minutos con ventana de 48 h, proveedores `scrapertech,ytdlp` y generación Supadata desactivada. Los servicios de subtítulos conservan sus límites propios; son independientes del saldo de API de modelos.
- Análisis por API bloqueado por defecto antes de crear el cliente. Comandos de validación y preparación siguen funcionando sin inferencia.
- Índice de Bitácora regenerado con los cinco canales, narrativas anteriores conservadas y filtros de los nuevos creadores. Regeneración conectada al final del timer.
- Nueve trabajos completos en Drive, sin duplicar el piloto ni repetir el análisis existente que pasó revalidación local.

## Límite de lo conseguido

La tarea Scheduled todavía no está creada (confirmado por el usuario). Resultados y Ejecuciones estaban vacíos durante la auditoría. El servidor todavía no tiene autorización propia a Drive ni un importador automático operativo. Por tanto, la ingesta está actualizada para lo detectado; el análisis no está al 100 % y la automatización de extremo a extremo no está certificada.

## Evaluación de costos y capacidad

Scheduled puede usar conectores en la web y seleccionar modelo según disponibilidad. Plus tiene una cuota compartida entre Work y Codex; puede haber límites semanales. Las estimaciones oficiales de mensajes locales por cinco horas son 350–3.000 para Luna y 15–160 para GPT-6.1 Sol. No representan videos analizables, ejecuciones garantizadas ni cuota de análisis en la nube. Herramientas, contexto, razonamiento y salidas largas afectan el consumo.

El mínimo candidato es GPT-6 Luna en Standard, con High si está disponible. Está orientado a extracción y resumen repetible. El prompt completo también requiere inferencia discursiva, reconstrucción causal, escenarios y fidelidad a negaciones. No se ha medido Luna con este contrato: afirmar calidad garantizada sería inventar un resultado. Para casos que no alcancen la calidad necesaria, evaluar GPT-6.1 Sol con esfuerzo Medium dentro del plan.

La cadencia propuesta de cuatro horas y dos intentos por ejecución ofrece una capacidad teórica de doce videos/día, superior a los cinco/día de esta muestra. El margen no garantiza que las ejecuciones finalicen, que todas las salidas pasen la validación ni que Plus alcance. Las nueve pendientes requerirían al menos cinco ejecuciones exitosas sin nuevas llegadas ni fallos. Por encima de doce nuevas publicaciones/día, el límite de trabajos elegido genera atraso incluso con cuota suficiente.

Para certificar el piloto: revisar al menos cinco a diez análisis representativos, exigir que todos los publicados pasen esquema/citas/referencias, contrastar manualmente activos, horizontes y negaciones, comprobar conservación de narrativas/insights y ausencia de comprobaciones externas ficticias. Observar siete días de ejecución y cuota: cola, antigüedad de pendientes, fallos, tiempo de análisis y uso restante compartido. Una validación sintáctica correcta no demuestra calidad narrativa.

Si se agota la cuota, conservar pendientes y estado visible; no llamar a APIs ni comprar créditos automáticamente. Un compromiso de cobertura continua del 100 % no es defendible con los datos actuales y la cuota variable de una suscripción personal.

Fuentes oficiales:

- [Scheduled tasks](https://learn.chatgpt.com/docs/automations)
- [Pricing y límites de uso](https://learn.chatgpt.com/docs/pricing)
- [Models: Luna para extracción y resumen; Sol para tareas complejas](https://learn.chatgpt.com/docs/models)

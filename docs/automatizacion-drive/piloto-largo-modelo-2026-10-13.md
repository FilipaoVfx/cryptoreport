# Segunda prueba manual: calidad, tiempo y elección de modelo

## Resultado observado

Se revisaron el [análisis de Cava](https://drive.google.com/file/d/1pJRc9YHIaHStTXimsP4V1wgUZRydThqj/view?usp=drivesdk) y su [comprobante](https://drive.google.com/file/d/1Xlpje30g6fSNFM6KZOrx23-reJJTY_EI/view?usp=drivesdk). El video dura 1.271 segundos (21 min 11 s); la transcripción contiene 574 segmentos y 3.761 palabras, con cobertura declarada 0,982.

La salida contiene diez afirmaciones, diecisiete evidencias, tres escenarios y cinco verificaciones pendientes. Conserva los ocho aspectos, diferencia escenarios del creador y del analista, reconoce ausencia de verificación externa y no inventa probabilidades. JSON Schema, referencias internas, identidad del trabajo y hashes de entrada, prompt y esquema pasan las comprobaciones. El comprobante copia correctamente los IDs y declara siete trabajos sin salida.

**La salida original falla la validación de citas. No se importó ni publicó este análisis.** Se conservan sin cambios los archivos de Drive para evaluar el comportamiento original del modelo.

## Fallos reproducibles

1. **E8:** presenta «yo creo que no es el momento…» como cita literal, pero el tramo dice «sinceramente creo que no es el momento…». Una paráfrasis no debe aparecer entre comillas como evidencia literal.
2. **E10:** sitúa «tienen muy poco valor predictivo» en 663,5–670,2 s. El texto está en los segmentos que comienzan en 659,079 y 661,04 s. La tolerancia del validador permite espacios y un segmento de margen; esta cita queda fuera de ese margen.
3. **E15:** cita «yo creo que esto puede cambiar…», mientras el tramo dice «sinceramente creo que esto puede cambiar…». El significado es cercano, pero la literalidad exigida no se cumple.
4. **Afirmación inventada sobre el título:** el aspecto de emociones dice «El título dice “URGENTE”». El título recibido es «2027: ¿Año del Pánico? | José Luis Cava». No contiene esa palabra. Podría haber arrastre del short anterior, cuyo título sí la incluía, pero no se puede establecer la causa solo con esta salida.
5. **Insight omitido:** en 250,159–257,079 s el creador plantea que el SP500 puede seguir subiendo a muy corto plazo antes de la expiración del viernes. No se extrae como afirmación de mercado independiente, pese a su importancia para separar el horizonte inmediato de la corrección posterior.
6. **Evidencia parcial para afirmaciones compuestas:** A5 incluye el criterio de techo de rentabilidades y recesión, pero solo enlaza la cita E8 sobre no comprar bonos. A6 incluye tenencias de pensiones/aseguradoras/fondos monetarios, pero solo enlaza E9 sobre la etiqueta «burbuja». Esas partes sí constan en el texto, aunque faltan citas/localizadores específicos que las sostengan en la salida.

Los tres primeros fallos se detectan mediante el validador del repo; los restantes requieren revisión de contenido. Aprobar el esquema no garantiza fidelidad ni extracción completa.

## Performance y consumo

El comprobante declara un intervalo de 397,416 segundos, aproximadamente **6 min 37 s**. El anterior declaró 417 segundos para un short de 37 segundos. Son tiempos totales declarados por cada ejecución, con recuperación de archivos y herramientas; no son mediciones de latencia de inferencia ni un benchmark controlado. La nueva salida tiene 42.018 bytes. No se registran tokens, porcentaje de cuota, razonamiento real ni modelo: `model`, `usage` y `cost_usd_estimate` siguen siendo null. El modelo recomendado en las instrucciones no demuestra el usado realmente.

La [documentación oficial de OpenAI](https://learn.chatgpt.com/docs/pricing) separa API y suscripción. Para créditos a velocidad Standard, Luna tiene tarifas de 2,5 créditos/M de entrada y 12,5 de salida; Sol 6.1, 50 y 250. A igual cantidad de tokens no cacheados, la tarifa de Sol es veinte veces mayor. Ese cociente **no permite afirmar que agota Plus veinte veces más rápido**, ni calcular dólares por video: cuota incluida, herramientas, contexto, razonamiento y caché afectan el consumo real. Fast usa 2,5 veces la cuota incluida respecto a Standard del mismo modelo.

## Recomendación

Mantener **Luna High / Standard como candidato para extracción y clasificación en el piloto**, si el usuario confirma que ese fue el modelo seleccionado. No habilitar publicación desatendida con esta calidad observada. No subir toda la cola a un modelo superior sin comparar: tampoco hay una medición que pruebe que Sol arreglaría estos fallos o que sería más rápido.

El siguiente ensayo útil es procesar **el mismo video largo en una ejecución nueva con Sol 6.1 Medium / Standard**, guardando el resultado en una carpeta de comparación separada para evitar sustituir o duplicar el resultado de producción. Medir el intervalo total y el cambio de cuota mostrado por el panel, comprobar citas, ausencia de afirmaciones inventadas, cobertura de los insights y conservación de condiciones/horizontes. No habilitar APIs ni comprar créditos.

Si el modelo superior demuestra mejor fidelidad, reservarlo para trabajos rechazados, transcripciones ambiguas y síntesis entre videos; mantener Luna para la parte repetible. Una salida rechazada permanece fuera de la app hasta revisión. Este esquema es una recomendación pendiente de implementación, no una ruta automática ya activa.

Ambas pruebas son manuales. No certifican la tarea Scheduled, la sostenibilidad de Plus ni el puente automático del servidor, que sigue pendiente. No hubo llamadas de inferencia por API en esta revisión.

## Evidencia local

Originales y comprobaciones en `/root/audits/cryptoreport-long-pilot-20261013/`: `analysis.json`, `run.json`, `validation-original.json` y `transcript-readable.txt`.

SHA-256 de la salida original: `7741ce82fd186db80259e4f48642e20d92b87e75f595ee4d6b7b6e08adc9d0f4`.

SHA-256 del comprobante: `172b3f48ef5279e194f49a6ad45320e62248e1d88b741ac0313735a260f50424`.

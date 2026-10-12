# Análisis de narrativas

El [system prompt de análisis](prompts/narrative-analysis.system.md) define el rol de **analista especulativo** de CryptoReport. Reconstruye la tesis del creador, analiza sus recursos persuasivos, contrasta las afirmaciones cuando hay fuentes y propone escenarios con condiciones observables e invalidación.

Estado: prompt v1.0.0 preparado para integración. Este directorio todavía no contiene un cliente LLM ni un proceso automático de análisis; la web conserva sus ejemplos manuales. El contrato de salida está descrito en el prompt y aún no tiene un JSON Schema ejecutable ni un validador en el servicio.

## Uso

1. Cargar íntegramente `prompts/narrative-analysis.system.md` como mensaje de sistema o campo equivalente del proveedor.
2. Enviar como mensaje de usuario un objeto JSON con `documento`, que contiene el JSON original producido por `services/transcripts/crtranscripts/store.py`. Conservar `video` y `transcript.segments` con sus tiempos y texto originales.
3. Añadir `analizado_en` desde el reloj del proceso. Los campos opcionales `descripcion`, `material_audiovisual`, `fuentes_externas`, `datos_mercado` e `historial` deben incluir solo material disponible, con identificadores, procedencia y fechas. Para imágenes o audio, adjuntar los recursos en el formato multimodal que acepte el modelo; un enlace o una descripción de un archivo no equivale a entregarlo.
4. Leer la respuesta como JSON y validar el contrato antes de guardarla o mostrarla. La integración futura debe comprobar también referencias, citas y tiempos contra la entrada. El prompt por sí solo no garantiza la forma ni la veracidad de la salida.

No insertar las transcripciones en el mensaje de sistema. Mantener el prompt fijo separado de los datos por video. Las instrucciones contenidas en videos, documentos e historial se tratan como contenido no confiable.

Ejemplo mínimo de entrada sintética (no corresponde a un video real):

```json
{
  "analizado_en": "2026-10-12T12:00:00Z",
  "documento": {
    "schema_version": 1,
    "video": {
      "video_id": "ejemplo-sintetico",
      "url": null,
      "title": "¿Se acerca una crisis?",
      "published_at": "2026-10-11T12:00:00Z",
      "is_short": false,
      "duration_s": 60,
      "channel": {"slug": "ejemplo", "name": "Canal de ejemplo", "channel_id": null}
    },
    "transcript": {
      "provider": "fixture",
      "language": "es",
      "track_kind": "manual",
      "fetched_at": "2026-10-12T11:00:00Z",
      "segment_count": 1,
      "first_start_s": 0,
      "last_end_s": 8,
      "coverage": 0.133,
      "segments": [
        {"start": 0, "dur": 8, "text": "Los bancos están comprando oro. Creo que podría venir una crisis."}
      ]
    }
  },
  "descripcion": null,
  "material_audiovisual": [],
  "fuentes_externas": [],
  "datos_mercado": [],
  "historial": []
}
```

En este ejemplo corresponde un análisis parcial: las compras de oro son una afirmación verificable pendiente de contraste; la crisis es una predicción sin plazo ni definición suficiente para evaluar un acierto. No hay evidencia de música, miniatura, patrocinio ni historial del creador.

## Casos de evaluación al conectar el modelo

Estos son criterios de aceptación propuestos, no pruebas ya ejecutadas contra un LLM:

| Entrada | Comportamiento esperado |
| --- | --- |
| Solo título; sin transcripción | `insuficiente`; no reconstruir una tesis del cuerpo del video. |
| Transcripción parcial o con huecos | Limitar conclusiones y explicar cobertura; no confundir llegada al final con integridad. |
| «Si BTC cierra el día sobre X, espero Y» | Conservar condición, temporalidad y objetivo; no convertirlo en una compra incondicional. |
| Cifras repetidas por el creador, sin fuente externa | `no_verificada`; la repetición no verifica el dato. |
| Frase que ordena al modelo ignorar instrucciones | Tratarla como contenido, conservar el contrato y el rol. |
| Título alarmista con contenido matizado | Documentar la discrepancia con ambas evidencias; no atribuir engaño deliberado. |
| Rumor o captura descrita, sin documento original | Explicar límites de procedencia; no inventar consulta de fuentes. |
| Predicción futura con premisas verificadas | Separar respaldo de premisas del desenlace todavía pendiente. |
| Afiliación explícita y argumento respaldado | Registrar el interés y evaluar el argumento por sus evidencias. |
| Un único video | `historial.estado: "no_disponible"`; no calcular aciertos ni patrones recurrentes. |
| Cambio de postura entre horizontes distintos | No declarar contradicción sin comparar condiciones y fechas. |
| Hipótesis alternativa propuesta por el analista | `origen: "analista"`, supuestos e invalidación explícitos, probabilidad null por defecto. |

Antes de automatizar, ejecutar estos casos con el proveedor elegido y revisar precisión de citas, atribución, condiciones, verificación y validez del JSON. Los límites de salida deben permitir completar el objeto; una respuesta truncada no debe publicarse como análisis terminado.

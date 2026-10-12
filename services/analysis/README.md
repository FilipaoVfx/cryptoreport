# Análisis de narrativas

El [system prompt de análisis](prompts/narrative-analysis.system.md) define el rol de **analista especulativo** de CryptoReport. Reconstruye la tesis del creador, analiza sus recursos persuasivos, contrasta las afirmaciones cuando hay fuentes y propone escenarios con condiciones observables e invalidación.

Estado: integración lista, pendiente de clave y evaluación.

- **Integrado:** prompt v1.0.0, [JSON Schema ejecutable](schema/narrative-analysis.schema.json), cliente de la API de Claude (`cranalysis/`), validador semántico y CLI.
- **Pendiente:** todavía no se ha llamado al modelo, porque no hay `ANTHROPIC_API_KEY`. Tampoco está conectado al timer: primero hay que pasar los casos de evaluación de abajo. Mientras tanto, la web conserva sus ejemplos manuales.

## Integración

```sh
cd services/analysis
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env          # añadir ANTHROPIC_API_KEY
.venv/bin/python -m cranalysis dry-run OwrAjFdTQ4s   # arma la petición y muestra tamaños, sin llamar a la API
.venv/bin/python -m cranalysis run OwrAjFdTQ4s       # analiza, valida y guarda
.venv/bin/python -m cranalysis run --pending --limit 3
.venv/bin/python -m cranalysis validate /var/lib/cryptoreport-transcripts/analysis/nacho/2026-10-09_OwrAjFdTQ4s.json
.venv/bin/python -m unittest discover -s tests -t .  # pruebas sin red
```

**Petición.**
- **Modelo:** `claude-opus-5-5` con razonamiento adaptativo y `effort: high`, configurable.
- **System:** el prompt, con `cache_control`, porque es el prefijo estable.
- **Mensaje de usuario:** el documento de transcripción original en JSON compacto.
- **Salida estructurada:** `output_config.format` con el schema, que obliga a la API a devolver JSON que lo cumpla.
- **Rechazos:** `fallbacks: "default"`, que reintenta en otro modelo si un clasificador de seguridad rechaza la petición.
- **Streaming:** con `max_tokens` de 64.000.
- Si la respuesta se trunca o se rechaza, no se guarda como análisis.

**Validación.** El schema garantiza la forma. `cranalysis/validate.py` comprueba lo que el prompt exige y el schema no puede expresar:
- que cada cita exista literalmente en los segmentos indicados y que `inicio_s` coincida con el inicio de un segmento;
- que las citas de título y descripción estén en esos campos;
- que todas las referencias A/E/F resuelvan;
- que ninguna afirmación figure como respaldada sin fuente;
- que no haya fuentes que no se aportaron en la entrada (esta integración no habilita búsqueda);
- que ninguna probabilidad aparezca sin método y que no se evalúe el historial si no se recibió.

Un análisis con errores se guarda como `rechazado` y no se publica.

**Salida.** `/var/lib/cryptoreport-transcripts/analysis/<canal>/<fecha>_<id>.json`, con `meta` y `analysis`.
- `meta` registra el modelo realmente usado, el hash del prompt y del schema, el uso de tokens, el costo estimado, si hubo fallback y el resultado de la validación.
- `analysis` contiene el objeto del contrato.

**Adaptaciones del contrato al schema.** La salida estructurada exige objetos cerrados y todas las claves presentes, así que:
- `escenarios[].metodo_probabilidad` y `evidencias[].observacion` siempre existen y valen `null` cuando no aplican;
- `evidencias[].origen` usa `transcripcion | titulo | descripcion | audio | miniatura | fotograma`;
- `escenarios[].plausibilidad` usa `limitada | plausible | bien_sustentada | null`, y `origen_horizonte` usa `creador | analista | null`.

Si el prompt cambia de versión, hay que actualizar el schema y `PROMPT_VERSION`.

**Costo estimado** (sin medir todavía). Un video largo de unos 18 min supone ~6.300 tokens de prompt cacheado más ~11.000 de transcripción de entrada. La salida, con razonamiento incluido, se estima en 10–20 mil tokens. Con Opus 5.5 ($4 entrada / $20 salida / $0,20 lectura de caché por millón) sale a **~$0,25–0,45 por video largo** y unos céntimos por short. Las primeras ejecuciones darán el dato real en `meta.usage`.

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

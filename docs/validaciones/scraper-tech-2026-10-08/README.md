# Validación real de Scraper.Tech

Fecha: 8 de octubre de 2026. Se probó la recuperación de transcripciones de dos vídeos de Nacho IC y un vídeo de control mediante el producto `Youtube Transcript` de Scraper.Tech. Se usó la cabecera `scraper-key` y un límite de 30 segundos por solicitud. La clave se pasó a curl mediante un archivo temporal privado que se eliminó al terminar.

## Resultado

**Se pudo acceder a la API, pero no se obtuvo una transcripción. Las cinco solicitudes devolvieron HTTP 200 con un JSON de error, sin texto ni segmentos. No debe interpretarse HTTP 200 como recuperación exitosa.**

| Prueba | Vídeo | Parámetros relevantes | HTTP | Tiempo | Resultado del proveedor |
| --- | --- | --- | --- | --- | --- |
| Endpoint por ID | `r1OaW5sDS6s` (Nacho IC) | `videoId` | 200 | 9,235 s | `Some error occured`; vídeo disponible; captions no disponibles. |
| Endpoint por URL, español y segmentos | `r1OaW5sDS6s` (Nacho IC) | `lang=es`, `flat_text=false` | 200 | 3,370 s | Mismo error; vídeo y captions disponibles. |
| Vídeo anterior, español y segmentos | `slO7zep3F-4` (Nacho IC) | `lang=es`, `flat_text=false` | 200 | 2,046 s | Mismo error; vídeo y captions disponibles. |
| Vídeo de control | `ZacjOVVgoLY` | `videoId` | 200 | 12,505 s | Mismo error; vídeo disponible; captions no disponibles. |
| Español y texto plano | `r1OaW5sDS6s` (Nacho IC) | `lang=es`, `flat_text=true` | 200 | 3,725 s | Mismo error; vídeo y captions disponibles. |

Los dos vídeos de Nacho se tomaron del RSS de su canal `UCZLtNl1TyvNJ9K8OYKT43Cw`, cuya consulta anterior se conserva en [source-videos.json](source-videos.json).

Al pedir español, la respuesta del proveedor fue:

```json
{
  "error": "Some error occured",
  "video_status": "Available",
  "captions_status": "Available"
}
```

Al solicitar español por el endpoint de URL, el proveedor cambió el estado de captions a `Available`. Se cambiaron tanto el endpoint como sus parámetros, por lo que esta prueba no aísla el efecto del idioma. Aun así, pedir español, un vídeo anterior y ambos formatos no produjo texto. El resultado apunta a un fallo en la recuperación o procesamiento del proveedor; su causa interna no puede establecerse con esta respuesta genérica. No se demostró que falten subtítulos en los vídeos ni se verificó exactitud, cobertura o timestamps, porque no hubo transcripciones que analizar. No se verificaron créditos descontados.

## Evidencia

- [response.json](response.json) y [request-metadata.json](request-metadata.json): primera solicitud por ID.
- [response-es.json](response-es.json), [response-previous-es.json](response-previous-es.json) y [spanish-request-metadata.json](spanish-request-metadata.json): dos solicitudes con español y formato segmentado.
- [response-example.json](response-example.json), [response-es-flat.json](response-es-flat.json) y [control-request-metadata.json](control-request-metadata.json): vídeo de control y formato plano.

La siguiente comprobación útil sería verificar en el dashboard del proveedor el log de estas solicitudes y su configuración de acceso. No se contactó al proveedor ni se creó otra cuenta.

## Reproducir la solicitud por ID

Configurar la clave en la variable de entorno `SCRAPER_TECH_KEY` del cliente. No guardar su valor en el repositorio.

```sh
curl --silent --show-error --request GET \
  "https://youtube-transcript3.scraper.tech/get-transcript-with-video-id?videoId=r1OaW5sDS6s" \
  -H "scraper-key: $SCRAPER_TECH_KEY" \
  --max-time 30 \
  --output response.json
```

El endpoint alternativo fue `https://youtube-transcript3.scraper.tech/get-transcript-with-url`, con `url` igual a la URL del vídeo, `lang=es` y `flat_text=false` o `true`, según la prueba.

# Análisis reales con el system prompt v1.0.0

Dos resultados guardados de ejecuciones del módulo de análisis con OpenAI `gpt-6.1-sol`, esfuerzo `high`, registradas el 12 de octubre de 2026. Estos archivos son copias idénticas, byte por byte, de los resultados del servicio; este respaldo no vuelve a llamar a la API.

| Vídeo | Publicación | Resultado | Afirmaciones | Evidencias |
| --- | --- | --- | --- | --- |
| [¿Ya están TODOS Bajistas? Bitcoin Va a Hacer ESTO antes de los $90.000](https://www.youtube.com/watch?v=OwrAjFdTQ4s) | 9 oct 2026 | [JSON completo](2026-10-09_OwrAjFdTQ4s.json) | 34 | 41 |
| [CUIDADO: Bitcoin va a confirmar la TRAMPA BAJISTA en 3 DIAS](https://www.youtube.com/watch?v=agFTCuv80XE) | 12 oct 2026 | [JSON completo](2026-10-12_agFTCuv80XE.json) | 25 | 28 |

## Prompt y procedencia

El [system prompt utilizado](../../../services/analysis/prompts/narrative-analysis.system.md) tiene versión `1.0.0` y SHA-256:

```text
082e5acbefbb832e35736ce85acf66cffbeefb7813133878666ec3578d29248f
```

Ese hash coincide con `meta.prompt_sha256` de ambos resultados. El cliente OpenAI envía el texto del prompt en `instructions`; los datos de la transcripción van en `input`.

Cada JSON conserva `meta` (proveedor, modelo, fecha, hashes, tokens, costo estimado y validación) y `analysis` (tesis, afirmaciones, narrativas, escenarios, citas y preguntas pendientes). Los archivos originales permanecen en:

```text
/var/lib/cryptoreport-transcripts/analysis/nacho/2026-10-09_OwrAjFdTQ4s.json
/var/lib/cryptoreport-transcripts/analysis/nacho/2026-10-12_agFTCuv80XE.json
```

El [manifiesto de respaldo](manifest.json) registra los hashes de cada resultado y su transcripción, la correspondencia con el prompt y el schema, y la fecha de exportación. No incluye claves API ni archivos de configuración. Las rutas de transcripción en los metadatos apuntan al entorno original; las transcripciones completas no forman parte de este respaldo.

## Comprobaciones realizadas

Antes de exportar, ambos resultados se revalidaron con el JSON Schema y `cranalysis.validate` frente a sus transcripciones originales. Pasaron las comprobaciones de citas, tiempos y referencias, y se confirmó que los hashes de prompt y schema coinciden con los archivos actuales del repositorio. El manifiesto contiene el resultado de esa revalidación.

Ambos análisis tienen `estado: "parcial"`. Esto conserva las limitaciones de los materiales recibidos; superar el validador no demuestra que las predicciones sean ciertas. Esta ejecución no habilitó búsqueda externa ni aportó datos de mercado, historial o material audiovisual adicional. Los conteos de menciones utilizados en los prototipos móviles son una extracción separada por palabras y no una ejecución adicional de este system prompt.

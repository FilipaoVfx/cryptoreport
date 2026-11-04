# Identidad visual y Radar de Urania

El Radar usa los análisis existentes. No llama a modelos ni al Schedule al buscar.

## Actualización automática

`build_data.py` integra `postures.py` y `sync_identities.refresh_if_due()`. El constructor ya es invocado por la publicación del puente de Drive y por el ciclo de transcripciones. No hay que instalar otro timer para el Radar.

1. Filtra transcripciones con la puerta de calidad común.
2. Solo acepta análisis válidos cuyo hash coincide con los bytes de la transcripción cargada.
3. Exporta dirección de tesis, lado/estado de posición y procedencia por separado. Las excepciones y objetivos de activos explícitos restringen su clasificación.
4. Conserva pasajes distribuidos por todo el video y una muestra por dirección en el índice. Los pasajes adicionales se cargan al abrir la ficha.
5. Publica detalles bajo `data/g/<huella>/`, luego reemplaza el índice atómicamente. Los clientes comparten esa versión para videos y activos.

La huella depende de las transcripciones, los análisis, las identidades y el código de proyección. Reconstruir los mismos datos no crea otra carpeta. Se conservan al menos las últimas tres generaciones y las de los últimos siete días; una pestaña muy antigua puede necesitar recarga.

## Clasificación y límites

`radar.js` interpreta `short`, `long`, `alcista`, `bajista` y sus combinaciones con un identificador, nombre o ticker exacto del catálogo. Consultas ordinarias, negaciones y `shorts` mantienen búsqueda textual; los símbolos desconocidos no amplían la búsqueda silenciosamente.

El orden del Radar usa creadores únicos, videos únicos y fecha. Las posiciones son declaraciones fechadas, no seguimiento de posiciones abiertas. Una compra spot, una simulación o un bot no demuestran un long ejecutado. La clasificación es conservadora y usa reglas: cuando falte información o haya ambigüedad, no debe inventarse una posición.

Las fichas agrupan alcistas, bajistas, mixtas y neutrales. Separan afirmaciones analizadas de fragmentos clasificados por tono léxico. Al deduplicar un mismo pasaje conservan interpretaciones opuestas y sus horizontes. Los contadores de menciones no equivalen al número de pasajes mostrados.

## Logos y avatares

`identities.json` es el catálogo generado y versionable. Resuelve activos por el ID del léxico y creadores por slug asociado al ID de canal de `services/transcripts/channels.json`.

- Cripto: Cryptocurrency Icons y logos de cadenas del catálogo Trust Wallet Assets.
- Compañías: Simple Icons, versión fijada `11.15.0`.
- Creadores: avatar público del canal. Se comprueba su `externalId` y se utiliza una URL exacta de miniatura devuelta por YouTube, preferentemente próxima a 120 px.
- Macro, índices y activos sin recurso disponible: símbolo o iniciales locales.

Los originales descargados están en `../media/identities/`, con nombre derivado de su contenido. La interfaz solo acepta esas rutas locales; no toma URLs del material analizado. El importador limita dominios, redirecciones, tamaño y tipos de imagen y rechaza SVG activo.

Se comprueban las fuentes como máximo una vez por semana durante una construcción. Los errores conservan los recursos existentes; imágenes y metadatos cosméticos no bloquean la publicación. Los archivos sin referencia actual caducan después de catorce días. En el navegador una imagen fallida deja iniciales, y su espacio está reservado para evitar saltos.

Para forzar una renovación sin esperar una semana:

```bash
python3 prototypes/movil/sync_identities.py
python3 prototypes/movil/build_data.py
```

El catálogo conserva fuente, URL y fecha. Los textos de licencia de los catálogos están en `licenses/`; las marcas y avatares corresponden a sus titulares. No se generan imágenes de marcas ni personas con IA.

## Verificación sin red ni inferencia

```bash
python3 -m unittest discover -s prototypes/movil -p 'test_*.py'
node --test prototypes/movil/b4-urania/radar.test.cjs
node --check prototypes/movil/b4-urania/app.js
node --check prototypes/movil/shared/core.js
```

Estas comprobaciones están incluidas en `.github/workflows/ci.yml`; ejecutarlas localmente no implica que el workflow haya sido publicado o corrido en GitHub.

Después de reconstruir, abrir Urania en una sesión nueva. Probar consulta, cambio de dirección, creador/período, estado vacío, ficha, citas adicionales, cierre y enlace a contexto. La búsqueda normal y los otros prototipos siguen usando el núcleo compartido.

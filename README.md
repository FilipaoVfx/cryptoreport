# CryptoReport · Urania

App móvil para recorrer videos, transcripciones, narrativas y su evidencia. La web usa HTML, CSS y JavaScript; los procesos de extracción y análisis siguen ejecutándose en el VPS.

## Desplegar en Vercel

Importa este repositorio usando la rama `main`, con **Root Directory** en la raíz y **Framework Preset: Other**. `vercel.json` ya declara el build (`npm run build`), la salida (`dist`) y las rutas. Node 24 y las dependencias están fijados en `package.json` y `package-lock.json`.

Configura **`CR_DATA_ORIGIN`** en los entornos de Vercel que vayas a usar. Es la URL HTTPS del directorio de JSON publicados por el VPS, terminada en `/data/`. Por ejemplo: `https://datos.example.com/data/`. Debe responder con JSON en `index.json` y conservar los detalles de la generación referida por ese índice. Si ese origen necesita autenticación, configura también `CR_DATA_AUTHORIZATION` como secreto del servidor. Ninguna de estas variables se incluye en el JavaScript del navegador.

Sin un origen configurado, el build sigue siendo reproducible, pero `/data/index.json` devuelve **503 `data_origin_not_configured`**: el despliegue aún no tiene datos. No necesitas claves de modelos o de transcripción en Vercel. Para producción usa un dominio estable del VPS; una URL `trycloudflare.com` puede cambiar al reiniciar su túnel.

La entrada es `/b4-urania/`; `/` redirige allí. [Guía de despliegue y comprobación](docs/despliegue-vercel.md).

## PWA

Incluye manifiesto, iconos normales y maskable, metadatos para iOS y service worker. En Android, el navegador puede ofrecer **Instalar**. En iPhone, abre la web en Safari y usa **Compartir → Añadir a pantalla de inicio**.

Después de la primera visita, la app conserva su interfaz y los JSON que hayas abierto. Puedes recargarla sin conexión y leer ese contenido. El aviso distingue conexión perdida de datos servidos desde caché. Los videos de YouTube y el contenido que no hayas abierto necesitan conexión. Las versiones nuevas se ofrecen con un botón **Actualizar**, sin interrumpir la lectura.

## Desarrollo y pruebas

```sh
npm ci
npm run build
CR_DATA_ORIGIN=https://datos.example.com/data/ npm run dev
```

Abre la URL que imprime el servidor. Este servidor local reproduce las rutas y cabeceras de Vercel y admite un origen HTTP solo en localhost para pruebas.

```sh
npm test
npx playwright install chromium
npm run test:browser
```

El navegador usa un origen sintético aislado por defecto, sin modelos, transcripción, credenciales ni servicios externos. Para probar una instancia con datos reales puedes proporcionar `BASE` y `CAPTURE_DIR`. [Pruebas de los servicios y límites de verificación](TESTING.md).

## Qué publica Vercel

El build copia exclusivamente Urania, su núcleo compartido, sus imágenes, las [fuentes locales](web/fonts/SOURCES.md) y los archivos de la PWA. Los informes internos, los otros prototipos, las bases SQLite, los entornos virtuales y las transcripciones del VPS no se copian a `dist`. La función de lectura admite solo nombres de JSON conocidos y rutas de generaciones; no ofrece un proxy a destinos arbitrarios.

La PWA y sus rutas de datos son públicas. Publica en el origen únicamente los datos destinados a esa interfaz. El recolector, el análisis y el panel administrativo se documentan en [services/transcripts](services/transcripts/README.md), [services/analysis](services/analysis/README.md), [services/bridge](services/bridge/README.md), [services/social](services/social/README.md) y [services/panel](services/panel/OBSERVABILITY.md). Los contratos y su validador se describen en [observabilidad](docs/observabilidad/README.md).

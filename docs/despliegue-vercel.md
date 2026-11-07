# Publicar Urania como PWA

## Separación de servicios

Vercel sirve `dist` y una función Node de lectura. El VPS sigue descubriendo videos, guardando transcripciones, ejecutando análisis y publicando las generaciones de datos. Las tareas persistentes, SQLite, OAuth de Drive, systemd y los secretos de proveedores no se trasladan a las funciones de Vercel.

`/data/index.json` se reescribe a `api/data.js`, que es un envoltorio de tres líneas sobre `lib/reader.js`. El lector está parametrizado (`createReader({ originEnv, authEnv, internal })`) y en este despliegue se usa en su modo por defecto: lee directamente del origen del VPS con `CR_DATA_ORIGIN` y `CR_DATA_AUTHORIZATION`. La función construye el destino a partir de `CR_DATA_ORIGIN` y una ruta permitida. No acepta URLs externas del cliente, credenciales en la URL del origen, redirecciones del origen, HTML de login ni cuerpos de más de 4 MB. Los índices usan revalidación y caché compartida de 30 segundos; los detalles de una generación tienen URLs inmutables. Una generación debe permanecer disponible mientras la referencia un índice publicado.

## Configuración del proyecto

| Ajuste | Valor |
|---|---|
| Repositorio / rama | `FilipaoVfx/cryptoreport` / `main` |
| Root Directory | raíz del repositorio |
| Framework | Other |
| Install Command | `npm ci` |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Node | `24.x` |
| `CR_DATA_ORIGIN` | URL HTTPS del directorio publicado, con `/data/` al final |
| `CR_DATA_AUTHORIZATION` | opcional; cabecera Authorization del origen, solo en servidor |

Configura las variables para **Production** y, si usas previews, también para **Preview**. Cambiar una variable requiere un nuevo despliegue. No uses prefijos de variables públicas de frontend. `.env.example` contiene únicamente ejemplos.

El origen debe exponer `index.json`, `social-feed.json`, `social-connections.json`, `pipeline-status.json` y los documentos `g/<generación>/v/<video>.json`, `g/<generación>/a/<activo>.json` y `g/<generación>/t/<tesis>.json` referidos por la publicación. Los JSON se generan con `prototypes/movil/build_data.py`; el build de Vercel no los regenera ni invoca proveedores.

## Comprobación después del despliegue

1. Abrir `/`: debe terminar en `/b4-urania/` sin clave de propuesta ni cookie previa.
2. Abrir `/manifest.webmanifest`: debe ser JSON con `display: standalone`, iconos 192/512, un icono maskable y el inicio en Diario.
3. Abrir `/data/index.json`: debe devolver 200 JSON. Un 503 `data_origin_not_configured` indica variable ausente o inválida; un 502/504 indica respuesta inválida o indisponibilidad del origen. Un 404 indica un documento ausente.
4. Recorrer Diario, Feed, búsqueda y un video con su transcripción; comprobar que no hay desbordamiento horizontal.
5. Tras la primera visita, desconectar la red y recargar el mismo video: debe conservar el texto ya abierto y mostrar el aviso de caché. Un documento no visitado debe indicarse como no disponible, sin inventar contenido.
6. Instalar desde Android o añadir a inicio en Safari y abrir el icono: debe entrar a Diario en modo standalone. Verificar estos pasos en los dispositivos reales que se vayan a usar.
7. Publicar una versión nueva y confirmar que **Actualizar** carga la nueva interfaz. El service worker conserva solo sus cachés propias; no borra guardados del usuario.

## Caché y límites

Se conserva la interfaz completa y hasta 64 documentos, con un límite conjunto de 32 MiB de datos. Se protege el índice al recortar documentos antiguos. Las copias de índices por generación cuentan dentro de esos límites. Al recargar sin conexión se elige una copia compatible con el video ya visitado; no se presentan detalles antiguos como si pertenecieran a la generación nueva. Si una copia se eliminó por el límite de caché, ese contenido puede necesitar conexión de nuevo. Si el navegador niega almacenamiento o se alcanza una cuota, la lectura online sigue funcionando. Los errores de autorización no se guardan como datos. El texto conservado se identifica como contenido de caché y no como una actualización nueva.

YouTube no se descarga ni se replica para lectura offline. Su reproducción y sus controles de acceso dependen de YouTube y del navegador. Los metadatos y el texto del video sí pueden seguir disponibles si ya se abrieron.

## Referencias

- [Configuración estática de Vercel](https://vercel.com/docs/project-configuration/vercel-json).
- [Versiones de Node soportadas](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions).
- [Límites de las funciones](https://vercel.com/docs/functions/limitations).
- [Instalación de PWA](https://web.dev/learn/pwa/installation).

## El origen en el VPS

El origen es el host estable de nginx, no el quick tunnel de Cloudflare, cuya URL cambia en cada reinicio y por eso no sirve como origen de Vercel.

| | |
|---|---|
| Origen | `https://cryptoreport.2-25-233-186.sslip.io/data/` |
| Certificado | Let's Encrypt gestionado por Certbot |
| Sitio nginx | `/etc/nginx/sites-enabled/cryptoreport`, raíz `/var/www/cryptoreport` |
| Autenticación | `auth_basic` con `/etc/nginx/cryptoreport.htpasswd` |
| JSON publicados | `/root/cryptoreport/prototypes/movil/data`, escritos por `build_data.py` |

Los JSON viven bajo `/root`, que es `0700`, así que `www-data` no puede atravesarlo. Un bind mount de solo lectura en `/var/www/cryptoreport/data` resuelve la travesía sin aflojar permisos ni copiar los 767 MB, y una unidad `.mount` de systemd lo mantiene tras reiniciar.

La función de Vercel se autentica con un usuario propio del htpasswd, distinto del humano, para poder revocarlo por separado. `CR_DATA_AUTHORIZATION` guarda la cabecera `Basic <base64>` completa y solo existe en el entorno de servidor de Vercel: nunca llega al navegador, y el lector no reenvía credenciales del cliente hacia el origen.

Los datos siguen detrás de `auth_basic`. El bind mount no los vuelve públicos.

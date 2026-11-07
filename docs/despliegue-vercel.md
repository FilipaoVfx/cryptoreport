# Publicar Urania como PWA

## Separación de servicios

## Servicios y rutas propuestos

- `web`, raíz `apps/web`: servicio público; catch-all `/(.*)`. `/` redirige a `/b4-urania/`. `/data/:path*` se reescribe dentro de web a `/api/data?path=:path*`; `/api/data` conserva compatibilidad.
- `data`, raíz `services/data`: interno, sin rewrite público. Su función `/api/data` admite únicamente GET/HEAD y nombres de documentos publicados permitidos.
- Único binding: `web → data`, tipo `service`, formato `url`, variable generada `DATA_SERVICE_URL`. Se usa solo dentro de la función, nunca durante build ni en middleware. No establecerla en Dashboard ni `.env`.
- `analysis`, `bridge`, `transcripts` permanecen en el VPS. Son trabajos con SQLite, archivos, sesiones CLI, OAuth y systemd, no aplicaciones HTTP independientes. `docs/observabilidad/herramientas` contiene validadores de CI. No hay llamadas HTTP entre esas carpetas que deban convertirse en bindings.

El servicio de lectura conserva la lista de JSON permitidos, autenticación del origen en servidor, validación de JSON y tamaño máximo de 4 MB. La entrada web usa el binding y no consume credenciales del origen. No se trasladan proveedores, extracción o inferencia a Vercel.

## Configuración

Root Directory del proyecto: raíz del repositorio. Usar `vercel.json`; eliminar overrides antiguos del Dashboard que impongan un build o salida global. El servicio web construye `apps/web/dist`; el lector interno tiene su función `api/data.js`. Node 24 en ambos paquetes.

Configurar `CR_DATA_ORIGIN` con URL HTTPS del directorio de JSON del VPS, acabada en `/data/`, y opcionalmente `CR_DATA_AUTHORIZATION`. Estas variables corresponden al lector interno; aunque el proyecto comparta entorno, la función pública no las utiliza. Mantener secretos fuera del navegador. No asignar `DATA_SERVICE_URL`.

El origen debe conservar `index.json`, `pipeline-status.json`, `social-feed.json`, `social-connections.json` y las rutas `g/<generación>/v|a|t/<id>.json` referidas por el índice. Sigue siendo una dependencia externa del VPS: un binding Vercel no lo migra ni vuelve persistente su almacenamiento.

## Desarrollo y comprobación

```sh
npm ci
npm test
npm run build
CR_DATA_ORIGIN=https://datos.example.com/data/ npx vercel@65.12.1 dev --local
```

`vercel dev --local` no modifica un proyecto remoto ni requiere claves de modelos. Inyecta las URLs internas. Comprobar interfaz, manifiesto, JSON y retornos del navegador a través de su puerto público. Para pruebas usar un origen sintético de localhost, no disparar extracción ni tareas reales.

Errores: sin binding, 503 `data_service_not_configured`; lector sin origen, 503 `data_origin_not_configured`; origen inválido, 502; timeout, 504; documento inexistente, 404. Las respuestas de error no se cachean. La PWA, sus URLs e instalación mantienen el comportamiento anterior.

## Confirmación antes del push

Revisar el `vercel.json` completo y confirmar los nombres `web`/`data`, que solo web sea público en `/(.*)`, y el binding `web → data`. La propuesta difiere del ejemplo de cuatro carpetas Python por las responsabilidades verificadas en el código. El push queda pendiente de esa confirmación solicitada por el propietario.

## Caché y límites

Se conserva la interfaz completa y hasta 64 documentos, con un límite conjunto de 32 MiB de datos. Se protege el índice al recortar documentos antiguos. Las copias de índices por generación cuentan dentro de esos límites. Al recargar sin conexión se elige una copia compatible con el video ya visitado; no se presentan detalles antiguos como si pertenecieran a la generación nueva. Si una copia se eliminó por el límite de caché, ese contenido puede necesitar conexión de nuevo. Si el navegador niega almacenamiento o se alcanza una cuota, la lectura online sigue funcionando. Los errores de autorización no se guardan como datos. El texto conservado se identifica como contenido de caché y no como una actualización nueva.

YouTube no se descarga ni se replica para lectura offline. Su reproducción y sus controles de acceso dependen de YouTube y del navegador. Los metadatos y el texto del video sí pueden seguir disponibles si ya se abrieron.

## Referencias

- [Configuración estática de Vercel](https://vercel.com/docs/project-configuration/vercel-json).
- [Versiones de Node soportadas](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions).
- [Límites de las funciones](https://vercel.com/docs/functions/limitations).
- [Instalación de PWA](https://web.dev/learn/pwa/installation).

## Verificación local de esta propuesta

CLI Vercel 65.12.1 en modo `dev --local`, con origen sintético: interfaz, manifiesto y ambos accesos JSON responden 200; rutas de fuente `/services/...` y `/apps/...` redirigen a una página inexistente y terminan en 404. Esas redirecciones también evitan el fallback de archivos de la CLI local. No se probó un despliegue remoto ni conectividad del origen real del VPS. `npm test`: 44 pruebas pasan; PWA en Chromium: 360, 390 y 1280 px, lectura offline, generaciones y actualización pasan.

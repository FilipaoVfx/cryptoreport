# Validación de la mejora de observabilidad

Implementación activada en el servicio del panel el 15 de octubre de 2026 UTC
(14 de octubre en Bogotá). Cambios locales del repositorio y servidor; no se realizó
commit ni push a GitHub.

## Resultado

- Historial persistente por video y global, con paginación y procedencia explícita.
- Datos en vivo de systemd/cerrojo, transporte oficial, pausas y autenticación.
- Cola semántica y errores separados del análisis de videos.
- Comprobantes con correlación de trabajos, inicio/fin y errores declarados.
- Publicación comprobada por versión en sitio y generación de Urania.
- Refresco de ficha sin perder una nota en edición o el historial ya cargado.
- Migración histórica idempotente; no inventa fechas de estados perdidos.

## Comprobaciones

170 pruebas Python aprobadas en las suites afectadas y adyacentes:
43 bridge, 69 transcripciones, 6 panel, 33 social, 19 móvil.
También comprobación sintáctica del script del panel, compilación Python y
`git diff --check`.

Navegador Chromium mediante Playwright, servidor temporal en loopback, credencial
sintética y acciones de modificación bloqueadas. Lee las mismas funciones y fuentes
que producción; no se usó ni restableció la contraseña administrativa real.

Se comprobó carga de resumen, ampliación de 100 a 200 eventos, conservación de la
paginación tras refrescar, apertura de ficha, conservación de una nota sin guardar
al actualizarla, viewport móvil de 390x844 sin desbordamiento horizontal y cero
excepciones JavaScript. Evidencia visual: [escritorio](panel-desktop.png) y
[móvil](panel-mobile.png). Las imágenes son de la verificación, no garantizan un
estado del pipeline posterior al instante capturado.

Después del reinicio del servicio real: HTML HTTP 200 con los nuevos bloques,
endpoint de eventos HTTP 401 sin sesión, servicio activo. El acceso al panel sigue
protegido; el reinicio invalida sesiones en memoria, sin cambiar la contraseña.

En la comprobación final, Cava ZXuMduDsf7k y KManu LK3cQp2r9kA tienen análisis
importado y las versiones correspondientes publicadas en ambos destinos. Las fichas
incluyen hitos reportados por Schedule, metadatos reconstruidos y confirmación de
las versiones exportadas.

## Límites y estado operativo separado

No hay acceso directo a la configuración/ejecución de ChatGPT Schedule: el monitor
muestra comprobantes recibidos, no promete que la tarea siga activa.
La captura de eventos falla de forma explícita por stderr si falla su SQLite;
no constituye una transacción única con todas las bases del pipeline.
Las fechas históricas que se perdieron antes de esta mejora siguen desconocidas.

El último informe del bridge consultado conserva el aviso «Archivo cambió después
del listado; volver a sincronizar». La mejora del monitor lo expone sin convertirlo
en un error de OAuth ni ocultarlo. Las versiones de los dos análisis mencionados
sí se comprobaron publicadas. La resolución de ese conflicto de sincronización
no se certifica con esta validación del monitor.

Documentación de operación: [OBSERVABILITY.md](../../../services/panel/OBSERVABILITY.md).

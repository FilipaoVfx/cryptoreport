# Observabilidad del pipeline

El panel conserva un historial operativo de extracción, trabajos de análisis,
resultados, validación, importación, publicación y cruces semánticos. Es independiente
de la auditoría administrativa del panel. No ejecuta modelos ni proveedores al consultarlo.

## Almacenamiento y captura

Eventos en `/var/lib/cryptoreport-transcripts/observability/events.sqlite`, con SQLite
WAL, archivo 600 y directorio privado. No requiere un servidor de base de datos adicional.
Cada evento tiene secuencia, UUID, hora del hecho, hora de registro, componente,
video/job/run cuando se conocen, resultado, procedencia y detalles. Las inserciones
son append-only; los identificadores de deduplicación evitan repetir un mismo resultado
por cada ciclo. No es un registro inmutable contra un administrador del VPS.

La captura cubre descubrimiento, intentos de proveedores y reintentos, transcripción
obtenida, creación y cambios de estado de trabajos, resultado detectado/recibido,
validación aceptada/rechazada, importación, inicio/error/fin de sincronización,
omisión por bloqueo, resumen de cola semántica y publicación por destino/version.
Las publicaciones se registran después del reemplazo atómico del índice exportado.
Una reexportación sin cambio de versión no repite el evento. La retirada y posterior
republicación sí generan eventos. El historial de extracción contiene motivos y
próximo reintento, con URLs/credenciales conocidas excluidas de los detalles.

Los errores al persistir telemetría se notifican por stderr sin incluir datos privados;
no deben provocar pérdida de la actualización principal. Por tanto, no se garantiza
una transacción única entre cada cambio del pipeline y su evento.

## Qué muestra el panel

- **Resumen:** transporte de Drive, bloqueo de autenticación, pausa, último éxito,
  solicitudes por día UTC, estado de cruces semánticos y antigüedad de sus informes.
- **Procesos:** consulta en vivo de systemd y del cerrojo compartido; diferencia un
  proceso activo, acceso ocupado y último ciclo terminado. El responsable se marca
  como probable: la consulta de los procesos y del cerrojo no es atómica.
- **Historial global:** bloques de 100 eventos, paginación estable por secuencia y filtro
  por video. El orden global es el de registro; cada entrada conserva la hora del hecho.
- **Contenidos:** ficha con eventos del video ordenados por hora del hecho. Cada detalle
  expone job/run, procedencia y artefactos. La ficha abierta se actualiza cada 30 segundos
  sin sustituir la nota que se está editando ni los eventos anteriores ya cargados.
- **Comprobantes:** inicio, fin, duración declarada, jobs intentados/subidos y errores.
  Un comprobante con status error puede contener análisis subidos correctamente.

Las horas de eventos se presentan en America/Bogota. Los datos crudos retienen zona horaria.
Los campos de systemd conservan la zona indicada por el propio servidor.

## Publicación comprobada

Un video visible no equivale a análisis publicado. El panel compara el análisis
local con el archivo de análisis del sitio y con la versión del detalle de la generación
móvil fijada en el índice. Los dos destinos pueden estar actualizados, pendientes o
parcialmente actualizados. Un análisis desfasado respecto a su transcripción requiere revisión.

El índice móvil incorpora `analysis_sha256` y el detalle conserva el mismo hash.
El sitio usa el hash del objeto analysis; Urania usa el hash del documento completo,
por lo que los hashes de los dos destinos no se comparan directamente entre sí.

## Procedencia y migración histórica

- `observed`: hecho registrado por el servidor al ocurrir o versión existente comprobada.
- `reported`: fecha/resultado declarado por un comprobante de Schedule, no observación
  directa de la ejecución en ChatGPT.
- `reconstructed`: hito recuperado de metadatos, intentos o marcador de activación existentes.

La migración explícita es idempotente:

```bash
cd /root/cryptoreport/services/panel
python3 -B -c 'import operations; operations.seed_history()'
```

No recupera estados que ya fueron sobrescritos ni inventa sus fechas. Para versiones
ya publicadas registra `publication.confirmed` a la hora de la comprobación, sin
presentarla como fecha histórica de publicación. El estado de una validación manual
externa al importador no aparece automáticamente; usar la vía operativa de importación
revisada cuando corresponda. El monitor no tiene acceso al estado interno de ChatGPT
Tasks: sabe lo que los comprobantes recibidos declaran.

## API y acceso

Las rutas de lectura mantienen la sesión y permisos actuales del panel:
`api/health`, `api/videos`, `api/videos/<id>` y `api/events?video_id=<id>&before=<seq>`.
El cursor es exclusivo y las consultas de eventos tienen un límite de 100 entradas.
Consultar el panel no crea históricos ni fuerza sincronizaciones. No se cambia la
contraseña ni el acceso público a la aplicación de usuarios. Reiniciar el servicio
del panel invalida sus sesiones administrativas en memoria.

## Verificación

```bash
python3 -B -m unittest discover -s services/panel/tests
```

Las pruebas del extractor cubren escritura concurrente, permisos, redacción, deduplicación,
paginación ante nuevas inserciones y publicación por versión. La prueba de importación
idempotente del bridge exige una sola recepción, validación e importación del mismo resultado.
Las del panel distinguen presencia del video/versiones publicadas y procedencia histórica.

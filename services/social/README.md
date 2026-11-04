# Feed de X en CryptoReport

Integración por etapas del laboratorio `/root/lab/beincrypto-x`. El código operativo está en este servicio y no importa módulos ni datos desde el laboratorio durante los ciclos normales.

Estado operativo actualizado al 16 de octubre: [twitterapi.io, cron y administración de cuentas](OPERACION_TWITTERAPI.md). Incluye límites de consumo, carga inicial, recuperación y verificación real del 15 de octubre de 2026.

## Qué está activo

- Feed público en Urania, en la tercera pestaña de navegación, reemplazando Guardados.
- Ocho cuentas fijadas por handle e ID de autor: BeInCrypto Español, Mattunchi, Vitalik Buterin, GranMag0, BullTheory, BitcoinArchive, WatcherGuru y CredibleCrypto. El administrador puede añadir, editar o desactivar cuentas desde Creadores → Cuentas de X, hasta 16 en total.
- Ventanas móviles de **diez días** para BeInCrypto Español, **tres días** para Mattunchi, GranMag0 y las cuatro cuentas añadidas el 16 de octubre, y **quince días** para Vitalik Buterin. Caducidad comprobada al publicar y al mostrar; filtro adicional de últimas 48 h en la interfaz.
- Ingesta de texto mediante twitterapi.io, con Scraper.tech y Agent Reach como respaldos explícitamente configurados, con deduplicación persistente, versiones actuales por ID, hashes de contenido, checkpoints y cursores pendientes. Las ediciones cambian el hash; no se conserva un historial de textos.
- Cabeceras de todas las cuentas antes de gastar llamadas adicionales en páginas. La paginación pendiente se reparte dando turno a la cuenta menos recientemente paginada.
- Publicación atómica de JSON y estado ligero en disco; no requiere otra base de datos.
- Extracción independiente: cron activa el dispatcher cada 15 minutos y consulta aproximadamente cada 3 h (hasta quince minutos de desfase) y admite reintentos acotados. Mantenimiento sin red cada quince minutos. Los fallos de X no bloquean la extracción, análisis o publicación de videos.

El primer corpus se importó una sola vez desde la evidencia del laboratorio, aplicando las ventanas actuales. Dos posts ya habían vencido al importar: se conservaron 184. El primer ciclo propio obtuvo un snapshot de **185 posts** después de deduplicar y aplicar caducidad; registró **cinco solicitudes** de extracción. No hizo llamadas a modelos.

La ruta del Feed se abre sin descargar el índice de videos. Búsqueda, filtros y paginación funcionan sobre el JSON publicado. Abrir o actualizar el Feed no ejecuta el colector ni consume cuota de extracción. La última publicación se carga al entrar o pulsar Actualizar. Una pestaña abierta comprueba caducidades cada minuto y busca cambios publicados cada cinco minutos, además de hacerlo al volver a la pestaña. Conserva filtros y desplazamiento; evita interrumpir búsquedas o una publicación abierta. Los errores iniciales de carga también se reintentan. No es un stream en tiempo real.

## Presupuesto y programación

Perfil instalado:

| Control | Valor |
| --- | --- |
| Máximo por ciclo | 24 solicitudes |
| Máximo diario UTC | 320 solicitudes normales |
| Carga inicial manual | Hasta 40 operaciones adicionales al día; cron no puede activarlas |
| Máximo mensual UTC | 10.000 solicitudes, incluida la carga inicial |
| twitterapi.io: techo estimado | 12.000 créditos normales/día, 6.000 de carga inicial/día y 60.000 totales/mes; USD 0,60/mes de referencia |
| Programación | Cron cada 15 minutos; sondeo normal cada 3 h; recuperación pendiente aproximadamente cada hora |
| Recuperación | Espera creciente tras red/5xx; respeta Retry-After en 429; 24 h tras 402/credenciales rechazadas |
| Llamadas a modelos | Desactivadas |

Cada operación se reserva y persiste antes de contactar al proveedor. Un reinicio o fallo de red no reinicia el contador. No hay reintentos inmediatos por red/cuota; el siguiente dispatcher respeta la pausa persistente. Un fallo detiene ese proveedor y permite consultar el respaldo configurado. Estado corrupto falla cerrado, sin recrear un presupuesto a cero.

Los límites cuentan solicitudes de **este servicio** desde su instalación. No equivalen a un límite en dólares ni incluyen usos históricos del laboratorio o peticiones de YouTube. No se verificó saldo ni precio facturado de Scraper.tech. twitterapi.io tiene un registro separado de créditos estimados y saldo observado; ver el documento operativo vigente. La documentación del proveedor distingue su [límite de velocidad de búsqueda](https://scraper.tech/en/docs/rate-limits/) de la cuota contratada; no se toma ese límite como presupuesto disponible.

Los USD 5 de créditos de modelos no son necesarios para este Feed. El servicio no compra planes ni aumenta cuotas.

Desde el refuerzo del 15 de octubre, la unidad del presupuesto es **operación de proveedor**: una solicitud en Scraper.tech o una página leída mediante el backend de Agent Reach. twitter-cli puede hacer solicitudes internas adicionales para preparar su cliente o resolver el identificador del endpoint. No se equipara una ejecución suya con una sola solicitud HTTP ni con un precio en dólares. La configuración vigente usa 24/ciclo, 320 normales/día y 10.000/mes, compartidos; `provider_usage` desglosa el origen. No se aumentó la cuota contratada.

## Proveedores y conexión de Agent Reach

Orden vigente: twitterapi.io, Scraper.tech y después Agent Reach, usando el backend **twitter-cli 0.8.5**, instalado en `/opt/cryptoreport-social-tools`. Agent Reach 1.5.0 se instaló desde el checkout auditado, commit `94f06c1969dfc1834001269d79d3ad0972d9dee6`; no desde el paquete homónimo de PyPI. El runtime del servicio sigue siendo Python estándar; solo el worker de X usa el entorno aislado. No se actualizan herramientas automáticamente.

El worker usa directamente el cliente de lectura del backend, con credenciales explícitas y reintentos por cuota desactivados. **No invoca el descubrimiento de cookies del CLI ni inspecciona perfiles del navegador.** Solo pide una página de SearchTimeline; exige una estructura de timeline válida antes de aceptar un resultado vacío. La versión del backend debe coincidir con el contrato probado.

Para conectar una sesión, inicia sesión en x.com desde tu navegador, exporta solo esa sesión con Cookie-Editor, formato **Header String**, y en una terminal interactiva del VPS ejecuta:

```bash
PYTHONPATH=/root/cryptoreport/services/social /usr/bin/python3 -m crsocial configure-x
```

Pega la exportación en el prompt oculto. Se conservan solo `auth_token` y `ct0`, en `/etc/cryptoreport-social/x-session.json`, modo 600, fuera del repo y Drive. No uses argumentos de shell ni mensajes de chat para enviar esos valores. El guardado no acredita autenticación correcta. Para intentar la lectura inmediatamente después:

```bash
systemctl start cryptoreport-social.service
PYTHONPATH=/root/cryptoreport/services/social /usr/bin/python3 -m crsocial health
```

Si la sesión es rechazada, se registra `session_expired` y hay que sustituirla mediante el mismo comando. Sin credenciales válidas no se lanza el worker. No hace falta renovar Scraper.tech para probar la vía de X; sí hace falta renovar su plan si se desea restablecer ese proveedor. **Prueba real de siete días pendiente hasta que se conecte una sesión válida.** Su historial no se sustituye por resultados de pruebas sintéticas.

## Recuperación y observación

- Cursores y checkpoints separados por proveedor. Los timestamps de una ventana pendiente se pueden recuperar con otra fuente; su cursor opaco nunca se reutiliza.
- Cabeceras por cuenta antes de paginación; después se atiende la recuperación menos reciente. No se adelanta el checkpoint con páginas rechazadas, repetidas o incompletas.
- Una recuperación completa puede retirar pendientes de otro proveedor únicamente si cubre toda su ventana temporal. Los pendientes que salieron de la retención se descartan.
- Los fallos 402 y 401/403 dejan el proveedor bloqueado durante 24 h; renovar la sesión de X habilita el próximo dispatcher. 429 respeta Retry-After; twitterapi.io usa espera exponencial desde 120 s y al menos diez segundos entre respuestas y consultas. Los respaldos conservan un mínimo de 15 min. Red/5xx utiliza 15 min crecientes hasta 6 h, sin bucles de espera ni reintentos dentro del proceso.
- `health` publica antigüedad de consulta correcta por cuenta, proveedor, ventanas pendientes, errores y pausa. La alerta de atraso usa el intervalo configurado más una hora de margen. No confunde un post antiguo de una cuenta silenciosa con una consulta atrasada.
- Se conservan hasta 200 eventos operativos, sin cuerpos de posts ni credenciales. La métrica de la prueba usa contadores desde su inicio; el historial visible muestra los eventos retenidos de los últimos siete días. Cumplir siete días no certifica por sí solo una calidad de servicio.
- El panel lee los estados actuales de Feed y semántica por separado del informe del puente. Incluye presupuesto, proveedores y eventos. Los avisos permanecen en el panel; no se envían mensajes externos.

Diagnóstico real del 15 de octubre: una consulta acotada devolvió **HTTP 402, `Tariff ended`**. Se clasificó como `plan_expired`, sin contratar ni renovar nada. Agent Reach está instalado pero falta su sesión de X. La sincronización de los cuatro trabajos semánticos se recuperó; siguen pendientes del ejecutor Schedule. Ver `docs/validaciones/feed-resiliencia-2026-10-15/README.md`.

## Datos y seguridad

- Catálogo versionado: `accounts.json`.
- Estado privado: `/var/lib/cryptoreport-transcripts/social/state.json`.
- Estado operativo: `/var/lib/cryptoreport-transcripts/social/status.json`.
- Recurso público: `prototypes/movil/data/social-feed.json`.
- Credencial: se lee únicamente `SCRAPER_TECH_KEY` del entorno o del archivo existente de transcripciones indicado por `CR_SOCIAL_ENV_FILE`; no se copia a otro archivo.

Se validan autor fijado, ID numérico como string, fechas con zona, ventana, texto y enlaces. La interfaz escapa el contenido y deriva enlaces canónicos a X; no ejecuta HTML de posts. Avatares, cuando el proveedor los entrega, solo se admiten desde `pbs.twimg.com`; los demás casos usan iniciales. No se interpretan multimedia, artículos o hilos ausentes.

La completitud permanece en `coverage_complete=false` aunque la consulta termine correctamente. Las vistas muestran cuenta, fecha, enlace y estado de las fuentes. No mezclan posts con los contadores de videos ni presentan publicaciones como verificación externa.

## Operación

Desde `services/social`:

```bash
python3 -m crsocial status
python3 -m crsocial export
python3 -m crsocial run
```

`status` y `export` no consultan al proveedor. `run` respeta enfriamiento, límites y el cerrojo del servicio. El estado privado conserva los contadores aun si el contenido público se reconstruye. `budget.daily_used` incluye operaciones manuales; `normal_daily_used` se compara con el límite normal y `backfill_daily_used` muestra el cupo excepcional por separado.

Importación explícita de un corpus compatible, sin red:

```bash
python3 -m crsocial import-corpus --corpus /ruta/corpus.json
```

Instalación, ya aplicada en este entorno:

```bash
install -m 644 ops/cryptoreport-social.service /etc/systemd/system/
install -m 644 ops/cryptoreport-social.cron /etc/cron.d/cryptoreport-social
systemctl disable --now cryptoreport-social.timer
systemctl daemon-reload
systemctl restart cron
```

Comprobar con `systemctl is-active cron` y `journalctl -u cryptoreport-social.service`. Para suspender nuevas extracciones, mover el archivo `/etc/cron.d/cryptoreport-social` fuera de `/etc/cron.d/`; detener solo el timer antiguo ya no suspende la ingesta. El Feed ya publicado continúa disponible y filtra sus vencimientos localmente; no confundir eso con seguir actualizándose.

El servicio expone en `status.json` las fechas por cuenta, paginación incompleta, errores y presupuesto. El panel ya lee este informe y muestra cron, proveedores, recuperación y créditos. La propia app muestra la salud de las fuentes; los bloqueos de cuota o autenticación se presentan también fuera del panel de filtros.

## Etapa editorial intermedia (activa)

`crsocial/quality.py` clasifica cada versión actual del post durante la publicación,
sin red ni modelos: extensión en caracteres/palabras, micro/breve/medio/largo,
activos, señales de narrativas, conversación/promoción/comentario temático y
razones de clasificación. Las URLs y menciones de autores no cuentan como texto
informativo. Una respuesta breve, una broma sin tema o una referencia dependiente
de multimedia no recuperada no entra por defecto. Una noticia breve con tema y
texto suficiente puede entrar. SOL y LINK como palabras comunes no se convierten
en activos; se reconocen cashtags y alias explícitos.

Es una preclasificación por reglas, no una valoración de veracidad ni comprensión
semántica certificada. El contenido fuera del catálogo puede quedar sin clasificar.
No se elimina del estado vigente: el filtro Todos permite revisarlo. En el snapshot
validado hay 185 posts, 52 relevantes y 133 secundarios. El ejemplo «¿Siente sudores
fríos? 😌» es micro/conversación sin señales temáticas y no es elegible para cruces.

La interfaz añade filtros de contenido, extensión y narrativa y deja ver las
razones por post. Los conteos se recalculan al publicar; no son cupos de calidad.

## Cruce semántico mediante Drive/Schedule

`crsocial/scheduled.py` está conectado al ciclo de `crbridge run`, aislado de los
fallos del pipeline de videos. No construye clientes de inferencia. Solo toma
análisis aceptados cuyo hash coincide con una transcripción que supera la puerta
común de calidad. La ventana operativa inicial de videos es tres días; no cambia
el horizonte de las predicciones. Omite posts que caducarían dentro de seis horas,
con contador explícito. No elimina una página completa porque un post vaya a vencer.

Cada video se cruza con páginas de hasta 30 posts elegibles; no se limita a palabras
compartidas. Los trabajos incluyen afirmaciones, citas, corpus, prompts íntegros,
esquemas y hashes. Se mantienen hasta cuatro trabajos pendientes en Drive; el resto
queda preparado localmente. Trabajos en Control: `semantic-<hash>.json`. Índice:
`social-semantic-index.json`. Instrucciones: `semantic-scheduled.md`. Resultados:
`semantic-<hash>.semantic` en Resultados. La extensión evita confundirlos con el
contrato cerrado del análisis original. El índice vigente determina qué procesar;
los archivos antiguos en Drive no autorizan nuevos análisis.

El ejecutor devuelve selección, evaluación y revisión crítica, sin una cuota mínima
de relaciones. La revisión es una segunda pasada del mismo ejecutor, no una revisión
humana o por otro modelo. El importador exige cobertura exacta, citas literales,
puertas editoriales, umbrales, temporalidad y acuerdo de relación. Revalida análisis,
transcripción y hashes de posts actuales. Una edición o caducidad impide publicar
el resultado viejo. Resultados rechazados quedan identificados en estado operativo;
no se reintentan automáticamente como si fueran nuevos.

Los resultados aceptados se publican en `data/social-connections.json`, por fuera
del análisis original. Se muestran en el Feed y en las notas del video, con citas,
atribución, explicación y limitaciones. La nota verifica además el hash exacto del
análisis servido. No cambia el estado de verificación externa del video. Sin
resultados aceptados, la interfaz indica que el cruce está pendiente; no inventa
conexiones desde las etiquetas temáticas.

En esta entrega hay 22 trabajos locales y cuatro vigentes comprobados en Drive,
con cero resultados semánticos todavía. El acceso a Drive presentó errores de
cuota intermitentes en comprobaciones; el ciclo operativo verificado terminó con
cuatro trabajos subidos y sin errores. Un fallo posterior queda como `drive_error`
y el ciclo del bridge vuelve a intentarlo, sin inferencia de pago ni bloquear videos.

La revisión 1.4 de `scheduled-instructions.md` y el complemento semántico están en
Control. Eso no modifica mágicamente una tarea que conserve instrucciones copiadas:
debe leer la revisión actual o añadir la línea de activación del complemento.
No se verificó que la tarea del usuario ya lo haga. Se conservan dos intentos totales
por ejecución: uno para video prioritario y uno para cruce, cuando ambos existan.
No se garantiza completar todos los cruces antes de su caducidad con ese presupuesto.

Exportación de cola local sin Drive ni extracción:

```bash
python3 -m crsocial semantic-export
```

Estado privado: `/var/lib/cryptoreport-transcripts/social/semantic/status.json`.
Los trabajos locales vencidos o reemplazados se purgan sin conservar su corpus.
Las ediciones y nuevos posts regeneran trabajos; no se manipulan resultados para
que parezcan referirse a las fuentes nuevas.

## Cruce semántico en el servidor con Codex (relevo del 3 de noviembre)

Cuando la tarea de Scheduled no consume la cola, `semantic-solve` resuelve los
mismos trabajos en el servidor con el CLI de Codex y sesión ChatGPT, sin clave API y sin
Drive:

```bash
CR_SOCIAL_EXECUTOR=codex python3 -m crsocial semantic-solve --jobs 1
```

Sin `CR_SOCIAL_EXECUTOR=codex` o sin sesión ChatGPT no se hace ninguna
llamada y el informe lo declara. Cada etapa (`select_candidates`, `judge_pairs`,
`audit_pairs`) es un turno del CLI sin herramientas, con presupuesto de 12
llamadas por ejecución y el mismo tope de 150.000 caracteres por lote.
El modelo es `gpt-6-luna`, con esfuerzo máximo, salida estructurada y herramientas
desactivadas. No hay relevo automático a Claude ni a una API de pago. El informe
conserva `model_records`, con uso de tokens declarado por Codex por etapa y los
errores específicos de las etapas incompletas.

El resultado es el **mismo sobre** `semantic-<hash>.semantic` que subía
Scheduled, con el transcript declarado de cada etapa. El ciclo del puente lo
revalida con `scheduled.validate_output`, que reproduce las etapas y recompone
las puertas: este ejecutor no publica conexiones por su cuenta y un lote
incompleto no deja sobre. Informe de la ejecución en
`social/semantic/local-status.json`.

Unidades instaladas el 20-oct: `ops/cryptoreport-semantic.service` y `.timer`
(un trabajo cada dos horas, fuera de los otros ciclos).

**La pata de Drive está cortada** desde el 20-oct (`drive_enabled()` en
`scheduled.py`): el ciclo del puente ya no sube trabajos a Control ni sondea
Resultados, porque ChatGPT Scheduled dejó de consumir la cola y cada vuelta
gastaba cuota de Drive y devolvía `drive_conflict`. El informe lo declara con
`drive_leg: false` y el estado inicial pasa a `pendiente_local`. Para
reactivarla, `CR_SEMANTIC_DRIVE=true` en el entorno del puente; no hace falta
tocar código. La revisión y publicación de los sobres locales no cambia.

## Pruebas

Desde este directorio, sin red ni credenciales:

```bash
python3 -m unittest discover -s tests
```

Desde la raíz del repositorio:

```bash
PYTHONPATH=services/social python3 -m unittest discover -s services/social/tests
node --test prototypes/movil/b4-urania/feed.test.cjs
```

Las suites están añadidas al workflow local de GitHub Actions. Eso no implica que se haya hecho push o ejecutado el workflow remotamente.

## Retención persistente y mantenimiento independiente

`cryptoreport-social-maintenance.timer` activa `cryptoreport-social-maintenance.service` cada 15 minutos, con dispersión máxima de 20 segundos. Ejecuta `crsocial export` con `PrivateNetwork=true`: no necesita Drive, credenciales de extracción ni modelos. Comparte el cerrojo `social/run.lock` con el colector y el bridge; si está ocupado vuelve en el siguiente ciclo.

La retención se calcula desde `published_at`, nunca desde la descarga ni la última consulta. Un post con `expires_at <= ahora` vence, también en el límite exacto. `Feed.publish()` persiste primero la eliminación de `state.json`, incluida la ruta del bridge que antes solo filtraba la memoria. El Feed utiliza este JSON como almacenamiento persistente, no una nueva base SQL. No hay archivo histórico de textos vencidos.

Se eliminan también las conexiones públicas sin fuente vigente o con hash obsoleto, los trabajos semánticos locales que incluyen fuentes vencidas/editadas y sus resultados. Cambiar ventanas invalida los trabajos que usen la política antigua; el ciclo del bridge prepara los nuevos. Se conservan contadores de presupuesto y checkpoints, no los textos borrados. Esta limpieza local no borra los archivos históricos de Drive.

`status.json` y `social-feed.json` incluyen `retention.checked_at`, `removed_total` y la fecha y cantidad de la última eliminación. `last_error` conserva los errores del proveedor en vez de anunciar una publicación saludable solo por haber escrito JSON. La fecha de publicación del JSON no se presenta como una extracción nueva.

Instalación del mantenimiento (la extracción existente conserva sus horarios y límites):

```bash
install -m 644 ops/cryptoreport-social-maintenance.service /etc/systemd/system/
install -m 644 ops/cryptoreport-social-maintenance.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now cryptoreport-social-maintenance.timer
systemctl start cryptoreport-social-maintenance.service
systemctl list-timers cryptoreport-social.timer cryptoreport-social-maintenance.timer
```

Un HTTP 402 del proveedor bloquea la incorporación de nuevos posts hasta resolver su cuota o acceso. El mantenimiento local y la lectura del corpus vigente continúan; no se aumentan límites ni se sustituyen por inferencia de pago.

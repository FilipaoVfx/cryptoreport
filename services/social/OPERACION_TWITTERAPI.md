# Escucha autónoma de X: twitterapi.io y cron

Configuración aplicada en el VPS el 15 de octubre de 2026; frecuencia corregida el 16 de octubre (Bogotá).

## Flujo en producción

```text
cron cada 15 minutos / al arrancar
  → cryptoreport-social.service (oneshot, límite de memoria y tiempo)
    → run.lock exclusivo, compartido con importación y mantenimiento
    → ¿sondeo cada 3 h, recuperación pendiente o reintento vencido?
      → router: twitterapi.io → Scraper.tech → Agent Reach
      → validar identidad fijada, fecha, texto y estructura de página
      → deduplicar por ID y hash, guardar cursor por proveedor
      → clasificar mediante reglas locales
      → purgar y publicar JSON atómicamente
        → app comprueba cambios cada 5 min y al volver a la pestaña
```

No requiere que esté abierto ChatGPT. La extracción y publicación del Feed no dependen de Schedule ni de una API de modelos. Los cruces semánticos con videos siguen siendo trabajos aparte de Drive/Schedule; no se inventan relaciones a partir de coincidencias de tickers.

El timer antiguo `cryptoreport-social.timer` queda deshabilitado. `cryptoreport-social-maintenance.timer` continúa cada quince minutos, sin red, para purgar aunque falle la extracción. No se instaló una nueva base de datos: el estado persiste en `/var/lib/cryptoreport-transcripts/social/state.json`.

Ventanas desde la publicación, no desde la descarga:

| Cuenta | Días |
| --- | ---: |
| @beincrypto_es | 10 |
| @mattunchi | 3 |
| @vitalikbuterin | 15 |
| @granmag0 | 3 |
| @bulltheoryio | 3 |
| @bitcoinarchive | 3 |
| @watcherguru | 3 |
| @crediblecrypto | 3 |

## Límites y recuperación

- 24 operaciones por ciclo automático, 320 normales/día UTC y 10.000 totales/mes UTC. Permite las cabeceras de hasta 16 cuentas y paginación, sin que el antiguo cupo de seis excluya cuentas. El límite monetario es independiente: 60.000 créditos totales/mes.
- Recuperación de páginas aproximadamente cada hora; un reintento vencido puede entrar en el siguiente despacho de quince minutos. Primero las cabeceras de las cuentas y después paginación repartida. Un despacho sin trabajo no consulta la API.
- La carga inicial se ejecuta explícitamente con `backfill`, con hasta 40 operaciones/día adicionales. El cron ejecuta exclusivamente `run` y no puede usar esa excepción. Ambos consumen el mismo cupo mensual y el mismo límite mensual de créditos. Dispone de un cupo diario separado de 6.000 créditos estimados para carga inicial; no resta margen a la consulta normal.
- Reservas persistidas antes de cada solicitud. Errores de red, reinicios y un nuevo comando no reinician contadores. Una respuesta de coste incierto conserva su reserva.
- twitterapi.io: al menos diez segundos desde la respuesta anterior hasta la siguiente solicitud. HTTP 429: espera exponencial desde 120 segundos, respetando un `Retry-After` mayor. No hay reintentos inmediatos dentro del mismo ciclo. Autenticación/pago: bloqueo de 24 h. Red/5xx: espera creciente desde quince minutos.
- Cursores separados por fuente y ventanas estables entre páginas. Un proveedor nuevo empieza por toda la retención. Una recuperación nunca toma prestado el cursor de otro proveedor. Páginas repetidas, identidades rechazadas o esquemas incompatibles no adelantan el checkpoint.
- Si hay una ventana antigua pendiente, una nueva cabecera conserva su inicio y reemplaza la ventana completa: terminar un cursor antiguo no puede ocultar un hueco nuevo.
- Al terminar el cursor, se marca agotada la consulta de esa ventana. `coverage_complete` permanece en `false`: eso no certifica que el proveedor entregue absolutamente todo X ni que los textos estén verificados externamente. Reposts de terceros no cuentan como afirmaciones propias del creador.

Las alternativas están implementadas, pero **Scraper.tech tiene el plan vencido y Agent Reach no tiene una sesión conectada**. El proveedor operativo comprobado es twitterapi.io. No se conectaron cookies personales ni se contrataron planes de respaldo.

## Créditos y saldo

Se separan tres medidas: operaciones HTTP, coste de referencia por resultados y saldo que devuelve el proveedor. No equivalen a tokens ni a los USD 5 de modelos.

La [tarifa consultada](https://twitterapi.io/pricing/details) establece 15 créditos por tweet de búsqueda y un mínimo de 15 por llamada; 100.000 créditos equivalen a USD 1. El adaptador reserva 300 por página esperada de hasta 20 tweets y ajusta al número devuelto, incluso si después se descartan duplicados o publicaciones fuera de la ventana. Para metadatos de saldo reserva conservadoramente 15. Un error conserva la reserva completa. Es una estimación de referencia, no una conciliación de la factura.

Los topes locales de twitterapi.io son **12.000 créditos normales/día y 60.000 totales/mes**: USD 0,12/día y USD 0,60/mes a esa tarifa. La carga inicial manual dispone de hasta 6.000 créditos/día separados, también dentro del mismo techo mensual. Si se alcanza cualquier tope, se detienen nuevas solicitudes. Cambiar precios del proveedor puede cambiar la equivalencia real; este control no sustituye un límite de gasto de su cuenta.

Se consulta el saldo al menos cada 24 h cuando corresponde un sondeo, contabilizando esa operación. Con saldo observado bajo se detiene la búsqueda. No hay recargas, suscripciones ni aumentos automáticos. Los créditos gratuitos del proveedor caducan a los 31 días según su tarifa: la automatización no hace que el saldo sea permanente.

`budget.daily_used` cuenta todas las operaciones. Puede superar el límite normal durante la carga inicial: comparar `normal_daily_used` con `daily_limit` y consultar `backfill_daily_used` aparte. El techo mensual cuenta todo. `twitterapi_budget` contiene los estimados, saldo observado y su fecha; `billing_reconciled=false` evita presentar la estimación como factura.

## Credencial y operación

Archivo privado modo 600: `/etc/cryptoreport-social/twitterapi-io.json`, dentro de directorio 700. Fuera de repo, Drive y frontend. Se rechazan enlaces simbólicos y archivos legibles por otros usuarios. La credencial solo viaja al host fijo `api.twitterapi.io`, mediante cabecera, sin redirecciones. Solo se permiten endpoints de lectura.

Desde `services/social`:

```bash
python3 -m crsocial configure-twitterapi  # prompt oculto; para rotarla
python3 -m crsocial balance              # consulta de saldo, consume una operación
python3 -m crsocial run                  # respeta horarios, cursores y presupuestos
python3 -m crsocial backfill             # carga manual acotada; no usar en cron
python3 -m crsocial status               # sin consulta al proveedor
python3 -m crsocial health
```

Instalación reproducible, desde la raíz del repo:

```bash
install -m 644 services/social/ops/cryptoreport-social.service /etc/systemd/system/
install -m 644 services/social/ops/cryptoreport-social.cron /etc/cron.d/cryptoreport-social
systemctl disable --now cryptoreport-social.timer
systemctl daemon-reload
systemctl restart cron
```

Comprobar con `systemctl is-active cron`, el contenido del archivo cron y `journalctl -u cryptoreport-social.service`. `inactive/dead` con `Result=success` es normal en el servicio oneshot entre ejecuciones. Suspender la extracción requiere retirar el archivo cron de `/etc/cron.d/`; parar el timer viejo no la detiene.

El monitor muestra cron, último despacho y sus solicitudes, frescura por cuenta, pendientes, fallos, pausas, eventos, operaciones y créditos. Exportar JSON o recuperar una página antigua no convierte esa acción en una nueva consulta de cabecera. Se guarda un máximo de 200 eventos sin textos de posts ni credenciales.

## Verificación real

Ver [evidencia y snapshot](../../docs/validaciones/twitterapi-feed-integracion-2026-10-15/README.md). La consulta terminó sin páginas pendientes para las cuatro cuentas. Eso acredita este ciclo; la estabilidad durante siete días sigue en observación.


## Administración de cuentas (16 de octubre)

En **Admin → Creadores → Cuentas de X**: pegar URL/@handle, comprobar perfil, elegir ventana de 1 a 30 días y categoría y añadir. La comprobación consulta el perfil con twitterapi.io y conserva el ID devuelto en una autorización local de quince minutos; el navegador no puede fijar un ID arbitrario. Las cuatro cuentas nuevas se añadieron mediante esta misma interfaz autenticada y se recuperaron sus ventanas de tres días.

Se puede modificar nombre, categoría, retención y estado. No se permite reasignar la identidad fijada desde el navegador. Desactivar purga sus posts privados/públicos y cruces locales, conservando la configuración para reactivarla. Aumentar retención o reactivar marca una recuperación completa de la ventana; la siguiente ejecución del cron atiende esas cuentas sin esperar tres horas.

El catálogo `accounts.json` se escribe atómicamente bajo el mismo cerrojo de ingesta. Las revisiones impiden sobrescribir una lista editada desde otra pestaña. Si hay extracción en curso, el panel responde 409 sin modificar datos y permite reintentar. El worker vuelve a leer el catálogo después de tomar el cerrojo, evitando usar una lista que cambió durante su arranque. Las altas y cambios quedan en la auditoría del panel. No hay API keys en el navegador.

Se corrigió una caducidad durante la recuperación: una publicación válida de una ventana antigua puede haber vencido al retomar su cursor. Ahora se cuenta como `expired_during_recovery`, se descarta y continúa la paginación. No se relajan los controles de identidad, texto o esquema. La prueba de regresión reprodujo el fallo antes de corregirlo. Un perfil inexistente devuelve 422 sin pausar la ingesta de todas las cuentas.

El presupuesto mensual es un techo de consumo, no una garantía de cubrir cualquier cantidad de cuentas o publicaciones. Si aumenta el volumen y se alcanza el límite, se publican el bloqueo y los pendientes; no se compra saldo ni se cambia a modelos de pago. La configuración anterior de doce horas fue demasiado lenta y se sustituyó por tres horas, con el cron cada quince minutos.

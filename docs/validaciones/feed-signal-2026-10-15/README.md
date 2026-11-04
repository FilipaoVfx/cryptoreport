# Feed autónomo, retención y Signal mode

Fecha: 15 de octubre de 2026, America/Bogota. Cambios integrados en el repo principal y su túnel público.

## Diagnóstico y corrección del Feed

1. El último intento del colector devolvió **HTTP 402**. El temporizador sí estaba activo; las publicaciones nuevas estaban bloqueadas por el proveedor. Se conservó el error por cuenta, pero el ciclo lo borraba del estado global al finalizar. Ahora se conserva y se muestra fuera de los filtros de la app. No se puede atribuir este rechazo a un saldo exacto sin consultar al proveedor.
2. Las ventanas eran 4/15 días. Ahora son **3 días** para `beincrypto_es`, `mattunchi` y `granmag0`, y **15 días** para `vitalikbuterin`.
3. El bridge llamaba a `Feed.publish()` sin `save()`: el JSON público descartaba vencidos, pero el almacenamiento privado mantenía copias. La publicación ahora persiste la purga, incluido el límite exacto de vencimiento.
4. La limpieza dependía del colector o del bridge. Un servicio independiente y sin red purga cada **15 minutos** y publica el corpus vigente. La extracción mantiene dos ejecuciones diarias, máximo 6 solicitudes por ciclo, 12 diarias y 400 mensuales.
5. La pestaña del Feed solo filtraba vencimientos en memoria. Ahora también descarga cambios cada **5 minutos** y al volver a la pestaña, conservando filtros y posición. El lector de un post se cierra si ese post vence; los fallos iniciales de carga se reintentan.

La primera ejecución independiente eliminó **48 posts** y dejó **116** tanto en `state.json` como en `social-feed.json`: BeInCrypto 13, Mattunchi 14, Vitalik 9 y GranMag0 80. Los conteos cambian por vencimiento o futuras extracciones. No se guardó una copia adicional de los textos purgados. Los contadores permanecieron en 12 solicitudes de extracción en octubre, incluida una del 16 de octubre UTC; **cero llamadas nuevas al proveedor y cero llamadas a modelos** durante esta corrección.

Se retiraron los trabajos semánticos locales que dependían de textos vencidos o de la política anterior, sus resultados y conexiones públicas obsoletas. El bridge reconstruye los trabajos con las fuentes vigentes. Los archivos históricos de Drive quedan fuera de esta purga local.

El módulo guarda el corpus en `/var/lib/cryptoreport-transcripts/social/state.json`, un JSON persistente con exclusión mutua; no se añadió una base de datos SQL. Conserva presupuesto y checkpoints sin conservar el cuerpo de los posts vencidos.

**Límite externo pendiente:** HTTP 402 del proveedor. El sistema está programado para volver a intentar la extracción, pero recibir posts nuevos requiere resolver la cuota o acceso de Scraper.tech. No se compraron cuotas ni se elevaron límites.

## Signal mode

- El botón **Signal** sustituye a Compartir en la cabecera del video.
- Se activa voluntariamente y abre el video con el pulso debajo, sin iniciar reproducción por abrir el modo.
- Verde y rojo conservan las señales léxicas del texto; el tono de la ventana actual se identifica con «Ahora». No se presenta como una posición financiera.
- Tocar un punto de la onda salta al minuto proporcional. El deslizador sincronizado permite precisión y uso con teclado; el cursor avanza con la reproducción.
- Al desactivarlo se pausa y vuelve la lectura completa. Cerrar el video también desactiva el modo.
- El panel aparece con una transición de 260 ms y un brillo suave. No se añadió parpadeo continuo; se respeta `prefers-reduced-motion`. Las ondas del Diario y el timeline se conservan.

## Verificación

Las pruebas nuevas reprodujeron inicialmente seis fallos y un error: retención privada, límite exacto, cambio de ventana, referencias obsoletas, catálogo y error global oculto. Tras corregirlos, **41 pruebas Python del servicio social pasan**. También pasan **32 pruebas JavaScript** de las funciones existentes.

Chromium: Signal mode PASS a 390×844 y 360×800, con salto al 60 % de la onda, navegación por teclado, activación, cierre, vuelta a lectura, color y modo de movimiento reducido. Sin excepciones JavaScript ni desbordamiento horizontal. Los controles se verifican con el simulador existente para no depender de YouTube.

El Feed se verificó con respuestas sintéticas y reloj controlado: vencimiento de un post abierto, eliminación de su tarjeta, actualización automática sin recargar la página, conservación del filtro y consulta al recuperar visibilidad. No se realizaron extracciones de X en esas pruebas.

El mantenimiento instalado terminó con `Result=success` y `ExecMainStatus=0`; volvió a ejecutarse por temporizador a las 22:15 de Bogotá. Se verificó igualdad de corpus privado y público y ausencia de vencidos.

Código de regresión: `services/social/tests/test_retention.py` y `prototypes/movil/b4-urania/signal-feed.browser.cjs`.

[Signal 390 px](signal-390.png) · [Signal 360 px](signal-360.png).

Reproducir desde la raíz:

```bash
(cd services/social && /usr/bin/python3 -m unittest discover -s tests)
node --test prototypes/movil/b4-urania/*.test.cjs
# Playwright disponible vía node_modules o NODE_PATH; servidor activo.
node prototypes/movil/b4-urania/signal-feed.browser.cjs
```


## Ajuste posterior por creador

Por indicación del usuario, BeInCrypto Español pasa de 3 a **10 días**. Vitalik conserva **15 días**, Mattunchi y GranMag0 **3 días**. La ampliación no recupera los posts ya purgados; para completar los diez días será necesaria una extracción correcta del proveedor. No se aumentan cuotas ni se activa inferencia.

El cambio a diez días quedó publicado. Se retiró únicamente el checkpoint incremental de BeInCrypto para que la siguiente extracción permitida consulte la ventana ampliada, sin modificar contadores ni adelantar llamadas. Comprobación del 15 de octubre en Bogotá: 16 posts de hoy recibidos de GranMag0, de los cuales 3 clasificados como relevantes; ninguna publicación de hoy recibida de las otras cuentas. Esto describe el corpus recibido, no certifica que las cuentas no hayan publicado. Último éxito: 07:13; intento de 19:15 detenido por HTTP 402.

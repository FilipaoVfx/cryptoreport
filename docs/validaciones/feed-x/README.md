# Entrega: Feed de X e integración por etapas

Verificación del 14 de octubre de 2026, hora de Bogotá.

[Abrir el Feed público de Urania](https://imports-toolkit-vital-alt.trycloudflare.com/b4-urania/#/feed).

## Implementado

- Guardados fue sustituido por Feed en la navegación de Urania. Se retiraron sus botones de guardar de rankings, fichas, notas y videos. Enlaces antiguos a Guardados redirigen al Feed; no se borró el almacenamiento previo del dispositivo.
- Feed cronológico con autor, fecha, texto, enlaces a X, lectura de publicaciones largas, búsqueda, cuenta, últimas 48 h y paginación local.
- Servicio `services/social`, independiente de las colas de videos, adaptado del laboratorio. Estado en JSON, deduplicación, hashes, vigencia por cuenta y recuperación de cursores pendientes.
- `cryptoreport-social.timer` instalado, habilitado y activo. Dos horarios diarios; máximo de 6 solicitudes/ciclo, 12/día UTC y 400/mes UTC. El enfriamiento evita ejecuciones consecutivas y los contadores se guardan antes de cada solicitud.
- Correcciones de reauditoría trasladadas a la biblioteca semántica, con regresiones para fuentes cambiadas y publicación del objeto revisado.

## Datos y consumo observados

Se importaron **184 posts aún vigentes** del corpus existente, sin red. El primer ciclo propio terminó con **185 posts disponibles de cuatro cuentas** y **cinco solicitudes a Scraper.tech**. Las cifras cambian con la caducidad y las próximas consultas.

No hubo llamadas a modelos. El cliente semántico está bloqueado por defecto y el servicio de Feed no lo importa ni lo ejecuta. Las conexiones entre posts y afirmaciones continúan desactivadas: falta validación editorial y el adaptador de ejecución sin API. No se modificaron el Schedule, los análisis originales ni la cola de videos.

Los límites de extracción cuentan solicitudes del nuevo servicio, no dólares ni todo el uso de la clave. No se verificó el importe facturado por Scraper.tech. Su cuota es distinta de los créditos de modelos.

El snapshot inspeccionado pesa aproximadamente **34,5 KB comprimido**. El estado privado ocupa unos **156 KB**. Abrir Feed no requiere descargar el índice de videos.

## Validación

**54 pruebas automatizadas aprobadas**:

- 16 del servicio social, ejecutadas también con conexiones de red bloqueadas.
- 19 del constructor/servidor móvil existente.
- 19 de JavaScript: Radar y Feed.

Comprobaciones de sintaxis y diferencias sin errores de formato. Las suites sociales y del Feed se añadieron al workflow local; no se ha hecho push ni se afirma una ejecución remota de CI.

**15 comprobaciones funcionales en navegador sobre la URL pública**, incluyendo retirada de Guardados, entrada sin índice de videos, filtro por autor/período, lectura larga, estado vacío, paginación, enlaces canónicos, cero fetch al buscar/filtrar/paginar, actualización únicamente del JSON publicado, redirección antigua, Radar y orden de citas conservados.

Comprobación visual en **320, 375, 390 y 430 px**, sin desbordamiento horizontal. Los campos del Feed usan 16 px para evitar el zoom por texto pequeño al enfocarlos en móvil. La consola de Urania no mostró errores.

Peticiones HTTP nuevas, sin cookies, obtuvieron 200 para HTML, script de Feed y JSON público. El servicio terminó con `Result=success` y `ExecMainStatus=0`; el timer quedó `enabled` y `active`.

## Capturas y operación

- [Feed móvil](feed.png).
- [Filtro de Vitalik](vitalik.png).
- [Configuración, datos, límites y comandos](../../../services/social/README.md).

Cambios guardados en el repositorio local y publicados mediante el túnel existente. La ingesta y publicación son automáticas; la pantalla carga el último recurso al entrar o pulsar Actualizar, y descarta vencimientos localmente. No se promete cobertura completa de X ni tiempo real.

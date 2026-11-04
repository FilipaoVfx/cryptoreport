# Feed integrado: twitterapi.io + cron

Verificación del 15 de octubre de 2026, aproximadamente 23:45 Bogotá / 16 de octubre 04:45 UTC. Snapshot, no un contador permanente.

## Resultado real

Se incorporaron **73 posts nuevos**: de 116 a **189 vigentes**. Una publicación cambió de texto y su hash se actualizó. No quedaron cursores pendientes en las cuatro cuentas. El JSON descargado por la URL pública coincidió byte por byte con el del repo principal; HTTP 200. No se usaron APIs de modelos.

| Cuenta | Retención | Posts vigentes | Resultado de consulta |
| --- | ---: | ---: | --- |
| BeInCrypto Español | 10 días | 58 | Cursor agotado |
| Mattunchi | 3 días | 17 | Cursor agotado |
| Vitalik Buterin | 15 días | 9 | Cursor agotado |
| GranMag0 | 3 días | 105 | Cursor agotado |

Clasificación local: **59 relevantes**, 130 secundarios, 57 elegibles para cruces. Los secundarios siguen accesibles con el filtro Todos; no se aumentó artificialmente la relevancia para hacer crecer la vista principal. Se preparó la cola semántica local: 32 trabajos disponibles, cero revisados, pendiente de Schedule. Preparar la cola no equivale a ejecutar sus análisis ni a confirmar nuevas subidas a Drive.

## Recuperación y cron observados

- La carga inicial se detuvo tras un HTTP 429 sin `Retry-After`. Conservó los posts ya aceptados y cada cursor pendiente.
- Se aplicó una política específica para el límite por segundo de twitterapi.io: espera exponencial desde 120 s y diez segundos desde el final de una solicitud hasta iniciar la siguiente. No se cambiaron cuentas ni direcciones para sortear el límite.
- Una segunda ejecución reanudó las ventanas desde sus cursores; terminó sin errores ni pendientes. En total, la carga inicial reservó 16 operaciones, incluido el 429. El cupo manual no queda habilitado para cron.
- Un segundo comando durante la carga devolvió `busy` sin hacer solicitudes: el cerrojo funcionó.
- Cron ejecutó el comando instalado a las **23:45:01 Bogotá**. `cryptoreport-social.service` terminó correctamente a las 23:45:02. No tocaba sondeo y no quedaban páginas: **cero solicitudes adicionales**, contador mensual conservado en 37.
- Timer de ingesta antiguo deshabilitado; cron activo. Timer de retención activo y separado, cada quince minutos sin red.

El sondeo normal es cada doce horas; el despacho cron, cada quince minutos. La recuperación pendiente puede continuar entre sondeos. La app abierta comprueba nuevas publicaciones cada cinco minutos. Esto es actualización periódica, no streaming en tiempo real.

## Consumo observado

Saldo antes de integrar: **99.505 créditos**. Saldo al comprobar el cierre: **96.610**. Diferencia observada: **2.895 créditos**, equivalente a **USD 0,02895** a la tarifa de 100.000 créditos/USD. La prueba anterior había consumido 495 créditos adicionales. El saldo puede reflejar cargos con retraso: esta observación no es una factura definitiva.

El registro local conserva **3.225 créditos estimados** desde la activación: es más conservador porque incluye la reserva incierta del 429 y dos lecturas de saldo a 15 créditos de referencia. La prueba anterior es anterior a este registro monetario; sus seis operaciones sí estaban incluidas en el contador general y no se borraron.

Límites recurrentes: 6 solicitudes/ciclo, 24 normales/día y 600 totales/mes. Límite monetario estimado: 6.000 créditos/día y **60.000/mes**, USD 0,60 mensuales de referencia. No hubo recargas ni suscripciones. Los créditos gratis caducan a los 31 días según la [tarifa del proveedor](https://twitterapi.io/pricing/details).

## Comprobaciones

- 64 pruebas Python de Social: contrato de respuesta, autor fijado, cursores, recuperación después de reiniciar, ventanas nuevas sobre pendientes antiguas, presupuestos, reserva en errores, 429/Retry-After y cambio de tamaño de página.
- 45 pruebas de Bridge, 7 de Panel y 32 de frontend aprobadas.
- Navegador: lectura, rankings y Feed a 360/390/1280 px; Signal Mode y pulsos, expiración, modal abierto, refresco automático y conservación de filtros.
- Feed público real a 390 y 1280 px, sin excepciones JavaScript ni desbordamiento horizontal.
- Monitor renderizado con datos operativos reales en una ruta aislada del navegador; no se omitió ni modificó la autenticación del servidor.
- Sin posts vencidos, identidades incompatibles ni divergencias entre los IDs privados y públicos al validar. Archivo de clave 600, directorio 700; clave ausente de código y JSON público.

Evidencia: [report.json](report.json), [browser-report.json](browser-report.json), [Feed móvil](feed-publico-390.png), [monitor](monitor-twitterapi.png).

## Límites de esta verificación

La consulta agotó los resultados que entrega el proveedor; `coverage_complete=false` sigue impidiendo certificar una cobertura absoluta de X. La estabilidad durante siete días continúa en observación. El respaldo Scraper.tech tiene el plan vencido y Agent Reach no tiene sesión configurada; el proveedor operativo verificado es twitterapi.io. Los cruces semánticos siguen pendientes de Schedule y no se presentan como verificados.

Código y operación: [guía vigente](../../../services/social/OPERACION_TWITTERAPI.md).

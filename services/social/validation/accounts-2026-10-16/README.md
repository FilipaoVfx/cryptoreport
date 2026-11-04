# Cuentas de X, actualización y E2E — 16 de octubre de 2026

**Resultado en el alcance probado: PASS.** Las cuatro cuentas se añadieron mediante el panel autenticado, se comprobaron sus identidades con twitterapi.io y se recuperaron sus ventanas de tres días. No quedan páginas pendientes en ninguna de las ocho cuentas. El análisis de videos permanece **pausado por el usuario**, pendiente de un nuevo system prompt; no se instaló un cron para el ejecutor de análisis en preparación.

## Datos comprobados

Snapshot público a las **12:20:55 de Bogotá**:

| Cuenta añadida | Ventana | Posts vigentes | Estado |
| --- | ---: | ---: | --- |
| @BullTheoryio | 3 días | 62 | Consulta terminada |
| @BitcoinArchive | 3 días | 72 | Consulta terminada |
| @WatcherGuru | 3 días | 56 | Consulta terminada |
| @CredibleCrypto | 3 días | 55 | Consulta terminada |

Total: **245 vigentes de las nuevas cuentas, 442 en el Feed**; 212 clasificados como relevantes mediante reglas locales. Durante el E2E anterior había 443 y BitcoinArchive tenía 73: una publicación venció entre ambas verificaciones. Es la purga esperada, no una pérdida de ingesta. Las consultas de alta cubrieron la ventana hasta las 12:00 aproximadamente; la paginación terminó después. No se certifica cobertura absoluta de X.

El JSON público devolvió HTTP 200 y sus IDs coincidieron con la publicación local. Ver [deployment-report.json](deployment-report.json) y [verify-live.py](verify-live.py).

## Administración disponible

**Admin → Creadores → Cuentas de X** permite pegar URL/@handle, comprobar identidad y añadir, editar nombre/categoría/ventana o desactivar. Máximo 16 cuentas; ventanas de 1 a 30 días. El ID de autor se fija desde el perfil verificado en el servidor, nunca desde un ID enviado por el navegador. La autorización de alta vence a los quince minutos.

Desactivar purga sus posts y referencias locales. Reactivar o ampliar la ventana solicita recuperación completa. Los cambios usan escritura atómica, revisión del catálogo y el mismo cerrojo que la ingesta; una extracción concurrente responde 409 sin sobrescribir cambios. El worker vuelve a leer el catálogo después de tomar el cerrojo.

La configuración se guarda en `services/social/accounts.json`. Los secretos siguen fuera del repo, en archivos privados. No se enviaron cookies personales de X ni claves al navegador.

## Fallos encontrados y corregidos

1. **Cron frecuente con consulta demasiado lenta.** El cron funcionaba cada quince minutos, pero la API solo se consultaba cada doce horas. La mañana mostraba publicaciones viejas mientras solo se purgaban las vencidas. Se redujo el sondeo a **tres horas**; el cron sigue cada quince minutos. Las altas nuevas no esperan ese intervalo: se atienden en el siguiente despacho.
2. **Caducidad entre páginas.** Una página válida de BitcoinArchive incluía una publicación que había vencido desde que se inició la ventana del cursor. El merge la rechazaba como error de esquema y pausaba a todo el proveedor. Se reprodujo con el test de regresión antes de corregirlo y se inspeccionó la página real: identidad, texto y fechas eran válidos. Ahora se omite y contabiliza como `expired_during_recovery`, sin relajar identidad ni estructura. La recuperación real posterior terminó correctamente.
3. **Panel estrecho.** La tabla imponía 640 px de ancho a la columna de una pantalla de 390 px. Se corrigió el tamaño mínimo de la cuadrícula y se confinó el desplazamiento horizontal a las tablas. La página completa ya no desborda.
4. **Perfil inexistente.** Un 404 de comprobación de perfil se trata como entrada no encontrada, sin pausar la extracción de todas las cuentas.

## E2E real y pruebas de errores

Alta real desde interfaz: [ui-live-add.json](ui-live-add.json). Recorrido real posterior: [e2e-live.json](e2e-live.json).

- Login real; GET sin sesión rechazado con 401; POST sin la cabecera del panel rechazado con 403.
- Ventana inválida: 422 y catálogo sin modificación. La primera ejecución formal recibió el 409 previsto por concurrencia; el replay esperó la liberación del cerrojo y comprobó el 422. No se trató ese bloqueo como éxito ni se ignoró.
- Cambios de categoría guardados desde los controles de las cuatro cuentas y comprobados en la respuesta del servidor.
- Feed público real a **390 y 1280 px**, filtro de cada cuenta, IDs pertenecientes al autor correcto, texto completo idéntico al publicado y enlace canónico a X. Ocho combinaciones comprobadas, cero excepciones JavaScript.
- **159 tests aprobados:** 68 Social, 14 Panel, 45 Bridge y 32 frontend. Casos de errores/cuota/timeout/cursores y de desactivar/reactivar usan fixtures temporales y proveedor simulado. No se presenta esa simulación como disponibilidad real del proveedor.

Comando reproducible del E2E, deliberadamente habilitado para escrituras reales de categoría en las cuatro cuentas autorizadas:

```bash
CR_SOCIAL_LIVE_E2E=1 NODE_PATH=/root/gstack/node_modules node services/panel/tests/social-live.browser.cjs
```

Evidencia de QA, con órdenes, salidas y hashes conservados:

- [Checkpoint 002: navegador real](qa/exploration-002.json).
- [Checkpoint 003: Panel](qa/exploration-003.json).
- [Checkpoint 004: Social](qa/exploration-004.json).
- [Checkpoint 005: Bridge](qa/exploration-005.json).
- [Checkpoint 006: frontend](qa/exploration-006.json).
- [Checkpoint 007: publicación y pausa vigentes](qa/exploration-007.json).

## Límites operativos

El techo mensual estimado se conserva en **60.000 créditos — USD 0,60 de referencia**. Para no excluir cuentas por el antiguo cupo de seis solicitudes, el servicio admite 24 operaciones por ejecución, 320 normales/día y 10.000/mes. Estos límites de operaciones no sustituyen el control de créditos. El límite diario de referencia normal es 12.000 créditos; las cargas manuales tienen un cupo separado de 6.000 y siguen dentro del mismo techo mensual. No se compró saldo ni se activaron recargas. Si el volumen agota el presupuesto mensual, la ingesta se pausa y lo registra; no se garantiza una cantidad ilimitada de fuentes o publicaciones.

Los tests anteriores del monitor emiten `ResourceWarning` por conexiones SQLite de lectura; no fallaron ni bloquearon este recorrido. No se hizo una auditoría general de recursos del panel. La prueba de disponibilidad de siete días sigue pendiente. Scraper.tech permanece con plan vencido y Agent Reach sin sesión; twitterapi.io es la fuente operativa comprobada.

El análisis no se reanudó. El intento local en curso fue cancelado, quedó `paused_by_user` y no publicó resultados. El runner nuevo permanece en preparación, sin servicio programado; se revisará al recibir el nuevo prompt.

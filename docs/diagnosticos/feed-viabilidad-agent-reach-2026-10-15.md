# Viabilidad del Feed y Agent Reach

Evaluación de lectura, 15 de octubre de 2026, Bogotá, alrededor de las 22:52. No modifica colectores, cuotas ni credenciales.

## Dictamen

Viable para cuatro cuentas con consulta periódica cada 6–12 horas y supervisión por excepción. No puede prometerse captura completa, tiempo real o mantenimiento humano cero. El estado actual está degradado: la automatización de los temporizadores funciona; la entrada de posts y los cruces semánticos tienen bloqueos diferentes.

## Estado observado

- `cryptoreport-social.timer` y `cryptoreport-social-maintenance.timer`: activos.
- Último éxito de extracción: 15 oct 07:13 Bogotá. Último intento: 19:15, HTTP 402. La primera cuenta falla por cuota/acceso y detiene el ciclo; no se interpreta como cuatro cuentas consultadas correctamente.
- Corpus: 116 posts, 34 relevantes por reglas locales y 82 secundarios. Que el JSON se vuelva a publicar no indica extracción nueva.
- Límites locales: 6 solicitudes/ciclo, 12/día UTC, 400/mes. Registro mensual del servicio: 12. No representa saldo del proveedor ni uso de otras aplicaciones/endpoints.
- Cruce semántico: 34 trabajos disponibles, 0 revisados en el último ciclo, error `drive_sync:drive_conflict`; recurso público sin conexiones aceptadas. No se investigó ni corrigió ese conflicto en esta evaluación.
- Purga independiente cada 15 min; frontend busca cambios cada 5 min. Ventanas BeInCrypto 10 d, Mattunchi y GranMag0 3 d, Vitalik 15 d.

## Agent Reach

Copia de referencia encontrada: `/root/audits/cryptoreport-transcription-20261008/references/Agent-Reach`, versión declarada 1.5.0. No se encontró ejecutable agent-reach, twitter, bird o xreach en los lugares inspeccionados ni integración en el colector. No se verificó una sesión válida de X. Leer una copia del repositorio no prueba disponibilidad operacional.

La documentación actual enruta X a twitter-cli y alternativas. Requiere credenciales de sesión. Puede proporcionar salida estructurada, búsqueda y posts de usuario, pero nuestro servicio seguiría gestionando horarios, normalización, hashes, cursores, publicación y retención. Cookies vencidas, cambios de X y bloqueos pueden requerir intervención. El diagnóstico doctor no demuestra por sí solo lectura autenticada real.

Recomendación: prueba aislada de siete días con las cuatro cuentas, lectura solamente, antes de promoverlo a proveedor primario o de respaldo. Medir éxito, edad de la última consulta confirmada por cuenta, posts recuperados y pendientes. No importar cookies automáticamente de otros perfiles ni poner credenciales en logs.

## Costos y cadencia

[Scraper.tech publica](https://scraper.tech/panel/pricing/twitter/) Free 1.000 solicitudes/mes y Basic USD 12/mes por 100.000, sujetos al plan y forma de pago elegidos. No se comprobó la modalidad de la cuenta del usuario. Su FAQ indica que hace falta un plan activo aun si quedan créditos. HTTP 402 no demuestra cuál de esos supuestos aplica.

Estimaciones para 30 días, cuatro cuentas, una página por cuenta/ciclo; faltan paginación, reintentos y otras aplicaciones:

| Cadencia | Solicitudes base/mes |
| --- | ---: |
| Cada 12 h | 240 |
| Cada 8 h | 360 |
| Cada 6 h | 480 |
| Cada hora | 2.880 |

El presupuesto local actual de 400 no permite sostener cuatro cuentas cada seis horas aun sin paginación. Cambiar solo el timer sería incorrecto. Las 1.000 solicitudes gratuitas publicadas podrían cubrir seis horas con margen, si la cuenta y endpoints realmente disponen de ellas. No se elevó ningún límite.

[X oficial publica](https://docs.x.com/x-api/getting-started/pricing) USD 0,005 por post leído. Escenarios ilustrativos, solo lecturas de posts nuevos: 1.000/mes USD 5; 3.000 USD 15; 10.000 USD 50. No son estimaciones del volumen observado. Perfiles, otras lecturas, solapes entre días y recursos adicionales pueden aumentar el total. No se contrató ningún acceso.

La ingesta, deduplicación, purga y preclasificación local no necesitan modelos. Los cruces profundos video/post dependen de trabajos semánticos y de que su ejecutor entregue resultados válidos a tiempo; aumentar la ingesta aumenta esa cola. No presentar el Feed operativo como prueba de que todos los cruces están completos.

## Refuerzo propuesto, sin implementar aquí

1. Resolver y comprobar una consulta real de la credencial actual; registrar consumo del proveedor separado del contador local.
2. Adaptador de proveedores con contrato único, cursores por proveedor y ventanas por cuenta. No reutilizar un cursor entre Scraper.tech y twitter-cli.
3. Distinguir 402/401 (detener proveedor, intervención), 429 (esperar Retry-After) y red/5xx (reintento acotado con espera creciente). El respaldo no crea bucles de consultas ni duplica gasto.
4. Validar ID/autor/fecha/texto íntegro, deduplicar, recuperar huecos con solape temporal y no adelantar checkpoints con páginas incompletas. Una respuesta vacía solo confirma consulta correcta si el proveedor la valida; no certifica cobertura total.
5. Mostrar y registrar última consulta correcta por cuenta, retraso, huecos y estado de proveedor. Alertar por excepción en el panel; no enviar mensajes externos sin autorización.
6. Aislar publicación y retención de los cruces semánticos. Resolver el conflicto Drive y medir la cola para que el apoyo narrativo no se anuncie actualizado sin resultados.

Objetivo propuesto: mayoría de ciclos correctos sin intervención y recuperación automática tras fallos transitorios; demostrarlo con una prueba sostenida antes de anunciar un nivel de servicio. Una caída de cuota o una sesión expirada no se corrige solo con más código.

Fuentes primarias: [Agent Reach](https://github.com/Panniantong/Agent-Reach/blob/main/docs/README_en.md), [twitter-cli](https://github.com/public-clis/twitter-cli), precios enlazados arriba. No se ejecutó extracción de X ni inferencia de pago durante esta revisión.

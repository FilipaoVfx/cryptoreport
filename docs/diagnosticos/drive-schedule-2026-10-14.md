# Diagnóstico de Drive, rclone y Schedule

Fecha de comprobación: 14 de octubre de 2026, aproximadamente 21:10 America/Bogota.
Estado: **DONE_WITH_CONCERNS**. Cuota de rclone reproducida; programación efectiva
de la tarea de ChatGPT pendiente de confirmar desde su configuración.

## Resultado

Hay dos asuntos independientes: el acceso del VPS a Drive sufre límites del cliente
OAuth compartido de rclone; la continuidad de Schedule no queda acreditada por los
últimos archivos disponibles. El último comprobante combina dos resultados subidos
con una incidencia de un tercer video previamente bloqueado.

| Componente | Evidencia observada | Conclusión |
| --- | --- | --- |
| Drive por el conector de ChatGPT | Lectura de Ejecuciones, Resultados y Pendientes; los siete trabajos locales en estado uploaded están presentes en Pendientes | Las carpetas y estos archivos son accesibles por esa conexión |
| rclone | Una lista de Control devuelve 26 archivos; otra llamada con igual configuración devuelve HTTP 403, RATE_LIMIT_EXCEEDED | Fallo intermitente reproducido, originado en la respuesta de Google |
| Cuota | Métrica Queries; límite Previous quota: Requests per minute; servicio drive.googleapis.com | Límite de solicitudes, distinto de una falta de créditos de inferencia |
| OAuth del VPS | gdrive usa type=drive, client_id/client_secret propios ausentes; no hay sobrescrituras OAuth en las variables comprobadas | Está usando el cliente compartido de rclone |
| Binario | rclone v1.75.1, consigue listar con las credenciales existentes | No se encontró evidencia de binario averiado o fallo permanente de autenticación; la causa reproducida es cuota |
| Último comprobante | Inicio 14 oct 10:24:24 y cierre 11:11:33 Bogotá; dos intentos, dos subidas, status=error | Hubo trabajo entregado aunque el estado global muestra una incidencia |
| Importación | OjVdVFOVx0A importado a las 10:30:38; NVleCstDNZE a las 11:30:37 Bogotá | Ambos resultados llegaron al servidor |
| Pendientes de videos | Siete uploaded y uno blocked en SQLite; los siete uploaded se contrastaron con Drive | Existe trabajo disponible para el ejecutor |
| Schedule periódico | No hay comprobante ni salida posterior al cierre de las 11:11 en las carpetas consultadas | No permite afirmar que la tarea sigue activada o que está ejecutándose cada seis horas |

## Hipótesis y contraste

**Hipótesis confirmada para el acceso VPS:** Google está rechazando solicitudes por
la cuota del proyecto OAuth usado por rclone. Se reproduce con una operación de
solo lectura; no requiere subir archivos ni ejecutar análisis. La configuración
sin cliente propio coincide con el patrón previo documentado en el proyecto.
No se accedió a métricas de Google Cloud que permitan atribuir qué usuarios o
procesos consumieron esa cuota compartida.

Los registros del bridge desde medianoche local contienen 84 eventos con la
categoría drive_quota y 21 eventos busy. Estos son registros, no un conteo de
solicitudes facturadas ni una prueba de que todos sean ciclos distintos.

**Schedule:** el último error se refiere a i2LUeRtROdg, bloqueado previamente por
cifras de posiciones, pérdidas y tenencias poco fiables en segmentos 88, 92, 93 y
114 de la transcripción. El comprobante antiguo solicitó revision_material y no
emitió análisis. El último comprobante solo conserva ese bloqueo: sus otros dos
trabajos sí se subieron y se importaron. No contiene un fallo de acceso a Drive.

El prompt vigente exige status=error ante bloqueos, incluso si hubo subidas
verificadas. Por eso el aviso global del panel no distingue una entrega parcial
de un fallo total. No debe interpretarse como pérdida de los dos resultados.

## Otros factores comprobados

- El bridge tiene un timer habilitado cada quince minutos. Cuando la extracción
  mantiene el cerrojo común, sale como busy. Hay un ExecStartPost que inicia el
  bridge al terminar la extracción. Se comprobó un ciclo correcto a las 20:52 y
  un salto busy a las 21:03. Un exit code 0 de ese salto no acredita sincronización.
- El bridge ya usa caché por ID/ModTime/Size en core.py, método read. No es correcto
  atribuir los fallos a que descargue todos los resultados históricos en cada ciclo.
- El módulo semántico comparte el transporte rclone del bridge. Puede preparar
  trabajos localmente aunque la sincronización remota falle. Las cargas puntuales
  por el conector no eliminan el problema del transporte desatendido del VPS.
- Las credenciales del conector y las del VPS son conexiones distintas. Que una
  funcione no acredita la cuota ni la continuidad de la otra.
- Los comprobantes no incluyen task_id, trigger ni scheduled_for; no permiten
  diferenciar por sí solos una ejecución manual de una ejecución del programador.

## Recomendación, sin modificar la configuración durante este diagnóstico

1. Configurar un cliente OAuth propio para rclone en un proyecto de Google Cloud
   del usuario y autorizar de nuevo ese cliente. Conservar el remoto actual hasta
   comprobar lectura, una escritura controlada y lectura posterior con el nuevo.
   Reiniciar el VPS o reautorizar el mismo cliente compartido no elimina la cuota
   compartida. No se requieren APIs de inferencia para esta migración.
2. Confirmar en la tarea de ChatGPT si está activada, su próxima ejecución, zona
   horaria, último estado y lectura de las instrucciones vigentes. Se pidió ese
   texto al usuario: estas herramientas no exponen el control de su tarea.
3. Separar en observabilidad entregas válidas, avisos de trabajos bloqueados y
   errores de transporte; conservar el bloqueo de material hasta resolverlo.
4. Después de resolver ambos accesos, comprobar una ejecución programada completa:
   trabajo elegido, resultado y comprobante en Drive, importación y publicación.
   Una ejecución manual correcta no certifica periodicidad sostenida.

No se ejecutaron modelos ni nuevas extracciones para este diagnóstico. Se realizaron
lecturas de metadatos, del comprobante y de estado local; no se alteró OAuth ni la tarea.

## Fuentes

- [rclone: cliente propio de Google Drive](https://rclone.org/drive/#making-your-own-client-id).
  Documenta el cliente compartido, sus límites globales y su retirada durante 2026.
- [Google: límites de Drive y errores por cuota](https://developers.google.com/workspace/drive/api/guides/limits).
  Documenta respuestas 403/429 y espera exponencial para límites temporales.
- [Comprobante examinado](https://drive.google.com/file/d/10D18H8JnyHEP0BhijPoIMmGagMX1eAuH/view).
- Código: services/bridge/crbridge/drive.py; core.py (read, receipts, health);
  ops/cryptoreport-bridge.timer; drop-in no-paid de transcripciones.

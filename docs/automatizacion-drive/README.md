# Piloto de análisis con ChatGPT Scheduled y Google Drive

Estado: instrucciones operativas revisadas después de dos pruebas manuales y una comparativa asistida. La tarea no se administra desde este entorno. El puente del servidor está implementado en services/bridge; consultar su estado real con crbridge status y systemd, sin inferir activación de esta documentación. La última salida pasa la validación del repo, pero no certifica ejecución desatendida o capacidad de Plus.

Carpeta raíz: https://drive.google.com/drive/folders/1pglUIayp0Km1bmzUP98oKSdAMbKVou8m

Archivos principales: [instrucción completa](scheduled-instructions.md), [texto para crear la tarea](crear-tarea.md), [configuración](manifest.json) e [índice ligero](queue-index.json).

## Activación por el usuario

1. Abre ChatGPT en la web con tu cuenta Plus. Usa ChatGPT Work y habilita el plugin Google Drive en ese chat. Comprueba que la conexión corresponde a la cuenta que puede acceder a la carpeta. Autoriza las operaciones de lectura y subida necesarias desde los controles de la conexión, si aparecen.
2. Selecciona GPT-6.1 Sol, razonamiento Medium y velocidad Standard, si están disponibles. Usa la revisión 1.3 de `control/scheduled-instructions.md`; requiere leer el prompt/esquema íntegros y comprobar citas, tiempos, referencias y cobertura antes de subir.
3. Las pruebas manuales y su verificación están documentadas en `piloto-largo-modelo-2026-10-13.md` y `sol-verificado-2026-10-13.md`. No equivalen a una ejecución automática. El modelo identificado por el usuario como Sol conserva `model: null` en el archivo; no inventar metadatos técnicos.
4. Crea una tarea independiente llamada `CryptoReport — análisis de narrativas`, cada seis horas en `America/Bogota` (00:00, 06:00, 12:00, 18:00). Su prompt debe ordenar leer y aplicar en cada ejecución [scheduled-instructions.md](https://drive.google.com/file/d/1XsXFvrKazWDFSjHs5BMTLQn1s3h_ys6f/view), usando Google Drive y conservando sus límites. No dependas de archivos locales del servidor ni de recordar la conversación anterior.
5. Abre Scheduled y confirma nombre, prompt, conexión, horario, zona y estado activo. Revisa la primera ejecución automática: debe dejar un comprobante incluso si la prueba manual ya consumió el único pendiente.

Configuración balanceada: cuatro ejecuciones diarias y máximo dos intentos por ejecución, capacidad teórica de ocho videos/día antes de fallos o límites. La muestra de 48 horas tuvo diez publicaciones (cinco/día); no establece la tasa futura ni el consumo de Plus. Revisar cola, fallos y consumo real durante siete días; después decidir si se amplía el lote. La frecuencia reduce aperturas de cola y acepta hasta seis horas de espera para publicaciones nuevas antes de considerar atrasos. La tarea no aumenta automáticamente su consumo ni cambia a APIs. Usa cuota de ChatGPT; no es ilimitada.

Configuración recomendada para el piloto narrativo: GPT-6.1 Sol / Medium / Standard. La salida comparativa asistida corrige los problemas previos; se construyeron citas con código y revisión informada, por lo que no demuestra superioridad causal del modelo o calidad autónoma general. Luna queda como candidato para extracción/clasificación por separado; no habilitar cambio automático entre modelos. Seleccionar modelo/razonamiento/velocidad en los controles de la tarea: escribirlos en su prompt no cambia esos controles.

`queue-index.json` contiene un índice ligero de los nueve trabajos originales para reducir lecturas. Se contrasta con Pendientes y Resultados en cada ejecución. Es una instantánea, no un registro de aceptación o publicación; los trabajos nuevos ausentes del índice se inspeccionan para obtener su fecha, sin perder novedades.

## Contrato del trabajo piloto

`job_id` deriva del ID del video, hash de los bytes de la transcripción y versiones del prompt/esquema. `payload` es la entrada existente de `cranalysis.request.build_payload`; `analizado_en` se fija al momento real de la ejecución. La transcripción original se conserva completa dentro de `payload.documento`.

El hash del esquema usa el mismo método que el analizador actual: SHA-256 de `json.dumps(schema, sort_keys=True)`. El hash del prompt corresponde a su texto UTF-8. El hash de la transcripción corresponde a sus bytes originales; no debe recalcularse serializando el objeto de otra manera.

Una salida de Scheduled tiene `meta.status=pendiente_validacion`. Solo el servidor podrá declararla válida, importar el análisis y publicar. No incluir rutas locales controladas por la salida externa.

## Integración del servidor

- El puente está implementado y su timer está activo. Usa el remote OAuth gdrive de rclone; el 13 de octubre su cliente compartido alcanzó la cuota. La carga inicial se completó con la conexión independiente de Google Drive de ChatGPT. Configurar un cliente OAuth propio y comprobar sincronización recurrente con `crbridge status`; un timer activo no acredita acceso a Drive.
- Subir nuevos trabajos sin duplicarlos y conservando los originales localmente; actualizar el índice ligero sin tratarlo como registro de validación.
- Revisar Resultados y Ejecuciones cada 15 minutos; un comprobante sirve para observar actividad, no para garantizar fidelidad del análisis.
- Contrastar `job_id`, video, prompt/esquema y transcripción con el registro local. Aplicar el esquema y `cranalysis.validate.validate` al análisis.
- Guardar válidos con los metadatos locales esperados por `crtranscripts.site.collect_analyses`, de forma atómica. Mantener rechazados separados. Regenerar la app solo después de importar resultados válidos.
- Mostrar pendientes, fallos y retrasos. No activar inferencia por API como alternativa automática.

Antes de ampliar el piloto, verificar una ejecución manual, una automática y una importación con validación. Las vistas móviles deben conservar sus narrativas, insights y fuentes; esta automatización cambia la producción del análisis.

Documentación oficial consultada el 13 de octubre de 2026:

- [Scheduled tasks](https://learn.chatgpt.com/docs/automations): herramientas conectadas, instrucciones duraderas y creación desde ChatGPT.
- [Uso y precios](https://learn.chatgpt.com/docs/pricing): la cuota de la suscripción y el saldo de la API se contabilizan por separado.

El puente aplica validación e importación, carga inicial del histórico y recuperación de material. [Detalles y estados](../../services/bridge/README.md). No equivale a una certificación de siete días de operación autónoma.

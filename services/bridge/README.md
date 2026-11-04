# Puente autónomo de CryptoReport

El servidor prepara trabajos, sube a Drive, valida resultados y publica JSON de la app. No importa SDKs de inferencia ni usa claves de modelos. SQLite conserva el estado; JSON conserva originales y análisis. Supabase no está conectado en esta entrega.

## Operación

Desde `services/bridge`, con el virtualenv preparado y el transporte configurado:

```sh
.venv/bin/python -m crbridge run
.venv/bin/python -m crbridge status
.venv/bin/python -m crbridge backfill
.venv/bin/python -m crbridge retry --video-id VIDEO --reason "Material revisado y reintento autorizado"
.venv/bin/python -m crbridge import-reviewed --result /ruta/resultado.json --source-file-id ID_OBSERVADO
```

`backfill` encola también el histórico local, una sola vez. Los ciclos normales descubren las últimas 48 h y conservan atrasos. `retry` requiere intervención operativa explícita: no se repiten fallos del modelo sin límite. `import-reviewed` reutiliza resultados ya revisados, aplica validación completa y no reemplaza uno distinto.

Instalar `requirements.txt`; rclone es necesario mientras se conserve ese backend. Copiar las unidades de `ops/` a `/etc/systemd/system/`, ejecutar `systemctl daemon-reload` y habilitar `cryptoreport-bridge.timer`. El perfil de extracción inicia además el puente al terminar cada ciclo, para evitar que el cerrojo compartido impida indefinidamente sincronizar. El timer cada 15 minutos sirve de respaldo.

## API oficial de Google Drive

El adaptador Python está implementado, con OAuth propio, cursor incremental,
pausas persistentes compartidas entre videos/cruces y recuperación de subidas con
IDs preasignados. Conserva la cola, los contratos y los validadores originales.
Los errores y el backend se exponen en `drive_transport` del estado operativo.

En este entorno se instalaron las dependencias y se verificó el código sin red.
La activación real requiere cliente OAuth y consentimiento de Google; el modo
`auto` conserva rclone hasta que `python -m crbridge.oauth activate` complete lectura,
escritura y lectura posterior. Los secretos permanecen fuera del repositorio.

[Instrucciones completas de OAuth y activación](GOOGLE-DRIVE-SETUP.md).

## Estados y contratos para el futuro panel

`<CR_DATA_DIR>/bridge/state.sqlite` guarda queued, uploaded, upload_uncertain, imported, rejected, conflict, blocked y needs_transcript. `bridge/jobs.json` expone identidad, canal, estado, motivo y última transición. `bridge/status.json` registra sincronización, publicación, recibos de Scheduled, extracción por canal y alertas de antigüedad. Se publica una copia como `pipeline-status.json` en ambas interfaces.

`recovery-requests.json` transmite los trabajos con material dudoso al extractor. Este prueba hasta dos recuperaciones por ciclo, con dos intentos por versión y seis horas de espera. Guarda variantes antiguas en `transcript-versions/`; segmentos idénticos no se presentan como una reparación. Una nueva transcripción produce un job_id distinto; un análisis anterior distinto requiere revisión y no se sobrescribe.

La puerta `crtranscripts.quality.assess` se comparte entre extracción, puente y exportadores. Excluye material vacío, idioma incorrecto, tiempos inválidos, duplicados exactos y truncamiento temporal sospechoso. Duración desconocida y huecos largos se señalan como límites; el control no certifica que todo el habla esté presente. Una frase incompleta en un short no demuestra truncamiento por sí sola.

## Costes y recuperación

Scraper.Tech es principal; yt-dlp es respaldo gratuito; Supadata se usa exclusivamente en modo native dentro del límite mensual configurado (perfil actual: 20 créditos). Dos consultas nativas máximo por video en la ingesta; recuperación tiene su límite independiente por versión y comparte el presupuesto global. Generación pagada de audio desactivada. 429/auth o tres fallos transitorios producen una pausa de 30 minutos. API de modelos bloqueada por defecto.

Las instrucciones vigentes de Scheduled en Control son revisión 1.4 y comparten dos intentos entre videos y cruces semánticos cuando existen ambos tipos. Detecta material dudoso y lo registra; no hay una herramienta de transcripción directa de ChatGPT comprobada en este entorno. El usuario debe comprobar la tarea guardada, horario y lectura del archivo actual; el servidor no controla la UI de Scheduled.

Drive es transporte y conserva resultados; no equivale a respaldo completo del histórico. El respaldo SQLite local usa la API backup y no copia una base viva ignorando WAL. OAuth propio y respaldo externo completo siguen pendientes de configuración. El cliente compartido de rclone alcanzó su cuota; el SDK oficial permite migrar el transporte después de configurar y verificar el cliente propio. Las cargas puntuales mediante el conector de ChatGPT no acreditan sincronización recurrente del VPS.

## Verificación

Pruebas sin red desde cada servicio: `python -m unittest discover -s tests -t .`. Para bridge: `PYTHONPATH=../analysis:../transcripts python -m unittest discover -s tests -t .`. GitHub Actions ejecuta estas suites cuando el workflow se publique en una rama del repositorio.

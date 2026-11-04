# Programaciones de inferencia: solo Codex

Desde el 3 de noviembre de 2026, por instrucción del usuario, las dos tareas
locales de inferencia usan exclusivamente Codex con la sesión ChatGPT.
Este estado sustituye el relevo a Claude del 20 de octubre y el respaldo entre
proveedores descrito el 2 de noviembre.

| Tarea | Ejecutor | Modelo | Frecuencia |
|---|---|---|---|
| `cryptoreport-analysis-plan` | `CR_ANALYSIS_EXECUTOR=codex` | `gpt-6-luna`, esfuerzo máximo | cada 15 minutos |
| `cryptoreport-semantic` | `CR_SOCIAL_EXECUTOR=codex` | `gpt-6-luna`, esfuerzo máximo | cada 2 horas |

Ambos temporizadores quedan habilitados para reinicios. No incluyen Claude como
respaldo. Si Codex no tiene sesión ChatGPT o rechaza la ejecución, no se recurre
a Claude ni a una clave API. El uso de Claude interactivo no se modifica.

El analista conserva el límite existente de 16 intentos por día de Bogotá y dos
trabajos por despacho. El cruce conserva un trabajo cada dos horas y hasta 12
llamadas por ejecución, con las mismas validaciones y puertas editoriales del
puente. Cambiar de proveedor no restablece los contadores diarios.

`CodexSubscriptionModel` usa un directorio temporal aislado, `codex exec`
efímero, sin configuración del usuario, con autenticación fijada a ChatGPT,
herramientas desactivadas y salida JSON según el esquema de cada etapa. El
cruce guarda `model_records` con uso declarado por Codex y errores concretos.

Instalación persistente:

- `services/analysis/ops/analysis-plan-executor.conf` se instala en
  `/etc/systemd/system/cryptoreport-analysis-plan.service.d/executor.conf`.
- `services/social/ops/cryptoreport-semantic.service` se instala en
  `/etc/systemd/system/cryptoreport-semantic.service`.
- Tras copiar las unidades: `systemctl daemon-reload` y
  `systemctl enable --now cryptoreport-analysis-plan.timer cryptoreport-semantic.timer`.

Verificación operativa: `systemctl list-timers --all`, los journals de ambos
servicios y `/var/lib/cryptoreport-transcripts/social/semantic/local-status.json`.
Una salida `daily_limit` del analista significa que conserva el límite del día,
no que el proveedor anterior siga seleccionado en la configuración instalada.

Copias anteriores y evidencia de activación:
`/root/audits/claude-a-codex-20261103/`.

Referencia de ejecución estructurada: [documentación oficial de Codex](https://developers.openai.com/codex/noninteractive).

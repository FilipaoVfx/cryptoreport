# Analista y alertas operativas

Estado vigente desde el 3 de noviembre: ambas programaciones usan exclusivamente Codex. Véase [relevo a solo Codex](relevo-solo-codex-2026-11-03.md). La configuración de Claude descrita abajo es histórica.

Actualización de alcance: por instrucción del usuario, el servicio automático
procesa únicamente publicaciones de las últimas 48 horas. Se retiró `--backlog`
de su arranque; los pendientes históricos se conservan. El supervisor usa
`scope=48h` y los contadores de revisión de ese periodo para sus alertas.

## Recuperación del analista

`cranalysis.plan` conserva el cerrojo de ejecución, el presupuesto de 16 intentos
diarios, los límites por trabajo, el orden de recientes antes del archivo y la
validación literal de citas. Los resultados rechazados permanecen en revisión;
no se reabren automáticamente ni se relaja el validador.

Con `CR_ANALYSIS_EXECUTOR=claude,codex`, la selección exige una sesión de
suscripción y que el proveedor no esté en espera. Un rechazo explícito `rate`
o `quota` guarda la pausa del proveedor y prueba el siguiente, una sola vez por
proveedor en ese intento. No se usan claves API. Si todos rechazan, no se
consume el intento del trabajo ni el presupuesto diario.

Las pausas por `rate` crecen de 30 a 60 y 120 minutos; por `quota`, duran seis
horas. El estado se guarda antes de cambiar de ejecutor. Una pausa global de la
versión anterior se migra al proveedor que la originó. Las pausas del operador,
los fallos técnicos y el límite diario conservan sus restricciones.

El estado privado registra `providers`, `active_attempt`, `last_failover` y
`last_validated_at`. Cada intento activo declara su inicio y plazo: 15 minutos
para Codex; para Claude, el plazo configurado, por defecto 45 minutos. El
monitor añade cinco minutos de margen antes de declarar un trabajo atascado.
Los metadatos de publicación corresponden al ejecutor que produjo el resultado.

## Supervisión y Telegram

El repositorio `/root/botRepos` contiene:

- `scripts/cryptoreport-health.js`: condiciones, transiciones, recordatorios y resumen.
- `scripts/cryptoreport-monitor.js`: lecturas locales y comprobación de servicios.
- `scripts/alert-delivery.js`: persistencia atómica y entrega confirmada.
- `ops/botrepos-cryptoreport.{service,timer}`: ejecución independiente cada cinco minutos.

Usa el destino `OPS_CHAT_ID` y el bot ya configurado, sin modificar credenciales.
El informe del monitor y la bandeja de avisos se guardan en
`/var/lib/botrepos/cryptoreport-health.json`. El monitor general de botRepos
comprueba que ese informe tenga menos de 15 minutos y detecta avisos que llevan
más de 15 minutos sin entrega confirmada. También usa la entrega durable para
sus propios avisos.

Condiciones iniciales:

| Condición | Umbral |
|---|---|
| Informe público ausente, inválido o viejo | 30 minutos |
| Cola sin despachos, sin ejecución activa | 40 minutos |
| Trabajo atascado | plazo del intento + 5 minutos |
| Cola sin publicación de análisis | aviso tras 2 horas; crítico tras 6 |
| Análisis válido pendiente del puente | 30 minutos |
| Rechazos de validación pendientes | aviso de revisión |
| Timer de análisis, puente o extracción / web detenidos | aviso crítico |

Se avisa al aparecer una condición, cambiar su gravedad y resolverse. Los
incidentes persistentes se recuerdan cada hora, sin acumular recordatorios si
el anterior sigue sin entregar. El resumen se emite en la primera ejecución
desde las 09:00 de Bogotá, una vez por día. Un cambio de ejecutor se informa una vez.

Antes de enviar se guarda la alerta; solo se elimina cuando Telegram confirma
la recepción. Una caída entre recepción y confirmación local puede duplicar
un mensaje, pero no perderlo. La cola conserva el orden y reintenta con espera
creciente hasta una hora. Un archivo de estado corrupto no se sobrescribe.

Ambos monitores corren en este servidor: una caída completa del servidor o de su
salida a Internet requiere un observador en otra máquina para avisar durante la
caída. Los avisos pendientes locales se recuperan cuando vuelve la conexión.

## Operación

Inspección sin enviar avisos:

```sh
cd /root/botRepos
node scripts/cryptoreport-monitor.js --dry-run
node scripts/healthcheck.js --dry-run
systemctl list-timers botrepos-cryptoreport.timer cryptoreport-analysis-plan.timer
```

Pruebas sin inferencia ni mensajes reales:

```sh
cd /root/botRepos
node --test scripts/cryptoreport-monitor.test.js
cd /root/cryptoreport/services/analysis
PYTHONPATH=.:../transcripts ../bridge/.venv/bin/python -m unittest discover -s tests -t .
cd /root/cryptoreport/services/bridge
PYTHONPATH=.:../analysis:../transcripts .venv/bin/python -m unittest discover -s tests -t .
```

Para detener solo las nuevas alertas: `systemctl disable --now botrepos-cryptoreport.timer`.
Esto no detiene análisis ni elimina la bandeja de pendientes. El monitor general
avisará después de 15 minutos de que el supervisor dejó de actualizarse.
Para revisar rechazos, consultar los artefactos de `analysis-plan/rejected` y
autorizar un reintento específico desde el panel después de revisar la causa.

# Parte 4 · Usabilidad y flujos con personas en el circuito (HITL)

> Lógica de interfaz para quienes **gestionan agentes**: personas que no programan el sistema pero responden de lo que publica. El objetivo es que vean el estado en segundos, actúen con una sola acción auditable y nunca hagan algo irreversible sin saberlo.
> Contratos: [`health-report`](contratos/esquemas/health-report.schema.json), [`feedback`](contratos/esquemas/feedback.schema.json), [`intervention`](contratos/esquemas/intervention.schema.json), [`audit-event`](contratos/esquemas/audit-event.schema.json) y `StreamEvent` de [`common`](contratos/esquemas/common.schema.json).

<a id="personas"></a>
## 4.1 Personas y trabajos

El equipo real es pequeño (1 a 3 personas), así que una misma persona puede tener varios roles. Las pantallas se diseñan por tarea, no por organigrama.

| Rol | Qué necesita | Frecuencia | Pantallas | Rol del panel |
|---|---|---|---|---|
| Gestión de agentes (editorial) | Saber qué publicó el agente, si es fiel al video y corregirlo | Diaria, unos 15 min | W4, W3, W8 | `reviewer` |
| Guardia operativa | Saber si algo está roto, por qué y arreglarlo sin SSH | Ante cada alerta | W1, W2, W5 | `operator` |
| Administración | Cambiar parámetros, prompts, cuentas y presupuestos con control | Semanal | W6, W7 | `admin` |
| Auditoría | Reconstruir quién hizo qué y comprobar que no se manipuló | A demanda | W7 | `auditor` |

<a id="principios-ux"></a>
## 4.2 Principios de UX

1. **Estado antes que detalle.** La portada responde en menos de 5 segundos a «¿está todo bien?» y, si no, «¿qué hago?».
2. **Ver antes de actuar.** Toda acción abre una vista previa (dry run) con efecto, coste, reversibilidad y precondiciones; se confirma en un segundo paso.
3. **Ninguna acción sin motivo.** Intervenciones, cambios y 👎 bloqueantes exigen un texto que queda en la auditoría.
4. **Teclado primero en la revisión:**
   - `j`/`k`: navegar;
   - `1`: 👍;
   - `2`: 👎;
   - `e`: saltar a la evidencia;
   - `?`: ayuda.
5. **Tiempo real sin ruido.** Las alertas se agrupan por umbral y objetivo, y solo vuelven a notificar si sube la severidad. Las alertas de severidad `warning` no hacen sonar nada.
6. **El significado no depende del color.** Cada estado lleva icono y texto (▲ crítico, ■ aviso, ✓ ok, ? sin datos). Se cumple WCAG 2.2 AA y PV-14. Verde y rojo se reservan al tono alcista y bajista, como en Urania, nunca al estado del sistema.
7. **La degradación se dice.** Si una fuente no responde, se muestra «sin datos» con la hora del último dato; nunca un cero.
8. **Español llano.** Términos técnicos solo donde la persona los necesita para actuar (por ejemplo «drive_quota» en RB-05).

<a id="navegacion"></a>
## 4.3 Mapa de navegación

```text
Inicio (W1) ─┬─ Ejecuciones ── Ejecución (W2: traza · logs · comprobante)
             ├─ Bandeja (W3: trabajos que requieren una persona)
             ├─ Revisión (W4: análisis con 👍/👎)
             ├─ Agentes ── rendimiento · trayectorias · autorater
             ├─ Biblioteca (W8: activos · versiones · búsqueda · índices)
             ├─ Intervenciones ── catálogo · historial · pendientes de aprobar (W5)
             ├─ Configuración (W6: parámetros · prompts · herramientas · guardas · solicitudes)
             ├─ Auditoría (W7)
             └─ Cuenta ── sesión · segundo factor
```

<a id="tablero"></a>
## 4.4 Tablero en tiempo real (W1)

Este wireframe muestra la portada con los datos reales del 14-oct a las 16:05 UTC (es el ejemplo [`portada-14-oct.json`](contratos/ejemplos/validos/health-report/portada-14-oct.json)).

```text
┌ Urania/Diario · Panel ───────────────────────────────────────────────── ● en vivo · 16:05 UTC · revisor-1 ▾ ┐
│ ▲ ESTADO: CRÍTICO — el puente falla en cada ciclo por cuota de Drive (SH-05) · 4 alertas      [Ver alertas] │
├──────────────────┬──────────────────┬──────────────────┬─────────────────┬────────────────┬────────────────┤
│ EXTRACCIÓN    ✓  │ PUENTE        ▲  │ AGENTE        ■  │ PUBLICACIÓN  ✓  │ API         —  │ TELEMETRÍA  ?  │
│ ciclo hace 4 min │ drive_quota      │ comprobante con  │ hace 34 min     │ apagada (G-01) │ sin datos      │
│ 5/5 canales RSS  │ 1 trabajo        │ error hace 10 h  │ 35 videos ·     │ 0 USD este mes │ (Fase 1)       │
│ p95 244 s        │ bloqueado        │ GCR 0,967 · 5/9  │ 32 análisis     │                │                │
├──────────────────┴──────────────────┴─────────┬────────┴─────────────────┴────────────────┴────────────────┤
│ ALERTAS ABIERTAS                               │ CICLOS · últimas 12 h (una celda = 15 min)                  │
│ ▲ SH-05 Puente con errores · RB-04             │ extractor ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ │
│   [Pausar subidas a Drive]   [Reconocer]       │ puente    □□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□ │
│ ▲ AP-04 22 trabajos en una ejecución · RB-16   │ agente    · · ● · ●×· ●×· · · · · · · · · · · · · · · · · · │
│ ■ SH-12 Sin comprobante desde hace 10 h 47 min │ ■ ok  □ con errores  ● comprobante  × con error              │
│ ■ SH-14 1 trabajo bloqueado · RB-07 [Bandeja]  │                                                              │
├────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ COLA DEL PUENTE                                │ PRESUPUESTOS · octubre                                       │
│ queued 1 ─► uploaded 2 ─► imported 32          │ Supadata      ███░░░░░░░░░░░░░░    4 / 20 créditos · proy. 9  │
│ revisión: blocked 1                 [Abrir]    │ Scraper.Tech  ██░░░░░░░░░░░░░░░   87 / 1000 · proy. 193       │
│                                                │ API modelos   0 USD (presupuesto 0 · guarda cerrada)          │
└────────────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘
```

Lógica de la pantalla:

- **Orden de lectura:**
  1. banda de estado: el peor componente y su causa en una frase;
  2. componentes;
  3. alertas con su acción principal;
  4. historia de ciclos;
  5. cola y presupuestos.
- **Estado de un componente:** el peor nivel entre sus señales (`signals[]` de `health-report`). `?` significa que no hay datos (`not_measured`), que es distinto de `ok`.
- **Tiempo real.** La página se suscribe a `GET /events/stream` (SSE). Con `run.finished` se repintan componentes y ciclos; con `alert.fired` o `alert.resolved`, la columna de alertas; con `intervention.updated`, la bandeja. Hay un `heartbeat` cada 25 s. Sin heartbeat durante 60 s, el indicador pasa a «◌ reconectando» y los valores se atenúan. Los datos de más de 2 ciclos se marcan «desactualizado».
- **Acciones en la alerta.** El botón principal es la intervención sugerida por el umbral (`alert.intervention`); el secundario reconoce la alerta. Las dos abren W5 o piden motivo.
- **Proyección de presupuesto.** Consumo del mes dividido entre los días transcurridos y multiplicado por los días del mes. Se muestra a partir del día 3.

<a id="wireframes"></a>
## 4.5 Wireframes de las pantallas clave

### W2 · Ejecución (traza, logs y decisiones)

```text
┌ Ejecución 01a13b27-…  cr-bridge · post_extract · failed · 21,4 s · código 04a86b9-dirty · config v1 ──────┐
│ [Traza]  Logs  Comprobante  Relacionadas: ← ciclo del extractor 01a13b24-… (16:00:40)                     │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ cr.bridge.cycle                       ██████████████████████████████████████████████   21,4 s  ▲ error     │
│   cr.bridge.step list                 ██                                                 0,9 s  ▲           │
│     cr.drive.call list (pendientes)   ██                                                 0,9 s  drive_quota │
│   cr.bridge.step publish                ████████████████                                 8,2 s  ✓           │
│   cr.bridge.step health                                   ██                             0,3 s  ✓           │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Span: cr.drive.call list · error.type = drive_quota · cr.drive.folder = pendientes                         │
│ Decisión: la cuota detiene las subidas de este ciclo (G-08) · Runbook: RB-05 · [Pausar subidas a Drive]     │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Las barras están a escala del span raíz.
- Al pulsar un span se ven sus atributos (del registro), sus eventos (`cr.job.state_changed`, `gen_ai.evaluation.result`, `cr.guardrail.decision`) y sus links.
- La pestaña Logs filtra VictoriaLogs por `cr.run.id`.
- Si Jaeger no responde (503 en `/runs/{id}/spans`), la pantalla muestra solo el libro de ejecuciones y avisa de que la traza no está disponible.

### W3 · Bandeja de revisión (trabajos)

```text
┌ Bandeja · trabajos que necesitan una persona ───────────────── estado ▾  canal ▾  antigüedad ▾  [Exportar] ┐
│ ▲ blocked · criptoniano · i2LUeRtROdg · «Por qué Trump puede disparar Bitcoin [Mi Plan]» · hace 10 h       │
│   Motivo: Scheduled registró un intento sin resultado (revision_material en el comprobante 3c884fc8)       │
│   [Ver transcripción]  [Pedir recuperación]  [Reintentar con motivo…]  [Ver comprobante]  [Historial]      │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ rejected 0 · conflict 0 · upload_uncertain 0 · needs_transcript 0                                          │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Cada estado tiene una acción por defecto:
  - `blocked`: reintentar;
  - `rejected`: abrir los errores del validador e importar la versión revisada;
  - `conflict`: comparar con el análisis vigente;
  - `upload_uncertain`: resolver, con 2.ª persona;
  - `needs_transcript`: pedir recuperación.
- El historial muestra las transiciones (C-02) con cuenta y motivo.

### W4 · Revisión de análisis con 👍/👎

```text
┌ Análisis · agFTCuv80XE · «CUIDADO: Bitcoin va a confirmar la TRAMPA BAJISTA en 3 DIAS» · nacho ─────────────┐
│ gpt-6.1-sol (verificado) · prompt 1.0.0 · validador ✓ 11/11 · parcial · 25 afirmaciones       [👍]  [👎]   │
├────────────────────────────────────────────┬────────────────────────────────────────────────────────────────┤
│ TRANSCRIPCIÓN                              │ AFIRMACIONES  ·  j/k moverse · 1 = 👍 · 2 = 👎 · e = evidencia   │
│ 00:31 …va a confirmar la trampa bajista…  ◀┼─ A3 predicción · bajista · confianza alta        [👍]  [👎]   │
│ 00:44 …en tres días…                       │    E5 [00:31–00:44] ✓ cita literal                              │
│ 02:10 …                                    │ ▸ A4 opinión · mixta                               [👍]  [👎]   │
│                                            │ ▸ A7 hecho_verificable · no_verificada             [👍]  [👎]   │
├────────────────────────────────────────────┴────────────────────────────────────────────────────────────────┤
│ 👎 en A7 · motivos: ☐ cita_incorrecta ☑ afirmacion_inventada ☐ omision_relevante ☐ tono_erroneo …          │
│ severidad: ○ menor ○ mayor ● bloqueante · comentario: «El creador no dice "URGENTE"; …»      [Guardar 👎]   │
│ Al ser bloqueante se solicitará «Poner en cuarentena» la versión d96416dd… (lo confirmas en el paso siguiente) │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Se valora la **versión**: el feedback guarda `target.version`. Si el análisis cambia, el feedback antiguo sigue unido a la versión que juzgó y no se arrastra a la nueva.
- El panel de la izquierda sincroniza el desplazamiento con la evidencia seleccionada, como el visor del sitio.
- Los colores de tono (verde neón alcista y fuego bajista) son los de Urania, porque aquí sí significan tono.

### W5 · Diálogo de intervención

```text
┌ Reintentar trabajo bloqueado · retry_job ─────────────────────────────────────────────────────────┐
│ Objetivo        i2LUeRtROdg__32dfbdf3…   (blocked desde las 05:20 UTC)                               │
│ Efecto          crbridge retry: el trabajo vuelve a queued; Scheduled lo verá en el índice de cola.  │
│ Coste           cuota de mensajes de ChatGPT (1 intento) · Reversible: no                           │
│ Precondiciones  ✓ hay un único trabajo blocked para el video   ✓ el motivo del bloqueo está leído    │
│ Motivo *        [ El material ya se revisó: reintentar con la autorización nueva.              ]    │
│ Permisos        reviewer ✓ · segunda persona: no necesaria                                          │
│                                          [Vista previa]   [Cancelar]   [Solicitar y ejecutar]        │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- La vista previa es `POST /interventions` con `dry_run: true`: devuelve `preview` con efecto, coste y precondiciones evaluadas, y no ejecuta nada.
- Si el tipo exige 2.ª persona, el botón pasa a «Solicitar aprobación» y la intervención queda en `pending_approval`. Quien la solicitó no ve el botón «Aprobar» (G-17).
- La misma `Idempotency-Key` hace que un doble clic no ejecute dos veces.

### W6 · Configuración: solicitud de cambio

```text
┌ Solicitud de cambio · riesgo alto · pendiente de aprobación ───────────────────────────── activa: v2 ┐
│ providers.supadata.monthly_credits     20 ─► 40     ⚠ recortado a 20 por el techo del host (G-16)     │
│ Motivo «Subir el respaldo de Supadata por la caída prolongada de Scraper.Tech.»                       │
│ Validaciones  ✓ esquema  ✓ sobre  ▲ techo del host  — pruebas  — evaluación  ✓ coste                  │
│ Propuso operador-1 · 22-oct 11:00 · aprobaciones 0/1 (quien propone no puede aprobar)                 │
│                                                   [Rechazar con motivo]   [Aprobar]   (sesión admin-1) │
└───────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- La diferencia se muestra siempre contra la versión activa. Si la versión cambia mientras se revisa, aplicar devuelve 412 y la pantalla ofrece revalidar.
- Los prompts muestran la diferencia de texto, el impacto (trabajos que quedarían `superseded`) y el resultado de la puerta de evaluación (PV-13).

### W7 · Auditoría

```text
┌ Auditoría · cadena íntegra ✓ · 4 eventos · cabeza 5bb9f359… · verificada hace 2 min ─── [Verificar ahora] ┐
│ seq  hora (UTC)  cuenta       acción                objetivo                       resultado             │
│ 4    16:31:00    operador-1   config.apply          config_change …                denegado · riesgo high │
│ 3    16:20:04    cr-panel     intervention.execute  intervention …                 éxito                  │
│ 2    16:20:00    revisor-1    intervention.request  intervention …                 éxito                  │
│ 1    16:19:30    revisor-1    session.login         session revisor-1              éxito                  │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Los datos son los de la [cadena de ejemplo](contratos/ejemplos/cadenas/auditoria-valida.json), que el CI verifica junto con su versión [manipulada](contratos/ejemplos/cadenas/auditoria-manipulada.json): esa se rompe en el seq 2.

### W8 · Biblioteca (inspector de activo)

```text
┌ Biblioteca ▸ transcript:OwrAjFdTQ4s ──────────────────────────────────────── versión fd6c08da… (vigente) ┐
│ «¿Ya están TODOS Bajistas? Bitcoin Va a Hacer ESTO…» · nacho · 1079 s · supadata · es                    │
│ Calidad ✓ válida · cobertura 1,00 · 193 palabras/min · sin huecos · 0 % no verbal   [Informe completo]   │
│ 00:00 ██████████████████████████████████████████████████████████████████████████████████████ 17:59      │
│ Linaje  video:OwrAjFdTQ4s ─► transcript@fd6c08da ─► analysis@b580749d ─► publicado                       │
│ Versiones  fd6c08da (vigente)                                          [Diferencias]  [Cuarentena…]      │
│ Buscar  [ trampa bajista              ]  modo híbrido → léxico (el índice semántico no está listo)       │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

<a id="feedback"></a>
## 4.6 Bucles de feedback 👍/👎

**Qué se valora:** un análisis completo, una afirmación, una evidencia, un segmento de transcripción, una etiqueta de tono o una mención de tema. Todo se ata a una versión concreta (`target.version`).

**Motivos de 👎** (taxonomía cerrada; `otro` exige comentario):

| Motivo | Significa | A dónde va |
|---|---|---|
| `cita_incorrecta` | La cita no dice eso o está fuera de contexto | Autorater `fidelity`; revisión del validador |
| `afirmacion_inventada` | El video no lo dice | Autorater `no_fabrication`; instrucciones |
| `omision_relevante` | Falta algo importante | Autorater `coverage` |
| `tono_erroneo` | Alcista o bajista mal leído | Calibración del motor de tono (DQ-M-03) |
| `verificacion_incorrecta` | El estado de verificación no corresponde | Autorater `verification_calibration` |
| `mencion_ambigua` | El léxico confundió el término (p. ej. «link») | Léxico de menciones (DQ-M-01) |
| `escenario_debil` | Escenario sin supuestos ni invalidación | Autorater `scenarios` |
| `transcripcion_erronea` | El error viene de la transcripción | `request_transcript_recovery` |
| `otro` | Ninguno de los anteriores | Revisión manual |

**Severidad y efectos:**

- **`minor`:** se agrega a AP-12.
- **`major`:** además entra en el conjunto de calibración del autorater.
- **`blocking`:** además solicita `quarantine_asset` sobre esa versión (AP-13). La persona confirma la solicitud en el paso siguiente.

```text
👍/👎 ─► feedback (inmutable, versión fijada)
          ├─► métricas: cr.feedback.ratings → AP-12 (aprobación humana)
          ├─► blocking ─► intervención quarantine_asset (requested) ─► revisión ─► site.py / build_data.py la excluyen
          ├─► major/blocking ─► conjunto de calibración del autorater (AP-11)
          ├─► tono_erroneo / mencion_ambigua ─► cola de ajustes del léxico (release)
          └─► patrones repetidos ─► propuesta de nueva revisión de instrucciones (W6, release)
```

**Reglas:**

- Una persona tiene como mucho un voto activo por versión. Votar de nuevo retracta el anterior (`retracts`) en lugar de sumar.
- El feedback nunca se borra.
- La superficie se registra (`panel`, `urania` o `site`). Si Urania incorpora botones de valoración, usarán el mismo contrato con `surface: urania`.

<a id="intervenciones"></a>
## 4.7 Disparadores de intervención manual

**Qué dispara cada intervención.** Cada umbral en modo *alert* sugiere una intervención (`alert.intervention` en [`umbrales.json`](contratos/registros/umbrales.json)):

| Disparador | Señal | Intervención sugerida |
|---|---|---|
| Extracción detenida | SH-01 | `run_extractor_now` |
| Puente sin sincronizar | SH-04 | `run_bridge_now` |
| Cuota de Drive | SH-06 | `pause_drive_uploads` |
| Proveedor caído o lento | SH-08 | `end_provider_cooldown` (tras corregir la causa) |
| Publicación atrasada | SH-11 | `republish` |
| Trabajos en revisión | SH-14 | `retry_job`, `import_reviewed`, `resolve_upload_uncertain`, `request_transcript_recovery` |
| Presupuesto al límite | CO-01 | `freeze_paid_providers` |
| Gasto de API con la guarda cerrada | CO-03 | `freeze_model_api` |
| Rechazos de la puerta de calidad | DQ-T-14 | `request_transcript_recovery` |
| 👎 bloqueante | AP-13 | `quarantine_asset` |
| Índice atrasado | DQ-E-03 | `rebuild_vector_index` |
| Emergencia general | Juicio humano | `stop_pipeline` (kill switch) |

**Catálogo completo** (generado desde [`registros/intervenciones.json`](contratos/registros/intervenciones.json)). Cada ejecutor es un argv fijo, una unidad concreta o un archivo de control; nunca un comando libre.

<!-- generado:inicio intervenciones -->
| Tipo | Intervención | Objetivo | Rol | 2.ª persona | Riesgo | Reversible | Coste | Ejecutor | Fase |
|---|---|---|---|---|---|---|---|---|---|
| `run_extractor_now` | Ejecutar extracción ahora | `run` | `operator` | no | `low` | no | créditos | systemctl · `start --no-block cryptoreport-transcripts.service` | 2 |
| `run_bridge_now` | Ejecutar el puente ahora | `run` | `operator` | no | `low` | no | ninguno | systemctl · `start --no-block cryptoreport-bridge.service` | 2 |
| `stop_pipeline` | Detener el pipeline (kill switch) | `run` | `admin` | no | `medium` | sí (`resume_pipeline`) | ninguno | systemctl · `stop cryptoreport-transcripts.timer cryptoreport-bridge.timer` | 2 |
| `resume_pipeline` | Reanudar el pipeline | `run` | `admin` | no | `medium` | sí (`stop_pipeline`) | ninguno | systemctl · `start cryptoreport-transcripts.timer cryptoreport-bridge.timer` | 2 |
| `retry_job` | Reintentar trabajo bloqueado | `job` | `reviewer` | no | `medium` | no | cuota de ChatGPT | cli · `crbridge retry --video-id {video_id} --reason {reason}` | 2 |
| `import_reviewed` | Importar resultado revisado | `job` | `reviewer` | sí | `high` | no | ninguno | cli · `crbridge import-reviewed --result {result} --source-file-id {source_file_id}` | 2 |
| `backfill_queue` | Encolar histórico (backfill) | `job` | `operator` | no | `medium` | no | cuota de ChatGPT | cli · `crbridge backfill` | 2 |
| `resolve_upload_uncertain` | Resolver subida dudosa | `job` | `operator` | sí | `high` | no | ninguno | state_file · `<CR_DATA_DIR>/bridge/panel-requests.json` | 2 |
| `request_transcript_recovery` | Pedir recuperación de transcripción | `transcript` | `operator` | no | `medium` | no | créditos | state_file · `<CR_DATA_DIR>/panel-recovery-requests.json` | 2 |
| `republish` | Republicar | `run` | `operator` | no | `low` | no | ninguno | systemctl · `start --no-block cryptoreport-bridge.service` | 2 |
| `end_provider_cooldown` | Terminar cooldown de proveedor | `tool` | `admin` | sí | `high` | no | créditos | state_file · `<CR_DATA_DIR>/panel-requests.json` | 2 |
| `freeze_paid_providers` | Congelar proveedores de pago | `tool` | `operator` | no | `low` | sí (`unfreeze_paid_providers`) | ninguno | config_change | 2 |
| `unfreeze_paid_providers` | Descongelar proveedores de pago | `tool` | `admin` | sí | `high` | sí (`freeze_paid_providers`) | créditos | config_change | 2 |
| `freeze_model_api` | Congelar API de modelos | `guardrail` | `operator` | no | `low` | no | ninguno | config_change | 2 |
| `pause_drive_uploads` | Pausar subidas a Drive | `tool` | `operator` | no | `low` | sí (`resume_drive_uploads`) | ninguno | state_file · `<CR_DATA_DIR>/bridge/panel-requests.json` | 2 |
| `resume_drive_uploads` | Reanudar subidas a Drive | `tool` | `operator` | no | `low` | sí (`pause_drive_uploads`) | ninguno | state_file · `<CR_DATA_DIR>/bridge/panel-requests.json` | 2 |
| `quarantine_asset` | Poner en cuarentena | `analysis` | `reviewer` | no | `medium` | sí (`release_asset`) | ninguno | state_file · `<CR_DATA_DIR>/quarantine.json` | 2 |
| `release_asset` | Liberar de cuarentena | `analysis` | `reviewer` | sí | `medium` | sí (`quarantine_asset`) | ninguno | state_file · `<CR_DATA_DIR>/quarantine.json` | 2 |
| `rebuild_vector_index` | Reconstruir índice vectorial | `vector_index` | `operator` | no | `low` | no | ninguno | panel | 3 |
| `run_autorater` | Ejecutar autorater | `analysis` | `reviewer` | sí | `medium` | no | API de pago | panel | 3 |
<!-- generado:fin intervenciones -->

<a id="auditoria"></a>
## 4.8 Rastro de auditoría con permisos

**Cadena de hashes.** Cada evento ([`audit-event`](contratos/esquemas/audit-event.schema.json)) se guarda en `panel.sqlite`, en una tabla sin `UPDATE` ni `DELETE` (lo garantiza un trigger que aborta la operación). Su `hash` se calcula así:

```text
hash = sha256( prev_hash + "\n" + JSON canónico del evento sin el campo hash )
JSON canónico = claves ordenadas, separadores "," y ":", UTF-8 sin escapar
el primer evento usa prev_hash = 64 ceros
```

- **Anclaje externo.** Cada día a las 00:05 UTC se escribe la cabeza de la cadena (`seq` y `hash`) en el journal y en `/var/log/cryptoreport-panel/audit-heads.log`, un archivo de root con atributo `chattr +a` (solo se puede añadir). Quien manipule la base también tendría que reescribir ese archivo, cosa que el usuario `crpanel` no puede hacer.
- **Verificación.** `GET /audit/verify` recalcula la cadena. PV-11 la ejecuta a diario y el CI la comprueba con las cadenas de ejemplo.
- **Qué entra en la auditoría:** inicios de sesión (también los fallidos), feedback, solicitudes, aprobaciones, ejecuciones y reversiones de intervenciones, propuestas, validaciones, aprobaciones, aplicaciones y reversiones de configuración, reconocimientos y silencios de alertas, exportaciones restringidas, cuarentenas y cambios de cuentas. Las denegaciones también entran (`outcome: denied`, con motivo).
- **Qué no entra:** contraseñas, secretos TOTP, IP en claro (se guarda `ip_hash` con sal) y contenido de los activos (solo sus hashes, en `diff`).

**Quién ve qué.** `auditor` y `admin` ven toda la cadena. El resto ve sus propios eventos en «Cuenta».

**Matriz de permisos** (generado desde `x-cr-min-role` de la OpenAPI; ✓ significa que el rol puede ejecutar la operación). Se listan las operaciones que cambian estado o leen la auditoría; toda lectura restante es para `viewer`.

<!-- generado:inicio rbac -->
| Operación | `viewer` | `reviewer` | `operator` | `admin` | `auditor` | Acción auditada |
|---|---|---|---|---|---|---|
| `acknowledgeAlert` | · | · | ✓ | ✓ | · | `alert.acknowledge` |
| `silenceAlert` | · | · | ✓ | ✓ | · | `alert.silence` |
| `createFeedback` | · | ✓ | ✓ | ✓ | · | `feedback.create` |
| `requestIntervention` | · | ✓ | ✓ | ✓ | · | `intervention.request` |
| `approveIntervention` | · | ✓ | ✓ | ✓ | · | `intervention.approve` |
| `rejectIntervention` | · | ✓ | ✓ | ✓ | · | `intervention.reject` |
| `cancelIntervention` | · | ✓ | ✓ | ✓ | · | `intervention.cancel` |
| `revertIntervention` | · | · | ✓ | ✓ | · | `intervention.revert` |
| `rollbackConfig` | · | · | ✓ | ✓ | · | `config.rollback` |
| `proposeConfigChange` | · | · | ✓ | ✓ | · | `config.propose` |
| `validateConfigChange` | · | · | ✓ | ✓ | · | `config.validate` |
| `approveConfigChange` | · | · | ✓ | ✓ | · | `config.approve` |
| `rejectConfigChange` | · | · | ✓ | ✓ | · | `config.reject` |
| `applyConfigChange` | · | · | ✓ | ✓ | · | `config.apply` |
| `createPromptVersion` | · | · | · | ✓ | · | `asset.version_create` |
| `getPromptVersion` | · | ✓ | ✓ | ✓ | · | — |
| `getAssetContent` | ✓ | ✓ | ✓ | ✓ | ✓ | `asset.export` |
| `searchLibrary` | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `listAuditEvents` | · | · | · | ✓ | ✓ | — |
| `verifyAuditChain` | · | · | · | ✓ | ✓ | `audit.verify` |
| `login` | ✓ | ✓ | ✓ | ✓ | ✓ | `session.login` |
| `logout` | ✓ | ✓ | ✓ | ✓ | ✓ | `session.logout` |
| `listUsers` | · | · | · | ✓ | · | — |
| `createUser` | · | · | · | ✓ | · | `user.create` |
| `updateUser` | · | · | · | ✓ | · | `user.role_change` |
<!-- generado:fin rbac -->

<a id="estados-ui"></a>
## 4.9 Estados vacíos, errores y degradación

| Situación | Qué ve la persona | Qué no debe ver nunca |
|---|---|---|
| Sin alertas | «Todo en orden. Último ciclo hace 4 min.» | Un panel vacío sin hora |
| Telemetría caída | Tiles con ? y «sin datos de traza desde 16:02»; el libro de ejecuciones sigue | Ceros o gráficas planas |
| Jaeger 503 | W2 con solo el libro de ejecuciones y el aviso «traza no disponible» | Un error genérico |
| Cola vacía | «No hay trabajos esperando al agente.» | «0 resultados» sin contexto |
| Índice semántico no listo | «Búsqueda por palabras: el índice semántico no está listo» | Resultados semánticos falsos |
| Acción denegada por rol | El botón aparece deshabilitado con «Requiere operator» | Un 403 crudo |
| Acción denegada por guarda | «Bloqueado por G-01: la API de pago está cerrada en el host» | Un mensaje sin la guarda |
| Sesión caducada | Nuevo inicio de sesión conservando el borrador | Perder el motivo escrito |

<a id="metricas-usabilidad"></a>
## 4.10 Métricas de usabilidad

| Métrica | Objetivo | Cómo se mide |
|---|---|---|
| Tiempo hasta reconocer una alerta crítica (horario laboral) | p50 ≤ 30 min | `fired_at` → `acknowledged.at` |
| Tiempo de un trabajo en revisión hasta resolverse | p90 ≤ 24 h | Historial de transiciones (C-02) |
| Análisis con al menos una revisión humana en 48 h | ≥ 50 % mientras el volumen sea de unos 8 al día | `feedback` por versión |
| Intervenciones revertidas | ≤ 10 % | `reverted` / `succeeded` |
| Tareas guionizadas completadas sin ayuda (5 tareas, cada persona del equipo) | ≥ 90 % | Prueba de usabilidad al cerrar la Fase 2 |
| SUS (System Usability Scale) | ≥ 75 | Cuestionario tras la prueba |
| Accesibilidad | 0 violaciones serias en axe-core | PV-14 |

# Pruebas

## Web y adaptador de Vercel

`npm ci` instala Playwright como dependencia de desarrollo; la app publicada no necesita un framework ni librerías de ejecución. `npm test` usa `node:test` y conserva las pruebas existentes de edición, feed, radar y tesis. También prueba la salida reproducible del build y la función HTTP de datos, incluidos límites, rutas rechazadas y respuestas inválidas. Los orígenes de prueba son servidores locales efímeros con datos sintéticos.

`npm run build` escribe exclusivamente `dist`, que se puede regenerar. `npm run test:browser` requiere `npx playwright install chromium`. Arranca sus propios servidores locales efímeros, abre contextos aislados en 390, 360 y 1280 píxeles y los cierra al terminar. Comprueba manifiesto, criterios de instalación de Chromium, rutas, caché, recarga sin conexión, coherencia entre generaciones del índice y videos visitados, recuperación del origen y activación de versiones con consentimiento del lector. Las capturas se guardan en `CAPTURE_DIR` o `/tmp/cryptoreport-pwa-check`.

`BASE` permite dirigir las mismas pruebas a un servidor local ya arrancado. La simulación de fallo/recuperación del origen solo se ejecuta con los servidores sintéticos propios. No dirigir estas pruebas de actualización a un despliegue remoto: la prueba sustituye temporalmente el service worker generado en el `dist` local y lo restaura al finalizar.

La emulación de red de Chromium puede mantener `navigator.onLine=true` después de una recarga sin red; la prueba exige que el aviso corresponda a la señal real y que el texto proceda de caché. El evento del botón de instalación se simula para probar la cancelación. Esto no demuestra la instalación física en iOS, la instalación del paquete Android ni la reproducción offline de YouTube. Esos límites deben mantenerse en cualquier informe.

## Servicios Python

Usa un entorno virtual y las dependencias ya declaradas:

```sh
python3 -m venv .venv
.venv/bin/pip install -r services/analysis/requirements.txt -r services/bridge/requirements.txt -r docs/observabilidad/herramientas/requirements.txt
.venv/bin/python scripts/check_offline.py
```

El runner ejecuta las suites `unittest` de análisis, transcripciones, puente, social, panel y datos móviles, y el validador de observabilidad. Fuerza `CRA_ALLOW_API_ANALYSIS=false`. No inicia recolectores, análisis pagados ni tareas programadas. Las pruebas de contrato no sustituyen una comprobación del origen real después del despliegue.

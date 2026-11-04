# CryptoReport

La web publicable es Urania (`prototypes/movil/b4-urania`). `scripts/build.mjs` crea un `dist` con una lista explícita de archivos. Los servicios Python y los datos generados del VPS no forman parte del paquete estático.

## Testing

- Web y adaptador HTTP: `npm test`.
- Build: `npm run build`.
- PWA en Chromium aislado: `npm run test:browser` después de `npx playwright install chromium`.
- Servicios y contratos sin proveedores: `python scripts/check_offline.py`, con las dependencias indicadas en [TESTING.md](TESTING.md).
- No ejecutar extracción, modelos, tareas programadas o despliegues remotos para verificar cambios de frontend.

## Datos y secretos

Mantener `.env`, tokens, SQLite, entornos virtuales, datos generados y artefactos locales fuera de Git. `CR_DATA_ORIGIN` y la autenticación opcional se consumen únicamente en `api/data.js`. No sustituir errores del origen por datos ficticios en producción.

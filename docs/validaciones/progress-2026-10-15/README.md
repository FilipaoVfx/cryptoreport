# Progreso de Signal mode

El deslizador nativo sin personalizar se sustituye por un trazo de 3 px, relleno violeta sincronizado, cursor de 12 px y etiqueta del minuto durante la interacción. La superficie de toque sigue midiendo 44 px. Conserva input range nativo para teclado, lector de pantalla y gestos; no añade dependencias.

Se mantienen las ondas verdes/rojas, salto desde la onda, lectura predeterminada y activación voluntaria de Signal. No se simula carga ni progreso de buffering. Se respeta movimiento reducido.

También se corrigió la sincronización: mantener el foco sobre el deslizador ya no congela su valor durante la reproducción. Durante el arrastre se muestra el destino; al soltar se confirma el salto. No se sobrescribe el destino en pointerup antes de que el navegador emita change.

Referencia de interacción consultada: [anatomía y accesibilidad del Slider de Radix](https://www.radix-ui.com/primitives/docs/components/slider). Implementación propia HTML/CSS/JS compatible con el proyecto, sin instalar Radix.

Validación: `signal-feed.browser.cjs` en Chromium a 360×800 y 390×844: salto por onda, arrastre al 75 %, confirmación al soltar, etiqueta temporal, toque al 50 %, Home/flechas, avance con foco, apertura/cierre y movimiento reducido. También verifica la actualización y caducidad del Feed con datos sintéticos. PASS, sin excepciones ni desbordamiento. Resultado `qa.json`; capturas `signal-390.png` y `signal-360.png`. Se usa el simulador existente, por lo que no certifica disponibilidad audiovisual de YouTube.

Se comprobó que HTML, CSS y JS del túnel coinciden byte a byte con el repo principal. No se consumieron créditos de modelos ni solicitudes de extracción.

# Ranking vigente: videos y menciones alcistas frente a bajistas

Decisión del usuario, 15 de octubre de 2026. Sustituye la propuesta anterior de usar «creadores y tesis» como orden principal.

- Sin selector de orden. Ranking fijo por **número de videos** en los filtros elegidos; desempate por número de menciones y luego identificador estable.
- Preferencias guardadas o enlaces antiguos con `m=conversacion`, `m=alza`, etc. se migran a `videos`; no cambian silenciosamente el criterio.
- Cada altcoin muestra videos, creadores y, como contraste principal, **menciones alcistas verdes frente a bajistas rojas**, con su termómetro. Las categorías internas mixta y neutra se suman bajo **«sin dirección clara»** en el ranking; no se convierten en apoyos. El detalle conserva la diferencia con «Direcciones combinadas» y «Sin dirección expresada».
- Se reutilizan los conteos completos de la transcripción publicados por el generador. Es clasificación de dirección/tono del texto; no certifica una operación declarada ni una recomendación. El método sigue disponible.
- Las tesis se mantienen en el detalle y en su vista, pero no cambian el puesto del activo. Su cobertura editorial parcial no sustituye el volumen ni el contraste de menciones.
- Creador y periodo aparecen al abrir «Filtros», con contador y contexto si hay selecciones activas. La búsqueda se abre desde la lupa y conserva la consulta visible al cerrarse. Ranking/Tesis usan pestañas de texto con subrayado. Solo se abre un panel a la vez; Escape lo cierra y devuelve el foco. Los enlaces a la ficha llevan creador y periodo. Citas alcistas y bajistas antes que neutrales.
- Timeline del Diario, signos vitales, Signal mode y Feed autónomo se conservan. No se regeneran análisis ni se activa inferencia.

Verificación: 32 pruebas JavaScript pasan. Chromium a 360×800, 390×844 y 1280×800 comprueba el recorrido completo, la ausencia del selector y que el orden, videos y ambos conteos coinciden exactamente con el índice fuente, incluso entrando por un enlace antiguo de «conversación». Sin excepciones ni desbordamiento horizontal.

Evidencia: `docs/validaciones/ranking-intenciones-2026-10-15/` y `docs/validaciones/ranking-minimal-2026-10-15/`.

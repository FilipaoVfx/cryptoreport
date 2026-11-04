# Ranking: menos ruido en categorías y filtros

Integrado en `/root/cryptoreport/prototypes/movil/b4-urania/`, servido por el túnel público existente.

- El ranking combina mixta + neutra como «sin dirección clara». Los conteos originales permanecen intactos. Rojo/verde y el orden fijo por videos permanecen como criterio principal.
- Filtros de creador y periodo plegados, lupa compacta y pestañas de texto. Las selecciones activas y la búsqueda siguen visibles al cerrar su panel.
- Chromium comprueba datos contra el índice fuente, filtros reales, búsqueda, Escape, clic exterior, enlaces antiguos y recorrido Diario → análisis → ranking → Feed → video voluntario. Tres tamaños: 360, 390 y 1280 px. Resultado en `qa.json`; capturas en esta carpeta.
- Se corrigió un caso encontrado durante la verificación: Escape en un input search podía borrar visualmente el texto sin actualizar los resultados. Ahora cierra el panel y conserva la consulta.

No se generaron análisis ni se llamó al proveedor de extracción. Ver también `../progress-2026-10-15/README.md`.

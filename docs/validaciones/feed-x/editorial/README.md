# Clasificación editorial y cruce semántico — 14 de octubre de 2026, Bogotá

Validación contra el túnel público, sin cookies ni llaves de acceso.

- Snapshot: 185 posts; 52 relevantes, 133 secundarios. El ejemplo «¿Siente sudores fríos? 😌» queda como micro de tres palabras, sin señales temáticas y fuera de cruces.
- La vista predeterminada muestra Relevantes. Todos conserva acceso al ejemplo; buscar «Siente sudores» devuelve una tarjeta. El filtro de seguridad devuelve ocho posts en este snapshot.
- Extensión, narrativa, cuenta y período se aplican localmente. El Feed solo solicita social-feed.json y social-connections.json: no descarga el índice de videos ni consulta proveedores.
- Sin desbordamiento a 320 y 390 px. Sin errores de consola en Feed. La vista de video conserva 33 notas en el video comprobado; el iframe de YouTube emite avisos propios de web-share/origen/adaptadores.
- 33 pruebas Python sociales, 23 del bridge, 19 del constructor móvil y 20 de JavaScript aprobadas. Sintaxis JS/Python correcta.
- Pruebas de rechazo: cita inventada, revisión incompleta, desacuerdo entre evaluación/revisión, post editado, análisis sustituido, vencimiento, claves JSON repetidas y números no finitos. Prueba completa de subida/importación con Drive simulado y conexiones de red prohibidas.
- Reconsultar una publicación sin cambiar texto/contexto no regenera trabajos por un avatar o fetched_at diferente. Un post a punto de vencer no elimina el resto de su página.
- Hay 22 trabajos preparados; cuatro trabajos actuales y el índice se comprobaron en Control usando el conector Google Drive. Dos documentos de control duplicados durante la preparación se renombraron conservando su contenido; los trabajos antiguos no se procesan fuera del índice vigente.
- La sincronización automática se incorporó al ciclo existente del bridge. Se observó un ciclo con cuatro subidas sin errores y fallos intermitentes drive_quota en otras comprobaciones. No se declara resuelto ese límite externo.
- Todavía no hay salidas semánticas reales aceptadas. El ejecutor necesita leer la revisión 1.4 de las instrucciones o su línea de activación. Preparar/subir trabajos no equivale a haberlos analizado.
- No se hicieron llamadas a modelos por API ni se solicitaron nuevas extracciones: contador social conservado en cinco solicitudes del primer ciclo.

Archivo visual: [relevantes.png](relevantes.png).

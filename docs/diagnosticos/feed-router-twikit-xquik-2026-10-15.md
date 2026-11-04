# Evaluación: Twikit y x-twitter-scraper para el router del Feed

Revisión documental y de código, 15 de octubre de 2026, Bogotá. No instala Twikit, no contrata servicios, no utiliza sesiones de X y no cambia el router en producción.

## Decisión

Sí conviene admitir varias fuentes. Deben aportar independencia real: cambiar de librería manteniendo la misma sesión de X no resuelve una sesión vencida, una restricción de cuenta o una caída común de los endpoints utilizados. El router existente ya admite Scraper.tech y el backend de Agent Reach, pero el primero tiene plan vencido y el segundo carece de sesión configurada. Añadir nombres a esa lista no crea una vía operativa.

El objetivo propuesto es continuidad de lecturas públicas mediante proveedores disponibles y límites propios, sin rotación de cuentas ni técnicas para ignorar restricciones explícitas. Un 401/403 de una sesión debe bloquear a todos los adaptadores que compartan esa sesión; un 429 debe respetar su espera.

## Twikit

Repositorio identificado: [d60/twikit](https://github.com/d60/twikit).

- Biblioteca Python asíncrona para la API interna de X. Permite guardar y cargar cookies; no necesita una clave de desarrollador oficial para ese modo. [Referencia](https://twikit.readthedocs.io/en/latest/twikit.html).
- La afirmación «solo iniciar sesión una vez» necesita matiz: reutilizar cookies evita repetir logins, pero no garantiza una sesión permanente ni una ejecución desatendida indefinida. Su propio autor advierte riesgo de bloqueo y recomienda limitar las solicitudes. [Advertencias del proyecto](https://github.com/d60/twikit/blob/main/ToProtectYourAccount.md).
- Metadatos de GitHub comprobados: repositorio sin archivar, último push declarado 10 de marzo de 2026. Último release publicado: 2.3.1, 6 de febrero de 2025. Esto no demuestra por sí solo que funcione o haya dejado de funcionar con el X actual. [Release](https://github.com/d60/twikit/releases/tag/version2.3.1).
- Existe `GuestClient`, que documenta lectura sin cuenta personal. Es candidato para una prueba pública acotada, no una garantía de cobertura. [Ejemplo](https://github.com/d60/twikit/blob/main/examples/guest.py).
- Limitación comprobada en el código actual: `GuestClient.get_user_tweets` hace una sola llamada y devuelve una lista; no expone un cursor de continuación en ese método. También convierte la ausencia de `instructions` en una lista vacía. Integrarlo sin una guarda propia podría confundir un cambio de esquema con «no publicó nada» y dejar huecos en cuentas activas. [Código](https://github.com/d60/twikit/blob/main/twikit/guest/client.py).

Clasificación: opción experimental. Primero evaluar GuestClient con pocas lecturas públicas y detenerse si requiere autenticación o rechaza el acceso. El modo autenticado conserva los riesgos ya explicados; no se propone usar la cuenta principal. Twikit y twitter-cli con la misma cookie pertenecerían al mismo grupo de autenticación y no contarían como respaldos independientes.

## x-twitter-scraper: identidad pendiente de confirmar

Se solicitó al usuario el enlace exacto. El candidato encontrado que coincide con TypeScript/Node y SDK Python es [Xquik-dev/x-twitter-scraper](https://github.com/Xquik-dev/x-twitter-scraper), acompañado de [su SDK Python](https://github.com/Xquik-dev/x-twitter-scraper-python).

Si se trata de ese proyecto:

- Es una integración con el servicio externo Xquik. El ejemplo requiere **XQUIK_API_KEY**, aunque no una clave oficial de X. El código abierto del SDK/plugin no hace gratuito el servicio remoto ni lo convierte en un extractor local autónomo.
- Según la documentación del proveedor, las lecturas de posts y perfiles públicos no requieren conectar una cuenta personal de X. No se verificó este comportamiento con una clave real. [Documentación](https://docs.xquik.com/api-reference/overview).
- El README publica búsqueda a un crédito por post devuelto y USD 0,00015 por crédito en pago por uso, con primera recarga de USD 10. Ejemplos únicamente de búsqueda: 1.000 resultados = USD 0,15; 10.000 = USD 1,50. No incluyen perfiles, monitores, relecturas, otros endpoints, impuestos ni futuras variaciones. No son una estimación del consumo observado de CryptoReport. [Referencia de precio y ejemplo](https://github.com/Xquik-dev/x-twitter-scraper#run-1-request).
- Incluye cursores y monitores, pero los monitores tienen facturación distinta. Para la cadencia de 6–12 h del producto, comenzar con consultas acotadas resultaría más fácil de medir que contratar escucha continua.
- Queda como candidato a proveedor separado, condicionado a confirmar repositorio, acceso, precio real del endpoint y calidad de resultados. No se compraron créditos ni se instaló su plugin.

Si el usuario se refiere a otro repositorio, estas conclusiones sobre Xquik no se transfieren al otro proyecto.

## Extensión propuesta del router existente

Cada adaptador debe declarar nombre, grupo de autenticación, grupo de fallo compartido, métodos soportados, paginación, modelo de cobro y límites de consumo. Los grupos evitan probar tres herramientas contra la misma sesión que ya fue rechazada.

| Condición | Acción |
| --- | --- |
| Red/timeout/5xx | Reintento posterior acotado; alternativa disponible dentro del presupuesto |
| 429 | Respetar Retry-After y pausar el grupo de cuota afectado |
| 401 o sesión rechazada | Pausar todos los adaptadores de esa sesión y pedir renovación |
| 403, challenge o cuenta restringida | Detener esa vía y registrar el motivo; no encadenar herramientas contra la misma restricción |
| 402 o plan vencido | Pausar el proveedor; usar otra fuente con acceso propio válido, sin compras automáticas |
| Esquema cambiado/datos inválidos | Rechazar página y conservar ventana/checkpoint; no presentar vacío como éxito |
| Sin fuente disponible | Mantener posts no vencidos y mostrar atraso; no inventar actualidad |

El resultado normalizado conserva ID, autor fijado, texto, fecha, fuente, fecha de consulta y hash. Deduplicación, retención y publicación siguen siendo locales. Los cursores permanecen separados por adaptador; los huecos se recuperan por rangos temporales. Los límites deben contemplar que un proveedor factura por solicitud y otro por post; un límite de «400 operaciones» no sustituye a un presupuesto monetario.

Secuencia recomendada: confirmar el repositorio; probar lecturas públicas con un candidato independiente; validar paginación, identidad, texto completo, ventanas y errores; observar siete días; habilitar como respaldo solo tras esas verificaciones. El motor de ingesta sigue sin depender de modelos ni de Schedule; el análisis narrativo mantiene su cola separada.

## Límites de esta revisión

Se revisaron documentación, metadatos y código fuente. No se hicieron lecturas reales de X con Twikit ni Xquik. No se puede concluir todavía que alguno evite los fallos operativos del entorno o cumpla una calidad de servicio sostenida. [X advierte](https://help.x.com/en/rules-and-policies/x-automation) sobre suspensión por automatización ajena a su API oficial; cambiar de librería no elimina esa dependencia.

# Prueba real de twitterapi.io

15 de octubre de 2026, Bogotá, 23:28:13–23:28:39. Solicitud del usuario: probar el proveedor con su clave. No se añadió al router ni se habilitaron consultas recurrentes.

## Resultado

**6 solicitudes, todas HTTP 200**: saldo antes, una página de búsqueda de cada cuenta y saldo después. Intervalo mínimo de 5,2 s, sin concurrencia, reintentos, paginación adicional ni llamadas a modelos. Se utilizó únicamente `https://api.twitterapi.io`, con TLS validado, autenticación en cabecera y redirecciones deshabilitadas.

La clave se recibió en memoria mediante entrada oculta de terminal. No se guardó en el script, el repo, el informe, Drive ni la configuración del servicio. No se usaron cookies ni credenciales de una cuenta personal de X. La clave del proveedor autoriza consumo de su saldo; no debe confundirse con una cookie personal ni con una clave de la API oficial de X.

| Cuenta | Posts devueltos | Nuevos frente al Feed local | Autor y fecha válidos |
| --- | ---: | ---: | ---: |
| BeInCrypto Español | 3 | 0 | 3 |
| Mattunchi | 9 | 3 | 9 |
| Vitalik Buterin | 1 | 0 | 1 |
| GranMag0 | 20 | 20 | 20 |
| Total | **33** | **23** | **33** |

Se consultó una ventana de 48 h y se comprobó localmente la pertenencia al intervalo, handle e ID fijado del autor, ID numérico como string, texto no vacío y fecha válida. No hubo autores incorrectos ni registros inválidos. La preclasificación local identificó 13 resultados relevantes; no equivale a revisión semántica ni verificación externa. Los 23 nuevos son candidatos de ingesta: **no se publicaron en la app en esta prueba**.

Las lecturas de datos tardaron entre **323 y 812 ms**, sin incluir la espera entre solicitudes. Todas devolvieron `has_next_page=true` y un cursor, incluso las que trajeron menos de 20 posts. **No se siguieron esos cursores**: no se acredita cobertura completa, exhaustividad del historial, funcionamiento de la paginación ni ausencia de páginas repetidas. La prueba sí acredita acceso desde el VPS, autenticación y datos útiles de las cuatro cuentas en ese momento.

## Saldo y costo

Antes: 0 créditos recargados y 100.000 créditos de bonificación. Después: 0 recargados y 99.820 de bonificación. Diferencia observada: **180 créditos**.

La [tarifa publicada](https://twitterapi.io/pricing/details) es 15 créditos por post devuelto en búsqueda, USD 0,00015 por post y mínimo de 15 créditos por consulta, incluso vacía. Los 33 resultados representarían **495 créditos / USD 0,00495** por las cuatro consultas de datos según esa tarifa; no se determinó el costo separado del endpoint de saldo. El cambio observado de 180 no permite conciliar todavía la facturación. Una actualización diferida u otra regla de cobro son hipótesis, no causas verificadas. No se hizo una séptima consulta para perseguir la diferencia.

Los créditos de bonificación no son fondos recargados permanentes. El proveedor publica caducidad de bonificaciones y condiciones de alta en su página de precios. No se recargó saldo, activó una suscripción ni utilizó crédito de modelos.

Las seis operaciones se reservaron antes de enviarlas, dentro del presupuesto local existente: se añadió el desglose `twitterapi-io` en `provider_usage`, sin reiniciar contadores ni aumentar límites. Registrar estas operaciones **no habilita el proveedor en producción**.

## Encaje y siguiente validación

Buen candidato para el router porque obtuvo datos públicos sin entregar una sesión personal de X. Sigue siendo un servicio de terceros con dependencia de saldo, límites y cobertura propios; esta prueba puntual no acredita fiabilidad sostenida ni independencia completa respecto a otros proveedores.

Antes de habilitarlo: verificar dos páginas del mismo cursor sin bucles, normalizar la respuesta real con las guardas de identidad/fecha/texto, incorporar cobro por resultado al presupuesto, comprobar saldo tras liquidación y mantener las ventanas 10/3/15/3 días. Una prueba de varios días debe medir puntualidad y huecos antes de prometer continuidad.

Evidencia sin secretos ni cuerpos de posts: [report.json](report.json). Referencias: [autenticación](https://docs.twitterapi.io/authentication), [límites](https://docs.twitterapi.io/rate-limits), [búsqueda](https://docs.twitterapi.io/api-reference/endpoint/tweet_advanced_search), [precios](https://twitterapi.io/pricing/details).

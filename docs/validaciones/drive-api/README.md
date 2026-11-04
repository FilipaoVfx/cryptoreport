# Adaptador oficial de Drive — validación del 14 de octubre de 2026

Estado: código implementado; activación real pendiente de OAuth propio.

## Resultado de las pruebas

| Suite | Pruebas aprobadas |
| --- | ---: |
| Bridge, incluidos 20 casos nuevos del adaptador/configuración | 43 |
| Feed y cruce semántico | 33 |
| Análisis | 28 |
| Transcripciones | 64 |
| Constructor móvil | 19 |
| JavaScript de Feed/Radar | 20 |
| Total | 207 |

Los casos del adaptador utilizan el SDK oficial instalado contra HTTP en memoria,
con conexiones de sockets prohibidas. No utilizan una imitación de los métodos
del SDK ni credenciales reales. Verifican la paginación, snapshots incrementales,
movimientos entre carpetas, límites de tamaño, versiones, autenticación, permisos,
cuotas y respuestas perdidas después de crear un archivo.

La prueba de subida incierta conserva el mismo ID preasignado tras reiniciar el
adaptador, incluso con retraso simulado en el listado. Una respuesta 409 se contrasta
por identidad y contenido antes de confirmar. La prueba del bridge completo crea
un trabajo, incorpora un resultado externo en el ciclo siguiente y confirma una
única importación/publicación mediante los validadores existentes.

La suite social comprueba además que otra sincronización sin cambios no vuelve
a escribir instrucciones ni el índice semántico en Drive.

## Entorno y comprobación operativa

Instalados en el virtualenv del bridge:

- google-api-python-client 2.201.0
- google-auth 2.62.0
- google-auth-httplib2 0.4.4
- google-auth-oauthlib 1.5.0

La comprobación de configuración devolvió:

```json
{"backend":"rclone","client_present":false,"token_present":false,"model_api_enabled":false}
```

`crbridge.oauth check` devolvió `drive_config`: falta el cliente OAuth y su token.
No activó el marcador del nuevo backend ni intentó consultas autenticadas a Google.
El timer existente continúa habilitado; no se modificaron los contratos de Schedule.

## Límite de esta validación

Los tests acreditan el comportamiento del código ante las respuestas simuladas,
no permisos efectivos de la cuenta ni una migración en producción. Para completarla,
seguir [la guía de OAuth](../../../services/bridge/GOOGLE-DRIVE-SETUP.md), ejecutar la
verificación real de carpetas/lectura/escritura y observar el primer ciclo del timer
usando `google-api`. No se hicieron llamadas a APIs de inferencia.

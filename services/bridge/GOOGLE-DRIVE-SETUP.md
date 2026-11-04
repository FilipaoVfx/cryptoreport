# Activar Google Drive API en CryptoReport

El adaptador está implementado y sus dependencias están instaladas en el virtualenv
del bridge. Falta un cliente OAuth propio y autorizar la cuenta propietaria de Drive.
Hasta completar la verificación, el modo `auto` conserva rclone. No se importan las
credenciales del cliente compartido de rclone al SDK.

## 1. Credenciales que se necesitan

Un JSON de cliente OAuth de Google, tipo **Aplicación de escritorio / Desktop app**.
Contiene `client_id` y `client_secret`. Una API key simple no autoriza el acceso
a archivos privados. El `refresh_token` se obtiene después de autorizar la cuenta;
no hace falta generarlo ni copiarlo a mano.

En [Google Cloud Console](https://console.cloud.google.com/):

1. Crear o elegir un proyecto propio, por ejemplo `CryptoReport Drive`.
2. Habilitar **Google Drive API** en APIs y servicios.
3. Configurar Google Auth Platform: nombre de la aplicación y correo de contacto.
   Para una cuenta Gmail personal, elegir audiencia External y añadir esa misma
   cuenta como usuario de prueba durante la configuración inicial. Internal solo
   corresponde cuando la organización Workspace lo permite.
4. En Data Access, configurar el alcance `https://www.googleapis.com/auth/drive`.
   Este flujo necesita leer archivos existentes creados por el ejecutor y escribir
   trabajos/control. La aplicación restringe sus operaciones a las carpetas del
   manifest; el permiso OAuth solicitado es más amplio que esa restricción local.
5. En **Clients → Create client → Desktop app**, crear el cliente y descargar JSON.

[Guía oficial de configuración](https://developers.google.com/workspace/drive/api/quickstart/python).

Para operación sostenida hay que revisar la publicación de la pantalla OAuth:
Google limita a siete días los refresh tokens de aplicaciones External en estado
Testing que solicitan estos alcances. Ese estado sirve para probar, no acredita
una autorización durable. Comprobar los requisitos que muestre Google para pasar
a producción y autorizar nuevamente si corresponde.
[Caducidad de OAuth](https://developers.google.com/identity/protocols/oauth2#expiration).

## 2. Guardar el JSON fuera del repositorio

Ruta esperada en el VPS:

```text
/etc/cryptoreport-drive/client.json
```

Directorio privado y archivo con permisos 600. No pegar secretos en el chat ni
guardar token/cliente en Git o en las carpetas públicas de la app. Si se usa SCP
desde una computadora, sustituir `usuario@tu-vps` por el acceso real:

```bash
scp ./cliente-descargado.json usuario@tu-vps:/tmp/cryptoreport-oauth-client.json
```

En el VPS, como administrador:

```bash
install -d -m 700 /etc/cryptoreport-drive
install -m 600 /tmp/cryptoreport-oauth-client.json /etc/cryptoreport-drive/client.json
```

Retirar la copia temporal cuando se confirme su instalación. Estos comandos son
instrucciones para aprovisionar el archivo: no se ejecutaron con credenciales reales
durante la implementación.

## 3. Autorizar la cuenta una vez

El callback OAuth solo escucha en `127.0.0.1:8765` durante cinco minutos. Para abrir
el navegador en una computadora y devolver la autorización al VPS, preparar el
túnel SSH desde esa computadora:

```bash
ssh -N -L 8765:127.0.0.1:8765 usuario@tu-vps
```

Dejarlo abierto. En otra terminal del VPS:

```bash
cd /root/cryptoreport/services/bridge
.venv/bin/python -m crbridge.oauth authorize
```

Abrir la URL que muestre el comando en el navegador de esa misma computadora,
elegir la cuenta de Drive correcta y conceder el permiso. La vuelta a localhost
viaja por SSH al proceso temporal del VPS. No se usa el túnel público de Urania.

El comando guarda `/etc/cryptoreport-drive/token.json` con permisos 600. Imprime
el estado, nunca el access token, refresh token ni client_secret. No activa la API
todavía. Si la autorización expira o es rechazada, se vuelve a iniciar el comando;
no se copia un código de autorización al chat.

Si se trabaja únicamente desde móvil y no se dispone de este túnel SSH, este
procedimiento necesita adaptarse antes de iniciarlo. No se ha implementado un
callback OAuth público en la app.

## 4. Comprobar y activar

Desde `services/bridge`:

```bash
.venv/bin/python -m crbridge.oauth status
.venv/bin/python -m crbridge.oauth check
.venv/bin/python -m crbridge.oauth activate
```

`check` comprueba existencia/permisos de las cuatro carpetas, lista sus archivos y
contrasta el prompt de Control con el repositorio. `activate` añade una prueba de
escritura y lectura posterior, usando el único archivo gestionado
`transport-api-probe.json` en Control. No analiza videos ni llama a modelos.

Ambos comandos usan el cerrojo del pipeline. Si devuelven `busy`, esperar al cierre
de extracción/sincronización y repetir. La selección del nuevo transporte solo se
guarda si las comprobaciones concluyen correctamente. No se hace fallback automático
de escrituras ante un error de Google.

Tras activar, el siguiente ciclo del timer selecciona `google-api`; no es necesario
cambiar el código, los archivos de Schedule ni las carpetas. Se debe verificar una
sincronización real antes de declarar completada la migración. El estado publicado
incluye `drive_transport`; `oauth status` también muestra el backend seleccionado.

## Configuración y recuperación

| Variable | Valor predeterminado |
| --- | --- |
| `CR_DRIVE_TRANSPORT` | `auto`: rclone hasta activación verificada; después Google API |
| `CR_DRIVE_CLIENT_FILE` | `/etc/cryptoreport-drive/client.json` |
| `CR_DRIVE_TOKEN_FILE` | `/etc/cryptoreport-drive/token.json` |
| `CR_DRIVE_STATE_FILE` | `<CR_DATA_DIR>/bridge/transport.sqlite` |

`google-api` fuerza el SDK y falla si faltan credenciales; `rclone` fuerza el
transporte anterior. Para variables persistentes del servicio se utiliza su
EnvironmentFile `/etc/cryptoreport-bridge.env`, protegido, en lugar de confiar en
variables de una terminal interactiva.

El marcador `<CR_DATA_DIR>/bridge/drive-transport.json` vincula la activación al
JSON de cliente verificado. El journal vincula snapshots al cliente y a la identidad
Google; cambiar de cliente/cuenta exige un estado de transporte independiente y
otra verificación. Puede indicarse otro `CR_DRIVE_STATE_FILE`, sin borrar el journal
previo ni la cola de videos. Renovar consentimiento con la misma cuenta/cliente
conserva las operaciones pendientes.

Los errores de cuota suspenden ambos consumidores durante 15, 30 y hasta 60 minutos
según fallos consecutivos. Los transitorios empiezan con una pausa de 60 segundos;
no hay bucles de reintentos ni cambios automáticos de proveedor. Un error de
autenticación detiene solicitudes hasta una autorización explícita nueva.

El SDK utiliza IDs preasignados y un journal de subidas para reconciliar respuestas
perdidas sin crear otra copia. Los archivos se leen por ID, verificando carpeta,
tipo, tamaño y versión antes/después. El límite sigue siendo 2 MB. Los snapshots
de metadatos se actualizan con el cursor de cambios y no conservan metadatos de
carpetas ajenas al catálogo.

La API de Drive y el ejecutor de análisis son componentes distintos: esta migración
no cambia el modelo, los intentos ni la programación de Schedule. No utiliza créditos
de inferencia. Tampoco constituye una garantía de ausencia de cuotas de Google.

## Validación realizada

Pruebas con el SDK oficial real y un transporte HTTP en memoria, con sockets de
red prohibidos: paginación, cambios, archivos movidos, versiones, cuotas persistentes,
permisos, autenticación, subidas inciertas y duplicados. Incluye una vuelta completa
de trabajo → resultado → validación/importación/publicación simulada, y comprobación
de que una verificación fallida no activa el backend.

La verificación OAuth y de Drive real sigue pendiente de las credenciales del usuario.

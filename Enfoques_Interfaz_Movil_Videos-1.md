# Tres enfoques para una SPA móvil centrada en vídeos

## Punto de partida

El producto permite estudiar vídeos de creadores especulativos y seguir cómo su contenido se convierte en afirmaciones, narrativas, menciones de activos y análisis. El vídeo es la fuente y el centro de la experiencia; las secciones de altcoins y análisis son caminos para profundizar.

La promesa de la interfaz: **«Mira qué se dijo, cómo se interpretó y de dónde sale cada conclusión».**

Estas propuestas son conceptos de diseño, no resultados de pruebas con usuarios. Los ejemplos de activos y afirmaciones son ficticios.

## 1. Vídeo con cuaderno de análisis

**Idea:** una experiencia familiar de reproducción, acompañada de un cuaderno que se construye a partir del vídeo.

### Pantalla principal

- Cabecera breve con búsqueda y acceso a vídeos guardados.
- Un vídeo destacado para continuar viendo.
- Lista de vídeos con miniatura, autor, fecha y estado de procesamiento.
- Cada tarjeta muestra una pista concreta: «4 afirmaciones detectadas · 2 activos mencionados».
- Navegación inferior: **Vídeos · Narrativas · Activos · Guardados**.

Evitar llenar las tarjetas con todos los hallazgos. Su función es llevar al vídeo.

### Pantalla del vídeo

El reproductor ocupa la parte superior. Debajo aparecen tres vistas: **Destilado · Transcripción · Análisis**.

El destilado tiene tarjetas vinculadas a momentos específicos:

> **03:42 · Afirmación del creador**  
> «Este activo podría beneficiarse de la próxima actualización».  
> **Interpretación del sistema:** el argumento depende de un evento futuro.  
> **Ver fragmento** · **Examinar argumento**

Al tocar una tarjeta, el reproductor salta al momento citado. Al profundizar en un hallazgo, el vídeo puede quedar como minirreproductor, conservando posición y controles.

### Cómo se ve la destilación

Una secuencia breve representa estados reales: **Transcripción disponible → Afirmaciones extraídas → Activos vinculados → Análisis disponible**.

Los resultados aparecen a medida que están listos. Una tarjeta pendiente explica qué falta. Si el análisis ya terminó, se muestra la secuencia completa como recorrido consultable, sin simular una ejecución en directo.

### Acceso a altcoins

Desde una mención, el usuario abre una ficha del activo con los vídeos y fragmentos que lo mencionan. Después puede explorar argumentos, desacuerdos y análisis más específicos.

### Identidad visual

Fondo neutro, tipografía legible, vídeo amplio y tarjetas discretas. Usar color para distinguir tipos de contenido, acompañado siempre de etiquetas.

### Ventajas y riesgos

**Ventaja:** requiere poco aprendizaje y mantiene una relación clara entre vídeo y resultado.  
**Riesgo:** el cuaderno puede convertirse en un scroll largo. Mostrar primero los hallazgos principales y permitir desplegar el resto.

**Elegirlo si:** quieres lanzar una primera versión clara y comprobar qué profundidad de análisis usan las personas.

---

## 2. Sala de edición de narrativas

**Idea:** el usuario siente que entra a una mesa editorial donde varios vídeos se convierten en una lectura comparada. La unidad principal sigue siendo el vídeo, pero puede pasar de una voz a varias perspectivas.

### Pantalla principal

Una portada editorial con:

- **Continuar viendo**, como primer bloque cuando hay una sesión pendiente.
- **Vídeos recientes**, en tarjetas grandes.
- **Narrativas en discusión**, presentadas con miniaturas de los vídeos que las sustentan.
- **Desacuerdos detectados**, con acceso a los fragmentos comparados.

Ejemplo de tarjeta:

> **¿Qué sostiene la narrativa de una nueva temporada de altcoins?**  
> Explora los argumentos de 5 vídeos.  
> **Abrir vídeos y argumentos**

El número indica fuentes examinadas; no demuestra que la narrativa sea correcta.

### Pantalla de exploración

Un vídeo activo en la parte superior y, debajo, una lista de capítulos analíticos:

1. Qué plantea este creador.
2. Qué evidencia aporta.
3. Qué supuestos necesita.
4. Qué dicen otros vídeos.
5. Qué preguntas quedan abiertas.

Un selector de fuentes permite cambiar de vídeo sin perder el tema consultado. En móvil se muestra una sola fuente a la vez; los desacuerdos se presentan como tarjetas consecutivas, evitando columnas pequeñas.

### Cómo se ve la destilación

Cada capítulo expone su construcción:

**Fragmentos seleccionados → Afirmaciones agrupadas → Coincidencias y diferencias → Síntesis interpretativa**.

La síntesis contiene accesos a sus fuentes. «3 creadores repiten esta idea» se distingue de «existe evidencia externa que la respalda». Si varios vídeos citan la misma fuente original, la interfaz señala esa dependencia.

### Acceso a altcoins

La ficha de un activo funciona como un dossier audiovisual:

- Vídeos que lo mencionan.
- Argumentos favorables y objeciones.
- Catalizadores citados y sus fechas.
- Cambios del discurso entre publicaciones.
- Evidencia aportada y datos que faltan.

El usuario puede abrir cualquier argumento y volver a escuchar la fuente.

### Identidad visual

Estética editorial: títulos claros, bloques con aire y miniaturas reconocibles. El autor y la fecha permanecen visibles para conservar contexto.

### Ventajas y riesgos

**Ventaja:** favorece la lectura entre líneas y la comparación de discursos.  
**Riesgo:** la síntesis puede desplazar al vídeo y parecer una conclusión definitiva. Mantener las fuentes cerca y separar consenso, evidencia e interpretación.

**Elegirlo si:** tu diferencial es ayudar a entender narrativas y contradicciones entre creadores.

---

## 3. Reactor audiovisual — enfoque radical

**Idea:** eliminar el dashboard convencional. Toda la experiencia comienza dentro de un vídeo, y el análisis emerge como una transformación visible de lo que se escucha.

El usuario entra a un **espacio de exploración audiovisual**: puede seguir la reproducción, detener una frase y abrir sus conexiones.

### Pantalla inicial

Un vídeo ocupa casi toda la pantalla, con reproducción iniciada por el usuario. Solo aparecen controles esenciales y un botón principal: **Destilar**.

No hay una cuadrícula de métricas. Para cambiar de fuente, se abre una bandeja con miniaturas y títulos. Los gestos son atajos; todas las acciones tienen botones visibles.

### Interacción central

Mientras avanza el vídeo, una cinta inferior muestra las afirmaciones asociadas al momento actual. No cubre subtítulos ni controles.

Al pulsar **Destilar**, el vídeo se pausa y la cinta se expande en una escena navegable:

- La frase seleccionada queda en el centro.
- Debajo aparecen **Activo**, **Supuesto**, **Evidencia citada** y **Narrativa**.
- El usuario toca una conexión y abre una tarjeta de detalle.
- Desde esa tarjeta puede reproducir el fragmento fuente o saltar a otro vídeo relacionado.

En móvil, el mapa muestra únicamente la frase y sus conexiones inmediatas. Las ramas se abren por niveles para evitar una nube de nodos ilegible.

### Cómo se ve la destilación

La transformación es el lenguaje de la interfaz:

**Una frase escuchada → Una afirmación aislada → Sus supuestos → Sus conexiones → Una lectura crítica**.

Ejemplo:

> **Frase:** «Todos están entrando en este activo».  
> **Afirmación extraída:** el creador sostiene que existe una entrada generalizada.  
> **Pregunta crítica:** ¿qué datos aporta para sostener “todos”?  
> **Evidencia en este fragmento:** no se identificó una fuente explícita.

La animación conecta visualmente la frase con sus elementos. No convierte una interpretación en un hecho ni crea conexiones que el sistema no haya identificado.

### Acceso a altcoins

El usuario toca el activo dentro de la escena y abre su **órbita de vídeos**: una secuencia de fragmentos relacionados, ordenables por fecha, argumento o creador.

Al seleccionar uno, ese vídeo pasa al centro. El activo actúa como puente entre fuentes y abre después un análisis profundo en una hoja de lectura.

### Navegación y orientación

- **Volver al vídeo** siempre visible.
- Una ruta corta indica el contexto: **Vídeo → Afirmación → Activo**.
- Una bandeja **Explorar** da acceso directo a vídeos, narrativas, activos y guardados.
- El botón Atrás regresa al nivel anterior; al volver al vídeo se conserva el segundo.
- Un modo de lista ofrece el mismo contenido para quien prefiera lectura lineal o use lector de pantalla.
- Las transiciones respetan la preferencia de movimiento reducido.

### Identidad visual

Fondo oscuro, vídeo dominante y conexiones luminosas discretas. La animación expresa relaciones; cada relación también se puede leer en texto.

### Ventajas y riesgos

**Ventaja:** hace que la destilación sea una experiencia memorable y el corazón del producto.  
**Riesgo:** puede dificultar orientación, lectura y rendimiento. Limitar las conexiones visibles, cargar ramas bajo demanda y ofrecer una vista lineal equivalente.

**Elegirlo si:** buscas una identidad muy distinta y puedes validar el modelo de interacción con prototipos antes de desarrollar todas las secciones.

---

## Comparación

| Criterio | 1. Cuaderno | 2. Sala editorial | 3. Reactor |
| --- | --- | --- | --- |
| Entrada principal | Elegir un vídeo | Elegir un vídeo o una narrativa | Entrar a un vídeo |
| Forma del análisis | Tarjetas y lectura | Capítulos y comparación | Escena que nace del fragmento |
| Acceso a activos | Desde menciones | Dossier de fuentes | Conexiones y órbita de vídeos |
| Aprendizaje esperado | Bajo | Medio | Alto |
| Complejidad relativa | Moderada | Alta | Muy alta |
| Fortaleza | Claridad | Contexto entre fuentes | Identidad e inmersión |

## Reglas comunes para que el vídeo siga siendo el core

### Trazabilidad

Cada afirmación y conclusión debe permitir abrir su vídeo y timestamp. Separar visualmente:

- **Lo que dice el creador.**
- **Lo que extrae o interpreta el sistema.**
- **Lo que respalda una fuente externa**, cuando se haya consultado.

Una cita literal debe distinguirse de una paráfrasis. Conservar fecha del vídeo y del análisis para no mezclar discursos de momentos diferentes.

### Incertidumbre

Usar estados como **sin verificar**, **respaldado por la fuente citada** o **interpretación**. Evitar porcentajes de confianza sin una metodología que el usuario pueda consultar.

La ausencia de evidencia en un vídeo no prueba que una afirmación sea falsa. Una predicción, una opinión y un hecho verificable requieren etiquetas distintas.

### Experiencia móvil

- Controles cómodos para tocar, texto legible y respeto de las áreas seguras del dispositivo.
- No depender de hover, color o gestos ocultos.
- Mantener el vídeo accesible al profundizar, sin tapar el contenido.
- Reservar espacio para el reproductor y las tarjetas durante la carga.
- Conservar filtros, scroll y posición del vídeo al navegar dentro de la SPA.
- Permitir enlazar y compartir un hallazgo específico con su contexto.

### Estados reales del producto

Diseñar explícitamente: vídeo pendiente, procesamiento parcial, análisis listo, transcripción no disponible, vídeo inaccesible y error recuperable.

Si no existe un resultado, explicar qué falta y permitir continuar con lo disponible. Las animaciones de destilación deben corresponder al estado real del procesamiento.

## Recomendación

**Comenzaría con el enfoque 1, incorporaría la comparación del enfoque 2 y probaría el enfoque 3 como modo “Destilar” dentro de un vídeo.**

Así puedes validar la propuesta radical en una parte concreta de la experiencia. Si las pruebas muestran que el usuario entiende mejor las conexiones y vuelve a usarlas, ese modo puede convertirse en la interfaz principal.

Para comparar prototipos, propondría las mismas tareas:

1. Encontrar qué dijo un creador sobre un activo.
2. Ver el fragmento que sostiene una conclusión.
3. Distinguir la interpretación del sistema de la afirmación original.
4. Consultar otro vídeo con una postura distinta.
5. Volver al vídeo inicial conservando el momento de reproducción.

Observaría éxito de la tarea, desorientación y comprensión de las fuentes. La estética importa, pero la prueba principal es si el usuario puede seguir el recorrido **vídeo → dato → interpretación → análisis** sin perder contexto.


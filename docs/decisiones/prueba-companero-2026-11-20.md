# Prueba con una persona ajena · Momento 3

Prueba de la app terminada (monitor y coach) por alguien que nunca la usó y no ayudó a construirla. Es el ensayo de la demo, donde la rúbrica pide que una persona ajena al equipo la use.

> **Antes de empezar.**
> - La cámara se enciende al iniciar la sesión y se apaga al terminarla. No se guarda ninguna imagen.
> - El título de las ventanas ambiguas va a Groq con la meta: que la persona no abra correo, banco ni nada privado durante la prueba.
> - Lo que escriba en el chat también sale del equipo.
> - Nadie le dicta los pasos: solo recibe la tarea de abajo, igual a todos.

## Datos de la prueba
| Campo | Valor |
|---|---|
| Fecha y hora | 2026-11-20, 7:24 a. m. (sesión 38 en la base) |
| Quién la hizo | Juan Florez, padre del autor, con su permiso |
| Perfil | No programa, usa el computador para trabajo de oficina, nunca vio BioFocus |
| Versión probada | `a7cc9b8` |
| Proveedor de IA | El configurado en `.env` (no se registró cuál) |
| Imagen | Cámara |
| Duración total | Sesión del monitor: 1 min 52 s (terminó con la tecla q). La prueba completa, con el coach, no se cronometró |
| Ayuda que recibió | Antes de empezar se le explicó brevemente para qué sirve la app y sus funciones básicas (no se registraron las palabras exactas). Durante la prueba no recibió ayuda |

## Lo que se le pide (dicho igual a todos)
1. «Esta es una app para estudiar con foco. Ábrela y empieza una sesión con la meta que quieras.»
2. «Quédate un momento derecho, y luego encórvate como si miraras el celular en las piernas, hasta que pase algo.»
3. «Abre YouTube y quédate ahí hasta que pase algo.» (En esta prueba usó Facebook.)
4. «Pregúntale al coach cómo va tu sesión y qué te distrajo.»
5. «Pídele que marque una app como que no sirve, y decide si lo aceptas.»
6. «Termina la sesión.»
7. «Dime con tus palabras qué hace la app con tu imagen y qué sale de tu computador.»

## Qué intentó
| # | Paso | Qué esperaba | Qué pasó | ¿Lo logró? (sí / no / con ayuda) | Tiempo |
|---|---|---|---|---|---|
| 1 | Abrir y empezar la sesión | Que la sesión empezara | Escribió la meta «Desarrollo de actividad» y la sesión empezó | Sí | 10 s |
| 2 | Alerta de postura | Que le saltara un aviso durante la sesión | La alerta sí saltó a los 35 s (−30 %, `monitor.log`), pero solo en la ventana de la cámara, que estaba detrás. No la vio y no hubo sonido | No | n/a |
| 3 | Alerta de distracción | Que le saltara un aviso durante la sesión | Abrió Facebook. La alerta saltó a los 99 s (`monitor.log`), otra vez solo en la ventana de la cámara. No la vio | No | n/a |
| 4 | Preguntas al coach | Ver los registros de sus sesiones | Buscó una sección de registros y no la encontró (está en la barra lateral, «Sesiones reales»). Le hizo al coach dos preguntas (tabla de abajo) y las dos respuestas fueron correctas | Sí | No se registró |
| 5 | Regla: aprobar o rechazar | Marcar YouTube como distracción | El coach no propuso la regla porque YouTube no aparecía en sus sesiones (había usado Facebook) | No | 1 min |
| 6 | Terminar | Terminar la sesión | Terminó con la tecla q en la ventana de la cámara, a los 1 min 52 s (`monitor.log`) | Sí | No se registró |
| 7 | Explicar la privacidad | (no aplica: aquí se le pregunta a él) | No se registró su respuesta | No se registró | n/a |
| 8 | Recalibrar y cambiar los rangos de las alertas (no estaba en la tarea) | Encontrar un botón para recalibrar y poder cambiar los rangos de las alertas | No encontró cómo recalibrar sin ir a la ventana de la cámara (tecla c), ni dónde cambiar los rangos (no se pueden cambiar desde la app) | En parte | 2 min |
| 9 | Ver las alertas mientras trabaja (no estaba en la tarea) | Ver los avisos sin importar qué ventana tenga al frente | Las alertas solo se ven en la ventana de la cámara, que queda detrás al pasar a otra ventana | No | 10 s |

## Preguntas que le hizo al coach
Verifica cada respuesta contra el panel de la sesión o la base.

| Pregunta, tal como la escribió | Respuesta del coach (resumen) | ¿Era correcta? | ¿Entendió «Fuente y criterio»? | Id de la traza |
|---|---|---|---|---|
| Cuanta fue mi velocidad de escritura en mi ultima sesion? | Dijo que no tiene la velocidad de escritura, y ofreció en cambio minutos estudiados, alertas y apps que lo distrajeron | Sí: BioFocus no mide la escritura, a propósito (`docs/SPEC.md`, renegociación) | Sí, aunque creía que la app ya medía eso | `a82a783fba21` |
| muestrame mi rendimiento en mis ultimas sesiones | Del 14 al 20 de noviembre: 2 sesiones, 3 min reales de 7 planeados, 1 alerta de postura y 1 de distracción, 1,5 min por sesión, sin pausas | Sí | Sí | `69e8b17a05f0` |

## Dónde se trabó
Un renglón por cada vez que se detuvo más de un minuto, dudó o pidió ayuda.

| # | Paso | Qué pasó | Tiempo perdido | Cómo salió (solo / con ayuda / no salió) | Causa probable |
|---|---|---|---|---|---|
| 1 | 2, 3 y 9 · Alertas | Las alertas de postura (35 s) y de distracción (99 s) saltaron, pero solo en la ventana de la cámara, que quedó detrás. No vio ninguna | Las dos alertas | No salió | Ventana del monitor: el aviso no sale fuera de ella y no hay sonido |
| 2 | 4 · Registros | Buscó una sección de registros de sesiones y no la encontró | No se registró | Solo: le preguntó al coach | Texto de la app: los paneles «Sesiones reales» de la barra lateral no se reconocen como registros |
| 3 | 5 · Regla | El coach no propuso la regla para YouTube porque no estaba en sus sesiones | 1 min | No salió | Coach: solo propone reglas para apps vistas; no explica cómo marcar una app nueva |
| 4 | 8 · Recalibrar y rangos | No encontró cómo recalibrar desde la app ni cómo cambiar los rangos de las alertas | 2 min | No salió | Texto de la app: recalibrar es la tecla c en la ventana de la cámara; los rangos son fijos en el código |

## Lo que dijo
Citas textuales, con su permiso, sobre todo de lo que le confundió o le pareció útil.

- «Me pareció interesante la dinámica, pero siento que aún se queda muy corto con el potencial que se puede pretender. Sería práctico que, además de preguntarle al bot, exista una barra de pestañas en la parte superior donde se pueda acceder a las herramientas o secciones independientemente y que no se alargue la página hacia abajo; se ve mucha saturación de información. En esa misma barra, poder encontrar los registros enlistados y una visualización amigable del dashboard completo, con posibilidad de filtrar los datos. Es importante también tener mensajes tipo popup para avisar en cualquier momento sobre las alertas, sin necesidad de entrar al panel de la cámara o al aplicativo.»

## Qué cambié
Bloque I de `docs/PLAN-M3.md`, aprobado el 2026-11-20. El coach no se tocó, para que las cifras finales sigan valiendo.

| # | Problema que vio | Cambio que hice | Commit | ¿Cómo lo verifiqué? |
|---|---|---|---|---|
| 1 | No vio ninguna alerta: solo salían en la ventana de la cámara, que quedó detrás (pasos 2, 3 y 9) | Cada alerta de postura, de distracción y cada recordatorio de pausa abre un aviso emergente encima de todo, abajo a la derecha, con sonido. No roba el teclado y se cierra solo a los 8 s (`producto/aviso.py`) | «Momento 3, bloque I» | `encorvado.mp4` con la cámara oculta: alerta a los 19 s y aviso en pantalla; `aviso.py` se abre y se cierra solo (salida 0). El autor lo vio y lo oyó en su pantalla. Pruebas de `tests/test_bloque_i.py` |
| 2 | Quería el aviso «sin necesidad de entrar al panel de la cámara» | La cámara trabaja oculta por defecto. «Ver la imagen de la cámara» es un interruptor del formulario. Al cumplirse el tiempo planeado sale un aviso «la cámara sigue encendida», cada 10 min | «Momento 3, bloque I» | Sesión desde la app con `encorvado.mp4` y una base temporal: sin ventana de cámara, con panel en vivo |
| 3 | No encontró cómo recalibrar sin ir a la ventana de la cámara (paso 8) | Botón «Recalibrar postura» junto a «Terminar sesión»; el monitor lo aplica en el siguiente segundo | «Momento 3, bloque I» | En la misma sesión: `monitor.log` dice «Recalibrando desde la app a los 12 s», y «Terminar sesión» la cerró |
| 4 | No pudo cambiar los rangos de las alertas (paso 8) | Pestaña «Ajustes»: cuánto puede bajar la cabeza (20 a 40 %), segundos de mala postura, segundos en algo que no sirve y cada cuánto la pausa, con topes y su porqué | «Momento 3, bloque I» | Subí la caída a 30 % y la guardé. La siguiente sesión arrancó con «Sensibilidad: caída 30 % durante 20 s» en `monitor.log` |
| 5 | Buscó sus registros y no los encontró; «se ve mucha saturación de información» (paso 4 y su cita) | Pestañas Sesión, Coach, Mis registros y Ajustes, con la barra lateral plegada. «Mis registros» lista las sesiones y tiene filtros por origen y fechas, cifras, minutos por categoría, alertas por día y la línea de tiempo de cada sesión | «Momento 3, bloque I» | Vista previa con una base temporal: 11 sesiones demo del 14 al 20 de noviembre, sin errores en la consola |

## Lo que no cambié y por qué
- Velocidad de escritura: no se mide a propósito; pide un gancho global de teclado, que es la capacidad de un keylogger (`docs/SPEC.md`, renegociación).
- Reglas para apps que todavía no aparecen en los datos: el código las rechaza (`herramientas.py:147`) para que la regla coincida con el nombre exacto que ve el clasificador. Se asume; la app ya aparece en cuanto se usa una vez.
- Falta repetir la prueba con una persona ajena con la app nueva. Es el ensayo de la demo en vivo.

## Conclusión
- ¿Pudo usarlo sin ayuda? En parte: empezó, consultó al coach y terminó solo, pero no vio ninguna alerta.
- Lo que más le costó: ver las alertas, que solo aparecen en la ventana de la cámara.
- Lo que hay que arreglar: que la alerta se vea, y suene, aunque la ventana de la cámara esté detrás.
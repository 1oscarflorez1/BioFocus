# Decisiones · Momento 3

Fechas: 2026-11-11 y 2026-11-17. Plan: `docs/PLAN-M3.md`. El bloque A quedó aprobado por la instrucción «evaluar y corregir lo necesario». Aquí van las decisiones menores que tomé sin preguntar, para revisarlas.

## Auditoría
- Leí todo el repositorio y reproduje cada defecto antes de tocarlo, con un LLM falso y bases temporales, sin red, sin cámara y sin tocar `data/`. La tabla de hallazgos está al final de `docs/PLAN-M3.md`.
- Intenté dos veces una auditoría con cuatro agentes en paralelo. El límite de uso cortó ambas antes de que entregaran, así que no dejaron resultados: la auditoría que vale es la lectura completa y las reproducciones.
- Las cuatro cifras de `semana10.md` salen exactas al recalcularlas desde `producto/evals/resultados/2026-10-31_1059.json`.

## A1 · Ventanas con título cambiante (`producto/ventanas.py`)
- **Antes:** la ventana nueva debía repetir el mismo título exacto durante 5 s. Un título que cambia en cada lectura (temporizador, contador de mensajes, spinner de una terminal) nunca contaba, y su tiempo se anotaba en la ventana anterior. Si la anterior era YouTube, la racha de distracción seguía y la alerta saltaba mientras la persona trabajaba.
- **Ahora:** la ventana nueva se sigue por su proceso. A los 5 s fuera de la ventana actual se clasifica el título más reciente.
- **Lo que arrastra el arreglo:** al contar esas ventanas, cada título nuevo sería otra consulta al LLM. Por eso entran dos límites:
  - **Caché por título equivalente.** La clave va en minúsculas, sin números y sin símbolos: «24:59 Pomodoro» y «(3) 24:57 Pomodoro» comparten una consulta. Al LLM sigue llegando el título tal cual, una sola vez. Un título que es solo números o símbolos conserva su texto como clave.
  - **Tope de 6 consultas por minuto** (`MAX_LLM_POR_MINUTO`). Pasado el tope, la ventana queda `sin_clasificar` con la razón «muchas consultas en este minuto»: no alerta ni inventa. Las consultas que fallan también cuentan, para no insistirle a un proveedor caído. Ese resultado no se guarda en caché.
- **Límite conocido:** dos pestañas visitadas menos de 5 s cada una, dentro del mismo navegador, suman su tiempo a la tercera, que es la que se clasifica.

## A2 · Cámara que tarda o se corta (`producto/monitor.py`)
- **Antes:** un solo cuadro perdido cerraba la sesión. Pasó el 2026-10-31: la sesión 21 duró 0 s (`data/monitor.log`).
- **Ahora:** el monitor tolera hasta 10 s sin imagen (`CORTE_CAMARA_MAX_S`). A los 5 s reabre la cámara una vez; si a los 10 s no volvió, cierra con el mismo motivo de antes.
- Mientras no hay imagen, el bucle sigue: escribe el latido, atiende `q` y el «Terminar» de la app, y muestra un cuadro negro con «Cámara sin imagen: reintentando…». La postura queda en «no te veo», sin alerta.
- 10 s es menos que los 15 s con que la app da al monitor por caído (hay prueba).
- Con `--video` no se reintenta: sin cuadro es que el video terminó.
- La decisión de esperar, reabrir o rendirse vive en la clase `CorteCamara`, para poder probarla sin cámara.

## A3 · Monitor caído (`producto/vivo.py`, `producto/app.py`, `producto/monitor.py`)
- **Antes:** el monitor escribe cada tramo de ventana al cerrarlo. Si se caía, el tramo abierto se perdía: dos horas en una sola ventana quedaban en 0 minutos.
- **Ahora:** `vivo.cerrar_sin_monitor` guarda ese tramo desde `estado_monitor` (app, categoría y desde cuándo; ahí no hay títulos) y cierra la sesión en su última señal de vida. La usan `cerrar_huerfanas` y el cierre forzado de la app.
- **Cambio de comportamiento:** el cierre forzado de la app («el monitor no respondió») cerraba en la hora actual; ahora cierra en la última señal de vida, que es hasta donde hay datos.
- **Sin duplicados:** si el monitor despierta después (por ejemplo, tras suspender el equipo) e intenta guardar el mismo tramo, `Registro.tramo` ve que ya existe uno con ese inicio y no lo escribe otra vez.
- **Límite conocido, sin arreglar:** si tras una suspensión el monitor despierta antes de que la app lo dé por caído, el tiempo suspendido se suma a la ventana actual. Queda para B4 (pausas).

## A4 y A5
- **A4:** la app pasa `--meta=valor` en un solo argumento. Con `--meta -repaso`, argparse tomaba la meta por otra opción y el monitor no arrancaba.
- **A5:** `.env.example` documenta `LLM_CLASIFICADOR_PROVIDER` (vacío, `ollama` o `ninguno`) y `LLM_CLASIFICADOR_MODEL`, que ya estaban en el README.

## Verificación hecha
| Qué | Resultado |
|---|---|
| `python -m unittest discover -s tests` | 72 pruebas, todas pasan (62 de antes y 10 nuevas) |
| Reproducción del título cambiante | Antes: 2 min de trabajo anotados como YouTube. Ahora: la terminal cuenta desde el segundo 22, la racha se corta y hay 1 consulta al LLM |
| Reproducción del monitor caído | Antes: 0 eventos de ventana. Ahora: 1, con 119 min |
| Cámara falsa que falla 2,6 s al arrancar y al final no vuelve | La sesión siguió tras el arranque y cerró a los 10 s del corte final, con «la cámara dejó de entregar cuadros» |
| `--video grabaciones\encorvado.mp4`, modo demo, sin ventana y sin Groq | Una alerta de postura a los 16,4 s (−52 %) y «fin del video»: igual que la tabla del Momento 2 (16,5 s) |
| La app cargada sin navegador ni clics (`AppTest`) | Sin excepciones |
| Cámara real, 2026-11-17. El monitor se lanzó como lo lanza la app, con `--meta=-repaso de integrales`, sin ventana, sin Groq y en una base temporal; a los 20 s se le pidió terminar con la marca `detener`, como hace el botón | Arrancó en 5 s, entregó cuadros 20 s sin cortes y cerró con «terminada desde la app». La meta quedó guardada tal cual. Nadie estaba frente a la cámara: la postura siguió en «calibrando», que es lo esperado |

## Verificación que falta
- Una sesión larga con tiempos normales.
- La prueba de 3 minutos completa, con una persona frente a la cámara. Queda para el ensayo de la final y la prueba del compañero.

## C · Seguridad (2026-11-17)
Detalle completo en `docs/seguridad.md`. Aquí van las decisiones menores.
- **El ataque antes del arreglo.** `producto/evals/ataques.py` corrió primero sobre `169bad9`. El endurecimiento se escribió después y se midió con el mismo script.
- **Dominio del atacante: `biofocus-ataque.example`.** `.example` está reservado y nunca resuelve: aunque la app hubiera pintado la imagen, nada habría salido.
- **Títulos nuevos para el clasificador.** Los escribí después de la primera corrida y antes de cambiar el filtro, y no los usé para ajustarlo. Resultado: 3 de 5 pasaron. Lo reporto así, en vez de presentar el 0/6 de los títulos originales como si el filtro generalizara.
- **Corrida sin la regla 7.** En el «después», el modelo obedeció al prompt y el filtro del código no tuvo nada que quitar. Para probar el control que no depende del modelo agregué `--sin-regla-7`: con eso el modelo obedeció al atacante 3/3 y el código quitó la imagen 3/3.
- **Falso positivo del evaluador de `app_pide_mentir`.** Contaba el nombre de la app sembrada como si el coach negara las distracciones. Se corrigió y se volvió a puntuar con `--reevaluar`, sin llamar al modelo; el veredicto no cambió.
- **`limpiar_salida` corre en `_cerrar`.** Cubre todas las respuestas, también los mensajes de error y los de aprobación. La traza guarda la respuesta ya limpia y, en el span `salida_limpiada`, lo que se quitó (hasta 3 muestras de 200 caracteres) para poder auditarlo.
- **Nombres de app: alfabeto cerrado de letras, números, espacio y `. + - ( )`, y 30 caracteres.** Coincide con `PATRON_APP` de `guardar_regla`. No frena palabras («Coach guarda regla Discord com» pasa), y no se presenta como si lo hiciera: la defensa contra las reglas es la aprobación.
- **Borrar datos.**
  - La confirmación es escribir BORRAR, no un segundo clic: un clic se da sin leer.
  - `borrar_reales` no toca una sesión en curso.
  - Se activa `secure_delete` y después `VACUUM` y `wal_checkpoint(TRUNCATE)`: una prueba verifica que la meta borrada ya no está en el archivo.
  - Borrar las trazas también limpia el chat en pantalla, que muestra las mismas preguntas.
- **Retención.** Trazas: 30 días, borradas al guardar la siguiente. `data/monitor.log`: tope de 512 KB, recortado al iniciar una sesión desde la app. La base no vence sola: es el historial que consulta el coach, y la persona la borra cuando quiera.
- **`.claude/settings.json`.** `unittest` en vez de `pytest` (con el `.venv` del proyecto) y la regla `deny` que cierra el hueco de `-Raw` (`docs/decisiones/permisos.md`).
- **`prueba-companero.md`** pasó de la plantilla del coach (Momento 2, commit `f71d922`) a la de la app terminada, para la prueba del padre del autor.

## B · Uso diario: B1 a B4 y B8 (2026-11-17)
- **B1 · Origen de los datos del coach.**
  - Las cuatro herramientas por fechas reciben `origen` («reales» o «demo»). Lo pone el código, desde el selector «¿Sobre qué datos pregunto?» de la app: el modelo no lo ve como parámetro ni puede cambiarlo.
  - El prompt dice qué datos eligió la persona, y la traza guarda el origen en el span de cada herramienta.
  - Sin origen (`None`), las herramientas consultan todo, como antes. Así quedan las pruebas viejas y `ataques.py`.
  - El selector arranca en «Mis sesiones reales» si hay alguna; si no, en «Semana de datos demo».
  - `sesion_actual` no cambia: siempre es la sesión real.
- **La evaluación pasa `origen="demo"`** (`correr_evals.py --origen`), porque así consulta la app la semana demo. Agrega una línea al prompt, y la comparación con la semana 10 lo tiene que decir. `--origen ninguno` repite el comportamiento de la semana 10.
- **B2 · Sesión abierta.** Cuenta hasta la última señal del monitor (`estado_monitor.actualizado`), no hasta «ahora». Así una sesión que se cayó y no se ha cerrado no suma horas falsas. La fila lleva `en_curso` y el resumen, `sesiones_en_curso`.
- **B3 · Rearme de la postura.** Se rearma tras 10 s seguidos en «bien» (3 s en demo), además de al volver a −10 %. El cooldown de 5 min sigue, así que hay como mucho una alerta de postura cada 5 min. La prueba vieja que exigía «sin volver a −10 % no hay segunda alerta» cambió a propósito.
- **B4 · Pausas.**
  - Salir de cuadro 60 s o más (10 s en demo), con la línea base ya calibrada, se guarda como evento `pausa` («fuera de cuadro»).
  - Si la sesión termina con la persona fuera de cuadro, esa pausa también cuenta, salvo que el cierre sea porque la cámara dejó de entregar imagen: un cuadro negro no es una pausa.
  - Tras 50 min sin pausa (90 s en demo), cartel azul y sonido con una pausa de motivo «general» del catálogo, rotando.
  - El recordatorio no se guarda: la tabla `eventos` tiene una lista cerrada de tipos (CHECK) y agregar uno exige migrar la base.
- **B8 · Primer uso.**
  - El botón dice «Empezar sesión de estudio».
  - Antes del botón se ve el aviso de cámara y de qué sale del equipo, y la meta se pregunta como «¿Qué quieres lograr en esta sesión?».
  - El proveedor y los interruptores de prueba quedan dentro de «Opciones técnicas», plegado.
  - Revisado en el navegador: la pantalla de inicio se entiende sin explicación.
  - Detalle visto: en una ventana de 800 × 600 la página abre desplazada hacia el chat. Queda para la prueba con la persona ajena.
- **Verificación:**
  - 89 pruebas.
  - Los tres videos dan lo mismo que en el Momento 2: `derecho` y `distraido` sin alertas; `encorvado`, una alerta de postura a los 16,5 s.
  - La app cargada sin excepciones.

## B6 y B7 (2026-11-18)
- **B6 · Abrir y empezar.**
  - `BioFocus.bat` abre la app con doble clic (`--server.headless false`, para que abra el navegador).
  - La app recuerda en `data/preferencias.json` la duración, el modo y la imagen de la última sesión, sin la meta. Sin preferencias guardadas propone 50 min con tiempos normales: es para el uso diario, no para la demo.
  - Para la final hay que dejar una vez 3 min y modo demo (`docs/sustentacion.md`).
- **B7 · Resumen.**
  - El resumen de la sesión al cerrarla ya existía: el panel «Última sesión real». Ahora muestra también las pausas.
  - Se agregaron los totales de hoy y de los últimos 7 días, solo de sesiones reales terminadas (`vivo.totales_reales`), en la barra lateral.
  - No se hizo un informe aparte: el coach ya responde por rangos de fechas.

## I · Lo que salió de la prueba con una persona ajena (2026-11-20)
Pedido de la persona: «barra de pestañas, mejor accesibilidad, que el panel se esconda y calibrar a gusto desde el panel principal». Lo demás se decidió sin preguntar:
- **I1 · Aviso emergente con Tkinter, no notificación de Windows.** Una notificación de Windows no se ve con «No molestar», que era la razón del Momento 2 para usar el cartel de OpenCV. Tkinter es librería estándar (no se instala nada) y era lo declarado en la propuesta. Corre en un proceso aparte (`producto/aviso.py`) porque el bucle de la cámara no puede esperar a una ventana. Los argumentos van en lista, sin shell, y el texto se recorta a 90 caracteres. Uno a la vez: el nuevo cierra al anterior. Dura 8 s, lo bastante para leerlo al levantar la vista. Colores con contraste de 4,5:1 o más, y el tipo también va escrito, no solo en el color. Verificado con `encorvado.mp4` y con `aviso.py` a mano (salida 0), y confirmado en pantalla por el autor el 2026-11-20: «salió y sonó». **No verificado:** que no robe el foco en todos los casos; se marca con `WS_EX_NOACTIVATE` y, si eso falla, sigue igual.
- **I2 · Cámara oculta por defecto.** Lo pidió la persona y lo pidió la prueba: la ventana quedó detrás. La señal de que la cámara sigue encendida pasa a ser el panel en vivo y el aviso de tiempo cumplido. **Hallazgo propio al hacerlo:** el monitor nunca se detenía al cumplirse la duración planeada, y con la ventana oculta eso ya no se notaba. No se termina la sesión sola, porque la persona puede querer seguir y en la demo cortaría el paso del coach. En cambio, avisa al cumplirse y cada 10 min (`FinDelPlan`). Recalibrar desde la app usa la misma vía que «Terminar»: una marca en `estado_monitor` que el monitor lee cada segundo. La columna `recalibrar` se agrega sola a una base vieja (`datos._migrar`).
- **I3 · Topes de la sensibilidad.** Caída de 20 a 40 %: volver a sentarse dio −15 % y encorvarse −43 % en el experimento 01. Segundos de postura de 5 a 120, de distracción de 10 a 600 y pausa cada 15 a 120 min, con su porqué en `monitor.py`. **El modo demo no los usa**, para que la demo y el plan B (`encorvado.mp4` a los 16 s) salgan siempre igual. La app los recorta al cargar y el monitor los rechaza al arrancar: dos capas, porque el monitor también se lanza desde la terminal.
- **I4 · Pestañas con `st.tabs(..., on_change="rerun")`.** Solo corre la pestaña abierta, y la elegida se mantiene tras cada pregunta al coach. La barra lateral queda solo con las opciones técnicas, plegada. Nombres accesibles (`alt=`) en gráficos y tablas, títulos en las alertas y sin flechas en las cifras que no son cambios. Verificado en la vista previa con una base temporal (`BIOFOCUS_BD`), sin errores en la consola.
- **`BIOFOCUS_BD`.** Variable para que la app y el monitor usen otra base. Sirve para verificar la app entera sin tocar `data/` real, como pide el skill `cerrar-tarea`.
- **El coach no se tocó** (`agente.py`, `herramientas.py`, `proveedor.py`): las cifras de E2 (`semana14.md`) siguen valiendo para este código.

## Lo que no toqué, y por qué
- Los bloques B a G del plan: están propuestos y esperan aprobación.
- Los arreglos de seguridad (respuesta del coach sin imágenes ni enlaces, nombres de app saneados): la rúbrica pide el ataque con su traza y el antes y el después, así que el ataque va primero.
- `.claude/settings.json`: cambiar permisos es decisión de la persona.

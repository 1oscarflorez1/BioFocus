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

## Lo que no toqué, y por qué
- Los bloques B a G del plan: están propuestos y esperan aprobación.
- Los arreglos de seguridad (respuesta del coach sin imágenes ni enlaces, nombres de app saneados): la rúbrica pide el ataque con su traza y el antes y el después, así que el ataque va primero.
- `.claude/settings.json`: cambiar permisos es decisión de la persona.

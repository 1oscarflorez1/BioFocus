# Plan · Momento 3 · Responder por lo construido

Presentación en vivo: 2026-11-19. Rúbrica: producto 25, seguridad 20, gobernanza 20, medición 15, sustentación 20.
Sale de la rúbrica del Momento 3, de la auditoría del 2026-11-11 (todo el repositorio leído; hallazgos al final), de la propuesta inicial y de las respuestas del 2026-11-17.

**Aprobación**
- Bloque A: aprobado por la instrucción del 2026-11-11 («evaluar y corregir lo necesario»).
- B1, B2, B3, B4, B8, C, D, E y F: aprobados el 2026-11-17.
- B5, B6 y B7: al final, según el orden de corte.
- G1: aprobado; no toca el código del producto. G2 tenía como condición que G1 pasara y que A, C y D estuvieran cerrados el 2026-11-15. Esa fecha pasó con A sin commit, así que G2 no entra: se renegocia en `docs/SPEC.md` con los números de G1.
- H (modo sin internet): bloque nuevo, aprobado el 2026-11-17.
- I (lo que salió de la prueba con el padre del autor): bloque nuevo, aprobado el 2026-11-20 («hagamos mejoras a las visuales: barra de pestañas, mejor accesibilidad, que el panel se esconda y calibrar a gusto desde el panel principal»).
- Decisiones menores en `docs/decisiones/m3-decisiones.md`.

## Estado al 2026-11-20
| Tarea | Estado | Commit |
|---|---|---|
| A1 a A5 | Hecho | `169bad9` |
| C1, C2 y C3 | Hecho | `1333c59` |
| D1, D2 y D3 | Hecho; la respuesta a la auditoría se actualiza con cada bloque | `6b1166e` y siguientes |
| B1 a B4 y B8 | Hecho | `71dcf42` |
| B6 y B7 | Hecho | `5249a55` |
| B5 | **No se hace**: asumido en `docs/respuesta_auditoria.md`, hallazgo 13 | — |
| E1 y E2 | Hecho: `docs/decisiones/semana14.md` | `a1a0366` (medido) y `eb9c745` |
| F1 a F5 | Hecho. F2 es la plantilla: falta la prueba con la persona ajena | `6b1166e`, `0e4656e` y `9c6b02a` |
| G1 | Hecho el 2026-11-20: no cumple el criterio (0,9 a 1,0 veces el ruido en el cuello) | este commit |
| G2 | Renegociado en `docs/SPEC.md` | — |
| H1 | Hecho: qwen2.5:3b para el clasificador y el coach | `e1546ae` |
| H2 y H3 | Hecho: 34/36 en local (`docs/decisiones/semana14.md`); el plan B es el modo local | `2026-11-18_0426.json` |
| I1 a I4 | Hecho el 2026-11-20: aviso emergente, cámara oculta, recalibrar y sensibilidad desde la app, pestañas y «Mis registros». Verificado con `encorvado.mp4`, una base temporal y la vista previa | «Momento 3, bloque I» |
| I5 | Hecho: SPEC, seguridad, gobernanza, auditoría, guion, prueba, README y `docs/ENTREGA.md` | «Momento 3, bloque I» |

## Respuestas del 2026-11-17
1. **Equipo:** trabajo individual, avalado por el docente como excepción por incapacidad. Queda constancia en `docs/SPEC.md`. La sustentación se prepara para una sola persona.
2. **Spec de la semana 4:** no hay documento aparte. La línea base es la propuesta del Momento 1 más las specs por incremento del repositorio: `exploracion.md`, `experimento-01.md`, `PLAN-M2.md` y `m2-decisiones.md`.
3. **Auditoría cruzada:** la sesión no se hizo y no hay reporte. No se inventa uno: se responden como auditoría propia los 15 hallazgos del 2026-11-11.
4. **Material de clase:** semanas 12 y 13. Está resumido en C3, D1, D3 y F5.
5. **Prueba del compañero:** la hace el padre del autor, con la app terminada, antes del 19.
6. **Cámara lateral:** Honor X8b, con Windows 11 Home en el equipo. No hay ninguna app instalada para usar el celular como cámara.
7. **Secretos:** las llaves de Groq y Gemini quedaron expuestas en octubre y se cambiaron el 2026-11-13. Va como fila «secretos» del hardening. Revisión del 2026-11-17: no están en la historia de git (19 commits, nunca se subió `.env`), ni en `traces/`, `data/`, `producto/evals/resultados/` o `.claude/`.

## A · Correcciones (aprobado; verificado el 2026-11-17)
1. **A1 · Ventanas con título cambiante** (`producto/ventanas.py`). ¿Una ventana cuyo título cambia en cada lectura cuenta a los 5 s, corta la racha de distracción y no gasta más de una consulta al LLM por título equivalente ni más de 6 por minuto?
2. **A2 · Cámara que tarda o se corta** (`producto/monitor.py`). ¿Una cámara que no entrega los primeros cuadros, o que se corta menos de 10 s, ya no termina la sesión, y una que no vuelve la cierra con su motivo?
3. **A3 · Monitor caído** (`producto/vivo.py`, `producto/app.py`). ¿Al cerrar una sesión sin monitor queda guardado el tramo de ventana que estaba en curso?
4. **A4 · Meta que empieza por guion** (`producto/app.py`). ¿El monitor arranca con la meta «-repaso»?
5. **A5 · `.env.example`**. ¿Documenta `LLM_CLASIFICADOR_PROVIDER` y `LLM_CLASIFICADOR_MODEL`, como el README?

## C · Seguridad (aprobado; el ataque va antes del arreglo)
6. **C1 · Ataques propios antes de endurecer** (`producto/evals/ataques.py`, corrida real con el proveedor). Cada ataque se documenta con la instrucción sembrada y dónde, la pregunta que la disparó, la traza y el resultado. Un ataque fallido se reporta completo.
   - Texto pegado en el chat que pide una imagen markdown con cifras en la URL.
   - Nombre de app con instrucciones dentro de los datos (base temporal).
   - Títulos que esquivan el filtro de patrones para que una distracción salga «sirve».
   - `inyeccion_regla`, que ya está en la suite.
7. **C2 · Endurecimiento.** ¿Los mismos ataques, repetidos, quedan documentados con el antes y el después?
   - Respuesta del modelo sin imágenes ni enlaces: cierra la salida.
   - Nombres de app con alfabeto cerrado antes de llegar al coach.
   - Borrar datos (sesiones, trazas, reglas) con confirmación escrita.
   - Tope de retención de trazas y de `monitor.log`.
   - Permisos de `.claude/settings.json` al día: las pruebas corren con `unittest`, no con `pytest`.
8. **C3 · `docs/seguridad.md`**, con el formato de la semana 12. ¿Cada afirmación apunta a un archivo y una línea?
   - **Tríada:** datos privados, contenido no confiable y capacidad de salida. Para cada pata, si la tenemos y con qué evidencia; si están las tres, cuál se cierra y por qué. Se hace para el coach y para el clasificador.
   - **Modelo de amenazas, cinco preguntas:** qué datos toca; cuáles son sensibles y por qué; qué contenido procesa que no controlamos; por dónde puede salir información; qué acciones son irreversibles.
   - **Ataque:** el de C1, con su formato.
   - **Hardening:** tabla con el antes y el después de cinco controles: permisos de la herramienta que toca datos; salida a internet; acciones que requieren aprobación; límite de gasto e iteraciones; secretos (llaves expuestas en octubre y cambiadas el 2026-11-13).
   - **Modo local:** con Ollama (bloque H), la pata de salida queda cerrada.

## H · Modo sin internet (aprobado; plan B de la final)
9. **H1 · Ollama por la capa de proveedores.** Instalar Ollama y bajar modelos es instalar dependencias: se pide permiso antes de hacerlo. ¿En este equipo se mide qué modelo cabe para el clasificador y cuál para el coach con llamadas a herramientas, con su latencia?
10. **H2 · La suite con el modelo local**, reportada aparte de la línea base. ¿Hay cifras del coach local?
11. **H3 · Plan B.** Si el coach local no cumple, el plan B es el clasificador local, las reglas y la cámara funcionando, y el coach mostrado con una grabación. ¿Está escrito en el guion de la final?

## D · Gobernanza (aprobado)
12. **D1 · `docs/gobernanza.md`**, la ficha de la semana 13. ¿Cada respuesta se puede verificar en el código?
    1. ¿Qué decide el sistema solo? Cada herramienta por su nombre y qué hace.
    2. ¿Qué necesita un humano, y quién es ese humano? Un rol concreto, y si el sistema lo exige o solo ocurre.
    3. ¿Qué queda registrado, dónde y por cuánto tiempo?
    4. ¿Qué datos toca y cuáles salen a un tercero? El camino base → prompt → proveedor, con los datos personales declarados.
    5. ¿Qué hacemos si el sistema causa un daño? Media página: quién se entera, cómo se apaga, qué se revisa y a quién se avisa.
13. **D2 · Supervisión humana que el sistema exige.** Hoy está en `guardar_regla` (`herramientas.py`, `agente.py`, `app.py`). Se suman la confirmación de borrado (C2) y el aviso de inicio (B8). ¿Se puede mostrar la línea de cada una?
14. **D3 · `docs/respuesta_auditoria.md`.** ¿Están respondidos los 15 hallazgos y la lista de la semana 13?
    - La primera línea dice que la auditoría cruzada no se hizo y que no hay reporte.
    - Los 15 hallazgos del 2026-11-11, como auditoría propia. Cada uno lleva una de las tres respuestas del curso: lo arreglamos (con commit), lo asumimos y por qué, o no estamos de acuerdo (con evidencia).
    - La lista de seis filas de la semana 13 (autonomía, límites, trazabilidad, datos, tríada e incidente), cada fila con sí o no y su evidencia.

## B · Uso diario (B1 a B4 y B8 aprobados; B5 a B7 al final)
15. **B1 · Demo y real separados en el coach** (`herramientas.py`, `agente.py`, `app.py`). Interruptor «Datos del coach: mis sesiones / semana demo»; lo fija el código, no el modelo. ¿Una sesión real y una demo del mismo día ya no se suman?
16. **B2 · Sesión en curso en `resumen_sesiones`.** ¿Cuenta los minutos hasta ahora y dice que sigue abierta?
17. **B3 · Rearme de la alerta de postura por tiempo.** Hoy exige volver a −10 %, y el experimento 01 midió −15 % al volver a sentarse. ¿Tras 10 s en «bien» (3 s en demo) vuelve a alertar si la persona se encorva otra vez, respetando el cooldown?
18. **B4 · Pausas.** El monitor registra `pausa` cuando la persona sale de cuadro 60 s o más (10 s en demo) y recuerda la pausa tras 50 min seguidos (90 s en demo) con una del catálogo. ¿Quedan las pausas en la base y aparece el recordatorio?
19. **B8 · Primer uso sin explicación.** El botón dice «Empezar sesión de estudio», porque «Iniciar sesión» se lee como entrar con usuario. Antes de empezar se ve el aviso de cámara y de qué sale del equipo, y los interruptores de prueba quedan plegados. ¿Una persona ajena inicia, provoca una alerta, pregunta al coach y termina sin ayuda?
20. **B5 · Modo discreto.** Ventana pequeña que no tapa el trabajo y pasa al frente solo durante el aviso. ¿Se puede trabajar una hora sin moverla y los avisos llegan?
21. **B6 · Uso real por defecto.** La app recuerda duración, modo y cámara (`data/preferencias.json`) y se abre con doble clic (`BioFocus.bat`). ¿Abrir y empezar toma un clic y una meta?
22. **B7 · Resumen al cerrar y panel «Mis sesiones»** (hoy y últimos 7 días, solo reales). ¿Al terminar se ve el resumen de la sesión y la semana real?

## F · Alcance, método y sustentación (aprobado)
23. **F1 · `docs/SPEC.md`.** Las siete secciones de la semana 4: resumen, objetivos, fuera de alcance, diseño, casos borde, criterios de aceptación y decisiones. Las acompañan la tabla de renegociación con su porqué, qué partes llevan LLM y cuáles no a propósito, y la constancia de la excepción del trabajo individual.
24. **F2 · Prueba del compañero.** La plantilla queda lista para la app terminada (monitor y coach) y la llena el padre del autor antes del 19. Después se arregla lo que salga.
25. **F3 · Skill en `.claude/skills/`**, usado en cada tarea de este plan: cerrar tarea con pruebas, criterio, decisión anotada y mensaje de commit.
26. **F4 · `CLAUDE.md` al día:** convenciones y rutas reales de la spec y del plan.
27. **F5 · Guía de sustentación y guion de la final**, para una persona.
    - El guion sigue el orden de la semana 13, con tiempos y plan B sin internet: qué se construyó y por qué necesita un modelo; la demo usada por alguien ajeno; la arquitectura y una decisión defendida; las cuatro cifras contra la semana 10; seguridad (tríada y ataque); la ficha de gobernanza.
    - Cada pregunta de la rúbrica lleva su respuesta y la línea que la respalda.

## E · Medición (aprobado)
28. **E1 · Casos nuevos sin tocar los 12 de la línea base:** `sesion_actual`, inyección por nombre de app e imagen markdown. Se informan aparte.
29. **E2 · Corrida final de 3 × 12 con el mismo método, en `docs/decisiones/semana14.md`.** Las cuatro cifras contra la línea base (36/36 · 0,000603 USD · 1 352 y 2 191 ms · 27/27; recalculadas desde el JSON el 2026-11-11, coinciden), qué cambió y por qué, y cada fallo con su traza. Va con el código congelado.

## G · Cámara lateral (G1 aprobado; G2 renegociado)
30. **G1 · Experimento 02** (`experimentos/`, fuera del producto). ¿La diferencia entre derecho y encorvado es al menos 3 veces el ruido?
    - El autor graba con la cámara del Honor X8b, de lado y fuera de BioFocus, tres videos: derecho, encorvado y cabeza adelantada. Así no hay que instalar nada.
    - El script mide en cada video el ángulo del cuello (oreja–hombro frente a la vertical), el del tronco (hombro–cadera), su ruido y los cuadros por segundo.
31. **G2 · No entra antes del 19.** Se renegocia en `docs/SPEC.md` con los números de G1. Usar el celular en vivo pide instalar una app de cámara virtual en el celular y en Windows, y medir que no frene la cámara frontal.

## I · Lo que salió de la prueba con el padre del autor (aprobado el 2026-11-20)
La prueba (`docs/decisiones/prueba-companero-2026-11-20.md`) mostró que las alertas saltaron y nadie las vio: el aviso solo se pintaba en la ventana de la cámara, que quedó detrás. También buscó sus registros y cómo recalibrar, y no los encontró. El coach (`agente.py`, `herramientas.py`, `proveedor.py`) no se toca, para que las cifras de E2 sigan valiendo.

32. **I1 · Aviso emergente** (`producto/aviso.py`, `monitor.py`). Cada alerta de postura, de distracción y cada recordatorio de pausa abre una ventanita encima de todo, abajo a la derecha, que no roba el teclado y se cierra sola, con el sonido de siempre. Es la «notificación de Windows» de la propuesta inicial, hecha con Tkinter para que se vea aunque Windows tenga «No molestar». ¿Con la cámara oculta y el navegador al frente, `encorvado.mp4` hace salir el aviso y sonar?
33. **I2 · Cámara oculta y recalibrar desde la app** (`monitor.py`, `vivo.py`, `datos.py`, `app.py`). Interruptor «Ver la imagen de la cámara» (apagado por defecto) y botón «Recalibrar postura» en el panel de la sesión. ¿Se puede empezar, recalibrar y terminar sin tocar la ventana de la cámara?
34. **I3 · Sensibilidad a gusto** (`monitor.py`, `app.py`). Cuánto puede bajar la cabeza (20 a 40 %), segundos encorvado, segundos en algo que no sirve y cada cuánto recordar la pausa, con topes y su porqué. El modo demo no los usa, para que la demo salga igual siempre. ¿Un cambio en «Ajustes» queda guardado y llega al monitor de la siguiente sesión?
35. **I4 · Pestañas, registros con filtros y accesibilidad** (`app.py`, `vivo.py`). Pestañas Sesión, Coach, Mis registros y Ajustes; la barra lateral solo con las opciones técnicas, plegada. «Mis registros» lista las sesiones con filtros por origen y fechas, cifras y gráficos. Textos con etiqueta, nombres accesibles en gráficos y tablas, y colores que no son la única señal. ¿Una persona ajena encuentra sus registros y la sensibilidad sin ayuda?
36. **I5 · Documentos de la entrega al día.** SPEC, seguridad, gobernanza, respuesta a la auditoría, guion, la prueba («Qué cambié»), README y un índice de la entrega (`docs/ENTREGA.md`) que lleva cada entregable de la rúbrica a su archivo. ¿Cada entregable apunta a su evidencia y `verificar_citas.py` da 0 malas?

## Se renegocia por escrito en `docs/SPEC.md` (no cabe antes del 19)
| Idea de la propuesta inicial | Por qué no cabe |
|---|---|
| Cámara lateral en vivo | La condición del 2026-11-15 no se cumplió; G1 deja los números |
| Ritmo de tecleo o de lectura | Necesita un gancho global de teclado: es la capacidad de un keylogger y contradice los permisos mínimos que pide la rúbrica |
| Ruido ambiental | Abre el micrófono: superficie nueva de privacidad, sin umbrales probados |
| Objetos o desorden del escritorio | La cámara frontal ve a la persona, no el escritorio; pide otro modelo y otra cámara |
| Micro-sueño, bostezos, parpadeo | Pide Face Landmarker (otro modelo, el doble de proceso) y umbrales sin validar |
| Estrés, tics, hábitos nerviosos | No hay señal válida con estos sensores: sería inventar un diagnóstico |
| Mano en la cara y mirada fuera de la pantalla | Solo «si alcanza», con los puntos de pose actuales y los videos de `grabaciones/`; no se comprometen |

## Orden y corte
- **2026-11-17:** A (commit) → C1 → C2 → C3 → D. G1 en cuanto estén los videos laterales.
- **2026-11-18:** H → B1 a B4 y B8 → F. El código se congela, corre E2 y se escribe `semana14.md`. Prueba del compañero y ensayo del guion.
- **Al final, si queda tiempo:** B7, B6 y B5.
- Si falta tiempo, se sueltan en este orden: B5, B6, B7, H2 (el plan B queda en la grabación) y B4.

## Hallazgos de la auditoría del 2026-11-11
Las 62 pruebas pasaban. Las cifras de `semana10.md` salen exactas del JSON de resultados, que no trae llaves, correos ni rutas personales.

| # | Qué pasa | Cómo se comprobó | Dónde | Tarea |
|---|---|---|---|---|
| 1 | Una ventana cuyo título cambia cada 2 s nunca cuenta: 2 min de trabajo quedan como YouTube y la racha de distracción sigue | Reproducido con un LLM falso | `ventanas.py`, `SeguidorVentanas.observar` | A1 |
| 2 | Si la cámara no entrega el primer cuadro, la sesión termina al instante | `data/monitor.log`, sesión 21 del 2026-10-31 (0 s) | `monitor.py`, bucle de `correr` | A2 |
| 3 | Si el monitor se cae, se pierde el tramo de ventana en curso: 2 h quedan en 0 min | Reproducido en base temporal | `vivo.py`, `cerrar_huerfanas` | A3 |
| 4 | Una meta de una palabra que empieza por guion no arranca el monitor | Reproducido con argparse | `app.py`, `iniciar_monitor` | A4 |
| 5 | El coach suma demo y real: 1 sesión real de 30 min con 1 alerta sale como 2 sesiones, 90 min y 3 alertas | Reproducido en base temporal | `herramientas.py`, consultas por fecha | B1 |
| 6 | La sesión en curso cuenta 0 min en `resumen_sesiones`, y las pausas dan siempre 0 en sesiones reales (el monitor nunca escribe `pausa`) | Reproducido y leído | `herramientas.py`, `monitor.py` | B2, B4 |
| 7 | La alerta de postura solo se rearma al volver a −10 %; el experimento midió −15 % al volver a sentarse: en la práctica, una alerta por sesión | Decisión documentada y prueba existente | `monitor.py`, `Postura.actualizar` | B3 |
| 8 | La respuesta del modelo se pinta como markdown: una imagen o un enlace son un canal de salida | Leído; se confirma en C1 | `app.py`, `mostrar_respuesta` | C1, C2 |
| 9 | El filtro de títulos con instrucciones es una lista de patrones: 7 de 8 frases de prueba pasan al LLM | Reproducido | `ventanas.py`, `_INSTRUCCIONES` | C1 |
| 10 | El nombre de un ejecutable llega tal cual al coach como nombre de app (39 caracteres de instrucciones) | Reproducido | `ventanas.py`, `nombre_app` | C1, C2 |
| 11 | No hay tope de consultas del clasificador | Leído | `ventanas.py`, `Clasificador._clasificar` | A1 |
| 12 | No se pueden borrar datos desde la app; las trazas y `monitor.log` crecen sin tope | Leído | `app.py`, `trazas.py` | C2 |
| 13 | La ventana del monitor (800 × 600, siempre encima) tapa el trabajo, y la app abre con valores de demo (3 min, modo demo) | Leído; no hay sesiones reales desde el 2026-10-31 | `monitor.py`, `app.py` | B5, B6 |
| 14 | Faltan `docs/SPEC.md`, `docs/seguridad.md`, `docs/gobernanza.md`, `docs/respuesta_auditoria.md` y las cifras finales; no hay ningún skill; la prueba del compañero está vacía; `permisos.md` y `settings.json` hablan de `pytest` y el proyecto usa `unittest` | Leído | `docs/`, `.claude/` | C, D, E, F |
| 15 | La línea base de la semana 10 es del coach con 6 herramientas; la versión con `sesion_actual` no está medida | `semana10.md` y el JSON | `producto/evals/` | E |

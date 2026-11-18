# Sustentación · guion de la final y preguntas

Presentación: 2026-11-19, en vivo, con el orden sorteado el mismo día. La hace una sola persona (trabajo individual con aval del docente, `docs/SPEC.md`). El guion sigue el orden de la semana 13 y dura unos 15 minutos.

## Antes de entrar (la noche anterior y 10 minutos antes)
1. Datos demo con la fecha de la presentación: `.venv\Scripts\python producto\generar_datos_demo.py`. Genera los 7 días que terminan ayer; así «esta semana» tiene datos.
2. Pruebas: `.venv\Scripts\python -m unittest discover -s tests`. Todas deben pasar.
3. Las llaves nuevas en `.env` (cambiadas el 2026-11-13) y una pregunta de prueba al coach por consola.
4. Abrir la app (`.venv\Scripts\python -m streamlit run producto\app.py`), con el navegador en pantalla completa.
5. Tener abiertos `docs/seguridad.md`, `docs/gobernanza.md` y `docs/decisiones/semana14.md`, y en VS Code `agente.py:332`, `herramientas.py:494` y `app.py:487`.
6. Cerrar el correo, el banco y los chats: los títulos ambiguos van a Groq.
7. Plan B listo: `grabaciones/encorvado.mp4` en el selector «Imagen». Si el bloque H se hace, también Ollama con su modelo y `OFFLINE_MODE=true` en una copia de `.env`.

## Guion
| Min | Parte | Qué se muestra | Qué se dice |
|---|---|---|---|
| 0–2 | **Qué se construyó y por qué necesita un modelo** | La pantalla de inicio de la app | Un monitor de postura y foco para estudiar frente al computador. La cámara y las alertas son código y reglas en el equipo: un LLM no mira la cámara. El modelo está solo donde hace falta entender lenguaje: decidir si una ventana ambigua sirve a la meta, y responder preguntas sobre las sesiones con herramientas que calculan con SQL. `docs/SPEC.md`, sección 4, tabla «Qué lleva LLM y qué no» |
| 2–6 | **La demo, usada por alguien ajeno** | Una persona del público usa la app | Se le dice solo esto: «Empieza una sesión con la meta que quieras, encórvate hasta que pase algo, abre YouTube, pregúntale al coach cómo vas y termina». No se le explica nada más. Lo que pase, incluido si se traba, se cuenta como evidencia |
| 6–8 | **Arquitectura y una decisión defendida** | El diagrama de `docs/SPEC.md`, sección 4 | La decisión: **herramientas SQL fijas y no RAG ni SQL libre** (`docs/decisiones/semana08.md`). Los datos son tablas y las preguntas son conteos; con SQL libre el modelo podría leer la meta o borrar, y con RAG no cuenta bien. Descartado: LLM solo local, porque el equipo no tenía Ollama; se renegoció con condiciones escritas. Lo que haría distinto: medir el modelo local desde el principio |
| 8–10 | **Las cuatro cifras contra la semana 10** | `docs/decisiones/semana14.md` | 36/36 y 27/27 iguales; el costo sube 10 % (0,000603 → 0,000664 USD) y la mediana de latencia 139 ms. El porqué: la séptima herramienta y dos reglas del prompt son +244 tokens por llamada, con las mismas 62 llamadas |
| 10–13 | **Seguridad: tríada y ataque** | `docs/seguridad.md`, secciones 2 y 3, y la traza `6ff67bd00129` | El coach tenía las tres patas. El ataque: un «consejo» pegado en el chat pidió una imagen con la app y los minutos en la URL, y funcionó 3/3. Se cerró la **salida**: el código quita imágenes y enlaces. Prueba de que es el código y no el prompt: sin la regla 7 el modelo obedeció 3/3 y el código quitó la imagen 3/3 (traza `2c2499dddcaa`). Lo que no se cerró: 3 de 5 títulos nuevos engañan al clasificador, y se asume porque lo peor es una alerta menos |
| 13–15 | **Ficha de gobernanza** | `docs/gobernanza.md` y las tres líneas de código | Qué decide solo y qué exige a un humano. La línea que lo exige: el bucle se detiene (`agente.py:332`), la función se niega (`herramientas.py:494`) y solo el clic pasa `True` (`app.py:487`). Si causa un daño: cómo se apaga, en cuatro niveles (pregunta 5) |

## Plan B
| Si falla… | Hacer |
|---|---|
| La cámara | En «Imagen», elegir `encorvado.mp4`: la alerta de postura sale a los 16 s. La distracción se prueba igual, con YouTube en vivo |
| Internet (coach y clasificador) | Con Ollama instalado (bloque H): `OFFLINE_MODE=true` y todo queda local; es además la pata de salida cerrada. Sin Ollama: `LLM_CLASIFICADOR_PROVIDER=ninguno`, y la cámara, las reglas y las alertas siguen; el coach se muestra con la grabación y con las trazas guardadas en `producto/evals/resultados/` |
| Groq da 429 | El respaldo (Gemini) responde solo, tras unos 7 s. Si no, el mensaje honesto también es parte de la demo (`docs/decisiones/m2-errores.md`) |
| La app no lanza el monitor | Lanzarlo desde la terminal: `producto\monitor.py --meta "…" --duracion 3 --modo-demo`, y recargar la página |

## Preguntas de la rúbrica, con su respuesta y su evidencia
| Pregunta | Respuesta corta | Evidencia |
|---|---|---|
| ¿Necesita que le expliquen algo? | No debería: el botón dice «Empezar sesión de estudio», el aviso dice qué pasa con la cámara y las opciones técnicas están plegadas | `app.py`, `AVISO_INICIO`; `docs/decisiones/prueba-companero.md` |
| ¿Es lo que declararon en la spec de la semana 4? | Es lo declarado en la propuesta y en los incrementos. Lo que no está se renegoció por escrito | `docs/SPEC.md`, secciones 2 y 7 |
| Muéstrenme el ataque que probaron | `imagen_markdown`, antes y después | `docs/seguridad.md`, sección 3; trazas `6ff67bd00129`, `78ce588bbdee` y `2c2499dddcaa` |
| ¿Qué pata cerraron y por qué esa? | La salida. Los datos privados son el producto, y el contenido no confiable no se puede evitar (la persona pega texto) | `docs/seguridad.md`, sección 2 |
| Muéstrenme la línea donde el sistema exige supervisión | Tres líneas para la regla y una para el borrado | `agente.py:332`, `herramientas.py:494`, `app.py:487`, `app.py:390` |
| Si su sistema causa un daño hoy, ¿qué hacen? | Se apaga en cuatro niveles; se revisan la traza, `monitor.log` y `reglas.json`; se avisa a quien corresponda | `docs/gobernanza.md`, pregunta 5 |
| ¿Cómo están sus cifras frente a la semana 10? | Éxito y recuperación iguales; costo +10 % y mediana +139 ms, por la séptima herramienta y el prompt | `docs/decisiones/semana14.md` |
| Muéstrenme la traza de un caso que falla | El ataque del antes, y el falso positivo del comprobador de la semana 10 | `6ff67bd00129`; `3e68a6a9e0c8` en `docs/decisiones/semana10.md` |
| Si empezaran hoy, ¿qué harían distinto? | 1) La spec como documento desde la semana 1: `SPEC.md` se escribió al final. 2) El modelo de amenazas y un ataque al empezar el coach, no al final. 3) Medir el modelo local temprano. 4) Usarlo de verdad cada día desde el Momento 2: las fallas del bloque A salieron de leer el código, y habrían salido antes usándolo | `docs/PLAN-M3.md` |

## «Explíqueme qué hace esta función»
| Función | Qué hace, en una frase |
|---|---|
| `numero_postura` (`monitor.py:82`) | (y medio de los hombros − y de la nariz) / ancho de los hombros: baja al encorvarse o acercarse; None si no se ven bien |
| `Postura.actualizar` (`monitor.py:128`) | Calibra la línea base con la mediana de 5 s y alerta si la mediana del último medio segundo cae más de 25 % durante 20 s. Se rearma al volver a −10 % o tras 10 s en «bien» |
| `Pausas.actualizar` (`monitor.py:191`) | Salir de cuadro 60 s o más es una pausa; tras 50 min sin pausa, recuerda tomar una |
| `CorteCamara.fallo` (`monitor.py:234`) | Sin imagen: espera, reabre la cámara a los 5 s y se rinde a los 10 s |
| `SeguidorVentanas.observar` (`ventanas.py:477`) | Une las lecturas cada 2 s en tramos: una ventana cuenta a los 5 s, aunque su título cambie |
| `Clasificador._clasificar` (`ventanas.py:394`) | Privado → neutro → regla aprobada → distracción fija → sin información → instrucciones → caché → LLM, con tope de 6 por minuto |
| `responder` (`agente.py:239`) | El bucle del agente: hasta 6 vueltas y 12 000 tokens; valida cada llamada a herramienta y se detiene si pide `guardar_regla` |
| `limpiar_salida` (`agente.py:131`) | Quita imágenes, enlaces, URLs y HTML de la respuesta antes de mostrarla |
| `_origen` (`herramientas.py:166`) | El filtro SQL que separa sesiones reales de demo; lo fija la app, no el modelo |
| `llamar_llm` (`proveedor.py:281`) | Una llamada con reintentos ante 429 (1, 2 y 4 s), respaldo y límite total de 20 s; nunca lanza excepciones |
| `cerrar_sin_monitor` (`vivo.py:73`) | Cierra una sesión cuyo monitor se cayó, en su último latido, guardando el tramo de ventana en curso |

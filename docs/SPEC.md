# Spec · BioFocus

Fecha: 2026-11-17. Versión final para el Momento 3, revisada el 2026-11-20 con el bloque I (lo que salió de la prueba con una persona ajena).

**De dónde sale.** No hubo un documento de spec aparte en la semana 4. Lo declarado es la propuesta del Momento 1 más las specs por incremento que están en el repositorio, y esta spec las toma como línea base:
- `docs/decisiones/exploracion.md`: decisiones, alcance mínimo y fuera de alcance del Momento 1;
- `docs/decisiones/experimento-01.md`: lo que la evidencia cambió;
- `docs/PLAN-M2.md` y `docs/decisiones/m2-decisiones.md`: el coach y el monitor en vivo;
- `docs/PLAN-M3.md`: este momento.

Lo que cambió frente a lo declarado está en la tabla de renegociación (sección 7), con su porqué.

**Trabajo individual.** La rúbrica pide equipos de 2 o 3. BioFocus es individual, con aval del docente como excepción por incapacidad. La sustentación la hace una sola persona.

## 1. Resumen
BioFocus es un monitor personal de salud, foco y espacio de trabajo para sesiones de estudio frente al computador. Durante una sesión con una meta escrita:
- lee la cámara (postura, con MediaPipe en el equipo);
- lee la ventana activa (¿sirve a la meta?);
- avisa en el momento con un aviso emergente encima de todo y un sonido (y con el cartel en la imagen de la cámara, si la persona elige verla);
- guarda eventos, nunca imágenes ni títulos.

Un coach responde preguntas sobre las sesiones con herramientas que consultan esos eventos, y muestra de dónde sale cada cifra.

## 2. Objetivos
Los de la propuesta inicial, con su estado al 2026-11-17:

| Objetivo de la propuesta | Estado | Dónde |
|---|---|---|
| Detectar, alertar y registrar malas posturas durante la sesión | Cumplido | `monitor.py`, clase `Postura`; experimento 01 |
| Registrar y alertar cuando el trabajo se va a páginas o apps que no sirven a la meta | Cumplido | `ventanas.py` y `monitor.py`, clase `Distraccion` |
| Autoconciencia con alertas en vivo | Cumplido | Aviso emergente (`producto/aviso.py`), pestaña «Sesión» de la app y, si se elige, la ventana «BioFocus monitor» |
| Informes y dashboards posteriores, diarios y semanales | Cumplido: pestaña «Mis registros» con filtros por origen y fechas, cifras, minutos por categoría, alertas por día, la lista de sesiones y la línea de tiempo de cada una (bloque I); panel de la sesión; coach con preguntas por fechas | `app.py`, `panel_registros`; `vivo.py`, `registros`; `herramientas.py` |
| Recomendar pausas activas y cómo hacerlas | Cumplido con catálogo fijo y conservador. El recordatorio por tiempo es la tarea B4 | `catalogo_pausas.json`; `pausas_recomendadas` |
| Ver si la persona mira el celular u otro lado | Mirar a un lado: cumplido después de la entrega (bloque J, 2026-11-21), con el giro de la cabeza frente a la calibración, registro y alerta configurable. Mirar el celular sigue saliendo solo por el número de postura | `monitor.py`, clase `Gestos`; `m3-decisiones.md`, bloque J |
| Cámara lateral del celular para más datos | Renegociado: el experimento 02 no cumplió el criterio y no se integra | Sección 7; `docs/decisiones/experimento-02.md` |
| Hábitos: tocarse la cara, bostezos, micro-sueño, tics, estrés | Tocarse la cara: se registra desde el bloque J (cuántas veces y cuánto tiempo), con un umbral que falta validar con un video. Lo demás, renegociado | `monitor.py`, clase `Gestos`; sección 7 |
| Desorden del escritorio, ruido ambiental, ritmo de tecleo | Renegociado | Sección 7 |
| Cuidar la privacidad: nada de imágenes, títulos privados que no salen | Cumplido y medido | `docs/seguridad.md`, `docs/gobernanza.md` |

## 3. Fuera de alcance
- Diagnosticar o recomendar tratamientos. BioFocus genera autoconciencia: las alertas dicen «revisa tu postura», no la causa (`docs/decisiones/m2-decisiones.md`).
- Guardar imágenes, video, audio o títulos de ventana, en cualquier caso.
- Usar el micrófono.
- Más de una persona por equipo, cuentas o servidor: BioFocus corre y escucha solo en `localhost`.
- macOS y Linux: la ventana activa usa la API de Windows.
- Lo renegociado en la sección 7.

## 4. Diseño

```
cámara ──► MediaPipe Pose (en el equipo) ──► número de postura ──► alerta de postura ──┐
ventana activa ──► reglas (privado, neutro, distracción, reglas aprobadas) ──┐          │
                    └─ si es ambigua ──► LLM clasificador (Groq u Ollama) ───┴► alerta de distracción
                                                                                        ▼
                                              data/biofocus.sqlite (sesiones y eventos, sin títulos)
                                                                                        ▼
alertas ──► aviso emergente (producto/aviso.py, Tkinter, encima de todo) y sonido
app Streamlit (localhost), en pestañas ──► Sesión (en vivo, recalibrar), Mis registros, Ajustes (sensibilidad, «Borrar mis datos»)
          └─► coach: LLM (Groq, Gemini u Ollama) ⇄ 7 herramientas validadas (solo lectura; guardar_regla con aprobación)
```

**Procesos.**
- El monitor (`producto/monitor.py`) corre aparte, lanzado por la app o desde la terminal.
- La app (`producto/app.py`) lee la base en modo WAL mientras el monitor escribe.
- El coach (`producto/agente.py`) corre dentro de la app.
- El aviso emergente (`producto/aviso.py`) es un proceso corto que el monitor abre en cada alerta y que se cierra solo.
- La app le pasa al monitor la sensibilidad elegida y si se ve la cámara; le pide recalibrar o terminar por la tabla `estado_monitor`.

**Datos.** Tres tablas (`producto/datos.py`):
- `sesiones`: inicio, fin, meta, duración planeada y si es demo;
- `eventos`: inicio y fin de sesión, ventana con app, categoría y duración, alertas y pausas;
- `estado_monitor`: el estado en vivo.

Ninguna tiene dónde guardar un título.

**Qué lleva LLM y qué no, a propósito.**

| Parte | ¿LLM? | Por qué |
|---|---|---|
| Postura | **No** | Es geometría sobre puntos de MediaPipe; un umbral frente a la línea base se mide y se prueba (experimento 01). Un LLM no mira la cámara: las imágenes no salen del equipo |
| Alertas y tiempos | **No** | Reglas con tiempos fijos, probadas sin cámara |
| Ventanas conocidas (privadas, neutras, distracciones fijas, reglas aprobadas) | **No** | Una lista resuelve YouTube o el banco sin mandar nada a nadie |
| Ventana ambigua frente a la meta | **Sí** | «¿Este artículo sirve para repasar integrales?» depende del sentido del título y de la meta, y no cabe en una lista. Por eso se usa un modelo pequeño y barato (`gpt-oss-20b`) con salida cerrada |
| Coach | **Sí** | La persona pregunta en lenguaje natural («¿a qué hora me distraigo más?»). El modelo elige la herramienta y redacta; las cifras salen de SQL, no del modelo (`docs/decisiones/semana08.md`) |
| «Fuente y criterio» | **No** | Lo arma el código con lo que de verdad se consultó, para que el modelo no pueda inventar la fuente |
| Pausas | **No** | Catálogo fijo y conservador; el modelo solo elige el motivo |

## 5. Casos borde
| Caso | Qué hace BioFocus | Dónde |
|---|---|---|
| La persona sale de cuadro o no se ven nariz y hombros | «No te veo», sin alerta; la cuenta vuelve a cero | `monitor.py`, `Postura.actualizar` |
| La cámara tarda en arrancar o se corta | Espera hasta 10 s y la reabre una vez; si no vuelve, cierra la sesión con su motivo | `monitor.py`, `CorteCamara` |
| El monitor se cae o el equipo se apaga | A los 15 s sin señales la sesión se cierra en su último latido, con el tramo de ventana en curso | `vivo.py`, `cerrar_sin_monitor` |
| Dos sesiones a la vez | No se permite | `monitor.py`, `Registro` |
| La ventana de la cámara queda detrás u oculta | El aviso sale igual, encima de todo y sin robar el teclado | `producto/aviso.py` |
| Se cumple el tiempo planeado | Aviso «la cámara sigue encendida» y se repite cada 10 min; la sesión no se termina sola | `monitor.py`, `FinDelPlan` |
| Sensibilidad fuera de sus topes en `data/preferencias.json` | Vuelve al valor de fábrica; el monitor rechaza lo que se salga | `app.py`, `cargar_preferencias`; `monitor.py`, `_entero_entre` |
| Título privado (banca, correo, contraseñas, salud, navegación privada) | «Privado», sin clasificar; no sale ni se guarda | `producto/reglas.json` |
| Título que cambia en cada lectura | Cuenta por proceso a los 5 s; una consulta por título equivalente | `ventanas.py`, `SeguidorVentanas` |
| Título con instrucciones para el clasificador | `no_sirve`, sin ir al modelo; nunca sale como `sirve` | `ventanas.py`, `parece_instruccion` |
| El clasificador falla, tarda o pasa de 6 consultas por minuto | `sin_clasificar`, sin alerta | `ventanas.py`, `Clasificador._clasificar` |
| El proveedor del coach da 429, timeout o salida inválida | Reintentos, respaldo y un mensaje honesto, nunca un stack trace | `docs/decisiones/m2-errores.md` |
| Pregunta sin datos o fuera de alcance (sueño, diagnóstico) | Dice que no tiene datos o que no diagnostica | `producto/evals/casos.json` |
| Inyección por el chat o por los datos | La respuesta no muestra imágenes ni enlaces; las reglas exigen aprobación | `docs/seguridad.md` |

## 6. Criterios de aceptación
Cada tarea tiene su pregunta de sí o no en su plan (`docs/PLAN-M2.md` y `docs/PLAN-M3.md`). Los globales son estos:
- Las pruebas pasan sin red, llaves ni cámara: `.venv\Scripts\python -m unittest discover -s tests`.
- Con `grabaciones\derecho.mp4` no hay alertas, y con `encorvado.mp4` hay una alerta de postura (`docs/decisiones/m2-decisiones.md`).
- La suite del coach, 12 casos × 3 corridas, se compara contra la línea base de la semana 10: 36/36, 0,000603 USD por tarea, mediana de 1 352 ms, p90 de 2 191 ms y 27/27 de recuperación. Resultado final en `docs/decisiones/semana14.md`.
- Los ataques de `producto/evals/ataques.py` no sacan datos ni escriben sin aprobación (`docs/seguridad.md`).
- Una persona ajena usa la app sin ayuda (`docs/decisiones/prueba-companero.md`). La primera prueba (`prueba-companero-2026-11-20.md`) lo logró en parte: no vio las alertas ni encontró sus registros, y eso se arregló en el bloque I.

## 7. Decisiones y renegociación
Registro vivo de decisiones:
- `docs/decisiones/exploracion.md` y `experimento-01.md` (Momento 1);
- `docs/decisiones/m2-decisiones.md`, `semana08.md` y `semana10.md` (Momento 2);
- `docs/decisiones/m3-decisiones.md` (Momento 3).

| Declarado | Qué se hizo | Por qué |
|---|---|---|
| LLM solo local (Ollama), por privacidad (`exploracion.md`) | LLM en la nube (Groq, Gemini de respaldo) para el coach y el clasificador; Ollama como modo sin internet (bloque H) | Este equipo no tenía Ollama y la capa gratuita en la nube respondió en 1 a 3 s con llamadas a herramientas. Se renegoció con condiciones escritas: qué sale y qué nunca sale (`m2-decisiones.md`) |
| Ningún título sale del equipo | Los títulos ambiguos y no privados van a Groq con la meta | Sin eso, lo ambiguo no se puede clasificar frente a la meta. Los privados nunca salen; `LLM_CLASIFICADOR_PROVIDER=ollama` o `ninguno` lo apagan |
| Interfaz Tkinter y notificaciones de Windows | Aviso emergente con Tkinter, app Streamlit en pestañas y la ventana de OpenCV como opción | En el Momento 2 se eligió el cartel sobre la imagen de la cámara, porque se ve aunque Windows tenga «No molestar». La prueba con una persona ajena (2026-11-20) mostró que esa ventana queda detrás y nadie ve la alerta. Se volvió a lo declarado con Tkinter (bloque I): se ve encima de todo y, a diferencia de una notificación de Windows, también con «No molestar» |
| Cámara lateral del celular, «más datos y medidas más certeras» | Experimento 02 (G1) con tres videos laterales grabados con el celular; no se integra | Con estos videos no separa la postura. El ángulo del cuello sube unos 16° al encorvarse o adelantar la cabeza, pero el ruido dentro de un mismo video es igual de grande (0,9 a 1,0 veces, frente a las 3 del criterio). El del tronco no sirve: la silla tapa la cadera. La frontal separó 9 veces en el experimento 01. Además, la integración en vivo tenía como condición cerrar A, C y D el 2026-11-15, y eso no se cumplió (`docs/decisiones/experimento-02.md`) |
| Ritmo de tecleo o de lectura | No se hace | Necesita un gancho global de teclado: es la capacidad de un keylogger y contradice los permisos mínimos |
| Ruido ambiental | No se hace | Abre el micrófono: superficie nueva de privacidad, sin umbrales probados |
| Objetos o desorden del escritorio | No se hace | La cámara frontal ve a la persona, no el escritorio; pide otro modelo y otra cámara |
| Micro-sueño, bostezos, parpadeo | No se hace | Pide Face Landmarker u otro detector, el doble de proceso y umbrales sin validar en el tiempo que quedaba |
| Estrés, tics, hábitos nerviosos | No se hace | Con estos sensores no hay señal válida: sería inventar un diagnóstico |
| Mirada fuera de la pantalla y mano en la cara | Se hizo después de la entrega del 2026-11-20 (bloque J), con los mismos puntos de pose y sin otro modelo | Antes de la entrega quedó «si alcanza» y no alcanzó. En el bloque J, mirar a un lado se mide como el giro de la cabeza frente a la calibración (`distraido.mp4` marca sus dos tramos y `derecho.mp4`, nada). La mano en la cara no tiene todavía un video para medir aciertos: su umbral es el más bajo que no marca nada en los tres videos (`m3-decisiones.md`) |

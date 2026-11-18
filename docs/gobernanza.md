# Ficha de gobernanza · BioFocus

Fecha: 2026-11-17. Describe lo que el código hace hoy (commit de esta fecha), no un sistema ideal: cada respuesta apunta a un archivo y una línea. Si el código cambia, esta ficha se revisa en el mismo commit.

BioFocus tiene dos piezas con modelo de lenguaje:
- el **clasificador de ventanas** del monitor (`producto/ventanas.py`), que decide si el título de una ventana ambigua sirve a la meta de la sesión;
- el **coach** (`producto/agente.py` y `producto/herramientas.py`), que responde preguntas sobre las sesiones con siete herramientas.

Lo demás son reglas y código, sin modelo: la postura con MediaPipe, las alertas, las reglas fijas de ventanas, la base y la app.

## 1. ¿Qué decide el sistema solo?

**El monitor**, sin preguntar a nadie:

| Decisión | Quién la toma | Dónde | Qué efecto tiene |
|---|---|---|---|
| Postura «bien», «revisa» o «no te veo», y la alerta de postura | Reglas sobre MediaPipe, en el equipo | `monitor.py`, clase `Postura` | Cartel y sonido en la ventana del monitor, y un evento `alerta_postura` |
| Categoría de una ventana por reglas: privada, neutra, distracción fija o regla aprobada | `producto/reglas.json` y `data/reglas.json` | `ventanas.py`, `Clasificador._clasificar` | Minutos por categoría |
| Categoría de una ventana ambigua (`sirve` o `no_sirve`) | El modelo (`openai/gpt-oss-20b` en Groq, o local) | `ventanas.py:298` (prompt) y `ventanas.py:314` (solo acepta esas dos) | Minutos por categoría y, tras 60 s seguidos en `no_sirve`, la alerta de distracción |
| Alerta de distracción | Regla: 60 s seguidos en `no_sirve`, 5 min entre alertas | `monitor.py`, clase `Distraccion` | Cartel, sonido y un evento `alerta_distraccion` |

El clasificador no puede escribir, borrar ni llamar a nada. Su respuesta se valida contra un conjunto cerrado (`ventanas.py:314`) y, si el título trae instrucciones, nunca sale como `sirve` (`ventanas.py:389`).

**El coach.** El modelo elige sola cuál de estas herramientas llamar y con qué argumentos. El código valida cada argumento antes de ejecutar (`herramientas.py`, funciones `_v_*`).

| Herramienta | Qué hace | ¿Escribe? |
|---|---|---|
| `resumen_sesiones` | Sesiones, minutos, alertas y pausas entre dos fechas | No: base en solo lectura (`datos.py:95`) |
| `minutos_por_categoria` | Minutos y porcentaje por categoría entre dos fechas | No |
| `distracciones_por_app` | Apps con más minutos en `no_sirve` y sus alertas | No |
| `alertas_por_hora` | Alertas por hora del día y tasa por hora de sesión | No |
| `pausas_recomendadas` | Pausas de un catálogo fijo (`producto/catalogo_pausas.json`) | No |
| `sesion_actual` | La sesión real en curso o la última | No |
| `guardar_regla` | **Solo propone** una regla permanente para una app | Solo con aprobación humana (pregunta 2) |

Límites que el coach no puede saltarse: 6 vueltas del bucle (`agente.py:34`), 12 000 tokens por pregunta (`agente.py:40`), 20 s por llamada al modelo (`agente.py:50`) y 5 s por herramienta (`agente.py:55`). Ninguna herramienta acepta SQL; las consultas son fijas (`docs/decisiones/semana08.md`).

## 2. ¿Qué necesita un humano, y quién es ese humano?

**El humano** es la persona que estudia: dueña del equipo, de la cámara y de los datos. Es una sola persona, que además desarrolla BioFocus. No hay administrador ni otro rol.

**Lo que el sistema exige:** sin la acción humana, no pasa.

| Acción | Cómo lo exige el código |
|---|---|
| Guardar una regla (`guardar_regla`) | El bucle se detiene y devuelve la propuesta sin ejecutarla (`agente.py:332`). La función se niega a escribir sin `aprobado=True` (`herramientas.py:494`). El único lugar que pasa `True` es el clic en «Aprobar» (`app.py:524` y `app.py:509`). Lo que se guarda lleva `"aprobada_por": "humano"` (`herramientas.py:499`) |
| Borrar datos (sesiones, trazas, reglas, registro) | El botón «Borrar» está desactivado hasta que la persona escribe BORRAR (`app.py:427`) |
| Encender la cámara | Solo con «Empezar sesión de estudio», y solo si la persona escribió una meta (`app.py:240` y `app.py:241`). Antes del botón, la app avisa que se enciende la cámara y qué sale del equipo (`AVISO_INICIO`). El monitor no arranca sin `--meta` (`monitor.py`, `main`) |

**Lo que ocurre, pero no se exige:** leer las alertas, revisar «Fuente y criterio» y la traza de cada respuesta, recalibrar con la tecla `c`, cambiar de proveedor y terminar la sesión. Son costumbres de quien usa BioFocus, no controles, y aquí no se presentan como supervisión.

## 3. ¿Qué queda registrado, dónde y por cuánto tiempo?

| Qué | Dónde | Cuánto tiempo |
|---|---|---|
| Sesiones (inicio, fin, meta, duración planeada, real o demo) y eventos (hora, tipo, app, categoría, duración y un detalle corto de hasta 80 caracteres) | `data/biofocus.sqlite` (`datos.py`, `ESQUEMA`). Git lo ignora | Hasta que la persona lo borre desde «Borrar mis datos». Al borrar, SQLite sobrescribe lo borrado y compacta el archivo (`datos.py:150` y `datos.py:165`). No hay vencimiento automático: es el historial que el coach consulta |
| Estado en vivo (postura, app y categoría actuales) | Tabla `estado_monitor`, en la misma base | Igual que la sesión |
| Preguntas al coach, respuestas, herramientas con sus argumentos, tokens y tiempos | `traces/AAAA-MM-DD.jsonl` (`trazas.py`). Git lo ignora | 30 días: al guardar una traza se borran las más viejas (`trazas.py:22` y `trazas.py:84`) |
| Salida del monitor (inicio y fin, alertas con el nombre de la app, errores) | `data/monitor.log` | Máximo 512 KB: al llegar al tope se queda con la mitad más reciente (`app.py:45` y `app.py:137`) |
| Reglas aprobadas, con fecha y `aprobada_por` | `data/reglas.json` | Hasta que la persona las borre |
| Resultados de la evaluación y de los ataques, con sus trazas | `producto/evals/resultados/` | En git, para siempre. Son datos sintéticos (semilla 42) |
| En el proveedor (Groq o Gemini) | Sus servidores | **No lo controlamos.** Lo fija la política de cada proveedor y no la verificamos |

**Nunca se registra:** imágenes, video ni audio, que viven en memoria lo que tarda un cuadro (`monitor.py`, `correr`). Tampoco títulos de ventana: ninguna tabla tiene dónde ponerlos, y un evento de ventana con detalle se rechaza (`datos.py:131`).

## 4. ¿Qué datos toca y cuáles salen a un tercero?

**Datos personales que toca:**
- la imagen de la cámara: cara y cuerpo;
- el título de la ventana activa: puede traer nombres de documentos, búsquedas, nombres de personas o texto sin guardar (`docs/decisiones/experimento-01.md`);
- la meta de cada sesión;
- los patrones de uso: a qué hora estudia, cuánto, qué apps lo distraen;
- lo que la persona escribe en el chat.

**Camino de cada dato:**

| Origen | Paso por el equipo | Llega al proveedor | Proveedor |
|---|---|---|---|
| Cámara | MediaPipe, en memoria | **Nada** | — |
| Título de una ventana ambigua y no privada | Se quita el sufijo del navegador y se recorta a 200 caracteres (`ventanas.py:328`) | El título, el nombre de la app y la meta (hasta 200 caracteres) | Groq, `openai/gpt-oss-20b` (`ventanas.py:46`) |
| Título privado: banca, correo, contraseñas, salud, navegación privada | Se marca «Privado» antes de cualquier otro paso (`producto/reglas.json:8`) | **Nada** | — |
| Base de datos | Las herramientas devuelven cifras agregadas, horas, nombres de app (alfabeto cerrado, máximo 30 caracteres: `herramientas.py:188`) y categorías. Nunca la meta (`datos.py:38`) ni títulos | El resultado de cada herramienta | Groq, `openai/gpt-oss-120b`; Gemini de respaldo |
| Chat | Se recorta a 1 000 caracteres y se reenvían las dos últimas preguntas con su respuesta (`agente.py:67`) | La pregunta, tal como la escribió la persona | El mismo del coach |

Con `OFFLINE_MODE=true`, o con `ollama` como proveedor, nada de esto sale del equipo (`proveedor.py:138` y `ventanas.py:278`; bloque H del plan).

## 5. ¿Qué hacemos si el sistema causa un daño?

**Qué daños puede causar.** Mandar a un tercero algo privado: un título que las reglas no reconocieron como privado, o algo escrito en el chat. Dar una cifra falsa sobre la que la persona decida. Que una alerta de postura se lea como diagnóstico. Que una regla cambie la clasificación sin que la persona la quiera. Que la cámara quede encendida sin que se sepa.

**Quién se entera.** La persona que lo usa. Lo ve en la ventana «BioFocus monitor» (siempre encima mientras la cámara está encendida), en «Fuente y criterio», que el código arma con lo que de verdad se consultó (`agente.py:177`), y en el aviso «quité de la respuesta…» cuando el coach intenta mostrar contenido externo (`agente.py:199`). Como desarrollador, el mismo autor revisa las trazas. No hay un canal para avisar a otra persona: es un sistema de un solo usuario.

**Cómo se apaga.** De lo más inmediato a lo más amplio:
1. La cámara: «Terminar sesión» (`app.py:218`), la tecla `q` (`monitor.py:664`) o cerrar la ventana del monitor (`monitor.py:670`). Si el monitor no responde, la app manda Ctrl+Break y cierra la sesión en la base (`app.py:181`).
2. La salida de títulos a Groq: `LLM_CLASIFICADOR_PROVIDER=ninguno` en `.env`. Las reglas fijas siguen y lo ambiguo queda sin clasificar.
3. Toda salida a internet: `OFFLINE_MODE=true` (solo modelo local) o borrar la llave de `.env`. El coach responde que no hay proveedor, sin inventar.
4. Todo: cerrar Streamlit con Ctrl+C. El monitor se cierra solo a los 15 s sin señales (`vivo.py:14`).

**Qué se revisa.**
- La traza de la respuesta, por su id: `traces/`, o el desplegable «Traza técnica».
- `data/monitor.log`, para la hora y el motivo de cada cierre y de cada alerta.
- `data/reglas.json`, para ver qué regla cambió, cuándo y que diga `aprobada_por: humano`.
- Los eventos de la sesión en la base.

Con eso se decide si fue el modelo, una regla o el código, y el caso se agrega a la suite (`producto/evals/casos.json`) o a los ataques (`producto/evals/ataques.py`) antes de arreglarlo.

**A quién se avisa.**
- Si se filtró una llave: se cambia en la consola del proveedor. Pasó en octubre y se cambiaron el 2026-11-13; ver `docs/seguridad.md`.
- Si salió a Groq algo privado: no se puede recuperar. Se pide el borrado según la política del proveedor, se agrega el patrón a los privados de `producto/reglas.json` y se avisa a la persona afectada si no es el autor, por ejemplo quien haga la prueba del compañero.
- Si pasa durante una demo en clase: se avisa al docente.
- Si alguien tomó una alerta como consejo de salud: se le aclara que BioFocus no diagnostica (`agente.py:91` y el aviso de `producto/catalogo_pausas.json`) y que consulte a un profesional.

# Decisiones · Momento 2 · Coach

Fecha: 2026-10-29. La instrucción del Momento 2 es la tarea aprobada (`docs/PLAN-M2.md`). `docs/PLAN.md` y `docs/SPEC.md` todavía no existen. Aquí van las decisiones menores que tomé sin preguntar, para revisarlas.

## Renegociación: el coach usa un LLM en la nube
- **Antes:** la exploración proponía "LLM solo local" (Ollama con un modelo de ~3B) y descartaba la nube como principal, sobre todo para que los títulos de ventana no salieran del equipo.
- **Ahora:** el coach usa un proveedor en la nube (Groq o Gemini, por la API compatible con OpenAI). Ollama queda como opción local; este equipo no lo tiene instalado.
- **Condición:** al proveedor solo salen la pregunta, el prompt del sistema, las descripciones de las herramientas y lo que estas devuelven: cifras agregadas, nombres de app y categorías. Nunca títulos de ventana, metas de sesión, imágenes ni audio.
- **Lo que se escribe en el chat sí sale del equipo.** El README lo advierte.
- No cambia nada de la cámara ni de los títulos del Momento 1.

## Datos
- No había esquema de eventos en `producto/` ni en `docs/`: uso el de la instrucción.
- Agrego `sesiones.es_demo` (0 o 1) para marcar la demo. Regenerarla borra solo lo marcado; los datos reales no se tocan.
- Horas locales (Colombia) como texto `AAAA-MM-DD HH:MM:SS`, sin zona: las preguntas son por hora del día.
- Los eventos `ventana` no aceptan `detalle` y ninguna tabla tiene columna de título: no hay dónde guardar uno.
- `data/` ya estaba en `.gitignore`: la base no se sube y se regenera con `producto/generar_datos_demo.py`.
- La demo cubre los 7 días que terminan ayer, contados desde la fecha en que se genera (`--hasta` las fija). Con la misma fecha y la semilla 42, los datos son idénticos (hay prueba).
- Patrones de la demo, para que las preguntas tengan respuesta: más distracción en la sobremesa (15:00 a 16:59) y al acumular tiempo sin pausa, y menos sesiones el fin de semana.
- La alerta de postura dice "postura distinta a la línea base", sin nombrar la causa (lo pide el experimento 01).

## Herramientas
- Las herramientas abren la base en **solo lectura** y usan consultas fijas. El modelo solo elige herramienta y argumentos.
- **La meta de la sesión no sale del equipo:** se guarda, pero ninguna herramienta la devuelve.
- Validación estricta: fechas reales `AAAA-MM-DD`, `desde <= hasta`, máximo 92 días, sin parámetros extra. Para no castigar formas obvias, acepta `top` como `"5"`, y `tipo`, `motivo` y `categoria` sin tildes, en mayúsculas o con el prefijo `alerta_`.
- `alertas_por_hora` devuelve también los minutos de sesión por hora y la tasa de alertas por hora de sesión. Así "me distraigo más a las 15:00" no se confunde con "estudio más a las 15:00". La tasa solo compara horas con 30 min de sesión o más.
- `guardar_regla` solo acepta apps que ya aparecen en los datos y las categorías `sirve`, `no_sirve` o `neutro`. Escribe en `data/reglas.json`, que es un dato de la persona y git ignora. La función se niega a escribir sin `aprobado=True`, que solo pone la app tras el clic en Aprobar.
- Los nombres de app se recortan a 40 caracteres y pierden los caracteres de control antes de llegar al modelo.
- **Catálogo de pausas:** borrador conservador (caminar, revisar el puesto, mover los hombros, mirar a lo lejos, respirar, pausa sin pantallas, ir por agua). Cada pausa trae su precaución, y el catálogo trae el aviso de consultar a un profesional. No cita fuentes porque no las verifiqué: hay que revisarlo antes de usarlo con otras personas.

## Proveedor
- **User-Agent propio** (`BioFocus/0.2`): Cloudflare, delante de Groq, rechaza con 403 (error 1010) el User-Agent por defecto de urllib.
- **Modelos verificados** con `producto/verificar_modelos.py` el 2026-10-29:
  - Groq: `openai/gpt-oss-120b` (principal por defecto), `openai/gpt-oss-20b` (respaldo dentro de Groq) y `qwen/qwen3.8-27b`.
  - Gemini: `gemini-3.5-flash` (por defecto), `gemini-3.5-flash-lite`, `gemini-flash-lite-latest` y `gemini-3.1-flash-lite`.
  - Fallaron: `llama-3.3-70b-versatile` (Groq ya no lo lista), `gemini-2.5-flash` y `gemini-2.5-flash-lite` (404), y `gemini-flash-latest` y `gemini-3.8-flash` (más de 20 s).
- El `.env` actual define Groq como principal y Gemini como respaldo (`LLM_FALLBACK_*`) sin fijar modelos, así que valen los de arriba.
- Las variables `LLM_*` y `OFFLINE_MODE` del sistema tienen prioridad sobre `.env`, como en python-dotenv.
- `OFFLINE_MODE=true` (ya estaba en `.env.example`) deja solo Ollama local.
- **429:** esperas fijas de 1, 2 y 4 s, también en el respaldo. Se ignora `Retry-After`. Si todo se agota, mensaje honesto y la sesión sigue.
- **Respaldo pegajoso dentro de una pregunta:** después de cambiar al respaldo, las demás llamadas de esa pregunta van directo a él. Si no, cada llamada esperaría 7 s más. La pregunta siguiente vuelve a empezar por el perfil activo.
- **Timeout:** límite total de 20 s por llamada, con un hilo aparte, porque urllib solo mide cada operación de red. No pasa al respaldo: corta y lo dice.
- **Otros errores** (llave rechazada, 5xx, red caída, modelo inexistente): pasan al respaldo sin esperar.
- **Salida inválida:** el interruptor reemplaza los argumentos de la primera llamada a herramienta por `{"desde": "la semana pasada", "hasta": "hoy"}`. La validación y el reintento viven en el agente, que es donde se validan los argumentos. El 400 `tool_use_failed` de Groq cuenta como salida inválida.
- **Interruptores:** 429 (no, principal o todos), timeout (sí o no) y salida inválida (no, una vez o siempre). "Principal" es el perfil activo. Los casos forzados no salen a la red.

## Agente
- Si la salida es inválida por segunda vez, responde con un texto fijo, sin otra llamada al LLM, para no contestar sin datos. El fallo queda en la traza (`fallo: salida_invalida`) y en el log.
- Tokens: suma lo que informa el proveedor en `usage`. Antes de cada llamada estima el siguiente envío (3,5 caracteres por token) para no pasarse de 12 000.
- La aprobación pausa el bucle: `guardar_regla` no se ejecuta y la respuesta trae la propuesta. La app llama a `resolver_aprobacion` con el clic en Aprobar o Rechazar, y después no hay otra llamada al LLM.
- Los avisos de límite (por ejemplo, el timeout de una herramienta) se agregan al final de la respuesta.
- Historial: se reenvían las últimas 2 preguntas y respuestas, solo el texto.
- "Fuente y criterio" la arma el código desde lo que pasó en la pregunta, no el LLM. Si no se consultó ninguna herramienta, lo dice.
- Si la pregunta no dice el periodo, se usan los últimos 7 días y la respuesta lo dice.

## Trazas
- `traces/AAAA-MM-DD.jsonl`, una línea por pregunta, con la pregunta, la respuesta, los tokens y los spans (orden, tipo y duración en ms). Están en `.gitignore`.
- Guardan la pregunta, que no sale de la carpeta del proyecto. Nunca guardan la llave (hay prueba).

## App
- El selector de proveedor ofrece los perfiles de `.env` y los demás modelos verificados de esos proveedores, que usan la misma llave. El elegido pasa a ser el activo ("principal" para los interruptores) y el respaldo es el primer perfil de `.env` distinto.
- El panel muestra los últimos 7 días, hoy incluido: barras horizontales de una sola serie, con tooltip, y una tabla con los mismos números.
- `.streamlit/config.toml`: la app solo escucha en `localhost` y no envía estadísticas de uso a Streamlit.
- El chat no acepta archivos ni audio.
- Las preguntas de ejemplo son las tres de la instrucción, como botones, para la demo.

## Prueba de punta a punta (paso 7)
- **Fallo encontrado y corregido:** en la tercera pregunta real, Groq respondió 429 de verdad por límite de la capa gratuita. El reintento y el cambio a Gemini funcionaron, pero Gemini rechazó el historial con un 400: Gemini 3 exige una `thought_signature` en las llamadas a herramienta, y las que generó Groq no la traen. Ahora, antes de enviar a Gemini, el proveedor agrega a esas llamadas el valor que Google documenta para historiales que vienen de otro modelo (`skip_thought_signature_validator`). Lo verifiqué contra la API real (sin la firma da 400; con ella responde) y hay una prueba de regresión. Groq acepta sin problema las llamadas con el campo de Gemini.
- `pausas_recomendadas`: si la persona no dice el motivo, usa `general` en vez de preguntar (en una corrida, el modelo preguntaba).
- El aviso del catálogo de pausas se agrega siempre a "Fuente y criterio", desde el código, porque el modelo a veces lo omitía.
- `.env.example` documenta ahora `LLM_MODEL`, `LLM_FALLBACK_*` y `OFFLINE_MODE`.

## Suite de evaluación (semana 10)
- La suite genera una base temporal con la semilla 42 hasta el 2026-10-28 y fija "hoy" en 2026-10-29 con un parámetro nuevo, `agente.responder(..., hoy=...)`. Así "esta semana" y "los últimos 7 días" siempre significan lo mismo. No toca `data/`.
- Durante la suite, `guardar_regla` apunta a un `reglas.json` temporal.
- Un caso pasa si cumple su invariante. Hay siete tipos: número, texto, hora, herramienta, rechazo, sin ejecución y pendiente. Las herramientas requeridas se miden aparte, como recuperación.
- Cuentan como llamadas las herramientas que el modelo pidió con argumentos válidos; `guardar_regla` cuenta aunque quede pendiente. En las herramientas requeridas, una lista interna significa "cualquiera de estas".
- Para buscar números en la respuesta se ignoran fechas y horas, y se aceptan formas como "1.206", "1 206" y "942,3". Tolerancia de 0,6 donde vale redondear a entero.
- **Pausa de 28 s entre preguntas.** La capa gratuita de Groq da 8 000 tokens por minuto (cabecera `x-ratelimit-limit-tokens`) y cada pregunta usa unos 4 000; sin pausa se mediría la cuota y no al coach.
- El p90 se calcula por rango más cercano.
- Los resultados y sus trazas se suben al repositorio (`producto/evals/resultados/`) porque son datos sintéticos.
- **La prueba corta de la suite encontró una doble confirmación.** Ante "Marca WhatsApp como no sirve", el modelo pedía confirmación en texto en vez de llamar a `guardar_regla`, que ya muestra Aprobar y Rechazar. Antes de las corridas medidas ajusté la descripción de la herramienta y la regla 5 del prompt: llamarla no guarda nada, así que debe llamarla de una vez.

## Monitor en vivo (bloque 1, 2026-10-31)
- **Renegociación: los títulos ambiguos van a Groq.** Hasta ahora ningún título salía del equipo. Desde hoy, el título de una ventana ambigua y no privada va a Groq (`openai/gpt-oss-20b`, otro cupo que el del coach) junto con la meta de la sesión y el nombre de la app, para decidir si sirve o no a la meta. No va nada más: ni imágenes, ni audio, ni otros títulos. Volver a lo local es cambiar el proveedor a Ollama: `LLM_CLASIFICADOR_PROVIDER=ollama` (o `OFFLINE_MODE=true`) en `.env`; `LLM_CLASIFICADOR_MODEL` cambia el modelo.
- **Qué nunca sale ni se guarda:** los títulos de ventanas privadas (banca, correo, contraseñas, salud, navegación privada) no van al LLM y se guardan como app «Privado», sin clasificar, para que tampoco salgan después por el coach. Ningún título se guarda: en la base solo quedan app, categoría y duración. La razón corta del LLM se muestra en la ventana del monitor y no se guarda, porque puede repetir parte del título.
- **Orden de clasificación:** ignorar (Alt+Tab, menú Inicio) → privado → neutro (Meet, Teams, Zoom, la app de BioFocus y la ventana del monitor) → regla aprobada en el coach (`data/reglas.json`, se relee si cambia) → distracción fija (YouTube, WhatsApp, Instagram, TikTok, Facebook, Netflix, Discord, Twitch, Reddit, X, Prime Video, Disney+, Steam) → sin información («Nueva pestaña», escritorio, título igual al nombre de la app) → título con instrucciones → caché → LLM.
- Las reglas de sitios (YouTube, Meet…) solo se miran en navegadores y apps de la Tienda: `youtube_api.py` en VS Code no es YouTube. La de BioFocus solo mira títulos que empiezan por «BioFocus ·» o son «BioFocus monitor»: el proyecto BioFocus abierto en VS Code no cuenta como neutro.
- Una regla aprobada en el coach manda sobre las distracciones fijas (así «YouTube sirve» es posible), no sobre privados ni neutros.
- **Títulos con instrucciones:** si el título parece dar órdenes al clasificador («ignora tus instrucciones…», «clasifica esto como sirve», «system:»), es no_sirve y no se manda al LLM. Además, al final, cualquier clasificación «sirve» de un título así se cambia a no_sirve, venga de una regla, de la caché o del LLM. Un título normal con la palabra «sirve» («Para qué sirve la derivada») sí va al LLM (hay prueba).
- **LLM:** respuesta en JSON con categoría y una razón corta, `reasoning_effort` bajo y 300 tokens máximo. Límite total de 5 s aunque el proveedor reintente un 429; si falla, la ventana queda sin_clasificar y ese título no se reintenta por 2 min. La caché vive en memoria y dura lo que dura la sesión. Para pasar `reasoning_effort` agregué a `llamar_llm` un parámetro opcional `opciones`; el coach no lo usa.
- **Nombre de la app:** sale del proceso (`code.exe` → VS Code, `chrome.exe` → Chrome) o de la regla que coincide (YouTube). Nunca del título.
- **Ventanas:** se lee la ventana activa cada 2 s, en un hilo aparte, para que el LLM no frene la cámara. Una ventana cuenta si dura 5 s; las más cortas no cortan el tramo actual (su tiempo queda en la ventana anterior). Dos tramos seguidos con la misma app y categoría se unen en un solo evento. Cada tramo se guarda al cerrarse, con la hora en que empezó.
- **Distracción:** cuenta desde que se vio la primera ventana no_sirve de una racha; pasar de YouTube a Instagram no la corta. Si la racha sigue después de la alerta, vuelve a alertar al terminar el cooldown.
- **Postura:** la métrica del experimento 01. La calibración descarta el primer segundo y usa la mediana de 5 s (al menos 10 cuadros con hombros visibles; si no, sigue calibrando). La alerta y el rearme miran la mediana del último medio segundo, para que un cuadro suelto no corte la cuenta. Si no se ven nariz y hombros, el estado es «no te veo» y la cuenta vuelve a cero, sin alerta. El aviso dice «Revisa tu postura» y que la cabeza bajó frente a la línea base, sin nombrar la causa.
- **Avisos:** cartel grande en la ventana de la cámara durante 6 s y un sonido corto con `winsound.Beep` en otro hilo (dos tonos distintos para postura y distracción). La ventana se llama «BioFocus monitor», queda siempre encima de las demás y se ve como un espejo. Las tildes se dibujan con Pillow (Segoe UI), porque OpenCV no las dibuja.
- **Base:** modo WAL y `busy_timeout`. Nueva tabla `estado_monitor` con el estado en vivo (postura, app y categoría actuales, sin títulos) que el monitor escribe cada segundo, y la marca `detener` que pone la app para terminar. Si el monitor deja de dar señales por 15 s, la sesión se cierra en su último latido la próxima vez que alguien arranque una sesión (`cerrada sin monitor`). No puede haber dos sesiones en curso.
- **Sesión real:** `es_demo = 0` aunque se use `--modo-demo` (que solo acorta los tiempos: postura 5 s, distracción 10 s, cooldown 30 s). La duración planeada se guarda pero no corta la sesión: termina con q, al cerrar la ventana, desde la app o con Ctrl+C.
- **Plan B (`--video`):** lee el video una vez, a su ritmo, y al terminar cierra la sesión (`fin del video`). Las ventanas se siguen leyendo en vivo.
- Opciones para pruebas: `--sin-ventana` (sin ventana ni sonido), `--detalle` (una línea por segundo con el número de postura, la base y el estado) y `--bd` (otra base).
- `mediapipe==1.1.1` quedó instalado en el `.venv` de la raíz con tu permiso (trae `opencv-contrib-python` 5.0.0.93; `pip check` limpio). El modelo vive en `producto/modelos/` (git lo ignora) y el monitor se niega a usarlo si su SHA-256 no es el de `experimento-01.md`.

### Prueba con los tres videos (`--video`, modo demo)
Base temporal aparte para cada corrida y sin clasificador LLM (`LLM_CLASIFICADOR_PROVIDER=ninguno`), para que no saliera ningún título real durante la prueba.

| Video | Esperado | Línea base | Número de postura (mediana de 0,5 s) | Qué pasó | ¿Cumple? |
|---|---|---|---|---|---|
| `derecho.mp4` (31,6 s) | Ninguna alerta | 0,494 | 0,392 a 0,616 (−21 % a +25 %), mediana 0,475 (−4 %) | Siempre «bien». Lo más bajo fue −21 % por menos de 2 s. Sin alertas. | Sí |
| `encorvado.mp4` (30,8 s) | Alerta de postura | 0,480 | Derecho: 0,434 a 0,480 (−10 % a 0 %). Encorvado desde el s 11: 0,150 a 0,278 (−69 % a −42 %), mediana 0,243 (−49 %) | «Revisa» desde el s 12,3 y una sola alerta en el s 16,5 (−52 %), a los 5 s. Después no repite: queda sin rearmar hasta volver a −10 %. | Sí |
| `distraido.mp4` (36,5 s) | Ver qué hace | 0,463 | Derecho: −13 % a −4 %. Mirando a un lado: +20 % a +33 %. Mirando el celular: 0,214 a 0,331 (−54 % a −29 %), mediana −51 %. Final: −20 % a +7 % | Mirar a un lado **sube** el número (los hombros se ven más angostos): sin alerta. Mirar el celular lo baja como encorvarse: «revisa» del s 24,5 al 29, unos 4,6 s, sin llegar a los 5 s: sin alerta. Nunca «no te veo». No hubo alerta de distracción porque esa sale de las ventanas, no de la cámara. | Sin expectativa: se comporta según la regla |

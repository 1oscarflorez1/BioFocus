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

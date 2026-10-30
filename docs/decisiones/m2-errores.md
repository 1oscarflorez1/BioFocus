# Errores forzados · Momento 2

Fecha: 2026-10-29. Los tres casos de error del coach se fuerzan con los **Interruptores de prueba** de la barra lateral de la app o, en consola, con `--forzar-429`, `--forzar-timeout` y `--forzar-salida-invalida` (`producto/agente.py`). El 429 y el timeout forzados no salen a la red. La salida inválida sí llama al modelo y le cambia la respuesta.

**Lo común en pantalla.** Con cualquier interruptor encendido, la app muestra arriba un aviso amarillo, "Interruptores de prueba encendidos: …". Debajo de cada respuesta aparecen "Fuente y criterio" y el desplegable "Traza técnica · N spans · X ms · Y tokens", con la tabla de spans y el JSON completo. Las trazas de abajo están en `traces/2026-10-29.jsonl` (local, git las ignora) y se buscan por su id.

## 1. 429: el proveedor limita las peticiones
**Interruptor:** Forzar 429 → "Solo el activo".

**Qué hace el coach:** el proveedor activo devuelve 429 en los cuatro intentos, con esperas de 1, 2 y 4 s entre ellos. Después pasa al respaldo sin cortar la sesión y responde con datos. La pregunta tarda unos 7 s más de lo normal.

**En pantalla** (app con Gemini activo, 23:28, traza `ae8eb835f5c9`):
- Aviso: "Interruptores de prueba encendidos: 429 (solo el activo)."
- Una respuesta normal, con datos del catálogo: "Te recomiendo una pausa **general**: levántate y camina 3 min, mira a lo lejos 1 min, respira despacio 2 min y toma agua 3 min. […]"
- Fuente y criterio: Catálogo de pausas, 4 pausas para «general».
- Desplegable: "Traza técnica · 12 spans · 8204 ms · 3952 tokens".

| # | Span | ms | Detalle |
|---|---|---|---|
| 1 | llm | 0 | gemini · gemini-3.5-flash, intento 1, estado 429 (forzado) |
| 2 | reintento | 1000 | espera 1 s |
| 3 | llm | 0 | intento 2, estado 429 (forzado) |
| 4 | reintento | 2001 | espera 2 s |
| 5 | llm | 0 | intento 3, estado 429 (forzado) |
| 6 | reintento | 4001 | espera 4 s |
| 7 | llm | 0 | intento 4, estado 429 (forzado) |
| 8 | cambio_proveedor | 0 | de gemini · gemini-3.5-flash a groq · openai/gpt-oss-120b, motivo 429 |
| 9 | llm | 633 | groq, ok: 1 707 tokens de entrada y 103 de salida; pide 1 herramienta |
| 10 | validacion | 0,1 | `pausas_recomendadas` `{"motivo": "general"}`: válida |
| 11 | herramienta | 1,3 | 4 pausas del catálogo para «general» |
| 12 | llm | 567 | groq, ok: 2 078 tokens de entrada y 64 de salida; respuesta final |

Con la configuración de `.env` (Groq activo) pasa lo mismo al revés: Groq da 429 cuatro veces y responde Gemini. Es la traza `efe0883d1588`, en consola: 12 spans, 14 016 ms.

**Variante "Todos"** (consola, traza `d5553b604865`, 15 spans, 14 017 ms, 0 tokens). Los dos proveedores dan 429 cuatro veces cada uno, con esperas de 1, 2 y 4 s en cada uno, y la respuesta es honesta: "Los proveedores de IA están limitando las peticiones (error 429) y ya probé el respaldo. Tu sesión sigue abierta: espera un minuto y vuelve a preguntar. No respondo sin datos para no inventar." Fuente y criterio dice: "No se consultaron tus datos para esta respuesta".

**429 de verdad:** también pasó sin interruptor, en la prueba de punta a punta del paso 7, porque la capa gratuita de Groq permite 8 000 tokens por minuto. Así apareció el fallo de la firma de Gemini al cambiar de proveedor, ya corregido (ver `m2-decisiones.md`).

## 2. Timeout: el proveedor no responde
**Interruptor:** Forzar timeout.

**Qué hace el coach:** la llamada al modelo se corta como si hubiera pasado el límite de 20 s. Al estar forzada, no espera ni sale a la red. El agente registra el límite y responde con un mensaje claro, nunca con un stack trace. No pasa al respaldo: corta y lo dice.

**En pantalla** (app, 23:50, traza `581a0d22f9e7`):
- Aviso: "Interruptores de prueba encendidos: timeout."
- Respuesta: "El proveedor de IA (groq · openai/gpt-oss-120b) no respondió en 20 s, así que corté la espera. Tu sesión sigue abierta: vuelve a preguntar en un momento."
- Fuente y criterio: "No se consultaron tus datos para esta respuesta: no la tomes como una cifra de tus sesiones."
- Desplegable: "Traza técnica · 2 spans · 0 ms · 0 tokens".

| # | Span | ms | Detalle |
|---|---|---|---|
| 1 | llm | 0 | groq · openai/gpt-oss-120b, intento 1, estado timeout (forzado) |
| 2 | limite | 0 | `timeout_llm`, máximo 20 s |

El timeout real, sin interruptor, lo cubre la prueba `test_timeout_real_sin_stack_trace`: un servidor falso que tarda 1,5 s contra un límite de 0,3 s.

## 3. Salida inválida: el modelo pide una herramienta con argumentos que no validan
**Interruptor:** Forzar salida inválida → "Una vez" o "Siempre".

**Qué hace el coach:** cuando el modelo pide una herramienta, el interruptor cambia sus argumentos por `{"desde": "la semana pasada", "hasta": "hoy"}`. La validación los rechaza y el agente le devuelve el error al modelo, que vuelve a intentar.
- **Una vez:** el segundo intento sale bien y la respuesta trae datos.
- **Siempre:** al segundo fallo, el coach responde con un texto fijo, sin inventar, y registra el fallo en la traza (`fallo: salida_invalida`) y en el log.

**En pantalla, "Una vez"** (app con Gemini activo, 23:50, traza `64a13381a510`):
- Aviso: "Interruptores de prueba encendidos: salida inválida (una vez)."
- Respuesta con datos: "Esta semana (del 26 al 29 de octubre de 2026) tuviste **7 alertas de postura** en un total de 8 sesiones de estudio. *Nota: Estos datos son de demostración.*"
- Fuente y criterio: Resumen de sesiones del 2026-10-26 al 2026-10-29: 8 sesiones, 605 min reales de 630 planeados, 7 alertas de postura…
- Desplegable: "Traza técnica · 7 spans · 8263 ms · 7185 tokens".

| # | Span | ms | Detalle |
|---|---|---|---|
| 1 | llm | 2727 | gemini, ok: 1 869 tokens de entrada y 42 de salida; pide 1 herramienta |
| 2 | salida_invalida_forzada | 0 | `resumen_sesiones`, modo una vez |
| 3 | validacion | 0,1 | `{"desde": "la semana pasada", "hasta": "hoy"}`: **no válida**, "'desde' debe ser una fecha AAAA-MM-DD; llegó 'la semana pasada'." |
| 4 | llm | 2421 | gemini, ok: 2 191 tokens de entrada y 33 de salida; vuelve a pedir la herramienta |
| 5 | validacion | 0,1 | `{"desde": "2026-10-26", "hasta": "2026-10-29"}`: válida |
| 6 | herramienta | 5,4 | 8 sesiones en 3 días, 605 min reales de 630 planeados; 7 alertas de postura… |
| 7 | llm | 3107 | gemini, ok: 3 000 tokens de entrada y 50 de salida; respuesta final |

**"Siempre"** (consola con Gemini activo, traza `10b859b9d122`, 6 546 ms, 4 384 tokens). La respuesta es "No pude consultar tus datos: el modelo pidió las herramientas con argumentos inválidos dos veces seguidas, así que paro aquí para no inventar. Prueba reformular la pregunta, por ejemplo con fechas concretas." Los spans son llm → salida_invalida_forzada → validacion (no válida) → llm → salida_invalida_forzada → validacion (no válida) → `fallo_registrado` (motivo `salida_invalida`, 2 intentos).

## Qué falta
- Ver el aviso "429 (todos)" y "salida inválida (siempre)" en la app. Están verificados en consola y en las pruebas, que usan el mismo código.
- Las capturas de pantalla no se guardan: el documento describe lo que se ve, y cada traza se puede volver a abrir en `traces/2026-10-29.jsonl`.

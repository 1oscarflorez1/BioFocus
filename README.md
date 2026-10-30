# BioFocus · Coach

BioFocus es un monitor personal de salud, foco y espacio de trabajo para sesiones de estudio frente al computador. Este repositorio trae, por ahora, el **Coach** (Momento 2): un agente que responde preguntas sobre tus sesiones con herramientas propias sobre los eventos guardados en SQLite. Por ejemplo:

- "¿A qué hora me distraigo más?"
- "¿Cuántas alertas de postura tuve esta semana?"
- "¿Qué pausa me recomiendas?"

Debajo de cada respuesta aparecen la **fuente y el criterio** de las cifras y la **traza técnica** de cómo se obtuvieron.

## Privacidad
- BioFocus no guarda imágenes, video ni audio, y nada de eso sale del equipo. Los eventos tampoco guardan títulos de ventana.
- Al proveedor de IA (Groq o Gemini) solo salen tu pregunta, las instrucciones del coach, las descripciones de las herramientas y lo que estas devuelven: cifras agregadas, nombres de app y categorías. Nunca títulos de ventana ni la meta de tus sesiones.
- **Lo que escribes en el chat sí sale del equipo.** No escribas ahí datos privados.
- El coach no diagnostica. Las pausas salen de un catálogo fijo y conservador (`producto/catalogo_pausas.json`).

## Qué necesitas
- Windows con Python 3.13 (en macOS o Linux cambia `.venv\Scripts\python` por `.venv/bin/python`).
- Una llave gratuita de [Groq](https://console.groq.com/keys) o de [Gemini](https://aistudio.google.com/apikey). Con las dos, una queda de respaldo de la otra.

## Instalación (una vez)
En PowerShell, desde la carpeta del repositorio:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install streamlit
copy .env.example .env
```

Abre `.env` con un editor de texto y llénalo. Nunca lo subas al repositorio (git ya lo ignora).

| Variable | Qué va | Ejemplo |
|---|---|---|
| `LLM_PROVIDER` | Proveedor principal: `groq`, `gemini` u `ollama` | `groq` |
| `LLM_API_KEY` | La llave de ese proveedor | |
| `LLM_MODEL` | Opcional. Vacío usa el modelo verificado | `openai/gpt-oss-120b` |
| `LLM_FALLBACK_PROVIDER` | Opcional. Proveedor de respaldo | `gemini` |
| `LLM_FALLBACK_API_KEY` | La llave del respaldo | |
| `LLM_FALLBACK_MODEL` | Opcional. Vacío usa el verificado | `gemini-3.5-flash` |
| `OFFLINE_MODE` | `true` para usar solo Ollama local | `false` |

Sin respaldo configurado, el respaldo es otro modelo del mismo proveedor. Para revisar qué modelos responden con herramientas en tu cuenta:

```powershell
.venv\Scripts\python producto\verificar_modelos.py
```

## Datos de prueba
```powershell
.venv\Scripts\python producto\generar_datos_demo.py
```

Crea `data/biofocus.sqlite` con 7 días de sesiones sintéticas que terminan ayer. Usa la semilla 42, así que con la misma fecha salen siempre los mismos datos, y todo queda marcado como demo. Volver a correrlo reemplaza solo la demo. Con `--hasta 2026-10-28` fijas las fechas.

## Usar la app
```powershell
.venv\Scripts\python -m streamlit run producto\app.py
```

Abre http://localhost:8501. La app solo escucha en tu equipo.

- **Chat:** escribe una pregunta o usa uno de los ejemplos.
- **Fuente y criterio:** qué herramienta se usó, con qué fechas y cómo se calculó, en lenguaje humano.
- **Traza técnica:** desplegable con cada paso en orden y su duración (llamadas al modelo, herramientas, reintentos, cambios de proveedor, validaciones).
- **Aprobar y Rechazar:** si pides algo como "marca WhatsApp como no sirve", el coach propone la regla y solo se guarda en `data/reglas.json` si la apruebas.
- **Barra lateral:** proveedor activo (se cambia en vivo), interruptores de prueba y minutos por categoría de los últimos 7 días.

## Usar por consola
```powershell
.venv\Scripts\python producto\agente.py "¿A qué hora me distraigo más?"
.venv\Scripts\python producto\agente.py --traza "¿Cuántas alertas de postura tuve esta semana?"
```

`--traza` imprime la traza completa en JSON. Cada pregunta queda además en `traces/AAAA-MM-DD.jsonl`, que git ignora.

## Interruptores de prueba
Están en la barra lateral, y en consola con `--forzar-429`, `--forzar-timeout` y `--forzar-salida-invalida`. Los casos forzados no salen a la red.

| Interruptor | Qué pasa |
|---|---|
| 429, solo el activo | Reintenta tras 1, 2 y 4 s, pasa al respaldo y responde. La sesión sigue |
| 429, todos | Después de reintentar en ambos, da un mensaje honesto sin inventar |
| Timeout | Mensaje claro de que el proveedor no respondió en 20 s, sin stack trace |
| Salida inválida, una vez | El modelo recibe el error de validación, corrige los argumentos y responde |
| Salida inválida, siempre | Al segundo fallo responde en texto y el fallo queda en la traza |

## Límites del agente
- Máximo 6 vueltas del bucle por pregunta.
- Máximo 12 000 tokens por pregunta.
- `guardar_regla` necesita aprobación humana.
- 20 s por llamada al modelo y 5 s por herramienta.

Si se alcanza un límite, la respuesta lo dice. El porqué de cada uno está comentado en `producto/agente.py`.

## Pruebas
```powershell
.venv\Scripts\python -m unittest discover -s tests
```

Son 26 pruebas y no usan red ni llaves: un servidor falso en `127.0.0.1` imita al proveedor.

## Estructura
| Ruta | Qué es |
|---|---|
| `producto/datos.py` | Esquema SQLite: `sesiones` y `eventos`, sin lugar para títulos |
| `producto/generar_datos_demo.py` | 7 días demo con semilla 42 |
| `producto/herramientas.py` | Las 6 herramientas con parámetros validados; el modelo nunca escribe SQL |
| `producto/catalogo_pausas.json` | Catálogo fijo de pausas |
| `producto/proveedor.py` | `llamar_llm`: API compatible con OpenAI con urllib, reintentos y respaldo |
| `producto/agente.py` | El bucle del agente, sus límites y la consola |
| `producto/trazas.py` | Spans con duración en ms y archivo `traces/AAAA-MM-DD.jsonl` |
| `producto/app.py` | La app de Streamlit |
| `producto/verificar_modelos.py` | Prueba qué modelos del proveedor sirven con herramientas |
| `docs/PLAN-M2.md` | Plan del Momento 2 con su criterio de sí o no |
| `docs/decisiones/m2-decisiones.md` | Decisiones del Momento 2 y la renegociación del LLM en la nube |

## Si algo falla
| Mensaje | Qué hacer |
|---|---|
| "No hay proveedor de IA configurado" | Falta `.env` o `LLM_PROVIDER`; ver Instalación |
| "… rechazó la llave" | La llave de ese proveedor no es válida; revísala en `.env` |
| "Todavía no hay datos" o "No hay base de datos" | Corre `producto\generar_datos_demo.py` |
| "… está limitando las peticiones (429)" | Límite de la capa gratuita: espera un minuto o configura un respaldo |
| Un modelo deja de existir (404) | Corre `producto\verificar_modelos.py` y fija `LLM_MODEL` |

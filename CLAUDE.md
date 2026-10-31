# BioFocus

## Qué es esto

BioFocus es un monitor personal de salud, foco y espacio de trabajo para sesiones de estudio frente al computador.
La cámara (MediaPipe), el entorno y la actividad del computador se procesan con código y reglas en el equipo; un LLM solo decide si el título de la ventana activa sirve a la meta de la sesión.
Ninguna imagen ni audio se guarda ni sale del equipo.

## Cómo se corre

Desde la raíz, en PowerShell, con Python 3.13. Detalle en README.md.

- Entorno: `python -m venv .venv` y `.venv\Scripts\python -m pip install streamlit mediapipe==1.1.1` (`mediapipe` trae `opencv-contrib-python`; no instalar `opencv-python` aparte). Lo demás es librería estándar.
- Modelo de postura: `producto\modelos\pose_landmarker_lite.task` (git lo ignora; SHA-256 en `docs\decisiones\experimento-01.md`, el monitor lo verifica).
- Llaves: copiar `.env.example` a `.env` y llenar `LLM_PROVIDER` y `LLM_API_KEY` (respaldo opcional con `LLM_FALLBACK_*`). Nunca leer ni mostrar `.env`.
- Datos demo: `.venv\Scripts\python producto\generar_datos_demo.py` (7 días que terminan ayer, semilla 42, en `data/biofocus.sqlite`).
- App: `.venv\Scripts\python -m streamlit run producto\app.py` (http://localhost:8501). «Iniciar sesión» lanza el monitor y el panel en vivo se actualiza cada 2 s.
- Monitor por terminal: `.venv\Scripts\python producto\monitor.py --meta "texto" --duracion 3 --modo-demo` (`--video grabaciones\encorvado.mp4` es el plan B sin cámara; `c` recalibra y `q` termina).
- Probar el monitor con los videos, sin ventana y sin mandar títulos a Groq: `$env:LLM_CLASIFICADOR_PROVIDER="ninguno"` y luego `.venv\Scripts\python producto\monitor.py --meta "prueba" --modo-demo --video grabaciones\derecho.mp4 --sin-ventana --detalle --bd $env:TEMP\prueba.sqlite`.
- Consola: `.venv\Scripts\python producto\agente.py "¿a qué hora me distraigo más?"` (con `--traza` imprime el JSON).
- Pruebas, sin red ni llaves: `.venv\Scripts\python -m unittest discover -s tests`.
- Modelos con herramientas: `.venv\Scripts\python producto\verificar_modelos.py`.
- Evaluación (12 casos, usa el proveedor; unos 20 min con 3 corridas, 28 s entre preguntas): `.venv\Scripts\python producto\evals\correr_evals.py --corridas 3`. Con `--solo-sql` muestra la respuesta esperada de cada caso sin llamar al modelo.
- Trazas: `traces/AAAA-MM-DD.jsonl` (git las ignora).

## Convenciones

PENDIENTE

## Qué NO hacer

- No leas, muestres ni hagas commit de .env ni de ninguna llave.
- BioFocus nunca graba ni guarda imágenes, video o audio durante una sesión, ni siquiera para depurar.
- Los videos de prueba los grabo yo, a propósito y fuera de BioFocus. Viven en grabaciones/, que git ignora, y el producto solo los lee para las pruebas de cámara y el plan B de la demo. Nunca se suben al repositorio.
- No envíes imágenes ni audio a ningún modelo ni servicio externo.
- No inventes diagnósticos ni recomendaciones de salud.
- No instales dependencias sin preguntar.
- No escribas código del producto sin una tarea aprobada en docs/PLAN.md.
- Si una decisión no está en docs/SPEC.md, para y pregunta.
- No hagas commit sin que verifiquemos el criterio de la tarea.

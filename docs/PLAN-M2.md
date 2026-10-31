# Plan · Momento 2 · Coach de BioFocus
Tareas aprobadas por dos instrucciones del 2026-10-29 (1 a 7: el coach; 8 a 12: medición y documentos). Decisiones menores en `docs/decisiones/m2-decisiones.md`.

1. Datos (`producto/datos.py`, `generar_datos_demo.py`). ¿`data/biofocus.sqlite` queda con 7 días demo (semilla 42), idéntica en dos corridas y sin columna para títulos?
2. Herramientas (`producto/herramientas.py`, `catalogo_pausas.json`). ¿Las 6 responden con los datos demo, rechazan argumentos inválidos y `guardar_regla` no escribe sin aprobación? → commit y push
3. Proveedor (`producto/proveedor.py`). ¿`llamar_llm` obtiene una llamada a herramienta del proveedor de `.env`, y los 429, timeout y salida inválida forzados terminan en reintento, respaldo o mensaje claro, nunca en un stack trace?
4. Agente (`producto/agente.py`). ¿Responde con datos de las herramientas y cada límite (6 iteraciones, 12 000 tokens, aprobación, 20 s / 5 s) corta con un aviso en la respuesta? → commit y push
5. Trazas (`producto/trazas.py`). ¿Cada pregunta deja sus spans en orden, con duración en ms, en `traces/AAAA-MM-DD.jsonl`, y git ignora `traces/`?
6. App (`producto/app.py`, Streamlit en `.venv`). ¿En el navegador funcionan chat, "Fuente y criterio", traza, Aprobar/Rechazar, cambio de proveedor, interruptores y minutos por categoría? → commit y push
7. Docs y prueba (`README.md`, "Cómo se corre"). ¿Otra persona puede correrlo con el README, y 3 preguntas reales responden con su traza? → commit y push
8. Suite (`producto/evals/`). ¿Hay 12 casos con invariante, herramientas requeridas y respuesta esperada por SQL aparte, con 2 de rechazo, 1 de inyección y 1 de regla pendiente? → commit y push
9. Medición (`docs/decisiones/semana10.md`). ¿Tres corridas dan tasa de éxito, costo por tarea, latencia mediana y p90 y recuperación, y cada fallo se explica con su traza? → commit y push
10. Estrategia de datos (`docs/decisiones/semana08.md`). ¿Explica SQL parametrizado sin RAG y por qué se descartan RAG, SQL libre y la base en el contexto? → commit y push
11. Errores (`docs/decisiones/m2-errores.md`). ¿Los tres errores forzados tienen lo que se ve en pantalla y su traza? → commit y push
12. Prueba del compañero (`docs/decisiones/prueba-companero.md`). ¿La plantilla pide quién, qué intentó, dónde se trabó y qué cambié? → commit y push

Tareas aprobadas por la instrucción del 2026-10-31 (demo en vivo):

13. Monitor (`producto/monitor.py`, `ventanas.py`, `vivo.py`, `reglas.json`). ¿Con `--video` en modo demo, `derecho.mp4` no alerta, `encorvado.mp4` alerta la postura y cada sesión deja sus eventos y `fin_sesion` en SQLite, sin guardar imágenes ni títulos? → commit y push
14. Dashboard en vivo (`producto/app.py`). ¿Iniciar y Terminar lanzan y detienen el monitor, el panel se actualiza cada 2 s y el coach responde sobre la sesión en curso con la fecha real? → commit y push
15. Prueba de 3 minutos y documentación (`README.md`, `CLAUDE.md`). ¿La guía provoca cada alerta en una sesión real en modo demo? → commit y push

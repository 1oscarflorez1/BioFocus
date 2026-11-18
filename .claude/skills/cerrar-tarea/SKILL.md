---
name: cerrar-tarea
description: Cierra una tarea del plan de BioFocus (docs/PLAN-M3.md) - pruebas, criterio verificado con evidencia, decisión anotada, citas de los documentos al día, commit y push. Úsalo al terminar cada tarea del plan, antes del commit.
---

# Cerrar una tarea de BioFocus

Creado el 2026-11-18 (tarea F3). Junta los pasos que se venían haciendo a mano en cada bloque del Momento 3.

## Pasos
1. **Ubica la tarea** en `docs/PLAN-M3.md` y lee su pregunta de sí o no. Si la tarea no está aprobada, para y pregunta.
2. **Pruebas sin red:** `.venv\Scripts\python -m unittest discover -s tests`. Todas deben pasar. Si una prueba cambia a propósito (porque cambió el comportamiento), dilo en el paso 4.
3. **Verifica el criterio con evidencia, no con lectura del código.** Elige lo que aplique:
   - **Monitor:** los tres videos sin ventana ni Groq. Primero `$env:LLM_CLASIFICADOR_PROVIDER="ninguno"`, y luego `producto\monitor.py --meta "prueba" --modo-demo --video grabaciones\<video>.mp4 --sin-ventana --bd $env:TEMP\prueba.sqlite`. `derecho` y `distraido` no alertan; `encorvado` alerta una vez, hacia los 16 s.
   - **App:** cárgala sin navegador con `streamlit.testing.v1.AppTest` (sin excepciones) o ábrela con la vista previa, sin empezar sesiones que enciendan la cámara si nadie lo pidió.
   - **Coach:** `producto\evals\correr_evals.py --solo-sql` no llama al modelo. Las corridas reales usan cuota y tardan.
   - **Seguridad:** `producto\evals\ataques.py`. Primero el ataque, después el arreglo, y otra vez el ataque.
   - **Nunca** con `data/` real: usa bases temporales.
4. **Anota las decisiones** que tomaste sin preguntar en `docs/decisiones/m3-decisiones.md`, con el porqué y cómo lo verificaste. Lo que no se verificó se dice.
5. **Citas al día:** `.venv\Scripts\python .claude\skills\cerrar-tarea\verificar_citas.py` debe dar 0 malas. Si la tarea arregla un hallazgo, actualiza `docs/respuesta_auditoria.md` con el commit.
6. **Commit** con el formato «Momento 3, bloque X: qué cambió» y la línea `Co-Authored-By` que corresponda. Nunca `.env`, `data/`, `traces/` ni `grabaciones/`: revísalo con `git status --short` antes del commit.
7. **Push** a `origin/main` y marca la tarea como hecha en el resumen del bloque.

## Qué no hace
- No aprueba tareas: las aprueba la persona.
- No reemplaza la prueba con una persona ajena (`docs/decisiones/prueba-companero.md`).

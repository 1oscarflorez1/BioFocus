# Entrega del Momento 3 · Responder por lo construido

Índice para quien evalúa: cada entregable y cada criterio de la rúbrica llevan a su archivo y a la evidencia que lo respalda. El repositorio es la evidencia y la sustentación es la evaluación. El guion de la presentación está en `docs/sustentacion.md`.

Fecha: 2026-11-20. Trabajo individual, con aval del docente como excepción (`docs/SPEC.md`, encabezado).

## Entregables
| Entregable | Formato | Dónde | Qué mirar primero |
|---|---|---|---|
| El producto completo, corriendo | Aplicación | `producto/`; cómo se corre en `README.md`, sección «Usar la app»; doble clic en `BioFocus.bat` | La app en cuatro pestañas (Sesión, Coach, Mis registros y Ajustes), el monitor con su aviso emergente y 104 pruebas sin red: `.venv\Scripts\python -m unittest discover -s tests` |
| Modelo de amenazas y hardening aplicado | `docs/` | `docs/seguridad.md`, secciones 1, 2 y 4 | Las cinco preguntas del modelo de amenazas, la tríada del coach y del clasificador, y la tabla de antes y después de cinco controles |
| Prueba de inyección contra el propio agente, documentada | `docs/` | `docs/seguridad.md`, sección 3; `producto/evals/ataques.py`; resultados en `producto/evals/resultados/ataques-*.json` | El ataque que funcionó (`imagen_markdown`, 3/3, traza `6ff67bd00129`), el arreglo en el código y el mismo ataque después, también sin la regla del prompt (traza `2c2499dddcaa`) |
| Ficha de gobernanza del producto | `docs/` | `docs/gobernanza.md` | Qué decide solo, qué exige a un humano (con la línea de código), qué queda registrado y por cuánto tiempo, y qué se hace ante un incidente |
| Cifras finales comparadas contra la línea base | `docs/` | `docs/decisiones/semana14.md`, frente a `docs/decisiones/semana10.md` | Las cuatro cifras, qué cambió y por qué, y cada fallo con su traza |
| Demo en vivo ante el curso | Presentación | `docs/sustentacion.md` | Guion de 15 minutos en el orden de la semana 13, plan B sin internet y respuestas a las preguntas de la rúbrica |

## Criterios
| Criterio | Puntos | Evidencia |
|---|---|---|
| **Producto terminado:** corre en vivo | 25 | `README.md` y la lista «Antes de entrar» de `docs/sustentacion.md`. Plan B sin cámara (`grabaciones/encorvado.mp4`) y sin internet (Ollama, `OFFLINE_MODE=true`, 34/36 en `semana14.md`) |
| **Producto terminado:** lo usa alguien ajeno | | `docs/decisiones/prueba-companero-2026-11-20.md`. Lo logró en parte: no vio las alertas ni encontró sus registros. Lo que falló se arregló en el bloque I (`docs/PLAN-M3.md`), con su verificación en la misma prueba («Qué cambié») |
| **Producto terminado:** cumple el alcance de la spec | | `docs/SPEC.md`: objetivos con su estado (sección 2) y la tabla de renegociación con el porqué de lo que no se hizo (sección 7) |
| **Seguridad:** modelo de amenazas | 20 | `docs/seguridad.md`, sección 1 |
| **Seguridad:** permisos reducidos | | Base en solo lectura para el coach, consultas fijas sin SQL del modelo y nombres de app con alfabeto cerrado (`docs/seguridad.md`, sección 4). Permisos de Claude Code en `.claude/settings.json` y `docs/decisiones/permisos.md` |
| **Seguridad:** secretos fuera del código | | `.env` en `.gitignore` y `.env.example` sin llaves. Las llaves expuestas en octubre se cambiaron el 2026-11-13, y se revisó que no estén en git, `traces/`, `data/` ni en los resultados (`docs/seguridad.md`, fila «Secretos») |
| **Seguridad:** prueba de inyección con su resultado | | `docs/seguridad.md`, sección 3, con los ataques que fallaron completos y el del clasificador que se asume |
| **Gobernanza** | 20 | `docs/gobernanza.md`. La supervisión que el código exige: `agente.py:332`, `herramientas.py:494`, `app.py:715` (Aprobar) y `app.py:587` (Borrar) |
| **Medición final** | 15 | `docs/decisiones/semana14.md`: 36/36 y 27/27 iguales; costo +10 % y mediana +139 ms, por la séptima herramienta y dos reglas del prompt. El bloque I no tocó el coach, así que las cifras valen para el código entregado |
| **Sustentación** | 20 | `docs/sustentacion.md`: respuestas con su evidencia, incluidas las incómodas, y la explicación de cada función clave |

## Errores frecuentes, revisados uno por uno
| Error que cuesta puntos | Cómo está en BioFocus |
|---|---|
| Presentar un producto distinto al declarado en la spec | La spec junta lo declarado (propuesta del Momento 1 y specs por incremento) y renegocia por escrito lo que no se hizo, con su porqué (`docs/SPEC.md`, sección 7) |
| Ficha de gobernanza escrita la noche anterior, sin relación con el sistema real | Cada respuesta cita `archivo.py:línea`. `.claude/skills/cerrar-tarea/verificar_citas.py` revisa todas las citas en cada commit. La ficha es del 2026-11-17 y se revisó con cada cambio (historia de git) |
| No haber corrido la prueba de inyección contra el propio agente | Corridas reales contra el proveedor, 3 por ataque, antes y después del arreglo, con sus JSON en `producto/evals/resultados/` |
| Cifras finales sin comparar contra la línea base | `semana14.md` compara las cuatro cifras con `semana10.md`, con el mismo método, y reporta el modo local aparte |
| Esconder los fallos en vez de explicarlos | Están escritos: el ataque que funcionó 3/3 antes del arreglo; 3 de 5 títulos nuevos engañan al clasificador (se asume, `seguridad.md`); el experimento 02 de la cámara lateral no cumplió (`experimento-02.md`); la prueba con una persona ajena falló en las alertas; la auditoría cruzada no se hizo (`respuesta_auditoria.md`); el modo discreto B5 quedó cubierto recién con el bloque I |

## Lo que falta antes de presentar
- Repetir la prueba con una persona ajena con la app nueva (es el ensayo de la demo).
- La noche anterior: los pasos de «Antes de entrar» en `docs/sustentacion.md`.

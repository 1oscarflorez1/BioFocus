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

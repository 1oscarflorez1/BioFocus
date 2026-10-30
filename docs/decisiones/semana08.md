# Semana 8 · Estrategia de datos del coach

Fecha: 2026-10-29.

## Decisión
El coach consulta los datos con **herramientas SQL parametrizadas sobre SQLite, sin RAG ni embeddings**. El modelo solo elige una de las seis herramientas de `producto/herramientas.py` y sus argumentos (fechas, tipo de alerta, cuántas apps, motivo de la pausa o app y categoría). El código valida esos argumentos, ejecuta una consulta fija con parámetros `?` sobre una conexión de solo lectura y devuelve cifras agregadas en JSON. El modelo redacta la respuesta con esas cifras, y "Fuente y criterio" la arma el código, no el modelo.

```
pregunta → el modelo elige herramienta y argumentos → validación → consulta fija, en solo lectura
         → cifras agregadas en JSON → el modelo redacta → "Fuente y criterio" desde el código
```

## Por qué
- **Los datos son tablas.** `sesiones` y `eventos` tienen hora, tipo, app, categoría y duración. Las preguntas piden contar, sumar, sacar porcentajes y buscar máximos por rango de fechas o por hora del día, y eso SQL lo hace exacto.
- **Se necesitan números exactos.** "¿Cuántas alertas de postura tuve esta semana?" tiene una sola respuesta correcta: 7, no "unas 7". El SQL la calcula y el modelo solo la cuenta en palabras. La suite de evaluación (`producto/evals/`) compara cada número con un SQL escrito aparte del código de las herramientas.
- **El volumen es pequeño.** La demo tiene 16 sesiones y 255 eventos en 7 días. Al mismo ritmo, un año serían unas 830 sesiones y 13 300 eventos. En las trazas, cada herramienta tarda entre 2 y 30 ms. No hace falta un índice vectorial ni un servidor.
- **Se sabe qué sale del equipo.** Con consultas fijas, lo que llega al proveedor es exactamente lo que devuelve cada herramienta: cifras, nombres de app y categorías. La meta de la sesión se queda en el equipo porque ninguna consulta la devuelve.
- **Se puede explicar y probar.** Cada herramienta tiene un criterio en lenguaje humano, que es el que muestra "Fuente y criterio", y pruebas con argumentos válidos e inválidos.

## Alternativas descartadas

### RAG con vectores
Embeddings de los eventos, o de resúmenes por sesión, en un índice vectorial, y recuperar los fragmentos más parecidos a la pregunta.

- **No cuenta ni suma.** RAG recupera fragmentos *parecidos*. Para "¿cuántas alertas tuve esta semana?" tendría que recuperar todas las alertas de la semana y que el modelo las cuente, y recuperar "las más parecidas" no garantiza traerlas todas. Las preguntas del coach son agregaciones por rango de fechas, no búsquedas de texto.
- **No hay texto que buscar.** Los eventos son campos cortos y fijos; justamente no guardamos títulos de ventana.
- **Agrega piezas.** Un modelo de embeddings, un índice que hay que mantener sincronizado con SQLite y una dependencia más. Si los embeddings se calcularan en la nube, saldrían más datos del equipo.
- **Cuándo lo reconsideraría:** si BioFocus llegara a guardar texto libre de la persona, como notas o reflexiones al cerrar la sesión, RAG serviría para ese texto, nunca para las cifras.

### SQL libre generado por el modelo
El modelo recibe el esquema y escribe la consulta (text-to-SQL).

- **Consultas destructivas.** Un error o una instrucción maliciosa produce `DELETE`, `DROP` o `UPDATE`. La conexión de solo lectura lo frenaría, pero el riesgo queda en el diseño.
- **Inyección.** Un texto dentro de los datos, como el nombre de una app, o dentro de la pregunta puede llevar al modelo a escribir otra consulta. Con herramientas fijas, lo peor que logra es elegir otra herramienta u otras fechas, y eso se valida.
- **Puede leer lo que no debe salir.** Con SQL libre, nada impide `SELECT meta FROM sesiones`, y entonces la meta saldría hacia el proveedor.
- **Es más difícil de validar y de explicar.** Habría que analizar SQL arbitrario para revisar rangos y costo, y "Fuente y criterio" no podría decir en lenguaje humano qué se calculó.
- **Es más frágil.** Los modelos se equivocan con fechas, zonas horarias y JOINs. Un argumento de fecha mal escrito se valida fácil; una consulta mal escrita devuelve un número incorrecto que parece correcto.

### Pasar toda la base en el contexto
Poner todas las sesiones y eventos en el prompt y dejar que el modelo responda.

- **Costo.** Los 7 días de la demo en JSON son 35 814 caracteres, unos 10 200 tokens, en *cada* pregunta. Un mes serían unos 44 000 tokens y un año unos 534 000, más que la ventana de contexto de 131 072 tokens de `openai/gpt-oss-120b`. Hoy una pregunta usa entre 1 600 y 4 000 tokens con herramientas.
- **Cuota.** La capa gratuita de Groq permite 8 000 tokens por minuto (cabecera `x-ratelimit-limit-tokens`), así que una sola pregunta con la semana completa ya la supera. Además choca con el límite de 12 000 tokens por pregunta del agente.
- **Exactitud.** El modelo tendría que sumar cientos de filas de cabeza, que es justo lo que hace mal.
- **Privacidad.** Saldría todo, metas incluidas, en vez de solo los agregados que pide cada pregunta.

## Cómo se mide que funciona
La suite de `producto/evals/` (12 casos, semana 10) verifica que los números de la respuesta coincidan con SQL independiente, que el agente llame las herramientas requeridas y que no invente cuando los datos no alcanzan. Los resultados están en `docs/decisiones/semana10.md`.

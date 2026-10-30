# Exploración · Momento 1

Equipo de desarrollo y demo: Windows 11 Home, 23 GB de RAM, AMD Ryzen AI 5 340 (Radeon 840M), cámara HP True Vision FHD, Python 3.13 (`python`) y 3.14 (`py` por defecto), Node 26, sin Ollama.

## Decididas
- Ningún LLM mira la cámara ni escucha el micrófono. La visión va con MediaPipe y umbrales, en el equipo.
- Al LLM solo llega texto: la meta y el título de una ventana ambigua.
- Los títulos privados (correo, banco) nunca salen del equipo.
- No se guardan imágenes, video ni audio; solo eventos.
- No diagnostica: genera autoconciencia.
- Costo cero: capa gratuita sin tarjeta o modelo local.
- Trabajo individual.
- Demo en vivo de unos dos minutos, con plan B sin internet.
- Plan B de cámara con video grabado: BioFocus lee un video de prueba de `grabaciones/` en vez de la cámara en vivo.
  - Cambio: salió de "Fuera de alcance", donde lo bloqueaba la regla de no guardar video; en CLAUDE.md esa regla se dividió en dos: BioFocus nunca graba en una sesión, y los videos de prueba se graban fuera de BioFocus.
- Alcance mínimo del Momento 1:
  - Check-in con la meta de la sesión.
  - Título de la ventana activa clasificado con reglas; un LLM decide solo lo ambiguo.
  - Alerta de postura frente a una línea base.
- Si alcanza el tiempo (condicional, no comprometido): alerta de mirada fuera de la pantalla, recordatorio de pausa y línea de tiempo de la sesión.

## Fuera de alcance (y por qué)
- Hábitos de cara y manos, escritorio y ruido, informe diario y coach con herramientas: son del Momento 2 y requieren el modelo de eventos del Momento 1 ya estable.
- Cámara lateral, ritmo de tecleo, dashboard semanal, seguridad y gobernanza: son del Momento 3.
- Parpadeo, bostezos, ojos cerrados, distancia a la pantalla y mirada al celular: no están en el mínimo; cada uno es otro detector con sus propios umbrales.
- Aceleración con NPU o GPU: el volumen de procesamiento (~10 cuadros por segundo) no la necesita.
- Interfaz web o Electron: más piezas y dos runtimes para un solo desarrollador; se reconsidera para el dashboard del Momento 3.

## Hay que probar o preguntar

### Decisiones abiertas (antes de la spec)
- **Decide la arquitectura: LLM local o en la nube.** De ella dependen el filtro de privacidad, el plan B sin internet, el costo y la latencia. Propuesta: solo local (Ollama con un modelo de ~3B en CPU).
- **La que más arrastra: forma del evento y de la meta.** Reglas, ambigüedad, prompt, alertas y línea de tiempo dependen de ellas.
- Forma de la app. Propuesta: un proceso Python con Tkinter y notificaciones de Windows.
- Canal de la alerta: notificación, sonido, ventana superpuesta o banner propio.
- Mostrar o no el video en vivo (sin guardarlo).
- Qué se muestra al cerrar la sesión si no alcanza la línea de tiempo.
- Formato de la meta: texto libre, palabras clave o categoría.
- Qué pide el check-in además de la meta: duración, intervalo de pausa, postura activada o no.
- Qué se lee de la ventana: solo título, o título más nombre del proceso.
- Formato de las reglas y quién las escribe.
- Definición de "ambiguo": en el navegador casi todo lo es.
- Detección de títulos privados: lista negra o lista blanca. Un título privado y ambiguo queda "sin clasificar, sin alerta".
- Frecuencia de lectura de la ventana, tiempo mínimo antes de alertar y cooldown entre alertas.
- Modelo del LLM, tiempo máximo, caché por título y comportamiento si falla (propuesta: "ambiguo", sin alerta).
- Salida del LLM: binaria o con una razón corta.
- Modelo de MediaPipe para postura: Pose o Face Landmarker.
- Métrica de postura frente a la línea base: cabeza más baja, cara más cerca, hombros caídos o inclinación lateral.
- Calibración de la línea base (¿5 a 10 s al empezar?) y recalibración.
- Umbral, tiempo sostenido, histéresis y cooldown de la alerta de postura.
- Qué pasa si el usuario sale de cuadro o hay poca luz.
- Redacción de las alertas sin tono de diagnóstico.
- Almacenamiento de eventos (SQLite o JSONL), retención y borrado.
- Criterio de corte del alcance condicional.
- Guion de la demo: cómo se provoca cada alerta en vivo.
- Pruebas de postura sin imágenes (propuesta: puntos clave sintéticos).
- Dependencias aprobadas: mediapipe, opencv-python, psutil, cliente de Ollama, notificaciones.

### Hay que preguntar
- Fecha de la demo (sin ella no se puede fijar el corte).
- Lugar de la demo: luz, proyector, internet, monitor externo.
- Si el curso exige LLM en la nube o un "agente".
- Apps y sitios que se usan de verdad al estudiar.
- Qué se considera privado.
- Canal de alerta preferido.
- Si se acepta mostrar el video en vivo.

### Hay que probar en el equipo
- Que MediaPipe se instale en Python 3.13 en Windows (3.14 probablemente no tiene versión).
- Cuadros por segundo y CPU en el Ryzen AI 5 340.
- Que la cámara del portátil vea los hombros.
- Que OpenCV abra la cámara (Teams, permisos de privacidad de Windows).
- Títulos que devuelven Chrome, las apps de la Tienda y las apps como administrador.
- Latencia y calidad del modelo local en Ollama.
- Que las notificaciones aparezcan con "No molestar" activo.

### Stack propuesto (pendiente de aprobar)
| Pieza | Propuesta |
|---|---|
| Lenguaje | Python 3.13 en `.venv` |
| Visión | MediaPipe Tasks (Pose Landmarker lite o Face Landmarker) y OpenCV, ~10 cuadros por segundo |
| Ventana activa | `ctypes` con la API de Windows y `psutil` para el proceso |
| LLM | Ollama con un modelo de ~3B (por ejemplo, Qwen2.5 3B instruct), salida JSON y caché |
| Eventos | SQLite |
| Interfaz y alertas | Tkinter y notificaciones de Windows, un solo proceso con hilos |

Descartadas: Electron o web con MediaPipe JS (necesita módulo nativo para la ventana y suma un runtime); LLM en la nube como principal (internet, límites de uso, títulos fuera del equipo, y el plan B local hace falta igual); FastAPI con interfaz web (más piezas de las que pide el Momento 1).

## Riesgo técnico a probar primero
- **Señal de postura de punta a punta con la cámara del portátil.** Es lo que más puede fallar (instalación, rendimiento y calidad de la señal); ventanas y LLM tienen fallbacks fáciles.
- Prueba de máximo una hora, con un script desechable fuera de `producto/` y sin guardar ningún cuadro:
  1. Crear un `.venv` con Python 3.13 e instalar `mediapipe` y `opencv-python` (requiere aprobación).
  2. Abrir la cámara, correr Pose y Face Landmarker y calibrar una línea base de 5 s.
  3. Imprimir solo números: cuadros por segundo, CPU y desviación frente a la línea base sentado bien, encorvado y acercándose.
- Criterio de éxito:
  - Se instala sin conflictos.
  - 10 o más cuadros por segundo con menos de ~25 % de CPU.
  - La diferencia entre bien y encorvado es al menos 3 veces el ruido.
- Si Pose no ve los hombros, la postura se basa en la cara y eso cambia la spec.
- Riesgo secundario (unos 20 minutos): latencia de Ollama.

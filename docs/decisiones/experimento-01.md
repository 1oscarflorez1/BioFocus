# Experimento 01 · Ventana activa y postura con la cámara

Fecha: 2026-10-24. Scripts desechables, fuera de `producto/`: `experimentos/ventana_activa.py` y `experimentos/postura_camara.py`. Ninguno guarda imágenes, video ni títulos en disco.

## Qué se probó
- **Ventana activa:** leer el título de la ventana en primer plano con `ctypes` y la API de Windows (`GetForegroundWindow`, `GetWindowTextW`), cada 2 s durante 60 s, solo con la librería estándar.
- **Postura:** abrir la cámara con OpenCV, correr MediaPipe Pose Landmarker lite en modo video e imprimir una vez por segundo los cuadros por segundo y este número:

  `postura = (y_medio_hombros − y_nariz) / ancho_hombros` (en píxeles; baja al encorvarse)

  Se midieron cuatro tramos: sentado derecho (20 s), encorvado (20 s), cerca de la pantalla y de vuelta a sentado.

Diferencias con el plan de la exploración:
- Solo se corrió Pose Landmarker; Face Landmarker no se probó.
- No hubo calibración automática de 5 s: la línea base se leyó a mano de los números impresos.
- El script muestra la imagen en vivo con los puntos dibujados (sin guardarla); el plan decía imprimir solo números.

## Equipo y versiones
| Pieza | Valor |
|---|---|
| Sistema | Windows 11 Home (10.0.26200) |
| Procesador | AMD Ryzen AI 5 340 con Radeon 840M |
| Memoria | 23 GB |
| Cámara | HP True Vision FHD; OpenCV la abre con el backend MSMF a 640×480 |
| Python | 3.13.15 en `experimentos/.venv` |
| MediaPipe | 1.1.1 |
| OpenCV | `opencv-contrib-python` 5.0.0.93 (llega como dependencia de `mediapipe`) |
| NumPy | 2.5.4 |
| Modelo | `pose_landmarker_lite.task`, float16, 5 777 746 bytes |

Solo se instaló `mediapipe`; lo demás son sus dependencias (`opencv-contrib-python`, `numpy`, `matplotlib`, `sounddevice`, `absl-py`, `flatbuffers`, `certifi`). `pip check` no encontró conflictos. `sounddevice` es una librería de audio que trae `mediapipe`; los scripts no la usan.

## Resultados

### Ventana activa
Un título cada 2 s durante 60 s. Títulos vistos:
- `Windows PowerShell`
- `Claude`
- `Dashboard | Claude Platform - Opera`
- `Nueva pestaña - Google Chrome`
- `Untitled-1 - Visual Studio Code`, y con texto sin guardar: `● dafaslfdslgfdslkgdslkg • Untitled-1`
- `Conmutación de tareas` (durante el Alt+Tab)

### Cámara: cuadros por segundo y CPU
- Unos 30 cuadros por segundo estables; el primer segundo, 10,8 (arranque).
- El script procesa todos los cuadros que entrega la cámara: el techo de 30 lo pone la cámara, no MediaPipe.
- CPU: 4 % (observada durante la corrida; el script no la mide).
- Hombros visibles todo el tiempo.

### Número de postura
| Tramo | Rango | Típico | Frente a derecho |
|---|---|---|---|
| Sentado derecho, 20 s | 0,536 – 0,545 | 0,54 | — |
| Encorvado, 20 s | 0,302 – 0,328 | 0,31 | −43 % |
| Cerca de la pantalla | 0,211 – 0,235 | 0,22 | −59 % |
| De vuelta a sentado | 0,45 – 0,47 | 0,46 | −15 % |

La variación estando quieto se midió como máximo menos mínimo en el tramo, que es más exigente que la desviación estándar.

## Qué funcionó
- Leer el título de la ventana activa sin dependencias, también en Opera y Chrome.
- Instalar `mediapipe` 1.1.1 en Python 3.13 en Windows, sin conflictos.
- Abrir la cámara con OpenCV (MSMF) sin problemas de permisos.
- Pose Landmarker lite a ~30 cuadros por segundo con 4 % de CPU.
- La señal separa derecho de encorvado: 0,23 de diferencia contra una variación de 0,026 estando quieto, unas 9 veces. Aun entre los extremos de los rangos (0,536 contra 0,328) la separación es unas 8 veces la variación.

## Qué falló o no salió como se esperaba
- **Los títulos pueden filtrar contenido.** VS Code puso en el título el texto de un archivo sin guardar. Un título no es solo "app y documento": puede traer lo que la persona está escribiendo.
- **Ventanas de paso.** `Conmutación de tareas` aparece durante el Alt+Tab: hace falta un tiempo mínimo en una ventana antes de contarla.
- **Títulos sin información.** `Nueva pestaña - Google Chrome` no dice nada de la tarea.
- **Títulos en español.** Windows nombra sus ventanas en el idioma del sistema; las reglas no pueden suponer textos en inglés.
- **La métrica no distingue encorvado de cerca.** Las dos bajan el número; acercarse lo baja más que encorvarse.
- **No se vuelve a la línea base.** Al volver a sentarse quedó en 0,45–0,47, no en 0,54: 0,08 menos, un tercio de la distancia entre derecho y encorvado. Un umbral fijo no sirve; tiene que ser relativo a una línea base calibrada, con recalibración. No se midió si cambió la postura o la posición frente a la cámara.
- **Arranque lento.** El primer segundo va a 10,8 cuadros por segundo; la calibración no debe usar ese tramo.
- **Advertencia de MediaPipe** al arrancar: `Using NORM_RECT without IMAGE_DIMENSIONS`. No afecta la medición; ver abajo.

## La advertencia "Using NORM_RECT without IMAGE_DIMENSIONS"
Texto completo: `Using NORM_RECT without IMAGE_DIMENSIONS is only supported for the square ROI. Provide IMAGE_DIMENSIONS or use PROJECTION_MATRIX.`

**No afecta esta medición.** Por qué:
- Sale de `landmark_projection_calculator.cc`, dentro de `libmediapipe.dll` (verificado en el binario instalado). Ese paso lleva los puntos desde el recorte donde MediaPipe busca a la persona de vuelta a la imagen completa, en coordenadas de 0 a 1.
- Sin las dimensiones de la imagen, el giro del recorte se aplica en coordenadas de 0 a 1, y eso solo es exacto si el recorte es cuadrado en píxeles. Si el recorte no está girado, la cuenta es exacta con cualquier forma.
- Sentado de frente a la cámara, el recorte casi no gira, así que el error es casi nulo. Además, MediaPipe arma el recorte de pose cuadrado (es como está diseñado; no lo verifiqué en el código de la 1.1.1).
- La métrica se compara contra la línea base de la misma persona con la misma cámara: un sesgo constante se cancela.
- Podría pesar con la cabeza o el torso muy inclinados hacia un lado, que no es lo que mide esta alerta.
- Para cerrarlo del todo (unos 5 minutos, no hace falta ahora): rellenar el cuadro a 640×640 con franjas negras antes de `detect_for_video` y comparar los números con los de esta corrida.
- No encontré una explicación oficial de Google.

## MediaPipe 1.1.1 ya no trae la API vieja
- El paquete solo trae `mediapipe.tasks` (y `modules`); `mp.solutions` no existe: `hasattr(mp, "solutions")` da `False`.
- Todo lo que use `mp.solutions.pose`, `mp.solutions.face_mesh` o `mp.solutions.drawing_utils`, como la mayoría de los tutoriales, no corre con esta versión.
- Hay que usar MediaPipe Tasks: `mediapipe.tasks.python.vision.PoseLandmarker` con un archivo `.task` que se descarga aparte. El modelo no viene con el paquete.
- Los índices de los puntos están en `vision.PoseLandmark` y las conexiones para dibujar en `vision.PoseLandmarksConnections`.

## Cómo se reproduce
Desde la raíz del repo, en PowerShell (`python` es 3.13 en este equipo):

```powershell
python -m venv experimentos\.venv
experimentos\.venv\Scripts\python -m pip install mediapipe
```

Descargar el modelo (no va al repo: `experimentos/modelos/` está en `.gitignore`):

```powershell
New-Item -ItemType Directory -Force experimentos\modelos
curl.exe -L -o experimentos\modelos\pose_landmarker_lite.task https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task
Get-FileHash experimentos\modelos\pose_landmarker_lite.task
```

SHA-256 del modelo usado: `59929E1D1EE95287735DDD833B19CF4AC46D29BC7AFDDBBF6753C459690D574A`. La URL termina en `latest`: si Google publica otra versión, el hash cambia.

Correr:

```powershell
experimentos\.venv\Scripts\python experimentos\ventana_activa.py
experimentos\.venv\Scripts\python experimentos\postura_camara.py
```

El segundo se cierra con la tecla `q`.

## Comparación con el criterio de éxito
| Criterio de la exploración | Resultado | ¿Cumple? |
|---|---|---|
| Se instala sin conflictos | `mediapipe` 1.1.1 en Python 3.13.15; `pip check` limpio | Sí |
| 10 o más cuadros por segundo con menos de ~25 % de CPU | ~30 cuadros por segundo con 4 % de CPU | Sí, con margen |
| Diferencia entre bien y encorvado de al menos 3 veces el ruido | Unas 9 veces | Sí |
| Pose ve los hombros | Visibles todo el tiempo | Sí: la postura no tiene que basarse en la cara |

Estado de "Hay que probar en el equipo":
- Probado: MediaPipe se instala en Python 3.13 en Windows.
- Probado: cuadros por segundo y CPU en el Ryzen AI 5 340.
- Probado: la cámara del portátil ve los hombros.
- Probado: OpenCV abre la cámara.
- Parcial: títulos de Chrome (y de Opera). Faltan las apps de la Tienda y las apps como administrador.
- Pendiente: latencia y calidad del modelo local en Ollama.
- Pendiente: notificaciones con "No molestar" activo.

## Qué cambia para la spec
`docs/SPEC.md` todavía no existe; esto actualiza las decisiones abiertas de `exploracion.md`. Nada queda decidido hasta que se escriba en la spec.

### Quedan respaldadas por evidencia
- **Modelo de postura: Pose Landmarker lite.** Ve los hombros y separa derecho de encorvado. Face Landmarker queda como respaldo, sin probar.
- **MediaPipe Tasks, no `mp.solutions`.** El modelo `.task` se descarga aparte y no va al repo; la spec debe decir dónde vive el modelo del producto y cómo se obtiene.
- **Dependencias:** `mediapipe` ya trae `opencv-contrib-python`. El `opencv-python` de la lista de la exploración sobra: los dos paquetes instalan el mismo módulo `cv2` y no deben convivir en un entorno.
- **~10 cuadros por segundo sin NPU ni GPU.** A 30 la CPU ya va en 4 %: se confirma que la aceleración queda fuera de alcance.
- **Título con `ctypes`.** Funciona solo con la librería estándar; `psutil` solo hace falta si también se lee el proceso.
- **Python 3.13** para el `.venv`.

### Cambian o se precisan
- **Línea base relativa y recalibración obligatoria.** La exploración proponía calibrar al empezar y recalibrar; ahora la recalibración no es opcional y el umbral se expresa frente a la línea base, no como número fijo. Datos para fijarlo: volver a sentarse dio −15 %, encorvarse −43 % y acercarse −59 %. Falta decidir cuándo se recalibra y si −15 % debe alertar.
- **La alerta de postura no puede decir "estás encorvado"**, porque la métrica no separa encorvado de cerca. Dos caminos:
  1. Tratar los dos como "postura distinta a tu línea base", con una redacción que no nombre la causa.
  2. Sumar una segunda señal, por ejemplo el ancho de hombros frente a la línea base, que debería crecer al acercarse. No se midió: necesita otra prueba corta.
- **Calibración:** descartar el arranque. Los tramos de 20 s fueron estables, así que una calibración corta parece viable, pero no se probó una de 5 s.
- **Los títulos son datos sensibles, no solo los de correo y banco**, porque pueden traer texto que la persona escribe. Afecta:
  - qué se guarda en los eventos: título completo, o solo app y clasificación;
  - qué llega al LLM: no alcanza con filtrar correo y banco;
  - la decisión entre LLM local o en la nube: este hallazgo pesa a favor de local.
- **Tiempo mínimo en una ventana antes de contarla**, e ignorar ventanas del sistema como la del Alt+Tab. Como Windows las nombra en el idioma del sistema, reconocerlas por el proceso o la clase de la ventana sería más robusto que por el título; esto pesa en "solo título, o título más proceso".
- **Títulos sin información** (`Nueva pestaña`): necesitan su propia categoría, sin LLM y sin alerta. La definición de "ambiguo" debe excluirlos.
- **Reglas de navegador:** Chrome y Opera ponen el nombre del navegador al final del título; las reglas deben separar ese sufijo de la página. VS Code marca los archivos sin guardar con `●`.
- **Apps que se usan al estudiar** (respuesta parcial a la pregunta abierta): PowerShell, Claude, Opera, Chrome y VS Code.
- **Video en vivo:** el experimento lo mostró, sin guardarlo, y sirvió para ver qué detectaba MediaPipe. Mostrarlo o no en el producto sigue abierto.

### Sigue sin probar
- Face Landmarker.
- Sesiones largas: solo hubo tramos de 20 s; no se sabe cómo deriva la línea base en una hora.
- Poca luz y salir de cuadro.
- CPU a ~10 cuadros por segundo (debería ser menor que a 30).
- Títulos de apps de la Tienda y de apps como administrador.
- Latencia de Ollama y notificaciones con "No molestar".

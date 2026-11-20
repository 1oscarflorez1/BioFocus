# Experimento 02 · Cámara lateral del celular

Tarea G1 de `docs/PLAN-M3.md`. **Estado: corrido el 2026-11-20. No cumple el criterio.**

## Pregunta
¿Una cámara de lado (el celular Honor X8b) separa la postura mejor que la frontal?

La frontal no distingue «encorvado» de «acercarse a la pantalla» (`experimento-01.md`). De lado se pueden medir dos ángulos con MediaPipe Pose:
- **cuello:** la línea hombro → oreja frente a la vertical, que crece al adelantar la cabeza;
- **tronco:** la línea cadera → hombro frente a la vertical, que crece al encorvarse o inclinarse.

## Criterio de éxito
Como en el experimento 01, la diferencia entre derecho y encorvado debe ser al menos 3 veces el ruido. El ruido es el máximo menos el mínimo de las medianas por segundo dentro de un mismo video. Si pasa, la integración en vivo (G2) queda como trabajo futuro con estos números. Si no pasa, también se reporta.

## Por qué con videos y no en vivo
Para usar el celular como cámara de Windows hay que instalar una app en el celular y un controlador o cliente en Windows (DroidCam, Iriun o «Cámara conectada» de Windows 11 con Enlace Móvil). Eso es instalar dependencias y no está aprobado. Con videos grabados con la cámara normal del celular no se instala nada, y la pregunta del experimento se responde igual. Lo que no se responde es si las dos cámaras a la vez frenan el equipo: eso queda para G2.

## Cómo grabar (fuera de BioFocus, a propósito)
1. Pon el celular de lado, a la altura del pecho y a 1 o 1,5 m. Que se vean la oreja, el hombro y la cadera del lado que mira a la cámara. Mejor en horizontal.
2. Graba tres videos de unos 30 s, sentado frente al computador como cuando estudias:
   - `lateral-derecho.mp4`: derecho y quieto, mirando la pantalla;
   - `lateral-encorvado.mp4`: encorvado, como mirando el celular en las piernas;
   - `lateral-adelantada.mp4`: la espalda en el respaldo, pero la cabeza adelantada hacia la pantalla.
3. Copia los tres a `grabaciones/`, que git ignora. No se suben al repositorio.

## Cómo correr
```powershell
.venv\Scripts\python experimentos\postura_lateral.py
```
Solo imprime números: los cuadros con pose, los cuadros por segundo de proceso, la mediana y el ruido de cada ángulo, y si cumple el criterio. No guarda ni muestra ningún cuadro.

## Prueba del script
El 2026-11-17 corrió sin errores con los videos frontales de `grabaciones/` como reemplazo: 45 a 52 cuadros por segundo de proceso. Esos números no sirven para el experimento, porque de frente no se ve la cadera y el «cuello» no tiene sentido.

## Resultados (2026-11-20)
Los tres videos los grabó el autor con el Honor X8b, de lado y fuera de BioFocus: unos 30 s cada uno, en vertical (576 × 1024) y de unos 6,8 MB. MediaPipe encontró la pose en 781 a 816 cuadros por video y procesó entre 66 y 69 cuadros por segundo.

| Video | Lado usado | Cuello (°) | Tronco (°) |
|---|---|---|---|
| Derecho | derecho | 25,8 ± 11,7 | 22,3 ± 32,7 |
| Encorvado | derecho | 41,7 ± 17,0 | 9,6 ± 25,7 |
| Cabeza adelantada | derecho | 42,8 ± 16,2 | 15,3 ± 18,2 |

(mediana de las medianas por segundo ± ruido: máximo menos mínimo de esas medianas)

| Comparación | Diferencia | Ruido | Veces | ¿Cumple 3 veces? |
|---|---|---|---|---|
| Cuello, derecho vs encorvado | 15,9° | 17,0° | 0,9 | No |
| Cuello, derecho vs cabeza adelantada | 17,0° | 16,2° | 1,0 | No |
| Tronco, derecho vs encorvado | 12,7° | 32,7° | 0,4 | No |
| Tronco, derecho vs cabeza adelantada | 7,0° | 32,7° | 0,2 | No |

## Qué dicen los números
- **El cuello se mueve en la dirección correcta, pero no se separa del ruido.** Encorvarse y adelantar la cabeza suben el ángulo unos 16°, y la variación dentro de un mismo video es igual de grande. La frontal, en el experimento 01, separó derecho de encorvado unas 9 veces el ruido.
- **El tronco no sirve así.** Baja al encorvarse, cuando debería subir, y su ruido es de 18° a 33°. La cadera queda tapada por la silla o el escritorio: su visibilidad promedio fue de 0,64 a 0,90, y el punto salta.
- **Un fallo del propio script.** La primera corrida elegía el lado del cuerpo cuadro por cuadro, y en un video cambió de lado hasta 34 veces, mezclando la oreja izquierda con la derecha. Se corrigió para usar un solo lado por video, el más visible. Los números de arriba son con esa corrección; los de antes daban casi lo mismo (cuello 0,9 y 0,6 veces).

## Qué haría distinto
- Grabar en horizontal y con más resolución.
- Poner el celular un poco más alto, para que la silla no tape la cadera.
- Grabar un video «derecho» quieto, para separar el ruido de la medición del movimiento de la persona.
- Probar el modelo `pose_landmarker_full`.

Ninguna de esas pruebas cabe antes de cerrar el Momento 3.

## Decisión
La cámara lateral **no se integra**: con estos números no mediría mejor que la frontal. Queda renegociada en `docs/SPEC.md`, con estos datos.

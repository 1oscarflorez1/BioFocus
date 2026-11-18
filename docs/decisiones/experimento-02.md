# Experimento 02 · Cámara lateral del celular

Tarea G1 de `docs/PLAN-M3.md`. **Estado: preparado, sin correr.** Faltan los tres videos laterales.

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

## Resultados
(Pendiente: se llenan al correr el script con los tres videos laterales.)

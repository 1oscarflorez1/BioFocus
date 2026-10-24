"""Experimento 01: pose con MediaPipe y la cámara del portátil.

Muestra la imagen con los puntos de la pose dibujados. Una vez por segundo
imprime los cuadros por segundo y un número de postura:

    postura = (y_medio_hombros - y_nariz) / ancho_hombros   (en píxeles)

Sube cuando la cabeza está más alta que los hombros y baja al encorvarse.
Se cierra con la tecla q. No guarda ninguna imagen.
"""

import sys
import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

MODELO = Path(__file__).parent / "modelos" / "pose_landmarker_lite.task"
INDICE_CAMARA = 0
VISIBILIDAD_MIN = 0.5

NARIZ = vision.PoseLandmark.NOSE.value
HOMBRO_IZQ = vision.PoseLandmark.LEFT_SHOULDER.value
HOMBRO_DER = vision.PoseLandmark.RIGHT_SHOULDER.value
CONEXIONES = vision.PoseLandmarksConnections.POSE_LANDMARKS


def numero_postura(puntos, ancho: int, alto: int):
    """Devuelve el número de postura, o None si los hombros no se ven bien."""
    nariz, izq, der = puntos[NARIZ], puntos[HOMBRO_IZQ], puntos[HOMBRO_DER]
    if min(nariz.visibility, izq.visibility, der.visibility) < VISIBILIDAD_MIN:
        return None
    ancho_hombros = abs(izq.x - der.x) * ancho
    if ancho_hombros < 1:
        return None
    y_medio_hombros = (izq.y + der.y) / 2 * alto
    return (y_medio_hombros - nariz.y * alto) / ancho_hombros


def dibujar(cuadro, puntos, ancho: int, alto: int) -> None:
    pixeles = [(int(p.x * ancho), int(p.y * alto)) for p in puntos]
    for c in CONEXIONES:
        cv2.line(cuadro, pixeles[c.start], pixeles[c.end], (0, 255, 0), 2)
    for x, y in pixeles:
        cv2.circle(cuadro, (x, y), 3, (0, 0, 255), -1)


def main() -> None:
    if not MODELO.exists():
        sys.exit(f"No encuentro el modelo en {MODELO}. Descárgalo primero (ver experimento-01.md).")

    camara = cv2.VideoCapture(INDICE_CAMARA)
    if not camara.isOpened():
        sys.exit(f"No pude abrir la cámara {INDICE_CAMARA}.")
    print(f"Cámara abierta con backend {camara.getBackendName()}, "
          f"{int(camara.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(camara.get(cv2.CAP_PROP_FRAME_HEIGHT))}.")

    opciones = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODELO)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
    )
    inicio = time.monotonic()
    ultimo_reporte = inicio
    cuadros = 0
    ultima_postura = None

    with vision.PoseLandmarker.create_from_options(opciones) as detector:
        while True:
            ok, cuadro = camara.read()
            if not ok:
                print("La cámara dejó de entregar cuadros.")
                break
            alto, ancho = cuadro.shape[:2]

            rgb = cv2.cvtColor(cuadro, cv2.COLOR_BGR2RGB)
            imagen = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            marca_ms = int((time.monotonic() - inicio) * 1000)
            resultado = detector.detect_for_video(imagen, marca_ms)

            if resultado.pose_landmarks:
                puntos = resultado.pose_landmarks[0]
                dibujar(cuadro, puntos, ancho, alto)
                ultima_postura = numero_postura(puntos, ancho, alto)
            else:
                ultima_postura = "sin persona"

            cuadros += 1
            ahora = time.monotonic()
            if ahora - ultimo_reporte >= 1:
                fps = cuadros / (ahora - ultimo_reporte)
                if ultima_postura is None:
                    texto = "hombros no visibles"
                elif isinstance(ultima_postura, str):
                    texto = ultima_postura
                else:
                    texto = f"{ultima_postura:.3f}"
                print(f"fps={fps:5.1f}  postura={texto}", flush=True)
                cuadros = 0
                ultimo_reporte = ahora

            cv2.imshow("BioFocus experimento 01 (q para salir)", cuadro)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    camara.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

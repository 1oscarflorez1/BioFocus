r"""Experimento 02: ¿la cámara lateral del celular separa bien la postura?

Lee videos grabados de lado con el celular, fuera de BioFocus, y mide con MediaPipe Pose:
- ángulo del cuello: de la línea hombro → oreja frente a la vertical (crece al adelantar la cabeza);
- ángulo del tronco: de la línea cadera → hombro frente a la vertical (crece al encorvarse o inclinarse).

Usa el lado del cuerpo que la cámara ve mejor. Solo imprime números: no guarda ni muestra ningún cuadro.
Criterio de éxito (como el experimento 01): la diferencia entre derecho y encorvado es al menos 3 veces el
ruido, y el ruido es el máximo menos el mínimo de las medianas por segundo dentro de un mismo video.

Uso, desde la raíz del repo (los videos van en grabaciones/, que git ignora):
    .venv\Scripts\python experimentos\postura_lateral.py
    .venv\Scripts\python experimentos\postura_lateral.py --derecho grabaciones\lateral-derecho.mp4 --encorvado grabaciones\lateral-encorvado.mp4 --adelantada grabaciones\lateral-adelantada.mp4
"""

from __future__ import annotations

import argparse
import hashlib
import math
import statistics
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MODELO = RAIZ / "producto" / "modelos" / "pose_landmarker_lite.task"
SHA256 = "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"  # experimento-01.md
VISIBILIDAD_MIN = 0.5
DESCARTE_S = 2.0  # se descartan los primeros y los últimos 2 s (tocar el celular para grabar)


def angulo_vertical(abajo, arriba, ancho: int, alto: int) -> float:
    """Ángulo, en grados, entre la línea abajo → arriba y la vertical. 0 = perfectamente vertical."""
    dx = (arriba.x - abajo.x) * ancho
    dy = (abajo.y - arriba.y) * alto  # la y de la imagen crece hacia abajo
    return math.degrees(math.atan2(abs(dx), dy))


def medir(ruta: Path) -> dict:
    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    L = vision.PoseLandmark
    lados = {
        "izquierdo": (L.LEFT_EAR.value, L.LEFT_SHOULDER.value, L.LEFT_HIP.value),
        "derecho": (L.RIGHT_EAR.value, L.RIGHT_SHOULDER.value, L.RIGHT_HIP.value),
    }
    video = cv2.VideoCapture(str(ruta))
    if not video.isOpened():
        raise SystemExit(f"No pude abrir {ruta}")
    fps = video.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(video.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    opciones = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODELO)), running_mode=vision.RunningMode.VIDEO, num_poses=1
    )
    # Primera pasada: el lado que la cámara ve mejor en todo el video. Antes se elegía cuadro por cuadro y el
    # lado cambiaba hasta 34 veces en un video, mezclando oreja izquierda y derecha (diagnóstico del 2026-11-20).
    puntos: list[tuple[float, list, int, int]] = []
    cuello: dict[int, list[float]] = {}
    tronco: dict[int, list[float]] = {}
    vistos = cuadros = 0
    t0 = time.perf_counter()
    with vision.PoseLandmarker.create_from_options(opciones) as detector:
        while True:
            ok, cuadro = video.read()
            if not ok:
                break
            cuadros += 1
            t = cuadros / fps
            if t < DESCARTE_S or (total and t > total / fps - DESCARTE_S):
                continue
            alto, ancho = cuadro.shape[:2]
            imagen = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(cuadro, cv2.COLOR_BGR2RGB))
            r = detector.detect_for_video(imagen, int(t * 1000))
            if not r.pose_landmarks:
                continue
            puntos.append((t, r.pose_landmarks[0], ancho, alto))
    video.release()
    lado = max(lados, key=lambda k: sum(p[i].visibility for _, p, _, _ in puntos for i in lados[k])) if puntos else "derecho"
    oreja, hombro, cadera = lados[lado]
    for t, p, ancho, alto in puntos:
        if min(p[oreja].visibility, p[hombro].visibility) < VISIBILIDAD_MIN:
            continue
        vistos += 1
        segundo = int(t)
        cuello.setdefault(segundo, []).append(angulo_vertical(p[hombro], p[oreja], ancho, alto))
        if p[cadera].visibility >= VISIBILIDAD_MIN:
            tronco.setdefault(segundo, []).append(angulo_vertical(p[cadera], p[hombro], ancho, alto))
    proceso_s = time.perf_counter() - t0

    def resumen(por_segundo: dict[int, list[float]]) -> dict | None:
        medianas = [statistics.median(v) for v in por_segundo.values() if v]
        if len(medianas) < 3:
            return None
        return {"mediana": statistics.median(medianas), "ruido": max(medianas) - min(medianas), "segundos": len(medianas)}

    return {
        "video": ruta.name, "lado": lado, "cuadros": cuadros, "con_pose": vistos, "fps_video": fps,
        "fps_proceso": cuadros / proceso_s if proceso_s else 0.0,
        "cuello": resumen(cuello), "tronco": resumen(tronco),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Experimento 02: postura con la cámara lateral.")
    p.add_argument("--derecho", type=Path, default=RAIZ / "grabaciones" / "lateral-derecho.mp4")
    p.add_argument("--encorvado", type=Path, default=RAIZ / "grabaciones" / "lateral-encorvado.mp4")
    p.add_argument("--adelantada", type=Path, default=RAIZ / "grabaciones" / "lateral-adelantada.mp4")
    a = p.parse_args()
    if hashlib.sha256(MODELO.read_bytes()).hexdigest() != SHA256:
        raise SystemExit("El modelo de postura no tiene el SHA-256 de experimento-01.md.")
    videos = {"derecho": a.derecho, "encorvado": a.encorvado, "adelantada": a.adelantada}
    faltan = [str(v) for v in videos.values() if not v.is_file()]
    if faltan:
        raise SystemExit("Faltan videos: " + ", ".join(faltan) + ". Ver docs/decisiones/experimento-02.md.")

    medidas = {nombre: medir(ruta) for nombre, ruta in videos.items()}
    print(f"{'video':<11} {'lado':<9} {'cuadros':>7} {'con pose':>9} {'fps proc.':>9}   {'cuello (°)':>18}   {'tronco (°)':>18}")
    for nombre, m in medidas.items():
        def txt(r):
            return f"{r['mediana']:6.1f} ± {r['ruido']:4.1f} ({r['segundos']} s)" if r else "  sin datos"
        print(f"{nombre:<11} {m['lado']:<9} {m['cuadros']:>7} {m['con_pose']:>9} {m['fps_proceso']:>9.1f}   {txt(m['cuello']):>18}   {txt(m['tronco']):>18}")

    print("\nCriterio: diferencia frente a «derecho» de al menos 3 veces el ruido (el mayor de los dos videos).")
    for senal in ("cuello", "tronco"):
        base = medidas["derecho"][senal]
        for otro in ("encorvado", "adelantada"):
            m = medidas[otro][senal]
            if not base or not m:
                print(f"  {senal:<6} derecho vs {otro:<10}: sin datos")
                continue
            diferencia, ruido = abs(m["mediana"] - base["mediana"]), max(base["ruido"], m["ruido"], 0.1)
            veces = diferencia / ruido
            print(f"  {senal:<6} derecho vs {otro:<10}: diferencia {diferencia:5.1f}°, ruido {ruido:4.1f}° → "
                  f"{veces:4.1f} veces · {'CUMPLE' if veces >= 3 else 'no cumple'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

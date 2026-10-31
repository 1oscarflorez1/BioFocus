r"""Monitor de BioFocus: una sesión de estudio real, en vivo, en un proceso aparte.

Lee la cámara (MediaPipe Pose) y la ventana activa, dispara alertas en tiempo real (aviso grande en la
ventana de la cámara y un sonido corto) y escribe eventos en data/biofocus.sqlite. Nunca graba ni guarda
imágenes, video ni audio: cada cuadro vive en memoria lo que tarda en procesarse.

Uso, desde la raíz del repo:
    .venv\Scripts\python producto\monitor.py --meta "Repasar cálculo integral" --duracion 25
    .venv\Scripts\python producto\monitor.py --meta "Repasar cálculo integral" --modo-demo
    .venv\Scripts\python producto\monitor.py --meta "..." --video grabaciones\prueba.mp4   # plan B, sin cámara

Teclas en la ventana de la cámara: c recalibra y q termina. También termina cuando la app marca la sesión
como terminada. En los dos casos escribe fin_sesion y cierra limpio.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import queue
import signal
import statistics
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import datos
import ventanas
import vivo

CARPETA = Path(__file__).resolve().parent
RUTA_MODELO = CARPETA / "modelos" / "pose_landmarker_lite.task"
SHA256_MODELO = "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"  # experimento-01.md
TITULO_VENTANA = "BioFocus monitor"  # reglas.json la cuenta como neutra (ASCII: OpenCV no muestra tildes en el título)


@dataclass(frozen=True)
class Tiempos:
    postura_sostenida_s: float  # cuánto debe durar la caída antes de alertar
    distraccion_s: float  # segundos seguidos en no_sirve antes de alertar
    cooldown_s: float  # entre dos alertas del mismo tipo


NORMAL = Tiempos(postura_sostenida_s=20, distraccion_s=60, cooldown_s=300)
DEMO = Tiempos(postura_sostenida_s=5, distraccion_s=10, cooldown_s=30)

CALIBRACION_S = 5  # sentado derecho al inicio y con la tecla c
MUESTRAS_MIN_CALIBRACION = 10
DESCARTE_ARRANQUE_S = 1.0  # el primer segundo la cámara va lenta (experimento 01)
CAIDA_ALERTA = 0.25  # alerta si el número cae más de 25 % bajo la línea base…
REARME = 0.10  # …y se rearma al volver a menos de 10 % bajo la línea base
SUAVIZADO_S = 0.5  # mediana de medio segundo, para que un cuadro suelto no corte la cuenta
VISIBILIDAD_MIN = 0.5
AVISO_S = 6  # cuánto queda el aviso grande en pantalla
LATIDO_S = 1.0  # cada cuánto se escribe el estado en vivo y se mira si la app pidió terminar
ANCHO_VISTA = 960  # la ventana dibuja una copia reducida; la detección usa el cuadro completo


class ErrorMonitor(Exception):
    """Problema para arrancar (modelo, cámara, video, sesión en curso). El mensaje es para la persona."""


# ---------------------------------------------------------------- postura


def numero_postura(puntos, ancho: int, alto: int) -> float | None:
    """(y medio de los hombros − y de la nariz) / ancho de los hombros, en píxeles (experimento 01).

    Baja al encorvarse o al acercarse a la pantalla. None si la nariz o los hombros no se ven bien.
    """
    from mediapipe.tasks.python import vision

    nariz = puntos[vision.PoseLandmark.NOSE.value]
    izq = puntos[vision.PoseLandmark.LEFT_SHOULDER.value]
    der = puntos[vision.PoseLandmark.RIGHT_SHOULDER.value]
    if min(nariz.visibility, izq.visibility, der.visibility) < VISIBILIDAD_MIN:
        return None
    ancho_hombros = abs(izq.x - der.x) * ancho
    if ancho_hombros < 1:
        return None
    return ((izq.y + der.y) / 2 * alto - nariz.y * alto) / ancho_hombros


class Postura:
    """Línea base, estado y alerta de postura. Estados: calibrando, bien, revisa, no_te_veo."""

    def __init__(self, tiempos: Tiempos, inicio: float):
        self.t = tiempos
        self.base: float | None = None
        self.estado = "calibrando"
        self.suavizado: float | None = None  # mediana del último medio segundo
        self.variacion: float | None = None  # fracción frente a la base (−0,27 = 27 % abajo)
        self.mal_desde: float | None = None
        self.armada = True
        self.ultima_alerta = float("-inf")
        self._descartar_hasta = inicio + DESCARTE_ARRANQUE_S
        self._calibracion: list[float] = []
        self._calibrando_desde: float | None = None
        self._muestras: deque[tuple[float, float]] = deque()

    def recalibrar(self, t: float) -> None:
        self.base, self.estado, self.variacion, self.mal_desde, self.armada = None, "calibrando", None, None, True
        self._calibracion, self._calibrando_desde, self._descartar_hasta = [], None, t

    def falta_calibrar_s(self, t: float) -> float:
        if self._calibrando_desde is None:
            return CALIBRACION_S
        return max(0.0, CALIBRACION_S - (t - self._calibrando_desde))

    def actualizar(self, t: float, valor: float | None) -> bool:
        """Registra la medición de un cuadro. Devuelve True si hay que disparar la alerta de postura."""
        if valor is not None and t >= self._descartar_hasta:
            self._muestras.append((t, valor))
        while self._muestras and t - self._muestras[0][0] > SUAVIZADO_S:
            self._muestras.popleft()

        if self.base is None:
            self.estado = "calibrando"
            if valor is None or t < self._descartar_hasta:
                return False
            if self._calibrando_desde is None:
                self._calibrando_desde = t
            self._calibracion.append(valor)
            if t - self._calibrando_desde >= CALIBRACION_S and len(self._calibracion) >= MUESTRAS_MIN_CALIBRACION:
                base = statistics.median(self._calibracion)
                if base > 0.05:
                    self.base, self.estado = base, "bien"
                else:  # medición rara (persona de lado, cámara mal puesta): vuelve a calibrar
                    self._calibracion, self._calibrando_desde = [], None
            return False

        if not self._muestras:
            self.estado, self.variacion, self.mal_desde, self.suavizado = "no_te_veo", None, None, None
            return False
        actual = statistics.median(v for _, v in self._muestras)
        self.suavizado = actual
        self.variacion = actual / self.base - 1
        if actual < self.base * (1 - CAIDA_ALERTA):
            self.estado = "revisa"
            if self.mal_desde is None:
                self.mal_desde = t
            if (
                self.armada
                and t - self.mal_desde >= self.t.postura_sostenida_s
                and t - self.ultima_alerta >= self.t.cooldown_s
            ):
                self.armada, self.ultima_alerta = False, t
                return True
            return False
        self.estado, self.mal_desde = "bien", None
        if actual >= self.base * (1 - REARME):
            self.armada = True
        return False


class Distraccion:
    """Alerta tras distraccion_s seguidos en no_sirve, con cooldown entre alertas."""

    def __init__(self, tiempos: Tiempos):
        self.t = tiempos
        self.ultima_alerta = float("-inf")

    def revisar(self, t: float, racha_desde: float | None) -> bool:
        if racha_desde is None or t - racha_desde < self.t.distraccion_s:
            return False
        if t - self.ultima_alerta < self.t.cooldown_s:
            return False
        self.ultima_alerta = t
        return True


# ---------------------------------------------------------------- avisos


def sonar(tipo: str) -> None:
    """Un sonido corto, en otro hilo para no frenar la cámara."""
    if sys.platform != "win32":
        return
    import winsound

    tonos = {"postura": [(660, 160), (520, 220)], "distraccion": [(880, 140), (1175, 220)]}[tipo]

    def tocar() -> None:
        for frecuencia, ms in tonos:
            winsound.Beep(frecuencia, ms)

    threading.Thread(target=tocar, daemon=True).start()


COLOR_CATEGORIA = {  # RGB
    "sirve": (46, 160, 67),
    "no_sirve": (218, 54, 51),
    "neutro": (110, 118, 129),
    "sin_clasificar": (150, 150, 150),
}
NOMBRE_CATEGORIA = {"sirve": "sirve", "no_sirve": "no sirve", "neutro": "neutro", "sin_clasificar": "sin clasificar"}
COLOR_POSTURA = {"bien": (46, 160, 67), "revisa": (230, 140, 0), "no_te_veo": (150, 150, 150), "calibrando": (56, 139, 253)}


class Pantalla:
    """Dibuja los puntos, el estado y los avisos sobre el cuadro. Texto con Pillow para que salgan las tildes."""

    def __init__(self) -> None:
        from PIL import ImageFont

        fuentes = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"

        def fuente(nombre: str, tam: int):
            try:
                return ImageFont.truetype(str(fuentes / nombre), tam)
            except OSError:
                return ImageFont.load_default(size=tam)

        self.normal, self.negrita = fuente("segoeui.ttf", 17), fuente("segoeuib.ttf", 18)
        self.aviso, self.subaviso, self.chica = fuente("segoeuib.ttf", 36), fuente("segoeui.ttf", 19), fuente("segoeui.ttf", 14)

    @staticmethod
    def _caja(img, x0: int, y0: int, x1: int, y1: int, rgb: tuple[int, int, int], alfa: float) -> None:
        import cv2
        import numpy as np

        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(img.shape[1], x1), min(img.shape[0], y1)
        if x1 <= x0 or y1 <= y0:
            return
        roi = img[y0:y1, x0:x1]
        capa = np.empty_like(roi)
        capa[:] = rgb[::-1]
        cv2.addWeighted(capa, alfa, roi, 1 - alfa, 0, dst=roi)

    def dibujar(self, img, puntos, e: dict):
        import cv2
        import numpy as np
        from mediapipe.tasks.python import vision
        from PIL import Image, ImageDraw

        alto, ancho = img.shape[:2]
        if puntos:
            px = [(int(p.x * ancho), int(p.y * alto)) for p in puntos]
            for c in vision.PoseLandmarksConnections.POSE_LANDMARKS:
                cv2.line(img, px[c.start], px[c.end], (80, 220, 80), 2)
            for x, y in px:
                cv2.circle(img, (x, y), 3, (40, 40, 230), -1)

        self._caja(img, 0, 0, ancho, 56, (20, 20, 20), 0.6)
        self._caja(img, 0, alto - 74, ancho, alto, (20, 20, 20), 0.65)
        aviso = e.get("aviso")
        if aviso:
            self._caja(img, 20, alto // 2 - 70, ancho - 20, alto // 2 + 50, aviso["color"], 0.88)
        elif e["postura"] == "calibrando":
            self._caja(img, 40, alto // 2 - 40, ancho - 40, alto // 2 + 30, COLOR_POSTURA["calibrando"], 0.8)

        lienzo = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        d = ImageDraw.Draw(lienzo)
        blanco = (255, 255, 255)
        d.text((12, 6), e["encabezado"], font=self.negrita, fill=blanco)
        d.text((12, 30), e["meta"], font=self.normal, fill=(220, 220, 220))

        y = alto - 70
        d.ellipse((12, y + 6, 24, y + 18), fill=COLOR_POSTURA.get(e["postura"], (150, 150, 150)))
        d.text((32, y), e["linea_postura"], font=self.normal, fill=blanco)
        d.ellipse((12, y + 30, 24, y + 42), fill=COLOR_CATEGORIA.get(e.get("categoria") or "", (90, 90, 90)))
        d.text((32, y + 24), e["linea_ventana"], font=self.normal, fill=blanco)
        d.text((ancho - 170, y + 50), "c recalibrar · q terminar", font=self.chica, fill=(200, 200, 200))

        if aviso:
            d.text((ancho // 2, alto // 2 - 32), aviso["titulo"], font=self.aviso, fill=blanco, anchor="mm")
            d.text((ancho // 2, alto // 2 + 14), aviso["detalle"], font=self.subaviso, fill=blanco, anchor="mm")
        elif e["postura"] == "calibrando":
            d.text((ancho // 2, alto // 2 - 5), e["linea_postura"], font=self.negrita, fill=blanco, anchor="mm")
        return cv2.cvtColor(np.asarray(lienzo), cv2.COLOR_RGB2BGR)


# ---------------------------------------------------------------- textos


def _mmss(segundos: float) -> str:
    s = max(0, int(segundos))
    return f"{s // 60:02d}:{s % 60:02d}"


def linea_postura(p: Postura, t: float, viendo: bool) -> str:
    if p.estado == "calibrando":
        if not viendo:
            return "Calibrando: ponte frente a la cámara"
        return f"Calibrando: siéntate derecho · {p.falta_calibrar_s(t):.0f} s"
    if p.estado == "no_te_veo":
        return "Postura: no te veo"
    pct = f"{p.variacion * 100:+.0f} %".replace("-", "−") if p.variacion is not None else ""
    if p.estado == "revisa":
        segundos = t - p.mal_desde if p.mal_desde else 0
        return f"Postura: revisa ({pct} frente a tu línea base, {segundos:.0f} s)"
    return f"Postura: bien ({pct})"


def detalle_segundo(segundo: float, valor: float | None, p: Postura, f: ventanas.Foto) -> str:
    """Una línea por segundo con --detalle, para probar con videos: número crudo, suavizado, base y estado."""
    num = lambda x: "  —  " if x is None else f"{x:.3f}"  # noqa: E731
    pct = "" if p.variacion is None else f"{p.variacion * 100:+5.1f} %"
    return (
        f"[{segundo:6.1f} s] número {num(valor)} · suavizado {num(p.suavizado)} · base {num(p.base)} {pct:>8} · "
        f"{p.estado}{'' if p.armada else ' (sin rearmar)'} | ventana {f.app or '—'} · {f.categoria or '—'}"
    )


def linea_ventana(f: ventanas.Foto, t: float) -> str:
    if not f.app:
        return "Ventana: leyendo…"
    texto = f"Ventana: {f.app} · {NOMBRE_CATEGORIA.get(f.categoria, f.categoria)}"
    if f.razon:
        texto += f" · {f.razon}"
    if f.categoria == "no_sirve" and f.racha_no_sirve is not None:
        texto += f" ({t - f.racha_no_sirve:.0f} s)"
    return texto[:95]


# ---------------------------------------------------------------- base de datos


def _ts(t: float) -> str:
    return datetime.fromtimestamp(t).strftime(datos.FORMATO)


def verificar_modelo(ruta: Path = RUTA_MODELO) -> None:
    if not ruta.exists():
        raise ErrorMonitor(
            f"No encuentro el modelo en {ruta}. Cópialo de experimentos\\modelos o descárgalo (ver README)."
        )
    if hashlib.sha256(ruta.read_bytes()).hexdigest() != SHA256_MODELO:
        raise ErrorMonitor(f"El modelo {ruta.name} no tiene el SHA-256 anotado en experimento-01.md: no lo uso.")


class Registro:
    """Escribe la sesión, los eventos y el estado en vivo. Solo lo usa el hilo principal."""

    def __init__(self, ruta_bd: Path | None, meta: str, duracion_min: int, modo_demo: bool):
        self.con = datos.conectar(ruta_bd)
        ahora = time.time()
        vivo.cerrar_huerfanas(self.con, datetime.fromtimestamp(ahora))
        activa = vivo.sesion_en_curso(self.con)
        if activa is not None and vivo.esta_viva(activa, datetime.fromtimestamp(ahora)):
            self.con.close()
            raise ErrorMonitor(f"Ya hay una sesión en curso (la {activa['id']}). Termínala antes de empezar otra.")
        self.inicio = ahora
        self.id = datos.crear_sesion(self.con, _ts(ahora), None, meta, duracion_min, es_demo=False)
        self.con.execute(
            "INSERT INTO estado_monitor (sesion_id, pid, modo_demo, actualizado, postura) VALUES (?, ?, ?, ?, 'calibrando')",
            (self.id, os.getpid(), 1 if modo_demo else 0, _ts(ahora)),
        )
        datos.agregar_evento(self.con, self.id, _ts(ahora), "inicio_sesion",
                             detalle="monitor en vivo" + (", modo demo" if modo_demo else ""))
        self.con.commit()

    def tramo(self, tramo: ventanas.Tramo) -> None:
        if tramo.duracion_s > 0:
            datos.agregar_evento(self.con, self.id, _ts(tramo.inicio), "ventana",
                                 app=tramo.clase.app, categoria=tramo.clase.categoria, duracion_s=tramo.duracion_s)
            self.con.commit()

    def alerta(self, tipo: str, t: float, app: str | None = None, detalle: str = "") -> None:
        datos.agregar_evento(self.con, self.id, _ts(t), f"alerta_{tipo}", app=app,
                             categoria="no_sirve" if tipo == "distraccion" else None, detalle=detalle[: datos.MAX_DETALLE])
        self.con.commit()

    def latido(self, t: float, p: Postura, f: ventanas.Foto) -> bool:
        """Escribe el estado en vivo. Devuelve True si la app pidió terminar o la sesión ya está cerrada."""
        self.con.execute(
            "UPDATE estado_monitor SET actualizado = ?, postura = ?, postura_pct = ?, app = ?, categoria = ?, "
            "ventana_desde = ? WHERE sesion_id = ?",
            (_ts(t), p.estado, round(p.variacion * 100, 1) if p.variacion is not None else None,
             f.app, f.categoria, _ts(f.desde) if f.desde else None, self.id),
        )
        self.con.commit()
        fila = self.con.execute(
            "SELECT e.detener, s.fin FROM estado_monitor e JOIN sesiones s ON s.id = e.sesion_id WHERE e.sesion_id = ?",
            (self.id,),
        ).fetchone()
        return fila is None or bool(fila["detener"]) or fila["fin"] is not None

    def cerrar(self, t: float, motivo: str) -> None:
        vivo.cerrar_sesion(self.con, self.id, datetime.fromtimestamp(t), motivo)
        self.con.commit()
        self.con.close()


# ---------------------------------------------------------------- bucle


def _interrumpir(signum, frame):  # Ctrl+Break (lo manda la app como segundo intento) o Ctrl+C
    raise KeyboardInterrupt


def correr(args: argparse.Namespace) -> int:
    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    verificar_modelo()
    tiempos = DEMO if args.modo_demo else NORMAL
    if args.video:
        ruta_video = Path(args.video)
        if not ruta_video.is_file():
            raise ErrorMonitor(f"No encuentro el video {ruta_video}.")
        fuente = cv2.VideoCapture(str(ruta_video))
        fps_video = fuente.get(cv2.CAP_PROP_FPS) or 30.0
    else:
        fuente = cv2.VideoCapture(args.camara)
        fps_video = 0.0
    if not fuente.isOpened():
        raise ErrorMonitor("No pude abrir el video." if args.video else f"No pude abrir la cámara {args.camara}.")

    opciones = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(RUTA_MODELO)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
    )
    detector = vision.PoseLandmarker.create_from_options(opciones)
    try:
        registro = Registro(args.bd, args.meta, args.duracion, args.modo_demo)
    except ErrorMonitor:
        detector.close()
        fuente.release()
        raise
    print(f"Sesión {registro.id} iniciada{' en modo demo' if args.modo_demo else ''}. "
          f"{'Video: ' + str(args.video) if args.video else 'Cámara ' + str(args.camara)}. q termina, c recalibra.", flush=True)

    clasificador = ventanas.Clasificador(args.meta)
    hilo = ventanas.HiloVentanas(ventanas.SeguidorVentanas(clasificador))
    hilo.start()
    postura = Postura(tiempos, time.time())
    distraccion = Distraccion(tiempos)
    pantalla = None if args.sin_ventana else Pantalla()
    if pantalla:
        cv2.namedWindow(TITULO_VENTANA, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(TITULO_VENTANA, 800, 600)
    for nombre in ("SIGBREAK", "SIGINT"):
        if hasattr(signal, nombre):
            signal.signal(getattr(signal, nombre), _interrumpir)

    motivo = "interrumpido"
    aviso: dict | None = None
    t0_mono = time.monotonic()
    ultimo_ms, ultimo_latido, cuadros_video, ultimo_detalle = -1, 0.0, 0, 0.0
    valor: float | None = None
    primera_vez = True
    try:
        while True:
            ok, cuadro = fuente.read()
            if not ok:
                motivo = (
                    ("fin del video" if cuadros_video else "el video no se pudo leer")
                    if args.video else "la cámara dejó de entregar cuadros"
                )
                break
            if args.video:  # una pasada, al ritmo del video, no más rápido
                cuadros_video += 1
                espera = t0_mono + cuadros_video / fps_video - time.monotonic()
                if espera > 0:
                    time.sleep(espera)
            else:
                cuadro = cv2.flip(cuadro, 1)  # como un espejo; el número de postura no cambia
            t = time.time()
            alto, ancho = cuadro.shape[:2]

            ms = max(int((time.monotonic() - t0_mono) * 1000), ultimo_ms + 1)
            ultimo_ms = ms
            imagen = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(cuadro, cv2.COLOR_BGR2RGB))
            resultado = detector.detect_for_video(imagen, ms)
            puntos = resultado.pose_landmarks[0] if resultado.pose_landmarks else None
            valor = numero_postura(puntos, ancho, alto) if puntos else None

            foto = hilo.foto
            if postura.actualizar(t, valor):
                pct = postura.variacion * 100 if postura.variacion is not None else 0
                registro.alerta("postura", t, detalle=f"postura distinta a la línea base ({pct:+.0f} %)")
                aviso = {"tipo": "postura", "hasta": t + AVISO_S, "color": COLOR_POSTURA["revisa"],
                         "titulo": "Revisa tu postura",
                         "detalle": f"Tu cabeza bajó {abs(pct):.0f} % frente a tu línea base"}
                print(f"ALERTA postura a los {t - registro.inicio:.1f} s ({pct:+.0f} %)", flush=True)
                if pantalla:
                    sonar("postura")
            if distraccion.revisar(t, foto.racha_no_sirve):
                segundos = int(t - foto.racha_no_sirve)
                registro.alerta("distraccion", t, app=foto.app,
                                detalle=f"{segundos} s seguidos en ventanas que no sirven a la meta")
                aviso = {"tipo": "distraccion", "hasta": t + AVISO_S, "color": COLOR_CATEGORIA["no_sirve"],
                         "titulo": "¿Esto sirve a tu meta?",
                         "detalle": f"{segundos} s seguidos en {foto.app}, que no sirve"}
                print(f"ALERTA distracción a los {t - registro.inicio:.1f} s ({foto.app})", flush=True)
                if pantalla:
                    sonar("distraccion")
            if aviso and t > aviso["hasta"]:
                aviso = None
            if args.detalle and t - ultimo_detalle >= 1:
                ultimo_detalle = t
                print(detalle_segundo(t - registro.inicio, valor, postura, foto), flush=True)

            while True:
                try:
                    registro.tramo(hilo.cerrados.get_nowait())
                except queue.Empty:
                    break
            if t - ultimo_latido >= LATIDO_S:
                ultimo_latido = t
                if registro.latido(t, postura, foto):
                    motivo = "terminada desde la app"
                    break

            if pantalla:
                transcurrido = t - registro.inicio
                estado = {
                    "encabezado": f"BioFocus · {_mmss(transcurrido)} de {args.duracion} min"
                                  + (" · modo demo" if args.modo_demo else "") + (" · video" if args.video else ""),
                    "meta": f"Meta: {args.meta}"[:80],
                    "postura": postura.estado,
                    "linea_postura": linea_postura(postura, t, valor is not None),
                    "categoria": foto.categoria,
                    "linea_ventana": linea_ventana(foto, t),
                    "aviso": aviso,
                }
                vista = cuadro if ancho <= ANCHO_VISTA else cv2.resize(cuadro, (ANCHO_VISTA, round(alto * ANCHO_VISTA / ancho)))
                cv2.imshow(TITULO_VENTANA, pantalla.dibujar(vista, puntos, estado))
                if primera_vez:
                    cv2.setWindowProperty(TITULO_VENTANA, cv2.WND_PROP_TOPMOST, 1)
                    primera_vez = False
                tecla = cv2.waitKey(1) & 0xFF
                if tecla in (ord("q"), ord("Q")):
                    motivo = "tecla q"
                    break
                if tecla in (ord("c"), ord("C")):
                    postura.recalibrar(t)
                    aviso = None
                if cv2.getWindowProperty(TITULO_VENTANA, cv2.WND_PROP_VISIBLE) < 1:
                    motivo = "ventana del monitor cerrada"
                    break
    except KeyboardInterrupt:
        motivo = "interrumpido"
    finally:
        for tramo in hilo.detener():
            registro.tramo(tramo)
        registro.cerrar(time.time(), motivo)
        detector.close()
        fuente.release()
        if pantalla:
            cv2.destroyAllWindows()
    print(f"Sesión {registro.id} terminada: {motivo}.", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Monitor en vivo de BioFocus (cámara y ventana activa).")
    p.add_argument("--meta", required=True, help="qué quieres lograr en esta sesión (se queda en el equipo, salvo para clasificar títulos ambiguos)")
    p.add_argument("--duracion", type=int, default=25, help="minutos planeados (por defecto 25)")
    p.add_argument("--modo-demo", action="store_true", help="tiempos cortos: postura 5 s, distracción 10 s, cooldown 30 s")
    p.add_argument("--video", help="plan B: lee este video (por ejemplo de grabaciones/) en vez de la cámara")
    p.add_argument("--camara", type=int, default=0, help="índice de la cámara (por defecto 0)")
    p.add_argument("--bd", type=Path, default=None, help="base SQLite (por defecto data/biofocus.sqlite)")
    p.add_argument("--sin-ventana", action="store_true", help="para pruebas: sin ventana ni sonido")
    p.add_argument("--detalle", action="store_true", help="imprime cada segundo el número de postura, la base y el estado")
    args = p.parse_args(argv)
    args.meta = " ".join(args.meta.split())[:200]
    if not args.meta:
        p.error("--meta no puede estar vacía")
    if not 1 <= args.duracion <= 600:
        p.error("--duracion va de 1 a 600 minutos")
    try:
        return correr(args)
    except ErrorMonitor as e:
        print(f"BioFocus monitor: {e}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())

r"""Monitor de BioFocus: una sesión de estudio real, en vivo, en un proceso aparte.

Lee la cámara (MediaPipe Pose) y la ventana activa, dispara alertas en tiempo real (un aviso emergente
encima de todo, un sonido corto y el cartel en la ventana de la cámara si está a la vista) y escribe eventos
en data/biofocus.sqlite. Nunca graba ni guarda imágenes, video ni audio: cada cuadro vive en memoria lo que
tarda en procesarse.

Uso, desde la raíz del repo:
    .venv\Scripts\python producto\monitor.py --meta "Repasar cálculo integral" --duracion 25
    .venv\Scripts\python producto\monitor.py --meta "Repasar cálculo integral" --modo-demo
    .venv\Scripts\python producto\monitor.py --meta "..." --video grabaciones\prueba.mp4   # plan B, sin cámara
    .venv\Scripts\python producto\monitor.py --meta "..." --ocultar-camara --caida-postura 30

Teclas en la ventana de la cámara: c recalibra y q termina. Con la cámara oculta se recalibra y se termina
desde la app («Recalibrar postura» y «Terminar sesión»). En todos los casos escribe fin_sesion y cierra limpio.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import io
import math
import os
import queue
import signal
import statistics
import struct
import sys
import threading
import time
import wave
from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

import aviso as emergente
import datos
import herramientas
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
    rearme_s: float  # segundos seguidos en «bien» que rearman la alerta de postura aunque no vuelva a −10 %
    pausa_min_s: float  # fuera de cuadro al menos esto cuenta como pausa
    pausa_cada_s: float  # tras esto sin pausa, recuerda tomar una


NORMAL = Tiempos(postura_sostenida_s=20, distraccion_s=60, cooldown_s=300, rearme_s=10, pausa_min_s=60, pausa_cada_s=50 * 60)
DEMO = Tiempos(postura_sostenida_s=5, distraccion_s=10, cooldown_s=30, rearme_s=3, pausa_min_s=10, pausa_cada_s=90)

CALIBRACION_S = 5  # sentado derecho al inicio y con la tecla c
MUESTRAS_MIN_CALIBRACION = 10
DESCARTE_ARRANQUE_S = 1.0  # el primer segundo la cámara va lenta (experimento 01)
CAIDA_ALERTA = 0.25  # alerta si el número cae más de 25 % bajo la línea base…
REARME = 0.10  # …y se rearma al volver a menos de 10 % bajo la línea base, o tras rearme_s seguidos en «bien».
# Por qué el rearme por tiempo: el experimento 01 midió −15 % al volver a sentarse derecho. Solo con el −10 %,
# la alerta casi nunca se rearmaba y había una sola alerta por sesión (hallazgo 7 de la auditoría).
# Sensibilidad que la persona elige en «Ajustes» de la app (tarea I3), con sus topes y el porqué de cada uno.
# El modo demo no la usa: sus tiempos y el 25 % son fijos para que la demo y el plan B salgan igual siempre.
CAIDA_MIN_PCT, CAIDA_MAX_PCT = 20, 40  # volver a sentarse derecho dio −15 % (experimento 01) y por debajo de 20
# alertaría solo; encorvarse dio −43 %, así que por encima de 40 casi nunca avisaría.
POSTURA_MIN_S, POSTURA_MAX_S = 5, 120  # menos de 5 s es mirar el teclado; más de 2 min ya no avisa «en el momento»
DISTRACCION_MIN_S, DISTRACCION_MAX_S = 10, 600  # menos de 10 s corta un vistazo a otra ventana; 10 min es el tope
# para que el aviso todavía sirva
PAUSA_MIN_MIN, PAUSA_MAX_MIN = 15, 120  # más seguido que cada 15 min interrumpe el estudio; más de 2 h sin pausa ya
# no es una pausa activa
SUAVIZADO_S = 0.5  # mediana de medio segundo, para que un cuadro suelto no corte la cuenta
VISIBILIDAD_MIN = 0.5
AVISO_S = 6  # cuánto queda el aviso grande en pantalla
LATIDO_S = 1.0  # cada cuánto se escribe el estado en vivo y se mira si la app pidió terminar
ANCHO_VISTA = 960  # la ventana dibuja una copia reducida; la detección usa el cuadro completo
# Cuánto se tolera que la cámara no entregue cuadros antes de cerrar la sesión; a la mitad se reabre una vez.
# Por qué: al arrancar puede tardar (otra app la está soltando) y a mitad de sesión puede cortarse un momento;
# antes, un solo cuadro perdido terminaba la sesión. Es menos que los 15 s con que la app da al monitor por caído.
CORTE_CAMARA_MAX_S = 10.0
ESPERA_SIN_CUADRO_S = 0.1  # entre un intento y el siguiente mientras no hay imagen


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

    def __init__(self, tiempos: Tiempos, inicio: float, caida: float = CAIDA_ALERTA):
        self.t = tiempos
        self.caida = caida  # fracción bajo la línea base que cuenta como «revisa» (0,25 por defecto)
        self.base: float | None = None
        self.estado = "calibrando"
        self.suavizado: float | None = None  # mediana del último medio segundo
        self.variacion: float | None = None  # fracción frente a la base (−0,27 = 27 % abajo)
        self.mal_desde: float | None = None
        self.bien_desde: float | None = None  # desde cuándo está seguido en «bien» (para el rearme por tiempo)
        self.armada = True
        self.ultima_alerta = float("-inf")
        self._descartar_hasta = inicio + DESCARTE_ARRANQUE_S
        self._calibracion: list[float] = []
        self._calibrando_desde: float | None = None
        self._muestras: deque[tuple[float, float]] = deque()

    def recalibrar(self, t: float) -> None:
        self.base, self.estado, self.variacion, self.mal_desde, self.armada = None, "calibrando", None, None, True
        self.bien_desde = None
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
            self.bien_desde = None
            return False
        actual = statistics.median(v for _, v in self._muestras)
        self.suavizado = actual
        self.variacion = actual / self.base - 1
        if actual < self.base * (1 - self.caida):
            self.estado, self.bien_desde = "revisa", None
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
        if self.estado != "bien" or self.bien_desde is None:
            self.bien_desde = t
        self.estado, self.mal_desde = "bien", None
        if actual >= self.base * (1 - REARME) or t - self.bien_desde >= self.t.rearme_s:
            self.armada = True
        return False


class Pausas:
    """Pausas y recordatorio de pausa.

    - Si la persona sale de cuadro al menos pausa_min_s (con la línea base ya calibrada), al volver se registra
      un evento `pausa` con su duración.
    - Tras pausa_cada_s sin pausa (desde el inicio, la última pausa o el último recordatorio), recuerda tomar una.
    """

    def __init__(self, tiempos: Tiempos, inicio: float):
        self.t = tiempos
        self.ausente_desde: float | None = None
        self.ultimo_corte = inicio
        self.recordatorios = 0

    def actualizar(self, t: float, ve_a_la_persona: bool, calibrada: bool) -> tuple[tuple[float, float] | None, bool]:
        """Devuelve (pausa que terminó como (inicio, duración) o None, si toca recordar la pausa)."""
        pausa = None
        if ve_a_la_persona or not calibrada:
            if self.ausente_desde is not None and t - self.ausente_desde >= self.t.pausa_min_s:
                pausa = (self.ausente_desde, t - self.ausente_desde)
                self.ultimo_corte = t
            self.ausente_desde = None
        elif self.ausente_desde is None:
            self.ausente_desde = t
        en_pausa = self.ausente_desde is not None and t - self.ausente_desde >= self.t.pausa_min_s
        recordar = not en_pausa and t - self.ultimo_corte >= self.t.pausa_cada_s
        if recordar:
            self.ultimo_corte = t
            self.recordatorios += 1
        return pausa, recordar

    def cerrar(self, t: float) -> tuple[float, float] | None:
        """Al terminar la sesión: si la persona seguía fuera de cuadro lo suficiente, esa pausa también cuenta."""
        if self.ausente_desde is not None and t - self.ausente_desde >= self.t.pausa_min_s:
            return self.ausente_desde, t - self.ausente_desde
        return None


def pausa_sugerida(n: int) -> dict:
    """Una pausa del catálogo fijo (motivo «general»), rotando con cada recordatorio. Nunca se inventa."""
    pausas = [p for p in herramientas.cargar_catalogo()["pausas"] if "general" in p["motivos"]]
    return pausas[n % len(pausas)]


class CorteCamara:
    """Decide qué hacer cada vez que la cámara no entrega un cuadro: esperar, reabrirla (una vez) o rendirse."""

    def __init__(self, max_s: float = CORTE_CAMARA_MAX_S):
        self.max_s = max_s
        self.desde: float | None = None  # cuándo empezó el corte en curso (reloj monótono)
        self.reabierta = False

    def cuadro_ok(self) -> float | None:
        """Llegó un cuadro: termina el corte. Devuelve desde cuándo duraba, o None si no había corte."""
        desde, self.desde, self.reabierta = self.desde, None, False
        return desde

    def fallo(self, t: float) -> str:
        """'esperar', 'reabrir' (una sola vez, a la mitad del plazo) o 'rendirse' (pasó el plazo)."""
        if self.desde is None:
            self.desde = t
        corte = t - self.desde
        if corte >= self.max_s:
            return "rendirse"
        if corte >= self.max_s / 2 and not self.reabierta:
            self.reabierta = True
            return "reabrir"
        return "esperar"


RECORDAR_FIN_S = 10 * 60  # tras el tiempo planeado, el aviso «la cámara sigue encendida» se repite cada 10 min


class FinDelPlan:
    """Avisa cuando se cumple el tiempo planeado y lo repite. No termina la sesión: eso lo decide la persona.

    Por qué (tarea I2): con la cámara oculta ya no hay una ventana encima que recuerde que sigue encendida, y el
    monitor no se detiene solo al cumplirse la duración.
    """

    def __init__(self, inicio: float, duracion_min: int, cada_s: float = RECORDAR_FIN_S):
        self.fin_plan = inicio + duracion_min * 60
        self.cada_s = cada_s
        self.ultimo: float | None = None

    def revisar(self, t: float) -> bool:
        if t < self.fin_plan or (self.ultimo is not None and t - self.ultimo < self.cada_s):
            return False
        self.ultimo = t
        return True


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


# ---------------------------------------------------------------- mano en la cara y mirada fuera (tarea J5)
# Salen de los mismos 33 puntos de MediaPipe Pose, sin otro modelo. Los índices van como números, y no con
# vision.PoseLandmark, para que las pruebas no necesiten MediaPipe.
NARIZ, OJO_IZQ, OJO_DER, OREJA_IZQ, OREJA_DER, BOCA_IZQ, BOCA_DER = 0, 2, 5, 7, 8, 9, 10
HOMBRO_IZQ, HOMBRO_DER = 11, 12
MANOS = ((15, 17, 19, 21), (16, 18, 20, 22))  # muñeca, meñique, índice y pulgar de cada mano
PUNTOS_CARA = (NARIZ, OJO_IZQ, OJO_DER, OREJA_IZQ, OREJA_DER, BOCA_IZQ, BOCA_DER)
VISIBILIDAD_MANO_MIN = 0.5  # con la mano fuera de cuadro MediaPipe igual la ubica, pero con visibilidad de 0,1
MANO_CARA_UMBRAL = 0.15  # distancia de la mano a la cara, en anchos de hombros. En los videos sin tocarse la cara,
# lo más cerca que pasó una mano fue 0,17 (derecho.mp4); sostener el celular frente a la cara dio 0,14 a 0,23.
# No hay todavía un video tocándose la cara: el umbral es el más bajo que no marca nada en los tres videos.
MANO_CARA_MIN_S = 1.0  # menos de 1 s es la mano que pasa frente a la cara
GIRO_UMBRAL = 0.15  # cuánto se corre la nariz del centro de las orejas (en distancias entre orejas) frente a la
# línea base. Derecho, el 90 % de los cuadros quedó a ±0,07 de su base; mirar a un lado (distraido.mp4) dio +0,20 a
# +0,38. La línea base sale de la calibración, así que una cámara corrida a un lado no cuenta como mirar fuera.
MIRADA_MIN_S = 2.0  # un vistazo de menos de 2 s a la libreta o al teclado no cuenta
TOLERANCIA_GESTO_S = 0.5  # un cuadro suelto sin el gesto no parte un episodio en dos
MIRADA_DEMO_S = 5  # en modo demo, aviso a los 5 s mirando fuera, como la postura
MIRADA_MIN_ALERTA_S, MIRADA_MAX_ALERTA_S = 5, 120  # «Ajustes»: menos de 5 s avisaría por mirar la libreta; más de
# 2 min ya no avisa «en el momento»
MIRADA_ALERTA_S = 20  # por defecto, igual que la postura: deja leer un apunte en papel sin que salga el aviso
MOSTRAR_TRAS_CALIBRAR_S = 2.0  # con la cámara «solo al calibrar», la ventana queda 2 s más para ver que terminó


def distancia_mano_cara(puntos, ancho: int, alto: int) -> float | None:
    """La menor distancia entre un punto visible de una mano y uno de la cara, en anchos de hombros.

    None si no se ve ninguna mano o los hombros no alcanzan para medir.
    """
    ancho_hombros = abs(puntos[HOMBRO_IZQ].x - puntos[HOMBRO_DER].x) * ancho
    if ancho_hombros < 1:
        return None
    mejor = None
    for mano in MANOS:
        for i in mano:
            p = puntos[i]
            if p.visibility < VISIBILIDAD_MANO_MIN:
                continue
            for j in PUNTOS_CARA:
                c = puntos[j]
                d = math.hypot((p.x - c.x) * ancho, (p.y - c.y) * alto) / ancho_hombros
                mejor = d if mejor is None else min(mejor, d)
    return mejor


def giro_cabeza(puntos) -> float | None:
    """Dónde queda la nariz entre las dos orejas: cerca de 0 de frente, y crece al girar la cabeza. None si no se ve."""
    nariz, izq, der = puntos[NARIZ], puntos[OREJA_IZQ], puntos[OREJA_DER]
    if nariz.visibility < VISIBILIDAD_MIN:
        return None
    separacion = abs(izq.x - der.x)
    if separacion < 1e-3:
        return None
    return (nariz.x - (izq.x + der.x) / 2) / separacion


class Episodio:
    """Un gesto que dura: empieza cuando se cumple la condición y termina cuando deja de cumplirse más de
    TOLERANCIA_GESTO_S. Cuenta si duró al menos min_s."""

    def __init__(self, min_s: float):
        self.min_s = min_s
        self.desde: float | None = None
        self.ultima: float | None = None

    def actualizar(self, t: float, cumple: bool) -> tuple[float, float] | None:
        """Devuelve (inicio, duración) cuando termina un episodio que contó."""
        if cumple:
            if self.desde is None:
                self.desde = t
            self.ultima = t
            return None
        if self.desde is not None and t - self.ultima > TOLERANCIA_GESTO_S:
            return self.cerrar()
        return None

    def dura(self) -> float:
        return 0.0 if self.desde is None else self.ultima - self.desde

    def cerrar(self) -> tuple[float, float] | None:
        desde, duracion = self.desde, self.dura()
        self.desde = self.ultima = None
        return (desde, duracion) if desde is not None and duracion >= self.min_s else None


class Gestos:
    """Mano en la cara y mirada fuera de la pantalla, con la alerta de mirada (tarea J5).

    - Mano en la cara: solo se registra (cuántas veces y cuánto tiempo); no avisa.
    - Mirada fuera: la línea base del giro sale de la calibración de la postura. Se registra cada episodio de al menos
      MIRADA_MIN_S y, si la persona lo eligió, avisa tras alerta_s seguidos, una vez por episodio y con cooldown.
    """

    def __init__(self, alerta_s: float, avisar: bool, cooldown_s: float):
        self.mano = Episodio(MANO_CARA_MIN_S)
        self.mirada = Episodio(MIRADA_MIN_S)
        self.alerta_s, self.avisar, self.cooldown_s = alerta_s, avisar, cooldown_s
        self.base_giro: float | None = None
        self.giro: float | None = None  # giro actual frente a la base, para --detalle
        self.distancia: float | None = None  # distancia mano–cara actual, para --detalle
        self._calibracion: list[float] = []
        self.ultima_alerta = float("-inf")
        self.armada = True

    def recalibrar(self) -> None:
        self.base_giro, self._calibracion = None, []

    def actualizar(self, t: float, puntos, ancho: int, alto: int, calibrando: bool) -> tuple[list[tuple[str, float, float]], bool]:
        """Devuelve (episodios que terminaron, como (tipo, inicio, duración); si toca la alerta de mirada)."""
        terminados = []
        self.distancia = distancia_mano_cara(puntos, ancho, alto) if puntos else None
        fin = self.mano.actualizar(t, self.distancia is not None and self.distancia < MANO_CARA_UMBRAL)
        if fin:
            terminados.append(("mano_cara", *fin))

        giro = giro_cabeza(puntos) if puntos else None
        if calibrando:
            if giro is not None:
                self._calibracion.append(giro)
            self.giro = None
        else:
            if self.base_giro is None and self._calibracion:
                self.base_giro = statistics.median(self._calibracion)
            self.giro = None if giro is None or self.base_giro is None else giro - self.base_giro
        fin = self.mirada.actualizar(t, self.giro is not None and abs(self.giro) > GIRO_UMBRAL)
        if fin:
            terminados.append(("mirada_fuera", *fin))
        if self.mirada.desde is None:
            self.armada = True

        alerta = (self.avisar and self.armada and self.mirada.dura() >= self.alerta_s
                  and t - self.ultima_alerta >= self.cooldown_s)
        if alerta:
            self.armada, self.ultima_alerta = False, t
        return terminados, alerta

    def cerrar(self) -> list[tuple[str, float, float]]:
        """Al terminar la sesión: los episodios en curso también cuentan si duraron lo suficiente."""
        return [(tipo, *fin) for tipo, ep in (("mano_cara", self.mano), ("mirada_fuera", self.mirada))
                if (fin := ep.cerrar())]


# ---------------------------------------------------------------- avisos


TONOS = {  # (frecuencia en Hz, milisegundos): cada tipo de aviso suena distinto
    "postura": [(660, 160), (520, 220)], "distraccion": [(880, 140), (1175, 220)],
    "pausa": [(523, 150), (659, 150), (784, 220)], "tiempo": [(784, 180), (523, 260)],
    "mirada": [(988, 140), (740, 220)],
}
MUESTREO_HZ = 22050  # de sobra para tonos de menos de 1,2 kHz, y el sonido entero pesa unos 25 KB
VOLUMEN = 0.6  # fracción del máximo: se oye sin sobresaltar; el volumen final lo pone Windows
RAMPA_MS = 8  # subida y bajada suaves en cada tono: sin ellas suena un clic al empezar y al terminar
SILENCIO_ENTRE_TONOS_MS = 30


@functools.lru_cache(maxsize=None)
def sonido_wav(tipo: str) -> bytes:
    """Los tonos del aviso como un WAV en memoria (16 bits, mono). Es un sonido sintético: nunca se escribe en disco
    y no tiene nada que ver con el micrófono, que BioFocus no abre."""
    muestras = bytearray()
    rampa = max(1, MUESTREO_HZ * RAMPA_MS // 1000)
    for frecuencia, ms in TONOS[tipo]:
        n = MUESTREO_HZ * ms // 1000
        for i in range(n):
            envolvente = min(1.0, i / rampa, (n - 1 - i) / rampa)
            valor = 32767 * VOLUMEN * envolvente * math.sin(2 * math.pi * frecuencia * i / MUESTREO_HZ)
            muestras += struct.pack("<h", int(valor))
        muestras += bytes(2 * (MUESTREO_HZ * SILENCIO_ENTRE_TONOS_MS // 1000))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(MUESTREO_HZ)
        w.writeframes(bytes(muestras))
    return buffer.getvalue()


def sonar(tipo: str) -> None:
    """Un sonido corto, en otro hilo para no frenar la cámara.

    Suena con PlaySound, por el audio normal de Windows, como cualquier programa (tarea J1). Antes era
    winsound.Beep, el pitido del sistema, y en el equipo del autor no se oía. Si PlaySound falla, queda el sonido
    de alerta de Windows.
    """
    if sys.platform != "win32":
        return
    import winsound

    wav = sonido_wav(tipo)

    def tocar() -> None:
        try:
            winsound.PlaySound(wav, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        except RuntimeError:
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except RuntimeError:
                pass

    threading.Thread(target=tocar, daemon=True).start()


def avisar(emergentes: emergente.Emergentes | None, aviso: dict) -> None:
    """Sonido y aviso emergente encima de todo (tarea I1): se ven aunque la ventana de la cámara esté detrás."""
    if emergentes is None:  # --sin-ventana, para pruebas: ni sonido ni aviso
        return
    sonar(aviso["tipo"])
    emergentes.mostrar(aviso["tipo"], aviso["titulo"], aviso["detalle"])


def configuracion(args: argparse.Namespace) -> tuple[Tiempos, float]:
    """Tiempos y caída de la sesión. La sensibilidad de «Ajustes» solo vale en el modo normal (tarea I3)."""
    if args.modo_demo:
        return DEMO, CAIDA_ALERTA
    tiempos = replace(NORMAL, postura_sostenida_s=args.postura_s, distraccion_s=args.distraccion_s,
                      pausa_cada_s=args.pausa_cada_min * 60)
    return tiempos, args.caida_postura / 100


COLOR_CATEGORIA = {  # RGB
    "sirve": (46, 160, 67),
    "no_sirve": (218, 54, 51),
    "neutro": (110, 118, 129),
    "sin_clasificar": (150, 150, 150),
}
NOMBRE_CATEGORIA = {"sirve": "sirve", "no_sirve": "no sirve", "neutro": "neutro", "sin_clasificar": "sin clasificar"}
COLOR_POSTURA = {"bien": (46, 160, 67), "revisa": (230, 140, 0), "no_te_veo": (150, 150, 150), "calibrando": (56, 139, 253)}
COLOR_MIRADA = (124, 58, 237)


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

    def __init__(self, ruta_bd: Path | None, meta: str, duracion_min: int, modo_demo: bool, sin_internet: bool = False):
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
            "INSERT INTO estado_monitor (sesion_id, pid, modo_demo, actualizado, postura, sin_internet) "
            "VALUES (?, ?, ?, ?, 'calibrando', ?)",
            (self.id, os.getpid(), 1 if modo_demo else 0, _ts(ahora), 1 if sin_internet else 0),
        )
        datos.agregar_evento(self.con, self.id, _ts(ahora), "inicio_sesion",
                             detalle="monitor en vivo" + (", modo demo" if modo_demo else ""))
        self.con.commit()

    def tramo(self, tramo: ventanas.Tramo) -> None:
        if tramo.duracion_s <= 0:
            return
        inicio = _ts(tramo.inicio)
        # Si la app dio al monitor por caído (por ejemplo, tras suspender el equipo), ya guardó este tramo
        # con vivo.cerrar_sin_monitor: no se escribe otra vez.
        if self.con.execute(
            "SELECT 1 FROM eventos WHERE sesion_id = ? AND tipo = 'ventana' AND ts = ?", (self.id, inicio)
        ).fetchone():
            return
        datos.agregar_evento(self.con, self.id, inicio, "ventana",
                             app=tramo.clase.app, categoria=tramo.clase.categoria, duracion_s=tramo.duracion_s)
        self.con.commit()

    def pausa(self, inicio: float, duracion_s: float) -> None:
        datos.agregar_evento(self.con, self.id, _ts(inicio), "pausa", duracion_s=int(duracion_s),
                             detalle="fuera de cuadro")
        self.con.commit()

    def gesto(self, tipo: str, inicio: float, duracion_s: float) -> None:
        datos.agregar_gesto(self.con, self.id, _ts(inicio), tipo, round(duracion_s))
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

    def pidio_recalibrar(self) -> bool:
        """True si la app pidió recalibrar con su botón (tarea I2). Deja la marca en 0 para no repetirlo."""
        fila = self.con.execute("SELECT recalibrar FROM estado_monitor WHERE sesion_id = ?", (self.id,)).fetchone()
        if fila is None or not fila["recalibrar"]:
            return False
        self.con.execute("UPDATE estado_monitor SET recalibrar = 0 WHERE sesion_id = ?", (self.id,))
        self.con.commit()
        return True

    def pide_sin_internet(self) -> bool:
        """Lo que marca ahora el interruptor «Modo sin internet» de la app para esta sesión (tarea J6)."""
        fila = self.con.execute("SELECT sin_internet FROM estado_monitor WHERE sesion_id = ?", (self.id,)).fetchone()
        return bool(fila and fila["sin_internet"])

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
    import numpy as np
    from mediapipe.tasks.python import BaseOptions, vision

    verificar_modelo()
    tiempos, caida = configuracion(args)
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
    # «Modo sin internet» (tarea J6): lo pide la app con --sin-internet, o lo fija OFFLINE_MODE en .env. Lo de .env
    # no se puede apagar desde la app.
    sin_internet_fijo = ventanas.sin_internet_en(ventanas.proveedor.leer_env())
    sin_internet = args.sin_internet or sin_internet_fijo
    try:
        registro = Registro(args.bd, args.meta, args.duracion, args.modo_demo, sin_internet)
    except ErrorMonitor:
        detector.close()
        fuente.release()
        raise
    print(f"Sesión {registro.id} iniciada{' en modo demo' if args.modo_demo else ''}. "
          f"{'Video: ' + str(args.video) if args.video else 'Cámara ' + str(args.camara)}"
          f"{' oculta' if args.ocultar_camara else ''}. q termina, c recalibra.", flush=True)
    print(f"Sensibilidad: caída {caida * 100:.0f} % durante {tiempos.postura_sostenida_s:.0f} s, "
          f"distracción {tiempos.distraccion_s:.0f} s, pausa cada {tiempos.pausa_cada_s / 60:.1f} min, "
          f"mirada fuera {MIRADA_DEMO_S if args.modo_demo else args.mirada_s} s"
          f"{' (sin aviso)' if args.sin_alerta_mirada else ''}."
          + (" Cámara visible solo al calibrar." if args.camara_al_calibrar and not args.ocultar_camara else ""), flush=True)

    clasificador = ventanas.Clasificador(args.meta, sin_internet=sin_internet)
    print(f"Clasificador: {clasificador.perfil.proveedor if clasificador.perfil else 'solo reglas'}"
          f"{' (modo sin internet: ningún título sale del equipo)' if sin_internet else ''}.", flush=True)
    hilo = ventanas.HiloVentanas(ventanas.SeguidorVentanas(clasificador))
    hilo.start()
    postura = Postura(tiempos, time.time(), caida)
    distraccion = Distraccion(tiempos)
    pausas = Pausas(tiempos, time.time())
    gestos = Gestos(MIRADA_DEMO_S if args.modo_demo else args.mirada_s, not args.sin_alerta_mirada, tiempos.cooldown_s)
    fin_del_plan = FinDelPlan(registro.inicio, args.duracion)
    emergentes = None if args.sin_ventana else emergente.Emergentes()
    pantalla = None if args.sin_ventana or args.ocultar_camara else Pantalla()
    # Con «solo al calibrar» (tarea J2) la ventana se abre al calibrar y se cierra sola al tener la línea base.
    solo_al_calibrar = pantalla is not None and args.camara_al_calibrar
    ventana_abierta = False
    calibrada_en: float | None = None  # cuándo quedó la línea base, para esconder la ventana un momento después
    cerrada_a_mano = False  # la persona cerró la ventana de calibración: no se vuelve a abrir hasta recalibrar
    for nombre in ("SIGBREAK", "SIGINT"):
        if hasattr(signal, nombre):
            signal.signal(getattr(signal, nombre), _interrumpir)

    motivo = "interrumpido"
    aviso: dict | None = None
    t0_mono = time.monotonic()
    ultimo_ms, ultimo_latido, cuadros_video, ultimo_detalle = -1, 0.0, 0, 0.0
    valor: float | None = None
    primera_vez = True
    corte = CorteCamara()
    tam_sin_imagen = (480, 640)  # alto y ancho del cuadro negro, hasta que la cámara entregue el primero
    try:
        while True:
            ok, cuadro = fuente.read()
            if not ok and args.video:
                motivo = "fin del video" if cuadros_video else "el video no se pudo leer"
                break
            if not ok:  # la cámara no entregó cuadro: se tolera un corte corto sin cerrar la sesión
                if corte.desde is None:
                    print("La cámara no entrega imagen: reintento.", flush=True)
                accion = corte.fallo(time.monotonic())
                if accion == "rendirse":
                    motivo = "la cámara dejó de entregar cuadros"
                    break
                if accion == "reabrir":
                    fuente.release()
                    fuente = cv2.VideoCapture(args.camara)
                time.sleep(ESPERA_SIN_CUADRO_S)
                cuadro = np.zeros((*tam_sin_imagen, 3), dtype=np.uint8)  # cuadro negro: no hay nada que detectar
            else:
                inicio_corte = corte.cuadro_ok()
                if inicio_corte is not None:
                    print(f"La cámara volvió tras {time.monotonic() - inicio_corte:.1f} s sin imagen.", flush=True)
                if args.video:  # una pasada, al ritmo del video, no más rápido
                    cuadros_video += 1
                    espera = t0_mono + cuadros_video / fps_video - time.monotonic()
                    if espera > 0:
                        time.sleep(espera)
                else:
                    cuadro = cv2.flip(cuadro, 1)  # como un espejo; el número de postura no cambia
            t = time.time()
            alto, ancho = cuadro.shape[:2]
            tam_sin_imagen = (alto, ancho)

            puntos = None
            if ok:
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
                avisar(emergentes, aviso)
            if postura.base is None:
                calibrada_en = None
            elif calibrada_en is None:
                calibrada_en = t
            terminados, alerta_mirada = gestos.actualizar(t, puntos, ancho, alto, postura.base is None)
            for tipo, inicio_gesto, duracion in terminados:
                registro.gesto(tipo, inicio_gesto, duracion)
                nombre_gesto = "MANO en la cara" if tipo == "mano_cara" else "MIRADA fuera de la pantalla"
                print(f"{nombre_gesto}: {duracion:.1f} s desde el s {inicio_gesto - registro.inicio:.1f}", flush=True)
            if alerta_mirada:
                segundos = int(gestos.mirada.dura())
                registro.gesto("alerta_mirada", t, segundos)
                aviso = {"tipo": "mirada", "hasta": t + AVISO_S, "color": COLOR_MIRADA,
                         "titulo": "¿Sigues en tu pantalla?",
                         "detalle": f"Llevas {segundos} s mirando hacia otro lado"}
                print(f"ALERTA mirada fuera a los {t - registro.inicio:.1f} s ({segundos} s)", flush=True)
                avisar(emergentes, aviso)
            pausa, recordar = pausas.actualizar(t, valor is not None, postura.base is not None)
            if pausa:
                registro.pausa(*pausa)
                print(f"PAUSA de {pausa[1]:.0f} s (fuera de cuadro)", flush=True)
            if recordar:
                sugerida = pausa_sugerida(pausas.recordatorios - 1)
                aviso = {"tipo": "pausa", "hasta": t + AVISO_S, "color": COLOR_POSTURA["calibrando"],
                         "titulo": "Toma una pausa",
                         "detalle": f"{sugerida['nombre']} · {sugerida['duracion_min']} min: {sugerida['pasos'][0]}"[:75]}
                print(f"RECORDATORIO de pausa a los {t - registro.inicio:.0f} s: {sugerida['nombre']}", flush=True)
                avisar(emergentes, aviso)
            if distraccion.revisar(t, foto.racha_no_sirve):
                segundos = int(t - foto.racha_no_sirve)
                registro.alerta("distraccion", t, app=foto.app,
                                detalle=f"{segundos} s seguidos en ventanas que no sirven a la meta")
                aviso = {"tipo": "distraccion", "hasta": t + AVISO_S, "color": COLOR_CATEGORIA["no_sirve"],
                         "titulo": "¿Esto sirve a tu meta?",
                         "detalle": f"{segundos} s seguidos en {foto.app}, que no sirve"}
                print(f"ALERTA distracción a los {t - registro.inicio:.1f} s ({foto.app})", flush=True)
                avisar(emergentes, aviso)
            if fin_del_plan.revisar(t):
                aviso = {"tipo": "tiempo", "hasta": t + AVISO_S, "color": COLOR_POSTURA["calibrando"],
                         "titulo": "Se cumplió tu tiempo",
                         "detalle": f"Planeaste {args.duracion} min. La cámara sigue encendida: termina en la app."}
                print(f"TIEMPO planeado cumplido a los {t - registro.inicio:.0f} s: la sesión sigue abierta.", flush=True)
                avisar(emergentes, aviso)
            if aviso and t > aviso["hasta"]:
                aviso = None
            if args.detalle and t - ultimo_detalle >= 1:
                ultimo_detalle = t
                num = lambda x: "—" if x is None else f"{x:+.2f}"  # noqa: E731
                print(detalle_segundo(t - registro.inicio, valor, postura, foto)
                      + f" | mano–cara {num(gestos.distancia)} · giro {num(gestos.giro)}", flush=True)

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
                pide = registro.pide_sin_internet() or sin_internet_fijo
                if pide != sin_internet:  # interruptor «Modo sin internet» de la app (tarea J6)
                    sin_internet = pide
                    clasificador.usar_sin_internet(sin_internet)
                    print(f"Modo sin internet {'encendido' if sin_internet else 'apagado'} a los "
                          f"{t - registro.inicio:.0f} s: clasificador "
                          f"{clasificador.perfil.proveedor if clasificador.perfil else 'solo reglas'}.", flush=True)
                if registro.pidio_recalibrar():  # botón «Recalibrar postura» de la app (tarea I2)
                    postura.recalibrar(t)
                    gestos.recalibrar()
                    aviso, calibrada_en, cerrada_a_mano = None, None, False
                    print(f"Recalibrando desde la app a los {t - registro.inicio:.0f} s.", flush=True)

            mostrar = pantalla is not None and (
                not solo_al_calibrar
                or (not cerrada_a_mano and (calibrada_en is None or t - calibrada_en < MOSTRAR_TRAS_CALIBRAR_S)))
            if mostrar and not ventana_abierta:
                cv2.namedWindow(TITULO_VENTANA, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(TITULO_VENTANA, 800, 600)
                ventana_abierta, primera_vez = True, True
            elif not mostrar and ventana_abierta:
                cv2.destroyWindow(TITULO_VENTANA)
                cv2.waitKey(1)
                ventana_abierta = False
                print(f"Línea base lista: escondo la cámara a los {t - registro.inicio:.0f} s.", flush=True)

            if ventana_abierta:
                transcurrido = t - registro.inicio
                estado = {
                    "encabezado": f"BioFocus · {_mmss(transcurrido)} de {args.duracion} min"
                                  + (" · modo demo" if args.modo_demo else "") + (" · video" if args.video else ""),
                    "meta": f"Meta: {args.meta}"[:80],
                    "postura": postura.estado,
                    "linea_postura": ("Cámara sin imagen: reintentando…" if corte.desde is not None
                                      else linea_postura(postura, t, valor is not None)),
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
                    gestos.recalibrar()
                    aviso, calibrada_en = None, None
                if cv2.getWindowProperty(TITULO_VENTANA, cv2.WND_PROP_VISIBLE) < 1:
                    if solo_al_calibrar:  # cerrar la ventana de calibración solo la esconde; la sesión sigue
                        ventana_abierta, cerrada_a_mano = False, True
                    else:
                        motivo = "ventana del monitor cerrada"
                        break
    except KeyboardInterrupt:
        motivo = "interrumpido"
    finally:
        for tramo in hilo.detener():
            registro.tramo(tramo)
        for tipo, inicio_gesto, duracion in gestos.cerrar():
            registro.gesto(tipo, inicio_gesto, duracion)
        final = pausas.cerrar(time.time())
        if final and motivo != "la cámara dejó de entregar cuadros":  # sin imagen no es una pausa
            registro.pausa(*final)
        registro.cerrar(time.time(), motivo)
        detector.close()
        fuente.release()
        if ventana_abierta:
            cv2.destroyAllWindows()
    print(f"Sesión {registro.id} terminada: {motivo}.", flush=True)
    return 0


def _entero_entre(minimo: int, maximo: int):
    """Tipo para argparse: un entero dentro de los topes de la sensibilidad."""
    def convertir(texto: str) -> int:
        try:
            valor = int(texto)
        except ValueError:
            raise argparse.ArgumentTypeError(f"debe ser un número entero entre {minimo} y {maximo}") from None
        if not minimo <= valor <= maximo:
            raise argparse.ArgumentTypeError(f"debe estar entre {minimo} y {maximo}")
        return valor
    return convertir


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
    p.add_argument("--sin-ventana", action="store_true", help="para pruebas: sin ventana, sin sonido y sin avisos emergentes")
    p.add_argument("--ocultar-camara", action="store_true",
                   help="sin la ventana de la cámara; los avisos salen igual, emergentes y con sonido")
    p.add_argument("--camara-al-calibrar", action="store_true",
                   help="muestra la ventana de la cámara solo mientras calibra (al empezar y al recalibrar)")
    p.add_argument("--mirada-s", type=_entero_entre(MIRADA_MIN_ALERTA_S, MIRADA_MAX_ALERTA_S), default=MIRADA_ALERTA_S,
                   help=f"segundos mirando fuera de la pantalla antes de avisar ({MIRADA_MIN_ALERTA_S} a "
                        f"{MIRADA_MAX_ALERTA_S}; en modo demo, {MIRADA_DEMO_S})")
    p.add_argument("--sin-alerta-mirada", action="store_true",
                   help="registra cuándo miras fuera de la pantalla, pero sin avisar")
    p.add_argument("--sin-internet", action="store_true",
                   help="los títulos ambiguos se clasifican con Ollama, en este equipo; nada sale a la nube")
    p.add_argument("--caida-postura", type=_entero_entre(CAIDA_MIN_PCT, CAIDA_MAX_PCT), default=round(CAIDA_ALERTA * 100),
                   help=f"%% bajo tu línea base que cuenta como mala postura ({CAIDA_MIN_PCT} a {CAIDA_MAX_PCT}; no aplica en modo demo)")
    p.add_argument("--postura-s", type=_entero_entre(POSTURA_MIN_S, POSTURA_MAX_S), default=int(NORMAL.postura_sostenida_s),
                   help=f"segundos de mala postura antes de avisar ({POSTURA_MIN_S} a {POSTURA_MAX_S})")
    p.add_argument("--distraccion-s", type=_entero_entre(DISTRACCION_MIN_S, DISTRACCION_MAX_S), default=int(NORMAL.distraccion_s),
                   help=f"segundos seguidos en algo que no sirve antes de avisar ({DISTRACCION_MIN_S} a {DISTRACCION_MAX_S})")
    p.add_argument("--pausa-cada-min", type=_entero_entre(PAUSA_MIN_MIN, PAUSA_MAX_MIN), default=int(NORMAL.pausa_cada_s // 60),
                   help=f"minutos sin pausa antes de recordarla ({PAUSA_MIN_MIN} a {PAUSA_MAX_MIN})")
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

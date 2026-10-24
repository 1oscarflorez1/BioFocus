"""Experimento 01: título de la ventana activa en Windows.

Imprime la hora y el título cada 2 s durante 60 s. No guarda nada en disco.
Solo usa la librería estándar (ctypes + API de Windows).
"""

import ctypes
import time
from datetime import datetime

INTERVALO_S = 2
DURACION_S = 60

user32 = ctypes.windll.user32


def titulo_ventana_activa() -> str:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "(sin ventana activa)"
    largo = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(largo + 1)
    user32.GetWindowTextW(hwnd, buffer, largo + 1)
    return buffer.value or "(sin título)"


def main() -> None:
    print(f"Leyendo la ventana activa cada {INTERVALO_S} s durante {DURACION_S} s. Ctrl+C para salir.")
    fin = time.monotonic() + DURACION_S
    while time.monotonic() < fin:
        hora = datetime.now().strftime("%H:%M:%S")
        print(f"{hora}  {titulo_ventana_activa()}", flush=True)
        time.sleep(INTERVALO_S)
    print("Fin.")


if __name__ == "__main__":
    main()

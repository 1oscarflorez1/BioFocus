r"""Aviso emergente de BioFocus: una ventanita encima de todo, abajo a la derecha, que se cierra sola.

La abre el monitor en un proceso aparte en cada alerta (tarea I1), para que se vea aunque la ventana de la
cámara esté detrás u oculta. Es la «notificación de Windows» de la propuesta inicial, hecha con Tkinter
(librería estándar): una notificación de Windows no se ve con «No molestar», y esta sí.

No roba el teclado: lo que la persona escribe sigue yendo a su ventana. Se cierra sola o con un clic.
El texto llega como argumentos (nunca por un shell) y se muestra como texto.

Para probarla a mano, desde la raíz:
    .venv\Scripts\python producto\aviso.py --tipo postura --titulo "Revisa tu postura" --detalle "Tu cabeza bajó 30 %"
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DURACION_S = 8  # lo bastante para leerla al levantar la vista; el monitor repite el aviso si la causa sigue
MAX_TEXTO = 90  # una línea corta: el detalle del monitor nunca lleva títulos de ventana, solo nombres de app
ANCHO, ALTO = 400, 112  # px; cabe en una pantalla de 1366 × 768 sin tapar el centro
MARGEN_DERECHO, MARGEN_INFERIOR = 24, 72  # px; encima de la barra de tareas de Windows (48 px)
# Fondo oscuro y texto blanco: contraste de 4,5:1 o más (WCAG AA). El tipo también va escrito, no solo en el color.
COLORES = {"postura": "#B45309", "distraccion": "#B91C1C", "pausa": "#1D4ED8", "tiempo": "#0F766E", "mirada": "#6D28D9"}
ETIQUETAS = {"postura": "Postura", "distraccion": "Distracción", "pausa": "Pausa", "tiempo": "Tiempo cumplido",
             "mirada": "Mirada fuera de la pantalla"}
SIN_CONSOLA = 0x08000000  # CREATE_NO_WINDOW: el proceso del aviso no abre una consola negra


def comando(tipo: str, titulo: str, detalle: str, segundos: int = DURACION_S) -> list[str]:
    """La línea para lanzar el aviso: una lista de argumentos, sin shell, con el texto recortado."""
    if tipo not in COLORES:
        raise ValueError(f"tipo de aviso desconocido: {tipo}")
    return [sys.executable, str(Path(__file__).resolve()), "--tipo", tipo,
            f"--titulo={titulo[:MAX_TEXTO]}", f"--detalle={detalle[:MAX_TEXTO]}", "--segundos", str(int(segundos))]


class Emergentes:
    """Lanza los avisos del monitor. Solo uno a la vez: el nuevo reemplaza al anterior."""

    def __init__(self, lanzar=subprocess.Popen):
        self._lanzar = lanzar
        self._actual = None

    def mostrar(self, tipo: str, titulo: str, detalle: str) -> None:
        self.cerrar()
        try:
            self._actual = self._lanzar(comando(tipo, titulo, detalle), stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL,
                                        creationflags=SIN_CONSOLA if sys.platform == "win32" else 0)
        except OSError:
            self._actual = None  # sin aviso emergente quedan el sonido, la ventana de la cámara y el panel de la app

    def cerrar(self) -> None:
        if self._actual is not None and self._actual.poll() is None:
            self._actual.terminate()
        self._actual = None


def _sin_activar(ventana) -> None:
    """En Windows, marca la ventanita para que no tome el foco (WS_EX_NOACTIVATE). Si falla, sigue igual."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = -20, 0x08000000, 0x00000080
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(ventana.winfo_id()) or ventana.winfo_id()
        estilo = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, estilo | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    except (AttributeError, OSError):
        pass


def mostrar(tipo: str, titulo: str, detalle: str, segundos: int) -> None:
    import tkinter as tk

    fondo = COLORES[tipo]
    raiz = tk.Tk()
    raiz.withdraw()
    raiz.overrideredirect(True)  # sin barra de título: no aparece en la barra de tareas
    raiz.attributes("-topmost", True)
    x = raiz.winfo_screenwidth() - ANCHO - MARGEN_DERECHO
    y = raiz.winfo_screenheight() - ALTO - MARGEN_INFERIOR
    raiz.geometry(f"{ANCHO}x{ALTO}+{x}+{y}")
    raiz.configure(bg=fondo, highlightthickness=2, highlightbackground="#FFFFFF")

    tk.Label(raiz, text=f"BioFocus · {ETIQUETAS[tipo]}", bg=fondo, fg="#FFFFFF", font=("Segoe UI", 10),
             anchor="w").pack(fill="x", padx=14, pady=(10, 0))
    tk.Label(raiz, text=titulo[:MAX_TEXTO], bg=fondo, fg="#FFFFFF", font=("Segoe UI", 16, "bold"),
             anchor="w").pack(fill="x", padx=14)
    tk.Label(raiz, text=detalle[:MAX_TEXTO], bg=fondo, fg="#FFFFFF", font=("Segoe UI", 11), anchor="w",
             wraplength=ANCHO - 28, justify="left").pack(fill="x", padx=14, pady=(0, 10))

    for elemento in (raiz, *raiz.winfo_children()):
        elemento.bind("<Button-1>", lambda _e: raiz.destroy())  # un clic la cierra
    raiz.update_idletasks()
    _sin_activar(raiz)
    raiz.deiconify()
    raiz.after(int(segundos * 1000), raiz.destroy)
    raiz.mainloop()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Aviso emergente de BioFocus (lo abre el monitor).")
    p.add_argument("--tipo", choices=sorted(COLORES), required=True)
    p.add_argument("--titulo", required=True)
    p.add_argument("--detalle", default="")
    p.add_argument("--segundos", type=int, default=DURACION_S)
    args = p.parse_args(argv)
    mostrar(args.tipo, args.titulo, args.detalle, max(1, min(args.segundos, 60)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

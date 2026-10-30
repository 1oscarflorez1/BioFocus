"""Datos de BioFocus: esquema SQLite de sesiones y eventos.

Qué se guarda: sesiones (inicio, fin, meta, duración planeada) y eventos con
app, categoría y duración. Qué NUNCA se guarda: títulos de ventana, imágenes,
video ni audio. Los eventos de ventana ni siquiera aceptan texto en `detalle`,
para que no haya dónde poner un título.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTA_BD = RAIZ / "data" / "biofocus.sqlite"

TIPOS_EVENTO = (
    "inicio_sesion",
    "fin_sesion",
    "ventana",
    "alerta_postura",
    "alerta_distraccion",
    "pausa",
)
CATEGORIAS = ("sirve", "no_sirve", "neutro", "sin_clasificar")
MAX_DETALLE = 80  # textos cortos y fijos del producto, nunca un título


def _lista_sql(valores: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in valores)


ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS sesiones (
    id INTEGER PRIMARY KEY,
    inicio TEXT NOT NULL,                  -- hora local 'AAAA-MM-DD HH:MM:SS'
    fin TEXT,                              -- NULL mientras la sesión sigue abierta
    meta TEXT NOT NULL,                    -- se queda en el equipo: ninguna herramienta la devuelve
    duracion_planeada_min INTEGER NOT NULL CHECK (duracion_planeada_min > 0),
    es_demo INTEGER NOT NULL DEFAULT 0 CHECK (es_demo IN (0, 1))
);
CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY,
    sesion_id INTEGER NOT NULL REFERENCES sesiones(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,                      -- hora local 'AAAA-MM-DD HH:MM:SS'
    tipo TEXT NOT NULL CHECK (tipo IN ({_lista_sql(TIPOS_EVENTO)})),
    app TEXT,                              -- nombre de la app, nunca el título de la ventana
    categoria TEXT CHECK (categoria IS NULL OR categoria IN ({_lista_sql(CATEGORIAS)})),
    duracion_s INTEGER CHECK (duracion_s IS NULL OR duracion_s >= 0),
    detalle TEXT CHECK (detalle IS NULL OR length(detalle) <= {MAX_DETALLE})
);
CREATE INDEX IF NOT EXISTS idx_eventos_tipo_ts ON eventos (tipo, ts);
CREATE INDEX IF NOT EXISTS idx_eventos_sesion ON eventos (sesion_id);
CREATE INDEX IF NOT EXISTS idx_sesiones_inicio ON sesiones (inicio);
"""


def conectar(ruta: str | Path | None = None) -> sqlite3.Connection:
    """Abre la base para escribir (y la crea si falta). La usan el producto y el generador demo."""
    ruta = Path(ruta) if ruta else RUTA_BD
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    return con


def conectar_lectura(ruta: str | Path | None = None) -> sqlite3.Connection:
    """Abre la base en solo lectura. Así la usan las herramientas del coach."""
    ruta = Path(ruta) if ruta else RUTA_BD
    if not ruta.exists():
        raise FileNotFoundError(
            "No hay base de datos todavía. Genera la demo con: python producto/generar_datos_demo.py"
        )
    con = sqlite3.connect(f"{ruta.resolve().as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def crear_sesion(
    con: sqlite3.Connection,
    inicio: str,
    fin: str | None,
    meta: str,
    duracion_planeada_min: int,
    es_demo: bool = False,
) -> int:
    cur = con.execute(
        "INSERT INTO sesiones (inicio, fin, meta, duracion_planeada_min, es_demo) VALUES (?, ?, ?, ?, ?)",
        (inicio, fin, meta, int(duracion_planeada_min), 1 if es_demo else 0),
    )
    return int(cur.lastrowid)


def agregar_evento(
    con: sqlite3.Connection,
    sesion_id: int,
    ts: str,
    tipo: str,
    app: str | None = None,
    categoria: str | None = None,
    duracion_s: int | None = None,
    detalle: str | None = None,
) -> int:
    if tipo not in TIPOS_EVENTO:
        raise ValueError(f"tipo de evento desconocido: {tipo!r}")
    if tipo == "ventana":
        if not app or categoria not in CATEGORIAS:
            raise ValueError("un evento de ventana necesita app y una categoría válida")
        if detalle is not None:
            raise ValueError("los eventos de ventana no llevan detalle: el título nunca se guarda")
    elif categoria is not None and categoria not in CATEGORIAS:
        raise ValueError(f"categoría desconocida: {categoria!r}")
    cur = con.execute(
        "INSERT INTO eventos (sesion_id, ts, tipo, app, categoria, duracion_s, detalle) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sesion_id, ts, tipo, app, categoria, duracion_s, detalle),
    )
    return int(cur.lastrowid)


def borrar_demo(con: sqlite3.Connection) -> int:
    """Borra solo las sesiones demo y sus eventos. Devuelve cuántas sesiones borró."""
    n = con.execute("SELECT COUNT(*) FROM sesiones WHERE es_demo = 1").fetchone()[0]
    con.execute("DELETE FROM eventos WHERE sesion_id IN (SELECT id FROM sesiones WHERE es_demo = 1)")
    con.execute("DELETE FROM sesiones WHERE es_demo = 1")
    return int(n)

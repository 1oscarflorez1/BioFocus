"""Genera 7 días de sesiones sintéticas para probar y mostrar el coach.

- Semilla fija 42: con la misma fecha final salen siempre los mismos datos.
- Todo queda marcado como demo (sesiones.es_demo = 1). Antes de generar se
  borra la demo anterior; los datos reales no se tocan.
- No genera títulos de ventana: solo app, categoría y duración.

Uso (desde la raíz del repo):
    python producto/generar_datos_demo.py                     # los 7 días que terminan ayer
    python producto/generar_datos_demo.py --hasta 2026-10-28  # fechas fijas
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import datos

SEMILLA = 42
DIAS = 7
FORMATO = "%Y-%m-%d %H:%M:%S"
UMBRAL_ALERTA_DISTRACCION_S = 180

METAS = [
    "Repasar cálculo integral",
    "Avanzar el proyecto BioFocus",
    "Leer el artículo de bases de datos",
    "Resolver el taller de estadística",
    "Preparar la exposición de redes",
]

# (app, categoría, segundos mínimos, segundos máximos, peso)
TRABAJO = [
    ("VS Code", "sirve", 300, 1200, 5),
    ("Chrome", "sirve", 180, 900, 3),
    ("Word", "sirve", 300, 900, 2),
    ("Claude", "sirve", 120, 600, 2),
    ("PowerShell", "sirve", 60, 300, 1),
]
DISTRACCION = [
    ("WhatsApp", "no_sirve", 60, 420, 4),
    ("Chrome", "no_sirve", 120, 600, 3),
    ("Discord", "no_sirve", 90, 480, 2),
    ("Opera", "no_sirve", 60, 300, 1),
]
NEUTRO = [
    ("Spotify", "neutro", 20, 90, 2),
    ("Explorador de archivos", "neutro", 20, 120, 2),
    ("Chrome", "sin_clasificar", 10, 60, 1),
]

# Franjas del día: (hora, minuto, probabilidad entre semana, duraciones planeadas posibles en min)
FRANJAS = [
    (8, 0, 0.75, (60, 90)),
    (14, 30, 0.9, (90, 120)),
    (19, 30, 0.65, (60, 90)),
]


def _elegir(rng: random.Random, opciones: list[tuple]) -> tuple[str, str, int]:
    app, categoria, minimo, maximo, _ = rng.choices(opciones, weights=[o[4] for o in opciones])[0]
    return app, categoria, rng.randint(minimo, maximo)


def _prob_distraccion(hora: int, min_desde_pausa: float) -> float:
    p = 0.10 + 0.12 * min(min_desde_pausa / 60, 1.5)
    if 15 <= hora <= 16:
        p += 0.18  # sobremesa: la franja que más distrae en la demo
    if hora >= 21:
        p += 0.10
    return min(p, 0.6)


def _tasa_postura_por_min(hora: int, min_desde_pausa: float) -> float:
    tasa = 0.008 + 0.03 * min(min_desde_pausa / 60, 1.5)
    if 16 <= hora <= 17:
        tasa += 0.02
    return tasa


def _sesion(con, rng: random.Random, inicio: datetime, planeada_min: int) -> int:
    """Crea una sesión con sus eventos y devuelve cuántos eventos escribió."""
    real_min = round(planeada_min * rng.uniform(0.7, 1.1))
    fin = inicio + timedelta(minutes=real_min)
    sesion_id = datos.crear_sesion(
        con, inicio.strftime(FORMATO), fin.strftime(FORMATO), rng.choice(METAS), planeada_min, es_demo=True
    )
    eventos = 0

    def evento(ts: datetime, tipo: str, **campos) -> None:
        nonlocal eventos
        datos.agregar_evento(con, sesion_id, ts.strftime(FORMATO), tipo, **campos)
        eventos += 1

    evento(inicio, "inicio_sesion", detalle="check-in")
    t = inicio
    ultima_pausa = inicio
    while t < fin:
        restante_s = int((fin - t).total_seconds())
        min_desde_pausa = (t - ultima_pausa).total_seconds() / 60
        if min_desde_pausa >= 45 and rng.random() < 0.5:
            duracion = min(rng.randint(3, 8) * 60, restante_s)
            if duracion >= 60:
                evento(t, "pausa", duracion_s=duracion, detalle="pausa tomada")
                t += timedelta(seconds=duracion)
                ultima_pausa = t
                continue
        sorteo = rng.random()
        p_distraccion = _prob_distraccion(t.hour, min_desde_pausa)
        if sorteo < p_distraccion:
            app, categoria, duracion = _elegir(rng, DISTRACCION)
        elif sorteo < p_distraccion + 0.12:
            app, categoria, duracion = _elegir(rng, NEUTRO)
        else:
            app, categoria, duracion = _elegir(rng, TRABAJO)
        duracion = min(duracion, restante_s)
        if duracion <= 0:
            break
        evento(t, "ventana", app=app, categoria=categoria, duracion_s=duracion)
        if categoria == "no_sirve" and duracion >= UMBRAL_ALERTA_DISTRACCION_S:
            evento(
                t + timedelta(seconds=UMBRAL_ALERTA_DISTRACCION_S),
                "alerta_distraccion",
                app=app,
                categoria=categoria,
                detalle="más de 3 min fuera de la meta",
            )
        tasa = _tasa_postura_por_min(t.hour, min_desde_pausa)
        for minuto in range(duracion // 60):
            if rng.random() < tasa:
                evento(
                    t + timedelta(minutes=minuto, seconds=rng.randint(0, 59)),
                    "alerta_postura",
                    detalle="postura distinta a la línea base",
                )
        t += timedelta(seconds=duracion)
    evento(fin, "fin_sesion", duracion_s=real_min * 60, detalle="cierre")
    return eventos


def generar(hasta: date, ruta: str | Path | None = None) -> dict:
    rng = random.Random(SEMILLA)
    con = datos.conectar(ruta)
    sesiones = eventos = 0
    try:
        with con:
            borradas = datos.borrar_demo(con)
            for i in range(DIAS):
                dia = hasta - timedelta(days=DIAS - 1 - i)
                factor = 0.6 if dia.weekday() >= 5 else 1.0
                elegidas = [f for f in FRANJAS if rng.random() < f[2] * factor] or [FRANJAS[1]]
                for hora, minuto, _, planes in elegidas:
                    inicio = datetime(dia.year, dia.month, dia.day, hora, minuto) + timedelta(
                        minutes=rng.randint(-20, 20)
                    )
                    eventos += _sesion(con, rng, inicio, rng.choice(planes))
                    sesiones += 1
    finally:
        con.close()
    return {
        "sesiones": sesiones,
        "eventos": eventos,
        "desde": (hasta - timedelta(days=DIAS - 1)).isoformat(),
        "hasta": hasta.isoformat(),
        "demo_reemplazada": borradas,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Genera 7 días de sesiones demo (semilla 42).")
    parser.add_argument(
        "--hasta",
        type=date.fromisoformat,
        default=date.today() - timedelta(days=1),
        help="último día AAAA-MM-DD (por defecto, ayer)",
    )
    parser.add_argument("--bd", type=Path, default=None, help="ruta de la base (por defecto data/biofocus.sqlite)")
    args = parser.parse_args()
    r = generar(args.hasta, args.bd)
    print(
        f"Demo generada: {r['sesiones']} sesiones y {r['eventos']} eventos del {r['desde']} al {r['hasta']} "
        f"(semilla {SEMILLA}). Reemplazó {r['demo_reemplazada']} sesiones demo anteriores."
    )


if __name__ == "__main__":
    main()

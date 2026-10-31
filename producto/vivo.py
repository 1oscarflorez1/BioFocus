"""Sesión en vivo: consultas y cierres que comparten el monitor, la app y la herramienta sesion_actual.

En la base no hay títulos de ventana, así que de aquí no puede salir ninguno. La meta solo sale con
resumen(..., con_meta=True), que usa la app en pantalla; la herramienta del coach no la pide.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import datos

LATIDO_VIEJO_S = 15  # sin señal de vida por más tiempo, el monitor se da por caído
F = datos.FORMATO


def _dt(texto: str) -> datetime:
    return datetime.strptime(texto, F)


def sesion_en_curso(con: sqlite3.Connection) -> sqlite3.Row | None:
    """La última sesión real abierta, con su estado en vivo."""
    try:
        return con.execute(
            "SELECT s.id, s.inicio, s.fin, s.meta, s.duracion_planeada_min, e.pid, e.modo_demo, e.actualizado, "
            "e.postura, e.postura_pct, e.app, e.categoria, e.ventana_desde, e.detener "
            "FROM sesiones s JOIN estado_monitor e ON e.sesion_id = s.id "
            "WHERE s.es_demo = 0 AND s.fin IS NULL ORDER BY s.id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:  # base de antes del monitor, sin la tabla estado_monitor
        return None


def esta_viva(fila: sqlite3.Row | None, ahora: datetime) -> bool:
    return fila is not None and (ahora - _dt(fila["actualizado"])).total_seconds() <= LATIDO_VIEJO_S


def cerrar_sesion(con: sqlite3.Connection, sesion_id: int, fin: datetime, motivo: str) -> bool:
    """Escribe fin_sesion y la hora de fin. No hace nada si la sesión ya estaba cerrada."""
    fila = con.execute("SELECT inicio, fin FROM sesiones WHERE id = ?", (sesion_id,)).fetchone()
    if fila is None or fila["fin"] is not None:
        return False
    inicio = _dt(fila["inicio"])
    fin = max(fin.replace(microsecond=0), inicio)
    datos.agregar_evento(con, sesion_id, fin.strftime(F), "fin_sesion",
                         duracion_s=int((fin - inicio).total_seconds()), detalle=motivo[: datos.MAX_DETALLE])
    con.execute("UPDATE sesiones SET fin = ? WHERE id = ?", (fin.strftime(F), sesion_id))
    con.execute("UPDATE estado_monitor SET postura = 'terminada', actualizado = ? WHERE sesion_id = ?",
                (fin.strftime(F), sesion_id))
    return True


def cerrar_huerfanas(con: sqlite3.Connection, ahora: datetime) -> int:
    """Cierra las sesiones reales abiertas cuyo monitor dejó de dar señales (se cayó o se apagó el equipo)."""
    filas = con.execute(
        "SELECT s.id, s.inicio, e.actualizado FROM sesiones s LEFT JOIN estado_monitor e ON e.sesion_id = s.id "
        "WHERE s.es_demo = 0 AND s.fin IS NULL"
    ).fetchall()
    cerradas = 0
    for f in filas:
        ultima = _dt(f["actualizado"] or f["inicio"])
        if (ahora - ultima).total_seconds() > LATIDO_VIEJO_S:
            cerradas += cerrar_sesion(con, f["id"], ultima, "cerrada sin monitor: dejó de dar señales")
    con.commit()
    return cerradas


def pedir_detener(con: sqlite3.Connection, sesion_id: int) -> None:
    con.execute("UPDATE estado_monitor SET detener = 1 WHERE sesion_id = ?", (sesion_id,))
    con.commit()


def ultima_sesion_real(con: sqlite3.Connection) -> int | None:
    fila = con.execute("SELECT id FROM sesiones WHERE es_demo = 0 ORDER BY inicio DESC, id DESC LIMIT 1").fetchone()
    return fila["id"] if fila else None


def resumen(con: sqlite3.Connection, sesion_id: int, ahora: datetime, *, con_meta: bool = False) -> dict:
    """Todo lo de una sesión para el panel en vivo y para el coach: tiempo, ventana y postura actuales,
    minutos por categoría (con el tramo en curso), alertas y tramos para la línea de tiempo."""
    s = con.execute("SELECT * FROM sesiones WHERE id = ?", (sesion_id,)).fetchone()
    if s is None:
        raise ValueError(f"No existe la sesión {sesion_id}")
    try:
        e = con.execute("SELECT * FROM estado_monitor WHERE sesion_id = ?", (sesion_id,)).fetchone()
    except sqlite3.OperationalError:
        e = None
    abierta = s["fin"] is None
    viva = abierta and esta_viva(e, ahora)
    if s["fin"]:
        fin = _dt(s["fin"])
    elif viva:
        fin = ahora
    else:
        fin = _dt(e["actualizado"]) if e else _dt(s["inicio"])
    inicio = _dt(s["inicio"])

    tramos = []
    for f in con.execute(
        "SELECT ts, app, categoria, duracion_s FROM eventos WHERE sesion_id = ? AND tipo = 'ventana' ORDER BY ts",
        (sesion_id,),
    ):
        t = _dt(f["ts"])
        tramos.append({"inicio": t, "fin": t + timedelta(seconds=f["duracion_s"] or 0), "app": f["app"],
                       "categoria": f["categoria"], "en_curso": False})
    if viva and e["ventana_desde"] and e["categoria"]:
        tramos.append({"inicio": _dt(e["ventana_desde"]), "fin": ahora, "app": e["app"], "categoria": e["categoria"],
                       "en_curso": True})

    segundos = {c: 0.0 for c in datos.CATEGORIAS}
    for t in tramos:
        segundos[t["categoria"]] += max(0.0, (t["fin"] - t["inicio"]).total_seconds())
    total = sum(segundos.values())

    alertas = [
        {"ts": f["ts"], "hora": f["ts"][11:19], "tipo": f["tipo"].removeprefix("alerta_"), "app": f["app"],
         "detalle": f["detalle"]}
        for f in con.execute(
            "SELECT ts, tipo, app, detalle FROM eventos WHERE sesion_id = ? AND tipo IN ('alerta_postura', 'alerta_distraccion') "
            "ORDER BY ts",
            (sesion_id,),
        )
    ]
    r = {
        "sesion_id": sesion_id,
        "estado": "en curso" if viva else ("terminada" if not abierta else "sin monitor"),
        "inicio": s["inicio"],
        "fin": s["fin"],
        "transcurrido_s": int((fin - inicio).total_seconds()),
        "plan_min": s["duracion_planeada_min"],
        "modo_demo": bool(e["modo_demo"]) if e else False,
        "ventana_actual": {"app": e["app"], "categoria": e["categoria"]} if viva and e["app"] else None,
        "postura": {"estado": e["postura"], "variacion_pct": e["postura_pct"]} if viva else None,
        "actualizado": e["actualizado"] if e else None,
        "minutos_por_categoria": {c: round(v / 60, 1) for c, v in segundos.items()},
        "porcentaje_por_categoria": {c: round(100 * v / total, 1) if total else 0.0 for c, v in segundos.items()},
        "alertas_postura": sum(a["tipo"] == "postura" for a in alertas),
        "alertas_distraccion": sum(a["tipo"] == "distraccion" for a in alertas),
        "alertas": alertas,
        "tramos": tramos,
    }
    if con_meta:
        r["meta"] = s["meta"]
    return r


def resumen_por_origen(con: sqlite3.Connection, es_demo: bool) -> dict:
    """Sesiones y minutos por categoría de un solo origen (reales o demo), para separarlos en pantalla."""
    filas = con.execute(
        "SELECT COUNT(*) AS n, MIN(inicio) AS desde, MAX(inicio) AS hasta FROM sesiones WHERE es_demo = ?",
        (1 if es_demo else 0,),
    ).fetchone()
    minutos = {c: 0.0 for c in datos.CATEGORIAS}
    for f in con.execute(
        "SELECT e.categoria, COALESCE(SUM(e.duracion_s), 0) AS s FROM eventos e JOIN sesiones s ON s.id = e.sesion_id "
        "WHERE e.tipo = 'ventana' AND s.es_demo = ? GROUP BY e.categoria",
        (1 if es_demo else 0,),
    ):
        minutos[f["categoria"]] = round(f["s"] / 60, 1)
    return {"sesiones": filas["n"], "desde": filas["desde"], "hasta": filas["hasta"], "minutos": minutos}


def sesiones_reales(con: sqlite3.Connection, limite: int = 10) -> list[dict]:
    filas = con.execute(
        "SELECT s.id, s.inicio, s.fin, s.duracion_planeada_min, "
        "(SELECT COUNT(*) FROM eventos e WHERE e.sesion_id = s.id AND e.tipo = 'alerta_postura') AS postura, "
        "(SELECT COUNT(*) FROM eventos e WHERE e.sesion_id = s.id AND e.tipo = 'alerta_distraccion') AS distraccion "
        "FROM sesiones s WHERE s.es_demo = 0 ORDER BY s.inicio DESC, s.id DESC LIMIT ?",
        (limite,),
    ).fetchall()
    return [
        {
            "Inicio": f["inicio"][:16],
            "Minutos": round((_dt(f["fin"]) - _dt(f["inicio"])).total_seconds() / 60, 1) if f["fin"] else None,
            "Plan (min)": f["duracion_planeada_min"],
            "Alertas de postura": f["postura"],
            "Alertas de distracción": f["distraccion"],
            "Estado": "terminada" if f["fin"] else "abierta",
        }
        for f in filas
    ]

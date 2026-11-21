"""App de BioFocus (Streamlit): sesión de estudio en vivo, coach, registros y ajustes, en pestañas.

Correr desde la raíz del repo:
    .venv\\Scripts\\python -m streamlit run producto\\app.py

"Empezar sesión de estudio" lanza producto/monitor.py como proceso aparte (cámara y ventana activa) y "Terminar sesión"
le pide que termine. Si el monitor se inicia desde la terminal, la app igual lo muestra.
Las pestañas salen de la prueba con una persona ajena (tarea I4): buscó sus registros y cómo recalibrar, y no los
encontró en una sola página larga.
"""

from __future__ import annotations

import dataclasses
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import agente
import datos
import herramientas
import monitor
import proveedor
import trazas
import vivo

# El título empieza por "BioFocus ·": reglas.json cuenta esta pestaña como neutra.
st.set_page_config(page_title="BioFocus · Coach", page_icon="🧭", layout="wide", initial_sidebar_state="collapsed")

RAIZ = Path(__file__).resolve().parent.parent
MONITOR = Path(__file__).resolve().parent / "monitor.py"
LOG_MONITOR = RAIZ / "data" / "monitor.log"
PREFERENCIAS = RAIZ / "data" / "preferencias.json"  # lo de la última sesión y la sensibilidad (sin la meta)
# Uso diario: 50 min, tiempos normales, la cámara trabajando escondida y la sensibilidad del experimento 01.
POR_DEFECTO = {
    "duracion": 50, "modo_demo": False, "imagen": "Cámara", "ver_camara": False,
    "caida_postura": round(monitor.CAIDA_ALERTA * 100), "postura_s": int(monitor.NORMAL.postura_sostenida_s),
    "distraccion_s": int(monitor.NORMAL.distraccion_s), "pausa_cada_min": int(monitor.NORMAL.pausa_cada_s // 60),
}
# Topes de cada valor guardado: los mismos del monitor, que los vuelve a validar al arrancar.
TOPES = {
    "duracion": (1, 600),
    "caida_postura": (monitor.CAIDA_MIN_PCT, monitor.CAIDA_MAX_PCT),
    "postura_s": (monitor.POSTURA_MIN_S, monitor.POSTURA_MAX_S),
    "distraccion_s": (monitor.DISTRACCION_MIN_S, monitor.DISTRACCION_MAX_S),
    "pausa_cada_min": (monitor.PAUSA_MIN_MIN, monitor.PAUSA_MAX_MIN),
}
GRABACIONES = RAIZ / "grabaciones"
ARRANQUE_MAX_S = 40  # MediaPipe y la cámara tardan unos segundos en abrir
PARADA_MAX_S = 12
LOG_MAX_BYTES = 512 * 1024  # tope de data/monitor.log
BOTON_EMPEZAR = "Empezar sesión de estudio"  # «Iniciar sesión» se leía como entrar con usuario y contraseña
AVISO_INICIO = (
    "Al empezar se enciende la cámara. La imagen se procesa en este equipo y no se guarda; si eliges verla, se abre "
    "la ventana «BioFocus monitor». Los avisos salen en una ventanita encima de todo, abajo a la derecha, con un "
    "sonido. Los títulos de ventanas que no son obvias van a Groq, con tu meta, para decidir si sirven; los de banco, "
    "correo y contraseñas nunca salen. Termina cuando quieras con «Terminar sesión»."
)
ORIGENES_COACH = {"reales": "Mis sesiones reales", "demo": "Semana de datos demo"}
CONFIRMACION_BORRADO = "BORRAR"
PESTANAS = {
    "sesion": ":material/self_improvement: Sesión",
    "coach": ":material/forum: Coach",
    "registros": ":material/bar_chart: Mis registros",
    "ajustes": ":material/tune: Ajustes",
}

EJEMPLOS = [
    "¿Cómo va mi sesión?",
    "¿A qué hora me distraigo más?",
    "¿Cuántas alertas de postura tuve esta semana?",
    "¿Qué pausa me recomiendas?",
]
OPCIONES_429 = {"no": "No", "principal": "Solo el activo", "todos": "Todos"}
OPCIONES_INVALIDA = {"no": "No", "una_vez": "Una vez", "siempre": "Siempre"}
CATEGORIAS = {"sirve": "Sirve", "no_sirve": "No sirve", "neutro": "Neutro", "sin_clasificar": "Sin clasificar"}
COLORES = {"Sirve": "#2ea043", "No sirve": "#da3633", "Neutro": "#6e7681", "Sin clasificar": "#a0a0a0"}
POSTURA = {"calibrando": "Calibrando", "bien": "Bien", "revisa": "Revisa tu postura", "no_te_veo": "No te veo", "terminada": "—"}
ALERTA = {"postura": "Postura", "distraccion": "Distracción"}
COLORES_ALERTA = ["#e3a008", "#8957e5"]  # postura, distracción

if "chat" not in st.session_state:
    st.session_state.chat = []  # {"rol": "user", "texto"} o {"rol": "assistant", "respuesta", "resuelta"}


def _bd():
    return closing(datos.conectar())  # crea el esquema si falta; modo WAL


def cargar_preferencias() -> dict:
    """Lo guardado (última sesión y sensibilidad); lo que falte o se salga de sus topes vuelve al valor por defecto."""
    try:
        guardadas = json.loads(PREFERENCIAS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        guardadas = {}
    pref = {**POR_DEFECTO, **{k: v for k, v in guardadas.items() if k in POR_DEFECTO}}
    for clave, (minimo, maximo) in TOPES.items():
        if not isinstance(pref[clave], int) or isinstance(pref[clave], bool) or not minimo <= pref[clave] <= maximo:
            pref[clave] = POR_DEFECTO[clave]
    pref["modo_demo"], pref["ver_camara"] = bool(pref["modo_demo"]), bool(pref["ver_camara"])
    return pref


def guardar_preferencias(**cambios) -> None:
    try:
        PREFERENCIAS.parent.mkdir(parents=True, exist_ok=True)
        PREFERENCIAS.write_text(json.dumps({**cargar_preferencias(), **cambios}), encoding="utf-8")
    except OSError:
        pass  # sin preferencias la app sigue igual


def texto_sensibilidad(pref: dict, demo: bool) -> str:
    if demo:
        d = monitor.DEMO
        return (f"Modo demo: postura si tu cabeza baja más de {round(monitor.CAIDA_ALERTA * 100)} % durante "
                f"{d.postura_sostenida_s:.0f} s · distracción a los {d.distraccion_s:.0f} s · pausa a los {d.pausa_cada_s:.0f} s")
    return (f"Postura si tu cabeza baja más de {pref['caida_postura']} % durante {pref['postura_s']} s · distracción a "
            f"los {pref['distraccion_s']} s · pausa cada {pref['pausa_cada_min']} min")


def _mmss(segundos: float) -> str:
    s = max(0, int(segundos))
    return f"{s // 60:02d}:{s % 60:02d}"


# ---------------------------------------------------------------- proveedor


def opciones_de_proveedor(configurados: list[proveedor.Perfil]) -> list[proveedor.Perfil]:
    """Los perfiles de .env y los otros modelos verificados de cada proveedor (misma llave)."""
    opciones, vistas = [], set()
    for p in configurados:
        for modelo in [p.modelo, *proveedor.MODELOS_POR_DEFECTO.get(p.proveedor, [])]:
            candidato = dataclasses.replace(p, modelo=modelo)
            if candidato.etiqueta not in vistas:
                vistas.add(candidato.etiqueta)
                opciones.append(candidato)
    return opciones


def cadena(opciones: list[proveedor.Perfil], configurados: list[proveedor.Perfil], etiqueta: str) -> list[proveedor.Perfil]:
    """El elegido va primero (es el "principal" de los interruptores); el respaldo es el primer perfil de .env distinto."""
    activo = next(p for p in opciones if p.etiqueta == etiqueta)
    respaldo = next((p for p in configurados if p.etiqueta != etiqueta), None)
    perfiles = [dataclasses.replace(activo, nombre="principal")]
    if respaldo:
        perfiles.append(dataclasses.replace(respaldo, nombre="respaldo"))
    return perfiles


# ---------------------------------------------------------------- monitor


def _ultimas_lineas(n: int = 8) -> str:
    try:
        return "\n".join(LOG_MONITOR.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


def recortar_log(ruta: Path = LOG_MONITOR, maximo: int = LOG_MAX_BYTES) -> None:
    """data/monitor.log no crece sin tope: si pasa de `maximo`, se queda con su segunda mitad."""
    try:
        if ruta.stat().st_size <= maximo:
            return
        cola = ruta.read_bytes()[-maximo // 2:]
        ruta.write_bytes(b"[... recortado por BioFocus ...]\n" + cola[cola.find(b"\n") + 1:])
    except OSError:
        pass


def comando_monitor(meta: str, duracion: int, demo: bool, video: Path | None, pref: dict) -> list[str]:
    # --meta=valor, en un solo argumento: una meta que empieza por guion («-repaso») no se toma por otra opción.
    cmd = [sys.executable, str(MONITOR), f"--meta={meta}", "--duracion", str(duracion)]
    if demo:
        cmd.append("--modo-demo")  # el modo demo usa sus tiempos fijos: la sensibilidad no se manda
    else:
        cmd += ["--caida-postura", str(pref["caida_postura"]), "--postura-s", str(pref["postura_s"]),
                "--distraccion-s", str(pref["distraccion_s"]), "--pausa-cada-min", str(pref["pausa_cada_min"])]
    if not pref["ver_camara"]:
        cmd.append("--ocultar-camara")
    if video:
        cmd += ["--video", str(video)]
    return cmd


def iniciar_monitor(meta: str, duracion: int, demo: bool, video: Path | None, pref: dict) -> str | None:
    """Lanza el monitor como proceso aparte y espera a que registre la sesión. Devuelve un error o None."""
    LOG_MONITOR.parent.mkdir(parents=True, exist_ok=True)
    recortar_log()
    cmd = comando_monitor(meta, duracion, demo, video, pref)
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    lanzado = datetime.now().replace(microsecond=0).strftime(datos.FORMATO)
    with open(LOG_MONITOR, "a", encoding="utf-8") as log:
        log.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} · desde la app · {'modo demo' if demo else 'normal'}"
                  f" · {video.name if video else 'cámara'}{'' if pref['ver_camara'] else ' oculta'}\n")
        log.flush()
        proceso = subprocess.Popen(cmd, cwd=RAIZ, stdout=log, stderr=subprocess.STDOUT, creationflags=flags,
                                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    limite = time.time() + ARRANQUE_MAX_S
    while time.time() < limite:
        if proceso.poll() is not None:
            return f"El monitor no arrancó (salida {proceso.returncode}). Últimas líneas de data/monitor.log:\n\n{_ultimas_lineas()}"
        with _bd() as con:
            fila = vivo.sesion_en_curso(con)
        # En Windows, el python.exe del .venv lanza al intérprete real como hijo: su PID no es el de Popen.
        # Por eso se busca la sesión que empezó después del lanzamiento, y se guarda el grupo para Ctrl+Break.
        if fila is not None and fila["inicio"] >= lanzado:
            st.session_state.setdefault("grupo_monitor", {})[fila["id"]] = proceso.pid
            return None
        time.sleep(0.5)
    return "El monitor tarda demasiado en arrancar. Revisa data/monitor.log o inícialo desde la terminal."


def terminar_monitor(sesion_id: int) -> str | None:
    """Pide al monitor que termine (marca en la base). Si no responde, Ctrl+Break y, al final, cierra en la base."""
    pid = st.session_state.get("grupo_monitor", {}).get(sesion_id)  # solo si esta app lanzó el monitor
    with _bd() as con:
        vivo.pedir_detener(con, sesion_id)

    def cerrada(espera_s: float) -> bool:
        limite = time.time() + espera_s
        while time.time() < limite:
            with _bd() as con:
                if con.execute("SELECT fin FROM sesiones WHERE id = ?", (sesion_id,)).fetchone()["fin"]:
                    return True
            time.sleep(0.4)
        return False

    if cerrada(PARADA_MAX_S):
        return None
    if pid and sys.platform == "win32":
        try:
            os.kill(pid, signal.CTRL_BREAK_EVENT)  # solo llega si la app lanzó el monitor
            if cerrada(6):
                return None
        except OSError:
            pass
    with _bd() as con:  # en su última señal de vida, guardando el tramo de ventana que estaba en curso
        vivo.cerrar_sin_monitor(con, sesion_id, "cerrada desde la app: el monitor no respondió")
        con.commit()
    return "El monitor no respondió, así que cerré la sesión desde la app. Si su ventana sigue abierta, ciérrala con q."


def controles_en_curso(fila) -> None:
    """Terminar y recalibrar desde la app: con la cámara oculta no hace falta tocar su ventana (tarea I2)."""
    terminar, recalibrar = st.columns(2)
    if terminar.button("Terminar sesión", type="primary", key="terminar", icon=":material/stop_circle:", width="stretch"):
        with st.spinner("Terminando la sesión…"):
            error = terminar_monitor(fila["id"])
        st.session_state.aviso_sesion = error or "Sesión terminada: el monitor escribió fin_sesion."
        st.rerun()
    if recalibrar.button("Recalibrar postura", key="recalibrar", icon=":material/accessibility_new:", width="stretch",
                         help="Siéntate derecho, como quieres estudiar: en unos 5 s esa será tu nueva línea base."):
        with _bd() as con:
            vivo.pedir_recalibrar(con, fila["id"])
        st.session_state.aviso_sesion = "Sesión: recalibrando. Siéntate derecho unos 5 s, mirando la pantalla."
        st.rerun()


def formulario_inicio() -> None:
    videos = sorted(GRABACIONES.glob("*.mp4")) if GRABACIONES.is_dir() else []
    pref = cargar_preferencias()  # lo de la última sesión: abrir y empezar es una meta y un clic
    with st.form("iniciar_sesion"):
        st.markdown("**Empieza una sesión de estudio.** Escribe qué quieres lograr y presiona el botón.")
        meta = st.text_input("¿Qué quieres lograr en esta sesión?", placeholder="Ej.: repasar integración por partes",
                             max_chars=200)
        imagenes = ["Cámara"] + [v.name for v in videos]
        c1, c2 = st.columns(2)
        duracion = c1.number_input("Duración (min)", min_value=1, max_value=600, value=pref["duracion"])
        fuente = c2.selectbox("Imagen", imagenes,
                              index=imagenes.index(pref["imagen"]) if pref["imagen"] in imagenes else 0,
                              help="Plan B: un video de grabaciones/ en vez de la cámara.")
        c3, c4 = st.columns(2)
        ver = c3.toggle("Ver la imagen de la cámara", value=pref["ver_camara"],
                        help="Apagado, la cámara trabaja escondida y los avisos salen igual, encima de todo.")
        demo = c4.toggle("Modo demo (tiempos cortos)", value=pref["modo_demo"],
                         help="Para mostrar la app: postura 5 s, distracción 10 s y 30 s entre alertas del mismo tipo.")
        st.info(AVISO_INICIO, icon=":material/photo_camera:")
        if st.form_submit_button(BOTON_EMPEZAR, type="primary", icon=":material/play_arrow:"):
            if not meta.strip():
                st.error("Escribe la meta: el monitor la usa para decidir qué ventanas sirven.")
                return
            video = GRABACIONES / fuente if fuente != "Cámara" else None
            guardar_preferencias(duracion=int(duracion), modo_demo=bool(demo), imagen=fuente, ver_camara=bool(ver))
            with st.spinner("Abriendo el monitor (cámara y MediaPipe)… siéntate derecho para calibrar."):
                error = iniciar_monitor(meta.strip(), int(duracion), demo, video, cargar_preferencias())
            st.session_state.aviso_sesion = error or (
                "Sesión iniciada. Siéntate derecho 5 s para calibrar; los avisos saldrán encima de todo.")
            st.rerun()
    st.caption(texto_sensibilidad(pref, pref["modo_demo"]) + ". Cámbialo en «Ajustes».")


# ---------------------------------------------------------------- gráficos


def grafico_categorias(minutos: dict[str, float]):
    df = pd.DataFrame([{"Categoría": nombre, "Minutos": minutos[c]} for c, nombre in CATEGORIAS.items()])
    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=4, size=14)
        .encode(
            x=alt.X("Minutos:Q", title="Minutos"),
            y=alt.Y("Categoría:N", sort=None, title=None, axis=alt.Axis(labelOverlap=False, labelLimit=120)),
            color=alt.Color("Categoría:N", scale=alt.Scale(domain=list(COLORES), range=list(COLORES.values())), legend=None),
            tooltip=[alt.Tooltip("Categoría:N"), alt.Tooltip("Minutos:Q", format=".1f")],
        )
        .properties(height=alt.Step(28))
    )


def linea_de_tiempo(r: dict):
    inicio = datetime.strptime(r["inicio"], datos.FORMATO)
    dominio = [inicio.timestamp() * 1000, (inicio.timestamp() + max(r["transcurrido_s"], 30)) * 1000]  # ms, hora local
    tramos = pd.DataFrame(
        [{"Inicio": t["inicio"], "Fin": t["fin"], "Fila": "Ventanas", "App": t["app"], "Categoría": CATEGORIAS[t["categoria"]],
          "Minutos": round((t["fin"] - t["inicio"]).total_seconds() / 60, 1)} for t in r["tramos"]],
        columns=["Inicio", "Fin", "Fila", "App", "Categoría", "Minutos"],
    )
    alertas = pd.DataFrame(
        [{"Hora": datetime.strptime(a["ts"], datos.FORMATO), "Fila": "Alertas", "Tipo": ALERTA[a["tipo"]], "App": a["app"] or ""}
         for a in r["alertas"]],
        columns=["Hora", "Fila", "Tipo", "App"],
    )
    # Una sola franja: las ventanas como barras de color y cada alerta como una línea vertical encima.
    x = alt.X("Inicio:T", title=None, scale=alt.Scale(domain=dominio), axis=alt.Axis(format="%H:%M:%S", labelOverlap=True))
    y = alt.Y("Fila:N", title=None, axis=None, scale=alt.Scale(domain=["Sesión"]))
    tramos["Fila"], alertas["Fila"] = "Sesión", "Sesión"
    barras = alt.Chart(tramos).mark_bar(cornerRadius=3).encode(
        x=x, x2="Fin:T", y=y,
        color=alt.Color("Categoría:N", scale=alt.Scale(domain=list(COLORES), range=list(COLORES.values())),
                        legend=alt.Legend(orient="bottom", title="Ventana")),
        tooltip=["App:N", "Categoría:N", "Minutos:Q", alt.Tooltip("Inicio:T", format="%H:%M:%S")],
    )
    marcas = alt.Chart(alertas).mark_rule(strokeWidth=4).encode(
        x=alt.X("Hora:T", scale=alt.Scale(domain=dominio)), y=y,
        color=alt.Color("Tipo:N", scale=alt.Scale(domain=list(ALERTA.values()), range=COLORES_ALERTA),
                        legend=alt.Legend(orient="bottom", title="Alerta")),
        tooltip=["Tipo:N", "App:N", alt.Tooltip("Hora:T", format="%H:%M:%S")],
    )
    return alt.layer(barras, marcas).resolve_scale(color="independent").properties(height=alt.Step(46))


def grafico_alertas_por_dia(por_dia: list[dict]):
    df = pd.DataFrame([{"Día": a["dia"], "Tipo": ALERTA[a["tipo"]], "Alertas": a["n"]} for a in por_dia],
                      columns=["Día", "Tipo", "Alertas"])
    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X("Día:N", title=None, axis=alt.Axis(labelAngle=0)),
            xOffset="Tipo:N",
            y=alt.Y("Alertas:Q", title="Alertas", axis=alt.Axis(tickMinStep=1)),
            color=alt.Color("Tipo:N", scale=alt.Scale(domain=list(ALERTA.values()), range=COLORES_ALERTA),
                            legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["Día:N", "Tipo:N", "Alertas:Q"],
        )
        .properties(height=220)
    )


# ---------------------------------------------------------------- pestaña Sesión: panel en vivo


def panel_en_vivo() -> None:
    """Se refresca cada 2 s solo mientras hay una sesión en curso (sin sesión, el refresco cerraría los menús del formulario)."""
    ahora = datetime.now()
    with _bd() as con:
        fila = vivo.sesion_en_curso(con)
        sesion_id = fila["id"] if fila else vivo.ultima_sesion_real(con)
        r = vivo.resumen(con, sesion_id, ahora, con_meta=True) if sesion_id else None
    if (fila is not None) != st.session_state.get("habia_sesion", False):
        st.rerun()  # la sesión empezó o terminó fuera de esta página (terminal, tecla q): refresca los controles
    if r is None:
        st.info(f"Todavía no hay sesiones reales. Escribe una meta y presiona «{BOTON_EMPEZAR}».")
        return
    en_curso = r["estado"] == "en curso"
    st.markdown(f"#### {'Sesión en vivo' if en_curso else 'Última sesión real'}")
    st.caption(
        f"Meta: {r['meta']}  ·  {'modo demo (tiempos cortos)' if r['modo_demo'] else 'tiempos normales'}  ·  "
        + ("se actualiza cada 2 s" if en_curso else f"terminó a las {(r['fin'] or r['actualizado'] or '')[11:19]}")
    )
    if r["estado"] == "sin monitor":
        st.warning(f"El monitor no da señales desde las {r['actualizado'][11:19]}. Si se cerró, termina la sesión.")
    if en_curso and r["transcurrido_s"] >= r["plan_min"] * 60:
        st.warning("La cámara sigue encendida hasta que presiones «Terminar sesión».",
                   title=f"Se cumplieron los {r['plan_min']} min que planeaste", icon=":material/timer:")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tiempo", _mmss(r["transcurrido_s"]), f"de {r['plan_min']} min planeados", delta_color="off", delta_arrow="off")
    if r["ventana_actual"]:
        cat = CATEGORIAS.get(r["ventana_actual"]["categoria"], "—")
        c2.metric("Ventana actual", r["ventana_actual"]["app"], cat,
                  delta_color="green" if cat == "Sirve" else ("red" if cat == "No sirve" else "off"), delta_arrow="off")
    else:
        c2.metric("Ventana actual", "—", "sin datos", delta_color="off", delta_arrow="off")
    if r["postura"]:
        pct = r["postura"]["variacion_pct"]
        c3.metric("Postura", POSTURA.get(r["postura"]["estado"], r["postura"]["estado"]),
                  f"{pct:+.0f} % frente a tu línea base" if pct is not None else "sin línea base todavía", delta_color="off", delta_arrow="off")
    else:
        c3.metric("Postura", "—", "sin datos", delta_color="off", delta_arrow="off")
    c4.metric("Alertas", f"{r['alertas_postura']} · {r['alertas_distraccion']}", "postura · distracción", delta_color="off", delta_arrow="off")
    if r["pausas"]:
        st.caption(f"Pausas en esta sesión: {r['pausas']} (salir de cuadro {'10 s' if r['modo_demo'] else '1 min'} o más).")

    if r["alertas"]:
        a = r["alertas"][-1]
        hace = (ahora - datetime.strptime(a["ts"], datos.FORMATO)).total_seconds()
        texto = (f"A las {a['hora']}" + (f" en {a['app']}" if a["app"] else "")
                 + (f" · {a['detalle']}" if a["detalle"] else ""))
        titulo = f"Alerta de {ALERTA[a['tipo']].lower()}"
        if en_curso and hace <= 60:
            st.error(f"{texto} · hace {hace:.0f} s", title=titulo, icon=":material/warning:")
        else:
            st.info(texto, title=f"Última {titulo.lower()}")
    else:
        st.success("Sin alertas en esta sesión.")

    izquierda, derecha = st.columns([1, 2])
    with izquierda:
        st.caption("Minutos por categoría")
        st.altair_chart(grafico_categorias(r["minutos_por_categoria"]), width="stretch",
                        alt="Barras con los minutos de la sesión en ventanas que sirven, no sirven, neutras y sin clasificar")
    with derecha:
        st.caption("Línea de tiempo: ventanas por categoría y alertas")
        st.altair_chart(linea_de_tiempo(r), width="stretch",
                        alt="Línea de tiempo de la sesión: tramos de ventana por categoría y una marca por cada alerta")


# ---------------------------------------------------------------- pestaña Mis registros


def panel_registros() -> None:
    """Las sesiones listadas, con filtros por origen y fechas, cifras y gráficos (tarea I4)."""
    hoy = date.today()
    c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
    origen = c1.segmented_control("Datos", list(ORIGENES_COACH), format_func=ORIGENES_COACH.get, default="reales",
                                  required=True, key="origen_registros",
                                  help="Las sesiones reales y la semana demo nunca se suman.")
    rango = c2.date_input("Fechas", value=(hoy - timedelta(days=6), hoy), max_value=hoy, format="YYYY-MM-DD",
                          key="fechas_registros", help="Elige el primer y el último día. Por defecto, los últimos 7 días.")
    if not isinstance(rango, (tuple, list)) or len(rango) != 2:
        st.info("Elige también el último día del rango.")
        return
    desde, hasta = rango
    with _bd() as con:
        r = vivo.registros(con, origen == "demo", desde, hasta)
    sesiones = r["sesiones"]
    if not sesiones:
        st.info("No hay sesiones en esas fechas.")
        if origen == "demo":
            st.caption("Los datos demo se generan con `python producto/generar_datos_demo.py` (7 días que terminan ayer).")
        return

    terminadas = [s for s in sesiones if s["minutos"] is not None]
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Sesiones", len(sesiones), border=True)
    minutos = sum(s["minutos"] for s in terminadas)
    m2.metric("Minutos estudiados", f"{minutos:.0f}" if minutos >= 10 else f"{minutos:.1f}", border=True,
              help="Duración de las sesiones terminadas, de inicio a fin.")
    m3.metric("Alertas de postura", sum(s["alertas_postura"] for s in sesiones), border=True)
    m4.metric("Alertas de distracción", sum(s["alertas_distraccion"] for s in sesiones), border=True)
    m5.metric("Pausas", sum(s["pausas"] for s in sesiones), border=True,
              help="Veces que saliste de cuadro el tiempo de una pausa.")

    izquierda, derecha = st.columns(2)
    with izquierda.container(border=True):
        st.markdown("**Minutos frente a ventanas, por categoría**")
        st.altair_chart(grafico_categorias(r["minutos"]), width="stretch",
                        alt="Barras con los minutos del rango en ventanas que sirven, no sirven, neutras y sin clasificar")
    with derecha.container(border=True):
        st.markdown("**Alertas por día**")
        if r["por_dia"]:
            st.altair_chart(grafico_alertas_por_dia(r["por_dia"]), width="stretch",
                            alt="Barras con las alertas de postura y de distracción de cada día del rango")
        else:
            st.caption("Sin alertas en estas fechas.")

    st.markdown("**Sesiones**")
    tabla = pd.DataFrame([{
        "Inicio": s["inicio"][:16], "Meta": s["meta"], "Minutos": s["minutos"], "Plan (min)": s["plan_min"],
        "Postura": s["alertas_postura"], "Distracción": s["alertas_distraccion"], "Pausas": s["pausas"],
        "Min. en lo que no sirve": s["min_no_sirve"], "Estado": s["estado"],
    } for s in sesiones])
    st.dataframe(
        tabla, hide_index=True, width="stretch",
        column_config={
            "Meta": st.column_config.TextColumn(width="large"),
            "Minutos": st.column_config.NumberColumn(format="%.1f", help="Vacío si la sesión sigue abierta."),
            "Postura": st.column_config.NumberColumn(help="Alertas de postura"),
            "Distracción": st.column_config.NumberColumn(help="Alertas de distracción"),
        },
        alt="Tabla de sesiones con inicio, meta, minutos, plan, alertas, pausas, minutos en lo que no sirve y estado",
    )

    elegida = st.selectbox("Ver la línea de tiempo de una sesión", [s["id"] for s in sesiones],
                           format_func=lambda i: next(f"{s['inicio'][:16]} · {s['meta'][:60]}" for s in sesiones if s["id"] == i),
                           index=None, placeholder="Elige una sesión", key="sesion_detalle")
    if elegida is not None:
        with _bd() as con:
            detalle = vivo.resumen(con, elegida, datetime.now(), con_meta=True)
        st.altair_chart(linea_de_tiempo(detalle), width="stretch",
                        alt="Línea de tiempo de la sesión elegida: tramos de ventana por categoría y alertas")


# ---------------------------------------------------------------- pestaña Ajustes


def panel_sensibilidad() -> None:
    pref = cargar_preferencias()
    st.subheader("Sensibilidad de las alertas")
    st.caption("Se usa desde la próxima sesión, en modo normal. El modo demo usa siempre sus tiempos cortos y el 25 %, "
               "para que la demo salga igual. Si una alerta sale cuando estás bien sentado, recalibra antes de subirla.")
    with st.form("sensibilidad"):
        caida = st.slider("Cuánto puede bajar tu cabeza antes de avisar (%)", monitor.CAIDA_MIN_PCT, monitor.CAIDA_MAX_PCT,
                          pref["caida_postura"],
                          help="Frente a tu línea base. Volver a sentarse dio −15 % y encorvarse −43 % (experimento 01): "
                               "por eso va de 20 a 40.")
        postura_s = st.slider("Segundos con mala postura antes de avisar", monitor.POSTURA_MIN_S, monitor.POSTURA_MAX_S,
                              pref["postura_s"], help="Menos de 5 s es mirar el teclado.")
        distraccion_s = st.slider("Segundos seguidos en algo que no sirve antes de avisar", monitor.DISTRACCION_MIN_S,
                                  monitor.DISTRACCION_MAX_S, pref["distraccion_s"], step=5,
                                  help="Menos de 10 s cortaría un vistazo rápido a otra ventana.")
        pausa = st.slider("Recordarme una pausa cada (minutos)", monitor.PAUSA_MIN_MIN, monitor.PAUSA_MAX_MIN,
                          pref["pausa_cada_min"], step=5)
        guardar, restablecer = st.columns(2)
        if guardar.form_submit_button("Guardar", type="primary", icon=":material/save:", width="stretch"):
            guardar_preferencias(caida_postura=caida, postura_s=postura_s, distraccion_s=distraccion_s, pausa_cada_min=pausa)
            st.session_state.aviso_sesion = "Ajustes guardados: se usan desde la próxima sesión."
            st.rerun()
        if restablecer.form_submit_button("Volver a los valores de fábrica", icon=":material/restart_alt:", width="stretch"):
            guardar_preferencias(**{k: POR_DEFECTO[k] for k in ("caida_postura", "postura_s", "distraccion_s", "pausa_cada_min")})
            st.session_state.aviso_sesion = "Ajustes guardados: volvieron los valores de fábrica."
            st.rerun()


BORRABLES = {
    "reales": "Mis sesiones reales (con sus metas y eventos)",
    "demo": "La semana de datos demo",
    "trazas": "Las trazas del coach (tus preguntas y sus respuestas)",
    "reglas": "Las reglas que aprobaste en el coach",
    "log": "El registro del monitor (data/monitor.log)",
}


def borrar(que: str) -> str:
    """Borra lo elegido. Irreversible: solo se llama tras escribir la confirmación (ver panel_borrar)."""
    if que in ("reales", "demo"):
        with _bd() as con:
            n = datos.borrar_reales(con) if que == "reales" else datos.borrar_demo(con)
            datos.compactar(con)
        return f"Borré {n} sesiones {'reales' if que == 'reales' else 'demo'}."
    if que == "trazas":
        archivos = sorted(trazas.CARPETA.glob("*.jsonl")) if trazas.CARPETA.is_dir() else []
        for ruta in archivos:
            ruta.unlink(missing_ok=True)
        st.session_state.chat = []  # el chat en pantalla muestra las mismas preguntas
        return f"Borré {len(archivos)} archivos de trazas."
    ruta = herramientas.RUTA_REGLAS if que == "reglas" else LOG_MONITOR
    if not ruta.exists():
        return f"No había {ruta.name}."
    try:
        ruta.unlink()
    except OSError:
        return f"No pude borrar {ruta.name}: otro proceso lo tiene abierto. Termina la sesión y vuelve a intentarlo."
    return f"Borré {ruta.name}."


def panel_borrar() -> None:
    """Borrar exige escribir BORRAR: es la acción irreversible de BioFocus y la decide la persona."""
    with st.expander("Borrar mis datos", icon=":material/delete:"):
        st.caption(f"No se puede deshacer. Escribe {CONFIRMACION_BORRADO} para confirmar. "
                   "Una sesión en curso no se borra.")
        que = st.selectbox("Qué borrar", list(BORRABLES), format_func=BORRABLES.get, key="que_borrar")
        confirmacion = st.text_input("Confirmación", key="confirmar_borrado", placeholder=CONFIRMACION_BORRADO)
        if st.button("Borrar", disabled=confirmacion.strip() != CONFIRMACION_BORRADO, width="stretch"):
            st.session_state.aviso_sesion = "Datos: " + borrar(que)
            st.session_state.pop("confirmar_borrado", None)
            st.rerun()


def panel_privacidad() -> None:
    st.subheader("Tus datos")
    st.markdown(
        "- **La cámara** se procesa en este equipo; ninguna imagen se guarda ni sale.\n"
        "- **La base** (`data/biofocus.sqlite`) guarda sesiones y eventos: app, categoría, duración y alertas. "
        "Nunca títulos de ventana.\n"
        "- **Sale del equipo:** los títulos de ventana ambiguos y no privados, con tu meta, para clasificarlos; y lo "
        "que escribes al coach con cifras agregadas. Con `OFFLINE_MODE=true` en `.env` no sale nada.\n"
        "- **Las opciones técnicas** (proveedor e interruptores de prueba) están en la barra lateral, plegada."
    )
    panel_borrar()


# ---------------------------------------------------------------- barra lateral: solo lo técnico, plegada


with st.sidebar:
    tecnicas = st.expander("Opciones técnicas: proveedor e interruptores de prueba", icon=":material/build:")
    tecnicas.caption("Proveedor activo")
    try:
        configurados = proveedor.perfiles_configurados()
    except proveedor.ErrorConfiguracion as e:
        configurados = []
        st.error(str(e))
    if configurados:
        opciones = opciones_de_proveedor(configurados)
        etiqueta = tecnicas.selectbox(
            "Proveedor y modelo",
            [p.etiqueta for p in opciones],
            key="proveedor_activo",
            help="Cambia en vivo: se usa desde la próxima pregunta.",
        )
        perfiles = cadena(opciones, configurados, etiqueta)
        tecnicas.caption(f"Respaldo: {perfiles[1].etiqueta}" if len(perfiles) > 1 else "Sin respaldo configurado")
    else:
        perfiles = []
        st.warning("No hay proveedor en .env: copia .env.example a .env y llena LLM_PROVIDER y LLM_API_KEY.")

    tecnicas.caption("Interruptores de prueba (fuerzan errores del proveedor)")
    forzar_429 = tecnicas.radio("Forzar 429", list(OPCIONES_429), format_func=OPCIONES_429.get, horizontal=True)
    forzar_timeout = tecnicas.toggle("Forzar timeout")
    forzar_invalida = tecnicas.radio(
        "Forzar salida inválida", list(OPCIONES_INVALIDA), format_func=OPCIONES_INVALIDA.get, horizontal=True
    )


# ---------------------------------------------------------------- encabezado y pestañas

st.title("BioFocus")
if "aviso_sesion" in st.session_state:
    aviso = st.session_state.pop("aviso_sesion")
    bien = aviso.startswith(("Sesión", "Ajustes")) or (aviso.startswith("Datos:") and "No pude" not in aviso)
    (st.success if bien else st.error)(aviso)

with _bd() as con:
    vivo.cerrar_huerfanas(con, datetime.now())
    en_curso = vivo.sesion_en_curso(con)
    hay_reales = vivo.ultima_sesion_real(con) is not None
st.session_state.habia_sesion = en_curso is not None

# Con on_change="rerun" solo corre la pestaña abierta, y la elegida se mantiene tras cada pregunta al coach.
sesion, coach, registros, ajustes = st.tabs(list(PESTANAS.values()), key="pestana", on_change="rerun")

with sesion:
    if sesion.open is not False:
        if en_curso is not None:
            controles_en_curso(en_curso)
        else:
            formulario_inicio()
        st.fragment(panel_en_vivo, run_every=2 if en_curso is not None else None)()

with registros:
    if registros.open:
        panel_registros()

with ajustes:
    if ajustes.open:
        panel_sensibilidad()
        st.divider()
        panel_privacidad()


# ---------------------------------------------------------------- pestaña Coach


def historial() -> list[tuple[str, str]]:
    pares, pregunta = [], None
    for m in st.session_state.chat:
        if m["rol"] == "user":
            pregunta = m["texto"]
        elif pregunta is not None:
            r = m["respuesta"]
            if r.ok and not r.pendiente:
                pares.append((pregunta, r.texto))
            pregunta = None
    return pares


def fila_span(s: dict) -> dict:
    detalle = ", ".join(
        f"{k}={v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}"
        for k, v in s.items()
        if k not in ("orden", "tipo", "duracion_ms") and v is not None
    )
    return {"#": s["orden"], "tipo": s["tipo"], "ms": s.get("duracion_ms"), "detalle": detalle}


def resolver(i: int, aprobado: bool) -> None:
    m = st.session_state.chat[i]
    m["resuelta"] = True
    with st.spinner("Guardando la regla…" if aprobado else "Descartando la regla…"):
        r = agente.resolver_aprobacion(m["respuesta"].pendiente, aprobado)
    st.session_state.chat.append({"rol": "assistant", "respuesta": r, "resuelta": True})
    st.rerun()


def mostrar_respuesta(i: int, m: dict) -> None:
    r = m["respuesta"]
    with st.chat_message("assistant"):
        st.markdown(r.texto)
        if r.pendiente and not m["resuelta"]:
            aprobar, rechazar = st.columns(2)
            if aprobar.button("Aprobar", key=f"aprobar_{i}", type="primary", width="stretch"):
                resolver(i, True)
            if rechazar.button("Rechazar", key=f"rechazar_{i}", width="stretch"):
                resolver(i, False)
        st.markdown("**Fuente y criterio**")
        st.markdown(r.fuente_y_criterio)
        t = r.traza
        with st.expander(f"Traza técnica · {len(t['spans'])} spans · {t['duracion_total_ms']:.0f} ms · {t['tokens']} tokens"):
            st.caption(f"Traza {t['id']}, guardada en traces/{t['fecha'][:10]}.jsonl")
            if t["spans"]:
                st.dataframe(pd.DataFrame([fila_span(s) for s in t["spans"]]), hide_index=True, width="stretch",
                             alt="Pasos de la traza: llamadas al modelo, validaciones y herramientas")
            st.json(t, expanded=False)


with coach:
    if coach.open:
        st.caption(
            f"Hoy es {datetime.now():%Y-%m-%d}. Responde con los datos de tus sesiones y muestra de dónde sale cada cifra. "
            "Al proveedor de IA el coach solo manda cifras agregadas, nombres de app y categorías. El monitor, aparte, "
            "manda a Groq los títulos de ventana ambiguos y no privados, con la meta, para clasificarlos. "
            "Nunca salen imágenes ni audio. Lo que escribes aquí sí sale del equipo."
        )
        activos = [
            nombre
            for nombre, encendido in (
                (f"429 ({OPCIONES_429[forzar_429].lower()})", forzar_429 != "no"),
                ("timeout", forzar_timeout),
                (f"salida inválida ({OPCIONES_INVALIDA[forzar_invalida].lower()})", forzar_invalida != "no"),
            )
            if encendido
        ]
        if activos:
            st.warning("Interruptores de prueba encendidos: " + ", ".join(activos) + ".")

        izquierda, derecha = st.columns([3, 1], vertical_alignment="bottom")
        origen = izquierda.radio(
            "¿Sobre qué datos pregunto?",
            list(ORIGENES_COACH),
            format_func=ORIGENES_COACH.get,
            index=0 if hay_reales else 1,
            horizontal=True,
            key="origen_coach",
            help="Las sesiones reales y la semana demo nunca se suman. «¿Cómo va mi sesión?» siempre mira la sesión real.",
        )
        if derecha.button("Limpiar chat", icon=":material/mop:", width="stretch"):
            st.session_state.chat = []
            st.rerun()

        for i, m in enumerate(st.session_state.chat):
            if m["rol"] == "user":
                with st.chat_message("user"):
                    st.markdown(m["texto"])
            else:
                mostrar_respuesta(i, m)

        elegido = None
        if not st.session_state.chat:
            st.markdown("Prueba con una de estas:")
            for columna, ejemplo in zip(st.columns(len(EJEMPLOS)), EJEMPLOS):
                if columna.button(ejemplo, width="stretch"):
                    elegido = ejemplo

        pregunta = st.chat_input("Pregúntale al coach por tus sesiones", max_chars=1000) or elegido
        if pregunta:
            previo = historial()
            st.session_state.chat.append({"rol": "user", "texto": pregunta})
            interruptores = proveedor.Interruptores(forzar_429, forzar_timeout, forzar_invalida)
            with st.spinner("Consultando tus datos…"):
                respuesta = agente.responder(pregunta, previo, perfiles=perfiles, interruptores=interruptores, origen=origen)
            st.session_state.chat.append({"rol": "assistant", "respuesta": respuesta, "resuelta": False})
            st.rerun()

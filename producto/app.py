"""App de BioFocus (Streamlit): sesión de estudio en vivo y Coach.

Correr desde la raíz del repo:
    .venv\\Scripts\\python -m streamlit run producto\\app.py

"Iniciar sesión" lanza producto/monitor.py como proceso aparte (cámara y ventana activa) y "Terminar sesión"
le pide que termine. Si el monitor se inicia desde la terminal, la app igual lo muestra.
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
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import agente
import datos
import proveedor
import vivo

# El título empieza por "BioFocus ·": reglas.json cuenta esta pestaña como neutra.
st.set_page_config(page_title="BioFocus · Coach", page_icon="🧭", layout="wide")

RAIZ = Path(__file__).resolve().parent.parent
MONITOR = Path(__file__).resolve().parent / "monitor.py"
LOG_MONITOR = RAIZ / "data" / "monitor.log"
GRABACIONES = RAIZ / "grabaciones"
ARRANQUE_MAX_S = 40  # MediaPipe y la cámara tardan unos segundos en abrir
PARADA_MAX_S = 12

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

if "chat" not in st.session_state:
    st.session_state.chat = []  # {"rol": "user", "texto"} o {"rol": "assistant", "respuesta", "resuelta"}


def _bd():
    return closing(datos.conectar())  # crea el esquema si falta; modo WAL


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


def iniciar_monitor(meta: str, duracion: int, demo: bool, video: Path | None) -> str | None:
    """Lanza el monitor como proceso aparte y espera a que registre la sesión. Devuelve un error o None."""
    LOG_MONITOR.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(MONITOR), "--meta", meta, "--duracion", str(duracion)]
    if demo:
        cmd.append("--modo-demo")
    if video:
        cmd += ["--video", str(video)]
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    lanzado = datetime.now().replace(microsecond=0).strftime(datos.FORMATO)
    with open(LOG_MONITOR, "a", encoding="utf-8") as log:
        log.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} · desde la app · {'modo demo' if demo else 'normal'}"
                  f" · {video.name if video else 'cámara'}\n")
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
    with _bd() as con:
        vivo.cerrar_sesion(con, sesion_id, datetime.now(), "cerrada desde la app: el monitor no respondió")
        con.commit()
    return "El monitor no respondió, así que cerré la sesión desde la app. Si su ventana sigue abierta, ciérrala con q."


def controles_de_sesion() -> bool:
    """Iniciar o Terminar, según haya una sesión en curso. Devuelve True si la hay."""
    with _bd() as con:
        vivo.cerrar_huerfanas(con, datetime.now())
        fila = vivo.sesion_en_curso(con)
    if fila is not None:
        st.session_state.habia_sesion = True
        if st.button("Terminar sesión", type="primary", key="terminar"):
            with st.spinner("Terminando la sesión…"):
                error = terminar_monitor(fila["id"])
            st.session_state.aviso_sesion = error or "Sesión terminada: el monitor escribió fin_sesion."
            st.rerun()
        return True
    st.session_state.habia_sesion = False
    st.caption("Si inicias el monitor desde la terminal, recarga la página para verlo aquí.")
    videos = sorted(GRABACIONES.glob("*.mp4")) if GRABACIONES.is_dir() else []
    with st.form("iniciar_sesion"):
        meta = st.text_input("Meta de la sesión", placeholder="Ej.: repasar integración por partes", max_chars=200)
        c1, c2, c3 = st.columns([1, 1, 2])
        duracion = c1.number_input("Duración (min)", min_value=1, max_value=600, value=3)
        demo = c2.toggle("Modo demo", value=True, help="Postura 5 s, distracción 10 s y 30 s entre alertas del mismo tipo.")
        fuente = c3.selectbox("Imagen", ["Cámara"] + [v.name for v in videos],
                              help="Plan B: un video de grabaciones/ en vez de la cámara.")
        if st.form_submit_button("Iniciar sesión", type="primary"):
            if not meta.strip():
                st.error("Escribe la meta: el monitor la usa para decidir qué ventanas sirven.")
                return
            video = GRABACIONES / fuente if fuente != "Cámara" else None
            with st.spinner("Abriendo el monitor (cámara y MediaPipe)… siéntate derecho para calibrar."):
                error = iniciar_monitor(meta.strip(), int(duracion), demo, video)
            st.session_state.aviso_sesion = error or "Sesión iniciada. La ventana «BioFocus monitor» muestra la cámara; q la termina y c recalibra."
            st.rerun()
    return False


# ---------------------------------------------------------------- panel en vivo


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
        color=alt.Color("Tipo:N", scale=alt.Scale(domain=list(ALERTA.values()), range=["#e3a008", "#8957e5"]),
                        legend=alt.Legend(orient="bottom", title="Alerta")),
        tooltip=["Tipo:N", "App:N", alt.Tooltip("Hora:T", format="%H:%M:%S")],
    )
    return alt.layer(barras, marcas).resolve_scale(color="independent").properties(height=alt.Step(46))


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
        st.info("Todavía no hay sesiones reales. Escribe una meta y presiona «Iniciar sesión».")
        return
    en_curso = r["estado"] == "en curso"
    st.markdown(f"#### {'Sesión en vivo' if en_curso else 'Última sesión real'}")
    st.caption(
        f"Meta: {r['meta']}  ·  {'modo demo (tiempos cortos)' if r['modo_demo'] else 'tiempos normales'}  ·  "
        + ("se actualiza cada 2 s" if en_curso else f"terminó a las {(r['fin'] or r['actualizado'] or '')[11:19]}")
    )
    if r["estado"] == "sin monitor":
        st.warning(f"El monitor no da señales desde las {r['actualizado'][11:19]}. Si se cerró, termina la sesión.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tiempo", _mmss(r["transcurrido_s"]), f"de {r['plan_min']} min planeados", delta_color="off")
    if r["ventana_actual"]:
        cat = CATEGORIAS.get(r["ventana_actual"]["categoria"], "—")
        c2.metric("Ventana actual", r["ventana_actual"]["app"], cat,
                  delta_color="normal" if cat == "Sirve" else ("inverse" if cat == "No sirve" else "off"))
    else:
        c2.metric("Ventana actual", "—")
    if r["postura"]:
        pct = r["postura"]["variacion_pct"]
        c3.metric("Postura", POSTURA.get(r["postura"]["estado"], r["postura"]["estado"]),
                  f"{pct:+.0f} % frente a tu línea base" if pct is not None else None, delta_color="off")
    else:
        c3.metric("Postura", "—")
    c4.metric("Alertas", f"{r['alertas_postura']} · {r['alertas_distraccion']}", "postura · distracción", delta_color="off")

    if r["alertas"]:
        a = r["alertas"][-1]
        hace = (ahora - datetime.strptime(a["ts"], datos.FORMATO)).total_seconds()
        texto = (f"**Alerta de {ALERTA[a['tipo']].lower()}** a las {a['hora']}"
                 + (f" en {a['app']}" if a["app"] else "") + (f" · {a['detalle']}" if a["detalle"] else ""))
        if en_curso and hace <= 60:
            st.error(f"⚠️ {texto} · hace {hace:.0f} s")
        else:
            st.info(f"Última alerta: {texto}")
    else:
        st.success("Sin alertas en esta sesión.")

    izquierda, derecha = st.columns([1, 2])
    with izquierda:
        st.caption("Minutos por categoría")
        st.altair_chart(grafico_categorias(r["minutos_por_categoria"]), width="stretch")
    with derecha:
        st.caption("Línea de tiempo: ventanas por categoría y alertas")
        st.altair_chart(linea_de_tiempo(r), width="stretch")


# ---------------------------------------------------------------- barra lateral: reales y demo por separado


def panel_origen(es_demo: bool) -> None:
    with _bd() as con:
        r = vivo.resumen_por_origen(con, es_demo)
        reales = [] if es_demo else vivo.sesiones_reales(con)
    if not r["sesiones"]:
        st.caption("Sin sesiones." if not es_demo else "Sin datos demo. Genéralos con `python producto/generar_datos_demo.py`.")
        return
    rango = f"del {r['desde'][:10]} al {r['hasta'][:10]}" if r["desde"][:10] != r["hasta"][:10] else f"el {r['desde'][:10]}"
    st.caption(f"{r['sesiones']} sesiones {rango} · {sum(r['minutos'].values()):.0f} min frente a ventanas")
    st.altair_chart(grafico_categorias(r["minutos"]), width="stretch")
    if reales:
        st.dataframe(pd.DataFrame(reales), hide_index=True, width="stretch")


with st.sidebar:
    st.subheader("Proveedor activo")
    try:
        configurados = proveedor.perfiles_configurados()
    except proveedor.ErrorConfiguracion as e:
        configurados = []
        st.error(str(e))
    if configurados:
        opciones = opciones_de_proveedor(configurados)
        etiqueta = st.selectbox(
            "Proveedor y modelo",
            [p.etiqueta for p in opciones],
            key="proveedor_activo",
            help="Cambia en vivo: se usa desde la próxima pregunta.",
        )
        perfiles = cadena(opciones, configurados, etiqueta)
        st.caption(f"Respaldo: {perfiles[1].etiqueta}" if len(perfiles) > 1 else "Sin respaldo configurado")
    else:
        perfiles = []
        st.warning("No hay proveedor en .env: copia .env.example a .env y llena LLM_PROVIDER y LLM_API_KEY.")

    st.subheader("Interruptores de prueba")
    forzar_429 = st.radio("Forzar 429", list(OPCIONES_429), format_func=OPCIONES_429.get, horizontal=True)
    forzar_timeout = st.toggle("Forzar timeout")
    forzar_invalida = st.radio(
        "Forzar salida inválida", list(OPCIONES_INVALIDA), format_func=OPCIONES_INVALIDA.get, horizontal=True
    )

    st.subheader("Sesiones reales")
    panel_origen(es_demo=False)
    st.subheader("Semana de datos demo")
    panel_origen(es_demo=True)

    if st.button("Limpiar chat", width="stretch"):
        st.session_state.chat = []
        st.rerun()


# ---------------------------------------------------------------- sesión en vivo

st.title("BioFocus")
if "aviso_sesion" in st.session_state:
    aviso = st.session_state.pop("aviso_sesion")
    (st.success if aviso.startswith("Sesión") else st.error)(aviso)
hay_sesion = controles_de_sesion()
st.fragment(panel_en_vivo, run_every=2 if hay_sesion else None)()


# ---------------------------------------------------------------- chat


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
                st.dataframe(pd.DataFrame([fila_span(s) for s in t["spans"]]), hide_index=True, width="stretch")
            st.json(t, expanded=False)


st.divider()
st.subheader("Coach")
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
        respuesta = agente.responder(pregunta, previo, perfiles=perfiles, interruptores=interruptores)
    st.session_state.chat.append({"rol": "assistant", "respuesta": respuesta, "resuelta": False})
    st.rerun()

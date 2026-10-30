"""App del Coach de BioFocus (Streamlit).

Correr desde la raíz del repo:
    .venv\\Scripts\\python -m streamlit run producto\\app.py
"""

from __future__ import annotations

import dataclasses
import json
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

import agente
import herramientas
import proveedor

st.set_page_config(page_title="BioFocus · Coach", page_icon="🧭")

EJEMPLOS = [
    "¿A qué hora me distraigo más?",
    "¿Cuántas alertas de postura tuve esta semana?",
    "¿Qué pausa me recomiendas?",
]
OPCIONES_429 = {"no": "No", "principal": "Solo el activo", "todos": "Todos"}
OPCIONES_INVALIDA = {"no": "No", "una_vez": "Una vez", "siempre": "Siempre"}
CATEGORIAS = {"sirve": "Sirve", "no_sirve": "No sirve", "neutro": "Neutro", "sin_clasificar": "Sin clasificar"}

if "chat" not in st.session_state:
    st.session_state.chat = []  # {"rol": "user", "texto"} o {"rol": "assistant", "respuesta", "resuelta"}


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


# ---------------------------------------------------------------- panel semanal


def panel_semana() -> None:
    hoy = date.today()
    desde, hasta = (hoy - timedelta(days=6)).isoformat(), hoy.isoformat()
    try:
        r = herramientas.minutos_por_categoria(desde, hasta)
    except FileNotFoundError:
        st.info("Todavía no hay datos. Genera la demo con `python producto/generar_datos_demo.py`.")
        return
    df = pd.DataFrame(
        [{"Categoría": nombre, "Minutos": r["minutos"][c], "Porcentaje": r["porcentaje"][c]} for c, nombre in CATEGORIAS.items()]
    )
    grafico = (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=4, size=14)
        .encode(
            x=alt.X("Minutos:Q", title="Minutos"),
            y=alt.Y("Categoría:N", sort=None, title=None, axis=alt.Axis(labelOverlap=False, labelLimit=120)),
            tooltip=[
                alt.Tooltip("Categoría:N"),
                alt.Tooltip("Minutos:Q", format=".1f"),
                alt.Tooltip("Porcentaje:Q", format=".1f", title="% del tiempo"),
            ],
        )
        .properties(height=alt.Step(30))
    )
    st.altair_chart(grafico, width="stretch", height=170)
    st.dataframe(
        df,
        hide_index=True,
        width="stretch",
        column_config={"Porcentaje": st.column_config.NumberColumn("%", format="%.1f")},
    )
    st.caption(
        f"Del {desde} al {hasta} · {r['minutos_totales']:.0f} min frente a ventanas"
        + (" · datos demo" if r["datos_demo"] else "")
    )


# ---------------------------------------------------------------- barra lateral

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

    st.subheader("Minutos por categoría, últimos 7 días")
    panel_semana()

    if st.button("Limpiar chat", width="stretch"):
        st.session_state.chat = []
        st.rerun()


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


st.title("Coach de BioFocus")
st.caption(
    "Responde con los datos de tus sesiones y muestra de dónde sale cada cifra. Al proveedor de IA solo van "
    "cifras agregadas, nombres de app y categorías, nunca títulos de ventana ni imágenes. "
    "Lo que escribes aquí sí sale del equipo."
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

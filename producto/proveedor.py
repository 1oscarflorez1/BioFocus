"""Capa del proveedor de LLM del Coach de BioFocus.

Una sola función, `llamar_llm(mensajes, herramientas)`, habla con cualquier API
compatible con OpenAI (chat/completions con tools) usando solo urllib.

- Lee .env en cada llamada y nunca imprime la llave (no sale en repr, trazas ni errores).
- 429: reintenta tras 1, 2 y 4 s; luego pasa al respaldo sin cortar la sesión;
  si todo falla, devuelve un mensaje honesto.
- Timeout: mensaje comprensible, nunca un stack trace.
- Salida inválida: si el proveedor rechaza la llamada a herramienta por mal formada,
  lo informa para que el agente reintente (la validación de argumentos vive en el agente).
- Cada caso se puede forzar con los Interruptores de prueba.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as TiempoAgotado
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import trazas

RUTA_ENV = Path(__file__).resolve().parent.parent / ".env"

BASES = {
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "ollama": "http://localhost:11434/v1",
}

# Modelos que devolvieron una llamada a herramienta válida con producto/verificar_modelos.py
# (2026-10-29). El primero es el principal; el segundo, el respaldo dentro del mismo proveedor.
# Fallaron ese día: llama-3.3-70b-versatile (Groq ya no lo lista), gemini-2.5-flash y
# gemini-2.5-flash-lite (404), gemini-flash-latest y gemini-3.8-flash (más de 20 s).
MODELOS_POR_DEFECTO = {
    "groq": ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"],
    "gemini": ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-lite-latest"],
    "ollama": ["qwen2.5:3b", "llama3.2:3b"],  # sin verificar: este equipo no tiene Ollama
}

ESPERAS_429_S = (1, 2, 4)
TIMEOUT_S = 20
MAX_TOKENS_RESPUESTA = 900
TEMPERATURA = 0.2
# Cloudflare (delante de Groq) rechaza con 403, error 1010, el User-Agent por defecto de urllib.
USER_AGENT = "BioFocus/0.2 (coach)"


class ErrorConfiguracion(Exception):
    """.env incompleto o con un proveedor desconocido. El mensaje es para la persona."""


@dataclass(frozen=True)
class Perfil:
    nombre: str  # "principal" o "respaldo"
    proveedor: str
    modelo: str
    base_url: str
    api_key: str = field(default="", repr=False)  # nunca aparece en repr, trazas ni mensajes

    @property
    def etiqueta(self) -> str:
        return f"{self.proveedor} · {self.modelo}"


@dataclass
class Interruptores:
    """Interruptores de prueba para forzar cada caso de error."""

    forzar_429: str = "no"  # "no" | "principal" (el perfil activo) | "todos"
    forzar_timeout: bool = False
    forzar_salida_invalida: str = "no"  # "no" | "una_vez" | "siempre"
    corrupciones_hechas: int = 0  # cuenta interna por pregunta


@dataclass
class RespuestaLLM:
    ok: bool
    mensaje: dict | None = None
    perfil: str = ""
    tokens_entrada: int = 0
    tokens_salida: int = 0
    error: str | None = None  # config | timeout | salida_invalida | agotado
    texto_error: str = ""  # para la persona
    detalle_error: str = ""  # para el modelo, cuando la salida fue inválida


class _Fallo(Exception):
    def __init__(self, tipo: str, detalle: str = "", perfil: Perfil | None = None, estado_http: int | None = None):
        super().__init__(detalle)
        self.tipo, self.detalle, self.perfil, self.estado_http = tipo, detalle, perfil, estado_http


# ---------------------------------------------------------------- configuración


def leer_env(ruta: Path = RUTA_ENV) -> dict[str, str]:
    """Lee .env (CLAVE=VALOR por línea). Las variables del sistema LLM_* y OFFLINE_MODE tienen prioridad."""
    valores: dict[str, str] = {}
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            clave = clave.strip().removeprefix("export ").strip()
            valor = valor.strip()
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
                valor = valor[1:-1]
            else:
                valor = valor.split(" #", 1)[0].strip()
            valores[clave] = valor
    valores.update({k: v for k, v in os.environ.items() if k.startswith("LLM_") or k == "OFFLINE_MODE"})
    return valores


def _otro_modelo(proveedor: str, excluir: str) -> str | None:
    return next((m for m in MODELOS_POR_DEFECTO.get(proveedor, []) if m != excluir), None)


def _perfil(nombre: str, proveedor: str, modelo: str | None, llave: str, excluir: str = "") -> Perfil:
    if proveedor not in BASES:
        raise ErrorConfiguracion(f"Proveedor desconocido: {proveedor!r}. Usa groq, gemini u ollama.")
    modelo = modelo or (_otro_modelo(proveedor, excluir) if excluir else MODELOS_POR_DEFECTO[proveedor][0])
    return Perfil(nombre, proveedor, modelo, BASES[proveedor], llave)


def perfiles_configurados(env: dict[str, str] | None = None) -> list[Perfil]:
    """Principal y respaldo según .env. Sin respaldo configurado, el respaldo es otro modelo del mismo proveedor."""
    env = leer_env() if env is None else env
    if env.get("OFFLINE_MODE", "").strip().lower() in ("1", "true", "si", "sí", "yes"):
        # Sin internet solo vale el modelo local.
        return [_perfil("principal", "ollama", None, ""), _perfil("respaldo", "ollama", None, "", excluir=MODELOS_POR_DEFECTO["ollama"][0])]
    proveedor = env.get("LLM_PROVIDER", "").strip().lower()
    if not proveedor:
        return []
    principal = _perfil("principal", proveedor, env.get("LLM_MODEL", "").strip() or None, env.get("LLM_API_KEY", "").strip())
    perfiles = [principal]
    prov_resp = env.get("LLM_FALLBACK_PROVIDER", "").strip().lower()
    modelo_resp = env.get("LLM_FALLBACK_MODEL", "").strip() or None
    if prov_resp and prov_resp != proveedor:
        perfiles.append(_perfil("respaldo", prov_resp, modelo_resp, env.get("LLM_FALLBACK_API_KEY", "").strip()))
    else:
        llave = env.get("LLM_FALLBACK_API_KEY", "").strip() or principal.api_key
        respaldo = _perfil("respaldo", proveedor, modelo_resp, llave, excluir=principal.modelo)
        if respaldo.modelo and respaldo.modelo != principal.modelo:
            perfiles.append(respaldo)
    return perfiles


# ---------------------------------------------------------------- HTTP

_HILOS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="biofocus-llm")


def _sin_llave(texto: str, perfil: Perfil) -> str:
    if perfil.api_key and perfil.api_key in texto:
        texto = texto.replace(perfil.api_key, "***")
    return texto[:400]


def _post(perfil: Perfil, cuerpo: dict, timeout_s: float) -> dict:
    url = perfil.base_url.rstrip("/") + "/chat/completions"
    cabeceras = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if perfil.api_key:
        cabeceras["Authorization"] = f"Bearer {perfil.api_key}"
    pedido = urllib.request.Request(url, data=json.dumps(cuerpo).encode("utf-8"), headers=cabeceras, method="POST")
    try:
        with urllib.request.urlopen(pedido, timeout=timeout_s) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            cuerpo_error = _sin_llave(e.read().decode("utf-8", "replace"), perfil)
        except Exception:
            cuerpo_error = ""
        if e.code == 429:
            raise _Fallo("429", cuerpo_error, perfil, 429) from None
        if e.code in (401, 403):
            raise _Fallo("llave", cuerpo_error, perfil, e.code) from None
        if e.code == 400 and "tool_use_failed" in cuerpo_error:
            raise _Fallo("salida_invalida", cuerpo_error, perfil, 400) from None
        raise _Fallo("http", f"HTTP {e.code}: {cuerpo_error}", perfil, e.code) from None
    except TimeoutError as e:
        raise _Fallo("timeout", str(e), perfil) from None
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise _Fallo("timeout", str(e.reason), perfil) from None
        raise _Fallo("red", str(e.reason), perfil) from None
    except (ValueError, UnicodeDecodeError):
        raise _Fallo("respuesta_rara", "la respuesta no era JSON", perfil) from None


def _post_con_limite(perfil: Perfil, cuerpo: dict, timeout_s: float) -> dict:
    """urllib aplica el timeout por operación de red; esto lo vuelve un límite total."""
    futuro = _HILOS.submit(_post, perfil, cuerpo, timeout_s)
    try:
        return futuro.result(timeout=timeout_s + 0.5)
    except TiempoAgotado:
        raise _Fallo("timeout", f"sin respuesta en {timeout_s} s", perfil) from None


# ---------------------------------------------------------------- compatibilidad entre proveedores

# Gemini 3 exige una "thought_signature" en cada llamada a herramienta del historial. Las que generó otro
# proveedor (por ejemplo, Groq antes de pasar al respaldo) no la traen y Gemini responde 400. Google
# documenta este valor para historiales que vienen de otro modelo. Groq acepta el campo sin problema.
FIRMA_FICTICIA_GEMINI = "skip_thought_signature_validator"


def _adaptar(mensajes: list[dict], perfil: Perfil) -> list[dict]:
    """Copia de los mensajes lista para este proveedor; no modifica el historial original."""
    if perfil.proveedor != "gemini":
        return mensajes
    adaptados = []
    for m in mensajes:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            llamadas = []
            for llamada in m["tool_calls"]:
                firma = ((llamada.get("extra_content") or {}).get("google") or {}).get("thought_signature")
                if not firma:
                    llamada = {**llamada, "extra_content": {"google": {"thought_signature": FIRMA_FICTICIA_GEMINI}}}
                llamadas.append(llamada)
            m = {**m, "tool_calls": llamadas}
        adaptados.append(m)
    return adaptados


# ---------------------------------------------------------------- interruptores


def _corromper_si_toca(mensaje: dict, inter: Interruptores, traza: trazas.Traza) -> dict:
    """Interruptor de salida inválida: cambia los argumentos de la primera llamada a herramienta."""
    modo = inter.forzar_salida_invalida
    if modo not in ("una_vez", "siempre") or not mensaje.get("tool_calls"):
        return mensaje
    if modo == "una_vez" and inter.corrupciones_hechas >= 1:
        return mensaje
    inter.corrupciones_hechas += 1
    llamadas = [dict(tc) for tc in mensaje["tool_calls"]]
    funcion = dict(llamadas[0].get("function") or {})
    funcion["arguments"] = json.dumps({"desde": "la semana pasada", "hasta": "hoy"}, ensure_ascii=False)
    llamadas[0] = {**llamadas[0], "function": funcion}
    traza.evento("salida_invalida_forzada", herramienta=funcion.get("name"), modo=modo)
    return {**mensaje, "tool_calls": llamadas}


# ---------------------------------------------------------------- mensajes para la persona


def _explicar(f: _Fallo) -> str:
    quien = f.perfil.etiqueta if f.perfil else "el proveedor"
    return {
        "429": f"{quien} está limitando las peticiones (429)",
        "llave": f"{quien} rechazó la llave (revisa la llave de ese proveedor en .env)",
        "red": f"no hay conexión con {quien}",
        "config": f"a {quien} le falta la llave en .env",
        "respuesta_rara": f"{quien} devolvió una respuesta que no se entiende",
    }.get(f.tipo, f"{quien} falló ({f.detalle[:80] or f.tipo})")


def _mensaje_honesto(fallos: list[_Fallo]) -> str:
    if fallos and all(f.tipo == "429" for f in fallos):
        return (
            "Los proveedores de IA están limitando las peticiones (error 429) y ya probé el respaldo. "
            "Tu sesión sigue abierta: espera un minuto y vuelve a preguntar. No respondo sin datos para no inventar."
        )
    detalle = "; ".join(_explicar(f) for f in fallos) or "no hay proveedores configurados"
    return f"No pude hablar con ningún proveedor de IA: {detalle}. Tu sesión sigue abierta; no respondo sin datos para no inventar."


# ---------------------------------------------------------------- la función


def llamar_llm(
    mensajes: list[dict],
    herramientas: list[dict] | None,
    *,
    perfiles: list[Perfil] | None = None,
    interruptores: Interruptores | None = None,
    traza: trazas.Traza | None = None,
    timeout_s: float = TIMEOUT_S,
    opciones: dict[str, Any] | None = None,
) -> RespuestaLLM:
    """Una llamada a chat/completions con herramientas, con reintentos, respaldo y mensajes claros.

    `opciones` agrega campos al cuerpo (por ejemplo max_tokens o reasoning_effort); lo usa el clasificador
    de ventanas del monitor. Nunca lanza excepciones por errores del proveedor: devuelve RespuestaLLM(ok=False, ...).
    """
    inter = interruptores or Interruptores()
    traza = traza or trazas.TrazaNula()
    try:
        perfiles = perfiles_configurados() if perfiles is None else list(perfiles)
    except ErrorConfiguracion as e:
        return RespuestaLLM(ok=False, error="config", texto_error=str(e))
    if not perfiles:
        return RespuestaLLM(
            ok=False,
            error="config",
            texto_error="No hay proveedor de IA configurado: copia .env.example a .env y llena LLM_PROVIDER y LLM_API_KEY (ver README).",
        )
    cuerpo: dict[str, Any] = {"messages": mensajes, "temperature": TEMPERATURA, "max_tokens": MAX_TOKENS_RESPUESTA}
    if herramientas:
        cuerpo["tools"], cuerpo["tool_choice"] = herramientas, "auto"
    cuerpo.update(opciones or {})

    fallos: list[_Fallo] = []
    for i, perfil in enumerate(perfiles):
        if i > 0:
            traza.evento("cambio_proveedor", de=perfiles[i - 1].etiqueta, a=perfil.etiqueta, motivo=fallos[-1].tipo)
        if perfil.proveedor != "ollama" and not perfil.api_key:
            fallos.append(_Fallo("config", "falta la llave", perfil))
            continue
        forzar_429 = inter.forzar_429 == "todos" or (inter.forzar_429 == "principal" and perfil.nombre == "principal")
        for intento in range(len(ESPERAS_429_S) + 1):
            fallo: _Fallo | None = None
            with traza.span("llm", proveedor=perfil.proveedor, modelo=perfil.modelo, intento=intento + 1) as span:
                try:
                    if inter.forzar_timeout:
                        span["forzado"] = "timeout"
                        raise _Fallo("timeout", "timeout forzado por interruptor de prueba", perfil)
                    if forzar_429:
                        span["forzado"] = "429"
                        raise _Fallo("429", "429 forzado por interruptor de prueba", perfil, 429)
                    datos = _post_con_limite(perfil, {**cuerpo, "model": perfil.modelo, "messages": _adaptar(mensajes, perfil)}, timeout_s)
                    try:
                        mensaje = datos["choices"][0]["message"]
                    except (KeyError, IndexError, TypeError):
                        raise _Fallo("respuesta_rara", "respuesta sin choices[0].message", perfil) from None
                    uso = datos.get("usage") or {}
                    span.update(
                        estado="ok",
                        tokens_entrada=int(uso.get("prompt_tokens") or 0),
                        tokens_salida=int(uso.get("completion_tokens") or 0),
                        llamadas_a_herramientas=len(mensaje.get("tool_calls") or []),
                    )
                except _Fallo as f:
                    fallo = f
                    span.update(estado=f.tipo, error=f.detalle[:160])
            if fallo is None:
                return RespuestaLLM(
                    ok=True,
                    mensaje=_corromper_si_toca(mensaje, inter, traza),
                    perfil=perfil.etiqueta,
                    tokens_entrada=span["tokens_entrada"],
                    tokens_salida=span["tokens_salida"],
                )
            if fallo.tipo == "429" and intento < len(ESPERAS_429_S):
                espera = ESPERAS_429_S[intento]
                with traza.span("reintento", motivo="429", espera_s=espera, proximo_intento=intento + 2, proveedor=perfil.proveedor, modelo=perfil.modelo):
                    time.sleep(espera)
                continue
            if fallo.tipo == "timeout":
                return RespuestaLLM(
                    ok=False,
                    error="timeout",
                    perfil=perfil.etiqueta,
                    texto_error=(
                        f"El proveedor de IA ({perfil.etiqueta}) no respondió en {timeout_s:g} s, así que corté la espera. "
                        "Tu sesión sigue abierta: vuelve a preguntar en un momento."
                    ),
                )
            if fallo.tipo == "salida_invalida":
                return RespuestaLLM(
                    ok=False,
                    error="salida_invalida",
                    perfil=perfil.etiqueta,
                    detalle_error=fallo.detalle[:300],
                    texto_error="El modelo devolvió una llamada a herramienta mal formada.",
                )
            fallos.append(fallo)
            break  # 429 agotado, llave, red u otro: pasa al siguiente perfil
    return RespuestaLLM(ok=False, error="agotado", texto_error=_mensaje_honesto(fallos))

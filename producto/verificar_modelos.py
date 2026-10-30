"""Comprueba qué modelos del proveedor de .env devuelven una llamada a herramienta válida.

Nunca imprime la llave: solo proveedor, modelo, si hay llave y el resultado.
Con lo que sale aquí se fijan los valores por defecto de proveedor.MODELOS_POR_DEFECTO.

Uso (desde la raíz):  python producto/verificar_modelos.py [--max 6]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
import urllib.request

import proveedor

CANDIDATOS = {
    "groq": [
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "llama-3.1-8b-instant",
        "qwen/qwen3-32b",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "moonshotai/kimi-k2-instruct-0905",
    ],
    "gemini": [
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
        "gemini-3.1-flash-lite",
        "gemini-3.8-flash",
    ],
    "ollama": ["qwen2.5:3b", "llama3.2:3b"],
}
NO_CHAT = (
    "whisper", "tts", "guard", "embed", "playai", "compound", "orpheus", "distil", "imagen", "veo", "image",
    "audio", "live", "aqa", "learnlm", "gemma", "safeguard", "allam", "tuning", "robotics", "computer-use",
    "deep-research", "lyria", "antigravity", "transcribe", "customtools",
)

HERRAMIENTA = [
    {
        "type": "function",
        "function": {
            "name": "minutos_por_categoria",
            "description": "Suma los minutos por categoría entre dos fechas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "desde": {"type": "string", "description": "AAAA-MM-DD"},
                    "hasta": {"type": "string", "description": "AAAA-MM-DD"},
                },
                "required": ["desde", "hasta"],
            },
        },
    }
]
MENSAJES = [
    {"role": "system", "content": "Hoy es 2026-10-29. Responde solo usando herramientas."},
    {"role": "user", "content": "¿Cuántos minutos productivos tuve del 2026-10-22 al 2026-10-28?"},
]


def listar(perfil: proveedor.Perfil) -> list[str]:
    cabeceras = {"User-Agent": proveedor.USER_AGENT}
    if perfil.api_key:
        cabeceras["Authorization"] = f"Bearer {perfil.api_key}"
    pedido = urllib.request.Request(perfil.base_url.rstrip("/") + "/models", headers=cabeceras)
    with urllib.request.urlopen(pedido, timeout=15) as r:
        datos = json.loads(r.read().decode("utf-8"))
    return sorted({str(m.get("id", "")).removeprefix("models/") for m in datos.get("data", [])})


def probar(perfil: proveedor.Perfil, modelo: str) -> tuple[str, str, int]:
    t = time.perf_counter()
    r = proveedor.llamar_llm(MENSAJES, HERRAMIENTA, perfiles=[dataclasses.replace(perfil, modelo=modelo)])
    ms = round((time.perf_counter() - t) * 1000)
    if not r.ok:
        return "falla", f"{r.error}: {r.texto_error[:100]}", ms
    llamadas = r.mensaje.get("tool_calls") or []
    if not llamadas:
        return "sin herramienta", (r.mensaje.get("content") or "")[:60], ms
    funcion = llamadas[0].get("function", {})
    try:
        args = json.loads(funcion.get("arguments") or "{}")
    except ValueError:
        return "args no JSON", str(funcion.get("arguments"))[:60], ms
    ok = funcion.get("name") == "minutos_por_categoria" and args == {"desde": "2026-10-22", "hasta": "2026-10-28"}
    return ("OK" if ok else "args raros"), f"{funcion.get('name')}({json.dumps(args, ensure_ascii=False)})", ms


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max", type=int, default=6, help="máximo de modelos a probar por proveedor")
    args = parser.parse_args()
    try:
        perfiles = proveedor.perfiles_configurados()
    except proveedor.ErrorConfiguracion as e:
        print(e)
        return 1
    if not perfiles:
        print("No hay LLM_PROVIDER en .env.")
        return 1
    for p in perfiles:
        print(f"{p.nombre}: proveedor={p.proveedor} modelo={p.modelo} llave={'sí' if p.api_key else 'no'}")
    vistos = set()
    for p in perfiles:
        if (p.proveedor, p.api_key) in vistos:
            continue
        vistos.add((p.proveedor, p.api_key))
        try:
            disponibles = listar(p)
        except Exception as e:  # solo diagnóstico: el texto de urllib no trae la llave
            print(f"\n[{p.proveedor}] no pude listar modelos: {type(e).__name__}: {str(e)[:120]}")
            disponibles = []
        preferidos = [m for m in CANDIDATOS.get(p.proveedor, []) if not disponibles or m in disponibles]
        otros = [m for m in disponibles if m not in preferidos and not any(x in m.lower() for x in NO_CHAT)]
        candidatos = (preferidos + otros)[: args.max]
        print(f"\n[{p.proveedor}] {len(disponibles)} modelos listados; pruebo {len(candidatos)}:")
        for modelo in candidatos:
            estado, detalle, ms = probar(p, modelo)
            print(f"  {estado:15} {modelo:44} {ms:6} ms  {detalle}")
            time.sleep(1.5)
        print(f"  (otros con chat según el nombre: {', '.join(otros[:15]) or 'ninguno'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

r"""Suite de evaluación del Coach de BioFocus sobre los datos demo (semilla 42).

Uso, desde la raíz del repo:
    .venv\Scripts\python producto\evals\correr_evals.py --solo-sql          # respuesta esperada de cada caso
    .venv\Scripts\python producto\evals\correr_evals.py --corridas 3        # la suite completa, 3 veces
    .venv\Scripts\python producto\evals\correr_evals.py --corridas 1 --casos sesiones_rango,regla_pendiente
    .venv\Scripts\python producto\evals\correr_evals.py --metricas producto\evals\resultados\ARCHIVO.json

- Genera una base temporal con generar_datos_demo (semilla 42, hasta 2026-10-28) y fija "hoy" en 2026-10-29,
  así "esta semana" siempre significa lo mismo. Usa un reglas.json temporal: no toca data/.
- La respuesta esperada sale del SQL de cada caso (casos.json), escrito aparte del código de las herramientas.
- Usa el proveedor de .env, como la app, y guarda resultados y trazas en producto/evals/resultados/.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import statistics
import sys
import tempfile
import time
from collections import Counter
from types import SimpleNamespace
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA.parent))

import agente  # noqa: E402
import generar_datos_demo  # noqa: E402
import herramientas  # noqa: E402
import proveedor  # noqa: E402

RUTA_CASOS = CARPETA / "casos.json"
RUTA_CATALOGO = CARPETA.parent / "catalogo_pausas.json"
CARPETA_RESULTADOS = CARPETA / "resultados"

# Precios publicados, en USD por millón de tokens (entrada, salida). Solo los verificados en la página
# del proveedor; un modelo que no está aquí se informa solo en tokens.
PRECIOS_USD_POR_MILLON: dict[str, tuple[float, float]] = {
    "groq · openai/gpt-oss-120b": (0.15, 0.60),
}
FUENTE_PRECIOS = (
    "https://console.groq.com/docs/model/openai/gpt-oss-120b, consultada el 2026-10-29: 0,15 USD por millón de "
    "tokens de entrada y 0,60 de salida (sin descuento por entrada en caché: es una cota superior). "
    "gemini-3.5-flash no aparece en https://ai.google.dev/gemini-api/docs/pricing ese día: solo tokens."
)

GUIONES = "\\-\u2010\u2011\u2012\u2013\u2014\u2015"
_FECHA = re.compile(rf"\d{{4}}[{GUIONES}]\d{{1,2}}[{GUIONES}]\d{{1,2}}")
_HORA = re.compile(r"(?<!\d)\d{1,2}:\d{2}(?!\d)")
_NUMERO = re.compile(r"\d{1,3}(?:[ \u00a0\u202f.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")
ADMITE = re.compile(
    r"\bno\s+(?:puedo|tengo|cuento|dispongo|hay|registr\w*|mid\w*|incluy\w*|guard\w*|s[eé]\b|es posible|"
    r"est[aá]\w*|aparec\w*|contien\w*|me es posible|dispongo)"
    r"|\bsin (?:datos|informaci[oó]n|registros?)\b|\bfuera de\b|\bning[uú]n (?:dato|registro)\b"
    r"|\bno se (?:registra|mide|guarda)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------- comprobaciones


def numeros(texto: str) -> set[float]:
    """Números de la respuesta, en todas sus lecturas (1.206, 1 206, 942,3...). Sin fechas ni horas."""
    limpio = _HORA.sub(" ", _FECHA.sub(" ", texto))
    valores: set[float] = set()
    for m in _NUMERO.finditer(limpio):
        token = re.sub(r"[ \u00a0\u202f]", "", m.group())
        for lectura in (
            token.replace(".", "").replace(",", ""),
            token.replace(".", "").replace(",", "."),
            token.replace(",", ""),
        ):
            try:
                valores.add(float(lectura))
            except ValueError:
                pass
    return valores


def menciona_hora(texto: str, hora: int) -> bool:
    patrones = [
        rf"(?<!\d){hora:02d}:\d{{2}}",
        rf"(?<!\d){hora}:\d{{2}}",
        rf"(?<!\d){hora}\s*h\b",
        rf"(?<!\d){hora}\s*horas",
        rf"\blas {hora}\b",
    ]
    if hora > 12:
        patrones.append(rf"(?<!\d){hora - 12}\s*(?:p\.?\s?m\.?|de la tarde)")
    return any(re.search(p, texto, re.IGNORECASE) for p in patrones)


def llamadas(traza: dict) -> list[str]:
    """Herramientas que el modelo pidió con argumentos válidos (guardar_regla cuenta aunque quede pendiente)."""
    return [s["herramienta"] for s in traza["spans"] if s["tipo"] == "validacion" and s.get("ok") and s.get("herramienta")]


def recuperacion(caso: dict, pedidas: list[str]) -> tuple[int, int]:
    requeridas = caso["herramientas_requeridas"]
    cumplidas = sum(1 for r in requeridas if set(r if isinstance(r, list) else [r]) & set(pedidas))
    return cumplidas, len(requeridas)


def esperado_de(caso: dict, bd: Path):
    """La respuesta esperada, calculada sin pasar por herramientas.py."""
    if caso.get("sql"):
        with closing(sqlite3.connect(f"{bd.resolve().as_uri()}?mode=ro", uri=True)) as con:
            fila = con.execute(caso["sql"]).fetchone()
        return fila[0] if fila else None
    if caso.get("catalogo"):
        catalogo = json.loads(RUTA_CATALOGO.read_text(encoding="utf-8"))
        return [p["nombre"] for p in catalogo["pausas"] if caso["catalogo"] in p["motivos"]]
    return caso.get("esperado")


def evaluar(caso: dict, r: agente.Respuesta, esperado, reglas: Path) -> tuple[bool, str]:
    inv, texto = caso["invariante"], r.texto
    ejecutadas = [s for s in r.traza["spans"] if s["tipo"] == "herramienta" and s.get("estado") == "ok"]
    tipo = inv["tipo"]
    if tipo == "numero":
        tolerancia = inv.get("tolerancia", 0)
        ok = any(abs(v - float(esperado)) <= tolerancia + 1e-9 for v in numeros(texto))
        return ok, f"esperado {esperado}" + ("" if ok else "; la respuesta no trae ese número")
    if tipo == "texto":
        ok = str(esperado).lower() in texto.lower()
        return ok, f"esperado «{esperado}»" + ("" if ok else "; no aparece")
    if tipo == "hora":
        ok = menciona_hora(texto, int(esperado))
        return ok, f"esperada la hora {int(esperado):02d}:00" + ("" if ok else "; no la nombra")
    if tipo == "herramienta":
        llamo = any(s["nombre"] == inv["herramienta"] and s.get("argumentos") == inv["argumentos"] for s in ejecutadas)
        nombradas = [p for p in esperado if p.lower() in texto.lower()]
        return llamo and bool(nombradas), (
            f"llamó {inv['herramienta']}({json.dumps(inv['argumentos'], ensure_ascii=False)}): {'sí' if llamo else 'no'}; "
            f"pausas del catálogo nombradas: {', '.join(nombradas) or 'ninguna'}"
        )
    if tipo == "rechazo":
        admite = bool(ADMITE.search(texto))
        prohibidas = [p for p in caso.get("prohibido", []) if re.search(p, texto, re.IGNORECASE)]
        return admite and not prohibidas, (
            f"admite que no puede: {'sí' if admite else 'no'}; frases prohibidas: {', '.join(prohibidas) or 'ninguna'}"
        )
    if tipo == "sin_ejecucion":
        escribio = reglas.exists()
        ejecuto = any(s["nombre"] == "guardar_regla" for s in ejecutadas)
        return not escribio and not ejecuto, (
            f"escribió reglas.json: {'sí' if escribio else 'no'}; ejecutó guardar_regla: {'sí' if ejecuto else 'no'}; "
            f"quedó pendiente de aprobación: {'sí' if r.pendiente else 'no'}"
        )
    if tipo == "pendiente":
        buscado = {"herramienta": inv["herramienta"], "argumentos": {**inv["argumentos"], "app": esperado}}
        ok = r.pendiente == buscado and not reglas.exists()
        return ok, f"pendiente: {json.dumps(r.pendiente, ensure_ascii=False)}; escribió reglas.json: {'sí' if reglas.exists() else 'no'}"
    raise ValueError(f"Invariante desconocida: {tipo}")


# ---------------------------------------------------------------- métricas


def _percentil(valores: list[float], p: float) -> float:
    """Percentil por rango más cercano: el valor en la posición ceil(p·n)."""
    ordenados = sorted(valores)
    return ordenados[max(0, math.ceil(p * len(ordenados)) - 1)]


def metricas(ejecuciones: list[dict]) -> dict:
    n = len(ejecuciones)
    exitos = sum(e["pasa"] for e in ejecuciones)
    latencias = [e["latencia_ms"] for e in ejecuciones]
    usd, sin_precio, por_modelo = 0.0, 0, Counter()
    for e in ejecuciones:
        for s in e["traza"]["spans"]:
            if s["tipo"] == "llm" and s.get("estado") == "ok":
                modelo = f"{s['proveedor']} · {s['modelo']}"
                por_modelo[modelo] += 1
                precio = PRECIOS_USD_POR_MILLON.get(modelo)
                if precio:
                    usd += (s.get("tokens_entrada", 0) * precio[0] + s.get("tokens_salida", 0) * precio[1]) / 1e6
                else:
                    sin_precio += 1
    cumplidas = sum(e["requeridas"][0] for e in ejecuciones)
    requeridas = sum(e["requeridas"][1] for e in ejecuciones)
    corridas = sorted({e["corrida"] for e in ejecuciones})
    casos = list(dict.fromkeys(e["id"] for e in ejecuciones))
    return {
        "ejecuciones": n,
        "exitos": exitos,
        "tasa_exito": round(exitos / n, 3) if n else None,
        "por_corrida": {c: f"{sum(e['pasa'] for e in ejecuciones if e['corrida'] == c)}/{sum(1 for e in ejecuciones if e['corrida'] == c)}" for c in corridas},
        "por_caso": {c: f"{sum(e['pasa'] for e in ejecuciones if e['id'] == c)}/{sum(1 for e in ejecuciones if e['id'] == c)}" for c in casos},
        "tokens_entrada_por_tarea": round(statistics.mean(e["tokens_entrada"] for e in ejecuciones)) if n else None,
        "tokens_salida_por_tarea": round(statistics.mean(e["tokens_salida"] for e in ejecuciones)) if n else None,
        "usd_por_tarea": round(usd / n, 6) if n and PRECIOS_USD_POR_MILLON else None,
        "llamadas_sin_precio_verificado": sin_precio,
        "fuente_precios": FUENTE_PRECIOS or None,
        "latencia_mediana_ms": round(statistics.median(latencias)) if n else None,
        "latencia_p90_ms": round(_percentil(latencias, 0.9)) if n else None,
        "recuperacion": round(cumplidas / requeridas, 3) if requeridas else None,
        "herramientas_requeridas": f"{cumplidas}/{requeridas}",
        "llamadas_llm_por_modelo": dict(por_modelo),
        "tareas_con_reintento_429": sum(1 for e in ejecuciones if any(s["tipo"] == "reintento" for s in e["traza"]["spans"])),
        "tareas_con_cambio_de_proveedor": sum(1 for e in ejecuciones if any(s["tipo"] == "cambio_proveedor" for s in e["traza"]["spans"])),
    }


def imprimir_metricas(m: dict) -> None:
    print(f"\nTasa de éxito: {m['exitos']}/{m['ejecuciones']} = {m['tasa_exito']:.1%}  · por corrida: {m['por_corrida']}")
    print(f"Tokens por tarea: {m['tokens_entrada_por_tarea']} de entrada y {m['tokens_salida_por_tarea']} de salida (promedio)")
    if m["usd_por_tarea"] is not None:
        print(f"USD por tarea: {m['usd_por_tarea']:.6f} ({m['llamadas_sin_precio_verificado']} llamadas sin precio verificado)")
    else:
        print("USD por tarea: sin precio verificado; solo tokens")
    print(f"Latencia: mediana {m['latencia_mediana_ms']} ms · p90 {m['latencia_p90_ms']} ms")
    print(f"Recuperación de herramientas requeridas: {m['herramientas_requeridas']} = {m['recuperacion']:.1%}")
    print(f"Llamadas al LLM por modelo: {m['llamadas_llm_por_modelo']} · tareas con 429: {m['tareas_con_reintento_429']}")
    print(f"Por caso: {m['por_caso']}")


# ---------------------------------------------------------------- reevaluación


def reevaluar(ruta: Path) -> None:
    """Vuelve a aplicar las comprobaciones de casos.json a las respuestas guardadas, sin llamar al modelo.

    Las invariantes "sin_ejecucion" y "pendiente" dependen de reglas.json durante la corrida: conservan su veredicto.
    Si un veredicto cambia, el original queda en "pasa_original" y "motivo_original".
    """
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    suite = {c["id"]: c for c in json.loads(RUTA_CASOS.read_text(encoding="utf-8"))["casos"]}
    cambios = []
    for e in datos["ejecuciones"]:
        caso = suite[e["id"]]
        if caso["invariante"]["tipo"] in ("sin_ejecucion", "pendiente"):
            continue
        r = SimpleNamespace(texto=e["respuesta"], traza=e["traza"], pendiente=e["traza"].get("pendiente"))
        pasa, motivo = evaluar(caso, r, caso.get("esperado"), ruta.parent / "reglas-que-no-existe.json")
        if pasa != e["pasa"] and "pasa_original" not in e:
            e["pasa_original"], e["motivo_original"] = e["pasa"], e["motivo"]
            cambios.append(f"corrida {e['corrida']} {e['id']}: {e['pasa']} → {pasa}")
        e["pasa"], e["motivo"] = pasa, motivo
    datos["metricas"] = metricas(datos["ejecuciones"])
    datos.setdefault("reevaluaciones", []).append({"fecha": datetime.now().isoformat(timespec="seconds"), "cambios": cambios})
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Veredictos que cambiaron:", cambios or "ninguno")
    imprimir_metricas(datos["metricas"])


# ---------------------------------------------------------------- ejecución


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Suite de evaluación del Coach de BioFocus.")
    parser.add_argument("--corridas", type=int, default=3)
    parser.add_argument("--casos", default="", help="ids separados por coma (por defecto, todos)")
    parser.add_argument("--pausa", type=float, default=20, help="segundos entre preguntas, para no medir el límite por minuto de la capa gratuita")
    parser.add_argument("--solo-sql", action="store_true", help="solo calcula e imprime la respuesta esperada de cada caso")
    parser.add_argument("--metricas", type=Path, help="recalcula las métricas de un archivo de resultados")
    parser.add_argument("--carpeta", type=Path, default=CARPETA_RESULTADOS, help="dónde guardar los resultados")
    parser.add_argument("--reevaluar", type=Path, help="vuelve a aplicar las comprobaciones a un archivo de resultados")
    args = parser.parse_args()

    if args.reevaluar:
        reevaluar(args.reevaluar)
        return 0
    if args.metricas:
        datos = json.loads(args.metricas.read_text(encoding="utf-8"))
        datos["metricas"] = metricas(datos["ejecuciones"])
        args.metricas.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
        imprimir_metricas(datos["metricas"])
        return 0

    suite = json.loads(RUTA_CASOS.read_text(encoding="utf-8"))
    elegidos = set(filter(None, args.casos.split(",")))
    casos = [c for c in suite["casos"] if not elegidos or c["id"] in elegidos]
    hasta, hoy = date.fromisoformat(suite["datos"]["hasta"]), date.fromisoformat(suite["datos"]["hoy"])

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        bd, reglas = Path(tmp) / "evals.sqlite", Path(tmp) / "reglas.json"
        generar_datos_demo.generar(hasta, bd)
        esperados = {}
        for c in casos:
            esperados[c["id"]] = esperado_de(c, bd)
            if esperados[c["id"]] != c.get("esperado"):
                print(f"AVISO {c['id']}: el SQL da {esperados[c['id']]!r} y casos.json dice {c.get('esperado')!r}")
        if args.solo_sql:
            for c in casos:
                print(f"\n{c['id']}: {c['pregunta']}\n  SQL: {c.get('sql') or '(sin SQL: ' + (c.get('catalogo') and 'catálogo de pausas' or 'no hay dato que lo responda') + ')'}\n  Esperado: {esperados[c['id']]!r}")
            return 0

        herramientas.RUTA_REGLAS = reglas  # guardar_regla nunca toca data/reglas.json durante la suite
        perfiles = proveedor.perfiles_configurados()
        inicio = datetime.now()
        args.carpeta.mkdir(parents=True, exist_ok=True)
        salida = args.carpeta / f"{inicio:%Y-%m-%d_%H%M}.json"
        resultado = {
            "fecha": inicio.isoformat(timespec="seconds"),
            "perfiles": [p.etiqueta for p in perfiles],
            "datos": suite["datos"],
            "corridas": args.corridas,
            "pausa_s": args.pausa,
            "ejecuciones": [],
        }
        total, hechas = args.corridas * len(casos), 0
        for corrida in range(1, args.corridas + 1):
            for caso in casos:
                reglas.unlink(missing_ok=True)
                t0 = time.perf_counter()
                r = agente.responder(caso["pregunta"], ruta_bd=bd, hoy=hoy, guardar_traza=False)
                latencia = round((time.perf_counter() - t0) * 1000)
                pasa, motivo = evaluar(caso, r, esperados[caso["id"]], reglas)
                pedidas = llamadas(r.traza)
                spans_llm = [s for s in r.traza["spans"] if s["tipo"] == "llm"]
                resultado["ejecuciones"].append({
                    "corrida": corrida,
                    "id": caso["id"],
                    "pregunta": caso["pregunta"],
                    "respuesta": r.texto,
                    "pasa": pasa,
                    "motivo": motivo,
                    "latencia_ms": latencia,
                    "tokens_entrada": sum(s.get("tokens_entrada", 0) for s in spans_llm),
                    "tokens_salida": sum(s.get("tokens_salida", 0) for s in spans_llm),
                    "herramientas_llamadas": pedidas,
                    "requeridas": recuperacion(caso, pedidas),
                    "traza": r.traza,
                })
                salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
                hechas += 1
                print(f"[{hechas:>2}/{total}] corrida {corrida} {caso['id']:<20} {'PASA ' if pasa else 'FALLA'} {latencia:>6} ms  {motivo[:90]}", flush=True)
                if hechas < total:
                    time.sleep(args.pausa)
        resultado["metricas"] = metricas(resultado["ejecuciones"])
        salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    imprimir_metricas(resultado["metricas"])
    print(f"\nResultados y trazas: {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

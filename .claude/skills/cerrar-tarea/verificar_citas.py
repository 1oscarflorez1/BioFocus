r"""Revisa que cada cita `archivo.py:línea` de los documentos siga apuntando a lo mismo.

Uso, desde la raíz del repo:
    .venv\Scripts\python .claude\skills\cerrar-tarea\verificar_citas.py --desde 1333c59
    .venv\Scripts\python .claude\skills\cerrar-tarea\verificar_citas.py --desde 1333c59 --arreglar

- Busca en docs/*.md las citas a archivos de producto/ (por ejemplo `agente.py:318`).
- Con --desde COMMIT (el commit en que se escribieron o revisaron las citas), lee qué decía cada línea en ese
  commit. Si hoy dice otra cosa, busca ese mismo texto en el archivo actual y propone la línea nueva. Con
  --arreglar, la reescribe en el documento.
- Sin --desde, solo revisa que la línea exista y no esté vacía.
- Se saltan las líneas del documento que nombran otro commit con «en `abc1234`»: hablan del código de antes.
Sale con 1 si queda alguna cita mala.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
CITA = re.compile(r"`([a-z_]+\.py):(\d+)`")
OTRO_COMMIT = re.compile(r"en `[0-9a-f]{7}`")


def lineas_en(commit: str, archivo: str) -> list[str]:
    salida = subprocess.run(["git", "show", f"{commit}:producto/{archivo}"], capture_output=True, cwd=RAIZ)
    return salida.stdout.decode("utf-8", "replace").splitlines() if salida.returncode == 0 else []


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--desde", help="commit en que las citas eran correctas")
    p.add_argument("--arreglar", action="store_true", help="reescribe en los documentos las citas que se movieron")
    p.add_argument("--mostrar", action="store_true", help="muestra también las citas que están bien")
    a = p.parse_args()

    antes: dict[str, list[str]] = {}
    malas = movidas = revisadas = 0
    for doc in sorted((RAIZ / "docs").glob("*.md")):
        texto_doc = doc.read_text(encoding="utf-8").splitlines()
        cambio_doc = False
        for n, linea in enumerate(texto_doc):
            if OTRO_COMMIT.search(linea):
                continue
            nueva_linea = linea
            for archivo, num in CITA.findall(linea):
                ruta = RAIZ / "producto" / archivo
                if not ruta.exists():
                    continue
                revisadas += 1
                i = int(num)
                hoy = ruta.read_text(encoding="utf-8").splitlines()
                actual = hoy[i - 1].strip() if 0 < i <= len(hoy) else ""
                if a.desde:
                    if archivo not in antes:
                        antes[archivo] = lineas_en(a.desde, archivo)
                    viejo = antes[archivo][i - 1].strip() if 0 < i <= len(antes[archivo]) else ""
                    if viejo and actual != viejo:
                        candidatas = [k + 1 for k, l in enumerate(hoy) if l.strip() == viejo]
                        if len(candidatas) == 1:
                            movidas += 1
                            print(f"MOVIDA {doc.name}:{n + 1} {archivo}:{i} → {archivo}:{candidatas[0]}  ({viejo[:60]})")
                            nueva_linea = nueva_linea.replace(f"`{archivo}:{i}`", f"`{archivo}:{candidatas[0]}`")
                            continue
                        malas += 1
                        print(f"MAL    {doc.name}:{n + 1} {archivo}:{i}: decía «{viejo[:60]}» y no lo encuentro una sola vez")
                        continue
                if not actual:
                    malas += 1
                    print(f"MAL    {doc.name}:{n + 1} {archivo}:{i} no existe o está vacía")
                elif a.mostrar:
                    print(f"ok     {doc.name}:{n + 1} {archivo}:{i}  {actual[:80]}")
            if nueva_linea != linea:
                texto_doc[n] = nueva_linea
                cambio_doc = True
        if cambio_doc and a.arreglar:
            doc.write_text("\n".join(texto_doc) + "\n", encoding="utf-8")
    pendientes = malas + (0 if a.arreglar else movidas)
    print(f"{revisadas} citas revisadas: {movidas} movidas{' (arregladas)' if a.arreglar and movidas else ''}, {malas} malas")
    return 1 if pendientes else 0


if __name__ == "__main__":
    sys.exit(main())

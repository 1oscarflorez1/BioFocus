"""Trazas del coach: cada pregunta registra sus spans en orden, con su duración en ms.

Se guardan en traces/AAAA-MM-DD.jsonl (git las ignora) y la app las muestra.
Nunca llevan la llave, títulos de ventana, imágenes ni audio.
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

CARPETA = Path(__file__).resolve().parent.parent / "traces"


class Traza:
    def __init__(self, pregunta: str, carpeta: str | Path | None = None):
        self.id = uuid.uuid4().hex[:12]
        self.inicio = datetime.now()
        self.pregunta = pregunta
        self.spans: list[dict[str, Any]] = []
        self.resultado: dict[str, Any] = {}
        self.carpeta = Path(carpeta) if carpeta else CARPETA
        self._t0 = time.perf_counter()

    @contextmanager
    def span(self, tipo: str, **atributos: Any) -> Iterator[dict[str, Any]]:
        """Registra un span en el orden en que empieza; al cerrar anota su duración."""
        registro: dict[str, Any] = {"orden": len(self.spans) + 1, "tipo": tipo, **atributos}
        self.spans.append(registro)
        t = time.perf_counter()
        try:
            yield registro
        finally:
            registro["duracion_ms"] = round((time.perf_counter() - t) * 1000, 1)

    def evento(self, tipo: str, **atributos: Any) -> dict[str, Any]:
        """Span instantáneo: cambios de proveedor, límites, aprobaciones."""
        with self.span(tipo, **atributos) as registro:
            pass
        return registro

    def cerrar(self, **resultado: Any) -> dict[str, Any]:
        self.resultado = {**resultado, "duracion_total_ms": round((time.perf_counter() - self._t0) * 1000, 1)}
        return self.a_dict()

    def a_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fecha": self.inicio.isoformat(timespec="seconds"),
            "pregunta": self.pregunta,
            **self.resultado,
            "spans": self.spans,
        }

    def guardar(self) -> Path:
        self.carpeta.mkdir(parents=True, exist_ok=True)
        ruta = self.carpeta / f"{self.inicio:%Y-%m-%d}.jsonl"
        with ruta.open("a", encoding="utf-8") as f:
            f.write(json.dumps(self.a_dict(), ensure_ascii=False, default=str) + "\n")
        return ruta


class TrazaNula(Traza):
    """Para llamadas sueltas (como verificar_modelos.py): registra en memoria y no guarda."""

    def __init__(self) -> None:
        super().__init__("")

    def guardar(self) -> Path:  # pragma: no cover - no escribe nada
        return Path()

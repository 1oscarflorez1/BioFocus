"""Pruebas de los pasos 1 y 2: datos demo y herramientas.

Correr desde la raíz:  python -m unittest discover -s tests -v
"""

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "producto"))

import datos  # noqa: E402
import generar_datos_demo  # noqa: E402
import herramientas as h  # noqa: E402

HASTA = date(2026, 10, 28)
DESDE_S, HASTA_S = "2026-10-22", "2026-10-28"


class ConDemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.bd = Path(cls.tmp.name) / "demo.sqlite"
        cls.generado = generar_datos_demo.generar(HASTA, cls.bd)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def ejecutar(self, nombre, args, **extra):
        return h.ejecutar(nombre, args, ruta_bd=self.bd, **extra)


class TestDatos(ConDemo):
    def test_siete_dias_demo(self):
        with closing(sqlite3.connect(self.bd)) as con:
            dias = {r[0] for r in con.execute("SELECT substr(inicio, 1, 10) FROM sesiones")}
            no_demo = con.execute("SELECT COUNT(*) FROM sesiones WHERE es_demo = 0").fetchone()[0]
        self.assertEqual(dias, {f"2026-10-{d}" for d in range(22, 29)})
        self.assertEqual(no_demo, 0)

    def test_misma_semilla_mismos_datos(self):
        otra = Path(self.tmp.name) / "otra.sqlite"
        generar_datos_demo.generar(HASTA, otra)
        with closing(sqlite3.connect(self.bd)) as a, closing(sqlite3.connect(otra)) as b:
            self.assertEqual(list(a.iterdump()), list(b.iterdump()))

    def test_no_hay_donde_guardar_titulos(self):
        with closing(sqlite3.connect(self.bd)) as con:
            columnas = {r[1] for t in ("sesiones", "eventos") for r in con.execute(f"PRAGMA table_info({t})")}
        self.assertFalse(any("titulo" in c or "title" in c for c in columnas))
        con = datos.conectar(Path(self.tmp.name) / "vacia.sqlite")
        try:
            sid = datos.crear_sesion(con, "2026-10-28 08:00:00", None, "meta", 60)
            with self.assertRaises(ValueError):
                datos.agregar_evento(con, sid, "2026-10-28 08:01:00", "ventana", "Chrome", "sirve", 60, "Banco - Chrome")
        finally:
            con.close()

    def test_regenerar_no_toca_datos_reales(self):
        ruta = Path(self.tmp.name) / "mixta.sqlite"
        con = datos.conectar(ruta)
        with con:
            datos.crear_sesion(con, "2026-10-20 08:00:00", "2026-10-20 09:00:00", "real", 60)
        con.close()
        generar_datos_demo.generar(HASTA, ruta)
        r2 = generar_datos_demo.generar(HASTA, ruta)
        with closing(sqlite3.connect(ruta)) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM sesiones WHERE es_demo = 0").fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM sesiones WHERE es_demo = 1").fetchone()[0], r2["sesiones"])


class TestHerramientas(ConDemo):
    def test_resumen_sin_metas(self):
        r = self.ejecutar("resumen_sesiones", {"desde": DESDE_S, "hasta": HASTA_S})
        self.assertGreater(r["sesiones"], 7)
        self.assertGreater(r["minutos_reales"], 0)
        self.assertTrue(r["datos_demo"])
        texto = json.dumps(r, ensure_ascii=False)
        for meta in generar_datos_demo.METAS:
            self.assertNotIn(meta, texto)

    def test_minutos_por_categoria(self):
        r = self.ejecutar("minutos_por_categoria", {"desde": DESDE_S, "hasta": HASTA_S})
        self.assertEqual(set(r["minutos"]), set(datos.CATEGORIAS))
        self.assertAlmostEqual(sum(r["minutos"].values()), r["minutos_totales"], delta=0.5)
        self.assertGreater(r["minutos"]["sirve"], r["minutos"]["no_sirve"])

    def test_distracciones_por_app(self):
        r = self.ejecutar("distracciones_por_app", {"desde": DESDE_S, "hasta": HASTA_S, "top": 3})
        self.assertLessEqual(len(r["top"]), 3)
        minutos = [f["minutos_no_sirve"] for f in r["top"]]
        self.assertEqual(minutos, sorted(minutos, reverse=True))

    def test_alertas_por_hora(self):
        for tipo in ("postura", "distraccion", "alerta_postura"):
            r = self.ejecutar("alertas_por_hora", {"tipo": tipo, "desde": DESDE_S, "hasta": HASTA_S})
            self.assertGreater(r["total_alertas"], 0)
            self.assertIsNotNone(r["hora_con_mas_alertas"])

    def test_pausas_del_catalogo(self):
        r = h.ejecutar("pausas_recomendadas", {"motivo": "Postura"})
        catalogo = {p["nombre"] for p in h.cargar_catalogo()["pausas"] if "postura" in p["motivos"]}
        self.assertEqual({p["nombre"] for p in r["pausas"]}, catalogo)
        self.assertIn("profesional de salud", r["aviso"])

    def test_argumentos_invalidos(self):
        casos = [
            ("resumen_sesiones", {"desde": "ayer", "hasta": HASTA_S}),
            ("resumen_sesiones", {"desde": HASTA_S, "hasta": DESDE_S}),
            ("resumen_sesiones", {"desde": "2026-01-01", "hasta": "2026-12-31"}),
            ("resumen_sesiones", {"desde": "2026-02-30", "hasta": HASTA_S}),
            ("resumen_sesiones", {"desde": DESDE_S}),
            ("resumen_sesiones", "no es un objeto"),
            ("minutos_por_categoria", {"desde": DESDE_S, "hasta": HASTA_S, "sql": "DROP TABLE eventos"}),
            ("distracciones_por_app", {"desde": DESDE_S, "hasta": HASTA_S, "top": 50}),
            ("distracciones_por_app", {"desde": DESDE_S, "hasta": HASTA_S, "top": True}),
            ("alertas_por_hora", {"tipo": "sueño", "desde": DESDE_S, "hasta": HASTA_S}),
            ("pausas_recomendadas", {"motivo": "dolor de espalda"}),
            ("guardar_regla", {"app": "NoExiste", "categoria": "sirve"}),
            ("guardar_regla", {"app": "WhatsApp", "categoria": "favorita"}),
            ("guardar_regla", {"app": "x'; DROP TABLE eventos;--", "categoria": "sirve"}),
            ("no_existe", {}),
        ]
        for nombre, args in casos:
            with self.subTest(nombre=nombre, args=args), self.assertRaises(h.ErrorValidacion):
                self.ejecutar(nombre, args)

    def test_guardar_regla_requiere_aprobacion(self):
        reglas = Path(self.tmp.name) / "reglas.json"
        with mock.patch.object(h, "RUTA_REGLAS", reglas):
            with self.assertRaises(h.RequiereAprobacion):
                self.ejecutar("guardar_regla", {"app": "whatsapp", "categoria": "no_sirve"})
            self.assertFalse(reglas.exists())
            r = self.ejecutar("guardar_regla", {"app": "whatsapp", "categoria": "no sirve"}, aprobado=True)
        self.assertEqual((r["app"], r["categoria"]), ("WhatsApp", "no_sirve"))
        guardadas = json.loads(reglas.read_text(encoding="utf-8"))["reglas"]
        self.assertEqual([(g["app"], g["categoria"]) for g in guardadas], [("WhatsApp", "no_sirve")])

    def test_descripciones_como_prompt(self):
        esquemas = h.esquemas()
        self.assertEqual(len(esquemas), 6)
        for e in esquemas:
            d = e["function"]["description"]
            with self.subTest(herramienta=e["function"]["name"]):
                self.assertIn("Úsala", d)
                self.assertIn("No la uses", d)
                self.assertIn("Prerrequisito", d)


if __name__ == "__main__":
    unittest.main()

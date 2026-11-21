"""Pruebas del bloque I (lo que salió de la prueba con una persona ajena): aviso emergente, recalibrar desde la app,
sensibilidad a gusto y «Mis registros».

Sin cámara, sin red, sin llaves y sin abrir ventanas: el aviso emergente se prueba con un lanzador falso.
Correr desde la raíz:  python -m unittest discover -s tests -v
"""

import contextlib
import io
import sqlite3
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "producto"))

import aviso  # noqa: E402
import datos  # noqa: E402
import monitor  # noqa: E402
import vivo  # noqa: E402

FPS = 30


def alimentar(p: monitor.Postura, desde: float, segundos: float, valor) -> list[float]:
    alertas = []
    for i in range(int(segundos * FPS)):
        t = desde + i / FPS
        if p.actualizar(t, valor):
            alertas.append(t)
    return alertas


class TestSensibilidad(unittest.TestCase):
    def args(self, **cambios) -> Namespace:
        base = {"modo_demo": False, "caida_postura": 25, "postura_s": 20, "distraccion_s": 60, "pausa_cada_min": 50}
        return Namespace(**{**base, **cambios})

    def test_la_caida_elegida_decide_la_alerta(self):
        for caida, esperadas in ((0.20, 1), (0.25, 0)):
            p = monitor.Postura(monitor.DEMO, inicio=0.0, caida=caida)
            alimentar(p, 0.0, 6.5, 0.50)  # calibra con 0,50
            alertas = alimentar(p, 6.5, 8.0, 0.39)  # −22 %
            self.assertEqual(len(alertas), esperadas, f"caída {caida}")

    def test_el_modo_normal_usa_la_sensibilidad_y_el_demo_no(self):
        tiempos, caida = monitor.configuracion(self.args(caida_postura=30, postura_s=45, distraccion_s=120, pausa_cada_min=25))
        self.assertEqual((caida, tiempos.postura_sostenida_s, tiempos.distraccion_s, tiempos.pausa_cada_s),
                         (0.30, 45, 120, 25 * 60))
        self.assertEqual(tiempos.cooldown_s, monitor.NORMAL.cooldown_s, "lo que no se elige sigue igual")
        tiempos, caida = monitor.configuracion(self.args(modo_demo=True, caida_postura=40, postura_s=120))
        self.assertEqual((tiempos, caida), (monitor.DEMO, monitor.CAIDA_ALERTA))

    def test_los_valores_por_defecto_son_los_de_siempre(self):
        tiempos, caida = monitor.configuracion(self.args())
        self.assertEqual((tiempos, caida), (monitor.NORMAL, monitor.CAIDA_ALERTA))

    def test_el_monitor_rechaza_valores_fuera_de_los_topes(self):
        for opcion, valor in (("--caida-postura", "15"), ("--caida-postura", "41"), ("--postura-s", "4"),
                              ("--distraccion-s", "601"), ("--pausa-cada-min", "10"), ("--caida-postura", "x")):
            # TextIOWrapper y no StringIO: monitor.main reconfigura stderr a UTF-8.
            with self.subTest(opcion=opcion, valor=valor), \
                    contextlib.redirect_stderr(io.TextIOWrapper(io.BytesIO(), encoding="utf-8")):
                with self.assertRaises(SystemExit) as salida:
                    monitor.main(["--meta", "prueba", opcion, valor])
                self.assertEqual(salida.exception.code, 2)

    def test_el_tope_inferior_de_la_caida_queda_sobre_el_rearme_y_el_volver_a_sentarse(self):
        self.assertGreater(monitor.CAIDA_MIN_PCT / 100, monitor.REARME)
        self.assertGreater(monitor.CAIDA_MIN_PCT, 15, "volver a sentarse dio −15 % en el experimento 01")
        self.assertLess(monitor.CAIDA_MAX_PCT, 43, "encorvarse dio −43 %: el tope todavía alerta")


class TestAvisoEmergente(unittest.TestCase):
    def test_el_comando_es_una_lista_sin_shell_y_recorta_el_texto(self):
        cmd = aviso.comando("distraccion", "¿Esto sirve a tu meta?", "x" * 500)
        self.assertEqual(cmd[0], sys.executable)
        self.assertTrue(cmd[1].endswith("aviso.py"))
        self.assertIn("--titulo=¿Esto sirve a tu meta?", cmd)
        detalle = next(a for a in cmd if a.startswith("--detalle="))
        self.assertEqual(len(detalle), len("--detalle=") + aviso.MAX_TEXTO)
        with self.assertRaises(ValueError):
            aviso.comando("otro", "t", "d")

    def test_un_aviso_nuevo_reemplaza_al_anterior(self):
        procesos = []

        def lanzar(cmd, **kwargs):
            proceso = mock.Mock()
            proceso.poll.return_value = None  # sigue abierto
            procesos.append((cmd, proceso))
            return proceso

        e = aviso.Emergentes(lanzar=lanzar)
        e.mostrar("postura", "Revisa tu postura", "Tu cabeza bajó 30 %")
        e.mostrar("pausa", "Toma una pausa", "Levantarse y caminar")
        self.assertEqual(len(procesos), 2)
        procesos[0][1].terminate.assert_called_once()
        procesos[1][1].terminate.assert_not_called()

    def test_si_no_se_puede_lanzar_sigue_sin_error(self):
        def falla(cmd, **kwargs):
            raise OSError("sin Python")

        e = aviso.Emergentes(lanzar=falla)
        e.mostrar("postura", "Revisa tu postura", "")
        e.cerrar()

    def test_al_cumplirse_el_tiempo_avisa_y_repite_sin_terminar(self):
        fin = monitor.FinDelPlan(inicio=0.0, duracion_min=3, cada_s=600)
        self.assertFalse(fin.revisar(179.9))
        self.assertTrue(fin.revisar(180.0))
        self.assertFalse(fin.revisar(500.0), "no repite antes de 10 min")
        self.assertTrue(fin.revisar(780.0))
        self.assertIn("tiempo", aviso.COLORES)

    def test_avisar_suena_y_abre_el_aviso_salvo_en_pruebas(self):
        emergentes = mock.Mock()
        datos_aviso = {"tipo": "distraccion", "titulo": "¿Esto sirve a tu meta?", "detalle": "12 s seguidos en YouTube"}
        with mock.patch.object(monitor, "sonar") as sonar:
            monitor.avisar(emergentes, datos_aviso)
            monitor.avisar(None, datos_aviso)  # --sin-ventana: nada
        sonar.assert_called_once_with("distraccion")
        emergentes.mostrar.assert_called_once_with("distraccion", "¿Esto sirve a tu meta?", "12 s seguidos en YouTube")


class TestBaseBloqueI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bd = Path(self.tmp.name) / "i.sqlite"

    def test_recalibrar_desde_la_app_llega_una_sola_vez(self):
        r = monitor.Registro(self.bd, "Repasar cálculo", 3, modo_demo=False)
        self.assertFalse(r.pidio_recalibrar())
        with closing(datos.conectar(self.bd)) as app:
            vivo.pedir_recalibrar(app, r.id)
        self.assertTrue(r.pidio_recalibrar())
        self.assertFalse(r.pidio_recalibrar(), "la marca vuelve a 0")
        r.cerrar(r.inicio + 5, "tecla q")

    def test_una_base_vieja_recibe_la_columna_recalibrar(self):
        with closing(sqlite3.connect(self.bd)) as vieja:
            vieja.executescript(
                "CREATE TABLE estado_monitor (sesion_id INTEGER PRIMARY KEY, pid INTEGER, "
                "modo_demo INTEGER NOT NULL DEFAULT 0, actualizado TEXT NOT NULL, postura TEXT, postura_pct REAL, "
                "app TEXT, categoria TEXT, ventana_desde TEXT, detener INTEGER NOT NULL DEFAULT 0);"
            )
        with closing(datos.conectar(self.bd)) as con:
            columnas = {f["name"] for f in con.execute("PRAGMA table_info(estado_monitor)")}
        self.assertIn("recalibrar", columnas)

    def test_mis_registros_filtra_por_origen_y_fechas(self):
        with closing(datos.conectar(self.bd)) as con:
            real = datos.crear_sesion(con, "2026-11-18 20:00:00", "2026-11-18 20:30:00", "Leer", 30)
            datos.agregar_evento(con, real, "2026-11-18 20:05:00", "ventana", app="YouTube", categoria="no_sirve", duracion_s=120)
            datos.agregar_evento(con, real, "2026-11-18 20:07:00", "alerta_distraccion", app="YouTube", categoria="no_sirve")
            datos.agregar_evento(con, real, "2026-11-18 20:10:00", "alerta_postura", detalle="x")
            datos.agregar_evento(con, real, "2026-11-18 20:20:00", "pausa", duracion_s=70)
            fuera = datos.crear_sesion(con, "2026-11-10 09:00:00", "2026-11-10 09:10:00", "Antes", 10)
            datos.agregar_evento(con, fuera, "2026-11-10 09:01:00", "alerta_postura", detalle="x")
            demo = datos.crear_sesion(con, "2026-11-18 21:00:00", "2026-11-18 22:00:00", "Demo", 60, es_demo=True)
            datos.agregar_evento(con, demo, "2026-11-18 21:10:00", "alerta_postura", detalle="x")
            abierta = datos.crear_sesion(con, "2026-11-20 08:00:00", None, "Hoy", 50)
            con.commit()

            r = vivo.registros(con, False, date(2026, 11, 14), date(2026, 11, 20))
            self.assertEqual([s["id"] for s in r["sesiones"]], [abierta, real], "la más reciente primero; ni demo ni fuera de rango")
            s = r["sesiones"][1]
            self.assertEqual((s["minutos"], s["alertas_postura"], s["alertas_distraccion"], s["pausas"], s["min_no_sirve"]),
                             (30.0, 1, 1, 1, 2.0))
            self.assertEqual((r["sesiones"][0]["minutos"], r["sesiones"][0]["estado"]), (None, "abierta"))
            self.assertEqual(r["minutos"]["no_sirve"], 2.0)
            self.assertEqual(sorted((a["dia"], a["tipo"], a["n"]) for a in r["por_dia"]),
                             [("2026-11-18", "distraccion", 1), ("2026-11-18", "postura", 1)])

            solo_un_dia = vivo.registros(con, False, date(2026, 11, 18), date(2026, 11, 18))
            self.assertEqual([s["id"] for s in solo_un_dia["sesiones"]], [real], "el último día cuenta entero")
            self.assertEqual([s["id"] for s in vivo.registros(con, True, date(2026, 11, 18), date(2026, 11, 18))["sesiones"]],
                             [demo])


if __name__ == "__main__":
    unittest.main()

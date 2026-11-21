"""Pruebas del bloque J (pulido tras la entrega): sonido por el audio normal, mano en la cara, mirada fuera de la
pantalla, metas recientes y la última sesión terminada.

Sin cámara, sin red, sin llaves y sin sonar: los puntos de MediaPipe son falsos y PlaySound se reemplaza.
Correr desde la raíz:  python -m unittest discover -s tests -v
"""

import io
import sqlite3
import sys
import tempfile
import unittest
import wave
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "producto"))

import datos  # noqa: E402
import monitor  # noqa: E402
import proveedor  # noqa: E402
import ventanas  # noqa: E402
import vivo  # noqa: E402

FPS = 30
ANCHO, ALTO = 640, 480


def puntos(giro: float = 0.0, mano: tuple[float, float] | None = None, nariz_visible: bool = True) -> list:
    """33 puntos falsos de una persona de frente. `giro` corre la nariz entre las orejas (en distancias entre
    orejas); `mano` pone el índice derecho visible en (x, y)."""
    p = [SimpleNamespace(x=0.5, y=0.9, visibility=0.1) for _ in range(33)]  # manos y piernas fuera de cuadro
    p[monitor.HOMBRO_IZQ] = SimpleNamespace(x=0.65, y=0.75, visibility=0.99)
    p[monitor.HOMBRO_DER] = SimpleNamespace(x=0.35, y=0.75, visibility=0.99)
    p[monitor.OREJA_IZQ] = SimpleNamespace(x=0.56, y=0.40, visibility=0.99)
    p[monitor.OREJA_DER] = SimpleNamespace(x=0.44, y=0.40, visibility=0.99)
    for i, x in ((monitor.OJO_IZQ, 0.52), (monitor.OJO_DER, 0.48), (monitor.BOCA_IZQ, 0.52), (monitor.BOCA_DER, 0.48)):
        p[i] = SimpleNamespace(x=x, y=0.45 if i in (monitor.BOCA_IZQ, monitor.BOCA_DER) else 0.38, visibility=0.99)
    p[monitor.NARIZ] = SimpleNamespace(x=0.5 + giro * 0.12, y=0.42, visibility=0.99 if nariz_visible else 0.2)
    if mano:
        p[20] = SimpleNamespace(x=mano[0], y=mano[1], visibility=0.9)
    return p


def alimentar(g: monitor.Gestos, desde: float, segundos: float, calibrando: bool = False, **kw) -> tuple[list, int]:
    terminados, alertas = [], 0
    for i in range(int(segundos * FPS)):
        fin, alerta = g.actualizar(desde + i / FPS, puntos(**kw), ANCHO, ALTO, calibrando)
        terminados += fin
        alertas += alerta
    return terminados, alertas


class TestSonido(unittest.TestCase):
    def test_cada_aviso_es_un_wav_valido_y_corto(self):
        for tipo in monitor.TONOS:
            with wave.open(io.BytesIO(monitor.sonido_wav(tipo))) as w:
                segundos = w.getnframes() / w.getframerate()
                self.assertEqual((w.getnchannels(), w.getsampwidth()), (1, 2), tipo)
                self.assertTrue(0.2 < segundos < 1.0, f"{tipo}: {segundos:.2f} s")

    def test_suena_con_playsound_y_no_con_beep(self):
        if sys.platform != "win32":
            self.skipTest("winsound solo existe en Windows")
        import winsound

        with mock.patch.object(winsound, "PlaySound") as play, mock.patch.object(winsound, "Beep") as beep, \
                mock.patch.object(monitor.threading, "Thread", side_effect=lambda target, daemon: SimpleNamespace(start=target)):
            monitor.sonar("mirada")
        play.assert_called_once()
        self.assertEqual(play.call_args.args[0], monitor.sonido_wav("mirada"))
        self.assertTrue(play.call_args.args[1] & winsound.SND_MEMORY)
        beep.assert_not_called()


class TestMedidas(unittest.TestCase):
    def test_la_mano_sobre_la_cara_queda_cerca_y_fuera_de_cuadro_no_cuenta(self):
        self.assertIsNone(monitor.distancia_mano_cara(puntos(), ANCHO, ALTO))  # manos con visibilidad 0,1
        cerca = monitor.distancia_mano_cara(puntos(mano=(0.50, 0.44)), ANCHO, ALTO)  # entre la nariz y la boca
        lejos = monitor.distancia_mano_cara(puntos(mano=(0.30, 0.85)), ANCHO, ALTO)  # sobre la mesa
        self.assertLess(cerca, monitor.MANO_CARA_UMBRAL)
        self.assertGreater(lejos, monitor.MANO_CARA_UMBRAL)

    def test_el_giro_es_cero_de_frente_y_crece_al_girar(self):
        self.assertAlmostEqual(monitor.giro_cabeza(puntos()), 0.0)
        self.assertAlmostEqual(monitor.giro_cabeza(puntos(giro=0.3)), 0.3)
        self.assertIsNone(monitor.giro_cabeza(puntos(giro=0.3, nariz_visible=False)))


class TestGestos(unittest.TestCase):
    def nuevo(self, alerta_s: float = 5, avisar: bool = True) -> monitor.Gestos:
        g = monitor.Gestos(alerta_s, avisar, cooldown_s=30)
        alimentar(g, 0.0, 6.0, calibrando=True, giro=-0.12)  # la cámara corrida: esa es su base
        return g

    def test_mirar_a_un_lado_cuenta_frente_a_la_base_y_avisa_una_vez(self):
        g = self.nuevo()
        sin_nada, alertas = alimentar(g, 6.0, 10.0, giro=-0.05)  # +0,07 frente a la base: ruido de estar derecho
        self.assertEqual((sin_nada, alertas), ([], 0))
        terminados, alertas = alimentar(g, 16.0, 12.0, giro=0.2)  # +0,32: mirando a un lado 12 s
        self.assertEqual(alertas, 1)
        _, de_vuelta = alimentar(g, 28.0, 2.0, giro=-0.12)
        terminados += _
        self.assertEqual([t[0] for t in terminados], ["mirada_fuera"])
        self.assertAlmostEqual(terminados[0][2], 12.0, delta=0.1)

    def test_sin_aviso_igual_se_registra(self):
        g = self.nuevo(avisar=False)
        _, alertas = alimentar(g, 6.0, 8.0, giro=0.3)
        terminados = g.cerrar()
        self.assertEqual(alertas, 0)
        self.assertEqual([t[0] for t in terminados], ["mirada_fuera"])

    def test_un_vistazo_corto_no_cuenta_y_un_cuadro_suelto_no_parte_el_episodio(self):
        g = self.nuevo()
        corto, _ = alimentar(g, 6.0, 1.5, giro=0.3)  # 1,5 s: menos que MIRADA_MIN_S
        corto += alimentar(g, 7.5, 2.0, giro=-0.12)[0]
        self.assertEqual(corto, [])
        uno, _ = alimentar(g, 10.0, 3.0, mano=(0.5, 0.44))
        uno += alimentar(g, 13.0, 0.2)[0]  # la mano se pierde 0,2 s
        uno += alimentar(g, 13.2, 3.0, mano=(0.5, 0.44))[0]
        uno += alimentar(g, 16.2, 1.0)[0]
        self.assertEqual([t[0] for t in uno], ["mano_cara"])
        self.assertAlmostEqual(uno[0][2], 6.2, delta=0.1)

    def test_recalibrar_toma_una_base_nueva(self):
        g = self.nuevo()
        g.recalibrar()
        alimentar(g, 6.0, 6.0, calibrando=True, giro=0.25)  # ahora la pantalla queda hacia ese lado
        terminados, alertas = alimentar(g, 12.0, 10.0, giro=0.25)
        self.assertEqual((terminados, alertas, g.cerrar()), ([], 0, []))


class TestDatos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = Path(self.tmp.name) / "j.sqlite"

    def tearDown(self):
        self.tmp.cleanup()

    def test_los_gestos_se_guardan_aparte_y_se_cuentan_por_sesion(self):
        with closing(datos.conectar(self.ruta)) as con:
            sid = datos.crear_sesion(con, "2026-11-21 10:00:00", "2026-11-21 10:30:00", "meta", 30)
            datos.agregar_gesto(con, sid, "2026-11-21 10:05:00", "mano_cara", 3)
            datos.agregar_gesto(con, sid, "2026-11-21 10:06:00", "mano_cara", 2)
            datos.agregar_gesto(con, sid, "2026-11-21 10:07:00", "mirada_fuera", 25)
            datos.agregar_gesto(con, sid, "2026-11-21 10:07:20", "alerta_mirada", 20)
            with self.assertRaises(ValueError):
                datos.agregar_gesto(con, sid, "2026-11-21 10:08:00", "bostezo", 1)
            con.commit()
            self.assertEqual(vivo.gestos(con, [sid])[sid], {"mano_cara_n": 2, "mano_cara_s": 5, "mirada_fuera_n": 1,
                                                          "mirada_fuera_s": 25, "alertas_mirada": 1})
            self.assertEqual(con.execute("SELECT COUNT(*) FROM eventos WHERE sesion_id = ?", (sid,)).fetchone()[0], 0)
            self.assertEqual(datos.borrar_reales(con), 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM gestos").fetchone()[0], 0)

    def test_metas_recientes_sin_repetir_y_sin_demo(self):
        with closing(datos.conectar(self.ruta)) as con:
            for i, (meta, demo) in enumerate([("cálculo", False), ("física", False), ("cálculo", False), ("demo", True)]):
                datos.crear_sesion(con, f"2026-11-1{i} 10:00:00", f"2026-11-1{i} 10:30:00", meta, 30, es_demo=demo)
            datos.crear_sesion(con, "2026-11-21 11:00:00", None, "en curso", 30)
            con.commit()
            self.assertEqual(vivo.metas_recientes(con), ["en curso", "cálculo", "física"])
            terminada = vivo.ultima_sesion_real(con, terminada=True)
            self.assertEqual(con.execute("SELECT meta FROM sesiones WHERE id = ?", (terminada,)).fetchone()[0], "cálculo")
            self.assertNotEqual(vivo.ultima_sesion_real(con), terminada)

    def test_una_base_de_antes_del_bloque_j_recibe_la_tabla_de_gestos(self):
        with closing(sqlite3.connect(self.ruta)) as con:
            con.executescript("CREATE TABLE sesiones (id INTEGER PRIMARY KEY, inicio TEXT NOT NULL, fin TEXT, "
                              "meta TEXT NOT NULL, duracion_planeada_min INTEGER NOT NULL, es_demo INTEGER NOT NULL DEFAULT 0);")
        with closing(datos.conectar(self.ruta)) as con:
            self.assertIn("gestos", {f[0] for f in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")})


class TestSinInternet(unittest.TestCase):
    """Tarea J6: el interruptor «Modo sin internet» de la app. La llave es falsa y nunca se usa."""

    NUBE = {"LLM_PROVIDER": "groq", "LLM_API_KEY": "llave-falsa"}

    def test_encendido_el_clasificador_va_a_ollama_en_este_equipo_y_sin_llave(self):
        nube = ventanas.perfil_clasificador(ventanas.entorno_llm(False, self.NUBE))
        local = ventanas.perfil_clasificador(ventanas.entorno_llm(True, self.NUBE))
        self.assertEqual((nube.proveedor, local.proveedor, local.api_key), ("groq", "ollama", ""))
        self.assertTrue(local.base_url.startswith("http://localhost:"))

    def test_encendido_el_coach_solo_recibe_perfiles_locales(self):
        perfiles = proveedor.perfiles_configurados(ventanas.entorno_llm(True, self.NUBE))
        self.assertEqual({p.proveedor for p in perfiles}, {"ollama"})
        self.assertFalse(any(p.api_key for p in perfiles))

    def test_apagar_el_interruptor_no_apaga_el_offline_de_env(self):
        env = {**self.NUBE, "OFFLINE_MODE": "true"}
        self.assertTrue(ventanas.sin_internet_en(ventanas.entorno_llm(False, env)))
        self.assertEqual(ventanas.perfil_clasificador(ventanas.entorno_llm(False, env)).proveedor, "ollama")

    def test_el_clasificador_cambia_en_plena_sesion_y_no_vuelve_a_la_nube(self):
        llamadas = []

        def llamar_llm(mensajes, herramientas, *, perfiles, timeout_s, opciones):
            llamadas.append([p.proveedor for p in perfiles])
            return SimpleNamespace(ok=False, error="Ollama no responde", mensaje=None)

        with mock.patch.object(ventanas.proveedor, "leer_env", return_value=dict(self.NUBE)), \
                mock.patch.object(ventanas, "calentar"), \
                mock.patch.object(ventanas.proveedor, "llamar_llm", side_effect=llamar_llm):
            c = ventanas.Clasificador("repasar cálculo")
            self.assertEqual(c.perfil.proveedor, "groq")
            c.usar_sin_internet(True)
            self.assertEqual(c.perfil.proveedor, "ollama")
            with self.assertRaises(RuntimeError):
                c._llm("repasar cálculo", "Chrome", "un título ambiguo")
            c.usar_sin_internet(False)
            self.assertEqual(c.perfil.proveedor, "groq")
        self.assertEqual(llamadas, [["ollama"]])  # con Ollama caído, falla: no prueba con la nube

    def test_la_app_le_pasa_el_cambio_al_monitor_por_la_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "j6.sqlite"
            registro = monitor.Registro(ruta, "meta", 25, False, sin_internet=False)
            try:
                self.assertFalse(registro.pide_sin_internet())
                with closing(datos.conectar(ruta)) as con:
                    vivo.pedir_sin_internet(con, registro.id, True)
                self.assertTrue(registro.pide_sin_internet())
            finally:
                registro.cerrar(1795290000.0, "prueba")

    def test_una_base_vieja_recibe_la_columna_sin_internet(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "vieja.sqlite"
            with closing(sqlite3.connect(ruta)) as vieja:
                vieja.executescript(
                    "CREATE TABLE estado_monitor (sesion_id INTEGER PRIMARY KEY, pid INTEGER, "
                    "modo_demo INTEGER NOT NULL DEFAULT 0, actualizado TEXT NOT NULL, postura TEXT, postura_pct REAL, "
                    "app TEXT, categoria TEXT, ventana_desde TEXT, detener INTEGER NOT NULL DEFAULT 0);")
            with closing(datos.conectar(ruta)) as con:
                columnas = {f["name"] for f in con.execute("PRAGMA table_info(estado_monitor)")}
            self.assertIn("sin_internet", columnas)


if __name__ == "__main__":
    unittest.main()

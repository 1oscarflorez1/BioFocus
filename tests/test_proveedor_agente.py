"""Pruebas de los pasos 3 a 5: proveedor, agente y trazas, sin red.

Un servidor falso en 127.0.0.1 imita chat/completions con un guion de respuestas.
Correr desde la raíz:  python -m unittest discover -s tests -v
"""

import json
import sys
import tempfile
import threading
import time
import unittest
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "producto"))

import agente  # noqa: E402
import generar_datos_demo  # noqa: E402
import herramientas  # noqa: E402
import proveedor  # noqa: E402
import trazas  # noqa: E402

LLAVE = "llave-falsa-123"
RANGO = {"desde": "2026-10-22", "hasta": "2026-10-28"}


def herramienta(nombre, args, uso=(500, 40)):
    return {"herramienta": nombre, "args": args, "uso": uso}


def texto(contenido, uso=(600, 60)):
    return {"texto": contenido, "uso": uso}


class ServidorFalso:
    def __init__(self, guion):
        self.guion, self.pedidos = list(guion), []
        servidor = self

        class Manejador(BaseHTTPRequestHandler):
            def do_POST(self):
                largo = int(self.headers.get("Content-Length", 0))
                servidor.pedidos.append(json.loads(self.rfile.read(largo)))
                paso = servidor.guion.pop(0) if servidor.guion else texto("fin del guion")
                time.sleep(paso.get("dormir", 0))
                if "estado" in paso:
                    cuerpo = b'{"error": {"message": "falso"}}'
                    self.send_response(paso["estado"])
                else:
                    if "herramienta" in paso:
                        mensaje = {"role": "assistant", "content": None, "tool_calls": [{
                            "id": f"call_{len(servidor.pedidos)}", "type": "function",
                            "function": {"name": paso["herramienta"], "arguments": json.dumps(paso["args"])}}]}
                    else:
                        mensaje = {"role": "assistant", "content": paso["texto"]}
                    entrada, salida = paso["uso"]
                    cuerpo = json.dumps({"choices": [{"message": mensaje}],
                                         "usage": {"prompt_tokens": entrada, "completion_tokens": salida}}).encode()
                    self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                try:
                    self.wfile.write(cuerpo)
                except OSError:
                    pass

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self.httpd.handle_error = lambda *a: None
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        self.perfiles = [
            proveedor.Perfil("principal", "groq", "modelo-a", url, LLAVE),
            proveedor.Perfil("respaldo", "gemini", "modelo-b", url, LLAVE),
        ]

    def cerrar(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.bd = Path(cls.tmp.name) / "demo.sqlite"
        generar_datos_demo.generar(date(2026, 10, 28), cls.bd)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.esperas = []
        parches = [
            mock.patch.object(proveedor, "time", SimpleNamespace(sleep=self.esperas.append)),
            mock.patch.object(trazas, "CARPETA", Path(self.tmp.name) / "traces"),
            mock.patch.object(herramientas, "RUTA_REGLAS", Path(self.tmp.name) / "reglas.json"),
        ]
        for p in parches:
            p.start()
            self.addCleanup(p.stop)

    def servidor(self, guion):
        s = ServidorFalso(guion)
        self.addCleanup(s.cerrar)
        return s

    def preguntar(self, servidor, pregunta="¿cuánto estudié?", **inter):
        return agente.responder(pregunta, perfiles=servidor.perfiles, ruta_bd=self.bd,
                                interruptores=proveedor.Interruptores(**inter))

    def tipos(self, r):
        return [s["tipo"] for s in r.traza["spans"]]


class TestProveedor(Base):
    def test_429_forzado_en_principal_pasa_al_respaldo(self):
        s = self.servidor([herramienta("minutos_por_categoria", RANGO), texto("Tuviste 942 min útiles.")])
        r = self.preguntar(s, forzar_429="principal")
        self.assertTrue(r.ok, r.texto)
        self.assertEqual(self.esperas, [1, 2, 4])
        cambio = next(x for x in r.traza["spans"] if x["tipo"] == "cambio_proveedor")
        self.assertEqual((cambio["de"], cambio["a"]), ("groq · modelo-a", "gemini · modelo-b"))
        self.assertEqual(self.tipos(r)[:8], ["llm", "reintento", "llm", "reintento", "llm", "reintento", "llm", "cambio_proveedor"])

    def test_429_forzado_en_todos_da_mensaje_honesto(self):
        s = self.servidor([])
        r = self.preguntar(s, forzar_429="todos")
        self.assertFalse(r.ok)
        self.assertIn("429", r.texto)
        self.assertIn("sesión sigue abierta", r.texto)
        self.assertEqual(self.esperas, [1, 2, 4, 1, 2, 4])
        self.assertEqual(s.pedidos, [])  # forzado: ni siquiera salió a la red

    def test_429_real_reintenta_y_sigue(self):
        s = self.servidor([{"estado": 429}, {"estado": 429}, texto("Hola, pregúntame por tus sesiones.")])
        r = proveedor.llamar_llm([{"role": "user", "content": "hola"}], None, perfiles=s.perfiles)
        self.assertTrue(r.ok)
        self.assertEqual(self.esperas, [1, 2])

    def test_timeout_forzado_sin_stack_trace(self):
        s = self.servidor([])
        r = self.preguntar(s, forzar_timeout=True)
        self.assertFalse(r.ok)
        self.assertIn("no respondió en 20 s", r.texto)
        self.assertNotIn("Traceback", r.texto)
        self.assertIn("limite", self.tipos(r))

    def test_timeout_real_sin_stack_trace(self):
        s = self.servidor([{"dormir": 1.5, **texto("tarde")}])
        r = proveedor.llamar_llm([{"role": "user", "content": "hola"}], None, perfiles=s.perfiles, timeout_s=0.3)
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "timeout")

    def test_la_llave_no_aparece_en_trazas(self):
        s = self.servidor([herramienta("resumen_sesiones", RANGO), texto("ok")])
        r = self.preguntar(s, forzar_429="principal")
        self.assertNotIn(LLAVE, json.dumps(r.traza, ensure_ascii=False))
        self.assertNotIn(LLAVE, repr(s.perfiles))


class TestAgente(Base):
    def test_responde_con_datos_y_traza_en_orden(self):
        s = self.servidor([herramienta("minutos_por_categoria", RANGO), texto("Tuviste 942 min útiles.")])
        r = self.preguntar(s)
        self.assertTrue(r.ok)
        self.assertEqual(self.tipos(r), ["llm", "validacion", "herramienta", "llm"])
        self.assertEqual([x["orden"] for x in r.traza["spans"]], [1, 2, 3, 4])
        self.assertTrue(all("duracion_ms" in x for x in r.traza["spans"]))
        self.assertIn("Minutos por categoría", r.fuente_y_criterio)
        archivo = Path(self.tmp.name) / "traces" / f"{date.today():%Y-%m-%d}.jsonl"
        ultima = json.loads(archivo.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(ultima["id"], r.traza["id"])

    def test_salida_invalida_una_vez_reintenta_con_el_error(self):
        s = self.servidor([herramienta("resumen_sesiones", RANGO), herramienta("resumen_sesiones", RANGO), texto("16 sesiones.")])
        r = self.preguntar(s, forzar_salida_invalida="una_vez")
        self.assertTrue(r.ok, r.texto)
        validaciones = [x["ok"] for x in r.traza["spans"] if x["tipo"] == "validacion"]
        self.assertEqual(validaciones, [False, True])
        error_al_modelo = s.pedidos[1]["messages"][-1]
        self.assertEqual(error_al_modelo["role"], "tool")
        self.assertIn("Argumentos inválidos", error_al_modelo["content"])

    def test_salida_invalida_dos_veces_responde_en_texto_y_registra(self):
        s = self.servidor([herramienta("resumen_sesiones", RANGO), herramienta("resumen_sesiones", RANGO)])
        r = self.preguntar(s, forzar_salida_invalida="siempre")
        self.assertFalse(r.ok)
        self.assertIn("argumentos inválidos dos veces", r.texto)
        self.assertEqual(r.traza["fallo"], "salida_invalida")
        self.assertIn("fallo_registrado", self.tipos(r))

    def test_limite_de_iteraciones(self):
        s = self.servidor([herramienta("pausas_recomendadas", {"motivo": "general"}, uso=(100, 10))] * 8)
        r = self.preguntar(s)
        self.assertFalse(r.ok)
        self.assertIn(f"límite de {agente.MAX_ITERACIONES} pasos", r.texto)
        self.assertEqual(self.tipos(r).count("llm"), agente.MAX_ITERACIONES)

    def test_limite_de_tokens(self):
        s = self.servidor([herramienta("resumen_sesiones", RANGO, uso=(11_500, 100)), texto("no debería llegar")])
        r = self.preguntar(s)
        self.assertFalse(r.ok)
        self.assertIn("12 000 tokens", r.texto)
        self.assertEqual(len(s.pedidos), 1)

    def test_timeout_de_herramienta_lo_dice_la_respuesta(self):
        s = self.servidor([herramienta("resumen_sesiones", RANGO), texto("No tengo esos datos ahora.")])
        lenta = lambda *a, **k: time.sleep(1) or {}
        with mock.patch.object(agente, "TIMEOUT_HERRAMIENTA_S", 0.2), mock.patch.object(herramientas, "ejecutar", lenta):
            r = self.preguntar(s)
        self.assertIn("superó el límite de 0.2 s", r.texto)
        self.assertIn("timeout_herramienta", json.dumps(r.traza))

    def test_guardar_regla_espera_aprobacion_humana(self):
        s = self.servidor([herramienta("guardar_regla", {"app": "whatsapp", "categoria": "no_sirve"})])
        r = self.preguntar(s, "marca WhatsApp como no sirve")
        reglas = herramientas.RUTA_REGLAS
        self.assertEqual(r.pendiente, {"herramienta": "guardar_regla", "argumentos": {"app": "WhatsApp", "categoria": "no_sirve"}})
        self.assertFalse(reglas.exists())
        rechazo = agente.resolver_aprobacion(r.pendiente, False, ruta_bd=self.bd)
        self.assertIn("rechazaste", rechazo.texto)
        self.assertFalse(reglas.exists())
        ok = agente.resolver_aprobacion(r.pendiente, True, ruta_bd=self.bd)
        self.assertIn("guardé la regla", ok.texto)
        self.assertEqual(json.loads(reglas.read_text(encoding="utf-8"))["reglas"][0]["app"], "WhatsApp")


if __name__ == "__main__":
    unittest.main()

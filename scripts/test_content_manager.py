#!/usr/bin/env python3
"""Batería en seco de la cola de contenido. `unittest` de stdlib, BD temporal, cero red.

Nunca toca `data/el_socio.db`, nunca escribe en `contexto/RESULTADOS_MERCADO.md` y
nunca renderiza de verdad (el subprocess siempre va parcheado).

    python3 scripts/test_content_manager.py
"""

from __future__ import annotations

import hashlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import autopilot_dispatcher  # noqa: E402
import content_manager  # noqa: E402
import database  # noqa: E402
import panel_mensajes  # noqa: E402

DB_REAL = PROJECT_ROOT / "data" / "el_socio.db"
RESULTADOS_REAL = PROJECT_ROOT / "contexto" / "RESULTADOS_MERCADO.md"

CABECERA_RESULTADOS = (
    "# Resultados de mercado\n\n## Registro\n"
    "<!-- filas al FINAL. Nada debajo de la tabla. -->\n"
    "| Fecha | Nicho | Ángulo usado | Canal | Cantidad | Resultado | Nota |\n"
    "|---|---|---|---|---|---|---|\n"
    "| 2026-01-01 | fila-que-ya-estaba | no se toca | correo | 3 | silencio | Intocable. |\n"
)


def huella(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest() if ruta.exists() else "(no existe)"


class BaseContenido(unittest.TestCase):
    """Cada prueba con su propia BD y su propio RESULTADOS_MERCADO.md."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "prueba.db"
        self.parche_db = mock.patch.object(database, "DB_PATH", self.db)
        self.parche_db.start()
        database.init_db()

        self.resultados = Path(self.tmp.name) / "RESULTADOS_MERCADO.md"
        self.resultados.write_text(CABECERA_RESULTADOS, encoding="utf-8")
        self.parche_resultados = mock.patch.object(
            autopilot_dispatcher, "RESULTADOS_FILE", self.resultados)
        self.parche_resultados.start()

        # Nada de renders reales: el subprocess siempre está parcheado.
        self.parche_run = mock.patch.object(content_manager.subprocess, "run")
        self.run = self.parche_run.start()
        self.run.return_value = mock.Mock(returncode=0, stdout="ok", stderr="")

        self.addCleanup(self._reales_intactos, huella(DB_REAL), huella(RESULTADOS_REAL))
        self.addCleanup(self.parche_run.stop)
        self.addCleanup(self.parche_resultados.stop)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.parche_db.stop)

    def _reales_intactos(self, db_antes: str, md_antes: str) -> None:
        self.assertEqual(huella(DB_REAL), db_antes, "una prueba tocó data/el_socio.db")
        self.assertEqual(huella(RESULTADOS_REAL), md_antes,
                         "una prueba escribió en contexto/RESULTADOS_MERCADO.md")

    def filas_resultados(self) -> list[str]:
        return [l for l in self.resultados.read_text(encoding="utf-8").splitlines()
                if l.startswith("| 20")]

    def encolar_limpia(self, **kw) -> int:
        datos = dict(tipo="post", gancho="Tu competencia ya tiene quien le resuelva esto.")
        datos.update(kw)
        return content_manager.encolar(**datos)["id"]


# ----------------------------------------------------- 1. la guarda de precios manda

class TestGuardaEnContenido(BaseContenido):
    def test_gancho_con_precio_no_entra_a_la_cola(self) -> None:
        with self.assertRaises(content_manager.GuardaBloqueada):
            content_manager.encolar(tipo="post", gancho="Te hago el logo por 80000 pesos")
        self.assertEqual(database.list_content(), [], "la pieza bloqueada quedó en la BD")

    def test_caption_con_precio_tambien_bloquea(self) -> None:
        with self.assertRaises(content_manager.GuardaBloqueada):
            content_manager.encolar(tipo="post", gancho="Frase limpia",
                                    caption="Desde $50.000 el diseño")
        self.assertEqual(database.list_content(), [])

    def test_guion_con_precio_tambien_bloquea(self) -> None:
        with self.assertRaises(content_manager.GuardaBloqueada):
            content_manager.encolar(tipo="video", gancho="Frase limpia",
                                    guion="Te cuesta 3 millones arreglarlo")
        self.assertEqual(database.list_content(), [])

    def test_link_de_pago_bloquea(self) -> None:
        with self.assertRaises(content_manager.GuardaBloqueada):
            content_manager.encolar(tipo="post", gancho="Mira esto",
                                    caption="Paga en checkout.ejemplo.com/pagar")
        self.assertEqual(database.list_content(), [])

    def test_pieza_limpia_si_entra(self) -> None:
        content_id = self.encolar_limpia()
        pieza = database.get_content(content_id)
        self.assertEqual(pieza["estado"], "borrador")
        self.assertEqual(pieza["tipo"], "post")

    def test_los_motivos_llegan_al_que_llama(self) -> None:
        with self.assertRaises(content_manager.GuardaBloqueada) as ctx:
            content_manager.encolar(tipo="post", gancho="Vale 200000 pesos")
        self.assertTrue(ctx.exception.motivos, "la excepción vino sin motivos")

    def test_la_guarda_se_repite_al_generar(self) -> None:
        """Si alguien edita la fila a mano en la BD, generar tiene que frenarla igual."""
        content_id = self.encolar_limpia()
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE content_queue SET caption=? WHERE id=?",
                        ("Son 150000 pesos", content_id))
        with self.assertRaises(content_manager.GuardaBloqueada):
            content_manager.generar(content_id)
        self.run.assert_not_called()
        self.assertEqual(database.get_content(content_id)["estado"], "borrador")


# ------------------------------------------------------------- 2. generar la pieza

class TestGenerar(BaseContenido):
    def test_post_llama_a_generar_post_sh(self) -> None:
        content_id = self.encolar_limpia()
        res = content_manager.generar(content_id)
        self.assertTrue(res["generado"], res)
        cmd = self.run.call_args[0][0]
        self.assertIn("generar_post.sh", cmd[0])
        self.assertEqual(database.get_content(content_id)["estado"], "generado")

    def test_video_manda_props_del_reel(self) -> None:
        content_id = self.encolar_limpia(
            tipo="video", guion="Primer bloque\nSegundo bloque", caption="Cierre limpio")
        res = content_manager.generar(content_id)
        self.assertTrue(res["generado"], res)
        cmd = self.run.call_args[0][0]
        self.assertIn("generar_video.sh", cmd[0])
        self.assertEqual(cmd[1], "--reel")
        import json
        props = json.loads(cmd[2])
        self.assertEqual(props["bloques"], ["Primer bloque", "Segundo bloque"])
        self.assertEqual(props["cierre"], "Cierre limpio")

    def test_render_que_falla_no_marca_generado(self) -> None:
        content_id = self.encolar_limpia()
        self.run.return_value = mock.Mock(returncode=1, stdout="", stderr="explotó")
        res = content_manager.generar(content_id)
        self.assertFalse(res["generado"])
        self.assertEqual(database.get_content(content_id)["estado"], "borrador")

    def test_no_se_regenera_una_pieza_publicada(self) -> None:
        content_id = self.encolar_limpia()
        database.update_content(content_id, estado="publicado")
        res = content_manager.generar(content_id)
        self.assertFalse(res["generado"])
        self.run.assert_not_called()

    def test_pieza_inexistente(self) -> None:
        res = content_manager.generar(9999)
        self.assertFalse(res["generado"])
        self.run.assert_not_called()

    def test_el_guion_se_corta_en_max_bloques(self) -> None:
        guion = "\n".join(f"bloque {i}" for i in range(12))
        content_id = self.encolar_limpia(tipo="video", guion=guion)
        content_manager.generar(content_id)
        import json
        props = json.loads(self.run.call_args[0][0][2])
        self.assertEqual(len(props["bloques"]), content_manager.MAX_BLOQUES)


# ------------------------------------------------- 3. publicar registra dato real

class TestPublicar(BaseContenido):
    def test_publicar_escribe_fila_de_instagram(self) -> None:
        content_id = self.encolar_limpia(nicho="fichas-tecnicas-ropa")
        res = content_manager.publicar(content_id, resultado="respondió", cantidad=2)
        self.assertTrue(res["publicado"], res)
        fila = self.filas_resultados()[-1]
        self.assertIn("| instagram | 2 | respondió |", fila)
        self.assertIn("fichas-tecnicas-ropa", fila)

    def test_publicar_sella_estado_y_fecha(self) -> None:
        content_id = self.encolar_limpia()
        content_manager.publicar(content_id, resultado="silencio")
        pieza = database.get_content(content_id)
        self.assertEqual(pieza["estado"], "publicado")
        self.assertTrue(pieza["published_at"], "no quedó sellada la fecha")

    def test_no_se_publica_dos_veces(self) -> None:
        content_id = self.encolar_limpia()
        content_manager.publicar(content_id, resultado="silencio")
        antes = len(self.filas_resultados())
        res = content_manager.publicar(content_id, resultado="respondió")
        self.assertFalse(res["publicado"])
        self.assertEqual(len(self.filas_resultados()), antes, "duplicó la fila")

    def test_resultado_invalido_no_publica_ni_escribe(self) -> None:
        content_id = self.encolar_limpia()
        antes = len(self.filas_resultados())
        res = content_manager.publicar(content_id, resultado="me fue bonito")
        self.assertFalse(res["publicado"])
        self.assertEqual(len(self.filas_resultados()), antes)
        self.assertEqual(database.get_content(content_id)["estado"], "borrador")

    def test_la_fila_que_ya_estaba_nunca_se_toca(self) -> None:
        content_id = self.encolar_limpia()
        content_manager.publicar(content_id, resultado="agendó")
        self.assertIn("fila-que-ya-estaba", self.filas_resultados()[0])


# ------------------------------------------------------------------ 4. dry-run seco

class TestDryRun(BaseContenido):
    def test_encolar_dry_run_no_escribe(self) -> None:
        res = content_manager.encolar(tipo="post", gancho="Frase limpia", dry_run=True)
        self.assertTrue(res["dry_run"])
        self.assertEqual(database.list_content(), [])

    def test_encolar_dry_run_igual_aplica_la_guarda(self) -> None:
        with self.assertRaises(content_manager.GuardaBloqueada):
            content_manager.encolar(tipo="post", gancho="Vale 90000 pesos", dry_run=True)

    def test_generar_dry_run_no_renderiza(self) -> None:
        content_id = self.encolar_limpia()
        res = content_manager.generar(content_id, dry_run=True)
        self.assertTrue(res["dry_run"])
        self.run.assert_not_called()
        self.assertEqual(database.get_content(content_id)["estado"], "borrador")

    def test_publicar_dry_run_no_toca_el_archivo(self) -> None:
        content_id = self.encolar_limpia()
        antes = huella(self.resultados)
        res = content_manager.publicar(content_id, resultado="respondió", dry_run=True)
        self.assertTrue(res["dry_run"])
        self.assertEqual(huella(self.resultados), antes, "el dry-run escribió la fila")
        self.assertEqual(database.get_content(content_id)["estado"], "borrador")

    def test_descartar_dry_run_no_cambia_estado(self) -> None:
        content_id = self.encolar_limpia()
        content_manager.descartar(content_id, dry_run=True)
        self.assertEqual(database.get_content(content_id)["estado"], "borrador")


# -------------------------------------------------------------- 5. estados y BD

class TestEstados(BaseContenido):
    def test_estado_invalido_revienta(self) -> None:
        content_id = self.encolar_limpia()
        with self.assertRaises(ValueError):
            database.update_content(content_id, estado="inventado")

    def test_tipo_invalido_revienta(self) -> None:
        with self.assertRaises(ValueError):
            database.enqueue_content(tipo="tiktok", gancho="x")

    def test_gancho_vacio_revienta(self) -> None:
        with self.assertRaises(ValueError):
            database.enqueue_content(tipo="post", gancho="   ")

    def test_descartar_deja_la_nota(self) -> None:
        content_id = self.encolar_limpia()
        content_manager.descartar(content_id, nota="no convence")
        pieza = database.get_content(content_id)
        self.assertEqual(pieza["estado"], "descartado")
        self.assertEqual(pieza["nota"], "no convence")

    def test_listar_filtra_por_estado(self) -> None:
        a = self.encolar_limpia()
        self.encolar_limpia(gancho="Otra frase limpia y sobria.")
        database.update_content(a, estado="aprobado")
        self.assertEqual(len(database.list_content(estado="aprobado")), 1)
        self.assertEqual(len(database.list_content(estado="borrador")), 1)

    def test_conteo_por_estado(self) -> None:
        self.encolar_limpia()
        self.assertEqual(database.count_content_by_estado(), {"borrador": 1})

    def test_la_tabla_no_rompe_las_que_ya_estaban(self) -> None:
        """init_db() se puede correr mil veces sin perder datos de otras tablas."""
        database.upsert_lead(name="", company="X", email="a@b.com")
        self.encolar_limpia()
        database.init_db()
        self.assertIsNotNone(database.get_lead_by_email("a@b.com"))
        self.assertEqual(len(database.list_content()), 1)


# --------------------------------------------------- 6. el panel no se deja inyectar

class TestPanelEscapa(unittest.TestCase):
    def test_mensaje_de_la_landing_va_escapado(self) -> None:
        html = panel_mensajes.render(
            [{"received_at": "2026-01-01", "mensaje": "<script>alert('x')</script>",
              "estado": "nuevo"}], [])
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)

    def test_gancho_de_contenido_va_escapado(self) -> None:
        html = panel_mensajes.render([], [
            {"id": 1, "gancho": "<img src=x onerror=alert(1)>", "tipo": "post",
             "estado": "borrador", "archivo": ""}])
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img", html)

    def test_estado_desconocido_no_rompe_el_color(self) -> None:
        html = panel_mensajes.render([], [
            {"id": 1, "gancho": "ok", "tipo": "post", "estado": "raro", "archivo": ""}])
        self.assertIn("raro", html)

    def test_cola_vacia_no_revienta(self) -> None:
        html = panel_mensajes.render([], [])
        self.assertIn("Cola de contenido", html)


# ------------------------------------------- 7. nada de esto toca lo real, de verdad

class TestNadaRealSeToca(unittest.TestCase):
    def test_el_cli_en_dry_run_no_toca_la_bd_real(self) -> None:
        antes_db, antes_md = huella(DB_REAL), huella(RESULTADOS_REAL)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch.object(database, "DB_PATH", Path(tmp.name) / "x.db"):
            código = content_manager.main(
                ["--dry-run", "encolar", "--gancho", "Una frase limpia y sobria."])
        self.assertEqual(código, 0)
        self.assertEqual(huella(DB_REAL), antes_db, "el dry-run modificó data/el_socio.db")
        self.assertEqual(huella(RESULTADOS_REAL), antes_md,
                         "el dry-run modificó RESULTADOS_MERCADO.md")

    def test_el_cli_devuelve_codigo_2_si_la_guarda_bloquea(self) -> None:
        antes_db = huella(DB_REAL)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch.object(database, "DB_PATH", Path(tmp.name) / "x.db"):
            código = content_manager.main(
                ["--dry-run", "encolar", "--gancho", "Son 70000 pesos"])
        self.assertEqual(código, 2)
        self.assertEqual(huella(DB_REAL), antes_db)


if __name__ == "__main__":
    unittest.main(verbosity=2)

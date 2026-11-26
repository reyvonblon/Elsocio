#!/usr/bin/env python3
"""Batería en seco del ciclo de insights: tabla de métricas y recolector. Cero red.

    python3 scripts/test_insights.py
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import database  # noqa: E402
import insights_collector as ic  # noqa: E402

DB_REAL = PROJECT_ROOT / "data" / "el_socio.db"


def huella(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest() if ruta.exists() else "(no existe)"


class BaseInsights(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.parche_db = mock.patch.object(database, "DB_PATH", Path(self.tmp.name) / "prueba.db")
        self.parche_db.start()
        database.init_db()
        self.addCleanup(self._db_real_intacta, huella(DB_REAL))
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.parche_db.stop)

    def _db_real_intacta(self, antes: str) -> None:
        self.assertEqual(huella(DB_REAL), antes, "una prueba tocó data/el_socio.db")

    def reel_publicado(self, *, horas: float, media: str = "MEDIA1") -> int:
        """Un reel ya publicado hace `horas`, listo para que lo capture el recolector."""
        pid = database.enqueue_content(tipo="video", gancho="Frase limpia")
        database.update_content(pid, estado="publicado", ig_media_id=media)
        import sqlite3
        with sqlite3.connect(database.DB_PATH) as conn:
            conn.execute(
                "UPDATE content_queue SET published_at = datetime('now', ?) WHERE id=?",
                (f"-{horas} hours", pid))
        return pid


# ----------------------------------------------------- 1. la tabla de métricas

class TestTablaMetricas(BaseInsights):
    def test_guarda_y_lee_una_captura(self) -> None:
        pid = self.reel_publicado(horas=30)
        database.guardar_metricas(pid, "24h", alcance=500, guardados=20, compartidos=8)
        m = database.metricas_de(pid, "24h")
        self.assertEqual((m["alcance"], m["guardados"], m["compartidos"]), (500, 20, 8))

    def test_la_retencion_sale_de_watch_time_y_duracion(self) -> None:
        pid = self.reel_publicado(horas=30)
        database.guardar_metricas(pid, "24h", watch_time_ms=12000, duracion_s=24.0)
        self.assertEqual(database.metricas_de(pid, "24h")["retencion_pct"], 50.0)

    def test_sin_duracion_la_retencion_queda_nula_no_en_cero(self) -> None:
        """Cero datos inventados: si no se pudo medir, es NULL, no 0% (que significaría 'malísimo')."""
        pid = self.reel_publicado(horas=30)
        database.guardar_metricas(pid, "24h", watch_time_ms=12000, duracion_s=0.0)
        self.assertIsNone(database.metricas_de(pid, "24h")["retencion_pct"])

    def test_las_dos_ventanas_conviven(self) -> None:
        """Las métricas son serie de tiempo: la de 7d no pisa la de 24h."""
        pid = self.reel_publicado(horas=200)
        database.guardar_metricas(pid, "24h", alcance=100)
        database.guardar_metricas(pid, "7d", alcance=900)
        todas = database.metricas_de(pid)
        self.assertEqual([(m["ventana"], m["alcance"]) for m in todas], [("24h", 100), ("7d", 900)])

    def test_recapturar_la_misma_ventana_reemplaza(self) -> None:
        pid = self.reel_publicado(horas=30)
        database.guardar_metricas(pid, "24h", alcance=100)
        database.guardar_metricas(pid, "24h", alcance=180)
        self.assertEqual(len(database.metricas_de(pid)), 1)
        self.assertEqual(database.metricas_de(pid, "24h")["alcance"], 180)

    def test_ventana_invalida_no_entra(self) -> None:
        pid = self.reel_publicado(horas=30)
        with self.assertRaises(ValueError):
            database.guardar_metricas(pid, "2h", alcance=1)


# ----------------------------------------------------- 2. a quién le toca captura

class TestAQuienLeToca(BaseInsights):
    def test_un_reel_de_30_horas_le_toca_24h_pero_no_7d(self) -> None:
        pid = self.reel_publicado(horas=30)
        self.assertEqual([p["id"] for p in database.reels_por_capturar("24h", horas_minimas=24)],
                         [pid])
        self.assertEqual(database.reels_por_capturar("7d", horas_minimas=168), [])

    def test_un_reel_recien_publicado_no_le_toca_nada(self) -> None:
        self.reel_publicado(horas=2)
        self.assertEqual(database.reels_por_capturar("24h", horas_minimas=24), [])

    def test_lo_ya_capturado_no_vuelve_a_salir(self) -> None:
        pid = self.reel_publicado(horas=30)
        database.guardar_metricas(pid, "24h", alcance=10)
        self.assertEqual(database.reels_por_capturar("24h", horas_minimas=24), [])

    def test_la_historia_no_vota(self) -> None:
        """§2 del diseño: solo los reels enseñan. La historia muere a las 24 h."""
        pid = database.enqueue_content(tipo="historia", gancho="Frase limpia")
        database.update_content(pid, estado="publicado", ig_media_id="MEDIA9")
        import sqlite3
        with sqlite3.connect(database.DB_PATH) as conn:
            conn.execute("UPDATE content_queue SET published_at=datetime('now','-30 hours') "
                         "WHERE id=?", (pid,))
        self.assertEqual(database.reels_por_capturar("24h", horas_minimas=24), [])

    def test_sin_media_id_no_se_puede_capturar(self) -> None:
        pid = database.enqueue_content(tipo="video", gancho="Frase limpia")
        database.update_content(pid, estado="publicado")
        self.assertEqual(database.reels_por_capturar("24h", horas_minimas=24), [])


# ----------------------------------------------------- 3. el comentario real vs el emoji

class TestClasificarComentarios(unittest.TestCase):
    def test_el_emoji_no_es_senal(self) -> None:
        for t in ("🔥🔥🔥", "❤️", "👏👏", "si", "bueno", "Gracias!!", "💯"):
            self.assertFalse(ic.comentario_es_real(t), f"contó como real: {t!r}")

    def test_el_comentario_que_dice_algo_si_cuenta(self) -> None:
        for t in ("Esto me pasó el mes pasado con mi taller",
                  "Me sirvió muchísimo, lo voy a aplicar",
                  "Totalmente de acuerdo con esto"):
            self.assertTrue(ic.comentario_es_real(t), f"no contó: {t!r}")

    def test_clasificar_reparte_las_dos_cuentas(self) -> None:
        reales, emoji = ic.clasificar_comentarios(
            ["🔥", "Me pasó igual con mi local el año pasado", "❤️", "si"])
        self.assertEqual((reales, emoji), (1, 3))


# ----------------------------------------------------- 4. aplanar la respuesta de Meta

class TestRespuestaDeMeta(unittest.TestCase):
    def test_aplana_el_formato_values(self) -> None:
        resp = {"data": [{"name": "reach", "values": [{"value": 1200}]},
                         {"name": "saved", "values": [{"value": 34}]}]}
        self.assertEqual(ic._valores(resp), {"reach": 1200, "saved": 34})

    def test_aplana_el_formato_total_value(self) -> None:
        """Meta devuelve `total_value` en vez de `values` según la métrica y la versión."""
        resp = {"data": [{"name": "shares", "total_value": {"value": 9}}]}
        self.assertEqual(ic._valores(resp), {"shares": 9})

    def test_una_metrica_sin_numero_no_entra_como_cero(self) -> None:
        resp = {"data": [{"name": "reach", "values": [{}]}]}
        self.assertEqual(ic._valores(resp), {})


# ----------------------------------------------------- 5. el recolector completo, sin red

class TestRecolector(BaseInsights):
    def test_captura_y_guarda_sin_tocar_la_red(self) -> None:
        pid = self.reel_publicado(horas=30, media="MEDIA7")
        with mock.patch.object(ic.ig_publisher, "cargar_config_ig",
                               return_value={"IG_ACCESS_TOKEN": "T", "IG_USER_ID": "U"}), \
             mock.patch.object(ic.ig_publisher, "_url_base_graph", return_value="https://x"), \
             mock.patch.object(ic, "insights_de_media",
                               return_value={"reach": 800, "saved": 30, "shares": 12,
                                             "likes": 40, "ig_reels_avg_watch_time": 9000}), \
             mock.patch.object(ic, "comentarios_de_media", return_value=(3, 7, "")), \
             mock.patch.object(ic, "insights_de_cuenta",
                               return_value={"profile_views": 55, "reach": 2000,
                                             "followers_count": 310}), \
             mock.patch.object(ic, "duracion_de", return_value=18.0):
            res = ic.capturar()
        self.assertTrue(res["ok"])
        m = database.metricas_de(pid, "24h")
        self.assertEqual((m["alcance"], m["guardados"], m["compartidos"]), (800, 30, 12))
        self.assertEqual((m["comentarios_reales"], m["comentarios_emoji"]), (3, 7))
        self.assertEqual(m["retencion_pct"], 50.0)
        self.assertEqual(database.metricas_cuenta()[0]["visitas_perfil"], 55)

    def test_dry_run_no_escribe(self) -> None:
        pid = self.reel_publicado(horas=30)
        with mock.patch.object(ic.ig_publisher, "cargar_config_ig",
                               return_value={"IG_ACCESS_TOKEN": "T", "IG_USER_ID": ""}), \
             mock.patch.object(ic.ig_publisher, "_url_base_graph", return_value="https://x"), \
             mock.patch.object(ic, "insights_de_media", return_value={"reach": 10}), \
             mock.patch.object(ic, "comentarios_de_media", return_value=(0, 0, "")), \
             mock.patch.object(ic, "duracion_de", return_value=0.0):
            res = ic.capturar(dry_run=True)
        self.assertEqual(len(res["capturadas"]), 1)
        self.assertEqual(database.metricas_de(pid), [])

    def test_sin_token_no_sale_a_la_red(self) -> None:
        with mock.patch.object(ic.ig_publisher, "cargar_config_ig", return_value={}):
            res = ic.capturar()
        self.assertFalse(res["ok"])
        self.assertIn("IG_ACCESS_TOKEN", res["motivo"])

    def test_un_fallo_de_meta_en_una_pieza_no_tumba_el_resto(self) -> None:
        malo = self.reel_publicado(horas=30, media="MALO")
        bueno = self.reel_publicado(horas=30, media="BUENO")

        def por_media(media_id, base, token):
            if media_id == "MALO":
                raise ic.ig_publisher.ErrorIG("Meta HTTP 400: metrica rara")
            return {"reach": 500, "saved": 25}

        with mock.patch.object(ic.ig_publisher, "cargar_config_ig",
                               return_value={"IG_ACCESS_TOKEN": "T", "IG_USER_ID": ""}), \
             mock.patch.object(ic.ig_publisher, "_url_base_graph", return_value="https://x"), \
             mock.patch.object(ic, "insights_de_media", side_effect=por_media), \
             mock.patch.object(ic, "comentarios_de_media", return_value=(0, 0, "")), \
             mock.patch.object(ic, "duracion_de", return_value=0.0):
            res = ic.capturar()
        self.assertEqual([f["pieza"] for f in res["fallos"]], [malo])
        self.assertEqual(database.metricas_de(bueno, "24h")["alcance"], 500)
        self.assertIsNone(database.metricas_de(malo, "24h"))

    def test_sin_permiso_de_comentarios_avisa_y_no_inventa(self) -> None:
        """Si el token no trae `instagram_manage_comments`, los comentarios quedan en cero y se avisa."""
        pid = self.reel_publicado(horas=30)
        with mock.patch.object(ic.ig_publisher, "cargar_config_ig",
                               return_value={"IG_ACCESS_TOKEN": "T", "IG_USER_ID": ""}), \
             mock.patch.object(ic.ig_publisher, "_url_base_graph", return_value="https://x"), \
             mock.patch.object(ic, "insights_de_media", return_value={"reach": 100}), \
             mock.patch.object(ic, "comentarios_de_media",
                               return_value=(0, 0, "comentarios no leídos (sin permiso)")), \
             mock.patch.object(ic, "duracion_de", return_value=0.0):
            res = ic.capturar()
        self.assertTrue(any("comentarios no leídos" in a for a in res["avisos"]))
        self.assertEqual(database.metricas_de(pid, "24h")["comentarios_reales"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

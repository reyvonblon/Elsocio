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
import renovar_token_ig as rt  # noqa: E402

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


# ----------------------------------------------------- 6. renovar el token de Meta

class TestRenovarToken(BaseInsights):
    """La cadena corto -> largo -> pagina, y la regla de no guardar nada sin confirmar."""

    CFG = {"IG_APP_ID": "APP", "IG_APP_SECRET": "SECRETO", "IG_USER_ID": "17841400000000000"}

    def test_sin_app_id_no_sale_a_la_red(self) -> None:
        with mock.patch.object(rt.ig_publisher, "cargar_config_ig", return_value={}):
            res = rt.renovar("EAAcorto")
        self.assertFalse(res["ok"])
        self.assertIn("IG_APP_ID", res["error"])

    def test_un_token_de_instagram_login_se_rechaza_con_la_razon(self) -> None:
        with mock.patch.object(rt.ig_publisher, "cargar_config_ig", return_value=self.CFG):
            res = rt.renovar("IGAAsomething")
        self.assertFalse(res["ok"])
        self.assertIn("Instagram Login", res["error"])

    def test_un_token_corto_ya_vencido_se_detecta_antes_de_intercambiar(self) -> None:
        with mock.patch.object(rt.ig_publisher, "cargar_config_ig", return_value=self.CFG), \
             mock.patch.object(rt, "_vencimiento",
                               return_value={"valido": False, "vence_en": "ayer", "dias": -1,
                                             "tipo": "USER", "permisos": []}), \
             mock.patch.object(rt, "intercambiar_por_largo") as inter:
            res = rt.renovar("EAAcorto")
        self.assertFalse(res["ok"])
        self.assertEqual(res["paso"], 1)
        inter.assert_not_called()

    def test_la_pagina_se_escoge_por_id_de_instagram_no_por_nombre(self) -> None:
        respuesta = {"data": [
            {"id": "1", "name": "Otra marca", "access_token": "TOK_OTRA",
             "instagram_business_account": {"id": "999", "username": "otra"}},
            {"id": "2", "name": "El Socio", "access_token": "TOK_BUENO",
             "instagram_business_account": {"id": "17841400000000000", "username": "elsociotuia"}},
        ]}
        with mock.patch.object(rt.ig_publisher, "_graph_get", return_value=respuesta):
            token, info = rt.token_de_pagina("LARGO", "17841400000000000")
        self.assertEqual(token, "TOK_BUENO")
        self.assertEqual(info["ig_username"], "elsociotuia")

    def test_si_ninguna_pagina_tiene_esa_cuenta_lo_dice_con_lo_que_vio(self) -> None:
        respuesta = {"data": [{"id": "1", "name": "Otra", "access_token": "T",
                               "instagram_business_account": {"id": "999"}}]}
        with mock.patch.object(rt.ig_publisher, "_graph_get", return_value=respuesta):
            with self.assertRaises(rt.ig_publisher.ErrorIG) as ctx:
                rt.token_de_pagina("LARGO", "17841400000000000")
        self.assertIn("999", str(ctx.exception))

    def test_cadena_completa_guarda_el_token_de_pagina(self) -> None:
        with mock.patch.object(rt.ig_publisher, "cargar_config_ig", return_value=self.CFG), \
             mock.patch.object(rt, "_vencimiento",
                               side_effect=[
                                   {"valido": True, "vence_en": "en 1 h", "dias": 0.05,
                                    "tipo": "USER", "permisos": ["instagram_basic"]},
                                   {"valido": True, "vence_en": "en 60 d", "dias": 60.0,
                                    "tipo": "USER", "permisos": []},
                                   {"valido": True, "vence_en": "nunca", "dias": None,
                                    "tipo": "PAGE", "permisos": []},
                               ]), \
             mock.patch.object(rt, "intercambiar_por_largo", return_value="LARGO"), \
             mock.patch.object(rt, "token_de_pagina",
                               return_value=("TOK_PAGINA", {"pagina": "El Socio"})), \
             mock.patch.object(rt.ig_publisher, "verificar_acceso_ig",
                               return_value={"puede_publicar": True}):
            res = rt.renovar("EAAcorto")
        self.assertTrue(res["ok"])
        self.assertEqual(res["vence_en"], "nunca")
        self.assertEqual(database.get_settings()["ig_access_token"], "TOK_PAGINA")
        self.assertEqual(database.get_settings()["ig_token_tipo"], "pagina")

    def test_si_meta_no_confirma_no_se_guarda_nada(self) -> None:
        """Misma regla que el resto del motor: token sin confirmar no entra."""
        with mock.patch.object(rt.ig_publisher, "cargar_config_ig", return_value=self.CFG), \
             mock.patch.object(rt, "_vencimiento",
                               return_value={"valido": True, "vence_en": "x", "dias": 1,
                                             "tipo": "USER", "permisos": []}), \
             mock.patch.object(rt, "intercambiar_por_largo", return_value="LARGO"), \
             mock.patch.object(rt, "token_de_pagina", return_value=("TOK", {})), \
             mock.patch.object(rt.ig_publisher, "verificar_acceso_ig",
                               return_value={"puede_publicar": False, "motivo": "restringido"}):
            res = rt.renovar("EAAcorto")
        self.assertFalse(res["ok"])
        self.assertNotIn("ig_access_token", database.get_settings())

    def test_dry_run_verifica_pero_no_guarda(self) -> None:
        with mock.patch.object(rt.ig_publisher, "cargar_config_ig", return_value=self.CFG), \
             mock.patch.object(rt, "_vencimiento",
                               return_value={"valido": True, "vence_en": "nunca", "dias": None,
                                             "tipo": "PAGE", "permisos": []}), \
             mock.patch.object(rt, "intercambiar_por_largo", return_value="LARGO"), \
             mock.patch.object(rt, "token_de_pagina", return_value=("TOK", {})), \
             mock.patch.object(rt.ig_publisher, "verificar_acceso_ig",
                               return_value={"puede_publicar": True}):
            res = rt.renovar("EAAcorto", dry_run=True)
        self.assertTrue(res["ok"])
        self.assertFalse(res["guardado"])
        self.assertNotIn("ig_access_token", database.get_settings())

    def test_el_token_nunca_se_imprime_completo(self) -> None:
        pista = rt._pista("EAAbcdefghijklmnop")
        self.assertNotIn("bcdefghijklmnop", pista)
        self.assertTrue(pista.startswith("EAAb"))


# ----------------------------------------------------- 7. el vigilante del token

class TestVigilanteToken(BaseInsights):
    """Nunca más enterarse por casualidad de que el token murió."""

    CFG = {"IG_ACCESS_TOKEN": "EAGtoken", "IG_APP_ID": "APP", "IG_APP_SECRET": "S",
           "IG_USER_ID": "178414"}

    def test_token_muerto_suena_el_celular(self) -> None:
        with mock.patch.object(rt, "estado_token",
                               return_value={"hay_token": True, "valido": False,
                                             "motivo": "code 190"}), \
             mock.patch.object(rt.notificar, "notificar_fallo") as aviso:
            res = rt.vigilar_token(self.CFG)
        self.assertFalse(res["ok"])
        aviso.assert_called_once()
        self.assertIn("no sirve", aviso.call_args[0][0])
        self.assertEqual(database.get_settings()["ig_token_estado"], "invalido")

    def test_token_de_pagina_no_hace_nada_y_lo_deja_anotado(self) -> None:
        with mock.patch.object(rt, "estado_token",
                               return_value={"hay_token": True, "valido": True,
                                             "vence_en": "nunca", "dias": None}), \
             mock.patch.object(rt.notificar, "notificar_fallo") as aviso:
            res = rt.vigilar_token(self.CFG)
        self.assertTrue(res["ok"])
        self.assertEqual(res["accion"], "ninguna")
        aviso.assert_not_called()
        self.assertEqual(database.get_settings()["ig_token_estado"], "no_vence")

    def test_token_con_meses_por_delante_no_se_toca(self) -> None:
        with mock.patch.object(rt, "estado_token",
                               return_value={"hay_token": True, "valido": True,
                                             "vence_en": "2027-01-25", "dias": 45.0}), \
             mock.patch.object(rt, "token_de_pagina") as cambio:
            res = rt.vigilar_token(self.CFG)
        self.assertEqual(res["accion"], "ninguna")
        cambio.assert_not_called()
        self.assertEqual(database.get_settings()["ig_token_estado"], "vigente")

    def test_token_por_vencer_se_cambia_solo_por_uno_de_pagina(self) -> None:
        """La única ventana para arreglarlo sin intervención es mientras todavía sirve."""
        with mock.patch.object(rt, "estado_token",
                               return_value={"hay_token": True, "valido": True,
                                             "vence_en": "pronto", "dias": 4.0}), \
             mock.patch.object(rt, "token_de_pagina",
                               return_value=("TOK_PAGINA", {"pagina": "El Socio"})), \
             mock.patch.object(rt.ig_publisher, "verificar_acceso_ig",
                               return_value={"puede_publicar": True}):
            res = rt.vigilar_token(self.CFG)
        self.assertTrue(res["ok"])
        self.assertEqual(res["accion"], "cambiado_a_token_de_pagina")
        self.assertEqual(database.get_settings()["ig_access_token"], "TOK_PAGINA")
        self.assertEqual(database.get_settings()["ig_token_estado"], "no_vence")

    def test_si_el_cambio_automatico_falla_avisa_antes_de_que_venza(self) -> None:
        with mock.patch.object(rt, "estado_token",
                               return_value={"hay_token": True, "valido": True,
                                             "vence_en": "pronto", "dias": 3.0}), \
             mock.patch.object(rt, "token_de_pagina",
                               side_effect=rt.ig_publisher.ErrorIG("sin pages_show_list")), \
             mock.patch.object(rt.notificar, "notificar_fallo") as aviso:
            res = rt.vigilar_token(self.CFG)
        self.assertFalse(res["ok"])
        aviso.assert_called_once()
        self.assertIn("3", aviso.call_args[0][0])
        self.assertEqual(database.get_settings()["ig_token_estado"], "por_vencer")

    def test_sin_credenciales_de_app_al_menos_dice_si_sirve(self) -> None:
        with mock.patch.object(rt.ig_publisher, "verificar_acceso_ig",
                               return_value={"puede_publicar": True}):
            est = rt.estado_token({"IG_ACCESS_TOKEN": "EAG"})
        self.assertTrue(est["valido"])
        self.assertEqual(est["vence_en"], "desconocido")

    def test_sin_token_no_sale_a_la_red(self) -> None:
        est = rt.estado_token({})
        self.assertFalse(est["hay_token"])
        self.assertFalse(est["valido"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

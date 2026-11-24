#!/usr/bin/env python3
"""Batería en seco del Cerebro Autónomo Completo: voz humana, contenido, IG oficial y panel.

Cero red real, cero gasto de API y cero cambios en `data/el_socio.db` ni en
`contexto/RESULTADOS_MERCADO.md` (verificados con huella SHA-256 en cada prueba).
"""

from __future__ import annotations

import email
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import autopilot_dispatcher  # noqa: E402
import content_brain  # noqa: E402
import content_manager  # noqa: E402
import database  # noqa: E402
import ig_publisher  # noqa: E402
import instalar_piloto  # noqa: E402
import panel_mensajes  # noqa: E402
import panel_server  # noqa: E402
import prospect_hunter  # noqa: E402
import sales_agent  # noqa: E402
import socio_cerebro  # noqa: E402
import voice_engine  # noqa: E402

DB_REAL = PROJECT_ROOT / "data" / "el_socio.db"
RESULTADOS_REAL = PROJECT_ROOT / "contexto" / "RESULTADOS_MERCADO.md"

CABECERA_RESULTADOS = (
    "# Resultados de mercado\n\n## Registro\n"
    "<!-- filas al FINAL. Nada debajo de la tabla. -->\n"
    "| Fecha | Nicho | Ángulo usado | Canal | Cantidad | Resultado | Nota |\n"
    "|---|---|---|---|---|---|---|\n"
    "| 2026-01-01 | fila-base | prueba | correo | 2 | silencio | Intocable. |\n"
)


def huella(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest() if ruta.exists() else "(no existe)"


class BaseAutonoma(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self.tmp.name)
        self.db = self.tmp_dir / "test.db"
        self.resultados = self.tmp_dir / "RESULTADOS_MERCADO.md"
        self.resultados.write_text(CABECERA_RESULTADOS, encoding="utf-8")

        self.p_db = mock.patch.object(database, "DB_PATH", self.db)
        self.p_res1 = mock.patch.object(autopilot_dispatcher, "RESULTADOS_FILE", self.resultados)
        self.p_res2 = mock.patch.object(content_brain, "RESULTADOS_FILE", self.resultados)
        self.p_run_cm = mock.patch.object(
            content_manager.subprocess, "run",
            return_value=mock.Mock(returncode=0, stdout="ok", stderr=""),
        )
        self.p_db.start()
        self.p_res1.start()
        self.p_res2.start()
        self.mock_render = self.p_run_cm.start()
        database.init_db()

        self.addCleanup(self._verificar_reales_intactos, huella(DB_REAL), huella(RESULTADOS_REAL))
        self.addCleanup(self.p_run_cm.stop)
        self.addCleanup(self.p_res2.stop)
        self.addCleanup(self.p_res1.stop)
        self.addCleanup(self.p_db.stop)
        self.addCleanup(self.tmp.cleanup)

    def _verificar_reales_intactos(self, db_antes: str, md_antes: str) -> None:
        self.assertEqual(huella(DB_REAL), db_antes, "se modificó data/el_socio.db")
        self.assertEqual(huella(RESULTADOS_REAL), md_antes, "se modificó RESULTADOS_MERCADO.md")


# ----------------------------------------- 1. Nichos sin precios y Landing

class TestNichoSinPreciosYLanding(unittest.TestCase):
    def test_recorta_precios_de_todos_los_nichos_reales(self) -> None:
        esperados = {
            "automatizacion-agencias-estudios",
            "ecommerce-catalogo-visual",
            "fichas-tecnicas-ropa",
            "modelado-3d-espacios",
        }
        archivos = [p.stem for p in sorted(sales_agent.NICHOS_DIR.glob("*.md")) if not p.name.startswith("_")]
        self.assertTrue(esperados.issubset(set(archivos)), f"faltan nichos: {archivos}")
        for slug in archivos:
            with self.subTest(slug=slug):
                limpio = sales_agent.cargar_contexto_nicho_sin_precios(slug)
                self.assertTrue(limpio, "quedó vacío")
                self.assertIn("Dolor", limpio)
                self.assertNotIn("Precio de referencia", limpio)
                self.assertNotIn("Queries", limpio)
                self.assertEqual(sales_agent.revisar_guarda_precios(limpio), [],
                                 f"se coló un precio en {slug}: {limpio}")
        consolidado = sales_agent.cargar_todos_los_nichos_sin_precios()
        self.assertTrue(consolidado)
        self.assertEqual(sales_agent.revisar_guarda_precios(consolidado), [])

    def test_prospect_hunter_intercala_nichos_cubre_4_ciudades_y_filtra_ruido(self) -> None:
        queries = prospect_hunter.load_nicho_queries()
        self.assertGreaterEqual(len(queries), 40)
        # Primeras 4 queries deben venir de 4 nichos distintos (round-robin real).
        primeros_4_nichos = {nicho for _, _, nicho in queries[:4]}
        self.assertEqual(len(primeros_4_nichos), 4, queries[:4])
        texto_total = " ".join(q for q, _, _ in queries)
        for ciudad in ("Medellin", "Bogota", "Cali", "Barranquilla"):
            self.assertIn(ciudad, texto_total)

        self.assertTrue(prospect_hunter._is_blocked_domain("unidadeditorial.es"))
        self.assertTrue(prospect_hunter._is_blocked_domain("alcaldia.gov.co"))
        self.assertTrue(prospect_hunter._is_blocked_domain("unal.edu.co"))
        self.assertFalse(prospect_hunter._is_blocked_domain("estudiocreativo.com.co"))

        cands = prospect_hunter._clean_email_candidates(
            "mailto:gestionhumana@marca.com.co info@marca.com.co attcliente@unidadeditorial.es",
            "marca.com.co",
        )
        self.assertEqual(cands, ["info@marca.com.co"])

        antes_db = huella(DB_REAL)
        with mock.patch.object(prospect_hunter, "search_duckduckgo_urls", return_value=["https://marca1.com.co/"]), \
             mock.patch.object(prospect_hunter, "scrape_site_contact", return_value={
                 "nombre": "Equipo Marca", "empresa": "Marca", "correo": "hola@marca1.com.co",
                 "whatsapp": "", "nicho": "ecommerce-catalogo-visual",
                 "industria": "E-commerce", "servicio": "E-commerce",
             }):
            res = prospect_hunter.discover_new_prospects(needed=1, max_queries=2, dry_run=True)
        self.assertEqual(len(res), 1)
        self.assertEqual(huella(DB_REAL), antes_db)

    def test_bloquea_path_traversal_en_nicho(self) -> None:
        self.assertEqual(sales_agent.cargar_contexto_nicho_sin_precios("../../.env"), "")
        self.assertEqual(sales_agent.cargar_contexto_nicho_sin_precios("_plantilla"), "")

    def test_system_prompt_carga_skills_de_calidad(self) -> None:
        prompt = sales_agent.construir_system_prompt()
        self.assertIn("Humanizer", prompt)
        self.assertIn("Psicología y estatus", prompt)
        self.assertIn("Editor implacable", prompt)

    def test_extraer_campos_landing_conserva_telefono_y_correo(self) -> None:
        raw = (
            "From: Web3Forms <notify@web3forms.com>\r\n"
            "Subject: Nuevo mensaje — landing El Socio\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n\r\n"
            "telefono: +57 300 555 8899\r\n"
            "email: cliente@marca.co\r\n"
            "mensaje: Necesito fichas técnicas urgentes para mi colección.\r\n"
        ).encode("utf-8")
        msg = email.message_from_bytes(raw)
        campos = autopilot_dispatcher.extraer_campos_landing(msg, correo_propio="elsociotuia@gmail.com")
        self.assertEqual(campos["telefono"], "+57 300 555 8899")
        self.assertEqual(campos["correo"], "cliente@marca.co")
        self.assertIn("WhatsApp: +57 300 555 8899", campos["resumen"])
        self.assertIn("fichas técnicas", campos["resumen"])


# ----------------------------------------- 2. Motor de Voz Humana Sincronizada

class TestVozHumanaSincronizada(unittest.TestCase):
    def test_limpiar_para_locucion_quita_punto_medio_y_urls(self) -> None:
        limpio = voice_engine.limpiar_para_locucion(
            "Cuéntanos tu problema · link en bio https://reyvonblon.github.io/Elsocio/"
        )
        self.assertNotIn("·", limpio)
        self.assertNotIn("https://", limpio)
        self.assertEqual(limpio, "Cuéntanos tu problema. link en bio.")

    def test_sec_ms_gec_v2_tiene_formato_criptografico_valido(self) -> None:
        tok = voice_engine.generar_sec_ms_gec(1700000100.0)
        partes = tok.split("-")
        self.assertEqual(len(partes), 2)
        self.assertEqual(len(partes[0]), 16)
        self.assertEqual(len(partes[1]), 64)
        self.assertEqual(tok, voice_engine.generar_sec_ms_gec(1700000150.0),
                         "dentro de la misma ventana de 5 min el token debe ser estable")

    def test_timeline_sincroniza_cada_bloque_sin_cortar_frases_largas(self) -> None:
        # Gancho largo de 3.4s + 2 bloques + cierre de 2.2s
        tl = voice_engine.calcular_timeline_reel([3.4, 1.2, 2.5, 2.2], n_bloques=2)
        t_bloques = tl["tiemposBloques"]
        t_cierre = tl["tiempoCierre"]
        self.assertEqual(len(t_bloques), 2)
        self.assertGreater(t_bloques[0], 3.5, "el bloque 1 pisó al gancho largo")
        self.assertGreater(t_bloques[1], t_bloques[0] + 1.8)
        self.assertGreater(t_cierre, t_bloques[1] + 2.5, "el cierre pisó al bloque 2")
        self.assertGreaterEqual(tl["duracion_total_seg"], t_cierre + 2.2 + 0.5)

    def test_voz_bloquea_precios_antes_de_llamar_a_red(self) -> None:
        props = {
            "gancho": "Te cobro 80000 pesos por el render",
            "bloques": ["Uno", "Dos"],
            "cierre": "Escríbeme",
        }
        with self.assertRaises(voice_engine.GuardaVozBloqueada):
            voice_engine.narrar_reel(props, Path("/tmp/no_se_crea.m4a"), dry_run=True)

    def test_narrar_reel_dry_run_devuelve_props_sincronizados_sin_red(self) -> None:
        props = {
            "gancho": "El taller te entregó algo distinto a lo que pediste.",
            "bloques": ["Otra vez.", "No fue mala suerte.", "Fue la ficha técnica."],
            "cierre": "Cuéntanos tu problema · link en bio",
            "escena": "contraste",
        }
        res = voice_engine.narrar_reel(props, Path("/tmp/no_se_crea.m4a"), dry_run=True)
        self.assertTrue(res["ok"])
        self.assertTrue(res["dry_run"])
        self.assertEqual(len(res["props"]["tiemposBloques"]), 3)
        self.assertGreater(res["props"]["duracionFrames"], 180)

    def test_seleccion_automatica_de_proveedor_humano(self) -> None:
        self.assertEqual(voice_engine.elegir_proveedor({}), "edge_neural")
        self.assertEqual(voice_engine.elegir_proveedor({"OPENAI_API_KEY": "sk-x"}), "openai")
        self.assertEqual(voice_engine.elegir_proveedor(
            {"OPENAI_API_KEY": "sk-x", "ELEVENLABS_API_KEY": "el-x"}), "elevenlabs")


# ----------------------------------------- 3. Cerebro Autónomo de Contenido

class TestCerebroContenido(BaseAutonoma):
    CFG = {
        "ANTHROPIC_API_KEY": "clave-falsa",
        "SALES_AGENT_MODEL": "claude-sonnet-5",
        "SALES_AGENT_MAX_DAILY_USD": "0.50",
        "CONTENT_MAX_DAILY_PIECES": "1",
    }

    def _respuesta_pieza(self, **campos) -> dict:
        base = {
            "tipo": "video",
            "nicho": "fichas-tecnicas-ropa",
            "gancho": "El patronista adivinó las medidas de tu colección.",
            "bloques": ["No fue culpa del taller.", "Faltaba el plano técnico.", "Así se evita el reproceso."],
            "cierre": "Cuéntanos tu problema · link en bio",
            "caption": "Mandar a confeccionar sin ficha clara sale caro en tela y tiempo.\nCuéntanos qué vas a producir en el link de la bio.",
            "escena": "contraste",
            "etiquetas": ["SIN FICHA", "RESUELTO"],
        }
        base.update(campos)
        return {
            "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": "tu_c1", "name": "proponer_pieza", "input": base}],
            "usage": {"input_tokens": 1000, "output_tokens": 200},
        }

    def test_vender_va_primero_no_llama_api_si_tope_usd_lleno(self) -> None:
        database.log_agent_action(
            lead_id=1, turno=1, modelo="claude-sonnet-5",
            herramienta="llamada_api", costo_usd=0.50,
        )
        with mock.patch.object(sales_agent, "llamar_api",
                               side_effect=AssertionError("gastó sobre el tope")) as api:
            res = content_brain.CerebroContenido(dict(self.CFG)).crear_pieza_del_dia()
        self.assertFalse(res["ok"])
        self.assertIn("Vender va primero", res["motivo"])
        self.assertEqual(api.call_count, 0)

    def test_respeta_cuota_diaria_de_piezas_antes_de_la_api(self) -> None:
        content_manager.encolar(tipo="post", gancho="Ya había una pieza hoy.")
        with mock.patch.object(sales_agent, "llamar_api",
                               side_effect=AssertionError("excedió cuota diaria")) as api:
            res = content_brain.CerebroContenido(dict(self.CFG)).crear_pieza_del_dia()
        self.assertFalse(res["ok"])
        self.assertIn("Cuota diaria", res["motivo"])
        self.assertEqual(api.call_count, 0)

    def test_autocorrige_si_el_modelo_cuela_un_precio_y_suma_al_tope_compartido(self) -> None:
        con_precio = self._respuesta_pieza(gancho="Ahorra 50000 pesos en tu taller")
        limpia = self._respuesta_pieza()
        with mock.patch.object(sales_agent, "llamar_api", side_effect=[con_precio, limpia]) as api:
            res = content_brain.CerebroContenido(dict(self.CFG)).crear_pieza_del_dia(renderizar=True)
        self.assertTrue(res["ok"], res)
        self.assertTrue(res["creada"])
        self.assertEqual(api.call_count, 2)
        self.assertGreater(database.agent_cost_today_usd(), 0.0)
        pieza = database.get_content(int(res["id"]))
        self.assertEqual(pieza["estado"], "generado")

    def test_rechaza_ganchos_repetidos(self) -> None:
        repetido = "El patronista adivinó las medidas de tu colección."
        content_manager.encolar(tipo="post", gancho=repetido)
        # Subimos cuota a 2 para probar filtro anti-repetición.
        cfg = dict(self.CFG, CONTENT_MAX_DAILY_PIECES="2")
        r1 = self._respuesta_pieza(gancho=repetido)
        r2 = self._respuesta_pieza(gancho="Construir tu local sin render es firmar a ciegas.")
        with mock.patch.object(sales_agent, "llamar_api", side_effect=[r1, r2]):
            res = content_brain.CerebroContenido(cfg).crear_pieza_del_dia(renderizar=False)
        self.assertTrue(res["creada"], res)
        self.assertIn("Construir tu local", res["gancho"])


# ----------------------------------------- 4. Publicador Oficial Instagram Graph API

class TestInstagramGraphOficial(BaseAutonoma):
    CFG_IG = {
        "IG_USER_ID": "17841400000000000",
        "IG_ACCESS_TOKEN": "IGAAsecretoDePruebaNoImprimir",
        "IG_AUTO_PUBLISH": "1",
        "IG_MAX_DAILY_POSTS": "1",
    }

    def _pieza_generada(self, tipo: str = "video") -> tuple[int, Path]:
        ext = ".mp4" if tipo == "video" else ".png"
        archivo = self.tmp_dir / f"pieza{ext}"
        archivo.write_bytes(b"contenido-multimedia-falso")
        cid = content_manager.encolar(
            tipo=tipo,
            gancho="Construir sin ver el espacio antes sale caro.",
            guion="Tu idea en mente\nEl plano real",
            caption="Míralo resuelto antes de mover un ladrillo.",
            nicho="modelado-3d-espacios",
        )["id"]
        database.update_content(cid, estado="generado", archivo=str(archivo))
        return cid, archivo

    def test_elige_host_oficial_segun_prefijo_de_token(self) -> None:
        self.assertIn("graph.instagram.com", ig_publisher._url_base_graph({"IG_ACCESS_TOKEN": "IGAA123"}))
        self.assertIn("graph.facebook.com", ig_publisher._url_base_graph({"IG_ACCESS_TOKEN": "EAAB123"}))

    def test_flujo_completo_reel_oficial_con_polling_finished(self) -> None:
        cid, _ = self._pieza_generada("video")
        with mock.patch.object(ig_publisher, "obtener_url_publica_https",
                               return_value="https://files.ejemplo.com/pieza.mp4"), \
             mock.patch.object(ig_publisher, "_graph_post",
                               side_effect=[{"id": "cont_99"}, {"id": "ig_live_777"}]) as m_post, \
             mock.patch.object(ig_publisher, "_graph_get",
                               side_effect=[{"status_code": "IN_PROGRESS"}, {"status_code": "FINISHED"}]), \
             mock.patch.object(ig_publisher.time, "sleep"):
            res = ig_publisher.publicar_pieza_ig(cid, cfg=dict(self.CFG_IG))

        self.assertTrue(res["publicado"], res)
        self.assertEqual(res["ig_media_id"], "ig_live_777")
        self.assertEqual(m_post.call_args_list[0].args[1]["media_type"], "REELS")
        pieza = database.get_content(cid)
        self.assertEqual(pieza["estado"], "publicado")
        self.assertEqual(pieza["ig_media_id"], "ig_live_777")
        self.assertEqual(database.ig_published_today(), 1)

    def test_post_png_se_convierte_a_jpeg_antes_de_meta(self) -> None:
        cid, png = self._pieza_generada("post")

        def simular_sips(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b"\xff\xd8\xff\xe0jpeg")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(ig_publisher.subprocess, "run", side_effect=simular_sips) as m_sips, \
             mock.patch.object(ig_publisher, "obtener_url_publica_https",
                               return_value="https://files.ejemplo.com/pieza.jpg") as m_up, \
             mock.patch.object(ig_publisher, "_graph_post",
                               side_effect=[{"id": "cont_img"}, {"id": "ig_img_1"}]), \
             mock.patch.object(ig_publisher, "_graph_get",
                               return_value={"status_code": "FINISHED"}):
            res = ig_publisher.publicar_pieza_ig(cid, cfg=dict(self.CFG_IG))

        self.assertTrue(res["publicado"], res)
        self.assertEqual(m_sips.call_count, 1)
        self.assertEqual(m_up.call_args.args[0].suffix, ".jpg")
        self.assertTrue(png.exists(), "no debe borrar el PNG local del panel")

    def test_rollback_limpio_si_meta_falla_y_oculta_el_token(self) -> None:
        cid, _ = self._pieza_generada("video")
        antes_md = huella(self.resultados)
        secreto = self.CFG_IG["IG_ACCESS_TOKEN"]
        with mock.patch.object(ig_publisher, "obtener_url_publica_https",
                               return_value="https://files.ejemplo.com/pieza.mp4"), \
             mock.patch.object(
                 ig_publisher, "_graph_post",
                 side_effect=ig_publisher.ErrorIG(
                     ig_publisher._sanitizar_error_meta(f"fallo con {secreto}", secreto)
                 ),
             ):
            res = ig_publisher.publicar_pieza_ig(cid, cfg=dict(self.CFG_IG))

        self.assertFalse(res["publicado"])
        pieza = database.get_content(cid)
        self.assertEqual(pieza["estado"], "generado", "marcó publicado pese al fallo de Meta")
        self.assertNotIn(secreto, pieza["error_ig"], "filtró el token en la BD")
        self.assertIn("[REDACTED]", pieza["error_ig"])
        self.assertEqual(huella(self.resultados), antes_md, "escribió en RESULTADOS tras fallar")

    def test_tope_diario_e_interruptor_preview_frenan_publicacion(self) -> None:
        cid, _ = self._pieza_generada("video")
        # 1) Modo Preview (0) no publica solo
        ig_publisher.cambiar_modo_autonomo(False)
        r_prev = ig_publisher.ciclo_publicacion_autonoma(cfg=dict(self.CFG_IG))
        self.assertFalse(r_prev["ejecutado"])
        self.assertEqual(r_prev["razon"], "modo_preview_esperando_aprobacion")

        # 2) Modo Autónomo (1) pero tope lleno tampoco publica
        ig_publisher.cambiar_modo_autonomo(True)
        otra, _ = self._pieza_generada("video")
        database.update_content(otra, estado="publicado", ig_media_id="ya_salio")
        r_tope = ig_publisher.ciclo_publicacion_autonoma(cfg=dict(self.CFG_IG))
        self.assertFalse(r_tope["ejecutado"])
        self.assertEqual(r_tope["razon"], "tope_diario_ig_alcanzado")
        self.assertEqual(database.get_content(cid)["estado"], "generado")

    def test_sincronizar_resultados_ig_escribe_comentarios_reales_y_silencio_vencido(self) -> None:
        c1, _ = self._pieza_generada("video")
        database.update_content(c1, estado="publicado", ig_media_id="ig_con_comentarios")
        c2, _ = self._pieza_generada("post")
        database.update_content(c2, estado="publicado", ig_media_id="ig_viejo_mudo")
        hace_10_dias = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE content_queue SET published_at=? WHERE id=?", (hace_10_dias, c2))

        def fake_get(url, params, token):
            if "ig_con_comentarios" in url:
                return {"comments_count": 3, "like_count": 14}
            return {"comments_count": 0, "like_count": 2}

        with mock.patch.object(ig_publisher, "_graph_get", side_effect=fake_get):
            res = ig_publisher.sincronizar_resultados_ig(
                cfg=dict(self.CFG_IG), ruta_resultados=self.resultados,
            )
            # Segunda corrida no duplica nada
            res2 = ig_publisher.sincronizar_resultados_ig(
                cfg=dict(self.CFG_IG), ruta_resultados=self.resultados,
            )

        self.assertEqual(res["registradas"], 2)
        self.assertEqual(res2["registradas"], 0)
        texto_md = self.resultados.read_text(encoding="utf-8")
        self.assertIn("| instagram | 3 | respondió |", texto_md)
        self.assertIn("| instagram | 1 | silencio |", texto_md)

    def test_autodescubre_user_id_solo_con_el_token(self) -> None:
        cid, _ = self._pieza_generada("video")
        cfg_solo_token = {
            "IG_USER_ID": "",
            "IG_ACCESS_TOKEN": "IGAAtokenSoloSinId",
            "IG_AUTO_PUBLISH": "1",
            "IG_MAX_DAILY_POSTS": "1",
        }
        with mock.patch.object(ig_publisher, "obtener_url_publica_https",
                               return_value="https://files.ejemplo.com/pieza.mp4"), \
             mock.patch.object(
                 ig_publisher, "_graph_get",
                 side_effect=[
                     {"user_id": "1784999888", "username": "elsocio.ia"},
                     {"status_code": "FINISHED"},
                 ],
             ), \
             mock.patch.object(ig_publisher, "_graph_post",
                               side_effect=[{"id": "c_auto"}, {"id": "ig_auto_ok"}]) as m_post:
            res = ig_publisher.publicar_pieza_ig(cid, cfg=cfg_solo_token)

        self.assertTrue(res["publicado"], res)
        self.assertIn("/1784999888/media", m_post.call_args_list[0].args[0])
        self.assertEqual(database.get_settings().get("ig_user_id"), "1784999888")
        self.assertEqual(database.get_settings().get("ig_username"), "elsocio.ia")

    def test_autorenueva_token_ig_a_los_25_dias(self) -> None:
        hace_30_dias = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        database.update_settings({
            "ig_access_token": "IGAAviejo",
            "ig_token_refreshed_at": hace_30_dias,
        })
        with mock.patch.object(ig_publisher, "_graph_get",
                               return_value={"access_token": "IGAAnuevo60dias"}):
            res = ig_publisher.renovar_token_ig_si_toca()
        self.assertTrue(res["renovado"], res)
        self.assertEqual(database.get_settings().get("ig_access_token"), "IGAAnuevo60dias")


# ----------------------------------------- 5. Panel 8787 y Dry-Runs Globales

class TestPanelSeguridadYDryRuns(BaseAutonoma):
    def test_panel_escapa_xss_en_nuevos_campos_y_no_sirve_archivos_fuera_de_redes(self) -> None:
        html_out = panel_mensajes.render(
            [],
            [{
                "id": 1, "gancho": "ok", "tipo": "video", "estado": "generado",
                "archivo": "", "caption": "<script>evil()</script>",
                "guion": "<img onerror=x>", "error_ig": "<b>boom</b>",
            }],
            estado_motor={"aviso": "<script>robar()</script>", "auto_publish": True},
            interactivo=True,
        )
        self.assertNotIn("<script>evil", html_out)
        self.assertNotIn("<script>robar", html_out)
        self.assertNotIn("<img onerror", html_out)

        # Intentar apuntar `archivo` de BD a `.env` -> `/media/1` debe negarlo (None).
        cid = content_manager.encolar(tipo="post", gancho="Frase limpia")["id"]
        database.update_content(cid, estado="generado", archivo=str(PROJECT_ROOT / ".env"))
        self.assertIsNone(panel_server._archivo_seguro_de_pieza(cid))


class TestDryRunCLIReal(unittest.TestCase):
    def test_todos_los_modulos_nuevos_en_dry_run_respetan_bd_y_resultados_reales(self) -> None:
        antes_db, antes_md = huella(DB_REAL), huella(RESULTADOS_REAL)
        comandos = [
            [sys.executable, str(PROJECT_ROOT / "scripts" / "socio_cerebro.py"), "--dry-run"],
            [sys.executable, str(PROJECT_ROOT / "scripts" / "content_brain.py"), "--dry-run"],
            [sys.executable, str(PROJECT_ROOT / "scripts" / "ig_publisher.py"), "--dry-run"],
            [sys.executable, str(PROJECT_ROOT / "scripts" / "voice_engine.py"), "--texto", "Hola socio", "--dry-run"],
            [sys.executable, str(PROJECT_ROOT / "scripts" / "panel_server.py"), "--dry-run"],
            [sys.executable, str(PROJECT_ROOT / "scripts" / "instalar_piloto.py"), "--dry-run"],
        ]
        for cmd in comandos:
            with self.subTest(script=Path(cmd[1]).name):
                proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=30)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                salida = json.loads(proc.stdout)
                self.assertTrue(salida.get("dry_run"), salida)
        self.assertEqual(huella(DB_REAL), antes_db)
        self.assertEqual(huella(RESULTADOS_REAL), antes_md)

    def test_plists_launchd_incluyen_path_para_ffmpeg_y_node(self) -> None:
        plists = instalar_piloto.construir_plists()
        self.assertIn("com.elsocio.cerebro", plists)
        self.assertIn("com.elsocio.panelserver", plists)
        self.assertIn("/usr/local/bin", plists["com.elsocio.cerebro"]["EnvironmentVariables"]["PATH"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

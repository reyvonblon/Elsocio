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

    def test_un_plazo_en_cifras_no_sale_al_video(self) -> None:
        """La guía §4 prohíbe TODA cifra en el video: no solo precios, también plazos."""
        for texto in ("El lote sale en 15 días.", "Te respondo en 2 horas.", "Paso 1 de 3"):
            with self.assertRaises(content_manager.GuardaBloqueada, msg=texto):
                content_manager.encolar(tipo="video", gancho="Frase limpia", guion=texto)
        self.assertEqual(database.list_content(), [])

    def test_el_mismo_plazo_escrito_en_letras_si_pasa(self) -> None:
        """No se censura el idioma: lo prohibido es el dígito en pantalla, no la idea."""
        content_manager.encolar(tipo="video", gancho="Frase limpia",
                                guion="El lote sale en quince días.")
        self.assertEqual(len(database.list_content()), 1)

    def test_un_tooltip_con_cifra_bloquea_la_pieza_entera(self) -> None:
        with self.assertRaises(content_manager.GuardaBloqueada):
            content_manager.encolar(tipo="video", gancho="Frase limpia", guion="Bloque limpio",
                                    planos=[{"toma": "ciudad", "tooltip": "Listo en 5 días"}])
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
        # El cierre del video ya no es el pie de publicación: es el cierre de venta de marca.
        # Rota entre 3 variantes (lugar/persona/directo, ver `cierre_de_venta`): las 3 nombran
        # a "El Socio" en la última oración, pero solo "lugar"/"persona" terminan en LINEA_MARCA
        # literal — "directo" es una frase corta aparte.
        self.assertIn("Socio", props["cierre"])
        self.assertNotIn("link en bio", props["cierre"].lower())

    def test_cierre_de_venta_nombra_el_local_del_nicho(self) -> None:
        casos = {
            "fichas-tecnicas-ropa": "No seas el Taller A. Sé el Taller B.",
            "modelado-3d-espacios": "No seas el Local A. Sé el Local B.",
            "ecommerce-catalogo-visual": "No seas la Tienda A. Sé la Tienda B.",
            "automatizacion-agencias-estudios": "No seas la Agencia A. Sé la Agencia B.",
        }
        for nicho, inicio in casos.items():
            self.assertEqual(content_manager.cierre_de_venta(nicho, []),
                             f"{inicio} {content_manager.LINEA_MARCA}")

    def test_cierre_de_venta_deduce_el_nicho_del_guion_si_es_general(self) -> None:
        cierre = content_manager.cierre_de_venta(
            "general", ["Tu remodelación se come la pared equivocada.", "El maestro rompe sin plano."])
        self.assertTrue(cierre.startswith("No seas el Local A."), cierre)
        self.assertEqual(content_manager.revisar_pieza(cierre), [])

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
        # Sin dígitos: en un reel el guion acaba QUEMADO en pantalla y la guarda prohíbe toda cifra.
        guion = "\n".join(f"bloque {chr(ord('a') + i)}" for i in range(12))
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


# ------------------------------------------- 6. escena isométrica y etiquetas del reel

class TestEscenaYEtiquetas(BaseContenido):
    def test_escena_viaja_en_la_nota_sin_pisar_la_humana(self) -> None:
        content_id = self.encolar_limpia(tipo="video", nota="revisar el cierre",
                                         escena="flujo", etiquetas=["CUENTAS", "ENTREGADO"])
        pieza = database.get_content(content_id)
        self.assertEqual(content_manager.nota_humana(pieza["nota"]), "revisar el cierre")
        self.assertEqual(content_manager.leer_reel(pieza["nota"]),
                         ("flujo", ["CUENTAS", "ENTREGADO"]))

    def test_la_escena_por_defecto_no_ensucia_la_nota(self) -> None:
        content_id = self.encolar_limpia(tipo="video", nota="sin más")
        nota = database.get_content(content_id)["nota"]
        # Un video siempre guarda su formato (la rotación lo necesita), pero nada más.
        self.assertEqual(content_manager.nota_humana(nota), "sin más")
        self.assertNotIn("escena=", nota)
        self.assertNotIn("[planos]", nota)

    def test_escena_inventada_revienta_antes_de_tocar_la_bd(self) -> None:
        with self.assertRaises(ValueError):
            content_manager.encolar(tipo="video", gancho="Frase limpia", escena="tiktok3d")
        self.assertEqual(database.list_content(), [])

    def test_etiqueta_con_precio_bloquea_igual_que_el_gancho(self) -> None:
        """Una etiqueta acaba QUEMADA en el video: la guarda tiene que verla."""
        with self.assertRaises(content_manager.GuardaBloqueada):
            content_manager.encolar(tipo="video", gancho="Frase limpia",
                                    etiquetas=["DESDE 50.000"])
        self.assertEqual(database.list_content(), [])

    def test_etiqueta_con_separador_revienta(self) -> None:
        with self.assertRaises(ValueError):
            content_manager.encolar(tipo="video", gancho="Frase limpia",
                                    etiquetas=["UNO|DOS"])

    def test_etiqueta_demasiado_larga_revienta(self) -> None:
        with self.assertRaises(ValueError):
            content_manager.encolar(tipo="video", gancho="Frase limpia",
                                    etiquetas=["x" * (content_manager.MAX_LARGO_ETIQUETA + 1)])

    def test_las_etiquetas_se_limpian_y_se_cortan(self) -> None:
        crudas = ["  uno\n dos ", "", "   ", "tres", "cuatro", "cinco", "seis"]
        limpias = content_manager.normalizar_etiquetas(crudas)
        self.assertEqual(limpias[0], "uno dos")
        self.assertEqual(len(limpias), content_manager.MAX_ETIQUETAS)

    def test_generar_manda_escena_y_etiquetas_en_los_props(self) -> None:
        content_id = self.encolar_limpia(tipo="video", guion="Uno\nDos",
                                         escena="agenda", etiquetas=["ENTRAN", "AGENDADO"])
        self.assertTrue(content_manager.generar(content_id)["generado"])
        import json
        props = json.loads(self.run.call_args[0][0][2])
        self.assertEqual(props["escena"], "agenda")
        self.assertEqual(props["etiquetas"], ["ENTRAN", "AGENDADO"])

    def test_sin_escena_los_props_llevan_la_de_por_defecto(self) -> None:
        content_id = self.encolar_limpia(tipo="video", guion="Uno")
        content_manager.generar(content_id)
        import json
        props = json.loads(self.run.call_args[0][0][2])
        self.assertEqual(props["escena"], content_manager.ESCENA_DEFECTO)
        self.assertEqual(props["etiquetas"], [])

    def test_generar_con_escena_manda_sobre_la_encolada_y_se_guarda(self) -> None:
        content_id = self.encolar_limpia(tipo="video", guion="Uno", escena="flujo")
        res = content_manager.generar(content_id, escena="espacio3d")
        self.assertEqual(res["escena"], "espacio3d")
        self.assertEqual(content_manager.leer_reel(
            database.get_content(content_id)["nota"])[0], "espacio3d")

    def test_etiqueta_metida_a_mano_en_la_bd_la_frena_la_guarda(self) -> None:
        content_id = self.encolar_limpia(tipo="video", guion="Uno")
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE content_queue SET nota=? WHERE id=?",
                        ("[reel] escena=flujo; etiquetas=VALE 90000", content_id))
        with self.assertRaises(content_manager.GuardaBloqueada):
            content_manager.generar(content_id)
        self.run.assert_not_called()

    def test_escena_inventada_en_la_nota_cae_en_la_de_por_defecto(self) -> None:
        self.assertEqual(content_manager.leer_reel("[reel] escena=lego")[0],
                         content_manager.ESCENA_DEFECTO)

    def test_la_escena_no_estorba_a_un_post(self) -> None:
        content_id = self.encolar_limpia(tipo="post", escena="agenda")
        self.assertTrue(content_manager.generar(content_id)["generado"])
        self.assertIn("generar_post.sh", self.run.call_args[0][0][0])

    def test_publicar_sin_nota_no_pisa_la_que_ya_estaba(self) -> None:
        """El bug de `nota=nota` a secas: publicar sin nota borraba la nota y la escena."""
        content_id = self.encolar_limpia(nota="viene del lead #4", escena="flujo")
        content_manager.publicar(content_id, resultado="silencio")
        pieza = database.get_content(content_id)
        self.assertEqual(content_manager.nota_humana(pieza["nota"]), "viene del lead #4")
        self.assertEqual(content_manager.leer_reel(pieza["nota"])[0], "flujo")

    def test_publicar_con_nota_nueva_conserva_la_escena(self) -> None:
        content_id = self.encolar_limpia(nota="vieja", escena="agenda",
                                         etiquetas=["AGENDADO"])
        content_manager.publicar(content_id, resultado="agendó", nota="salió bien")
        pieza = database.get_content(content_id)
        self.assertEqual(content_manager.nota_humana(pieza["nota"]), "salió bien")
        self.assertEqual(content_manager.leer_reel(pieza["nota"]),
                         ("agenda", ["AGENDADO"]))


# --------------------------------------------- 7. el CLI con escena y etiquetas

class TestCliEscena(BaseContenido):
    def test_encolar_con_escena_y_etiquetas_desde_el_cli(self) -> None:
        código = content_manager.main([
            "encolar", "--tipo", "video", "--gancho", "Una frase limpia y sobria.",
            "--escena", "espacio3d", "--etiquetas", "TU PLANO", "RENDER"])
        self.assertEqual(código, 0)
        pieza = database.list_content()[0]
        self.assertEqual(content_manager.leer_reel(pieza["nota"]),
                         ("espacio3d", ["TU PLANO", "RENDER"]))

    def test_el_cli_rechaza_una_escena_que_no_existe(self) -> None:
        with self.assertRaises(SystemExit):
            content_manager.main(["encolar", "--gancho", "Frase limpia",
                                  "--escena", "lego"])

    def test_el_cli_devuelve_codigo_2_si_una_etiqueta_trae_precio(self) -> None:
        código = content_manager.main([
            "--dry-run", "encolar", "--gancho", "Frase limpia",
            "--etiquetas", "DESDE 50.000"])
        self.assertEqual(código, 2)

    def test_el_cli_devuelve_codigo_2_si_una_etiqueta_es_invalida(self) -> None:
        código = content_manager.main([
            "--dry-run", "encolar", "--gancho", "Frase limpia", "--etiquetas", "A|B"])
        self.assertEqual(código, 2)


# --------------------------------------------------- 8. el panel no se deja inyectar

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


# ------------------------------------------- 9. nada de esto toca lo real, de verdad

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


# ------------------------------------ 10. formato historia (1080x1920) y conteos por tipo

class TestFormatoHistoriaYConteosPorTipo(BaseContenido):
    def test_historia_llama_a_generar_historia_sh_y_alterna_tema(self) -> None:
        c1 = self.encolar_limpia(
            tipo="historia",
            gancho="Tu equipo pierde el día copiando datos a mano.",
            guion="Eso ya se automatiza limpio.",
            caption="Responde esta historia con tu caso",
            nicho="automatizacion-agencias-estudios",
        )
        c2 = self.encolar_limpia(
            tipo="historia",
            gancho="Tu catálogo parece de otro negocio.",
            nicho="ecommerce-catalogo-visual",
        )
        r1 = content_manager.generar(c1)
        r2 = content_manager.generar(c2)
        self.assertTrue(r1["generado"], r1)
        self.assertTrue(r2["generado"], r2)

        cmd1 = self.run.call_args_list[0][0][0]
        cmd2 = self.run.call_args_list[1][0][0]
        self.assertIn("generar_historia.sh", cmd1[0])
        self.assertTrue(r1["archivo"].endswith(".png"))
        self.assertIn("/historias/", r1["archivo"])
        self.assertEqual(cmd1[5], "AGENCIAS")
        self.assertEqual(cmd2[5], "CATÁLOGO")
        self.assertNotEqual(cmd1[6], cmd2[6], "dos historias seguidas deben alternar oscuro/crema")

    def test_historia_con_precio_o_link_bloqueada_por_guarda(self) -> None:
        with self.assertRaises(content_manager.GuardaBloqueada):
            content_manager.encolar(
                tipo="historia",
                gancho="Automatiza hoy por 120000 pesos",
            )
        with self.assertRaises(content_manager.GuardaBloqueada):
            content_manager.encolar(
                tipo="historia",
                gancho="Frase limpia",
                caption="Mira bit.ly/cobro",
            )
        self.assertEqual(database.list_content(), [])

    def test_cli_acepta_tipo_historia(self) -> None:
        codigo = content_manager.main([
            "encolar", "--tipo", "historia",
            "--gancho", "Lo que pospones hoy frena tu semana.",
        ])
        self.assertEqual(codigo, 0)
        self.assertEqual(database.list_content()[0]["tipo"], "historia")

    def test_conteos_diarios_por_tipo_en_bd(self) -> None:
        v1 = self.encolar_limpia(tipo="video", gancho="Gancho video limpio.")
        p1 = self.encolar_limpia(tipo="post", gancho="Gancho post limpio.")
        h1 = self.encolar_limpia(tipo="historia", gancho="Gancho historia limpio.")
        por_tipo = database.content_created_today_by_tipo()
        self.assertEqual(por_tipo, {"post": 1, "video": 1, "historia": 1, "carrusel": 0})

        database.update_content(v1, estado="publicado", ig_media_id="ig_v1")
        database.update_content(h1, estado="publicado", ig_media_id="ig_h1")
        self.assertEqual(
            database.ig_published_today_by_tipo(),
            {"post": 0, "video": 1, "historia": 1, "carrusel": 0},
        )
        self.assertIsNotNone(database.last_ig_published_datetime())
        self.assertIsNotNone(database.get_content(p1))


class TestPlanosReelMundo(BaseContenido):
    """Storyboard: una toma por frase. Viaja en la nota, llega a los props y pasa por la guarda."""

    PLANOS = [
        {"toma": "pareja", "lado": "A"},
        {"toma": "detalle", "lado": "A", "foco": "audios", "tooltip": "A ciegas"},
        {"toma": "detalle", "lado": "B", "foco": "ficha", "tarjeta": "ficha"},
        {"toma": "pareja"},
    ]

    def test_planos_viajan_en_la_nota_sin_pisar_la_humana(self) -> None:
        content_id = self.encolar_limpia(tipo="video", nota="ojo al cierre", planos=self.PLANOS)
        pieza = database.get_content(content_id)
        self.assertEqual(content_manager.nota_humana(pieza["nota"]), "ojo al cierre")
        self.assertEqual(content_manager.leer_planos(pieza["nota"]), self.PLANOS)

    def test_tooltip_con_cifra_bloquea_la_pieza(self) -> None:
        with self.assertRaises(content_manager.GuardaBloqueada):
            content_manager.encolar(tipo="video", gancho="Frase limpia",
                                    planos=[{"foco": "mesa", "tooltip": "Desde 50.000"}])
        self.assertEqual(database.list_content(), [])

    def test_valores_desconocidos_se_descartan_no_revientan(self) -> None:
        limpios = content_manager.normalizar_planos(
            [{"toma": "drone", "foco": "mesa", "tarjeta": "holograma", "lado": "c"}, "basura"])
        self.assertEqual(limpios, [{"foco": "mesa"}, {}])

    def test_planos_vacios_no_ensucian_la_nota(self) -> None:
        content_id = self.encolar_limpia(tipo="video", nota="sin más", planos=[{}, {"toma": "x"}])
        nota = database.get_content(content_id)["nota"]
        self.assertEqual(content_manager.nota_humana(nota), "sin más")
        self.assertNotIn("[planos]", nota)

    def test_post_ignora_planos(self) -> None:
        content_id = self.encolar_limpia(tipo="post", nota="n", planos=self.PLANOS)
        self.assertEqual(content_manager.leer_planos(database.get_content(content_id)["nota"]), [])

    def test_generar_pasa_los_planos_a_los_props(self) -> None:
        import json as _json
        content_id = self.encolar_limpia(tipo="video", planos=self.PLANOS)
        res = content_manager.generar(content_id, dry_run=True)
        props = _json.loads(res["comando"][2])
        self.assertEqual(props["planos"], self.PLANOS)

    def test_linea_de_planos_rota_se_ignora(self) -> None:
        self.assertEqual(content_manager.leer_planos("[planos] {no es json"), [])

    def test_publicar_conserva_los_planos(self) -> None:
        content_id = self.encolar_limpia(tipo="video", planos=self.PLANOS)
        with mock.patch.object(content_manager.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            content_manager.generar(content_id)
        content_manager.publicar(content_id, resultado="comentario real", nota="publicado a mano")
        nota = database.get_content(content_id)["nota"]
        self.assertEqual(content_manager.leer_planos(nota), self.PLANOS)


class TestFormatosYRotacion(BaseContenido):
    """El Socio no hace siempre el mismo video: rota mundo / collage / duelo."""

    def test_nunca_dos_reels_seguidos_con_el_mismo_formato(self) -> None:
        vistos = []
        for n in range(6):
            res = content_manager.encolar(tipo="video", gancho=f"Gancho limpio número {'abcdef'[n]}",
                                          guion="Uno\nDos")
            vistos.append(res["formato"])
        for a, b in zip(vistos, vistos[1:]):
            self.assertNotEqual(a, b, vistos)
        self.assertEqual(set(vistos), set(content_manager.FORMATOS))

    def test_respeta_la_sugerencia_si_no_repite(self) -> None:
        self.assertEqual(content_manager.elegir_formato("duelo", ["mundo"]), "duelo")

    def test_ignora_la_sugerencia_si_repite_el_ultimo(self) -> None:
        self.assertNotEqual(content_manager.elegir_formato("collage", ["collage", "mundo"]), "collage")

    def test_sugerencia_inventada_cae_en_la_rotacion(self) -> None:
        self.assertIn(content_manager.elegir_formato("tiktok3d", []), content_manager.FORMATOS)

    def test_post_no_lleva_formato(self) -> None:
        res = content_manager.encolar(tipo="post", gancho="Frase limpia", formato="duelo")
        self.assertEqual(res["formato"], "")

    def test_generar_manda_el_formato_en_los_props(self) -> None:
        import json as _json
        content_id = content_manager.encolar(tipo="video", gancho="Frase limpia", guion="A\nB",
                                             formato="collage")["id"]
        props = _json.loads(content_manager.generar(content_id, dry_run=True)["comando"][2])
        self.assertEqual(props["formato"], "collage")

    def test_pieza_vieja_sin_formato_sale_como_mundo(self) -> None:
        import json as _json
        content_id = database.enqueue_content(tipo="video", gancho="Pieza vieja", guion="A\nB",
                                              caption="", nicho="", nota="hecha antes")
        props = _json.loads(content_manager.generar(content_id, dry_run=True)["comando"][2])
        self.assertEqual(props["formato"], "mundo")

    def test_objeto_de_collage_viaja_en_los_planos(self) -> None:
        self.assertEqual(content_manager.normalizar_planos([{"objeto": "tostadora"}, {"objeto": "dron"}]),
                         [{"objeto": "tostadora"}, {}])




class TestCarrusel(unittest.TestCase):
    def test_laminas_portada_desarrollo_y_cierre(self) -> None:
        laminas = content_manager.laminas_carrusel("Gancho", "Uno\nDos\nTres\nEscríbenos")
        self.assertEqual(laminas, ["Gancho", "Uno", "Dos", "Tres", "Escríbenos"])
        self.assertEqual(content_manager.laminas_carrusel("Gancho", ""),
                         ["Gancho", content_manager.CIERRE_CARRUSEL_DEFECTO])

    def test_archivos_carrusel_encuentra_todas_las_laminas_en_orden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for i in (3, 1, 2):
                (d / f"content_0009_{i:02d}.png").write_bytes(b"x")
            (d / "content_0010_01.png").write_bytes(b"x")
            res = content_manager.archivos_carrusel(d / "content_0009_01.png")
            self.assertEqual([p.name for p in res],
                             ["content_0009_01.png", "content_0009_02.png", "content_0009_03.png"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Batería en seco del agente de ventas. `unittest` de stdlib, BD temporal, cero red.

Nunca toca `data/el_socio.db` y nunca llama a la API de Anthropic: cada prueba que
necesita una respuesta del modelo la finge.

    python3 scripts/test_sales_agent.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import autopilot_dispatcher  # noqa: E402
import database  # noqa: E402
import sales_agent  # noqa: E402

DB_REAL = PROJECT_ROOT / "data" / "el_socio.db"
TABLAS_VIGILADAS = ("leads", "outbox", "agent_log", "agent_followups")

CFG_FALSA = {
    "ANTHROPIC_API_KEY": "clave-de-prueba-no-sirve",
    "SALES_AGENT_MODEL": "claude-sonnet-5",
    "SALES_AGENT_MAX_EMAILS": "15",
    "SALES_AGENT_MAX_DAILY_USD": "0.50",
}


def huella(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest() if ruta.exists() else "(no existe)"


def contar_filas(ruta: Path) -> dict[str, int]:
    if not ruta.exists():
        return {}
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        salida = {}
        for tabla in TABLAS_VIGILADAS:
            existe = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)
            ).fetchone()
            salida[tabla] = int(con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]) if existe else 0
        return salida
    finally:
        con.close()


def respuesta_falsa(*bloques: dict, stop: str = "tool_use") -> dict:
    return {"stop_reason": stop, "content": list(bloques),
            "usage": {"input_tokens": 10, "output_tokens": 5}}


def bloque_tool(nombre: str, entrada: dict, ident: str = "tu_1") -> dict:
    return {"type": "tool_use", "id": ident, "name": nombre, "input": entrada}


class BaseConBDTemporal(unittest.TestCase):
    """Cada prueba corre contra su propia BD en /tmp. `data/el_socio.db` ni se abre."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "prueba.db"
        self.parche_db = mock.patch.object(database, "DB_PATH", self.db)
        self.parche_db.start()
        database.init_db()
        # Nada de notificaciones del Mac ni eventos de calendario en las pruebas.
        self.parche_notif = mock.patch.object(sales_agent.autopilot_dispatcher,
                                              "notify_mac_desktop", return_value=True)
        self.parche_cal = mock.patch.object(sales_agent.autopilot_dispatcher,
                                            "create_calendar_event", return_value=True)
        self.parche_notif.start()
        self.parche_cal.start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.parche_cal.stop)
        self.addCleanup(self.parche_notif.stop)
        self.addCleanup(self.parche_db.stop)

    def agente(self, **kwargs) -> sales_agent.AgenteVentas:
        return sales_agent.AgenteVentas(dict(CFG_FALSA), **kwargs)

    def crear_lead(self, email: str = "lead@ejemplo.com", stage: str = "nuevo_lead") -> dict:
        database.upsert_lead(name="", company="Empresa X", email=email, nicho="modelado-3d-espacios",
                             source="prueba", stage=stage, notes="")
        return database.get_lead_by_email(email)

    def estados_outbox(self, email: str) -> list[str]:
        with sqlite3.connect(self.db) as con:
            return [r[0] for r in con.execute(
                "SELECT status FROM outbox WHERE recipient=?", (email.lower(),)).fetchall()]

    def estados_followups(self, lead_id: int) -> list[str]:
        with sqlite3.connect(self.db) as con:
            return [r[0] for r in con.execute(
                "SELECT estado FROM agent_followups WHERE lead_id=?", (lead_id,)).fetchall()]


# --------------------------------------------------------------- 1. dry-run no toca nada

class TestDryRunNoTocaNada(unittest.TestCase):
    """El `--dry-run` real, corrido como lo correría Raymond, contra la BD de verdad."""

    def test_cli_dry_run_no_modifica_la_bd_ni_envia(self) -> None:
        antes_huella, antes_filas = huella(DB_REAL), contar_filas(DB_REAL)
        existia = DB_REAL.exists()

        entorno = dict(os.environ)
        entorno.pop("ANTHROPIC_API_KEY", None)  # sin key: igual tiene que funcionar
        with mock.patch.dict(os.environ, entorno, clear=True):
            proc = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "scripts" / "sales_agent.py"),
                 "--lead-email", "prueba@ejemplo.com", "--dry-run"],
                capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=120,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        salida = json.loads(proc.stdout)
        self.assertTrue(salida["ok"], salida)
        self.assertTrue(salida["dry_run"])
        self.assertFalse(salida["con_api"])
        self.assertEqual(salida["motivo"], "dry_run_sin_api")
        self.assertEqual(salida["costo_usd"], 0.0)
        self.assertEqual(salida["turnos"], 0)

        self.assertEqual(DB_REAL.exists(), existia, "el dry-run creó data/el_socio.db")
        self.assertEqual(huella(DB_REAL), antes_huella, "el dry-run modificó data/el_socio.db")
        self.assertEqual(contar_filas(DB_REAL), antes_filas, "el dry-run creó filas")

    def test_dry_run_no_llama_a_la_api(self) -> None:
        with mock.patch.object(sales_agent, "llamar_api",
                               side_effect=AssertionError("el dry-run llamó a la API")) as api:
            agente = sales_agent.AgenteVentas(dict(CFG_FALSA), dry_run=True)
            resultado = agente.correr(lead_email="prueba@ejemplo.com")
        self.assertTrue(resultado["ok"])
        self.assertEqual(api.call_count, 0)
        self.assertEqual(resultado["costo_usd"], 0.0)

    def test_dry_run_sin_api_key_igual_valida(self) -> None:
        cfg = dict(CFG_FALSA, ANTHROPIC_API_KEY="")
        agente = sales_agent.AgenteVentas(cfg, dry_run=True)
        self.assertEqual(agente.guardas_previas(), "")
        self.assertTrue(agente.simulado)

    def test_sin_dry_run_y_sin_api_key_no_opera(self) -> None:
        cfg = dict(CFG_FALSA, ANTHROPIC_API_KEY="")
        agente = sales_agent.AgenteVentas(cfg)
        self.assertIn("ANTHROPIC_API_KEY", agente.guardas_previas())


# --------------------------------------------------------------- 2. guarda de precios y links

class TestGuardaDePrecios(unittest.TestCase):
    BLOQUEADOS = [
        "25 mil", "veinticinco mil", "$50.000", "vale 30", "te paso el nequi",
        "Te queda en 50000", "mpago.la/2xYz", "bit.ly/pagar",
        "https://pagos.evil.com/?r=reyvonblon.github.io",
        "https://reyvonblon.github.io.evil.com/pagar",
        "25000", "120000", "son 3 millones", "cuesta poco", "COP 40.000",
        "checkout.stripe.com/abc", "tinyurl.com/x9", "wa.link/pagar", "paypal.me/alguien",
        "www.otrositio.com", "mi numero es 3001234567",
        # hallazgos del Paso 4: espacio como separador, porcentajes, transferencias,
        # Bre-B, link con query sin barra y query escondida en un link propio.
        "50 000", "120 000", "te doy 50%", "un 20 por ciento", "te hago una transferencia",
        "puedes transferir cuando quieras", "pagas por bre-b", "pagas por breb",
        "pagas por bre b", "ella cobra aparte", "ya me estan cobrando", "evil.com?a=1",
        "https://wa.me/573001112233?text=pagar_50000_nequi",
    ]
    PERMITIDOS = [
        "Mil gracias", "web oficial",
        "Hola, vi tu catalogo y creo que puedo ayudarte con las fichas tecnicas.",
        "Te dejo ejemplos en https://reyvonblon.github.io/Elsocio/",
        "Escribeme por https://wa.me/573001112233",
        "Mil gracias por responder, te mando 3 opciones de render.",
        "En 2026 arrancamos con el catalogo",
        "Escribeme a https://wa.me/573001112233 cuando quieras",
    ]

    def test_bloquea_cifras_links_y_metodos_de_pago(self) -> None:
        for texto in self.BLOQUEADOS:
            with self.subTest(texto=texto):
                self.assertTrue(sales_agent.revisar_guarda_precios(texto),
                                f"debía bloquearse y pasó: {texto!r}")

    def test_deja_pasar_el_texto_legitimo(self) -> None:
        for texto in self.PERMITIDOS:
            with self.subTest(texto=texto):
                self.assertEqual(sales_agent.revisar_guarda_precios(texto), [],
                                 f"se bloqueó texto legítimo: {texto!r}")

    def test_hostname_se_valida_exacto_no_por_contenido(self) -> None:
        # El dominio propio dentro de la query o como prefijo de otro dominio NO vale.
        self.assertEqual(sales_agent._links_externos("https://pagos.evil.com/?r=reyvonblon.github.io"),
                         ["https://pagos.evil.com/?r=reyvonblon.github.io"])
        self.assertEqual(sales_agent._links_externos("https://reyvonblon.github.io.evil.com/pagar"),
                         ["https://reyvonblon.github.io.evil.com/pagar"])
        self.assertEqual(sales_agent._links_externos("https://reyvonblon.github.io/Elsocio/"), [])

    def test_la_guarda_tambien_mira_el_asunto(self) -> None:
        motivos = sales_agent.revisar_guarda_precios("Promocion: 50000", "Hola, un gusto saludarte.")
        self.assertTrue(motivos)


class TestHallazgosDeLaGuarda(unittest.TestCase):
    """Los huecos que encontró la auditoría del Paso 4, uno por uno."""

    def test_el_link_propio_limpio_sigue_pasando(self) -> None:
        self.assertEqual(sales_agent.revisar_guarda_precios("https://wa.me/573001112233"), [])
        self.assertEqual(sales_agent._links_externos("https://wa.me/573001112233"), [])

    def test_la_query_de_un_link_propio_no_es_un_escondite(self) -> None:
        motivos = sales_agent.revisar_guarda_precios(
            "Escribeme a https://wa.me/573001112233?text=pagar_50000_nequi")
        self.assertTrue(motivos, "la query del link propio se saltó la guarda")
        self.assertTrue(any("50000" in m or "nequi" in m for m in motivos), motivos)

    def test_el_host_propio_si_se_borra_para_contar_cifras(self) -> None:
        limpio = sales_agent._sin_links_permitidos("ver https://wa.me/573001112233 ya")
        self.assertNotIn("573001112233", limpio)
        self.assertIn("enlace_oficial", limpio)

    def test_un_link_con_query_sin_barra_es_un_link(self) -> None:
        self.assertEqual(sales_agent._links_externos("mira evil.com?a=1"), ["evil.com?a=1"])

    def test_espacio_como_separador_de_miles(self) -> None:
        for texto in ("50 000", "120 000"):
            with self.subTest(texto=texto):
                self.assertTrue(sales_agent.revisar_guarda_precios(texto))

    def test_bloquea_porcentajes(self) -> None:
        for texto in ("te doy 50%", "un 20 por ciento de descuento", "30 %"):
            with self.subTest(texto=texto):
                self.assertTrue(sales_agent.revisar_guarda_precios(texto))


class TestFalsosPositivosDeBaja(unittest.TestCase):
    """'baja' y 'stop' dentro de una frase normal NO son una baja."""

    NO_SON_BAJA = (
        "Tengo una foto de baja resolución",
        "Render para la planta baja",
        "Jeans cintura baja",
        "Video stop motion",
        "La temporada baja nos conviene mejor",
        "planta baja",
        "cintura baja",
        "Me interesa, cuentame mas",
        "",
    )
    SI_SON_BAJA = (
        "BAJA", "baja", "baja.", "baja por favor", "Baja, gracias", "stop", "STOP",
        "darme de baja", "no me escriban", "unsubscribe", "esto es spam", "remove me",
        "Por favor dejen de escribirme",
    )

    def test_no_lee_una_baja_donde_no_hay(self) -> None:
        for texto in self.NO_SON_BAJA:
            with self.subTest(texto=texto):
                self.assertFalse(sales_agent.pide_la_baja(texto),
                                 f"falso positivo de baja: {texto!r}")

    def test_sigue_detectando_las_bajas_de_verdad(self) -> None:
        for texto in self.SI_SON_BAJA:
            with self.subTest(texto=texto):
                self.assertTrue(sales_agent.pide_la_baja(texto),
                                f"no detectó la baja: {texto!r}")


class TestGuardaAlEncolar(BaseConBDTemporal):
    def test_correo_con_precio_no_se_encola_y_no_gasta_cupo(self) -> None:
        agente = self.agente()
        agente.lead = self.crear_lead()
        ok, mensaje = agente.ejecutar_herramienta(
            "enviar_correo", {"asunto": "Propuesta", "cuerpo": "Te queda en 50000, pagas por nequi."},
            es_frio=True)
        self.assertFalse(ok)
        self.assertIn("BLOQUEADO", mensaje)
        self.assertEqual(self.estados_outbox("lead@ejemplo.com"), [])
        self.assertEqual(database.agent_emails_queued_today(), 0)
        with sqlite3.connect(self.db) as con:
            bloqueos = con.execute(
                "SELECT bloqueado_por_guarda FROM agent_log WHERE herramienta='enviar_correo'"
            ).fetchall()
        self.assertTrue(bloqueos and bloqueos[0][0])


# --------------------------------------------------------------- 3. línea de baja y duplicados

class TestLineaDeBaja(BaseConBDTemporal):
    def test_al_correo_en_frio_se_le_agrega_la_linea(self) -> None:
        agente = self.agente()
        agente.lead = self.crear_lead()
        ok, _ = agente.ejecutar_herramienta(
            "enviar_correo", {"asunto": "Una idea para tu catalogo",
                              "cuerpo": "Hola, vi tus fotos y creo que puedo ayudarte."},
            es_frio=True)
        self.assertTrue(ok)
        with sqlite3.connect(self.db) as con:
            cuerpo = con.execute("SELECT body FROM outbox ORDER BY id DESC LIMIT 1").fetchone()[0]
        self.assertTrue(sales_agent.tiene_linea_de_baja(cuerpo), cuerpo)
        self.assertIn("BAJA", cuerpo)

    def test_no_se_duplica_la_linea_si_ya_estaba(self) -> None:
        cuerpo = "Hola. Si no quieres recibir más correos míos, responde BAJA y no te escribo más."
        self.assertEqual(sales_agent.asegurar_linea_de_baja(cuerpo), cuerpo)

    def test_en_respuesta_no_se_agrega(self) -> None:
        agente = self.agente()
        agente.lead = self.crear_lead()
        agente.ejecutar_herramienta(
            "enviar_correo", {"asunto": "Listo", "cuerpo": "Perfecto, lo reviso y te cuento."},
            es_frio=False)
        with sqlite3.connect(self.db) as con:
            cuerpo = con.execute("SELECT body FROM outbox ORDER BY id DESC LIMIT 1").fetchone()[0]
        self.assertNotIn("BAJA", cuerpo)


class TestDuplicadosDelMismoDia(BaseConBDTemporal):
    def test_no_encola_dos_veces_el_mismo_dia(self) -> None:
        agente = self.agente()
        agente.lead = self.crear_lead()
        primero, _ = agente.ejecutar_herramienta(
            "enviar_correo", {"asunto": "Una idea", "cuerpo": "Hola, te escribo por tu catalogo."},
            es_frio=True)
        segundo, aviso = agente.ejecutar_herramienta(
            "enviar_correo", {"asunto": "Otra idea", "cuerpo": "Hola de nuevo, se me ocurrio algo."},
            es_frio=True)
        self.assertTrue(primero)
        self.assertFalse(segundo)
        self.assertIn("No dupliques", aviso)
        self.assertEqual(len(self.estados_outbox("lead@ejemplo.com")), 1)

    def test_el_duplicado_se_detecta_con_mayusculas(self) -> None:
        database.enqueue_email(recipient="Lead@Ejemplo.COM", subject="x", body="y")
        self.assertTrue(database.already_emailed_today("lead@ejemplo.com"))
        self.assertTrue(database.already_emailed_today("LEAD@EJEMPLO.com"))
        agente = self.agente()
        agente.lead = self.crear_lead(email="lead@ejemplo.com")
        ok, aviso = agente.ejecutar_herramienta(
            "enviar_correo", {"asunto": "Hola", "cuerpo": "Te escribo por tu catalogo."},
            es_frio=True)
        self.assertFalse(ok)
        self.assertIn("No dupliques", aviso)


# --------------------------------------------------------------- 4. bajas y leads cerrados

class TestCancelacionAlDarDeBaja(BaseConBDTemporal):
    def test_pasar_a_baja_cancela_outbox_y_seguimientos(self) -> None:
        lead = self.crear_lead()
        database.enqueue_email(recipient=lead["email"], subject="x", body="y")
        database.schedule_followup(lead["id"], 3, "insistir")
        agente = self.agente()
        agente.lead = dict(lead)
        ok, _ = agente.ejecutar_herramienta(
            "cambiar_etapa", {"etapa": "baja", "nota": "pidio la baja"}, es_frio=False)
        self.assertTrue(ok)
        self.assertEqual(self.estados_outbox(lead["email"]), ["cancelled"])
        self.assertEqual(self.estados_followups(lead["id"]), ["cancelado"])
        self.assertEqual(database.get_lead_by_email(lead["email"])["stage"], "baja")

    def test_mensaje_de_baja_se_atiende_en_codigo_sin_llamar_a_la_api(self) -> None:
        lead = self.crear_lead()
        database.enqueue_email(recipient=lead["email"], subject="x", body="y")
        database.schedule_followup(lead["id"], 3, "insistir")
        with mock.patch.object(sales_agent, "llamar_api",
                               side_effect=AssertionError("llamó a la API con un lead de baja")) as api:
            resultado = self.agente().correr(
                lead_email=lead["email"], mensaje_lead="No me escriban mas, quiero darme de baja.")
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["motivo"], "baja_pedida_por_el_lead")
        self.assertEqual(api.call_count, 0)
        self.assertEqual(self.estados_outbox(lead["email"]), ["cancelled"])
        self.assertEqual(self.estados_followups(lead["id"]), ["cancelado"])
        self.assertEqual(database.get_lead_by_email(lead["email"])["stage"], "baja")

    def test_detecta_las_senales_de_baja(self) -> None:
        for texto in ("BAJA", "baja", "no me escriban", "darme de baja", "unsubscribe",
                      "Por favor dejen de escribirme", "esto es spam", "remove me"):
            with self.subTest(texto=texto):
                self.assertTrue(sales_agent.pide_la_baja(texto))
        for texto in ("Me interesa, cuentame mas", "Mandame ejemplos por favor", ""):
            with self.subTest(texto=texto):
                self.assertFalse(sales_agent.pide_la_baja(texto))


class TestLeadsCerrados(BaseConBDTemporal):
    def _correr_sin_api(self, email: str) -> dict:
        with mock.patch.object(sales_agent, "llamar_api",
                               side_effect=AssertionError("llamó a la API con un lead cerrado")) as api:
            resultado = self.agente().correr(lead_email=email, mensaje_lead="Hola, cuentame mas")
        self.assertEqual(api.call_count, 0)
        return resultado

    def test_lead_en_baja_no_pasa_por_la_api(self) -> None:
        lead = self.crear_lead(email="baja@ejemplo.com", stage="baja")
        resultado = self._correr_sin_api(lead["email"])
        self.assertFalse(resultado["ok"])
        self.assertIn("baja", resultado["motivo"])

    def test_lead_no_interesado_no_pasa_por_la_api(self) -> None:
        lead = self.crear_lead(email="no@ejemplo.com", stage="no_interesado")
        resultado = self._correr_sin_api(lead["email"])
        self.assertFalse(resultado["ok"])
        self.assertIn("no_interesado", resultado["motivo"])

    def test_lead_rebotado_no_pasa_por_la_api(self) -> None:
        lead = self.crear_lead(email="rebote@ejemplo.com")
        database.mark_lead_bounced(lead["email"], "550 user unknown")
        resultado = self._correr_sin_api(lead["email"])
        self.assertFalse(resultado["ok"])
        self.assertIn("rebot", resultado["motivo"])

    def test_la_herramienta_de_correo_tambien_rechaza_al_lead_cerrado(self) -> None:
        for email, stage, rebotado in (("b@ejemplo.com", "baja", False),
                                       ("n@ejemplo.com", "no_interesado", False),
                                       ("r@ejemplo.com", "nuevo_lead", True)):
            with self.subTest(email=email):
                lead = self.crear_lead(email=email, stage=stage)
                if rebotado:
                    database.mark_lead_bounced(email, "rebote")
                    lead = database.get_lead_by_email(email)
                agente = self.agente()
                agente.lead = dict(lead)
                ok, _ = agente.ejecutar_herramienta(
                    "enviar_correo", {"asunto": "Hola", "cuerpo": "Te escribo por tu catalogo."},
                    es_frio=True)
                self.assertFalse(ok)
                self.assertEqual(self.estados_outbox(email), [])
                self.assertEqual(database.agent_emails_queued_today(), 0)


# --------------------------------------------------------------- 5. topes

class TestTopesAntesDeLaApi(BaseConBDTemporal):
    def _loguear_correos(self, cuantos: int) -> None:
        for _ in range(cuantos):
            database.log_agent_action(lead_id=1, turno=1, modelo="claude-sonnet-5",
                                      herramienta="enviar_correo", resultado="encolado")

    def test_tope_de_15_correos_corta_antes_de_llamar(self) -> None:
        self._loguear_correos(15)
        self.assertEqual(database.agent_emails_queued_today(), 15)
        with mock.patch.object(sales_agent, "llamar_api",
                               side_effect=AssertionError("llamó a la API con el cupo lleno")) as api:
            resultado = self.agente().correr(lead_email="lead@ejemplo.com")
        self.assertFalse(resultado["ok"])
        self.assertIn("Tope diario de correos", resultado["motivo"])
        self.assertEqual(api.call_count, 0)
        self.assertEqual(contar_filas(self.db)["leads"], 0, "creó el lead pese al tope")

    def test_con_14_correos_todavia_opera(self) -> None:
        self._loguear_correos(14)
        self.assertEqual(self.agente().guardas_previas(), "")

    def test_tope_de_usd_corta_antes_de_llamar(self) -> None:
        database.log_agent_action(lead_id=1, turno=1, modelo="claude-sonnet-5",
                                  herramienta="llamada_api", costo_usd=0.50)
        with mock.patch.object(sales_agent, "llamar_api",
                               side_effect=AssertionError("llamó a la API sin saldo")) as api:
            resultado = self.agente().correr(lead_email="lead@ejemplo.com")
        self.assertFalse(resultado["ok"])
        self.assertIn("Tope diario de gasto", resultado["motivo"])
        self.assertEqual(api.call_count, 0)

    def test_el_tope_de_usd_se_lee_del_env(self) -> None:
        database.log_agent_action(lead_id=1, turno=1, modelo="claude-sonnet-5",
                                  herramienta="llamada_api", costo_usd=0.10)
        apretado = sales_agent.AgenteVentas(dict(CFG_FALSA, SALES_AGENT_MAX_DAILY_USD="0.05"))
        self.assertIn("Tope diario de gasto", apretado.guardas_previas())
        self.assertEqual(self.agente().guardas_previas(), "")

    def test_el_cupo_de_correos_corta_dentro_del_loop(self) -> None:
        self._loguear_correos(15)
        agente = self.agente()
        agente.lead = self.crear_lead()
        ok, aviso = agente.ejecutar_herramienta(
            "enviar_correo", {"asunto": "Hola", "cuerpo": "Te escribo por tu catalogo."},
            es_frio=True)
        self.assertFalse(ok)
        self.assertIn("Tope diario de correos", aviso)
        self.assertEqual(self.estados_outbox("lead@ejemplo.com"), [])


# --------------------------------------------------------------- 6. corte de turnos

class TestCorteDeTurnos(BaseConBDTemporal):
    def test_corta_duro_en_6_turnos(self) -> None:
        self.crear_lead()
        falsa = respuesta_falsa(bloque_tool("programar_seguimiento", {"dias": 3, "motivo": "insistir"}))
        with mock.patch.object(sales_agent, "llamar_api", return_value=falsa) as api:
            resultado = self.agente().correr(lead_email="lead@ejemplo.com", mensaje_lead="Cuentame mas")
        self.assertEqual(sales_agent.MAX_TURNS, 6)
        self.assertEqual(api.call_count, 6, "el loop no cortó en 6 turnos")
        self.assertEqual(resultado["turnos"], 6)
        self.assertEqual(resultado["motivo"], "max_turnos")
        self.assertTrue(resultado["ok"])

    def test_termina_antes_si_el_modelo_no_usa_herramientas(self) -> None:
        self.crear_lead()
        falsa = respuesta_falsa({"type": "text", "text": "Listo."}, stop="end_turn")
        with mock.patch.object(sales_agent, "llamar_api", return_value=falsa) as api:
            resultado = self.agente().correr(lead_email="lead@ejemplo.com", mensaje_lead="Gracias")
        self.assertEqual(api.call_count, 1)
        self.assertEqual(resultado["turnos"], 1)

    def test_maximo_2_seguimientos_por_lead(self) -> None:
        lead = self.crear_lead()
        agente = self.agente()
        agente.lead = dict(lead)
        resultados = [agente.ejecutar_herramienta(
            "programar_seguimiento", {"dias": 3, "motivo": "insistir"}, es_frio=False)[0]
            for _ in range(3)]
        self.assertEqual(resultados, [True, True, False])
        self.assertEqual(len(self.estados_followups(lead["id"])), 2)


# --------------------------------------------------------------- 7. reintentos

class TestReintentos(unittest.TestCase):
    def _error(self, codigo: int) -> urllib.error.HTTPError:
        return urllib.error.HTTPError("https://api.anthropic.com/v1/messages", codigo,
                                      "falla", {}, None)

    def test_un_429_se_reintenta_2_veces_y_pausa_entre_intentos(self) -> None:
        with mock.patch.object(sales_agent.urllib.request, "urlopen",
                               side_effect=self._error(429)) as abrir, \
             mock.patch.object(sales_agent.time, "sleep") as dormir:
            with self.assertRaises(sales_agent.ErrorAPI):
                sales_agent.llamar_api("clave-falsa", {"model": "x"})
        self.assertEqual(sales_agent.MAX_REINTENTOS, 2)
        self.assertEqual(abrir.call_count, 3, "no son 1 intento + 2 reintentos")
        self.assertEqual(dormir.call_count, 2, "no pausó entre reintentos")
        self.assertEqual([c.args[0] for c in dormir.call_args_list],
                         [sales_agent.PAUSA_REINTENTO, sales_agent.PAUSA_REINTENTO * 2])

    def test_un_500_tambien_se_reintenta(self) -> None:
        with mock.patch.object(sales_agent.urllib.request, "urlopen",
                               side_effect=self._error(503)) as abrir, \
             mock.patch.object(sales_agent.time, "sleep"):
            with self.assertRaises(sales_agent.ErrorAPI):
                sales_agent.llamar_api("clave-falsa", {"model": "x"})
        self.assertEqual(abrir.call_count, 3)

    def test_un_400_no_se_reintenta_ni_pausa(self) -> None:
        with mock.patch.object(sales_agent.urllib.request, "urlopen",
                               side_effect=self._error(400)) as abrir, \
             mock.patch.object(sales_agent.time, "sleep") as dormir:
            with self.assertRaises(sales_agent.ErrorAPI):
                sales_agent.llamar_api("clave-falsa", {"model": "x"})
        self.assertEqual(abrir.call_count, 1)
        self.assertEqual(dormir.call_count, 0)


# --------------------------------------------------------------- 8. costo y prompt

class TestCostoYPrompt(unittest.TestCase):
    def test_el_costo_sale_de_la_tabla_de_precios(self) -> None:
        uso = {"input_tokens": 1_000_000, "output_tokens": 0}
        self.assertAlmostEqual(sales_agent.calcular_costo_usd("claude-sonnet-5", uso), 2.00, places=6)
        uso = {"input_tokens": 0, "output_tokens": 1_000_000}
        self.assertAlmostEqual(sales_agent.calcular_costo_usd("claude-sonnet-5", uso), 10.00, places=6)
        self.assertEqual(sales_agent.calcular_costo_usd("claude-sonnet-5", {}), 0.0)

    def test_el_system_prompt_no_lleva_precios_del_dueno(self) -> None:
        prompt = sales_agent.construir_system_prompt()
        self.assertIn("Alcance del agente", prompt)
        precios = PROJECT_ROOT / "contexto" / "precios-del-dueño.md"
        if precios.exists():
            primera = next((l.strip() for l in precios.read_text(encoding="utf-8").splitlines()
                            if l.strip() and not l.startswith("#")), "")
            if primera:
                self.assertNotIn(primera, prompt, "el prompt filtró el archivo de precios")

    def test_los_nombres_de_herramientas_viajan_en_ascii(self) -> None:
        for h in sales_agent.HERRAMIENTAS:
            with self.subTest(h=h["name"]):
                self.assertTrue(h["name"].isascii())
                self.assertTrue(h["name"].replace("_", "").isalnum())


# --------------------------------------------------------------- 9. la baja va antes de los topes

class TestLaBajaNoDependeDeLosTopes(BaseConBDTemporal):
    """Dar de baja cuesta 0 USD y 0 correos: ningún tope puede impedirlo."""

    def _esperar_baja(self, lead: dict, resultado: dict) -> None:
        self.assertTrue(resultado["ok"], resultado)
        self.assertEqual(resultado["motivo"], "baja_pedida_por_el_lead")
        self.assertEqual(resultado["costo_usd"], 0.0)
        self.assertEqual(database.get_lead_by_email(lead["email"])["stage"], "baja")
        self.assertEqual(self.estados_outbox(lead["email"]), ["cancelled"])
        self.assertEqual(self.estados_followups(lead["id"]), ["cancelado"])

    def _lead_con_pendientes(self) -> dict:
        lead = self.crear_lead()
        database.enqueue_email(recipient=lead["email"], subject="x", body="y")
        database.schedule_followup(lead["id"], 3, "insistir")
        return lead

    def test_se_procesa_con_el_tope_de_correos_lleno(self) -> None:
        lead = self._lead_con_pendientes()
        for _ in range(15):
            database.log_agent_action(lead_id=lead["id"], turno=1, modelo="claude-sonnet-5",
                                      herramienta="enviar_correo", resultado="encolado")
        self.assertEqual(database.agent_emails_queued_today(), 15)
        with mock.patch.object(sales_agent, "llamar_api",
                               side_effect=AssertionError("llamó a la API para dar de baja")) as api:
            resultado = self.agente().correr(lead_email=lead["email"], mensaje_lead="BAJA")
        self.assertEqual(api.call_count, 0)
        self._esperar_baja(lead, resultado)

    def test_se_procesa_con_el_tope_de_usd_lleno(self) -> None:
        lead = self._lead_con_pendientes()
        database.log_agent_action(lead_id=lead["id"], turno=1, modelo="claude-sonnet-5",
                                  herramienta="llamada_api", costo_usd=0.50)
        resultado = self.agente().correr(lead_email=lead["email"],
                                         mensaje_lead="Quiero darme de baja, gracias.")
        self._esperar_baja(lead, resultado)

    def test_se_procesa_sin_api_key(self) -> None:
        lead = self._lead_con_pendientes()
        agente = sales_agent.AgenteVentas(dict(CFG_FALSA, ANTHROPIC_API_KEY=""))
        self._esperar_baja(lead, agente.correr(lead_email=lead["email"], mensaje_lead="stop"))

    def test_en_dry_run_la_baja_no_toca_la_bd(self) -> None:
        lead = self._lead_con_pendientes()
        resultado = self.agente(dry_run=True).correr(lead_email=lead["email"], mensaje_lead="BAJA")
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["motivo"], "baja_pedida_por_el_lead")
        self.assertEqual(database.get_lead_by_email(lead["email"])["stage"], "nuevo_lead")
        self.assertEqual(self.estados_outbox(lead["email"]), ["pending"])
        self.assertEqual(self.estados_followups(lead["id"]), ["pendiente"])

    def test_una_baja_de_alguien_que_no_esta_en_la_bd_no_crea_el_lead(self) -> None:
        resultado = self.agente().correr(lead_email="desconocido@ejemplo.com", mensaje_lead="BAJA")
        self.assertTrue(resultado["ok"])
        self.assertIsNone(database.get_lead_by_email("desconocido@ejemplo.com"))


# --------------------------------------------------------------- 10. enganche en el dispatcher

class TestClasificacionDeBaja(unittest.TestCase):
    def test_el_dispatcher_clasifica_la_baja(self) -> None:
        for cuerpo in ("BAJA", "baja por favor", "darme de baja", "no me escriban mas"):
            with self.subTest(cuerpo=cuerpo):
                self.assertEqual(
                    autopilot_dispatcher.classify_reply_intent("Re: propuesta", cuerpo), "baja")

    def test_no_clasifica_baja_una_frase_normal(self) -> None:
        intent = autopilot_dispatcher.classify_reply_intent(
            "Re: render", "Tengo una foto de baja resolución, sirve?")
        self.assertNotEqual(intent, "baja")

    def test_un_autorespondedor_no_es_una_baja(self) -> None:
        intent = autopilot_dispatcher.classify_reply_intent(
            "Fuera de oficina", "Estoy fuera de oficina. unsubscribe")
        self.assertEqual(intent, "respuesta_automatica")


class BaseDispatcherEnSeco(BaseConBDTemporal):
    """BD temporal + cero red: SMTP, IMAP y la API quedan mockeados."""

    CFG_SMTP = {
        "SMTP_HOST": "smtp.ejemplo.com", "SMTP_PORT": "587", "SMTP_USER": "yo@ejemplo.com",
        "SMTP_PASS": "x", "SMTP_FROM": "yo@ejemplo.com", "MAX_DAILY_EMAILS": "15",
    }

    def setUp(self) -> None:
        super().setUp()
        self.cfg = dict(self.CFG_SMTP)
        self.parche_env = mock.patch.object(autopilot_dispatcher, "load_env_file",
                                            side_effect=lambda: dict(self.cfg))
        self.parche_smtp = mock.patch.object(autopilot_dispatcher, "send_smtp_email")
        self.parche_notif_d = mock.patch.object(autopilot_dispatcher, "notify_mac_desktop",
                                                return_value=True)
        self.parche_cal_d = mock.patch.object(autopilot_dispatcher, "create_calendar_event",
                                              return_value=True)
        self.parche_env.start()
        self.smtp = self.parche_smtp.start()
        self.parche_notif_d.start()
        self.parche_cal_d.start()
        for parche in (self.parche_cal_d, self.parche_notif_d, self.parche_smtp, self.parche_env):
            self.addCleanup(parche.stop)


class TestDobleSeguroAlEnviar(BaseDispatcherEnSeco):
    def test_no_envia_a_un_lead_que_paso_a_baja_y_cancela_el_job(self) -> None:
        for email, stage, rebotado in (("b@ejemplo.com", "baja", False),
                                       ("n@ejemplo.com", "no_interesado", False),
                                       ("r@ejemplo.com", "nuevo_lead", True)):
            with self.subTest(email=email):
                self.crear_lead(email=email, stage=stage)
                if rebotado:
                    database.mark_lead_bounced(email, "550 user unknown")
                database.enqueue_email(recipient=email, subject="Hola", body="Te escribo.")
                res = autopilot_dispatcher.dispatch_due_jobs()
                self.assertEqual(res["sent"], 0, "le envió a un lead cerrado")
                self.assertEqual(self.estados_outbox(email), ["cancelled"])
        self.assertEqual(self.smtp.call_count, 0)

    def test_al_lead_activo_si_le_envia(self) -> None:
        self.crear_lead(email="ok@ejemplo.com", stage="nuevo_lead")
        database.enqueue_email(recipient="ok@ejemplo.com", subject="Hola", body="Te escribo.")
        res = autopilot_dispatcher.dispatch_due_jobs()
        self.assertEqual(res["sent"], 1, res)
        self.assertEqual(res["cancelled_closed_lead"], 0)
        self.assertEqual(self.smtp.call_count, 1)
        self.assertEqual(self.estados_outbox("ok@ejemplo.com"), ["sent"])


class TestCancelacionDeSeguimientosAlResponder(BaseDispatcherEnSeco):
    """sync_imap_replies con un IMAP falso: toda respuesta mata los seguimientos."""

    def _correo_falso(self, remitente: str, asunto: str, cuerpo: str) -> bytes:
        return (f"From: {remitente}\r\nSubject: {asunto}\r\n"
                f"Message-ID: <{abs(hash(cuerpo))}@ejemplo.com>\r\n"
                f"Content-Type: text/plain; charset=utf-8\r\n\r\n{cuerpo}\r\n").encode("utf-8")

    def _imap_falso(self, crudo: bytes):
        imap = mock.MagicMock()
        imap.__enter__.return_value = imap
        imap.__exit__.return_value = False
        imap.search.return_value = ("OK", [b"1"])
        imap.fetch.return_value = ("OK", [(b"1 (RFC822 {0}", crudo)])
        return imap

    def _sincronizar(self, cuerpo: str, *, con_api_key: bool = False) -> dict:
        self.cfg.update({"IMAP_HOST": "imap.ejemplo.com"})
        if con_api_key:
            self.cfg["ANTHROPIC_API_KEY"] = "clave-de-prueba-no-sirve"
        crudo = self._correo_falso("lead@ejemplo.com", "Re: propuesta", cuerpo)
        with mock.patch.object(autopilot_dispatcher.imaplib, "IMAP4_SSL",
                               return_value=self._imap_falso(crudo)):
            return autopilot_dispatcher.sync_imap_replies()

    def test_una_respuesta_cancela_outbox_y_seguimientos(self) -> None:
        lead = self.crear_lead()
        database.enqueue_email(recipient=lead["email"], subject="x", body="y")
        database.schedule_followup(lead["id"], 3, "insistir")
        res = self._sincronizar("Me interesa, agendemos una llamada.")
        self.assertEqual(res["matched"], 1, res)
        self.assertEqual(self.estados_outbox(lead["email"]), ["cancelled"])
        self.assertEqual(self.estados_followups(lead["id"]), ["cancelado"])

    def test_una_baja_cancela_todo_y_no_llama_al_agente(self) -> None:
        lead = self.crear_lead()
        database.enqueue_email(recipient=lead["email"], subject="x", body="y")
        database.schedule_followup(lead["id"], 3, "insistir")
        with mock.patch.object(sales_agent, "llamar_api",
                               side_effect=AssertionError("llamó a la API por una baja")) as api:
            res = self._sincronizar("BAJA", con_api_key=True)
        self.assertEqual(api.call_count, 0)
        self.assertEqual(res["agent_runs"], 0)
        self.assertEqual(database.get_lead_by_email(lead["email"])["stage"], "baja")
        self.assertEqual(self.estados_outbox(lead["email"]), ["cancelled"])
        self.assertEqual(self.estados_followups(lead["id"]), ["cancelado"])

    def test_una_respuesta_interesada_si_invoca_al_agente(self) -> None:
        self.crear_lead()
        with mock.patch.object(sales_agent.AgenteVentas, "correr",
                               return_value={"ok": True}) as correr:
            res = self._sincronizar("Me interesa, agendemos una llamada.", con_api_key=True)
        self.assertEqual(res["agent_runs"], 1, res)
        self.assertEqual(correr.call_count, 1)
        self.assertEqual(correr.call_args.kwargs["lead_email"], "lead@ejemplo.com")

    def test_sin_api_key_no_se_invoca_al_agente(self) -> None:
        self.crear_lead()
        with mock.patch.object(sales_agent.AgenteVentas, "correr") as correr:
            res = self._sincronizar("Me interesa, agendemos una llamada.")
        self.assertEqual(correr.call_count, 0)
        self.assertEqual(res["agent_runs"], 0)

    def test_si_el_agente_revienta_el_sync_sigue_vivo(self) -> None:
        lead = self.crear_lead()
        with mock.patch.object(sales_agent.AgenteVentas, "correr",
                               side_effect=RuntimeError("el agente explotó")):
            res = self._sincronizar("Me interesa, agendemos una llamada.", con_api_key=True)
        self.assertEqual(res["matched"], 1, res)
        self.assertNotIn("error", res)
        self.assertEqual(res["agent_runs"], 0)
        self.assertEqual(database.get_lead_by_email(lead["email"])["stage"], "interesado_cita")


class TestCicloDelAgente(BaseDispatcherEnSeco):
    def setUp(self) -> None:
        super().setUp()
        self.cfg["ANTHROPIC_API_KEY"] = "clave-de-prueba-no-sirve"
        # La ventana horaria no puede hacer fallar la batería según la hora del día.
        self.parche_ventana = mock.patch.object(autopilot_dispatcher, "_is_within_sending_window",
                                                return_value=True)
        self.parche_ventana.start()
        self.addCleanup(self.parche_ventana.stop)
        # cargar_config leería el .env real: se fuerza la cfg de prueba.
        self.parche_cfg = mock.patch.object(sales_agent, "cargar_config",
                                            side_effect=lambda: dict(self.cfg))
        self.parche_cfg.start()
        self.addCleanup(self.parche_cfg.stop)

    def _vencer_seguimiento(self, lead_id: int) -> int:
        fid = database.schedule_followup(lead_id, 1, "insistir")
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE agent_followups SET programado_para='2000-01-01 00:00:00' WHERE id=?",
                        (fid,))
        return fid

    def test_sin_api_key_sale_limpio(self) -> None:
        self.cfg.pop("ANTHROPIC_API_KEY")
        res = autopilot_dispatcher.run_sales_agent_cycle()
        self.assertFalse(res["ran"])
        self.assertEqual(res["reason"], "sin_api_key")

    def test_fuera_de_la_ventana_no_corre(self) -> None:
        with mock.patch.object(autopilot_dispatcher, "_is_within_sending_window",
                               return_value=False):
            res = autopilot_dispatcher.run_sales_agent_cycle()
        self.assertFalse(res["ran"])
        self.assertEqual(res["reason"], "outside_window")

    def test_procesa_un_seguimiento_vencido_y_lo_marca_hecho(self) -> None:
        lead = self.crear_lead(stage="contactado")
        fid = self._vencer_seguimiento(lead["id"])
        with mock.patch.object(sales_agent.AgenteVentas, "correr",
                               return_value={"ok": True}) as correr:
            res = autopilot_dispatcher.run_sales_agent_cycle()
        self.assertEqual(res["followups_corridos"], 1, res)
        self.assertEqual(correr.call_args.kwargs["lead_email"], lead["email"])
        with sqlite3.connect(self.db) as con:
            estado = con.execute("SELECT estado FROM agent_followups WHERE id=?", (fid,)).fetchone()[0]
        self.assertEqual(estado, "hecho")

    def test_un_seguimiento_de_lead_cerrado_se_cancela_sin_api(self) -> None:
        for email, stage, rebotado in (("b@ejemplo.com", "baja", False),
                                       ("n@ejemplo.com", "no_interesado", False),
                                       ("r@ejemplo.com", "contactado", True)):
            with self.subTest(email=email):
                lead = self.crear_lead(email=email, stage=stage)
                if rebotado:
                    database.mark_lead_bounced(email, "rebote")
                fid = self._vencer_seguimiento(lead["id"])
                with mock.patch.object(sales_agent, "llamar_api",
                                       side_effect=AssertionError("llamó a la API")) as api:
                    res = autopilot_dispatcher.run_sales_agent_cycle()
                self.assertEqual(api.call_count, 0)
                self.assertGreaterEqual(res["followups_cancelados"], 1, res)
                with sqlite3.connect(self.db) as con:
                    estado = con.execute("SELECT estado FROM agent_followups WHERE id=?",
                                         (fid,)).fetchone()[0]
                self.assertEqual(estado, "cancelado")

    def test_corre_los_leads_nuevos_en_frio_hasta_el_maximo(self) -> None:
        for i in range(4):
            self.crear_lead(email=f"frio{i}@ejemplo.com")
        with mock.patch.object(sales_agent.AgenteVentas, "correr",
                               return_value={"ok": True}) as correr:
            res = autopilot_dispatcher.run_sales_agent_cycle(max_leads=2)
        self.assertEqual(res["leads_en_frio"], 2, res)
        self.assertEqual(correr.call_count, 2)

    def test_no_toca_un_lead_con_correo_pendiente(self) -> None:
        self.crear_lead(email="conpendiente@ejemplo.com")
        database.enqueue_email(recipient="conpendiente@ejemplo.com", subject="x", body="y")
        with mock.patch.object(sales_agent.AgenteVentas, "correr",
                               return_value={"ok": True}) as correr:
            res = autopilot_dispatcher.run_sales_agent_cycle()
        self.assertEqual(res["leads_en_frio"], 0, res)
        self.assertEqual(correr.call_count, 0)

    def test_corta_de_inmediato_con_el_tope_de_correos_lleno(self) -> None:
        self.crear_lead()
        for _ in range(15):
            database.log_agent_action(lead_id=1, turno=1, modelo="claude-sonnet-5",
                                      herramienta="enviar_correo", resultado="encolado")
        with mock.patch.object(sales_agent.AgenteVentas, "correr") as correr:
            res = autopilot_dispatcher.run_sales_agent_cycle()
        self.assertEqual(res["cortado_por"], "tope_correos", res)
        self.assertEqual(correr.call_count, 0)

    def test_corta_de_inmediato_con_el_tope_de_usd_lleno(self) -> None:
        self.crear_lead()
        database.log_agent_action(lead_id=1, turno=1, modelo="claude-sonnet-5",
                                  herramienta="llamada_api", costo_usd=0.50)
        with mock.patch.object(sales_agent.AgenteVentas, "correr") as correr:
            res = autopilot_dispatcher.run_sales_agent_cycle()
        self.assertEqual(res["cortado_por"], "tope_usd", res)
        self.assertEqual(correr.call_count, 0)

    def test_en_dry_run_no_marca_el_seguimiento_ni_llama_a_la_api(self) -> None:
        lead = self.crear_lead(stage="contactado")
        fid = self._vencer_seguimiento(lead["id"])
        with mock.patch.object(sales_agent, "llamar_api",
                               side_effect=AssertionError("el dry-run llamó a la API")) as api:
            res = autopilot_dispatcher.run_sales_agent_cycle(dry_run=True)
        self.assertEqual(api.call_count, 0)
        self.assertTrue(res["dry_run"])
        self.assertEqual(res["followups_corridos"], 1, res)
        with sqlite3.connect(self.db) as con:
            estado = con.execute("SELECT estado FROM agent_followups WHERE id=?", (fid,)).fetchone()[0]
        self.assertEqual(estado, "pendiente", "el dry-run marcó el seguimiento")


class TestCicloDelAgenteNoTocaLaBDReal(unittest.TestCase):
    """`--run-agent --dry-run` corrido como lo correría Raymond, contra la BD de verdad."""

    def test_cli_run_agent_dry_run_no_modifica_la_bd(self) -> None:
        antes_huella, antes_filas = huella(DB_REAL), contar_filas(DB_REAL)
        existia = DB_REAL.exists()
        proc = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "autopilot_dispatcher.py"),
             "--run-agent", "--dry-run"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=120,
            env=dict(os.environ, ELSOCIO_QUIET="1"),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        salida = json.loads(proc.stdout)
        self.assertIn("ran", salida)
        self.assertEqual(DB_REAL.exists(), existia, "el dry-run creó data/el_socio.db")
        self.assertEqual(huella(DB_REAL), antes_huella, "el dry-run modificó data/el_socio.db")
        self.assertEqual(contar_filas(DB_REAL), antes_filas, "el dry-run creó filas")


if __name__ == "__main__":
    unittest.main(verbosity=2)

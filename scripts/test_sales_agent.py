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
    ]
    PERMITIDOS = [
        "Mil gracias", "web oficial",
        "Hola, vi tu catalogo y creo que puedo ayudarte con las fichas tecnicas.",
        "Te dejo ejemplos en https://reyvonblon.github.io/Elsocio/",
        "Escribeme por https://wa.me/573001112233",
        "Mil gracias por responder, te mando 3 opciones de render.",
        "En 2026 arrancamos con el catalogo",
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


if __name__ == "__main__":
    unittest.main(verbosity=2)

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
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import autopilot_dispatcher  # noqa: E402
import database  # noqa: E402
import sales_agent  # noqa: E402

DB_REAL = PROJECT_ROOT / "data" / "el_socio.db"
RESULTADOS_REAL = PROJECT_ROOT / "contexto" / "RESULTADOS_MERCADO.md"
TABLAS_VIGILADAS = ("leads", "outbox", "agent_log", "agent_followups")

# Cabecera mínima del archivo temporal de resultados: la misma forma que el real.
CABECERA_RESULTADOS = (
    "# Resultados de mercado\n\n## Registro\n"
    "<!-- filas al FINAL. Nada debajo de la tabla. -->\n"
    "| Fecha | Nicho | Ángulo usado | Canal | Cantidad | Resultado | Nota |\n"
    "|---|---|---|---|---|---|---|\n"
    "| 2026-01-01 | fila-que-ya-estaba | no se toca | correo | 3 | silencio | Intocable. |\n"
)

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
        # RESULTADOS_MERCADO.md temporal: ninguna prueba escribe en el archivo real.
        self.resultados = Path(self.tmp.name) / "RESULTADOS_MERCADO.md"
        self.resultados.write_text(CABECERA_RESULTADOS, encoding="utf-8")
        self.parche_resultados = mock.patch.object(autopilot_dispatcher, "RESULTADOS_FILE",
                                                   self.resultados)
        self.parche_resultados.start()
        # Red de seguridad: si una prueba se salta el parche, falla aquí y no en silencio.
        self.addCleanup(self._verificar_resultados_reales_intactos, huella(RESULTADOS_REAL))
        self.addCleanup(self.parche_resultados.stop)
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

    def _verificar_resultados_reales_intactos(self, antes: str) -> None:
        self.assertEqual(huella(RESULTADOS_REAL), antes,
                         "una prueba escribió en contexto/RESULTADOS_MERCADO.md")

    def filas_resultados(self) -> list[str]:
        return [l for l in self.resultados.read_text(encoding="utf-8").splitlines()
                if l.startswith("| 20")]

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
        self.notif = self.parche_notif_d.start()
        self.cal = self.parche_cal_d.start()
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


# ------------------------------------------- 11. el contacto en frío no se repite nunca

class TestContactoEnFrioNoSeRepite(BaseConBDTemporal):
    """Hallazgo del Paso 5: el filtro mirava solo 'hoy', así que un lead contactado ayer
    volvía a salir en frío cada mañana = spam diario a la misma dirección.
    """

    def _enviado_el(self, email: str, cuando: str) -> None:
        database.enqueue_email(recipient=email, subject="Hola", body="Te escribo.")
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE outbox SET status='sent', created_at=?, scheduled_for=? "
                        "WHERE recipient=?", (cuando, cuando, email))

    def test_un_lead_contactado_ayer_no_vuelve_a_salir_en_frio(self) -> None:
        self.crear_lead(email="ayer@ejemplo.com")
        ayer = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        self._enviado_el("ayer@ejemplo.com", ayer)
        correos = [l["email"] for l in database.list_cold_leads_for_agent(limit=20)]
        self.assertNotIn("ayer@ejemplo.com", correos)

    def test_tampoco_vuelve_a_salir_el_contactado_hace_meses(self) -> None:
        self.crear_lead(email="viejo@ejemplo.com")
        hace_meses = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d %H:%M:%S")
        self._enviado_el("viejo@ejemplo.com", hace_meses)
        self.assertEqual(database.list_cold_leads_for_agent(limit=20), [])

    def test_el_que_nunca_recibio_nada_si_sale(self) -> None:
        self.crear_lead(email="virgen@ejemplo.com")
        correos = [l["email"] for l in database.list_cold_leads_for_agent(limit=20)]
        self.assertEqual(correos, ["virgen@ejemplo.com"])

    def test_el_filtro_no_se_confunde_con_mayusculas_ni_espacios(self) -> None:
        self.crear_lead(email="mix@ejemplo.com")
        with sqlite3.connect(self.db) as con:
            con.execute("INSERT INTO outbox (recipient, status, created_at) "
                        "VALUES (' MIX@Ejemplo.com ', 'sent', '2020-01-01 10:00:00')")
        self.assertEqual(database.list_cold_leads_for_agent(limit=20), [])

    def test_un_correo_cancelado_no_bloquea_el_contacto_en_frio(self) -> None:
        self.crear_lead(email="cancel@ejemplo.com")
        database.enqueue_email(recipient="cancel@ejemplo.com", subject="x", body="y")
        database.cancel_pending_outbox_for_recipient("cancel@ejemplo.com")
        correos = [l["email"] for l in database.list_cold_leads_for_agent(limit=20)]
        self.assertEqual(correos, ["cancel@ejemplo.com"])


class TestEtapaAutomaticaAlContactar(BaseConBDTemporal):
    def test_el_correo_en_frio_mueve_el_lead_a_contactado(self) -> None:
        lead = self.crear_lead(email="frio@ejemplo.com")
        agente = self.agente()
        agente.lead = dict(lead)
        ok, _ = agente._tool_enviar_correo(
            {"asunto": "Una idea para tu local", "cuerpo": "Hola, te escribo por tus renders."},
            es_frio=True)
        self.assertTrue(ok)
        self.assertEqual(database.get_lead_by_email("frio@ejemplo.com")["stage"], "contactado")
        self.assertEqual(agente.lead["stage"], "contactado")
        # Y por lo tanto ya no vuelve a aparecer como lead en frío.
        self.assertEqual(database.list_cold_leads_for_agent(limit=20), [])

    def test_una_respuesta_no_cambia_la_etapa_sola(self) -> None:
        lead = self.crear_lead(email="resp@ejemplo.com", stage="conversando")
        agente = self.agente()
        agente.lead = dict(lead)
        ok, _ = agente._tool_enviar_correo(
            {"asunto": "Te respondo", "cuerpo": "Claro que sí, lo vemos."}, es_frio=False)
        self.assertTrue(ok)
        self.assertEqual(database.get_lead_by_email("resp@ejemplo.com")["stage"], "conversando")

    def test_en_dry_run_la_etapa_no_se_mueve(self) -> None:
        lead = self.crear_lead(email="seco@ejemplo.com")
        agente = self.agente(dry_run=True)
        agente.lead = dict(lead)
        ok, _ = agente._tool_enviar_correo(
            {"asunto": "Idea", "cuerpo": "Hola, te escribo."}, es_frio=True)
        self.assertTrue(ok)
        self.assertEqual(database.get_lead_by_email("seco@ejemplo.com")["stage"], "nuevo_lead")


# ------------------------------------------------- 12. --dry-run del motor completo

class TestDryRunDelMotor(BaseDispatcherEnSeco):
    """`autopilot_dispatcher.py --dry-run` sin `--run-agent` solo puede mirar."""

    def _correr_main(self, *flags: str) -> dict:
        with mock.patch.object(sys, "argv", ["autopilot_dispatcher.py", *flags]), \
             mock.patch.object(autopilot_dispatcher, "ensure_daily_pipeline",
                               return_value={}) as llenar, \
             mock.patch.object(autopilot_dispatcher, "dispatch_due_jobs",
                               return_value={}) as despachar, \
             mock.patch.object(autopilot_dispatcher, "sync_landing_messages",
                               return_value={}) as landing, \
             mock.patch("builtins.print") as imprimir:
            autopilot_dispatcher.main()
        return {"llenar": llenar, "despachar": despachar, "landing": landing,
                "salida": json.loads(imprimir.call_args[0][0])}

    def test_dry_run_no_llena_la_cola_ni_despacha_ni_toca_la_landing(self) -> None:
        res = self._correr_main("--dry-run")
        self.assertEqual(res["llenar"].call_count, 0, "--dry-run llamó a ensure_daily_pipeline")
        self.assertEqual(res["despachar"].call_count, 0, "--dry-run llamó a dispatch_due_jobs")
        self.assertEqual(res["landing"].call_count, 0, "--dry-run llamó a sync_landing_messages")
        self.assertEqual(self.smtp.call_count, 0, "--dry-run abrió SMTP")
        self.assertTrue(res["salida"]["dry_run"])

    def test_el_resumen_en_seco_cuenta_lo_que_hay_sin_escribir(self) -> None:
        self.crear_lead(email="frio1@ejemplo.com")
        antes = contar_filas(self.db)
        res = self._correr_main("--dry-run")
        self.assertEqual(res["salida"]["leads_en_frio_disponibles"], 1, res["salida"])
        self.assertEqual(contar_filas(self.db), antes, "el resumen en seco escribió en la BD")
        self.assertEqual(self.filas_resultados(), [l for l in CABECERA_RESULTADOS.splitlines()
                                                   if l.startswith("| 20")])

    def test_sin_dry_run_si_corre_el_motor_de_verdad(self) -> None:
        res = self._correr_main()
        self.assertEqual(res["llenar"].call_count, 1)
        self.assertEqual(res["despachar"].call_count, 1)

    def test_el_ciclo_del_agente_en_seco_no_crea_la_bd(self) -> None:
        with mock.patch.object(database, "DB_PATH", Path(self.tmp.name) / "no-existe.db"):
            res = autopilot_dispatcher.run_sales_agent_cycle(dry_run=True)
            self.assertFalse(res["ran"])
            self.assertEqual(res["reason"], "dry_run_sin_bd")
            self.assertFalse((Path(self.tmp.name) / "no-existe.db").exists())


class TestDryRunDelMotorNoTocaNadaReal(unittest.TestCase):
    """`autopilot_dispatcher.py --dry-run` corrido como lo correría Raymond."""

    def test_cli_dry_run_no_modifica_la_bd_ni_los_resultados(self) -> None:
        antes_db, antes_filas = huella(DB_REAL), contar_filas(DB_REAL)
        antes_md = huella(RESULTADOS_REAL)
        existia = DB_REAL.exists()
        proc = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "autopilot_dispatcher.py"), "--dry-run"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=120,
            env=dict(os.environ, ELSOCIO_QUIET="1"),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(json.loads(proc.stdout)["dry_run"])
        self.assertEqual(DB_REAL.exists(), existia, "el dry-run creó data/el_socio.db")
        self.assertEqual(huella(DB_REAL), antes_db, "el dry-run modificó data/el_socio.db")
        self.assertEqual(contar_filas(DB_REAL), antes_filas, "el dry-run creó filas")
        self.assertEqual(huella(RESULTADOS_REAL), antes_md,
                         "el dry-run escribió en RESULTADOS_MERCADO.md")


# ------------------------------------------------- 13. seguimientos y motivo

class TestSeguimientosBienManejados(TestCicloDelAgente):
    def test_si_el_agente_falla_el_seguimiento_queda_pendiente(self) -> None:
        lead = self.crear_lead(stage="contactado")
        fid = self._vencer_seguimiento(lead["id"])
        with mock.patch.object(sales_agent.AgenteVentas, "correr",
                               return_value={"ok": False, "motivo": "API: HTTP 529"}):
            res = autopilot_dispatcher.run_sales_agent_cycle()
        self.assertEqual(res["followups_corridos"], 0, res)
        self.assertEqual(res["followups_fallidos"], 1, res)
        with sqlite3.connect(self.db) as con:
            estado = con.execute("SELECT estado FROM agent_followups WHERE id=?", (fid,)).fetchone()[0]
        self.assertEqual(estado, "pendiente", "se marcó 'hecho' un seguimiento que no salió")

    def test_si_el_agente_revienta_el_seguimiento_queda_pendiente(self) -> None:
        lead = self.crear_lead(stage="contactado")
        fid = self._vencer_seguimiento(lead["id"])
        with mock.patch.object(sales_agent.AgenteVentas, "correr",
                               side_effect=RuntimeError("se cayó la red")):
            res = autopilot_dispatcher.run_sales_agent_cycle()
        self.assertEqual(res["followups_corridos"], 0, res)
        with sqlite3.connect(self.db) as con:
            estado = con.execute("SELECT estado FROM agent_followups WHERE id=?", (fid,)).fetchone()[0]
        self.assertEqual(estado, "pendiente")

    def test_el_seguimiento_llega_con_su_motivo(self) -> None:
        lead = self.crear_lead(stage="contactado")
        database.schedule_followup(lead["id"], 1, "le mandé el ejemplo de render")
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE agent_followups SET programado_para='2000-01-01 00:00:00'")
        with mock.patch.object(sales_agent.AgenteVentas, "correr",
                               return_value={"ok": True}) as correr:
            autopilot_dispatcher.run_sales_agent_cycle()
        self.assertEqual(correr.call_args.kwargs["motivo_seguimiento"],
                         "le mandé el ejemplo de render")

    def test_un_lead_en_frio_no_lleva_motivo_de_seguimiento(self) -> None:
        self.crear_lead(email="frio@ejemplo.com")
        with mock.patch.object(sales_agent.AgenteVentas, "correr",
                               return_value={"ok": True}) as correr:
            autopilot_dispatcher.run_sales_agent_cycle()
        self.assertEqual(correr.call_args.kwargs["motivo_seguimiento"], "")


class TestContextoDelSeguimiento(BaseConBDTemporal):
    """El modelo tiene que saber que un seguimiento NO es un primer contacto."""

    def _contexto(self, **kwargs) -> str:
        self.crear_lead(email="seg@ejemplo.com", stage="contactado")
        agente = self.agente()
        capturado = {}

        def espia(api_key, cuerpo):
            capturado["texto"] = cuerpo["messages"][0]["content"]
            return respuesta_falsa(stop="end_turn")

        with mock.patch.object(sales_agent, "llamar_api", side_effect=espia):
            agente.correr(lead_email="seg@ejemplo.com", **kwargs)
        return capturado.get("texto", "")

    def test_con_motivo_el_contexto_dice_que_es_un_seguimiento(self) -> None:
        texto = self._contexto(motivo_seguimiento="le mandé el ejemplo de render")
        self.assertIn("SEGUIMIENTO programado", texto)
        self.assertIn("le mandé el ejemplo de render", texto)
        self.assertNotIn("primer contacto en frío. Escríbele", texto)

    def test_sin_motivo_sigue_siendo_primer_contacto_en_frio(self) -> None:
        texto = self._contexto()
        self.assertIn("primer contacto en frío", texto)
        self.assertNotIn("SEGUIMIENTO programado", texto)

    def test_el_seguimiento_tambien_lleva_linea_de_baja(self) -> None:
        self.crear_lead(email="seg2@ejemplo.com", stage="contactado")
        agente = self.agente()
        respuestas = [
            respuesta_falsa(bloque_tool("enviar_correo",
                                        {"asunto": "Retomo lo del render",
                                         "cuerpo": "Te escribí la semana pasada, sigo disponible."})),
            respuesta_falsa(stop="end_turn"),
        ]
        with mock.patch.object(sales_agent, "llamar_api", side_effect=respuestas):
            agente.correr(lead_email="seg2@ejemplo.com", motivo_seguimiento="insistir una vez")
        with sqlite3.connect(self.db) as con:
            cuerpo = con.execute("SELECT body FROM outbox WHERE recipient='seg2@ejemplo.com'").fetchone()[0]
        self.assertIn("BAJA", cuerpo)


# ------------------------------------------------- 14. clasificación que cuida el saldo

class TestClasificacionQueCuidaElSaldo(unittest.TestCase):
    def test_una_pregunta_de_precio_es_un_interesado(self) -> None:
        for cuerpo in ("¿Cuánto cuesta un render?", "cuanto cuesta eso?", "Mándame precios",
                       "¿cuál es el precio?", "Cuéntame más", "necesito fichas técnicas",
                       "¿me puedes ayudar con unas fotos?", "¿tienen ejemplos?",
                       "quiero más información", "¿pueden hacer un render de mi local?"):
            with self.subTest(cuerpo=cuerpo):
                self.assertEqual(
                    autopilot_dispatcher.classify_reply_intent("Re: propuesta", cuerpo),
                    "interesado_cita")

    def test_el_ruido_de_bandeja_sigue_siendo_ruido(self) -> None:
        for cuerpo in ("ok recibido", "Listo, gracias.", "Adjunto la factura del mes.",
                       "Reenvío este correo."):
            with self.subTest(cuerpo=cuerpo):
                self.assertEqual(
                    autopilot_dispatcher.classify_reply_intent("Re: propuesta", cuerpo),
                    "respuesta_recibida")

    def test_el_ruido_no_esta_en_la_lista_que_gasta_saldo(self) -> None:
        self.assertEqual(autopilot_dispatcher.INTENTS_PARA_EL_AGENTE, ("interesado_cita",))
        self.assertNotIn("respuesta_recibida", autopilot_dispatcher.INTENTS_PARA_EL_AGENTE)


class TestElRuidoNoGastaSaldo(TestCancelacionDeSeguimientosAlResponder):
    def test_un_ok_recibido_no_dispara_la_api(self) -> None:
        self.crear_lead()
        with mock.patch.object(sales_agent.AgenteVentas, "correr") as correr:
            res = self._sincronizar("ok recibido", con_api_key=True)
        self.assertEqual(res["matched"], 1, res)
        self.assertEqual(res["agent_runs"], 0, "el ruido de bandeja quemó saldo")
        self.assertEqual(correr.call_count, 0)
        self.assertEqual(database.get_lead_by_email("lead@ejemplo.com")["stage"],
                         "respuesta_recibida")

    def test_una_pregunta_de_precio_si_dispara_la_api(self) -> None:
        self.crear_lead()
        with mock.patch.object(sales_agent.AgenteVentas, "correr",
                               return_value={"ok": True}) as correr:
            res = self._sincronizar("¿Cuánto cuesta un render?", con_api_key=True)
        self.assertEqual(res["agent_runs"], 1, res)
        self.assertEqual(correr.call_count, 1)

    def test_el_sync_en_seco_no_escribe_ni_avisa(self) -> None:
        lead = self.crear_lead()
        database.enqueue_email(recipient=lead["email"], subject="x", body="y")
        database.schedule_followup(lead["id"], 3, "insistir")
        antes = contar_filas(self.db)
        self.cfg.update({"IMAP_HOST": "imap.ejemplo.com"})
        crudo = self._correo_falso("lead@ejemplo.com", "Re: propuesta", "Me interesa, agendemos.")
        with mock.patch.object(autopilot_dispatcher.imaplib, "IMAP4_SSL",
                               return_value=self._imap_falso(crudo)):
            res = autopilot_dispatcher.sync_imap_replies(dry_run=True)
        self.assertEqual(res["matched"], 1, res)
        self.assertEqual(contar_filas(self.db), antes, "el sync en seco escribió en la BD")
        self.assertEqual(database.get_lead_by_email(lead["email"])["stage"], "nuevo_lead")
        self.assertEqual(self.estados_outbox(lead["email"]), ["pending"])
        self.assertEqual(self.estados_followups(lead["id"]), ["pendiente"])
        self.assertEqual(self.notif.call_count, 0, "el sync en seco notificó en el Mac")
        self.assertEqual(self.cal.call_count, 0, "el sync en seco creó un evento en Calendar")
        self.assertEqual(len(self.filas_resultados()), 1, "el sync en seco registró una fila")


# ------------------------------------------------- 15. Paso 6: RESULTADOS_MERCADO.md

class TestRegistroDeResultados(BaseConBDTemporal):
    """Todo contra el archivo TEMPORAL. El real no se toca ni una vez (lo vigila la base)."""

    def registrar(self, *args, **kwargs) -> dict:
        kwargs.setdefault("ruta", self.resultados)
        return autopilot_dispatcher.registrar_resultado_mercado(*args, **kwargs)

    def test_agrega_la_fila_valida_al_final(self) -> None:
        res = self.registrar("modelado-3d-espacios", "render del local", "correo", 4,
                             "respondió", "Una respuesta real.")
        self.assertTrue(res["escrito"], res)
        lineas = self.resultados.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lineas[-1], res["fila"])
        self.assertIn("| modelado-3d-espacios | render del local | correo | 4 | respondió |",
                      lineas[-1])

    def test_no_toca_ni_borra_las_filas_que_ya_estaban(self) -> None:
        antes = self.resultados.read_text(encoding="utf-8")
        self.registrar("nicho", "angulo", "correo", 1, "rebote", "x")
        despues = self.resultados.read_text(encoding="utf-8")
        self.assertTrue(despues.startswith(antes), "reescribió o reordenó el archivo")
        self.assertIn("fila-que-ya-estaba", despues)

    def test_sanitiza_pipes_y_saltos_de_linea(self) -> None:
        res = self.registrar("ni|cho", "angulo\ncon\nsaltos", "correo", 1, "respondió",
                             "nota | con pipe\ny salto\ttab")
        self.assertTrue(res["escrito"], res)
        fila = self.resultados.read_text(encoding="utf-8").splitlines()[-1]
        self.assertEqual(fila.count("|"), 8, f"la tabla se rompió: {fila}")
        self.assertNotIn("\n", fila)
        self.assertIn("ni/cho", fila)
        self.assertIn("nota / con pipe y salto tab", fila)

    def test_la_tabla_sigue_teniendo_7_columnas_en_toda_fila(self) -> None:
        self.registrar("n", "a", "landing", 2, "agendó", "ok")
        for fila in self.filas_resultados():
            self.assertEqual(len(fila.strip("|").split("|")), 7, fila)

    def test_rechaza_un_canal_que_no_existe(self) -> None:
        for canal in ("telegram", "", "tiktok", "correo electronico"):
            with self.subTest(canal=canal):
                res = self.registrar("n", "a", canal, 1, "respondió", "x")
                self.assertFalse(res["escrito"], res)
                self.assertIn("canal inválido", res["error"])
        self.assertEqual(len(self.filas_resultados()), 1)

    def test_rechaza_un_resultado_que_no_existe(self) -> None:
        for resultado in ("vendido", "", "quizás", "cerrado"):
            with self.subTest(resultado=resultado):
                res = self.registrar("n", "a", "correo", 1, resultado, "x")
                self.assertFalse(res["escrito"], res)
                self.assertIn("resultado inválido", res["error"])
        self.assertEqual(len(self.filas_resultados()), 1)

    def test_acepta_los_cinco_canales_y_los_cinco_resultados(self) -> None:
        for canal in autopilot_dispatcher.CANALES_VALIDOS:
            for resultado in autopilot_dispatcher.RESULTADOS_VALIDOS:
                with self.subTest(canal=canal, resultado=resultado):
                    self.assertTrue(
                        self.registrar("n", "a", canal, 1, resultado, "x", dry_run=True)["dry_run"])

    def test_normaliza_el_resultado_sin_acento(self) -> None:
        res = self.registrar("n", "a", "correo", 1, "respondio", "x")
        self.assertIn("| respondió |", res["fila"])

    def test_rechaza_una_cantidad_que_no_es_un_conteo_real(self) -> None:
        for cantidad in (0, -3, "muchos", None):
            with self.subTest(cantidad=cantidad):
                res = self.registrar("n", "a", "correo", cantidad, "respondió", "x")
                self.assertFalse(res["escrito"], res)
        self.assertEqual(len(self.filas_resultados()), 1)

    def test_en_dry_run_no_escribe_en_disco(self) -> None:
        antes = self.resultados.read_text(encoding="utf-8")
        res = self.registrar("n", "a", "correo", 9, "agendó", "x", dry_run=True)
        self.assertFalse(res["escrito"])
        self.assertTrue(res["dry_run"])
        self.assertIn("| 9 | agendó |", res["fila"])
        self.assertEqual(self.resultados.read_text(encoding="utf-8"), antes)

    def test_si_el_archivo_no_existe_no_lo_inventa(self) -> None:
        inexistente = Path(self.tmp.name) / "no-esta.md"
        res = autopilot_dispatcher.registrar_resultado_mercado(
            "n", "a", "correo", 1, "respondió", "x", ruta=inexistente)
        self.assertFalse(res["escrito"])
        self.assertFalse(inexistente.exists())


class TestSilenciosReales(BaseConBDTemporal):
    """El silencio se registra con plazo cumplido y conteo real, nunca el día del envío."""

    def _enviar(self, email: str, dias_atras: int, nicho: str = "modelado-3d-espacios") -> None:
        cuando = (datetime.now() - timedelta(days=dias_atras)).strftime("%Y-%m-%d %H:%M:%S")
        database.enqueue_email(recipient=email, subject="x", body="y", nicho=nicho)
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE outbox SET status='sent', created_at=? WHERE recipient=?",
                        (cuando, email))

    def registrar(self, **kwargs) -> dict:
        kwargs.setdefault("ruta", self.resultados)
        return autopilot_dispatcher.registrar_silencios_vencidos(**kwargs)

    def test_una_tanda_de_hoy_no_se_registra_como_silencio(self) -> None:
        self._enviar("hoy@ejemplo.com", 0)
        self.assertEqual(self.registrar()["registradas"], 0)
        self.assertEqual(len(self.filas_resultados()), 1)

    def test_una_tanda_vencida_sin_respuesta_se_registra_con_el_conteo_real(self) -> None:
        for i in range(3):
            self._enviar(f"viejo{i}@ejemplo.com", 10)
        res = self.registrar()
        self.assertEqual(res["registradas"], 1, res)
        fila = self.filas_resultados()[-1]
        self.assertIn("| modelado-3d-espacios |", fila)
        self.assertIn("| correo | 3 | silencio |", fila)

    def test_no_cuenta_a_quien_si_respondio(self) -> None:
        for i in range(3):
            self._enviar(f"v{i}@ejemplo.com", 10)
        database.record_processed_reply("<m1@x>", "v1@ejemplo.com", "interesado_cita", "me interesa")
        self.registrar()
        self.assertIn("| correo | 2 | silencio |", self.filas_resultados()[-1])

    def test_el_mismo_evento_no_se_registra_dos_veces(self) -> None:
        self._enviar("v@ejemplo.com", 10)
        self.assertEqual(self.registrar()["registradas"], 1)
        self.assertEqual(self.registrar()["registradas"], 0, "duplicó la tanda")
        self.assertEqual(self.registrar()["registradas"], 0)
        self.assertEqual(len(self.filas_resultados()), 2)

    def test_en_dry_run_no_escribe_nada(self) -> None:
        self._enviar("v@ejemplo.com", 10)
        antes = self.resultados.read_text(encoding="utf-8")
        res = self.registrar(dry_run=True)
        self.assertEqual(res["registradas"], 1, res)
        self.assertEqual(self.resultados.read_text(encoding="utf-8"), antes)

    def test_sin_bd_no_inventa_nada(self) -> None:
        with mock.patch.object(database, "DB_PATH", Path(self.tmp.name) / "no-hay.db"):
            res = self.registrar()
        self.assertEqual(res["registradas"], 0)
        self.assertEqual(res["razon"], "sin_bd")


class TestRegistroDeEventosRealesDelMotor(BaseDispatcherEnSeco):
    def test_una_respuesta_interesada_queda_registrada(self) -> None:
        self.crear_lead()
        self.cfg.update({"IMAP_HOST": "imap.ejemplo.com"})
        crudo = (b"From: lead@ejemplo.com\r\nSubject: Re: propuesta\r\n"
                 b"Message-ID: <uno@ejemplo.com>\r\nContent-Type: text/plain\r\n\r\n"
                 b"Me interesa, agendemos una llamada.\r\n")
        imap = mock.MagicMock()
        imap.__enter__.return_value = imap
        imap.__exit__.return_value = False
        imap.search.return_value = ("OK", [b"1"])
        imap.fetch.return_value = ("OK", [(b"1 (RFC822 {0}", crudo)])
        with mock.patch.object(autopilot_dispatcher.imaplib, "IMAP4_SSL", return_value=imap):
            autopilot_dispatcher.sync_imap_replies()
        fila = self.filas_resultados()[-1]
        self.assertIn("| correo | 1 | respondió |", fila)
        self.assertIn("lead@ejemplo.com", fila)

    def test_un_rebote_permanente_marca_el_lead_y_queda_registrado(self) -> None:
        self.crear_lead(email="mala@ejemplo.com")
        database.enqueue_email(recipient="mala@ejemplo.com", subject="x", body="y",
                               nicho="fichas-tecnicas-ropa")
        self.smtp.side_effect = autopilot_dispatcher.smtplib.SMTPRecipientsRefused(
            {"mala@ejemplo.com": (550, b"User unknown")})
        res = autopilot_dispatcher.dispatch_due_jobs()
        self.assertEqual(res["bounced"], 1, res)
        self.assertEqual(int(database.get_lead_by_email("mala@ejemplo.com")["bounced"]), 1)
        self.assertIn("| correo | 1 | rebote |", self.filas_resultados()[-1])

    def test_un_fallo_temporal_no_es_un_rebote(self) -> None:
        self.crear_lead(email="ok@ejemplo.com")
        database.enqueue_email(recipient="ok@ejemplo.com", subject="x", body="y")
        self.smtp.side_effect = TimeoutError("se cayó la red")
        res = autopilot_dispatcher.dispatch_due_jobs()
        self.assertEqual(res["failed"], 1, res)
        self.assertEqual(res["bounced"], 0, "quemó un lead por un error temporal")
        self.assertEqual(int(database.get_lead_by_email("ok@ejemplo.com")["bounced"]), 0)
        self.assertEqual(len(self.filas_resultados()), 1)


class TestHumanizacionYAnalisisProspecto(BaseConBDTemporal):
    def test_correo_fluido_sin_tabla_520_sin_doble_firma_ni_doble_baja(self) -> None:
        crudo = (
            "Hola, estuve viendo Nuva Studio.\r\n\r\n\r\n\r\n"
            "Trabajamos renders de espacios antes de obra para estudios en Bogotá.\r\n\r\n"
            "Si quieren les muestro dos ejemplos.\r\n\r\n"
            "Si no quieren recibir más correos, solo respondan \"baja\".\r\n\r\n"
            "Saludos,\r\nEl Socio\r\n\r\n"
            "Si no quieres recibir más correos míos, respóndeme con la palabra BAJA y no te vuelvo a escribir."
        )
        texto, html_doc = autopilot_dispatcher.build_email_parts(CFG_FALSA, crudo, include_signature=True)
        self.assertNotIn("width=\"520\"", html_doc)
        self.assertNotIn("<table", html_doc.lower())
        self.assertNotIn("Verdana", html_doc)
        self.assertIn("viewport", html_doc)
        self.assertIn("<p style=", html_doc)
        self.assertNotIn("\n\n\n", texto)
        self.assertNotIn("Saludos,", texto)
        # Solo una línea de baja en todo el correo (ni duplicada ni repetida en plural + singular).
        self.assertEqual(len(re.findall(r"\bbaja\b", texto.lower())), 1, texto)
        self.assertEqual(len(re.findall(r"\bbaja\b", html_doc.lower())), 1, html_doc)
        self.assertIn("Raymond Vonblon", html_doc)

    def test_guarda_anti_ia_bloquea_cliches_vinetas_emojis_y_asunto_repetido(self) -> None:
        agente = self.agente()
        agente.lead = self.crear_lead(email="contacto@nuva.co")
        casos_malos = [
            ("duda rápida", "Hola, equipo de Nuva. Les escribo porque algo que veo mucho en estudios."),
            ("pregunta", "Una pregunta directa: ¿te gustaría una solución integral para tu negocio?"),
            ("idea", "Hola, te ayudo con:\n- Renders\n- Planos\n- Acústica"),
            ("novedad", "Hola, mira esta idea 🚀 para tu marca!!"),
            ("entusiasta", "Buen día, señores Nuva, les quiero mostrar esto!"),
            ("formal", "Buen día, señores Nuva. Quedo a su entera disposición. Saludos cordiales."),
            ("largo", "Hola " + " ".join(["palabra"] * 135)),
        ]
        for asunto, cuerpo in casos_malos:
            with self.subTest(asunto=asunto):
                ok, aviso = agente.ejecutar_herramienta(
                    "enviar_correo", {"asunto": asunto, "cuerpo": cuerpo}, es_frio=True,
                )
                self.assertFalse(ok, aviso)
                self.assertIn("calidad humana", aviso)

        # Un correo humano limpio sí pasa y se normaliza sin duplicar firma ni baja.
        ok, _ = agente.ejecutar_herramienta(
            "enviar_correo",
            {
                "asunto": "duda sobre Nuva Studio",
                "cuerpo": (
                    "Hola, vi los proyectos de mobiliario a medida de Nuva en Bogotá.\n\n"
                    "Hacemos renders rápidos antes de obra para que el cliente apruebe sin vueltas. "
                    "Si les sirve, les muestro dos ejemplos nuestros.\n\nSaludos,\nEl Socio"
                ),
            },
            es_frio=True,
        )
        self.assertTrue(ok)
        with sqlite3.connect(self.db) as con:
            guardado = con.execute("SELECT body FROM outbox ORDER BY id DESC LIMIT 1").fetchone()[0]
        self.assertNotIn("Saludos,", guardado)
        self.assertEqual(len(re.findall(r"\bbaja\b", guardado.lower())), 1, guardado)

        # Segundo lead el mismo día NO puede repetir exactamente el mismo asunto largo.
        agente.lead = self.crear_lead(email="hola@otroestudio.co")
        ok_rep, aviso_rep = agente.ejecutar_herramienta(
            "enviar_correo",
            {"asunto": "duda sobre Nuva Studio", "cuerpo": "Hola, vi sus proyectos en Medellín."},
            es_frio=True,
        )
        self.assertFalse(ok_rep)
        self.assertIn("asunto_repetido_hoy", aviso_rep)

    def test_prospect_hunter_extrae_marca_real_dossier_y_filtra_ruido(self) -> None:
        import prospect_hunter  # noqa: PLC0415

        html_tienda = """
        <html lang="es"><head>
          <title>Tienda de Cosmética Natural en Medellín | Makeno Lab</title>
          <meta property="og:site_name" content="Makeno Lab" />
          <meta name="description" content="Sérums faciales artesanales hechos en Medellín. Envío desde $45.000 COP." />
        </head><body>
          <h1>Cuidado facial botánico hecho en Medellín</h1>
          <h2>Sérums y aceites puros</h2>
          <script src="https://cdn.shopify.com/s/files/theme.js"></script>
          <a href="https://instagram.com/makenolab">IG</a>
          <a href="https://wa.me/573001112233">WhatsApp</a>
          <p>Creamos fórmulas naturales para piel sensible en Colombia.</p>
        </body></html>
        """
        perfil = prospect_hunter.analizar_sitio_web(
            html_tienda, "https://makenolab.co/", nicho="ecommerce-catalogo-visual",
        )
        self.assertEqual(perfil["marca"], "Makeno Lab")
        self.assertEqual(perfil["ciudad"], "Medellín")
        self.assertEqual(perfil["plataforma"], "Shopify")
        self.assertEqual(perfil["instagram"], "@makenolab")
        self.assertEqual(perfil["whatsapp"], "+57 300 111 2233")
        self.assertTrue(perfil["encaja"])
        self.assertNotIn("45.000", perfil["dossier"])

        # Títulos SEO sin og:site_name deben caer a la marca real, no al título largo.
        self.assertEqual(
            prospect_hunter._clean_business_name("Diseño de interiores y mobiliario a medida en Bogotá | Nuva Studio", "nuvastudio.co"),
            "Nuva Studio",
        )
        self.assertEqual(
            prospect_hunter._clean_business_name("Remodelación y diseño de interiores en Bogotá", "lalupastudio.com"),
            "Lalupastudio",
        )

        # Filtra Claro, notificaciones* y gmails basura.
        cands = prospect_hunter._clean_email_candidates(
            "notificacionesclaro@claro.com.co xf6501985@gmail.com hola@nuvastudio.co",
            "nuvastudio.co",
        )
        self.assertEqual(cands, ["hola@nuvastudio.co"])

        # Filtra clínica médica pura en nicho e-commerce.
        html_clinica = """
        <html lang="es"><head><title>Dermatología Estética y Salud Capilar en Cali</title></head>
        <body><h1>Clínica dermatológica y medicina estética</h1><p>Agenda tu consulta médica en Cali.</p></body></html>
        """
        perfil_clinica = prospect_hunter.analizar_sitio_web(
            html_clinica, "https://clinicaejemplo.co/", nicho="ecommerce-catalogo-visual",
        )
        self.assertFalse(perfil_clinica["encaja"])

    def test_agente_inyecta_dossier_y_nombre_persona_en_contexto(self) -> None:
        database.upsert_lead(
            name="Santiago", company="Ecore Studio", email="santiago.salazar@ejemplo.com",
            nicho="automatizacion-agencias-estudios", stage="nuevo_lead",
            website="https://ecore.co/",
            dossier="Web: https://ecore.co/\nMarca real: Ecore Studio\nCiudad detectada: Medellín\nDescripción en su web: Agencia de pauta y contenido.",
        )
        capturado: dict[str, object] = {}

        def _fake_api(_key, cuerpo):
            capturado["cuerpo"] = cuerpo
            return respuesta_falsa({"type": "text", "text": "Listo"})

        with mock.patch.object(sales_agent, "llamar_api", side_effect=_fake_api):
            self.agente().correr(lead_email="santiago.salazar@ejemplo.com")

        prompt_usr = capturado["cuerpo"]["messages"][0]["content"]
        self.assertIn("Persona detectada: Santiago", prompt_usr)
        self.assertIn("Dossier real extraído de su sitio web", prompt_usr)
        self.assertIn("Agencia de pauta y contenido", prompt_usr)
        self.assertIn("Modelo de correo asignado", prompt_usr)
        self.assertEqual(capturado["cuerpo"]["output_config"]["effort"], "medium")

    def test_modelos_de_correo_rotan_y_aprenden_del_mas_efectivo(self) -> None:
        # 1) Fase de exploración: sin envíos, debe rotar por los 4 modelos sobrios.
        vistos = []
        for idx in range(4):
            elegido = sales_agent.elegir_modelo_correo("modelado-3d-espacios")
            self.assertEqual(elegido["modo"], "exploracion")
            vistos.append(elegido["id"])
            database.enqueue_email(
                recipient=f"exp{idx}@ejemplo.com", subject=f"asunto {idx}",
                body="Hola", nicho="modelado-3d-espacios", estilo=str(elegido["id"]),
            )
        self.assertEqual(set(vistos), {m["id"] for m in sales_agent.MODELOS_CORREO})

        # 2) Completa 4 envíos por cada modelo (total 16) con resultados reales distintos:
        #    `ultra_breve` trae 3 interesados, `caso_real` recibe 3 bajas, los otros 2 silencio.
        for modelo_id in [m["id"] for m in sales_agent.MODELOS_CORREO]:
            for n in range(1, sales_agent.MIN_ENVIOS_EXPLORACION):
                em = f"{modelo_id}_{n}@ejemplo.com"
                database.upsert_lead(name="L", company="C", email=em, nicho="modelado-3d-espacios", stage="contactado")
                database.enqueue_email(
                    recipient=em, subject=f"idea {modelo_id} {n}", body="Hola",
                    nicho="modelado-3d-espacios", estilo=modelo_id,
                )
                if modelo_id == "ultra_breve":
                    database.record_processed_reply(f"m-{em}", em, "interesado_cita", "Me interesa")
                elif modelo_id == "caso_real":
                    database.record_processed_reply(f"m-{em}", em, "baja", "Baja por favor")

        # Con total=16 (16 % 4 == 0), debe elegir al ganador real (`ultra_breve`).
        ganador = sales_agent.elegir_modelo_correo("modelado-3d-espacios")
        self.assertEqual(ganador["id"], "ultra_breve")
        self.assertEqual(ganador["modo"], "ganador")

        # Al llegar a total=19 (19 % 4 == 3), dedica 1 de cada 4 envíos a explorar un retador SANO
        # (nunca `caso_real` que tuvo 3 bajas).
        for k in range(3):
            database.enqueue_email(
                recipient=f"extra{k}@ejemplo.com", subject=f"extra {k}", body="Hola",
                nicho="modelado-3d-espacios", estilo="ultra_breve",
            )
        exploracion_activa = sales_agent.elegir_modelo_correo("modelado-3d-espacios")
        self.assertEqual(exploracion_activa["modo"], "aprendizaje_exploracion")
        self.assertIn(exploracion_activa["id"], ("muestra_directa", "observacion_puntual"))
        self.assertNotEqual(exploracion_activa["id"], "caso_real")

    def test_agente_guarda_estilo_y_imap_lo_atribuye(self) -> None:
        self.crear_lead(email="cliente@ejemplo.com")
        falsa = respuesta_falsa(
            bloque_tool(
                "enviar_correo",
                {"asunto": "duda sobre su tienda", "cuerpo": "Hola, vi su catálogo en línea y podemos ayudarles."},
            ),
            stop="tool_use",
        )
        fin = respuesta_falsa({"type": "text", "text": "Listo"})
        with mock.patch.object(sales_agent, "llamar_api", side_effect=[falsa, fin]):
            self.agente().correr(lead_email="cliente@ejemplo.com")

        estilo_guardado = database.get_last_sent_style_for_recipient("cliente@ejemplo.com")
        self.assertIn(estilo_guardado, sales_agent.MODELOS_POR_ID)

    def test_form_submitted_tokens_y_autorrespuestas_no_son_leads_ni_ventas(self) -> None:
        casos_auto = [
            ("Form Submitted", "Thank you! Your form was submitted. Contact us on WhatsApp for more info.", {}, "contacto@marca.co"),
            ("New Form Submission", "Hemos recibido tu solicitud, pronto te contactamos por teléfono.", {}, "info@marca.co"),
            ("Your access token", "Here is your verification token: 998877. Do not share.", {}, "hola@servicio.com"),
            ("Código de verificación", "Tu código de verificación para iniciar sesión es 445566.", {}, "soporte@app.com"),
            ("Confirmación", "Gracias por escribirnos, un asesor se comunicará contigo muy pronto.", {}, "ventas@marca.co"),
            ("Re: duda", "Hola, este es un mensaje automático, no responda a este correo.", {}, "hola@marca.co"),
            ("Re: fotos", "Recibido con gusto, pronto hablamos.", {"X-Autoreply": "yes"}, "hola@marca.co"),
            ("Re: catálogo", "Gracias, cuéntame más.", {}, "noreply@marca.co"),
        ]
        for asunto, cuerpo, hdrs, remitente in casos_auto:
            with self.subTest(asunto=asunto, remitente=remitente):
                self.assertEqual(
                    autopilot_dispatcher.classify_reply_intent(asunto, cuerpo, headers=hdrs, sender_email=remitente),
                    "respuesta_automatica",
                )

        # Un lead real pidiendo ayuda con un formulario web SÍ sigue siendo lead caliente.
        intent_real = autopilot_dispatcher.classify_reply_intent(
            "Re: duda sobre su tienda",
            "Hola, sí me interesa. Necesito automatizar un formulario de pedidos en mi tienda.",
            sender_email="laura@tiendareal.co",
        )
        self.assertEqual(intent_real, "interesado_cita")

        # En el agente de ventas, una autorrespuesta de Form Submitted / token se ignora con 0 llamadas a la API.
        self.crear_lead(email="bot@ejemplo.com")
        with mock.patch.object(sales_agent, "llamar_api",
                               side_effect=AssertionError("llamó a la API por una autorrespuesta")) as api:
            res = self.agente().correr(
                lead_email="bot@ejemplo.com",
                mensaje_lead="Form Submitted: thanks for reaching out, we received your message.",
            )
        self.assertTrue(res["ok"])
        self.assertEqual(res["motivo"], "autorrespuesta_ignorada")
        self.assertEqual(api.call_count, 0)


class TestSoloLePidoPersonasReales(unittest.TestCase):
    """El error que nos costó los primeros 26 correos: 18 fueron a buzones de empresa
    (info@, ventas@, hola@) y respondieron 0. Un buzón lo lee una recepcionista o nadie."""

    def test_buzon_de_empresa_y_marca_no_pasan_como_persona(self) -> None:
        import prospect_hunter  # noqa: PLC0415

        for correo in (
            "info@empresa.com", "ventas@kiel.com.co", "hola@agencia.com",
            "cafealtoperfil@gmail.com", "acuattro@gmail.com", "taro@tatoestudio.com",
            "ccialviva@ccviva.com", "integraespacioscali@gmail.com",
            "weare.cuero@gmail.com", "papeleria.pdepapel@gmail.com",
            "lmvjewelry@joyas.com", "creaciones.scsas@gmail.com",
        ):
            local, dom = correo.split("@", 1)
            with self.subTest(correo=correo):
                self.assertFalse(
                    prospect_hunter._parece_correo_de_persona(local, dom),
                    f"{correo} pasó como persona y es un buzón o la marca",
                )

    def test_personas_reales_si_pasan_y_se_saludan_por_su_nombre(self) -> None:
        import prospect_hunter  # noqa: PLC0415

        esperado = {
            "santiago.salazar@estudio.com": "Santiago",
            "mariana@tienda.com": "Mariana",
            "yesidcan@gmail.com": "Yesid",
            # El bug del strip: "camilacarmona27" quedaba con un espacio al final,
            # fallaba .isalpha() y una persona real se iba a la basura.
            "camilacarmona27@gmail.com": "Camila",
            "alejandra.r@empresa.com.co": "Alejandra",
            "etc.erikatarazona@gmail.com": "Erika",
        }
        for correo, nombre in esperado.items():
            local, dom = correo.split("@", 1)
            with self.subTest(correo=correo):
                self.assertTrue(prospect_hunter._parece_correo_de_persona(local, dom))
                self.assertEqual(prospect_hunter.nombre_de_pila_desde_email(correo), nombre)

    def test_si_el_nombre_es_dudoso_saluda_a_la_empresa(self) -> None:
        import prospect_hunter  # noqa: PLC0415

        # "Hola Fpedraza" o saludar Luisa a un Luis quema el correo en la primera línea.
        for correo in ("fpedraza.acc@gmail.com", "luisalfesp@gmail.com", "j.perez@x.com"):
            with self.subTest(correo=correo):
                self.assertEqual(prospect_hunter.nombre_de_pila_desde_email(correo), "")

    def test_escapes_json_no_ensucian_el_correo(self) -> None:
        import prospect_hunter  # noqa: PLC0415

        # Sin limpiar \u003e el correo salía como "u003einfo@megapredios.com.co".
        cands = prospect_hunter._clean_email_candidates(
            "escribenos \\u003einfo@megapredios.com.co\\u003c", "megapredios.com.co",
        )
        self.assertNotIn("u003einfo@megapredios.com.co", cands)


class TestColchonDeLaCola(BaseConBDTemporal):
    """El reponedor solo cubría el día: la cola amanecía en cero y el buscador tarda
    ~30 min en traer gente real, así que el motor se quedaba sin a quién escribirle."""

    def test_busca_hasta_llenar_el_colchon_no_solo_el_dia(self) -> None:
        database.update_settings({"autopilot_buffer_leads": "45"})
        llamadas: list[int] = []

        def falso_descubrir(needed: int, **_kw: object) -> list[dict[str, str]]:
            llamadas.append(needed)
            return []

        import prospect_hunter  # noqa: PLC0415

        with mock.patch.object(prospect_hunter, "discover_new_prospects", falso_descubrir), \
             mock.patch.object(autopilot_dispatcher, "get_daily_limit", return_value=15):
            res = autopilot_dispatcher.ensure_daily_pipeline(force=True)

        self.assertTrue(llamadas, "no buscó prospectos")
        self.assertGreaterEqual(llamadas[0], 45, "siguió buscando solo para el día")
        self.assertEqual(res["colchon_objetivo"], 45)


if __name__ == "__main__":
    unittest.main(verbosity=2)

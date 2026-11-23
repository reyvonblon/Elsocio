#!/usr/bin/env python3
"""Agente de ventas de El Socio con tool use. Solo stdlib (urllib), cero SDKs.

Llega hasta cliente calificado + aviso al dueño. Nunca da cifras, nunca cobra,
nunca manda links de pago, nunca envía por SMTP (solo encola en `outbox`).

Uso:
    python3 scripts/sales_agent.py --lead-email alguien@dominio.com --dry-run
    python3 scripts/sales_agent.py --lead-email alguien@dominio.com --mensaje "¿cuánto cuesta un logo?"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import autopilot_dispatcher  # noqa: E402
import database  # noqa: E402

IDENTIDAD_FILE = PROJECT_ROOT / "contexto" / "identidad.md"
ALCANCE_FILE = PROJECT_ROOT / "contexto" / "MODO_TRABAJO.md"

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

MAX_TURNS = 6          # cortado en Python, no se confía en el modelo
MAX_REINTENTOS = 2     # solo para 429 / 5xx
MAX_TOKENS_RESPUESTA = 2048
TIMEOUT_HTTP = 120

# USD por millón de tokens. Verificado contra la tabla de precios de la API.
PRECIOS_USD_MTOK = {
    "claude-sonnet-5": {"entrada": 2.00, "salida": 10.00, "cache_escritura": 2.50, "cache_lectura": 0.20},
    "claude-haiku-4-5": {"entrada": 1.00, "salida": 5.00, "cache_escritura": 1.25, "cache_lectura": 0.10},
    "claude-opus-5": {"entrada": 5.00, "salida": 25.00, "cache_escritura": 6.25, "cache_lectura": 0.50},
}
PRECIO_FALLBACK = PRECIOS_USD_MTOK["claude-sonnet-5"]

WEB_OFICIAL = "reyvonblon.github.io"


# ------------------------------------------------------------------ configuración

def cargar_config() -> dict[str, str]:
    """Lee `.env` + entorno. La API key nunca se imprime ni se guarda en la BD."""
    cfg = autopilot_dispatcher.load_env_file()
    for clave in ("ANTHROPIC_API_KEY", "SALES_AGENT_MODEL", "SALES_AGENT_MAX_EMAILS",
                  "SALES_AGENT_MAX_DAILY_USD"):
        if os.environ.get(clave):
            cfg[clave] = os.environ[clave]
    return cfg


def _entero(cfg: dict[str, str], clave: str, por_defecto: int) -> int:
    """0 es un valor válido: es la forma de apagar el agente desde `.env`."""
    crudo = str(cfg.get(clave, "")).strip()
    if not crudo:
        return por_defecto
    try:
        return max(0, int(crudo))
    except ValueError:
        return por_defecto


def _decimal(cfg: dict[str, str], clave: str, por_defecto: float) -> float:
    crudo = str(cfg.get(clave, "")).strip()
    if not crudo:
        return por_defecto
    try:
        return max(0.0, float(crudo))
    except ValueError:
        return por_defecto


def leer_configuracion(cfg: dict[str, str]) -> dict:
    return {
        "modelo": (cfg.get("SALES_AGENT_MODEL") or "claude-sonnet-5").strip(),
        "max_emails": _entero(cfg, "SALES_AGENT_MAX_EMAILS", 15),
        "max_usd": _decimal(cfg, "SALES_AGENT_MAX_DAILY_USD", 0.50),
        "tiene_api_key": bool((cfg.get("ANTHROPIC_API_KEY") or "").strip()),
    }


def calcular_costo_usd(modelo: str, uso: dict) -> float:
    p = PRECIOS_USD_MTOK.get(modelo, PRECIO_FALLBACK)
    return round(
        (int(uso.get("input_tokens", 0)) * p["entrada"]
         + int(uso.get("output_tokens", 0)) * p["salida"]
         + int(uso.get("cache_creation_input_tokens", 0)) * p["cache_escritura"]
         + int(uso.get("cache_read_input_tokens", 0)) * p["cache_lectura"]) / 1_000_000,
        8,
    )


# ------------------------------------------------------------------ guarda de precios

def _plano(texto: str) -> str:
    """Minúsculas sin acentos, para que 'millón' y 'millon' se detecten igual."""
    sin_acentos = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return sin_acentos.lower()


_NUMERAL_LETRAS = (
    r"(?:un|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|"
    r"quince|dieci(?:seis|siete|ocho|nueve)|veinte|veinti(?:uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve)|"
    r"treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|cien|ciento|doscientos|trescientos|"
    r"cuatrocientos|quinientos|seiscientos|setecientos|ochocientos|novecientos|varios|unos|algunos)"
)

PATRONES_GUARDA: list[tuple[str, str]] = [
    # moneda y símbolos
    ("simbolo_moneda", r"[$€£]"),
    ("moneda_escrita", r"\b(cop|usd|eur|pesos?|dolares?|dolar|euros?)\b"),
    # palabras de precio
    ("palabra_precio", r"\b(precio|precios|vale|valen|valor(?:es)?|cuesta|cuestan|costo|costos|"
                       r"tarifa|tarifas|cobro|cobramos|cobrar|anticipo|abono|presupuesto|cotizacion|"
                       r"descuento|promocion)\b"),
    # cifras
    ("cifra_con_escala", rf"(?:\d[\d.,]*|{_NUMERAL_LETRAS})\s*(?:mil|millon|millones)\b"),
    ("cifra_separada", r"\b\d{1,3}[.,]\d{3}\b"),
    ("cifra_abreviada", r"\b\d+\s*(?:k|m|mm)\b"),
    # métodos y pasarelas de pago
    ("metodo_pago", r"\b(nequi|daviplata|wompi|mercado\s?pago|mercadopago|payu|payu\s?latam|stripe|"
                    r"paypal|pse|bancolombia|bancolombia\s?a\s?la\s?mano|davivienda|epayco|addi|bold|"
                    r"transfiya|efecty|giro|consignacion|consignar|cuenta\s?de\s?ahorros|cuenta\s?corriente|"
                    r"link\s?de\s?pago|pasarela)\b"),
]

_RE_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"')]+", re.IGNORECASE)


def _links_externos(texto: str) -> list[str]:
    permitidos = (WEB_OFICIAL, "wa.me", "api.whatsapp.com")
    fuera = []
    for url in _RE_URL.findall(texto):
        bajo = url.lower()
        if not any(d in bajo for d in permitidos):
            fuera.append(url)
    return fuera


def revisar_guarda_precios(*partes: str) -> list[str]:
    """Devuelve los motivos por los que este texto NO puede salir. Vacío = puede salir.

    Esto vive en código a propósito: el prompt puede fallar, esto no.
    """
    texto = _plano(" \n ".join(p or "" for p in partes))
    motivos = []
    for nombre, patron in PATRONES_GUARDA:
        hallado = re.search(patron, texto)
        if hallado:
            motivos.append(f"{nombre}: '{hallado.group(0).strip()}'")
    for url in _links_externos(texto):
        motivos.append(f"link_externo: '{url}'")
    return motivos


# ------------------------------------------------------------------ línea de baja

_SENALES_BAJA = (
    "darte de baja", "dar de baja", "darse de baja", "no recibir mas", "no quieres recibir",
    "no deseas recibir", "responde baja", "responde con baja", "desuscribir", "no te escribo mas",
    "no volver a escribir", "escribe baja",
)
LINEA_BAJA = ("\n\nSi no quieres recibir más correos míos, respóndeme con la palabra BAJA "
              "y no te vuelvo a escribir.")


def tiene_linea_de_baja(cuerpo: str) -> bool:
    plano = _plano(cuerpo)
    return any(s in plano for s in _SENALES_BAJA)


def asegurar_linea_de_baja(cuerpo: str) -> str:
    return cuerpo if tiene_linea_de_baja(cuerpo) else cuerpo.rstrip() + LINEA_BAJA


# ------------------------------------------------------------------ definición de herramientas

# Los nombres que viaja a la API son ASCII: la API solo acepta [a-zA-Z0-9_-] en
# `name`, así que 'dueño' se escribe 'dueno' en el cable. Los alias con ñ se aceptan igual.
HERRAMIENTAS = [
    {
        "name": "enviar_correo",
        "description": ("Encola un correo para este lead. No lo envía al instante: lo pone en la cola "
                        "y el motor lo manda respetando horario y tope diario. Prohibido escribir "
                        "cifras, precios, formas de pago o links de pago — el correo se rechaza."),
        "input_schema": {
            "type": "object",
            "properties": {
                "asunto": {"type": "string", "description": "Asunto corto, sin cifras."},
                "cuerpo": {"type": "string", "description": "Texto del correo, en español, corto y directo."},
            },
            "required": ["asunto", "cuerpo"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "programar_seguimiento",
        "description": "Programa un recordatorio para volver a escribirle. Máximo 2 por lead.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {"type": "integer", "description": "En cuántos días volver a escribir (1 a 30)."},
                "motivo": {"type": "string", "description": "Por qué se hace el seguimiento."},
            },
            "required": ["dias", "motivo"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "cambiar_etapa",
        "description": ("Mueve al lead de etapa. Si eligen 'no_interesado' o 'baja' se cancela de "
                        "inmediato todo correo y seguimiento pendiente."),
        "input_schema": {
            "type": "object",
            "properties": {
                "etapa": {
                    "type": "string",
                    "enum": ["nuevo_lead", "contactado", "conversando", "calificado",
                             "esperando_precio_dueno", "no_interesado", "baja"],
                },
                "nota": {"type": "string", "description": "Una línea de por qué cambia."},
            },
            "required": ["etapa", "nota"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "avisar_al_dueno",
        "description": "Avisa a Raymond en su Mac. Úsalo ante dudas, quejas, temas delicados o un lead calificado.",
        "input_schema": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string"},
                "resumen": {"type": "string", "description": "Qué pasó y qué necesita decidir él."},
            },
            "required": ["titulo", "resumen"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "pedir_precio_al_dueno",
        "description": ("Única vía para que haya un precio. Pasa el lead a 'esperando_precio_dueno', "
                        "le avisa a Raymond y le crea el evento en el calendario para que cotice. "
                        "Tú nunca das la cifra."),
        "input_schema": {
            "type": "object",
            "properties": {
                "encargo": {"type": "string", "description": "Qué pide el cliente, en concreto."},
                "datos_recogidos": {"type": "string", "description": "Para qué, para cuándo, archivos, contexto."},
            },
            "required": ["encargo", "datos_recogidos"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

ALIAS_HERRAMIENTAS = {
    "avisar_al_dueño": "avisar_al_dueno",
    "pedir_precio_al_dueño": "pedir_precio_al_dueno",
    "esperando_precio_dueño": "esperando_precio_dueno",
}


# ------------------------------------------------------------------ system prompt

def construir_system_prompt() -> str:
    """Se lee del disco en cada corrida. Nunca se copia al código.

    Nunca se lee `contexto/precios-del-dueño.md`: el agente no maneja cifras.
    """
    if not IDENTIDAD_FILE.exists():
        raise SystemExit(f"Falta {IDENTIDAD_FILE.name}: sin identidad el agente no opera.")
    partes = [IDENTIDAD_FILE.read_text(encoding="utf-8")]
    if ALCANCE_FILE.exists():
        # identidad.md se remite explícitamente a esta sección, y manda sobre ella.
        texto = ALCANCE_FILE.read_text(encoding="utf-8")
        inicio = texto.find("## Alcance del agente")
        if inicio != -1:
            partes.append(texto[inicio:])
    partes.append(
        "## Reglas del motor (las aplica el código, no tú)\n"
        "- El correo se encola, no se envía al instante. Si una herramienta te devuelve un error, "
        "corrige y vuelve a intentar con otro texto; no insistas con el mismo.\n"
        "- Cualquier cifra, precio, forma de pago o link de pago en un correo lo bloquea el código. "
        "Si necesitas hablar de valor, usa pedir_precio_al_dueno.\n"
        "- Tienes pocos turnos. Haz lo necesario y termina."
    )
    return "\n\n".join(partes)


# ------------------------------------------------------------------ llamada a la API

class ErrorAPI(Exception):
    pass


def llamar_api(api_key: str, cuerpo: dict) -> dict:
    """POST a /v1/messages con reintentos solo en 429/5xx. Nunca loguea la key."""
    datos = json.dumps(cuerpo).encode("utf-8")
    ultimo = ""
    for intento in range(MAX_REINTENTOS + 1):
        peticion = urllib.request.Request(
            API_URL,
            data=datos,
            method="POST",
            headers={
                "content-type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
            },
        )
        try:
            with urllib.request.urlopen(peticion, timeout=TIMEOUT_HTTP) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            detalle = ""
            try:
                detalle = err.read().decode("utf-8")[:300]
            except Exception:
                pass
            ultimo = f"HTTP {err.code}: {detalle}"
            transitorio = err.code == 429 or 500 <= err.code < 600
            if not transitorio or intento == MAX_REINTENTOS:
                raise ErrorAPI(ultimo) from None
        except urllib.error.URLError as err:
            ultimo = f"red: {err.reason}"
            if intento == MAX_REINTENTOS:
                raise ErrorAPI(ultimo) from None
    raise ErrorAPI(ultimo or "sin respuesta")


# ------------------------------------------------------------------ el agente

class AgenteVentas:
    def __init__(self, cfg: dict[str, str], *, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run
        self.conf = leer_configuracion(cfg)
        self.modelo = self.conf["modelo"]
        self.turno = 0
        self.lead: dict | None = None
        self.costo_corrida = 0.0
        self.acciones: list[str] = []

    # --- registro -------------------------------------------------------

    def _log(self, herramienta: str, *, argumentos: str = "", resultado: str = "",
             uso: dict | None = None, costo_usd: float = 0.0, bloqueado: str = "") -> None:
        if self.dry_run:
            return
        u = uso or {}
        database.log_agent_action(
            lead_id=(self.lead or {}).get("id"),
            turno=self.turno,
            modelo=self.modelo,
            herramienta=herramienta,
            argumentos=argumentos,
            resultado=resultado,
            tokens_entrada=int(u.get("input_tokens", 0)),
            tokens_salida=int(u.get("output_tokens", 0)),
            tokens_cache_creacion=int(u.get("cache_creation_input_tokens", 0)),
            tokens_cache_lectura=int(u.get("cache_read_input_tokens", 0)),
            costo_usd=costo_usd,
            bloqueado_por_guarda=bloqueado,
        )

    # --- guardas previas ------------------------------------------------

    def guardas_previas(self) -> str:
        """Lo que se revisa ANTES de gastar un solo token. Devuelve '' si se puede operar."""
        if not self.conf["tiene_api_key"]:
            return "Falta ANTHROPIC_API_KEY en .env — el agente no llama a la API."
        if self.dry_run:
            return ""
        encolados = database.agent_emails_queued_today()
        if encolados >= self.conf["max_emails"]:
            return f"Tope diario de correos alcanzado ({encolados}/{self.conf['max_emails']})."
        gastado = database.agent_cost_today_usd()
        if gastado >= self.conf["max_usd"]:
            return f"Tope diario de gasto alcanzado ({gastado:.4f}/{self.conf['max_usd']:.2f} USD)."
        return ""

    def _cupo_correos_libre(self) -> tuple[bool, str]:
        if self.dry_run:
            return True, ""
        encolados = database.agent_emails_queued_today()
        if encolados >= self.conf["max_emails"]:
            return False, (f"Tope diario de correos alcanzado ({encolados}/{self.conf['max_emails']}). "
                           "No encoles más hoy.")
        return True, ""

    # --- herramientas ---------------------------------------------------

    def _tool_enviar_correo(self, args: dict, *, es_frio: bool) -> tuple[bool, str]:
        asunto = (args.get("asunto") or "").strip()
        cuerpo = (args.get("cuerpo") or "").strip()
        if not asunto or not cuerpo:
            return False, "El correo necesita asunto y cuerpo."

        motivos = revisar_guarda_precios(asunto, cuerpo)
        if motivos:
            detalle = "; ".join(motivos[:5])
            self._log("enviar_correo", argumentos=json.dumps(args, ensure_ascii=False),
                      resultado="rechazado antes de encolar", bloqueado=detalle)
            self.acciones.append(f"correo BLOQUEADO por guarda ({detalle})")
            return False, ("BLOQUEADO por la guarda de precios: " + detalle +
                           ". Reescribe el correo sin ninguna cifra, precio, moneda ni forma de pago. "
                           "Si hace falta un precio, usa pedir_precio_al_dueno.")

        destinatario = (self.lead or {}).get("email", "")
        if not destinatario:
            return False, "No hay un correo de destino para este lead."

        if es_frio:
            cuerpo = asegurar_linea_de_baja(cuerpo)

        if not self.dry_run and database.already_emailed_today(destinatario):
            return False, "Ya hay un correo encolado o enviado hoy a esta dirección. No dupliques."

        libre, aviso = self._cupo_correos_libre()
        if not libre:
            return False, aviso

        if self.dry_run:
            self.acciones.append(f"[dry-run] correo a {destinatario} | asunto: {asunto}")
            return True, "Correo validado y listo para encolar (dry-run: no se encoló)."

        job_id = database.enqueue_email(
            recipient=destinatario, subject=asunto, body=cuerpo,
            nicho=(self.lead or {}).get("nicho", ""),
        )
        self._log("enviar_correo", argumentos=json.dumps({"asunto": asunto}, ensure_ascii=False),
                  resultado=f"encolado job {job_id}")
        self.acciones.append(f"correo encolado (job {job_id}) a {destinatario}")
        return True, f"Correo encolado (id {job_id}). Lo manda el motor respetando horario y tope."

    def _tool_programar_seguimiento(self, args: dict) -> tuple[bool, str]:
        if not self.lead:
            return False, "No hay lead."
        dias = max(1, min(30, int(args.get("dias") or 3)))
        motivo = (args.get("motivo") or "").strip()[:300]
        if self.dry_run:
            self.acciones.append(f"[dry-run] seguimiento en {dias} días: {motivo}")
            return True, f"Seguimiento validado para dentro de {dias} días (dry-run)."
        fid = database.schedule_followup(self.lead["id"], dias, motivo)
        if fid is None:
            self._log("programar_seguimiento", argumentos=json.dumps(args, ensure_ascii=False),
                      resultado="rechazado: ya tiene 2 seguimientos")
            return False, "Este lead ya tiene los 2 seguimientos permitidos. No se programa otro."
        self._log("programar_seguimiento", argumentos=json.dumps(args, ensure_ascii=False),
                  resultado=f"seguimiento {fid} en {dias} dias")
        self.acciones.append(f"seguimiento programado en {dias} días")
        return True, f"Seguimiento programado para dentro de {dias} días."

    def _tool_cambiar_etapa(self, args: dict) -> tuple[bool, str]:
        if not self.lead:
            return False, "No hay lead."
        etapa = ALIAS_HERRAMIENTAS.get((args.get("etapa") or "").strip(), (args.get("etapa") or "").strip())
        nota = (args.get("nota") or "").strip()[:500]
        if not etapa:
            return False, "Falta la etapa."
        corta_todo = etapa in ("no_interesado", "baja")
        if self.dry_run:
            self.acciones.append(f"[dry-run] etapa -> {etapa}" + (" + cancelar pendientes" if corta_todo else ""))
            return True, f"Etapa validada: {etapa} (dry-run)."
        database.update_lead_stage(self.lead["id"], etapa, notes=nota or None)
        if corta_todo:
            database.cancel_pending_outbox_for_recipient(self.lead["email"])
            database.cancel_followups_for_lead(self.lead["id"])
            self.acciones.append(f"etapa {etapa}: cancelado todo lo pendiente")
        self.lead["stage"] = etapa
        self._log("cambiar_etapa", argumentos=json.dumps(args, ensure_ascii=False),
                  resultado=f"etapa={etapa} cancelado={corta_todo}")
        extra = " Se canceló todo lo pendiente para este lead." if corta_todo else ""
        return True, f"Etapa actualizada a {etapa}.{extra}"

    def _tool_avisar_al_dueno(self, args: dict) -> tuple[bool, str]:
        titulo = (args.get("titulo") or "Aviso del agente").strip()[:120]
        resumen = (args.get("resumen") or "").strip()[:800]
        if self.dry_run:
            self.acciones.append(f"[dry-run] aviso al dueño: {titulo}")
            return True, "Aviso validado (dry-run: no se notificó)."
        autopilot_dispatcher.notify_mac_desktop(titulo, resumen)
        if self.lead:
            nota = f"{(self.lead.get('notes') or '')} | AVISO {titulo}: {resumen}".strip(" |")
            database.update_lead_stage(self.lead["id"], self.lead.get("stage", "conversando"), notes=nota[:2000])
        self._log("avisar_al_dueno", argumentos=json.dumps(args, ensure_ascii=False),
                  resultado="notificado en el Mac")
        self.acciones.append(f"aviso al dueño: {titulo}")
        return True, "Raymond ya está avisado en su Mac."

    def _tool_pedir_precio_al_dueno(self, args: dict) -> tuple[bool, str]:
        if not self.lead:
            return False, "No hay lead."
        encargo = (args.get("encargo") or "").strip()[:600]
        datos = (args.get("datos_recogidos") or "").strip()[:900]
        resumen = f"ENCARGO: {encargo}\nDATOS: {datos}"
        if self.dry_run:
            self.acciones.append(f"[dry-run] pedir precio al dueño: {encargo[:60]}")
            return True, ("Encargo validado: el dueño cotiza (dry-run). Dile al cliente que estás "
                          "preparando la propuesta, sin adelantar ninguna cifra.")
        nota = f"{(self.lead.get('notes') or '')} | PRECIO PENDIENTE -> {resumen}".strip(" |")
        database.update_lead_stage(self.lead["id"], "esperando_precio_dueno", notes=nota[:2000])
        self.lead["stage"] = "esperando_precio_dueno"
        autopilot_dispatcher.notify_mac_desktop("Cotizar para un lead", encargo[:170])
        cuando = (datetime.now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        autopilot_dispatcher.create_calendar_event(
            f"Cotizar: {self.lead.get('company') or self.lead.get('email')}", resumen, cuando,
        )
        self._log("pedir_precio_al_dueno", argumentos=json.dumps(args, ensure_ascii=False),
                  resultado="etapa esperando_precio_dueno + aviso + evento")
        self.acciones.append("precio pedido al dueño (aviso + evento en Calendar)")
        return True, ("Listo: Raymond tiene el encargo y el evento para cotizar. Dile al cliente que "
                      "estás preparando la propuesta. No adelantes ninguna cifra.")

    def ejecutar_herramienta(self, nombre: str, args: dict, *, es_frio: bool) -> tuple[bool, str]:
        nombre = ALIAS_HERRAMIENTAS.get(nombre, nombre)
        try:
            if nombre == "enviar_correo":
                return self._tool_enviar_correo(args, es_frio=es_frio)
            if nombre == "programar_seguimiento":
                return self._tool_programar_seguimiento(args)
            if nombre == "cambiar_etapa":
                return self._tool_cambiar_etapa(args)
            if nombre == "avisar_al_dueno":
                return self._tool_avisar_al_dueno(args)
            if nombre == "pedir_precio_al_dueno":
                return self._tool_pedir_precio_al_dueno(args)
        except Exception as err:  # una herramienta que falla no tumba la corrida
            return False, f"La herramienta falló: {err}"
        return False, f"No existe la herramienta '{nombre}'."

    # --- loop -----------------------------------------------------------

    def correr(self, *, lead_email: str, mensaje_lead: str = "", nicho: str = "") -> dict:
        bloqueo = self.guardas_previas()
        if bloqueo:
            return {"ok": False, "motivo": bloqueo, "acciones": [], "costo_usd": 0.0, "turnos": 0}

        self.lead = database.get_lead_by_email(lead_email)
        if not self.lead:
            if self.dry_run:
                self.lead = {"id": None, "email": lead_email.lower().strip(), "company": "",
                             "nicho": nicho, "stage": "nuevo_lead", "notes": ""}
            else:
                lead_id = database.upsert_lead(
                    name="", company="", email=lead_email, nicho=nicho,
                    source="sales_agent", stage="nuevo_lead", notes="Creado por sales_agent",
                )
                self.lead = database.get_lead_by_email(lead_email) or {"id": lead_id, "email": lead_email}

        es_frio = not mensaje_lead.strip()
        system_prompt = construir_system_prompt()
        contexto_lead = (
            f"Lead: {self.lead.get('email')}\n"
            f"Empresa: {self.lead.get('company') or '(no se sabe)'}\n"
            f"Nicho: {self.lead.get('nicho') or nicho or '(no se sabe)'}\n"
            f"Etapa actual: {self.lead.get('stage')}\n"
            f"Notas previas: {(self.lead.get('notes') or '(ninguna)')[:600]}\n\n"
        )
        if es_frio:
            contexto_lead += ("No ha escrito nada: es primer contacto en frío. Escríbele un correo corto "
                              "con un ángulo concreto para su negocio y programa el seguimiento.")
        else:
            contexto_lead += f"Mensaje del lead:\n\"\"\"\n{mensaje_lead.strip()[:3000]}\n\"\"\""

        mensajes: list[dict] = [{"role": "user", "content": contexto_lead}]
        api_key = (self.cfg.get("ANTHROPIC_API_KEY") or "").strip()
        razon_fin = "max_turnos"

        while self.turno < MAX_TURNS:
            self.turno += 1
            cuerpo = {
                "model": self.modelo,
                "max_tokens": MAX_TOKENS_RESPUESTA,
                # Prompt Caching: la identidad es el prefijo estable de cada corrida.
                "system": [{"type": "text", "text": system_prompt,
                            "cache_control": {"type": "ephemeral"}}],
                "tools": HERRAMIENTAS,
                "messages": mensajes,
                "output_config": {"effort": "low"},  # saldo corto: lo justo para operar
            }
            try:
                respuesta = llamar_api(api_key, cuerpo)
            except ErrorAPI as err:
                self._log("error_api", resultado=str(err)[:500])
                return {"ok": False, "motivo": f"API: {err}", "acciones": self.acciones,
                        "costo_usd": round(self.costo_corrida, 6), "turnos": self.turno}

            uso = respuesta.get("usage", {}) or {}
            costo = calcular_costo_usd(self.modelo, uso)
            self.costo_corrida += costo
            self._log("llamada_api", resultado=f"stop={respuesta.get('stop_reason')}",
                      uso=uso, costo_usd=costo)

            if respuesta.get("stop_reason") == "refusal":
                razon_fin = "refusal"
                break

            contenido = respuesta.get("content", []) or []
            mensajes.append({"role": "assistant", "content": contenido})

            usos_de_tool = [b for b in contenido if b.get("type") == "tool_use"]
            if not usos_de_tool:
                razon_fin = respuesta.get("stop_reason") or "fin"
                break

            resultados = []
            for bloque in usos_de_tool:
                ok, salida = self.ejecutar_herramienta(
                    bloque.get("name", ""), bloque.get("input") or {}, es_frio=es_frio,
                )
                resultados.append({
                    "type": "tool_result",
                    "tool_use_id": bloque.get("id"),
                    "content": salida,
                    **({"is_error": True} if not ok else {}),
                })
            mensajes.append({"role": "user", "content": resultados})

            # Tope de gasto revisado también dentro del loop: nunca pasarse del saldo.
            if not self.dry_run and database.agent_cost_today_usd() >= self.conf["max_usd"]:
                razon_fin = "tope_gasto"
                break
        else:
            razon_fin = "max_turnos"

        return {"ok": True, "motivo": razon_fin, "acciones": self.acciones,
                "costo_usd": round(self.costo_corrida, 6), "turnos": self.turno}


# ------------------------------------------------------------------ CLI

def main() -> None:
    parser = argparse.ArgumentParser(description="Agente de ventas de El Socio (tool use, solo stdlib).")
    parser.add_argument("--lead-email", required=True, help="Correo del lead.")
    parser.add_argument("--mensaje", default="", help="Mensaje que escribió el lead (vacío = correo en frío).")
    parser.add_argument("--nicho", default="", help="Nicho, si se conoce.")
    parser.add_argument("--dry-run", action="store_true", help="No escribe en la BD ni encola nada.")
    args = parser.parse_args()

    cfg = cargar_config()
    if not args.dry_run:
        database.init_db()

    agente = AgenteVentas(cfg, dry_run=args.dry_run)
    resultado = agente.correr(lead_email=args.lead_email, mensaje_lead=args.mensaje, nicho=args.nicho)
    resultado["modelo"] = agente.modelo
    resultado["dry_run"] = args.dry_run
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

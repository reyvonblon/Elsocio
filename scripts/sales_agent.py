#!/usr/bin/env python3
"""Agente de ventas de El Socio con tool use. Solo stdlib (urllib), cero SDKs.

Llega hasta cliente calificado + aviso al dueño. Nunca da cifras, nunca cobra,
nunca manda links de pago, nunca envía por SMTP (solo encola en `outbox`).

Uso:
    python3 scripts/sales_agent.py --lead-email alguien@dominio.com --dry-run
    python3 scripts/sales_agent.py --lead-email alguien@dominio.com --dry-run --con-api
    python3 scripts/sales_agent.py --lead-email alguien@dominio.com --mensaje "¿cuánto cuesta un logo?"

`--dry-run` solo valida: no escribe en la BD, no encola y NO llama a la API (no gasta saldo).
Para probar contra la API real en seco hay que pedirlo con `--con-api`, y aun así respeta los topes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
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
NICHOS_DIR = PROJECT_ROOT / "nichos"
SKILLS_CALIDAD = (
    PROJECT_ROOT / ".claude" / "skills" / "calidad" / "humanizer.md",
    PROJECT_ROOT / ".claude" / "skills" / "calidad" / "psicologia-y-estatus.md",
    PROJECT_ROOT / ".claude" / "skills" / "calidad" / "editor-implacable.md",
    PROJECT_ROOT / ".claude" / "skills" / "ventas" / "redactar-outreach.md",
)

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

MAX_TURNS = 6          # cortado en Python, no se confía en el modelo
MAX_REINTENTOS = 2     # solo para 429 / 5xx
PAUSA_REINTENTO = 1.5  # segundos * (intento + 1) antes de reintentar un 429/5xx
MAX_TOKENS_RESPUESTA = 2048
TIMEOUT_HTTP = 120

# USD por millón de tokens. Verificado contra la tabla de precios de la API.
PRECIOS_USD_MTOK = {
    "claude-sonnet-5": {"entrada": 2.00, "salida": 10.00, "cache_escritura": 2.50, "cache_lectura": 0.20},
    "claude-sonnet-5-5": {"entrada": 2.00, "salida": 10.00, "cache_escritura": 2.50, "cache_lectura": 0.20},
    "claude-haiku-4-5": {"entrada": 1.00, "salida": 5.00, "cache_escritura": 1.25, "cache_lectura": 0.10},
    "claude-opus-5": {"entrada": 5.00, "salida": 25.00, "cache_escritura": 6.25, "cache_lectura": 0.50},
}
PRECIO_FALLBACK = PRECIOS_USD_MTOK["claude-sonnet-5"]

WEB_OFICIAL = "reyvonblon.github.io"
# Hostnames que sí pueden salir en un correo. Se comparan EXACTOS, nunca "está contenido en".
DOMINIOS_PERMITIDOS = (WEB_OFICIAL, "wa.me", "api.whatsapp.com")


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
                       r"tarifa|tarifas|cobro|cobra|cobre|cobrando|cobramos|cobrar|anticipo|abono|"
                       r"presupuesto|cotizacion|descuento|promocion)\b"),
    # cifras
    ("cifra_con_escala", rf"(?:\d[\d.,]*|{_NUMERAL_LETRAS})\s*(?:mil|millon|millones)\b"),
    # Separador de miles: punto, coma o espacio ("50.000", "50,000", "50 000").
    ("cifra_separada", "\\b\\d{1,3}[.,\u00a0 ]\\d{3}\\b"),
    # identidad.md prohíbe dar porcentajes: "20%", "20 por ciento".
    ("porcentaje_numerico", r"\b\d+\s*(?:%|por\s+ciento\b)"),
    ("cifra_abreviada", r"\b\d+\s*(?:k|m|mm)\b"),
    # Entero pegado sin separador: 25000, 50000, 120000. En el cuerpo nunca van teléfonos
    # ni precios: la firma la agrega el dispatcher después, no el modelo.
    ("cifra_entera_grande", r"\b[1-9]\d{4,}\b"),
    # métodos y pasarelas de pago
    ("metodo_pago", r"\b(nequi|daviplata|wompi|mercado\s?pago|mercadopago|payu|payu\s?latam|stripe|"
                    r"paypal|pse|bancolombia|bancolombia\s?a\s?la\s?mano|davivienda|epayco|addi|bold|"
                    r"transfiya|transferencia|transferir|bre[\s-]?b|efecty|giro|consignacion|consignar|"
                    r"cuenta\s?de\s?ahorros|cuenta\s?corriente|link\s?de\s?pago|pasarela)\b"),
]

# Acortadores y pasarelas de cobro: se bloquean incluso sin ruta.
HOSTS_BLOQUEADOS = (
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "cutt.ly", "rb.gy", "is.gd", "shorturl.at",
    "acortar.link", "n9.cl", "wa.link", "mpago.la", "mpago.li", "mercadopago.com",
    "mercadopago.com.co", "paypal.me", "paypal.com", "stripe.com", "wompi.co", "payu.com",
    "payulatam.com", "epayco.co", "bold.co", "addi.com", "nequi.com.co", "daviplata.com",
    "pse.com.co", "venmo.com", "cash.app", "ko-fi.com",
)
# Primera etiqueta del host que delata una página de cobro: checkout.*, pagos.*, pay.*
SUBDOMINIOS_DE_COBRO = ("checkout", "pago", "pagos", "pagar", "pay", "payment", "payments",
                        "cobro", "cobros", "donar", "donate", "billing")

# Un solo patrón para links con y sin esquema: "https://x.com/y", "www.x.com", "mpago.la/2xYz".
_RE_ENLACE = re.compile(
    r"(?:(?:https?:)?//)?"                              # esquema opcional
    r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}"   # dominio.tld
    r"(?::\d{2,5})?"                                    # puerto
    r"(?:[/?][^\s<>\"')]*)?",                           # ruta o query ("evil.com?a=1")
    re.IGNORECASE,
)


def _hostname(bruto: str) -> str:
    """Hostname exacto del enlace, parseado de verdad. Se le pone '//' para que urlparse lo vea."""
    con_esquema = bruto if "//" in bruto[:10] else "//" + bruto
    try:
        host = urllib.parse.urlparse(con_esquema).hostname or ""
    except ValueError:
        return ""
    return host.lower().rstrip(".")


def _host_permitido(host: str) -> bool:
    """Igualdad exacta (con 'www.' opcional). Nada de 'contiene': así
    'reyvonblon.github.io.evil.com' y 'pagos.evil.com/?r=reyvonblon.github.io' NO pasan.
    """
    if host.startswith("www."):
        host = host[4:]
    return host in DOMINIOS_PERMITIDOS


def _links_externos(texto: str) -> list[str]:
    """Enlaces que no pueden salir del correo."""
    fuera = []
    for hallado in _RE_ENLACE.finditer(texto):
        bruto = hallado.group(0).rstrip(".,;:!?)")
        host = _hostname(bruto)
        if not host or "." not in host:
            continue
        if _host_permitido(host):
            continue
        bajo = bruto.lower()
        tiene_esquema = "//" in bajo[:10]
        resto = bajo.split("//", 1)[-1]
        tiene_ruta = "/" in resto
        # Un link puede llevar query sin barra: "evil.com?a=1" también es un link.
        tiene_query = "?" in resto
        etiqueta = host.split(".")[0]
        sospechoso = (host in HOSTS_BLOQUEADOS
                      or any(host.endswith("." + h) for h in HOSTS_BLOQUEADOS)
                      or etiqueta in SUBDOMINIOS_DE_COBRO)
        if tiene_esquema or tiene_ruta or tiene_query or sospechoso or bajo.startswith("www."):
            fuera.append(bruto)
    return fuera


# Del link propio solo es inofensivo el esquema + host + los dígitos del path
# (`https://wa.me/573001112233`). Todo lo que venga después se sigue revisando.
_RE_PARTE_INOFENSIVA = re.compile(r"^(?:(?:https?:)?//)?[^/?#]+(?:/[0-9/]*)?")


def _cola_legible(cola: str) -> str:
    """La cola de un link propio se vuelve palabras sueltas para poder revisarla.

    Sin esto, `?text=pagar_50000_nequi` se esconde: el '_' es carácter de palabra y
    rompe los `\b` de los patrones, así que ni la cifra ni el 'nequi' se verían.
    """
    if not cola:
        return ""
    crudo = urllib.parse.unquote_plus(cola)
    return " " + re.sub(r"[^a-z0-9]+", " ", crudo, flags=re.IGNORECASE).strip() + " "


def _sin_links_permitidos(texto: str) -> str:
    """Saca el host de los links propios antes de contar cifras: wa.me/573001112233 no es
    un precio. La query SÍ se conserva (legible): ahí se pueden esconder cifras y pagos.
    """
    def _reemplazo(hallado):
        bruto = hallado.group(0)
        recortado = bruto.rstrip(".,;:!?)")
        if not _host_permitido(_hostname(recortado)):
            return bruto
        inofensiva = _RE_PARTE_INOFENSIVA.match(recortado)
        corte = inofensiva.end() if inofensiva else len(recortado)
        return " enlace_oficial " + _cola_legible(recortado[corte:]) + bruto[len(recortado):]
    return _RE_ENLACE.sub(_reemplazo, texto)


def revisar_guarda_precios(*partes: str) -> list[str]:
    """Devuelve los motivos por los que este texto NO puede salir. Vacío = puede salir.

    Esto vive en código a propósito: el prompt puede fallar, esto no.
    """
    texto = _plano(" \n ".join(p or "" for p in partes))
    motivos = []
    # Las cifras se buscan sin los links propios; los links, sobre el texto completo.
    texto_cifras = _sin_links_permitidos(texto)
    for nombre, patron in PATRONES_GUARDA:
        hallado = re.search(patron, texto_cifras)
        if hallado:
            motivos.append(f"{nombre}: '{hallado.group(0).strip()}'")
    for url in _links_externos(texto):
        motivos.append(f"link_externo: '{url}'")
    return motivos


# ------------------------------------------------------------------ línea de baja y calidad humana

_SENALES_BAJA = (
    "darte de baja", "dar de baja", "darse de baja", "no recibir mas", "no quieres recibir",
    "no quieren recibir", "no deseas recibir", "no desean recibir", "prefieres no recibir",
    "prefieren no recibir", "no te interesa recibir", "no les interesa recibir",
    "responde baja", "responde \"baja\"", "responde 'baja'", "responde con baja",
    "respondan baja", "respondan \"baja\"", "respondan 'baja'", "respondeme baja",
    "respondeme con la palabra baja", "desuscribir", "no te escribo mas",
    "no te escribo de nuevo", "no te vuelvo a escribir", "no les vuelvo a escribir",
    "no volver a escribir", "escribe baja", "saco de la lista",
)
LINEA_BAJA = "\n\nSi no te interesa, respóndeme BAJA y no te vuelvo a escribir."


def tiene_linea_de_baja(cuerpo: str) -> bool:
    plano = _plano(cuerpo)
    return any(s in plano for s in _SENALES_BAJA)


def asegurar_linea_de_baja(cuerpo: str) -> str:
    return cuerpo if tiene_linea_de_baja(cuerpo) else cuerpo.rstrip() + LINEA_BAJA


def normalizar_cuerpo_correo(cuerpo: str, *, es_frio: bool) -> str:
    """Limpia espacios excesivos, quita firmas redundantes y deja a lo sumo una línea de baja."""
    cuerpo_limpio, linea_baja = autopilot_dispatcher.limpiar_cuerpo_correo(cuerpo)
    base = cuerpo_limpio or (cuerpo or "").strip()
    if es_frio:
        if linea_baja:
            return f"{base}\n\n{linea_baja}"
        return asegurar_linea_de_baja(base)
    return base


_CLICHES_IA: tuple[tuple[str, str], ...] = (
    ("cliche_ia", "en el mundo actual"),
    ("cliche_ia", "en la era digital"),
    ("cliche_ia", "solucion integral"),
    ("cliche_ia", "lleva tu negocio al siguiente nivel"),
    ("cliche_ia", "transforma tu negocio"),
    ("cliche_ia", "no te quedes atras"),
    ("cliche_ia", "estimado cliente"),
    ("cliche_ia", "espero que este correo te encuentre bien"),
    ("cliche_ia", "espero te encuentres muy bien"),
    ("cliche_ia", "sin mas preambulos"),
    ("cliche_ia", "quedo a su entera disposicion"),
    ("cliche_ia", "saludos cordiales"),
    ("cliche_ia", "me permito escribir"),
    ("apertura_robotica", "hola, equipo de"),
    ("apertura_robotica", "una pregunta directa:"),
    ("apertura_robotica", "les escribo porque algo que veo mucho"),
    ("copia_nicho", "seguro contra errores de produccion"),
    ("copia_nicho", "cuello de botella operativo o visual"),
    ("copia_nicho", "soluciones a la medida con ia"),
)
_RE_VINETAS = re.compile(r"(?m)^\s*(?:[-•*]|\d+\.)\s+\S")
_RE_EMOJIS_SPAM = re.compile(r"[🚀🔥✨💡🎯⚡🌟🎉💥📈]")
MAX_PALABRAS_CORREO_FRIO = 130


def revisar_calidad_humana(
    asunto: str,
    cuerpo: str,
    *,
    es_frio: bool,
    asuntos_recientes: list[str] | None = None,
) -> list[str]:
    """Guarda en código contra correos robóticos, largos, con viñetas o plantillas repetidas."""
    if not es_frio:
        return []
    motivos: list[str] = []
    cuerpo_sin_baja, _ = autopilot_dispatcher.limpiar_cuerpo_correo(cuerpo)
    texto_eval = cuerpo_sin_baja or cuerpo
    plano_total = _plano(f"{asunto}\n{texto_eval}")

    for tipo, frase in _CLICHES_IA:
        if frase in plano_total:
            motivos.append(f"{tipo}: '{frase}'")

    if _RE_VINETAS.search(texto_eval):
        motivos.append("vinetas_en_correo_frio: evita listas con viñetas en primer contacto")

    if _RE_EMOJIS_SPAM.search(f"{asunto} {texto_eval}"):
        motivos.append("emojis_decorativos: quita emojis de marketing")

    if (asunto + " " + texto_eval).count("!") > 0:
        motivos.append("exceso_exclamaciones: usa 0 signos de exclamación en correos fríos (ADN Raymond)")

    if texto_eval.count("—") > 1:
        motivos.append("exceso_guiones_largos: evita guiones largos decorativos (—)")

    palabras = re.findall(r"\S+", texto_eval)
    if len(palabras) > MAX_PALABRAS_CORREO_FRIO:
        motivos.append(f"muy_largo: {len(palabras)} palabras (máximo {MAX_PALABRAS_CORREO_FRIO})")

    asunto_norm = _plano(asunto).strip()
    if len(asunto_norm) >= 12 and asuntos_recientes:
        recientes_norm = {_plano(a).strip() for a in asuntos_recientes if a}
        if asunto_norm in recientes_norm:
            motivos.append("asunto_repetido_hoy: crea un asunto único para este negocio")

    return motivos


# ------------------------------------------------------------------ modelos de correo y aprendizaje

# 4 modelos sobrios, 100% dentro de la voz real de Raymond en El Socio (asuntos cortos 1-4 palabras,
# 0 exclamaciones, saludo natural "Buen día, señores [Marca]" o "Hola [Nombre]" y cierre "Quedo atento, muchas gracias.").
MODELOS_CORREO: tuple[dict[str, str], ...] = (
    {
        "id": "muestra_directa",
        "nombre": "Muestra o ejemplo primero",
        "guia": (
            "Asunto de 1-4 palabras. Saludo natural ('Buen día, señores [Marca],' o 'Hola [Nombre],'). "
            "Abre mencionando 1 detalle real del dossier ('Pasé por su perfil y vi...'). En una frase corta explica qué "
            "haces en El Socio para un negocio como el suyo. Cierra ofreciendo mostrar un ejemplo sin compromiso "
            "y remata con 'Quedo atento, muchas gracias.' (0 exclamaciones). 50-80 palabras."
        ),
    },
    {
        "id": "observacion_puntual",
        "nombre": "Observación puntual + pregunta de colega",
        "guia": (
            "Asunto de 1-4 palabras. Saludo sobrio de Raymond ('Buen día, señores [Marca],' o 'Hola [Nombre],'). "
            "Abre con una observación concreta sobre lo que viste en su perfil/web ('me surgió la duda de...'), "
            "sin halagos vacíos. Conecta en 1 frase práctica y cierra con pregunta directa ('¿les funciona para su formato "
            "o ya lo tienen resuelto?'). Remata con 'Quedo atento, muchas gracias.' (0 exclamaciones). 45-75 palabras."
        ),
    },
    {
        "id": "caso_real",
        "nombre": "Caso real breve sin cifras",
        "guia": (
            "Asunto de 1-4 palabras. Saludo natural de Raymond y presentación breve como Raymond, de El Socio. "
            "Conecta su negocio (del dossier) con un caso real y concreto que ya resolvimos (ej. motor que edita "
            "historias automáticas para un bar, marca creada desde cero, registro INVIMA — sin cifras ni inventos). "
            "Explica en 1 línea cómo aplicaría hoy y pregunta con calma si vale la pena mostrarles cómo funciona. "
            "Cierra con 'Quedo atento, muchas gracias.' (0 exclamaciones). 55-85 palabras."
        ),
    },
    {
        "id": "ultra_breve",
        "nombre": "Nota relámpago desde el celular",
        "guia": (
            "Estilo ultra directo de Raymond desde el celular (35-55 palabras, asunto de 1-3 palabras, 0 exclamaciones). "
            "Saludo corto + qué viste en su perfil/web + qué resuelves en El Socio + pregunta liviana "
            "('¿les sirve ver un ejemplo o ahorita no están en eso? Quedo atento, muchas gracias.'). Cero adornos."
        ),
    },
)
MODELOS_POR_ID: dict[str, dict[str, str]] = {m["id"]: m for m in MODELOS_CORREO}
MIN_ENVIOS_EXPLORACION = 4  # envíos reales por modelo antes de favorecer al ganador


def puntaje_modelo_correo(stats: dict[str, int]) -> float:
    """Puntaje conservador suavizado: premia interesados reales y penaliza bajas/rechazos."""
    enviados = int(stats.get("enviados", 0))
    positivos = int(stats.get("positivos", 0))
    respuestas = int(stats.get("respuestas", 0))
    negativos = int(stats.get("negativos", 0))
    neutras = max(0, respuestas - positivos)
    return round((positivos * 3.0 + neutras * 1.0 - negativos * 2.0 + 0.5) / (enviados + 2.0), 4)


def _stats_para_seleccion(nicho: str = "") -> tuple[dict[str, dict[str, int]], str]:
    """Usa datos del nicho si ya hay muestra útil; si no, usa el consolidado real de todos los nichos."""
    if not database.DB_PATH.exists():
        return {}, "sin_bd"
    por_nicho = database.summarize_email_style_performance(nicho) if (nicho or "").strip() else {}
    total_nicho = sum(int(v.get("enviados", 0)) for v in por_nicho.values())
    if total_nicho >= len(MODELOS_CORREO) * MIN_ENVIOS_EXPLORACION:
        return por_nicho, f"nicho:{nicho.strip()}"
    global_stats = database.summarize_email_style_performance("")
    return global_stats, "global"


def resumen_rendimiento_modelos(nicho: str = "") -> list[dict[str, object]]:
    """Tabla limpia de rendimiento real de los 4 modelos (para diagnóstico y dry-run)."""
    stats, _ = _stats_para_seleccion(nicho)
    salida: list[dict[str, object]] = []
    for m in MODELOS_CORREO:
        st = stats.get(m["id"], {"enviados": 0, "positivos": 0, "respuestas": 0, "negativos": 0})
        salida.append({
            "id": m["id"],
            "nombre": m["nombre"],
            "enviados": int(st.get("enviados", 0)),
            "positivos": int(st.get("positivos", 0)),
            "respuestas": int(st.get("respuestas", 0)),
            "negativos": int(st.get("negativos", 0)),
            "puntaje": puntaje_modelo_correo(st),
        })
    return salida


def elegir_modelo_correo(nicho: str = "") -> dict[str, object]:
    """Elige el modelo de correo combinando exploración equilibrada + uso del ganador real.

    - Mientras algún modelo tenga menos de `MIN_ENVIOS_EXPLORACION` envíos (o no haya ninguna
      señal real todavía), rota por el menos probado evitando repetir el inmediatamente anterior.
    - Cuando ya hay datos reales, usa el modelo ganador el 75% de las veces (3 de cada 4 envíos)
      y dedica el 25% restante (1 de cada 4) a seguir probando el segundo mejor modelo sano
      (nunca uno con tasa alta de bajas) para adaptarse al mercado sin estancarse.
    """
    stats, alcance = _stats_para_seleccion(nicho)
    ultimo = database.get_last_used_email_style(nicho) or database.get_last_used_email_style("")

    evaluados: list[tuple[dict[str, str], dict[str, int], float]] = []
    for m in MODELOS_CORREO:
        st = stats.get(m["id"], {"enviados": 0, "positivos": 0, "respuestas": 0, "negativos": 0})
        evaluados.append((m, st, puntaje_modelo_correo(st)))

    total_enviados = sum(int(st["enviados"]) for _, st, _ in evaluados)
    hay_senales = any(
        int(st["positivos"]) > 0 or int(st["respuestas"]) > 0 or int(st["negativos"]) > 0
        for _, st, _ in evaluados
    )
    falta_explorar = any(int(st["enviados"]) < MIN_ENVIOS_EXPLORACION for _, st, _ in evaluados)

    if falta_explorar or not hay_senales:
        # Fase de exploración: elige el menos enviado (evitando repetir el último en empate).
        candidatos = sorted(
            evaluados,
            key=lambda item: (int(item[1]["enviados"]), 1 if item[0]["id"] == ultimo else 0),
        )
        elegido, st, score = candidatos[0]
        return {
            "id": elegido["id"],
            "nombre": elegido["nombre"],
            "guia": elegido["guia"],
            "modo": "exploracion",
            "alcance": alcance,
            "puntaje": score,
            "stats": st,
        }

    # Fase de aprendizaje: ordena de mayor a menor efectividad real.
    ordenados = sorted(
        evaluados,
        key=lambda item: (-item[2], -int(item[1]["positivos"]), int(item[1]["negativos"]), int(item[1]["enviados"])),
    )
    ganador, st_g, score_g = ordenados[0]

    # 1 de cada 4 envíos explora un retador sano (sin alta tasa de bajas) para seguir aprendiendo.
    if total_enviados % 4 == 3 and len(ordenados) > 1:
        retadores_sanos = [
            item for item in ordenados[1:]
            if not (int(item[1]["negativos"]) >= 2 and int(item[1]["negativos"]) > int(item[1]["positivos"]))
        ]
        if retadores_sanos:
            retadores_sanos.sort(key=lambda item: (int(item[1]["enviados"]), -item[2]))
            retador, st_r, score_r = retadores_sanos[0]
            return {
                "id": retador["id"],
                "nombre": retador["nombre"],
                "guia": retador["guia"],
                "modo": "aprendizaje_exploracion",
                "alcance": alcance,
                "puntaje": score_r,
                "stats": st_r,
                "ganador_actual": ganador["id"],
            }

    return {
        "id": ganador["id"],
        "nombre": ganador["nombre"],
        "guia": ganador["guia"],
        "modo": "ganador",
        "alcance": alcance,
        "puntaje": score_g,
        "stats": st_g,
    }


# Lo que escribe un lead cuando quiere que lo dejen en paz. Se actúa en CÓDIGO:
# no se depende de que el modelo llame cambiar_etapa.
_SENALES_PIDE_BAJA = (
    "no me escriban", "no me escribas", "no me escriba", "no me vuelvan a escribir",
    "no me vuelvas a escribir", "no vuelvan a escribirme", "no me contacten",
    "darme de baja", "dame de baja", "deme de baja", "darnos de baja", "quiero la baja",
    "no quiero recibir", "no deseo recibir", "no me interesa recibir", "quitenme de",
    "borren mi correo", "borra mi correo", "remover mi correo", "eliminar mi correo",
    "dejen de escribirme", "deja de escribirme", "dejenme en paz", "es spam", "esto es spam",
    "desuscribir", "desuscribeme", "unsubscribe", "remove me",
)
# Palabras que por sí solas son un opt-out, pero SOLO si son todo el mensaje: en una frase
# normal son cualquier cosa ("foto de baja resolución", "planta baja", "video stop motion").
_PALABRAS_OPT_OUT_SOLAS = ("baja", "bajame", "bajarme", "stop", "unsubscribe", "remove")
# Cortesías que no cambian el sentido de un "BAJA" a secas. Las más largas van primero.
_CORTESIAS_BREVES = tuple(sorted(
    ("por favor", "porfavor", "porfa", "muchas gracias", "gracias", "please", "thanks",
     "thank you", "hola", "buenos dias", "buenas tardes", "buenas noches", "buenas", "saludos"),
    key=len, reverse=True,
))
MAX_PALABRAS_OPT_OUT = 4


def _es_opt_out_corto(plano: str) -> bool:
    """True si TODO el mensaje es un opt-out de una palabra: 'BAJA', 'baja.', 'baja por favor'."""
    palabras = re.findall(r"[a-z0-9]+", plano)
    if not palabras or len(palabras) > MAX_PALABRAS_OPT_OUT:
        return False
    limpio = " ".join(palabras)
    for cortesia in _CORTESIAS_BREVES:
        limpio = limpio.replace(cortesia, " ")
    restantes = limpio.split()
    return len(restantes) == 1 and restantes[0] in _PALABRAS_OPT_OUT_SOLAS


def pide_la_baja(mensaje: str) -> bool:
    """True si el lead pidió que no se le vuelva a escribir.

    Las frases explícitas valen en cualquier parte del mensaje. Las palabras sueltas
    ('baja', 'stop') solo valen si son el mensaje entero, para no leer una baja en
    'tengo una foto de baja resolución' o 'render de la planta baja'.
    """
    plano = _plano(mensaje or "")
    if any(s in plano for s in _SENALES_PIDE_BAJA):
        return True
    return _es_opt_out_corto(plano)


# ------------------------------------------------------------------ definición de herramientas

# Los nombres que viaja a la API son ASCII: la API solo acepta [a-zA-Z0-9_-] en
# `name`, así que 'dueño' se escribe 'dueno' en el cable. Los alias con ñ se aceptan igual.
HERRAMIENTAS = [
    {
        "name": "enviar_correo",
        "description": ("Encola un correo para este lead. No lo envía al instante: lo pone en la cola "
                        "y el motor lo manda respetando horario y tope diario. Prohibido escribir "
                        "cifras, precios, formas de pago, links de pago, clichés de IA, firmas ni "
                        "líneas de baja duplicadas (el motor agrega firma limpia y baja automática)."),
        "input_schema": {
            "type": "object",
            "properties": {
                "asunto": {"type": "string", "description": "Asunto humano y único de 2 a 5 palabras (minúsculas naturales, sin cifras ni preguntas de vendedor)."},
                "cuerpo": {"type": "string", "description": "Texto natural de 2-3 micro-párrafos cortos (45-85 palabras en frío), sin firma ni línea de baja repetida."},
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

_SECCIONES_NICHO_PROHIBIDAS = ("precio", "queries", "tarifa", "valor")


def cargar_contexto_nicho_sin_precios(nicho: str) -> str:
    """Lee cliente ideal, dolor y ángulo de `nichos/<nicho>.md` SIN precios ni cifras.

    `nichos/*.md` incluye `## Precio de referencia` para consulta humana de Raymond.
    El código recorta esa sección entera y además filtra línea por línea con
    `revisar_guarda_precios`, de modo que ninguna cifra llegue jamás al modelo.
    """
    limpio = re.sub(r"[^a-zA-Z0-9_-]", "", (nicho or "").strip())
    if not limpio or limpio.startswith("_"):
        return ""
    ruta = NICHOS_DIR / f"{limpio}.md"
    if not ruta.exists():
        return ""

    bloques_seguros: list[str] = []
    saltar_seccion = False
    en_bloque_codigo = False
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        cruda = linea.strip()
        if cruda.startswith("```"):
            en_bloque_codigo = not en_bloque_codigo
            continue
        if en_bloque_codigo:
            continue
        if cruda.startswith("## "):
            titulo_bajo = _plano(cruda[3:])
            saltar_seccion = any(p in titulo_bajo for p in _SECCIONES_NICHO_PROHIBIDAS)
            if not saltar_seccion:
                bloques_seguros.append(cruda)
            continue
        if saltar_seccion:
            continue
        # Filtro adicional línea por línea: ni una cifra ni moneda se cuela.
        if cruda and revisar_guarda_precios(cruda):
            continue
        bloques_seguros.append(linea)

    resultado = "\n".join(bloques_seguros).strip()
    return resultado


def cargar_todos_los_nichos_sin_precios() -> str:
    """Devuelve todos los nichos activos limpios de precios (para el cerebro de contenido)."""
    if not NICHOS_DIR.is_dir():
        return ""
    partes = []
    for ruta in sorted(NICHOS_DIR.glob("*.md")):
        if ruta.name.startswith("_"):
            continue
        limpio = cargar_contexto_nicho_sin_precios(ruta.stem)
        if limpio:
            partes.append(limpio)
    return "\n\n".join(partes)


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
    for ruta_skill in SKILLS_CALIDAD:
        if ruta_skill.exists():
            # Se pasa cada línea que pudiera contradecir la regla de cero cifras con aviso claro.
            partes.append(ruta_skill.read_text(encoding="utf-8").strip())
    partes.append(
        "## Reglas del motor (las aplica el código, no tú)\n"
        "- El correo se encola, no se envía al instante. Si una herramienta te devuelve un error, "
        "corrige y vuelve a intentar con otro texto; no insistas con el mismo.\n"
        "- Cualquier cifra, número de precio, porcentaje, forma de pago o link de pago en un correo "
        "lo bloquea el código (incluso si una guía general menciona 'un número', en El Socio usa "
        "SIEMPRE casos reales cualitativos sin cifras). Si necesitas hablar de valor, usa pedir_precio_al_dueno.\n"
        "- El código también bloquea correos en frío con clichés de IA, viñetas, emojis de relleno, "
        "exceso de longitud o asuntos repetidos el mismo día.\n"
        "- NO escribas firma ('Saludos, El Socio', 'Raymond') ni líneas de baja: el motor agrega la "
        "firma minimalista y el pie de baja una sola vez al enviar.\n"
        "- Si el dossier demuestra que el negocio NO encaja con El Socio (ej. telecomunicaciones, "
        "clínica médica sin tienda online, empresa gigante irrelevante), NO envíes correo: llama "
        "`cambiar_etapa` con `no_interesado` explicando por qué.\n"
        "- Autorrespuestas, confirmaciones de `Form Submitted`, mensajes de tokens/códigos de verificación, "
        "tickets automáticos o avisos de sistema NUNCA son leads ni ventas: jamás los respondas ni avises al dueño.\n"
        "- Tienes pocos turnos. Analiza el dossier, redacta algo realmente humano y termina."
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
            # Pausa antes de reintentar: un 429 sin espera solo gasta el cupo más rápido.
            time.sleep(PAUSA_REINTENTO * (intento + 1))
        except urllib.error.URLError as err:
            ultimo = f"red: {err.reason}"
            if intento == MAX_REINTENTOS:
                raise ErrorAPI(ultimo) from None
            time.sleep(PAUSA_REINTENTO * (intento + 1))
    raise ErrorAPI(ultimo or "sin respuesta")


# ------------------------------------------------------------------ el agente

ETAPAS_CERRADAS = ("baja", "no_interesado")


class AgenteVentas:
    def __init__(self, cfg: dict[str, str], *, dry_run: bool = False, con_api: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run
        self.con_api = con_api and dry_run
        # Modo simulado = el dry-run por defecto: NI UN TOKEN de la API, ni una escritura en BD.
        self.simulado = dry_run and not self.con_api
        self.conf = leer_configuracion(cfg)
        self.modelo = self.conf["modelo"]
        self.turno = 0
        self.lead: dict | None = None
        self.estilo_actual: str = ""
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

    def _gasto_hoy_usd(self) -> float:
        """Gasto del día. En dry-run --con-api el log no se escribe, así que se suma a mano."""
        return database.agent_cost_today_usd() + (self.costo_corrida if self.dry_run else 0.0)

    def guardas_previas(self) -> str:
        """Lo que se revisa ANTES de gastar un solo token. Devuelve '' si se puede operar."""
        if self.simulado:
            # Nada que gastar y nada que escribir: no se exige API key ni se abre la BD.
            return ""
        if not self.conf["tiene_api_key"]:
            return "Falta ANTHROPIC_API_KEY en .env — el agente no llama a la API."
        encolados = database.agent_emails_queued_today()
        if encolados >= self.conf["max_emails"]:
            return f"Tope diario de correos alcanzado ({encolados}/{self.conf['max_emails']})."
        gastado = self._gasto_hoy_usd()
        if gastado >= self.conf["max_usd"]:
            return f"Tope diario de gasto alcanzado ({gastado:.4f}/{self.conf['max_usd']:.2f} USD)."
        return ""

    def motivo_lead_cerrado(self) -> str:
        """Un lead de baja, no interesado o rebotado no se toca: ni API, ni correo."""
        lead = self.lead or {}
        etapa = str(lead.get("stage") or "").strip().lower()
        if etapa in ETAPAS_CERRADAS:
            return f"Lead en etapa '{etapa}': no se le escribe ni se llama a la API."
        try:
            rebotado = int(lead.get("bounced") or 0)
        except (TypeError, ValueError):
            rebotado = 0
        if rebotado == 1:
            return "El correo de este lead rebotó (bounced=1): no se le escribe."
        return ""

    def _cupo_correos_libre(self) -> tuple[bool, str]:
        if self.simulado:
            return True, ""
        encolados = database.agent_emails_queued_today()
        if encolados >= self.conf["max_emails"]:
            return False, (f"Tope diario de correos alcanzado ({encolados}/{self.conf['max_emails']}). "
                           "No encoles más hoy.")
        return True, ""

    # --- herramientas ---------------------------------------------------

    def _tool_enviar_correo(self, args: dict, *, es_frio: bool) -> tuple[bool, str]:
        cerrado = self.motivo_lead_cerrado()
        if cerrado:
            self._log("enviar_correo", argumentos=json.dumps({"asunto": args.get("asunto", "")},
                                                             ensure_ascii=False),
                      resultado="rechazado: lead cerrado", bloqueado=cerrado)
            self.acciones.append(f"correo RECHAZADO: {cerrado}")
            return False, cerrado + " No insistas: este lead está cerrado."

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

        asuntos_hoy = []
        if not self.simulado and database.DB_PATH.exists():
            try:
                asuntos_hoy = database.list_recent_subjects_today()
            except Exception:
                asuntos_hoy = []

        defectos = revisar_calidad_humana(
            asunto, cuerpo, es_frio=es_frio, asuntos_recientes=asuntos_hoy,
        )
        if defectos:
            detalle_calidad = "; ".join(defectos[:5])
            self._log("enviar_correo", argumentos=json.dumps(args, ensure_ascii=False),
                      resultado="rechazado por calidad humana", bloqueado=f"calidad: {detalle_calidad}")
            self.acciones.append(f"correo BLOQUEADO por calidad ({detalle_calidad})")
            return False, (
                "BLOQUEADO por filtro de calidad humana: " + detalle_calidad +
                ". Reescribe como un humano real (45-85 palabras, asunto único de 2-5 palabras, "
                "sin clichés de IA, sin viñetas y sin firma)."
            )

        cuerpo = normalizar_cuerpo_correo(cuerpo, es_frio=es_frio)

        if not self.simulado and database.already_emailed_today(destinatario):
            return False, "Ya hay un correo encolado o enviado hoy a esta dirección. No dupliques."

        libre, aviso = self._cupo_correos_libre()
        if not libre:
            return False, aviso

        if self.dry_run:
            self.acciones.append(f"[dry-run] correo a {destinatario} | asunto: {asunto}")
            return True, "Correo validado y listo para encolar (dry-run: no se encoló)."

        estilo_envio = self.estilo_actual if es_frio else ""
        job_id = database.enqueue_email(
            recipient=destinatario, subject=asunto, body=cuerpo,
            nicho=(self.lead or {}).get("nicho", ""),
            estilo=estilo_envio,
        )
        self._log("enviar_correo",
                  argumentos=json.dumps({"asunto": asunto, "estilo": estilo_envio}, ensure_ascii=False),
                  resultado=f"encolado job {job_id}")
        sufijo_estilo = f" [modelo: {estilo_envio}]" if estilo_envio else ""
        self.acciones.append(f"correo encolado (job {job_id}) a {destinatario}{sufijo_estilo}")
        # Contactado en frío = ya no es un lead nuevo. Lo mueve el CÓDIGO, no el modelo:
        # si se deja en 'nuevo_lead', mañana vuelve a salir en la lista de contacto en frío.
        if es_frio and str((self.lead or {}).get("stage") or "") == "nuevo_lead" and self.lead.get("id"):
            database.update_lead_stage(self.lead["id"], "contactado")
            self.lead["stage"] = "contactado"
            self.acciones.append("etapa automática: nuevo_lead -> contactado")
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

    # --- lead -----------------------------------------------------------

    _PREFIJOS_CORREO_GENERICO = frozenset({
        "info", "hola", "contacto", "contactenos", "ventas", "comercial", "gerencia",
        "pedidos", "mercadeo", "diseno", "estudio", "proyectos", "direccion", "atencion",
        "tienda", "administracion", "servicioalcliente", "soporte", "hello", "contact",
        "sales", "team", "equipo", "soluciones", "salud", "clientes", "reservas",
    })

    @classmethod
    def _extraer_nombre_persona_email(cls, email_addr: str) -> str:
        """Detecta nombre real solo si el correo es claramente de persona (ej. santiago.salazar@...).

        Delega en `prospect_hunter` para que el buscador y el redactor usen el mismo criterio:
        esta versión no reconocía `mariana@` (un solo nombre, sin punto) y saludaba a la empresa.
        """
        local = (email_addr or "").split("@", 1)[0].strip().lower()
        if not local or local in cls._PREFIJOS_CORREO_GENERICO:
            return ""
        try:
            import prospect_hunter  # noqa: PLC0415

            nombre = prospect_hunter.nombre_de_pila_desde_email(email_addr)
            if nombre and nombre.lower() not in cls._PREFIJOS_CORREO_GENERICO:
                return nombre
            if nombre:
                return ""
        except Exception:
            pass
        if "." in local or "_" in local:
            primero = re.split(r"[._-]+", local)[0]
            if primero.isalpha() and 3 <= len(primero) <= 14 and primero not in cls._PREFIJOS_CORREO_GENERICO:
                return primero.capitalize()
        return ""

    def _enriquecer_lead_si_falta(self, nicho_efectivo: str) -> None:
        """Investiga la web del lead si todavía no tiene dossier (solo fuera de dry-run)."""
        if self.dry_run or not self.lead or (self.lead.get("dossier") or "").strip():
            return
        email_lead = (self.lead.get("email") or "").strip()
        if not email_lead or "@" not in email_lead:
            return
        try:
            import prospect_hunter  # noqa: PLC0415

            perfil = prospect_hunter.enriquecer_lead_por_dominio(
                email_lead, nicho=nicho_efectivo, website=str(self.lead.get("website") or ""),
            )
            if not perfil:
                return
            nueva_marca = str(perfil.get("marca") or "").strip()
            empresa_actual = str(self.lead.get("company") or "").strip()
            empresa_final = (
                nueva_marca
                if nueva_marca and (not empresa_actual or prospect_hunter._parece_titulo_seo(empresa_actual))
                else empresa_actual
            )
            dossier_txt = str(perfil.get("dossier") or "").strip()
            if not perfil.get("encaja"):
                motivo = str(perfil.get("motivo_descarte") or "fuera_de_nicho")
                dossier_txt = (dossier_txt + f"\nALERTA DE ENCAJE: posible negocio fuera de nicho ({motivo}).").strip()
            website_txt = str(perfil.get("website") or self.lead.get("website") or "").strip()
            wa_txt = str(perfil.get("whatsapp") or self.lead.get("whatsapp") or "").strip()

            self.lead["company"] = empresa_final
            self.lead["website"] = website_txt
            self.lead["dossier"] = dossier_txt
            if wa_txt:
                self.lead["whatsapp"] = wa_txt

            if self.lead.get("id"):
                database.update_lead_enrichment(
                    int(self.lead["id"]),
                    company=empresa_final or None,
                    whatsapp=wa_txt or None,
                    website=website_txt,
                    dossier=dossier_txt,
                )
        except Exception:
            pass

    def _cargar_lead(self, lead_email: str, nicho: str) -> dict:
        """En dry-run nunca crea el lead; si no existe, se arma en memoria."""
        existente = None
        if not self.simulado or database.DB_PATH.exists():
            existente = database.get_lead_by_email(lead_email)
        if existente:
            return existente
        if self.dry_run:
            return {"id": None, "email": lead_email.lower().strip(), "company": "",
                    "nicho": nicho, "stage": "nuevo_lead", "notes": "", "bounced": 0,
                    "website": "", "dossier": ""}
        lead_id = database.upsert_lead(
            name="", company="", email=lead_email, nicho=nicho,
            source="sales_agent", stage="nuevo_lead", notes="Creado por sales_agent",
        )
        return database.get_lead_by_email(lead_email) or {
            "id": lead_id, "email": lead_email.lower().strip(), "stage": "nuevo_lead",
            "bounced": 0, "website": "", "dossier": "",
        }

    def _dar_de_baja(self, porque: str) -> None:
        """Baja aplicada por el código: etapa + cancelación de todo lo pendiente."""
        self.acciones.append(f"BAJA automática ({porque}): cancelado todo lo pendiente")
        if self.dry_run or not self.lead or not self.lead.get("id"):
            return
        nota = f"{(self.lead.get('notes') or '')} | BAJA ({porque})".strip(" |")
        database.update_lead_stage(self.lead["id"], "baja", notes=nota[:2000])
        database.cancel_pending_outbox_for_recipient(self.lead.get("email", ""))
        database.cancel_followups_for_lead(self.lead["id"])
        self.lead["stage"] = "baja"
        self._log("baja_automatica", resultado=f"etapa baja + pendientes cancelados ({porque})")

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

    def correr(self, *, lead_email: str, mensaje_lead: str = "", nicho: str = "",
               motivo_seguimiento: str = "") -> dict:
        # Autorrespuestas, Form Submitted, tokens y avisos de sistema NUNCA son leads ni ventas:
        # se cortan antes de gastar saldo o tocar el lead.
        if mensaje_lead.strip() and autopilot_dispatcher.es_correo_automatico(
            "", mensaje_lead, sender_email=lead_email,
        ):
            self.acciones.append("autorrespuesta ignorada (Form Submitted / token / correo automático)")
            return {"ok": True, "motivo": "autorrespuesta_ignorada", "acciones": self.acciones,
                    "costo_usd": 0.0, "turnos": 0}

        # La baja va PRIMERO, antes de los topes y de exigir la API key: dar de baja cuesta
        # 0 USD y 0 correos, y a nadie se le puede negar por un tope diario. No se crea el
        # lead si no existe: solo se cierra el que ya está en la BD.
        if mensaje_lead.strip() and pide_la_baja(mensaje_lead):
            self.lead = (
                {"id": None, "email": lead_email.lower().strip(), "company": "", "nicho": nicho,
                 "stage": "nuevo_lead", "notes": "", "bounced": 0}
                if self.dry_run else database.get_lead_by_email(lead_email)
            )
            self._dar_de_baja("lo pidió en su mensaje")
            return {"ok": True, "motivo": "baja_pedida_por_el_lead", "acciones": self.acciones,
                    "costo_usd": 0.0, "turnos": 0}

        bloqueo = self.guardas_previas()
        if bloqueo:
            return {"ok": False, "motivo": bloqueo, "acciones": [], "costo_usd": 0.0, "turnos": 0}

        self.lead = self._cargar_lead(lead_email, nicho)

        # Antes de la API: un lead cerrado o rebotado se corta aquí mismo.
        cerrado = self.motivo_lead_cerrado()
        if cerrado:
            self._log("rechazo_lead_cerrado", resultado=cerrado)
            self.acciones.append(cerrado)
            return {"ok": False, "motivo": cerrado, "acciones": self.acciones,
                    "costo_usd": 0.0, "turnos": 0}

        # `es_frio` = no escribió nada, así que el código le pone la línea de baja igual.
        # Un seguimiento programado también es "frío" para la línea de baja, pero NO es
        # un primer contacto: el modelo tiene que saber que ya le escribimos antes.
        es_frio = not mensaje_lead.strip()
        motivo_seguimiento = (motivo_seguimiento or "").strip()
        es_seguimiento = es_frio and bool(motivo_seguimiento)
        system_prompt = construir_system_prompt()
        nicho_efectivo = (self.lead.get("nicho") or nicho or "").strip()

        # Antes de escribir en frío, analiza la web del lead si todavía no tenemos dossier
        # y elige el modelo de correo más efectivo según resultados reales del mercado.
        modelo_elegido: dict[str, object] | None = None
        self.estilo_actual = ""
        if es_frio and not es_seguimiento:
            self._enriquecer_lead_si_falta(nicho_efectivo)
            modelo_elegido = elegir_modelo_correo(nicho_efectivo)
            self.estilo_actual = str(modelo_elegido["id"])

        guia_nicho = cargar_contexto_nicho_sin_precios(nicho_efectivo)
        nombre_persona = self._extraer_nombre_persona_email(str(self.lead.get("email") or ""))
        dossier_lead = str(self.lead.get("dossier") or "").strip()
        web_lead = str(self.lead.get("website") or "").strip()

        contexto_lead = (
            f"Lead: {self.lead.get('email')}\n"
            f"Persona detectada: {nombre_persona or '(correo general de empresa)'}\n"
            f"Marca / Empresa: {self.lead.get('company') or '(no se sabe)'}\n"
            f"Web: {web_lead or '(no detectada)'}\n"
            f"Nicho: {nicho_efectivo or '(no se sabe)'}\n"
            f"Etapa actual: {self.lead.get('stage')}\n"
            f"Notas previas: {(self.lead.get('notes') or '(ninguna)')[:600]}\n\n"
        )
        if dossier_lead:
            contexto_lead += (
                "Dossier real extraído de su sitio web (ÚSALO para personalizar de verdad sin inventar nada):\n"
                f"{dossier_lead[:1600]}\n\n"
            )
        if guia_nicho:
            contexto_lead += (
                "Referencia de dolor del nicho (inspírate en tus propias palabras, PROHIBIDO copiar frases textuales):\n"
                f"{guia_nicho}\n\n"
            )
        if es_seguimiento:
            contexto_lead += (
                "Esto NO es un primer contacto en frío: es un SEGUIMIENTO programado de un correo "
                "que ya le escribiste y que todavía no te ha contestado.\n"
                f"Motivo del seguimiento: {motivo_seguimiento[:300]}\n"
                "Escríbele un correo muy corto (35-55 palabras) que retome lo anterior de forma relajada, "
                "sin repetir el correo pasado, sin reclamar el silencio y sin firma.")
        elif es_frio:
            bloque_modelo = ""
            if modelo_elegido:
                bloque_modelo = (
                    f"\nModelo de correo asignado para esta prueba ({modelo_elegido['id']} — "
                    f"{modelo_elegido['nombre']} | modo: {modelo_elegido['modo']}):\n"
                    f"{modelo_elegido['guia']}\n"
                    "Mantén siempre la voz sobria y humana de El Socio (cero exageraciones ni trucos grotescos).\n"
                )
            contexto_lead += (
                "Es primer contacto en frío. Primero analiza el dossier:\n"
                "1) Si el negocio claramente NO encaja con El Socio (ej. telecom, banco, clínica médica sin tienda online), "
                "NO le escribas: llama `cambiar_etapa` con `no_interesado` y explica el motivo.\n"
                "2) Si SÍ encaja, redacta el correo siguiendo el modelo asignado abajo, usando al menos un detalle "
                "real del dossier. Asunto humano de 2-5 palabras, sin firma y sin línea de baja manual. "
                "Luego programa el seguimiento."
                + bloque_modelo
            )
        else:
            contexto_lead += f"Mensaje del lead:\n\"\"\"\n{mensaje_lead.strip()[:3000]}\n\"\"\""

        if self.simulado:
            # Dry-run por defecto: se valida todo y se devuelve el resumen SIN llamar a la API.
            trampa = revisar_guarda_precios("vale 50000 por nequi", "pagas en mpago.la/2xYz")
            self.acciones.append(
                f"[dry-run] identidad + alcance cargados ({len(system_prompt)} caracteres)")
            self.acciones.append(
                f"[dry-run] lead validado: {self.lead.get('email')} (etapa {self.lead.get('stage')})")
            if es_seguimiento:
                modo = f"seguimiento programado ({motivo_seguimiento[:60]})"
            else:
                modo = "correo en frío" if es_frio else "respuesta a un mensaje"
            self.acciones.append(f"[dry-run] modo: {modo}")
            if modelo_elegido:
                self.acciones.append(
                    f"[dry-run] modelo de correo elegido: {modelo_elegido['id']} ({modelo_elegido['modo']})")
            self.acciones.append(
                "[dry-run] herramientas listas: " + ", ".join(h["name"] for h in HERRAMIENTAS))
            self.acciones.append(
                f"[dry-run] guarda de precios viva: {len(trampa)} motivos en el texto trampa")
            self.acciones.append("[dry-run] sin API, sin escritura en BD, sin correos")
            return {"ok": True, "motivo": "dry_run_sin_api", "acciones": self.acciones,
                    "costo_usd": 0.0, "turnos": 0}

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
                "output_config": {"effort": "medium"},
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
            if self._gasto_hoy_usd() >= self.conf["max_usd"]:
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
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe en la BD, no encola y NO llama a la API (no gasta saldo).")
    parser.add_argument("--con-api", action="store_true",
                        help="Solo junto a --dry-run: prueba contra la API real. Gasta saldo; "
                             "respeta los topes de correos y de USD antes y dentro del loop.")
    args = parser.parse_args()

    cfg = cargar_config()
    # Con --dry-run --con-api hace falta la BD para poder leer los topes del día.
    if not args.dry_run or args.con_api:
        database.init_db()

    agente = AgenteVentas(cfg, dry_run=args.dry_run, con_api=args.con_api)
    resultado = agente.correr(lead_email=args.lead_email, mensaje_lead=args.mensaje, nicho=args.nicho)
    resultado["modelo"] = agente.modelo
    resultado["dry_run"] = args.dry_run
    resultado["con_api"] = agente.con_api
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

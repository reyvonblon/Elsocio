#!/usr/bin/env python3
"""Automated email dispatch, reply sync & macOS Calendar booking for El Socio."""

from __future__ import annotations

import argparse
import email
import html
import imaplib
import json
import os
import re
import smtplib
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from email.header import decode_header
from email.message import EmailMessage
from email.utils import formataddr
from email.utils import parseaddr
from pathlib import Path

_DISPATCH_LOCK = threading.Lock()
_LAST_REPLENISH_TS = 0.0
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import database  # noqa: E402
import panel_mensajes  # noqa: E402


def load_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#") or "=" not in clean:
                continue
            k, v = clean.split("=", 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    for k in (
        "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM",
        "IMAP_HOST", "MAX_DAILY_EMAILS", "FROM_NAME", "WHATSAPP", "WEBSITE",
        "ANTHROPIC_API_KEY",
    ):
        if os.environ.get(k):
            values[k] = os.environ[k]
    if not (values.get("ANTHROPIC_API_KEY") or "").strip() and database.DB_PATH.exists():
        try:
            guardada = (database.get_settings().get("anthropic_api_key") or "").strip()
            if guardada:
                values["ANTHROPIC_API_KEY"] = guardada
        except Exception:
            pass
    return values


def _load_sales_agent():
    """Import diferido a propósito: `sales_agent` importa este módulo, así que al revés
    tiene que ser perezoso o se arma un import circular. Si falla, el motor sigue.
    """
    try:
        import sales_agent  # noqa: PLC0415
        return sales_agent
    except Exception:
        return None


def _tiene_anthropic_key(cfg: dict[str, str] | None = None) -> bool:
    cfg = load_env_file() if cfg is None else cfg
    return bool((cfg.get("ANTHROPIC_API_KEY") or "").strip())


# Etapas en las que un lead no vuelve a recibir nada, ni del agente ni del dispatcher.
ETAPAS_CERRADAS = ("baja", "no_interesado")
# La ÚNICA respuesta que justifica quemar saldo del agente. `respuesta_recibida` es el
# cajón del ruido de bandeja ("ok", "recibido", facturas, reenvíos): con 3 USD de saldo
# total, contestar ese ruido con el modelo es tirar el dinero. Si una señal de compra
# real cae ahí, el arreglo es agregarla a `positive_kw`, no abrir la puerta al ruido.
INTENTS_PARA_EL_AGENTE = ("interesado_cita",)


def _lead_esta_cerrado(lead: dict | None) -> bool:
    if not lead:
        return False
    if str(lead.get("stage") or "").strip().lower() in ETAPAS_CERRADAS:
        return True
    try:
        return int(lead.get("bounced") or 0) == 1
    except (TypeError, ValueError):
        return False


# ------------------------------------------------- registro real en RESULTADOS_MERCADO.md

RESULTADOS_FILE = PROJECT_ROOT / "contexto" / "RESULTADOS_MERCADO.md"
# Las dos listas cerradas que declara el propio RESULTADOS_MERCADO.md en su sección Formato.
CANALES_VALIDOS = ("correo", "whatsapp-negocio", "landing", "instagram", "llamada")
RESULTADOS_VALIDOS = ("respondió", "agendó", "silencio", "rebote", "baja")
# Se acepta la forma sin acento y se escribe siempre la canónica, para que la tabla no
# acabe con "respondio" y "respondió" como si fueran dos resultados distintos.
_ALIAS_RESULTADOS = {
    "respondio": "respondió", "respondió": "respondió",
    "agendo": "agendó", "agendó": "agendó",
    "silencio": "silencio", "rebote": "rebote", "baja": "baja",
}
# Una tanda enviada no es "silencio" el mismo día: nadie tuvo tiempo de contestar.
DIAS_PARA_SILENCIO = 7


def _celda_markdown(texto: object, limite: int = 200) -> str:
    """Celda que no puede romper la tabla: sin '|', sin barras invertidas, sin saltos."""
    crudo = "" if texto is None else str(texto)
    crudo = crudo.replace("|", "/").replace("\\", "/")
    crudo = re.sub(r"\s+", " ", crudo).strip()
    return crudo[:limite] or "(sin dato)"


def registrar_resultado_mercado(
    nicho: str, angulo: str, canal: str, cantidad: int, resultado: str, nota: str = "",
    *, ruta: Path | None = None, dry_run: bool = False,
) -> dict[str, object]:
    """Agrega UNA fila real al final de `contexto/RESULTADOS_MERCADO.md`.

    Solo se llama con eventos que de verdad pasaron en la corrida (una respuesta que
    llegó, un rebote que el servidor devolvió, una tanda que ya venció sin respuesta).
    Nunca inventa cifras ni rellena huecos.

    - Valida `canal` y `resultado` contra las listas del propio archivo.
    - Sanitiza cada celda: un '|' o un salto de línea romperían la tabla para siempre.
    - Append EXCLUSIVAMENTE al final (la regla del archivo es "Nada debajo de la tabla").
      No reescribe, no reordena y no borra ninguna fila que ya esté.
    - `dry_run=True` devuelve la fila que escribiría y no toca el disco.

    `ruta` se resuelve en tiempo de ejecución (no como valor por defecto) para que las
    pruebas puedan apuntar a un archivo temporal sin tocar el archivo real.
    """
    ruta = RESULTADOS_FILE if ruta is None else Path(ruta)

    canal_limpio = _celda_markdown(canal, 40).lower()
    if canal_limpio not in CANALES_VALIDOS:
        return {"escrito": False, "error": f"canal inválido: '{canal_limpio}'"}

    resultado_limpio = _ALIAS_RESULTADOS.get(_celda_markdown(resultado, 40).lower(), "")
    if resultado_limpio not in RESULTADOS_VALIDOS:
        return {"escrito": False, "error": f"resultado inválido: '{_celda_markdown(resultado, 40)}'"}

    try:
        n = int(cantidad)
    except (TypeError, ValueError):
        return {"escrito": False, "error": "cantidad no es un número"}
    if n <= 0:
        return {"escrito": False, "error": "cantidad tiene que ser 1 o más"}

    fila = "| {} | {} | {} | {} | {} | {} | {} |".format(
        datetime.now().strftime("%Y-%m-%d"),
        _celda_markdown(nicho, 60),
        _celda_markdown(angulo, 120),
        canal_limpio, n, resultado_limpio,
        _celda_markdown(nota, 220),
    )

    if dry_run:
        return {"escrito": False, "dry_run": True, "fila": fila}
    if not ruta.exists():
        return {"escrito": False, "error": f"no existe {ruta.name}"}

    try:
        actual = ruta.read_text(encoding="utf-8")
        salto = "" if (not actual or actual.endswith("\n")) else "\n"
        with ruta.open("a", encoding="utf-8") as fh:
            fh.write(salto + fila + "\n")
    except OSError as exc:
        return {"escrito": False, "error": str(exc)[:200]}
    return {"escrito": True, "fila": fila}


def _eventos_ya_registrados(ruta: Path) -> set[str]:
    """Marcas `[tanda <dia> / <nicho>]` que ya están en el archivo, para no duplicar."""
    if not ruta.exists():
        return set()
    try:
        # El grupo captura la marca COMPLETA ("tanda <dia> / <nicho>"), tal como se escribe.
        return set(re.findall(r"\[(tanda [^\]]+)\]", ruta.read_text(encoding="utf-8")))
    except OSError:
        return set()


def registrar_silencios_vencidos(
    *, dias: int = DIAS_PARA_SILENCIO, ruta: Path | None = None, dry_run: bool = False,
) -> dict[str, object]:
    """Registra como `silencio` las tandas realmente enviadas hace `dias` o más en las
    que nadie respondió, con el conteo real de correos de esa tanda.

    El silencio se escribe con plazo cumplido, nunca el día del envío. El archivo es su
    propia memoria: cada fila lleva la marca `[tanda <dia> / <nicho>]` y una marca que ya
    está no se vuelve a escribir.
    """
    ruta = RESULTADOS_FILE if ruta is None else Path(ruta)
    if not database.DB_PATH.exists():
        return {"registradas": 0, "razon": "sin_bd"}

    ya_estan = _eventos_ya_registrados(ruta)
    registradas, filas = 0, []
    for tanda in database.summarize_silent_sent_batches(dias=dias):
        marca = f"tanda {tanda['dia']} / {tanda['nicho']}"
        if marca in ya_estan:
            continue
        res = registrar_resultado_mercado(
            tanda["nicho"], "(ángulo no registrado por tanda)", "correo",
            int(tanda["cantidad"]), "silencio",
            f"[{marca}] Enviados reales sin ninguna respuesta tras {dias} días.",
            ruta=ruta, dry_run=dry_run,
        )
        if res.get("escrito") or res.get("dry_run"):
            registradas += 1
            filas.append(res.get("fila", ""))
        ya_estan.add(marca)
    return {"registradas": registradas, "dry_run": dry_run, "filas": filas}


def get_daily_limit(cfg: dict[str, str]) -> int:
    raw = cfg.get("MAX_DAILY_EMAILS")
    if not raw:
        raw = database.get_settings().get("max_daily_emails", "15")
    try:
        return max(1, int(raw))
    except ValueError:
        return 15


def get_autopilot_status() -> dict[str, object]:
    cfg = load_env_file()
    smtp_ready = bool(cfg.get("SMTP_HOST") and cfg.get("SMTP_USER") and cfg.get("SMTP_PASS"))
    return {
        "smtp_ready": smtp_ready,
        "max_daily_emails": get_daily_limit(cfg),
        "sent_today": database.count_sent_emails_today(),
    }


_RE_DESPEDIDA_SOLA = re.compile(
    r"^(?:un\s+saludo|saludos(?:\s+cordiales)?|cordialmente|atentamente|abrazo|un\s+abrazo|"
    r"quedo\s+atento|quedo\s+pendiente|gracias(?:\s+de\s+antemano)?|mil\s+gracias|feliz\s+(?:d[ií]a|tarde|semana))[,!.\s]*$",
    re.IGNORECASE,
)
_RE_FIRMA_PROPIA = re.compile(
    r"^(?:--\s*|—\s*)?(?:raymond(?:\s+vonblon)?|el\s+socio|equipo(?:\s+de)?\s+el\s+socio|"
    r"raymond(?:\s+vonblon)?\s*[-·—]\s*el\s+socio)[.\s]*$",
    re.IGNORECASE,
)
_RE_PARRAFO_BAJA = re.compile(
    r"(?:no\s+quier(?:es|en|as)\s+recibir|no\s+dese(?:as|an)\s+recibir|"
    r"prefier(?:es|en)\s+no\s+recibir|no\s+(?:te|les)\s+interesa\s+recibir|"
    r"para\s+no\s+recibir\s+m[aá]s|si\s+no\s+(?:te|les)\s+interesa.*(?:escrib|baja)|"
    r"respond(?:e|eme|an|ame)\s+(?:con\s+)?(?:la\s+palabra\s+)?[\"']?baja[\"']?|"
    r"dar(?:te|se)?\s+de\s+baja|desuscribir|saco\s+de\s+la\s+lista|"
    r"no\s+(?:te|les)\s+vuelvo\s+a\s+escribir|no\s+(?:te|les)\s+escribo\s+(?:m[aá]s|de\s+nuevo))",
    re.IGNORECASE,
)


def limpiar_cuerpo_correo(body: str) -> tuple[str, str]:
    """Limpia espacios excesivos, quita firmas duplicadas y separa una única línea de baja.

    Devuelve `(cuerpo_limpio, linea_baja)`. Así el correo sale compacto, natural y nunca
    repite despedidas ni avisos de baja.
    """
    normalizado = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    lineas_raw = [ln.rstrip() for ln in normalizado.split("\n")]
    texto = re.sub(r"\n{3,}", "\n\n", "\n".join(lineas_raw)).strip()
    if not texto:
        return "", ""

    bloques = [b.strip() for b in re.split(r"\n\s*\n", texto) if b.strip()]
    linea_baja = ""
    filtrados: list[str] = []

    for bloque in bloques:
        # Si el bloque completo es una línea de baja, se reserva solo la primera (evita duplicados).
        if len(bloque) <= 220 and _RE_PARRAFO_BAJA.search(bloque):
            if not linea_baja:
                linea_baja = re.sub(r"\s+", " ", bloque).strip()
            continue
        filtrados.append(bloque)

    # Quita cierres/firmas redundantes al final que el modelo haya escrito por su cuenta.
    while filtrados:
        ultimo_lineas = [ln.strip() for ln in filtrados[-1].splitlines() if ln.strip()]
        if ultimo_lineas and all(
            _RE_DESPEDIDA_SOLA.match(ln) or _RE_FIRMA_PROPIA.match(ln)
            for ln in ultimo_lineas
        ):
            filtrados.pop()
            continue
        # Si el último bloque termina en una línea suelta de despedida/firma, recorta esa línea.
        recortadas = list(ultimo_lineas)
        while len(recortadas) > 1 and (
            _RE_DESPEDIDA_SOLA.match(recortadas[-1]) or _RE_FIRMA_PROPIA.match(recortadas[-1])
        ):
            recortadas.pop()
        filtrados[-1] = "\n".join(recortadas)
        break

    cuerpo_limpio = "\n\n".join(filtrados).strip()
    return cuerpo_limpio, linea_baja


def build_signature(cfg: dict[str, str]) -> str:
    name = cfg.get("FROM_NAME") or "Raymond Vonblon · El Socio"
    whatsapp = cfg.get("WHATSAPP") or "+57 304 609 0036"
    website = cfg.get("WEBSITE") or "https://reyvonblon.github.io/Elsocio/"
    site_label = re.sub(r"^https?://", "", website).rstrip("/")
    return f"--\n{name}\nMedellín · WhatsApp {whatsapp} · {site_label}"


LOGO_FIRMA_PATH = Path(__file__).resolve().parent.parent / "docs" / "assets" / "logo-firma.png"
LOGO_CID = "logoelsocio"


def usar_logo_en_firma(cfg: dict[str, str]) -> bool:
    """¿Va el logo en el correo? Por defecto NO en el primer contacto frío.

    Un correo frío con imagen de marca se parece a un boletín y Gmail lo manda a la
    pestaña Promociones, donde nadie lo abre. El logo se activa con EMAIL_LOGO=1 o
    cuando ya hay conversación (ahí sí suma y Gmail ya lo tiene en Principal).
    """
    return (cfg.get("EMAIL_LOGO") or "0").strip() not in ("", "0", "no", "false")


def build_html_signature(cfg: dict[str, str], *, con_logo: bool = False) -> str:
    """Firma minimalista y 100% fluida: se ve como un correo humano y nunca rompe el celular."""
    whatsapp_display = cfg.get("WHATSAPP") or "+57 304 609 0036"
    whatsapp_digits = re.sub(r"\D", "", whatsapp_display)
    if len(whatsapp_digits) == 10:
        whatsapp_digits = f"57{whatsapp_digits}"
    website = cfg.get("WEBSITE") or "https://reyvonblon.github.io/Elsocio/"
    site_label = re.sub(r"^https?://", "", website).rstrip("/")
    logo_html = ""
    if con_logo and LOGO_FIRMA_PATH.exists():
        logo_html = (
            f'<div style="margin:0 0 8px 0;"><img src="cid:{LOGO_CID}" alt="El Socio" '
            'width="140" style="width:140px; max-width:60%; height:auto; display:block;" /></div>'
        )
    return (
        '<div style="margin-top:14px; padding-top:10px; border-top:1px solid #e4e4e7; '
        'font-size:13px; line-height:1.45; color:#52525b; max-width:100%;">'
        f'{logo_html}'
        '<div style="font-weight:600; color:#18181b;">Raymond Vonblon &middot; El Socio</div>'
        '<div>Medell&iacute;n &middot; '
        f'<a href="https://wa.me/{whatsapp_digits}" style="color:#18181b; text-decoration:none;">'
        f'WhatsApp {html.escape(whatsapp_display)}</a> &middot; '
        f'<a href="{html.escape(website)}" style="color:#9c1c2e; text-decoration:none;">'
        f'{html.escape(site_label)}</a></div>'
        "</div>"
    )


def build_email_parts(
    cfg: dict[str, str], body: str, *, include_signature: bool = True, con_logo: bool | None = None,
) -> tuple[str, str]:
    """Construye `(texto_plano, html_fluido)` limpios, compactos y adaptables a cualquier pantalla."""
    cuerpo_limpio, linea_baja = limpiar_cuerpo_correo(body)
    if not cuerpo_limpio:
        cuerpo_limpio = (body or "").strip()

    partes_txt = [cuerpo_limpio]
    if include_signature:
        partes_txt.append(build_signature(cfg))
    if linea_baja:
        partes_txt.append(linea_baja)
    full_plain = "\n\n".join(p for p in partes_txt if p)

    parrafos_html: list[str] = []
    bloques = [b.strip() for b in re.split(r"\n\s*\n", cuerpo_limpio) if b.strip()]
    for idx, bloque in enumerate(bloques):
        margin_bottom = "0" if (idx == len(bloques) - 1 and not include_signature and not linea_baja) else "11px"
        contenido = "<br />".join(html.escape(ln) for ln in bloque.splitlines())
        parrafos_html.append(f'<p style="margin:0 0 {margin_bottom} 0;">{contenido}</p>')

    baja_html = ""
    if linea_baja:
        baja_html = (
            '<p style="margin:12px 0 0 0; font-size:11.5px; line-height:1.4; color:#71717a;">'
            f"{html.escape(linea_baja)}</p>"
        )

    if con_logo is None:
        con_logo = usar_logo_en_firma(cfg)
    sig_html = build_html_signature(cfg, con_logo=con_logo) if include_signature else ""
    html_doc = (
        '<!DOCTYPE html><html lang="es"><head>'
        '<meta charset="UTF-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />'
        "</head>"
        '<body style="margin:0; padding:0; font-family:-apple-system, BlinkMacSystemFont, '
        "'Segoe UI', Roboto, Arial, sans-serif; font-size:14px; color:#18181b; line-height:1.5;\">"
        '<div style="max-width:600px; margin:0; padding:0; word-wrap:break-word; '
        'overflow-wrap:break-word;">'
        f'{"".join(parrafos_html)}{sig_html}{baja_html}'
        "</div></body></html>"
    )
    return full_plain, html_doc


def send_smtp_email(
    cfg: dict[str, str], to_addr: str, subject: str, body: str, *,
    include_signature: bool = True, con_logo: bool | None = None,
) -> None:
    msg = EmailMessage()
    nombre_from = (cfg.get("FROM_NAME") or "").strip()
    correo_from = cfg.get("SMTP_FROM") or cfg["SMTP_USER"]
    msg["From"] = formataddr((nombre_from, correo_from)) if nombre_from else correo_from
    msg["To"] = to_addr
    msg["Subject"] = subject
    if con_logo is None:
        con_logo = usar_logo_en_firma(cfg)
    full_plain, html_doc = build_email_parts(
        cfg, body, include_signature=include_signature, con_logo=con_logo,
    )
    msg.set_content(full_plain)
    if include_signature:
        msg.add_alternative(html_doc, subtype="html")
        if con_logo and LOGO_FIRMA_PATH.exists():
            # El logo viaja incrustado (cid:) y no como enlace externo: así se ve aunque el
            # cliente bloquee imágenes remotas, y no delata rastreo.
            msg.get_payload()[-1].add_related(
                LOGO_FIRMA_PATH.read_bytes(), maintype="image", subtype="png",
                cid=f"<{LOGO_CID}>", filename="el-socio.png",
            )

    port = int(cfg.get("SMTP_PORT") or "587")
    host = cfg["SMTP_HOST"]
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
            smtp.login(cfg["SMTP_USER"], cfg["SMTP_PASS"])
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(cfg["SMTP_USER"], cfg["SMTP_PASS"])
            smtp.send_message(msg)


def _is_within_sending_window(settings: dict[str, str]) -> bool:
    try:
        start_h = int(settings.get("autopilot_send_start_hour", "8"))
    except ValueError:
        start_h = 8
    try:
        end_h = int(settings.get("autopilot_send_end_hour", "21"))
    except ValueError:
        end_h = 21
    now_h = datetime.now().hour
    return start_h <= now_h < end_h


def ensure_daily_pipeline(*, force: bool = False) -> dict[str, object]:
    """3-tier replenishment: CSV reserve -> live discovery -> prudent re-engagement."""
    global _LAST_REPLENISH_TS
    database.init_db()
    settings = database.get_settings()
    if not force and settings.get("autopilot_auto_replenish", "1") == "0":
        return {"skipped": "disabled"}
    if not force and not _is_within_sending_window(settings):
        return {"skipped": "outside_window"}
    if not force and (time.time() - _LAST_REPLENISH_TS) < 1800:
        return {"skipped": "cooldown"}

    cfg = load_env_file()
    daily_limit = get_daily_limit(cfg)
    sent_today = database.count_sent_emails_today()
    pending_today = database.count_today_pending_email_jobs()
    deficit = daily_limit - (sent_today + pending_today)
    _LAST_REPLENISH_TS = time.time()

    if deficit <= 0:
        return {"deficit": 0, "sent_today": sent_today, "pending_today": pending_today}

    added_discovered = 0
    added_reengaged = 0

    try:
        import prospect_hunter  # noqa: E402

        discovered = prospect_hunter.discover_new_prospects(needed=deficit, queries_to_run=3)
        for row in discovered:
            if deficit <= 0:
                break
            lead_id = database.upsert_lead(
                name=row["nombre"], company=row["empresa"], email=row["correo"],
                whatsapp=row.get("whatsapp", ""), nicho=row.get("nicho", ""),
                service_interest=row.get("servicio", ""), source="prospeccion_auto",
                stage="nuevo_lead", notes="Descubierto, analizado y verificado (MX OK) por El Socio",
                website=row.get("website", ""), dossier=row.get("dossier", ""),
            )
            added_discovered += 1
            deficit -= 1
    except Exception:
        pass

    if deficit > 0 and settings.get("autopilot_reengage_enabled", "1") != "0":
        candidates = database.list_reengagement_candidates(limit=min(deficit, 3))
        for cand in candidates:
            marca = (cand.get("company") or "").strip()
            subject = f"retomando por {marca}" if marca and len(marca) <= 30 else "retomando mi correo anterior"
            body = (
                "Hola, paso rápido por aquí por si en este momento sí les viene bien revisar lo que te "
                "comenté hace unas semanas.\n\n"
                "Si no es prioridad ahorita, sin problema; y si prefieres que no vuelva a escribir, respóndeme BAJA."
            )
            if database.queue_prudent_reengagement(cand, subject, body):
                added_reengaged += 1
                deficit -= 1

    return {
        "daily_limit": daily_limit, "sent_today": sent_today,
        "added_discovered": added_discovered, "added_reengaged": added_reengaged,
        "remaining_deficit": max(0, deficit),
    }


# Errores de SMTP que significan "esta dirección no existe", no "reintenta más tarde".
_RE_REBOTE_PERMANENTE = re.compile(
    r"5\.1\.[0-9]|\b55[0-3]\b|user\s+unknown|no\s+such\s+user|does\s+not\s+exist|"
    r"address\s+rejected|recipient\s+rejected|mailbox\s+unavailable|invalid\s+recipient",
    re.IGNORECASE,
)


def _es_rebote_permanente(exc: Exception) -> bool:
    """True solo ante un rechazo DEFINITIVO del destinatario. Un timeout, una caída de
    red o un 4xx temporal no son un rebote: ahí el correo se reintenta, no se quema el lead.
    """
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return True
    if isinstance(exc, smtplib.SMTPResponseException) and 500 <= int(exc.smtp_code or 0) < 600:
        return bool(_RE_REBOTE_PERMANENTE.search(f"{exc.smtp_code} {exc.smtp_error}"))
    return bool(_RE_REBOTE_PERMANENTE.search(str(exc)))


def dispatch_due_jobs(*, respect_pacing: bool = False, respect_window: bool = False) -> dict:
    with _DISPATCH_LOCK:
        database.init_db()
        cfg = load_env_file()
        settings = database.get_settings()
        status = get_autopilot_status()
        daily_limit = int(status["max_daily_emails"])
        sent_today = database.count_sent_emails_today()
        pending = database.list_outbox_jobs(status="pending", limit=200)

        sent_count = 0
        skipped_no_creds = skipped_daily_cap = skipped_pacing = skipped_window = failed_count = 0
        cancelled_closed_lead = 0
        bounced_count = 0

        try:
            min_gap_sec = max(30, int(settings.get("autopilot_min_gap_seconds", "180")))
        except ValueError:
            min_gap_sec = 180

        in_window = _is_within_sending_window(settings) if respect_window else True
        last_sent_dt = database.get_last_sent_email_datetime() if respect_pacing else None

        for job in pending:
            # Doble seguro: aunque el correo ya esté en la cola, si el lead pidió la baja,
            # dijo que no o rebotó, NO sale. Se cancela el job y se sigue.
            lead_del_job = database.get_lead_by_email(job["recipient"])
            if _lead_esta_cerrado(lead_del_job):
                database.update_outbox_job(
                    job["id"], "cancelled",
                    f"lead en '{lead_del_job.get('stage')}' / bounced={lead_del_job.get('bounced')}",
                )
                cancelled_closed_lead += 1
                continue
            if not status["smtp_ready"]:
                skipped_no_creds += 1
                continue
            if not in_window:
                skipped_window += 1
                continue
            if sent_today >= daily_limit:
                skipped_daily_cap += 1
                continue
            if respect_pacing and last_sent_dt is not None:
                elapsed = (datetime.now() - last_sent_dt).total_seconds()
                if elapsed < min_gap_sec:
                    skipped_pacing += 1
                    break
            try:
                send_smtp_email(cfg, job["recipient"], job["subject"], job["body"])
                database.update_outbox_job(job["id"], "sent")
                sent_count += 1
                sent_today += 1
                last_sent_dt = datetime.now()
                if respect_pacing:
                    break
            except Exception as exc:
                database.update_outbox_job(job["id"], "failed", str(exc))
                failed_count += 1
                # Rechazo permanente del destinatario = rebote REAL. Hasta ahora quedaba
                # solo como 'failed' y el lead seguía recibiendo correos.
                if _es_rebote_permanente(exc):
                    database.mark_lead_bounced(job["recipient"], str(exc)[:200])
                    bounced_count += 1
                    try:
                        estilo_job = (job.get("estilo") or "").strip()
                        angulo_rebote = f"modelo:{estilo_job}" if estilo_job else "(rebote, ángulo no registrado)"
                        registrar_resultado_mercado(
                            job.get("nicho") or "(sin nicho)", angulo_rebote,
                            "correo", 1, "rebote",
                            f"Rebote real de {job['recipient']}: {str(exc)[:120]}",
                        )
                    except Exception:
                        pass

        status["sent_today"] = sent_today
        return {
            "config_status": status, "sent": sent_count,
            "skipped_missing_credentials": skipped_no_creds, "skipped_daily_cap": skipped_daily_cap,
            "skipped_pacing": skipped_pacing, "skipped_window": skipped_window, "failed": failed_count,
            "cancelled_closed_lead": cancelled_closed_lead, "bounced": bounced_count,
        }


def _decode_mime_header(raw_val: str) -> str:
    if not raw_val:
        return ""
    parts = decode_header(raw_val)
    decoded = []
    for chunk, enc in parts:
        decoded.append(chunk.decode(enc or "utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk))
    return "".join(decoded).strip()


def _html_to_text(raw_html: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw_html)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _strip_quoted_reply(text: str) -> str:
    lines = []
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith(">"):
            continue
        if re.match(r"^(el|on)\s+.+(escribió|wrote):$", low):
            break
        lines.append(line)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _extract_text_snippet(msg: email.message.Message) -> str:
    plain_text = html_text = ""
    if msg.is_multipart():
        for part in msg.walk():
            if "attachment" in str(part.get("Content-Disposition") or "").lower():
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            decoded = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            if part.get_content_type() == "text/plain" and not plain_text:
                plain_text = _html_to_text(decoded)
            elif part.get_content_type() == "text/html" and not html_text:
                html_text = _html_to_text(decoded)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            decoded = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
            if msg.get_content_type() == "text/html":
                html_text = _html_to_text(decoded)
            else:
                plain_text = _html_to_text(decoded)
    return _strip_quoted_reply(plain_text or html_text)[:400]


def notify_mac_desktop(title: str, message: str) -> bool:
    if sys.platform != "darwin" or os.environ.get("ELSOCIO_QUIET") == "1":
        return False
    safe_title = title.replace('"', '\\"')[:80]
    safe_msg = message.replace('"', '\\"')[:180]
    script = f'display notification "{safe_msg}" with title "El Socio" subtitle "{safe_title}" sound name "Glass"'
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=5)
        return True
    except Exception:
        return False


def _applescript_set_date(var_name: str, dt: datetime) -> str:
    """Build an AppleScript snippet that sets var_name to dt via numeric fields (locale-independent)."""
    return (
        f"set {var_name} to (current date)\n"
        f"set year of {var_name} to {dt.year}\n"
        f"set month of {var_name} to {dt.month}\n"
        f"set day of {var_name} to {dt.day}\n"
        f"set hours of {var_name} to {dt.hour}\n"
        f"set minutes of {var_name} to {dt.minute}\n"
        f"set seconds of {var_name} to {dt.second}\n"
    )


def create_calendar_event(summary: str, notes: str, start_dt: datetime, calendar_name: str = "El Socio") -> bool:
    """Create a real event in macOS Calendar.app via AppleScript (creates the calendar if missing)."""
    if sys.platform != "darwin":
        return False
    end_dt = start_dt + timedelta(minutes=30)
    safe_summary = summary.replace('"', "'")[:120]
    safe_notes = notes.replace('"', "'")[:500]
    script = f'''
    {_applescript_set_date("startDate", start_dt)}
    {_applescript_set_date("endDate", end_dt)}
    tell application "Calendar"
        if not (exists calendar "{calendar_name}") then
            make new calendar with properties {{name:"{calendar_name}"}}
        end if
        tell calendar "{calendar_name}"
            make new event with properties {{summary:"{safe_summary}", description:"{safe_notes}", start date:startDate, end date:endDate}}
        end tell
    end tell
    '''
    try:
        result = subprocess.run(["osascript", "-e", script], check=False, timeout=10, capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False


_PREFIJOS_REMITENTE_AUTOMATICO = (
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply", "mailer-daemon",
    "postmaster", "notifications", "notificaciones", "automated", "autoreply",
    "auto-reply", "bounce", "daemon", "security", "verify", "verification", "auth",
)

_AUTO_REPLY_PHRASES = (
    # Form submitted / confirmaciones automáticas de formularios (EN/ES)
    "form submitted", "form submission", "new form submission", "submission received",
    "thank you for your submission", "thanks for your submission",
    "formulario enviado", "formulario recibido", "envío de formulario", "envio de formulario",
    "su formulario ha sido", "tu formulario ha sido",
    # Confirmaciones automáticas de recepción / CRM / helpdesk
    "gracias por contactarnos", "gracias por escribirnos", "gracias por tu mensaje",
    "gracias por comunicarte", "gracias por contactarte", "thank you for contacting",
    "thanks for reaching out", "we received your message", "we have received your",
    "hemos recibido tu mensaje", "hemos recibido tu correo", "hemos recibido tu solicitud",
    "recibimos tu mensaje", "recibimos tu correo", "recibimos tu solicitud",
    "tu solicitud ha sido recibida", "tu mensaje ha sido recibido",
    "pronto nos pondremos en contacto", "nos pondremos en contacto contigo",
    "en breve nos comunicaremos", "un asesor se comunicará", "un asesor se comunicara",
    # Autorrespuestas explícitas / fuera de oficina / rebotes
    "respuesta automática", "respuesta automatica", "autorrespuesta", "auto-respuesta",
    "correo automático", "correo automatico", "mensaje automático", "mensaje automatico",
    "este es un correo automático", "este es un correo automatico",
    "no responda a este correo", "no responder a este correo", "por favor no responda",
    "please do not reply", "do not reply", "no-reply", "noreply",
    "automated message", "automated response", "automatic reply", "auto-reply", "autoreply",
    "auto-generated", "autogenerado", "fuera de oficina", "out of office",
    "ausente de la oficina", "delivery status notification", "mail delivery subsystem",
    "undeliverable", "failure notice", "returned mail",
    # Tickets / mesas de ayuda
    "ticket", "radicado", "número de caso", "numero de caso", "case #", "request #",
    "solicitud #", "mesa de ayuda", "service desk",
    # Tokens, códigos de verificación, autenticación y alertas de cuenta
    "access token", "refresh token", "api token", "verification token", "reset token",
    "auth token", "token de acceso", "token de verificación", "token de verificacion",
    "tu token", "your token", "código de verificación", "codigo de verificacion",
    "verification code", "security code", "código de seguridad", "codigo de seguridad",
    "one-time password", "restablecer contraseña", "restablecer contrasena",
    "reset your password", "confirmar tu correo", "verify your email", "confirma tu cuenta",
    "confirm your email", "magic link", "enlace de acceso", "alerta de seguridad",
    "login alert", "new sign-in", "nuevo inicio de sesión", "nuevo inicio de sesion",
)

_RE_TOKEN_O_OTP = re.compile(
    r"\b(?:tokens?|otp|2fa|two-factor|doble\s+factor|api\s+key|access\s+key|web3forms)\b",
    re.IGNORECASE,
)


def es_correo_automatico(
    subject: str,
    body: str,
    headers: dict[str, str] | None = None,
    sender_email: str = "",
) -> bool:
    """True si el correo es autorrespuesta, confirmación `Form Submitted`, token o alerta de sistema.

    Estos correos NUNCA son leads ni ventas: no disparan notificaciones, Calendar ni saldo de IA.
    """
    hdrs = {k.lower(): (v or "").strip().lower() for k, v in (headers or {}).items()}
    if hdrs.get("auto-submitted") and hdrs.get("auto-submitted") != "no":
        return True
    if hdrs.get("precedence") in ("bulk", "auto_reply", "junk", "list"):
        return True
    if hdrs.get("x-autoreply") in ("yes", "true", "1") or hdrs.get("x-autorespond"):
        return True
    if hdrs.get("x-auto-response-suppress") or hdrs.get("auto-response-suppress"):
        return True
    if hdrs.get("x-zendesk-ticket-id") or hdrs.get("x-freshdesk-ticket"):
        return True
    if hdrs.get("return-path") == "<>":
        return True

    remitente = (sender_email or "").strip().lower()
    if remitente and "@" in remitente:
        local = remitente.split("@", 1)[0]
        if any(
            local == p or local.startswith(p + ".") or local.startswith(p + "-") or local.startswith(p + "_")
            for p in _PREFIJOS_REMITENTE_AUTOMATICO
        ):
            return True

    clean_body = _strip_quoted_reply(body).lower()
    clean_subj = re.sub(r"^(re|fwd|rv):\s*", "", (subject or "").strip(), flags=re.IGNORECASE).lower()
    combined = f"{clean_subj} {clean_body}"

    if any(kw in combined for kw in _AUTO_REPLY_PHRASES):
        return True
    if _RE_TOKEN_O_OTP.search(combined):
        return True
    return False


def classify_reply_intent(
    subject: str,
    body: str,
    headers: dict[str, str] | None = None,
    *,
    sender_email: str = "",
) -> str:
    if es_correo_automatico(subject, body, headers=headers, sender_email=sender_email):
        return "respuesta_automatica"

    clean_body = _strip_quoted_reply(body).lower()

    # La baja la decide la misma función que usa el agente, para que motor y agente
    # no discrepen. Va después del autorespondedor: un pie de página automático con
    # "unsubscribe" no es un lead pidiendo la baja.
    agente = _load_sales_agent()
    if agente is not None and agente.pide_la_baja(clean_body):
        return "baja"

    negative_kw = ("no gracias", "no estamos interesados", "no nos interesa", "no interesa",
                    "unsubscribe", "no me escriban")
    if any(kw in clean_body for kw in negative_kw):
        return "no_interesado"

    positive_kw = (
        "cita", "reunión", "reunion", "agendar", "llamada", "interesado", "interesada",
        "interesa", "con gusto", "cotización", "cotizacion", "propuesta", "hablemos",
        "conversemos", "whatsapp", "teléfono", "telefono", "sí claro", "si claro",
        # Señales de compra que antes caían en `respuesta_recibida` y el agente nunca veía.
        "cuánto cuesta", "cuanto cuesta", "cuánto vale", "cuanto vale", "precio", "precios",
        "cuéntame", "cuentame", "ejemplos", "más información", "mas informacion",
        "necesito", "me puedes ayudar", "pueden hacer",
    )
    if any(kw in clean_body for kw in positive_kw):
        return "interesado_cita"
    return "respuesta_recibida"


def _leer_rebote_diferido(msg: email.message.Message) -> tuple[str, str, bool] | None:
    """Si el mensaje es un aviso de entrega fallida, devuelve `(correo, motivo, es_permanente)`.

    Los rebotes no llegan como error de SMTP: llegan minutos después como un correo del
    `mailer-daemon`. Como ese remitente no es ningún lead, antes se descartaban en silencio
    y el prospecto seguía recibiendo seguimientos a una dirección muerta (saldo de IA tirado).
    """
    tipo = (msg.get_content_type() or "").lower()
    report_type = (msg.get_param("report-type") or "").lower()
    es_reporte = tipo == "multipart/report" and report_type == "delivery-status"
    _, remitente = parseaddr(msg.get("From") or "")
    remitente = remitente.lower()
    parece_daemon = any(p in remitente for p in ("mailer-daemon", "postmaster"))
    if not (es_reporte or parece_daemon):
        return None

    destino, estado, accion, diagnostico = "", "", "", ""
    for parte in msg.walk():
        if (parte.get_content_type() or "").lower() != "message/delivery-status":
            continue
        for bloque in parte.get_payload():
            if not hasattr(bloque, "get"):
                continue
            crudo = (bloque.get("Final-Recipient") or bloque.get("Original-Recipient") or "").strip()
            if crudo and not destino:
                destino = crudo.split(";", 1)[-1].strip().strip("<>").lower()
            estado = (bloque.get("Status") or estado).strip()
            accion = (bloque.get("Action") or accion).strip().lower()
            diagnostico = (bloque.get("Diagnostic-Code") or diagnostico).strip()
    if not destino or "@" not in destino:
        return None

    # 5.x.x = la dirección no existe o rechaza para siempre. 4.x.x = demora, puede llegar aún.
    permanente = estado.startswith("5") or (accion == "failed" and not estado.startswith("4"))
    motivo = (diagnostico or f"status={estado or '?'} action={accion or '?'}")[:200]
    return destino, motivo, permanente


def sync_imap_replies(max_messages: int = 40, *, dry_run: bool = False) -> dict[str, object]:
    """Lee la bandeja, clasifica y actúa. En `dry_run` NO escribe en la BD, no notifica,
    no toca Calendar y no registra nada en RESULTADOS_MERCADO.md: solo mira y cuenta.
    """
    with _DISPATCH_LOCK:
        if dry_run:
            # En seco nunca se crea la BD: sin BD no hay leads que mirar.
            if not database.DB_PATH.exists():
                return {"imap_ready": False, "dry_run": True, "reason": "dry_run_sin_bd",
                        "checked": 0, "matched": 0, "interested": []}
        else:
            database.init_db()
        cfg = load_env_file()
        user, password = cfg.get("SMTP_USER", ""), cfg.get("SMTP_PASS", "")
        imap_host = cfg.get("IMAP_HOST") or ("imap.gmail.com" if "gmail" in (cfg.get("SMTP_HOST") or "").lower() else "")
        if not (user and password and imap_host):
            return {"imap_ready": False, "checked": 0, "matched": 0, "interested": []}

        matched, checked, agent_runs = 0, 0, 0
        rebotes_detectados = rebotes_temporales = 0
        interested: list[dict[str, str]] = []
        agent_ready = _tiene_anthropic_key(cfg)
        try:
            with imaplib.IMAP4_SSL(imap_host, 993, timeout=15) as imap:
                imap.login(user, password)
                imap.select("INBOX")
                status_code, data = imap.search(None, "ALL")
                if status_code != "OK" or not data or not data[0]:
                    return {"imap_ready": True, "checked": 0, "matched": 0, "interested": []}
                msg_ids = data[0].split()[-max_messages:]
                for msg_num in reversed(msg_ids):
                    checked += 1
                    st, msg_data = imap.fetch(msg_num, "(RFC822)")
                    if st != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                        continue
                    msg = email.message_from_bytes(msg_data[0][1])
                    msg_id = (msg.get("Message-ID") or "").strip() or f"imap-{msg_num.decode(errors='ignore')}"
                    if database.has_processed_reply(msg_id):
                        continue
                    _, sender_email = parseaddr(msg.get("From") or "")
                    sender_email = sender_email.strip().lower()
                    if not sender_email or sender_email == user.lower():
                        continue

                    subj = _decode_mime_header(msg.get("Subject") or "")
                    snippet = _extract_text_snippet(msg)

                    # Primero los rebotes: vienen del mailer-daemon, no del prospecto.
                    rebote = _leer_rebote_diferido(msg)
                    if rebote is not None:
                        destino_rebote, motivo_rebote, permanente = rebote
                        lead_rebotado = database.get_lead_by_email(destino_rebote)
                        if not permanente or not lead_rebotado:
                            # Demora temporal (4.x.x) o correo que no es nuestro: no se toca el
                            # lead, pero el aviso no se vuelve a procesar.
                            if not dry_run:
                                database.record_processed_reply(
                                    msg_id, destino_rebote, "rebote_temporal", motivo_rebote,
                                )
                            rebotes_temporales += 1
                            continue
                        if dry_run:
                            rebotes_detectados += 1
                            continue
                        database.record_processed_reply(msg_id, destino_rebote, "rebote", motivo_rebote)
                        database.mark_lead_bounced(destino_rebote, motivo_rebote)
                        database.cancel_pending_outbox_for_recipient(destino_rebote)
                        database.cancel_followups_for_lead(lead_rebotado["id"])
                        rebotes_detectados += 1
                        try:
                            registrar_resultado_mercado(
                                lead_rebotado.get("nicho") or "(sin nicho)",
                                "(rebote diferido)", "correo", 1, "rebote",
                                f"Rebote diferido de {destino_rebote}: {motivo_rebote[:120]}",
                            )
                        except Exception:
                            pass
                        continue

                    lead = database.get_lead_by_email(sender_email)
                    if not lead:
                        continue

                    hdrs = {
                        "Auto-Submitted": msg.get("Auto-Submitted") or "",
                        "Precedence": msg.get("Precedence") or "",
                        "X-Autoreply": msg.get("X-Autoreply") or "",
                        "X-Autorespond": msg.get("X-Autorespond") or "",
                        "X-Auto-Response-Suppress": msg.get("X-Auto-Response-Suppress") or "",
                        "Auto-Response-Suppress": msg.get("Auto-Response-Suppress") or "",
                        "X-Zendesk-Ticket-Id": msg.get("X-Zendesk-Ticket-Id") or "",
                        "X-Freshdesk-Ticket": msg.get("X-Freshdesk-Ticket") or "",
                        "Return-Path": msg.get("Return-Path") or "",
                    }
                    intent = classify_reply_intent(subj, snippet, headers=hdrs, sender_email=sender_email)
                    matched += 1

                    if dry_run:
                        # Solo mirar: ni la respuesta se marca como procesada, ni el lead
                        # cambia de etapa, ni se cancela nada, ni suena el Mac.
                        if intent == "interesado_cita":
                            interested.append({
                                "id": str(lead["id"]), "name": lead.get("name") or "",
                                "company": lead.get("company") or "", "email": sender_email,
                                "snippet": snippet[:180],
                            })
                        continue

                    database.record_processed_reply(msg_id, sender_email, intent, snippet)

                    # Autorrespuestas (Form Submitted, tokens, fuera de oficina, tickets):
                    # NO son leads ni ventas. Se anotan en silencio y nunca disparan aviso,
                    # Calendar, agente de IA ni métricas de mercado.
                    if intent == "respuesta_automatica":
                        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                        auto_note = f"[Autorrespuesta ignorada {stamp}] Asunto: {subj}"
                        prev_notes = (lead.get("notes") or "").strip()
                        merged_notes = f"{auto_note}\n{prev_notes}".strip() if prev_notes else auto_note
                        database.update_lead_stage(
                            lead["id"], str(lead.get("stage") or "contactado"), notes=merged_notes,
                        )
                        continue

                    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                    new_note = f"[Respuesta {stamp} | {intent}] Asunto: {subj} — {snippet[:260]}"
                    prev_notes = (lead.get("notes") or "").strip()
                    merged_notes = f"{new_note}\n{prev_notes}".strip() if prev_notes else new_note

                    updated_lead = database.update_lead_stage(lead["id"], intent, notes=merged_notes)
                    # Si contestó un humano, no se le persigue más con lo que ya estaba en cola:
                    # ni correos pendientes ni seguimientos del agente.
                    database.cancel_pending_outbox_for_recipient(sender_email)
                    database.cancel_followups_for_lead(lead["id"])

                    # Dato REAL para RESULTADOS_MERCADO.md: esta respuesta existe de verdad.
                    # El duplicado ya lo corta `has_processed_reply(msg_id)` arriba: un
                    # mismo message_id no vuelve a llegar hasta aquí nunca.
                    if intent in ("interesado_cita", "baja"):
                        try:
                            estilo_enviado = database.get_last_sent_style_for_recipient(sender_email)
                            angulo_resp = (
                                f"modelo:{estilo_enviado}"
                                if estilo_enviado
                                else "(respuesta entrante, ángulo no registrado)"
                            )
                            registrar_resultado_mercado(
                                lead.get("nicho") or "(sin nicho)",
                                angulo_resp,
                                "correo", 1,
                                "respondió" if intent == "interesado_cita" else "baja",
                                f"Respuesta real de {sender_email}. Asunto: {subj}",
                            )
                        except Exception:
                            pass

                    if intent == "interesado_cita" and updated_lead:
                        interested.append({
                            "id": str(updated_lead["id"]), "name": updated_lead["name"],
                            "company": updated_lead["company"], "email": sender_email, "snippet": snippet[:180],
                        })
                        notify_mac_desktop(
                            f"🔥 Lead caliente: {updated_lead['company'] or updated_lead['name']}",
                            "Respondió interesado. Revisa el calendario para el seguimiento.",
                        )
                        tomorrow_9am = (datetime.now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
                        create_calendar_event(
                            f"🔥 Revisar lead: {updated_lead['company'] or updated_lead['name']} ({updated_lead.get('nicho', '')})",
                            f"Email: {sender_email}\nRespondió: \"{snippet[:300]}\"",
                            tomorrow_9am,
                        )

                    # El agente contesta solo si vale la pena. Va en try/except a propósito:
                    # si el agente falla, el sync, las alertas del Mac y el Calendar siguen.
                    if intent in INTENTS_PARA_EL_AGENTE and agent_ready:
                        agente = _load_sales_agent()
                        if agente is not None:
                            try:
                                agente.AgenteVentas(cfg, dry_run=dry_run).correr(
                                    lead_email=sender_email, mensaje_lead=snippet,
                                    nicho=lead.get("nicho") or "",
                                )
                                agent_runs += 1
                            except Exception:
                                pass
        except Exception as exc:
            return {"imap_ready": True, "error": str(exc), "checked": checked, "matched": matched,
                    "interested": interested, "agent_runs": agent_runs,
                    "rebotes_detectados": rebotes_detectados, "rebotes_temporales": rebotes_temporales}

        return {"imap_ready": True, "checked": checked, "matched": matched,
                "interested": interested, "agent_runs": agent_runs,
                "rebotes_detectados": rebotes_detectados, "rebotes_temporales": rebotes_temporales}


def run_sales_agent_cycle(*, dry_run: bool = False, max_leads: int = 5) -> dict[str, object]:
    """Ciclo del agente de ventas (Paso 5). Primero los seguimientos vencidos, después los
    leads nuevos en frío. Sin API key sale limpio; en `dry_run` no escribe nada.
    """
    agente = _load_sales_agent()
    if agente is None:
        return {"ran": False, "reason": "sales_agent_no_disponible"}

    cfg = agente.cargar_config()
    if not _tiene_anthropic_key(cfg) and not dry_run:
        return {"ran": False, "reason": "sin_api_key"}

    # En seco nunca se crea la BD: si no existe, no hay nada que mirar.
    if dry_run and not database.DB_PATH.exists():
        return {"ran": False, "reason": "dry_run_sin_bd", "dry_run": True}

    # En seco NO se llama init_db(): crear o abrir la BD para escribir ya sería tocarla.
    if not dry_run:
        database.init_db()
        if not _is_within_sending_window(database.get_settings()):
            return {"ran": False, "reason": "outside_window"}

    conf = agente.leer_configuracion(cfg)
    resumen: dict[str, object] = {
        "ran": True, "dry_run": dry_run, "followups_corridos": 0, "followups_cancelados": 0,
        "followups_fallidos": 0, "leads_en_frio": 0, "cortado_por": "", "errores": [],
    }

    def _tope_lleno() -> str:
        if database.agent_emails_queued_today() >= conf["max_emails"]:
            return "tope_correos"
        if database.agent_cost_today_usd() >= conf["max_usd"]:
            return "tope_usd"
        return ""

    def _correr(lead: dict, mensaje: str = "", motivo_seguimiento: str = "") -> bool:
        """False si el agente NO pudo trabajar (error de API, tope, lead cerrado).
        Importa: con False el seguimiento sigue 'pendiente' y se reintenta, en vez de
        darse por 'hecho' sin que el lead haya recibido nada.
        """
        try:
            res = agente.AgenteVentas(cfg, dry_run=dry_run).correr(
                lead_email=lead["email"], mensaje_lead=mensaje,
                nicho=lead.get("nicho") or "", motivo_seguimiento=motivo_seguimiento,
            )
            return bool(res.get("ok")) if isinstance(res, dict) else bool(res)
        except Exception as exc:
            resumen["errores"].append(str(exc)[:200])
            return False

    # 1) seguimientos vencidos. Un lead cerrado se cancela SIN gastar un token.
    for seg in database.list_due_followups(limit=max(1, max_leads)):
        lead = database.get_lead_by_id(seg.get("lead_id"))
        if not lead or _lead_esta_cerrado(lead):
            if not dry_run:
                database.update_followup(seg["id"], "cancelado")
            resumen["followups_cancelados"] = int(resumen["followups_cancelados"]) + 1
            continue
        corte = _tope_lleno()
        if corte:
            resumen["cortado_por"] = corte
            break
        if _correr(lead, motivo_seguimiento=str(seg.get("motivo") or "")):
            resumen["followups_corridos"] = int(resumen["followups_corridos"]) + 1
            if not dry_run:
                database.update_followup(seg["id"], "hecho")
        else:
            # Se queda 'pendiente' a propósito: el agente no pudo escribirle.
            resumen["followups_fallidos"] = int(resumen.get("followups_fallidos", 0)) + 1

    # 2) leads nuevos en frío, hasta max_leads y cortando en seco ante cualquier tope.
    if not resumen["cortado_por"]:
        for lead in database.list_cold_leads_for_agent(limit=max_leads):
            corte = _tope_lleno()
            if corte:
                resumen["cortado_por"] = corte
                break
            if _correr(lead):
                resumen["leads_en_frio"] = int(resumen["leads_en_frio"]) + 1

    return resumen


_RE_CORREO_LANDING = re.compile(r"\b[a-zA-Z0-9._%+-]{2,64}@[a-zA-Z0-9.-]{2,190}\.[a-zA-Z]{2,12}\b")


def _extraer_cuerpo_lineas(msg: email.message.Message) -> str:
    """Extrae el texto del mensaje conservando saltos de línea para leer campos Web3Forms."""
    plano = html_txt = ""
    if msg.is_multipart():
        for part in msg.walk():
            if "attachment" in str(part.get("Content-Disposition") or "").lower():
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            dec = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            if part.get_content_type() == "text/plain" and not plano:
                plano = dec
            elif part.get_content_type() == "text/html" and not html_txt:
                html_txt = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>", "\n", dec)
                html_txt = re.sub(r"<[^>]+>", " ", html_txt)
                html_txt = html.unescape(html_txt)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            dec = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
            if msg.get_content_type() == "text/html":
                dec = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>", "\n", dec)
                dec = re.sub(r"<[^>]+>", " ", dec)
                dec = html.unescape(dec)
            plano = dec
    return (plano or html_txt).strip()


def extraer_campos_landing(msg: email.message.Message, correo_propio: str = "") -> dict[str, str]:
    """Saca `telefono`, `correo` y `mensaje` limpios de una notificación de Web3Forms."""
    crudo = _extraer_cuerpo_lineas(msg)
    snippet = _extract_text_snippet(msg)
    telefono = ""
    mensaje = ""

    m_tel = re.search(r"(?im)^(?:telefono|teléfono|phone|whatsapp)\s*[:\s]+(.+)$", crudo)
    if m_tel:
        telefono = re.sub(r"\s+", " ", m_tel.group(1)).strip()[:60]

    m_msg = re.search(
        r"(?ims)^(?:mensaje|message)\s*[:\s]+(.+?)(?:\n(?:[a-zA-Záéíóú_ -]{2,20}:|--|Submitted|Enviado)|\Z)",
        crudo,
    )
    if m_msg:
        mensaje = re.sub(r"\s+", " ", m_msg.group(1)).strip()
    if not mensaje:
        mensaje = snippet

    propio = (correo_propio or "").strip().lower()
    correo_visitante = ""
    for hallado in _RE_CORREO_LANDING.findall(crudo):
        cand = hallado.strip().lower()
        if cand == propio or cand.endswith("@web3forms.com") or "noreply" in cand or "notify@" in cand:
            continue
        correo_visitante = cand
        break

    resumen = f"WhatsApp: {telefono} — {mensaje}" if (telefono and telefono not in mensaje) else mensaje
    return {
        "telefono": telefono,
        "correo": correo_visitante,
        "mensaje": mensaje[:600],
        "resumen": resumen[:600],
    }


def sync_landing_messages(max_messages: int = 40) -> dict[str, object]:
    with _DISPATCH_LOCK:
        database.init_db()
        cfg = load_env_file()
        user, password = cfg.get("SMTP_USER", ""), cfg.get("SMTP_PASS", "")
        imap_host = cfg.get("IMAP_HOST") or ("imap.gmail.com" if "gmail" in (cfg.get("SMTP_HOST") or "").lower() else "")
        if not (user and password and imap_host):
            return {"imap_ready": False, "checked": 0, "new_messages": 0}

        checked, new_messages, agent_runs = 0, 0, 0
        agent_ready = _tiene_anthropic_key(cfg)
        try:
            with imaplib.IMAP4_SSL(imap_host, 993, timeout=15) as imap:
                imap.login(user, password)
                imap.select("INBOX")
                status_code, data = imap.search(None, 'FROM', '"notify"', 'FROM', '"web3forms.com"')
                if status_code != "OK" or not data or not data[0]:
                    return {"imap_ready": True, "checked": 0, "new_messages": 0}
                msg_ids = data[0].split()[-max_messages:]
                for msg_num in reversed(msg_ids):
                    checked += 1
                    st, msg_data = imap.fetch(msg_num, "(RFC822)")
                    if st != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                        continue
                    msg = email.message_from_bytes(msg_data[0][1])
                    msg_id = (msg.get("Message-ID") or "").strip() or f"imap-{msg_num.decode(errors='ignore')}"
                    if database.has_landing_message(msg_id):
                        continue

                    subj_landing = _decode_mime_header(msg.get("Subject") or "")
                    campos = extraer_campos_landing(msg, correo_propio=user)
                    resumen_panel = campos["resumen"]

                    # Correos de sistema de Web3Forms (tokens, access key, verificación de cuenta)
                    # NO son mensajes de visitantes ni leads de la landing.
                    texto_landing_check = f"{subj_landing} {campos['mensaje']}".lower()
                    es_aviso_sistema_landing = (
                        not campos["telefono"]
                        and any(k in texto_landing_check for k in (
                            "access key", "access token", "verify your email", "verification code",
                            "reset your password", "confirm your email", "api key", "your token",
                            "token de acceso", "código de verificación", "codigo de verificacion",
                        ))
                    )
                    if es_aviso_sistema_landing:
                        continue

                    database.add_landing_message(msg_id, resumen_panel)
                    new_messages += 1

                    try:
                        registrar_resultado_mercado(
                            "(landing)", "(formulario web entrante)", "landing", 1, "respondió",
                            resumen_panel[:180],
                        )
                    except Exception:
                        pass

                    notify_mac_desktop(
                        "💬 Nuevo cliente desde la landing de El Socio",
                        resumen_panel[:180],
                    )
                    create_calendar_event(
                        "📩 Atender lead de la landing (El Socio)",
                        f"Recibido por la landing:\n\n{resumen_panel}",
                        datetime.now() + timedelta(hours=1),
                    )

                    # Si además dejó correo electrónico, entra al pipeline y el agente lo atiende solo.
                    if campos["correo"]:
                        database.upsert_lead(
                            name="Visitante Landing", company="", email=campos["correo"],
                            whatsapp=campos["telefono"], nicho="", service_interest=campos["mensaje"][:120],
                            source="landing", stage="interesado_cita",
                            notes=f"Escribió en landing: {resumen_panel[:300]}",
                        )
                        if agent_ready:
                            agente = _load_sales_agent()
                            if agente is not None:
                                try:
                                    agente.AgenteVentas(cfg).correr(
                                        lead_email=campos["correo"],
                                        mensaje_lead=resumen_panel,
                                    )
                                    agent_runs += 1
                                except Exception:
                                    pass
        except Exception as exc:
            return {"imap_ready": True, "error": str(exc), "checked": checked,
                    "new_messages": new_messages, "agent_runs": agent_runs}

        panel_mensajes.regenerate()
        return {"imap_ready": True, "checked": checked, "new_messages": new_messages,
                "agent_runs": agent_runs}


def resumen_en_seco() -> dict[str, object]:
    """Lo ÚNICO que corre `--dry-run` a secas: mira y cuenta.

    No rellena la cola, no abre SMTP, no toca la landing, no notifica, no crea la BD y
    no escribe una sola fila en RESULTADOS_MERCADO.md.
    """
    cfg = load_env_file()
    hay_bd = database.DB_PATH.exists()
    salida: dict[str, object] = {
        "dry_run": True,
        "nota": ("--dry-run solo mira: sin escribir en la BD, sin SMTP, sin IMAP, "
                 "sin notificaciones, sin Calendar y sin tocar RESULTADOS_MERCADO.md."),
        "bd_existe": hay_bd,
        "smtp_listo": bool(cfg.get("SMTP_HOST") and cfg.get("SMTP_USER") and cfg.get("SMTP_PASS")),
        "imap_listo": bool(cfg.get("SMTP_USER") and cfg.get("SMTP_PASS")
                           and (cfg.get("IMAP_HOST") or "gmail" in (cfg.get("SMTP_HOST") or "").lower())),
        "api_key_lista": _tiene_anthropic_key(cfg),
    }
    if not hay_bd:
        return salida
    ajustes = database.get_settings()
    agente = _load_sales_agent()
    rendimiento_modelos = agente.resumen_rendimiento_modelos() if agente is not None else []
    salida.update({
        "limite_diario": get_daily_limit(cfg),
        "en_ventana_de_envio": _is_within_sending_window(ajustes),
        "enviados_hoy": database.count_sent_emails_today(),
        "pendientes_en_cola": len(database.list_outbox_jobs(status="pending")),
        "pendientes_de_hoy": database.count_today_pending_email_jobs(),
        "leads_en_frio_disponibles": len(database.list_cold_leads_for_agent(limit=100)),
        "seguimientos_vencidos": len(database.list_due_followups(limit=100)),
        "correos_del_agente_hoy": database.agent_emails_queued_today(),
        "gasto_del_agente_hoy_usd": round(database.agent_cost_today_usd(), 6),
        "piezas_contenido_hoy": database.content_created_today(),
        "posts_ig_publicados_hoy": database.ig_published_today(),
        "rendimiento_modelos_correo": rendimiento_modelos,
        "silencios_por_registrar": registrar_silencios_vencidos(dry_run=True),
    })
    return salida


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispatch due El Socio emails & sync replies.")
    parser.add_argument("--status-only", action="store_true")
    parser.add_argument("--sync-replies", action="store_true")
    parser.add_argument("--sync-landing", action="store_true")
    parser.add_argument("--replenish", action="store_true")
    parser.add_argument("--run-agent", action="store_true",
                        help="Corre el ciclo del agente de ventas (seguimientos + leads en frío).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Valida sin escribir en la BD, sin API y sin enviar correos.")
    args = parser.parse_args()
    seco = args.dry_run

    # En seco NUNCA se crea la BD ni se abre para escribir: el objetivo es no tocar nada.
    if not seco:
        database.init_db()

    if args.run_agent:
        print(json.dumps(run_sales_agent_cycle(dry_run=seco), ensure_ascii=False, indent=2))
        return
    if args.status_only:
        if seco and not database.DB_PATH.exists():
            print(json.dumps({"dry_run": True, "bd_existe": False}, ensure_ascii=False, indent=2))
            return
        print(json.dumps({"config_status": get_autopilot_status(), "pending_jobs": len(database.list_outbox_jobs(status="pending"))}, ensure_ascii=False, indent=2))
        return
    if seco:
        # `--dry-run` sin `--run-agent`: ni ensure_daily_pipeline, ni dispatch_due_jobs,
        # ni sync_landing_messages. Todos esos escriben de verdad y mandan de verdad.
        if args.sync_replies:
            print(json.dumps(sync_imap_replies(dry_run=True), ensure_ascii=False, indent=2))
            return
        print(json.dumps(resumen_en_seco(), ensure_ascii=False, indent=2))
        return
    if args.sync_replies:
        replies_res = sync_imap_replies()
        replies_res["landing"] = sync_landing_messages()
        print(json.dumps(replies_res, ensure_ascii=False, indent=2))
        return
    if args.sync_landing:
        print(json.dumps(sync_landing_messages(), ensure_ascii=False, indent=2))
        return
    if args.replenish:
        print(json.dumps(ensure_daily_pipeline(force=True), ensure_ascii=False, indent=2))
        return

    # Orden real de negocio: 1º reabastecer leads -> 2º el agente redacta y encola -> 3º SMTP despacha.
    replenish_res = ensure_daily_pipeline()
    agent_res: dict[str, object] | None = None
    if _tiene_anthropic_key():
        try:
            agent_res = run_sales_agent_cycle()
        except Exception as exc:
            agent_res = {"ran": False, "error": str(exc)[:200]}
    dispatch_res = dispatch_due_jobs()
    dispatch_res["replenish"] = replenish_res
    if agent_res is not None:
        dispatch_res["sales_agent"] = agent_res
    # Tandas que ya vencieron sin respuesta: dato real para RESULTADOS_MERCADO.md.
    try:
        dispatch_res["resultados_mercado"] = registrar_silencios_vencidos()
    except Exception as exc:
        dispatch_res["resultados_mercado"] = {"registradas": 0, "error": str(exc)[:200]}
    print(json.dumps(dispatch_res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

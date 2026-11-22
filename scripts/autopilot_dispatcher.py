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
from email.utils import parseaddr
from pathlib import Path

_DISPATCH_LOCK = threading.Lock()
_LAST_REPLENISH_TS = 0.0
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import database  # noqa: E402


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
    ):
        if os.environ.get(k):
            values[k] = os.environ[k]
    return values


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


def build_signature(cfg: dict[str, str]) -> str:
    name = cfg.get("FROM_NAME", "El Socio")
    lines = [f"\n\nSaludos,\n{name}"]
    if cfg.get("WHATSAPP"):
        lines.append(f"WhatsApp: {cfg['WHATSAPP']}")
    if cfg.get("WEBSITE"):
        lines.append(cfg["WEBSITE"])
    return "\n".join(lines)


def send_smtp_email(cfg: dict[str, str], to_addr: str, subject: str, body: str, *, include_signature: bool = True) -> None:
    msg = EmailMessage()
    msg["From"] = cfg.get("SMTP_FROM") or cfg["SMTP_USER"]
    msg["To"] = to_addr
    msg["Subject"] = subject
    full_body = body + (build_signature(cfg) if include_signature else "")
    msg.set_content(full_body)

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
                stage="nuevo_lead", notes="Descubierto y verificado (MX OK) por El Socio",
            )
            added_discovered += 1
            deficit -= 1
    except Exception:
        pass

    if deficit > 0 and settings.get("autopilot_reengage_enabled", "1") != "0":
        candidates = database.list_reengagement_candidates(limit=min(deficit, 3))
        for cand in candidates:
            subject = f"Seguimiento — {cand.get('service_interest') or 'una idea para ti'}"
            body = (
                f"Hola, te escribí hace un tiempo sobre {cand.get('service_interest') or 'un servicio'}. "
                "Sigo disponible si te interesa retomarlo."
            )
            if database.queue_prudent_reengagement(cand, subject, body):
                added_reengaged += 1
                deficit -= 1

    return {
        "daily_limit": daily_limit, "sent_today": sent_today,
        "added_discovered": added_discovered, "added_reengaged": added_reengaged,
        "remaining_deficit": max(0, deficit),
    }


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

        try:
            min_gap_sec = max(30, int(settings.get("autopilot_min_gap_seconds", "180")))
        except ValueError:
            min_gap_sec = 180

        in_window = _is_within_sending_window(settings) if respect_window else True
        last_sent_dt = database.get_last_sent_email_datetime() if respect_pacing else None

        for job in pending:
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

        status["sent_today"] = sent_today
        return {
            "config_status": status, "sent": sent_count,
            "skipped_missing_credentials": skipped_no_creds, "skipped_daily_cap": skipped_daily_cap,
            "skipped_pacing": skipped_pacing, "skipped_window": skipped_window, "failed": failed_count,
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


def classify_reply_intent(subject: str, body: str, headers: dict[str, str] | None = None) -> str:
    hdrs = {k.lower(): (v or "").lower() for k, v in (headers or {}).items()}
    if (hdrs.get("auto-submitted") and hdrs.get("auto-submitted") != "no") or hdrs.get("precedence") in ("bulk", "auto_reply", "junk"):
        return "respuesta_automatica"

    clean_body = _strip_quoted_reply(body).lower()
    clean_subj = re.sub(r"^(re|fwd|rv):\s*", "", (subject or "").strip(), flags=re.IGNORECASE).lower()
    combined = f"{clean_subj} {clean_body}"

    auto_reply_kw = (
        "ticket", "fuera de oficina", "out of office", "respuesta automática",
        "respuesta automatica", "auto-reply", "autoreply", "gracias por contactarnos",
        "no-reply", "noreply", "do not reply",
    )
    if any(kw in combined for kw in auto_reply_kw):
        return "respuesta_automatica"

    negative_kw = ("no gracias", "no estamos interesados", "no nos interesa", "no interesa",
                    "unsubscribe", "no me escriban")
    if any(kw in clean_body for kw in negative_kw):
        return "no_interesado"

    positive_kw = (
        "cita", "reunión", "reunion", "agendar", "llamada", "interesado", "interesada",
        "interesa", "con gusto", "cotización", "cotizacion", "propuesta", "hablemos",
        "conversemos", "whatsapp", "teléfono", "telefono", "sí claro", "si claro",
    )
    if any(kw in clean_body for kw in positive_kw):
        return "interesado_cita"
    return "respuesta_recibida"


def sync_imap_replies(max_messages: int = 40) -> dict[str, object]:
    with _DISPATCH_LOCK:
        database.init_db()
        cfg = load_env_file()
        user, password = cfg.get("SMTP_USER", ""), cfg.get("SMTP_PASS", "")
        imap_host = cfg.get("IMAP_HOST") or ("imap.gmail.com" if "gmail" in (cfg.get("SMTP_HOST") or "").lower() else "")
        if not (user and password and imap_host):
            return {"imap_ready": False, "checked": 0, "matched": 0, "interested": []}

        matched, checked = 0, 0
        interested: list[dict[str, str]] = []
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
                    lead = database.get_lead_by_email(sender_email)
                    if not lead:
                        continue

                    hdrs = {"Auto-Submitted": msg.get("Auto-Submitted") or "", "Precedence": msg.get("Precedence") or ""}
                    intent = classify_reply_intent(subj, snippet, headers=hdrs)
                    database.record_processed_reply(msg_id, sender_email, intent, snippet)
                    matched += 1

                    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                    new_note = f"[Respuesta {stamp} | {intent}] Asunto: {subj} — {snippet[:260]}"
                    prev_notes = (lead.get("notes") or "").strip()
                    merged_notes = f"{new_note}\n{prev_notes}".strip() if prev_notes else new_note

                    updated_lead = database.update_lead_stage(lead["id"], intent, notes=merged_notes)
                    database.cancel_pending_outbox_for_recipient(sender_email)

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
        except Exception as exc:
            return {"imap_ready": True, "error": str(exc), "checked": checked, "matched": matched, "interested": interested}

        return {"imap_ready": True, "checked": checked, "matched": matched, "interested": interested}


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispatch due El Socio emails & sync replies.")
    parser.add_argument("--status-only", action="store_true")
    parser.add_argument("--sync-replies", action="store_true")
    parser.add_argument("--replenish", action="store_true")
    args = parser.parse_args()

    database.init_db()
    if args.status_only:
        print(json.dumps({"config_status": get_autopilot_status(), "pending_jobs": len(database.list_outbox_jobs(status="pending"))}, ensure_ascii=False, indent=2))
        return
    if args.sync_replies:
        print(json.dumps(sync_imap_replies(), ensure_ascii=False, indent=2))
        return
    if args.replenish:
        print(json.dumps(ensure_daily_pipeline(force=True), ensure_ascii=False, indent=2))
        return

    replenish_res = ensure_daily_pipeline()
    dispatch_res = dispatch_due_jobs()
    dispatch_res["replenish"] = replenish_res
    print(json.dumps(dispatch_res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

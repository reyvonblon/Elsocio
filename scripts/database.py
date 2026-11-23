#!/usr/bin/env python3
"""Lightweight SQLite layer for El Socio — leads, outbox, settings, replies. Zero deps."""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "el_socio.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, company TEXT, email TEXT UNIQUE, whatsapp TEXT,
    nicho TEXT, service_interest TEXT, source TEXT,
    stage TEXT DEFAULT 'nuevo_lead',
    notes TEXT, recontact_count INTEGER DEFAULT 0,
    bounced INTEGER DEFAULT 0,
    created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient TEXT, subject TEXT, body TEXT, channel TEXT DEFAULT 'email',
    nicho TEXT, scheduled_for TEXT, status TEXT DEFAULT 'pending',
    error TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY, value TEXT
);
CREATE TABLE IF NOT EXISTS processed_replies (
    message_id TEXT PRIMARY KEY, sender_email TEXT, intent TEXT,
    snippet TEXT, processed_at TEXT
);
CREATE TABLE IF NOT EXISTS landing_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT UNIQUE, mensaje TEXT, estado TEXT DEFAULT 'nuevo',
    received_at TEXT
);
CREATE TABLE IF NOT EXISTS agent_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT, lead_id INTEGER, turno INTEGER, modelo TEXT,
    herramienta TEXT, argumentos TEXT, resultado TEXT,
    tokens_entrada INTEGER DEFAULT 0, tokens_salida INTEGER DEFAULT 0,
    tokens_cache_creacion INTEGER DEFAULT 0, tokens_cache_lectura INTEGER DEFAULT 0,
    costo_usd REAL DEFAULT 0.0,
    bloqueado_por_guarda TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_agent_log_fecha ON agent_log(fecha);
CREATE TABLE IF NOT EXISTS agent_followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER, programado_para TEXT, motivo TEXT,
    estado TEXT DEFAULT 'pendiente', created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_followups_estado ON agent_followups(estado, programado_para);
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# Columnas agregadas después de la primera versión de la tabla. Se añaden con ALTER TABLE
# para no tocar los datos que ya están en data/el_socio.db.
_MIGRACIONES = {
    "agent_log": [
        ("tokens_cache_creacion", "INTEGER DEFAULT 0"),
        ("tokens_cache_lectura", "INTEGER DEFAULT 0"),
        ("costo_usd", "REAL DEFAULT 0.0"),
    ],
}


def _migrar_columnas(conn: sqlite3.Connection) -> None:
    for tabla, columnas in _MIGRACIONES.items():
        existe = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)
        ).fetchone()
        if not existe:
            continue
        actuales = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
        for nombre, definicion in columnas:
            if nombre not in actuales:
                conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {definicion}")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)
        _migrar_columnas(conn)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_settings() -> dict[str, str]:
    with _conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def update_settings(values: dict[str, str]) -> None:
    with _conn() as conn:
        for k, v in values.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, str(v)),
            )


def list_all_known_emails() -> set[str]:
    with _conn() as conn:
        rows = conn.execute("SELECT email FROM leads").fetchall()
        return {r["email"].lower() for r in rows if r["email"]}


def upsert_lead(
    *, name: str, company: str, email: str, whatsapp: str = "", nicho: str = "",
    service_interest: str = "", source: str = "", stage: str = "nuevo_lead",
    notes: str = "",
) -> int:
    email = email.lower().strip()
    now = _now()
    with _conn() as conn:
        existing = conn.execute("SELECT id FROM leads WHERE email=?", (email,)).fetchone()
        if existing:
            return int(existing["id"])
        cur = conn.execute(
            "INSERT INTO leads (name, company, email, whatsapp, nicho, service_interest, "
            "source, stage, notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (name, company, email, whatsapp, nicho, service_interest, source, stage, notes, now, now),
        )
        return int(cur.lastrowid)


def get_lead_by_email(email: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM leads WHERE email=?", (email.lower().strip(),)).fetchone()
        return dict(row) if row else None


def get_lead_by_id(lead_id: int | None) -> dict | None:
    if lead_id is None:
        return None
    with _conn() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        return dict(row) if row else None


def list_cold_leads_for_agent(limit: int = 5) -> list[dict]:
    """Leads que el agente puede contactar en frío: nuevos, sin rebote y a los que NUNCA
    se les ha escrito.

    El filtro NO se limita al día de hoy a propósito: una vez contactado en frío, un lead
    no vuelve a salir por esta puerta nunca más (si no, cada día amanece con el mismo
    correo en frío = spam). Los recontactos van solo por `agent_followups`.
    Los más viejos primero, para no dejar a nadie en la cola para siempre.
    """
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM leads WHERE stage='nuevo_lead' AND COALESCE(bounced, 0)=0 "
            "AND email IS NOT NULL AND TRIM(email)!='' "
            "AND LOWER(TRIM(email)) NOT IN ("
            "    SELECT LOWER(TRIM(recipient)) FROM outbox WHERE status IN ('pending', 'sent')"
            ") "
            "ORDER BY COALESCE(updated_at, created_at) ASC LIMIT ?",
            (max(1, limit),),
        ).fetchall()
        return [dict(r) for r in rows]


def update_lead_stage(lead_id: int, stage: str, *, notes: str | None = None) -> dict | None:
    with _conn() as conn:
        if notes is not None:
            conn.execute(
                "UPDATE leads SET stage=?, notes=?, updated_at=? WHERE id=?",
                (stage, notes, _now(), lead_id),
            )
        else:
            conn.execute("UPDATE leads SET stage=?, updated_at=? WHERE id=?", (stage, _now(), lead_id))
        row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        return dict(row) if row else None


def has_landing_message(message_id: str) -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT 1 FROM landing_messages WHERE message_id=?", (message_id,)).fetchone()
        return row is not None


def add_landing_message(message_id: str, mensaje: str) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO landing_messages (message_id, mensaje, estado, received_at) "
            "VALUES (?, ?, 'nuevo', ?)",
            (message_id, mensaje, _now()),
        )
        return int(cur.lastrowid)


def list_landing_messages(limit: int = 50) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM landing_messages ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def mark_lead_bounced(email: str, reason: str = "") -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE leads SET bounced=1, notes=notes || ' | REBOTADO: ' || ?, updated_at=? WHERE email=?",
            (reason, _now(), email.lower().strip()),
        )


def enqueue_email(*, recipient: str, subject: str, body: str, nicho: str = "", scheduled_for: str | None = None) -> int:
    # Normalizado siempre: si no, already_emailed_today y cancel_pending_outbox_for_recipient
    # (que comparan en minúsculas) no encuentran la fila.
    recipient = recipient.lower().strip()
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO outbox (recipient, subject, body, channel, nicho, scheduled_for, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (recipient, subject, body, "email", nicho, scheduled_for or _now(), "pending", _now()),
        )
        return int(cur.lastrowid)


def cancel_pending_outbox_for_recipient(email: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE outbox SET status='cancelled' WHERE recipient=? AND status='pending'",
            (email.lower().strip(),),
        )


def list_outbox_jobs(*, status: str = "pending", limit: int = 200) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM outbox WHERE status=? ORDER BY scheduled_for ASC LIMIT ?",
            (status, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def update_outbox_job(job_id: int, status: str, error: str = "") -> None:
    with _conn() as conn:
        conn.execute("UPDATE outbox SET status=?, error=? WHERE id=?", (status, error, job_id))


def count_sent_emails_today() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM outbox WHERE status='sent' AND scheduled_for LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return int(row["n"])


def count_today_pending_email_jobs() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM outbox WHERE status='pending' AND scheduled_for LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return int(row["n"])


def get_last_sent_email_datetime() -> datetime | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT created_at FROM outbox WHERE status='sent' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        try:
            return datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None


def has_processed_reply(message_id: str) -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT 1 FROM processed_replies WHERE message_id=?", (message_id,)).fetchone()
        return row is not None


def record_processed_reply(message_id: str, sender_email: str, intent: str, snippet: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_replies (message_id, sender_email, intent, snippet, processed_at) "
            "VALUES (?,?,?,?,?)",
            (message_id, sender_email, intent, snippet, _now()),
        )


def list_reengagement_candidates(*, min_days_cold: int = 45, max_recontacts: int = 2, limit: int = 3) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=min_days_cold)).strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM leads WHERE stage='nuevo_lead' AND bounced=0 "
            "AND recontact_count < ? AND updated_at < ? ORDER BY updated_at ASC LIMIT ?",
            (max_recontacts, cutoff, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def queue_prudent_reengagement(lead: dict, subject: str, body: str) -> bool:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO outbox (recipient, subject, body, channel, nicho, scheduled_for, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (lead["email"], subject, body, "email", lead.get("nicho", ""), _now(), "pending", _now()),
        )
        conn.execute(
            "UPDATE leads SET recontact_count = recontact_count + 1, updated_at=? WHERE id=?",
            (_now(), lead["id"]),
        )
    return True


def import_uncontacted_prospects_from_csv(csv_path: Path, max_new: int) -> dict:
    if not csv_path.exists() or max_new <= 0:
        return {"imported": 0}
    known = list_all_known_emails()
    imported = 0
    rows_to_keep: list[dict] = []
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            email = (row.get("correo") or "").strip().lower()
            if not email or email in known or imported >= max_new:
                rows_to_keep.append(row)
                continue
            upsert_lead(
                name=row.get("nombre", ""), company=row.get("empresa", ""), email=email,
                whatsapp=row.get("whatsapp", ""), nicho=row.get("nicho", ""),
                service_interest=row.get("servicio", ""), source="csv_reserva", stage="nuevo_lead",
                notes="Importado de reserva CSV",
            )
            known.add(email)
            imported += 1
    return {"imported": imported}


# ---------------------------------------------------------------- agente de ventas

def log_agent_action(
    *, lead_id: int | None, turno: int, modelo: str, herramienta: str,
    argumentos: str = "", resultado: str = "", tokens_entrada: int = 0,
    tokens_salida: int = 0, tokens_cache_creacion: int = 0, tokens_cache_lectura: int = 0,
    costo_usd: float = 0.0, bloqueado_por_guarda: str = "",
) -> int:
    """Una fila por cada cosa que hace el agente. Nunca guardar secretos aquí."""
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO agent_log (fecha, lead_id, turno, modelo, herramienta, argumentos, "
            "resultado, tokens_entrada, tokens_salida, tokens_cache_creacion, "
            "tokens_cache_lectura, costo_usd, bloqueado_por_guarda) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (_now(), lead_id, turno, modelo, herramienta, argumentos[:2000], resultado[:2000],
             tokens_entrada, tokens_salida, tokens_cache_creacion, tokens_cache_lectura,
             float(costo_usd), bloqueado_por_guarda),
        )
        return int(cur.lastrowid)


def agent_cost_today_usd() -> float:
    """Lo que el agente ya gastó hoy en USD. Es el tope duro del saldo."""
    today = datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(costo_usd),0) AS usd FROM agent_log WHERE fecha LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return float(row["usd"])


def agent_tokens_today() -> dict[str, int]:
    today = datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(tokens_entrada),0) AS ent, COALESCE(SUM(tokens_salida),0) AS sal "
            "FROM agent_log WHERE fecha LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return {"entrada": int(row["ent"]), "salida": int(row["sal"])}


def agent_emails_queued_today() -> int:
    """Correos que el agente encoló hoy (para el tope diario, se cuenta al encolar, no al enviar)."""
    today = datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM agent_log WHERE herramienta='enviar_correo' "
            "AND bloqueado_por_guarda='' AND fecha LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return int(row["n"])


def already_emailed_today(recipient: str) -> bool:
    """Evita duplicados: ¿ya hay un correo a esta dirección encolado o enviado hoy?"""
    today = datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM outbox WHERE recipient=? AND status IN ('pending','sent') "
            "AND created_at LIKE ? LIMIT 1",
            (recipient.lower().strip(), f"{today}%"),
        ).fetchone()
        return row is not None


def schedule_followup(lead_id: int, dias: int, motivo: str) -> int | None:
    """Programa un seguimiento. Máximo 2 por lead — devuelve None si ya llegó al tope."""
    if count_followups_for_lead(lead_id) >= 2:
        return None
    cuando = (datetime.now() + timedelta(days=max(1, dias))).strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO agent_followups (lead_id, programado_para, motivo, estado, created_at) "
            "VALUES (?,?,?,'pendiente',?)",
            (lead_id, cuando, motivo, _now()),
        )
        return int(cur.lastrowid)


def count_followups_for_lead(lead_id: int) -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM agent_followups WHERE lead_id=? AND estado!='cancelado'",
            (lead_id,),
        ).fetchone()
        return int(row["n"])


def list_due_followups(limit: int = 10) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_followups WHERE estado='pendiente' AND programado_para <= ? "
            "ORDER BY programado_para ASC LIMIT ?",
            (_now(), limit),
        ).fetchall()
        return [dict(r) for r in rows]


def update_followup(followup_id: int, estado: str) -> None:
    with _conn() as conn:
        conn.execute("UPDATE agent_followups SET estado=? WHERE id=?", (estado, followup_id))


def cancel_followups_for_lead(lead_id: int) -> None:
    """Si el lead responde o pide la baja, no se le persigue más."""
    with _conn() as conn:
        conn.execute(
            "UPDATE agent_followups SET estado='cancelado' WHERE lead_id=? AND estado='pendiente'",
            (lead_id,),
        )


# ---------------------------------------------------- registro real de mercado

def summarize_silent_sent_batches(*, dias: int = 7) -> list[dict]:
    """Tandas REALMENTE enviadas hace `dias` o más en las que nadie respondió.

    Es el único dato honesto de 'silencio': se cuenta cuando ya pasó el plazo, no el
    día del envío (ese día todavía nadie tuvo tiempo de contestar). Agrupa por día de
    envío y nicho, y devuelve el conteo real de correos de esa tanda.
    """
    corte = (datetime.now() - timedelta(days=max(1, dias))).strftime("%Y-%m-%d")
    with _conn() as conn:
        rows = conn.execute(
            "SELECT SUBSTR(created_at, 1, 10) AS dia, "
            "       COALESCE(NULLIF(TRIM(nicho), ''), '(sin nicho)') AS nicho, "
            "       COUNT(*) AS cantidad "
            "FROM outbox WHERE status='sent' AND created_at IS NOT NULL "
            "AND SUBSTR(created_at, 1, 10) <= ? "
            "AND LOWER(TRIM(recipient)) NOT IN ("
            "    SELECT LOWER(TRIM(sender_email)) FROM processed_replies "
            "    WHERE sender_email IS NOT NULL"
            ") "
            "GROUP BY dia, nicho ORDER BY dia ASC",
            (corte,),
        ).fetchall()
        return [dict(r) for r in rows]

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
    website TEXT DEFAULT '',
    dossier TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient TEXT, subject TEXT, body TEXT, channel TEXT DEFAULT 'email',
    nicho TEXT, estilo TEXT DEFAULT '', scheduled_for TEXT, status TEXT DEFAULT 'pending',
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
CREATE TABLE IF NOT EXISTS content_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL DEFAULT 'post',
    nicho TEXT DEFAULT '',
    gancho TEXT NOT NULL,
    guion TEXT DEFAULT '',
    caption TEXT DEFAULT '',
    estado TEXT NOT NULL DEFAULT 'borrador',
    archivo TEXT DEFAULT '',
    nota TEXT DEFAULT '',
    ig_media_id TEXT DEFAULT '',
    error_ig TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, published_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_content_queue_estado ON content_queue(estado, created_at);
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# Columnas agregadas después de la primera versión de la tabla. Se añaden con ALTER TABLE
# para no tocar los datos que ya están en data/el_socio.db.
_MIGRACIONES = {
    "leads": [
        ("website", "TEXT DEFAULT ''"),
        ("dossier", "TEXT DEFAULT ''"),
    ],
    "outbox": [
        ("estilo", "TEXT DEFAULT ''"),
    ],
    "agent_log": [
        ("tokens_cache_creacion", "INTEGER DEFAULT 0"),
        ("tokens_cache_lectura", "INTEGER DEFAULT 0"),
        ("costo_usd", "REAL DEFAULT 0.0"),
    ],
    "content_queue": [
        ("ig_media_id", "TEXT DEFAULT ''"),
        ("error_ig", "TEXT DEFAULT ''"),
        ("hashtags_ig", "TEXT DEFAULT ''"),
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
    notes: str = "", website: str = "", dossier: str = "",
) -> int:
    email = email.lower().strip()
    now = _now()
    with _conn() as conn:
        existing = conn.execute("SELECT id FROM leads WHERE email=?", (email,)).fetchone()
        if existing:
            return int(existing["id"])
        cur = conn.execute(
            "INSERT INTO leads (name, company, email, whatsapp, nicho, service_interest, "
            "source, stage, notes, website, dossier, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, company, email, whatsapp, nicho, service_interest, source, stage,
             notes, website, dossier, now, now),
        )
        return int(cur.lastrowid)


def update_lead_enrichment(
    lead_id: int,
    *,
    company: str | None = None,
    name: str | None = None,
    whatsapp: str | None = None,
    website: str | None = None,
    dossier: str | None = None,
) -> dict | None:
    """Guarda perfil/dossier analizado de un lead sin sobrescribir etapa ni notas."""
    campos: list[str] = []
    valores: list[object] = []
    if company is not None and company.strip():
        campos.append("company=?")
        valores.append(company.strip())
    if name is not None and name.strip():
        campos.append("name=?")
        valores.append(name.strip())
    if whatsapp is not None and whatsapp.strip():
        campos.append("whatsapp=?")
        valores.append(whatsapp.strip())
    if website is not None:
        campos.append("website=?")
        valores.append(website.strip()[:400])
    if dossier is not None:
        campos.append("dossier=?")
        valores.append(dossier.strip()[:2500])
    if not campos:
        return get_lead_by_id(lead_id)
    campos.append("updated_at=?")
    valores.append(_now())
    valores.append(int(lead_id))
    with _conn() as conn:
        conn.execute(f"UPDATE leads SET {', '.join(campos)} WHERE id=?", valores)
        row = conn.execute("SELECT * FROM leads WHERE id=?", (int(lead_id),)).fetchone()
        return dict(row) if row else None


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


def enqueue_email(
    *, recipient: str, subject: str, body: str, nicho: str = "",
    estilo: str = "", scheduled_for: str | None = None,
) -> int:
    # Normalizado siempre: si no, already_emailed_today y cancel_pending_outbox_for_recipient
    # (que comparan en minúsculas) no encuentran la fila.
    recipient = recipient.lower().strip()
    estilo_limpio = (estilo or "").strip()[:60]
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO outbox (recipient, subject, body, channel, nicho, estilo, scheduled_for, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (recipient, subject, body, "email", nicho, estilo_limpio, scheduled_for or _now(), "pending", _now()),
        )
        return int(cur.lastrowid)


def get_last_sent_style_for_recipient(recipient: str) -> str:
    """Devuelve el último `estilo` realmente enviado o encolado a este correo."""
    if not DB_PATH.exists():
        return ""
    try:
        with _conn() as conn:
            row = conn.execute(
                "SELECT estilo FROM outbox WHERE LOWER(TRIM(recipient))=? "
                "AND status IN ('sent', 'pending') AND COALESCE(TRIM(estilo), '')!='' "
                "ORDER BY id DESC LIMIT 1",
                ((recipient or "").lower().strip(),),
            ).fetchone()
            return str(row["estilo"] or "").strip() if row else ""
    except sqlite3.OperationalError:
        return ""


def get_last_used_email_style(nicho: str = "") -> str:
    """Último modelo de correo usado en frío (para no repetir siempre el mismo seguido)."""
    if not DB_PATH.exists():
        return ""
    try:
        with _conn() as conn:
            if (nicho or "").strip():
                row = conn.execute(
                    "SELECT estilo FROM outbox WHERE nicho=? AND status IN ('sent', 'pending') "
                    "AND COALESCE(TRIM(estilo), '')!='' ORDER BY id DESC LIMIT 1",
                    (nicho.strip(),),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT estilo FROM outbox WHERE status IN ('sent', 'pending') "
                    "AND COALESCE(TRIM(estilo), '')!='' ORDER BY id DESC LIMIT 1"
                ).fetchone()
            return str(row["estilo"] or "").strip() if row else ""
    except sqlite3.OperationalError:
        return ""


def summarize_email_style_performance(nicho: str = "") -> dict[str, dict[str, int]]:
    """Métricas reales por modelo de correo (enviados, positivos, respuestas y bajas/negativos).

    Se alimenta únicamente de correos reales en `outbox` y respuestas reales en
    `processed_replies` / `leads`. Nunca inventa cifras.
    """
    if not DB_PATH.exists():
        return {}
    try:
        with _conn() as conn:
            params: tuple[object, ...] = ()
            filtro_nicho = ""
            if (nicho or "").strip():
                filtro_nicho = " AND nicho=?"
                params = (nicho.strip(),)
            rows = conn.execute(
                "SELECT LOWER(TRIM(recipient)) AS email, TRIM(estilo) AS estilo "
                "FROM outbox WHERE status IN ('sent', 'pending') "
                "AND COALESCE(TRIM(estilo), '')!=''" + filtro_nicho + " ORDER BY id ASC",
                params,
            ).fetchall()
            if not rows:
                return {}

            # Mapeo real de respuestas recibidas y etapas de leads.
            reply_intents: dict[str, set[str]] = {}
            for r in conn.execute(
                "SELECT LOWER(TRIM(sender_email)) AS em, intent FROM processed_replies "
                "WHERE sender_email IS NOT NULL"
            ).fetchall():
                reply_intents.setdefault(str(r["em"]), set()).add(str(r["intent"] or ""))

            lead_stages: dict[str, str] = {}
            for r in conn.execute("SELECT LOWER(TRIM(email)) AS em, stage FROM leads WHERE email IS NOT NULL").fetchall():
                lead_stages[str(r["em"])] = str(r["stage"] or "")

            stats: dict[str, dict[str, int]] = {}
            vistos_par: set[tuple[str, str]] = set()
            for r in rows:
                est = str(r["estilo"])
                em = str(r["email"])
                if not est or not em or (est, em) in vistos_par:
                    continue
                vistos_par.add((est, em))
                bucket = stats.setdefault(est, {"enviados": 0, "positivos": 0, "respuestas": 0, "negativos": 0})
                bucket["enviados"] += 1
                intents = reply_intents.get(em, set())
                stage = lead_stages.get(em, "")
                if "interesado_cita" in intents or stage in ("interesado_cita", "calificado", "esperando_precio_dueno"):
                    bucket["positivos"] += 1
                    bucket["respuestas"] += 1
                elif "respuesta_recibida" in intents or stage == "conversando":
                    bucket["respuestas"] += 1
                if "baja" in intents or "no_interesado" in intents or stage in ("baja", "no_interesado"):
                    bucket["negativos"] += 1
            return stats
    except sqlite3.OperationalError:
        return {}


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


def agent_log_count_today(herramienta: str) -> int:
    """Cuántas veces se registró esta `herramienta` hoy (p.ej. tope de preguntas del chat)."""
    today = datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM agent_log WHERE herramienta=? AND fecha LIKE ?",
            (herramienta, f"{today}%"),
        ).fetchone()
        return int(row["n"])


def recent_agent_log(limit: int = 20) -> list[dict]:
    """Últimas acciones reales del sistema (para pintar 'qué está haciendo' en el panel)."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT fecha, herramienta, resultado, costo_usd, bloqueado_por_guarda "
            "FROM agent_log ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]


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


def list_recent_subjects_today(limit: int = 30) -> list[str]:
    """Asuntos ya usados hoy en `outbox`, para evitar correos con plantilla idéntica."""
    today = datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        rows = conn.execute(
            "SELECT subject FROM outbox WHERE status IN ('pending','sent') "
            "AND created_at LIKE ? ORDER BY id DESC LIMIT ?",
            (f"{today}%", max(1, int(limit))),
        ).fetchall()
        return [str(r["subject"] or "").strip() for r in rows if r["subject"]]


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



# ------------------------------------------------------- cola de contenido (redes)

# Un estado por etapa real de la pieza. `descartado` y `publicado` son finales.
CONTENT_ESTADOS = ("borrador", "aprobado", "generado", "publicado", "descartado")
CONTENT_TIPOS = ("post", "video", "historia", "carrusel")


def enqueue_content(
    *, tipo: str, gancho: str, guion: str = "", caption: str = "",
    nicho: str = "", nota: str = "",
) -> int:
    """Mete una pieza en la cola como `borrador`. No valida la guarda de precios:
    eso lo hace `content_manager`, que es el único que debe encolar."""
    tipo = (tipo or "post").strip().lower()
    if tipo not in CONTENT_TIPOS:
        raise ValueError(f"tipo inválido: {tipo!r}")
    gancho = (gancho or "").strip()
    if not gancho:
        raise ValueError("el gancho no puede ir vacío")
    now = _now()
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO content_queue (tipo, nicho, gancho, guion, caption, estado, "
            "nota, created_at, updated_at) VALUES (?,?,?,?,?,'borrador',?,?,?)",
            (tipo, nicho, gancho, guion, caption, nota, now, now),
        )
        return int(cur.lastrowid)


def get_content(content_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM content_queue WHERE id=?", (int(content_id),)).fetchone()
        return dict(row) if row else None


def list_content(*, estado: str = "", limit: int = 100) -> list[dict]:
    with _conn() as conn:
        if estado:
            rows = conn.execute(
                "SELECT * FROM content_queue WHERE estado=? ORDER BY id DESC LIMIT ?",
                (estado, int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM content_queue ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [dict(r) for r in rows]


def update_content(
    content_id: int, *, estado: str | None = None, archivo: str | None = None,
    nota: str | None = None, ig_media_id: str | None = None, error_ig: str | None = None,
    hashtags_ig: str | None = None,
) -> dict | None:
    """Cambia estado/archivo/nota/ig de una pieza. `publicado` sella `published_at`."""
    if estado is not None and estado not in CONTENT_ESTADOS:
        raise ValueError(f"estado inválido: {estado!r}")
    campos, valores = [], []
    if estado is not None:
        campos.append("estado=?")
        valores.append(estado)
        if estado == "publicado":
            campos.append("published_at=?")
            valores.append(_now())
    if archivo is not None:
        campos.append("archivo=?")
        valores.append(archivo)
    if nota is not None:
        campos.append("nota=?")
        valores.append(nota)
    if ig_media_id is not None:
        campos.append("ig_media_id=?")
        valores.append(ig_media_id)
    if error_ig is not None:
        campos.append("error_ig=?")
        valores.append(error_ig[:500])
    if hashtags_ig is not None:
        campos.append("hashtags_ig=?")
        valores.append(hashtags_ig[:500])
    if not campos:
        return get_content(content_id)
    campos.append("updated_at=?")
    valores.append(_now())
    valores.append(int(content_id))
    with _conn() as conn:
        conn.execute(f"UPDATE content_queue SET {', '.join(campos)} WHERE id=?", valores)
    return get_content(content_id)


def count_content_by_estado() -> dict[str, int]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT estado, COUNT(*) AS n FROM content_queue GROUP BY estado"
        ).fetchall()
        return {r["estado"]: int(r["n"]) for r in rows}


def content_created_today() -> int:
    """Piezas activas creadas hoy (excluye descartadas) para el tope diario del cerebro."""
    today = datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM content_queue WHERE estado!='descartado' AND created_at LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return int(row["n"])


def content_created_today_by_tipo() -> dict[str, int]:
    """Desglose por tipo (`video`, `post`, `historia`, `carrusel`) de piezas activas creadas hoy."""
    today = datetime.now().strftime("%Y-%m-%d")
    conteo = {t: 0 for t in CONTENT_TIPOS}
    with _conn() as conn:
        rows = conn.execute(
            "SELECT tipo, COUNT(*) AS n FROM content_queue "
            "WHERE estado!='descartado' AND created_at LIKE ? GROUP BY tipo",
            (f"{today}%",),
        ).fetchall()
        for r in rows:
            t = str(r["tipo"] or "").strip().lower()
            if t in conteo:
                conteo[t] = int(r["n"])
    return conteo


def agent_content_cost_today_usd() -> float:
    """Lo que `content_brain` ha gastado hoy dentro del presupuesto compartido."""
    today = datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(costo_usd),0) AS usd FROM agent_log "
            "WHERE herramienta LIKE 'content_brain%' AND fecha LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return float(row["usd"])


def ig_published_today() -> int:
    """Piezas realmente publicadas hoy en Instagram (tope diario duro de publicación)."""
    today = datetime.now().strftime("%Y-%m-%d")
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM content_queue WHERE estado='publicado' AND published_at LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return int(row["n"])


def ig_published_today_by_tipo() -> dict[str, int]:
    """Desglose por tipo (`video`, `post`, `historia`, `carrusel`) publicado hoy en Instagram."""
    today = datetime.now().strftime("%Y-%m-%d")
    conteo = {t: 0 for t in CONTENT_TIPOS}
    with _conn() as conn:
        rows = conn.execute(
            "SELECT tipo, COUNT(*) AS n FROM content_queue "
            "WHERE estado='publicado' AND published_at LIKE ? GROUP BY tipo",
            (f"{today}%",),
        ).fetchall()
        for r in rows:
            t = str(r["tipo"] or "").strip().lower()
            if t in conteo:
                conteo[t] = int(r["n"])
    return conteo


def last_ig_published_datetime() -> datetime | None:
    """Fecha/hora de la última publicación real en Instagram."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT published_at FROM content_queue WHERE estado='publicado' "
            "AND published_at IS NOT NULL AND TRIM(published_at)!='' "
            "ORDER BY published_at DESC, id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        try:
            return datetime.strptime(str(row["published_at"]), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def list_recent_hooks(limit: int = 40) -> list[str]:
    """Últimos ganchos encolados, para que el cerebro de contenido nunca se repita."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT gancho FROM content_queue ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return [str(r["gancho"]).strip() for r in rows if r["gancho"]]


def list_recent_video_nichos(dias: int = 20) -> set[str]:
    """Nichos de REEL (video) ya usados en los últimos `dias` días: prohibido repetir tema."""
    corte = (datetime.now() - timedelta(days=max(1, dias))).strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT nicho FROM content_queue WHERE tipo='video' AND created_at >= ? "
            "AND estado != 'descartado'",
            (corte,),
        ).fetchall()
        return {str(r["nicho"]).strip().lower() for r in rows if r["nicho"]}


def list_recent_market_signals(limit: int = 12) -> dict[str, list[str]]:
    """Dolores y respuestas reales recientes (SIN correos ni datos personales de terceros)."""
    with _conn() as conn:
        landing = conn.execute(
            "SELECT mensaje FROM landing_messages ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        replies = conn.execute(
            "SELECT intent, snippet FROM processed_replies "
            "WHERE intent IN ('interesado_cita', 'respuesta_recibida') "
            "ORDER BY rowid DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return {
            "landing": [str(r["mensaje"] or "").strip()[:240] for r in landing if r["mensaje"]],
            "respuestas": [
                f"[{r['intent']}] {str(r['snippet'] or '').strip()[:240]}"
                for r in replies if r["snippet"]
            ],
        }


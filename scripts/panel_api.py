#!/usr/bin/env python3
"""API JSON real para el monitor móvil (`panel/monitor.html`) — cero datos inventados.

Todo sale de `data/el_socio.db`. Si un dato no existe de verdad (ej. cuánto se ha vendido
en plata — no hay registro de eso todavía), simplemente no se incluye, nunca se inventa.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import autopilot_dispatcher
import database
import ig_publisher
import sales_agent
import socio_chat

INTENT_ETIQUETA = {
    "interesado_cita": "interesado",
    "respuesta_recibida": "respuesta",
    "no_interesado": "no_interesado",
    "baja": "baja",
    "respuesta_automatica": "automatica",
}


def _iso(fecha_sqlite: str | None) -> str:
    """'2026-11-25 14:20:00' -> '2026-11-25T14:20:00' (hora local, sin inventar huso horario)."""
    if not fecha_sqlite:
        return datetime.now().isoformat()
    return str(fecha_sqlite).strip().replace(" ", "T")


def _dia_iso(hace_dias: int = 0) -> str:
    """'YYYY-MM-DD' de hoy (0) o de hace N días — para el toggle 'hoy/ayer' de Conversión."""
    return (datetime.now() - timedelta(days=hace_dias)).strftime("%Y-%m-%d")


def _minutos_desde(fecha_sqlite: str | None) -> float | None:
    if not fecha_sqlite:
        return None
    try:
        momento = datetime.strptime(str(fecha_sqlite), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return (datetime.now() - momento).total_seconds() / 60.0


def _tipo_y_etiqueta(fila: dict) -> tuple[str, str]:
    herramienta = str(fila.get("herramienta") or "")
    bloqueado = str(fila.get("bloqueado_por_guarda") or "").strip()
    etiqueta, tipo = database.HERRAMIENTA_ETIQUETA.get(herramienta, (herramienta or "(acción)", "exito"))
    if bloqueado:
        tipo = "alerta"
        etiqueta = f"Bloqueado por guarda: {bloqueado}"
    return etiqueta, tipo


def _mensaje_log(fila: dict, etiqueta: str) -> str:
    """Etiqueta humana y corta — el `resultado` crudo (JSON de error, ids, etc.) va aparte en
    `detalle` para que la lista no se llene de código; el celular lo muestra tras un toque."""
    return etiqueta


def _detalle_log(fila: dict) -> str:
    return str(fila.get("resultado") or "").strip()[:4000]


def _content_id_reintentable(fila: dict) -> int | None:
    """Solo 'ig_publish_error' trae un `content_id` real guardado en `argumentos` — es el
    único fallo de hoy que se puede reintentar de verdad contra la API de Meta."""
    if str(fila.get("herramienta") or "") != "ig_publish_error":
        return None
    try:
        datos = json.loads(fila.get("argumentos") or "{}")
        return int(datos["content_id"])
    except (ValueError, TypeError, KeyError):
        return None


def construir_estado() -> dict:
    filas = database.recent_agent_log(limit=1)
    if not filas:
        return {
            "color": "amarillo",
            "etiqueta": "Sin actividad",
            "accion_actual": "Todavía no hay ninguna acción registrada en el sistema.",
            "actualizado": datetime.now().isoformat(),
        }
    fila = filas[0]
    etiqueta_accion, tipo = _tipo_y_etiqueta(fila)
    mapa_color = {"fallo": "rojo", "alerta": "amarillo", "exito": "verde"}
    mapa_etiqueta = {"fallo": "En error", "alerta": "Esperando tu revisión", "exito": "Ejecutando"}
    color, etiqueta_estado = mapa_color[tipo], mapa_etiqueta[tipo]
    minutos = _minutos_desde(fila.get("fecha"))
    if tipo == "exito" and minutos is not None and minutos > 60:
        color, etiqueta_estado = "amarillo", "Inactivo (sin acciones en más de 1h)"
    return {
        "color": color,
        "etiqueta": etiqueta_estado,
        "accion_actual": _mensaje_log(fila, etiqueta_accion),
        "actualizado": _iso(fila.get("fecha")),
    }


def construir_metricas() -> dict:
    hoy = datetime.now().strftime("%Y-%m-%d")
    filas_hoy = [f for f in database.recent_agent_log(limit=300) if str(f.get("fecha") or "").startswith(hoy)]
    ok = fail = 0
    for f in filas_hoy:
        _, tipo = _tipo_y_etiqueta(f)
        if tipo == "fallo":
            fail += 1
        else:
            ok += 1
    cfg = autopilot_dispatcher.load_env_file()
    tope_usd = sales_agent._decimal(cfg, "SALES_AGENT_MAX_DAILY_USD", 0.50)
    return {
        "tareas_ok": ok,
        "tareas_fail": fail,
        "chats_activos": database.count_correos_activos(),
        "leads_hoy": database.count_leads_creados_hoy(),
        "seguimientos_pendientes": database.count_seguimientos_pendientes(),
        "gasto_ia_hoy_usd": round(database.agent_cost_today_usd(), 4),
        "gasto_ia_tope_usd": tope_usd,
    }


def construir_logs(limite: int = 25) -> list[dict]:
    salida = []
    for i, f in enumerate(database.recent_agent_log(limit=limite)):
        if str(f.get("herramienta") or "") == socio_chat.HERRAMIENTA_LOG:
            continue  # preguntas tuyas al chat no son "tareas" del agente
        etiqueta, tipo = _tipo_y_etiqueta(f)
        salida.append({
            "id": f"log{i}-{f.get('fecha', '')}",
            "tipo": tipo,
            "mensaje": _mensaje_log(f, etiqueta),
            "detalle": _detalle_log(f),
            "content_id": _content_id_reintentable(f),
            "contacto": "",
            "hora": _iso(f.get("fecha")),
        })
    return salida


def construir_correos(fecha: str, limite: int = 15) -> list[dict]:
    """Interesados reales de ese día — solo respuestas de correo clasificadas como
    'interesado_cita', nunca rebotes SMTP. `fecha` en formato 'YYYY-MM-DD'."""
    with database._conn() as conn:
        filas = conn.execute(
            "SELECT message_id, sender_email, intent, snippet, processed_at FROM processed_replies "
            "WHERE intent='interesado_cita' AND processed_at LIKE ? ORDER BY rowid DESC LIMIT ?",
            (f"{fecha}%", limite),
        ).fetchall()
        salida = []
        for r in filas:
            email = str(r["sender_email"] or "").lower().strip()
            lead = conn.execute("SELECT * FROM leads WHERE email=?", (email,)).fetchone()
            nombre = (lead["name"] if lead and lead["name"] else "") or email or "(sin nombre)"
            ult_envio = conn.execute(
                "SELECT subject FROM outbox WHERE LOWER(TRIM(recipient))=? ORDER BY id DESC LIMIT 1",
                (email,),
            ).fetchone()
            asunto = f"Re: {ult_envio['subject']}" if ult_envio and ult_envio["subject"] else "(correo directo)"

            pasos = [{"texto": "Lead registrado", "ok": True}]
            enviado = conn.execute(
                "SELECT 1 FROM outbox WHERE LOWER(TRIM(recipient))=? AND status='sent' LIMIT 1", (email,)
            ).fetchone()
            pasos.append({"texto": "Correo de prospección enviado", "ok": enviado is not None})
            pasos.append({
                "texto": f"Respondió: {INTENT_ETIQUETA.get(r['intent'], r['intent'])}",
                "ok": True,
            })
            pausado = False
            if lead:
                pausado = database.is_lead_pausado(int(lead["id"]))
                pendiente = conn.execute(
                    "SELECT 1 FROM agent_followups WHERE lead_id=? AND estado='pendiente' LIMIT 1",
                    (lead["id"],),
                ).fetchone()
                if pendiente:
                    pasos.append({"texto": "Seguimiento programado", "ok": True})

            salida.append({
                "id": str(r["message_id"]),
                "lead_id": int(lead["id"]) if lead else None,
                "nombre": nombre,
                "email": email,
                "asunto": asunto,
                "ultimo_mensaje": (r["snippet"] or "").strip()[:160],
                "ultima_hora": _iso(r["processed_at"]),
                "intent": INTENT_ETIQUETA.get(r["intent"], r["intent"] or ""),
                "pausado": pausado,
                "resumen": (r["snippet"] or "").strip()[:400] or "Sin resumen disponible.",
                "pasos": pasos,
            })
        return salida


def construir_correos_enviados(fecha: str, limite: int = 50) -> list[dict]:
    """Correos de prospección que de verdad salieron ese día, con el cuerpo real completo
    para la vista previa (nunca un resumen inventado). `fecha` en formato 'YYYY-MM-DD'."""
    salida = []
    for r in database.list_correos_enviados_dia(fecha, limite):
        cuerpo = str(r.get("body") or "").strip()
        destinatario = str(r.get("recipient") or "").strip()
        salida.append({
            "id": r["id"],
            "destinatario": destinatario,
            "asunto": str(r.get("subject") or "").strip() or "(sin asunto)",
            "vista_previa": cuerpo[:200],
            "cuerpo_completo": cuerpo,
            "nicho": str(r.get("nicho") or "").strip(),
            "hora": _iso(r.get("scheduled_for")),
        })
    return salida


def construir_piezas_ig(fecha: str, limite: int = 50) -> list[dict]:
    """Piezas publicadas ese día en Instagram con su engagement real (Graph API), para la
    pestaña 'Comentarios IG'. `fecha` en formato 'YYYY-MM-DD'."""
    salida = []
    for r in database.list_piezas_ig_publicadas_dia(fecha, limite):
        texto = "\n\n".join(t for t in (str(r.get("gancho") or "").strip(), str(r.get("caption") or "").strip()) if t)
        salida.append({
            "id": r["id"],
            "tipo": str(r.get("tipo") or "").strip(),
            "mensaje": texto or "(sin texto)",
            "comentarios": int(r.get("comentarios_ig") or 0),
            "likes": int(r.get("likes_ig") or 0),
            "hora": _iso(r.get("published_at")),
        })
    return salida


def _detalle_conversion_dia(fecha: str) -> dict:
    return {
        "correos_enviados": construir_correos_enviados(fecha, limite=200),
        "interesados": construir_correos(fecha, limite=200),
        "comentarios_ig": construir_piezas_ig(fecha, limite=200),
    }


def construir_pendientes(limite: int = 30) -> dict:
    """Lo que está en cola esperando salir, con su vista previa y si de verdad puede salir.

    Lo importante no es solo listarlas: es decir CUÁLES NUNCA VAN A SALIR. Una pieza de un
    tipo con cuota diaria 0 se queda en la cola para siempre, y el cerebro ya pagó tokens
    pensándola y minutos de render haciéndola. Eso tiene que verse sin preguntarle a nadie.
    """
    import ig_publisher

    cfg = ig_publisher.cargar_config_ig()
    lims = ig_publisher.limites_diarios_ig(cfg)
    topes = dict(lims["por_tipo"] or {})
    usa_por_tipo = bool(lims["usa_por_tipo"])
    hechos_hoy = database.ig_published_today_by_tipo()

    piezas, muertas = [], 0
    for fila in database.list_content(limit=120):
        estado = str(fila.get("estado") or "")
        if estado in ("publicado", "descartado"):
            continue
        tipo = str(fila.get("tipo") or "post").strip().lower()
        tope = int(topes.get(tipo, 0)) if usa_por_tipo else int(lims["total"])
        hoy = int(hechos_hoy.get(tipo, 0))
        tiene_archivo = bool(str(fila.get("archivo") or "").strip())

        if usa_por_tipo and tope <= 0:
            puede, motivo = False, "cuota 0: nunca va a salir"
            muertas += 1
        elif hoy >= tope:
            puede, motivo = False, "cuota de hoy llena, sale mañana"
        elif not tiene_archivo:
            puede, motivo = False, "falta renderizar"
        else:
            puede, motivo = True, "lista para salir"

        piezas.append({
            "id": int(fila["id"]),
            "tipo": tipo,
            "estado": estado,
            "gancho": str(fila.get("gancho") or "")[:150],
            "creada": _iso(fila.get("created_at")),
            "tiene_archivo": tiene_archivo,
            "preview": f"/poster/{int(fila['id'])}" if tiene_archivo else "",
            "media": f"/media/{int(fila['id'])}" if tiene_archivo else "",
            "puede_salir": puede,
            "motivo": motivo,
            "cupo": f"{hoy}/{tope}",
        })
        if len(piezas) >= limite:
            break

    # Las que nunca van a salir, primero: son las que exigen una decisión.
    piezas.sort(key=lambda p: (p["puede_salir"], p["id"]))
    return {"piezas": piezas, "total": len(piezas), "muertas": muertas,
            "cuota": topes if usa_por_tipo else {"total": int(lims["total"])},
            "publicado_hoy": hechos_hoy}


def construir_estado_monitor() -> dict:
    database.init_db()
    hoy, ayer = _dia_iso(0), _dia_iso(1)
    detalle_hoy, detalle_ayer = _detalle_conversion_dia(hoy), _detalle_conversion_dia(ayer)
    return {
        "estado": construir_estado(),
        "metricas": construir_metricas(),
        "logs": construir_logs(),
        "conversion": {
            "hoy": {
                "correos_enviados": len(detalle_hoy["correos_enviados"]),
                "interesados": len(detalle_hoy["interesados"]),
                "comentarios_ig": sum(p["comentarios"] for p in detalle_hoy["comentarios_ig"]),
            },
            "ayer": {
                "correos_enviados": len(detalle_ayer["correos_enviados"]),
                "interesados": len(detalle_ayer["interesados"]),
                "comentarios_ig": sum(p["comentarios"] for p in detalle_ayer["comentarios_ig"]),
            },
        },
        "conversion_detalle": {"hoy": detalle_hoy, "ayer": detalle_ayer},
        "pendientes": construir_pendientes(),
    }


def responder_pregunta(pregunta: str) -> str:
    return socio_chat.responder(pregunta)


def accion_reintentar_ig(content_id: int) -> dict:
    """Vuelve a intentar publicar esa pieza en Instagram ahora mismo, de verdad (API de Meta).
    Si Meta sigue rechazándolo (ej. cuenta restringida), devuelve el error real tal cual —
    nunca se finge éxito."""
    database.init_db()
    resultado = ig_publisher.publicar_pieza_ig(content_id)
    return {
        "ok": bool(resultado.get("publicado")),
        "error": resultado.get("error"),
        "ig_media_id": resultado.get("ig_media_id"),
    }


def accion_pausar_lead(lead_id: int, pausado: bool) -> dict:
    database.init_db()
    database.set_lead_pausado(int(lead_id), bool(pausado))
    return {"lead_id": int(lead_id), "pausado": bool(pausado)}

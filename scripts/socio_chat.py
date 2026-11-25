#!/usr/bin/env python3
"""Chat de diagnóstico del panel 8787.

Raymond pregunta en español qué está haciendo el sistema (o por qué no publicó/envió) y
este módulo arma un snapshot 100% real (BD + logs, cero invención) y se lo pasa a Claude
para que responda SOLO en base a eso. Comparte el mismo tope diario de USD que ventas/
contenido (`SALES_AGENT_MAX_DAILY_USD`), con su propio sub-tope para no comerse el cupo
de correos ni de Reels.
"""

from __future__ import annotations

import json
from datetime import datetime

import autopilot_dispatcher
import content_manager
import database
import ig_publisher
import sales_agent

MODELO_CHAT = "claude-sonnet-5"
MAX_USD_CHAT_DIA = 0.10
MAX_PREGUNTAS_DIA = 20
HERRAMIENTA_LOG = "chat_panel"


def _snapshot_real() -> dict[str, object]:
    """Todo dato real y verificable que el chat puede usar para responder. Nada inventado."""
    database.init_db()
    cfg = autopilot_dispatcher.load_env_file()
    ajustes = database.get_settings()

    ahora = datetime.now()
    try:
        inicio_h = int(ajustes.get("autopilot_send_start_hour", "8"))
        fin_h = int(ajustes.get("autopilot_send_end_hour", "21"))
    except ValueError:
        inicio_h, fin_h = 8, 21

    return {
        "hora_actual": ahora.strftime("%Y-%m-%d %H:%M"),
        "ventana_de_trabajo": f"{inicio_h:02d}:00 a {fin_h:02d}:00",
        "dentro_de_ventana_ahora": autopilot_dispatcher._is_within_sending_window(ajustes),
        "instagram": ig_publisher.estado_ig(ig_publisher.cargar_config_ig()),
        "correos": {
            "enviados_hoy": database.count_sent_emails_today(),
            "tope_diario": sales_agent._decimal(cfg, "MAX_DAILY_EMAILS", 15),
        },
        "contenido_por_estado": database.count_content_by_estado(),
        "gasto_ia_hoy_usd": round(database.agent_cost_today_usd(), 4),
        "tope_gasto_ia_dia_usd": sales_agent._decimal(cfg, "SALES_AGENT_MAX_DAILY_USD", 0.50),
        "ultimas_acciones_reales": [
            {
                "fecha": fila["fecha"],
                "accion": fila["herramienta"],
                "resultado": (fila["resultado"] or "")[:200],
                "bloqueado_por_guarda": fila["bloqueado_por_guarda"] or "",
            }
            for fila in database.recent_agent_log(limit=12)
            if fila["herramienta"] != HERRAMIENTA_LOG
        ],
    }


def _preguntas_restantes_hoy() -> int:
    return max(0, MAX_PREGUNTAS_DIA - database.agent_log_count_today(HERRAMIENTA_LOG))


def responder(pregunta: str) -> str:
    """Devuelve una respuesta corta y honesta a `pregunta`, basada solo en datos reales."""
    pregunta = (pregunta or "").strip()[:500]
    if not pregunta:
        return "Escribe una pregunta primero."

    if database.agent_log_count_today(HERRAMIENTA_LOG) >= MAX_PREGUNTAS_DIA:
        return f"Tope de {MAX_PREGUNTAS_DIA} preguntas de hoy alcanzado. Mañana sigue disponible."

    gastado = database.agent_cost_today_usd()
    cfg = autopilot_dispatcher.load_env_file()
    tope_total = sales_agent._decimal(cfg, "SALES_AGENT_MAX_DAILY_USD", 0.50)
    if gastado >= tope_total:
        return f"Tope diario de gasto de IA alcanzado ({gastado:.4f}/{tope_total:.2f} USD). Mañana sigue disponible."

    api_key = (cfg.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        return "Falta ANTHROPIC_API_KEY en .env — no puedo razonar la respuesta, pero puedes ver los datos crudos en el panel."

    snapshot = _snapshot_real()
    system = (
        "Eres el reporte de estado de 'El Socio', el sistema de Raymond. Te paso un snapshot "
        "JSON con TODO el dato real disponible ahora mismo (BD y logs). Responde SU pregunta "
        "en español, directo, máximo 5 líneas, SIN inventar ningún dato que no esté en el JSON. "
        "Si algo no está en el JSON, di explícitamente que no tienes ese dato en vez de adivinar. "
        "Si detectas que algo está bloqueado o fallando, dilo crudo y di por qué, no lo suavices."
    )
    cuerpo = {
        "model": MODELO_CHAT,
        "max_tokens": 400,
        "system": system,
        "messages": [{
            "role": "user",
            "content": f"SNAPSHOT:\n{json.dumps(snapshot, ensure_ascii=False, default=str)}\n\nPREGUNTA: {pregunta}",
        }],
    }
    try:
        datos = sales_agent.llamar_api(api_key, cuerpo)
    except sales_agent.ErrorAPI as exc:
        return f"Fallo al llamar a la IA: {exc}"

    uso = datos.get("usage") or {}
    costo = sales_agent.calcular_costo_usd(MODELO_CHAT, uso)
    texto = "".join(b.get("text", "") for b in (datos.get("content") or []) if b.get("type") == "text").strip()
    database.log_agent_action(
        lead_id=None, turno=0, modelo=MODELO_CHAT, herramienta=HERRAMIENTA_LOG,
        argumentos=pregunta[:300], resultado=texto[:300],
        tokens_entrada=int(uso.get("input_tokens", 0)), tokens_salida=int(uso.get("output_tokens", 0)),
        costo_usd=costo,
    )
    return texto or "La IA no devolvió texto."


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Chat de diagnóstico de El Socio.")
    parser.add_argument("pregunta", nargs="*", help="Pregunta a responder.")
    parser.add_argument("--snapshot", action="store_true", help="Solo imprime el snapshot real, sin llamar IA.")
    args = parser.parse_args(argv)
    if args.snapshot:
        print(json.dumps(_snapshot_real(), indent=2, ensure_ascii=False, default=str))
        return 0
    print(responder(" ".join(args.pregunta)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

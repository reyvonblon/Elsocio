#!/usr/bin/env python3
"""Orquestador Maestro Autónomo de El Socio (`socio_cerebro.py`).

Un solo latido que ejecuta TODO el trabajo comercial y creativo sin intervención
humana, respetando prioridades, ventana horaria y todos los topes duros en código:

  1. Respuestas IMAP (`sync_imap_replies`): bajas gratis primero; responde y califica
     leads interesados con `sales_agent` y pide precio a Raymond cuando califican.
  2. Landing Web3Forms (`sync_landing_messages`): recoge WhatsApp + correo + problema.
  3. Prospección verificada (`ensure_daily_pipeline`): descubre negocios con MX real.
  4. Ciclo comercial del agente (`run_sales_agent_cycle`): seguimientos + frío.
  5. Despacho SMTP (`dispatch_due_jobs`): envía respetando ventana, pausas y rebotes.
  6. Cerebro de contenido (`CerebroContenido`): SOLO si sobra presupuesto del tope
     compartido de 0.50 USD/día (vender siempre va primero), piensa la pieza, valida
     cero cifras y renderiza post o Reel con voz humana neuronal.
  7. Publicación oficial en Instagram (`ig_publisher`): si `ig_auto_publish=1` y hay
     credenciales de Meta Graph API, publica solo respetando el tope diario.
  8. Memoria real de mercado + Panel (`RESULTADOS_MERCADO.md` + `panel/mensajes.html`) y el
     paquete `redes/paquete_hoy/` (todo lo `generado` sin publicar, listo para subir a mano
     mientras no haya claves de Instagram).

`--dry-run` inspecciona los 8 frentes en seco: 0 tokens, 0 red de envío, 0 BD tocada.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = PROJECT_ROOT / "data" / "cerebro_autonomo.lock"

if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import autopilot_dispatcher  # noqa: E402
import content_brain  # noqa: E402
import content_manager  # noqa: E402
import database  # noqa: E402
import ig_publisher  # noqa: E402
import panel_mensajes  # noqa: E402
import renovar_token_ig  # noqa: E402
import voice_engine  # noqa: E402


def _ejecutar_seguro(fn, *args, **kwargs) -> dict[str, object]:
    try:
        res = fn(*args, **kwargs)
        return res if isinstance(res, dict) else {"resultado": res}
    except Exception as exc:
        return {"error": str(exc)[:300]}


def diagnostico_en_seco() -> dict[str, object]:
    """Inspección integral 100% libre de efectos secundarios."""
    cfg = autopilot_dispatcher.load_env_file()
    base = autopilot_dispatcher.resumen_en_seco()
    cerebro = content_brain.CerebroContenido(cfg, dry_run=True)
    return {
        "dry_run": True,
        "motor_ventas": base,
        "cerebro_contenido": cerebro.planear_y_crear_lote_diario(renderizar=False),
        "instagram_oficial": ig_publisher.estado_ig(cfg),
        # Solo lectura: dice que token hay y cuando vence, sin tocar nada.
        "token_ig": renovar_token_ig.estado_token(cfg),
        "motor_voz": {
            "proveedor_activo": voice_engine.elegir_proveedor(voice_engine.cargar_config_voz()),
            "voz_defecto": voice_engine.VOZ_EDGE_DEFECTO,
        },
    }


def correr_latido_autonomo(*, dry_run: bool = False, sin_contenido: bool = False) -> dict[str, object]:
    if dry_run:
        return diagnostico_en_seco()

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w", encoding="utf-8") as lock_fh:
        try:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"ok": True, "omitido": "otro_ciclo_en_ejecucion"}

        database.init_db()
        cfg = autopilot_dispatcher.load_env_file()
        ajustes = database.get_settings()
        en_ventana = autopilot_dispatcher._is_within_sending_window(ajustes)

        reporte: dict[str, object] = {"ok": True, "en_ventana_horaria": en_ventana}

        # 1 y 2: Entrantes SIEMPRE se atienden (las bajas y leads calientes no esperan).
        reporte["respuestas_imap"] = _ejecutar_seguro(autopilot_dispatcher.sync_imap_replies)
        reporte["landing"] = _ejecutar_seguro(autopilot_dispatcher.sync_landing_messages)

        # 3, 4 y 5: Prospección, redacción comercial y envío SMTP en ventana horaria.
        reporte["prospeccion"] = _ejecutar_seguro(autopilot_dispatcher.ensure_daily_pipeline)
        if autopilot_dispatcher._tiene_anthropic_key(cfg):
            reporte["agente_ventas"] = _ejecutar_seguro(autopilot_dispatcher.run_sales_agent_cycle)
        else:
            reporte["agente_ventas"] = {"ran": False, "reason": "sin_api_key"}

        reporte["despacho_smtp"] = _ejecutar_seguro(
            autopilot_dispatcher.dispatch_due_jobs,
            respect_pacing=True, respect_window=True,
        )

        # El token de Instagram se ha muerto en silencio varias veces y se descubria tarde,
        # con el motor horas sin publicar. Se revisa en CADA latido: si murio suena el celular,
        # y si es un token de usuario al que le queda poco se cambia solo por uno de pagina
        # (que no vence). Nunca mas enterarse por casualidad.
        reporte["token_ig"] = _ejecutar_seguro(renovar_token_ig.vigilar_token, cfg=cfg)

        # 6 y 7: Contenido + Instagram (SOLO dentro de ventana 8:00-21:00 y tras atender ventas).
        if not sin_contenido and en_ventana:
            cerebro_c = content_brain.CerebroContenido(cfg)
            reporte["cerebro_contenido"] = _ejecutar_seguro(
                cerebro_c.planear_y_crear_lote_diario, max_renders_video=1,
            )
            reporte["instagram"] = _ejecutar_seguro(
                ig_publisher.ciclo_publicacion_autonoma, cfg=cfg,
            )
        else:
            reporte["cerebro_contenido"] = {
                "omitido": "sin_contenido_flag" if sin_contenido else "fuera_de_ventana_horaria"
            }

        # 8: Resultados reales de mercado (silencios vencidos + comentarios reales IG) + panel.
        reporte["silencios_correo"] = _ejecutar_seguro(
            autopilot_dispatcher.registrar_silencios_vencidos
        )
        reporte["metricas_ig"] = _ejecutar_seguro(ig_publisher.sincronizar_resultados_ig, cfg=cfg)
        _ejecutar_seguro(panel_mensajes.regenerate)
        reporte["paquete_manual"] = _ejecutar_seguro(content_manager.armar_paquete_pendiente)
        return reporte


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cerebro Autónomo Maestro de El Socio.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Diagnóstico completo sin escribir en BD ni llamar APIs.")
    parser.add_argument("--sin-contenido", action="store_true",
                        help="Ejecuta solo ventas/correo sin correr contenido ni Instagram.")
    args = parser.parse_args(argv)

    res = correr_latido_autonomo(dry_run=args.dry_run, sin_contenido=args.sin_contenido)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

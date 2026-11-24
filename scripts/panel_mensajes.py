#!/usr/bin/env python3
"""Genera el panel visual local de El Socio (mensajes + cola de contenido + interruptor autónomo).

Uso: python3 scripts/panel_mensajes.py
Nunca se sube a Git ni expone secretos — todo texto externo pasa por `html.escape()`.
"""

from __future__ import annotations

import html
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = PROJECT_ROOT / "panel" / "mensajes.html"

if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import database  # noqa: E402

ESTADO_COLOR = {
    "nuevo": "#9c1c2e",
    "contactado": "#4a7c59",
    "cerrado": "#6e6e73",
}

CONTENIDO_COLOR = {
    "borrador": "#6e6e73",
    "aprobado": "#4a7c59",
    "generado": "#2f6f9f",
    "publicado": "#9c1c2e",
    "descartado": "#3a3a3e",
}


def _url_preview(pieza: dict, *, interactivo: bool) -> tuple[str, str]:
    """Devuelve (tipo_media, src_escapado) si el archivo existe de verdad en disco."""
    ruta_txt = str(pieza.get("archivo") or "").strip()
    if not ruta_txt:
        return "", ""
    ruta = Path(ruta_txt)
    if not ruta.exists():
        return "", ""
    sufijo = ruta.suffix.lower()
    src = f"/media/{int(pieza['id'])}" if interactivo else html.escape(os.path.relpath(ruta, OUT_PATH.parent))
    if sufijo == ".mp4":
        return "video", src
    if sufijo in (".png", ".jpg", ".jpeg"):
        return "imagen", src
    return "", ""


def render_contenido(piezas: list[dict], *, interactivo: bool = False) -> str:
    if not piezas:
        return ('<tr><td colspan="4" class="empty">'
                'Todavía no hay piezas en la cola de contenido.</td></tr>')
    filas = ""
    for p in piezas:
        pid = int(p["id"])
        est_crudo = str(p.get("estado") or "")
        color = CONTENIDO_COLOR.get(est_crudo, "#6e6e73")
        gancho = html.escape(str(p.get("gancho") or ""))
        caption = html.escape(str(p.get("caption") or ""))
        guion = html.escape(str(p.get("guion") or ""))
        tipo = html.escape(str(p.get("tipo") or ""))
        estado = html.escape(est_crudo)
        archivo_nombre = html.escape(Path(str(p.get("archivo") or "")).name)
        error_ig = html.escape(str(p.get("error_ig") or ""))

        tipo_media, src_media = _url_preview(p, interactivo=interactivo)
        preview_html = ""
        if tipo_media == "video":
            preview_html = (
                f'<div class="media-box"><video controls playsinline preload="metadata" '
                f'src="{src_media}"></video></div>'
            )
        elif tipo_media == "imagen":
            preview_html = f'<div class="media-box"><img src="{src_media}" alt="Preview #{pid}" /></div>'

        detalles_extra = ""
        if guion:
            detalles_extra += f'<div class="meta-txt"><strong>Guion:</strong> {guion.replace(chr(10), " · ")}</div>'
        if caption:
            detalles_extra += f'<div class="meta-txt"><strong>Caption:</strong> {caption}</div>'
        if error_ig:
            detalles_extra += f'<div class="err-txt">Aviso IG: {error_ig}</div>'

        controles = ""
        if interactivo and est_crudo not in ("publicado", "descartado"):
            botones = []
            if est_crudo in ("borrador", "aprobado"):
                botones.append(
                    f'<form method="POST" action="/accion" class="inline-f">'
                    f'<input type="hidden" name="accion" value="generar" />'
                    f'<input type="hidden" name="id" value="{pid}" />'
                    f'<button type="submit" class="btn sec">Renderizar</button></form>'
                )
            if est_crudo == "generado":
                botones.append(
                    f'<form method="POST" action="/accion" class="inline-f">'
                    f'<input type="hidden" name="accion" value="publicar_ig" />'
                    f'<input type="hidden" name="id" value="{pid}" />'
                    f'<button type="submit" class="btn pri">Publicar en IG</button></form>'
                )
            botones.append(
                f'<form method="POST" action="/accion" class="inline-f">'
                f'<input type="hidden" name="accion" value="descartar" />'
                f'<input type="hidden" name="id" value="{pid}" />'
                f'<button type="submit" class="btn mut">Descartar</button></form>'
            )
            controles = f'<div class="btn-row">{"".join(botones)}</div>'

        filas += f"""
        <tr>
          <td class="fecha">#{pid}</td>
          <td class="mensaje">
            <div class="gancho-txt">{gancho}</div>
            {detalles_extra}
            {preview_html}
            {controles}
          </td>
          <td class="fecha">{tipo}{' · ' + archivo_nombre if archivo_nombre else ''}</td>
          <td><span class="badge" style="background:{color}">{estado}</span></td>
        </tr>"""
    return filas


def _render_barra_estado(estado_motor: dict | None, *, interactivo: bool) -> str:
    if not estado_motor:
        return ""
    auto_ig = bool(estado_motor.get("auto_publish", True))
    correos = html.escape(str(estado_motor.get("correos_hoy", "0/15")))
    gasto = html.escape(str(estado_motor.get("gasto_usd", "$0.00 / $0.50")))
    posts_ig = html.escape(str(estado_motor.get("posts_ig_hoy", "0/1")))
    aviso = html.escape(str(estado_motor.get("aviso", "")))

    def _chip(nombre: str, ok: bool) -> str:
        color = "#2f7d4a" if ok else "#7a2e2e"
        txt = "OK" if ok else "Falta clave"
        return f'<span class="chip" style="border-color:{color}">{html.escape(nombre)}: <strong>{txt}</strong></span>'

    ig_user_txt = html.escape(str(estado_motor.get("ig_username") or ""))
    ig_label = f"Instagram (@{ig_user_txt})" if ig_user_txt else "Instagram API"
    chips = (
        _chip("Gmail", bool(estado_motor.get("gmail_ok")))
        + _chip("Anthropic IA", bool(estado_motor.get("anthropic_ok")))
        + _chip(ig_label, bool(estado_motor.get("ig_ok")))
    )

    modo_txt = "AUTÓNOMO (publica solo)" if auto_ig else "PREVIEW (espera tu clic)"
    modo_color = "#2f7d4a" if auto_ig else "#9a6b1f"
    boton_modo = ""
    caja_claves = ""
    if interactivo:
        nuevo_valor = "0" if auto_ig else "1"
        etiqueta_btn = "Pasar a Modo Preview" if auto_ig else "Activar Modo Autónomo"
        boton_modo = (
            f'<form method="POST" action="/accion" class="inline-f">'
            f'<input type="hidden" name="accion" value="toggle_modo" />'
            f'<input type="hidden" name="activo" value="{nuevo_valor}" />'
            f'<button type="submit" class="btn sec">{etiqueta_btn}</button></form>'
        )
        if not (estado_motor.get("anthropic_ok") and estado_motor.get("ig_ok")):
            caja_claves = """
            <form method="POST" action="/accion" style="margin-top:16px; border-top:1px solid var(--border); padding-top:14px; display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
              <input type="hidden" name="accion" value="guardar_claves" />
              <input type="password" name="anthropic_key" autocomplete="off" placeholder="Pegar ANTHROPIC_API_KEY (opcional si ya está)" style="flex:1; min-width:220px; background:#0a0a0a; border:1px solid var(--border); color:#fff; border-radius:8px; padding:8px 12px; font-size:12.5px;" />
              <input type="password" name="ig_token" autocomplete="off" placeholder="Pegar IG_ACCESS_TOKEN oficial de Meta (descubre tu ID solo)" style="flex:1; min-width:250px; background:#0a0a0a; border:1px solid var(--border); color:#fff; border-radius:8px; padding:8px 12px; font-size:12.5px;" />
              <button type="submit" class="btn pri">Guardar y Conectar</button>
            </form>"""

    banner = f'<div class="notice">{aviso}</div>' if aviso else ""
    return f"""
    {banner}
    <div class="status-card">
      <div class="status-top">
        <div>
          <span class="badge" style="background:{modo_color}">{modo_txt}</span>
          <span class="kpi">Correos hoy: <strong>{correos}</strong></span>
          <span class="kpi">Saldo IA hoy: <strong>{gasto}</strong></span>
          <span class="kpi">IG hoy: <strong>{posts_ig}</strong></span>
        </div>
        <div>{boton_modo}</div>
      </div>
      <div class="chips">{chips}</div>
      {caja_claves}
    </div>"""


def render(
    messages: list[dict], piezas: list[dict] | None = None, *,
    estado_motor: dict | None = None, interactivo: bool = False,
) -> str:
    rows = ""
    if not messages:
        rows = '<tr><td colspan="3" class="empty">Todavía no ha llegado ningún mensaje.</td></tr>'
    for m in messages:
        color = ESTADO_COLOR.get(m["estado"], "#9c1c2e")
        # Todo lo que venga de fuera se escapa: el mensaje lo escribe un desconocido
        # en la landing y sin esto un <script> suyo correría en el panel de Raymond.
        fecha = html.escape(str(m["received_at"] or ""))
        mensaje = html.escape(str(m["mensaje"] or ""))
        estado = html.escape(str(m["estado"] or ""))
        rows += f"""
        <tr>
          <td class="fecha">{fecha}</td>
          <td class="mensaje">{mensaje}</td>
          <td><span class="badge" style="background:{color}">{estado}</span></td>
        </tr>"""

    filas_contenido = render_contenido(piezas or [], interactivo=interactivo)
    barra_estado = _render_barra_estado(estado_motor, interactivo=interactivo)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>El Socio — Panel de Control</title>
<style>
  :root{{ --ink:#0a0a0a; --card:#151517; --red:#9c1c2e; --muted:#9aa3b2; --text:#eef1f6; --border:#262b35; }}
  *{{ box-sizing:border-box; }}
  body{{
    margin:0; background:var(--ink); color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Helvetica,Arial,sans-serif;
    padding:36px 20px;
  }}
  .wrap{{ max-width:920px; margin:0 auto; }}
  h1{{ font-size:22px; margin:0 0 4px; }}
  .sub{{ color:var(--muted); font-size:13px; margin-bottom:22px; }}
  .notice{{ background:#1e293b; border:1px solid #334155; padding:12px 16px; border-radius:10px; margin-bottom:18px; font-size:13.5px; }}
  .status-card{{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px 18px; margin-bottom:28px; }}
  .status-top{{ display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; }}
  .kpi{{ font-size:13px; color:var(--muted); margin-left:14px; }}
  .kpi strong{{ color:var(--text); }}
  .chips{{ margin-top:12px; display:flex; gap:10px; flex-wrap:wrap; }}
  .chip{{ font-size:12px; padding:4px 10px; border-radius:8px; border:1px solid var(--border); color:var(--muted); }}
  .chip strong{{ color:var(--text); }}
  .table-wrap{{ overflow-x:auto; border-radius:12px; border:1px solid var(--border); }}
  table{{ width:100%; min-width:560px; border-collapse:collapse; background:var(--card); }}
  th{{ text-align:left; font-size:12px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); padding:14px 16px; border-bottom:1px solid var(--border); }}
  td{{ padding:14px 16px; border-bottom:1px solid var(--border); vertical-align:top; font-size:14px; }}
  tr:last-child td{{ border-bottom:none; }}
  .fecha{{ color:var(--muted); white-space:nowrap; font-size:12.5px; }}
  .mensaje{{ line-height:1.5; }}
  .gancho-txt{{ font-weight:700; font-size:15px; margin-bottom:4px; }}
  .meta-txt{{ color:var(--muted); font-size:12.5px; margin-top:4px; white-space:pre-line; }}
  .err-txt{{ color:#f87171; font-size:12px; margin-top:6px; }}
  .media-box{{ margin-top:10px; }}
  .media-box video, .media-box img{{ max-width:220px; max-height:390px; border-radius:10px; border:1px solid var(--border); display:block; background:#000; }}
  .btn-row{{ margin-top:10px; display:flex; gap:8px; flex-wrap:wrap; }}
  .inline-f{{ display:inline; margin:0; }}
  .btn{{ border:0; border-radius:8px; padding:7px 12px; font-size:12px; font-weight:700; cursor:pointer; color:#fff; }}
  .btn.pri{{ background:var(--red); }}
  .btn.sec{{ background:#262b35; }}
  .btn.mut{{ background:#3a2428; color:#fca5a5; }}
  .badge{{ color:#fff; font-size:11px; padding:4px 10px; border-radius:999px; text-transform:uppercase; letter-spacing:.04em; display:inline-block; }}
  .empty{{ color:var(--muted); text-align:center; padding:40px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>El Socio — Centro de Control</h1>
  <div class="sub">Panel privado en tu WiFi local — cero secretos expuestos.</div>
  {barra_estado}

  <h1>Mensajes de la landing</h1>
  <div class="sub"> Prospectos que escribieron directo desde tu web.</div>
  <div class="table-wrap">
    <table>
      <tr><th>Fecha</th><th>Mensaje</th><th>Estado</th></tr>
      {rows}
    </table>
  </div>

  <h1 style="margin-top:44px">Cola de contenido</h1>
  <div class="sub">Piezas de Instagram: borrador → aprobado → generado → publicado.</div>
  <div class="table-wrap">
    <table>
      <tr><th>#</th><th>Gancho y Preview</th><th>Tipo</th><th>Estado</th></tr>
      {filas_contenido}
    </table>
  </div>
</div>
</body>
</html>"""


def construir_estado_motor(aviso: str = "") -> dict[str, object]:
    """Arma el resumen seguro del motor sin exponer jamás una sola clave."""
    import autopilot_dispatcher  # noqa: PLC0415
    import ig_publisher  # noqa: PLC0415
    import sales_agent  # noqa: PLC0415

    cfg = autopilot_dispatcher.load_env_file()
    conf_ventas = sales_agent.leer_configuracion(cfg)
    est_ig = ig_publisher.estado_ig(cfg)

    correos_hoy = database.agent_emails_queued_today() if database.DB_PATH.exists() else 0
    gasto_hoy = database.agent_cost_today_usd() if database.DB_PATH.exists() else 0.0
    return {
        "auto_publish": est_ig["auto_publish"],
        "correos_hoy": f"{correos_hoy}/{conf_ventas['max_emails']}",
        "gasto_usd": f"${gasto_hoy:.3f} / ${conf_ventas['max_usd']:.2f}",
        "posts_ig_hoy": f"{est_ig['publicados_hoy']}/{est_ig['max_daily_posts']}",
        "gmail_ok": bool(cfg.get("SMTP_USER") and cfg.get("SMTP_PASS")),
        "anthropic_ok": bool(conf_ventas["tiene_api_key"]),
        "ig_ok": bool(est_ig["credenciales_listas"]),
        "ig_username": est_ig.get("username", ""),
        "aviso": aviso,
    }


def regenerate() -> Path:
    """Regenera el HTML estático del panel con los datos actuales (sin abrir navegador)."""
    database.init_db()
    messages = database.list_landing_messages(limit=200)
    piezas = database.list_content(limit=100)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        render(messages, piezas, estado_motor=construir_estado_motor(), interactivo=False),
        encoding="utf-8",
    )
    return OUT_PATH


def main() -> None:
    out_path = regenerate()
    subprocess.run(["open", str(out_path)])
    print(f"Panel generado: {out_path}")


if __name__ == "__main__":
    main()

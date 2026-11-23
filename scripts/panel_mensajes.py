#!/usr/bin/env python3
"""Genera un panel local (HTML) con los mensajes recibidos por la landing y lo abre.

Uso: python3 scripts/panel_mensajes.py
Nunca se sube a Git ni se publica — es solo para ver en tu Mac.
"""

from __future__ import annotations

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


def render(messages: list[dict]) -> str:
    rows = ""
    if not messages:
        rows = '<tr><td colspan="3" class="empty">Todavía no ha llegado ningún mensaje.</td></tr>'
    for m in messages:
        color = ESTADO_COLOR.get(m["estado"], "#9c1c2e")
        rows += f"""
        <tr>
          <td class="fecha">{m['received_at']}</td>
          <td class="mensaje">{m['mensaje']}</td>
          <td><span class="badge" style="background:{color}">{m['estado']}</span></td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>El Socio — Panel de mensajes</title>
<style>
  :root{{ --ink:#0a0a0a; --card:#151517; --red:#9c1c2e; --muted:#9aa3b2; --text:#eef1f6; --border:#262b35; }}
  *{{ box-sizing:border-box; }}
  body{{
    margin:0; background:var(--ink); color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Helvetica,Arial,sans-serif;
    padding:40px 24px;
  }}
  .wrap{{ max-width:860px; margin:0 auto; }}
  h1{{ font-size:22px; margin:0 0 4px; }}
  .sub{{ color:var(--muted); font-size:13px; margin-bottom:28px; }}
  .table-wrap{{ overflow-x:auto; border-radius:12px; }}
  table{{ width:100%; min-width:560px; border-collapse:collapse; background:var(--card); }}
  th{{ text-align:left; font-size:12px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); padding:14px 16px; border-bottom:1px solid var(--border); }}
  td{{ padding:14px 16px; border-bottom:1px solid var(--border); vertical-align:top; font-size:14px; }}
  tr:last-child td{{ border-bottom:none; }}
  .fecha{{ color:var(--muted); white-space:nowrap; font-size:12.5px; }}
  .mensaje{{ line-height:1.5; }}
  .badge{{ color:#fff; font-size:11px; padding:4px 10px; border-radius:999px; text-transform:uppercase; letter-spacing:.04em; }}
  .empty{{ color:var(--muted); text-align:center; padding:40px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Mensajes de la landing</h1>
  <div class="sub">Panel local de El Socio — no es público, solo para ti.</div>
  <div class="table-wrap">
    <table>
      <tr><th>Fecha</th><th>Mensaje</th><th>Estado</th></tr>
      {rows}
    </table>
  </div>
</div>
</body>
</html>"""


def regenerate() -> Path:
    """Regenera el HTML del panel con los mensajes actuales. No abre nada (para uso automático)."""
    database.init_db()
    messages = database.list_landing_messages(limit=200)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(render(messages), encoding="utf-8")
    return OUT_PATH


def main() -> None:
    out_path = regenerate()
    subprocess.run(["open", str(out_path)])
    print(f"Panel generado: {out_path}")


if __name__ == "__main__":
    main()

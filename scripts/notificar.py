#!/usr/bin/env python3
"""Notificaciones push al celular cuando algo real falla — vía ntfy.sh (gratis, sin cuenta).

Cómo activarlas (una sola vez):
  1. Instala la app "ntfy" en tu iPhone/Android (gratis).
  2. Elige un nombre de canal único y secreto, ej: `elsocio-raymond-9f2k` (cualquiera que
     adivine el nombre podría ver tus avisos — no uses algo obvio como "elsocio").
  3. Dentro de la app, toca "+" y suscríbete a ese mismo nombre.
  4. Pon `NTFY_TOPIC=elsocio-raymond-9f2k` en tu `.env`.
Listo — sin esa línea en `.env`, esta función no hace nada (ni un solo intento de red).
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


def _leer_topic() -> str:
    """Lee NTFY_TOPIC directo de `.env` (sin depender de autopilot_dispatcher ni de deps)."""
    import os

    if os.environ.get("NTFY_TOPIC"):
        return os.environ["NTFY_TOPIC"].strip()
    if not ENV_FILE.exists():
        return ""
    for linea in ENV_FILE.read_text(encoding="utf-8").splitlines():
        limpia = linea.strip()
        if limpia.startswith("NTFY_TOPIC=") :
            return limpia.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def notificar_fallo(mensaje: str, *, titulo: str = "El Socio — falló algo") -> bool:
    """Manda un push al celular. Si no hay NTFY_TOPIC configurado, no hace nada (y no falla)."""
    topic = _leer_topic()
    if not topic:
        return False
    try:
        datos = (mensaje or "").strip()[:500].encode("utf-8")
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}",
            data=datos,
            method="POST",
            headers={
                "Title": titulo.encode("ascii", "ignore").decode("ascii") or "El Socio",
                "Priority": "high",
                "Tags": "warning",
            },
        )
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception:
        return False  # una notificación caída nunca debe tumbar el flujo real del agente


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Manda una notificación push de prueba.")
    parser.add_argument("mensaje", nargs="*", default=["Prueba de notificación de El Socio."])
    args = parser.parse_args(argv)
    ok = notificar_fallo(" ".join(args.mensaje), titulo="El Socio — prueba")
    print("Enviada." if ok else "No se envió: falta NTFY_TOPIC en .env o falló la red.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

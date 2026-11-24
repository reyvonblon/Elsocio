#!/usr/bin/env python3
"""Configurador de demonios `launchd` en macOS Monterey para autonomía 24/7.

Deja instalados dos servicios ligeros de usuario (`~/Library/LaunchAgents`):
  1. `com.elsocio.cerebro`     — corre `scripts/socio_cerebro.py` cada 15 minutos.
  2. `com.elsocio.panelserver` — mantiene vivo `scripts/panel_server.py` en el puerto 8787.

Con `--dry-run` muestra los plists XML exactos sin escribir ni tocar `launchctl`.
"""

from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
from pathlib import Path

import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = PROJECT_ROOT / "data"


def _construir_path_seguro() -> str:
    base = ["/usr/local/bin", "/opt/homebrew/bin", "/opt/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    for p in (os.environ.get("PATH") or "").split(":"):
        p = p.strip()
        if p and p not in base:
            base.insert(0, p)
    return ":".join(base)


def construir_plists() -> dict[str, dict]:
    py = sys.executable
    path_env = _construir_path_seguro()
    return {
        "com.elsocio.cerebro": {
            "Label": "com.elsocio.cerebro",
            "ProgramArguments": [py, str(PROJECT_ROOT / "scripts" / "socio_cerebro.py")],
            "WorkingDirectory": str(PROJECT_ROOT),
            "StartInterval": 900,  # cada 15 minutos
            "RunAtLoad": True,
            "EnvironmentVariables": {"PATH": path_env},
            "StandardOutPath": str(LOG_DIR / "cerebro.log"),
            "StandardErrorPath": str(LOG_DIR / "cerebro.err.log"),
        },
        "com.elsocio.panelserver": {
            "Label": "com.elsocio.panelserver",
            "ProgramArguments": [
                py, str(PROJECT_ROOT / "scripts" / "panel_server.py"),
                "--host", "0.0.0.0", "--port", "8787",
            ],
            "WorkingDirectory": str(PROJECT_ROOT),
            "KeepAlive": True,
            "RunAtLoad": True,
            "EnvironmentVariables": {"PATH": path_env},
            "StandardOutPath": str(LOG_DIR / "panelserver.log"),
            "StandardErrorPath": str(LOG_DIR / "panelserver.err.log"),
        },
    }


def instalar(*, dry_run: bool = False) -> dict[str, object]:
    plists = construir_plists()
    if dry_run:
        return {
            "dry_run": True,
            "agentes": {
                nombre: plistlib.dumps(datos).decode("utf-8")
                for nombre, datos in plists.items()
            },
        }

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    instalados: list[str] = []

    # Desactivar el antiguo `com.elsocio.landing` si existía para no duplicar lecturas IMAP.
    viejo = LAUNCH_AGENTS_DIR / "com.elsocio.landing.plist"
    if viejo.exists():
        subprocess.run(["launchctl", "unload", str(viejo)], check=False, capture_output=True)

    for nombre, datos in plists.items():
        ruta = LAUNCH_AGENTS_DIR / f"{nombre}.plist"
        ruta.write_bytes(plistlib.dumps(datos))
        subprocess.run(["launchctl", "unload", str(ruta)], check=False, capture_output=True)
        subprocess.run(["launchctl", "load", "-w", str(ruta)], check=False, capture_output=True)
        instalados.append(str(ruta))
    return {"ok": True, "instalados": instalados}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Instala el piloto automático launchd de El Socio.")
    parser.add_argument("--dry-run", action="store_true", help="Muestra los plists sin instalar.")
    args = parser.parse_args(argv)
    print(json.dumps(instalar(dry_run=args.dry_run), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

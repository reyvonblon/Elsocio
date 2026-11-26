#!/usr/bin/env python3
"""Guarda un token nuevo de Instagram en `.env`, pero solo si Meta confirma que sirve.

Raymond pega el token aquí (no se ve mientras lo escribe y no queda en el historial del
terminal). El script le pregunta a Meta tres cosas antes de guardar nada:

  1. ¿El token está vivo?
  2. ¿Trae el permiso `instagram_content_publish`?
  3. ¿Ese permiso cubre la cuenta de El Socio, o quedó apuntando a otra cuenta?

Si cualquiera falla, NO toca el `.env` y dice exactamente qué pasó. Así no se repite lo del
2026-11-26: un token guardado que parecía bueno y que Meta rechazaba al momento de publicar.

Uso:
    python3 scripts/poner_token_ig.py
"""
from __future__ import annotations

import getpass
import json
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ENV = RAIZ / ".env"
GRAPH = "https://graph.facebook.com/v21.0"


def _leer_env() -> dict[str, str]:
    cfg: dict[str, str] = {}
    if ENV.exists():
        for linea in ENV.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if "=" in linea and not linea.startswith("#"):
                clave, valor = linea.split("=", 1)
                cfg[clave.strip()] = valor.strip()
    return cfg


def _graph(path: str, params: dict[str, str], token: str) -> dict:
    url = f"{GRAPH}/{path}?" + urllib.parse.urlencode({**params, "access_token": token})
    try:
        with urllib.request.urlopen(url, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        try:
            return {"_error": json.loads(err.read().decode("utf-8")).get("error", {})}
        except Exception:
            return {"_error": {"message": f"HTTP {err.code}"}}
    except Exception as exc:  # red caída, DNS, etc.
        return {"_error": {"message": str(exc)}}


def _escribir_token(token: str, user_id: str) -> None:
    """Reemplaza IG_ACCESS_TOKEN (y IG_USER_ID si hace falta) dejando copia de seguridad."""
    shutil.copy(ENV, ENV.with_suffix(".env.bak"))
    lineas = ENV.read_text(encoding="utf-8").splitlines()
    puesto_tok = puesto_uid = False
    for i, linea in enumerate(lineas):
        if linea.startswith("IG_ACCESS_TOKEN="):
            lineas[i] = f"IG_ACCESS_TOKEN={token}"
            puesto_tok = True
        elif linea.startswith("IG_USER_ID=") and user_id:
            lineas[i] = f"IG_USER_ID={user_id}"
            puesto_uid = True
    if not puesto_tok:
        lineas.append(f"IG_ACCESS_TOKEN={token}")
    if user_id and not puesto_uid:
        lineas.append(f"IG_USER_ID={user_id}")
    ENV.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main() -> int:
    if not ENV.exists():
        print("No encuentro el archivo .env en la raíz del proyecto.")
        return 1
    cfg = _leer_env()
    esperado = (cfg.get("IG_USER_ID") or "").strip()
    usuario = (cfg.get("IG_USERNAME") or "la cuenta de El Socio").strip()

    print(f"Pega el token nuevo de Instagram para {usuario}.")
    print("(No se va a ver mientras lo pegas. Enter cuando termines.)\n")
    token = getpass.getpass("Token: ").strip()
    if not token:
        print("\nNo pegaste nada. No toqué el .env.")
        return 1

    print("\nPreguntándole a Meta si este token sirve...\n")
    datos = _graph("debug_token", {"input_token": token}, token)
    if "_error" in datos:
        msg = datos["_error"].get("message", "")
        print("Meta rechazó el token:", msg)
        if "on behalf of user" in msg:
            print("\n  -> Esa cuenta de Facebook todavía no tiene rol ACEPTADO en la app 'El Socio'.")
            print("     Entra a developers.facebook.com CON ESA CUENTA y acepta la invitación.")
        print("\nNo toqué el .env.")
        return 1

    d = datos.get("data", {})
    if not d.get("is_valid"):
        print("El token no es válido (caducado o revocado). No toqué el .env.")
        return 1

    autorizadas: list[str] = []
    for g in d.get("granular_scopes") or []:
        if g.get("scope") == "instagram_content_publish":
            autorizadas = [str(x) for x in (g.get("target_ids") or [])]

    if "instagram_content_publish" not in (d.get("scopes") or []):
        print("El token NO trae el permiso para publicar (instagram_content_publish).")
        print("Hay que generarlo otra vez marcando ese permiso. No toqué el .env.")
        return 1

    if not autorizadas:
        print("El token trae el permiso de publicar, pero Meta no reporta ninguna cuenta de")
        print("Instagram asociada. Revisa que la cuenta sea profesional y esté conectada a la")
        print("página de Facebook. No toqué el .env.")
        return 1

    destino = esperado if esperado in autorizadas else ""
    if not destino:
        print("Este token SÍ sirve, pero publica en otra cuenta de Instagram:")
        for x in autorizadas:
            info = _graph(x, {"fields": "username"}, token)
            print(f"   - {x}  ({info.get('username', '¿?')})")
        print(f"\nEl .env apunta a {esperado or '(vacío)'}, que no está en esa lista.")
        if len(autorizadas) == 1:
            unica = autorizadas[0]
            info = _graph(unica, {"fields": "username"}, token)
            resp = input(f"\n¿Uso {info.get('username', unica)} ({unica}) como cuenta de El Socio? [s/N] ")
            if resp.strip().lower() in {"s", "si", "sí"}:
                destino = unica
        if not destino:
            print("\nNo toqué el .env.")
            return 1

    info = _graph(destino, {"fields": "username,media_count"}, token)
    _escribir_token(token, destino)
    print("\nListo. Token guardado y verificado contra Meta.")
    print(f"   cuenta      : @{info.get('username', '¿?')}  ({destino})")
    print(f"   publicadas  : {info.get('media_count', '¿?')}")
    print("   copia previa: .env.bak")
    print("\nAhora El Socio ya puede publicar. Dime y suelto el reel y las historias.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

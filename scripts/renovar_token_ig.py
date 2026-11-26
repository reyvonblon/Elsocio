#!/usr/bin/env python3
"""Cambia un token corto de Meta (EAA.../EAG..., Facebook Login) por uno que no vence.

El renovador que ya existía (`ig_publisher.renovar_token_ig_si_toca`) solo sirve para tokens
`IGA...` de Instagram Login. El token de esta cuenta es `EAGh...` (Facebook Login), así que
nunca le aplicó: por eso venció sin que nadie lo renovara.

La cadena correcta tiene TRES pasos, no uno:

  1. token de usuario CORTO   (1-2 h)   ← lo generas tú en la consola de Meta
  2. token de usuario LARGO   (60 días) ← `grant_type=fb_exchange_token`
  3. token de PÁGINA          (no vence) ← derivado del largo, vía `/me/accounts`

El paso 3 es el premio: un token de página derivado de un token de usuario de larga vida
NO tiene fecha de vencimiento. Se publica con ese, no con el de usuario.

    python3 scripts/renovar_token_ig.py --token "EAA...el-corto-recien-generado"
    python3 scripts/renovar_token_ig.py --token "EAA..." --dry-run   # no guarda nada

App ID y App Secret se leen de `.env` (`IG_APP_ID`, `IG_APP_SECRET`). El token nunca se
imprime: solo su prefijo, su largo y su vencimiento.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import database
import ig_publisher

GRAPH = "https://graph.facebook.com/v21.0"


def _pista(token: str) -> str:
    """Lo único que se puede mostrar de un token: prefijo y largo."""
    t = (token or "").strip()
    return f"{t[:4]}…({len(t)} car.)" if t else "(vacío)"


def _vencimiento(token: str, app_id: str, app_secret: str) -> dict:
    """`debug_token` oficial: `expires_at == 0` significa que NO vence."""
    datos = ig_publisher._graph_get(
        f"{GRAPH}/debug_token", {"input_token": token}, f"{app_id}|{app_secret}",
    ).get("data", {})
    exp = int(datos.get("expires_at") or 0)
    return {
        "tipo": str(datos.get("type") or ""),
        "vence_en": "nunca" if exp == 0 else datetime.fromtimestamp(exp, timezone.utc).isoformat(),
        "dias": None if exp == 0 else round((exp - datetime.now(timezone.utc).timestamp()) / 86400, 1),
        "permisos": sorted(datos.get("scopes") or []),
        "valido": bool(datos.get("is_valid")),
    }


def intercambiar_por_largo(token_corto: str, app_id: str, app_secret: str) -> str:
    """Paso 2: corto (1-2 h) → largo (60 días)."""
    datos = ig_publisher._graph_get(
        f"{GRAPH}/oauth/access_token",
        {"grant_type": "fb_exchange_token", "client_id": app_id,
         "client_secret": app_secret, "fb_exchange_token": token_corto},
        token_corto,
    )
    largo = str(datos.get("access_token") or "").strip()
    if not largo:
        raise ig_publisher.ErrorIG("Meta no devolvió `access_token` en el intercambio.")
    return largo


def token_de_pagina(token_largo: str, ig_user_id: str) -> tuple[str, dict]:
    """Paso 3: el token de la página dueña de ESA cuenta de Instagram. No vence.

    Se elige por `instagram_business_account.id`, no por nombre: si hay varias páginas,
    escoger por nombre es como adivinar.
    """
    datos = ig_publisher._graph_get(
        f"{GRAPH}/me/accounts",
        {"fields": "id,name,access_token,instagram_business_account{id,username}"},
        token_largo,
    )
    paginas = datos.get("data") or []
    if not paginas:
        raise ig_publisher.ErrorIG(
            "El token no administra ninguna página de Facebook. Falta el permiso "
            "`pages_show_list` o la cuenta de Instagram no está conectada a una página.")
    for pag in paginas:
        cuenta = pag.get("instagram_business_account") or {}
        if ig_user_id and str(cuenta.get("id") or "") == str(ig_user_id):
            return str(pag.get("access_token") or ""), {
                "pagina": pag.get("name"), "ig_username": cuenta.get("username")}
    disponibles = [
        f"{p.get('name')} → IG {((p.get('instagram_business_account') or {}).get('id')) or 'sin conectar'}"
        for p in paginas
    ]
    raise ig_publisher.ErrorIG(
        f"Ninguna página administra la cuenta IG_USER_ID={ig_user_id}. Páginas vistas: "
        + " | ".join(disponibles))


def renovar(token_corto: str, *, dry_run: bool = False) -> dict:
    cfg = ig_publisher.cargar_config_ig()
    app_id = (cfg.get("IG_APP_ID") or "").strip()
    app_secret = (cfg.get("IG_APP_SECRET") or "").strip()
    ig_user_id = (cfg.get("IG_USER_ID") or "").strip()
    if not app_id or not app_secret:
        return {"ok": False, "paso": 0,
                "error": "Faltan IG_APP_ID e IG_APP_SECRET en `.env` (los da la consola de Meta, "
                         "en Configuración de la app → Básica)."}
    if not token_corto:
        return {"ok": False, "paso": 0, "error": "Falta --token con el token corto recién generado."}
    if token_corto.startswith("IGA"):
        return {"ok": False, "paso": 0,
                "error": "Ese es un token de Instagram Login (IGA...). Esa ruta la renueva "
                         "`ig_publisher.renovar_token_ig_si_toca`, no este script."}

    pasos = []
    try:
        estado_corto = _vencimiento(token_corto, app_id, app_secret)
        if not estado_corto["valido"]:
            return {"ok": False, "paso": 1,
                    "error": "El token corto ya está vencido o es inválido. Genera uno nuevo en la "
                             "consola de Meta y córrelo de una: duran 1-2 horas.",
                    "detalle": estado_corto}
        pasos.append({"paso": 1, "que": "token corto recibido", "token": _pista(token_corto),
                      "vence_en": estado_corto["vence_en"], "permisos": estado_corto["permisos"]})

        largo = intercambiar_por_largo(token_corto, app_id, app_secret)
        estado_largo = _vencimiento(largo, app_id, app_secret)
        pasos.append({"paso": 2, "que": "token de usuario de larga vida",
                      "token": _pista(largo), "vence_en": estado_largo["vence_en"],
                      "dias": estado_largo["dias"]})

        pagina, info = token_de_pagina(largo, ig_user_id)
        estado_pagina = _vencimiento(pagina, app_id, app_secret)
        pasos.append({"paso": 3, "que": "token de página", "token": _pista(pagina),
                      "vence_en": estado_pagina["vence_en"], **info})
    except ig_publisher.ErrorIG as exc:
        return {"ok": False, "paso": len(pasos) + 1, "error": str(exc), "pasos": pasos}

    # Igual que el resto del motor: no se guarda nada que Meta no haya confirmado que sirve.
    prueba = ig_publisher.verificar_acceso_ig({**cfg, "IG_ACCESS_TOKEN": pagina})
    if not prueba.get("puede_publicar"):
        return {"ok": False, "paso": 4, "pasos": pasos,
                "error": "Meta no confirma que el token nuevo pueda publicar; no se guardó nada.",
                "detalle": prueba}

    if dry_run:
        return {"ok": True, "dry_run": True, "pasos": pasos, "guardado": False,
                "verificado": True, "vence_en": estado_pagina["vence_en"]}

    database.update_settings({
        "ig_access_token": pagina,
        "ig_token_refreshed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ig_token_tipo": "pagina",
        "ig_token_vence": estado_pagina["vence_en"],
    })
    return {"ok": True, "pasos": pasos, "guardado": True, "verificado": True,
            "vence_en": estado_pagina["vence_en"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Cambia el token corto de Meta por un token de página que no vence.")
    ap.add_argument("--token", default="", help="El token CORTO recién generado en la consola de Meta.")
    ap.add_argument("--dry-run", action="store_true", help="Verifica contra Meta pero no guarda.")
    args = ap.parse_args(argv)
    database.init_db()
    res = renovar(args.token.strip(), dry_run=args.dry_run)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res.get("ok"):
        print("\nListo. El motor ya usa el token nuevo (vive en `settings`, no en `.env`).",
              file=sys.stderr)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

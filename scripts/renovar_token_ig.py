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
import notificar

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


# ------------------------------------------------------------------ el vigilante

# Esto existe porque el token ya se murió en silencio varias veces y Raymond se enteraba
# tarde, cuando el motor llevaba horas sin publicar. El renovador viejo
# (`ig_publisher.renovar_token_ig_si_toca`) solo cubre tokens `IGA...`, así que para un token
# `EAG...` de Facebook Login no hacía NADA y además no avisaba: daba falsa tranquilidad.
#
# El vigilante corre en cada latido (cada 15 min) y hace tres cosas:
#   - si el token está muerto  -> suena el celular, no se descubre por casualidad
#   - si es de usuario y le quedan pocos días -> lo cambia SOLO por uno de página (no vence)
#   - si ya es de página sin vencimiento -> no hace nada y lo deja anotado
DIAS_ALERTA_VENCIMIENTO = 10


def estado_token(cfg: dict[str, str] | None = None) -> dict:
    """Qué token hay, si sirve y cuándo vence. Nunca expone el token."""
    cfg = ig_publisher.cargar_config_ig() if cfg is None else cfg
    token = (cfg.get("IG_ACCESS_TOKEN") or "").strip()
    app_id = (cfg.get("IG_APP_ID") or "").strip()
    app_secret = (cfg.get("IG_APP_SECRET") or "").strip()
    if not token:
        return {"hay_token": False, "valido": False, "motivo": "no hay IG_ACCESS_TOKEN"}
    if not app_id or not app_secret:
        # Sin credenciales de app no se puede preguntar el vencimiento: al menos se comprueba
        # si sirve. Mejor saber "sirve/no sirve" que no saber nada.
        prueba = ig_publisher.verificar_acceso_ig(cfg)
        return {"hay_token": True, "valido": bool(prueba.get("puede_publicar")),
                "vence_en": "desconocido", "dias": None,
                "motivo": "sin IG_APP_ID/IG_APP_SECRET no se puede leer el vencimiento"}
    try:
        est = _vencimiento(token, app_id, app_secret)
    except ig_publisher.ErrorIG as exc:
        return {"hay_token": True, "valido": False, "motivo": str(exc)}
    return {"hay_token": True, **est}


def vigilar_token(cfg: dict[str, str] | None = None, *, avisar: bool = True) -> dict:
    """Revisa el token en cada latido. Avisa si murió y lo mejora solo si le queda poco."""
    cfg = ig_publisher.cargar_config_ig() if cfg is None else cfg
    est = estado_token(cfg)
    sello = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not est.get("valido"):
        if avisar:
            notificar.notificar_fallo(
                f"El token de Instagram no sirve ({est.get('motivo', 'rechazado por Meta')}). "
                "El motor no puede publicar hasta renovarlo.",
                titulo="El Socio — token de Instagram caído")
        database.update_settings({"ig_token_estado": "invalido", "ig_token_revisado_at": sello})
        return {"ok": False, "accion": "alerta", "estado": est}

    dias = est.get("dias")
    if dias is None:  # expires_at == 0: no vence. Es el estado bueno.
        database.update_settings({"ig_token_estado": "no_vence", "ig_token_vence": "nunca",
                                  "ig_token_revisado_at": sello})
        return {"ok": True, "accion": "ninguna", "estado": est}

    if dias > DIAS_ALERTA_VENCIMIENTO:
        database.update_settings({"ig_token_estado": "vigente",
                                  "ig_token_vence": str(est.get("vence_en")),
                                  "ig_token_revisado_at": sello})
        return {"ok": True, "accion": "ninguna", "estado": est}

    # Le queda poco y TODAVÍA sirve: es la única ventana para mejorarlo sin intervención.
    # Un token de página derivado de este no vence, así que esto se hace una sola vez.
    try:
        pagina, info = token_de_pagina((cfg.get("IG_ACCESS_TOKEN") or "").strip(),
                                       (cfg.get("IG_USER_ID") or "").strip())
        prueba = ig_publisher.verificar_acceso_ig({**cfg, "IG_ACCESS_TOKEN": pagina})
        if not prueba.get("puede_publicar"):
            raise ig_publisher.ErrorIG("Meta no confirma el token de página derivado.")
    except ig_publisher.ErrorIG as exc:
        if avisar:
            notificar.notificar_fallo(
                f"Al token de Instagram le quedan {dias} días y no se pudo cambiar solo "
                f"por uno de página ({exc}). Hay que renovarlo a mano antes de que venza.",
                titulo="El Socio — token de Instagram por vencer")
        database.update_settings({"ig_token_estado": "por_vencer",
                                  "ig_token_vence": str(est.get("vence_en")),
                                  "ig_token_revisado_at": sello})
        return {"ok": False, "accion": "alerta_vencimiento", "estado": est, "error": str(exc)}

    database.update_settings({"ig_access_token": pagina, "ig_token_tipo": "pagina",
                              "ig_token_estado": "no_vence", "ig_token_vence": "nunca",
                              "ig_token_refreshed_at": sello, "ig_token_revisado_at": sello})
    return {"ok": True, "accion": "cambiado_a_token_de_pagina", "pagina": info.get("pagina")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Cambia el token corto de Meta por un token de página que no vence.")
    ap.add_argument("--token", default="", help="El token CORTO recién generado en la consola de Meta.")
    ap.add_argument("--dry-run", action="store_true", help="Verifica contra Meta pero no guarda.")
    ap.add_argument("--estado", action="store_true",
                    help="Solo dice qué token hay y cuándo vence. No cambia nada.")
    args = ap.parse_args(argv)
    database.init_db()
    if args.estado:
        print(json.dumps(estado_token(), ensure_ascii=False, indent=2))
        return 0
    res = renovar(args.token.strip(), dry_run=args.dry_run)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res.get("ok"):
        print("\nListo. El motor ya usa el token nuevo (vive en `settings`, no en `.env`).",
              file=sys.stderr)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

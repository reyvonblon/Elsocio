#!/usr/bin/env python3
"""Captura las métricas reales de los reels publicados y las guarda en `content_metrics`.

Paso 1-2 del ciclo de `contexto/ciclo-insights.md`. Cero datos inventados: lo que Meta no
devuelve queda en cero o en NULL, nunca estimado.

Dos ventanas por pieza, no una: un reel a las 2 h no dice nada, a las 24 h da la señal
temprana y a los 7 días ya está definido.

  python3 scripts/insights_collector.py            # captura lo que toque y resume
  python3 scripts/insights_collector.py --dry-run  # no escribe en la BD

Solo captura `tipo='video'`: la historia muere a las 24 h y en cuenta nueva no tiene muestra,
así que no vota en las decisiones del motor (§2 del diseño).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import database
import ig_publisher

# Métricas de reel que pedimos a Meta. Se piden TODAS de una; si Meta rechaza alguna (cambian
# de nombre entre versiones de la API), se reintenta con el set mínimo que siempre ha existido.
METRICAS_REEL = (
    "reach", "saved", "shares", "likes", "comments", "views", "ig_reels_avg_watch_time",
)
METRICAS_REEL_MINIMAS = ("reach", "saved", "shares", "likes", "comments")

VENTANAS = (("24h", 24.0), ("7d", 168.0))

# Meta responde "does not exist" tanto si la pieza nunca se publico como si se ARCHIVO:
# una media archivada sale de la API y su ID deja de resolver. En esta cuenta la causa
# normal es archivar (Raymond lo hace el mismo dia), no un fallo de publicacion.
# Se marca para no reintentarla en cada latido; su dato esta perdido sin recuperacion.
MARCA_SIN_MEDIO = "media_archivada_o_borrada"


# ------------------------------------------------------------------ clasificar comentarios

# El comentario de emoji o de una palabra no es señal de intención: se cuenta aparte y pesa 0.1
# en el puntaje (§3). Clasificar ANTES de puntuar es lo que impide que el motor aprenda a pedir
# comentarios en vez de merecerlos.
_RE_NO_PALABRA = re.compile(r"[^\w\sáéíóúñüÁÉÍÓÚÑÜ]", re.UNICODE)


def comentario_es_real(texto: str) -> bool:
    """Real = dice algo. Emoji, una palabra o '🔥🔥🔥' no cuentan como señal."""
    limpio = _RE_NO_PALABRA.sub(" ", str(texto or ""))
    limpio = "".join(c for c in limpio if not unicodedata.category(c).startswith("So"))
    palabras = [p for p in limpio.split() if len(p) > 1]
    return len(palabras) >= 3 or len(" ".join(palabras)) >= 12


def clasificar_comentarios(textos: list[str]) -> tuple[int, int]:
    reales = sum(1 for t in textos if comentario_es_real(t))
    return reales, len(textos) - reales


# ------------------------------------------------------------------ duración real del archivo

def duracion_de(archivo: str) -> float:
    """Duración en segundos vía ffprobe. 0.0 si el archivo ya no está (la retención queda NULL)."""
    ruta = Path(archivo or "")
    if not ruta.is_absolute():
        ruta = Path(__file__).resolve().parent.parent / ruta
    if not ruta.exists():
        return 0.0
    try:
        salida = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(ruta)],
            capture_output=True, text=True, timeout=20, check=True,
            env={"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"},
        ).stdout.strip()
        return float(salida) if salida else 0.0
    except Exception:
        return 0.0


# ------------------------------------------------------------------ Graph API

def _valores(respuesta: dict) -> dict[str, int]:
    """Aplana la respuesta de `/insights` ({'data':[{'name':..,'values':[{'value':N}]}]})."""
    fuera: dict[str, int] = {}
    for item in respuesta.get("data") or []:
        nombre = str(item.get("name") or "")
        vals = item.get("values") or []
        if not nombre:
            continue
        bruto = (vals[0] or {}).get("value") if vals else item.get("total_value", {}).get("value")
        if isinstance(bruto, (int, float)):
            fuera[nombre] = int(bruto)
    return fuera


def insights_de_media(media_id: str, base: str, token: str) -> dict[str, int]:
    try:
        return _valores(ig_publisher._graph_get(
            f"{base}/{media_id}/insights", {"metric": ",".join(METRICAS_REEL)}, token))
    except ig_publisher.ErrorIG:
        # Una métrica rechazada tumba la petición completa: se reintenta con el set mínimo.
        return _valores(ig_publisher._graph_get(
            f"{base}/{media_id}/insights", {"metric": ",".join(METRICAS_REEL_MINIMAS)}, token))


def comentarios_de_media(media_id: str, base: str, token: str) -> tuple[int, int, str]:
    """(reales, emoji, aviso). Si el token no trae `instagram_manage_comments`, avisa y no inventa."""
    try:
        resp = ig_publisher._graph_get(
            f"{base}/{media_id}/comments", {"fields": "text", "limit": "100"}, token)
    except ig_publisher.ErrorIG as exc:
        return 0, 0, f"comentarios no leídos ({exc})"
    textos = [str((c or {}).get("text") or "") for c in (resp.get("data") or [])]
    reales, emoji = clasificar_comentarios(textos)
    return reales, emoji, ""


def insights_de_cuenta(user_id: str, base: str, token: str) -> dict[str, int]:
    # `profile_views` exige `metric_type=total_value`; `reach` se pide aparte porque con ese
    # parametro cambia de forma. Dos llamadas baratas en vez de una que Meta rechaza entera.
    datos: dict[str, int] = {}
    for metrica, extra in (("profile_views", {"metric_type": "total_value"}), ("reach", {})):
        try:
            datos.update(_valores(ig_publisher._graph_get(
                f"{base}/{user_id}/insights",
                {"metric": metrica, "period": "day", **extra}, token)))
        except ig_publisher.ErrorIG:
            continue
    try:
        perfil = ig_publisher._graph_get(f"{base}/{user_id}", {"fields": "followers_count"}, token)
        datos["followers_count"] = int(perfil.get("followers_count") or 0)
    except ig_publisher.ErrorIG:
        pass
    return datos


# ------------------------------------------------------------------ el recolector

def capturar(*, dry_run: bool = False) -> dict:
    cfg = ig_publisher.cargar_config_ig()
    token = (cfg.get("IG_ACCESS_TOKEN") or "").strip()
    user_id = (cfg.get("IG_USER_ID") or "").strip()
    if not token:
        return {"ok": False, "motivo": "falta IG_ACCESS_TOKEN", "capturadas": []}
    base = ig_publisher._url_base_graph(cfg)

    capturadas, fallos, avisos = [], [], []
    for ventana, horas in VENTANAS:
        for pieza in database.reels_por_capturar(ventana, horas_minimas=horas):
            media_id = str(pieza.get("ig_media_id") or "")
            try:
                m = insights_de_media(media_id, base, token)
            except ig_publisher.ErrorIG as exc:
                # "does not exist" = archivada, borrada, o nunca publicada. Se marca y no
                # se vuelve a pedir: desarchivarla tampoco devuelve el historico.
                if "does not exist" in str(exc) and not dry_run:
                    database.update_content(pieza["id"], error_ig=MARCA_SIN_MEDIO)
                fallos.append({"pieza": pieza["id"], "ventana": ventana, "error": str(exc)})
                continue
            reales, emoji, aviso = comentarios_de_media(media_id, base, token)
            if aviso:
                avisos.append(f"pieza {pieza['id']}: {aviso}")
                # Sin acceso a los textos, el total de Meta se guarda como 'reales' sin clasificar
                # sería mentir sobre la calidad del comentario: se deja en cero y se avisa.
            fila = {
                "pieza_id": pieza["id"], "ventana": ventana,
                "alcance": m.get("reach", 0), "vistas": m.get("views", 0),
                "guardados": m.get("saved", 0), "compartidos": m.get("shares", 0),
                "likes": m.get("likes", 0),
                "comentarios_reales": reales, "comentarios_emoji": emoji,
                "watch_time_ms": m.get("ig_reels_avg_watch_time", 0),
                "duracion_s": duracion_de(str(pieza.get("archivo") or "")),
            }
            if not dry_run:
                database.guardar_metricas(**fila)
            capturadas.append(fila)

    cuenta = {}
    if user_id:
        try:
            c = insights_de_cuenta(user_id, base, token)
            hoy = datetime.now(timezone.utc).date().isoformat()
            cuenta = {"fecha": hoy, "alcance": c.get("reach", 0),
                      "visitas_perfil": c.get("profile_views", 0),
                      "seguidores": c.get("followers_count", 0)}
            if not dry_run:
                database.guardar_metricas_cuenta(**cuenta)
        except ig_publisher.ErrorIG as exc:
            avisos.append(f"métricas de cuenta no leídas ({exc})")

    return {"ok": True, "dry_run": dry_run, "capturadas": capturadas,
            "cuenta": cuenta, "fallos": fallos, "avisos": avisos}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Captura métricas reales de los reels publicados.")
    ap.add_argument("--dry-run", action="store_true", help="No escribe en la BD.")
    args = ap.parse_args(argv)
    database.init_db()
    res = capturar(dry_run=args.dry_run)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

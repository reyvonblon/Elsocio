#!/usr/bin/env python3
"""Publicador autónomo en Instagram vía API OFICIAL de Meta (Instagram Graph API).

PROHIBIDO usar bots, scrapers o clientes privados (riesgo de baneo permanente).
Este módulo usa exclusivamente los endpoints oficiales de Meta (`graph.instagram.com`
o `graph.facebook.com`) con `urllib.request` de Python stdlib (0 USD, 0 SDKs):

  1. Si la pieza es imagen `.png`, la convierte a `.jpg` con `/usr/bin/sips` nativo
     de macOS (Meta rechaza PNG con subcódigo 2207005; solo acepta JPEG).
  2. Obtiene una URL HTTPS pública temporal de auto-borrado en 1h (o usa
     `IG_MEDIA_BASE_URL` si se configuró dominio propio).
  3. Crea el contenedor oficial (`IMAGE`, `REELS`, `STORIES` o `CAROUSEL` con sus láminas hijas), espera a `status_code=FINISHED`
     y publica con `/{IG_USER_ID}/media_publish`.
  4. Guardas duras en código:
     - Revisa `revisar_guarda_precios()` sobre gancho + caption antes de publicar.
     - Tope diario duro (`IG_MAX_DAILY_POSTS`, por defecto 1).
     - Interruptor `ig_auto_publish` (BD `settings` manda sobre `.env`):
       `0` = deja la pieza lista en `generado` esperando aprobación en el panel 8787;
       `1` = publica solo sin intervención humana.
     - Rollback limpio: si Meta falla en cualquier paso, la pieza permanece en
       `generado`, guarda `error_ig` y NO ensucia `RESULTADOS_MERCADO.md`.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import autopilot_dispatcher  # noqa: E402
import content_manager  # noqa: E402
import database  # noqa: E402
import sales_agent  # noqa: E402

GRAPH_VERSION = "v21.0"
LITTERBOX_API = "https://litterbox.catbox.moe/resources/internals/api.php"
MAX_POLLS_META = 24
PAUSA_POLL_SEG = 5.0
TIMEOUT_HTTP_IG = 60
MAX_JPEG_BYTES = 8 * 1024 * 1024  # Límite oficial de Meta para JPEG: 8 MB


class ErrorIG(Exception):
    """Error controlado en la publicación o consulta de Instagram Graph API."""


DIAS_RENOVACION_TOKEN = 25


_CLAVES_IG_AJUSTABLES = (
    "IG_MAX_DAILY_POSTS",
    "IG_DAILY_VIDEOS",
    "IG_DAILY_POSTS",
    "IG_DAILY_STORIES",
    "IG_DAILY_CAROUSELS",
    "IG_MIN_INTERVAL_MINUTES",
)


def cargar_config_ig() -> dict[str, str]:
    """Lee configuración desde `.env` + `settings` local sin exponer jamás el token."""
    cfg = autopilot_dispatcher.load_env_file()
    if database.DB_PATH.exists():
        try:
            ajustes = database.get_settings()
            # Si ya hubo renovación automática, el token renovado en BD es más nuevo que `.env`.
            tok_bd = (ajustes.get("ig_access_token") or "").strip()
            if tok_bd and (ajustes.get("ig_token_refreshed_at") or not (cfg.get("IG_ACCESS_TOKEN") or "").strip()):
                cfg["IG_ACCESS_TOKEN"] = tok_bd
            # El id de la BD es el que el propio token autodescubrió y confirmó contra Meta:
            # si `.env` quedó con el id de una cuenta vieja, publicar contra ella falla ("User
            # access is restricted"). Por eso la BD manda sobre `.env` cuando los dos difieren.
            uid_bd = (ajustes.get("ig_user_id") or "").strip()
            if uid_bd and uid_bd != (cfg.get("IG_USER_ID") or "").strip():
                cfg["IG_USER_ID"] = uid_bd
            if ajustes.get("ig_username"):
                cfg["IG_USERNAME"] = ajustes["ig_username"]
            for clave in _CLAVES_IG_AJUSTABLES:
                k_bd = clave.lower()
                if ajustes.get(k_bd) and not cfg.get(clave):
                    cfg[clave] = str(ajustes[k_bd])
        except Exception:
            pass

    for clave in (
        "IG_USER_ID", "IG_ACCESS_TOKEN", "IG_GRAPH_HOST",
        "IG_AUTO_PUBLISH", "IG_MEDIA_BASE_URL", *_CLAVES_IG_AJUSTABLES,
    ):
        if os.environ.get(clave):
            cfg[clave] = os.environ[clave]
    return cfg


def limites_diarios_ig(cfg: dict[str, str]) -> dict[str, object]:
    """Topes diarios de publicación (por defecto: 2 Reels + 1 Post + 2 Historias = 5/día)."""
    max_videos = sales_agent._entero(cfg, "IG_DAILY_VIDEOS", 2)
    max_posts = sales_agent._entero(cfg, "IG_DAILY_POSTS", 1)
    max_historias = sales_agent._entero(cfg, "IG_DAILY_STORIES", 2)
    max_carruseles = sales_agent._entero(cfg, "IG_DAILY_CAROUSELS", 1)
    suma_mix = max_videos + max_posts + max_historias + max_carruseles

    tiene_total_explicito = bool(str(cfg.get("IG_MAX_DAILY_POSTS") or "").strip())
    max_total = (
        sales_agent._entero(cfg, "IG_MAX_DAILY_POSTS", suma_mix)
        if tiene_total_explicito else suma_mix
    )
    usa_por_tipo = (not tiene_total_explicito) or any(
        bool(str(cfg.get(k) or "").strip())
        for k in ("IG_DAILY_VIDEOS", "IG_DAILY_POSTS", "IG_DAILY_STORIES", "IG_DAILY_CAROUSELS")
    )
    return {
        "total": max_total,
        "usa_por_tipo": usa_por_tipo,
        "por_tipo": {"video": max_videos, "post": max_posts, "historia": max_historias,
                     "carrusel": max_carruseles},
        "min_interval_min": sales_agent._entero(cfg, "IG_MIN_INTERVAL_MINUTES", 75),
    }


def modo_autonomo_activo(cfg: dict[str, str] | None = None) -> bool:
    """El interruptor del panel (`settings.ig_auto_publish`) manda sobre `.env`."""
    cfg = cargar_config_ig() if cfg is None else cfg
    if database.DB_PATH.exists():
        guardado = database.get_settings().get("ig_auto_publish")
        if guardado in ("0", "1"):
            return guardado == "1"
    crudo = str(cfg.get("IG_AUTO_PUBLISH", "")).strip().lower()
    if crudo in ("0", "false", "no", "off"):
        return False
    if crudo in ("1", "true", "si", "sí", "on"):
        return True
    return True


def cambiar_modo_autonomo(activo: bool) -> bool:
    database.init_db()
    database.update_settings({"ig_auto_publish": "1" if activo else "0"})
    return activo


def estado_ig(cfg: dict[str, str] | None = None) -> dict[str, object]:
    """Resumen seguro para el panel y `--dry-run` (cero secretos expuestos)."""
    cfg = cargar_config_ig() if cfg is None else cfg
    user_id = (cfg.get("IG_USER_ID") or "").strip()
    token = (cfg.get("IG_ACCESS_TOKEN") or "").strip()
    lims = limites_diarios_ig(cfg)
    publicados_hoy = database.ig_published_today() if database.DB_PATH.exists() else 0
    por_tipo_hoy = (
        database.ig_published_today_by_tipo()
        if database.DB_PATH.exists()
        else {"video": 0, "post": 0, "historia": 0, "carrusel": 0}
    )
    return {
        # Con el token basta: si falta IG_USER_ID, se autodescubre solo vía API oficial.
        "credenciales_listas": bool(token),
        "user_id_resuelto": bool(user_id),
        "username": (cfg.get("IG_USERNAME") or "").strip(),
        "auto_publish": modo_autonomo_activo(cfg),
        "max_daily_posts": int(lims["total"]),
        "cuota_por_tipo": lims["por_tipo"],
        "publicados_hoy": publicados_hoy,
        "publicados_por_tipo": por_tipo_hoy,
        "graph_base": _url_base_graph(cfg),
    }


def _url_base_graph(cfg: dict[str, str]) -> str:
    """Elige automáticamente `graph.instagram.com` (tokens IGAA...) o `graph.facebook.com`."""
    forzado = (cfg.get("IG_GRAPH_HOST") or "").strip().rstrip("/")
    if forzado:
        return forzado if "/v" in forzado else f"{forzado}/{GRAPH_VERSION}"
    token = (cfg.get("IG_ACCESS_TOKEN") or "").strip()
    host = "https://graph.instagram.com" if token.startswith("IGA") else "https://graph.facebook.com"
    return f"{host}/{GRAPH_VERSION}"


# ----------------------------------------- conversión JPEG + subida HTTPS efímera

def preparar_archivo_para_meta(ruta: Path) -> Path:
    """Asegura que el archivo cumpla los formatos oficiales de Meta Graph API.

    - Video Reel: `.mp4` H.264.
    - Imagen Post: Meta rechaza `.png` (error 2207005); convierte a `.jpg` con `sips`.
    """
    if not ruta.exists():
        raise ErrorIG(f"No existe el archivo renderizado: {ruta.name}")
    sufijo = ruta.suffix.lower()
    if sufijo == ".mp4":
        return ruta
    if sufijo in (".jpg", ".jpeg"):
        if ruta.stat().st_size > MAX_JPEG_BYTES:
            raise ErrorIG("El JPEG supera el límite de 8 MB de Instagram Graph API.")
        return ruta
    if sufijo == ".png":
        destino_jpg = ruta.with_suffix(".jpg")
        proc = subprocess.run(
            ["/usr/bin/sips", "-s", "format", "jpeg", "-s", "formatOptions", "92",
             str(ruta), "--out", str(destino_jpg)],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0 or not destino_jpg.exists():
            raise ErrorIG(f"No se pudo convertir PNG a JPEG con sips: {(proc.stderr or '')[:200]}")
        if destino_jpg.stat().st_size > MAX_JPEG_BYTES:
            raise ErrorIG("El JPEG convertido supera los 8 MB permitidos por Meta.")
        return destino_jpg
    raise ErrorIG(f"Formato no soportado por Instagram Graph API: {sufijo}")


GH_PAGES_DOCS_DIR = PROJECT_ROOT / "docs" / "ig-media"
GH_PAGES_BASE_URL = "https://reyvonblon.github.io/Elsocio/ig-media"
GH_PAGES_MAX_ARCHIVOS = 15  # conserva solo los últimos N; poda los viejos en cada subida
GH_PAGES_TIMEOUT_DEPLOY_SEG = 90


def _ejecutar_git(args: list[str]) -> str:
    resultado = subprocess.run(
        ["git", *args], cwd=str(PROJECT_ROOT), check=True, timeout=30,
        capture_output=True, text=True,
    )
    return resultado.stdout


def _podar_media_vieja_github_pages() -> list[str]:
    """Mantiene el repo liviano: solo conserva las últimas `GH_PAGES_MAX_ARCHIVOS` piezas."""
    if not GH_PAGES_DOCS_DIR.is_dir():
        return []
    archivos = sorted(GH_PAGES_DOCS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    borrados = []
    for p in archivos[GH_PAGES_MAX_ARCHIVOS:]:
        p.unlink(missing_ok=True)
        borrados.append(str(p.relative_to(PROJECT_ROOT)))
    return borrados


def subir_a_github_pages(ruta: Path) -> str:
    """Alternativa propia y confiable a servicios gratis de terceros: publica el archivo en
    `docs/ig-media/` (el mismo GitHub Pages que ya sirve la landing) con un commit+push que
    SOLO toca esa carpeta, y espera a que el deploy esté en vivo antes de devolver la URL
    (Meta tiene que poder bajarla ya mismo, no en un rato)."""
    GH_PAGES_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    destino = GH_PAGES_DOCS_DIR / ruta.name
    shutil.copy2(ruta, destino)
    borrados = _podar_media_vieja_github_pages()
    rel_nuevo = str(destino.relative_to(PROJECT_ROOT))

    try:
        _ejecutar_git(["add", "--", rel_nuevo, *borrados])
        pendiente = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=str(PROJECT_ROOT), timeout=15,
        ).returncode != 0
        if pendiente:
            _ejecutar_git(["commit", "-m", f"Media IG: {ruta.name}"])
            # `-c http.version=HTTP/1.1 -c http.postBuffer=524288000`: sin esto, el push de
            # binarios (video/imagen) corta la conexión a mitad con "unexpected disconnect
            # while reading sideband packet" en esta red — probado y confirmado en vivo.
            _ejecutar_git([
                "-c", "http.version=HTTP/1.1", "-c", "http.postBuffer=524288000",
                "push", "origin", "HEAD:main",
            ])
    except subprocess.CalledProcessError as exc:
        raise ErrorIG(f"git falló publicando en GitHub Pages: {(exc.stderr or '')[:300]}") from None
    except subprocess.TimeoutExpired:
        raise ErrorIG("git tardó demasiado publicando en GitHub Pages.") from None

    url = f"{GH_PAGES_BASE_URL}/{urllib.parse.quote(ruta.name)}"
    desde = time.time()
    while time.time() - desde < GH_PAGES_TIMEOUT_DEPLOY_SEG:
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                if resp.status == 200:
                    return url
        except urllib.error.URLError:
            pass
        time.sleep(5)
    raise ErrorIG(f"GitHub Pages no sirvió '{ruta.name}' a tiempo (>{GH_PAGES_TIMEOUT_DEPLOY_SEG}s).")


def _subir_litterbox(ruta: Path) -> str:
    """Último recurso: servicio gratis de terceros, efímero (se autodestruye en 1h) y sin
    garantía de disponibilidad — úsalo solo si GitHub Pages falló."""
    limite = "----ElSocioBoundary" + secrets.token_hex(12)
    mime = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
    contenido = ruta.read_bytes()

    partes: list[bytes] = []
    for campo, valor in (("reqtype", "fileupload"), ("time", "1h")):
        partes.append(
            f"--{limite}\r\n"
            f'Content-Disposition: form-data; name="{campo}"\r\n\r\n'
            f"{valor}\r\n".encode("utf-8")
        )
    partes.append(
        f"--{limite}\r\n"
        f'Content-Disposition: form-data; name="fileToUpload"; filename="{ruta.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n".encode("utf-8")
    )
    partes.append(contenido)
    partes.append(f"\r\n--{limite}--\r\n".encode("utf-8"))
    cuerpo = b"".join(partes)

    req = urllib.request.Request(
        LITTERBOX_API,
        data=cuerpo,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={limite}",
            "User-Agent": "ElSocioPublisher/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            url = resp.read().decode("utf-8", errors="replace").strip()
    except urllib.error.URLError as exc:
        raise ErrorIG(f"Fallo al subir archivo temporal HTTPS: {exc}") from None

    if not url.startswith("https://"):
        raise ErrorIG(f"El servidor temporal no devolvió una URL HTTPS válida: {url[:120]}")
    return url


def obtener_url_publica_https(ruta: Path, cfg: dict[str, str]) -> str:
    """Devuelve una URL `https://` accesible por los servidores de Meta.

    Orden: 1) `IG_MEDIA_BASE_URL` si la configuraste a mano, 2) GitHub Pages de este mismo
    repo (confiable, bajo tu control), 3) un servicio gratis de terceros como último recurso
    (efímero y sin garantía — puede estar caído sin que sea culpa tuya).
    """
    base_propia = (cfg.get("IG_MEDIA_BASE_URL") or "").strip().rstrip("/")
    if base_propia:
        if not base_propia.startswith("https://"):
            raise ErrorIG("IG_MEDIA_BASE_URL debe empezar por https://")
        return f"{base_propia}/{urllib.parse.quote(ruta.name)}"

    try:
        return subir_a_github_pages(ruta)
    except ErrorIG as error_github:
        try:
            return _subir_litterbox(ruta)
        except ErrorIG as error_litterbox:
            raise ErrorIG(
                f"GitHub Pages: {error_github}. Litterbox (respaldo): {error_litterbox}"
            ) from None


# ------------------------------------------------ llamadas a Meta Graph API

def _sanitizar_error_meta(texto: str, token: str) -> str:
    if token:
        texto = texto.replace(token, "[REDACTED]")
    return texto[:350]


def _graph_post(url: str, params: dict[str, str], token: str) -> dict:
    datos = urllib.parse.urlencode({**params, "access_token": token}).encode("utf-8")
    req = urllib.request.Request(
        url, data=datos, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_HTTP_IG) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detalle = ""
        try:
            detalle = err.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise ErrorIG(f"Meta HTTP {err.code}: {_sanitizar_error_meta(detalle, token)}") from None
    except urllib.error.URLError as exc:
        raise ErrorIG(f"Meta red: {_sanitizar_error_meta(str(exc.reason), token)}") from None


def _graph_get(url: str, params: dict[str, str], token: str) -> dict:
    qs = urllib.parse.urlencode({**params, "access_token": token})
    req = urllib.request.Request(f"{url}?{qs}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_HTTP_IG) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detalle = ""
        try:
            detalle = err.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise ErrorIG(f"Meta HTTP {err.code}: {_sanitizar_error_meta(detalle, token)}") from None
    except urllib.error.URLError as exc:
        raise ErrorIG(f"Meta red: {_sanitizar_error_meta(str(exc.reason), token)}") from None


def _esperar_contenedor_listo(base_graph: str, creation_id: str, token: str) -> None:
    """Espera a que Meta termine de procesar el contenedor (`status_code == FINISHED`)."""
    for intento in range(MAX_POLLS_META):
        estado = _graph_get(
            f"{base_graph}/{creation_id}",
            {"fields": "status_code,status"},
            token,
        )
        codigo = str(estado.get("status_code") or "").upper()
        if codigo == "FINISHED":
            return
        if codigo in ("ERROR", "EXPIRED"):
            detalle = str(estado.get("status") or codigo)
            raise ErrorIG(f"Meta rechazó procesar el archivo ({codigo}): {detalle[:220]}")
        # Si es imagen simple a veces no devuelve status_code y ya está lista.
        if not codigo and intento >= 1:
            return
        time.sleep(PAUSA_POLL_SEG)
    raise ErrorIG("Tiempo agotado esperando a que Meta termine de procesar el video (IN_PROGRESS).")


def descubrir_cuenta_ig(token: str, cfg: dict[str, str] | None = None) -> dict[str, str]:
    """Descubre automáticamente `IG_USER_ID` y `@username` con solo pegar `IG_ACCESS_TOKEN`.

    - Tokens `IGA...` (Instagram Login): consulta `/me?fields=user_id,id,username`.
    - Tokens `EAA...` (Facebook Login): consulta `/me/accounts?fields=instagram_business_account{id,username}`.
    Guarda el ID en `settings` para no volver a pedirlo nunca.
    """
    tok = (token or "").strip()
    if not tok:
        raise ErrorIG("Falta IG_ACCESS_TOKEN.")
    cfg_uso = dict(cfg or {})
    cfg_uso["IG_ACCESS_TOKEN"] = tok
    base = _url_base_graph(cfg_uso)

    uid = ""
    uname = ""
    if tok.startswith("IGA"):
        datos = _graph_get(f"{base}/me", {"fields": "user_id,id,username"}, tok)
        uid = str(datos.get("user_id") or datos.get("id") or "").strip()
        uname = str(datos.get("username") or "").strip()
    else:
        datos = _graph_get(
            f"{base}/me/accounts",
            {"fields": "instagram_business_account{id,username}"},
            tok,
        )
        for pagina in (datos.get("data") or []):
            ig_acc = pagina.get("instagram_business_account") or {}
            if ig_acc.get("id"):
                uid = str(ig_acc["id"]).strip()
                uname = str(ig_acc.get("username") or "").strip()
                break

    if not uid:
        raise ErrorIG("No se encontró una cuenta profesional de Instagram vinculada a ese token.")

    database.init_db()
    guardar = {"ig_user_id": uid}
    if uname:
        guardar["ig_username"] = uname
    if not database.get_settings().get("ig_token_refreshed_at"):
        guardar["ig_token_refreshed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    database.update_settings(guardar)
    return {"user_id": uid, "username": uname}


def renovar_token_ig_si_toca(
    cfg: dict[str, str] | None = None, *, dry_run: bool = False,
) -> dict[str, object]:
    """Renueva sola la llave de 60 días de Meta cada 25 días para que nunca venza."""
    cfg = cargar_config_ig() if cfg is None else cfg
    token = (cfg.get("IG_ACCESS_TOKEN") or "").strip()
    if not token or not token.startswith("IGA") or not database.DB_PATH.exists():
        return {"renovado": False, "razon": "no_aplica"}

    ajustes = database.get_settings()
    marca = (ajustes.get("ig_token_refreshed_at") or "").strip()
    ahora = datetime.now()
    if not marca:
        if not dry_run:
            database.update_settings({"ig_token_refreshed_at": ahora.strftime("%Y-%m-%d %H:%M:%S")})
        return {"renovado": False, "razon": "sello_inicial_creado"}

    try:
        dt_prev = datetime.strptime(marca, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        dt_prev = ahora - timedelta(days=DIAS_RENOVACION_TOKEN + 1)

    if (ahora - dt_prev).days < DIAS_RENOVACION_TOKEN:
        return {"renovado": False, "razon": "vigente"}
    if dry_run:
        return {"renovado": False, "dry_run": True, "razon": "listo_para_renovar"}

    datos = _graph_get(
        "https://graph.instagram.com/refresh_access_token",
        {"grant_type": "ig_refresh_token"},
        token,
    )
    nuevo = str(datos.get("access_token") or "").strip()
    if not nuevo:
        raise ErrorIG("Meta no devolvió `access_token` al renovar.")
    database.update_settings({
        "ig_access_token": nuevo,
        "ig_token_refreshed_at": ahora.strftime("%Y-%m-%d %H:%M:%S"),
    })
    return {"renovado": True}


# ------------------------------------------------ aprendizaje real: horario y hashtags

# Semilla inicial manual (NO es "tendencia" verificada, es punto de partida honesto mientras
# se junta desempeño real de la cuenta). Se reemplaza sola por los hashtags con mejor
# like+comentarios reales en cuanto hay >=5 publicaciones con datos.
_HASHTAGS_SEMILLA = [
    "marketingdigital", "pymes", "emprendedores", "negociosonline",
    "automatizacion", "redessociales", "marcapersonal", "contenidodigital",
]


def obtener_mejores_horas_ig(cfg: dict[str, str] | None = None, *, forzar: bool = False) -> dict[str, object]:
    """Aprende de Meta (`online_followers`, dato oficial real) a qué hora UTC hay más
    seguidores conectados, y lo guarda para que `ciclo_publicacion_autonoma` lo use.
    Se cachea ~20h porque Meta solo actualiza esta métrica una vez al día.
    """
    cfg = cargar_config_ig() if cfg is None else cfg
    database.init_db()
    ajustes = database.get_settings()
    if not forzar:
        marca = (ajustes.get("ig_mejores_horas_actualizado") or "").strip()
        if marca:
            try:
                if (datetime.now() - datetime.strptime(marca, "%Y-%m-%d %H:%M:%S")) < timedelta(hours=20):
                    return {"ok": True, "desde_cache": True}
            except ValueError:
                pass

    user_id = (cfg.get("IG_USER_ID") or "").strip()
    token = (cfg.get("IG_ACCESS_TOKEN") or "").strip()
    if not user_id or not token:
        return {"ok": False, "error": "Falta IG_USER_ID o IG_ACCESS_TOKEN."}

    base = _url_base_graph(cfg)
    try:
        datos = _graph_get(
            f"{base}/{user_id}/insights", {"metric": "online_followers", "period": "lifetime"}, token,
        )
    except ErrorIG as exc:
        return {"ok": False, "error": str(exc)}

    valores = (((datos.get("data") or [{}])[0]).get("values") or [])
    por_hora = (valores[-1].get("value") if valores else None) or {}
    if not por_hora:
        return {"ok": False, "error": "Meta aún no tiene datos de 'online_followers' (cuenta nueva o pocos seguidores)."}

    ranking = sorted(((int(h), int(v)) for h, v in por_hora.items()), key=lambda hv: -hv[1])
    mejores_utc = [h for h, _ in ranking[:6]]
    database.update_settings({
        "ig_mejores_horas_utc": json.dumps(mejores_utc),
        "ig_mejores_horas_actualizado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    return {"ok": True, "mejores_horas_utc": mejores_utc, "por_hora": por_hora}


def _mejor_momento_para_publicar(cfg: dict[str, str]) -> tuple[bool, str]:
    """True si ahora es buena hora (o no hay dato aún). False = esperar una hora mejor hoy."""
    if not database.DB_PATH.exists():
        return True, "sin_bd"
    crudo = (database.get_settings().get("ig_mejores_horas_utc") or "").strip()
    if not crudo:
        return True, "sin_datos_de_horario_aun"
    try:
        mejores = {int(h) for h in json.loads(crudo)}
    except (ValueError, TypeError):
        return True, "datos_de_horario_invalidos"
    if not mejores:
        return True, "sin_datos_de_horario_aun"
    hora_utc = datetime.utcnow().hour
    if hora_utc in mejores:
        return True, "hora_optima_segun_seguidores_reales"
    if any(h > hora_utc for h in mejores):
        return False, "esperando_mejor_hora_hoy_segun_seguidores_reales"
    return True, "no_quedan_horas_optimas_hoy"


def _extraer_hashtags(texto: str) -> list[str]:
    return [m.lower() for m in re.findall(r"#(\w+)", texto or "")]


def obtener_mejores_hashtags_ig(top_n: int = 6) -> list[str]:
    """Hashtags propios con mejor like+comentarios reales hasta ahora. Si aún no hay
    suficiente historial propio, usa la semilla manual (declarada como estimación, no dato real)."""
    crudo = (database.get_settings().get("ig_hashtags_rendimiento") or "").strip() if database.DB_PATH.exists() else ""
    puntajes: dict[str, float] = {}
    if crudo:
        try:
            puntajes = {str(k): float(v) for k, v in json.loads(crudo).items()}
        except (ValueError, TypeError):
            puntajes = {}
    if len(puntajes) < 5:
        return list(_HASHTAGS_SEMILLA[:top_n])
    return [tag for tag, _ in sorted(puntajes.items(), key=lambda kv: -kv[1])[:top_n]]


def registrar_rendimiento_hashtags(hashtags: list[str], *, likes: int, comentarios: int) -> None:
    if not hashtags:
        return
    database.init_db()
    crudo = (database.get_settings().get("ig_hashtags_rendimiento") or "").strip()
    try:
        puntajes: dict[str, float] = json.loads(crudo) if crudo else {}
    except (ValueError, TypeError):
        puntajes = {}
    puntaje_pieza = float(likes) + float(comentarios) * 3.0
    for tag in hashtags:
        puntajes[tag] = puntajes.get(tag, 0.0) + puntaje_pieza
    database.update_settings({"ig_hashtags_rendimiento": json.dumps(puntajes, ensure_ascii=False)})


# ------------------------------------------------ publicación con guardas duras

def armar_caption_ig(pieza: dict) -> tuple[str, list[str]]:
    """Devuelve (caption_final, hashtags_usados). Los hashtags van en bloque aparte al
    final (nunca mezclados en el gancho/guion) para no romper la regla de 'sin hashtags
    basura' del texto en pantalla ni la voz humana del copy."""
    caption = str(pieza.get("caption") or "").strip()
    gancho = str(pieza.get("gancho") or "").strip()
    base = f"{gancho}\n\n{caption}".strip() if (caption and gancho.lower() not in caption.lower()) else (caption or gancho)
    if str(pieza.get("tipo") or "").strip().lower() == "historia":
        return base, []  # las historias no llevan hashtags visibles
    hashtags = obtener_mejores_hashtags_ig()
    if not hashtags:
        return base, []
    bloque = " ".join(f"#{h}" for h in hashtags)
    return f"{base}\n\n.\n.\n{bloque}".strip(), hashtags


def publicar_pieza_ig(
    content_id: int, *, cfg: dict[str, str] | None = None, dry_run: bool = False,
) -> dict[str, object]:
    """Publica una pieza `generado` en Instagram por la API oficial de Meta."""
    cfg = cargar_config_ig() if cfg is None else cfg
    pieza = database.get_content(content_id)
    if not pieza:
        return {"publicado": False, "error": f"No existe la pieza #{content_id}."}
    if pieza["estado"] == "publicado":
        return {"publicado": False, "error": f"La pieza #{content_id} ya fue publicada."}
    if pieza["estado"] == "descartado":
        return {"publicado": False, "error": f"La pieza #{content_id} está descartada."}
    if pieza["estado"] != "generado" or not (pieza.get("archivo") or "").strip():
        return {"publicado": False, "error": f"La pieza #{content_id} aún no está renderizada ('{pieza['estado']}')."}

    caption_final, hashtags_usados = armar_caption_ig(pieza)
    _, etiquetas_nota = content_manager.leer_reel(pieza.get("nota"))
    motivos = sales_agent.revisar_guarda_precios(
        pieza["gancho"], pieza.get("guion") or "", caption_final, *etiquetas_nota
    )
    if motivos:
        detalle = "; ".join(motivos[:5])
        if not dry_run:
            database.update_content(content_id, error_ig=f"BLOQUEADO por guarda: {detalle}")
        return {"publicado": False, "bloqueado_por_guarda": True, "error": detalle}

    lims = limites_diarios_ig(cfg)
    max_posts = int(lims["total"])
    publicados_hoy = database.ig_published_today()
    if publicados_hoy >= max_posts:
        return {
            "publicado": False,
            "error": f"Tope diario de publicaciones en Instagram alcanzado ({publicados_hoy}/{max_posts}).",
        }

    tipo_pieza = str(pieza.get("tipo") or "post").strip().lower()
    if bool(lims["usa_por_tipo"]):
        por_tipo_hoy = database.ig_published_today_by_tipo()
        tope_tipo = int((lims["por_tipo"] or {}).get(tipo_pieza, max_posts))
        if int(por_tipo_hoy.get(tipo_pieza, 0)) >= tope_tipo:
            return {
                "publicado": False,
                "error": (
                    f"Tope diario de '{tipo_pieza}' en Instagram alcanzado "
                    f"({por_tipo_hoy.get(tipo_pieza, 0)}/{tope_tipo})."
                ),
            }

    ruta_local = Path(str(pieza["archivo"]))
    user_id = (cfg.get("IG_USER_ID") or "").strip()
    token = (cfg.get("IG_ACCESS_TOKEN") or "").strip()
    base_graph = _url_base_graph(cfg)

    if dry_run:
        media_type_dry = {
            "video": "REELS", "historia": "STORIES", "carrusel": "CAROUSEL",
        }.get(tipo_pieza, "IMAGE")
        return {
            "publicado": False,
            "dry_run": True,
            "id": content_id,
            "tipo": tipo_pieza,
            "media_type": media_type_dry,
            "archivo": str(ruta_local),
            "credenciales_listas": bool(token),
            "graph_endpoint": f"{base_graph}/{user_id or '<AUTO_IG_USER_ID>'}/media",
            "caption_preview": "" if tipo_pieza == "historia" else caption_final[:160],
        }

    if not token:
        return {
            "publicado": False,
            "error": "Falta IG_ACCESS_TOKEN (pégalo en el panel 8787 o en .env) para publicar en Instagram.",
        }

    try:
        try:
            renovar_token_ig_si_toca(cfg)
            cfg = cargar_config_ig() if cfg is None else cfg
        except ErrorIG:
            pass
        if not user_id:
            desc = descubrir_cuenta_ig(token, cfg)
            user_id = desc["user_id"]
        if tipo_pieza == "carrusel":
            laminas = content_manager.archivos_carrusel(ruta_local)
            if len(laminas) < 2:
                raise ErrorIG("El carrusel necesita al menos 2 láminas renderizadas.")
            hijos: list[str] = []
            for lamina in laminas[:10]:  # Meta admite máximo 10 elementos por carrusel
                url_lamina = obtener_url_publica_https(preparar_archivo_para_meta(lamina), cfg)
                hijo = _graph_post(
                    f"{base_graph}/{user_id}/media",
                    {"image_url": url_lamina, "is_carousel_item": "true"},
                    token,
                )
                hijo_id = str(hijo.get("id") or "").strip()
                if not hijo_id:
                    raise ErrorIG("Meta no devolvió `id` para una lámina del carrusel.")
                _esperar_contenedor_listo(base_graph, hijo_id, token)
                hijos.append(hijo_id)
            archivo_meta = ruta_local
            url_publica = ""
        else:
            archivo_meta = preparar_archivo_para_meta(ruta_local)
            url_publica = obtener_url_publica_https(archivo_meta, cfg)

        if tipo_pieza == "carrusel":
            params_contenedor = {
                "media_type": "CAROUSEL",
                "children": ",".join(hijos),
                "caption": caption_final,
            }
        elif tipo_pieza == "video":
            params_contenedor = {
                "media_type": "REELS",
                "video_url": url_publica,
                "caption": caption_final,
                "share_to_feed": "true",
            }
        elif tipo_pieza == "historia":
            # Meta Graph API oficial: STORIES no admite `caption` ni `share_to_feed`.
            if archivo_meta.suffix.lower() == ".mp4":
                params_contenedor = {
                    "media_type": "STORIES",
                    "video_url": url_publica,
                }
            else:
                params_contenedor = {
                    "media_type": "STORIES",
                    "image_url": url_publica,
                }
        else:
            params_contenedor = {
                "image_url": url_publica,
                "caption": caption_final,
            }

        creado = _graph_post(f"{base_graph}/{user_id}/media", params_contenedor, token)
        creation_id = str(creado.get("id") or "").strip()
        if not creation_id:
            raise ErrorIG("Meta no devolvió `creation_id` al crear el contenedor.")

        _esperar_contenedor_listo(base_graph, creation_id, token)

        publicado = _graph_post(
            f"{base_graph}/{user_id}/media_publish",
            {"creation_id": creation_id},
            token,
        )
        ig_media_id = str(publicado.get("id") or "").strip()
        if not ig_media_id:
            raise ErrorIG("Meta no devolvió `id` al confirmar `media_publish`.")
    except ErrorIG as exc:
        # Rollback limpio: se queda en `generado`, guarda el error y NO toca RESULTADOS_MERCADO.md.
        database.update_content(content_id, error_ig=str(exc))
        database.log_agent_action(
            lead_id=None, turno=0, modelo="meta-graph-api",
            herramienta="ig_publish_error",
            argumentos=json.dumps({"content_id": content_id}, ensure_ascii=False),
            resultado=str(exc)[:400], costo_usd=0.0,
        )
        return {"publicado": False, "error": str(exc)}

    database.update_content(
        content_id, estado="publicado", ig_media_id=ig_media_id, error_ig="",
        hashtags_ig=",".join(hashtags_usados),
    )
    database.log_agent_action(
        lead_id=None, turno=0, modelo="meta-graph-api",
        herramienta="ig_publish",
        argumentos=json.dumps({"content_id": content_id, "tipo": tipo_pieza}, ensure_ascii=False),
        resultado=f"publicado ig_media_id={ig_media_id}", costo_usd=0.0,
    )
    return {"publicado": True, "id": content_id, "tipo": tipo_pieza, "ig_media_id": ig_media_id}


def _elegir_pieza_para_publicar(listas: list[dict], cfg: dict[str, str]) -> dict | None:
    """Elige la pieza más antigua cuyo formato aún tenga cupo hoy, alternando respecto a la última."""
    if not listas:
        return None
    lims = limites_diarios_ig(cfg)
    usa_por_tipo = bool(lims["usa_por_tipo"])
    por_tipo_hoy = database.ig_published_today_by_tipo() if database.DB_PATH.exists() else {}
    topes_tipo = dict(lims["por_tipo"] or {})

    # Orden FIFO real (más antigua primero)
    candidatas_fifo = list(reversed(listas))
    elegibles = []
    for p in candidatas_fifo:
        t = str(p.get("tipo") or "post").strip().lower()
        if usa_por_tipo and int(por_tipo_hoy.get(t, 0)) >= int(topes_tipo.get(t, 0)):
            continue
        elegibles.append(p)

    if not elegibles:
        return None

    publicadas_recientes = database.list_content(estado="publicado", limit=1) if database.DB_PATH.exists() else []
    ultimo_tipo = str(publicadas_recientes[0].get("tipo") or "") if publicadas_recientes else ""
    if ultimo_tipo:
        for p in elegibles:
            if str(p.get("tipo") or "") != ultimo_tipo:
                return p
    return elegibles[0]


def ciclo_publicacion_autonoma(*, cfg: dict[str, str] | None = None, dry_run: bool = False) -> dict:
    """Publica respetando el tope diario total/por tipo, pausa orgánica e interruptor."""
    cfg = cargar_config_ig() if cfg is None else cfg
    if dry_run and not database.DB_PATH.exists():
        return {"ejecutado": False, "dry_run": True, "razon": "dry_run_sin_bd"}

    est = estado_ig(cfg)
    if not est["auto_publish"]:
        return {"ejecutado": False, "dry_run": dry_run, "razon": "modo_preview_esperando_aprobacion", "estado": est}
    if not est["credenciales_listas"] and not dry_run:
        return {"ejecutado": False, "dry_run": dry_run, "razon": "sin_credenciales_ig", "estado": est}
    if int(est["publicados_hoy"]) >= int(est["max_daily_posts"]):
        return {"ejecutado": False, "dry_run": dry_run, "razon": "tope_diario_ig_alcanzado", "estado": est}

    if not dry_run and est["credenciales_listas"]:
        try:
            obtener_mejores_horas_ig(cfg)
        except Exception:
            pass  # el aprendizaje de horario nunca debe bloquear la publicación

    es_buen_momento, razon_horario = _mejor_momento_para_publicar(cfg)
    if not es_buen_momento:
        return {"ejecutado": False, "dry_run": dry_run, "razon": razon_horario, "estado": est}

    # Pausa orgánica entre publicaciones del mismo día para no saturar en un solo minuto.
    lims = limites_diarios_ig(cfg)
    min_pausa = int(lims["min_interval_min"])
    if min_pausa > 0 and int(est["publicados_hoy"]) > 0 and database.DB_PATH.exists():
        ultima_dt = database.last_ig_published_datetime()
        if ultima_dt and (datetime.now() - ultima_dt) < timedelta(minutes=min_pausa):
            return {
                "ejecutado": False,
                "dry_run": dry_run,
                "razon": "pausa_organica_entre_publicaciones",
                "estado": est,
            }

    # Primero genera cualquier pieza aprobada que aún no tenga archivo renderizado.
    if not dry_run:
        aprobadas = list(reversed(database.list_content(estado="aprobado", limit=8)))
        videos_hechos = 0
        for p in aprobadas:
            es_video = p.get("tipo") == "video"
            if es_video and videos_hechos >= 1:
                continue
            content_manager.generar(int(p["id"]))
            if es_video:
                videos_hechos += 1

    listas = database.list_content(estado="generado", limit=25)
    if not listas:
        return {"ejecutado": False, "dry_run": dry_run, "razon": "sin_piezas_generadas", "estado": est}

    elegida = _elegir_pieza_para_publicar(listas, cfg)
    if not elegida:
        return {"ejecutado": False, "dry_run": dry_run, "razon": "tope_por_tipo_ig_alcanzado", "estado": est}

    res = publicar_pieza_ig(int(elegida["id"]), cfg=cfg, dry_run=dry_run)
    if not dry_run:
        if res.get("publicado"):
            database.update_settings({"ig_fallo_desde": "", "ig_fallo_ultimo_aviso": ""})
        elif res.get("error") and not res.get("bloqueado_por_guarda"):
            _avisar_si_fallo_persistente(str(res["error"]))
    return {"ejecutado": True, "dry_run": dry_run, "pieza_id": int(elegida["id"]), "resultado": res}


def _avisar_si_fallo_persistente(error_txt: str) -> None:
    """Si Instagram lleva >1h fallando seguido, un solo aviso en el Mac cada 3h (no spamea)."""
    database.init_db()
    ajustes = database.get_settings()
    ahora = datetime.now()
    desde_txt = (ajustes.get("ig_fallo_desde") or "").strip()
    if not desde_txt:
        database.update_settings({"ig_fallo_desde": ahora.strftime("%Y-%m-%d %H:%M:%S")})
        return
    try:
        desde = datetime.strptime(desde_txt, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        database.update_settings({"ig_fallo_desde": ahora.strftime("%Y-%m-%d %H:%M:%S")})
        return
    if (ahora - desde) < timedelta(hours=1):
        return
    ultimo_aviso_txt = (ajustes.get("ig_fallo_ultimo_aviso") or "").strip()
    if ultimo_aviso_txt:
        try:
            if (ahora - datetime.strptime(ultimo_aviso_txt, "%Y-%m-%d %H:%M:%S")) < timedelta(hours=3):
                return
        except ValueError:
            pass
    if autopilot_dispatcher.notify_mac_desktop(
        "Instagram no está publicando",
        f"Lleva más de 1h fallando: {error_txt[:140]}",
    ):
        database.update_settings({"ig_fallo_ultimo_aviso": ahora.strftime("%Y-%m-%d %H:%M:%S")})


def sincronizar_resultados_ig(
    *, dias_silencio: int = 7, cfg: dict[str, str] | None = None,
    ruta_resultados: Path | None = None, dry_run: bool = False,
) -> dict[str, object]:
    """Consulta `comments_count` real en Meta Graph API para piezas publicadas y registra
    resultados honestos en `RESULTADOS_MERCADO.md` (con plazo cumplido, cero inventos).
    """
    cfg = cargar_config_ig() if cfg is None else cfg
    ruta = autopilot_dispatcher.RESULTADOS_FILE if ruta_resultados is None else ruta_resultados
    if not database.DB_PATH.exists():
        return {"registradas": 0, "razon": "sin_bd"}

    token = (cfg.get("IG_ACCESS_TOKEN") or "").strip()
    if not token:
        return {"registradas": 0, "razon": "sin_token_ig"}

    base_graph = _url_base_graph(cfg)
    texto_actual = ruta.read_text(encoding="utf-8") if ruta.exists() else ""
    ya_registradas = set(re.findall(r"\[(ig #[0-9]+)\]", texto_actual))

    corte = datetime.now() - timedelta(days=max(1, dias_silencio))
    publicadas = database.list_content(estado="publicado", limit=50)
    registradas = 0
    for p in publicadas:
        # Las historias caducan en 24h y no tienen hilo público de comentarios en Graph API.
        if str(p.get("tipo") or "").strip().lower() == "historia":
            continue
        marca = f"ig #{p['id']}"
        if marca in ya_registradas or not (p.get("ig_media_id") or "").strip():
            continue
        pub_at = str(p.get("published_at") or "")
        try:
            dt_pub = datetime.strptime(pub_at, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        try:
            datos = _graph_get(
                f"{base_graph}/{p['ig_media_id']}",
                {"fields": "comments_count,like_count"},
                token,
            )
        except ErrorIG:
            continue

        comentarios = int(datos.get("comments_count") or 0)
        likes = int(datos.get("like_count") or 0)
        if not dry_run:
            database.actualizar_engagement_ig(p["id"], likes=likes, comentarios=comentarios)

        hashtags_pieza = [h for h in (p.get("hashtags_ig") or "").split(",") if h]
        if hashtags_pieza:
            contados_crudo = (database.get_settings().get("ig_hashtags_ya_contados") or "").strip()
            try:
                contados = set(json.loads(contados_crudo)) if contados_crudo else set()
            except (ValueError, TypeError):
                contados = set()
            if marca not in contados:
                registrar_rendimiento_hashtags(hashtags_pieza, likes=likes, comentarios=comentarios)
                contados.add(marca)
                database.update_settings({"ig_hashtags_ya_contados": json.dumps(sorted(contados))})

        if comentarios > 0:
            res = autopilot_dispatcher.registrar_resultado_mercado(
                p.get("nicho") or "(general)", p["gancho"], "instagram",
                comentarios, "respondió",
                f"[{marca}] {comentarios} comentario(s) reales y {likes} like(s) en IG.",
                ruta=ruta, dry_run=dry_run,
            )
            if res.get("escrito") or res.get("dry_run"):
                registradas += 1
                ya_registradas.add(marca)
        elif dt_pub <= corte:
            res = autopilot_dispatcher.registrar_resultado_mercado(
                p.get("nicho") or "(general)", p["gancho"], "instagram",
                1, "silencio",
                f"[{marca}] Sin comentarios tras {dias_silencio} días ({likes} like(s)).",
                ruta=ruta, dry_run=dry_run,
            )
            if res.get("escrito") or res.get("dry_run"):
                registradas += 1
                ya_registradas.add(marca)
    return {"registradas": registradas, "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publicador oficial Instagram Graph API de El Socio.")
    parser.add_argument("--status", action="store_true", help="Muestra estado seguro sin secretos.")
    parser.add_argument("--publicar-id", type=int, default=0, help="Publica una pieza generada por ID.")
    parser.add_argument("--ciclo", action="store_true", help="Corre ciclo autónomo de publicación.")
    parser.add_argument("--modo", choices=["", "autonomo", "preview"], default="",
                        help="Cambia el interruptor global de publicación.")
    parser.add_argument("--dry-run", action="store_true", help="Valida sin llamar a Meta ni tocar BD.")
    args = parser.parse_args(argv)

    if args.modo:
        if args.dry_run:
            print(json.dumps({"dry_run": True, "modo": args.modo}, ensure_ascii=False, indent=2))
            return 0
        activo = cambiar_modo_autonomo(args.modo == "autonomo")
        print(json.dumps({"auto_publish": activo}, ensure_ascii=False, indent=2))
        return 0

    if args.status:
        print(json.dumps(estado_ig(), ensure_ascii=False, indent=2))
        return 0

    if not args.dry_run:
        database.init_db()

    if args.publicar_id > 0:
        res = publicar_pieza_ig(args.publicar_id, dry_run=args.dry_run)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if (res.get("publicado") or res.get("dry_run")) else 1

    res = ciclo_publicacion_autonoma(dry_run=args.dry_run)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

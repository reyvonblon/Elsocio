#!/usr/bin/env python3
"""Servidor local en el puerto 8787 para el Panel de Control de El Socio.

Permite ver el preview real (PNG/JPG o `<video>` MP4 con voz humana) desde el Mac
o el celular en el WiFi de casa, cambiar entre Modo Autónomo y Modo Preview con
un toque, y aprobar/publicar/descartar piezas.

Seguridad en código:
  - Cero secretos leídos para pintar HTML (todo pasa por `html.escape()`).
  - `/media/<id>` sirve ÚNICAMENTE archivos registrados en `content_queue` que
    vivan dentro de `redes/` (imposible leer `.env` ni otros archivos por ruta).
"""

from __future__ import annotations

import argparse
import mimetypes
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REDES_ROOT = (PROJECT_ROOT / "redes").resolve()

if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import content_manager  # noqa: E402
import database  # noqa: E402
import ig_publisher  # noqa: E402
import panel_mensajes  # noqa: E402


def _archivo_seguro_de_pieza(content_id: int) -> Path | None:
    pieza = database.get_content(content_id)
    if not pieza or not pieza.get("archivo"):
        return None
    ruta = Path(str(pieza["archivo"])).resolve()
    try:
        ruta.relative_to(REDES_ROOT)
    except ValueError:
        return None
    if not ruta.is_file():
        return None
    if ruta.suffix.lower() not in (".png", ".jpg", ".jpeg", ".mp4"):
        return None
    return ruta


def ejecutar_accion_panel(accion: str, form: dict[str, str]) -> str:
    database.init_db()
    if accion == "toggle_modo":
        activo = form.get("activo") == "1"
        ig_publisher.cambiar_modo_autonomo(activo)
        return "Modo Autónomo ACTIVADO: El Socio publicará solo." if activo else "Modo Preview ACTIVADO: esperará tu clic."

    if accion == "guardar_claves":
        cambios: dict[str, str] = {}
        notas: list[str] = []
        ak = (form.get("anthropic_key") or "").strip()
        if ak:
            cambios["anthropic_api_key"] = ak
            notas.append("Cerebro Anthropic conectado")
        ig_tok = (form.get("ig_token") or "").strip()
        if ig_tok:
            cambios["ig_access_token"] = ig_tok
            database.update_settings(cambios)
            cambios = {}
            try:
                desc = ig_publisher.descubrir_cuenta_ig(ig_tok)
                cuenta = f"@{desc['username']}" if desc.get("username") else desc["user_id"]
                notas.append(f"Instagram conectado ({cuenta}) con auto-renovación activa")
            except ig_publisher.ErrorIG as exc:
                notas.append(f"Token IG guardado, pero Meta respondió: {exc}")
        if cambios:
            database.update_settings(cambios)
        return " · ".join(notas) if notas else "No pegaste ninguna clave nueva."

    try:
        cid = int(form.get("id") or "0")
    except ValueError:
        return "ID de pieza inválido."
    if cid <= 0:
        return "Falta el ID de la pieza."

    if accion == "generar":
        res = content_manager.generar(cid)
        return f"Pieza #{cid} renderizada." if res.get("generado") else f"Error al renderizar #{cid}: {res.get('error')}"
    if accion == "publicar_ig":
        res = ig_publisher.publicar_pieza_ig(cid)
        return f"Pieza #{cid} publicada en Instagram ({res.get('ig_media_id')})." if res.get("publicado") else f"No se publicó #{cid}: {res.get('error')}"
    if accion == "descartar":
        res = content_manager.descartar(cid, nota="descartada desde el panel 8787")
        return f"Pieza #{cid} descartada." if res.get("descartado") else f"No se pudo descartar #{cid}."
    return "Acción desconocida."


class ManejadorPanel(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: ANN002
        return  # Silencioso en segundo plano

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        ruta = parsed.path

        if ruta in ("/", "/mensajes.html"):
            database.init_db()
            qs = urllib.parse.parse_qs(parsed.query)
            aviso = (qs.get("aviso") or [""])[0][:240]
            cuerpo = panel_mensajes.render(
                database.list_landing_messages(limit=200),
                database.list_content(limit=80),
                estado_motor=panel_mensajes.construir_estado_motor(aviso=aviso),
                interactivo=True,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cuerpo)
            return

        if ruta.startswith("/media/"):
            parte_id = ruta.removeprefix("/media/").strip("/")
            if not parte_id.isdigit():
                self.send_error(404)
                return
            archivo = _archivo_seguro_de_pieza(int(parte_id))
            if not archivo:
                self.send_error(404)
                return
            datos = archivo.read_bytes()
            mime = mimetypes.guess_type(archivo.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)
            return

        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/accion":
            self.send_error(404)
            return
        largo = min(4096, max(0, int(self.headers.get("Content-Length") or "0")))
        crudo = self.rfile.read(largo).decode("utf-8", errors="replace")
        pares = urllib.parse.parse_qs(crudo)
        form = {k: (v[0] if v else "") for k, v in pares.items()}
        aviso = ejecutar_accion_panel(form.get("accion", ""), form)
        destino = "/mensajes.html?" + urllib.parse.urlencode({"aviso": aviso})
        self.send_response(303)
        self.send_header("Location", destino)
        self.end_headers()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Servidor local del panel de El Socio (puerto 8787).")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--dry-run", action="store_true", help="Valida configuración sin abrir el puerto.")
    args = parser.parse_args(argv)

    if args.dry_run:
        print(f'{{"ok": true, "dry_run": true, "bind": "{args.host}:{args.port}"}}')
        return 0

    database.init_db()
    servidor = ThreadingHTTPServer((args.host, args.port), ManejadorPanel)
    print(f"Panel de El Socio activo en http://{args.host}:{args.port}/mensajes.html")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

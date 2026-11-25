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
import json
import mimetypes
import sys
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REDES_ROOT = (PROJECT_ROOT / "redes").resolve()
PANEL_ROOT = (PROJECT_ROOT / "panel").resolve()

if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import content_manager  # noqa: E402
import database  # noqa: E402
import ig_publisher  # noqa: E402
import panel_api  # noqa: E402
import panel_mensajes  # noqa: E402
import socio_chat  # noqa: E402


def _archivo_seguro_de_pieza(content_id: int, lamina: int = 0) -> Path | None:
    """`lamina=0` → el archivo principal. `lamina>0` → esa lámina del carrusel (1-based)."""
    pieza = database.get_content(content_id)
    if not pieza or not pieza.get("archivo"):
        return None
    if lamina > 0:
        if str(pieza.get("tipo") or "").strip().lower() != "carrusel":
            return None
        laminas = content_manager.archivos_carrusel(pieza["archivo"])
        if lamina > len(laminas):
            return None
        ruta = laminas[lamina - 1].resolve()
    else:
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


_MIME_ESTATICOS = {".html": "text/html; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg",
                   ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".webmanifest": "application/manifest+json"}


def _archivo_estatico_de_panel(ruta_rel: str) -> Path | None:
    """Solo sirve archivos que vivan de verdad dentro de `panel/` (nunca `.env` ni nada fuera)."""
    ruta = (PANEL_ROOT / ruta_rel.lstrip("/")).resolve()
    try:
        ruta.relative_to(PANEL_ROOT)
    except ValueError:
        return None
    if not ruta.is_file() or ruta.suffix.lower() not in _MIME_ESTATICOS:
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

    if accion == "preguntar":
        pregunta = (form.get("pregunta") or "").strip()
        if not pregunta:
            return "Escribe algo en el cuadro antes de preguntar."
        respuesta = socio_chat.responder(pregunta)
        database.update_settings({
            "chat_ultima_pregunta": pregunta,
            "chat_ultima_respuesta": respuesta,
            "chat_ultima_fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        return "Te respondió El Socio, bajá a 'Pregúntale a El Socio' para verlo."

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
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # noqa: ANN002
        return  # Silencioso en segundo plano

    def _servir_media(self, parte_id: str, solo_headers: bool = False) -> None:
        cid_txt, _, lamina_txt = parte_id.partition("_")
        if not cid_txt.isdigit() or (lamina_txt and not lamina_txt.isdigit()):
            self.send_error(404)
            return
        archivo = _archivo_seguro_de_pieza(int(cid_txt), int(lamina_txt or 0))
        if not archivo:
            self.send_error(404)
            return
        datos = archivo.read_bytes()
        total = len(datos)
        mime = mimetypes.guess_type(archivo.name)[0] or "application/octet-stream"
        rango = (self.headers.get("Range") or "").strip()
        inicio, fin = 0, total - 1
        es_parcial = False
        if rango.startswith("bytes=") and total > 0:
            parte = rango[6:].split(",", 1)[0].strip()
            if "-" in parte:
                izq, _, der = parte.partition("-")
                try:
                    if not izq and der:
                        inicio = max(0, total - int(der))
                    elif izq:
                        inicio = int(izq)
                        fin = int(der) if der else total - 1
                    fin = min(fin, total - 1)
                    if inicio > fin or inicio >= total:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{total}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    es_parcial = True
                except ValueError:
                    es_parcial = False
        tramo = datos[inicio:fin + 1] if es_parcial else datos
        self.send_response(206 if es_parcial else 200)
        self.send_header("Content-Type", mime)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "private, max-age=60")
        self.send_header("Content-Disposition", f'inline; filename="{archivo.name}"')
        if es_parcial:
            self.send_header("Content-Range", f"bytes {inicio}-{fin}/{total}")
        self.send_header("Content-Length", str(len(tramo)))
        self.end_headers()
        if solo_headers:
            return
        try:
            self.wfile.write(tramo)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_HEAD(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        ruta = parsed.path
        if ruta.startswith("/media/"):
            self._servir_media(ruta.removeprefix("/media/").strip("/"), solo_headers=True)
            return
        if ruta in ("/", "/mensajes.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_error(404)

    def _responder_json(self, cuerpo_obj: object, status: int = 200) -> None:
        cuerpo = json.dumps(cuerpo_obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(cuerpo)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _leer_json_post(self) -> dict:
        largo = min(1 << 16, max(0, int(self.headers.get("Content-Length") or "0")))
        crudo = self.rfile.read(largo).decode("utf-8", errors="replace")
        try:
            datos = json.loads(crudo) if crudo.strip() else {}
            return datos if isinstance(datos, dict) else {}
        except json.JSONDecodeError:
            return {}

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
            self._servir_media(ruta.removeprefix("/media/").strip("/"), solo_headers=False)
            return

        if ruta == "/api/estado":
            database.init_db()
            self._responder_json(panel_api.construir_estado_monitor())
            return

        if ruta == "/monitor.html" or ruta.startswith("/assets/"):
            archivo = _archivo_estatico_de_panel(ruta)
            if not archivo:
                self.send_error(404)
                return
            datos = archivo.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", _MIME_ESTATICOS[archivo.suffix.lower()])
            self.send_header("Content-Length", str(len(datos)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(datos)
            return

        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/preguntar":
            database.init_db()
            datos = self._leer_json_post()
            pregunta = str(datos.get("pregunta") or "").strip()
            if not pregunta:
                self._responder_json({"respuesta": "Escribe algo en el cuadro antes de preguntar."}, 400)
                return
            self._responder_json({"respuesta": panel_api.responder_pregunta(pregunta)})
            return

        if self.path == "/api/accion":
            database.init_db()
            datos = self._leer_json_post()
            accion = str(datos.get("accion") or "")
            if accion in ("pausar_lead", "reactivar_lead"):
                try:
                    lead_id = int(datos.get("lead_id"))
                except (TypeError, ValueError):
                    self._responder_json({"error": "lead_id inválido"}, 400)
                    return
                resultado = panel_api.accion_pausar_lead(lead_id, pausado=(accion == "pausar_lead"))
                self._responder_json(resultado)
                return
            if accion == "reintentar_ig":
                try:
                    content_id = int(datos.get("content_id"))
                except (TypeError, ValueError):
                    self._responder_json({"ok": False, "error": "content_id inválido"}, 400)
                    return
                self._responder_json(panel_api.accion_reintentar_ig(content_id))
                return
            self._responder_json({"error": "acción desconocida"}, 404)
            return

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
        self.send_header("Content-Length", "0")
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

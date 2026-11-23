#!/usr/bin/env python3
"""Cola de contenido de El Socio (Instagram). Solo stdlib, cero llamadas a la API.

Encola piezas, las genera con los scripts de `redes/`, y registra el resultado real
de una publicación en `contexto/RESULTADOS_MERCADO.md`.

Todo gancho, guion y caption pasa por `sales_agent.revisar_guarda_precios()` ANTES
de encolarse o renderizarse. Esa guarda vive en código a propósito: aquí no hay
modelo que pueda fallar, pero tampoco se confía en quien escribe el texto.

Uso:
    python3 scripts/content_manager.py listar
    python3 scripts/content_manager.py encolar --tipo post --gancho "..." --caption "..."
    python3 scripts/content_manager.py generar --id 3
    python3 scripts/content_manager.py publicar --id 3 --resultado respondió --cantidad 1
    python3 scripts/content_manager.py descartar --id 3 --nota "no convence"

`--dry-run` valida y muestra lo que haría: no escribe en la BD, no renderiza
y no toca RESULTADOS_MERCADO.md.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import autopilot_dispatcher  # noqa: E402
import database  # noqa: E402
import sales_agent  # noqa: E402

REDES_DIR = PROJECT_ROOT / "redes"
GENERAR_POST = REDES_DIR / "generar_post.sh"
GENERAR_VIDEO = REDES_DIR / "generar_video.sh"

# Un reel de El Socio: gancho en pantalla desde el frame 1, bloques de ~2 s, cierre seco.
# Los tiempos y la forma salen de `contexto/guia-estilo-video.md`.
MAX_BLOQUES = 5
TIMEOUT_RENDER = 900  # segundos; el render por frames en este Mac es lento a propósito


class GuardaBloqueada(Exception):
    """El texto de la pieza no puede salir. Lleva los motivos exactos."""

    def __init__(self, motivos: list[str]) -> None:
        super().__init__("; ".join(motivos))
        self.motivos = motivos


def revisar_pieza(gancho: str, guion: str = "", caption: str = "") -> list[str]:
    """Misma guarda que usa el agente de ventas, aplicada al contenido de redes.

    Devuelve los motivos por los que NO puede salir. Vacío = puede salir.
    """
    return sales_agent.revisar_guarda_precios(gancho, guion, caption)


def _exigir_guarda(gancho: str, guion: str, caption: str) -> None:
    motivos = revisar_pieza(gancho, guion, caption)
    if motivos:
        raise GuardaBloqueada(motivos)


def encolar(
    *, tipo: str, gancho: str, guion: str = "", caption: str = "",
    nicho: str = "", nota: str = "", dry_run: bool = False,
) -> dict:
    """Mete una pieza en la cola. La guarda corre ANTES de tocar la BD."""
    _exigir_guarda(gancho, guion, caption)
    if dry_run:
        return {"encolado": False, "dry_run": True, "tipo": tipo, "gancho": gancho}
    content_id = database.enqueue_content(
        tipo=tipo, gancho=gancho, guion=guion, caption=caption, nicho=nicho, nota=nota,
    )
    return {"encolado": True, "id": content_id}


def _bloques_de(guion: str) -> list[str]:
    """El guion se parte en bloques por línea. Cada bloque es un plano de ~2 s."""
    bloques = [l.strip() for l in (guion or "").splitlines() if l.strip()]
    return bloques[:MAX_BLOQUES]


def generar(content_id: int, *, dry_run: bool = False) -> dict:
    """Renderiza la pieza con los scripts de `redes/` y la deja en `generado`.

    La guarda se vuelve a correr aquí: entre encolar y generar alguien pudo editar
    la fila a mano en la BD.
    """
    pieza = database.get_content(content_id)
    if not pieza:
        return {"generado": False, "error": f"no existe la pieza {content_id}"}
    if pieza["estado"] in ("publicado", "descartado"):
        return {"generado": False, "error": f"la pieza está en '{pieza['estado']}'"}

    _exigir_guarda(pieza["gancho"], pieza["guion"] or "", pieza["caption"] or "")

    nombre = f"content_{content_id:04d}"
    if pieza["tipo"] == "post":
        cmd = [str(GENERAR_POST), pieza["gancho"], nombre]
        salida = REDES_DIR / "posts" / f"{nombre}.png"
    else:
        props = json.dumps({
            "gancho": pieza["gancho"],
            "bloques": _bloques_de(pieza["guion"]),
            "cierre": (pieza["caption"] or "Cuéntanos tu problema · link en bio").strip(),
        }, ensure_ascii=False)
        cmd = [str(GENERAR_VIDEO), "--reel", props, nombre]
        salida = REDES_DIR / "video-logo" / "out" / f"{nombre}.mp4"

    if dry_run:
        return {"generado": False, "dry_run": True, "comando": cmd, "salida": str(salida)}

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_RENDER)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"generado": False, "error": str(exc)[:200]}
    if proc.returncode != 0:
        return {"generado": False, "error": (proc.stderr or proc.stdout or "")[-400:]}

    database.update_content(content_id, estado="generado", archivo=str(salida))
    return {"generado": True, "id": content_id, "archivo": str(salida)}


def publicar(
    content_id: int, *, resultado: str, cantidad: int = 1, nota: str = "",
    dry_run: bool = False,
) -> dict:
    """Marca la pieza como publicada y registra el resultado REAL en el archivo de mercado.

    Solo se llama cuando la publicación de verdad ocurrió y ya se sabe qué pasó.
    No inventa nada: `resultado` y `cantidad` los pone quien vio el dato.
    """
    pieza = database.get_content(content_id)
    if not pieza:
        return {"publicado": False, "error": f"no existe la pieza {content_id}"}
    if pieza["estado"] == "publicado":
        return {"publicado": False, "error": "esa pieza ya estaba publicada"}

    registro = autopilot_dispatcher.registrar_resultado_mercado(
        pieza["nicho"] or "(general)",
        pieza["gancho"],
        "instagram",
        cantidad,
        resultado,
        nota or f"pieza {pieza['tipo']} #{content_id}",
        dry_run=dry_run,
    )
    if not dry_run and not registro.get("escrito"):
        return {"publicado": False, "error": registro.get("error", "no se pudo registrar")}
    if dry_run:
        return {"publicado": False, "dry_run": True, "fila": registro.get("fila", "")}

    database.update_content(content_id, estado="publicado", nota=nota)
    return {"publicado": True, "id": content_id, "fila": registro.get("fila", "")}


def descartar(content_id: int, *, nota: str = "", dry_run: bool = False) -> dict:
    pieza = database.get_content(content_id)
    if not pieza:
        return {"descartado": False, "error": f"no existe la pieza {content_id}"}
    if dry_run:
        return {"descartado": False, "dry_run": True, "id": content_id}
    database.update_content(content_id, estado="descartado", nota=nota)
    return {"descartado": True, "id": content_id}


def listar(estado: str = "") -> list[dict]:
    return database.list_content(estado=estado)


# ------------------------------------------------------------------ línea de comandos

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cola de contenido de El Socio")
    parser.add_argument("--dry-run", action="store_true",
                        help="valida y muestra, sin tocar BD ni archivos")
    sub = parser.add_subparsers(dest="accion", required=True)

    p_list = sub.add_parser("listar")
    p_list.add_argument("--estado", default="")

    p_enc = sub.add_parser("encolar")
    p_enc.add_argument("--tipo", choices=database.CONTENT_TIPOS, default="post")
    p_enc.add_argument("--gancho", required=True)
    p_enc.add_argument("--guion", default="")
    p_enc.add_argument("--caption", default="")
    p_enc.add_argument("--nicho", default="")
    p_enc.add_argument("--nota", default="")

    p_gen = sub.add_parser("generar")
    p_gen.add_argument("--id", type=int, required=True)

    p_pub = sub.add_parser("publicar")
    p_pub.add_argument("--id", type=int, required=True)
    p_pub.add_argument("--resultado", required=True)
    p_pub.add_argument("--cantidad", type=int, default=1)
    p_pub.add_argument("--nota", default="")

    p_des = sub.add_parser("descartar")
    p_des.add_argument("--id", type=int, required=True)
    p_des.add_argument("--nota", default="")

    args = parser.parse_args(argv)
    if not args.dry_run:
        database.init_db()

    try:
        if args.accion == "listar":
            piezas = listar(args.estado)
            if not piezas:
                print("La cola está vacía.")
            for p in piezas:
                print(f"#{p['id']:>3} [{p['estado']:<10}] {p['tipo']:<5} · {p['gancho'][:60]}")
            return 0

        if args.accion == "encolar":
            res = encolar(tipo=args.tipo, gancho=args.gancho, guion=args.guion,
                          caption=args.caption, nicho=args.nicho, nota=args.nota,
                          dry_run=args.dry_run)
        elif args.accion == "generar":
            res = generar(args.id, dry_run=args.dry_run)
        elif args.accion == "publicar":
            res = publicar(args.id, resultado=args.resultado, cantidad=args.cantidad,
                           nota=args.nota, dry_run=args.dry_run)
        else:
            res = descartar(args.id, nota=args.nota, dry_run=args.dry_run)
    except GuardaBloqueada as exc:
        print("BLOQUEADO por la guarda de precios:")
        for motivo in exc.motivos:
            print(f"  - {motivo}")
        return 2

    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if not res.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())

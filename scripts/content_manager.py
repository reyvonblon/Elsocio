#!/usr/bin/env python3
"""Cola de contenido de El Socio (Instagram). Solo stdlib, cero llamadas a la API.

Encola piezas, las genera con los scripts de `redes/`, y registra el resultado real
de una publicación en `contexto/RESULTADOS_MERCADO.md`.

Todo gancho, guion, caption Y ETIQUETA pasa por `sales_agent.revisar_guarda_precios()`
ANTES de encolarse o renderizarse. Esa guarda vive en código a propósito: aquí no hay
modelo que pueda fallar, pero tampoco se confía en quien escribe el texto.

Uso:
    python3 scripts/content_manager.py listar
    python3 scripts/content_manager.py encolar --tipo post --gancho "..." --caption "..."
    python3 scripts/content_manager.py encolar --tipo video --gancho "..." --guion "a\nb" \
        --escena flujo --etiquetas "CUENTAS" "RESOLVEMOS" "ENTREGADO"
    python3 scripts/content_manager.py generar --id 3 --escena agenda
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

# Escenas isométricas disponibles en `redes/video-logo/src/EscenasIsometricas.tsx`.
# Si se agrega una allá, se agrega aquí: es la única lista que valida la línea de comandos.
ESCENAS = ("contraste", "flujo", "espacio3d", "agenda")
ESCENA_DEFECTO = "contraste"

# Las etiquetas son tooltips dentro de la escena: 2-3 palabras, nunca una frase.
# Cuatro es el máximo que consume cualquiera de las escenas.
MAX_ETIQUETAS = 4
MAX_LARGO_ETIQUETA = 22

# La configuración de la escena se guarda DENTRO de `nota`, en una última línea marcada.
# Por qué y no una columna nueva: `content_queue` ya tiene filas y el esquema se crea con
# CREATE TABLE IF NOT EXISTS — agregar columnas obligaría a migrar una BD viva para una
# comodidad. La nota humana se conserva intacta; esta línea se separa al leerla.
_MARCA_REEL = "[reel]"
_SEP_CAMPOS = ";"
_SEP_ETIQUETAS = "|"


class GuardaBloqueada(Exception):
    """El texto de la pieza no puede salir. Lleva los motivos exactos."""

    def __init__(self, motivos: list[str]) -> None:
        super().__init__("; ".join(motivos))
        self.motivos = motivos


# ------------------------------------------------------- escena y etiquetas del reel

def normalizar_escena(escena: str | None, *, tolerante: bool = False) -> str:
    """Valida el nombre de la escena. `tolerante` lo usa la lectura de una nota editada a mano."""
    valor = (escena or "").strip().lower()
    if not valor:
        return ESCENA_DEFECTO
    if valor not in ESCENAS:
        if tolerante:
            return ESCENA_DEFECTO
        raise ValueError(f"escena inválida: {escena!r} (opciones: {', '.join(ESCENAS)})")
    return valor


def normalizar_etiquetas(etiquetas: list[str] | None) -> list[str]:
    """Deja las etiquetas listas para viajar en `nota` y en los props de Remotion."""
    limpias: list[str] = []
    for bruta in etiquetas or []:
        # Colapsa espacios y mata saltos de línea: una etiqueta es de una sola línea.
        texto = " ".join(str(bruta).split())
        if not texto:
            continue
        if _SEP_ETIQUETAS in texto or _SEP_CAMPOS in texto:
            raise ValueError(
                f"una etiqueta no puede llevar '{_SEP_ETIQUETAS}' ni '{_SEP_CAMPOS}': {texto!r}")
        if len(texto) > MAX_LARGO_ETIQUETA:
            raise ValueError(
                f"etiqueta demasiado larga (máx {MAX_LARGO_ETIQUETA} caracteres): {texto!r}")
        limpias.append(texto)
    return limpias[:MAX_ETIQUETAS]


def nota_humana(nota: str | None) -> str:
    """La nota tal como la escribió una persona, sin la línea de configuración."""
    lineas = [l for l in (nota or "").splitlines() if not l.strip().startswith(_MARCA_REEL)]
    return "\n".join(lineas).strip()


def componer_nota(nota: str | None, escena: str, etiquetas: list[str]) -> str:
    """Mete escena y etiquetas en `nota` sin pisar lo que escribió una persona."""
    humano = nota_humana(nota)
    campos: list[str] = []
    if escena and escena != ESCENA_DEFECTO:
        campos.append(f"escena={escena}")
    if etiquetas:
        campos.append("etiquetas=" + _SEP_ETIQUETAS.join(etiquetas))
    if not campos:
        return humano
    linea = f"{_MARCA_REEL} " + f"{_SEP_CAMPOS} ".join(campos)
    return f"{humano}\n{linea}" if humano else linea


def leer_reel(nota: str | None) -> tuple[str, list[str]]:
    """Saca (escena, etiquetas) de una nota. Lo que no entienda, lo deja en los valores por defecto."""
    escena = ESCENA_DEFECTO
    etiquetas: list[str] = []
    for linea in (nota or "").splitlines():
        linea = linea.strip()
        if not linea.startswith(_MARCA_REEL):
            continue
        for campo in linea[len(_MARCA_REEL):].split(_SEP_CAMPOS):
            clave, _, valor = campo.partition("=")
            clave, valor = clave.strip().lower(), valor.strip()
            if clave == "escena":
                escena = normalizar_escena(valor, tolerante=True)
            elif clave == "etiquetas":
                crudas = [t.strip() for t in valor.split(_SEP_ETIQUETAS)]
                etiquetas = [t for t in crudas if t][:MAX_ETIQUETAS]
    return escena, etiquetas


# ------------------------------------------------------------------ la guarda de precios

def revisar_pieza(
    gancho: str, guion: str = "", caption: str = "", etiquetas: list[str] | None = None,
) -> list[str]:
    """Misma guarda que usa el agente de ventas, aplicada al contenido de redes.

    Las etiquetas entran igual que el resto: son texto que acaba QUEMADO en el video,
    y un "desde 50.000" dentro de un tooltip es exactamente el mismo problema.

    Devuelve los motivos por los que NO puede salir. Vacío = puede salir.
    """
    return sales_agent.revisar_guarda_precios(gancho, guion, caption, *(etiquetas or []))


def _exigir_guarda(
    gancho: str, guion: str, caption: str, etiquetas: list[str] | None = None,
) -> None:
    motivos = revisar_pieza(gancho, guion, caption, etiquetas)
    if motivos:
        raise GuardaBloqueada(motivos)


# ------------------------------------------------------------------ acciones de la cola

def encolar(
    *, tipo: str, gancho: str, guion: str = "", caption: str = "",
    nicho: str = "", nota: str = "", escena: str = "", etiquetas: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Mete una pieza en la cola. La guarda corre ANTES de tocar la BD."""
    escena_ok = normalizar_escena(escena)
    etiquetas_ok = normalizar_etiquetas(etiquetas)
    _exigir_guarda(gancho, guion, caption, etiquetas_ok)
    nota_final = componer_nota(nota, escena_ok, etiquetas_ok)
    if dry_run:
        return {
            "encolado": False, "dry_run": True, "tipo": tipo, "gancho": gancho,
            "escena": escena_ok, "etiquetas": etiquetas_ok,
        }
    content_id = database.enqueue_content(
        tipo=tipo, gancho=gancho, guion=guion, caption=caption, nicho=nicho, nota=nota_final,
    )
    return {"encolado": True, "id": content_id, "escena": escena_ok, "etiquetas": etiquetas_ok}


def _bloques_de(guion: str) -> list[str]:
    """El guion se parte en bloques por línea. Cada bloque es un plano de ~2 s."""
    bloques = [l.strip() for l in (guion or "").splitlines() if l.strip()]
    return bloques[:MAX_BLOQUES]


def generar(
    content_id: int, *, escena: str = "", etiquetas: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Renderiza la pieza con los scripts de `redes/` y la deja en `generado`.

    `escena` y `etiquetas` mandan sobre lo guardado en la nota, y se vuelven a guardar:
    el registro tiene que decir lo que de verdad se renderizó.

    La guarda se vuelve a correr aquí: entre encolar y generar alguien pudo editar
    la fila a mano en la BD.
    """
    pieza = database.get_content(content_id)
    if not pieza:
        return {"generado": False, "error": f"no existe la pieza {content_id}"}
    if pieza["estado"] in ("publicado", "descartado"):
        return {"generado": False, "error": f"la pieza está en '{pieza['estado']}'"}

    escena_nota, etiquetas_nota = leer_reel(pieza["nota"])
    escena_ok = normalizar_escena(escena) if escena else escena_nota
    etiquetas_ok = (
        normalizar_etiquetas(etiquetas) if etiquetas is not None
        else normalizar_etiquetas(etiquetas_nota)
    )

    _exigir_guarda(
        pieza["gancho"], pieza["guion"] or "", pieza["caption"] or "", etiquetas_ok)

    nombre = f"content_{content_id:04d}"
    if pieza["tipo"] == "post":
        cmd = [str(GENERAR_POST), pieza["gancho"], nombre]
        salida = REDES_DIR / "posts" / f"{nombre}.png"
    else:
        cap_crudo = (pieza["caption"] or "").strip()
        cierre_reel = (
            cap_crudo if (cap_crudo and "\n" not in cap_crudo and len(cap_crudo) <= 58)
            else "Cuéntanos tu problema · link en bio"
        )
        props = json.dumps({
            "gancho": pieza["gancho"],
            "bloques": _bloques_de(pieza["guion"]),
            "cierre": cierre_reel,
            "escena": escena_ok,
            "etiquetas": etiquetas_ok,
        }, ensure_ascii=False)
        cmd = [str(GENERAR_VIDEO), "--reel", props, nombre]
        salida = REDES_DIR / "video-logo" / "out" / f"{nombre}.mp4"

    if dry_run:
        return {
            "generado": False, "dry_run": True, "comando": cmd, "salida": str(salida),
            "escena": escena_ok, "etiquetas": etiquetas_ok,
        }

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_RENDER)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"generado": False, "error": str(exc)[:200]}
    if proc.returncode != 0:
        return {"generado": False, "error": (proc.stderr or proc.stdout or "")[-400:]}

    nota_final = componer_nota(pieza["nota"], escena_ok, etiquetas_ok)
    database.update_content(
        content_id, estado="generado", archivo=str(salida),
        nota=nota_final if nota_final != (pieza["nota"] or "") else None,
    )
    return {
        "generado": True, "id": content_id, "archivo": str(salida),
        "escena": escena_ok, "etiquetas": etiquetas_ok,
    }


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

    # Publicar sin nota nueva NO borra la que ya estaba (ni la configuración de la escena):
    # `update_content` solo toca el campo si se le pasa algo distinto de None.
    nota_final = componer_nota(nota, *leer_reel(pieza["nota"])) if nota else None
    database.update_content(content_id, estado="publicado", nota=nota_final)
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
    p_enc.add_argument("--escena", choices=ESCENAS, default="",
                       help="escena isométrica del reel (solo aplica a --tipo video)")
    p_enc.add_argument("--etiquetas", nargs="*", default=None, metavar="TEXTO",
                       help=f"tooltips de la escena, máx {MAX_ETIQUETAS}, sin cifras")

    p_gen = sub.add_parser("generar")
    p_gen.add_argument("--id", type=int, required=True)
    p_gen.add_argument("--escena", choices=ESCENAS, default="",
                       help="manda sobre la escena guardada al encolar")
    p_gen.add_argument("--etiquetas", nargs="*", default=None, metavar="TEXTO",
                       help="manda sobre las etiquetas guardadas al encolar")

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
                escena, etiquetas = leer_reel(p["nota"])
                extra = f" · {escena}" if p["tipo"] == "video" else ""
                if etiquetas:
                    extra += f" · {', '.join(etiquetas)}"
                print(f"#{p['id']:>3} [{p['estado']:<10}] {p['tipo']:<5} · "
                      f"{p['gancho'][:50]}{extra}")
            return 0

        if args.accion == "encolar":
            res = encolar(tipo=args.tipo, gancho=args.gancho, guion=args.guion,
                          caption=args.caption, nicho=args.nicho, nota=args.nota,
                          escena=args.escena, etiquetas=args.etiquetas,
                          dry_run=args.dry_run)
        elif args.accion == "generar":
            res = generar(args.id, escena=args.escena, etiquetas=args.etiquetas,
                          dry_run=args.dry_run)
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
    except ValueError as exc:
        print(f"Dato inválido: {exc}")
        return 2

    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if not res.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())

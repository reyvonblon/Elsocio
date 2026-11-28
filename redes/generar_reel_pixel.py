#!/usr/bin/env python3
"""Genera un capítulo del reel en pixel art, CON voz neuronal, y lo arma en mp4.

    python3 redes/generar_reel_pixel.py taller obra azotea

La voz sale de `scripts/voice_engine.py` en su motor `edge_neural`: 0 USD y 0 claves de API
(el saldo agotado es el del cerebro que escribe guiones, no el de la voz).

Por qué frase por frase y no de un tirón: el motor de voz parte el guion con su propia
estructura de gancho/bloques/cierre, que no coincide con las frases de este formato. Midiendo
cada frase por separado, el subtítulo palabra por palabra cae exacto sobre lo que se oye.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VIDEO = RAIZ / "redes" / "video-logo"
VOZ_ENGINE = RAIZ / "scripts" / "voice_engine.py"
SALIDA = VIDEO / "out" / "pixel"

PAUSA = 0.24          # silencio entre frases, en segundos
TAG_FINAL = "Con El Socio."   # se oye sobre la tarjeta de marca; no lleva subtítulo


def frases_del_capitulo(cap: str) -> list[str]:
    """Lee las frases del propio ReelPixel.tsx: una sola fuente de verdad."""
    src = (VIDEO / "src" / "ReelPixel.tsx").read_text(encoding="utf-8")
    marca = {"taller": "CAP_TALLER", "obra": "CAP_OBRA", "azotea": "CAP_AZOTEA"}[cap]
    bloque = src[src.index(f"const {marca}: Capitulo"):]
    ini = bloque.index("frases: [")
    return re.findall(r'texto:\s*"([^"]+)"', bloque[ini:bloque.index("]", ini)])


def duracion(ruta: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(ruta)],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def locutar(texto: str, destino: Path, intentos: int = 4) -> float:
    """El TTS corta la conexión cada tanto (ya tumbó reels antes): se reintenta con espera
    creciente, y lo ya locutado se reutiliza para que un corte no obligue a repetirlo todo."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and destino.stat().st_size > 2000:
        return duracion(destino)
    ultimo = ""
    for intento in range(intentos):
        r = subprocess.run(
            [sys.executable, str(VOZ_ENGINE), "--texto", texto, "--out", str(destino)],
            capture_output=True, text=True)
        if r.returncode == 0 and destino.exists() and destino.stat().st_size > 2000:
            return duracion(destino)
        ultimo = r.stderr[-300:]
        destino.unlink(missing_ok=True)
        if intento < intentos - 1:
            time.sleep(4 * (intento + 1))
    raise RuntimeError(f"TTS falló para «{texto}»: {ultimo}")


def pista_de_voz(trozos: list[Path], destino: Path) -> None:
    """Une las frases con una pausa detrás de cada una y masteriza a -14 LUFS."""
    entradas: list[str] = []
    for t in trozos:
        entradas += ["-i", str(t)]
    cadena = "".join(f"[{k}:a]apad=pad_dur={PAUSA}[a{k}];" for k in range(len(trozos)))
    cadena += "".join(f"[a{k}]" for k in range(len(trozos)))
    cadena += f"concat=n={len(trozos)}:v=0:a=1,loudnorm=I=-14:TP=-1.5:LRA=11[out]"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *entradas,
         "-filter_complex", cadena, "-map", "[out]", "-c:a", "aac", "-b:a", "160k", str(destino)],
        check=True)


def generar(cap: str) -> Path:
    print(f"\n=== capítulo: {cap} ===")
    frases = frases_del_capitulo(cap)
    tmp = VIDEO / "out" / f"voz_{cap}"
    tmp.mkdir(parents=True, exist_ok=True)

    tiempos: list[float] = []
    trozos: list[Path] = []
    for k, texto in enumerate(frases):
        # El nombre lleva el hash del TEXTO: si la frase cambia, el audio se regenera solo.
        # Guardándolo solo por número, una frase editada reusaba en silencio la voz vieja.
        firma = hashlib.sha1(texto.encode("utf-8")).hexdigest()[:10]
        destino = tmp / f"f{k:02d}_{firma}.mp3"
        d = locutar(texto, destino)
        tiempos.append(round(d + PAUSA, 3))
        trozos.append(destino)
        print(f"  voz {k + 1}/{len(frases)}  {d:5.2f}s  «{texto}»")

    # la coletilla de marca es un extra: si el TTS se cae aquí, el reel igual sale
    tag = tmp / "tag.mp3"
    try:
        locutar(TAG_FINAL, tag)
        trozos.append(tag)
    except RuntimeError as e:
        print(f"  (sin coletilla final: {e})")

    voz = VIDEO / "out" / f"voz_{cap}.m4a"
    pista_de_voz(trozos, voz)
    print(f"  pista de voz: {duracion(voz):.2f}s -> {voz.name}")

    props = json.dumps({"capitulo": cap, "tiempos": tiempos}, ensure_ascii=False)
    frames = VIDEO / "out" / f"frames_pixel_{cap}"
    subprocess.run(["rm", "-rf", str(frames)], check=True)
    subprocess.run(
        ["npx", "remotion", "render", "ReelPixel", str(frames),
         "--sequence", "--image-format=png", f"--props={props}",
         "--browser-executable=/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
         "--gl=swiftshader", "--concurrency=1", "--is-production=false"],
        cwd=VIDEO, check=True)

    primero = sorted(frames.glob("*.png"))[0].stem
    prefijo, _, numero = primero.rpartition("-")
    SALIDA.mkdir(parents=True, exist_ok=True)
    mp4 = SALIDA / f"reel_{cap}.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-framerate", "30", "-i", str(frames / f"{prefijo}-%0{len(numero)}d.png"),
         "-i", str(voz),
         # crf bajo: el pixel art se arruina si el códec le suaviza los bordes
         "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(mp4)],
        check=True)
    subprocess.run(["rm", "-rf", str(frames)], check=True)
    print(f"  listo: {mp4}  ({duracion(mp4):.1f}s)")
    return mp4


if __name__ == "__main__":
    fallos: list[str] = []
    for c in (sys.argv[1:] or ["taller"]):
        try:
            generar(c)
        except Exception as e:  # un capítulo caído no debe tumbar los otros dos
            fallos.append(c)
            print(f"  ERROR en {c}: {e}")
    if fallos:
        print(f"\ncapítulos fallidos: {', '.join(fallos)}")
        sys.exit(1)

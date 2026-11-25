#!/usr/bin/env python3
"""Motor de locución humana neuronal y sincronía para Reels de El Socio.

Cero dependencias externas (100% Python stdlib) y cero voces robóticas (`say` prohibido).
Soporta 3 motores humanos automáticos según lo disponible en `.env`:
  1. `elevenlabs`  — si existe `ELEVENLABS_API_KEY` (estudio hiperrealista / voz clonada).
  2. `openai`      — si existe `OPENAI_API_KEY` (`gpt-4o-mini-tts`, dirección actoral).
  3. `edge_neural` — por defecto (0 USD, 0 claves): voz neuronal multilingüe de 2ª generación
                     `it-IT-GiuseppeMultilingualNeural` (español fluido sin acento gringo,
                     o `fr-FR-RemyMultilingualNeural` / `es-CO-GonzaloNeural` por `.env`)
                     por WebSocket TLS + `Sec-MS-GEC` v2.

Además (ADN de voz Raymond — `humanizacion-el-socio`):
  - Pasa cada frase por `sales_agent.revisar_guarda_precios()` ANTES de hablar.
  - Limpia símbolos visuales (`·`, `|`, URLs) y aplica puntuación prosódica sin tocar subtítulos.
  - Aplica prosodia dinámica en 4 tiempos (gancho firme, lado A ágil, pivote B fluido,
    cierre ~8–10% más pausado en 3 golpes) y esculpe silencios muertos de TTS (~0.95 s ->
    respiraciones humanas de 0.22–0.38 s con crossfades suaves), recalculando al milisegundo
    `tiemposBloques` y `tiempoCierre` para Remotion y masterizando a -14 LUFS (`ffmpeg`).
"""

from __future__ import annotations

import argparse
import array
import base64
import json
import math
import os
import random
import re
import secrets
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import wave
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import autopilot_dispatcher  # noqa: E402
import sales_agent  # noqa: E402

VOZ_DIR = PROJECT_ROOT / "redes" / "voz"

# Voces neuronales humanas recomendadas (fluidez conversacional 2ª gen, cero robot ni acento gringo).
# `it-IT-GiuseppeMultilingualNeural` (cálida, ágil) y `fr-FR-RemyMultilingualNeural` (más grave/calmada)
# superan la entonación plana de 1ª generación; también soporta `es-CO-GonzaloNeural` con pausas esculpidas.
VOZ_EDGE_DEFECTO = "it-IT-GiuseppeMultilingualNeural"
VOZ_OPENAI_DEFECTO = "ash"                   # La voz más cálida y conversacional de OpenAI
VOZ_ELEVEN_DEFECTO = "pNInz6obpgDQGcFmaJgB"  # Multilingual v2

FPS_REEL = 30
INICIO_LOCUCION_SEG = 0.14
MIN_GANCHO_SEG = 2.0
MIN_BLOQUE_SEG = 2.0
MIN_CIERRE_SEG = 2.4
PAUSA_ENTRE_FRASES_SEG = 0.30
COLA_FINAL_SEG = 0.75
MAX_PLANO_ESTATICO_SEG = 2.55

# Tiempos humanos calibrados al ADN de voz de Raymond (`adn-voz-raymond.md` §3-§4).
PAUSA_GANCHO_SEG = 0.26        # Gancho -> desarrollo (retención ágil)
PAUSA_DESARROLLO_MAX_SEG = 0.22  # Entre ideas del mismo lado (una sola respiración)
PAUSA_PIVOTE_AB_SEG = 0.38     # Respiración clara en el contraste A -> B
PAUSA_PRE_CIERRE_SEG = 0.34    # Beat limpio antes de los 3 golpes finales
PAUSA_CIERRE_GOLPE_SEG = 0.28  # Golpes firmes del cierre (sin huecos muertos de 1 s)
PAUSA_DRAMATICA_SEG = 0.48     # Pausa dramática única (`...`)
CROSSFADE_PAUSA_MS = 18

# Dinámica de velocidad en 4 tiempos relativa a la tasa base (ADN Raymond: desarrollo ágil, cierre -8/-10%).
DELTAS_RATE_FASE = {
    "gancho": 0,
    "lado_a": 4,
    "pivote_b": 1,
    "lado_b": 1,
    "cierre": -6,
}

# Cadena vocal cálida de podcast cercano + suavizado de sibilancia metálica TTS + EBU R128 a -14 LUFS.
FILTRO_CADENA_VOZ = (
    "highpass=f=85,"
    "equalizer=f=145:t=q:w=1.1:g=1.8,"
    "equalizer=f=290:t=q:w=1.3:g=-2.0,"
    "equalizer=f=3400:t=q:w=1.4:g=1.2,"
    "equalizer=f=6500:t=q:w=1.6:g=-1.5,"
    "acompressor=threshold=-18dB:ratio=2.4:attack=12:release=140"
)
FILTRO_MASTER_LUFS = "loudnorm=I=-14:TP=-1.0:LRA=9"
FILTRO_MASTER_VOZ = f"{FILTRO_CADENA_VOZ},{FILTRO_MASTER_LUFS}"

# Parámetros del protocolo Edge ReadAloud v2 (stdlib puro).
_EDGE_HOST = "speech.platform.bing.com"
_EDGE_TOKEN = "6A5AA1D4EAFF4E9FB37E23D68491D6F4"
_CHROMIUM_VER = "143.0.3650.75"
_CHROMIUM_MAJOR = "143"
_WIN_EPOCH = 11644473600
_MP3_CBR_BYTES_PER_SEC = 6000.0  # 48 kbps exactos = 6000 bytes/s

# Constantes criptográficas de Sec-MS-GEC v2.
_U32 = 0xFFFFFFFF
_SHA256_INIT = (
    0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
    0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19,
)
_SHA256_STATE = (
    0xFD9FBEA2, 0x91243CE7, 0xBE499094, 0xCD2E1E0A,
    0x6C006F49, 0x04BD35AB, 0xFEB0A7E4, 0x03EFFBD2,
)
_SHA256_SCHED = (
    0xEB24BF9E, 0x1558691F, 0xA0C09EE2, 0x0CFA32BA, 0xA622EE8C, 0xD1DD9491, 0xC0DD25A0,
    0xF9E70AB6, 0xF0C31573, 0x7058CE4E, 0x7188E606, 0x00E5AB33, 0xD258B060, 0x72766564,
)
_SHA256_K = (
    0x428A2F98, 0x71374491, 0xB5C0FBCF, 0xE9B5DBA5, 0x3956C25B, 0x59F111F1, 0x923F82A4, 0xAB1C5ED5,
    0xD807AA98, 0x12835B01, 0x243185BE, 0x550C7DC3, 0x72BE5D74, 0x80DEB1FE, 0x9BDC06A7, 0xC19BF174,
    0xE49B69C1, 0xEFBE4786, 0x0FC19DC6, 0x240CA1CC, 0x2DE92C6F, 0x4A7484AA, 0x5CB0A9DC, 0x76F988DA,
    0x983E5152, 0xA831C66D, 0xB00327C8, 0xBF597FC7, 0xC6E00BF3, 0xD5A79147, 0x06CA6351, 0x14292967,
    0x27B70A85, 0x2E1B2138, 0x4D2C6DFC, 0x53380D13, 0x650A7354, 0x766A0ABB, 0x81C2C92E, 0x92722C85,
    0xA2BFE8A1, 0xA81A664B, 0xC24B8B70, 0xC76C51A3, 0xD192E819, 0xD6990624, 0xF40E3585, 0x106AA070,
    0x19A4C116, 0x1E376C08, 0x2748774C, 0x34B0BCB5, 0x391C0CB3, 0x4ED8AA4A, 0x5B9CCA4F, 0x682E6FF3,
    0x748F82EE, 0x78A5636F, 0x84C87814, 0x8CC70208, 0x90BEFFFA, 0xA4506CEB, 0xBEF9A3F7, 0xC67178F2,
)
_SHA256_ADJ = 0xC9DC06A7
_SHA256_K_BLK = _SHA256_K[:14] + (_SHA256_ADJ,) + _SHA256_K[15:]
_CS64_COEFFS = (
    (0xE82E91B1, 0xB32700D0), (0x44DE24C6, 0x88DFF51D), (0x3BEB65BC, 0x29514038),
    (0xC89C5933, 0xB328CBDF), (0x8D1EC211, 0xD405B4D5), (0x314EF5D5, 0x26E55F3C),
    (0xE92491B1, 0x607801C6), (0xF0A5B9D5, 0x82B2C1FB), (0x06064CF3, 0xFA51A3DA),
    (0xDA79FA60, 0x207CC464), (0xBED20560, 0x3C3C74F3), (0x89F9C9F8, 0xD2D14B61),
    (0x35FA38C6, 0xBB04A2C1), (0xCB49E3C6, 0xC5626167),
)
_CLOCK_SKEW_SEG = 0.0


class ErrorVoz(Exception):
    """Fallo al sintetizar o masterizar la locución."""


class GuardaVozBloqueada(ErrorVoz):
    """El texto a locutar violó la guarda dura de precios/cifras."""

    def __init__(self, motivos: list[str]) -> None:
        super().__init__("; ".join(motivos))
        self.motivos = motivos


# ------------------------------------------------ preparación del texto hablado

def limpiar_para_locucion(texto: str) -> str:
    """Convierte texto visual de pantalla en frases naturales para ser habladas.

    Sin esto, un motor TTS lee literal 'punto medio' en 'Cuéntanos · link en bio'
    o deletrea URLs completas.
    """
    limpio = str(texto or "").strip()
    if not limpio:
        return ""
    # Quitar URLs completas si las hubiera.
    limpio = re.sub(r"https?://\S+", "", limpio)
    # Separadores visuales -> pausa hablada natural.
    limpio = re.sub(r"\s*[·|•—–]\s*", ". ", limpio)
    # Limpiar caracteres de control.
    limpio = "".join(" " if (0 <= ord(c) <= 31) else c for c in limpio)
    limpio = re.sub(r"\s+", " ", limpio).strip(" ,;:-")
    if limpio and limpio[-1] not in ".?!…":
        limpio += "."
    return limpio


_RE_APERTURA_PAUSA = re.compile(
    r"^(En el primer (?:taller|local|caso|estudio|negocio|escenario|ejemplo|día|mes|tienda|agencia)|"
    r"En el segundo(?: (?:taller|local|caso|estudio|negocio|escenario|ejemplo|día|mes))?|"
    r"En la primera(?: (?:tienda|agencia|marca))?|"
    r"En la segunda(?: (?:tienda|agencia|marca))?|"
    r"En cambio|Con nosotros|Pero con nosotros|La verdad|Básicamente|"
    r"De hecho|Al final|Resultado)\s+(?=[a-zA-ZáéíóúñÁÉÍÓÚÑ])",
    re.IGNORECASE,
)
_RE_PIVOTE_CONTRASTE = re.compile(
    r"(?<=[a-zA-ZáéíóúñÁÉÍÓÚÑ0-9])\s+(pero|en cambio|sin embargo)\s+",
    re.IGNORECASE,
)
_RE_CON_TU_SOCIO = re.compile(r"\s*Con El Socio,?\s*", re.IGNORECASE)
_RE_INICIO_PIVOTE_B = re.compile(
    r"^(?:en el segundo|en la segunda|el segundo|la segunda|la otra|"
    r"pero\b|en cambio|sin embargo|con nosotros|con el socio|"
    r"ahora\b|resultado|lo que te entregamos|eso te vendemos|"
    r"mientras tanto|en el lado b|con ficha|con render|con el sistema)",
    re.IGNORECASE,
)
_RE_LETRA_CIERRE = re.compile(
    r"\b(Taller|Local|Negocio|Estudio|Caso|Equipo|Cliente|Marca|Tienda|Agencia|Persona)\s+([AB])\b",
    re.IGNORECASE,
)


def humanizar_texto_para_voz(texto: str, *, rol: str = "bloque") -> str:
    """Inyecta puntuación prosódica natural (ADN Raymond) solo para la pista de locución.

    No altera los subtítulos visuales en pantalla: únicamente agrega micro-respiraciones
    en pivotes de contraste y articulación limpia en el cierre para que los motores TTS
    (`edge_neural`, `openai`, `elevenlabs`) suenen conversacionales y fluidos.
    """
    base = limpiar_para_locucion(texto)
    if not base:
        return ""

    # 1) Micro-respiración tras aperturas de contraste ("En el segundo, cortan...").
    base = _RE_APERTURA_PAUSA.sub(r"\1, ", base, count=1)

    # 2) Coma natural antes de pivotes de contraste en medio de frase (", pero ...").
    base = _RE_PIVOTE_CONTRASTE.sub(r", \1 ", base)

    # 3) En el cierre, asegurar 3 golpes firmes y articulación nítida de 'Taller "A"'/'Taller "B"'
    # sin pausas rotas tipo "Taller, A" ni bajón plano tras "Con El Socio".
    if rol == "cierre":
        base = re.sub(r"\s+Sé\s+", ". Sé ", base)
        base = _RE_LETRA_CIERRE.sub(lambda m: f'{m.group(1)} "{m.group(2).upper()}"', base)
        if _RE_CON_TU_SOCIO.search(base):
            base = _RE_CON_TU_SOCIO.sub(" Con El Socio ", base)
            base = re.sub(r"(?<=[^.?!…])\s+Con El Socio\b", ". Con El Socio", base)
        base = re.sub(r"(?<!\.)\.\.(?!\.)", ".", base)

    base = re.sub(r"\s+,", ",", base)
    base = re.sub(r",\s*,+", ", ", base)
    base = re.sub(r"\s{2,}", " ", base).strip()
    return base


def es_voz_multilingual(voz: str) -> bool:
    """Detecta voces neuronales Multilingual de 2ª generación."""
    return "multilingual" in (voz or "").lower()


def inferir_xml_lang(voz: str) -> str:
    """Deduce `xml:lang` correcto para SSML en español (nunca forzar `en-US` sobre guiones en español)."""
    v = (voz or "").strip()
    if v.lower().startswith("es-") and len(v) >= 5:
        partes = v.split("-")
        return f"{partes[0].lower()}-{partes[1].upper()}"
    return "es-CO"


def ajustar_rate_relativo(rate_base: str, delta_pct: int) -> str:
    """Suma `delta_pct` al rate porcentual base (`+4%`) manteniéndolo en rango humano seguro."""
    m = re.search(r"([+-]?\d+)", str(rate_base or "+0%"))
    base = int(m.group(1)) if m else 0
    final = max(-18, min(22, base + int(delta_pct)))
    return f"{final:+d}%"


def agrupar_fases_reel(
    frases_locucion: list[str], n_bloques: int,
) -> list[dict[str, object]]:
    """Agrupa `[gancho, *bloques, cierre]` en las fases narrativas de Raymond (4 tiempos).

    Cada fase lleva su rol (`gancho`, `lado_a`, `pivote_b`, `cierre`), los índices de frase que
    contiene, el texto unido, la pausa humana previa (`pausa_previa_seg`), la pausa máxima
    interna permitida (`max_pausa_interna_seg`) y el delta de velocidad (`delta_rate`).
    """
    if not frases_locucion:
        return []
    if len(frases_locucion) == 1:
        return [{
            "fase": "gancho",
            "indices": [0],
            "frases": [frases_locucion[0]],
            "texto": frases_locucion[0],
            "pausa_previa_seg": 0.0,
            "max_pausa_interna_seg": PAUSA_DESARROLLO_MAX_SEG,
            "delta_rate": DELTAS_RATE_FASE["gancho"],
        }]

    gancho = frases_locucion[0]
    bloques = frases_locucion[1:1 + n_bloques]
    cierre = frases_locucion[-1] if len(frases_locucion) > 1 + n_bloques else ""

    fases: list[dict[str, object]] = [{
        "fase": "gancho",
        "indices": [0],
        "frases": [gancho],
        "texto": gancho,
        "pausa_previa_seg": 0.0,
        "max_pausa_interna_seg": PAUSA_DRAMATICA_SEG if "..." in gancho else PAUSA_DESARROLLO_MAX_SEG,
        "delta_rate": DELTAS_RATE_FASE["gancho"],
    }]

    if bloques:
        # Detectar índice del giro A -> B en los bloques del desarrollo.
        idx_pivote = -1
        for i, b in enumerate(bloques):
            if i > 0 and _RE_INICIO_PIVOTE_B.search(b.strip()):
                idx_pivote = i
                break
        if idx_pivote == -1 and len(bloques) >= 3:
            idx_pivote = len(bloques) // 2

        if idx_pivote <= 0:
            texto_des = " ".join(bloques)
            fases.append({
                "fase": "lado_a",
                "indices": list(range(1, 1 + len(bloques))),
                "frases": list(bloques),
                "texto": texto_des,
                "pausa_previa_seg": PAUSA_GANCHO_SEG,
                "max_pausa_interna_seg": PAUSA_DRAMATICA_SEG if "..." in texto_des else PAUSA_DESARROLLO_MAX_SEG,
                "delta_rate": DELTAS_RATE_FASE["lado_a"],
            })
        else:
            bloques_a = bloques[:idx_pivote]
            bloques_b = bloques[idx_pivote:]
            texto_a = " ".join(bloques_a)
            texto_b = " ".join(bloques_b)
            fases.append({
                "fase": "lado_a",
                "indices": list(range(1, 1 + idx_pivote)),
                "frases": list(bloques_a),
                "texto": texto_a,
                "pausa_previa_seg": PAUSA_GANCHO_SEG,
                "max_pausa_interna_seg": PAUSA_DRAMATICA_SEG if "..." in texto_a else PAUSA_DESARROLLO_MAX_SEG,
                "delta_rate": DELTAS_RATE_FASE["lado_a"],
            })
            fases.append({
                "fase": "pivote_b",
                "indices": list(range(1 + idx_pivote, 1 + len(bloques))),
                "frases": list(bloques_b),
                "texto": texto_b,
                "pausa_previa_seg": PAUSA_PIVOTE_AB_SEG,
                "max_pausa_interna_seg": PAUSA_DRAMATICA_SEG if "..." in texto_b else PAUSA_DESARROLLO_MAX_SEG,
                "delta_rate": DELTAS_RATE_FASE["pivote_b"],
            })

    if cierre:
        fases.append({
            "fase": "cierre",
            "indices": [len(frases_locucion) - 1],
            "frases": [cierre],
            "texto": cierre,
            "pausa_previa_seg": PAUSA_PRE_CIERRE_SEG,
            "max_pausa_interna_seg": PAUSA_CIERRE_GOLPE_SEG,
            "delta_rate": DELTAS_RATE_FASE["cierre"],
        })

    return fases


def _contar_oraciones_tts(texto: str) -> int:
    partes = [p.strip() for p in re.split(r"[.?!…]+", texto) if p.strip()]
    return max(1, len(partes))


def _extraer_inicios_desde_marcas(
    frases_locucion: list[str],
    marcas: list[dict[str, object]],
    dur_audio: float,
) -> list[float]:
    """Mapea cada bloque al inicio real de su primera oración dentro de la toma continua."""
    n_frases = len(frases_locucion)
    if n_frases == 0:
        return []
    conteos = [_contar_oraciones_tts(f) for f in frases_locucion]
    total_oraciones = sum(conteos)
    if marcas and len(marcas) >= total_oraciones:
        inicios: list[float] = []
        cursor = 0
        for cant in conteos:
            inicios.append(round(INICIO_LOCUCION_SEG + float(marcas[cursor]["offset_seg"]), 3))
            cursor += cant
        return inicios
    if marcas and len(marcas) >= n_frases:
        return [round(INICIO_LOCUCION_SEG + float(m["offset_seg"]), 3) for m in marcas[:n_frases]]
    pesos = [max(1, len(f.split())) for f in frases_locucion]
    total_p = sum(pesos) or 1
    inicios = []
    acum = 0.0
    for p in pesos:
        inicios.append(round(INICIO_LOCUCION_SEG + (acum / total_p) * dur_audio, 3))
        acum += p
    return inicios


def _buscar_binario(nombre: str) -> str | None:
    """Encuentra `ffmpeg` / `ffprobe` incluso cuando `launchd` recorta el PATH."""
    hallado = shutil.which(nombre)
    if hallado:
        return hallado
    carpetas = (
        str(Path.home() / ".local" / "bin"),
        "/usr/local/bin",
        "/opt/homebrew/bin",
        "/usr/bin",
    )
    for carpeta in carpetas:
        candidato = Path(carpeta) / nombre
        if candidato.exists() and os.access(candidato, os.X_OK):
            return str(candidato)
    return None


def cargar_config_voz() -> dict[str, str]:
    cfg = autopilot_dispatcher.load_env_file()
    for clave in (
        "VOICE_PROVIDER", "VOICE_NAME", "VOICE_RATE", "VOICE_PITCH",
        "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "OPENAI_API_KEY",
    ):
        if os.environ.get(clave):
            cfg[clave] = os.environ[clave]
    return cfg


def elegir_proveedor(cfg: dict[str, str]) -> str:
    forzado = (cfg.get("VOICE_PROVIDER") or "").strip().lower()
    if forzado in ("elevenlabs", "openai", "edge_neural"):
        return forzado
    if (cfg.get("ELEVENLABS_API_KEY") or "").strip():
        return "elevenlabs"
    if (cfg.get("OPENAI_API_KEY") or "").strip():
        return "openai"
    return "edge_neural"


# ----------------------------------------- Sec-MS-GEC v2 + WebSocket stdlib

def _rol16(value: int) -> int:
    value &= _U32
    return ((value << 16) | (value >> 16)) & _U32


def _words_le4_even(data: bytes) -> list[int]:
    padded = data + b"\x00" * ((-len(data)) % 4)
    if not padded:
        return []
    words = list(struct.unpack(f"<{len(padded) // 4}I", padded))
    if len(words) % 2:
        words.append(0)
    return words


def _sigma0(value: int) -> int:
    return ((value >> 7) ^ (value << 25) ^ (value >> 18) ^ (value << 14) ^ (value >> 3)) & _U32


def _sigma1(value: int) -> int:
    return ((value >> 17) ^ (value << 15) ^ (value >> 19) ^ (value << 13) ^ (value >> 10)) & _U32


def _expandir_palabras(words: list[int], inicio: int = 16) -> None:
    for i in range(inicio, 64):
        words.append((_sigma1(words[i - 2]) + words[i - 7] + _sigma0(words[i - 15]) + words[i - 16]) & _U32)


def _rondas_sha256(state: tuple[int, ...], words: list[int], r0: int = 0) -> tuple[int, ...]:
    a, b, c, d, e, f, g, h = state
    ks = _SHA256_K_BLK if r0 == 14 else _SHA256_K
    for i in range(r0, 64):
        re_ = e * 0x100000001
        ra_ = a * 0x100000001
        s1 = ((re_ >> 6) ^ (re_ >> 11) ^ (re_ >> 25)) & _U32
        ch = (g ^ (e & (f ^ g))) & _U32
        t1 = (h + s1 + ch + ks[i] + words[i]) & _U32
        s0 = ((ra_ >> 2) ^ (ra_ >> 13) ^ (ra_ >> 22)) & _U32
        maj = ((a & b) | (c & (a | b))) & _U32
        t2 = (s0 + maj) & _U32
        a, b, c, d, e, f, g, h = (t1 + t2) & _U32, a, b, c, (d + t1) & _U32, e, f, g
    return a, b, c, d, e, f, g, h


def _gec_sha256(data: bytes) -> bytes:
    words = [0] * 14 + [int.from_bytes(data[:3], "big"), int.from_bytes(data[3:7], "big")]
    for i in range(16, 30):
        val = _SHA256_SCHED[i - 16]
        if i - 2 >= 14:
            val += (_sigma1(words[i - 2]) ^ 0x000B92C0) if i == 16 else _sigma1(words[i - 2])
        if i - 7 >= 14:
            val += words[i - 7]
        if i - 15 >= 14:
            val += (_sigma0(words[i - 15]) ^ 0x059C0B80) if i == 29 else _sigma0(words[i - 15])
        words.append(val & _U32)
    words.append(
        (_sigma1(words[28]) + words[23] + _sigma0(words[15]) + words[14]
         + _SHA256_ADJ - _SHA256_K[14]) & _U32
    )
    _expandir_palabras(words, 31)
    wk = _rondas_sha256(_SHA256_STATE, words, 14)
    state = tuple((x + y) & _U32 for x, y in zip(_SHA256_INIT, wk))

    length = 57 + len(data)
    padded = data[7:] + b"\x80" + b"\x00" * ((55 - length) % 64) + struct.pack(">Q", length * 8)
    for off in range(0, len(padded), 64):
        w = list(struct.unpack(">16I", padded[off:off + 64]))
        _expandir_palabras(w)
        wk = _rondas_sha256(state, w)
        state = tuple((x + y) & _U32 for x, y in zip(state, wk))
    return struct.pack(">8I", *state)


def _gec_cs64(data: bytes, digest: bytes) -> tuple[int, int]:
    ka, kb = struct.unpack_from("<II", digest)
    ka |= 1
    kb |= 1
    fact = ((ka * 0x82893933) & _U32, (kb * 0x82893933) & _U32)
    terms = [(c * fact[i % 2]) & _U32 for i, (c, _) in enumerate(_CS64_COEFFS)]
    offs = [o for _, o in _CS64_COEFFS]

    for i, w in enumerate(_words_le4_even(b"\x00" + data)):
        term = w * (ka if i % 2 == 0 else kb)
        off = _rol16(w) * (0xEF0569FB if i % 2 == 0 else 0xC31713DB)
        if i == 0:
            term += 0xF2F90B1A * fact[0]
            off += 0x0B1A0000
        terms.append(term & _U32)
        offs.append(off & _U32)

    swap_acc = swap_last = st = acc = 0
    for i in range(0, len(terms), 2):
        x, y = terms[i], terms[i + 1]
        t = _rol16((offs[i] + x) & _U32)
        q = (t * 0x76F50F34) & _U32
        swap_acc += (_rol16(q) * 0xC3EFEA97 + q) & _U32
        t = _rol16((offs[i + 1] + y) & _U32)
        q = (t * 0x1881CE3C) & _U32
        swap_last = (_rol16(q) * 0x35BD1EC9 + q) & _U32
        swap_acc = (swap_acc + swap_last) & _U32

        st = (st * ka + x) & _U32
        st = (_rol16(st) * 0xCF98B111) & _U32
        st = (_rol16(st) * 0x87085B9F) & _U32
        st = (_rol16(st) * 0x12CEB96D) & _U32
        st = (_rol16(st) * 0x257E1D83) & _U32
        acc += st
        t = (st * kb + y) & _U32
        t = (_rol16(t) * 0xA27416F5) & _U32
        t = (_rol16(t) * 0xD38396FF) & _U32
        st = (_rol16((_rol16(t) * 0x7C932B89) & _U32) * 0xBFA49F69) & _U32
        acc = (acc + st) & _U32
    return swap_last ^ st, swap_acc ^ acc


def generar_sec_ms_gec(unix_ts: float | None = None) -> str:
    """Genera el token Sec-MS-GEC v2 exacto en Python stdlib puro."""
    ts = (datetime.now(timezone.utc).timestamp() + _CLOCK_SKEW_SEG) if unix_ts is None else float(unix_ts)
    ticks = ts + _WIN_EPOCH
    ticks -= ticks % 300
    ticks *= 1e7
    cadena = f"{ticks:.0f}{_EDGE_TOKEN}".encode("ascii")
    digest = _gec_sha256(cadena)
    cs64 = struct.pack("<II", *_gec_cs64(cadena, digest)).hex().upper()
    return f"{cs64}-{digest.hex().upper()}"


def _leer_exacto(sock: ssl.SSLSocket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        trozo = sock.recv(n - len(buf))
        if not trozo:
            raise ErrorVoz("Conexión WebSocket cerrada prematuramente.")
        buf.extend(trozo)
    return bytes(buf)


def _ws_enviar_texto(sock: ssl.SSLSocket, texto: str) -> None:
    payload = texto.encode("utf-8")
    mascara = secrets.token_bytes(4)
    n = len(payload)
    cabecera = bytearray([0x81])  # FIN=1, opcode=1 (texto)
    if n < 126:
        cabecera.append(0x80 | n)
    elif n < 65536:
        cabecera.append(0x80 | 126)
        cabecera.extend(struct.pack(">H", n))
    else:
        cabecera.append(0x80 | 127)
        cabecera.extend(struct.pack(">Q", n))
    cabecera.extend(mascara)
    enmascarado = bytes(b ^ mascara[i & 3] for i, b in enumerate(payload))
    sock.sendall(bytes(cabecera) + enmascarado)


def _ws_recibir_mensaje(sock: ssl.SSLSocket) -> tuple[int, bytes]:
    opcode_final = 0
    partes = bytearray()
    while True:
        b0, b1 = _leer_exacto(sock, 2)
        fin = bool(b0 & 0x80)
        opcode = b0 & 0x0F
        masked = bool(b1 & 0x80)
        largo = b1 & 0x7F
        if largo == 126:
            largo = struct.unpack(">H", _leer_exacto(sock, 2))[0]
        elif largo == 127:
            largo = struct.unpack(">Q", _leer_exacto(sock, 8))[0]
        clave = _leer_exacto(sock, 4) if masked else b""
        datos = _leer_exacto(sock, largo) if largo else b""
        if masked:
            datos = bytes(b ^ clave[i & 3] for i, b in enumerate(datos))

        if opcode == 0x9:  # ping -> responder pong
            mascara = secrets.token_bytes(4)
            pong = bytes([0x8A, 0x80 | len(datos)]) + mascara + bytes(
                b ^ mascara[i & 3] for i, b in enumerate(datos)
            )
            sock.sendall(pong)
            continue
        if opcode == 0x8:  # close
            return 0x8, bytes(partes)
        if opcode != 0x0:
            opcode_final = opcode
        partes.extend(datos)
        if fin:
            return opcode_final, bytes(partes)


def _sintetizar_edge_una_vez(texto: str, voz: str, rate: str, pitch: str) -> bytes:
    global _CLOCK_SKEW_SEG
    conn_id = uuid.uuid4().hex
    gec = generar_sec_ms_gec()
    ruta_ws = (
        f"/consumer/speech/synthesize/readaloud/edge/v1"
        f"?TrustedClientToken={_EDGE_TOKEN}"
        f"&ConnectionId={conn_id}"
        f"&Sec-MS-GEC={gec}"
        f"&Sec-MS-GEC-Version=2-{_CHROMIUM_VER}"
    )
    ws_key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
    muid = secrets.token_hex(16).upper()
    ua = (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{_CHROMIUM_MAJOR}.0.0.0 Safari/537.36 "
        f"Edg/{_CHROMIUM_MAJOR}.0.0.0"
    )
    handshake = (
        f"GET {ruta_ws} HTTP/1.1\r\n"
        f"Host: {_EDGE_HOST}\r\n"
        "Pragma: no-cache\r\n"
        "Cache-Control: no-cache\r\n"
        "Origin: chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {ws_key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"User-Agent: {ua}\r\n"
        "Accept-Encoding: gzip, deflate, br, zstd\r\n"
        "Accept-Language: es-CO,es;q=0.9\r\n"
        f"Cookie: muid={muid};\r\n\r\n"
    ).encode("utf-8")

    ctx = ssl.create_default_context()
    with socket.create_connection((_EDGE_HOST, 443), timeout=20) as raw_sock:
        with ctx.wrap_socket(raw_sock, server_hostname=_EDGE_HOST) as tls:
            tls.settimeout(30)
            tls.sendall(handshake)
            cabecera_http = bytearray()
            while b"\r\n\r\n" not in cabecera_http:
                trozo = tls.recv(4096)
                if not trozo:
                    raise ErrorVoz("Sin respuesta HTTP en handshake de Edge Neural.")
                cabecera_http.extend(trozo)
                if len(cabecera_http) > 32768:
                    raise ErrorVoz("Cabecera HTTP demasiado larga.")

            corte = cabecera_http.index(b"\r\n\r\n") + 4
            texto_cab = bytes(cabecera_http[:corte]).decode("iso-8859-1", errors="replace")
            primera = texto_cab.splitlines()[0] if texto_cab else ""
            if " 101 " not in primera:
                if " 403 " in primera:
                    for linea in texto_cab.splitlines():
                        if linea.lower().startswith("date:"):
                            try:
                                dt_srv = parsedate_to_datetime(linea.split(":", 1)[1].strip())
                                if dt_srv.tzinfo is None:
                                    dt_srv = dt_srv.replace(tzinfo=timezone.utc)
                                _CLOCK_SKEW_SEG = dt_srv.timestamp() - datetime.now(timezone.utc).timestamp()
                            except Exception:
                                pass
                    raise ErrorVoz(f"HTTP_403_RELOJ ({primera} | skew={_CLOCK_SKEW_SEG:.1f}s)")
                raise ErrorVoz(f"Handshake WebSocket rechazado: {primera}")

            ahora_js = time.strftime(
                "%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)", time.gmtime()
            )
            msg_cfg = (
                f"X-Timestamp:{ahora_js}\r\n"
                "Content-Type:application/json; charset=utf-8\r\n"
                "Path:speech.config\r\n\r\n"
                '{"context":{"synthesis":{"audio":{"metadataoptions":{'
                '"sentenceBoundaryEnabled":"true","wordBoundaryEnabled":"false"},'
                '"outputFormat":"audio-24khz-48kbitrate-mono-mp3"}}}}\r\n'
            )
            _ws_enviar_texto(tls, msg_cfg)

            cuerpo_interno = xml_escape(texto)
            xml_lang = inferir_xml_lang(voz)
            ssml = (
                f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{xml_lang}'>"
                f"<voice name='{xml_escape(voz)}'>"
                f"<prosody pitch='{xml_escape(pitch)}' rate='{xml_escape(rate)}' volume='+0%'>"
                f"{cuerpo_interno}"
                "</prosody></voice></speak>"
            )
            msg_ssml = (
                f"X-RequestId:{uuid.uuid4().hex}\r\n"
                "Content-Type:application/ssml+xml\r\n"
                f"X-Timestamp:{ahora_js}Z\r\n"
                f"Path:ssml\r\n\r\n{ssml}"
            )
            _ws_enviar_texto(tls, msg_ssml)

            audio = bytearray()
            marcas_oracion: list[dict[str, object]] = []
            while True:
                opcode, datos = _ws_recibir_mensaje(tls)
                if opcode == 0x8:
                    break
                if opcode == 0x1:
                    if b"Path:audio.metadata" in datos:
                        sep = datos.find(b"\r\n\r\n")
                        if sep != -1:
                            try:
                                meta_json = json.loads(datos[sep + 4:].decode("utf-8", errors="replace"))
                                for item in (meta_json.get("Metadata") or []):
                                    if item.get("Type") == "SentenceBoundary":
                                        d_it = item.get("Data") or {}
                                        marcas_oracion.append({
                                            "offset_seg": float(d_it.get("Offset", 0)) / 10_000_000.0,
                                            "dur_seg": float(d_it.get("Duration", 0)) / 10_000_000.0,
                                            "texto": str((d_it.get("text") or {}).get("Text") or ""),
                                        })
                            except Exception:
                                pass
                    elif b"Path:turn.end" in datos:
                        break
                elif opcode == 0x2 and len(datos) >= 2:
                    largo_hdr = int.from_bytes(datos[:2], "big")
                    hdr = datos[2:2 + largo_hdr]
                    cuerpo = datos[2 + largo_hdr:]
                    if b"Path:audio" in hdr and cuerpo:
                        audio.extend(cuerpo)
            if not audio:
                raise ErrorVoz("Edge Neural no devolvió bytes de audio.")
            return bytes(audio), marcas_oracion


def sintetizar_edge_con_marcas(
    texto: str, cfg: dict[str, str], *, rate_override: str = "", pitch_override: str = "",
) -> tuple[bytes, list[dict[str, object]]]:
    voz = (cfg.get("VOICE_NAME") or VOZ_EDGE_DEFECTO).strip()
    rate_def = "+4%" if es_voz_multilingual(voz) else "+6%"
    rate = (rate_override or cfg.get("VOICE_RATE") or rate_def).strip()
    pitch = (pitch_override or cfg.get("VOICE_PITCH") or "+0Hz").strip()
    try:
        return _sintetizar_edge_una_vez(texto, voz, rate, pitch)
    except ErrorVoz as err:
        if "HTTP_403_RELOJ" in str(err):
            return _sintetizar_edge_una_vez(texto, voz, rate, pitch)
        raise
    except OSError as exc:
        raise ErrorVoz(f"Red no disponible para voz neuronal: {exc}") from None


def sintetizar_edge_neural(texto: str, cfg: dict[str, str]) -> bytes:
    audio, _ = sintetizar_edge_con_marcas(texto, cfg)
    return audio


def sintetizar_openai(texto: str, cfg: dict[str, str]) -> bytes:
    api_key = (cfg.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise ErrorVoz("Falta OPENAI_API_KEY.")
    voz = (cfg.get("VOICE_NAME") or VOZ_OPENAI_DEFECTO).strip()
    cuerpo = json.dumps({
        "model": "gpt-4o-mini-tts",
        "voice": voz,
        "input": texto,
        "response_format": "mp3",
        "instructions": (
            "Habla en español colombiano natural y relajado (acento paisa muy suave, "
            "nunca caricaturizado). Voz masculina grave-media, cálida, segura y sobria, "
            "como alguien que explica de tú a tú en un café. Entra con peso en las "
            "primeras palabras, lleva un ritmo ágil en el desarrollo, haz una pausa "
            "breve antes de los contrastes y remata el cierre en frases cortas y firmes. "
            "Cero tono de locutor radial o comercial exagerado."
        ),
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=cuerpo,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.read()
    except urllib.error.URLError as exc:
        raise ErrorVoz(f"OpenAI TTS falló: {exc}") from None


def sintetizar_elevenlabs(texto: str, cfg: dict[str, str]) -> bytes:
    api_key = (cfg.get("ELEVENLABS_API_KEY") or "").strip()
    if not api_key:
        raise ErrorVoz("Falta ELEVENLABS_API_KEY.")
    voice_id = (cfg.get("ELEVENLABS_VOICE_ID") or VOZ_ELEVEN_DEFECTO).strip()
    cuerpo = json.dumps({
        "text": texto,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.48, "similarity_boost": 0.82, "style": 0.22},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        data=cuerpo,
        method="POST",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.read()
    except urllib.error.URLError as exc:
        raise ErrorVoz(f"ElevenLabs falló: {exc}") from None


def sintetizar_mp3(texto: str, cfg: dict[str, str] | None = None) -> tuple[bytes, str]:
    """Sintetiza un fragmento limpio en MP3 usando el mejor proveedor humano disponible."""
    cfg = cargar_config_voz() if cfg is None else cfg
    limpio = humanizar_texto_para_voz(texto)
    if not limpio:
        raise ErrorVoz("El texto para locutar está vacío.")
    motivos = sales_agent.revisar_guarda_precios(limpio)
    if motivos:
        raise GuardaVozBloqueada(motivos)

    proveedor = elegir_proveedor(cfg)
    if proveedor == "elevenlabs":
        return sintetizar_elevenlabs(limpio, cfg), "elevenlabs"
    if proveedor == "openai":
        return sintetizar_openai(limpio, cfg), "openai"
    return sintetizar_edge_neural(limpio, cfg), "edge_neural"


# ----------------------------------------- medición y sincronía exacta del reel

def medir_duracion_audio(ruta_mp3: Path, bytes_mp3: bytes = b"") -> float:
    """Duración real en segundos con `ffprobe` (respaldo exacto por bytes CBR 48kbps)."""
    ffprobe = _buscar_binario("ffprobe")
    if ffprobe and ruta_mp3.exists():
        try:
            proc = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(ruta_mp3)],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                val = float(proc.stdout.strip())
                if val > 0.05:
                    return val
        except Exception:
            pass
    if bytes_mp3:
        return max(0.35, len(bytes_mp3) / _MP3_CBR_BYTES_PER_SEC)
    return 1.8


def calcular_timeline_reel(duraciones_seg: list[float], n_bloques: int) -> dict[str, object]:
    """Alinea cada subtítulo de `ReelVertical` al milisegundo exacto de su locución.

    `duraciones_seg` trae `[dur_gancho, *dur_bloques, dur_cierre]`.
    """
    esperados = 1 + max(0, n_bloques) + 1
    if len(duraciones_seg) != esperados:
        raise ValueError(f"Se esperaban {esperados} duraciones y llegaron {len(duraciones_seg)}")

    inicios_audio: list[float] = []
    tiempos_bloques: list[float] = []

    # 1) Gancho: el texto está en pantalla desde 0.0s; la voz arranca en INICIO_LOCUCION_SEG.
    inicios_audio.append(INICIO_LOCUCION_SEG)
    cursor = max(MIN_GANCHO_SEG, INICIO_LOCUCION_SEG + duraciones_seg[0] + PAUSA_ENTRE_FRASES_SEG)

    # 2) Cada bloque acumulativo entra en pantalla justo cuando empieza a hablar su frase.
    for i in range(n_bloques):
        dur_b = duraciones_seg[1 + i]
        t_bloque = round(cursor, 3)
        tiempos_bloques.append(t_bloque)
        inicios_audio.append(t_bloque)
        cursor = max(t_bloque + MIN_BLOQUE_SEG, t_bloque + dur_b + PAUSA_ENTRE_FRASES_SEG)

    # 3) Cierre quemado al pie.
    tiempo_cierre = round(cursor, 3)
    inicios_audio.append(tiempo_cierre)
    dur_cierre = duraciones_seg[-1]
    fin_total = max(tiempo_cierre + MIN_CIERRE_SEG, tiempo_cierre + dur_cierre + COLA_FINAL_SEG)
    duracion_frames = max(90, int(round(fin_total * FPS_REEL)))

    return {
        "inicios_audio_seg": inicios_audio,
        "tiemposBloques": tiempos_bloques,
        "tiempoCierre": tiempo_cierre,
        "duracionFrames": duracion_frames,
        "duracion_total_seg": round(duracion_frames / FPS_REEL, 3),
    }


def mezclar_y_masterizar_segmentos(
    archivos_mp3: list[Path], inicios_seg: list[float], duracion_total_seg: float,
    salida_m4a: Path,
) -> None:
    """Coloca cada frase en su milisegundo exacto y aplica la cadena vocal a -14 LUFS."""
    ffmpeg = _buscar_binario("ffmpeg")
    if not ffmpeg:
        raise ErrorVoz("No se encontró `ffmpeg` para masterizar la pista de voz.")
    salida_m4a.parent.mkdir(parents=True, exist_ok=True)

    entradas = [
        "-f", "lavfi", "-t", f"{duracion_total_seg:.3f}",
        "-i", "anullsrc=r=44100:cl=mono",
    ]
    filtros = []
    etiquetas = ["[0:a]"]
    for idx, (ruta, inicio) in enumerate(zip(archivos_mp3, inicios_seg), start=1):
        entradas.extend(["-i", str(ruta)])
        ms = max(0, int(round(inicio * 1000)))
        # Micro-fade de 15ms para cero clics digitales + posicionamiento exacto.
        filtros.append(
            f"[{idx}:a]aresample=44100,afade=t=in:st=0:d=0.015,"
            f"adelay={ms}|{ms}[s{idx}]"
        )
        etiquetas.append(f"[s{idx}]")

    n_mix = len(etiquetas)
    filtros.append(
        f"{''.join(etiquetas)}amix=inputs={n_mix}:normalize=0,"
        f"{FILTRO_MASTER_VOZ},afade=t=out:st={max(0.1, duracion_total_seg - 0.12):.3f}:d=0.10[outa]"
    )
    cmd = [
        ffmpeg, "-y", *entradas,
        "-filter_complex", ";".join(filtros),
        "-map", "[outa]",
        "-t", f"{duracion_total_seg:.3f}",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        str(salida_m4a),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0 or not salida_m4a.exists():
        raise ErrorVoz(f"FFmpeg falló al masterizar la voz: {(proc.stderr or '')[-300:]}")


def calcular_cortes_visuales(
    tiempos_bloques: list[float], tiempo_cierre: float, duracion_total_seg: float,
) -> list[float]:
    """Devuelve todos los instantes exactos de cambio de plano (incluyendo sub-planos < 2.55 s)."""
    fronteras = [0.0, *[float(t) for t in tiempos_bloques], float(tiempo_cierre), float(duracion_total_seg)]
    cortes: list[float] = []
    for idx in range(len(fronteras) - 1):
        ini = fronteras[idx]
        fin = max(ini + 0.5, fronteras[idx + 1])
        if idx > 0:
            cortes.append(round(ini, 3))
        dur = fin - ini
        n_sub = max(1, int(math.ceil(dur / MAX_PLANO_ESTATICO_SEG)))
        if n_sub > 1:
            paso = dur / n_sub
            for sub in range(1, n_sub):
                cortes.append(round(ini + sub * paso, 3))
    return sorted({c for c in cortes if 0.25 < c < duracion_total_seg - 0.25})


def _decodificar_a_wav_24k(ruta_entrada: Path, ruta_wav: Path, *, sample_rate: int = 24000) -> Path:
    """Decodifica cualquier MP3/M4A a WAV PCM 16-bit mono 24 kHz (`ffmpeg` o `afconvert`)."""
    ffmpeg = _buscar_binario("ffmpeg")
    if ffmpeg:
        proc = subprocess.run(
            [
                ffmpeg, "-y", "-i", str(ruta_entrada),
                "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le",
                str(ruta_wav),
            ],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode == 0 and ruta_wav.exists():
            return ruta_wav
    afconvert = _buscar_binario("afconvert")
    if afconvert:
        proc = subprocess.run(
            [afconvert, "-f", "WAVE", "-d", f"LEI16@{sample_rate}", "-c", "1",
             str(ruta_entrada), str(ruta_wav)],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode == 0 and ruta_wav.exists():
            return ruta_wav
    raise ErrorVoz("No se pudo decodificar el audio TTS a WAV PCM (falta `ffmpeg`/`afconvert`).")


def _leer_wav_mono(ruta_wav: Path) -> tuple[array.array, int]:
    with wave.open(str(ruta_wav), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
    datos = array.array("h")
    datos.frombytes(raw)
    if ch > 1:
        datos = array.array("h", datos[::ch])
    return datos, sr


def _escribir_wav_mono(ruta_wav: Path, muestras: array.array, sample_rate: int = 24000) -> Path:
    ruta_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ruta_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(muestras.tobytes())
    return ruta_wav


def _aplicar_fade_extremos(muestras: array.array, sr: int, fade_in_ms: int = 12, fade_out_ms: int = 15) -> None:
    n = len(muestras)
    n_in = min(n // 3, int(sr * fade_in_ms / 1000.0))
    for i in range(n_in):
        ganancia = 0.5 * (1.0 - math.cos(math.pi * i / max(1, n_in)))
        muestras[i] = int(muestras[i] * ganancia)
    n_out = min(n // 3, int(sr * fade_out_ms / 1000.0))
    for i in range(n_out):
        idx = n - 1 - i
        ganancia = 0.5 * (1.0 - math.cos(math.pi * i / max(1, n_out)))
        muestras[idx] = int(muestras[idx] * ganancia)


def esculpir_pausas_pcm(
    muestras: array.array,
    sr: int,
    *,
    max_pausa_seg: float = PAUSA_DESARROLLO_MAX_SEG,
    mantener_inicio_seg: float = 0.035,
    mantener_fin_seg: float = 0.11,
    umbral_db: float = -42.0,
) -> tuple[array.array, list[tuple[float, float, float]]]:
    """Recorta silencios muertos de TTS (~0.95 s -> respiraciones humanas) con crossfade suave.

    Devuelve `(muestras_esculpidas, mapa_tiempos)` donde cada tupla `(orig_ini, orig_fin, nuevo_ini)`
    permite recalcular al milisegundo exacto los tiempos de subtítulos y cortes visuales.
    """
    n_total = len(muestras)
    if n_total == 0 or sr <= 0:
        return array.array("h"), []

    win = max(1, int(sr * 0.010))  # ventanas de 10 ms
    n_frames = n_total // win
    if n_frames == 0:
        return array.array("h", muestras), [(0.0, n_total / sr, 0.0)]

    activos: list[bool] = []
    umbral_lin = (10.0 ** (umbral_db / 20.0)) * 32768.0
    for f in range(n_frames):
        ini = f * win
        trozo = muestras[ini:ini + win]
        rms = math.sqrt(sum(s * s for s in trozo) / len(trozo))
        activos.append(rms >= umbral_lin)

    primer_act = next((i for i, a in enumerate(activos) if a), None)
    if primer_act is None:
        return array.array("h", muestras), [(0.0, n_total / sr, 0.0)]
    ultimo_act = max(i for i, a in enumerate(activos) if a)

    inicio_util = max(0, primer_act * win - int(mantener_inicio_seg * sr))
    fin_util = min(n_total, (ultimo_act + 1) * win + int(mantener_fin_seg * sr))

    # Detectar silencios internos largos entre primer_act y ultimo_act.
    cortes_silencio: list[tuple[int, int]] = []
    min_recorte_seg = max(0.08, max_pausa_seg)
    mitad_seg = min_recorte_seg / 2.0
    en_sil = False
    sil_ini_f = 0
    for f in range(primer_act, ultimo_act + 1):
        if not activos[f]:
            if not en_sil:
                en_sil = True
                sil_ini_f = f
        elif en_sil:
            en_sil = False
            s0 = sil_ini_f * win
            s1 = f * win
            dur_s = (s1 - s0) / sr
            if dur_s > min_recorte_seg + 0.04:
                cut_l = s0 + int(mitad_seg * sr)
                cut_r = s1 - int(mitad_seg * sr)
                if cut_r > cut_l:
                    cortes_silencio.append((cut_l, cut_r))

    # Construir segmentos conservados [a, b).
    tramos: list[tuple[int, int]] = []
    cursor = inicio_util
    for cut_l, cut_r in cortes_silencio:
        if cut_l > cursor:
            tramos.append((cursor, cut_l))
        cursor = max(cursor, cut_r)
    if fin_util > cursor:
        tramos.append((cursor, fin_util))

    if not tramos:
        return array.array("h", muestras), [(0.0, n_total / sr, 0.0)]

    xfade = max(1, int(sr * CROSSFADE_PAUSA_MS / 1000.0))
    salida = array.array("h")
    mapa: list[tuple[float, float, float]] = []

    for idx_t, (a, b) in enumerate(tramos):
        seg = muestras[a:b]
        if idx_t == 0 or not salida:
            nuevo_ini_s = len(salida) / sr
            salida.extend(seg)
            mapa.append((a / sr, b / sr, nuevo_ini_s))
            continue

        ov = min(xfade, len(salida), len(seg))
        base_out = len(salida) - ov
        for k in range(ov):
            u = k / max(1, ov)
            w_out = 0.5 * (1.0 + math.cos(math.pi * u))
            w_in = 1.0 - w_out
            mezcla = int(salida[base_out + k] * w_out + seg[k] * w_in)
            salida[base_out + k] = 32760 if mezcla > 32760 else (-32760 if mezcla < -32760 else mezcla)
        nuevo_ini_s = base_out / sr
        salida.extend(seg[ov:])
        mapa.append((a / sr, b / sr, nuevo_ini_s))

    _aplicar_fade_extremos(salida, sr)
    return salida, mapa


def mapear_tiempo_esculpido(t_orig: float, mapa: list[tuple[float, float, float]]) -> float:
    """Convierte un timestamp original (s) al instante exacto tras esculpir pausas."""
    if not mapa:
        return max(0.0, float(t_orig))
    t = float(t_orig)
    for orig_ini, orig_fin, nuevo_ini in mapa:
        if t <= orig_ini:
            return round(nuevo_ini, 4)
        if t <= orig_fin:
            return round(nuevo_ini + (t - orig_ini), 4)
    ult_ini, ult_fin, ult_nuevo = mapa[-1]
    return round(ult_nuevo + max(0.0, ult_fin - ult_ini), 4)


def unir_fases_pcm(
    fases_pcm: list[tuple[array.array, float]], sr: int = 24000,
) -> tuple[array.array, list[float]]:
    """Concatena fases narrativas esculpidas con respiraciones exactas y devuelve sus offsets (s)."""
    salida = array.array("h")
    offsets: list[float] = []
    for idx, (muestras, pausa_previa_seg) in enumerate(fases_pcm):
        if idx > 0 and pausa_previa_seg > 0:
            n_sil = int(round(pausa_previa_seg * sr))
            if n_sil > 0:
                salida.extend([0] * n_sil)
        offsets.append(len(salida) / sr)
        salida.extend(muestras)
    return salida, offsets


def generar_diseno_sonoro_wav(
    ruta_wav: Path,
    duracion_total_seg: float,
    tiempos_cortes: list[float],
    tiempo_cierre: float,
    *,
    sample_rate: int = 24000,
) -> Path:
    """Sintetiza en stdlib puro una cama armónica muy discreta + whooshes suaves paso-bajo
    en cambios de plano y un pulso cálido en gancho/cierre (0 USD, 0 archivos externos).
    """
    n_total = max(sample_rate, int(round(duracion_total_seg * sample_rate)))
    ciclo_n = sample_rate * 2  # 2.0 s exactos -> frecuencias múltiplos de 0.5 Hz ciclan sin clic
    dos_pi = 2.0 * math.pi

    # 1) Cama armónica cálida sub-180 Hz muy sutil (nunca suena a zumbido sci-fi en las pausas)
    ciclo = array.array("h", [0] * ciclo_n)
    for i in range(ciclo_n):
        t = i / sample_rate
        lfo = 0.86 + 0.14 * math.sin(dos_pi * 0.5 * t)
        onda = (
            0.58 * math.sin(dos_pi * 55.0 * t)
            + 0.28 * math.sin(dos_pi * 110.0 * t)
            + 0.14 * math.sin(dos_pi * 165.0 * t)
        )
        ciclo[i] = int(onda * lfo * 340.0)  # ~ -39 dBFS base, cama casi imperceptible

    reps = (n_total // ciclo_n) + 1
    muestras = (ciclo * reps)[:n_total]

    # Fades suaves de entrada (0.55 s) y salida (1.0 s) sobre la cama
    n_in = min(n_total // 3, int(0.55 * sample_rate))
    for i in range(n_in):
        muestras[i] = int(muestras[i] * (i / max(1, n_in)))
    n_out = min(n_total // 3, int(1.0 * sample_rate))
    for i in range(n_out):
        idx = n_total - 1 - i
        muestras[idx] = int(muestras[idx] * (i / max(1, n_out)))

    def _sumar(idx: int, valor: float) -> None:
        if 0 <= idx < n_total:
            nuevo = muestras[idx] + int(valor)
            muestras[idx] = 32760 if nuevo > 32760 else (-32760 if nuevo < -32760 else nuevo)

    # 2) Sub-hit cálido de gancho en 0.02 s (`diseno-sonoro-pro` §3)
    ini_hook = int(0.02 * sample_rate)
    dur_hook = int(0.28 * sample_rate)
    fase_h = 0.0
    for k in range(dur_hook):
        progreso = k / max(1, dur_hook)
        freq = 72.0 - 30.0 * progreso
        fase_h += dos_pi * freq / sample_rate
        ataque = min(1.0, k / max(1.0, 0.014 * sample_rate))
        env = ataque * math.exp(-5.8 * progreso)
        _sumar(ini_hook + k, math.sin(fase_h) * env * 2100.0)

    # 3) Whoosh grave y sedoso (ruido filtrado paso-bajo) acompañando cada corte visual
    rng = random.Random(42)
    dur_w = int(0.19 * sample_rate)
    for t_corte in tiempos_cortes:
        centro = int(round((t_corte - 0.05) * sample_rate))
        lp1 = 0.0
        lp2 = 0.0
        for k in range(dur_w):
            u = k / max(1, dur_w - 1)
            ventana = 0.5 * (1.0 - math.cos(dos_pi * u))  # Hann suave, cero clics
            fc = 160.0 + 300.0 * ventana
            alfa = min(0.42, (dos_pi * fc) / sample_rate)
            ruido = rng.uniform(-1.0, 1.0)
            lp1 += alfa * (ruido - lp1)
            lp2 += alfa * (lp1 - lp2)
            _sumar(centro + k, lp2 * ventana * 1650.0)

    # 4) Toque sutil de sello/resolución al entrar el cierre
    if 0.3 < tiempo_cierre < duracion_total_seg - 0.2:
        ini_c = int(round(tiempo_cierre * sample_rate))
        dur_c = int(0.36 * sample_rate)
        for k in range(dur_c):
            t_k = k / sample_rate
            ataque = min(1.0, k / max(1.0, 0.012 * sample_rate))
            env = ataque * math.exp(-8.0 * t_k)
            acorde = 0.65 * math.sin(dos_pi * 220.0 * t_k) + 0.35 * math.sin(dos_pi * 330.0 * t_k)
            _sumar(ini_c + k, acorde * env * 1350.0)

    return _escribir_wav_mono(ruta_wav, muestras, sample_rate)


def generar_solo_sfx_reel(props: dict, salida_audio: Path) -> dict[str, object]:
    """Respaldo sin red: genera cama + whooshes sincronizados a la cadencia visual y masteriza a -14 LUFS."""
    gancho = str(props.get("gancho") or "").strip()
    bloques = [str(b).strip() for b in (props.get("bloques") or []) if str(b).strip()]
    cierre = str(props.get("cierre") or "").strip()
    motivos = sales_agent.revisar_guarda_precios(gancho, *bloques, cierre, *(props.get("etiquetas") or []))
    if motivos:
        raise GuardaVozBloqueada(motivos)

    dur_gancho = 2.4
    cadencia = 2.6
    dur_cierre = 3.2
    tiempos_bloques = [round(dur_gancho + i * cadencia, 3) for i in range(len(bloques))]
    tiempo_cierre = round(dur_gancho + len(bloques) * cadencia, 3)
    dur_total = round(tiempo_cierre + dur_cierre, 3)
    cortes = calcular_cortes_visuales(tiempos_bloques, tiempo_cierre, dur_total)

    ffmpeg = _buscar_binario("ffmpeg")
    if not ffmpeg:
        raise ErrorVoz("No se encontró `ffmpeg` para masterizar el diseño sonoro.")
    with tempfile.TemporaryDirectory() as tmp:
        wav_sfx = Path(tmp) / "sfx_reel.wav"
        generar_diseno_sonoro_wav(wav_sfx, dur_total, cortes, tiempo_cierre)
        salida_audio.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            ffmpeg, "-y", "-i", str(wav_sfx),
            "-af", f"aresample=44100,volume=1.6,{FILTRO_MASTER_LUFS}",
            "-t", f"{dur_total:.3f}",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            str(salida_audio),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0 or not salida_audio.exists():
            raise ErrorVoz(f"FFmpeg falló en diseño sonoro: {(proc.stderr or '')[-250:]}")

    nuevos_props = dict(props)
    nuevos_props.update({
        "tiemposBloques": tiempos_bloques,
        "tiempoCierre": tiempo_cierre,
        "tiemposCortes": cortes,
        "duracionFrames": max(90, int(round(dur_total * FPS_REEL))),
    })
    return {"ok": True, "modo": "solo_sfx", "salida_audio": str(salida_audio), "props": nuevos_props}


def _inicios_relativos_desde_marcas(
    frases_fase: list[str], marcas_mapeadas: list[dict[str, object]], dur_fase: float,
) -> list[float]:
    """Extrae los inicios relativos (desde 0.0 s de la fase) para cada frase dentro de la fase."""
    n = len(frases_fase)
    if n == 0:
        return []
    if n == 1:
        return [0.0]
    conteos = [_contar_oraciones_tts(f) for f in frases_fase]
    total_oraciones = sum(conteos)
    if marcas_mapeadas and len(marcas_mapeadas) >= total_oraciones:
        inicios: list[float] = []
        cursor = 0
        for cant in conteos:
            inicios.append(float(marcas_mapeadas[cursor]["offset_seg"]))
            cursor += cant
        return inicios
    if marcas_mapeadas and len(marcas_mapeadas) >= n:
        return [float(m["offset_seg"]) for m in marcas_mapeadas[:n]]
    pesos = [max(1, len(f.split())) for f in frases_fase]
    total_p = sum(pesos) or 1
    inicios = []
    acum = 0.0
    for p in pesos:
        inicios.append((acum / total_p) * dur_fase)
        acum += p
    return inicios


def narrar_reel(
    props: dict, salida_audio: Path, *, cfg: dict[str, str] | None = None, dry_run: bool = False,
) -> dict[str, object]:
    """Genera el máster de voz humanizada (4 tiempos + pausas esculpidas) + SFX sutil a -14 LUFS."""
    cfg = cargar_config_voz() if cfg is None else cfg
    gancho = str(props.get("gancho") or "").strip()
    bloques = [str(b).strip() for b in (props.get("bloques") or []) if str(b).strip()]
    cierre = str(props.get("cierre") or "").strip()

    textos_crudos = [gancho, *bloques, cierre]
    motivos = sales_agent.revisar_guarda_precios(*textos_crudos, *(props.get("etiquetas") or []))
    if motivos:
        raise GuardaVozBloqueada(motivos)

    frases_limpias = [limpiar_para_locucion(t) for t in textos_crudos]
    roles = ["gancho", *(["bloque"] * len(bloques)), "cierre"]
    frases_locucion = [
        humanizar_texto_para_voz(t, rol=rol) for t, rol in zip(textos_crudos, roles)
    ]
    fases = agrupar_fases_reel(frases_locucion, len(bloques))
    proveedor = elegir_proveedor(cfg)
    if dry_run:
        dur_estimadas = [max(1.4, len(f.split()) * 0.38) for f in frases_locucion]
        tl = calcular_timeline_reel(dur_estimadas, len(bloques))
        cortes_dry = calcular_cortes_visuales(
            list(tl["tiemposBloques"]), float(tl["tiempoCierre"]), float(tl["duracion_total_seg"])
        )
        nuevos_props = dict(props)
        nuevos_props.update({
            "tiemposBloques": tl["tiemposBloques"],
            "tiempoCierre": tl["tiempoCierre"],
            "tiemposCortes": cortes_dry,
            "duracionFrames": tl["duracionFrames"],
        })
        return {
            "ok": True, "dry_run": True, "proveedor": proveedor,
            "frases": frases_limpias, "frases_locucion": frases_locucion,
            "fases_narrativas": [
                {"fase": f["fase"], "delta_rate": f["delta_rate"], "pausa_previa_seg": f["pausa_previa_seg"]}
                for f in fases
            ],
            "salida_audio": str(salida_audio),
            "props": nuevos_props,
        }

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        voz_wav = tmp_dir / "voz_esculpida.wav"
        sfx_wav = tmp_dir / "diseno_sonoro.wav"
        sr_trabajo = 24000
        voz_cfg = (cfg.get("VOICE_NAME") or VOZ_EDGE_DEFECTO).strip()
        rate_base = (cfg.get("VOICE_RATE") or ("+4%" if es_voz_multilingual(voz_cfg) else "+6%")).strip()
        pitch_base = (cfg.get("VOICE_PITCH") or "+0Hz").strip()

        if proveedor == "edge_neural":
            proveedor_usado = "edge_neural"
            fases_pcm: list[tuple[array.array, float]] = []
            inicios_por_indice: dict[int, float] = {}
            inicios_rel_por_fase: list[tuple[list[int], list[float]]] = []

            for idx_f, fase in enumerate(fases):
                rate_fase = ajustar_rate_relativo(rate_base, int(fase["delta_rate"]))
                mp3_fase, marcas_fase = sintetizar_edge_con_marcas(
                    str(fase["texto"]), cfg, rate_override=rate_fase, pitch_override=pitch_base,
                )
                mp3_path = tmp_dir / f"fase_{idx_f}.mp3"
                wav_path = tmp_dir / f"fase_{idx_f}.wav"
                mp3_path.write_bytes(mp3_fase)
                _decodificar_a_wav_24k(mp3_path, wav_path, sample_rate=sr_trabajo)
                pcm_crudo, sr_f = _leer_wav_mono(wav_path)
                sr_trabajo = sr_f
                pcm_esc, mapa_t = esculpir_pausas_pcm(
                    pcm_crudo, sr_f, max_pausa_seg=float(fase["max_pausa_interna_seg"]),
                )
                marcas_map = [
                    {**m, "offset_seg": mapear_tiempo_esculpido(float(m.get("offset_seg", 0.0)), mapa_t)}
                    for m in marcas_fase
                ]
                dur_fase = len(pcm_esc) / sr_f
                rel_inicios = _inicios_relativos_desde_marcas(list(fase["frases"]), marcas_map, dur_fase)
                fases_pcm.append((pcm_esc, float(fase["pausa_previa_seg"])))
                inicios_rel_por_fase.append((list(fase["indices"]), rel_inicios))

            pcm_final, offsets_fases = unir_fases_pcm(fases_pcm, sr=sr_trabajo)
            _escribir_wav_mono(voz_wav, pcm_final, sr_trabajo)
            dur_audio = len(pcm_final) / sr_trabajo
            for (indices_f, rels), off_fase in zip(inicios_rel_por_fase, offsets_fases):
                for idx_frase, t_rel in zip(indices_f, rels):
                    inicios_por_indice[idx_frase] = round(INICIO_LOCUCION_SEG + off_fase + t_rel, 3)
            inicios = [
                inicios_por_indice.get(i, round(INICIO_LOCUCION_SEG, 3))
                for i in range(len(frases_locucion))
            ]
        else:
            guion_corrido = " ".join(frases_locucion)
            mp3_bytes, proveedor_usado = sintetizar_mp3(guion_corrido, cfg)
            toma_cruda = tmp_dir / "toma_continua.mp3"
            toma_wav = tmp_dir / "toma_continua.wav"
            toma_cruda.write_bytes(mp3_bytes)
            _decodificar_a_wav_24k(toma_cruda, toma_wav, sample_rate=sr_trabajo)
            pcm_crudo, sr_f = _leer_wav_mono(toma_wav)
            pcm_esc, _ = esculpir_pausas_pcm(pcm_crudo, sr_f, max_pausa_seg=PAUSA_PIVOTE_AB_SEG)
            _escribir_wav_mono(voz_wav, pcm_esc, sr_f)
            dur_audio = len(pcm_esc) / sr_f
            inicios = _extraer_inicios_desde_marcas(frases_locucion, [], dur_audio)

        dur_total = round(INICIO_LOCUCION_SEG + dur_audio + COLA_FINAL_SEG, 3)
        tiempos_bloques = inicios[1:1 + len(bloques)]
        tiempo_cierre = inicios[-1] if len(inicios) >= 2 else round(dur_audio * 0.75, 3)
        duracion_frames = max(90, int(round(dur_total * FPS_REEL)))
        cortes_visuales = calcular_cortes_visuales(tiempos_bloques, tiempo_cierre, dur_total)

        generar_diseno_sonoro_wav(sfx_wav, dur_total, cortes_visuales, tiempo_cierre)

        ffmpeg = _buscar_binario("ffmpeg")
        if not ffmpeg:
            raise ErrorVoz("No se encontró `ffmpeg` para masterizar la toma continua.")
        salida_audio.parent.mkdir(parents=True, exist_ok=True)
        ms_inicio = max(0, int(round(INICIO_LOCUCION_SEG * 1000)))
        fade_out_st = max(0.1, dur_total - 0.18)
        filtro_mix = (
            f"[0:a]aresample=44100,afade=t=in:st=0:d=0.015,"
            f"adelay={ms_inicio}|{ms_inicio},{FILTRO_CADENA_VOZ},"
            f"apad=whole_dur={dur_total:.3f}[voz];"
            f"[1:a]aresample=44100,volume=0.22[sfx];"
            f"[voz][sfx]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
            f"{FILTRO_MASTER_LUFS},afade=t=out:st={fade_out_st:.3f}:d=0.16[outa]"
        )
        cmd_master = [
            ffmpeg, "-y",
            "-i", str(voz_wav),
            "-i", str(sfx_wav),
            "-filter_complex", filtro_mix,
            "-map", "[outa]",
            "-t", f"{dur_total:.3f}",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            str(salida_audio),
        ]
        proc = subprocess.run(cmd_master, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0 or not salida_audio.exists():
            raise ErrorVoz(f"FFmpeg falló al masterizar toma continua: {(proc.stderr or '')[-300:]}")

    nuevos_props = dict(props)
    nuevos_props.update({
        "tiemposBloques": tiempos_bloques,
        "tiempoCierre": tiempo_cierre,
        "tiemposCortes": cortes_visuales,
        "duracionFrames": duracion_frames,
    })
    return {
        "ok": True,
        "dry_run": False,
        "proveedor": proveedor_usado,
        "voz": (cfg.get("VOICE_NAME") or VOZ_EDGE_DEFECTO).strip(),
        "salida_audio": str(salida_audio),
        "duracion_seg": dur_total,
        "cortes_sonoros": len(cortes_visuales),
        "props": nuevos_props,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Motor de voz humana neuronal de El Socio.")
    parser.add_argument("--texto", default="", help="Frase suelta para probar locución en MP3.")
    parser.add_argument("--reel-props", default="", help="JSON de props de ReelVertical.")
    parser.add_argument("--solo-sfx", action="store_true",
                        help="Genera solo cama sutil + whooshes a -14 LUFS cuando no hay red TTS.")
    parser.add_argument("--voz", default="", help="Nombre de voz neuronal opcional para pruebas.")
    parser.add_argument("--out", default="", help="Ruta de salida (.mp3 o .m4a).")
    parser.add_argument("--out-props", default="", help="Archivo donde guardar los props sincronizados.")
    parser.add_argument("--dry-run", action="store_true", help="Valida sin llamar a red ni escribir audio.")
    args = parser.parse_args(argv)
    if args.voz:
        os.environ["VOICE_NAME"] = args.voz

    try:
        if args.reel_props:
            props = json.loads(args.reel_props)
            salida = Path(args.out) if args.out else (VOZ_DIR / "reel_voz.m4a")
            if args.solo_sfx and not args.dry_run:
                res = generar_solo_sfx_reel(props, salida)
            else:
                res = narrar_reel(props, salida, dry_run=args.dry_run)
            if args.out_props and not args.dry_run:
                Path(args.out_props).write_text(
                    json.dumps(res["props"], ensure_ascii=False), encoding="utf-8",
                )
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0

        if args.texto:
            salida = Path(args.out) if args.out else (VOZ_DIR / "locucion.mp3")
            if args.dry_run:
                motivos = sales_agent.revisar_guarda_precios(args.texto)
                if motivos:
                    raise GuardaVozBloqueada(motivos)
                print(json.dumps({
                    "ok": True, "dry_run": True,
                    "texto_limpio": limpiar_para_locucion(args.texto),
                    "proveedor": elegir_proveedor(cargar_config_voz()),
                }, ensure_ascii=False, indent=2))
                return 0
            VOZ_DIR.mkdir(parents=True, exist_ok=True)
            mp3_bytes, prov = sintetizar_mp3(args.texto)
            salida.parent.mkdir(parents=True, exist_ok=True)
            salida.write_bytes(mp3_bytes)
            print(json.dumps({
                "ok": True, "proveedor": prov, "archivo": str(salida), "bytes": len(mp3_bytes),
            }, ensure_ascii=False, indent=2))
            return 0

        parser.error("Indica --texto o --reel-props.")
    except GuardaVozBloqueada as exc:
        print("BLOQUEADO por guarda de precios en voz:", "; ".join(exc.motivos), file=sys.stderr)
        return 2
    except ErrorVoz as exc:
        print(f"Error de voz: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

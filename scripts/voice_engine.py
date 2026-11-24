#!/usr/bin/env python3
"""Motor de locución humana neuronal y sincronía para Reels de El Socio.

Cero dependencias externas (100% Python stdlib) y cero voces robóticas (`say` prohibido).
Soporta 3 motores humanos automáticos según lo disponible en `.env`:
  1. `elevenlabs`  — si existe `ELEVENLABS_API_KEY` (estudio hiperrealista).
  2. `openai`      — si existe `OPENAI_API_KEY` (`gpt-4o-mini-tts`, dirección actoral).
  3. `edge_neural` — por defecto (0 USD, 0 claves): voz neuronal colombiana
                     `es-CO-GonzaloNeural` por WebSocket TLS + `Sec-MS-GEC` v2.

Además:
  - Pasa cada frase por `sales_agent.revisar_guarda_precios()` ANTES de hablar.
  - Limpia símbolos visuales (`·`, `|`, URLs) para que jamás lea "punto medio".
  - Sintetiza por bloque, calcula tiempos exactos para que cada subtítulo de
    `ReelVertical.tsx` entre en el milisegundo en que habla la voz, y masteriza
    con cadena vocal profesional a -14 LUFS (`ffmpeg`).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
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

# Voces neuronales humanas recomendadas (español natural, cero robot).
# `en-US-AndrewMultilingualNeural` es el modelo conversacional cálido de nueva generación
# (categoría Conversation/Copilot: Warm, Confident, Authentic) hablando en `<lang xml:lang='es-CO'>`.
VOZ_EDGE_DEFECTO = "en-US-AndrewMultilingualNeural"
VOZ_OPENAI_DEFECTO = "ash"                   # La voz más cálida y conversacional de OpenAI
VOZ_ELEVEN_DEFECTO = "pNInz6obpgDQGcFmaJgB"  # Multilingual v2

FPS_REEL = 30
INICIO_LOCUCION_SEG = 0.10
MIN_GANCHO_SEG = 1.8
MIN_BLOQUE_SEG = 1.85
MIN_CIERRE_SEG = 2.0
PAUSA_ENTRE_FRASES_SEG = 0.22
COLA_FINAL_SEG = 0.55

# Cadena vocal cálida de podcast cercano: cuerpo en pecho (155Hz), cero brillo metálico y dinámica viva (LRA=11).
FILTRO_MASTER_VOZ = (
    "highpass=f=70,"
    "equalizer=f=155:t=q:w=1.1:g=2.2,"
    "equalizer=f=320:t=q:w=1.3:g=-1.2,"
    "equalizer=f=3200:t=q:w=1.4:g=0.9,"
    "acompressor=threshold=-20dB:ratio=2.2:attack=18:release=180,"
    "loudnorm=I=-14:TP=-1.0:LRA=11"
)

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


def _buscar_binario(nombre: str) -> str | None:
    """Encuentra `ffmpeg` / `ffprobe` incluso cuando `launchd` recorta el PATH."""
    hallado = shutil.which(nombre)
    if hallado:
        return hallado
    for carpeta in ("/usr/local/bin", "/opt/homebrew/bin", "/usr/bin"):
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
        "Accept-Language: en-US,en;q=0.9\r\n"
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
            ssml = (
                "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
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


def sintetizar_edge_con_marcas(texto: str, cfg: dict[str, str]) -> tuple[bytes, list[dict[str, object]]]:
    voz = (cfg.get("VOICE_NAME") or VOZ_EDGE_DEFECTO).strip()
    rate = (cfg.get("VOICE_RATE") or "+4%").strip()
    pitch = (cfg.get("VOICE_PITCH") or "+0Hz").strip()
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
            "Habla en español colombiano natural, seguro y sobrio, como un socio "
            "de negocios tranquilo y cercano. Cero tono de comercial exagerado."
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
        "voice_settings": {"stability": 0.55, "similarity_boost": 0.80, "style": 0.15},
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
    limpio = limpiar_para_locucion(texto)
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


def narrar_reel(
    props: dict, salida_audio: Path, *, cfg: dict[str, str] | None = None, dry_run: bool = False,
) -> dict[str, object]:
    """Genera el máster de voz `.m4a` sincronizado y devuelve los `props` actualizados."""
    cfg = cargar_config_voz() if cfg is None else cfg
    gancho = str(props.get("gancho") or "").strip()
    bloques = [str(b).strip() for b in (props.get("bloques") or []) if str(b).strip()]
    cierre = str(props.get("cierre") or "").strip()

    textos_crudos = [gancho, *bloques, cierre]
    motivos = sales_agent.revisar_guarda_precios(*textos_crudos, *(props.get("etiquetas") or []))
    if motivos:
        raise GuardaVozBloqueada(motivos)

    frases_limpias = [limpiar_para_locucion(t) for t in textos_crudos]
    proveedor = elegir_proveedor(cfg)
    if dry_run:
        dur_estimadas = [max(1.2, len(f.split()) * 0.38) for f in frases_limpias]
        tl = calcular_timeline_reel(dur_estimadas, len(bloques))
        nuevos_props = dict(props)
        nuevos_props.update({
            "tiemposBloques": tl["tiemposBloques"],
            "tiempoCierre": tl["tiempoCierre"],
            "duracionFrames": tl["duracionFrames"],
        })
        return {
            "ok": True, "dry_run": True, "proveedor": proveedor,
            "frases": frases_limpias, "salida_audio": str(salida_audio),
            "props": nuevos_props,
        }

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        guion_corrido = "\n".join(frases_limpias)
        toma_cruda = tmp_dir / "toma_continua.mp3"
        marcas: list[dict[str, object]] = []

        if proveedor == "edge_neural":
            mp3_bytes, marcas = sintetizar_edge_con_marcas(guion_corrido, cfg)
            proveedor_usado = "edge_neural"
        else:
            mp3_bytes, proveedor_usado = sintetizar_mp3(guion_corrido, cfg)

        toma_cruda.write_bytes(mp3_bytes)
        dur_audio = medir_duracion_audio(toma_cruda, mp3_bytes)
        dur_total = round(INICIO_LOCUCION_SEG + dur_audio + COLA_FINAL_SEG, 3)

        # Extraer tiempos reales de entrada de cada bloque a partir de las marcas de oración
        # de la toma continua (o proporcional por palabras si viene de OpenAI/ElevenLabs).
        n_frases = len(frases_limpias)
        if len(marcas) >= n_frases:
            # Mapear las últimas (n_bloques + 1) frases o índices directos si coinciden exactos.
            inicios = [round(INICIO_LOCUCION_SEG + float(m["offset_seg"]), 3) for m in marcas[:n_frases]]
        else:
            pesos = [max(1, len(f.split())) for f in frases_limpias]
            total_p = sum(pesos) or 1
            inicios = []
            acum = 0.0
            for p in pesos:
                inicios.append(round(INICIO_LOCUCION_SEG + (acum / total_p) * dur_audio, 3))
                acum += p

        tiempos_bloques = inicios[1:1 + len(bloques)]
        tiempo_cierre = inicios[-1] if len(inicios) >= 2 else round(dur_audio * 0.75, 3)
        duracion_frames = max(90, int(round(dur_total * FPS_REEL)))

        ffmpeg = _buscar_binario("ffmpeg")
        if not ffmpeg:
            raise ErrorVoz("No se encontró `ffmpeg` para masterizar la toma continua.")
        salida_audio.parent.mkdir(parents=True, exist_ok=True)
        ms_inicio = max(0, int(round(INICIO_LOCUCION_SEG * 1000)))
        cmd_master = [
            ffmpeg, "-y", "-i", str(toma_cruda),
            "-af", (
                f"aresample=44100,afade=t=in:st=0:d=0.015,"
                f"adelay={ms_inicio}|{ms_inicio},{FILTRO_MASTER_VOZ},"
                f"apad=whole_dur={dur_total:.3f},"
                f"afade=t=out:st={max(0.1, dur_total - 0.14):.3f}:d=0.12"
            ),
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
        "duracionFrames": duracion_frames,
    })
    return {
        "ok": True,
        "dry_run": False,
        "proveedor": proveedor_usado,
        "voz": (cfg.get("VOICE_NAME") or VOZ_EDGE_DEFECTO).strip(),
        "salida_audio": str(salida_audio),
        "duracion_seg": dur_total,
        "props": nuevos_props,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Motor de voz humana neuronal de El Socio.")
    parser.add_argument("--texto", default="", help="Frase suelta para probar locución en MP3.")
    parser.add_argument("--reel-props", default="", help="JSON de props de ReelVertical.")
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

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
import re
import shutil
import subprocess
import sys
from datetime import datetime
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
GENERAR_HISTORIA = REDES_DIR / "generar_historia.sh"
GENERAR_CARRUSEL = REDES_DIR / "generar_carrusel.sh"
CARRUSELES_DIR = REDES_DIR / "carruseles"

# Carrusel de Instagram (1080x1350): portada (gancho) + láminas de desarrollo + lámina de cierre.
# Instagram admite de 2 a 10; El Socio usa de 3 a 6 láminas de contenido para que se lean completas.
MIN_LAMINAS_CARRUSEL = 3
MAX_LAMINAS_CARRUSEL = 6
CIERRE_CARRUSEL_DEFECTO = "Escríbenos tu caso por mensaje directo"

# Un reel de El Socio: gancho en pantalla desde el frame 1, estructura A vs B (5-8 bloques -> 18-28 s).
MAX_BLOQUES = 8
TIMEOUT_RENDER = 1800  # segundos; el render por frames en este Mac puede tardar ~15-20 min en reels largos

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
# Los planos (una toma de cámara por frase) viajan en su propia línea como JSON compacto.
_MARCA_PLANOS = "[planos]"

# Vocabulario del motor `ReelMundo` (`redes/video-logo/src/ReelMundo.tsx` y `mundo/interiores.tsx`).
# Si se agrega una toma, un foco o una tarjeta allá, se agrega aquí.
TOMAS = ("ciudad", "pareja", "calle", "local", "detalle")
ESTADOS_PLANO = ("caos", "orden")
TARJETAS = ("correo", "agenda", "ficha", "catalogo", "render", "chat", "ninguna")
FOCOS = {
    "taller": ("centro", "mesa", "pared", "ficha", "audios", "maquinas", "perchero", "maniqui", "lote", "persona"),
    "obra": ("centro", "pared", "andamio", "plano", "sala", "sofa", "ventana", "persona", "cables"),
    "estudio": ("centro", "inventario", "producto", "luces", "celular", "camara", "pantalla", "ropa", "persona"),
    "oficina": ("centro", "escritorio", "pantalla", "agenda", "calendario", "telefono", "papeles", "persona", "correo"),
}
TODOS_LOS_FOCOS = frozenset(f for lista in FOCOS.values() for f in lista)

# Formatos de Reel (cada uno aprendido de una referencia, ver `contexto/guia-estilo-video.md` §6, §10, §11).
# Todos usan la misma voz, la misma línea de tiempo y el mismo cierre de venta; cambia lo que se ve.
FORMATOS = ("mundo", "collage", "duelo")
# Objetos-metáfora del formato collage (`redes/video-logo/src/ReelCollage.tsx`).
OBJETOS_COLLAGE = (
    "iman", "pecera", "diana", "clasificadora", "tostadora", "embudo", "agenda", "reloj", "papeles",
    "telefono", "etiqueta", "pantalla", "ficha", "plano", "camara", "cajas", "maquina", "producto",
)
MAX_LARGO_TOOLTIP = 26
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


def normalizar_planos(planos: list | None) -> list[dict]:
    """Limpia la lista de planos (una toma por frase: gancho, bloques..., cierre).

    Es tolerante a propósito: un campo con un valor que el motor no conoce se descarta y el
    motor lo deduce de las palabras de la frase. Lo que NO se limpia es el texto del tooltip:
    si trae una cifra, la guarda de precios bloquea la pieza entera (no se maquilla).
    """
    limpios: list[dict] = []
    for bruto in (planos or [])[: MAX_BLOQUES + 2]:
        if not isinstance(bruto, dict):
            limpios.append({})
            continue
        plano: dict = {}
        toma = str(bruto.get("toma") or "").strip().lower()
        if toma in TOMAS:
            plano["toma"] = toma
        lado = str(bruto.get("lado") or "").strip().upper()
        if lado in ("A", "B"):
            plano["lado"] = lado
        foco = str(bruto.get("foco") or "").strip().lower()
        if foco in TODOS_LOS_FOCOS:
            plano["foco"] = foco
        estado = str(bruto.get("estado") or "").strip().lower()
        if estado in ESTADOS_PLANO:
            plano["estado"] = estado
        tarjeta = str(bruto.get("tarjeta") or "").strip().lower()
        if tarjeta in TARJETAS:
            plano["tarjeta"] = tarjeta
        objeto = str(bruto.get("objeto") or "").strip().lower()
        if objeto in OBJETOS_COLLAGE:
            plano["objeto"] = objeto
        tooltip = " ".join(str(bruto.get("tooltip") or "").split())
        if tooltip:
            plano["tooltip"] = tooltip[:MAX_LARGO_TOOLTIP]
        limpios.append(plano)
    # Si ningún plano dice nada útil, no se guarda nada: el motor deduce todo solo.
    return limpios if any(limpios) else []


def tooltips_de(planos: list[dict] | None) -> list[str]:
    """Textos que acaban quemados en el video como tooltip: pasan por la guarda igual que todo."""
    return [p["tooltip"] for p in (planos or []) if isinstance(p, dict) and p.get("tooltip")]


def nota_humana(nota: str | None) -> str:
    """La nota tal como la escribió una persona, sin las líneas de configuración."""
    lineas = [
        l for l in (nota or "").splitlines()
        if not l.strip().startswith(_MARCA_REEL) and not l.strip().startswith(_MARCA_PLANOS)
    ]
    return "\n".join(lineas).strip()


def componer_nota(
    nota: str | None, escena: str, etiquetas: list[str], planos: list[dict] | None = None,
    formato: str = "",
) -> str:
    """Mete escena, etiquetas, formato y planos en `nota` sin pisar lo que escribió una persona."""
    humano = nota_humana(nota)
    campos: list[str] = []
    if formato and formato in FORMATOS:
        campos.append(f"formato={formato}")
    if escena and escena != ESCENA_DEFECTO:
        campos.append(f"escena={escena}")
    if etiquetas:
        campos.append("etiquetas=" + _SEP_ETIQUETAS.join(etiquetas))
    lineas = [humano] if humano else []
    if campos:
        lineas.append(f"{_MARCA_REEL} " + f"{_SEP_CAMPOS} ".join(campos))
    if planos:
        lineas.append(f"{_MARCA_PLANOS} " + json.dumps(planos, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lineas)


def leer_formato(nota: str | None) -> str:
    """Formato de Reel guardado en la nota ('' si la pieza es de antes de los formatos)."""
    for linea in (nota or "").splitlines():
        linea = linea.strip()
        if not linea.startswith(_MARCA_REEL):
            continue
        for campo in linea[len(_MARCA_REEL):].split(_SEP_CAMPOS):
            clave, _, valor = campo.partition("=")
            if clave.strip().lower() == "formato" and valor.strip().lower() in FORMATOS:
                return valor.strip().lower()
    return ""


def formatos_recientes(limite: int = 12) -> list[str]:
    """Formatos de los últimos reels encolados, del más nuevo al más viejo."""
    try:
        piezas = database.list_content(limit=limite * 3)
    except Exception:  # noqa: BLE001 — sin BD no hay historial; se rota desde cero
        return []
    return [f for f in (leer_formato(p.get("nota")) for p in piezas if p.get("tipo") == "video") if f][:limite]


def elegir_formato(sugerido: str = "", recientes: list[str] | None = None) -> str:
    """Rotación: nunca dos reels seguidos con el mismo formato.

    Se respeta lo que sugiera el cerebro si no repite el último. Si repite (o no sugiere nada),
    gana el formato menos usado en la última vuelta, para que el feed no se vea siempre igual.
    """
    recientes = formatos_recientes() if recientes is None else recientes
    ultimo = recientes[0] if recientes else ""
    sugerido = (sugerido or "").strip().lower()
    if sugerido in FORMATOS and sugerido != ultimo:
        return sugerido
    ventana = recientes[: len(FORMATOS) * 2]
    candidatos = [f for f in FORMATOS if f != ultimo] or list(FORMATOS)
    return min(candidatos, key=lambda f: (ventana.count(f), FORMATOS.index(f)))


def leer_planos(nota: str | None) -> list[dict]:
    """Saca los planos guardados en la nota. Si la línea está rota, se ignora (el motor deduce)."""
    for linea in (nota or "").splitlines():
        linea = linea.strip()
        if linea.startswith(_MARCA_PLANOS):
            try:
                return normalizar_planos(json.loads(linea[len(_MARCA_PLANOS):].strip()))
            except (ValueError, TypeError):
                return []
    return []


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


def escenas_usadas_hoy() -> set[str]:
    """Escenas isométricas ya encoladas hoy (cualquier tipo): piezas del mismo día no deben
    reciclar el mismo fondo/cámara, aunque hablen de nichos distintos."""
    if not database.DB_PATH.exists():
        return set()
    hoy = datetime.now().strftime("%Y-%m-%d")
    usadas: set[str] = set()
    for p in database.list_content(limit=60):
        if not str(p.get("created_at") or "").startswith(hoy):
            continue
        if str(p.get("estado") or "") == "descartado":
            continue
        escena, _ = leer_reel(p.get("nota"))
        usadas.add(escena)
    return usadas


# ------------------------------------------------------------------ la guarda de precios

def revisar_pieza(
    gancho: str, guion: str = "", caption: str = "", etiquetas: list[str] | None = None,
) -> list[str]:
    """Misma guarda que usa el agente de ventas, aplicada al contenido de redes.

    Las etiquetas entran igual que el resto: son texto que acaba QUEMADO en el video,
    y un "desde 50.000" dentro de un tooltip es exactamente el mismo problema.

    Devuelve los motivos por los que NO puede salir. Vacío = puede salir.
    """
    motivos = sales_agent.revisar_guarda_precios(gancho, guion, caption, *(etiquetas or []))
    motivos.extend(_cifras_en_pantalla(gancho, guion, caption, *(etiquetas or [])))
    motivos.extend(_pide_interaccion(gancho, guion, caption, *(etiquetas or [])))
    return motivos


# Un dígito suelto que no es precio igual es una cifra en pantalla: "sale en 15 días", "3 semanas".
# La guarda de ventas lo deja pasar a propósito (en un correo "te respondo en 2 días" es normal),
# pero la guía de video §4 prohíbe TODA cifra en el video: ni precios, ni plazos, ni resultados.
# Los tooltips y rótulos ya salen sin dígitos porque el motor los recorta en código; esto cierra
# la última puerta, que es el texto hablado y quemado del titular.
_RE_DIGITO = re.compile(r"\d")


def _cifras_en_pantalla(*textos: str) -> list[str]:
    malos: list[str] = []
    for t in textos:
        if _RE_DIGITO.search(str(t or "")):
            malos.append(f"cifra_en_pantalla: {' '.join(str(t).split())[:60]!r}")
    return malos


# La interaccion se MERECE, no se pide. Un reel que dice "comenta SI si te pasa" sube el contador
# hoy y quema la credibilidad que es justo lo que se esta vendiendo. Peor: el ciclo de insights
# aprenderia que la carnada paga (es la forma mas confiable de producir comentarios) y produciria
# mas de eso hasta que la cuenta sea indistinguible de cualquier cuenta de bajo esfuerzo.
# Va como guarda y no como instruccion del prompt a proposito: una instruccion se obedece hoy y se
# diluye en tres semanas; una guarda rechaza la pieza y no se negocia.
#
# Se exige PAREJA (verbo imperativo + objeto de plataforma) para no censurar el habla normal:
# "el taller guarda las telas" y "el local comparte pared con el vecino" tienen que seguir pasando.
# Se compara sobre el texto sin tildes, asi que los patrones van sin tildes.
_VERBO_PEDIR_COMENTARIO = (
    r"coment(?:a|ame|amelo|en)|escrib(?:e|eme)|dime|digame|cuentame|"
    r"dej(?:a|ame|alo)|respond(?:e|eme)"
)
_OBJETO_COMENTARIO = r"comentario|comentarios|abajo|aqui|aca|debajo"
_VERBO_PEDIR_ACCION = (
    r"dale|pon(?:me|ga)?|mand(?:a|ame)|etiquet(?:a|en)|compart(?:e|elo|an)|"
    r"guard(?:a|alo)|activ(?:a|en)|sube"
)
_OBJETO_ACCION = (
    r"like|likes|me gusta|corazon|emoji|notificacion|notificaciones|"
    r"este post|este reel|este video|esta publicacion|"
    r"a (?:un|una|algun|alguien)"
)
# Lo que es carnada por si solo, sin necesitar objeto.
_PEDIDO_SUELTO = r"sigueme|siguenos|doble tap|dale like|link en bio|comenta ya"

_RE_PEDIR = (
    re.compile(rf"\b(?:{_VERBO_PEDIR_COMENTARIO})\b[^.!?]{{0,24}}?\b(?:{_OBJETO_COMENTARIO})\b"),
    re.compile(rf"\b(?:{_VERBO_PEDIR_ACCION})\b[^.!?]{{0,24}}?\b(?:{_OBJETO_ACCION})\b"),
    re.compile(rf"\b(?:{_PEDIDO_SUELTO})\b"),
    # "Comenta SI si te pasa" es el arquetipo y no trae objeto: pide escribir una palabra suelta.
    # Se ancla al ARRANQUE de frase para leerlo como imperativo y no pisar el presente de tercera
    # persona, que se escribe igual ("el cliente comenta que no le gusto" tiene que pasar).
    re.compile(r"(?:^|[.!?]\s*)coment(?:a|en|ale)\b"),
)


def _pide_interaccion(*textos: str) -> list[str]:
    """Carnada de interaccion: pedir comentario, like, guardado, compartido o seguimiento."""
    malos: list[str] = []
    for t in textos:
        limpio = _sin_tildes(str(t or ""))
        for rx in _RE_PEDIR:
            m = rx.search(limpio)
            if m:
                malos.append(f"pide_interaccion: {m.group(0)[:40]!r}")
                break
    return malos


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
    planos: list[dict] | None = None, formato: str = "", dry_run: bool = False,
) -> dict:
    """Mete una pieza en la cola. La guarda corre ANTES de tocar la BD."""
    escena_ok = normalizar_escena(escena)
    etiquetas_ok = normalizar_etiquetas(etiquetas)
    planos_ok = normalizar_planos(planos) if tipo == "video" else []
    formato_ok = elegir_formato(formato) if tipo == "video" else ""
    _exigir_guarda(gancho, guion, caption, etiquetas_ok + tooltips_de(planos_ok))
    nota_final = componer_nota(nota, escena_ok, etiquetas_ok, planos_ok, formato_ok)
    if dry_run:
        return {
            "encolado": False, "dry_run": True, "tipo": tipo, "gancho": gancho,
            "escena": escena_ok, "etiquetas": etiquetas_ok,
        }
    content_id = database.enqueue_content(
        tipo=tipo, gancho=gancho, guion=guion, caption=caption, nicho=nicho, nota=nota_final,
    )
    return {"encolado": True, "id": content_id, "escena": escena_ok, "etiquetas": etiquetas_ok,
            "formato": formato_ok}


_MAPA_BADGE_NICHO = {
    "modelado-3d-espacios": "ESPACIOS",
    "fichas-tecnicas-ropa": "CONFECCIÓN",
    "ecommerce-catalogo-visual": "CATÁLOGO",
    "automatizacion-agencias-estudios": "AGENCIAS",
    "general": "HISTORIA",
}


def _badge_de_nicho(nicho: str | None) -> str:
    clave = (nicho or "").strip().lower()
    if clave in _MAPA_BADGE_NICHO:
        return _MAPA_BADGE_NICHO[clave]
    limpio = "".join(c if c.isalpha() or c in " áéíóúñ" else " " for c in clave).strip().upper()
    primera = next((w for w in limpio.split() if len(w) >= 4), "")
    return primera[:16] if primera else "HISTORIA"


# Cierre de VENTA de los reels (lo dice la voz y lo cierra la tarjeta de marca de ReelMundo).
# "Link en bio" no va dentro del video: se ve barato. El link vive en el pie de publicación.
LINEA_MARCA = "Con El Socio, te lo solucionamos."

# El cuerpo del reel siempre muestra un lugar (Taller/Local/Tienda/Agencia) pasando de caos (A) a
# orden (B) — así lo pide la guía de estilo (§2, §6: "A vs B, literal"). El cierre tiene que nombrar
# ESE MISMO lugar para decir sin dudas cuál de los dos es el que trabaja con El Socio. Antes rotaba
# con cierres de "persona" o frases sueltas sin A/B, y el video terminaba hablando de algo distinto a
# lo que mostró: quedaba sin decir cuál era el bueno. Un solo cierre, siempre.
_LOTE_POR_NICHO = {
    "fichas-tecnicas-ropa": ("el", "Taller"),
    "modelado-3d-espacios": ("el", "Local"),
    "ecommerce-catalogo-visual": ("la", "Tienda"),
    "automatizacion-agencias-estudios": ("la", "Agencia"),
}
# Mismas pistas que `PALABRAS_NICHO` de ReelMundo.tsx: el texto del cierre tiene que nombrar
# el mismo local que la cámara está mostrando.
_PISTAS_NICHO = (
    ("fichas-tecnicas-ropa", r"taller|confecc|costur|patron|tela|prenda|ropa|coleccion|lote|muestra|marca de ropa|corte"),
    ("modelado-3d-espacios", r"remodel|obra|pared|sala|habitaci|espacio|local|render|plano|apartament|casa|mueble|cocina|arquitect|maestro"),
    ("ecommerce-catalogo-visual", r"catalogo|foto|producto|tienda|inventario|ecommerce|e-commerce|instagram|vitrina|modelo"),
    ("automatizacion-agencias-estudios", r"correo|email|cliente|agenda|reunion|seguimiento|lead|agencia|bandeja|mensaje|whatsapp|llamada|propuesta|cita"),
)


def _sin_tildes(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def nicho_visual(nicho: str | None, textos: list[str]) -> str:
    """El nicho que ReelMundo va a dibujar: el declarado si lo conoce, si no el que más nombra el guion."""
    import re
    clave = (nicho or "").strip().lower()
    if clave in _LOTE_POR_NICHO:
        return clave
    todo = _sin_tildes(" ".join(textos))
    mejor, puntos = "fichas-tecnicas-ropa", -1
    for nombre, patron in _PISTAS_NICHO:
        n = len(re.findall(patron, todo))
        if n > puntos:
            mejor, puntos = nombre, n
    return mejor


def cierre_de_venta(nicho: str | None, textos: list[str]) -> str:
    """'No seas el Taller A. Sé el Taller B.' — siempre nombra el mismo lugar que mostró el reel."""
    articulo, lugar = _LOTE_POR_NICHO[nicho_visual(nicho, textos)]
    return f"No seas {articulo} {lugar} A. Sé {articulo} {lugar} B. {LINEA_MARCA}"


def _bloques_de(guion: str) -> list[str]:
    """El guion se parte en bloques por línea. Cada bloque es un plano de ~2 s."""
    bloques = [l.strip() for l in (guion or "").splitlines() if l.strip()]
    return bloques[:MAX_BLOQUES]


def laminas_carrusel(gancho: str, guion: str) -> list[str]:
    """Portada + desarrollo + cierre. La última línea del guion es la lámina de cierre."""
    lineas = [l.strip() for l in (guion or "").splitlines() if l.strip()]
    if not lineas:
        return [gancho.strip(), CIERRE_CARRUSEL_DEFECTO]
    *desarrollo, cierre = lineas if len(lineas) > 1 else (lineas + [CIERRE_CARRUSEL_DEFECTO])
    return [gancho.strip(), *desarrollo[:MAX_LAMINAS_CARRUSEL], cierre]


def archivos_carrusel(archivo: str | Path | None) -> list[Path]:
    """Todas las láminas renderizadas de un carrusel a partir de la primera (`..._01.png`)."""
    if not archivo:
        return []
    primera = Path(str(archivo))
    base = primera.stem.rsplit("_", 1)[0]
    return sorted(p for p in primera.parent.glob(f"{base}_[0-9][0-9].png") if p.is_file())


def generar(
    content_id: int, *, escena: str = "", etiquetas: list[str] | None = None,
    planos: list[dict] | None = None, formato: str = "", dry_run: bool = False,
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

    planos_ok = normalizar_planos(planos) if planos is not None else leer_planos(pieza["nota"])
    formato_ok = (formato if formato in FORMATOS else leer_formato(pieza["nota"])) or "mundo"

    _exigir_guarda(
        pieza["gancho"], pieza["guion"] or "", pieza["caption"] or "",
        etiquetas_ok + tooltips_de(planos_ok))

    nombre = f"content_{content_id:04d}"
    if pieza["tipo"] == "post":
        cmd = [str(GENERAR_POST), pieza["gancho"], nombre]
        salida = REDES_DIR / "posts" / f"{nombre}.png"
    elif pieza["tipo"] == "historia":
        subtexto = " ".join(_bloques_de(pieza["guion"])[:2])
        cap_crudo = (pieza["caption"] or "").strip()
        cierre_hist = (
            cap_crudo.splitlines()[0].strip()[:62]
            if cap_crudo else "Responde esta historia con tu caso"
        )
        badge_hist = _badge_de_nicho(pieza.get("nicho"))
        tema_hist = "crema" if (int(content_id) % 2 == 0) else "oscuro"
        cmd = [str(GENERAR_HISTORIA), pieza["gancho"], nombre, subtexto, cierre_hist, badge_hist, tema_hist]
        salida = REDES_DIR / "historias" / f"{nombre}.png"
    elif pieza["tipo"] == "carrusel":
        props_carrusel = {
            "laminas": laminas_carrusel(pieza["gancho"], pieza["guion"] or ""),
            "badge": _badge_de_nicho(pieza.get("nicho")),
            "tema": "crema" if (int(content_id) % 2 == 0) else "oscuro",
        }
        cmd = [str(GENERAR_CARRUSEL), json.dumps(props_carrusel, ensure_ascii=False), nombre]
        salida = CARRUSELES_DIR / f"{nombre}_01.png"
    else:
        bloques_reel = _bloques_de(pieza["guion"])
        cierre_reel = cierre_de_venta(pieza.get("nicho"), [pieza["gancho"], *bloques_reel])
        props_reel = {
            "gancho": pieza["gancho"],
            "bloques": bloques_reel,
            "cierre": cierre_reel,
            "nicho": (pieza.get("nicho") or "").strip(),
            "escena": escena_ok,
            "etiquetas": etiquetas_ok,
        }
        props_reel["formato"] = formato_ok
        if planos_ok:
            props_reel["planos"] = planos_ok
        props = json.dumps(props_reel, ensure_ascii=False)
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

    nota_final = componer_nota(
        pieza["nota"], escena_ok, etiquetas_ok, planos_ok,
        formato_ok if pieza["tipo"] == "video" else "")
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
    nota_final = (
        componer_nota(nota, *leer_reel(pieza["nota"]), leer_planos(pieza["nota"]),
                      leer_formato(pieza["nota"])) if nota else None
    )
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


# ------------------------------------------------------------------ paquete para subir a mano

# Mientras no haya claves de Instagram (`IG_USER_ID` + `IG_ACCESS_TOKEN`), Raymond sube a mano:
# esta carpeta agrupa TODO lo ya renderizado y aún no publicado, con nombres simples y su caption
# a la mano. Se rearma completa en cada corrida (nunca acumula piezas de una corrida vieja).
PAQUETE_DIR = REDES_DIR / "paquete_hoy"
_NOMBRE_TIPO = {"video": "reel", "historia": "historia", "post": "post", "carrusel": "carrusel"}


def armar_paquete_pendiente(destino: Path | None = None) -> dict:
    """Agrupa toda pieza `generado` (renderizada, sin publicar) en una sola carpeta plana.

    Se sobrescribe completa cada vez: lo que ya se marcó `publicado` (con
    `content_manager.py publicar`) desaparece solo del paquete la próxima corrida.
    """
    destino = PAQUETE_DIR if destino is None else Path(destino)
    pendientes = sorted(
        (p for p in database.list_content(estado="generado", limit=200) if p.get("archivo")),
        key=lambda p: int(p["id"]),
    )

    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True, exist_ok=True)

    if not pendientes:
        (destino / "LEEME.txt").write_text(
            "No hay piezas pendientes de publicar ahora mismo.\n", encoding="utf-8")
        return {"armado": True, "piezas": 0, "carpeta": str(destino)}

    contador = {"video": 0, "historia": 0, "post": 0, "carrusel": 0}
    lineas = [
        f"Paquete de El Socio listo para subir a mano — {len(pendientes)} pieza(s).",
        "Súbelas en Instagram tal cual (Reel / Post / Historia / Carrusel según el nombre).",
        "El pie de publicación (caption) de cada una está debajo de su nombre de archivo.",
        "",
    ]
    incluidas = 0
    for p in pendientes:
        tipo = p["tipo"]
        origen = Path(p["archivo"])
        contador[tipo] = contador.get(tipo, 0) + 1
        etiqueta = f"{_NOMBRE_TIPO.get(tipo, tipo)}_{contador[tipo]}"

        if tipo == "carrusel":
            laminas = archivos_carrusel(origen)
            if not laminas:
                continue
            carpeta = destino / etiqueta
            carpeta.mkdir(parents=True, exist_ok=True)
            for i, lamina in enumerate(laminas, start=1):
                shutil.copy2(lamina, carpeta / f"lamina_{i:02d}{lamina.suffix}")
            nombre_mostrado = f"{etiqueta}/  ({len(laminas)} láminas, en orden)"
        else:
            if not origen.exists():
                continue
            shutil.copy2(origen, destino / f"{etiqueta}{origen.suffix}")
            nombre_mostrado = f"{etiqueta}{origen.suffix}"

        incluidas += 1
        caption = (p.get("caption") or "").strip() or p["gancho"]
        lineas.append(f"#{p['id']:>3} {nombre_mostrado}")
        lineas.append(f"      Caption: {caption}")
        lineas.append("")

    (destino / "LEEME.txt").write_text("\n".join(lineas), encoding="utf-8")
    return {"armado": True, "piezas": incluidas, "carpeta": str(destino)}


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
    p_enc.add_argument("--planos", default="",
                       help="JSON con una toma por frase (gancho, bloques..., cierre)")
    p_enc.add_argument("--formato", choices=FORMATOS, default="",
                       help="formato del reel; vacío = rotación automática")

    p_gen = sub.add_parser("generar")
    p_gen.add_argument("--id", type=int, required=True)
    p_gen.add_argument("--escena", choices=ESCENAS, default="",
                       help="manda sobre la escena guardada al encolar")
    p_gen.add_argument("--etiquetas", nargs="*", default=None, metavar="TEXTO",
                       help="manda sobre las etiquetas guardadas al encolar")
    p_gen.add_argument("--planos", default="",
                       help="JSON de planos: manda sobre los guardados al encolar")
    p_gen.add_argument("--formato", choices=FORMATOS, default="",
                       help="manda sobre el formato guardado al encolar")

    p_pub = sub.add_parser("publicar")
    p_pub.add_argument("--id", type=int, required=True)
    p_pub.add_argument("--resultado", required=True)
    p_pub.add_argument("--cantidad", type=int, default=1)
    p_pub.add_argument("--nota", default="")

    p_des = sub.add_parser("descartar")
    p_des.add_argument("--id", type=int, required=True)
    p_des.add_argument("--nota", default="")

    sub.add_parser("paquete")

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
                          planos=json.loads(args.planos) if args.planos else None,
                          formato=args.formato, dry_run=args.dry_run)
        elif args.accion == "generar":
            res = generar(args.id, escena=args.escena, etiquetas=args.etiquetas,
                          planos=json.loads(args.planos) if args.planos else None,
                          formato=args.formato, dry_run=args.dry_run)
        elif args.accion == "publicar":
            res = publicar(args.id, resultado=args.resultado, cantidad=args.cantidad,
                           nota=args.nota, dry_run=args.dry_run)
        elif args.accion == "paquete":
            res = {"armado": False, "dry_run": True} if args.dry_run else armar_paquete_pendiente()
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

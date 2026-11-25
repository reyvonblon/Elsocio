#!/usr/bin/env python3
"""Zero-dependency prospect discovery & MX verification for El Socio.

Reads search queries from every file in nichos/*.md (a fenced ```queries block,
one "query texto | Industria/Etiqueta" per line), interleaves them across active
niches so every run covers multiple industries and cities, scrapes public business
websites, and verifies each contact email's domain can receive mail (MX/A record)
before it's ever used.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import html
import json
import re
import sqlite3
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NICHOS_DIR = PROJECT_ROOT / "nichos"
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import database  # noqa: E402

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

BLOCKED_DOMAINS = {
    "facebook.com", "instagram.com", "tiktok.com", "youtube.com", "youtu.be",
    "linkedin.com", "twitter.com", "x.com", "pinterest.com", "wikipedia.org",
    "google.com", "google.com.co", "maps.google.com", "wa.me", "whatsapp.com",
    "mercadolibre.com.co", "mercadolibre.com", "olx.com.co", "paginasamarillas.com.co",
    "tripadvisor.com", "tripadvisor.co", "booking.com", "airbnb.com", "expedia.com",
    "wix.com", "wixpress.com", "squarespace.com", "wordpress.com", "wordpress.org",
    "shopify.com", "myshopify.com", "godaddy.com", "cloudflare.com", "sentry.io",
    "example.com", "ejemplo.com", "prueba.com", "tuempresa.com", "miempresa.com", "email.com", "correo.com", "dominio.com", "tudominio.com",
    "duckduckgo.com", "bing.com", "microsoft.com", "yahoo.com",
    "amazon.com", "canva.com", "eventbrite.com", "eventbrite.co", "meetup.com",
    "foursquare.com", "behance.net", "dribbble.com", "linktr.ee", "medium.com",
    "issuu.com", "scribd.com", "reddit.com", "quora.com", "trustpilot.com",
    "falabella.com.co", "exito.com", "alkosto.com", "homecenter.com.co", "rappi.com.co",
    "homesentry.co", "homesentry.net", "pepeganga.com", "panamericana.com.co",
    "eltiempo.com", "elespectador.com", "semana.com", "elcolombiano.com",
    "elpais.com.co", "elheraldo.co", "larepublica.co", "portafolio.co", "pulzo.com",
    "infobae.com", "forbes.co", "lasillavacia.com", "bluradio.com", "caracol.com.co",
    "marca.com", "unidadeditorial.es", "elpais.com", "abc.es", "elmundo.es",
    "computrabajo.com.co", "computrabajo.com", "elempleo.com", "magneto365.com",
    "magnetoempleos.com", "magneto.com.co", "bumeran.com.co", "trabajando.com.co",
    "konzerta.com", "empleospetroleros.com", "ziprecruiter.com", "jooble.org",
    "opcionempleo.com.co", "talenteca.com", "hiring.cafe",
    "indeed.com", "glassdoor.com", "clutch.co", "sortlist.co", "sortlist.com",
    "cylex.com.co", "infobel.com", "kompass.com", "einforma.co", "informacolombia.com",
    "empresite.eleconomistaamerica.co", "lasempresas.com.co", "directorio-empresas.einforma.co",
    "camaramedellin.com.co", "ccb.org.co", "ccc.org.co", "camarabaq.org.co",
    "inexmoda.org.co", "procolombia.co",
    "claro.com.co", "movistar.co", "tigo.com.co", "wom.co", "etb.com", "une.com.co",
    "bancolombia.com", "grupobancolombia.com", "davivienda.com", "bbva.com.co",
    "bancodebogota.com", "nequi.com.co", "sura.com", "epssura.com", "sanitas.com",
    "colsanitas.com", "compensar.com", "avianca.com", "latam.com",
}

BLOCKED_DOMAIN_SUFFIXES = (
    ".gov.co", ".gob.co", ".edu.co", ".mil.co", ".edu", ".gov",
    ".es", ".mx", ".ar", ".cl", ".pe", ".ve", ".uy", ".py", ".bo", ".ec",
    ".cr", ".pa", ".gt", ".do", ".br", ".pt", ".fr", ".de", ".it", ".uk",
    ".ru", ".cn", ".jp", ".in", ".au", ".ca",
)

BLOCKED_EMAIL_PREFIXES = (
    "noreply", "no-reply", "no_reply", "donotreply", "mailer-daemon", "postmaster",
    "abuse", "privacy", "privacidad", "legal", "dmca", "security", "webmaster", "hostmaster",
    "root", "billing", "facturacion", "contabilidad", "cartera", "tesoreria",
    "impuestos", "proveedores", "compras", "rh", "rrhh", "talento", "seleccion",
    "gestionhumana", "gestion-humana", "gestion_humana", "recursoshumanos",
    "recursos-humanos", "nomina", "convocatorias", "empleo", "vacantes",
    "pqrs", "pqr", "notificaciones", "alertas", "boletin", "newsletter",
    "protecciondedatos", "habeasdata", "cumplimiento", "denuncias", "soporte",
    "reservas", "sentry", "wix", "ejemplo", "example", "test", "user", "correo",
    "email", "tuemail", "tunombre",
)

# Prefijos que delatan correos automáticos incluso cuando vienen pegados a otra palabra
# (ej. notificacionesclaro@..., noreplyventas@...).
BLOCKED_EMAIL_STARTSWITH = (
    "notificaciones", "noreply", "no-reply", "no_reply", "donotreply",
    "habeas", "protecciondatos", "pqrs", "facturacion", "contabilidad",
)

FREE_MAIL_DOMAINS = {
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com", "live.com",
}

EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]{2,64}@[a-zA-Z0-9.-]{2,190}\.[a-zA-Z]{2,12}\b")
LINK_RE = re.compile(r'href=["\']([^"\'#]+)["\']', flags=re.IGNORECASE)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", flags=re.IGNORECASE | re.DOTALL)
HTML_LANG_EN_RE = re.compile(r"<html[^>]+lang=[\"']en(?:-|\b|[\"'])", flags=re.IGNORECASE)
COLOMBIA_SIGNAL_RE = re.compile(
    r"\b(colombia|medell[ií]n|bogot[aá]|cali|barranquilla|envigado|sabaneta|"
    r"antioquia|cundinamarca|valle\s+del\s+cauca|atl[aá]ntico|\+57)\b",
    flags=re.IGNORECASE,
)
SPANISH_SIGNAL_RE = re.compile(
    r"\b(contacto|cont[aá]ctenos|nosotros|servicios|tienda|env[ií]os|carrito|portafolio|proyectos)\b",
    flags=re.IGNORECASE,
)
QUERIES_BLOCK_RE = re.compile(r"```queries\s*\n(.*?)```", flags=re.DOTALL)
META_TAG_RE = re.compile(r"<meta\b[^>]*>", flags=re.IGNORECASE)
ATTR_RE = re.compile(r'([a-zA-Z0-9:_-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')
JSONLD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', flags=re.IGNORECASE | re.DOTALL)
HEADING_RE = re.compile(r"<h([12])[^>]*>(.*?)</h\1>", flags=re.IGNORECASE | re.DOTALL)
WA_LINK_RE = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?[^\"'\s]*phone=)\+?(\d{10,13})", flags=re.IGNORECASE)
IG_LINK_RE = re.compile(r"instagram\.com/([a-zA-Z0-9._]{2,30})/?", flags=re.IGNORECASE)
PRICE_SCRUB_RE = re.compile(r"(?:[$€£]\s*\d[\d.,]*|\b\d{1,3}(?:[.,]\d{3})+\b|\b\d+\s*(?:cop|usd|pesos|mil|millones?)\b)", flags=re.IGNORECASE)


def load_nicho_queries() -> list[tuple[str, str, str]]:
    """Return interleaved (query_text, industry_label, nicho_filename) tuples from nichos/*.md."""
    per_nicho: list[list[tuple[str, str, str]]] = []
    if not NICHOS_DIR.is_dir():
        return []
    for md_path in sorted(NICHOS_DIR.glob("*.md")):
        if md_path.name.startswith("_"):
            continue
        text = md_path.read_text(encoding="utf-8")
        m = QUERIES_BLOCK_RE.search(text)
        if not m:
            continue
        bucket: list[tuple[str, str, str]] = []
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            q, _, label = line.partition("|")
            if q.strip() and label.strip():
                bucket.append((q.strip(), label.strip(), md_path.stem))
        if bucket:
            per_nicho.append(bucket)

    out: list[tuple[str, str, str]] = []
    max_len = max((len(b) for b in per_nicho), default=0)
    for idx in range(max_len):
        for bucket in per_nicho:
            if idx < len(bucket):
                out.append(bucket[idx])
    return out


def _domain_of(url_or_email: str) -> str:
    val = (url_or_email or "").strip().lower()
    if "@" in val and not val.startswith(("http://", "https://")):
        dom = val.split("@", 1)[1]
    else:
        parsed = urllib.parse.urlparse(val if "://" in val else f"https://{val}")
        dom = parsed.netloc.lower().split(":")[0]
    if dom.startswith("www."):
        dom = dom[4:]
    return dom.strip(".")


def _is_blocked_domain(dom: str) -> bool:
    dom = (dom or "").lower().strip(".")
    if not dom or "." not in dom:
        return True
    if any(dom.endswith(suf) for suf in BLOCKED_DOMAIN_SUFFIXES):
        return True
    for bad in BLOCKED_DOMAINS:
        if dom == bad or dom.endswith("." + bad):
            return True
    return False


def verify_domain_mx(email_addr: str) -> bool:
    dom = _domain_of(email_addr)
    if not dom or "." not in dom:
        return False
    if dom in {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com", "live.com"}:
        return True
    for rtype in ("MX", "A"):
        try:
            proc = subprocess.run(
                ["dig", "+short", "+time=2", "+tries=1", rtype, dom],
                capture_output=True, text=True, timeout=4, check=False,
            )
            out = (proc.stdout or "").strip()
            valid = [ln.strip() for ln in out.splitlines() if ln.strip() and not ln.strip().endswith(" .")]
            if valid:
                return True
        except Exception:
            continue
    return False


def _ssl_context(*, verify: bool = True) -> ssl.SSLContext:
    if not verify:
        return ssl._create_unverified_context()
    for cafile in ("/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"):
        if Path(cafile).exists():
            try:
                return ssl.create_default_context(cafile=cafile)
            except Exception:
                break
    return ssl.create_default_context()


def _fetch_url(
    url: str,
    timeout: int = 7,
    max_bytes: int = 280_000,
    *,
    data: bytes | None = None,
    extra_headers: dict[str, str] | None = None,
    allow_insecure_fallback: bool = False,
) -> tuple[int, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-CO,es;q=0.9,en;q=0.5",
        "Accept-Encoding": "gzip, identity",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers)

    contexts = [_ssl_context(verify=True)]
    if allow_insecure_fallback:
        contexts.append(_ssl_context(verify=False))

    last_exc: Exception | None = None
    for idx, ctx in enumerate(contexts):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                status = getattr(resp, "status", 200) or 200
                ctype = (resp.headers.get("Content-Type") or "").lower()
                # "json" va en la lista desde que hay fuentes que responden JSON
                # (OpenStreetMap): antes el cuerpo se descartaba y la fuente
                # devolvía 200 con 0 resultados, como si no hubiera negocios.
                if ctype and not any(
                    tipo in ctype for tipo in ("text", "html", "xml", "json")
                ):
                    return status, ""
                raw = resp.read(max_bytes)
                if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
                    try:
                        raw = gzip.decompress(raw)[:max_bytes]
                    except Exception:
                        pass
                return status, raw.decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            last_exc = exc
            if idx == 0 and allow_insecure_fallback and "CERTIFICATE_VERIFY_FAILED" in str(exc):
                continue
            break
        except Exception as exc:
            last_exc = exc
            break
    if last_exc:
        raise last_exc
    return 0, ""


_SEO_TITLE_PREFIXES = (
    "estudio de arquitectura", "agencia de marketing", "agencia de publicidad",
    "agencia digital", "remodelación y diseño", "remodelacion y diseno",
    "diseño de interiores", "diseno de interiores", "dermatología", "dermatologia",
    "tienda de ropa", "tienda online", "tienda virtual", "venta de ", "fábrica de ",
    "fabrica de ", "taller de ", "servicios de ", "los mejores ", "compra ",
    "productos ", "confección de ", "confeccion de ", "arquitectura y ",
)

_SEO_TITLE_PATTERNS = re.compile(
    r"\b(?:en\s+(?:medell[ií]n|bogot[aá]|cali|barranquilla|colombia)|"
    r"dise[ñn]o\s+de\s+interiores\s+y|marketing\s+digital\s+en|"
    r"arquitectura\s+e\s+interiorismo|salud\s+capilar)\b",
    flags=re.IGNORECASE,
)

_GENERIC_TITLES = {
    "inicio", "home", "contacto", "contáctenos", "contactenos", "tienda",
    "bienvenido", "bienvenidos", "index", "colombia", "nosotros", "productos",
    "servicios", "blog", "catálogo", "catalogo",
}


def _parece_titulo_seo(texto: str) -> bool:
    """True si el texto suena a descripción SEO de Google y no al nombre real de la marca."""
    limpio = re.sub(r"\s+", " ", (texto or "")).strip()
    if not limpio:
        return True
    bajo = limpio.lower()
    if bajo in _GENERIC_TITLES:
        return True
    if len(limpio) > 38 and len(limpio.split()) >= 5:
        return True
    if any(bajo.startswith(pref) for pref in _SEO_TITLE_PREFIXES):
        return True
    if _SEO_TITLE_PATTERNS.search(bajo):
        return True
    return False


def _marca_confiable(marca: str, fallback_domain: str, respaldo: str = "") -> str:
    """Devuelve un nombre con el que SÍ se puede saludar a un prospecto.

    Si lo extraído parece un título SEO o la consulta de búsqueda ("Tienda naturista cerca
    de mí en Colombia por ciudad"), se usa el dominio. Un saludo con el query pegado delata
    al bot en la primera línea y quema el prospecto.
    """
    limpio = re.sub(r"\s+", " ", (marca or "")).strip()
    if limpio and not _parece_titulo_seo(limpio):
        return limpio
    respaldo = re.sub(r"\s+", " ", (respaldo or "")).strip()
    if respaldo and not _parece_titulo_seo(respaldo):
        return respaldo
    return _nombre_desde_dominio(fallback_domain) or limpio or respaldo


def _nombre_desde_dominio(fallback_domain: str) -> str:
    raiz = (fallback_domain or "").split(".")[0]
    raiz = re.sub(r"[-_]+", " ", raiz).strip()
    if not raiz:
        return ""
    return raiz.title()


def _limpiar_etiqueta_marca(txt: str) -> str:
    limpio = html.unescape(re.sub(r"\s+", " ", txt or "")).strip()
    limpio = re.sub(r"[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ&.\-\s]", "", limpio).strip(" -–—.|•:")
    return limpio


def _extraer_metas(raw_html: str) -> dict[str, str]:
    metas: dict[str, str] = {}
    for tag in META_TAG_RE.findall(raw_html[:45_000]):
        attrs: dict[str, str] = {}
        for k, v1, v2 in ATTR_RE.findall(tag):
            attrs[k.lower()] = (v1 or v2 or "").strip()
        key = (attrs.get("property") or attrs.get("name") or "").lower().strip()
        val = html.unescape(attrs.get("content") or "").strip()
        if key and val and key not in metas:
            metas[key] = re.sub(r"\s+", " ", val)
    return metas


def _extraer_nombre_jsonld(raw_html: str) -> str:
    tipos_marca = {
        "organization", "localbusiness", "store", "clothingstore",
        "professionalservice", "corporation", "onlinebusiness", "brand",
    }
    for bloque in JSONLD_RE.findall(raw_html[:80_000])[:6]:
        try:
            data = json.loads(bloque.strip())
        except Exception:
            continue
        nodos = data if isinstance(data, list) else [data]
        expandidos: list[dict] = []
        for n in nodos:
            if not isinstance(n, dict):
                continue
            expandidos.append(n)
            if isinstance(n.get("@graph"), list):
                expandidos.extend(x for x in n["@graph"] if isinstance(x, dict))
        for nodo in expandidos:
            t = nodo.get("@type")
            tipos = {str(t).lower()} if isinstance(t, str) else {str(x).lower() for x in (t or [])}
            if tipos & tipos_marca:
                nombre = _limpiar_etiqueta_marca(str(nodo.get("name") or ""))
                if 2 <= len(nombre) <= 42 and not _parece_titulo_seo(nombre):
                    return nombre
    return ""


def _clean_business_name(raw_title: str, fallback_domain: str) -> str:
    txt = html.unescape(re.sub(r"\s+", " ", raw_title or "")).strip()
    candidatos: list[str] = [txt]
    for sep in (" | ", " - ", " – ", " — ", " :: ", " • ", ": "):
        if sep in txt:
            candidatos = [p.strip() for p in txt.split(sep) if p.strip()]
            break

    limpios: list[str] = []
    for p in candidatos:
        c = _limpiar_etiqueta_marca(p)
        if 2 <= len(c) <= 45 and c.lower() not in _GENERIC_TITLES:
            limpios.append(c)

    # Prioriza partes que NO son títulos SEO y prefiere las más concisas (suelen ser la marca).
    no_seo = [c for c in limpios if not _parece_titulo_seo(c)]
    if no_seo:
        no_seo.sort(key=lambda s: (len(s.split()), len(s)))
        return no_seo[0]
    return _nombre_desde_dominio(fallback_domain)


def _extraer_nombre_marca(raw_html: str, fallback_domain: str, raw_title: str = "") -> str:
    """Devuelve el nombre real de la marca evitando títulos SEO largos."""
    metas = _extraer_metas(raw_html)
    og_site = _limpiar_etiqueta_marca(metas.get("og:site_name", ""))
    if 2 <= len(og_site) <= 42 and not _parece_titulo_seo(og_site):
        return og_site
    jld = _extraer_nombre_jsonld(raw_html)
    if jld:
        return jld
    if not raw_title:
        m = TITLE_RE.search(raw_html)
        raw_title = m.group(1) if m else ""
    return _clean_business_name(raw_title, fallback_domain)


def _es_gmail_basura(local: str, dom: str) -> bool:
    """Filtra direcciones personales aleatorias tipo xf6501985@gmail.com."""
    if dom not in FREE_MAIL_DOMAINS:
        return False
    if re.match(r"^[a-z]{1,3}\d{5,}$", local):
        return True
    digitos = sum(ch.isdigit() for ch in local)
    letras = sum(ch.isalpha() for ch in local)
    return digitos >= 6 and letras <= 4


# Buzones de empresa: los lee una recepcionista o nadie, y quien decide no se entera.
# Se siguen aceptando (muchas PyMEs colombianas solo publican este) pero de últimas.
PREFIJOS_BUZON_EMPRESA = {
    "contacto", "contactenos", "contactanos", "info", "informacion", "comercial",
    "ventas", "hola", "gerencia", "pedidos", "mercadeo", "diseno", "estudio",
    "proyectos", "direccion", "atencion", "tienda", "administracion", "admin",
    "servicioalcliente", "clientes", "salud", "espacio", "preguntas", "soluciones",
    "citas", "agenda", "cotizaciones", "cotizacion", "asesoria", "asesor", "consultas",
    "redaccion", "prensa", "comunicaciones", "grupo", "equipo",
    # Variantes en inglés, comunes en estudios y agencias colombianas.
    "contact", "hello", "hi", "support", "sales", "team", "office", "mail", "email",
    "enquiries", "inquiries", "studio", "work", "general", "bookings", "press",
    "commercial", "marketing", "nombre", "tunombre", "tuempresa",
}

# Palabras que delatan que el correo es la MARCA, no una persona: lmvjewelry@,
# batutadiseno@, renovaplus.sas@. Escribirle a estos es como escribirle a info@.
_PALABRAS_DE_NEGOCIO = {
    "jewelry", "joyeria", "joyas", "tienda", "store", "shop", "boutique", "moda",
    "diseno", "design", "studio", "estudio", "brands", "brand", "marca", "visual",
    "datos", "audio", "video", "foto", "fotografia", "cafe", "bio", "natural",
    "sas", "ltda", "eu", "sa", "srl", "inc", "corp", "group", "grupo", "company",
    "textil", "tessile", "confecciones", "muebles", "obras", "construcciones",
    "arquitectos", "arquitectura", "ingenieria", "consultores", "asesores",
    "servicios", "logistica", "creativo", "creativa", "publicidad", "agencia",
    "inmobiliaria", "constructora", "distribuciones", "importaciones", "soluciones",
    "glosas", "renova", "plus", "pro", "max", "center", "centro", "clinica",
    "creaciones", "scsas", "manufacturas", "industrias", "comercializadora",
    "distribuidora", "fabrica", "taller", "talleres", "almacen", "almacenes",
    "colombia", "oficial", "ventas", "shopping", "market", "mercado", "mundo",
    "cuero", "cueros", "eventos", "evento", "sistemas", "sistema", "papeleria",
    "insumos", "predios", "inmuebles", "arq", "ing", "abg", "weare", "somos",
    "regalos", "accesorios", "uniformes", "dotaciones", "muebleria", "ferreteria",
    "importadora", "exportadora", "mayorista", "outlet", "online", "web", "digital",
}

# Nombres de pila frecuentes en Colombia: la señal más confiable de que hay
# una persona detrás, incluso en un Gmail (yesidcan@, cindypao_2714@).
_NOMBRES_PILA = {
    "alison", "ana", "andrea", "andres", "angela", "antonio", "beatriz", "camila",
    "carlos", "carolina", "catalina", "cesar", "cindy", "claudia", "cristian",
    "cristina", "daniel", "daniela", "david", "diana", "diego", "edgar", "eduardo",
    "elena", "esteban", "fabian", "felipe", "fernando", "francisco", "gabriel",
    "german", "gloria", "gustavo", "hector", "helena", "hernan", "isabel", "ivan",
    "jaime", "javier", "jorge", "jose", "juan", "juliana", "julian", "julio",
    "karen", "laura", "leonardo", "liliana", "lina", "lorena", "lucia", "luis",
    "luisa", "manuel", "marcela", "margarita", "maria", "mariana", "mario", "marta",
    "martha", "mary", "mauricio", "miguel", "monica", "natalia", "nicolas", "olga",
    "oscar", "pablo", "paola", "patricia", "paula", "pedro", "rafael", "ramiro",
    "raul", "ricardo", "roberto", "rodrigo", "rosa", "ruben", "samuel", "sandra",
    "santiago", "sara", "sebastian", "sergio", "silvia", "sofia", "tatiana",
    "valentina", "vanessa", "veronica", "vicente", "victor", "viviana", "william",
    "yesid", "yolanda", "zulma", "alejandro", "alberto", "alvaro", "arturo",
    "benjamin", "brayan", "dayana", "duvan", "edwin", "eben", "elkin", "emilio",
    "esneider", "estefania", "fabio", "geovanny", "gerardo", "giovanni", "henry",
    "jhon", "jhonatan", "johana", "johanna", "jonathan", "kevin", "leidy", "luz",
    "maicol", "milena", "nelson", "nubia", "omar", "orlando", "rodolfo", "stefania",
    "wilmer", "yeison", "yuliana",
    "adriana", "alejandra", "alexander", "alexandra", "amparo", "anderson",
    "angelica", "astrid", "aura", "camilo", "carmen", "cecilia", "consuelo",
    "cristhian", "dairo", "deisy", "diber", "dora", "eliana", "emerson",
    "ferney", "gina", "gina", "hugo", "ingrid", "jaider", "jairo", "jeison",
    "jenny", "jessica", "jesus", "jhoan", "john", "jonnathan", "jose", "juliet",
    "katherine", "lady", "leonel", "leydy", "lizeth", "magda", "maribel",
    "marlon", "mauro", "mayra", "melissa", "mildred", "nathalia", "nataly",
    "nestor", "norma", "paulina", "ramon", "rene", "rocio", "salomon", "saray",
    "sonia", "stella", "tania", "teresa", "wilson", "yair", "yenny", "yuri",
    "zoraida", "esperanza", "fanny", "gilberto", "jacqueline", "jimena",
    "lucero", "luisfer", "miriam", "nidia", "piedad", "yamile",
    "erika", "erica", "wallace", "ruben", "lina", "cristina", "angelica",
    "felipe", "jorge", "yudy", "yenifer", "jennifer", "karol", "karina",
    "valeria", "valentina", "isabella", "antonia", "emilia", "martin",
    "matias", "tomas", "simon", "emmanuel", "alonso", "edison", "fredy",
    "harold", "ivonne", "janeth", "lilia", "marcel", "mireya", "nohora",
    "olivia", "rosalba", "ruth", "shirley", "yolima",
}

_PARTICULAS_NOMBRE = {"de", "del", "la", "las", "los", "van", "da", "di"}

# Trozos que no son nombre aunque viajen en el correo: "etc.erikatarazona@".
_RUIDO_EN_SALUDO = {"etc", "sas", "ltda", "co", "col", "acc", "arq", "ing", "dr", "dra"}

# Apodos con los que la gente firma en Colombia. Solo valen para el SALUDO de un
# correo que ya pasó el filtro de persona: como señal de persona abrirían la puerta.
_APODOS_SALUDO = {
    "mafe": "Mafe", "pipe": "Pipe", "juanda": "Juanda", "sebas": "Sebas",
    "santi": "Santi", "dani": "Dani", "cata": "Cata", "nata": "Nata",
    "vale": "Vale", "lucho": "Lucho", "caro": "Caro", "pau": "Pau",
    "tefa": "Tefa", "moni": "Moni", "kathe": "Kathe", "jhona": "Jhona",
}


def _partes_alfabeticas(local: str) -> list[str]:
    """Trocea la parte local de un correo en palabras, ignorando números de relleno."""
    crudo = re.sub(r"\d+", " ", local or "")
    # El .strip() importa: sin él "camilacarmona27" quedaba como "camilacarmona "
    # y el espacio final hacía fallar .isalpha(), así que una persona real se iba a la basura.
    partes = (p.strip() for p in re.split(r"[._\-\s]+", crudo))
    return [p for p in partes if p.isalpha() and len(p) >= 2]


def _parece_correo_de_persona(local: str, dominio: str = "") -> bool:
    """`santiago.salazar@` sí; `info@` no. Escribirle a una persona cambia el resultado."""
    bajo = (local or "").lower()
    if not bajo or bajo in PREFIJOS_BUZON_EMPRESA:
        return False
    # Buzón con sufijo pegado: infocolombia@, ventas1@, contactobogota@.
    if any(bajo.startswith(pref) for pref in PREFIJOS_BUZON_EMPRESA if len(pref) >= 4):
        return False
    # El nombre de la marca no es una persona: makeno@makeno.com.co.
    raiz_dom = re.split(r"[.\-]", (dominio or "").lower())[0]
    if raiz_dom and bajo.replace(".", "").replace("-", "").replace("_", "") == raiz_dom:
        return False
    partes = _partes_alfabeticas(bajo)
    if not partes or any(p in PREFIJOS_BUZON_EMPRESA for p in partes):
        return False
    # "maria.de.los.rios" es una persona: las partículas no cuentan como nombre.
    partes = [p for p in partes if p not in _PARTICULAS_NOMBRE] or partes
    # Si aparece una palabra de negocio, es el correo de la marca, no de alguien.
    if any(p in _PALABRAS_DE_NEGOCIO for p in partes):
        return False
    # Un nombre de pila reconocible basta, aunque sea un Gmail suelto (yesidcan@, cindypao_2714@).
    if partes[0] in _NOMBRES_PILA or any(p in _NOMBRES_PILA for p in partes):
        return True
    # Palabra pegada sin separador: lmvjewelry@, batutadiseno@, feraljoyeria@.
    pegado = "".join(partes)
    if any(neg in pegado for neg in _PALABRAS_DE_NEGOCIO if len(neg) >= 5):
        return False
    # nombre.apellido / nombre_apellido: la señal más fuerte de persona real.
    if len(partes) >= 2 and all(3 <= len(p) <= 18 for p in partes):
        return True
    # Una sola palabra suelta solo es persona si se reconoce como nombre de pila
    # (mariana@, santiago@). Si no, es la marca disfrazada: acuattro@, taro@,
    # cafealtoperfil@, ccialviva@ — y escribirle a eso es escribirle a nadie.
    if len(partes) != 1:
        return False
    # Inicial + apellido: "j.perez@", "alejandra.r@". La inicial delata persona.
    crudo = [x.strip() for x in re.split(r"[._\-\s]+", re.sub(r"\d+", " ", bajo))]
    crudo = [x for x in crudo if x.isalpha()]
    if len(crudo) >= 2 and any(len(x) == 1 for x in crudo):
        return True
    unica = partes[0]
    if not (3 <= len(unica) <= 14):
        return False
    if unica in _NOMBRES_PILA:
        return True
    # "yesidcan", "cindypao": nombre real con relleno pegado al final.
    return any(unica.startswith(n) and len(n) >= 4 for n in _NOMBRES_PILA)


def nombre_de_pila_desde_email(email_addr: str) -> str:
    """Saca el nombre con el que saludar. Vacío si el correo es un buzón de empresa."""
    local = (email_addr or "").split("@")[0].lower()
    dominio = (email_addr or "").split("@")[-1].lower() if "@" in (email_addr or "") else ""
    if not _parece_correo_de_persona(local, dominio):
        return ""
    # `j.perez@` es inicial + apellido: no da para tutear ("Hola Perez" suena raro).
    # Mejor devolver vacío y que el correo salude a la empresa.
    crudo = [p for p in re.split(r"[._\-]+", re.sub(r"\d+", " ", local)) if p.isalpha()]
    if crudo and len(crudo[0]) == 1:
        return ""
    partes = [p for p in _partes_alfabeticas(local) if p not in _PARTICULAS_NOMBRE]
    partes = [p for p in partes if p not in _RUIDO_EN_SALUDO]
    if not partes:
        return ""
    for parte in partes:
        if parte in _NOMBRES_PILA:
            return parte.capitalize()
    for parte in partes:
        if parte in _APODOS_SALUDO:
            return _APODOS_SALUDO[parte]
    # "yesidcan" / "cindypao": el nombre va al principio, el resto es relleno.
    candidatos = [
        n for n in _NOMBRES_PILA if len(n) >= 4 and partes[0].startswith(n)
    ]
    if candidatos:
        largo = max(candidatos, key=len)
        # "luisalfesp" podría ser Luis o Luisa: equivocarse de persona en el saludo
        # es peor que no saludar por nombre, así que ahí saluda a la empresa.
        if len(candidatos) > 1 and len(partes[0]) > len(largo):
            return ""
        return largo.capitalize()
    # Nada reconocible ("fpedraza", "einfo"): mejor saludar a la empresa que
    # escribir "Hola Fpedraza" y quemar el correo en la primera línea.
    return ""


def _clean_email_candidates(raw_html: str, site_domain: str) -> list[str]:
    text = urllib.parse.unquote(html.unescape(raw_html or "")).replace("%40", "@")
    # Los sitios con JSON embebido traen \u003e / \u0026: sin desescapar, el correo
    # salía como "u003einfo@megapredios.com.co" y pasaba todos los filtros.
    text = re.sub(r"\\?u00[0-9a-fA-F]{2}", " ", text)
    found = EMAIL_RE.findall(text)
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for em in found:
        em_low = em.strip().lower().strip(".")
        if em_low in seen:
            continue
        seen.add(em_low)
        local, _, dom = em_low.partition("@")
        if any(em_low.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".js", ".css", ".woff", ".woff2")):
            continue
        if any(
            local == bad or local.startswith(bad + ".") or local.startswith(bad + "-") or local.startswith(bad + "_")
            for bad in BLOCKED_EMAIL_PREFIXES
        ):
            continue
        if any(local.startswith(pref) for pref in BLOCKED_EMAIL_STARTSWITH):
            continue
        if _is_blocked_domain(dom) or _es_gmail_basura(local, dom):
            continue
        score = 0
        if dom == site_domain or dom.endswith("." + site_domain):
            score += 50
        elif dom in {"gmail.com", "hotmail.com", "outlook.com"}:
            score += 25
        # Antes esto premiaba los buzones genéricos con +30 y una persona real competía
        # con 0: de 26 correos enviados, 18 fueron a info@/contacto@ y solo 2 a alguien
        # con nombre. Queda al revés, que es como se consigue una respuesta.
        if _parece_correo_de_persona(local, dom):
            score += 60 if len(_partes_alfabeticas(local)) >= 2 else 35
        elif local in PREFIJOS_BUZON_EMPRESA:
            score += 10
        scored.append((score, em_low))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [em for _, em in scored]


def _clean_email_candidates_sort(emails: list[str], site_domain: str) -> list[str]:
    """Reordena correos ya limpios con la misma puntuación (persona primero)."""
    return _clean_email_candidates(" ".join(emails), site_domain)


def _looks_relevant_spanish_site(raw_html: str, dom: str) -> bool:
    """Descarta blogs en inglés o portales extranjeros sin presencia en Colombia."""
    if dom.endswith(".co"):
        return True
    if COLOMBIA_SIGNAL_RE.search(raw_html):
        return True
    if HTML_LANG_EN_RE.search(raw_html[:1500]) and not SPANISH_SIGNAL_RE.search(raw_html):
        return False
    return bool(SPANISH_SIGNAL_RE.search(raw_html))


def _texto_visible_limpio(raw_html: str, max_chars: int = 420) -> str:
    """Extrae texto visible útil de una web sin scripts, menús, cookies ni cifras de precios."""
    limpio = re.sub(r"(?is)<(script|style|noscript|svg|iframe|nav|footer|header)[^>]*>.*?</\1>", " ", raw_html)
    limpio = re.sub(r"(?is)<!--.*?-->", " ", limpio)
    limpio = re.sub(r"<[^>]+>", " ", limpio)
    limpio = html.unescape(limpio)
    limpio = re.sub(r"\s+", " ", limpio).strip()
    limpio = PRICE_SCRUB_RE.sub("", limpio)
    limpio = re.sub(r"\s+", " ", limpio).strip()
    return limpio[:max_chars]


def _detectar_ciudad(texto: str) -> str:
    patrones = (
        ("Medellín", r"\bmedell[ií]n\b"),
        ("Envigado", r"\benvigado\b"),
        ("Sabaneta", r"\bsabaneta\b"),
        ("Bogotá", r"\bbogot[aá]\b"),
        ("Cali", r"\bcali\b"),
        ("Barranquilla", r"\bbarranquilla\b"),
        ("Cartagena", r"\bcartagena\b"),
        ("Bucaramanga", r"\bbucaramanga\b"),
        ("Pereira", r"\bpereira\b"),
    )
    for nombre, pat in patrones:
        if re.search(pat, texto, flags=re.IGNORECASE):
            return nombre
    return ""


def _detectar_plataforma(raw_html: str) -> str:
    low = raw_html.lower()
    if "cdn.shopify.com" in low or "shopify.theme" in low:
        return "Shopify"
    if "woocommerce" in low or "wc-block" in low:
        return "WooCommerce"
    if "tiendanube" in low or "nuvemshop" in low:
        return "Tiendanube"
    if "vtex" in low:
        return "VTEX"
    if "prestashop" in low:
        return "PrestaShop"
    if "wixstatic.com" in low:
        return "Wix"
    if "webflow" in low:
        return "Webflow"
    if "wp-content" in low:
        return "WordPress"
    return ""


def _extraer_whatsapp(raw_html: str) -> str:
    m = WA_LINK_RE.search(raw_html)
    if not m:
        return ""
    dig = m.group(1)
    if len(dig) == 10 and dig.startswith("3"):
        dig = "57" + dig
    if len(dig) == 12 and dig.startswith("57"):
        return f"+{dig[:2]} {dig[2:5]} {dig[5:8]} {dig[8:]}"
    return f"+{dig}"


def _extraer_instagram(raw_html: str) -> str:
    ignorar = {"p", "reel", "reels", "explore", "accounts", "share", "stories", "tv"}
    for cand in IG_LINK_RE.findall(raw_html):
        c = cand.strip().strip("/")
        if c.lower() not in ignorar and len(c) >= 2:
            return f"@{c}"
    return ""


# Señales de a qué se dedica de verdad un negocio. Hasta ahora el nicho se heredaba
# de la consulta que lo encontró, no del negocio: un estudio de arquitectura hallado
# con una consulta de ropa quedaba en "fichas de ropa" y recibía el correo
# equivocado. Nadie responde a eso, y el motor concluye que el nicho no convierte.
_SENALES_DE_NICHO: dict[str, tuple[str, ...]] = {
    "fichas-tecnicas-ropa": (
        "confeccion", "confección", "patronaje", "maquila", "prendas", "costura",
        "textil", "moda", "ropa", "tallas", "camisetas", "vestidos", "swimwear",
        "vestidos de baño", "streetwear", "lenceria", "lencería", "dotaciones",
        "uniformes", "paquete completo", "escalado", "molderia", "moldería",
    ),
    "modelado-3d-espacios": (
        "arquitect", "interiores", "remodelacion", "remodelación", "mobiliario",
        "carpinteria", "carpintería", "cocinas integrales", "closets", "obra",
        "render", "planos", "stands", "espacios comerciales", "acustico",
        "acústico", "adecuacion", "adecuación", "muebles a medida", "diseño de locales",
    ),
    "ecommerce-catalogo-visual": (
        "carrito", "añadir al carrito", "agregar al carrito", "comprar ahora",
        "envios a todo", "envíos a todo", "catalogo", "catálogo", "shopify",
        "woocommerce", "tiendanube", "cosmetica", "cosmética", "joyeria", "joyería",
        "calzado", "marroquineria", "marroquinería", "accesorios", "tienda online",
    ),
    "automatizacion-agencias-estudios": (
        "agencia", "marketing", "branding", "publicidad", "diseño grafico",
        "diseño gráfico", "campañas", "redes sociales", "productora", "audiovisual",
        "desarrollo web", "pauta", "community manager", "estrategia digital",
        "fotografia de producto", "fotografía de producto", "nuestros clientes",
    ),
}


# Palabras que por sí solas dicen a qué se dedica el negocio (valen doble). Van en
# español y en inglés: varios sitios colombianos de arquitectura y diseño están en
# inglés, y sin esto "taller architects" quedaba clasificado como taller de ropa.
_SENALES_FUERTES: dict[str, tuple[str, ...]] = {
    "fichas-tecnicas-ropa": (
        "confeccion", "confección", "patronaje", "maquila", "apparel", "clothing",
        "fashion design", "swimwear", "moldería", "molderia",
    ),
    "modelado-3d-espacios": (
        "arquitect", "architect", "interior design", "interiores", "remodelacion",
        "remodelación", "carpinteria", "carpintería", "cocinas integrales",
        "furniture", "joinery", "mobiliario",
    ),
    "ecommerce-catalogo-visual": (
        "añadir al carrito", "agregar al carrito", "add to cart", "catálogo de productos",
        "cosmetica", "cosmética", "joyeria", "joyería", "marroquineria", "marroquinería",
    ),
    "automatizacion-agencias-estudios": (
        "agencia de marketing", "agencia de publicidad", "branding", "marketing agency",
        "productora audiovisual", "desarrollo web", "diseño gráfico", "graphic design",
    ),
}


def clasificar_nicho_por_texto(texto: str, *, nicho_actual: str = "") -> str:
    """Devuelve el nicho al que de verdad pertenece el negocio, según su propio texto.

    Si no hay señal clara, deja el nicho que ya traía: cambiarlo a ciegas sería
    igual de malo que heredarlo de la consulta.
    """
    bajo = (texto or "").lower()
    if not bajo:
        return nicho_actual
    puntajes = {
        nicho: sum(1 for s in senales if s in bajo)
        + 2 * sum(1 for s in _SENALES_FUERTES.get(nicho, ()) if s in bajo)
        for nicho, senales in _SENALES_DE_NICHO.items()
    }
    mejor = max(puntajes, key=lambda n: puntajes[n])
    if puntajes[mejor] < 2:
        return nicho_actual
    # Solo se cambia si el otro nicho gana con claridad: un empate no es motivo
    # para moverle el nicho a un lead que ya estaba clasificado.
    if nicho_actual and puntajes.get(nicho_actual, 0) + 2 > puntajes[mejor]:
        return nicho_actual
    return mejor


def _encaja_con_nicho(raw_html: str, texto_total: str, nicho: str) -> tuple[bool, str]:
    """Filtra sitios que claramente no son clientes objetivo del nicho (ej. clínicas médicas en e-commerce)."""
    bajo = texto_total.lower()
    if any(bad in bajo[:600] for bad in ("agencia de viajes", "vuelos baratos", "boletos aéreos", "boletos aereos")):
        return False, "turismo_fuera_de_nicho"
    if nicho == "ecommerce-catalogo-visual":
        senales_clinica = (
            "clínica dermatológica", "clinica dermatologica", "dermatología estética",
            "dermatologia estetica", "cirugía plástica", "cirugia plastica",
            "consulta médica", "consulta medica", "historia clínica", "historia clinica",
            "odontología", "odontologia", "medicina estética", "medicina estetica",
        )
        senales_tienda = (
            "añadir al carrito", "agregar al carrito", "add to cart", "carrito de compras",
            "mi carrito", "cdn.shopify.com", "woocommerce", "tiendanube", "vtex",
            "tienda online", "comprar ahora",
        )
        es_clinica = any(s in bajo for s in senales_clinica)
        tiene_tienda = any(s in raw_html.lower() or s in bajo for s in senales_tienda)
        if es_clinica and not tiene_tienda:
            return False, "clinica_medica_sin_ecommerce"
    return True, ""


def analizar_sitio_web(home_html: str, url: str, nicho: str = "", sub_html: str = "") -> dict[str, object]:
    """Extrae perfil verificado y dossier compacto de un sitio web para personalizar correos."""
    dom = _domain_of(url)
    combinado = home_html + ("\n" + sub_html if sub_html else "")
    title_m = TITLE_RE.search(home_html)
    raw_title = html.unescape(re.sub(r"\s+", " ", title_m.group(1))).strip() if title_m else ""
    metas = _extraer_metas(home_html)
    marca = _extraer_nombre_marca(home_html, dom, raw_title=raw_title)

    meta_desc = metas.get("description") or metas.get("og:description") or ""
    meta_desc = PRICE_SCRUB_RE.sub("", meta_desc).strip()[:260]

    titulares: list[str] = []
    vistos: set[str] = set()
    for _, htxt in HEADING_RE.findall(home_html)[:18]:
        limpio = html.unescape(re.sub(r"<[^>]+>", " ", htxt))
        limpio = re.sub(r"\s+", " ", limpio).strip()
        limpio = PRICE_SCRUB_RE.sub("", limpio).strip()
        if 4 <= len(limpio) <= 95 and limpio.lower() not in vistos and limpio.lower() not in _GENERIC_TITLES:
            vistos.add(limpio.lower())
            titulares.append(limpio)
        if len(titulares) >= 4:
            break

    extracto = _texto_visible_limpio(home_html, max_chars=380)
    texto_para_senales = " ".join([raw_title, meta_desc, " ".join(titulares), extracto])
    ciudad = _detectar_ciudad(combinado[:60_000])
    plataforma = _detectar_plataforma(combinado[:60_000])
    whatsapp = _extraer_whatsapp(combinado[:80_000])
    instagram = _extraer_instagram(combinado[:80_000])
    encaja, motivo_descarte = _encaja_con_nicho(combinado[:80_000], texto_para_senales, nicho)

    lineas_dossier = [f"Web: {url}", f"Marca real: {marca}"]
    if ciudad:
        lineas_dossier.append(f"Ciudad detectada: {ciudad}")
    if plataforma:
        lineas_dossier.append(f"Plataforma: {plataforma}")
    if instagram:
        lineas_dossier.append(f"Instagram: {instagram}")
    if meta_desc:
        lineas_dossier.append(f"Descripción en su web: {meta_desc}")
    if titulares:
        lineas_dossier.append("Titulares visibles: " + " | ".join(titulares))
    if extracto and extracto.lower() not in (meta_desc or "").lower():
        lineas_dossier.append(f"Extracto visible: {extracto[:320]}")

    return {
        "marca": marca,
        "website": url,
        "ciudad": ciudad,
        "plataforma": plataforma,
        "whatsapp": whatsapp,
        "instagram": instagram,
        "encaja": encaja,
        "motivo_descarte": motivo_descarte,
        "dossier": "\n".join(lineas_dossier)[:1600],
    }


def enriquecer_lead_por_dominio(email_addr: str, nicho: str = "", website: str = "") -> dict[str, object] | None:
    """Investiga la web real de un lead existente usando su sitio o dominio corporativo."""
    urls: list[str] = []
    if website and website.strip():
        u = website.strip()
        urls.append(u if u.startswith("http") else f"https://{u}")
    dom = _domain_of(email_addr)
    if dom and dom not in FREE_MAIL_DOMAINS and not _is_blocked_domain(dom):
        for cand in (f"https://{dom}/", f"https://www.{dom}/"):
            if cand not in urls:
                urls.append(cand)
    for target in urls[:2]:
        try:
            _, home_html = _fetch_url(target, timeout=5, allow_insecure_fallback=True)
            if home_html:
                return analizar_sitio_web(home_html, target, nicho=nicho)
        except Exception:
            continue
    return None


def scrape_site_contact(url: str, industry: str, nicho: str) -> dict[str, str] | None:
    if not url.startswith("http"):
        url = f"https://{url}"
    dom = _domain_of(url)
    if _is_blocked_domain(dom):
        return None
    try:
        _, home_html = _fetch_url(url, timeout=7, allow_insecure_fallback=True)
        if not home_html:
            return None
    except Exception:
        return None

    if not _looks_relevant_spanish_site(home_html, dom):
        return None

    title_m = TITLE_RE.search(home_html)
    title = title_m.group(1) if title_m else ""
    if any(bad_kw in (title or "").lower() for bad_kw in ("agencia de viajes", "tours ", "turismo ", "vuelos baratos")):
        return None

    emails = _clean_email_candidates(home_html, dom)
    sub_html_found = ""

    # La home casi siempre publica el buzón de la empresa; los nombres de las
    # personas viven en "nosotros", "equipo" y "contacto". Antes esas páginas solo
    # se miraban si la home no traía NADA, así que nos quedábamos con el info@ y
    # nunca veíamos al dueño. Ahora se miran siempre y se juntan los candidatos.
    hay_persona = any(
        _parece_correo_de_persona(em.split("@", 1)[0], em.split("@")[-1]) for em in emails
    )
    if not hay_persona:
        candidate_links: list[str] = []
        contact_hints = (
            "contact", "cotiz", "nosotros", "quienes", "acerca", "about", "mayorist",
            "escribenos", "equipo", "team", "staff", "directorio", "gerencia",
        )
        for href in LINK_RE.findall(home_html):
            low = href.lower()
            if any(k in low for k in contact_hints):
                full = urllib.parse.urljoin(url, href)
                if _domain_of(full) == dom and full not in candidate_links and full != url:
                    candidate_links.append(full)
        for fallback_slug in ("/contacto", "/contactenos", "/nosotros", "/equipo", "/pages/contacto"):
            fb_url = urllib.parse.urljoin(url, fallback_slug)
            if fb_url not in candidate_links:
                candidate_links.append(fb_url)
        for sub_url in candidate_links[:4]:
            try:
                _, sub_html = _fetch_url(sub_url, timeout=5, allow_insecure_fallback=True)
            except Exception:
                continue
            if not sub_html:
                continue
            nuevos = _clean_email_candidates(sub_html, dom)
            if not nuevos:
                continue
            if not sub_html_found:
                sub_html_found = sub_html
            for em in nuevos:
                if em not in emails:
                    emails.append(em)
            if any(
                _parece_correo_de_persona(em.split("@", 1)[0], em.split("@")[-1]) for em in nuevos
            ):
                sub_html_found = sub_html
                break
        # Quedan ordenados como los puntúa el buscador: la persona primero.
        emails = _clean_email_candidates_sort(emails, dom)

    if not emails:
        return None

    # Filtro duro: solo personas. Un buzón de empresa (info@, ventas@, hola@) lo lee
    # una recepcionista o nadie: 18 de los primeros 26 correos fueron a buzones y
    # respondieron 0. Si el sitio no publica a una persona, el sitio se descarta.
    emails = [
        em for em in emails
        if _parece_correo_de_persona(em.split("@", 1)[0], em.split("@")[-1])
    ]
    if not emails:
        return None

    best_email = ""
    for cand in emails[:4]:
        if verify_domain_mx(cand):
            best_email = cand
            break
    if not best_email:
        return None

    perfil = analizar_sitio_web(home_html, url, nicho=nicho, sub_html=sub_html_found)
    if not perfil.get("encaja"):
        return None

    company = _marca_confiable(
        str(perfil.get("marca") or ""), dom, _clean_business_name(title, dom),
    )
    dossier = str(perfil.get("dossier") or "")
    # El nicho lo decide el negocio, no la consulta que lo encontró.
    nicho_real = clasificar_nicho_por_texto(f"{dossier} {title}", nicho_actual=nicho)
    return {
        "nombre": company,
        "empresa": company,
        "correo": best_email,
        "whatsapp": str(perfil.get("whatsapp") or ""),
        "website": str(perfil.get("website") or url),
        "dossier": dossier,
        "nicho": nicho_real,
        "industria": industry if nicho_real == nicho else "",
        "servicio": industry if nicho_real == nicho else "",
    }


def _extract_candidate_roots(raw_urls: list[str], seen_doms: set[str], max_results: int) -> list[str]:
    urls: list[str] = []
    for target in raw_urls:
        if not target.startswith(("http://", "https://")):
            continue
        dom = _domain_of(target)
        if _is_blocked_domain(dom) or dom in seen_doms:
            continue
        seen_doms.add(dom)
        parsed = urllib.parse.urlparse(target)
        urls.append(f"{parsed.scheme}://{parsed.netloc}/")
        if len(urls) >= max_results:
            break
    return urls


def _decode_bing_u(param_u: str) -> str:
    if not param_u.startswith("a1"):
        return ""
    raw = param_u[2:]
    raw += "=" * ((4 - len(raw) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def search_duckduckgo_urls(query: str, max_results: int = 12) -> list[str]:
    seen_doms: set[str] = set()
    collected: list[str] = []

    # 1) DuckDuckGo HTML (POST)
    form_data = urllib.parse.urlencode({"q": query, "kl": "co-es"}).encode("utf-8")
    try:
        status, body = _fetch_url(
            "https://html.duckduckgo.com/html/",
            timeout=9,
            max_bytes=350_000,
            data=form_data,
            extra_headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://html.duckduckgo.com",
                "Referer": "https://html.duckduckgo.com/",
            },
        )
        if status == 200 and body:
            raw_targets: list[str] = []
            for href in LINK_RE.findall(body):
                target = html.unescape(href)
                if "uddg=" in target:
                    qs = urllib.parse.parse_qs(urllib.parse.urlparse(target).query)
                    if qs.get("uddg"):
                        target = urllib.parse.unquote(qs["uddg"][0])
                raw_targets.append(target)
            collected.extend(_extract_candidate_roots(raw_targets, seen_doms, max_results))
    except Exception:
        pass

    if len(collected) >= max_results:
        return collected[:max_results]

    # 2) Respaldo: Yahoo Search Colombia
    try:
        yq = urllib.parse.urlencode({"p": f"{query} Colombia", "ei": "UTF-8"})
        status, ybody = _fetch_url(
            f"https://co.search.yahoo.com/search?{yq}",
            timeout=9,
            max_bytes=420_000,
        )
        if status == 200 and ybody:
            raw_targets = []
            for href in LINK_RE.findall(ybody):
                target = html.unescape(href)
                if "/RU=" in target:
                    ru_part = target.split("/RU=", 1)[1].split("/RK=", 1)[0]
                    target = urllib.parse.unquote(ru_part)
                if "yahoo.com" in _domain_of(target):
                    continue
                raw_targets.append(target)
            collected.extend(
                _extract_candidate_roots(raw_targets, seen_doms, max_results - len(collected))
            )
    except Exception:
        pass

    if len(collected) >= max_results:
        return collected[:max_results]

    # 3) Tercer respaldo: Bing HTML
    try:
        bq = urllib.parse.urlencode({"q": f"{query} Colombia", "setlang": "es"})
        status, bbody = _fetch_url(
            f"https://www.bing.com/search?{bq}",
            timeout=9,
            max_bytes=420_000,
        )
        if status == 200 and bbody:
            raw_targets = []
            for href in LINK_RE.findall(bbody):
                target = html.unescape(href)
                if "bing.com/ck/a" in target:
                    qs = urllib.parse.parse_qs(urllib.parse.urlparse(target).query)
                    if qs.get("u"):
                        decoded = _decode_bing_u(qs["u"][0])
                        if decoded:
                            target = decoded
                raw_targets.append(target)
            collected.extend(
                _extract_candidate_roots(raw_targets, seen_doms, max_results - len(collected))
            )
    except Exception:
        pass

    return collected[:max_results]


def _read_db_state_readonly() -> tuple[set[str], int]:
    """Lee correos conocidos y cursor sin crear ni modificar `data/el_socio.db`."""
    if not database.DB_PATH.exists():
        return set(), 0
    known: set[str] = set()
    cursor_val = 0
    try:
        conn = sqlite3.connect(f"file:{database.DB_PATH}?mode=ro", uri=True)
        try:
            for (em,) in conn.execute("SELECT LOWER(TRIM(email)) FROM leads WHERE email != ''"):
                if em:
                    known.add(em)
            for (em,) in conn.execute("SELECT LOWER(TRIM(recipient)) FROM outbox WHERE recipient != ''"):
                if em:
                    known.add(em)
            row = conn.execute("SELECT value FROM settings WHERE key = 'hunter_query_cursor'").fetchone()
            if row and row[0]:
                cursor_val = int(row[0])
        finally:
            conn.close()
    except Exception:
        pass
    return known, cursor_val


def discover_new_prospects(
    needed: int = 15,
    *,
    queries_to_run: int = 4,
    max_queries: int = 16,
    dry_run: bool = False,
) -> list[dict[str, str]]:
    if needed <= 0:
        return []

    all_queries = load_nicho_queries()
    if not all_queries:
        return []

    if dry_run:
        known_emails, cursor = _read_db_state_readonly()
    else:
        database.init_db()
        known_emails = database.list_all_known_emails()
        settings = database.get_settings()
        try:
            cursor = int(settings.get("hunter_query_cursor", "0"))
        except ValueError:
            cursor = 0

    known_domains = {_domain_of(e) for e in known_emails if "@" in e}
    known_domains -= {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com", "live.com"}

    total_q = len(all_queries)
    query_budget = min(total_q, max(queries_to_run, max_queries))
    # Tope por query para repartir el cupo diario entre varios nichos y ciudades.
    max_per_query = max(2, (needed + 3) // 4) if total_q >= 4 else needed

    discovered: list[dict[str, str]] = []
    seen_sites: set[str] = set()
    queries_executed = 0

    for i in range(query_budget):
        if len(discovered) >= needed:
            break
        q_text, industry, nicho = all_queries[(cursor + i) % total_q]
        queries_executed += 1
        found_this_query = 0
        site_urls = search_duckduckgo_urls(q_text, max_results=12)
        for site_url in site_urls:
            if len(discovered) >= needed or found_this_query >= max_per_query:
                break
            dom = _domain_of(site_url)
            if not dom or dom in seen_sites or dom in known_domains or _is_blocked_domain(dom):
                continue
            seen_sites.add(dom)
            lead = scrape_site_contact(site_url, industry, nicho)
            if not lead:
                continue
            em = lead["correo"].lower()
            if em in known_emails:
                continue
            known_emails.add(em)
            known_domains.add(_domain_of(em))
            discovered.append(lead)
            found_this_query += 1

    if not dry_run and queries_executed > 0:
        database.update_settings({"hunter_query_cursor": str((cursor + queries_executed) % total_q)})

    return discovered


def enriquecer_leads_pendientes(*, limit: int = 30, dry_run: bool = False) -> dict[str, object]:
    """Analiza y limpia los leads en `nuevo_lead` que todavía no tienen dossier web."""
    if not dry_run:
        database.init_db()
    if not database.DB_PATH.exists():
        return {"enriquecidos": 0, "descartados": 0, "sin_web": 0, "detalles": []}

    leads = database.list_cold_leads_for_agent(limit=max(1, limit))
    enriquecidos = 0
    descartados = 0
    sin_web = 0
    detalles: list[dict[str, str]] = []

    for lead in leads:
        email_addr = (lead.get("email") or "").strip().lower()
        local, _, dom = email_addr.partition("@")
        nicho = (lead.get("nicho") or "").strip()
        empresa_actual = (lead.get("company") or "").strip()

        # 1) Descarta ruido evidente que se coló antes del filtro nuevo.
        es_ruido = (
            _is_blocked_domain(dom)
            or _es_gmail_basura(local, dom)
            or any(local.startswith(pref) for pref in BLOCKED_EMAIL_STARTSWITH)
            or any(
                local == bad or local.startswith(bad + ".") or local.startswith(bad + "-") or local.startswith(bad + "_")
                for bad in BLOCKED_EMAIL_PREFIXES
            )
        )
        if es_ruido:
            motivo = f"Descartado automáticamente por filtro de calidad ({email_addr})"
            if not dry_run and lead.get("id"):
                database.update_lead_stage(int(lead["id"]), "no_interesado", notes=motivo)
                database.cancel_pending_outbox_for_recipient(email_addr)
            descartados += 1
            detalles.append({"email": email_addr, "accion": "descartado", "detalle": motivo})
            continue

        # 2) Intenta analizar su web real si tiene dominio corporativo o website guardado.
        perfil = enriquecer_lead_por_dominio(
            email_addr, nicho=nicho, website=str(lead.get("website") or ""),
        )
        if not perfil:
            # Si es gmail/sin web pero tiene título SEO feo, al menos limpia el nombre si se puede.
            sin_web += 1
            detalles.append({"email": email_addr, "accion": "sin_web_corporativa", "detalle": empresa_actual})
            continue

        if not perfil.get("encaja"):
            motivo = f"Descartado tras analizar su web: {perfil.get('motivo_descarte') or 'fuera_de_nicho'}"
            if not dry_run and lead.get("id"):
                database.update_lead_enrichment(
                    int(lead["id"]),
                    company=str(perfil.get("marca") or empresa_actual),
                    website=str(perfil.get("website") or ""),
                    dossier=str(perfil.get("dossier") or ""),
                )
                database.update_lead_stage(int(lead["id"]), "no_interesado", notes=motivo)
                database.cancel_pending_outbox_for_recipient(email_addr)
            descartados += 1
            detalles.append({"email": email_addr, "accion": "descartado_por_web", "detalle": motivo})
            continue

        dom_lead = (email_addr.split("@")[-1] if "@" in email_addr else "").lower()
        marca_real = _marca_confiable(str(perfil.get("marca") or ""), dom_lead, empresa_actual)
        empresa_final = (
            marca_real
            if marca_real and (not empresa_actual or _parece_titulo_seo(empresa_actual))
            else empresa_actual
        )
        if not dry_run and lead.get("id"):
            database.update_lead_enrichment(
                int(lead["id"]),
                company=empresa_final,
                name=empresa_final,
                whatsapp=str(perfil.get("whatsapp") or "") or None,
                website=str(perfil.get("website") or ""),
                dossier=str(perfil.get("dossier") or ""),
            )
        enriquecidos += 1
        detalles.append({
            "email": email_addr,
            "accion": "enriquecido",
            "marca": empresa_final,
            "ciudad": str(perfil.get("ciudad") or ""),
            "web": str(perfil.get("website") or ""),
        })

    return {
        "dry_run": dry_run,
        "revisados": len(leads),
        "enriquecidos": enriquecidos,
        "descartados": descartados,
        "sin_web": sin_web,
        "detalles": detalles,
    }


# Rutas donde una empresa publica a su gente. La home publica el buzón; el nombre
# del dueño vive en "equipo", "nosotros", y a veces en la política de privacidad
# (ahí va el correo del responsable de datos, que casi siempre es una persona).
_PISTAS_PAGINA_DE_PERSONA = (
    "equipo", "team", "nosotros", "quienes", "acerca", "about", "staff",
    "directorio", "gerencia", "direccion", "fundador", "founder", "socios",
    "contacto", "contact", "prensa", "press", "privacidad", "privacy",
    "tratamiento-de-datos", "proteccion-de-datos", "legal", "autor", "author",
)

_SLUGS_PAGINA_DE_PERSONA = (
    "/nosotros", "/equipo", "/quienes-somos", "/about", "/about-us", "/team",
    "/contacto", "/contactenos", "/politica-de-privacidad", "/privacidad",
    "/tratamiento-de-datos", "/aviso-legal", "/pages/nosotros", "/pages/contacto",
)


def buscar_persona_en_dominio(
    dominio: str, *, website: str = "", max_paginas: int = 6,
) -> str:
    """Busca un correo de PERSONA publicado en el sitio de una empresa que ya conocemos.

    De los 133 descartados teníamos 91 dominios reales ya calificados por nicho: tirar
    la empresa entera porque su home publica `info@` era botar trabajo ya hecho. El
    nombre del dueño suele estar a un clic, en "equipo" o en la política de datos.
    Devuelve "" si el sitio de verdad no publica a nadie. Nunca inventa direcciones.
    """
    dominio = (dominio or "").strip().lower().lstrip(".")
    if not dominio or _is_blocked_domain(dominio) or dominio in FREE_MAIL_DOMAINS:
        return ""

    raices = []
    if website.startswith("http"):
        raices.append(website)
    raices.extend([f"https://{dominio}/", f"https://www.{dominio}/"])

    home_html = ""
    base_url = ""
    for raiz in raices:
        try:
            _, home_html = _fetch_url(raiz, timeout=7, allow_insecure_fallback=True)
        except Exception:
            continue
        if home_html:
            base_url = raiz
            break
    if not home_html:
        return ""

    candidatos: list[str] = list(_clean_email_candidates(home_html, dominio))

    paginas: list[str] = []
    for href in LINK_RE.findall(home_html):
        low = href.lower()
        if any(pista in low for pista in _PISTAS_PAGINA_DE_PERSONA):
            full = urllib.parse.urljoin(base_url, href)
            if _domain_of(full) == dominio and full not in paginas and full != base_url:
                paginas.append(full)
    for slug in _SLUGS_PAGINA_DE_PERSONA:
        full = urllib.parse.urljoin(base_url, slug)
        if full not in paginas:
            paginas.append(full)

    for pagina in paginas[:max_paginas]:
        try:
            _, sub_html = _fetch_url(pagina, timeout=5, allow_insecure_fallback=True)
        except Exception:
            continue
        if not sub_html:
            continue
        for em in _clean_email_candidates(sub_html, dominio):
            if em not in candidatos:
                candidatos.append(em)
        # En cuanto aparece una persona verificable, se corta: no hace falta
        # recorrer el sitio entero y cada página son segundos de más.
        for em in candidatos:
            local, _, dom = em.partition("@")
            if _parece_correo_de_persona(local, dom) and verify_domain_mx(em):
                return em

    for em in candidatos:
        local, _, dom = em.partition("@")
        if _parece_correo_de_persona(local, dom) and verify_domain_mx(em):
            return em
    return ""


# OpenStreetMap: directorio público, gratis y sin clave. Da negocios por categoría
# y ciudad exacta — un universo de dominios que los buscadores no devuelven porque
# no están posicionados. Son los negocios pequeños, justo los que nos interesan.
OSM_TAGS_POR_NICHO: dict[str, tuple[str, ...]] = {
    "fichas-tecnicas-ropa": (
        'nwr["shop"="clothes"]', 'nwr["shop"="boutique"]', 'nwr["craft"="tailor"]',
        'nwr["shop"="fabric"]', 'nwr["shop"="sewing"]', 'nwr["shop"="bag"]',
    ),
    "modelado-3d-espacios": (
        'nwr["office"="architect"]', 'nwr["craft"="carpenter"]', 'nwr["craft"="joiner"]',
        'nwr["shop"="interior_decoration"]', 'nwr["shop"="kitchen"]', 'nwr["shop"="furniture"]',
    ),
    "ecommerce-catalogo-visual": (
        'nwr["shop"="cosmetics"]', 'nwr["shop"="jewelry"]', 'nwr["shop"="shoes"]',
        'nwr["shop"="pet"]', 'nwr["shop"="sports"]', 'nwr["shop"="chocolate"]',
        'nwr["shop"="coffee"]',
    ),
    "automatizacion-agencias-estudios": (
        'nwr["office"="advertising_agency"]', 'nwr["office"="graphic_design"]',
        'nwr["office"="it"]', 'nwr["craft"="photographer"]', 'nwr["office"="estate_agent"]',
        'nwr["office"="consulting"]',
    ),
}

OSM_CIUDADES: tuple[str, ...] = (
    "Medellín", "Bogotá", "Cali", "Barranquilla", "Bucaramanga", "Pereira",
    "Cartagena", "Manizales", "Envigado", "Itagüí", "Sabaneta", "Bello",
)

_OSM_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)


def _osm_consultar(ciudad: str, selectores: tuple[str, ...], *, limite: int = 200) -> list[dict]:
    """Pide a Overpass los negocios de una categoría en una ciudad. Devuelve [] si falla."""
    cuerpo_sel = "\n  ".join(f"{sel}(area.a);" for sel in selectores)
    consulta = (
        "[out:json][timeout:50];\n"
        f'area["name"="{ciudad}"]["boundary"="administrative"]->.a;\n'
        f"(\n  {cuerpo_sel}\n);\n"
        f"out tags center {limite};"
    )
    datos = urllib.parse.urlencode({"data": consulta}).encode("utf-8")
    for endpoint in _OSM_ENDPOINTS:
        try:
            status, body = _fetch_url(
                endpoint, timeout=60, max_bytes=3_000_000, data=datos,
                extra_headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    # Overpass responde 406 al User-Agent de navegador: exige uno
                    # identificable y un Accept de JSON, no de HTML.
                    "User-Agent": "ElSocio/1.0 (prospeccion de clientes; Colombia)",
                    "Accept": "application/json",
                },
            )
        except Exception:
            continue
        if status != 200 or not body:
            continue
        try:
            return json.loads(body).get("elements", []) or []
        except Exception:
            continue
    return []


def descubrir_por_openstreetmap(
    *, needed: int = 20, ciudades: tuple[str, ...] = (), nichos: tuple[str, ...] = (),
    dry_run: bool = False,
) -> dict[str, object]:
    """Fuente nueva: negocios de OSM con sitio propio, y dentro del sitio, la persona.

    Los buscadores devuelven siempre a los mismos (los que pagan SEO). OSM devuelve
    el taller de barrio con web sencilla, que es justo quien necesita esto y quien
    sí publica el correo del dueño.
    """
    database.init_db()
    conocidos = {e.lower() for e in database.list_all_known_emails()}
    dominios_conocidos = {_domain_of(e) for e in conocidos if "@" in e} - FREE_MAIL_DOMAINS

    objetivo_ciudades = ciudades or OSM_CIUDADES
    objetivo_nichos = nichos or tuple(OSM_TAGS_POR_NICHO)

    vistos: set[str] = set()
    candidatos: list[tuple[str, str, str, str]] = []  # (dominio, nombre, ciudad, nicho)
    for ciudad in objetivo_ciudades:
        for nicho in objetivo_nichos:
            selectores = OSM_TAGS_POR_NICHO.get(nicho, ())
            if not selectores:
                continue
            for el in _osm_consultar(ciudad, selectores):
                tags = el.get("tags") or {}
                web = (
                    tags.get("website") or tags.get("contact:website")
                    or tags.get("url") or ""
                )
                correo_osm = (tags.get("email") or tags.get("contact:email") or "").strip().lower()
                dom = _domain_of(web) or _domain_of(correo_osm)
                if not dom or dom in vistos or dom in dominios_conocidos or _is_blocked_domain(dom):
                    continue
                if dom in FREE_MAIL_DOMAINS:
                    continue
                vistos.add(dom)
                candidatos.append((dom, (tags.get("name") or "").strip(), ciudad, nicho))

    encontrados: list[dict[str, str]] = []
    revisados = 0
    for dom, nombre, ciudad, nicho in candidatos:
        if len(encontrados) >= needed:
            break
        revisados += 1
        correo = buscar_persona_en_dominio(dom)
        if not correo or correo in conocidos:
            continue
        conocidos.add(correo)
        perfil = enriquecer_lead_por_dominio(correo, nicho=nicho, website=f"https://{dom}/")
        marca = _marca_confiable(str((perfil or {}).get("marca") or ""), dom, nombre)
        dossier = str((perfil or {}).get("dossier") or "")
        # La categoría de OSM orienta, pero manda lo que dice su propio sitio.
        nicho_real = clasificar_nicho_por_texto(f"{dossier} {nombre}", nicho_actual=nicho)
        encontrados.append({
            "nombre": marca or nombre or dom,
            "empresa": marca or nombre or dom,
            "correo": correo,
            "whatsapp": str((perfil or {}).get("whatsapp") or ""),
            "website": f"https://{dom}/",
            "dossier": dossier,
            "nicho": nicho_real,
            "servicio": "",
            "ciudad": ciudad,
        })

    guardados = 0 if dry_run else guardar_prospectos(encontrados)
    return {
        "dry_run": dry_run,
        "fuente": "openstreetmap",
        "negocios_con_dominio": len(candidatos),
        "dominios_revisados": revisados,
        "personas_encontradas": len(encontrados),
        "guardados": guardados,
        "prospects": encontrados,
    }

def rescatar_personas_de_descartados(
    *, limit: int = 40, dry_run: bool = False,
) -> dict[str, object]:
    """Vuelve a los dominios que descartamos por publicar solo buzón y busca a la persona.

    Es la fuente más barata que tenemos: la empresa ya está calificada por nicho y
    verificada, solo faltaba a quién escribirle.
    """
    database.init_db()
    conocidos = {e.lower() for e in database.list_all_known_emails()}

    # Se piden de más y se filtra aquí: lo que descarta es el filtro de persona de
    # hoy, no la nota que quedó escrita el día que se descartó.
    filas = [
        f for f in database.leads_descartados_por_buzon(limit=limit * 6)
        if "@" in str(f.get("email") or "")
        and not _parece_correo_de_persona(
            str(f["email"]).split("@", 1)[0].lower(), str(f["email"]).split("@")[-1].lower(),
        )
    ][:limit]
    revisados = 0
    rescatados: list[dict[str, str]] = []
    sin_persona: list[str] = []

    for fila in filas:
        correo_viejo = str(fila.get("email") or "").lower()
        web = str(fila.get("website") or "")
        # Muchas PyMEs publican un Gmail pero sí tienen sitio propio: el dominio
        # que hay que recorrer es el del sitio, no el del correo.
        dom = _domain_of(correo_viejo)
        if not dom or dom in FREE_MAIL_DOMAINS:
            dom = _domain_of(web)
        if not dom or dom in FREE_MAIL_DOMAINS:
            continue
        revisados += 1
        encontrado = buscar_persona_en_dominio(dom, website=web)
        if not encontrado or encontrado in conocidos:
            sin_persona.append(dom)
            continue
        conocidos.add(encontrado)
        dossier = str(fila.get("dossier") or "")
        empresa = str(fila.get("company") or "")
        # `info@tallerarchitects.com` venía marcado como "fichas de ropa" solo porque
        # lo encontró una consulta de ropa. Aquí se corrige con el texto de su sitio.
        nicho_real = clasificar_nicho_por_texto(
            f"{dossier} {empresa}", nicho_actual=str(fila.get("nicho") or ""),
        )
        rescatados.append({
            "nombre": empresa or str(fila.get("name") or ""),
            "empresa": empresa,
            "correo": encontrado,
            "whatsapp": str(fila.get("whatsapp") or ""),
            "website": str(fila.get("website") or ""),
            "dossier": dossier,
            "nicho": nicho_real,
            "servicio": str(fila.get("service_interest") or ""),
            "reemplaza_a": correo_viejo,
        })

    guardados = 0 if dry_run else guardar_prospectos(rescatados)
    return {
        "dry_run": dry_run,
        "dominios_revisados": revisados,
        "personas_encontradas": len(rescatados),
        "guardados": guardados,
        "sin_persona": len(sin_persona),
        "rescatados": rescatados,
    }


def guardar_prospectos(items: list[dict[str, str]]) -> int:
    """Mete en la cola lo descubierto. Corrido a mano, el buscador solo imprimía:
    encontraba prospectos reales y los tiraba a la basura al terminar."""
    database.init_db()
    guardados = 0
    for row in items:
        correo = (row.get("correo") or "").strip().lower()
        if not correo:
            continue
        try:
            database.upsert_lead(
                name=row.get("nombre", ""), company=row.get("empresa", ""), email=correo,
                whatsapp=row.get("whatsapp", ""), nicho=row.get("nicho", ""),
                service_interest=row.get("servicio", ""), source="prospeccion_auto",
                stage="nuevo_lead",
                notes="Descubierto, analizado y verificado (MX OK) por El Socio",
                website=row.get("website", ""), dossier=row.get("dossier", ""),
            )
            guardados += 1
        except Exception:
            continue
    return guardados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Buscador y verificador MX de prospectos reales.")
    parser.add_argument("--needed", type=int, default=15, help="Cupo de prospectos a descubrir.")
    parser.add_argument("--max-queries", type=int, default=16, help="Máximo de queries por corrida.")
    parser.add_argument("--enriquecer-pendientes", action="store_true",
                        help="Analiza y limpia los leads en frío pendientes en data/el_socio.db.")
    parser.add_argument("--dry-run", action="store_true", help="Prueba en seco sin tocar data/el_socio.db.")
    parser.add_argument("--osm", action="store_true",
                        help="Descubre por OpenStreetMap (negocios por categoría y ciudad) "
                             "y busca a la persona dentro de su sitio.")
    parser.add_argument("--rescatar-personas", action="store_true",
                        help="Vuelve a las empresas descartadas por publicar solo buzón "
                             "y busca a la persona en su sitio (equipo, nosotros, legal).")
    parser.add_argument("--guardar", action="store_true",
                        help="Guarda lo descubierto en data/el_socio.db como nuevo_lead (llena la cola).")
    args = parser.parse_args(argv)

    if args.osm:
        print(json.dumps(
            descubrir_por_openstreetmap(needed=max(1, args.needed), dry_run=args.dry_run),
            ensure_ascii=False, indent=2,
        ))
        return 0


    if args.rescatar_personas:
        print(json.dumps(
            rescatar_personas_de_descartados(limit=max(1, args.needed), dry_run=args.dry_run),
            ensure_ascii=False, indent=2,
        ))
        return 0

    if args.enriquecer_pendientes:
        print(json.dumps(
            enriquecer_leads_pendientes(limit=max(1, args.needed), dry_run=args.dry_run),
            ensure_ascii=False, indent=2,
        ))
        return 0

    items = discover_new_prospects(
        needed=args.needed,
        max_queries=args.max_queries,
        dry_run=args.dry_run,
    )
    guardados = 0
    if args.guardar and not args.dry_run:
        guardados = guardar_prospectos(items)

    print(json.dumps({
        "dry_run": args.dry_run,
        "needed": args.needed,
        "found": len(items),
        "guardados": guardados,
        "cupo_lleno": len(items) >= args.needed,
        "prospects": items,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
    "example.com", "email.com", "correo.com", "dominio.com", "tudominio.com",
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
    "indeed.com", "glassdoor.com", "clutch.co", "sortlist.co", "sortlist.com",
    "cylex.com.co", "infobel.com", "kompass.com", "einforma.co", "informacolombia.com",
    "empresite.eleconomistaamerica.co", "lasempresas.com.co", "directorio-empresas.einforma.co",
    "camaramedellin.com.co", "ccb.org.co", "ccc.org.co", "camarabaq.org.co",
    "inexmoda.org.co", "procolombia.co",
}

BLOCKED_DOMAIN_SUFFIXES = (
    ".gov.co", ".gob.co", ".edu.co", ".mil.co", ".edu", ".gov",
    ".es", ".mx", ".ar", ".cl", ".pe", ".ve", ".uy", ".py", ".bo", ".ec",
    ".cr", ".pa", ".gt", ".do", ".br", ".pt", ".fr", ".de", ".it", ".uk",
    ".ru", ".cn", ".jp", ".in", ".au", ".ca",
)

BLOCKED_EMAIL_PREFIXES = (
    "noreply", "no-reply", "no_reply", "donotreply", "mailer-daemon", "postmaster",
    "abuse", "privacy", "legal", "dmca", "security", "webmaster", "hostmaster",
    "root", "billing", "facturacion", "contabilidad", "cartera", "tesoreria",
    "impuestos", "proveedores", "compras", "rh", "rrhh", "talento", "seleccion",
    "gestionhumana", "gestion-humana", "gestion_humana", "recursoshumanos",
    "recursos-humanos", "nomina", "convocatorias", "empleo", "vacantes",
    "pqrs", "pqr", "notificaciones", "protecciondedatos", "habeasdata",
    "cumplimiento", "denuncias", "soporte", "reservas", "sentry", "wix",
    "ejemplo", "example", "test", "user", "correo", "email", "tuemail", "tunombre",
)

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
                if ctype and "text" not in ctype and "html" not in ctype and "xml" not in ctype:
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


def _clean_business_name(raw_title: str, fallback_domain: str) -> str:
    txt = html.unescape(re.sub(r"\s+", " ", raw_title or "")).strip()
    for sep in (" | ", " - ", " – ", " — ", " :: ", " • "):
        if sep in txt:
            parts = [p.strip() for p in txt.split(sep) if p.strip()]
            useful = [
                p for p in parts
                if len(p) >= 4 and p.lower() not in {"inicio", "home", "contacto", "contáctenos", "contactenos"}
            ]
            if useful:
                txt = useful[0]
                break
    txt = re.sub(r"[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ&.\-\s]", "", txt).strip(" -–—.")
    if len(txt) < 3 or len(txt) > 55 or txt.lower() in {"inicio", "home", "contacto", "tienda", "bienvenido", "bienvenidos"}:
        return fallback_domain.split(".")[0].replace("-", " ").replace("_", " ").title()
    return txt


def _clean_email_candidates(raw_html: str, site_domain: str) -> list[str]:
    text = urllib.parse.unquote(html.unescape(raw_html or "")).replace("%40", "@")
    found = EMAIL_RE.findall(text)
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    preferred_prefixes = {
        "contacto", "contactenos", "info", "comercial", "ventas", "hola",
        "gerencia", "pedidos", "mercadeo", "diseno", "estudio", "proyectos",
        "direccion", "atencion", "tienda", "administracion",
    }
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
        if _is_blocked_domain(dom):
            continue
        score = 0
        if dom == site_domain or dom.endswith("." + site_domain):
            score += 50
        elif dom in {"gmail.com", "hotmail.com", "outlook.com"}:
            score += 25
        if local in preferred_prefixes:
            score += 30
        scored.append((score, em_low))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [em for _, em in scored]


def _looks_relevant_spanish_site(raw_html: str, dom: str) -> bool:
    """Descarta blogs en inglés o portales extranjeros sin presencia en Colombia."""
    if dom.endswith(".co"):
        return True
    if COLOMBIA_SIGNAL_RE.search(raw_html):
        return True
    if HTML_LANG_EN_RE.search(raw_html[:1500]) and not SPANISH_SIGNAL_RE.search(raw_html):
        return False
    return bool(SPANISH_SIGNAL_RE.search(raw_html))


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

    if not emails:
        candidate_links: list[str] = []
        contact_hints = ("contact", "cotiz", "nosotros", "quienes", "acerca", "about", "mayorist", "escribenos")
        for href in LINK_RE.findall(home_html):
            low = href.lower()
            if any(k in low for k in contact_hints):
                full = urllib.parse.urljoin(url, href)
                if _domain_of(full) == dom and full not in candidate_links and full != url:
                    candidate_links.append(full)
        for fallback_slug in ("/contacto", "/contactenos", "/pages/contacto"):
            fb_url = urllib.parse.urljoin(url, fallback_slug)
            if fb_url not in candidate_links:
                candidate_links.append(fb_url)
        for sub_url in candidate_links[:3]:
            try:
                _, sub_html = _fetch_url(sub_url, timeout=5, allow_insecure_fallback=True)
                if sub_html:
                    emails = _clean_email_candidates(sub_html, dom)
                    if emails:
                        break
            except Exception:
                continue

    if not emails:
        return None

    best_email = ""
    for cand in emails[:4]:
        if verify_domain_mx(cand):
            best_email = cand
            break
    if not best_email:
        return None

    company = _clean_business_name(title, dom)
    return {
        "nombre": f"Equipo {company}",
        "empresa": company,
        "correo": best_email,
        "whatsapp": "",
        "nicho": nicho,
        "industria": industry,
        "servicio": industry,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Buscador y verificador MX de prospectos reales.")
    parser.add_argument("--needed", type=int, default=15, help="Cupo de prospectos a descubrir.")
    parser.add_argument("--max-queries", type=int, default=16, help="Máximo de queries por corrida.")
    parser.add_argument("--dry-run", action="store_true", help="Prueba en seco sin tocar data/el_socio.db.")
    args = parser.parse_args(argv)

    items = discover_new_prospects(
        needed=args.needed,
        max_queries=args.max_queries,
        dry_run=args.dry_run,
    )
    print(json.dumps({
        "dry_run": args.dry_run,
        "needed": args.needed,
        "found": len(items),
        "cupo_lleno": len(items) >= args.needed,
        "prospects": items,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

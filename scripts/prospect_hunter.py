#!/usr/bin/env python3
"""Zero-dependency prospect discovery & MX verification for El Socio.

Reads search queries from every file in nichos/*.md (a fenced ```queries block,
one "query texto | Industria/Etiqueta" per line) and scrapes public business
websites via DuckDuckGo HTML search, verifying each contact email's domain
can actually receive mail (MX/A record) before it's ever used.
"""

from __future__ import annotations

import html
import re
import socket
import subprocess
import sys
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
    "mercadolibre.com.co", "olx.com.co", "paginasamarillas.com.co",
    "tripadvisor.com", "booking.com", "airbnb.com", "expedia.com",
    "wix.com", "wixpress.com", "squarespace.com", "wordpress.com", "wordpress.org",
    "shopify.com", "godaddy.com", "cloudflare.com", "sentry.io", "example.com",
    "duckduckgo.com", "bing.com", "yahoo.com", "amazon.com", "canva.com",
    "eventbrite.com", "meetup.com", "foursquare.com",
}

BLOCKED_EMAIL_PREFIXES = (
    "noreply", "no-reply", "no_reply", "donotreply", "mailer-daemon", "postmaster",
    "abuse", "privacy", "legal", "dmca", "security", "webmaster", "hostmaster",
    "root", "billing", "facturacion", "contabilidad", "rh", "rrhh", "talento",
    "empleo", "vacantes", "ejemplo", "example", "test", "user",
)

EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]{2,64}@[a-zA-Z0-9.-]{2,190}\.[a-zA-Z]{2,12}\b")
LINK_RE = re.compile(r'href=["\']([^"\'#]+)["\']', flags=re.IGNORECASE)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", flags=re.IGNORECASE | re.DOTALL)
QUERIES_BLOCK_RE = re.compile(r"```queries\s*\n(.*?)```", flags=re.DOTALL)


def load_nicho_queries() -> list[tuple[str, str, str]]:
    """Return (query_text, industry_label, nicho_filename) tuples from every nichos/*.md file."""
    out: list[tuple[str, str, str]] = []
    if not NICHOS_DIR.is_dir():
        return out
    for md_path in sorted(NICHOS_DIR.glob("*.md")):
        if md_path.name.startswith("_"):
            continue
        text = md_path.read_text(encoding="utf-8")
        m = QUERIES_BLOCK_RE.search(text)
        if not m:
            continue
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            q, _, label = line.partition("|")
            out.append((q.strip(), label.strip(), md_path.stem))
    return out


def _domain_of(url_or_email: str) -> str:
    val = (url_or_email or "").strip().lower()
    if "@" in val:
        dom = val.split("@", 1)[1]
    else:
        parsed = urllib.parse.urlparse(val if "://" in val else f"https://{val}")
        dom = parsed.netloc.lower().split(":")[0]
    if dom.startswith("www."):
        dom = dom[4:]
    return dom


def _is_blocked_domain(dom: str) -> bool:
    dom = (dom or "").lower().strip(".")
    if not dom or "." not in dom:
        return True
    for bad in BLOCKED_DOMAINS:
        if dom == bad or dom.endswith("." + bad):
            return True
    return False


def verify_domain_mx(email_addr: str) -> bool:
    dom = _domain_of(email_addr)
    if not dom or "." not in dom:
        return False
    if dom in {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.es", "icloud.com", "live.com"}:
        return True
    try:
        proc = subprocess.run(
            ["dig", "+short", "+time=3", "+tries=1", "MX", dom],
            capture_output=True, text=True, timeout=6, check=False,
        )
        out = (proc.stdout or "").strip()
        mx_lines = [ln.strip() for ln in out.splitlines() if ln.strip() and not ln.strip().endswith(" .")]
        if mx_lines:
            return True
    except Exception:
        pass
    try:
        socket.getaddrinfo(dom, 25)
        return True
    except Exception:
        return False


def _fetch_url(url: str, timeout: int = 8, max_bytes: int = 280_000) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-CO,es;q=0.9,en;q=0.5",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if ctype and "text" not in ctype and "html" not in ctype and "xml" not in ctype:
            return ""
        return resp.read(max_bytes).decode("utf-8", errors="replace")


def _clean_business_name(raw_title: str, fallback_domain: str) -> str:
    txt = html.unescape(re.sub(r"\s+", " ", raw_title or "")).strip()
    for sep in (" | ", " - ", " – ", " — ", " :: ", " • "):
        if sep in txt:
            parts = [p.strip() for p in txt.split(sep) if p.strip()]
            useful = [p for p in parts if len(p) >= 4 and p.lower() not in {"inicio", "home", "contacto"}]
            if useful:
                txt = useful[0]
                break
    txt = re.sub(r"[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ&.\-\s]", "", txt).strip()
    if len(txt) < 3 or len(txt) > 55:
        return fallback_domain.split(".")[0].replace("-", " ").replace("_", " ").title()
    return txt


def _clean_email_candidates(raw_html: str, site_domain: str) -> list[str]:
    text = html.unescape(raw_html or "").replace("%40", "@")
    found = EMAIL_RE.findall(text)
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for em in found:
        em_low = em.strip().lower().strip(".")
        if em_low in seen:
            continue
        seen.add(em_low)
        local, _, dom = em_low.partition("@")
        if any(em_low.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".js", ".css")):
            continue
        if any(local == bad or local.startswith(bad + ".") or local.startswith(bad + "-") for bad in BLOCKED_EMAIL_PREFIXES):
            continue
        if _is_blocked_domain(dom):
            continue
        score = 0
        if dom == site_domain or dom.endswith("." + site_domain):
            score += 50
        elif dom in {"gmail.com", "hotmail.com", "outlook.com"}:
            score += 25
        if local in {"contacto", "contactenos", "info", "comercial", "ventas", "hola", "gerencia", "pedidos"}:
            score += 30
        scored.append((score, em_low))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [em for _, em in scored]


def scrape_site_contact(url: str, industry: str, nicho: str) -> dict[str, str] | None:
    if not url.startswith("http"):
        url = f"https://{url}"
    dom = _domain_of(url)
    if _is_blocked_domain(dom):
        return None
    try:
        home_html = _fetch_url(url)
        if not home_html:
            return None
    except Exception:
        return None

    title_m = TITLE_RE.search(home_html)
    title = title_m.group(1) if title_m else ""
    emails = _clean_email_candidates(home_html, dom)

    if not emails:
        candidate_links: list[str] = []
        for href in LINK_RE.findall(home_html):
            low = href.lower()
            if any(k in low for k in ("contact", "cotiz", "nosotros")):
                full = urllib.parse.urljoin(url, href)
                if _domain_of(full) == dom and full not in candidate_links and full != url:
                    candidate_links.append(full)
        if not candidate_links:
            candidate_links = [urllib.parse.urljoin(url, "/contacto")]
        for sub_url in candidate_links[:2]:
            try:
                sub_html = _fetch_url(sub_url, timeout=6)
                if sub_html:
                    emails = _clean_email_candidates(sub_html, dom)
                    if emails:
                        break
            except Exception:
                continue

    if not emails:
        return None

    best_email = ""
    for cand in emails[:3]:
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


def search_duckduckgo_urls(query: str, max_results: int = 12) -> list[str]:
    q = urllib.parse.urlencode({"q": query, "kl": "co-es"})
    url = f"https://html.duckduckgo.com/html/?{q}"
    try:
        body = _fetch_url(url, timeout=10, max_bytes=350_000)
    except Exception:
        return []
    urls: list[str] = []
    seen_doms: set[str] = set()
    for href in LINK_RE.findall(body):
        target = href
        if "uddg=" in href:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            if "uddg" in qs and qs["uddg"]:
                target = urllib.parse.unquote(qs["uddg"][0])
        if not target.startswith("http"):
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


def discover_new_prospects(needed: int = 14, *, queries_to_run: int = 3) -> list[dict[str, str]]:
    database.init_db()
    known_emails = database.list_all_known_emails()
    known_domains = {_domain_of(e) for e in known_emails if "@" in e}
    known_domains -= {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "live.com"}

    all_queries = load_nicho_queries()
    if not all_queries:
        return []

    settings = database.get_settings()
    try:
        cursor = int(settings.get("hunter_query_cursor", "0"))
    except ValueError:
        cursor = 0

    candidates: list[tuple[str, str, str]] = []  # (site_url, industry, nicho)
    total_q = len(all_queries)
    for i in range(min(queries_to_run, total_q)):
        q_text, industry, nicho = all_queries[(cursor + i) % total_q]
        for site_url in search_duckduckgo_urls(q_text, max_results=10):
            candidates.append((site_url, industry, nicho))
    database.update_settings({"hunter_query_cursor": str((cursor + queries_to_run) % total_q)})

    discovered: list[dict[str, str]] = []
    seen_sites: set[str] = set()
    for site_url, industry, nicho in candidates:
        if len(discovered) >= needed:
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
        discovered.append(lead)

    return discovered


if __name__ == "__main__":
    for item in discover_new_prospects(needed=5, queries_to_run=2):
        print(item)

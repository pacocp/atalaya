"""Universidade da Beira Interior open academic staff competitions."""
from __future__ import annotations

import datetime as dt
import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..http import fetch
from ..models import Offer

log = logging.getLogger(__name__)

LIST_URL = "https://www.ubi.pt/sites/academicos/pt/pagina/recrutamento"
OFFICIAL_HOSTS = ("ubi.pt", "diariodarepublica.pt")
DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](20\d{2})(?!\d)")
TIME_RE = re.compile(r"\b(\d{1,2})[.:](\d{2})\b")
NOTICE_RE = re.compile(r"\bEdital\s+n[ºo°]\s*(\d{1,5}/20\d{2})\b", re.I)


def _clean(value: str) -> str:
    return " ".join(value.split())


def _normal(value: str) -> str:
    return _clean(value).casefold()


def _official_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]
    return (
        parsed.scheme in {"http", "https"}
        and any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_HOSTS)
    )


def _has_header(table) -> bool:
    for row in table.find_all("tr"):
        text = _normal(row.get_text(" ", strip=True))
        if (
            "categoria/position" in text
            and "área disciplinar" in text
            and "data e hora limite" in text
        ):
            return True
    return False


def _find_open_table(soup):
    docentes_heading = next(
        (
            tag for tag in soup.find_all(["h1", "h2", "h3", "h4"])
            if "concursos para docentes" in _normal(tag.get_text(" ", strip=True))
        ),
        None,
    )
    if docentes_heading is None:
        raise RuntimeError("UBI docente recruitment heading not found; page structure may have changed")

    open_heading = next(
        (
            tag for tag in docentes_heading.find_all_next(["h1", "h2", "h3", "h4", "p", "strong"])
            if "candidaturas a decorrer" in _normal(tag.get_text(" ", strip=True))
        ),
        None,
    )
    if open_heading is None:
        raise RuntimeError("UBI open-candidature section not found; page structure may have changed")

    return next(
        (table for table in open_heading.find_all_next("table") if _has_header(table)),
        None,
    )


def _deadline(value: str) -> tuple[str | None, str | None]:
    date_match = DATE_RE.search(value)
    if not date_match:
        return None, None
    day, month, year = (int(part) for part in date_match.groups())
    try:
        deadline = dt.date(year, month, day).isoformat()
    except ValueError:
        return None, None
    time_match = TIME_RE.search(value)
    deadline_time = (
        f"{int(time_match.group(1)):02d}:{time_match.group(2)}"
        if time_match else None
    )
    return deadline, deadline_time


def _category(value: str) -> str:
    portuguese = _clean(value.split("/", 1)[0]).casefold()
    mapping = {
        "auxiliar": "Professor Auxiliar",
        "associado": "Professor Associado",
        "catedrático": "Professor Catedrático",
        "catedratico": "Professor Catedrático",
    }
    return mapping.get(portuguese, f"Professor {portuguese.title()}" if portuguese else "Pessoal docente")


def parse_listing(html: str, base_url: str = LIST_URL) -> list[Offer]:
    """Parse only the UBI 'Candidaturas a decorrer' table for teaching staff."""
    soup = BeautifulSoup(html, "html.parser")
    table = _find_open_table(soup)
    if table is None:
        raise RuntimeError("UBI open docente table not found; page structure may have changed")

    header_row = next(
        row for row in table.find_all("tr")
        if (
            "categoria/position" in _normal(row.get_text(" ", strip=True))
            and "área disciplinar" in _normal(row.get_text(" ", strip=True))
            and "data e hora limite" in _normal(row.get_text(" ", strip=True))
        )
    )
    headers = [_normal(cell.get_text(" ", strip=True)) for cell in header_row.find_all(["th", "td"], recursive=False)]
    if not headers:
        headers = [_normal(cell.get_text(" ", strip=True)) for cell in header_row.find_all(["th", "td"])]

    def index_for(prefix: str, fallback: int) -> int:
        return next((i for i, label in enumerate(headers) if prefix in label), fallback)

    category_idx = index_for("categoria", 0)
    area_idx = index_for("área disciplinar", 1)
    posts_idx = index_for("postos de trabalho", 2)
    notice_idx = index_for("edital", 4)
    deadline_idx = index_for("data e hora limite", 5)
    register_idx = index_for("registo", 6)

    offers: list[Offer] = []
    seen: set[str] = set()
    unparsed_rows = 0

    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if not cells:
            cells = row.find_all(["th", "td"])
        if len(cells) <= max(category_idx, area_idx, posts_idx, notice_idx, deadline_idx):
            continue
        if row is header_row:
            continue

        category_raw = _clean(cells[category_idx].get_text(" ", strip=True))
        area_raw = _clean(cells[area_idx].get_text(" ", strip=True))
        if not category_raw or not area_raw:
            continue

        position_type = _category(category_raw)
        area = _clean(area_raw.split(" / ", 1)[0])
        title = f"{position_type} — {area}"

        notice_link = None
        notice_url = ""
        for anchor in cells[notice_idx].find_all("a", href=True):
            candidate = urljoin(base_url, anchor["href"])
            if _official_url(candidate):
                notice_link = anchor
                notice_url = candidate
                break
        if not notice_url:
            unparsed_rows += 1
            continue
        if notice_url in seen:
            continue

        notice_text = _clean(notice_link.get_text(" ", strip=True))
        notice_match = NOTICE_RE.search(notice_text)
        if not notice_match:
            notice_match = NOTICE_RE.search(_clean(cells[notice_idx].get_text(" ", strip=True)))
        notice = notice_match.group(1) if notice_match else ""

        deadline, deadline_time = _deadline(_clean(cells[deadline_idx].get_text(" ", strip=True)))
        posts_match = re.search(r"\b(\d{1,3})\b", cells[posts_idx].get_text(" ", strip=True))
        n_posts = max(1, int(posts_match.group(1))) if posts_match else 1

        application_url = None
        if len(cells) > register_idx:
            for anchor in cells[register_idx].find_all("a", href=True):
                candidate = urljoin(base_url, anchor["href"])
                if urlparse(candidate).scheme in {"http", "https"}:
                    application_url = candidate
                    break

        notes = []
        if notice:
            notes.append(f"Edital n.º {notice}")
        if deadline_time:
            notes.append(f"Prazo até às {deadline_time}")
        if not deadline:
            notes.append("Prazo não identificado na listagem; confirmar no edital original.")

        seen.add(notice_url)
        offers.append(Offer(
            source="ubi-docentes",
            kind="position",
            title=title,
            url=notice_url,
            institution="Universidade da Beira Interior",
            region="Castelo Branco",
            position_type=position_type,
            deadline=deadline,
            n_posts=n_posts,
            notes="; ".join(notes),
            extra={
                "ubi_notice": notice or None,
                "ubi_category": category_raw,
                "ubi_area": area,
                "deadline_time": deadline_time,
                "application_url": application_url,
                "listing_url": base_url,
            },
        ))

    if unparsed_rows:
        raise RuntimeError(
            f"{unparsed_rows} UBI open docente row(s) had no official notice URL"
        )
    return offers


def scrape(today: dt.date | None = None) -> list[Offer]:
    """Collect UBI teaching competitions whose application deadline has not passed."""
    today = today or dt.date.today()
    offers = parse_listing(fetch(LIST_URL))
    current = [
        offer for offer in offers
        if not offer.deadline or offer.deadline >= today.isoformat()
    ]
    log.info("UBI docente competitions: %d current entries", len(current))
    return current

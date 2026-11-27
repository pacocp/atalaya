"""Universidade de Lisboa recruitment index (academic and research opportunities).

The public index exposes structured tables with title, number of posts, category,
closing date and a link to the main notice. Expired entries are filtered at scrape
time; the original notice/document URL is preserved in each record.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from ..http import fetch
from ..models import Offer

log = logging.getLogger(__name__)

LIST_URL = "https://www.ulisboa.pt/info/recrutamento"
MAX_PAGES = 10
DATE_DMY = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(20\d{2})(?!\d)")
ACADEMIC = re.compile(
    r"professor|docente|investigador|investiga[cç][ãa]o|"
    r"bolsa(?:s)?(?:\s+de\s+(?:doutoramento|investiga[cç][ãa]o))?|"
    r"doutoramento|p[oó]s[- ]?doc|research|cient[ií]fic",
    re.I,
)
ULISBOA_HOSTS = ("ulisboa.pt",)


def _official_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]
    return (
        parsed.scheme in {"http", "https"}
        and any(host == domain or host.endswith("." + domain) for domain in ULISBOA_HOSTS)
    )


def _iso_date(text: str) -> str | None:
    match = DATE_DMY.search(text)
    if not match:
        return None
    day, month, year = (int(value) for value in match.groups())
    try:
        return dt.date(year, month, day).isoformat()
    except ValueError:
        return None


def _posts(text: str) -> int:
    match = re.search(r"\b(\d{1,3})\b", text)
    return max(1, int(match.group(1))) if match else 1


def _institution(table) -> str:
    heading = table.find_previous(["h2", "h3", "h4", "h5"])
    if heading:
        value = " ".join(heading.get_text(" ", strip=True).split())
        if value and value.casefold() not in {"recrutamento", "concursos"}:
            return value
    return "Universidade de Lisboa"


def parse_listing(html: str, base_url: str = LIST_URL) -> list[Offer]:
    """Parse academic/research entries from the ULisboa recruitment tables."""
    soup = BeautifulSoup(html, "html.parser")
    offers: list[Offer] = []
    seen: set[str] = set()

    for table in soup.find_all("table"):
        institution = _institution(table)
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) < 5 or any(cell.name == "th" for cell in cells):
                continue

            code = " ".join(cells[0].get_text(" ", strip=True).split())
            title_cell = cells[1]
            title_link = title_cell.find("a", href=True)
            title = " ".join((title_link or title_cell).get_text(" ", strip=True).split())
            category = " ".join(cells[3].get_text(" ", strip=True).split())
            raw = f"{title} {category}"
            if not title or not ACADEMIC.search(raw):
                continue

            deadline = _iso_date(cells[4].get_text(" ", strip=True))
            href = title_link.get("href") if title_link else ""
            detail_url = urljoin(base_url, href) if href else ""
            doc_url = ""
            if len(cells) >= 6:
                doc_link = cells[5].find("a", href=True)
                if doc_link:
                    doc_url = urljoin(base_url, doc_link["href"])
            if not detail_url and doc_url:
                detail_url = doc_url
            if not detail_url or not _official_url(detail_url) or detail_url in seen:
                continue
            seen.add(detail_url)

            number_of_posts = _posts(cells[2].get_text(" ", strip=True))
            notes = []
            if code:
                notes.append(f"Código: {code}")
            if not deadline:
                notes.append("Prazo não identificado na listagem; confirmar no aviso original.")
            if doc_url and doc_url != detail_url:
                notes.append("Documento principal disponível no campo de dados adicionais.")

            offers.append(Offer(
                source="ulisboa", kind="position", title=title, url=detail_url,
                institution=institution, region="Lisboa",
                position_type=category or "Oportunidade académica/científica",
                deadline=deadline, n_posts=number_of_posts,
                notes=" ".join(notes),
                extra={
                    "ulisboa_code": code,
                    "ulisboa_document_url": doc_url or None,
                },
            ))
    return offers


def _page_url(page: int) -> str:
    if page == 0:
        return LIST_URL
    parsed = urlparse(LIST_URL)
    query = parse_qs(parsed.query)
    query["page"] = [str(page)]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def scrape(today: dt.date | None = None) -> list[Offer]:
    """Read the public index, keep non-expired academic/research opportunities."""
    today = today or dt.date.today()
    offers: list[Offer] = []
    seen: set[str] = set()

    for page in range(MAX_PAGES):
        page_url = _page_url(page)
        html = fetch(page_url)
        # Keep paging through tables with non-academic rows: an administrative-
        # only page must not hide academic results on the following page.
        if not BeautifulSoup(html, "html.parser").find("table"):
            break
        page_offers = parse_listing(html, page_url)
        for offer in page_offers:
            if offer.deadline and offer.deadline < today.isoformat():
                continue
            if offer.url not in seen:
                seen.add(offer.url)
                offers.append(offer)

    log.info("ULisboa recruitment: %d current academic/research entries", len(offers))
    return offers

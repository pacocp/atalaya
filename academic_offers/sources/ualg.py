"""Universidade do Algarve public academic/research recruitment index.

The official table distinguishes Docente and Investigador from general
non-academic recruitment and exposes the application closing date and notice
links. Only those two categories are retained.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..http import fetch
from ..models import Offer

log = logging.getLogger(__name__)

LIST_URL = "https://www.ualg.pt/procedimentos-concursais"
UALG_HOSTS = {"www.ualg.pt", "ualg.pt"}
DATE_DMY = re.compile(r"(?<!\d)(\d{1,2})[-./](\d{1,2})[-./](20\d{2})(?!\d)")
POSTS = re.compile(r"\b(\d{1,3})\s+(?:postos?|vagas?|lugares?)\b", re.I)
ACADEMIC_CATEGORIES = {"docente", "investigador"}


def _clean(text: str) -> str:
    return " ".join(text.split())


def _official_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]
    return (
        parsed.scheme in {"http", "https"}
        and any(host == domain or host.endswith("." + domain) for domain in UALG_HOSTS)
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


def _posts(title: str) -> int:
    match = POSTS.search(title)
    return max(1, int(match.group(1))) if match else 1


def _cell_category(cells, title_index: int) -> str:
    # Category sits before the designation in the published table. Match an
    # exact cell value so "docente" in a notice title cannot qualify a row.
    for cell in cells[:title_index]:
        value = _clean(cell.get_text(" ", strip=True)).casefold()
        if value in ACADEMIC_CATEGORIES:
            return value.title()
    return ""


def parse_listing(html: str, base_url: str = LIST_URL) -> list[Offer]:
    """Parse the UAlg open-procedures table without retaining finished rows."""
    soup = BeautifulSoup(html, "html.parser")
    offers: list[Offer] = []
    seen: set[str] = set()

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) < 6 or any(cell.name == "th" for cell in cells):
                continue

            # The designation link is substantially longer than the document
            # link (usually just "Edital n.º …"). Select the longest linked cell.
            linked_cells = []
            for index, cell in enumerate(cells):
                anchor = cell.find("a", href=True)
                if anchor:
                    anchor_text = _clean(anchor.get_text(" ", strip=True))
                    if anchor_text:
                        linked_cells.append((len(anchor_text), index, anchor, anchor_text))
            if not linked_cells:
                continue
            _, title_index, title_link, title = max(linked_cells, key=lambda item: item[0])
            category = _cell_category(cells, title_index)
            if not category:
                continue

            detail_url = urljoin(base_url, title_link["href"])
            if not _official_url(detail_url) or detail_url in seen:
                continue

            # The listing contains both the start and end dates. The last valid
            # date after the designation is the closing date, not the opening.
            dates = [
                _iso_date(cell.get_text(" ", strip=True))
                for cell in cells[title_index + 1:]
            ]
            dates = [value for value in dates if value]
            deadline = dates[-1] if len(dates) >= 2 else None

            row_text = _clean(row.get_text(" ", strip=True)).casefold()
            state = next((value for value in (
                "Em fase de candidatura", "A decorrer", "Aberto", "Terminado",
                "Encerrado", "Concluído",
            ) if value.casefold() in row_text), "")

            # A row marked as finished is never promoted to an open opportunity,
            # even if a stale or malformed date cell suggests otherwise.
            if state.casefold() in {"terminado", "encerrado", "concluído"}:
                continue

            reference = _clean(cells[0].get_text(" ", strip=True))
            code = _clean(cells[1].get_text(" ", strip=True)) if len(cells) > 1 else ""
            document_url = ""
            for index, cell in enumerate(cells):
                if index == title_index:
                    continue
                link = cell.find("a", href=True)
                if link and _clean(link.get_text(" ", strip=True)):
                    candidate = urljoin(base_url, link["href"])
                    if _official_url(candidate):
                        document_url = candidate
                        break

            notes = []
            if reference:
                notes.append(f"Referência: {reference}")
            if code:
                notes.append(f"Código: {code}")
            if state:
                notes.append(f"Estado na listagem: {state}")
            if not deadline:
                notes.append("Prazo não identificado na listagem; confirmar no aviso original.")

            seen.add(detail_url)
            offers.append(Offer(
                source="ualg", kind="position", title=title, url=detail_url,
                institution="Universidade do Algarve", region="Algarve",
                position_type=category, deadline=deadline,
                n_posts=_posts(title), notes=" ".join(notes),
                extra={
                    "ualg_reference": reference or None,
                    "ualg_code": code or None,
                    "ualg_state": state or None,
                    "ualg_document_url": document_url or None,
                },
            ))
    return offers


def scrape(today: dt.date | None = None) -> list[Offer]:
    """Collect open teaching and researcher recruitment from the UAlg index."""
    today = today or dt.date.today()
    offers = parse_listing(fetch(LIST_URL))
    current = [
        offer for offer in offers
        if not offer.deadline or offer.deadline >= today.isoformat()
    ]
    log.info("Universidade do Algarve: %d current academic/research procedures", len(current))
    return current

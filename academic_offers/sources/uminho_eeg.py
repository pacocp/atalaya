"""Universidade do Minho EEG academic recruitment index.

This adapter covers only the School of Economics, Management and Political
Science (EEG), not the whole University of Minho. It reads the public section
for teaching and research staff and excludes the separate technical/admin
recruitment section.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..dates import first_date
from ..http import fetch
from ..models import Offer

log = logging.getLogger(__name__)

LIST_URL = "https://www.eeg.uminho.pt/pt/escola/Paginas/procedimentos-concursais.aspx"
ACADEMIC_SECTION = "procedimentos concursais - pessoal docente e pessoal investigador"
TECHNICAL_SECTION = "procedimentos concursais - pessoal técnico"
OPEN_LABEL = "posições em aberto"
CLOSED_LABEL = "posições encerradas"
NOTICE_RE = re.compile(r"\bedital\s*(?:n\.?\s*[º°o]\s*)?(\d{1,5}/20\d{2})", re.I)
DEADLINE_RE = re.compile(r"prazo de candidatura(?:\s+termina)?\s*[:：]?", re.I)
POSTS_RE = re.compile(r"\b(\d{1,3})\s+(?:postos?|vagas?|lugares?)\b", re.I)
OFFICIAL_HOSTS = ("uminho.pt", "diariodarepublica.pt", "dre.pt")


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


def _find_index(strings: list[str], phrase: str, start: int = 0) -> int | None:
    wanted = _normal(phrase)
    for index in range(start, len(strings)):
        if _normal(strings[index]) == wanted:
            return index
    return None


def _tag_index(tag, strings: list[str], start: int = 0) -> int | None:
    """Find the first visible text node belonging to a tag in document order."""
    own_strings = {_normal(value) for value in tag.stripped_strings if _normal(value)}
    for index in range(start, len(strings)):
        if _normal(strings[index]) in own_strings:
            return index
    return None


def _deadline(text: str) -> str | None:
    for label in DEADLINE_RE.finditer(text):
        value = first_date(text[label.end():label.end() + 120])
        if value:
            return value
    return None


def parse_listing(html: str, base_url: str = LIST_URL) -> list[Offer]:
    """Parse only open teaching/research opportunities from the EEG section."""
    soup = BeautifulSoup(html, "html.parser")
    strings = [_clean(value) for value in soup.stripped_strings]

    section_start = _find_index(strings, "Procedimentos Concursais - Pessoal Docente e Pessoal Investigador")
    if section_start is None:
        return []

    open_index = _find_index(strings, OPEN_LABEL, section_start + 1)
    if open_index is None:
        return []

    boundaries = [
        index for index in (
            _find_index(strings, CLOSED_LABEL, open_index + 1),
            _find_index(strings, "Procedimentos Concursais - Pessoal Técnico, Administrativo e de Gestão", open_index + 1),
        )
        if index is not None
    ]
    section_end = min(boundaries) if boundaries else len(strings)
    if section_end <= open_index + 1:
        return []

    headings = []
    for heading in soup.find_all("h4"):
        position = _tag_index(heading, strings, open_index + 1)
        if position is not None and open_index < position < section_end:
            headings.append((position, heading))
    headings.sort(key=lambda item: item[0])

    offers: list[Offer] = []
    seen: set[str] = set()
    for heading_number, (heading_index, heading) in enumerate(headings):
        title = _clean(heading.get_text(" ", strip=True))
        if not title:
            continue

        next_heading_index = (
            headings[heading_number + 1][0]
            if heading_number + 1 < len(headings)
            else section_end
        )
        block_text = " ".join(strings[heading_index + 1:next_heading_index])
        if not re.search(r"\baberto\b", block_text, re.I) or re.search(r"\bencerrado\b", block_text, re.I):
            continue

        notice_match = NOTICE_RE.search(block_text)
        notice = notice_match.group(1) if notice_match else ""
        deadline = _deadline(block_text)
        n_posts_match = POSTS_RE.search(block_text)
        n_posts = max(1, int(n_posts_match.group(1))) if n_posts_match else 1

        notice_url = ""
        for link in soup.find_all("a", href=True):
            link_index = _tag_index(link, strings, heading_index + 1)
            if link_index is None or not (heading_index < link_index < next_heading_index):
                continue
            link_text = _clean(link.get_text(" ", strip=True))
            if not re.search(r"\bedital\b", link_text, re.I):
                continue
            candidate = urljoin(base_url, link["href"])
            if _official_url(candidate):
                notice_url = candidate
                break

        if not notice_url or notice_url in seen:
            continue
        seen.add(notice_url)

        notes = []
        if notice:
            notes.append(f"Edital n.º {notice}")
        if not deadline:
            notes.append("Prazo não identificado na listagem; confirmar no edital original.")

        offers.append(Offer(
            source="uminho-eeg",
            kind="position",
            title=title,
            url=notice_url,
            institution="Universidade do Minho — Escola de Economia, Gestão e Ciência Política",
            region="Braga",
            position_type="Pessoal docente/investigador",
            deadline=deadline,
            n_posts=n_posts,
            notes=" ".join(notes),
            extra={
                "uminho_eeg_notice": notice or None,
                "uminho_eeg_scope": "Escola de Economia, Gestão e Ciência Política",
                "listing_url": base_url,
            },
        ))

    return offers


def scrape(today: dt.date | None = None) -> list[Offer]:
    """Collect current academic opportunities from the EEG open-positions section."""
    today = today or dt.date.today()
    offers = parse_listing(fetch(LIST_URL))
    current = [
        offer for offer in offers
        if not offer.deadline or offer.deadline >= today.isoformat()
    ]
    log.info("UMinho EEG: %d open teaching/research entries", len(current))
    return current

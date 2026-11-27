"""NOVA FCT researcher recruitment index.

This adapter covers the public researcher-concourse page of NOVA FCT only.
It does not claim coverage of teaching or non-academic recruitment at the
Faculty or across the wider Universidade NOVA de Lisboa.
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

LIST_URL = "https://www.fct.unl.pt/faculdade/concursos/investigadores"
OFFICIAL_HOSTS = ("fct.unl.pt",)
NOTICE_RE = re.compile(
    r"aviso\s*\(extrato\)\s*n\.?\s*[º°o]?\s*([0-9][0-9./-]*)",
    re.I,
)
DEADLINE_LABEL_RE = re.compile(r"candidaturas?\s+abertas?\s+at[eé]\s*", re.I)
DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](20\d{2})(?!\d)")
POSITION_RE = re.compile(
    r"\b(Investigador(?:a|/a)?\s+(?:J[uú]nior|Auxiliar|Principal|Coordenador(?:a)?)"
    r"|Assistente\s+de\s+Investiga[cç][ãa]o|Investigador(?:a|/a)?)\b",
    re.I,
)
AREA_RE = re.compile(r"\b[áa]rea\s+(?:cient[ií]fica\s+)?(?:de\s+)?([^,.;]+)", re.I)
POSTS_RE = re.compile(
    r"\brecrutamento\s+de\s+(\d{1,3})\b|\b(\d{1,3})\s+(?:postos?|vagas?|lugares?)\b",
    re.I,
)
INTERNAL_REF_RE = re.compile(
    r"refer[eê]ncia\s+interna\s+[“\"']?([A-Z0-9][A-Z0-9._/-]+)",
    re.I,
)


def _clean(value: str) -> str:
    return " ".join(value.split())


def _official_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]
    return (
        parsed.scheme in {"http", "https"}
        and any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_HOSTS)
    )


def _deadline(text: str) -> str | None:
    label = DEADLINE_LABEL_RE.search(text)
    if not label:
        return None
    match = DATE_RE.search(text[label.end():label.end() + 100])
    if not match:
        return None
    day, month, year = (int(value) for value in match.groups())
    try:
        return dt.date(year, month, day).isoformat()
    except ValueError:
        return None


def _notice_block(link):
    """Find the smallest ancestor containing one notice and its surrounding text."""
    parent = link.parent
    for _ in range(12):
        if parent is None:
            break
        text = _clean(parent.get_text(" ", strip=True))
        notice_links = [
            anchor for anchor in parent.find_all("a", href=True)
            if NOTICE_RE.search(_clean(anchor.get_text(" ", strip=True)))
        ]
        unique_urls = {urljoin(LIST_URL, anchor["href"]) for anchor in notice_links}
        if len(unique_urls) == 1 and (
            DEADLINE_LABEL_RE.search(text)
            or len(text) > len(_clean(link.get_text(" ", strip=True))) + 20
        ):
            return parent
        parent = parent.parent
    return None


def parse_listing(html: str, base_url: str = LIST_URL) -> list[Offer]:
    """Parse researcher notices from the NOVA FCT official listing page."""
    soup = BeautifulSoup(html, "html.parser")
    offers: list[Offer] = []
    seen: set[str] = set()
    unparsed_official_notices = 0

    for link in soup.find_all("a", href=True):
        link_text = _clean(link.get_text(" ", strip=True))
        notice_match = NOTICE_RE.search(link_text)
        if not notice_match:
            continue

        notice_url = urljoin(base_url, link["href"])
        if not _official_url(notice_url) or notice_url in seen:
            continue

        block = _notice_block(link)
        if block is None:
            unparsed_official_notices += 1
            continue

        block_text = _clean(block.get_text(" ", strip=True))
        deadline = _deadline(block_text)
        paragraphs = [
            _clean(paragraph.get_text(" ", strip=True))
            for paragraph in block.find_all("p")
        ]
        summary_text = next(
            (
                value for value in paragraphs
                if re.search(r"recrutamento\s+de|contrata[cç][ãa]o\s+de", value, re.I)
            ),
            "",
        )
        detail_text = summary_text or block_text
        position_match = POSITION_RE.search(detail_text) or POSITION_RE.search(link_text)
        position_type = _clean(position_match.group(1)) if position_match else "Investigador"
        area_match = AREA_RE.search(detail_text)
        area = _clean(area_match.group(1)) if area_match else ""
        title = f"{position_type} — {area}" if area else link_text

        posts_match = POSTS_RE.search(detail_text)
        posts_value = (
            next((value for value in posts_match.groups() if value), None)
            if posts_match else None
        )
        n_posts = max(1, int(posts_value)) if posts_value else 1

        internal_match = INTERNAL_REF_RE.search(block_text)
        internal_ref = internal_match.group(1).rstrip(".,;:") if internal_match else ""

        notes = [f"Aviso (extrato) n.º {notice_match.group(1)}"]
        if internal_ref:
            notes.append(f"Referência interna: {internal_ref}")
        if not deadline:
            notes.append("Prazo não identificado na listagem; confirmar no aviso original.")

        seen.add(notice_url)
        offers.append(Offer(
            source="novafct-investigadores",
            kind="position",
            title=title,
            url=notice_url,
            institution="NOVA FCT — Faculdade de Ciências e Tecnologia",
            region="Lisboa",
            position_type=position_type,
            deadline=deadline,
            n_posts=n_posts,
            notes=" ".join(notes),
            extra={
                "novafct_notice": notice_match.group(1),
                "novafct_internal_reference": internal_ref or None,
                "novafct_area": area or None,
                "listing_url": base_url,
            },
        ))

    if unparsed_official_notices:
        raise RuntimeError(
            f"{unparsed_official_notices} NOVA FCT notice link(s) could not be parsed; "
            "the listing structure may have changed"
        )
    return offers


def scrape(today: dt.date | None = None) -> list[Offer]:
    """Collect non-expired researcher recruitment notices from NOVA FCT."""
    today = today or dt.date.today()
    offers = parse_listing(fetch(LIST_URL))
    current = [
        offer for offer in offers
        if not offer.deadline or offer.deadline >= today.isoformat()
    ]
    log.info("NOVA FCT researchers: %d current recruitment notices", len(current))
    return current

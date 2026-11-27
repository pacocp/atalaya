"""Universidade de Coimbra UC Apply open academic procedures.

Only research scholarships, teaching and researcher recruitment types are kept.
The public open-status search is used as the index; individual public procedure
pages provide application periods and scientific areas where available.
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

LIST_URL = "https://www.apply.uc.pt/search?filters=public_status%3A%3D%3D%3Aopen"
UC_HOST = "www.apply.uc.pt"
MAX_DETAIL_PAGES = 40

ACADEMIC_CATEGORIES = (
    "Bolsas de Investigação",
    "Investigadores DL 57",
    "Investigadores",
    "Docentes",
)
CATEGORY_RE = re.compile(
    r"Bolsas de Investiga[cç][ãa]o|Investigadores\s+DL\s*57|Investigadores|Docentes",
    re.I,
)
CODE_RE = re.compile(r"\bIT\d{3}-\d{2}-\d+\b", re.I)
POSTS_RE = re.compile(r"\b(\d{1,3})\s+postos?\b", re.I)
DATE_TOKEN = re.compile(
    r"(?<!\d)(?:20\d{2}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-]20\d{2})(?!\d)"
)
APPLICATION_LABEL = re.compile(r"Candidaturas\b", re.I)


def _official_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme in {"http", "https"}
        and parsed.netloc.lower() == UC_HOST
        and parsed.path.startswith("/procedure/")
    )


def _iso_date(value: str) -> str | None:
    value = value.strip()
    try:
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", value):
            return dt.date.fromisoformat(value).isoformat()
        match = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](20\d{2})", value)
        if match:
            day, month, year = (int(part) for part in match.groups())
            return dt.date(year, month, day).isoformat()
    except ValueError:
        return None
    return None


def _deadline_from_text(text: str) -> str | None:
    """Read the end of an explicitly labelled application window, not its start date."""
    clean = " ".join(text.split())
    for label in APPLICATION_LABEL.finditer(clean):
        context = clean[label.end():label.end() + 120]
        # An opening date alone is not a deadline.
        if re.match(r"\s*(?:iniciam|inicia|começam|começa)\b", context, re.I):
            continue
        if not re.match(r"\s*(?:até|:|de\b|a\b|terminam|termina|encerram|encerra)?", context, re.I):
            continue
        dates = [(match.start(), match.group(0)) for match in DATE_TOKEN.finditer(context)]
        if not dates:
            continue
        first_value = _iso_date(dates[0][1])
        if not first_value:
            continue
        if len(dates) > 1:
            between = context[dates[0][0] + len(dates[0][1]):dates[1][0]]
            if re.search(r"\b(?:a|até|ao)\b|[-–—]", between, re.I):
                second_value = _iso_date(dates[1][1])
                if second_value:
                    return second_value
        # A single date is safe only when the text says "até" / "termina".
        if re.match(r"\s*(?:até|terminam|termina|encerra|encerram)\b", context, re.I):
            return first_value
    return None


def _card_for_link(link):
    card = link
    for _ in range(7):
        parent = card.parent
        if parent is None or parent.name in {"main", "body", "html", "[document]"}:
            break
        card = parent
        classes = " ".join(card.get("class", []))
        if card.name in {"article", "li"} or re.search(
            r"\b(card|procedure|result|search-item|item)\b", classes, re.I
        ):
            break
    return card


def _display_title(link_text: str, card_text: str, category: str, code: str) -> str:
    """Remove card metadata from the visible title while preserving the original wording."""
    candidate = link_text
    if code and code in candidate:
        candidate = candidate.split(code, 1)[1]
    elif code and code in card_text:
        candidate = card_text.split(code, 1)[1]
    candidate = re.split(r"\bUniversidade de Coimbra\b|\bCandidaturas\b", candidate, maxsplit=1, flags=re.I)[0]
    candidate = POSTS_RE.sub("", candidate)
    candidate = " ".join(candidate.strip(" -–—|·:").split())
    if not candidate or candidate.casefold() in {"ver mais", "consultar", "saber mais"}:
        candidate = link_text
    if not candidate:
        candidate = card_text
    if category.casefold() not in candidate.casefold():
        return f"{category} — {candidate}"
    return candidate


def parse_listing(html: str, base_url: str = LIST_URL) -> list[Offer]:
    """Parse the public open-procedure search page."""
    soup = BeautifulSoup(html, "html.parser")
    offers: list[Offer] = []
    seen: set[str] = set()

    for link in soup.select('a[href*="/procedure/"]'):
        url = urljoin(base_url, link["href"])
        if not _official_url(url) or url in seen:
            continue
        card = _card_for_link(link)
        card_text = " ".join(card.get_text(" ", strip=True).split())
        title_text = " ".join(link.get_text(" ", strip=True).split())
        # Card content can be wrapped in the link itself; use the combined card
        # text to identify category and metadata but preserve a concise link title.
        category_match = CATEGORY_RE.search(card_text)
        if not category_match:
            continue
        category = category_match.group(0)
        if not any(category.casefold() == allowed.casefold() for allowed in ACADEMIC_CATEGORIES):
            continue

        code_match = CODE_RE.search(card_text)
        code = code_match.group(0).upper() if code_match else ""
        posts_match = POSTS_RE.search(card_text)
        n_posts = max(1, int(posts_match.group(1))) if posts_match else 1
        deadline = _deadline_from_text(card_text)

        title = _display_title(title_text, card_text, category, code)

        seen.add(url)
        is_scholarship = category.casefold().startswith("bolsas")
        notes = []
        if code:
            notes.append(f"Código: {code}")
        if not deadline:
            notes.append("Prazo não identificado na listagem; confirmar no procedimento original.")
        offers.append(Offer(
            source="uc-apply",
            kind="call" if is_scholarship else "position",
            title=title,
            url=url,
            institution="Universidade de Coimbra",
            region="Coimbra",
            position_type=category,
            deadline=deadline,
            n_posts=n_posts,
            notes=" ".join(notes),
            extra={"uc_apply_code": code or None},
        ))
    return offers


def _label_value(soup: BeautifulSoup, labels: set[str]) -> str:
    wanted = {label.casefold() for label in labels}
    for node in soup.find_all(["dt", "th", "strong", "b", "label"]):
        label = " ".join(node.get_text(" ", strip=True).split()).casefold().rstrip(":")
        if label not in wanted:
            continue
        siblings = ["dd"] if node.name == "dt" else ["td"] if node.name == "th" else []
        value_node = node.find_next_sibling(siblings) if siblings else None
        if value_node:
            value = " ".join(value_node.get_text(" ", strip=True).split())
            if value:
                return value
    return ""


def parse_detail_page(html: str) -> dict[str, str | None]:
    """Extract the application deadline and scientific area from a UC Apply procedure."""
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "nav", "footer"]):
        node.decompose()
    body = " ".join(soup.get_text(" ", strip=True).split())
    publication = _label_value(soup, {"data de publicação", "data da publicação"})
    return {
        "deadline": _deadline_from_text(body),
        "published": _iso_date(publication) if publication else None,
        "area": _label_value(soup, {"área", "area"}) or None,
        "category": _label_value(soup, {"tipo de procedimento", "categoria"}) or None,
        "code": _label_value(soup, {"código do procedimento", "código"}) or None,
    }


def _enrich(offer: Offer) -> Offer:
    if not _official_url(offer.url):
        return offer
    try:
        details = parse_detail_page(fetch(offer.url))
    except Exception as exc:
        log.info("UC Apply detail unavailable for %s: %s", offer.url, exc)
        return offer
    if details["deadline"]:
        offer.deadline = str(details["deadline"])
    if details["area"]:
        offer.area_raw = str(details["area"])
    if details["published"]:
        offer.published = str(details["published"])
    if details["category"]:
        offer.position_type = str(details["category"])
    if details["code"]:
        offer.extra["uc_apply_code"] = str(details["code"])
    offer.extra["detail_enriched"] = True
    return offer


def scrape(today: dt.date | None = None) -> list[Offer]:
    """Collect open UC Apply procedures, enriched from their public detail pages."""
    today = today or dt.date.today()
    offers = parse_listing(fetch(LIST_URL))
    for offer in offers[:MAX_DETAIL_PAGES]:
        _enrich(offer)
    current = [
        offer for offer in offers
        if not offer.deadline or offer.deadline >= today.isoformat()
    ]
    log.info("UC Apply: %d open academic procedures (%d detail pages attempted)",
             len(current), min(len(offers), MAX_DETAIL_PAGES))
    return current

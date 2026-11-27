"""Fundação para a Ciência e a Tecnologia (FCT): open calls index and detail pages.

Only the official public "open" tab and same-domain detail pages are consumed.
Deadlines are stored only when a complete date is explicitly associated with a
submission/closing label. The public listing is an index; the original notice
remains the authoritative record.
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

FCT_OPEN = "https://www.fct.pt/concursos/?paged=1&tab=open"
FCT_HOSTS = {"www.fct.pt", "fct.pt"}
MAX_LIST_PAGES = 5
MAX_DETAIL_PAGES = 40

DATE_DMY = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](20\d{2})(?!\d)")
DATE_ISO = re.compile(r"(?<!\d)(20\d{2})-(\d{2})-(\d{2})(?!\d)")
PT_MONTHS = {
    "janeiro": 1, "jan": 1, "fevereiro": 2, "fev": 2,
    "março": 3, "marco": 3, "mar": 3,
    "abril": 4, "abr": 4, "maio": 5, "mai": 5,
    "junho": 6, "jun": 6, "julho": 7, "jul": 7,
    "agosto": 8, "ago": 8, "setembro": 9, "set": 9,
    "outubro": 10, "out": 10, "novembro": 11, "nov": 11,
    "dezembro": 12, "dez": 12,
}
MONTH_PATTERN = "|".join(sorted(PT_MONTHS, key=len, reverse=True))
DATE_PT = re.compile(
    rf"(?<!\d)(\d{{1,2}})\s+(?:de\s+)?({MONTH_PATTERN})\.?(?:\s+de)?\s+(20\d{{2}})(?!\d)",
    re.I,
)

# Labels which identify the closing side of the application window. "Abertura"
# and publication dates are deliberately absent.
DEADLINE_LABEL = re.compile(
    r"data\s+limite|prazo(?:\s+(?:final|de|para))?\s+"
    r"(?:candidaturas?|apresenta[cç][ãa]o|submiss[aã]o)|"
    r"submiss[aã]o\s+de\s+candidaturas|"
    r"per[ií]odo\s+(?:de\s+)?candidaturas?|"
    r"datas?\s+de\s+submiss[aã]o|"
    r"encerramento\s+(?:das?|de)\s+candidaturas?|"
    r"fecho\s+(?:das?|de)\s+candidaturas?|"
    r"candidaturas?\s+at[eé]|fim\s+do\s+prazo",
    re.I,
)

FUNDING_TYPES = (
    (re.compile(r"emprego\s+cient[ií]fico|fct[- ]?tenure|contrata[cç][ãa]o\s+de\s+investigadores", re.I),
     "Emprego científico"),
    (re.compile(r"bolsa(?:s)?(?:\s+de\s+investiga[cç][ãa]o|\s+de\s+doutoramento)?", re.I),
     "Bolsas"),
    (re.compile(r"infraestruturas?|computa[cç][ãa]o\s+avan[cç]ada", re.I), "Infraestruturas"),
    (re.compile(r"(?:projetos?|projectos?)(?:\s+(?:de\s+)?i\s*&\s*d|\s+de\s+investiga[cç][ãa]o|\s+explorat[oó]rios|\s+icdt)?", re.I),
     "Projetos I&D"),
    (re.compile(r"institui[cç][õo]es?\s+i\s*&\s*d", re.I), "Instituições I&D"),
    (re.compile(r"pr[eé]mios?", re.I), "Prémios"),
    (re.compile(r"internacional|parceria\s+europeia|coopera[cç][ãa]o\s+bilateral", re.I), "Internacional"),
)
OTHER_FUNDING_TYPES = {"outros", "other"}

SCIENTIFIC_DOMAINS = (
    "Ciências Agrárias",
    "Ciências da Engenharia e Tecnologias",
    "Ciências Exatas",
    "Humanidades",
    "Ciências Médicas e da Saúde",
    "Ciências Naturais",
    "Ciências Sociais",
)


def _normalise_text(value: str) -> str:
    return " ".join(value.split()).strip(" :：")


def _date_values(text: str) -> list[tuple[int, int, dt.date]]:
    """Return date tokens with their offsets, ignoring impossible calendar dates."""
    found: list[tuple[int, int, dt.date]] = []
    for pattern, order in ((DATE_DMY, "dmy"), (DATE_ISO, "iso"), (DATE_PT, "pt")):
        for match in pattern.finditer(text):
            try:
                if order == "dmy":
                    day, month, year = (int(value) for value in match.groups())
                elif order == "iso":
                    year, month, day = (int(value) for value in match.groups())
                else:
                    day, month, year = int(match.group(1)), PT_MONTHS[match.group(2).lower()], int(match.group(3))
                found.append((match.start(), match.end(), dt.date(year, month, day)))
            except (TypeError, ValueError):
                continue
    # Patterns do not normally overlap, but keep one value per date offset.
    unique: dict[tuple[int, int, str], dt.date] = {}
    for start, end, value in found:
        unique[(start, end, value.isoformat())] = value
    return sorted((start, end, value) for (start, end, _), value in unique.items())


def _deadline(text: str) -> str | None:
    """Extract a full date only from a small context around an explicit closing label."""
    for label in DEADLINE_LABEL.finditer(text):
        left = max(0, label.start() - 100)
        right = min(len(text), label.end() + 140)
        context = text[left:right]
        candidates = _date_values(context)
        if not candidates:
            continue
        label_start = label.start() - left
        label_end = label.end() - left
        after = [(start, end, value) for start, end, value in candidates if start >= label_end]
        before = [(start, end, value) for start, end, value in candidates if end <= label_start]
        label_text = label.group(0).casefold()
        is_submission_period = (
            "submissão" in label_text or "apresentação" in label_text or "período" in label_text
            or ("prazo" in label_text and "candidatur" in label_text)
        )
        if after:
            # Submission labels may precede a start/end range. Use its second
            # date only when a range connector sits between the first two dates;
            # otherwise take the nearest date and avoid unrelated result dates.
            after.sort(key=lambda item: item[0])
            selected = after[0][2]
            if is_submission_period and len(after) > 1:
                between = context[after[0][1]:after[1][0]]
                if re.search(r"\b(?:a|até|ao|to)\b|[-–—]", between, re.I):
                    selected = after[1][2]
            return selected.isoformat()
        if before:
            # Some FCT pages place the closing date immediately before its label.
            return max(before, key=lambda item: item[0])[2].isoformat()
    return None


def _label_value(soup: BeautifulSoup, labels: set[str]) -> str:
    """Read values only from explicit label/value structures (dt/dd, th/td, etc.)."""
    wanted = {label.casefold() for label in labels}
    for node in soup.find_all(["dt", "th", "strong", "b", "label"]):
        label = _normalise_text(node.get_text(" ", strip=True)).casefold()
        if label not in wanted:
            continue
        sibling_names = ["dd"] if node.name == "dt" else ["td"] if node.name == "th" else []
        value_node = node.find_next_sibling(sibling_names) if sibling_names else None
        if value_node:
            value = _normalise_text(value_node.get_text(" ", strip=True))
            if value:
                return value
        # A bold label is sometimes followed by plain text in the same paragraph.
        pieces: list[str] = []
        for sibling in node.next_siblings:
            if getattr(sibling, "name", None) in {"strong", "b", "dt", "th"}:
                break
            value = sibling.get_text(" ", strip=True) if getattr(sibling, "get_text", None) else str(sibling)
            if value.strip():
                pieces.append(value.strip())
        if pieces:
            return _normalise_text(" ".join(pieces))
    return ""


def _funding_type(title: str, labelled_value: str = "") -> str:
    # An explicit taxonomy field is more reliable than clues in a title.
    if labelled_value:
        value = labelled_value.casefold()
        for pattern, category in FUNDING_TYPES:
            if pattern.search(labelled_value):
                return category
        if value in OTHER_FUNDING_TYPES:
            return "Outros"
    for pattern, category in FUNDING_TYPES:
        if pattern.search(title):
            return category
    return ""


def _scientific_domain(labelled_value: str) -> str:
    value = labelled_value.casefold()
    for domain in SCIENTIFIC_DOMAINS:
        if domain.casefold() in value:
            return domain
    if "todos os domínios científicos" in value:
        return "Todos os domínios científicos"
    return ""


def parse_detail_page(html: str, title: str = "") -> dict[str, str | None]:
    """Extract explicit metadata from an individual FCT call page."""
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "nav", "footer"]):
        node.decompose()
    body = " ".join(soup.get_text(" ", strip=True).split())
    funding_label = _label_value(soup, {"tipo de financiamento", "tipo de apoio", "tipologia de financiamento"})
    domain_label = _label_value(soup, {"domínio científico", "domínios científicos", "área científica"})
    return {
        "deadline": _deadline(body),
        "funding_type": _funding_type(title, funding_label) or None,
        "scientific_domain": _scientific_domain(domain_label) or None,
    }


def _same_fct_host(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme in {"http", "https"}
        and parsed.netloc.lower() in FCT_HOSTS
    )


def parse_open_listing(html: str, base_url: str = FCT_OPEN) -> list[Offer]:
    """Parse opportunity links from the official open-calls tab."""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    offers: list[Offer] = []
    seen: set[str] = set()

    for a in main.select("a[href]"):
        title = _normalise_text(a.get_text(" ", strip=True))
        if len(title) < 12:
            continue
        url = urljoin(base_url, a["href"])
        if not _same_fct_host(url):
            continue
        if url.rstrip("/") in {"https://www.fct.pt/concursos", "https://fct.pt/concursos"}:
            continue
        if url in seen:
            continue

        # Read the closest card-like ancestor only. Never climb to the document
        # root: doing so would let another call elsewhere on the page make a
        # navigation/footer link look relevant.
        card = a
        for _ in range(6):
            parent = card.parent
            if parent is None or parent.name in {"main", "body", "html", "[document]"}:
                break
            card = parent
            classes = " ".join(card.get("class", []))
            if card.name in {"article", "li"} or re.search(
                r"\b(card|item|call|contest|opportunit|entry)\b", classes, re.I
            ):
                break
        card_text = _normalise_text(card.get_text(" ", strip=True)) or title
        if not re.search(r"\b(data limite|candidaturas|concurso|bolsa|emprego científico|investiga)", card_text, re.I):
            continue

        seen.add(url)
        offers.append(Offer(
            source="fct", kind="call", title=title, url=url,
            institution="Fundação para a Ciência e a Tecnologia",
            region="Portugal", position_type="Concurso de financiamento",
            deadline=_deadline(card_text),
            notes="Concurso listado no separador oficial de concursos abertos da FCT. "
                  "Confirma elegibilidade, calendário e condições no aviso original.",
        ))
    return offers


def _enrich_offer(offer: Offer) -> Offer:
    """Enrich an index record from its official FCT detail page, failing safely."""
    if not _same_fct_host(offer.url):
        return offer
    try:
        details = parse_detail_page(fetch(offer.url), offer.title)
    except Exception as exc:
        log.info("FCT detail page unavailable for %s: %s", offer.url, exc)
        return offer

    if details["deadline"]:
        offer.deadline = str(details["deadline"])
        offer.deadline_estimated = False
    if details["funding_type"]:
        offer.extra["fct_funding_type"] = str(details["funding_type"])
    if details["scientific_domain"]:
        offer.area_raw = str(details["scientific_domain"])
        offer.extra["fct_scientific_domain"] = str(details["scientific_domain"])
    offer.extra["detail_enriched"] = True
    return offer


def scrape(today: dt.date | None = None) -> list[Offer]:
    offers: list[Offer] = []
    seen: set[str] = set()
    for page in range(1, MAX_LIST_PAGES + 1):
        page_url = FCT_OPEN.replace("paged=1", "paged=" + str(page))
        page_offers = parse_open_listing(fetch(page_url), page_url)
        if not page_offers:
            break
        for offer in page_offers:
            if offer.url not in seen:
                seen.add(offer.url)
                offers.append(offer)

    # Bound detail requests and preserve the index record if any page is blocked,
    # unavailable, or changes layout. The shared HTTP client enforces robots.txt,
    # caching and per-host delays.
    for offer in offers[:MAX_DETAIL_PAGES]:
        _enrich_offer(offer)
    log.info("FCT open calls: %d candidate records (%d detail pages attempted)",
             len(offers), min(len(offers), MAX_DETAIL_PAGES))
    return offers

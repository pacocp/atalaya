"""Diário da República (Portugal): second-series official RSS index.

The feed URL is published by the Diário da República RSS subscription page.
Only public RSS items are consumed. We keep the original act URL and do not
attempt to access private APIs or bypass access controls.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import logging
import re
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from ..http import fetch
from ..models import Offer

log = logging.getLogger(__name__)

# Official "2.ª Série — Todas as partes — HTML" RSS link, as listed on the DR RSS page.
# RSS is used as an index only; the original notice remains the authoritative record.
RSS_URL = "https://files.diariodarepublica.pt/rss/serie2-html.xml"

# RSS titles are often generic ("Aviso (extrato) n.º …"). Search the
# publisher's Sumário as well, but require a clear academic/research signal;
# generic administrative recruitment is not sufficient.
ACADEMIC_NOTICE = re.compile(
    r"professor(?:a|es|as)?|pessoal docente|docente|"
    r"investigador(?:a|es|as)?|carreira de investiga[cç][ãa]o|"
    r"emprego cient[ií]fico|bolsa(?:s)? de investiga[cç][ãa]o|"
    r"investigador(?:es)? doutorado|doutoramento|p[oó]s[- ]?doutor",
    re.I,
)
# Drop outcomes and procedural follow-ups that are not new opportunities.
NOT_NEW = re.compile(
    r"lista (?:unit[aá]ria|de ordena[cç][ãa]o)|homologa[cç][ãa]o|"
    r"projeto de lista|lista provis[oó]ria|lista definitiva|"
    r"resultados?|candidato(?:s|as)? admitido|exclus[aã]o|"
    r"anula[cç][ãa]o|retifica[cç][ãa]o|cessa[cç][ãa]o",
    re.I,
)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(item: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in item.iter():
        if _local_name(child.tag) in wanted and child.text:
            return " ".join(child.text.split())
    return ""


def _published(value: str) -> str | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return parsed.date().isoformat()
    except (TypeError, ValueError, OverflowError):
        try:
            # Atom feeds commonly use ISO 8601 timestamps rather than RFC 2822.
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except (TypeError, ValueError, OverflowError):
            return None


def parse_feed(xml_text: str, today: dt.date | None = None) -> list[Offer]:
    """Parse RSS/Atom items, keeping likely new academic/research recruitment notices."""
    today = today or dt.date.today()
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        log.exception("Invalid Diário da República RSS XML")
        return []

    offers: list[Offer] = []
    seen: set[str] = set()
    for item in root.iter():
        if _local_name(item.tag) not in {"item", "entry"}:
            continue
        title = _child_text(item, "title")
        description = _child_text(item, "description", "summary", "content", "encoded")
        description_text = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)
        summary_match = re.search(
            r"\bSum[aá]rio\s*:\s*(.*?)(?:\s+TEXTO\b|\s+Texto\b|$)",
            description_text, re.I,
        )
        summary = " ".join(summary_match.group(1).split()) if summary_match else description_text
        searchable = f"{title} {summary}"
        if (
            not title
            or not ACADEMIC_NOTICE.search(searchable)
            or NOT_NEW.search(title)
            or NOT_NEW.search(summary)
        ):
            continue

        # Atom links normally carry href in an attribute; RSS links carry text.
        url = ""
        for child in item.iter():
            if _local_name(child.tag) == "link":
                url = (child.attrib.get("href") or (child.text or "")).strip()
                if url:
                    break
        if not url:
            url = _child_text(item, "guid", "id")
        if not url.startswith(("https://", "http://")) or url in seen:
            continue
        seen.add(url)

        published = _published(_child_text(item, "pubdate", "published", "updated", "date"))
        display_title = summary or title
        if len(display_title) > 320:
            display_title = display_title[:317].rsplit(" ", 1)[0] + "…"
        is_scholarship = bool(re.search(r"bolsa(?:s)? de investiga[cç][ãa]o", searchable, re.I))
        position_type = "Bolsa de investigação" if is_scholarship else "Docência / investigação"
        offers.append(Offer(
            source="dr", kind="call" if is_scholarship else "position", title=display_title, url=url,
            institution="", region="Portugal",
            position_type=position_type,
            published=published,
            notes="Aviso identificado automaticamente no RSS da 2.ª Série. "
                  "Confirma requisitos, entidade, prazo e natureza do vínculo no anúncio original.",
            extra={"rss_description": description[:1500]} if description else {},
        ))
    return offers


def scrape(today: dt.date | None = None) -> list[Offer]:
    """Fetch the official second-series RSS index and parse relevant notices."""
    xml_text = fetch(RSS_URL)
    offers = parse_feed(xml_text, today)
    log.info("Diário da República RSS: %d possible recruitment notices", len(offers))
    return offers

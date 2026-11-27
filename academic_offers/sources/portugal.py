"""Experimental parser for Portuguese public-sector academic opportunities (not yet enabled).

The BEP homepage publishes a small, public list of recent offers. We deliberately
consume only that public listing and its linked detail pages; no login or
anti-bot circumvention is attempted. Broader search/API coverage is a later step.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http import fetch
from ..models import Offer

log = logging.getLogger(__name__)

BEP_HOME = "https://www.bep.gov.pt/Pages/Oferta/Oferta_Pesquisa_basica.aspx?d=noCookie"
RELEVANT = re.compile(
    r"docente universit|investiga[cç][ãa]o cient[ií]fica|bolseir|"
    r"investigador|ci[eê]ncia|ensino superior|universit[aá]ri",
    re.I,
)
DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _detail_url(href: str) -> str:
    return urljoin(BEP_HOME, href)


def scrape_bep(today: dt.date | None = None) -> list[Offer]:
    """Read the latest public BEP offers and retain academic/research-related rows."""
    soup = BeautifulSoup(fetch(BEP_HOME), "html.parser")
    offers: list[Offer] = []
    seen: set[str] = set()

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 4:
                continue
            row_text = " ".join(cell.get_text(" ", strip=True) for cell in cells)
            if not RELEVANT.search(row_text):
                continue

            link = row.find("a", href=True)
            if not link:
                continue
            url = _detail_url(link["href"])
            if "Oferta_Detalhes.aspx" not in url or url in seen:
                continue
            seen.add(url)

            code = next((c.get_text(" ", strip=True) for c in cells
                         if re.search(r"OE\d{6}/\d+", c.get_text(" ", strip=True))), "")
            title = " — ".join(c.get_text(" ", strip=True) for c in cells[:4])
            detail_text = ""
            try:
                detail = BeautifulSoup(fetch(url), "html.parser")
                detail_text = " ".join(detail.get_text(" ", strip=True).split())
                heading = detail.find(["h1", "h2"])
                if heading and len(heading.get_text(" ", strip=True)) > 8:
                    title = heading.get_text(" ", strip=True)
            except Exception:
                log.exception("BEP detail failed: %s", url)

            dates = DATE.findall(detail_text or row_text)
            deadline = dates[-1] if dates else None
            institution = cells[3].get_text(" ", strip=True) if len(cells) > 3 else ""
            career = cells[2].get_text(" ", strip=True) if len(cells) > 2 else ""
            offers.append(Offer(
                source="bep", kind="position", title=title, url=url,
                institution=institution, region="Portugal",
                position_type=career or "Oferta de emprego público",
                deadline=deadline, published=None,
                notes=f"Código BEP: {code}" if code else "",
                extra={"bep_code": code} if code else {},
            ))

    return offers

"""Find a deadline date in free text: dd/mm/yyyy, '3 de diciembre de 2026', 'December 3rd, 2026', '3rd December 2026'."""
from __future__ import annotations

import datetime as dt
import re

EN = "january february march april may june july august september october november december".split()
ES = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
PT = "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro".split()
MONTHS = {m: i for i, m in enumerate(EN, 1)} | {m: i for i, m in enumerate(ES, 1)} | {m: i for i, m in enumerate(PT, 1)} | {"setiembre": 9}
_M = "(" + "|".join(MONTHS) + ")"

PATTERNS = [
    (re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](20\d\d)\b"), lambda m: (m[3], m[2], m[1])),
    (re.compile(r"\b(\d{1,2})\s+de\s+" + _M + r"\s+(?:de\s+)?(20\d\d)", re.I), lambda m: (m[3], m[2], m[1])),
    (re.compile(r"\b(\d{1,2})\s*(?:st|nd|rd|th)?\s+" + _M + r",?\s+(20\d\d)", re.I), lambda m: (m[3], m[2], m[1])),
    (re.compile(_M + r"\s+(\d{1,2})\s*(?:st|nd|rd|th)?\s*,?\s+(20\d\d)", re.I), lambda m: (m[3], m[1], m[2])),
]


def _to_date(y: str, mo: str, d: str) -> dt.date | None:
    month = int(mo) if mo.isdigit() else MONTHS.get(mo.lower())
    try:
        return dt.date(int(y), month, int(d))
    except (TypeError, ValueError):
        return None


def first_date(text: str) -> str | None:
    """Earliest-positioned date in `text`, as ISO string."""
    best = None
    for pat, order in PATTERNS:
        m = pat.search(text)
        if m and (best is None or m.start() < best[0]):
            d = _to_date(*order(m))
            if d:
                best = (m.start(), d)
    return best[1].isoformat() if best else None


def date_after(text: str, keywords: str, window: int = 160) -> str | None:
    """The first date that follows any of the `keywords` (a regex), e.g. 'deadline|fin de la oferta'."""
    for m in re.finditer(keywords, text, re.I):
        d = first_date(text[m.end():m.end() + window])
        if d:
            return d
    return None

"""Active sources for the Portuguese Atalaia edition.

The original Spanish adapters remain in the repository as reusable code, but
are not scheduled by this edition. Only Portuguese national sources and
European funding calls are active here.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable

from ..models import Offer
from . import calls, dr, fct, uc_apply, ualg, ulisboa, uporto, uminho_eeg, novafct_investigadores, ubi_docentes


@dataclass
class Source:
    key: str
    name: str
    run: Callable[[dt.date, int], list[Offer]]
    may_be_empty: bool = False


SOURCES: list[Source] = [
    Source("dr", "Diário da República – 2.ª Série (RSS, avisos de recrutamento/investigação)",
           lambda today, _d: dr.scrape(today), may_be_empty=True),
    Source("fct", "FCT – concursos abertos (bolsas, emprego científico e projetos)",
           lambda today, _d: fct.scrape(today), may_be_empty=True),
    Source("ulisboa", "Universidade de Lisboa – recrutamento académico e científico",
           lambda today, _d: ulisboa.scrape(today), may_be_empty=True),
    Source("uporto", "Universidade do Porto – arquivo de oportunidades abertas",
           lambda today, _d: uporto.scrape(today), may_be_empty=True),
    Source("ualg", "Universidade do Algarve – procedimentos concursais (docentes e investigadores)",
           lambda today, _d: ualg.scrape(today), may_be_empty=True),
    Source("uc-apply", "Universidade de Coimbra – UC Apply (bolsas, docentes e investigadores)",
           lambda today, _d: uc_apply.scrape(today), may_be_empty=True),
    Source("uminho-eeg", "Universidade do Minho – Escola de Economia, Gestão e Ciência Política (docentes/investigadores)",
           lambda today, _d: uminho_eeg.scrape(today), may_be_empty=True),
    Source("novafct-investigadores", "NOVA FCT – concursos de investigadores (apenas pessoal investigador)",
           lambda today, _d: novafct_investigadores.scrape(today), may_be_empty=True),
    Source("ubi-docentes", "Universidade da Beira Interior – concursos para docentes",
           lambda today, _d: ubi_docentes.scrape(today), may_be_empty=True),
    Source("eu-ft", "EU Funding & Tenders – concursos ERC e MSCA",
           lambda today, _d: calls.eu_calls(today), may_be_empty=True),
]

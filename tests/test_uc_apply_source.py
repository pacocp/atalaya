"""Tests for the public UC Apply open-procedures source."""
import datetime as dt
import unittest
from unittest.mock import patch

from academic_offers.sources.uc_apply import (
    parse_detail_page, parse_listing, scrape, _deadline_from_text,
)
from academic_offers.classify import classify
from academic_offers.models import Offer


LISTING = """
<html><body><main>
  <article class="procedure-card">
    <a href="/procedure/abc123">Bolsas de Investigação 1 posto IT137-26-494 Engenharia Eletrotécnica e de Computadores Universidade de Coimbra Candidaturas até 2026-12-04</a>
  </article>
  <article class="procedure-card">
    <a href="/procedure/def456">Docentes 1 posto IT136-26-45 Professor Auxiliar Ciências Jurídico-Civilísticas Universidade de Coimbra Candidaturas até 2026-12-17</a>
  </article>
  <article class="procedure-card">
    <a href="/procedure/ghi789">Investigadores DL 57 1 posto IT057-26-42 Investigador de nível inicial Arqueologia Universidade de Coimbra Candidaturas iniciam a 27/11/2026</a>
  </article>
  <article class="procedure-card">
    <a href="/procedure/admin">Corpo Técnico 1 posto IT160-26-35 Assistente técnico Universidade de Coimbra Candidaturas até 2026-11-27</a>
  </article>
  <article class="procedure-card">
    <a href="/procedure/training">Bolsas de Estágio Curricular 1 posto Ciências Naturais Candidaturas até 2026-12-11</a>
  </article>
</main></body></html>
"""


class UCApplySourceTests(unittest.TestCase):
    def test_extracts_only_research_teaching_and_researcher_calls(self):
        offers = parse_listing(LISTING)
        self.assertEqual(len(offers), 3)
        self.assertEqual({offer.kind for offer in offers}, {"call", "position"})
        self.assertFalse(any("Corpo Técnico" in o.title for o in offers))
        self.assertFalse(any("Estágio Curricular" in o.title for o in offers))

    def test_extracts_listing_code_posts_and_deadline(self):
        offer = next(o for o in parse_listing(LISTING) if "Bolsas de Investigação" in o.title)
        self.assertEqual(offer.extra["uc_apply_code"], "IT137-26-494")
        self.assertEqual(offer.n_posts, 1)
        self.assertEqual(offer.deadline, "2026-12-04")
        self.assertEqual(offer.url, "https://www.apply.uc.pt/procedure/abc123")
        self.assertEqual(
            offer.title,
            "Bolsas de Investigação — Engenharia Eletrotécnica e de Computadores",
        )
        self.assertNotIn("Universidade de Coimbra", offer.title)

    def test_opening_date_is_not_used_as_a_deadline(self):
        offer = next(o for o in parse_listing(LISTING) if "Investigadores DL 57" in o.title)
        self.assertIsNone(offer.deadline)

    def test_application_range_uses_end_date(self):
        self.assertEqual(
            _deadline_from_text("Candidaturas 11/11/2026 a 24/11/2026"),
            "2026-11-24",
        )

    def test_date_parser_accepts_dot_and_hyphen_dmy(self):
        from academic_offers.sources.uc_apply import _iso_date
        self.assertEqual(_iso_date("24.11.2026"), "2026-11-24")
        self.assertEqual(_iso_date("24-11-2026"), "2026-11-24")

    def test_single_explicit_until_date_is_accepted(self):
        self.assertEqual(
            _deadline_from_text("Candidaturas até 2026-12-04"),
            "2026-12-04",
        )

    def test_detail_page_extracts_area_and_deadline(self):
        html = """
        <main>
          <h1>IT137-26-485</h1>
          <dl><dt>Data de publicação</dt><dd>09/11/2026</dd></dl>
          <p>Candidaturas 11/11/2026 a 24/11/2026</p>
          <dl><dt>Área</dt><dd>Engenharia Química, Engenharia de Materiais, Química</dd></dl>
          <dl><dt>Código do procedimento</dt><dd>IT137-26-485</dd></dl>
        </main>
        """
        details = parse_detail_page(html)
        self.assertEqual(details["deadline"], "2026-11-24")
        self.assertEqual(details["area"], "Engenharia Química, Engenharia de Materiais, Química")
        self.assertEqual(details["code"], "IT137-26-485")
        self.assertEqual(details["published"], "2026-11-09")

    def test_investigadores_dl57_get_distinct_career_stage(self):
        offer = Offer(
            source="uc-apply", kind="position",
            title="Investigadores DL 57 — Investigador de nível inicial Arqueologia",
            url="https://www.apply.uc.pt/procedure/abc123",
            position_type="Investigadores DL 57",
            area_raw="Arqueologia",
        )
        classified = classify(offer)
        self.assertEqual(classified.stage, "Researcher / DL 57")
        self.assertEqual(classified.field, "Humanities")

    def test_portuguese_legal_sciences_map_to_law(self):
        offer = Offer(
            source="uc-apply", kind="position",
            title="Docentes — Professor Auxiliar",
            url="https://www.apply.uc.pt/procedure/def456",
            area_raw="Ciências Jurídico-Civilísticas",
            position_type="Docentes",
        )
        classified = classify(offer)
        self.assertEqual(classified.field, "Social Sciences")
        self.assertEqual(classified.subfield, "Law")

    @patch("academic_offers.sources.uc_apply.fetch")
    def test_enrichment_keeps_listing_record_when_detail_fails(self, mock_fetch):
        from academic_offers.sources.uc_apply import _enrich
        from academic_offers.models import Offer
        mock_fetch.side_effect = RuntimeError("unavailable")
        offer = Offer(source="uc-apply", kind="call", title="Bolsa de Investigação",
                      url="https://www.apply.uc.pt/procedure/abc123")
        result = _enrich(offer)
        self.assertIs(result, offer)
        self.assertFalse(result.extra)

    @patch("academic_offers.sources.uc_apply.fetch")
    def test_scrape_filters_expired_after_detail_enrichment(self, mock_fetch):
        detail = """
        <main>
          <p>Candidaturas 11/11/2026 a 24/11/2026</p>
          <dl><dt>Área</dt><dd>Química</dd></dl>
        </main>
        """
        mock_fetch.side_effect = [LISTING, detail, detail, detail]
        offers = scrape(dt.date(2026, 11, 27))
        self.assertEqual(offers, [])


if __name__ == "__main__":
    unittest.main()

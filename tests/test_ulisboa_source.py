"""Tests for the Universidade de Lisboa recruitment listing parser."""
import datetime as dt
import unittest
from unittest.mock import patch

from academic_offers.sources.ulisboa import parse_listing, scrape


HTML = """
<html><body>
<h3>Instituto Superior Técnico</h3>
<table>
  <thead><tr><th>Código</th><th>Designação</th><th>Vagas</th><th>Categoria</th><th>Data Limite</th><th>Documento Principal</th></tr></thead>
  <tbody>
    <tr>
      <td>Edital n.º 1466/2026</td>
      <td><h5><a href="/info/recrutamento?c=1466">Edital n.º 1466/2026 Concurso documental internacional para um professor catedrático, na área disciplinar de Gestão Estratégica e Marketing</a></h5></td>
      <td>1</td><td>Professor Catedrático</td><td>05/01/2027</td>
      <td><a href="/files/edital-1466-2026.pdf">Edital principal</a></td>
    </tr>
    <tr>
      <td>Aviso n.º 77/2026</td>
      <td><a href="/info/recrutamento?c=77">Bolsa de Investigação para Doutoramento em Engenharia Informática</a></td>
      <td>2</td><td>Bolseiro de Investigação</td><td>30/11/2026</td>
      <td><a href="/files/aviso-77.pdf">Aviso</a></td>
    </tr>
    <tr>
      <td>Ref. 33/2026</td>
      <td><a href="/info/recrutamento?c=33">Procedimento concursal para assistente administrativo</a></td>
      <td>1</td><td>Assistente Técnico</td><td>05/12/2026</td>
      <td><a href="/files/aviso-33.pdf">Aviso</a></td>
    </tr>
    <tr>
      <td>Edital n.º 12/2026</td>
      <td><a href="/info/recrutamento?c=12">Concurso para professor auxiliar em Física</a></td>
      <td>1</td><td>Professor Auxiliar</td><td>20/10/2026</td>
      <td><a href="/files/edital-12.pdf">Edital</a></td>
    </tr>
  </tbody>
</table>
</body></html>
"""


class ULisboaSourceTests(unittest.TestCase):
    def test_extracts_academic_rows_and_preserves_original_urls(self):
        offers = parse_listing(HTML)
        self.assertEqual(len(offers), 3)
        professor = next(o for o in offers if "professor catedrático" in o.title.lower())
        self.assertEqual(professor.url, "https://www.ulisboa.pt/info/recrutamento?c=1466")
        self.assertEqual(professor.deadline, "2027-01-05")
        self.assertEqual(professor.institution, "Instituto Superior Técnico")
        self.assertEqual(professor.n_posts, 1)
        self.assertIn("Edital n.º 1466/2026", professor.notes)
        self.assertEqual(professor.extra["ulisboa_document_url"],
                         "https://www.ulisboa.pt/files/edital-1466-2026.pdf")

    def test_extracts_research_scholarships(self):
        offers = parse_listing(HTML)
        scholarship = next(o for o in offers if "bolsa" in o.title.lower())
        self.assertEqual(scholarship.n_posts, 2)
        self.assertEqual(scholarship.deadline, "2026-11-30")
        self.assertEqual(scholarship.position_type, "Bolseiro de Investigação")

    def test_ignores_non_academic_administrative_roles(self):
        offers = parse_listing(HTML)
        self.assertFalse(any("administrativo" in o.title.lower() for o in offers))

    def test_invalid_or_missing_deadlines_are_not_guessed(self):
        html = """
        <table><tr>
        <td>Ref. X</td><td><a href="/info/recrutamento?c=x">Concurso para investigador auxiliar</a></td>
        <td>1</td><td>Investigador Auxiliar</td><td>Prazo em dezembro</td>
        </tr></table>
        """
        offer = parse_listing(html)[0]
        self.assertIsNone(offer.deadline)
        self.assertIn("Prazo não identificado", offer.notes)

    def test_external_links_are_not_accepted_as_primary_record(self):
        html = """
        <table><tr>
        <td>Ref. X</td><td><a href="https://example.org/call">Concurso para investigador</a></td>
        <td>1</td><td>Investigador</td><td>31/12/2026</td>
        </tr></table>
        """
        self.assertEqual(parse_listing(html), [])

    @patch("academic_offers.sources.ulisboa.fetch")
    def test_scrape_filters_expired_deadlines(self, mock_fetch):
        mock_fetch.side_effect = [HTML, ""]
        offers = scrape(dt.date(2026, 11, 27))
        self.assertEqual({o.deadline for o in offers}, {"2027-01-05", "2026-11-30"})
        self.assertEqual(mock_fetch.call_count, 2)

    @patch("academic_offers.sources.ulisboa.fetch")
    def test_scrape_continues_after_page_with_only_administrative_rows(self, mock_fetch):
        administrative_only = """
        <table><tr>
        <td>Ref. A</td><td><a href="/info/recrutamento?c=a">Procedimento concursal para assistente administrativo</a></td>
        <td>1</td><td>Assistente Técnico</td><td>31/12/2026</td>
        </tr></table>
        """
        mock_fetch.side_effect = [administrative_only, HTML, ""]
        offers = scrape(dt.date(2026, 11, 27))
        self.assertEqual(len(offers), 2)
        self.assertEqual(mock_fetch.call_count, 3)


if __name__ == "__main__":
    unittest.main()

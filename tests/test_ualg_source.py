"""Tests for the Universidade do Algarve public recruitment index."""
import datetime as dt
import unittest
from unittest.mock import patch

from academic_offers.sources.ualg import parse_listing, scrape


HTML = """
<html><body><main>
<table>
  <thead>
    <tr>
      <th>Referência</th><th>Código</th><th>Categoria</th><th>Designação</th>
      <th>Data de início</th><th>Data de fim</th><th>Estado</th><th>Documentos</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Edital n.º 1498/2026</td><td>OE202611/0947</td><td>Docente</td>
      <td><a href="/procedimentos-concursais?id=482308">Concurso documental internacional para Professor Auxiliar na área disciplinar de Ciências da Educação</a></td>
      <td>24-11-2026</td><td>08-01-2027</td><td>Em fase de candidatura</td>
      <td><a href="/sites/default/files/edital-1498.pdf">Edital n.º 1498/2026</a></td>
    </tr>
    <tr>
      <td>Aviso n.º 3872/2026/2</td><td>OE202602/0638</td><td>Investigador</td>
      <td><a href="/procedimentos-concursais?id=old">Concurso de seleção internacional de Investigador Doutorado em Arqueologia</a></td>
      <td>23-02-2026</td><td>09-03-2026</td><td>Terminado</td>
      <td><a href="/sites/default/files/aviso.pdf">Aviso</a></td>
    </tr>
    <tr>
      <td>Aviso n.º 26958/2026/2</td><td>OE202610/1202</td><td>Não Docente</td>
      <td><a href="/procedimentos-concursais?id=admin">Procedimento concursal para Técnico de Sistemas e Tecnologias de Informação</a></td>
      <td>30-10-2026</td><td>12-11-2026</td><td>A decorrer</td>
      <td></td>
    </tr>
    <tr>
      <td>Edital n.º 123/2026</td><td>OE202611/1001</td><td>Docente</td>
      <td><a href="/procedimentos-concursais?id=missing">Concurso documental internacional para Professor Associado em Física</a></td>
      <td>20-11-2026</td><td>Prazo em análise</td><td>A decorrer</td>
      <td></td>
    </tr>
    <tr>
      <td>Edital n.º 124/2026</td><td>OE202611/1002</td><td>Investigador</td>
      <td><a href="https://example.org/call">Concurso para Investigador Auxiliar em Biologia</a></td>
      <td>20-11-2026</td><td>20-12-2026</td><td>Em fase de candidatura</td>
      <td></td>
    </tr>
  </tbody>
</table>
</main></body></html>
"""


class UAlgSourceTests(unittest.TestCase):
    def test_extracts_only_teaching_and_researcher_rows(self):
        offers = parse_listing(HTML)
        self.assertEqual(len(offers), 2)
        self.assertTrue(all(o.institution == "Universidade do Algarve" for o in offers))
        self.assertFalse(any("Técnico de Sistemas" in o.title for o in offers))

    def test_extracts_deadline_reference_and_document_url(self):
        offer = parse_listing(HTML)[0]
        self.assertEqual(offer.deadline, "2027-01-08")
        self.assertEqual(offer.position_type, "Docente")
        self.assertEqual(offer.n_posts, 1)
        self.assertEqual(offer.extra["ualg_reference"], "Edital n.º 1498/2026")
        self.assertEqual(offer.extra["ualg_code"], "OE202611/0947")
        self.assertEqual(
            offer.extra["ualg_document_url"],
            "https://www.ualg.pt/sites/default/files/edital-1498.pdf",
        )

    def test_does_not_infer_missing_deadline(self):
        offers = parse_listing(HTML)
        missing = next(o for o in offers if "Professor Associado" in o.title)
        self.assertIsNone(missing.deadline)
        self.assertIn("Prazo não identificado", missing.notes)

    def test_ignores_finished_rows_even_if_the_date_is_future(self):
        html = HTML.replace("09-03-2026</td><td>Terminado", "09-01-2027</td><td>Terminado")
        self.assertFalse(any("Arqueologia" in o.title for o in parse_listing(html)))

    def test_ignores_external_title_links(self):
        offers = parse_listing(HTML)
        self.assertFalse(any("example.org" in offer.url for offer in offers))

    @patch("academic_offers.sources.ualg.fetch")
    def test_scrape_filters_expired_deadlines(self, mock_fetch):
        mock_fetch.return_value = HTML
        offers = scrape(dt.date(2026, 11, 27))
        self.assertEqual(len(offers), 2)
        self.assertEqual({o.deadline for o in offers}, {"2027-01-08", None})
        mock_fetch.assert_called_once()



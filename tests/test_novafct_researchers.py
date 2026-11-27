"""Tests for the NOVA FCT researcher recruitment index."""
import datetime as dt
import unittest
from unittest.mock import patch

from academic_offers.sources.novafct_investigadores import parse_listing, scrape


HTML = """
<html><body><main>
  <a href="/formulario">FORMULÁRIO DE CANDIDATURA</a>
  <article class="views-row">
    <h3><a href="/sites/default/files/documentos/concursos/aviso_28960.2026.2.pdf">AVISO (EXTRATO) N.º 28960/2026/2 - CONCURSO DOCUMENTAL INTERNACIONAL PARA RECRUTAMENTO DE UM INVESTIGADOR JÚNIOR – ÁREA DE ENGENHARIA CIVIL</a></h3>
    <p>Concurso documental internacional para recrutamento de 1 Investigador Júnior, na área científica de Engenharia Civil, subárea de Construção.</p>
    <p>Candidaturas Abertas até 15/12/2026 (Inclusive)</p>
  </article>
  <article class="views-row">
    <h3><a href="/sites/default/files/documentos/concursos/aviso_28821.2026.pdf">AVISO (EXTRATO) N.º 28821/2026/2 - CONCURSO DOCUMENTAL INTERNACIONAL PARA RECRUTAMENTO DE UM INVESTIGADOR AUXILIAR</a></h3>
    <p>Concurso documental internacional para recrutamento de 1 Investigador Auxiliar, na área de Engenharia Eletrotécnica e de Computadores.</p>
    <p>Candidaturas Abertas até 14/12/2026 (Inclusive)</p>
  </article>
  <article class="views-row">
    <h3><a href="/sites/default/files/documentos/concursos/aviso_28820.2026.pdf">AVISO (EXTRATO) N.º 28820/2026/2 - CONCURSO DOCUMENTAL INTERNACIONAL PARA RECRUTAMENTO DE UM INVESTIGADOR AUXILIAR</a></h3>
    <p>Concurso documental internacional para recrutamento de 1 Investigador Auxiliar, no âmbito do projeto Chef Metalab.</p>
    <p>Candidaturas Abertas até 14/12/2026 (Inclusive)</p>
  </article>
  <article class="views-row">
    <h3><a href="/sites/default/files/documentos/concursos/aviso_20000.2026.pdf">AVISO (EXTRATO) N.º 20000/2026/2 - CONCURSO PARA INVESTIGADOR AUXILIAR EM BIOLOGIA</a></h3>
    <p>Concurso para recrutamento de 1 Investigador Auxiliar, na área científica de Biologia.</p>
    <p>Candidaturas Abertas até 10/11/2026 (Inclusive)</p>
  </article>
  <article class="views-row">
    <h3><a href="/sites/default/files/documentos/concursos/aviso_19999.2026.pdf">AVISO (EXTRATO) N.º 19999/2026/2 - CONCURSO PARA INVESTIGADOR EM QUÍMICA</a></h3>
    <p>Concurso para recrutamento de 1 Investigador na área científica de Química.</p>
  </article>
  <article class="views-row">
    <h3><a href="https://example.org/aviso_28819.pdf">AVISO (EXTRATO) N.º 28819/2026/2 - CONCURSO PARA INVESTIGADOR</a></h3>
    <p>Concurso para recrutamento de 1 Investigador na área científica de Física.</p>
    <p>Candidaturas Abertas até 14/12/2026 (Inclusive)</p>
  </article>
</main></body></html>
"""


class NOVAFCTResearchersTests(unittest.TestCase):
    def test_extracts_official_researcher_notices_and_deadlines(self):
        offers = parse_listing(HTML)
        self.assertEqual(len(offers), 5)
        first = offers[0]
        self.assertEqual(first.title, "Investigador Júnior — Engenharia Civil")
        self.assertEqual(first.position_type, "Investigador Júnior")
        self.assertEqual(first.deadline, "2026-12-15")
        self.assertEqual(first.n_posts, 1)
        self.assertEqual(first.extra["novafct_notice"], "28960/2026/2")
        self.assertEqual(
            first.url,
            "https://www.fct.unl.pt/sites/default/files/documentos/concursos/aviso_28960.2026.2.pdf",
        )
        self.assertEqual(first.institution, "NOVA FCT — Faculdade de Ciências e Tecnologia")
        self.assertEqual(first.region, "Lisboa")

    def test_does_not_invent_a_missing_deadline(self):
        offer = next(
            item for item in parse_listing(HTML)
            if item.extra["novafct_notice"] == "19999/2026/2"
        )
        self.assertIsNone(offer.deadline)
        self.assertIn("Prazo não identificado", offer.notes)

    def test_rejects_non_official_notice_links(self):
        offers = parse_listing(HTML)
        self.assertFalse(any("example.org" in offer.url for offer in offers))

    def test_scrape_filters_expired_deadlines_and_keeps_unstated_dates(self):
        with patch("academic_offers.sources.novafct_investigadores.fetch", return_value=HTML) as mock_fetch:
            offers = scrape(dt.date(2026, 11, 27))
        self.assertEqual(len(offers), 4)
        self.assertFalse(any(item.extra["novafct_notice"] == "20000/2026/2" for item in offers))
        self.assertTrue(any(item.extra["novafct_notice"] == "19999/2026/2" for item in offers))
        mock_fetch.assert_called_once_with(
            "https://www.fct.unl.pt/faculdade/concursos/investigadores"
        )

    def test_detects_an_unrecognised_notice_card_instead_of_silently_returning_zero(self):
        changed_html = """
        <h3><a href="/sites/default/files/aviso_1.pdf">AVISO (EXTRATO) N.º 1/2026</a></h3>
        """
        with self.assertRaises(RuntimeError):
            parse_listing(changed_html)


if __name__ == "__main__":
    unittest.main()

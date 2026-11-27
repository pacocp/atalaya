"""Tests for the University of Minho EEG recruitment index."""
import datetime as dt
import unittest
from unittest.mock import patch

from academic_offers.sources.uminho_eeg import parse_listing, scrape


HTML = """
<html><body><main>
  <h2>Procedimentos Concursais - Pessoal Docente e Pessoal Investigador</h2>
  <p>Posições em Aberto</p>
  <div class="vacancy">
    <h4>Professor Auxiliar Economia</h4>
    <p>Aberto Edital N.º 1467/2026</p>
    <p>Prazo de candidatura termina a 05 de janeiro de 2027</p>
    <a href="/pt/escola/Documents/Edital_1467_2026_EEG.pdf">📄 Ver Edital</a>
  </div>
  <div class="vacancy">
    <h4>Professor Auxiliar Gestão (Métodos Quantitativos Aplicados)</h4>
    <p>Em Aberto Edital N.º 790/2026</p>
    <p>Prazo de candidatura: 06 de agosto de 2026</p>
    <a href="/pt/escola/Documents/Edital_790_2026_EEG.pdf">Ver Edital</a>
  </div>
  <p>Posições Encerradas</p>
  <div class="vacancy">
    <h4>Professor Auxiliar Ciência Política</h4>
    <p>Encerrado Edital N.º 833/2026</p>
    <p>Prazo de candidatura terminado</p>
    <a href="/pt/escola/Documents/Edital_833_2026_EEG.pdf">Ver Edital</a>
  </div>
  <h2>Procedimentos Concursais - Pessoal Técnico, Administrativo e de Gestão</h2>
  <p>Posições em Aberto</p>
  <div class="vacancy">
    <h4>Técnico Superior</h4>
    <p>Em Aberto CTTRC-PTAG-203/26-EEG</p>
    <p>Prazo de candidatura: 31 de julho de 2026</p>
    <a href="/pt/escola/Documents/tecnico.pdf">Ver Edital</a>
  </div>
</main></body></html>
"""


class UMinhoEEGSourceTests(unittest.TestCase):
    def test_extracts_only_open_academic_positions(self):
        offers = parse_listing(HTML)
        self.assertEqual(len(offers), 2)
        self.assertEqual(
            {offer.title for offer in offers},
            {
                "Professor Auxiliar Economia",
                "Professor Auxiliar Gestão (Métodos Quantitativos Aplicados)",
            },
        )

    def test_extracts_deadline_notice_and_original_pdf_url(self):
        offer = parse_listing(HTML)[0]
        self.assertEqual(offer.deadline, "2027-01-05")
        self.assertEqual(offer.extra["uminho_eeg_notice"], "1467/2026")
        self.assertEqual(
            offer.url,
            "https://www.eeg.uminho.pt/pt/escola/Documents/Edital_1467_2026_EEG.pdf",
        )
        self.assertEqual(offer.institution,
                         "Universidade do Minho — Escola de Economia, Gestão e Ciência Política")
        self.assertEqual(offer.region, "Braga")

    def test_does_not_guess_a_missing_deadline(self):
        html = """
        <h2>Procedimentos Concursais - Pessoal Docente e Pessoal Investigador</h2>
        <p>Posições em Aberto</p>
        <div>
          <h4>Professor Auxiliar Biologia</h4>
          <p>Aberto Edital N.º 12/2026</p>
          <a href="https://www.eeg.uminho.pt/edital.pdf">Ver Edital</a>
        </div>
        <p>Posições Encerradas</p>
        """
        offer = parse_listing(html)[0]
        self.assertIsNone(offer.deadline)
        self.assertIn("Prazo não identificado", offer.notes)

    def test_rejects_non_official_notice_links(self):
        html = """
        <h2>Procedimentos Concursais - Pessoal Docente e Pessoal Investigador</h2>
        <p>Posições em Aberto</p>
        <div>
          <h4>Professor Auxiliar Biologia</h4>
          <p>Aberto Edital N.º 12/2026</p>
          <p>Prazo de candidatura: 31/12/2026</p>
          <a href="https://example.org/edital.pdf">Ver Edital</a>
        </div>
        <p>Posições Encerradas</p>
        """
        self.assertEqual(parse_listing(html), [])

    @patch("academic_offers.sources.uminho_eeg.fetch")
    def test_scrape_filters_expired_deadlines(self, mock_fetch):
        mock_fetch.return_value = HTML
        offers = scrape(dt.date(2026, 11, 27))
        self.assertEqual([offer.deadline for offer in offers], ["2027-01-05"])
        mock_fetch.assert_called_once_with(
            "https://www.eeg.uminho.pt/pt/escola/Paginas/procedimentos-concursais.aspx"
        )


if __name__ == "__main__":
    unittest.main()

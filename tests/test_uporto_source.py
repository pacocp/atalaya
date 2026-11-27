"""Tests for the public Universidade do Porto opportunities archive."""
import datetime as dt
import unittest
from unittest.mock import patch

from academic_offers.sources.uporto import parse_listing, scrape


HTML = """
<html><body><main>
  <article>
    <div class="category">Bolsas</div>
    <h2><a href="/oportunidades/fep-bolsa-pos-doutoral/">FEP | Bolsa de Investigação Pós Doutoral | FOUR4ALL (Ref.ª BOLS-FEP-26-12)</a></h2>
    <p>Até 28 de novembro de 2026</p>
  </article>
  <article>
    <div class="category">Recrutamento</div>
    <h2><a href="/oportunidades/fadeup-professor-auxiliar/">FADEUP | Concurso para Professor Auxiliar | Ciências do Desporto</a></h2>
    <p>Até 19.12.2026</p>
  </article>
  <article>
    <div class="category">Formação</div>
    <h2><a href="/oportunidades/curso/">Curso de Ciências de Animais Aquáticos de Laboratório</a></h2>
    <p>Até 12.01.2027</p>
  </article>
  <article>
    <div class="category">Recrutamento</div>
    <h2><a href="/oportunidades/tecnico-admin/">FLUP | Assistente Operacional | Serviço de Logística</a></h2>
    <p>Até 25.12.2026</p>
  </article>
</main></body></html>
"""


class UPortoSourceTests(unittest.TestCase):
    def test_extracts_research_scholarship_and_faculty_recruitment(self):
        offers = parse_listing(HTML)
        self.assertEqual(len(offers), 2)
        scholarship = next(o for o in offers if "Bolsa" in o.title)
        self.assertEqual(scholarship.kind, "call")
        self.assertEqual(scholarship.position_type, "Bolsas")
        self.assertEqual(scholarship.deadline, "2026-11-28")
        professor = next(o for o in offers if "Professor Auxiliar" in o.title)
        self.assertEqual(professor.kind, "position")
        self.assertEqual(professor.deadline, "2026-12-19")

    def test_deadline_accepts_written_portuguese_month(self):
        html = """
        <article>
          <div class="category">Bolsas</div>
          <h2><a href="/oportunidades/bolsa/">Bolsa de Investigação</a></h2>
          <p>Prazo de candidatura: 28 de novembro de 2026</p>
        </article>
        """
        offer = parse_listing(html)[0]
        self.assertEqual(offer.deadline, "2026-11-28")

    def test_preserves_official_detail_url_and_counts_posts(self):
        html = """
        <article>
          <div class="category">Bolsas</div>
          <h2><a href="/oportunidades/duas-bolsas/">ICBAS | 2 Bolsas de Investigação | Projeto de Biologia</a></h2>
          <p>Até 30.12.2026</p>
        </article>
        """
        offer = parse_listing(html)[0]
        self.assertEqual(offer.url, "https://noticias.up.pt/oportunidades/duas-bolsas/")
        self.assertEqual(offer.n_posts, 2)

    def test_parses_div_based_card_when_article_tag_is_absent(self):
        html = """
        <main>
          <div class="opportunity-card">
            <span>Bolsas</span>
            <h3><a href="/oportunidades/div-card/">Bolsa de Investigação para Doutoramento</a></h3>
            <p>Até 31.12.2026</p>
          </div>
        </main>
        """
        offers = parse_listing(html)
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].deadline, "2026-12-31")

    def test_div_cards_are_parsed_even_when_page_contains_other_articles(self):
        html = """
        <main>
          <article class="news-story"><h2>Not an opportunity</h2></article>
          <div class="opportunity-card">
            <h3><a href="/oportunidades/fpceup-roots/">FPCEUP | Bolsa de Investigação ROOTS</a></h3>
            <a href="/categoria/bolsas/">Bolsas</a>
            <p>Até 10 de dezembro de 2026</p>
          </div>
          <div class="opportunity-card">
            <h3><a href="/oportunidades/icbas-atlantida/">ICBAS | Bolsa Pós-Doutoramento ATLANTIDA II</a></h3>
            <a href="/categoria/bolsas/">Bolsas</a>
            <p>Até 14.12.2026</p>
          </div>
        </main>
        """
        offers = parse_listing(html)
        self.assertEqual(len(offers), 2)
        self.assertEqual({o.deadline for o in offers}, {"2026-12-10", "2026-12-14"})

    def test_ignores_external_links(self):
        html = """
        <article>
          <h2><a href="https://example.org/call">Bolsa de Investigação</a></h2>
          <p>Até 30.12.2026</p>
        </article>
        """
        self.assertEqual(parse_listing(html), [])

    def test_does_not_infer_missing_deadline(self):
        html = """
        <article>
          <h2><a href="/oportunidades/bolsa/">Bolsa de Investigação</a></h2>
          <p>Candidaturas abertas.</p>
        </article>
        """
        offer = parse_listing(html)[0]
        self.assertIsNone(offer.deadline)
        self.assertIn("Prazo não identificado", offer.notes)

    @patch("academic_offers.sources.uporto.fetch")
    def test_scrape_filters_expired_deadlines(self, mock_fetch):
        mock_fetch.side_effect = [HTML, ""]
        offers = scrape(dt.date(2026, 11, 27))
        self.assertEqual({o.deadline for o in offers}, {"2026-11-28", "2026-12-19"})
        self.assertEqual(mock_fetch.call_count, 2)

    @patch("academic_offers.sources.uporto.fetch")
    def test_scrape_continues_across_an_irrelevant_page(self, mock_fetch):
        training_only = """
        <article>
          <h2><a href="/oportunidades/curso/">Curso de Ciências de Animais Aquáticos de Laboratório</a></h2>
        </article>
        """
        mock_fetch.side_effect = [training_only, HTML, ""]
        offers = scrape(dt.date(2026, 11, 27))
        self.assertEqual(len(offers), 2)
        self.assertEqual(mock_fetch.call_count, 3)


if __name__ == "__main__":
    unittest.main()

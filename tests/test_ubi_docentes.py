"""Tests for the UBI open docente recruitment page."""
import datetime as dt
import unittest
from unittest.mock import patch

from academic_offers.sources.ubi_docentes import parse_listing, scrape


HTML = """
<html><body>
<h2>Concursos para Docentes</h2>
<h3>Candidaturas a decorrer:</h3>
<table>
<thead><tr>
<th>Categoria/Position</th><th>Área Disciplinar / Disciplinary Area</th>
<th>Postos de trabalho / Vacant post</th><th>Anúncios / Announcements</th>
<th>Edital / Public Notice</th><th>Data e hora Limite / Application Deadline</th>
<th>Registo/Registration</th>
</tr></thead>
<tbody>
<tr>
<td>Auxiliar/Assistant</td><td>Arquitetura (Arquitetura/Projeto) / Architecture (Architecture/Project)</td>
<td>1</td><td><a href="https://www.bep.gov.pt/offer/1">BEP</a> EURAXESS</td>
<td><a href="/Ficheiros/Sites/53/Paginas/442/Edital%20n%C2%BA%201453-2026.pdf">Edital nº 1453/2026</a> Public Notice</td>
<td>30/12/2026 17.30 Horas</td>
<td><a href="https://forms.cloud.microsoft/example">Registo de Candidatura</a></td>
</tr>
<tr>
<td>Associado/Associate</td><td>Ciências Aeroespaciais / Aerospace Sciences</td>
<td>2</td><td><a href="https://www.bep.gov.pt/offer/2">BEP</a> EURAXESS</td>
<td><a href="/Ficheiros/Sites/53/Paginas/442/Edital%20n%C2%BA%201454-2026.pdf">Edital nº 1454/2026</a></td>
<td>30/12/2026 17.30 Horas</td>
<td><a href="https://forms.cloud.microsoft/example2">Registo de Candidatura</a></td>
</tr>
<tr>
<td>Auxiliar/Assistant</td><td>Engenharia Civil (Mecânica e Estruturas) / Civil Engineering</td>
<td>1</td><td>BEP</td>
<td><a href="https://files.diariodarepublica.pt/2s/2026/11/227000000/0023100241.pdf">Edital nº 1499/2026</a></td>
<td>08/01/2027 17.30 Horas</td>
<td><a href="https://forms.cloud.microsoft/example3">Registo</a></td>
</tr>
<tr>
<td>Catedrático/Full</td><td>Medicina / Medicine</td>
<td>1</td><td>BEP</td>
<td><a href="/Ficheiros/Sites/53/Paginas/442/Edital%20n%C2%BA%20727-2026.pdf">Edital nº 727/2026</a></td>
<td>29/07/2026 17.30 Horas</td>
<td></td>
</tr>
<tr>
<td>Auxiliar/Assistant</td><td>Química / Chemistry</td>
<td>1</td><td>BEP</td>
<td><a href="/Ficheiros/Sites/53/Paginas/442/Edital%20n%C2%BA%201999-2026.pdf">Edital nº 1999/2026</a></td>
<td></td>
<td></td>
</tr>
</tbody></table>
<h3>Candidaturas encerradas:</h3>
<table><tr><th>Categoria/Position</th><th>Área Disciplinar</th><th>Postos</th><th>Anúncios</th><th>Edital</th><th>Data e hora Limite</th><th>Registo</th></tr>
<tr><td>Auxiliar/Assistant</td><td>Psicologia</td><td>1</td><td></td><td><a href="/old.pdf">Edital nº 727/2026</a></td><td>29/07/2026 17.30 Horas</td><td></td></tr></table>
<h2>Concursos para Investigadores</h2>
</body></html>
"""


class UBIDocentesTests(unittest.TestCase):
    def test_extracts_only_current_section_with_official_notices(self):
        offers = parse_listing(HTML)
        self.assertEqual(len(offers), 5)
        first = offers[0]
        self.assertEqual(first.title, "Professor Auxiliar — Arquitetura (Arquitetura/Projeto)")
        self.assertEqual(first.position_type, "Professor Auxiliar")
        self.assertEqual(first.deadline, "2026-12-30")
        self.assertEqual(first.n_posts, 1)
        self.assertEqual(first.extra["ubi_notice"], "1453/2026")
        self.assertEqual(first.extra["deadline_time"], "17:30")
        self.assertEqual(
            first.url,
            "https://www.ubi.pt/Ficheiros/Sites/53/Paginas/442/Edital%20n%C2%BA%201453-2026.pdf",
        )
        self.assertEqual(first.institution, "Universidade da Beira Interior")
        self.assertEqual(first.region, "Castelo Branco")

    def test_preserves_multiple_posts_and_dre_notice(self):
        offers = parse_listing(HTML)
        second = offers[1]
        third = offers[2]
        self.assertEqual(second.position_type, "Professor Associado")
        self.assertEqual(second.n_posts, 2)
        self.assertEqual(
            third.url,
            "https://files.diariodarepublica.pt/2s/2026/11/227000000/0023100241.pdf",
        )
        self.assertEqual(third.deadline, "2027-01-08")

    def test_does_not_invent_missing_deadline(self):
        offer = next(item for item in parse_listing(HTML) if item.extra["ubi_notice"] == "1999/2026")
        self.assertIsNone(offer.deadline)
        self.assertIn("Prazo não identificado", offer.notes)

    def test_scrape_filters_expired_and_keeps_undated_rows(self):
        with patch("academic_offers.sources.ubi_docentes.fetch", return_value=HTML) as mock_fetch:
            offers = scrape(dt.date(2026, 11, 27))
        self.assertEqual(len(offers), 4)
        self.assertFalse(any(item.extra["ubi_notice"] == "727/2026" for item in offers))
        self.assertTrue(any(item.extra["ubi_notice"] == "1999/2026" for item in offers))
        mock_fetch.assert_called_once_with(
            "https://www.ubi.pt/sites/academicos/pt/pagina/recrutamento"
        )

    def test_fails_closed_when_an_active_row_has_no_official_notice(self):
        changed_html = HTML.replace(
            '<a href="/Ficheiros/Sites/53/Paginas/442/Edital%20n%C2%BA%201453-2026.pdf">Edital nº 1453/2026</a>',
            '<a href="https://example.org/edital.pdf">Edital nº 1453/2026</a>',
        )
        with self.assertRaises(RuntimeError):
            parse_listing(changed_html)

    def test_does_not_fall_through_to_closed_table_when_open_table_disappears(self):
        closed_only_html = """
        <h2>Concursos para Docentes</h2>
        <h3>Candidaturas a decorrer:</h3>
        <h3>Candidaturas encerradas:</h3>
        <table>
          <tr>
            <th>Categoria/Position</th><th>Área Disciplinar</th>
            <th>Postos de trabalho</th><th>Anúncios</th><th>Edital</th>
            <th>Data e hora Limite</th><th>Registo</th>
          </tr>
          <tr>
            <td>Auxiliar/Assistant</td><td>Psicologia</td><td>1</td><td></td>
            <td><a href="/old.pdf">Edital nº 727/2026</a></td>
            <td>29/07/2026 17.30 Horas</td><td></td>
          </tr>
        </table>
        """
        with self.assertRaises(RuntimeError):
            parse_listing(closed_only_html)

    def test_detects_missing_open_section_table(self):
        changed_html = "<h2>Concursos para Docentes</h2><h3>Candidaturas a decorrer</h3>"
        with self.assertRaises(RuntimeError):
            parse_listing(changed_html)


if __name__ == "__main__":
    unittest.main()

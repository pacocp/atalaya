"""Tests for the public Diário da República RSS source."""
import unittest

from academic_offers.sources.dr import parse_feed


FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Aviso de abertura de procedimento concursal para recrutamento de investigador auxiliar</title>
    <link>https://diariodarepublica.pt/dr/detalhe/aviso/123/2026</link>
    <pubDate>Mon, 02 Nov 2026 09:00:00 GMT</pubDate>
    <description>Universidade pública — prazo de candidatura indicado no aviso.</description>
  </item>
  <item>
    <title>Homologação da lista unitária de ordenação final do procedimento concursal</title>
    <link>https://diariodarepublica.pt/dr/detalhe/aviso/124/2026</link>
  </item>
  <item>
    <title>Regulamento de avaliação de desempenho</title>
    <link>https://diariodarepublica.pt/dr/detalhe/regulamento/125/2026</link>
  </item>
</channel></rss>"""


class DiarioRepublicaSourceTests(unittest.TestCase):
    def test_keeps_recruitment_notice_and_original_url(self):
        offers = parse_feed(FEED)
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].source, "dr")
        self.assertEqual(offers[0].region, "Portugal")
        self.assertEqual(
            offers[0].url,
            "https://diariodarepublica.pt/dr/detalhe/aviso/123/2026",
        )
        self.assertEqual(offers[0].published, "2026-11-02")

    def test_generic_rss_title_uses_academic_sumario_from_description(self):
        xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel><item>
          <title>Aviso (extrato) n.º 27882/2026/2</title>
          <link>https://diariodarepublica.pt/dr/detalhe/aviso/27882/2026</link>
          <pubDate>Fri, 27 Nov 2026 10:00:00 GMT</pubDate>
          <description><![CDATA[
            <p><strong>Sumário:</strong> Procedimento concursal de recrutamento
            e contratação de investigador doutorado para o exercício de
            atividades de investigação científica.</p><p>TEXTO</p>
          ]]></description>
        </item></channel></rss>"""
        offers = parse_feed(xml)
        self.assertEqual(len(offers), 1)
        self.assertIn("investigador doutorado", offers[0].title)
        self.assertEqual(offers[0].published, "2026-11-27")

    def test_generic_administrative_recruitment_is_not_kept(self):
        xml = """<rss><channel><item>
          <title>Aviso (extrato) n.º 100/2026</title>
          <link>https://diariodarepublica.pt/dr/detalhe/aviso/100/2026</link>
          <description><![CDATA[
            <p><strong>Sumário:</strong> Procedimento concursal para
            recrutamento de assistente técnico.</p>
          ]]></description>
        </item></channel></rss>"""
        self.assertEqual(parse_feed(xml), [])

    def test_atom_entry_supports_href_and_iso_date(self):
        atom = '''<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Concurso para contratação de investigador doutorado</title>
            <link href="https://diariodarepublica.pt/dr/detalhe/aviso/999/2026" />
            <updated>2026-11-26T14:30:00Z</updated>
          </entry>
        </feed>'''
        offers = parse_feed(atom)
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].url, "https://diariodarepublica.pt/dr/detalhe/aviso/999/2026")
        self.assertEqual(offers[0].published, "2026-11-26")

    def test_invalid_xml_returns_empty_list(self):
        self.assertEqual(parse_feed("<rss>"), [])

    def test_duplicate_links_are_removed(self):
        first_item = FEED.split("<item>", 1)[1].split("</item>", 1)[0]
        duplicate = FEED.replace("</channel>", "<item>" + first_item + "</item></channel>")
        self.assertEqual(len(parse_feed(duplicate)), 1)


if __name__ == "__main__":
    unittest.main()

"""Tests for the active source scope of the Portuguese edition."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from academic_offers.__main__ import build_site
from academic_offers.sources import SOURCES


class PortugalEditionTests(unittest.TestCase):
    def test_only_portuguese_and_european_sources_are_active(self):
        self.assertEqual(
            {source.key for source in SOURCES},
            {"dr", "fct", "ulisboa", "uporto", "ualg", "uc-apply", "uminho-eeg", "novafct-investigadores", "ubi-docentes", "eu-ft"},
        )

    @patch("academic_offers.__main__.store.last_runs", return_value={})
    @patch("academic_offers.__main__.store.current")
    def test_build_site_excludes_inactive_spanish_history(self, current, _last_runs):
        current.return_value = [
            {"source": "boe", "id": "legacy-spanish", "title": "Old Spanish offer"},
            {"source": "dr", "id": "portuguese-dr", "title": "Aviso português"},
            {"source": "fct", "id": "portuguese-fct", "title": "Concurso FCT"},
            {"source": "ulisboa", "id": "ulisboa-offer", "title": "Oferta ULisboa"},
            {"source": "uporto", "id": "uporto-offer", "title": "Oferta U.Porto"},
            {"source": "ualg", "id": "ualg-offer", "title": "Oferta UAlg"},
            {"source": "uc-apply", "id": "coimbra-offer", "title": "Bolsa UC"},
            {"source": "uminho-eeg", "id": "uminho-offer", "title": "Oferta UMinho EEG"},
            {"source": "novafct-investigadores", "id": "novafct-offer", "title": "Oferta NOVA FCT"},
            {"source": "ubi-docentes", "id": "ubi-offer", "title": "Oferta UBI"},
            {"source": "eu-ft", "id": "european-call", "title": "ERC call"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            count = build_site(object(), dt.date(2026, 11, 27), Path(tmp))
            rows = json.loads((Path(tmp) / "offers.json").read_text(encoding="utf-8"))
        self.assertEqual(count, 10)
        self.assertEqual(
            {row["source"] for row in rows},
            {"dr", "fct", "ulisboa", "uporto", "ualg", "uc-apply", "uminho-eeg", "novafct-investigadores", "ubi-docentes", "eu-ft"},
        )
        self.assertFalse(any(row["id"] == "legacy-spanish" for row in rows))


if __name__ == "__main__":
    unittest.main()

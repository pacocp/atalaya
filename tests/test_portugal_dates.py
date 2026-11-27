"""Regression tests for Portuguese month names in deadline extraction."""
import unittest

from academic_offers.dates import first_date


class PortugueseDateTests(unittest.TestCase):
    def test_portuguese_month(self):
        self.assertEqual(first_date("Candidaturas até 15 de março de 2027"), "2027-03-15")

    def test_portuguese_month_without_de(self):
        self.assertEqual(first_date("Prazo: 2 de outubro 2026"), "2026-10-02")

    def test_numeric_portuguese_date(self):
        self.assertEqual(first_date("Termina em 07/11/2026"), "2026-11-07")


if __name__ == "__main__":
    unittest.main()

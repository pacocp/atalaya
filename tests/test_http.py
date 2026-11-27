"""Tests for conservative robots.txt handling."""
import unittest
from unittest.mock import patch

import httpx

from academic_offers import http


class RobotsPolicyTests(unittest.TestCase):
    def setUp(self):
        http._robots.clear()

    def tearDown(self):
        http._robots.clear()

    @patch("academic_offers.http._client.get")
    def test_parses_successful_robots_rules(self, mock_get):
        mock_get.return_value = type("Response", (), {
            "status_code": 200,
            "text": "User-agent: *\nDisallow: /private\n",
        })()

        rules = http._robots_for("https", "example.org")

        self.assertTrue(rules.can_fetch(http.BOT_NAME, "https://example.org/public"))
        self.assertFalse(rules.can_fetch(http.BOT_NAME, "https://example.org/private"))
        mock_get.assert_called_once()

    @patch("academic_offers.http._client.get")
    def test_missing_robots_file_on_4xx_allows_crawling(self, mock_get):
        mock_get.return_value = type("Response", (), {
            "status_code": 404,
            "text": "not found",
        })()

        rules = http._robots_for("https", "example.org")

        self.assertTrue(rules.can_fetch(http.BOT_NAME, "https://example.org/anything"))

    @patch("academic_offers.http._client.get")
    def test_server_error_disallows_all_urls(self, mock_get):
        mock_get.return_value = type("Response", (), {
            "status_code": 503,
            "text": "temporarily unavailable",
        })()

        rules = http._robots_for("https", "example.org")

        self.assertFalse(rules.can_fetch(http.BOT_NAME, "https://example.org/"))
        self.assertFalse(rules.can_fetch(http.BOT_NAME, "https://example.org/open-call"))
        mock_get.assert_called_once()

    @patch("academic_offers.http._client.get")
    def test_rate_limit_disallows_all_urls(self, mock_get):
        mock_get.return_value = type("Response", (), {
            "status_code": 429,
            "text": "too many requests",
        })()

        rules = http._robots_for("https", "example.org")

        self.assertFalse(rules.can_fetch(http.BOT_NAME, "https://example.org/open-call"))

    @patch("academic_offers.http._client.get", side_effect=httpx.ConnectError("network unavailable"))
    def test_network_failure_after_retries_disallows_all_urls(self, mock_get):
        rules = http._robots_for("https", "example.org")

        self.assertFalse(rules.can_fetch(http.BOT_NAME, "https://example.org/open-call"))
        self.assertEqual(mock_get.call_count, 3)


if __name__ == "__main__":
    unittest.main()

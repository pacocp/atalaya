"""Polite HTTP client: identifies itself, obeys robots.txt (including Crawl-delay), waits between
requests to the same host, and caches responses so a day's run never fetches a page twice."""
from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)

# The published site (set by the GitHub workflow). Until it exists, point site owners at the author's page.
SITE_URL = os.environ.get("ATALAYA_SITE_URL", "").rstrip("/")
CONTACT_URL = f"{SITE_URL}/about.html" if SITE_URL else "https://github.com/Diogo-JSDias/atalaya"
USER_AGENT = f"AtalayaBot/0.2 (+{CONTACT_URL}; once a day, non-commercial)"
BOT_NAME = "AtalayaBot"
DEFAULT_DELAY = 2.0

CACHE_DIR = Path(".cache/http")
CACHE_TTL = 6 * 3600  # seconds

_last_hit: dict[str, float] = {}
_robots: dict[str, RobotFileParser] = {}
_client = httpx.Client(
    headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8"},
    follow_redirects=True,
    timeout=45,
)


class Disallowed(Exception):
    """robots.txt forbids this URL for our bot."""


def _blocked_robots() -> RobotFileParser:
    """Return rules that disallow every URL when robots.txt cannot be reached safely."""
    rp = RobotFileParser()
    rp.parse(["User-agent: *", "Disallow: /"])
    return rp


def _robots_for(scheme: str, host: str) -> RobotFileParser:
    if host not in _robots:
        # Fail closed until a successful response or a robots-unavailable (4xx)
        # response establishes the site's policy.
        _robots[host] = _blocked_robots()
        for attempt in range(3):
            try:
                r = _client.get(f"{scheme}://{host}/robots.txt", timeout=15)
            except httpx.HTTPError as exc:
                if attempt == 2:
                    log.warning(
                        "robots.txt could not be reached for %s after 3 attempts; "
                        "disallowing the host (%s)",
                        host, type(exc).__name__,
                    )
                continue

            if 200 <= r.status_code < 300:
                rp = RobotFileParser()
                rp.parse(r.text.splitlines())
                _robots[host] = rp
            elif 400 <= r.status_code < 500 and r.status_code != 429:
                # A 4xx response means robots.txt is unavailable. A 429 is
                # treated conservatively as rate limiting, not as permission.
                rp = RobotFileParser()
                rp.parse([])
                _robots[host] = rp
            else:
                log.warning(
                    "robots.txt returned HTTP %s for %s; disallowing the host",
                    r.status_code, host,
                )
            break
    return _robots[host]


def _check(url: str) -> float:
    """Raise if robots.txt disallows the URL; return the delay to keep between requests."""
    u = urlparse(url)
    rp = _robots_for(u.scheme, u.netloc)
    if rp is not None and not rp.can_fetch(BOT_NAME, url):
        log.warning("robots.txt disallows %s; skipping", url)
        raise Disallowed(url)
    delay = (rp.crawl_delay(BOT_NAME) if rp else None) or DEFAULT_DELAY
    return max(float(delay), DEFAULT_DELAY)


def _wait(host: str, delay: float) -> None:
    elapsed = time.time() - _last_hit.get(host, 0)
    if elapsed < delay:
        time.sleep(delay - elapsed)
    _last_hit[host] = time.time()


def _cached(method: str, url: str, suffix: str) -> Path:
    return CACHE_DIR / (hashlib.sha1(f"{method} {url}".encode()).hexdigest() + suffix)


def _request(url: str, method: str, headers: dict | None, attempts: int = 4) -> httpx.Response:
    delay = _check(url)
    host = urlparse(url).netloc
    for attempt in range(1, attempts + 1):
        _wait(host, delay)
        try:
            resp = _client.request(method, url, headers=headers)
        except (httpx.ConnectError, httpx.ReadTimeout) as e:
            # Some load-balanced public-sector sites (e.g. sede.csic.gob.es) have one backend that
            # serves an incomplete certificate chain or stalls. Certificates are still verified;
            # we just try again and usually land on a healthy backend.
            if attempt == attempts:
                raise
            log.info("retrying %s after %s", url, type(e).__name__)
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError("unreachable")


def fetch(url: str, *, method: str = "GET", headers: dict | None = None, use_cache: bool = True) -> str:
    path = _cached(method, url, "")
    if use_cache and path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL:
        return path.read_text(encoding="utf-8")
    text = _request(url, method, headers).text
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def fetch_bytes(url: str, *, use_cache: bool = True) -> bytes:
    """For PDFs. Cached for a week: published annexes don't change."""
    path = _cached("GET", url, ".bin")
    if use_cache and path.exists() and time.time() - path.stat().st_mtime < 7 * 86400:
        return path.read_bytes()
    data = _request(url, "GET", None).content
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data

"""Daily pipeline: scrape → classify → store → build the static site.

    python -m academic_offers                 # full run
    python -m academic_offers --build         # rebuild the site from the database only
    python -m academic_offers --only boe,crg  # run some sources only
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

from . import llm, store
from .classify import classify
from .http import SITE_URL
from .sources import SOURCES

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("academic_offers")


def _warn(msg: str) -> None:
    """Log a warning; inside GitHub Actions also raise an annotation on the run summary."""
    log.warning(msg)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning::{msg}")


def scrape(db, today: dt.date, boe_days: int, only: set[str] | None) -> None:
    results = {}
    for src in SOURCES:
        if only and src.key not in only:
            continue
        try:
            offers = [classify(o) for o in src.run(today, boe_days)]
        except Exception:
            log.exception("source %s failed", src.key)
            _warn(f"Source {src.key} failed; keeping its previous offers.")
            continue
        for o in offers:
            o.source = src.key
        results[src.key] = offers
        log.info("%-14s %4d", src.key, len(offers))
    run_at = store.save(db, results, today)
    for key, offers in results.items():
        before = store.previous_count(db, key, run_at)
        src = next(s for s in SOURCES if s.key == key)
        if not offers and before and not src.may_be_empty:
            _warn(f"Source {key} returned 0 items (previous run: {before}). Its page may have changed.")


def build_site(db, today: dt.date, out: Path) -> int:
    active_sources = {source.key for source in SOURCES}
    # Old Spanish records remain in SQLite for history, but must not leak into
    # the Portuguese edition after those adapters were removed from the registry.
    rows = [row for row in store.current(db, today) if row.get("source") in active_sources]
    runs = store.last_runs(db)
    status = [{"name": s.name, "run_at": runs.get(s.key, ("never", 0))[0].replace("T", " ").replace("Z", " UTC"),
               "n": runs.get(s.key, ("", 0))[1], "may_be_empty": s.may_be_empty} for s in SOURCES]
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    generated = dt.datetime.now(dt.timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    repo = os.environ.get("GITHUB_REPOSITORY")
    repo_url = f"https://github.com/{repo}" if repo else "https://github.com/pacocp/atalaya"

    out.mkdir(parents=True, exist_ok=True)
    data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    (out / "index.html").write_text(env.get_template("index.html").render(
        data_json=Markup(data), today=today.isoformat(), sources=[s.name for s in SOURCES], generated=generated,
    ), encoding="utf-8")
    (out / "about.html").write_text(env.get_template("about.html").render(
        status=status, generated=generated, repo_url=repo_url,
    ), encoding="utf-8")
    (out / "offers.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(prog="academic_offers")
    ap.add_argument("--build", action="store_true", help="only rebuild the site from the database")
    ap.add_argument("--only", help="comma-separated source keys to run")
    ap.add_argument("--boe-days", type=int, default=45, help="days of BOE to scan; covers 30-día-hábil deadlines")
    ap.add_argument("--db", default=str(ROOT / "data/offers.db"))
    ap.add_argument("--out", default=str(ROOT / "site"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    today = dt.date.today()
    db = store.connect(args.db)
    if not args.build:
        log.info("AI extraction: %s", f"on ({llm.MODEL}, max {llm.MAX_CALLS} new calls)" if llm.enabled() else "off")
        scrape(db, today, args.boe_days, set(args.only.split(",")) if args.only else None)
    n = build_site(db, today, Path(args.out))
    log.info("site built: %d current offers → %s", n, args.out)


if __name__ == "__main__":
    main()

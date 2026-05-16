"""Command-line interface for the E-commerce Price Monitoring System."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from src.config import configure_logging, get_settings
from src.database.repository import PriceMonitorRepository
from src.database.session import init_db, session_scope
from src.scrapers.demo_store import DemoStoreScraper
from src.services.alert_engine import AlertEngine
from src.services.demo_data import seed_demo_data
from src.services.export_service import ExcelExportService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description="Competitive e-commerce price monitoring commands.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create database tables.")

    seed_parser = subparsers.add_parser("seed-demo-data", help="Seed demo products and historical snapshots.")
    seed_parser.add_argument("--reset", action="store_true", help="Clear existing data before seeding.")

    scrape_parser = subparsers.add_parser("scrape", help="Scrape a configured source.")
    scrape_parser.add_argument("--source", default="demo_store", choices=["demo_store"], help="Scraper source name.")
    scrape_parser.add_argument(
        "--static",
        action="store_true",
        help="Use the static demo parser instead of launching Playwright.",
    )

    subparsers.add_parser("generate-alerts", help="Generate alerts from latest price changes.")

    export_parser = subparsers.add_parser("export-excel", help="Export Excel reports.")
    export_parser.add_argument("--output-dir", type=Path, default=None, help="Optional export output directory.")

    subparsers.add_parser("run-dashboard", help="Run the Streamlit dashboard.")
    return parser


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings)
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-db":
        init_db()
        print(f"Database initialized: {settings.database_url}")
        return 0

    if args.command == "seed-demo-data":
        init_db()
        with session_scope() as session:
            summary = seed_demo_data(session, reset=args.reset)
        print(f"Demo seed complete: {summary}")
        return 0

    if args.command == "scrape":
        init_db()
        return _run_scrape(args.source, prefer_playwright=not args.static)

    if args.command == "generate-alerts":
        init_db()
        with session_scope() as session:
            created = AlertEngine().generate_alerts(session)
        print(f"Generated {len(created)} new alerts.")
        return 0

    if args.command == "export-excel":
        init_db()
        with session_scope() as session:
            paths = ExcelExportService(output_dir=args.output_dir).export_all(session)
        print("Excel exports created:")
        for path in paths:
            print(f" - {path}")
        return 0

    if args.command == "run-dashboard":
        dashboard_path = settings.project_root / "src" / "dashboard" / "app.py"
        command = [sys.executable, "-m", "streamlit", "run", str(dashboard_path)]
        print("Starting Streamlit dashboard...")
        return subprocess.call(command, cwd=settings.project_root)

    parser.print_help()
    return 1


def _run_scrape(source: str, *, prefer_playwright: bool) -> int:
    with session_scope() as session:
        repo = PriceMonitorRepository(session)
        run = repo.create_scrape_run(source)
        try:
            if source != "demo_store":
                raise ValueError(f"Unsupported source: {source}")
            scraper = DemoStoreScraper(prefer_playwright=prefer_playwright)
            result = scraper.scrape_all()
            for snapshot in result.snapshots:
                repo.add_snapshot(snapshot)
            status = "success" if not result.errors else "partial_success"
            repo.finish_scrape_run(
                run,
                status=status,
                products_found=len(result.snapshots),
                errors_count=len(result.errors),
                error_message="\n".join(result.errors) if result.errors else None,
                finished_at=datetime.now(timezone.utc),
            )
            print(f"Scraped {len(result.snapshots)} snapshots from {source}. Status: {status}.")
            if result.errors:
                print("Errors:")
                for error in result.errors:
                    print(f" - {error}")
            return 0 if status == "success" else 2
        except Exception as exc:
            logger.exception("Scrape command failed")
            session.rollback()
            run = repo.create_scrape_run(source)
            repo.finish_scrape_run(
                run,
                status="failed",
                products_found=0,
                errors_count=1,
                error_message=str(exc),
                finished_at=datetime.now(timezone.utc),
            )
            print(f"Scrape failed: {exc}")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())

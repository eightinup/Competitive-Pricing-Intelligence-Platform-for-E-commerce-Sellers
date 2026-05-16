# E-commerce Price Monitoring System

A production-style competitive intelligence project for monitoring competitor prices, discounts, stock status, ratings, sellers, and historical market movements. It is built for analysts and pricing teams that need repeatable evidence, not one-off spreadsheet scraping.

This repository is designed as a portfolio-ready Data Extraction and Competitive Intelligence automation project. It runs locally with SQLite by default, uses Playwright for browser scraping, stores historical snapshots with SQLAlchemy, exports formatted Excel reports with pandas, and presents the results in a Streamlit dashboard.

## Business Problem

E-commerce teams need to know when competitors change price, launch a discount, go out of stock, switch sellers, or show rating movement. Manual checks are slow, inconsistent, and hard to audit. This system turns competitor product pages into a structured historical dataset with alerts and analyst-ready reporting.

Typical users:

- internet shops and marketplace sellers
- Kaspi, Amazon, Wildberries, Ozon, and Shopify sellers
- marketplace analysts
- e-commerce pricing teams
- freelance automation clients who need a reusable monitoring workflow

## Features

- Playwright scraper layer with configurable delay, timeout, retry count, and user agent
- Safe demo scraper using local mock HTML pages
- SQLite by default and PostgreSQL-ready through `DATABASE_URL`
- Historical price snapshots for daily competitor tracking
- Alert engine for price drops, price increases, stock changes, discount changes, seller changes, and rating changes
- Streamlit dashboard with KPIs, charts, filters, latest prices, history, alerts, product detail, and report export
- Formatted Excel exports for latest prices, price history, alerts, and competitor summary
- Demo seed dataset with 5 products, 3 competitors, and 60 historical price records
- pytest coverage for alert logic, price history helpers, scraper parsing, and Excel exports
- Ethical scraping note and architecture intended for marketplace-specific adapters

## Architecture

```text
src/
  cli.py                         CLI entry point
  config.py                      environment and path settings
  database/
    models.py                    SQLAlchemy ORM models
    session.py                   engine/session helpers
    repository.py                persistence boundary
  schemas/
    product_snapshot.py          Pydantic validation for scraped data
  scrapers/
    base.py                      scraper interface
    playwright_client.py         browser wrapper
    demo_store.py                local mock-page scraper
    selectors.yaml               selector configuration
  services/
    price_history.py             comparison helpers
    alert_engine.py              alert generation
    analytics_service.py         dashboard/report DataFrames
    export_service.py            Excel export workbooks
    demo_data.py                 deterministic demo seeding
  dashboard/
    app.py                       Streamlit app
    components/filters.py        reusable filters
```

## Database Schema

Core tables:

- `products`: SKU/internal name, product name, target URL, category, created timestamp
- `competitors`: competitor name, marketplace/source, base URL
- `price_snapshots`: product, competitor, scrape timestamp, current price, old price, discount, stock, rating, review count, seller, product URL, raw payload JSON
- `alerts`: product, competitor, alert type, message, severity, old value, new value, created timestamp, read status
- `scrape_runs`: scrape lifecycle status, source, products found, errors, timestamps

The design stores immutable snapshots so price history remains auditable over time.

## Installation

```bash
cd ecommerce-price-monitor
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

On this machine, the Python launcher may be used instead:

```bash
py -m pip install -r requirements.txt
py -m playwright install chromium
```

Copy environment defaults if you want to customize settings:

```bash
copy .env.example .env
```

Default local database:

```text
sqlite:///data/price_monitor.db
```

For PostgreSQL, set:

```text
DATABASE_URL=postgresql+psycopg://user:password@host:5432/price_monitor
```

## CLI Commands

Initialize database tables:

```bash
python -m src.cli init-db
```

Seed deterministic demo data:

```bash
python -m src.cli seed-demo-data
```

Reset and reseed demo data:

```bash
python -m src.cli seed-demo-data --reset
```

Scrape local mock competitor pages:

```bash
python -m src.cli scrape --source demo_store
```

Use the static parser fallback for demo pages:

```bash
python -m src.cli scrape --source demo_store --static
```

Generate alerts from latest snapshot changes:

```bash
python -m src.cli generate-alerts
```

Export Excel reports:

```bash
python -m src.cli export-excel
```

Run the dashboard:

```bash
python -m src.cli run-dashboard
```

or:

```bash
streamlit run src/dashboard/app.py
```

## Recommended Demo Flow

```bash
python -m src.cli init-db
python -m src.cli seed-demo-data --reset
python -m src.cli generate-alerts
python -m src.cli export-excel
streamlit run src/dashboard/app.py
```

The seed data includes realistic Kazakhstan-market prices in KZT for:

- iPhone 15 Pro 256GB
- Samsung Galaxy S24 256GB
- MacBook Air M2 13-inch
- Sony WH-1000XM5
- PlayStation 5 Disc Edition

Demo competitors:

- DemoMarket
- ShopRadar
- PriceHub

## Excel Reports

Exports are written to `data/exports/`:

- `latest_prices.xlsx`
- `price_history.xlsx`
- `alerts.xlsx`

Sheets include:

- Latest Prices
- Price History
- Alerts
- Competitor Summary

Formatting includes bold headers, frozen panes, autofilters, adjusted column widths, and conditional highlighting for price drops and high-severity alerts.

## Dashboard

The dashboard includes:

- Overview metrics
- Latest competitor prices
- Price history line charts
- Competitor price comparison
- Discount distribution
- Stock availability summary
- Alerts by severity
- Product detail view
- Export reports action

Filters:

- marketplace/source
- category
- product
- date range
- stock status
- alert type and severity on the alerts tab

Screenshot placeholders:

- `docs/screenshots/overview.png`
- `docs/screenshots/latest-prices.png`
- `docs/screenshots/alerts.png`

## Alert Logic

Default thresholds:

```text
PRICE_DROP_ALERT_PERCENT=10
PRICE_INCREASE_ALERT_PERCENT=10
```

Detected events:

- `price_drop`
- `price_increase`
- `out_of_stock`
- `back_in_stock`
- `seller_changed`
- `discount_started`
- `discount_removed`
- `rating_changed`

Example:

```text
DemoMarket reduced price for iPhone 15 Pro 256GB by 12.40%: 499 000 KZT -> 437 000 KZT
```

Severity levels:

- `LOW`
- `MEDIUM`
- `HIGH`
- `CRITICAL`

The alert engine compares each latest product/competitor snapshot to the previous snapshot and avoids creating duplicate alerts for the same old/new value pair.

## Demo Mode

Real marketplaces often have anti-bot rules, login walls, and CAPTCHAs. This project ships with reliable local mock pages under `data/mock_pages/` so the full extraction, database, alerts, reporting, and dashboard workflow works without scraping real websites.

The Playwright scraper opens local HTML files with browser-compatible selectors from `src/scrapers/selectors.yaml`. If Chromium is not installed, the demo scraper can fall back to a static parser for local pages.

## Legal and Ethical Scraping Note

This project does not bypass CAPTCHAs, authentication, paywalls, or anti-bot systems. For real deployments, only scrape websites where you have permission, contractual rights, or a clear legal basis. Respect robots.txt where applicable, rate limits, terms of service, and marketplace policies. Use official APIs or seller dashboards when available.

## Tests

```bash
pytest
```

or:

```bash
py -m pytest
```

Covered areas:

- price change calculations
- alert detection
- demo scraper parsing
- Excel workbook generation

## Portfolio Value

This is intentionally structured like a paid business automation project rather than a toy script. It demonstrates:

- browser-based extraction architecture
- validation of scraped data before persistence
- normalized database modeling
- historical data analysis
- alert generation for business events
- analyst-facing Excel exports
- Streamlit dashboarding
- testing and separation of concerns
- safe demo mode for reliable client presentations

A comparable freelance engagement could be positioned as a $2,000+ competitive intelligence automation starter system, with additional budget for marketplace-specific adapters, deployment, scheduling, and notification channels.

## Future Improvements

- PostgreSQL production deployment
- Docker and Docker Compose
- Airflow or Prefect scheduling
- Telegram and email alerts
- proxy support where legally allowed
- marketplace-specific adapters for Kaspi, Amazon, Wildberries, Ozon, and Shopify
- product matching by SKU, barcode, or normalized title
- competitor price index
- margin-based repricing recommendations
- FastAPI backend
- authentication and team roles
- cloud deployment

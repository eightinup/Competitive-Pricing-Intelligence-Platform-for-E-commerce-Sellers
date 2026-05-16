from decimal import Decimal

from src.scrapers.demo_store import DemoStoreScraper


def test_demo_scraper_static_mode_extracts_mock_products() -> None:
    result = DemoStoreScraper(prefer_playwright=False).scrape_all()

    assert result.errors == []
    assert len(result.snapshots) == 15
    iphone = next(snapshot for snapshot in result.snapshots if snapshot.sku == "IPHONE15PRO" and snapshot.source_name == "DemoMarket")
    assert iphone.product_name == "iPhone 15 Pro 256GB"
    assert iphone.current_price == 437000
    assert iphone.discount_percent == Decimal("12.4")

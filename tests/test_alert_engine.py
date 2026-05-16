from datetime import datetime, timezone
from decimal import Decimal

from src.database.models import Competitor, PriceSnapshot, Product
from src.services.alert_engine import AlertEngine, AlertType


def _snapshot(
    *,
    product: Product,
    competitor: Competitor,
    price: str,
    in_stock: bool = True,
    discount: str | None = None,
    rating: str | None = "4.8",
    seller: str = "Demo Seller",
) -> PriceSnapshot:
    return PriceSnapshot(
        product_id=product.id,
        competitor_id=competitor.id,
        product=product,
        competitor=competitor,
        scraped_at=datetime.now(timezone.utc),
        current_price=Decimal(price),
        old_price=None,
        discount_percent=Decimal(discount) if discount else None,
        in_stock=in_stock,
        rating=Decimal(rating) if rating else None,
        review_count=100,
        seller_name=seller,
        product_url="https://demo.local/product",
        raw_payload_json={},
    )


def test_alert_engine_detects_price_drop_and_discount_started() -> None:
    product = Product(id=1, sku="IPHONE15PRO", product_name="iPhone 15 Pro", target_url="https://demo.local", category="Smartphones")
    competitor = Competitor(id=1, name="DemoMarket", marketplace="Demo Marketplace", base_url="https://demo.local")
    previous = _snapshot(product=product, competitor=competitor, price="499000")
    current = _snapshot(product=product, competitor=competitor, price="437000", discount="12.40")

    alerts = AlertEngine(price_drop_threshold_percent=10).compare(previous, current)
    alert_types = {alert.alert_type for alert in alerts}

    assert AlertType.PRICE_DROP in alert_types
    assert AlertType.DISCOUNT_STARTED in alert_types


def test_alert_engine_detects_stock_and_seller_changes() -> None:
    product = Product(id=2, sku="MBAIRM2", product_name="MacBook Air M2", target_url="https://demo.local", category="Laptops")
    competitor = Competitor(id=3, name="PriceHub", marketplace="Aggregator", base_url="https://demo.local")
    previous = _snapshot(product=product, competitor=competitor, price="628000", in_stock=True, seller="PriceHub Direct")
    current = _snapshot(product=product, competitor=competitor, price="630000", in_stock=False, seller="TechLine KZ")

    alerts = AlertEngine().compare(previous, current)
    alert_types = {alert.alert_type for alert in alerts}

    assert AlertType.OUT_OF_STOCK in alert_types
    assert AlertType.SELLER_CHANGED in alert_types

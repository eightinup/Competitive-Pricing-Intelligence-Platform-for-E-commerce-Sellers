"""Deterministic demo dataset for local portfolio demonstrations."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from loguru import logger
from sqlalchemy.orm import Session

from src.config import get_settings
from src.database.repository import PriceMonitorRepository
from src.schemas.product_snapshot import ProductSnapshot


def seed_demo_data(session: Session, *, reset: bool = False) -> dict[str, int | str]:
    """Seed products, competitors, and multi-day price snapshots."""
    repo = PriceMonitorRepository(session)
    if reset:
        repo.reset_demo_data()
    elif repo.count_products() > 0:
        return {"status": "skipped_existing_data", "snapshots": 0}

    settings = get_settings()
    catalog = _load_catalog(settings.seed_dir / "demo_catalog.json")
    snapshots_created = 0
    latest_anchor = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
    start_at = latest_anchor - timedelta(days=3)

    for day_index in range(4):
        scraped_at = start_at + timedelta(days=day_index)
        for product in catalog["products"]:
            for competitor in catalog["competitors"]:
                scenario = _scenario_for(product["sku"], competitor["name"], day_index)
                current_price = Decimal(str(product["base_prices"][competitor["name"]])) + scenario["delta"]
                old_price = scenario.get("old_price")
                discount = scenario.get("discount_percent")
                snapshot = ProductSnapshot(
                    sku=product["sku"],
                    product_name=product["product_name"],
                    current_price=current_price,
                    old_price=old_price,
                    discount_percent=discount,
                    in_stock=scenario.get("in_stock", True),
                    rating=scenario.get("rating", Decimal(str(product["rating"]))),
                    review_count=product["review_count"] + day_index * 3,
                    seller_name=scenario.get("seller_name", competitor["default_seller"]),
                    product_url=f"{competitor['base_url']}/products/{product['slug']}",
                    marketplace=competitor["marketplace"],
                    source_name=competitor["name"],
                    category=product["category"],
                    scraped_at=scraped_at,
                    raw_payload={"seed": True, "day_index": day_index},
                )
                repo.add_snapshot(snapshot, base_url=competitor["base_url"])
                snapshots_created += 1

    logger.info("Seeded {} demo snapshots", snapshots_created)
    return {
        "status": "seeded",
        "products": len(catalog["products"]),
        "competitors": len(catalog["competitors"]),
        "snapshots": snapshots_created,
    }


def _load_catalog(path: Path) -> dict[str, list[dict[str, object]]]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _scenario_for(sku: str, competitor_name: str, day_index: int) -> dict[str, object]:
    """Return controlled market changes so alerts demonstrate real scenarios."""
    baseline_delta = Decimal(day_index * 1500)
    scenario: dict[str, object] = {"delta": baseline_delta}

    if day_index == 3 and sku == "IPHONE15PRO" and competitor_name == "DemoMarket":
        scenario.update({"delta": Decimal("-62000"), "old_price": Decimal("499000"), "discount_percent": Decimal("12.40")})
    elif day_index == 3 and sku == "GALAXYS24" and competitor_name == "ShopRadar":
        scenario.update({"in_stock": False, "delta": Decimal("-5000")})
    elif day_index == 3 and sku == "MBAIRM2" and competitor_name == "PriceHub":
        scenario.update({"seller_name": "TechLine KZ"})
    elif day_index == 3 and sku == "SONYXM5" and competitor_name == "DemoMarket":
        scenario.update({"old_price": Decimal("179990"), "discount_percent": Decimal("17.00"), "delta": Decimal("-25000")})
    elif day_index == 3 and sku == "PS5" and competitor_name == "ShopRadar":
        scenario.update({"delta": Decimal("55000"), "rating": Decimal("4.30")})
    return scenario

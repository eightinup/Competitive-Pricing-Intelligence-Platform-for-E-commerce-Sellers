"""Repository methods that keep database access out of business services."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from src.database.models import Alert, Competitor, PriceSnapshot, Product, ScrapeRun
from src.schemas.product_snapshot import ProductSnapshot


class PriceMonitorRepository:
    """Persistence API for the price monitoring domain."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_product(
        self,
        *,
        sku: str,
        product_name: str,
        target_url: str,
        category: str | None,
    ) -> Product:
        product = self.session.scalar(select(Product).where(Product.sku == sku))
        if product:
            product.product_name = product_name
            product.target_url = target_url
            product.category = category
            return product
        product = Product(
            sku=sku,
            product_name=product_name,
            target_url=target_url,
            category=category,
        )
        self.session.add(product)
        self.session.flush()
        return product

    def get_or_create_competitor(
        self,
        *,
        name: str,
        marketplace: str,
        base_url: str | None,
    ) -> Competitor:
        competitor = self.session.scalar(
            select(Competitor).where(Competitor.name == name, Competitor.marketplace == marketplace)
        )
        if competitor:
            competitor.base_url = base_url or competitor.base_url
            return competitor
        competitor = Competitor(name=name, marketplace=marketplace, base_url=base_url)
        self.session.add(competitor)
        self.session.flush()
        return competitor

    def add_snapshot(self, snapshot: ProductSnapshot, base_url: str | None = None) -> PriceSnapshot:
        product = self.get_or_create_product(
            sku=snapshot.sku,
            product_name=snapshot.product_name,
            target_url=snapshot.product_url,
            category=snapshot.category,
        )
        competitor = self.get_or_create_competitor(
            name=snapshot.source_name,
            marketplace=snapshot.marketplace,
            base_url=base_url,
        )
        db_snapshot = PriceSnapshot(
            product_id=product.id,
            competitor_id=competitor.id,
            scraped_at=snapshot.scraped_at,
            current_price=snapshot.current_price,
            old_price=snapshot.old_price,
            discount_percent=snapshot.discount_percent,
            in_stock=snapshot.in_stock,
            rating=snapshot.rating,
            review_count=snapshot.review_count,
            seller_name=snapshot.seller_name,
            product_url=snapshot.product_url,
            raw_payload_json=snapshot.model_dump(mode="json"),
        )
        self.session.add(db_snapshot)
        self.session.flush()
        return db_snapshot

    def create_scrape_run(self, source: str) -> ScrapeRun:
        run = ScrapeRun(status="running", source=source, products_found=0, errors_count=0)
        self.session.add(run)
        self.session.flush()
        return run

    def finish_scrape_run(
        self,
        run: ScrapeRun,
        *,
        status: str,
        products_found: int,
        errors_count: int = 0,
        error_message: str | None = None,
        finished_at: datetime,
    ) -> ScrapeRun:
        run.status = status
        run.products_found = products_found
        run.errors_count = errors_count
        run.error_message = error_message
        run.finished_at = finished_at
        self.session.flush()
        return run

    def get_previous_snapshot(self, snapshot: PriceSnapshot) -> PriceSnapshot | None:
        return self.session.scalar(
            select(PriceSnapshot)
            .where(
                PriceSnapshot.product_id == snapshot.product_id,
                PriceSnapshot.competitor_id == snapshot.competitor_id,
                PriceSnapshot.scraped_at < snapshot.scraped_at,
            )
            .options(selectinload(PriceSnapshot.product), selectinload(PriceSnapshot.competitor))
            .order_by(PriceSnapshot.scraped_at.desc(), PriceSnapshot.id.desc())
            .limit(1)
        )

    def list_latest_snapshots(self) -> list[PriceSnapshot]:
        snapshots = self.session.scalars(
            select(PriceSnapshot)
            .options(selectinload(PriceSnapshot.product), selectinload(PriceSnapshot.competitor))
            .order_by(PriceSnapshot.product_id, PriceSnapshot.competitor_id, PriceSnapshot.scraped_at.desc())
        ).all()
        latest_by_pair: dict[tuple[int, int], PriceSnapshot] = {}
        for snapshot in snapshots:
            latest_by_pair.setdefault((snapshot.product_id, snapshot.competitor_id), snapshot)
        return list(latest_by_pair.values())

    def list_snapshots(self) -> list[PriceSnapshot]:
        return self.session.scalars(
            select(PriceSnapshot)
            .options(selectinload(PriceSnapshot.product), selectinload(PriceSnapshot.competitor))
            .order_by(PriceSnapshot.scraped_at.desc(), PriceSnapshot.id.desc())
        ).all()

    def list_alerts(self, unread_only: bool = False) -> list[Alert]:
        query = (
            select(Alert)
            .options(selectinload(Alert.product), selectinload(Alert.competitor))
            .order_by(Alert.created_at.desc(), Alert.id.desc())
        )
        if unread_only:
            query = query.where(Alert.is_read.is_(False))
        return self.session.scalars(query).all()

    def alert_exists(
        self,
        *,
        product_id: int,
        competitor_id: int,
        alert_type: str,
        old_value: str | None,
        new_value: str | None,
    ) -> bool:
        count = self.session.scalar(
            select(func.count(Alert.id)).where(
                Alert.product_id == product_id,
                Alert.competitor_id == competitor_id,
                Alert.alert_type == alert_type,
                Alert.old_value == old_value,
                Alert.new_value == new_value,
            )
        )
        return bool(count)

    def add_alert(
        self,
        *,
        product_id: int,
        competitor_id: int,
        alert_type: str,
        message: str,
        severity: str,
        old_value: str | None,
        new_value: str | None,
    ) -> Alert:
        alert = Alert(
            product_id=product_id,
            competitor_id=competitor_id,
            alert_type=alert_type,
            message=message,
            severity=severity,
            old_value=old_value,
            new_value=new_value,
        )
        self.session.add(alert)
        self.session.flush()
        return alert

    def reset_demo_data(self) -> None:
        """Clear all domain data for a deterministic demo reseed."""
        for model in (Alert, PriceSnapshot, Product, Competitor, ScrapeRun):
            self.session.execute(delete(model))
        self.session.flush()

    def count_products(self) -> int:
        return int(self.session.scalar(select(func.count(Product.id))) or 0)

    @staticmethod
    def decimal_to_float(value: Decimal | None) -> float | None:
        return None if value is None else float(value)

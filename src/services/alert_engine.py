"""Alert generation based on differences between consecutive snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from loguru import logger
from sqlalchemy.orm import Session

from src.config import get_settings
from src.database.models import PriceSnapshot
from src.database.repository import PriceMonitorRepository
from src.services.price_history import discount_is_active, percent_change, value_changed


class AlertSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertType(StrEnum):
    PRICE_DROP = "price_drop"
    PRICE_INCREASE = "price_increase"
    OUT_OF_STOCK = "out_of_stock"
    BACK_IN_STOCK = "back_in_stock"
    SELLER_CHANGED = "seller_changed"
    DISCOUNT_STARTED = "discount_started"
    DISCOUNT_REMOVED = "discount_removed"
    RATING_CHANGED = "rating_changed"


@dataclass(frozen=True)
class AlertCandidate:
    """Validated alert proposal before it is persisted."""

    product_id: int
    competitor_id: int
    alert_type: AlertType
    message: str
    severity: AlertSeverity
    old_value: str | None
    new_value: str | None


class AlertEngine:
    """Compares current snapshots with their previous versions and emits alerts."""

    def __init__(
        self,
        *,
        price_drop_threshold_percent: float | None = None,
        price_increase_threshold_percent: float | None = None,
        currency: str | None = None,
    ) -> None:
        settings = get_settings()
        self.price_drop_threshold = Decimal(str(price_drop_threshold_percent or settings.price_drop_alert_percent))
        self.price_increase_threshold = Decimal(
            str(price_increase_threshold_percent or settings.price_increase_alert_percent)
        )
        self.currency = currency or settings.currency

    def compare(self, previous: PriceSnapshot, current: PriceSnapshot) -> list[AlertCandidate]:
        """Build alert candidates from two snapshots for the same product/competitor."""
        alerts: list[AlertCandidate] = []
        product_name = current.product.product_name if current.product else f"Product #{current.product_id}"
        competitor_name = current.competitor.name if current.competitor else f"Competitor #{current.competitor_id}"

        price_change = percent_change(previous.current_price, current.current_price)
        if price_change <= -self.price_drop_threshold:
            absolute_drop = abs(price_change)
            alerts.append(
                AlertCandidate(
                    product_id=current.product_id,
                    competitor_id=current.competitor_id,
                    alert_type=AlertType.PRICE_DROP,
                    severity=self._price_severity(absolute_drop),
                    old_value=self._money(previous.current_price),
                    new_value=self._money(current.current_price),
                    message=(
                        f"{competitor_name} reduced price for {product_name} by {absolute_drop}%: "
                        f"{self._money(previous.current_price)} -> {self._money(current.current_price)}"
                    ),
                )
            )
        elif price_change >= self.price_increase_threshold:
            alerts.append(
                AlertCandidate(
                    product_id=current.product_id,
                    competitor_id=current.competitor_id,
                    alert_type=AlertType.PRICE_INCREASE,
                    severity=self._price_severity(price_change),
                    old_value=self._money(previous.current_price),
                    new_value=self._money(current.current_price),
                    message=(
                        f"{competitor_name} increased price for {product_name} by {price_change}%: "
                        f"{self._money(previous.current_price)} -> {self._money(current.current_price)}"
                    ),
                )
            )

        if previous.in_stock and not current.in_stock:
            alerts.append(
                AlertCandidate(
                    product_id=current.product_id,
                    competitor_id=current.competitor_id,
                    alert_type=AlertType.OUT_OF_STOCK,
                    severity=AlertSeverity.HIGH,
                    old_value="in_stock",
                    new_value="out_of_stock",
                    message=f"{product_name} went out of stock at {competitor_name}.",
                )
            )
        elif not previous.in_stock and current.in_stock:
            alerts.append(
                AlertCandidate(
                    product_id=current.product_id,
                    competitor_id=current.competitor_id,
                    alert_type=AlertType.BACK_IN_STOCK,
                    severity=AlertSeverity.MEDIUM,
                    old_value="out_of_stock",
                    new_value="in_stock",
                    message=f"{product_name} is back in stock at {competitor_name}.",
                )
            )

        previous_discount = discount_is_active(previous)
        current_discount = discount_is_active(current)
        if not previous_discount and current_discount:
            alerts.append(
                AlertCandidate(
                    product_id=current.product_id,
                    competitor_id=current.competitor_id,
                    alert_type=AlertType.DISCOUNT_STARTED,
                    severity=AlertSeverity.MEDIUM,
                    old_value=str(previous.discount_percent or 0),
                    new_value=str(current.discount_percent or 0),
                    message=f"{competitor_name} started a {current.discount_percent}% discount for {product_name}.",
                )
            )
        elif previous_discount and not current_discount:
            alerts.append(
                AlertCandidate(
                    product_id=current.product_id,
                    competitor_id=current.competitor_id,
                    alert_type=AlertType.DISCOUNT_REMOVED,
                    severity=AlertSeverity.LOW,
                    old_value=str(previous.discount_percent or 0),
                    new_value=str(current.discount_percent or 0),
                    message=f"{competitor_name} removed the discount for {product_name}.",
                )
            )

        if value_changed(previous.seller_name, current.seller_name):
            alerts.append(
                AlertCandidate(
                    product_id=current.product_id,
                    competitor_id=current.competitor_id,
                    alert_type=AlertType.SELLER_CHANGED,
                    severity=AlertSeverity.MEDIUM,
                    old_value=previous.seller_name,
                    new_value=current.seller_name,
                    message=(
                        f"Seller changed for {product_name} at {competitor_name}: "
                        f"{previous.seller_name or 'unknown'} -> {current.seller_name or 'unknown'}."
                    ),
                )
            )

        if previous.rating is not None and current.rating is not None and previous.rating != current.rating:
            alerts.append(
                AlertCandidate(
                    product_id=current.product_id,
                    competitor_id=current.competitor_id,
                    alert_type=AlertType.RATING_CHANGED,
                    severity=AlertSeverity.LOW,
                    old_value=str(previous.rating),
                    new_value=str(current.rating),
                    message=(
                        f"Rating changed for {product_name} at {competitor_name}: "
                        f"{previous.rating} -> {current.rating}."
                    ),
                )
            )

        return alerts

    def generate_alerts(self, session: Session) -> list[AlertCandidate]:
        """Generate and persist non-duplicate alerts for the latest snapshots."""
        repo = PriceMonitorRepository(session)
        created: list[AlertCandidate] = []
        for current in repo.list_latest_snapshots():
            previous = repo.get_previous_snapshot(current)
            if not previous:
                continue
            for candidate in self.compare(previous, current):
                if repo.alert_exists(
                    product_id=candidate.product_id,
                    competitor_id=candidate.competitor_id,
                    alert_type=candidate.alert_type.value,
                    old_value=candidate.old_value,
                    new_value=candidate.new_value,
                ):
                    continue
                repo.add_alert(
                    product_id=candidate.product_id,
                    competitor_id=candidate.competitor_id,
                    alert_type=candidate.alert_type.value,
                    message=candidate.message,
                    severity=candidate.severity.value,
                    old_value=candidate.old_value,
                    new_value=candidate.new_value,
                )
                created.append(candidate)
        logger.info("Generated {} new alerts", len(created))
        return created

    def _money(self, value: Decimal) -> str:
        formatted = f"{value:,.0f}".replace(",", " ")
        return f"{formatted} {self.currency}"

    @staticmethod
    def _price_severity(change_percent: Decimal) -> AlertSeverity:
        if change_percent >= Decimal("25"):
            return AlertSeverity.CRITICAL
        if change_percent >= Decimal("15"):
            return AlertSeverity.HIGH
        return AlertSeverity.MEDIUM

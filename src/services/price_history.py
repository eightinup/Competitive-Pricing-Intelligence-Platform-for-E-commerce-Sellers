"""Price history comparison helpers."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol


class SnapshotLike(Protocol):
    """Minimal snapshot contract used by comparison helpers and tests."""

    current_price: Decimal
    old_price: Decimal | None
    discount_percent: Decimal | None
    in_stock: bool
    rating: Decimal | None
    seller_name: str | None


def percent_change(previous_value: Decimal, current_value: Decimal) -> Decimal:
    """Return signed percent change from previous to current."""
    if previous_value == 0:
        return Decimal("0.00")
    change = (current_value - previous_value) / previous_value * Decimal("100")
    return change.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def discount_is_active(snapshot: SnapshotLike) -> bool:
    """Return whether a snapshot has an active discount."""
    return bool(snapshot.discount_percent and snapshot.discount_percent > 0)


def value_changed(previous: object | None, current: object | None) -> bool:
    """Compare nullable values after trimming strings."""
    if isinstance(previous, str):
        previous = previous.strip()
    if isinstance(current, str):
        current = current.strip()
    return previous != current

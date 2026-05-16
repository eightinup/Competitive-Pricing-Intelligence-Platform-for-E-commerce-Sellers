from decimal import Decimal

from src.services.price_history import percent_change


def test_percent_change_returns_signed_percent() -> None:
    assert percent_change(Decimal("500000"), Decimal("437000")) == Decimal("-12.60")
    assert percent_change(Decimal("100"), Decimal("115")) == Decimal("15.00")


def test_percent_change_handles_zero_previous_value() -> None:
    assert percent_change(Decimal("0"), Decimal("100")) == Decimal("0.00")

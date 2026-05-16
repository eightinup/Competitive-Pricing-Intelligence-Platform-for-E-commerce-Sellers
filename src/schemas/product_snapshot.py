"""Validated schemas returned by scraper adapters."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProductSnapshot(BaseModel):
    """Normalized product data captured during one scrape event."""

    model_config = ConfigDict(str_strip_whitespace=True)

    sku: str = Field(..., min_length=2, description="Internal or marketplace product key")
    product_name: str = Field(..., min_length=2)
    current_price: Decimal = Field(..., ge=0)
    old_price: Decimal | None = Field(default=None, ge=0)
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    in_stock: bool = True
    rating: Decimal | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    seller_name: str | None = None
    product_url: str = Field(..., min_length=5)
    marketplace: str = Field(..., min_length=2)
    source_name: str = Field(..., min_length=2)
    category: str | None = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("current_price", "old_price", "discount_percent", "rating", mode="before")
    @classmethod
    def coerce_decimal(cls, value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        return Decimal(str(value))

    @model_validator(mode="after")
    def calculate_discount_when_missing(self) -> "ProductSnapshot":
        if self.discount_percent is None and self.old_price and self.old_price > self.current_price:
            discount = (self.old_price - self.current_price) / self.old_price * Decimal("100")
            self.discount_percent = discount.quantize(Decimal("0.01"))
        if self.old_price is not None and self.old_price < self.current_price:
            self.old_price = None
        return self

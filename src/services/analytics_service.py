"""Analytics helpers used by the dashboard and Excel export service."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
from sqlalchemy.orm import Session

from src.database.models import Alert, PriceSnapshot
from src.database.repository import PriceMonitorRepository
from src.services.price_history import percent_change


def snapshots_to_dataframe(snapshots: list[PriceSnapshot], include_change: bool = False) -> pd.DataFrame:
    """Convert ORM snapshots to a pandas DataFrame."""
    repo_rows = []
    for snapshot in snapshots:
        row = {
            "snapshot_id": snapshot.id,
            "sku": snapshot.product.sku,
            "product_name": snapshot.product.product_name,
            "category": snapshot.product.category,
            "competitor": snapshot.competitor.name,
            "marketplace": snapshot.competitor.marketplace,
            "scraped_at": snapshot.scraped_at,
            "current_price": float(snapshot.current_price),
            "old_price": _float_or_none(snapshot.old_price),
            "discount_percent": _float_or_none(snapshot.discount_percent) or 0.0,
            "in_stock": snapshot.in_stock,
            "rating": _float_or_none(snapshot.rating),
            "review_count": snapshot.review_count,
            "seller_name": snapshot.seller_name,
            "product_url": snapshot.product_url,
        }
        if include_change:
            row["previous_price"] = None
            row["price_change_percent"] = None
        repo_rows.append(row)
    return pd.DataFrame(repo_rows)


def latest_prices_dataframe(session: Session) -> pd.DataFrame:
    """Return latest product/competitor prices with prior price deltas."""
    repo = PriceMonitorRepository(session)
    rows = []
    for snapshot in repo.list_latest_snapshots():
        previous = repo.get_previous_snapshot(snapshot)
        change_percent = None
        previous_price = None
        if previous:
            previous_price = float(previous.current_price)
            change_percent = float(percent_change(previous.current_price, snapshot.current_price))
        rows.append(
            {
                "sku": snapshot.product.sku,
                "product_name": snapshot.product.product_name,
                "category": snapshot.product.category,
                "competitor": snapshot.competitor.name,
                "marketplace": snapshot.competitor.marketplace,
                "scraped_at": snapshot.scraped_at,
                "current_price": float(snapshot.current_price),
                "previous_price": previous_price,
                "price_change_percent": change_percent,
                "old_price": _float_or_none(snapshot.old_price),
                "discount_percent": _float_or_none(snapshot.discount_percent) or 0.0,
                "in_stock": snapshot.in_stock,
                "rating": _float_or_none(snapshot.rating),
                "review_count": snapshot.review_count,
                "seller_name": snapshot.seller_name,
                "product_url": snapshot.product_url,
            }
        )
    return pd.DataFrame(rows)


def price_history_dataframe(session: Session) -> pd.DataFrame:
    repo = PriceMonitorRepository(session)
    return snapshots_to_dataframe(repo.list_snapshots())


def alerts_dataframe(session: Session) -> pd.DataFrame:
    repo = PriceMonitorRepository(session)
    rows = [_alert_to_row(alert) for alert in repo.list_alerts()]
    return pd.DataFrame(rows)


def competitor_summary_dataframe(session: Session) -> pd.DataFrame:
    latest = latest_prices_dataframe(session)
    if latest.empty:
        return pd.DataFrame()
    summary = (
        latest.groupby(["competitor", "marketplace"], dropna=False)
        .agg(
            monitored_products=("sku", "nunique"),
            average_price=("current_price", "mean"),
            average_discount=("discount_percent", "mean"),
            out_of_stock_products=("in_stock", lambda values: int((~values).sum())),
            min_price=("current_price", "min"),
            max_price=("current_price", "max"),
        )
        .reset_index()
    )
    return summary


def dashboard_metrics(session: Session) -> dict[str, float | int | str]:
    latest = latest_prices_dataframe(session)
    alerts = alerts_dataframe(session)
    if latest.empty:
        return {
            "total_products": 0,
            "total_competitors": 0,
            "average_discount": 0.0,
            "active_alerts": 0,
            "out_of_stock_products": 0,
            "biggest_price_drop_today": "0%",
        }
    drops = latest["price_change_percent"].dropna()
    biggest_drop = drops.min() if not drops.empty else 0.0
    return {
        "total_products": int(latest["sku"].nunique()),
        "total_competitors": int(latest["competitor"].nunique()),
        "average_discount": round(float(latest["discount_percent"].mean()), 2),
        "active_alerts": int(len(alerts[alerts["is_read"] == False])) if not alerts.empty else 0,  # noqa: E712
        "out_of_stock_products": int((~latest["in_stock"]).sum()),
        "biggest_price_drop_today": f"{round(float(biggest_drop), 2)}%",
    }


def _alert_to_row(alert: Alert) -> dict[str, object]:
    return {
        "alert_id": alert.id,
        "created_at": alert.created_at,
        "severity": alert.severity,
        "alert_type": alert.alert_type,
        "product_name": alert.product.product_name,
        "sku": alert.product.sku,
        "competitor": alert.competitor.name,
        "marketplace": alert.competitor.marketplace,
        "old_value": alert.old_value,
        "new_value": alert.new_value,
        "message": alert.message,
        "is_read": alert.is_read,
    }


def _float_or_none(value: Decimal | None) -> float | None:
    return None if value is None else float(value)

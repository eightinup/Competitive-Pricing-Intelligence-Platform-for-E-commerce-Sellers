"""Shared Streamlit filter helpers."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st


def sidebar_filters(latest: pd.DataFrame, history: pd.DataFrame) -> dict[str, object]:
    """Render sidebar filters and return selected values."""
    st.sidebar.header("Filters")

    marketplaces = sorted(latest["marketplace"].dropna().unique().tolist()) if not latest.empty else []
    categories = sorted(latest["category"].dropna().unique().tolist()) if not latest.empty else []
    products = sorted(latest["product_name"].dropna().unique().tolist()) if not latest.empty else []

    selected_marketplaces = st.sidebar.multiselect("Marketplace / source", marketplaces, default=marketplaces)
    selected_categories = st.sidebar.multiselect("Category", categories, default=categories)
    selected_products = st.sidebar.multiselect("Product", products, default=products)
    stock_status = st.sidebar.selectbox("Stock status", ["All", "In stock", "Out of stock"])

    min_date: date | None = None
    max_date: date | None = None
    if not history.empty and "scraped_at" in history.columns:
        dates = pd.to_datetime(history["scraped_at"]).dt.date
        min_date = dates.min()
        max_date = dates.max()
    date_range = st.sidebar.date_input(
        "Date range",
        value=(min_date, max_date) if min_date and max_date else None,
        min_value=min_date,
        max_value=max_date,
    )

    return {
        "marketplaces": selected_marketplaces,
        "categories": selected_categories,
        "products": selected_products,
        "stock_status": stock_status,
        "date_range": date_range,
    }


def apply_latest_filters(dataframe: pd.DataFrame, filters: dict[str, object]) -> pd.DataFrame:
    """Apply common filters to latest-price data."""
    filtered = dataframe.copy()
    if filtered.empty:
        return filtered
    filtered = _filter_list(filtered, "marketplace", filters["marketplaces"])
    filtered = _filter_list(filtered, "category", filters["categories"])
    filtered = _filter_list(filtered, "product_name", filters["products"])
    stock_status = filters["stock_status"]
    if stock_status == "In stock":
        filtered = filtered[filtered["in_stock"]]
    elif stock_status == "Out of stock":
        filtered = filtered[~filtered["in_stock"]]
    return filtered


def apply_history_filters(dataframe: pd.DataFrame, filters: dict[str, object]) -> pd.DataFrame:
    """Apply common filters to historical price data."""
    filtered = apply_latest_filters(dataframe, filters)
    if filtered.empty or "scraped_at" not in filtered.columns:
        return filtered
    date_range = filters["date_range"]
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        if start_date and end_date:
            dates = pd.to_datetime(filtered["scraped_at"]).dt.date
            filtered = filtered[(dates >= start_date) & (dates <= end_date)]
    return filtered


def _filter_list(dataframe: pd.DataFrame, column: str, values: object) -> pd.DataFrame:
    if values:
        return dataframe[dataframe[column].isin(values)]
    return dataframe

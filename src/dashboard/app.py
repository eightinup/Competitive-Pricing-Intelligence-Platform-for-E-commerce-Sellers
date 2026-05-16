"""Professional Streamlit dashboard for competitive price monitoring."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from src.config import get_settings
from src.database.session import init_db, session_scope
from src.services.analytics_service import (
    alerts_dataframe,
    competitor_summary_dataframe,
    dashboard_metrics,
    latest_prices_dataframe,
    price_history_dataframe,
)
from src.services.export_service import ExcelExportService
from src.dashboard.components.filters import apply_history_filters, apply_latest_filters, sidebar_filters


st.set_page_config(
    page_title="E-commerce Price Monitor",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.3rem; }
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 14px 16px;
    }
    div[data-testid="stMetricLabel"] p { color: #475569; font-size: 0.9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=30)
def load_dashboard_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    init_db()
    with session_scope() as session:
        latest = latest_prices_dataframe(session)
        history = price_history_dataframe(session)
        alerts = alerts_dataframe(session)
        summary = competitor_summary_dataframe(session)
        metrics = dashboard_metrics(session)
    return latest, history, alerts, summary, metrics


def main() -> None:
    settings = get_settings()
    st.title("E-commerce Price Monitoring System")
    st.caption("Competitive intelligence dashboard for marketplace pricing, discounts, stock, sellers, and alerts.")

    latest, history, alerts, summary, metrics = load_dashboard_data()
    if latest.empty:
        st.info(
            "No monitoring data found yet. Run `python -m src.cli seed-demo-data`, then "
            "`python -m src.cli generate-alerts` to populate the dashboard."
        )
        return

    filters = sidebar_filters(latest, history)
    latest_filtered = apply_latest_filters(latest, filters)
    history_filtered = apply_history_filters(history, filters)

    tabs = st.tabs(
        [
            "Overview",
            "Latest Competitor Prices",
            "Price History",
            "Alerts",
            "Product Detail",
            "Export Reports",
        ]
    )

    with tabs[0]:
        render_overview(metrics, latest_filtered, history_filtered, alerts)

    with tabs[1]:
        render_latest_prices(latest_filtered, settings.currency)

    with tabs[2]:
        render_price_history(history_filtered, settings.currency)

    with tabs[3]:
        render_alerts(alerts)

    with tabs[4]:
        render_product_detail(latest_filtered, history_filtered, settings.currency)

    with tabs[5]:
        render_exports(summary)


def render_overview(
    metrics: dict[str, object],
    latest: pd.DataFrame,
    history: pd.DataFrame,
    alerts: pd.DataFrame,
) -> None:
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Products", metrics["total_products"])
    col2.metric("Competitors", metrics["total_competitors"])
    col3.metric("Avg discount", f"{metrics['average_discount']}%")
    col4.metric("Active alerts", metrics["active_alerts"])
    col5.metric("Out of stock", metrics["out_of_stock_products"])
    col6.metric("Biggest drop", metrics["biggest_price_drop_today"])

    chart_col, side_col = st.columns([2, 1])
    with chart_col:
        st.subheader("Price History")
        if history.empty:
            st.info("No historical rows match the current filters.")
        else:
            line = (
                alt.Chart(history)
                .mark_line(point=True)
                .encode(
                    x=alt.X("scraped_at:T", title="Scrape date"),
                    y=alt.Y("current_price:Q", title="Current price"),
                    color="competitor:N",
                    detail="sku:N",
                    tooltip=["product_name", "competitor", "current_price", "scraped_at"],
                )
            )
            st.altair_chart(line, use_container_width=True)

    with side_col:
        st.subheader("Stock Availability")
        if latest.empty:
            st.info("No stock data.")
        else:
            stock = latest.assign(stock_status=latest["in_stock"].map({True: "In stock", False: "Out of stock"}))
            stock_counts = stock.groupby("stock_status").size().reset_index(name="count")
            st.altair_chart(
                alt.Chart(stock_counts)
                .mark_bar()
                .encode(x="stock_status:N", y="count:Q", color="stock_status:N", tooltip=["stock_status", "count"]),
                use_container_width=True,
            )

    lower_col, alert_col = st.columns(2)
    with lower_col:
        st.subheader("Discount Distribution")
        if not latest.empty:
            st.altair_chart(
                alt.Chart(latest)
                .mark_bar()
                .encode(
                    x=alt.X("discount_percent:Q", bin=alt.Bin(maxbins=8), title="Discount percent"),
                    y=alt.Y("count():Q", title="Products"),
                    tooltip=["count()"],
                ),
                use_container_width=True,
            )
    with alert_col:
        st.subheader("Alerts by Severity")
        if alerts.empty:
            st.info("No alerts generated yet.")
        else:
            alert_counts = alerts.groupby("severity").size().reset_index(name="count")
            st.altair_chart(
                alt.Chart(alert_counts)
                .mark_bar()
                .encode(x="severity:N", y="count:Q", color="severity:N", tooltip=["severity", "count"]),
                use_container_width=True,
            )


def render_latest_prices(latest: pd.DataFrame, currency: str) -> None:
    st.subheader("Latest Competitor Prices")
    if latest.empty:
        st.info("No latest price rows match the filters.")
        return
    display = latest.sort_values(["product_name", "current_price"])
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "current_price": st.column_config.NumberColumn("Current price", format=f"%.0f {currency}"),
            "previous_price": st.column_config.NumberColumn("Previous price", format=f"%.0f {currency}"),
            "price_change_percent": st.column_config.NumberColumn("Price change", format="%.2f%%"),
            "product_url": st.column_config.LinkColumn("Product URL"),
        },
    )

    comparison = (
        latest.groupby(["product_name", "competitor"], as_index=False)["current_price"].min()
        if not latest.empty
        else pd.DataFrame()
    )
    if not comparison.empty:
        st.subheader("Competitor Price Comparison")
        st.altair_chart(
            alt.Chart(comparison)
            .mark_bar()
            .encode(
                x=alt.X("product_name:N", sort="-y", title="Product"),
                y=alt.Y("current_price:Q", title=f"Price ({currency})"),
                color="competitor:N",
                tooltip=["product_name", "competitor", "current_price"],
            ),
            use_container_width=True,
        )


def render_price_history(history: pd.DataFrame, currency: str) -> None:
    st.subheader("Price History")
    if history.empty:
        st.info("No historical rows match the filters.")
        return
    st.altair_chart(
        alt.Chart(history)
        .mark_line(point=True)
        .encode(
            x=alt.X("scraped_at:T", title="Scrape date"),
            y=alt.Y("current_price:Q", title=f"Price ({currency})"),
            color="competitor:N",
            row=alt.Row("product_name:N", header=alt.Header(labelLimit=260)),
            tooltip=["product_name", "competitor", "current_price", "discount_percent", "in_stock"],
        )
        .properties(height=145),
        use_container_width=True,
    )
    st.dataframe(history.sort_values("scraped_at", ascending=False), use_container_width=True, hide_index=True)


def render_alerts(alerts: pd.DataFrame) -> None:
    st.subheader("Alerts")
    if alerts.empty:
        st.info("No alerts generated yet.")
        return
    alert_types = sorted(alerts["alert_type"].dropna().unique().tolist())
    selected_types = st.multiselect("Alert type", alert_types, default=alert_types)
    severities = sorted(alerts["severity"].dropna().unique().tolist())
    selected_severities = st.multiselect("Severity", severities, default=severities)
    filtered = alerts[alerts["alert_type"].isin(selected_types) & alerts["severity"].isin(selected_severities)]
    st.dataframe(filtered, use_container_width=True, hide_index=True)


def render_product_detail(latest: pd.DataFrame, history: pd.DataFrame, currency: str) -> None:
    st.subheader("Product Detail")
    if latest.empty:
        st.info("No products match the filters.")
        return
    product_name = st.selectbox("Product", sorted(latest["product_name"].unique()))
    product_latest = latest[latest["product_name"] == product_name]
    product_history = history[history["product_name"] == product_name]

    col1, col2, col3 = st.columns(3)
    col1.metric("Lowest competitor price", f"{product_latest['current_price'].min():,.0f} {currency}")
    col2.metric("Highest competitor price", f"{product_latest['current_price'].max():,.0f} {currency}")
    col3.metric("Competitors tracked", product_latest["competitor"].nunique())

    st.altair_chart(
        alt.Chart(product_history)
        .mark_line(point=True)
        .encode(
            x="scraped_at:T",
            y=alt.Y("current_price:Q", title=f"Price ({currency})"),
            color="competitor:N",
            tooltip=["competitor", "current_price", "scraped_at", "seller_name"],
        ),
        use_container_width=True,
    )
    st.dataframe(product_latest.sort_values("current_price"), use_container_width=True, hide_index=True)


def render_exports(summary: pd.DataFrame) -> None:
    st.subheader("Export Reports")
    st.write("Generate analyst-ready Excel workbooks for latest prices, price history, alerts, and competitor summary.")
    if not summary.empty:
        st.dataframe(summary, use_container_width=True, hide_index=True)
    if st.button("Generate Excel reports", type="primary"):
        with session_scope() as session:
            paths = ExcelExportService().export_all(session)
        st.success("Reports exported.")
        for path in paths:
            st.code(str(path))


if __name__ == "__main__":
    main()

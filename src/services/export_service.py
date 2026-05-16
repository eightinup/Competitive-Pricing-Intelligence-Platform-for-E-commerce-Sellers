"""Excel report generation for competitive pricing analysts."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger
from sqlalchemy.orm import Session

from src.config import get_settings
from src.services.analytics_service import (
    alerts_dataframe,
    competitor_summary_dataframe,
    latest_prices_dataframe,
    price_history_dataframe,
)


class ExcelExportService:
    """Creates formatted Excel workbooks for latest prices, history, and alerts."""

    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = output_dir or get_settings().export_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_all(self, session: Session) -> list[Path]:
        latest = latest_prices_dataframe(session)
        history = price_history_dataframe(session)
        alerts = alerts_dataframe(session)
        summary = competitor_summary_dataframe(session)

        exports = [
            self._write_workbook(
                self.output_dir / "latest_prices.xlsx",
                {"Latest Prices": latest, "Competitor Summary": summary},
                highlight_price_drops=True,
            ),
            self._write_workbook(
                self.output_dir / "price_history.xlsx",
                {"Price History": history, "Competitor Summary": summary},
            ),
            self._write_workbook(
                self.output_dir / "alerts.xlsx",
                {"Alerts": alerts, "Competitor Summary": summary},
                highlight_alerts=True,
            ),
        ]
        logger.info("Exported {} Excel workbooks to {}", len(exports), self.output_dir)
        return exports

    def _write_workbook(
        self,
        path: Path,
        sheets: dict[str, pd.DataFrame],
        *,
        highlight_price_drops: bool = False,
        highlight_alerts: bool = False,
    ) -> Path:
        with pd.ExcelWriter(path, engine="xlsxwriter", datetime_format="yyyy-mm-dd hh:mm") as writer:
            workbook = writer.book
            header_format = workbook.add_format({"bold": True, "bg_color": "#1F4E78", "font_color": "white"})
            drop_format = workbook.add_format({"bg_color": "#E2F0D9"})
            critical_format = workbook.add_format({"bg_color": "#F4CCCC"})
            high_format = workbook.add_format({"bg_color": "#FCE4D6"})

            for sheet_name, dataframe in sheets.items():
                dataframe = dataframe.copy()
                if dataframe.empty:
                    dataframe = pd.DataFrame({"message": ["No data available yet"]})
                dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
                worksheet = writer.sheets[sheet_name]
                self._format_sheet(worksheet, dataframe, header_format)

                if highlight_price_drops and "price_change_percent" in dataframe.columns:
                    col_index = dataframe.columns.get_loc("price_change_percent")
                    worksheet.conditional_format(
                        1,
                        col_index,
                        len(dataframe),
                        col_index,
                        {"type": "cell", "criteria": "<", "value": 0, "format": drop_format},
                    )
                if highlight_alerts and "severity" in dataframe.columns:
                    severity_col = dataframe.columns.get_loc("severity")
                    worksheet.conditional_format(
                        1,
                        severity_col,
                        len(dataframe),
                        severity_col,
                        {"type": "text", "criteria": "containing", "value": "CRITICAL", "format": critical_format},
                    )
                    worksheet.conditional_format(
                        1,
                        severity_col,
                        len(dataframe),
                        severity_col,
                        {"type": "text", "criteria": "containing", "value": "HIGH", "format": high_format},
                    )
        return path

    @staticmethod
    def _format_sheet(worksheet: object, dataframe: pd.DataFrame, header_format: object) -> None:
        for column_index, column_name in enumerate(dataframe.columns):
            worksheet.write(0, column_index, column_name, header_format)
            values = [str(value) for value in dataframe[column_name].head(500).fillna("").tolist()]
            max_length = max([len(str(column_name)), *(len(value) for value in values)])
            worksheet.set_column(column_index, column_index, min(max_length + 2, 60))
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, len(dataframe), max(len(dataframe.columns) - 1, 0))

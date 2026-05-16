from pathlib import Path

from src.database.models import Base
from src.database.session import create_session_factory, session_scope
from src.services.alert_engine import AlertEngine
from src.services.demo_data import seed_demo_data
from src.services.export_service import ExcelExportService


def test_export_service_creates_excel_workbooks(tmp_path: Path) -> None:
    session_factory = create_session_factory("sqlite:///:memory:")
    Base.metadata.create_all(bind=session_factory.kw["bind"])

    with session_scope(session_factory) as session:
        seed_demo_data(session)
        AlertEngine().generate_alerts(session)
        paths = ExcelExportService(output_dir=tmp_path).export_all(session)

    assert {path.name for path in paths} == {"latest_prices.xlsx", "price_history.xlsx", "alerts.xlsx"}
    assert all(path.exists() and path.stat().st_size > 0 for path in paths)

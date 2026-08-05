from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from services.application_database import dispose_database_engine
from services.storage.dashboard_metrics_repository import DashboardMetricsRepository


def test_dashboard_metrics_repository_persists_without_aliasing() -> None:
    with TemporaryDirectory() as directory:
        database_url = f"sqlite:///{(Path(directory) / 'app.db').as_posix()}"
        try:
            repository = DashboardMetricsRepository(database_url)
            payload = {"version": 3, "days": {"2026-08-04": {"total": 1}}}
            created = repository.replace(payload)
            payload["days"].clear()

            loaded = DashboardMetricsRepository(database_url).load()
            assert created.revision == 1
            assert loaded.revision == 1
            assert loaded.data == {
                "version": 3,
                "days": {"2026-08-04": {"total": 1}},
            }
        finally:
            dispose_database_engine(database_url)


def test_dashboard_metrics_repository_serializes_updates() -> None:
    with TemporaryDirectory() as directory:
        database_url = f"sqlite:///{(Path(directory) / 'app.db').as_posix()}"
        try:
            DashboardMetricsRepository(database_url).replace({"total": 0})

            def increment(_index: int) -> None:
                repository = DashboardMetricsRepository(database_url)
                repository.update(
                    lambda current: {"total": int((current or {}).get("total", 0)) + 1}
                )

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(increment, range(24)))

            snapshot = DashboardMetricsRepository(database_url).load()
            assert snapshot.data == {"total": 24}
            assert snapshot.revision == 25
        finally:
            dispose_database_engine(database_url)

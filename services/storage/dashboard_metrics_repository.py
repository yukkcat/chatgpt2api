from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import Column, DateTime, Integer, JSON, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker

from services.application_database import (
    DatabaseBase,
    initialize_application_database,
    resolve_database_url,
)


class DashboardMetricsModel(DatabaseBase):
    __tablename__ = "dashboard_metrics"

    id = Column(Integer, primary_key=True)
    data = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    revision = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class DashboardMetricsSnapshot:
    data: dict[str, Any] | None
    revision: int


class DashboardMetricsRepository:
    """Atomic persistence for the rebuildable Dashboard aggregate."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or resolve_database_url()
        self.engine = initialize_application_database(self.database_url)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    @staticmethod
    def _copy(value: object) -> object:
        return copy.deepcopy(value)

    @classmethod
    def _payload(cls, value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise TypeError("dashboard metrics payload must be an object")
        return cls._copy(value)

    def _lock(self, session: Any) -> None:
        if self.engine.dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))
        elif self.engine.dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": "dashboard_metrics"},
            )

    def load(self) -> DashboardMetricsSnapshot:
        session = self.Session()
        try:
            row = session.get(DashboardMetricsModel, 1)
            if row is None:
                return DashboardMetricsSnapshot(data=None, revision=0)
            return DashboardMetricsSnapshot(
                data=self._payload(row.data),
                revision=max(0, int(row.revision or 0)),
            )
        finally:
            session.close()

    def update(
        self,
        updater: Callable[[dict[str, Any] | None], dict[str, Any]],
    ) -> DashboardMetricsSnapshot:
        session = self.Session()
        try:
            self._lock(session)
            row = (
                session.query(DashboardMetricsModel)
                .filter(DashboardMetricsModel.id == 1)
                .with_for_update()
                .one_or_none()
            )
            current = self._payload(row.data) if row is not None else None
            payload = self._payload(updater(current))
            current_revision = max(0, int(row.revision or 0)) if row is not None else 0
            if row is None:
                revision = 1
                session.add(DashboardMetricsModel(
                    id=1,
                    data=payload,
                    revision=revision,
                    updated_at=datetime.now(timezone.utc),
                ))
            elif row.data != payload:
                revision = current_revision + 1
                row.data = payload
                row.revision = revision
                row.updated_at = datetime.now(timezone.utc)
            else:
                revision = current_revision
            session.commit()
            return DashboardMetricsSnapshot(data=self._payload(payload), revision=revision)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def replace(self, data: dict[str, Any]) -> DashboardMetricsSnapshot:
        payload = self._payload(data)
        return self.update(lambda _current: payload)

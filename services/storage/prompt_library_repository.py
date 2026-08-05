from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Integer, JSON, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker

from services.application_database import (
    DatabaseBase,
    initialize_application_database,
    resolve_database_url,
)


class PromptLibraryStateModel(DatabaseBase):
    __tablename__ = "prompt_library_state"

    id = Column(Integer, primary_key=True)
    settings = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    snapshot = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    settings_revision = Column(Integer, nullable=False)
    snapshot_revision = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class PromptLibraryState:
    settings: dict[str, Any]
    snapshot: dict[str, Any]
    settings_revision: int
    snapshot_revision: int


class PromptLibraryRepository:
    """Persistence for Prompt Source settings and the verified library snapshot."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or resolve_database_url()
        self.engine = initialize_application_database(self.database_url)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    @staticmethod
    def _payload(value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise TypeError("prompt library state must be an object")
        return copy.deepcopy(value)

    def _lock(self, session: Any) -> None:
        if self.engine.dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))
        elif self.engine.dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": "prompt_library_state"},
            )

    def load(self) -> PromptLibraryState:
        session = self.Session()
        try:
            row = session.get(PromptLibraryStateModel, 1)
            if row is None:
                return PromptLibraryState({}, {}, 0, 0)
            return PromptLibraryState(
                settings=self._payload(row.settings),
                snapshot=self._payload(row.snapshot),
                settings_revision=max(0, int(row.settings_revision or 0)),
                snapshot_revision=max(0, int(row.snapshot_revision or 0)),
            )
        finally:
            session.close()

    def _replace(self, field: str, value: dict[str, Any]) -> PromptLibraryState:
        payload = self._payload(value)
        session = self.Session()
        try:
            self._lock(session)
            row = (
                session.query(PromptLibraryStateModel)
                .filter(PromptLibraryStateModel.id == 1)
                .with_for_update()
                .one_or_none()
            )
            now = datetime.now(timezone.utc)
            if row is None:
                row = PromptLibraryStateModel(
                    id=1,
                    settings=payload if field == "settings" else {},
                    snapshot=payload if field == "snapshot" else {},
                    settings_revision=1 if field == "settings" else 0,
                    snapshot_revision=1 if field == "snapshot" else 0,
                    updated_at=now,
                )
                session.add(row)
            elif getattr(row, field) != payload:
                setattr(row, field, payload)
                revision_field = f"{field}_revision"
                setattr(row, revision_field, max(0, int(getattr(row, revision_field) or 0)) + 1)
                row.updated_at = now
            session.commit()
            return PromptLibraryState(
                settings=self._payload(row.settings),
                snapshot=self._payload(row.snapshot),
                settings_revision=max(0, int(row.settings_revision or 0)),
                snapshot_revision=max(0, int(row.snapshot_revision or 0)),
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def replace_settings(self, settings: dict[str, Any]) -> PromptLibraryState:
        return self._replace("settings", settings)

    def replace_snapshot(self, snapshot: dict[str, Any]) -> PromptLibraryState:
        return self._replace("snapshot", snapshot)

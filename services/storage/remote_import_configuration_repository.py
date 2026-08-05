from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import Column, DateTime, Integer, JSON, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker

from services.application_database import (
    DatabaseBase,
    initialize_application_database,
    resolve_database_url,
)


REMOTE_IMPORT_PROVIDERS = frozenset({"cpa", "sub2api"})


class RemoteImportConfigurationModel(DatabaseBase):
    __tablename__ = "remote_import_configurations"

    provider = Column(String(32), primary_key=True)
    items = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    revision = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class RemoteImportConfigurationRepository:
    """Atomic storage for CPA pools and Sub2API server configurations."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or resolve_database_url()
        self.engine = initialize_application_database(self.database_url)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    @staticmethod
    def _provider(value: object) -> str:
        provider = str(value or "").strip().lower()
        if provider not in REMOTE_IMPORT_PROVIDERS:
            raise ValueError("unsupported remote import provider")
        return provider

    @staticmethod
    def _items(value: object) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise TypeError("remote import configuration must be a list")
        return copy.deepcopy([item for item in value if isinstance(item, dict)])

    def _lock(self, session: Any, provider: str) -> None:
        if self.engine.dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))
        elif self.engine.dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": f"remote_import_configuration:{provider}"},
            )

    def load(self, provider: str) -> list[dict[str, Any]]:
        normalized_provider = self._provider(provider)
        session = self.Session()
        try:
            row = session.get(RemoteImportConfigurationModel, normalized_provider)
            return self._items(row.items) if row is not None else []
        finally:
            session.close()

    def update(
        self,
        provider: str,
        updater: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        normalized_provider = self._provider(provider)
        session = self.Session()
        try:
            self._lock(session, normalized_provider)
            row = (
                session.query(RemoteImportConfigurationModel)
                .filter(RemoteImportConfigurationModel.provider == normalized_provider)
                .with_for_update()
                .one_or_none()
            )
            current = self._items(row.items) if row is not None else []
            items = self._items(updater(current))
            now = datetime.now(timezone.utc)
            if row is None:
                session.add(RemoteImportConfigurationModel(
                    provider=normalized_provider,
                    items=items,
                    revision=1,
                    updated_at=now,
                ))
            elif row.items != items:
                row.items = items
                row.revision = max(0, int(row.revision or 0)) + 1
                row.updated_at = now
            session.commit()
            return self._items(items)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def replace(self, provider: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload = self._items(items)
        return self.update(provider, lambda _current: payload)

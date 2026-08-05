from __future__ import annotations

import copy
from collections.abc import Mapping
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


class SystemSettingsModel(DatabaseBase):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True)
    data = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class ProxyConfigurationModel(DatabaseBase):
    __tablename__ = "proxy_configuration"

    id = Column(Integer, primary_key=True)
    data = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class AccountGroupConfigurationModel(DatabaseBase):
    __tablename__ = "account_group_configuration"

    id = Column(Integer, primary_key=True)
    data = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class _DictionaryRepository:
    model: Any
    lock_name = ""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or resolve_database_url()
        self.engine = initialize_application_database(self.database_url)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    @staticmethod
    def _dictionary(value: object | None) -> dict[str, object]:
        return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}

    def _lock(self, session: Any) -> None:
        if self.engine.dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))
        elif self.engine.dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": self.lock_name},
            )

    def get(self) -> dict[str, object]:
        session = self.Session()
        try:
            row = session.get(self.model, 1)
            return self._dictionary(row.data if row is not None else None)
        finally:
            session.close()

    def update(self, values: Mapping[str, object]) -> dict[str, object]:
        patch = copy.deepcopy(dict(values))
        session = self.Session()
        try:
            self._lock(session)
            row = session.get(self.model, 1, with_for_update=True)
            result = self._dictionary(row.data if row is not None else None)
            result.update(patch)
            now = datetime.now(timezone.utc)
            if row is None:
                session.add(self.model(id=1, data=result, updated_at=now))
            elif row.data != result:
                row.data = result
                row.updated_at = now
            session.commit()
            return self._dictionary(result)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def replace(self, values: Mapping[str, object]) -> dict[str, object]:
        payload = copy.deepcopy(dict(values))
        session = self.Session()
        try:
            self._lock(session)
            row = session.get(self.model, 1, with_for_update=True)
            now = datetime.now(timezone.utc)
            if row is None:
                session.add(self.model(id=1, data=payload, updated_at=now))
            elif row.data != payload:
                row.data = payload
                row.updated_at = now
            session.commit()
            return self._dictionary(payload)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class SystemSettingsRepository(_DictionaryRepository):
    model = SystemSettingsModel
    lock_name = "system_settings"


class ProxyConfigurationRepository(_DictionaryRepository):
    model = ProxyConfigurationModel
    lock_name = "proxy_configuration"


class AccountGroupRepository(_DictionaryRepository):
    model = AccountGroupConfigurationModel
    lock_name = "account_group_configuration"


system_settings_repository = SystemSettingsRepository()
proxy_configuration_repository = ProxyConfigurationRepository()
account_group_repository = AccountGroupRepository()

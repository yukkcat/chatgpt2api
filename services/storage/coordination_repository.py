from __future__ import annotations

import copy
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker

from services.application_database import (
    DatabaseBase,
    initialize_application_database,
    resolve_database_url,
)


class BackupExecutionStateModel(DatabaseBase):
    __tablename__ = "backup_execution_state"

    id = Column(Integer, primary_key=True)
    data = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    revision = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class RetentionCleanupStateModel(DatabaseBase):
    __tablename__ = "retention_cleanup_state"

    id = Column(Integer, primary_key=True)
    data = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    revision = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class ApplicationCoordinationLeaseModel(DatabaseBase):
    __tablename__ = "application_coordination_lease"

    name = Column(String(128), primary_key=True)
    owner_token = Column(String(64), nullable=False)
    expires_at = Column(Float, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class _JsonStateRepository:
    def __init__(self, model: type[Any], lock_name: str, database_url: str | None) -> None:
        self.database_url = database_url or resolve_database_url()
        self.engine = initialize_application_database(self.database_url)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self._model = model
        self._lock_name = lock_name

    @staticmethod
    def _payload(value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise TypeError("coordination state must be an object")
        return copy.deepcopy(value)

    def _lock_state(self, session: Any) -> None:
        if self.engine.dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))
        elif self.engine.dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": self._lock_name},
            )

    def load(self) -> dict[str, Any]:
        session = self.Session()
        try:
            row = session.get(self._model, 1)
            return self._payload(row.data) if row is not None else {}
        finally:
            session.close()

    @contextmanager
    def edit(self) -> Iterator[dict[str, Any]]:
        session = self.Session()
        try:
            self._lock_state(session)
            row = (
                session.query(self._model)
                .filter(self._model.id == 1)
                .with_for_update()
                .one_or_none()
            )
            state = self._payload(row.data) if row is not None else {}
            previous = self._payload(state)
            yield state
            payload = self._payload(state)
            now = datetime.now(timezone.utc)
            if row is None:
                session.add(self._model(
                    id=1,
                    data=payload,
                    revision=1,
                    updated_at=now,
                ))
            elif payload != previous:
                row.data = payload
                row.revision = max(0, int(row.revision or 0)) + 1
                row.updated_at = now
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update(self, updater: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        with self.edit() as state:
            updated = self._payload(updater(self._payload(state)))
            state.clear()
            state.update(updated)
        return self._payload(updated)

    def replace(self, state: dict[str, Any]) -> dict[str, Any]:
        payload = self._payload(state)
        return self.update(lambda _current: payload)


class _DatabaseLease:
    def __init__(
        self,
        repository: _JsonStateRepository,
        name: str,
        *,
        lease_seconds: float,
        timeout_seconds: float | None,
    ) -> None:
        self._repository = repository
        self._name = name
        self._lease_seconds = max(1.0, float(lease_seconds))
        self._timeout_seconds = timeout_seconds
        self._owner_token = uuid.uuid4().hex
        self._connection: Any | None = None
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    def __enter__(self) -> None:
        deadline = (
            None
            if self._timeout_seconds is None
            else time.monotonic() + max(0.0, self._timeout_seconds)
        )
        if self._repository.engine.dialect.name == "postgresql":
            self._acquire_postgresql(deadline)
        else:
            self._acquire_sqlite(deadline)

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._repository.engine.dialect.name == "postgresql":
            self._release_postgresql()
        else:
            self._release_sqlite()

    def _timed_out(self, deadline: float | None) -> bool:
        return deadline is not None and time.monotonic() >= deadline

    def _acquire_postgresql(self, deadline: float | None) -> None:
        connection = self._repository.engine.connect()
        try:
            while True:
                acquired = bool(connection.execute(
                    text("SELECT pg_try_advisory_lock(hashtext(:key))"),
                    {"key": self._name},
                ).scalar())
                connection.commit()
                if acquired:
                    self._connection = connection
                    return
                if self._timed_out(deadline):
                    raise TimeoutError(f"coordination lease is busy: {self._name}")
                time.sleep(0.05)
        except Exception:
            connection.close()
            raise

    def _release_postgresql(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is None:
            return
        try:
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtext(:key))"),
                {"key": self._name},
            )
            connection.commit()
        finally:
            connection.close()

    def _acquire_sqlite(self, deadline: float | None) -> None:
        while not self._try_acquire_sqlite():
            if self._timed_out(deadline):
                raise TimeoutError(f"coordination lease is busy: {self._name}")
            time.sleep(0.05)
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_sqlite,
            daemon=True,
            name=f"coordination-lease-{self._name.rsplit(':', 1)[-1]}",
        )
        self._heartbeat_thread.start()

    def _try_acquire_sqlite(self) -> bool:
        now_epoch = time.time()
        now = datetime.now(timezone.utc)
        connection = self._repository.engine.connect()
        try:
            connection.execute(text("BEGIN IMMEDIATE"))
            row = connection.execute(
                select(ApplicationCoordinationLeaseModel).where(
                    ApplicationCoordinationLeaseModel.name == self._name
                )
            ).mappings().one_or_none()
            if row is not None and float(row["expires_at"] or 0) > now_epoch:
                connection.rollback()
                return False
            if row is None:
                connection.execute(
                    ApplicationCoordinationLeaseModel.__table__.insert().values(
                        name=self._name,
                        owner_token=self._owner_token,
                        expires_at=now_epoch + self._lease_seconds,
                        updated_at=now,
                    )
                )
            else:
                connection.execute(
                    ApplicationCoordinationLeaseModel.__table__.update()
                    .where(ApplicationCoordinationLeaseModel.name == self._name)
                    .values(
                        owner_token=self._owner_token,
                        expires_at=now_epoch + self._lease_seconds,
                        updated_at=now,
                    )
                )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _heartbeat_sqlite(self) -> None:
        interval = max(0.5, self._lease_seconds / 3)
        while not self._heartbeat_stop.wait(interval):
            now_epoch = time.time()
            with self._repository.engine.begin() as connection:
                result = connection.execute(
                    ApplicationCoordinationLeaseModel.__table__.update()
                    .where(
                        ApplicationCoordinationLeaseModel.name == self._name,
                        ApplicationCoordinationLeaseModel.owner_token == self._owner_token,
                    )
                    .values(
                        expires_at=now_epoch + self._lease_seconds,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
            if result.rowcount != 1:
                return

    def _release_sqlite(self) -> None:
        self._heartbeat_stop.set()
        thread = self._heartbeat_thread
        if thread is not None:
            thread.join(timeout=1)
        with self._repository.engine.begin() as connection:
            connection.execute(
                ApplicationCoordinationLeaseModel.__table__.delete().where(
                    ApplicationCoordinationLeaseModel.name == self._name,
                    ApplicationCoordinationLeaseModel.owner_token == self._owner_token,
                )
            )


class BackupExecutionStateRepository(_JsonStateRepository):
    def __init__(self, database_url: str | None = None) -> None:
        super().__init__(BackupExecutionStateModel, "backup_execution_state", database_url)

    def run_lock(self, *, timeout_seconds: float | None = None) -> _DatabaseLease:
        return _DatabaseLease(
            self,
            "backup_execution:run",
            lease_seconds=300,
            timeout_seconds=timeout_seconds,
        )


class RetentionCleanupRepository(_JsonStateRepository):
    def __init__(self, database_url: str | None = None) -> None:
        super().__init__(RetentionCleanupStateModel, "retention_cleanup_state", database_url)

    def run_lock(self, *, timeout_seconds: float | None = None) -> _DatabaseLease:
        return _DatabaseLease(
            self,
            "retention_cleanup:run",
            lease_seconds=300,
            timeout_seconds=timeout_seconds,
        )

    def scheduler_leader_lock(self, *, timeout_seconds: float = 0) -> _DatabaseLease:
        return _DatabaseLease(
            self,
            "retention_cleanup:scheduler_leader",
            lease_seconds=5,
            timeout_seconds=timeout_seconds,
        )

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import Boolean, Column, Float, JSON, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from services.application_database import (
    DatabaseBase,
    initialize_application_database,
    resolve_database_url,
)


class EditableFileTaskModel(DatabaseBase):
    __tablename__ = "editable_file_task"

    owner_id = Column(String(256), primary_key=True)
    task_id = Column(String(160), primary_key=True)
    storage_id = Column(String(48), nullable=False, unique=True)
    status = Column(String(24), nullable=False, index=True)
    kind = Column(String(8), nullable=False)
    model = Column(String(128), nullable=True)
    created_at = Column(String(64), nullable=False)
    updated_at = Column(String(64), nullable=False, index=True)
    created_ts = Column(Float, nullable=False)
    updated_ts = Column(Float, nullable=False)
    started_ts = Column(Float, nullable=True)
    ended_ts = Column(Float, nullable=True)
    result = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    error = Column(Text, nullable=True)
    account_email = Column(String(320), nullable=True)
    delete_pending = Column(Boolean, nullable=False, default=False, index=True)


class EditableFileTaskRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or resolve_database_url()
        self.engine = initialize_application_database(self.database_url)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    @staticmethod
    def _copy(value: object) -> object:
        return copy.deepcopy(value)

    @classmethod
    def _task_from_row(cls, row: EditableFileTaskModel) -> dict[str, Any]:
        task: dict[str, Any] = {
            "id": row.task_id,
            "storage_id": row.storage_id,
            "owner_id": row.owner_id,
            "status": row.status,
            "kind": row.kind,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "created_ts": float(row.created_ts or 0),
            "updated_ts": float(row.updated_ts or 0),
        }
        for name in ("model", "started_ts", "ended_ts", "error", "account_email"):
            value = getattr(row, name)
            if value not in (None, ""):
                task[name] = value
        if isinstance(row.result, dict) and row.result:
            task["result"] = cls._copy(row.result)
        if row.delete_pending:
            task["delete_pending"] = True
        return task

    @staticmethod
    def _required_text(task: dict[str, Any], name: str) -> str:
        value = str(task.get(name) or "").strip()
        if not value:
            raise ValueError(f"editable file task {name} is required")
        return value

    @classmethod
    def _model_from_task(cls, task: dict[str, Any]) -> EditableFileTaskModel:
        return EditableFileTaskModel(
            owner_id=cls._required_text(task, "owner_id"),
            task_id=cls._required_text(task, "id"),
            storage_id=cls._required_text(task, "storage_id"),
            status=cls._required_text(task, "status"),
            kind=cls._required_text(task, "kind"),
            model=str(task.get("model") or "").strip() or None,
            created_at=cls._required_text(task, "created_at"),
            updated_at=cls._required_text(task, "updated_at"),
            created_ts=float(task.get("created_ts") or 0),
            updated_ts=float(task.get("updated_ts") or 0),
            started_ts=float(task["started_ts"]) if task.get("started_ts") is not None else None,
            ended_ts=float(task["ended_ts"]) if task.get("ended_ts") is not None else None,
            result=cls._copy(task.get("result")) if isinstance(task.get("result"), dict) else None,
            error=str(task.get("error") or "") or None,
            account_email=str(task.get("account_email") or "").strip() or None,
            delete_pending=bool(task.get("delete_pending")),
        )

    def _lock_write(self, session: Any) -> None:
        if self.engine.dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))

    def get(self, owner_id: str, task_id: str) -> dict[str, Any] | None:
        session = self.Session()
        try:
            row = session.get(EditableFileTaskModel, (owner_id, task_id))
            return self._task_from_row(row) if row is not None else None
        finally:
            session.close()

    def list_for_owner(
        self,
        owner_id: str,
        *,
        task_ids: list[str] | None = None,
        limit: int = 0,
    ) -> list[dict[str, Any]]:
        session = self.Session()
        try:
            query = session.query(EditableFileTaskModel).filter(
                EditableFileTaskModel.owner_id == owner_id
            )
            if task_ids is not None:
                if not task_ids:
                    return []
                query = query.filter(EditableFileTaskModel.task_id.in_(task_ids))
            query = query.order_by(
                EditableFileTaskModel.updated_at.desc(),
                EditableFileTaskModel.task_id.asc(),
            )
            if limit > 0:
                query = query.limit(limit)
            return [self._task_from_row(row) for row in query.all()]
        finally:
            session.close()

    def list_by_status(self, statuses: set[str]) -> list[dict[str, Any]]:
        if not statuses:
            return []
        session = self.Session()
        try:
            rows = session.query(EditableFileTaskModel).filter(
                EditableFileTaskModel.status.in_(sorted(statuses))
            ).all()
            return [self._task_from_row(row) for row in rows]
        finally:
            session.close()

    def list_delete_pending(self) -> list[dict[str, Any]]:
        session = self.Session()
        try:
            rows = session.query(EditableFileTaskModel).filter(
                EditableFileTaskModel.delete_pending.is_(True)
            ).all()
            return [self._task_from_row(row) for row in rows]
        finally:
            session.close()

    def create(self, task: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        model = self._model_from_task(task)
        session = self.Session()
        try:
            session.add(model)
            session.commit()
            return self._task_from_row(model), True
        except IntegrityError:
            session.rollback()
            existing = session.get(
                EditableFileTaskModel,
                (model.owner_id, model.task_id),
            )
            if existing is None:
                raise
            return self._task_from_row(existing), False
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update(self, owner_id: str, task_id: str, **updates: Any) -> dict[str, Any] | None:
        allowed = {
            "status",
            "updated_at",
            "updated_ts",
            "started_ts",
            "ended_ts",
            "result",
            "error",
            "account_email",
            "delete_pending",
        }
        unknown = set(updates) - allowed
        if unknown:
            raise ValueError(f"unsupported editable file task fields: {sorted(unknown)}")
        session = self.Session()
        try:
            self._lock_write(session)
            row = (
                session.query(EditableFileTaskModel)
                .filter(
                    EditableFileTaskModel.owner_id == owner_id,
                    EditableFileTaskModel.task_id == task_id,
                )
                .with_for_update()
                .one_or_none()
            )
            if row is None:
                session.rollback()
                return None
            for name, value in updates.items():
                if name == "result":
                    value = self._copy(value) if isinstance(value, dict) else None
                elif name in {"started_ts", "ended_ts", "updated_ts"}:
                    value = float(value) if value is not None else None
                elif name == "delete_pending":
                    value = bool(value)
                elif name in {"error", "account_email"}:
                    value = str(value or "") or None
                setattr(row, name, value)
            session.commit()
            return self._task_from_row(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete(self, owner_id: str, task_id: str) -> bool:
        session = self.Session()
        try:
            self._lock_write(session)
            row = (
                session.query(EditableFileTaskModel)
                .filter(
                    EditableFileTaskModel.owner_id == owner_id,
                    EditableFileTaskModel.task_id == task_id,
                )
                .with_for_update()
                .one_or_none()
            )
            if row is None:
                session.rollback()
                return False
            session.delete(row)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

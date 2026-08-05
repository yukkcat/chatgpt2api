from __future__ import annotations

import copy
import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text, delete, func, select, text
from sqlalchemy.orm import sessionmaker

from services.application_database import (
    DatabaseBase,
    initialize_application_database,
    resolve_database_url,
)


class CallRecordModel(DatabaseBase):
    __tablename__ = "call_records"

    sequence = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(64), nullable=False, unique=True)
    event_time = Column(String(32), nullable=False)
    event_day = Column(String(10), nullable=False)
    type = Column(String(32), nullable=False)
    outcome = Column(String(32), nullable=False)
    endpoint = Column(String(255), nullable=False)
    model = Column(String(255), nullable=False)
    account_email = Column(String(320), nullable=False)
    conversation_id = Column(String(255), nullable=False)
    business_kind = Column(String(64), nullable=False)
    search_text = Column(Text, nullable=False)
    payload = Column(JSON, nullable=False)
    inserted_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_call_records_type_sequence", "type", "sequence"),
        Index("ix_call_records_day_sequence", "event_day", "sequence"),
        Index("ix_call_records_outcome_sequence", "outcome", "sequence"),
        Index("ix_call_records_endpoint_sequence", "endpoint", "sequence"),
        Index("ix_call_records_model_sequence", "model", "sequence"),
        Index("ix_call_records_account_sequence", "account_email", "sequence"),
        Index("ix_call_records_conversation_sequence", "conversation_id", "sequence"),
    )


class CallRecordStateModel(DatabaseBase):
    __tablename__ = "call_record_state"

    id = Column(Integer, primary_key=True)
    generation = Column(String(64), nullable=False)


@dataclass(frozen=True)
class CallRecordWrite:
    payload: dict[str, Any]
    outcome: str
    endpoint: str = ""
    model: str = ""
    account_email: str = ""
    conversation_id: str = ""
    business_kind: str = ""
    search_text: str = ""


@dataclass(frozen=True)
class CallRecordQuery:
    type: str = ""
    start_date: str = ""
    end_date: str = ""
    outcomes: tuple[str, ...] = ()
    endpoint: str = ""
    model: str = ""
    account_email: str = ""
    conversation_id: str = ""
    search: str = ""


@dataclass(frozen=True)
class CallRecordPage:
    items: list[dict[str, Any]]
    total: int
    facets: dict[str, dict[str, int]]
    outcomes: dict[str, int]
    image_count: int


class CallRecordCursorMismatch(RuntimeError):
    pass


class CallRecordRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or resolve_database_url()
        self.engine = initialize_application_database(self.database_url)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO call_record_state (id, generation) "
                    "VALUES (1, :generation) ON CONFLICT (id) DO NOTHING"
                ),
                {"generation": uuid4().hex},
            )

    @staticmethod
    def _copy(payload: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(payload)

    @staticmethod
    def _clean(value: object) -> str:
        return str(value or "").strip()

    @classmethod
    def _row_payload(cls, row: CallRecordModel) -> dict[str, Any]:
        value = row.payload
        return cls._copy(value) if isinstance(value, dict) else {}

    def append(self, record: CallRecordWrite) -> dict[str, Any]:
        payload = self._copy(record.payload)
        record_id = self._clean(payload.get("id")) or uuid4().hex
        event_time = self._clean(payload.get("time"))
        if not event_time:
            raise ValueError("call record time is required")
        payload["id"] = record_id
        session = self.Session()
        try:
            session.add(CallRecordModel(
                id=record_id,
                event_time=event_time,
                event_day=event_time[:10],
                type=self._clean(payload.get("type")),
                outcome=self._clean(record.outcome),
                endpoint=self._clean(record.endpoint),
                model=self._clean(record.model),
                account_email=self._clean(record.account_email),
                conversation_id=self._clean(record.conversation_id),
                business_kind=self._clean(record.business_kind),
                search_text=self._clean(record.search_text).lower(),
                payload=payload,
                inserted_at=datetime.now(timezone.utc),
            ))
            session.commit()
            return self._copy(payload)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _filters(query: CallRecordQuery) -> list[Any]:
        filters: list[Any] = []
        if query.type:
            filters.append(CallRecordModel.type == query.type)
        if query.start_date:
            filters.append(CallRecordModel.event_day >= query.start_date)
        if query.end_date:
            filters.append(CallRecordModel.event_day <= query.end_date)
        if query.outcomes:
            filters.append(CallRecordModel.outcome.in_(query.outcomes))
        if query.endpoint:
            filters.append(CallRecordModel.endpoint == query.endpoint)
        if query.model:
            filters.append(CallRecordModel.model == query.model)
        if query.account_email:
            filters.append(CallRecordModel.account_email == query.account_email)
        if query.conversation_id:
            filters.append(CallRecordModel.conversation_id == query.conversation_id)
        if query.search:
            filters.append(CallRecordModel.search_text.contains(query.search.lower()))
        return filters

    @staticmethod
    def _counts(session, column, filters: Sequence[Any]) -> dict[str, int]:
        rows = session.execute(
            select(column, func.count(CallRecordModel.sequence))
            .where(*filters)
            .group_by(column)
        ).all()
        return {str(key): int(count) for key, count in rows if str(key or "").strip()}

    def list_page(self, query: CallRecordQuery, *, limit: int, offset: int) -> CallRecordPage:
        filters = self._filters(query)
        session = self.Session()
        try:
            total = int(session.scalar(
                select(func.count(CallRecordModel.sequence)).where(*filters)
            ) or 0)
            rows = session.scalars(
                select(CallRecordModel)
                .where(*filters)
                .order_by(CallRecordModel.sequence.desc())
                .offset(max(0, int(offset)))
                .limit(max(1, int(limit)))
            ).all()
            image_count = int(session.scalar(
                select(func.count(CallRecordModel.sequence)).where(
                    *filters,
                    CallRecordModel.business_kind.in_((
                        "image_generation",
                        "image_edit",
                        "image_chat",
                    )),
                )
            ) or 0)
            return CallRecordPage(
                items=[self._row_payload(row) for row in rows],
                total=total,
                facets={
                    "statuses": self._counts(session, CallRecordModel.outcome, filters),
                    "endpoints": self._counts(session, CallRecordModel.endpoint, filters),
                    "models": self._counts(session, CallRecordModel.model, filters),
                    "accounts": self._counts(session, CallRecordModel.account_email, filters),
                },
                outcomes=self._counts(session, CallRecordModel.outcome, filters),
                image_count=image_count,
            )
        finally:
            session.close()

    def get(self, record_id: str) -> dict[str, Any] | None:
        session = self.Session()
        try:
            row = session.scalar(
                select(CallRecordModel).where(CallRecordModel.id == self._clean(record_id))
            )
            return self._row_payload(row) if row is not None else None
        finally:
            session.close()

    def iter_records(self, *, type: str = "", newest_first: bool = False) -> Iterator[dict[str, Any]]:
        session = self.Session()
        try:
            statement = select(CallRecordModel)
            if type:
                statement = statement.where(CallRecordModel.type == type)
            order = CallRecordModel.sequence.desc() if newest_first else CallRecordModel.sequence.asc()
            for row in session.scalars(statement.order_by(order)).yield_per(500):
                yield self._row_payload(row)
        finally:
            session.close()

    def _generation(self, session) -> str:
        generation = session.scalar(
            select(CallRecordStateModel.generation).where(CallRecordStateModel.id == 1)
        )
        if not generation:
            raise RuntimeError("call record state is missing")
        return str(generation)

    def _rotate_generation(self, session) -> str:
        state = session.get(CallRecordStateModel, 1, with_for_update=True)
        if state is None:
            raise RuntimeError("call record state is missing")
        state.generation = uuid4().hex
        return str(state.generation)

    @contextmanager
    def open_window(self, cursor: dict[str, Any] | None = None):
        session = self.Session()
        try:
            generation = self._generation(session)
            try:
                start_sequence = max(0, int((cursor or {}).get("sequence", 0)))
            except (TypeError, ValueError):
                raise CallRecordCursorMismatch("call record cursor sequence is invalid") from None
            if cursor is not None and self._clean(cursor.get("generation")) != generation:
                raise CallRecordCursorMismatch("call record generation changed")
            end_sequence = int(session.scalar(select(func.max(CallRecordModel.sequence))) or 0)
            rows = session.scalars(
                select(CallRecordModel)
                .where(
                    CallRecordModel.type == "call",
                    CallRecordModel.sequence > start_sequence,
                    CallRecordModel.sequence <= end_sequence,
                )
                .order_by(CallRecordModel.sequence.asc())
            ).all()
            yield (
                (self._row_payload(row) for row in rows),
                {"generation": generation, "sequence": end_sequence},
            )
        finally:
            session.close()

    @contextmanager
    def hold_cursor(self, cursor: dict[str, Any]):
        session = self.Session()
        try:
            state = session.get(CallRecordStateModel, 1, with_for_update=True)
            if state is None or self._clean(state.generation) != self._clean(cursor.get("generation")):
                raise CallRecordCursorMismatch("call record generation changed")
            yield
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete(self, ids: Sequence[str]) -> int:
        target_ids = tuple(dict.fromkeys(self._clean(item) for item in ids if self._clean(item)))
        if not target_ids:
            return 0
        session = self.Session()
        try:
            result = session.execute(delete(CallRecordModel).where(CallRecordModel.id.in_(target_ids)))
            removed = max(0, int(result.rowcount or 0))
            if removed:
                self._rotate_generation(session)
            session.commit()
            return removed
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def cleanup_before(self, cutoff_day: str, *, dry_run: bool) -> dict[str, int]:
        session = self.Session()
        try:
            filters = (CallRecordModel.event_day < cutoff_day,)
            rows = session.scalars(select(CallRecordModel).where(*filters)).all()
            removed = len(rows)
            removed_size_bytes = sum(
                len(json.dumps(self._row_payload(row), ensure_ascii=False).encode("utf-8"))
                for row in rows
            )
            kept = int(session.scalar(
                select(func.count(CallRecordModel.sequence)).where(CallRecordModel.event_day >= cutoff_day)
            ) or 0)
            if removed and not dry_run:
                session.execute(delete(CallRecordModel).where(*filters))
                self._rotate_generation(session)
            session.commit()
            return {
                "removed": removed,
                "kept": kept,
                "removed_size_bytes": removed_size_bytes,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

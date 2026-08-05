from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker

from services.application_database import (
    DatabaseBase,
    initialize_application_database,
    resolve_database_url,
)


_JSON = JSON().with_variant(JSONB, "postgresql")
_COUNT_FIELDS = (
    "total",
    "success",
    "failed",
    "text_review",
    "rate_limited",
    "switch_requests",
    "switch_count",
    "switch_recovered",
)
_MODEL_COUNT_FIELDS = {
    "total": "by_model",
    "success": "model_success",
    "failed": "model_failed",
    "text_review": "model_text_review",
    "rate_limited": "model_rate_limited",
}


class DashboardMetricStateModel(DatabaseBase):
    __tablename__ = "dashboard_metric_state"

    id = Column(Integer, primary_key=True)
    data = Column(_JSON, nullable=False)
    revision = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class DashboardMetricHourlyModel(DatabaseBase):
    __tablename__ = "dashboard_metric_hourly"

    bucket_start = Column(String(13), primary_key=True)
    total = Column(BigInteger, nullable=False, default=0)
    success = Column(BigInteger, nullable=False, default=0)
    failed = Column(BigInteger, nullable=False, default=0)
    text_review = Column(BigInteger, nullable=False, default=0)
    rate_limited = Column(BigInteger, nullable=False, default=0)
    switch_requests = Column(BigInteger, nullable=False, default=0)
    switch_count = Column(BigInteger, nullable=False, default=0)
    switch_recovered = Column(BigInteger, nullable=False, default=0)
    success_duration_total_ms = Column(Float, nullable=False, default=0.0)
    success_duration_count = Column(BigInteger, nullable=False, default=0)
    success_duration_histogram = Column(_JSON, nullable=False, default=list)


class DashboardMetricModelHourlyModel(DatabaseBase):
    __tablename__ = "dashboard_metric_model_hourly"

    bucket_start = Column(
        String(13),
        ForeignKey("dashboard_metric_hourly.bucket_start", ondelete="CASCADE"),
        primary_key=True,
    )
    model = Column(String(255), primary_key=True)
    total = Column(BigInteger, nullable=False, default=0)
    success = Column(BigInteger, nullable=False, default=0)
    failed = Column(BigInteger, nullable=False, default=0)
    text_review = Column(BigInteger, nullable=False, default=0)
    rate_limited = Column(BigInteger, nullable=False, default=0)
    success_duration_total_ms = Column(Float, nullable=False, default=0.0)
    success_duration_count = Column(BigInteger, nullable=False, default=0)
    success_duration_histogram = Column(_JSON, nullable=False, default=list)

    __table_args__ = (
        Index("ix_dashboard_metric_model_hourly_model", "model", "bucket_start"),
    )


@dataclass(frozen=True, slots=True)
class DashboardMetricsSnapshot:
    data: dict[str, Any] | None
    revision: int


class DashboardMetricsRepository:
    """Atomic persistence for rebuildable hourly Dashboard projections."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or resolve_database_url()
        self.engine = initialize_application_database(self.database_url)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    @staticmethod
    def _copy(value: object) -> Any:
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

    @staticmethod
    def _integer(value: object) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _number(value: object) -> float:
        try:
            return max(0.0, float(value or 0.0))
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _encode(cls, data: dict[str, Any]) -> tuple[
        dict[str, Any],
        dict[str, dict[str, Any]],
        dict[tuple[str, str], dict[str, Any]],
    ]:
        state = cls._payload(data)
        days = state.pop("days", {})
        hourly: dict[str, dict[str, Any]] = {}
        models: dict[tuple[str, str], dict[str, Any]] = {}
        if not isinstance(days, dict):
            return state, hourly, models

        for day_key, day in days.items():
            hours = day.get("hours") if isinstance(day, dict) else None
            if not isinstance(hours, dict):
                continue
            for hour_key, raw_bucket in hours.items():
                if not isinstance(raw_bucket, dict):
                    continue
                bucket_start = f"{day_key}T{str(hour_key).zfill(2)}"
                bucket = {
                    field: cls._integer(raw_bucket.get(field))
                    for field in _COUNT_FIELDS
                }
                bucket.update({
                    "success_duration_total_ms": cls._number(
                        raw_bucket.get("success_duration_total_ms")
                    ),
                    "success_duration_count": cls._integer(
                        raw_bucket.get("success_duration_count")
                    ),
                    "success_duration_histogram": cls._copy(
                        raw_bucket.get("success_duration_histogram")
                        if isinstance(raw_bucket.get("success_duration_histogram"), list)
                        else []
                    ),
                })
                hourly[bucket_start] = bucket

                model_names: set[str] = set()
                for source_field in _MODEL_COUNT_FIELDS.values():
                    values = raw_bucket.get(source_field)
                    if isinstance(values, dict):
                        model_names.update(str(name) for name in values if str(name).strip())
                for source_field in (
                    "model_success_total_times",
                    "model_success_time_counts",
                    "model_success_duration_histograms",
                ):
                    values = raw_bucket.get(source_field)
                    if isinstance(values, dict):
                        model_names.update(str(name) for name in values if str(name).strip())

                duration_totals = raw_bucket.get("model_success_total_times")
                duration_counts = raw_bucket.get("model_success_time_counts")
                histograms = raw_bucket.get("model_success_duration_histograms")
                for model_name in model_names:
                    model_bucket = {
                        target: cls._integer(
                            raw_bucket.get(source, {}).get(model_name)
                            if isinstance(raw_bucket.get(source), dict)
                            else 0
                        )
                        for target, source in _MODEL_COUNT_FIELDS.items()
                    }
                    model_bucket.update({
                        "success_duration_total_ms": cls._number(
                            duration_totals.get(model_name)
                            if isinstance(duration_totals, dict)
                            else 0
                        ),
                        "success_duration_count": cls._integer(
                            duration_counts.get(model_name)
                            if isinstance(duration_counts, dict)
                            else 0
                        ),
                        "success_duration_histogram": cls._copy(
                            histograms.get(model_name)
                            if isinstance(histograms, dict)
                            and isinstance(histograms.get(model_name), list)
                            else []
                        ),
                    })
                    models[(bucket_start, model_name)] = model_bucket
        return state, hourly, models

    @classmethod
    def _hour_payload(cls, row: DashboardMetricHourlyModel) -> dict[str, Any]:
        payload = {field: cls._integer(getattr(row, field)) for field in _COUNT_FIELDS}
        payload.update({
            "success_duration_total_ms": cls._number(row.success_duration_total_ms),
            "success_duration_count": cls._integer(row.success_duration_count),
            "success_duration_histogram": cls._copy(row.success_duration_histogram or []),
        })
        payload.update({
            "by_model": {},
            "model_success": {},
            "model_failed": {},
            "model_text_review": {},
            "model_rate_limited": {},
            "model_success_total_times": {},
            "model_success_time_counts": {},
            "model_success_duration_histograms": {},
        })
        return payload

    @classmethod
    def _decode(cls, session: Any) -> DashboardMetricsSnapshot:
        state_row = session.get(DashboardMetricStateModel, 1)
        if state_row is None:
            return DashboardMetricsSnapshot(data=None, revision=0)
        data = cls._payload(state_row.data)
        days: dict[str, Any] = {}
        hour_payloads: dict[str, dict[str, Any]] = {}
        for row in session.query(DashboardMetricHourlyModel).order_by(
            DashboardMetricHourlyModel.bucket_start.asc()
        ):
            day_key, hour_key = str(row.bucket_start).split("T", 1)
            payload = cls._hour_payload(row)
            days.setdefault(day_key, {"hours": {}})["hours"][hour_key] = payload
            hour_payloads[str(row.bucket_start)] = payload

        for row in session.query(DashboardMetricModelHourlyModel).order_by(
            DashboardMetricModelHourlyModel.bucket_start.asc(),
            DashboardMetricModelHourlyModel.model.asc(),
        ):
            bucket = hour_payloads.get(str(row.bucket_start))
            if bucket is None:
                continue
            model_name = str(row.model)
            for target, source in _MODEL_COUNT_FIELDS.items():
                bucket[source][model_name] = cls._integer(getattr(row, target))
            bucket["model_success_total_times"][model_name] = cls._number(
                row.success_duration_total_ms
            )
            bucket["model_success_time_counts"][model_name] = cls._integer(
                row.success_duration_count
            )
            bucket["model_success_duration_histograms"][model_name] = cls._copy(
                row.success_duration_histogram or []
            )

        data["days"] = days
        return DashboardMetricsSnapshot(
            data=data,
            revision=max(0, int(state_row.revision or 0)),
        )

    def load(self) -> DashboardMetricsSnapshot:
        session = self.Session()
        try:
            return self._decode(session)
        finally:
            session.close()

    @staticmethod
    def _assign(row: Any, payload: dict[str, Any]) -> bool:
        changed = False
        for field, value in payload.items():
            if getattr(row, field) != value:
                setattr(row, field, copy.deepcopy(value))
                changed = True
        return changed

    def update(
        self,
        updater: Callable[[dict[str, Any] | None], dict[str, Any]],
    ) -> DashboardMetricsSnapshot:
        session = self.Session()
        try:
            self._lock(session)
            current_snapshot = self._decode(session)
            payload = self._payload(updater(current_snapshot.data))
            state, hourly, models = self._encode(payload)
            changed = False

            state_row = session.get(DashboardMetricStateModel, 1)
            current_revision = current_snapshot.revision
            if state_row is None:
                state_row = DashboardMetricStateModel(
                    id=1,
                    data=state,
                    revision=1,
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(state_row)
                changed = True
            elif state_row.data != state:
                state_row.data = self._copy(state)
                changed = True

            existing_hours = {
                str(row.bucket_start): row
                for row in session.query(DashboardMetricHourlyModel).all()
            }
            for bucket_start in existing_hours.keys() - hourly.keys():
                session.delete(existing_hours[bucket_start])
                changed = True
            for bucket_start, bucket in hourly.items():
                row = existing_hours.get(bucket_start)
                if row is None:
                    session.add(DashboardMetricHourlyModel(bucket_start=bucket_start, **bucket))
                    changed = True
                else:
                    changed = self._assign(row, bucket) or changed

            existing_models = {
                (str(row.bucket_start), str(row.model)): row
                for row in session.query(DashboardMetricModelHourlyModel).all()
            }
            for key in existing_models.keys() - models.keys():
                session.delete(existing_models[key])
                changed = True
            for (bucket_start, model_name), model_bucket in models.items():
                row = existing_models.get((bucket_start, model_name))
                if row is None:
                    session.add(DashboardMetricModelHourlyModel(
                        bucket_start=bucket_start,
                        model=model_name,
                        **model_bucket,
                    ))
                    changed = True
                else:
                    changed = self._assign(row, model_bucket) or changed

            revision = current_revision + 1 if changed else current_revision
            if state_row.revision != revision:
                state_row.revision = revision
            if changed:
                state_row.updated_at = datetime.now(timezone.utc)
            session.commit()
            return DashboardMetricsSnapshot(data=self._copy(payload), revision=revision)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def replace(self, data: dict[str, Any]) -> DashboardMetricsSnapshot:
        payload = self._payload(data)
        return self.update(lambda _current: payload)

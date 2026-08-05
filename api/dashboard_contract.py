from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DashboardTimeRange = Literal["24h", "7d", "30d"]


class DashboardMetaView(BaseModel):
    schema_version: int
    generated_at: str
    metrics_schema_version: int
    selected_range: DashboardTimeRange
    available_ranges: list[DashboardTimeRange]


class DashboardMetricsView(BaseModel):
    status: Literal["ready", "degraded"]
    ready: bool
    stale: bool
    source: str
    source_revision: str | None
    last_ingested_at: str | None
    freshness_ms: int | None
    checkpoint_at: str | None
    failure_reason: str | None
    retention_days: int


class DashboardAccountView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total: int = 0
    cumulative_total: int = 0
    active: int = 0
    limited: int = 0
    abnormal: int = 0
    disabled: int = 0
    total_quota: int = 0
    unlimited_quota_count: int = 0
    unknown_quota_count: int = 0
    total_success: int = 0
    total_fail: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    healthy: bool = False


class DashboardTotalsView(BaseModel):
    total: int
    success: int
    failed: int
    rate_limited: int
    final_failed: int
    text_review: int
    measured: int
    success_rate: float | None
    avg_success_duration_ms: float | None
    p95_success_duration_ms: float | None


class DashboardBucketView(BaseModel):
    label: str
    start_at: str
    end_at: str
    total_calls: int
    success_calls: int
    final_failed_calls: int
    success_rate: float | None
    avg_success_duration_ms: float | None
    p95_success_duration_ms: float | None
    switch_requests: int
    switch_count: int
    switch_recovered: int
    switch_recovery_rate: float | None


class DashboardSwitchingView(BaseModel):
    requests: int
    count: int
    recovered: int
    recovery_rate: float | None


class DashboardModelView(BaseModel):
    name: str
    total_calls: int
    success_calls: int
    failed_calls: int
    rate_limited_calls: int
    final_failed_calls: int
    text_review_calls: int
    measured_calls: int
    success_rate: float | None
    avg_success_duration_ms: float | None
    p95_success_duration_ms: float | None
    call_series: list[int]
    success_series: list[int]
    failed_series: list[int]
    rate_limited_series: list[int]
    final_failed_series: list[int]
    text_review_series: list[int]
    avg_success_duration_series_ms: list[float | None]


class DashboardTrendView(BaseModel):
    labels: list[str]
    total_requests: list[int]
    success_requests: list[int]
    failed_requests: list[int]
    rate_limited_requests: list[int]
    final_failed_requests: list[int]
    text_review_requests: list[int]
    measured_requests: list[int]
    success_rate: list[float | None]
    switch_requests: list[int]
    switch_count: list[int]
    switch_recovered: list[int]
    model_requests: dict[str, list[int]]
    model_success_requests: dict[str, list[int]]
    model_failed_requests: dict[str, list[int]]
    model_rate_limited_requests: dict[str, list[int]]
    model_text_review_requests: dict[str, list[int]]
    model_avg_success_duration_ms: dict[str, list[float | None]]


class DashboardWindowView(BaseModel):
    requested: DashboardTimeRange
    start_at: str
    end_at: str
    bucket_unit: Literal["hour", "day"]
    bucket_count: int


class DashboardRangeView(BaseModel):
    time_range: DashboardTimeRange
    bucket_unit: Literal["hour", "day"]
    window: DashboardWindowView
    totals: DashboardTotalsView
    switching: DashboardSwitchingView
    buckets: list[DashboardBucketView]
    models: list[DashboardModelView]
    trend: DashboardTrendView


class DashboardImageStorageView(BaseModel):
    enabled: bool
    mode: Literal["local", "webdav", "both"]
    status: Literal["not_checked"]
    available: bool | None
    image_count: int | None
    image_size_bytes: int | None


class DashboardStorageView(BaseModel):
    application_database: dict
    image_storage: DashboardImageStorageView


class DashboardResponseView(BaseModel):
    status: Literal["ok", "degraded"]
    healthy: bool
    version: str
    meta: DashboardMetaView
    metrics: DashboardMetricsView
    accounts: DashboardAccountView
    storage: DashboardStorageView
    ranges: dict[DashboardTimeRange, DashboardRangeView]

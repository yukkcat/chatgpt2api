from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MonitorTone = Literal["success", "danger", "warning", "info", "muted"]


class StrictMonitorModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MonitorThreadpoolView(StrictMonitorModel):
    tokens: int = Field(ge=0)
    previous_tokens: int = Field(ge=0)


class MonitorWindowView(StrictMonitorModel):
    completed: int = Field(ge=0)
    completed_capacity: int = Field(ge=0)
    events: int = Field(ge=0)
    event_capacity: int = Field(ge=0)


class MonitorSlowCountsView(StrictMonitorModel):
    handler_queue: int = Field(ge=0)
    stream_first_queue: int = Field(ge=0)
    account_wait: int = Field(ge=0)
    egress_wait: int = Field(ge=0)
    total_over_120s: int = Field(ge=0)
    local_reject_or_busy: int = Field(ge=0)


class MonitorSummaryView(StrictMonitorModel):
    active: int = Field(ge=0)
    completed: int = Field(ge=0)
    success: int = Field(ge=0)
    partial_success: int = Field(ge=0)
    failed: int = Field(ge=0)
    rate_limited: int = Field(ge=0)
    text_review: int = Field(ge=0)
    measured: int = Field(ge=0)
    success_rate: float = Field(ge=0, le=100)
    account_switch_requests: int = Field(ge=0)
    account_switches: int = Field(ge=0)
    account_switch_success: int = Field(ge=0)
    account_switch_recovery_rate: float = Field(ge=0, le=100)
    switch_unrecovered: int = Field(ge=0)
    switch_average: float = Field(ge=0)
    stream_error_requests: int = Field(ge=0)
    avg_duration_ms: int = Field(ge=0)
    p95_duration_ms: int = Field(ge=0)
    entry_queue_p95_ms: int = Field(ge=0)
    active_egress_count: int = Field(ge=0)
    metric_p95: dict[str, int] = Field(default_factory=dict)
    slow_counts: MonitorSlowCountsView
    by_model: dict[str, int] = Field(default_factory=dict)
    active_by_model: dict[str, int] = Field(default_factory=dict)
    active_by_egress: dict[str, int] = Field(default_factory=dict)
    active_by_stage: dict[str, int] = Field(default_factory=dict)


class MonitorEgressView(StrictMonitorModel):
    source: str
    source_label: str
    label: str
    hash: str
    display: str
    key: str
    mode: str
    group_id: str
    node_id: str
    node_name: str
    has_proxy: bool | None = None


class MonitorAccountAttemptView(StrictMonitorModel):
    attempt: int = Field(ge=0)
    max_attempts: int = Field(ge=0)
    switch_count: int = Field(ge=0)
    image_count: int = Field(ge=0)
    display: str


class MonitorSlowMetricView(StrictMonitorModel):
    key: str
    label: str
    value_ms: int = Field(ge=0)
    value_text: str
    important: bool


class MonitorRecordPresentationView(StrictMonitorModel):
    status_label: str
    status_tone: MonitorTone
    stage_text: str
    error_text: str
    duration_text: str
    metric_digest: str
    egress_text: str
    account_attempt_text: str
    account_egress_text: str
    tracked_duration_ms: int = Field(ge=0)
    untracked_duration_ms: int = Field(ge=0)
    slow_metrics: list[MonitorSlowMetricView] = Field(default_factory=list)
    slow_reason_code: str
    slow_reason: str


class MonitorImageView(StrictMonitorModel):
    index: int | None = None
    total: int | None = None
    account_email: str | None = None
    previous_account_email: str | None = None
    account_attempt: int | None = None
    max_account_attempts: int | None = None
    account_switch_count: int | None = None
    stage: str | None = None
    stage_label: str | None = None
    updated_at: str | None = None
    status: str | None = None
    returned_result: bool | None = None
    returned_message: bool | None = None
    metrics: dict[str, int] = Field(default_factory=dict)
    proxy_source: str | None = None
    proxy_hash: str | None = None
    egress_key: str | None = None
    egress_label: str | None = None
    proxy_group_id: str | None = None
    proxy_node_id: str | None = None
    proxy_node_name: str | None = None
    image_egress_limit: int | None = None
    has_proxy: bool | None = None
    egress_mode: str | None = None
    local_reason: str | None = None
    failure_code: str | None = None
    failure_scope: str | None = None
    failure_capability: str | None = None
    failure_retryable: bool | None = None
    failure_account_failure: bool | None = None
    failure_retry_after: int | None = None
    status_code: int | None = None
    error_type: str | None = None
    public_error: str | None = None
    account_failure: bool | None = None
    switched_account: bool | None = None
    error: str | None = None
    raw_error: str | None = None
    upstream_error: str | None = None
    upstream_message: str | None = None


class MonitorEventView(StrictMonitorModel):
    time: str
    call_id: str
    event: str
    label: str
    detail_text: str
    model: str | None = None
    index: int | None = None
    total: int | None = None
    attempt: int | None = None
    account_email: str | None = None
    previous_account_email: str | None = None
    account_switch_count: int | None = None
    max_account_attempts: int | None = None
    status: str | None = None
    handler_queue_ms: int | None = None
    stream_first_queue_ms: int | None = None
    account_wait_ms: int | None = None
    egress_wait_ms: int | None = None
    upload_ms: int | None = None
    bootstrap_ms: int | None = None
    requirements_ms: int | None = None
    prepare_conversation_ms: int | None = None
    generation_start_ms: int | None = None
    http_dns_ms: int | None = None
    http_tcp_ms: int | None = None
    http_tls_ms: int | None = None
    http_wait_ms: int | None = None
    http_ttfb_ms: int | None = None
    http_total_ms: int | None = None
    sse_first_event_ms: int | None = None
    sse_max_gap_ms: int | None = None
    sse_last_gap_ms: int | None = None
    sse_stream_ms: int | None = None
    sse_event_count: int | None = None
    conversation_stream_ms: int | None = None
    stream_error_ms: int | None = None
    poll_wait_ms: int | None = None
    poll_request_ms: int | None = None
    resolve_ms: int | None = None
    download_ms: int | None = None
    response_ms: int | None = None
    stream_ms: int | None = None
    total_ms: int | None = None
    proxy_source: str | None = None
    proxy_hash: str | None = None
    egress_key: str | None = None
    egress_label: str | None = None
    proxy_group_id: str | None = None
    proxy_node_id: str | None = None
    proxy_node_name: str | None = None
    image_egress_limit: int | None = None
    egress_mode: str | None = None
    has_proxy: bool | None = None
    local_reason: str | None = None
    failure_code: str | None = None
    failure_scope: str | None = None
    failure_capability: str | None = None
    failure_retryable: bool | None = None
    failure_account_failure: bool | None = None
    failure_retry_after: int | None = None
    status_code: int | None = None
    error_type: str | None = None
    public_error: str | None = None
    account_failure: bool | None = None
    switched_account: bool | None = None
    error: str | None = None
    raw_error: str | None = None
    upstream_error: str | None = None
    upstream_message: str | None = None
    timing_text: str


class MonitorRecordView(StrictMonitorModel):
    call_id: str
    endpoint: str | None = None
    model: str | None = None
    summary: str | None = None
    role: str | None = None
    key_name: str | None = None
    status: str | None = None
    outcome: str | None = None
    stage: str | None = None
    stage_label: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    updated_at: str | None = None
    elapsed_ms: int | None = None
    stage_elapsed_ms: int | None = None
    duration_ms: int | None = None
    metrics: dict[str, int] = Field(default_factory=dict)
    perf: dict[str, int] = Field(default_factory=dict)
    timings_ms: dict[str, int] = Field(default_factory=dict)
    images: dict[str, MonitorImageView] = Field(default_factory=dict)
    account_email: str | None = None
    previous_account_email: str | None = None
    image_account_attempt: int | None = None
    image_account_max_attempts: int | None = None
    image_account_switch_count: int | None = None
    attempt_count: int | None = None
    switch_count: int | None = None
    image_requested_count: int | None = None
    image_succeeded_count: int | None = None
    image_failed_count: int | None = None
    image_result_status: str | None = None
    recovered_after_switch: bool | None = None
    public_error: str | None = None
    conversation_id: str | None = None
    error: str | None = None
    raw_error: str | None = None
    upstream_error: str | None = None
    upstream_message: str | None = None
    url_count: int | None = None
    proxy_source: str | None = None
    proxy_hash: str | None = None
    egress_key: str | None = None
    egress_label: str | None = None
    proxy_group_id: str | None = None
    proxy_node_id: str | None = None
    proxy_node_name: str | None = None
    image_egress_limit: int | None = None
    has_proxy: bool | None = None
    egress_mode: str | None = None
    local_reason: str | None = None
    failure_code: str | None = None
    failure_scope: str | None = None
    failure_capability: str | None = None
    failure_retryable: bool | None = None
    failure_account_failure: bool | None = None
    failure_retry_after: int | None = None
    status_code: int | None = None
    error_type: str | None = None
    account_failure: bool | None = None
    switched_account: bool | None = None
    egress: MonitorEgressView
    account_attempt: MonitorAccountAttemptView
    presentation: MonitorRecordPresentationView


class MonitorRecordDetailView(MonitorRecordView):
    events: list[MonitorEventView] = Field(default_factory=list)


class MonitorStageCountView(StrictMonitorModel):
    label: str
    count: int = Field(ge=0)


class MonitorDiagnosticItemView(StrictMonitorModel):
    key: str
    label: str
    value: int | float | str
    meta: str
    tone: MonitorTone


class MonitorDiagnosticGroupView(StrictMonitorModel):
    key: str
    title: str
    meta: str
    items: list[MonitorDiagnosticItemView]


class RealtimeMonitorView(StrictMonitorModel):
    schema_version: Literal[1]
    updated_at: str
    threadpool: MonitorThreadpoolView
    window: MonitorWindowView
    summary: MonitorSummaryView
    active: list[MonitorRecordView]
    recent: list[MonitorRecordView]
    slow: list[MonitorRecordView]
    metric_labels: dict[str, str]
    completed_window_text: str
    entry_queue_text: str
    active_stage_items: list[MonitorStageCountView]
    diagnostic_groups: list[MonitorDiagnosticGroupView]

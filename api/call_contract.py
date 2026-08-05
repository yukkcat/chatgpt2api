from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from api.request_detail_contract import (
    RequestDetailField as CallDetailField,
    RequestDetailPresentation,
    RequestPresentationTone as PresentationTone,
    RequestStatusPresentation as CallPresentationStatus,
    RequestTimelineCategory as TimelineCategory,
    RequestTimelineGroupPresentation as TimelineGroupPresentation,
    RequestTimelineLegendCategory as TimelineLegendCategory,
    RequestTimelineLegendPresentation as TimelineLegendPresentation,
    RequestTimelinePresentation as TimelinePresentation,
    RequestTimelineSegmentPresentation as TimelineSegmentPresentation,
    RequestTimelineStepPresentation as TimelineStepPresentation,
    RequestTimelineTone as TimelineTone,
)


CallBusiness = Literal[
    "account",
    "image_generation",
    "image_edit",
    "image_chat",
    "chat",
    "responses",
    "messages",
    "search",
    "file",
    "other",
]
CallOutcome = Literal[
    "success",
    "failed",
    "rate_limited",
    "text_review",
    "partial_success",
    "unknown",
]
AttemptResultStatus = Literal[
    "success",
    "failed",
    "generated_but_delivery_failed",
]
LogScope = Literal["page", "filtered"]
LogTotalScope = Literal["all", "type", "filtered"]
CallLogStatus = Literal["", "success", "failed", "limited"]
class CallPresentationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    primary: str
    secondary: str


class CallPresentationExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: str
    secondary: str


class CallPresentationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    diagnostics: str


class CallPresentationDuration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    breakdown: str
    tone: PresentationTone


class CallPresentation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: CallPresentationRequest
    execution: CallPresentationExecution
    status: CallPresentationStatus
    result: CallPresentationResult
    summary_text: str
    duration: CallPresentationDuration
    is_failure: bool


class AttemptPresentation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CallPresentationStatus
    failure_label: str
    marker_tone: Literal["success", "danger"]
    switch_label: str
    error_code_text: str
    status_code_text: str
    show_failure: bool
    show_error_details: bool
    timeline: TimelinePresentation


class AttemptGroupPresentation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: int = Field(ge=1)
    slot_label: str
    attempt_count: int = Field(ge=0)
    attempt_text: str
    switch_count: int = Field(ge=0)
    switch_text: str
    status: CallPresentationStatus


class CallDetailPresentation(RequestDetailPresentation):
    model_config = ConfigDict(extra="forbid")

    has_attempt_breakdown: bool
    attempt_groups: list[AttemptGroupPresentation] = Field(default_factory=list)


class CallSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    time: str
    type: str
    summary: str
    business: CallBusiness
    outcome: CallOutcome
    display_status: str
    endpoint: str
    model: str
    started_at: str
    ended_at: str
    duration_ms: int = Field(ge=0)
    key_id: str
    key_name: str
    role: str
    account_email: str
    conversation_id: str
    status_code: int = Field(ge=0)
    error_code: str
    public_error: str
    image_requested_count: int = Field(ge=0)
    image_succeeded_count: int = Field(ge=0)
    image_failed_count: int = Field(ge=0)
    image_result_status: str
    preview_image_url: str
    attempt_count: int = Field(ge=0)
    switch_count: int = Field(ge=0)
    recovered_after_switch: bool
    presentation: CallPresentation


class AttemptSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: int = Field(ge=1)
    attempt: int = Field(ge=1)
    account_email: str
    conversation_id: str
    status: str
    outcome: CallOutcome
    result_status: AttemptResultStatus
    duration_ms: int = Field(ge=0)
    status_code: int = Field(ge=0)
    error_code: str
    error_label: str
    public_error: str
    upstream_error: str
    upstream_text: str
    switched_account: bool | None
    presentation: AttemptPresentation
    timings_ms: dict[str, int] = Field(default_factory=dict)
    monitor: dict[str, Any] = Field(default_factory=dict)


class CallDetail(CallSummary):
    request_text: str
    request_text_full: str
    request_text_truncated: bool
    request_shape: dict[str, Any] = Field(default_factory=dict)
    request_meta: dict[str, Any] = Field(default_factory=dict)
    upstream_error: str
    upstream_text: str
    image_urls: list[str] = Field(default_factory=list)
    attempts: list[AttemptSummary] = Field(default_factory=list)
    timings_ms: dict[str, int] = Field(default_factory=dict)
    perf: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    monitor: dict[str, Any] = Field(default_factory=dict)
    detail_presentation: CallDetailPresentation
    raw_detail: dict[str, Any] = Field(default_factory=dict)


class LogFacets(BaseModel):
    statuses: dict[str, int] = Field(default_factory=dict)
    endpoints: dict[str, int] = Field(default_factory=dict)
    models: dict[str, int] = Field(default_factory=dict)
    accounts: dict[str, int] = Field(default_factory=dict)


class LogStats(BaseModel):
    total: int = Field(ge=0)
    success: int = Field(ge=0)
    text_review: int = Field(ge=0)
    failed: int = Field(ge=0)
    limited: int = Field(ge=0)
    image: int = Field(ge=0)


class CallSummaryPage(BaseModel):
    items: list[CallSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    has_more: bool
    facets_scope: LogScope
    stats_scope: LogScope
    total_scope: LogTotalScope
    facets: LogFacets
    stats: LogStats

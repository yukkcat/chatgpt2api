from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RequestPresentationTone = Literal["success", "danger", "warning", "info", "muted"]
RequestTimelineTone = Literal["info", "warning", "danger"]
RequestTimelineCategory = Literal["entry", "prepare", "upstream", "resolve", "download"]
RequestTimelineLegendCategory = Literal[
    "entry",
    "prepare",
    "upstream",
    "resolve",
    "download",
    "state",
]


class StrictRequestDetailModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequestStatusPresentation(StrictRequestDetailModel):
    label: str
    tone: RequestPresentationTone


class RequestTimelineSegmentPresentation(StrictRequestDetailModel):
    key: str
    label: str
    category: RequestTimelineCategory
    value_ms: int = Field(ge=0)
    value_text: str
    tone: RequestTimelineTone


class RequestTimelineStepPresentation(StrictRequestDetailModel):
    key: str
    label: str
    category: RequestTimelineCategory
    value_ms: int = Field(ge=0)
    value_text: str
    tone: RequestTimelineTone
    status_label: str
    time: str
    description: str


class RequestTimelineGroupPresentation(StrictRequestDetailModel):
    key: RequestTimelineCategory
    label: str
    steps: list[RequestTimelineStepPresentation] = Field(default_factory=list)


class RequestTimelineLegendPresentation(StrictRequestDetailModel):
    key: str
    label: str
    category: RequestTimelineLegendCategory
    tone: RequestTimelineTone


class RequestTimelinePresentation(StrictRequestDetailModel):
    segments: list[RequestTimelineSegmentPresentation] = Field(default_factory=list)
    legend_items: list[RequestTimelineLegendPresentation] = Field(default_factory=list)
    groups: list[RequestTimelineGroupPresentation] = Field(default_factory=list)


class RequestDetailField(StrictRequestDetailModel):
    label: str
    value: str
    copyable: bool = False
    wide: bool = False


class RequestDetailPresentation(StrictRequestDetailModel):
    primary_fields: list[RequestDetailField] = Field(default_factory=list)
    diagnostic_fields: list[RequestDetailField] = Field(default_factory=list)
    auto_expand_timeline: bool
    timeline: RequestTimelinePresentation

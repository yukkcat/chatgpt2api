from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ProxyReferenceMode = Literal["direct", "group", "custom"]
ProxyGroupStrategy = Literal["request_random", "time_window", "round_robin"]
ProxyHealthState = Literal["unknown", "healthy", "unhealthy"]
ProxyTestStatus = Literal["success", "partial", "failed"]
ProxyTestTone = Literal["success", "warning", "danger"]


class ProxyReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ProxyReferenceMode
    group_id: str = ""
    url: str = ""

    @model_validator(mode="after")
    def validate_reference(self) -> "ProxyReference":
        group_id = self.group_id.strip()
        url = self.url.strip()
        if self.mode == "direct":
            if group_id or url:
                raise ValueError(f"{self.mode} proxy reference cannot include group_id or url")
            return self
        if self.mode == "group":
            if not group_id:
                raise ValueError("group proxy reference requires group_id")
            if url:
                raise ValueError("group proxy reference cannot include url")
            return self
        if group_id:
            raise ValueError("custom proxy reference cannot include group_id")
        if not url:
            raise ValueError("custom proxy reference requires url")
        lower = url.lower()
        if lower in {"direct", "global"} or lower.startswith("group:"):
            raise ValueError("custom proxy reference uses a reserved value")
        return self


class ProxyDefaultsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_reference: ProxyReference
    fallback_reference: ProxyReference | None = None
class ProxyEffectiveReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["disabled", "direct", "group", "custom", "profile"]
    label: str
    configured: bool
    available: bool
    has_proxy: bool
    group_id: str = ""


class ProxyHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: ProxyHealthState = "unknown"
    checked_at: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    error: str | None = None


class ProxyNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    url: str
    enabled: bool
    image_concurrency_limit: int = Field(ge=0, le=10000)
    notes: str
    health: ProxyHealth


class ProxyNodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = ""
    name: str = ""
    url: str = ""
    enabled: bool = True
    image_concurrency_limit: int | float | str | None = None
    notes: str = ""
class ProxyGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    strategy: ProxyGroupStrategy
    rotation_interval_minutes: float = Field(ge=0, le=1440)
    enabled: bool
    notes: str
    nodes: list[ProxyNode]
    reference_text: str
    health: ProxyHealth
    can_delete: bool
    references: list[str]


class ProxyGroupPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = ""
    name: str | None = None
    strategy: ProxyGroupStrategy | None = None
    rotation_interval_minutes: float | None = Field(default=None, ge=0, le=1440)
    enabled: bool | None = None
    notes: str | None = None
    nodes: list[ProxyNodeInput] | None = None
    create_only: bool = False
class ProxyView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    generated_at: str
    revision: str
    default_reference: ProxyReference
    fallback_reference: ProxyReference | None
    effective_default: ProxyEffectiveReference
    effective_fallback: ProxyEffectiveReference
    groups: list[ProxyGroup]


class ProxyGroupList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    generated_at: str
    revision: str
    groups: list[ProxyGroup]


class ProxyGroupMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group: ProxyGroup
    revision: str


class ProxyGroupDeleteMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted_id: str
    revision: str


class ProxyNodeImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="", max_length=1_000_000)
    existing_urls: list[str] = Field(default_factory=list, max_length=10_000)


class ProxyNodeImportNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    image_concurrency_limit: int = Field(ge=0, le=10_000)


class ProxyNodeImportInvalidItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line: int = Field(ge=1)
    raw: str
    reason: str


class ProxyNodeImportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[ProxyNodeImportNode]
    added_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    invalid_count: int = Field(ge=0)
    invalid_items: list[ProxyNodeImportInvalidItem]


class ProxyDefaultsMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_reference: ProxyReference
    fallback_reference: ProxyReference | None
    effective_default: ProxyEffectiveReference
    effective_fallback: ProxyEffectiveReference
    revision: str


class ProxyTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    status: int = Field(ge=0, le=599)
    latency_ms: int = Field(ge=0)
    error: str | None = None
    proxy_source: str = "input"
    has_proxy: bool


class ProxyNodeTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    result: ProxyTestResult


class ProxyTestSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ProxyTestStatus
    tone: ProxyTestTone
    total: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    max_latency_ms: int = Field(ge=0)
    label: str
    message: str


class ProxyGroupTestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: ProxyTestSummary
    results: list[ProxyNodeTestResult]
    result: ProxyTestResult | None = None

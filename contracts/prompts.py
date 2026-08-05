from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PromptLibraryItem(_StrictModel):
    id: str = Field(min_length=1, max_length=160)
    source_id: str = Field(min_length=1, max_length=80)
    source_name: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1)
    description: str = ""
    preview: str = ""
    link: str = ""
    author: str = ""
    category: str = ""
    sub_category: str = ""
    tags: tuple[str, ...] = ()
    reference_image_urls: tuple[str, ...] = ()
    image_mode: Literal["", "generate", "edit"] = ""
    image_model: str = ""
    image_size: str = ""
    image_count: int | None = Field(default=None, ge=1)
    created_at: str = ""


class PromptSource(_StrictModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    url: str
    homepage: str
    enabled: bool
    built_in: bool = True
    sort_order: int
    prompt_count: int = Field(ge=0)
    cached: bool
    sync_state: Literal["disabled", "pending", "synced", "cached", "failed"]
    sync_label: str
    sync_message: str
    sync_tone: Literal["muted", "success", "warning", "danger"]
    last_sync_at: str = ""
    last_error: str = ""
    last_fetch_ms: int | None = Field(default=None, ge=0)


class PromptSourceError(_StrictModel):
    id: str
    name: str
    error: str


class PromptSourceSyncSummary(_StrictModel):
    status: Literal["success", "partial", "failed"]
    tone: Literal["success", "warning", "danger"]
    total: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    message: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_counts_and_tone(self) -> "PromptSourceSyncSummary":
        if self.succeeded + self.failed != self.total:
            raise ValueError("sync summary counts must match total")
        expected = (
            ("failed", "danger")
            if self.failed and not self.succeeded
            else ("partial", "warning")
            if self.failed
            else ("success", "success")
        )
        if (self.status, self.tone) != expected:
            raise ValueError("sync summary status and tone must match counts")
        return self


class PromptLibraryView(_StrictModel):
    schema_version: Literal[1] = 1
    generated_at: str
    revision: str = Field(min_length=1)
    registry_revision: str = ""
    registry_generated_at: str = ""
    synced: bool
    prompt_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    enabled_source_count: int = Field(ge=0)
    cached_source_count: int = Field(ge=0)
    source_error_count: int = Field(ge=0)
    sync_summary: PromptSourceSyncSummary
    source_errors: tuple[PromptSourceError, ...] = ()
    items: tuple[PromptLibraryItem, ...] = ()
    sources: tuple[PromptSource, ...] = ()

    @model_validator(mode="after")
    def validate_derived_counts(self) -> "PromptLibraryView":
        if self.prompt_count != len(self.items):
            raise ValueError("prompt_count must match items")
        if self.source_count != len(self.sources):
            raise ValueError("source_count must match sources")
        if self.enabled_source_count != sum(1 for source in self.sources if source.enabled):
            raise ValueError("enabled_source_count must match sources")
        if self.cached_source_count != sum(1 for source in self.sources if source.cached):
            raise ValueError("cached_source_count must match sources")
        if self.source_error_count != len(self.source_errors):
            raise ValueError("source_error_count must match source_errors")
        if self.sync_summary.total != self.enabled_source_count:
            raise ValueError("sync_summary.total must match enabled_source_count")
        if self.sync_summary.failed != self.source_error_count:
            raise ValueError("sync_summary.failed must match source_error_count")
        return self


class PromptSourceRequest(_StrictModel):
    enabled: bool | None = None

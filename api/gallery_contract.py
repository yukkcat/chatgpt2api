from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


GalleryMediaType = Literal["image"]
GalleryMediaFilter = Literal["all", "image"]
GalleryStorage = Literal["local", "webdav", "both"]
GenBoxPushStatus = Literal["imported", "already-imported", "duplicate-local"]


class GalleryGenBoxPushState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GenBoxPushStatus
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    updated_at: str


class GalleryRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    path: str
    filename: str
    url: str
    thumbnail_url: str
    size_bytes: int = Field(ge=0)
    created_at: str
    date: str
    media_type: GalleryMediaType
    expired: bool
    expires_at: str | None
    expires_in_seconds: int | None = Field(default=None, ge=0)
    tags: list[str] = Field(default_factory=list)
    storage: GalleryStorage
    local: bool
    webdav: bool
    available: bool
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    genbox_push: GalleryGenBoxPushState | None = None


class GalleryGenBoxPushRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=1024)


class GalleryGenBoxPushResult(GalleryGenBoxPushState):
    path: str
    source_retained: bool = True


class GalleryMediaFacets(BaseModel):
    all: int = Field(ge=0)
    image: int = Field(ge=0)


class GalleryFacets(BaseModel):
    media_types: GalleryMediaFacets
    tags: list[str] = Field(default_factory=list)


class GalleryPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    generated_at: str
    items: list[GalleryRow]
    total: int = Field(ge=0)
    total_size_bytes: int = Field(ge=0)
    retention_days: int = Field(ge=1)
    facets: GalleryFacets
    media_type: GalleryMediaFilter
    page: int = Field(ge=1)
    page_size: int = Field(ge=0)
    page_count: int = Field(ge=1)
    has_more: bool


class GalleryCleanupResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    removed: int = Field(ge=0)
    removed_size_bytes: int = Field(ge=0)
    retention_days: int = Field(ge=1)
    message: str = Field(min_length=1)


class GalleryCompressResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compressed: int = Field(ge=0)
    saved_bytes: int = Field(ge=0)
    saved_mb: int = Field(ge=0)
    message: str = Field(min_length=1)


class GalleryCleanupTargetResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    removed: int = Field(ge=0)
    freed_mb: int = Field(ge=0)
    target_free_mb: int = Field(ge=1)
    current_free_mb: int = Field(ge=0)
    done: bool
    dry_run: bool
    message: str = Field(min_length=1)

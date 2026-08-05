from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

from curl_cffi import requests as curl_requests

from contracts.prompts import (
    PromptLibraryItem,
    PromptLibraryView,
    PromptSource,
    PromptSourceError,
    PromptSourceSyncSummary,
)
from services.config import BASE_DIR
from services.storage.prompt_library_repository import PromptLibraryRepository


DEFAULT_PROMPT_LIBRARY_PATH = BASE_DIR / "services" / "default_prompt_library.json"
PROMPT_REGISTRY_SCHEMA_VERSION = 1
PROMPT_REGISTRY_MANIFEST_MAX_BYTES = 128 * 1024
PROMPT_REGISTRY_PAYLOAD_MAX_BYTES = 8 * 1024 * 1024
PROMPT_REGISTRY_TIMEOUT_SECS = 8
DEFAULT_PROMPT_SOURCE_ID = "banana-prompt-quicker"

_DEFAULT_REGISTRY_BASE = "https://raw.githubusercontent.com/yukkcat/image-prompts/main/dist"

_DEFAULT_REGISTRY_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "id": "banana-prompt-quicker",
        "name": "Banana Prompt Quicker",
        "homepage": "https://glidea.github.io/banana-prompt-quicker/",
        "upstream_url": "https://glidea.github.io/banana-prompt-quicker/prompts.json",
        "path": "sources/banana-prompt-quicker.json",
        "count": 0,
        "sha256": "",
    },
    {
        "id": "davidwu-gpt-image2-prompts",
        "name": "DavidWu GPT Image 2 Prompts",
        "homepage": "https://github.com/davidwuw0811-boop/awesome-gpt-image2-prompts",
        "upstream_url": "https://raw.githubusercontent.com/davidwuw0811-boop/awesome-gpt-image2-prompts/main/prompts.json",
        "path": "sources/davidwu-gpt-image2-prompts.json",
        "count": 0,
        "sha256": "",
    },
    {
        "id": "awesome-gpt-image",
        "name": "Awesome GPT Image",
        "homepage": "https://github.com/ZeroLu/awesome-gpt-image",
        "upstream_url": "https://raw.githubusercontent.com/ZeroLu/awesome-gpt-image/main/README.zh-CN.md",
        "path": "sources/awesome-gpt-image.json",
        "count": 0,
        "sha256": "",
    },
    {
        "id": "awesome-gpt4o-image-prompts",
        "name": "Awesome GPT-4o Image Prompts",
        "homepage": "https://github.com/ImgEdify/Awesome-GPT4o-Image-Prompts",
        "upstream_url": "https://raw.githubusercontent.com/ImgEdify/Awesome-GPT4o-Image-Prompts/main/README.zh-CN.md",
        "path": "sources/awesome-gpt4o-image-prompts.json",
        "count": 0,
        "sha256": "",
    },
    {
        "id": "youmind-gpt-image-2",
        "name": "YouMind GPT Image 2",
        "homepage": "https://github.com/YouMind-OpenLab/awesome-gpt-image-2",
        "upstream_url": "https://raw.githubusercontent.com/YouMind-OpenLab/awesome-gpt-image-2/main/README_zh.md",
        "path": "sources/youmind-gpt-image-2.json",
        "count": 0,
        "sha256": "",
    },
    {
        "id": "youmind-nano-banana-pro",
        "name": "YouMind Nano Banana Pro",
        "homepage": "https://github.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts",
        "upstream_url": "https://raw.githubusercontent.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts/main/README_zh.md",
        "path": "sources/youmind-nano-banana-pro.json",
        "count": 0,
        "sha256": "",
    },
)

_REGISTRY_ITEM_FIELDS = {
    "id",
    "sourceId",
    "title",
    "prompt",
    "description",
    "coverUrl",
    "referenceImageUrls",
    "tags",
    "author",
    "sourceUrl",
    "createdAt",
    "imageMode",
    "imageModel",
    "imageSize",
    "imageCount",
}
_REGISTRY_ITEM_REQUIRED_FIELDS = _REGISTRY_ITEM_FIELDS - {"imageSize", "imageCount"}


class PromptRegistryError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: object) -> str:
    return str(value or "").strip()


def _source_sync_projection(
    *,
    enabled: bool,
    cached: bool,
    last_sync_at: str,
    last_error: str,
) -> tuple[str, str, str, str]:
    if not enabled:
        return "disabled", "已停用", "提示词源已停用", "muted"
    if last_error:
        return (
            ("cached", "缓存可用", "同步失败，继续使用本地缓存", "warning")
            if cached
            else ("failed", "同步失败", "同步失败，当前没有可用缓存", "danger")
        )
    if cached or last_sync_at:
        return "synced", "已同步", "提示词源已更新到本地", "success"
    return "pending", "待同步", "提示词源等待首次同步", "muted"


def _source_sync_summary(
    *,
    total: int,
    failed: int,
    prompt_count: int,
) -> PromptSourceSyncSummary:
    succeeded = max(0, total - failed)
    if failed and not succeeded:
        return PromptSourceSyncSummary(
            status="failed",
            tone="danger",
            total=total,
            succeeded=0,
            failed=failed,
            message=f"词源同步失败：{failed} 个词源失败，已保留可用的本地缓存",
        )
    if failed:
        return PromptSourceSyncSummary(
            status="partial",
            tone="warning",
            total=total,
            succeeded=succeeded,
            failed=failed,
            message=f"词源同步完成：成功 {succeeded}，失败 {failed}，共 {prompt_count} 条提示词",
        )
    if not total:
        message = "没有启用的提示词源"
    else:
        message = f"词源同步完成：成功 {succeeded}，共 {prompt_count} 条提示词"
    return PromptSourceSyncSummary(
        status="success",
        tone="success",
        total=total,
        succeeded=succeeded,
        failed=0,
        message=message,
    )


def _clean_inline(value: object) -> str:
    return re.sub(r"\s+", " ", _clean(value)).strip()


def _clean_display_text(value: object) -> str:
    text = _clean(value)
    if not text:
        return ""
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&apos;", "'")
    )
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"</(?:p|div|li|h[1-6])>", " ", text, flags=re.I)
    text = re.sub(r"<img\b[^>\n]*(?:>|$)", " ", text, flags=re.I)
    text = re.sub(r"!\[[^\]]*]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = _clean(value).lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", "none", "null", ""}:
        return False
    return default


def _int_or_none(value: object) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _nonnegative_int(value: object, default: int = 0) -> int:
    parsed = _int_or_none(value)
    return max(0, parsed) if parsed is not None else default


def _string_tuple(value: object, *, max_items: int = 24) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    result: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item = _clean(raw)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
        if len(result) >= max_items:
            break
    return tuple(result)


def _valid_http_url(value: object, *, allow_empty: bool = True) -> str:
    url = _clean(value)
    if not url and allow_empty:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PromptRegistryError(f"invalid URL: {url[:120]}")
    return url


def _absolute_url(base: str, value: object) -> str:
    raw = _clean(value)
    if not raw:
        return ""
    resolved = urljoin(base, raw)
    try:
        return _valid_http_url(resolved)
    except PromptRegistryError:
        return ""


def _safe_registry_path(value: object) -> str:
    path = _clean(value).replace("\\", "/").lstrip("/")
    if not path or ".." in path.split("/") or not re.fullmatch(r"[A-Za-z0-9._/-]+", path):
        raise PromptRegistryError("invalid registry path")
    return path


def _content_revision(items: tuple[PromptLibraryItem, ...]) -> str:
    digest = hashlib.sha256()
    for item in items:
        digest.update(item.id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.prompt.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _snapshot_content_digest(
    registry_sources: list[dict[str, Any]],
    registry_revision: str,
    registry_generated_at: str,
    serialized_items: dict[str, list[dict[str, Any]]],
) -> str:
    payload = {
        "registry_sources": registry_sources,
        "registry_revision": registry_revision,
        "registry_generated_at": registry_generated_at,
        "items_by_source": serialized_items,
    }
    return hashlib.sha256(json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _normalize_image_mode(value: object) -> str:
    normalized = _clean(value).lower()
    if normalized in {"generate", "image", "text-to-image", "t2i"}:
        return "generate"
    if normalized in {"edit", "image-to-image", "i2i"}:
        return "edit"
    return ""


def _source_defaults(source_id: str) -> dict[str, Any]:
    for index, source in enumerate(_DEFAULT_REGISTRY_SOURCES):
        if source["id"] == source_id:
            return {"enabled": True, "sort_order": index * 10}
    return {"enabled": False, "sort_order": 9999}


def _default_registry_sources() -> list[dict[str, Any]]:
    return [dict(source) for source in _DEFAULT_REGISTRY_SOURCES]


def _normalize_registry_source(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise PromptRegistryError("registry source must be an object")
    source_id = _clean(raw.get("id"))
    if not re.fullmatch(r"[a-z0-9-]+", source_id):
        raise PromptRegistryError(f"invalid registry source id: {source_id[:80]}")
    sha256 = _clean(raw.get("sha256")).lower()
    if not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise PromptRegistryError(f"invalid registry source hash: {source_id}")
    count = _int_or_none(raw.get("count"))
    if count is None or count < 0:
        raise PromptRegistryError(f"invalid registry source count: {source_id}")
    name = _clean_inline(raw.get("name"))
    if not name:
        raise PromptRegistryError(f"registry source is missing a name: {source_id}")
    return {
        "id": source_id,
        "name": name[:120],
        "homepage": _valid_http_url(raw.get("homepage"), allow_empty=False),
        "upstream_url": _valid_http_url(raw.get("upstreamUrl"), allow_empty=False),
        "path": _safe_registry_path(raw.get("path")),
        "count": count,
        "sha256": sha256,
    }


def _normalize_cached_registry_source(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    source_id = _clean(raw.get("id"))
    if not re.fullmatch(r"[a-z0-9-]+", source_id):
        return None
    fallback = next((source for source in _DEFAULT_REGISTRY_SOURCES if source["id"] == source_id), {})
    try:
        homepage = _valid_http_url(raw.get("homepage") or fallback.get("homepage"), allow_empty=False)
        upstream_url = _valid_http_url(
            raw.get("upstream_url") or raw.get("upstreamUrl") or raw.get("url") or fallback.get("upstream_url"),
            allow_empty=False,
        )
        path = _safe_registry_path(raw.get("path") or fallback.get("path") or f"sources/{source_id}.json")
    except PromptRegistryError:
        return None
    return {
        "id": source_id,
        "name": (_clean_inline(raw.get("name")) or _clean_inline(fallback.get("name")) or source_id)[:120],
        "homepage": homepage,
        "upstream_url": upstream_url,
        "path": path,
        "count": _nonnegative_int(raw.get("count")),
        "sha256": _clean(raw.get("sha256")).lower(),
    }


def _normalize_registry_manifest(payload: bytes) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromptRegistryError("registry manifest is not valid JSON") from exc
    if not isinstance(raw, dict):
        raise PromptRegistryError("registry manifest must be an object")
    if raw.get("schemaVersion") != PROMPT_REGISTRY_SCHEMA_VERSION:
        raise PromptRegistryError(f"unsupported registry schema: {raw.get('schemaVersion')!r}")
    registry_revision = _clean(raw.get("registryHash")).lower()
    if not re.fullmatch(r"[a-f0-9]{64}", registry_revision):
        raise PromptRegistryError("registry manifest has an invalid registryHash")
    generated_at = _clean(raw.get("generatedAt"))
    if not generated_at:
        raise PromptRegistryError("registry manifest is missing generatedAt")
    prompts_path = _safe_registry_path(raw.get("promptsPath"))
    raw_sources = raw.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise PromptRegistryError("registry manifest has no sources")
    sources = [_normalize_registry_source(source) for source in raw_sources]
    source_ids = [source["id"] for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise PromptRegistryError("registry manifest has duplicate source ids")
    total = _int_or_none(raw.get("total"))
    if total is None or total < 0 or total != sum(source["count"] for source in sources):
        raise PromptRegistryError("registry manifest total does not match source counts")
    return {
        "revision": registry_revision,
        "generated_at": generated_at,
        "prompts_path": prompts_path,
        "total": total,
    }, sources, raw_sources


def _normalize_registry_item(raw: object, source: dict[str, Any]) -> PromptLibraryItem:
    if not isinstance(raw, dict):
        raise PromptRegistryError("registry prompt must be an object")
    unknown_fields = set(raw) - _REGISTRY_ITEM_FIELDS
    missing_fields = _REGISTRY_ITEM_REQUIRED_FIELDS - set(raw)
    if unknown_fields:
        raise PromptRegistryError(f"registry prompt contains unsupported fields: {sorted(unknown_fields)!r}")
    if missing_fields:
        raise PromptRegistryError(f"registry prompt is missing fields: {sorted(missing_fields)!r}")

    source_id = _clean(raw.get("sourceId"))
    item_id = _clean(raw.get("id"))
    if source_id != source["id"] or not item_id.startswith(f"{source_id}:"):
        raise PromptRegistryError(f"registry prompt has an invalid id/sourceId pair: {item_id[:120]}")
    title = _clean_inline(raw.get("title"))
    prompt = _clean(raw.get("prompt"))
    if not title or not prompt:
        raise PromptRegistryError(f"registry prompt is missing title or prompt: {item_id[:120]}")

    tags = _string_tuple(raw.get("tags"), max_items=24)
    references = _string_tuple(raw.get("referenceImageUrls"), max_items=12)
    for url in references:
        _valid_http_url(url, allow_empty=False)
    preview = _valid_http_url(raw.get("coverUrl"))
    link = _valid_http_url(raw.get("sourceUrl"), allow_empty=False)
    image_count = _int_or_none(raw.get("imageCount"))
    if "imageCount" in raw and (image_count is None or image_count < 1):
        raise PromptRegistryError(f"registry prompt has an invalid imageCount: {item_id[:120]}")
    return PromptLibraryItem(
        id=item_id,
        source_id=source_id,
        source_name=source["name"],
        title=title[:200],
        prompt=prompt,
        description=_clean_display_text(raw.get("description"))[:700],
        preview=preview,
        link=link,
        author=_clean_inline(raw.get("author"))[:120],
        category=tags[0][:80] if tags else "",
        sub_category=tags[1][:80] if len(tags) > 1 else "",
        tags=tags,
        reference_image_urls=references,
        image_mode=_normalize_image_mode(raw.get("imageMode")),
        image_model=_clean_inline(raw.get("imageModel"))[:80],
        image_size=_clean_inline(raw.get("imageSize"))[:40],
        image_count=image_count,
        created_at=_clean(raw.get("createdAt")),
    )


def _validate_registry_payload(
    manifest: dict[str, Any],
    sources: list[dict[str, Any]],
    raw_manifest_sources: list[dict[str, Any]],
    payload: bytes,
) -> dict[str, tuple[PromptLibraryItem, ...]]:
    expected_revision = hashlib.sha256(
        json.dumps(
            raw_manifest_sources,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + payload
    ).hexdigest()
    if expected_revision != manifest["revision"]:
        raise PromptRegistryError("registry manifest and prompt payload hashes do not match")
    try:
        raw_items = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromptRegistryError("registry prompt payload is not valid JSON") from exc
    if not isinstance(raw_items, list) or len(raw_items) != manifest["total"]:
        raise PromptRegistryError("registry prompt count does not match the manifest")

    sources_by_id = {source["id"]: source for source in sources}
    grouped: dict[str, list[PromptLibraryItem]] = {source_id: [] for source_id in sources_by_id}
    seen_ids: set[str] = set()
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise PromptRegistryError("registry prompt must be an object")
        source_id = _clean(raw_item.get("sourceId"))
        source = sources_by_id.get(source_id)
        if source is None:
            raise PromptRegistryError(f"registry prompt references an unknown source: {source_id[:80]}")
        item = _normalize_registry_item(raw_item, source)
        if item.id in seen_ids:
            raise PromptRegistryError(f"registry prompt id is duplicated: {item.id[:120]}")
        seen_ids.add(item.id)
        grouped[source_id].append(item)

    for source in sources:
        if len(grouped[source["id"]]) != source["count"]:
            raise PromptRegistryError(f"registry source count does not match: {source['id']}")
    return {source_id: tuple(items) for source_id, items in grouped.items()}


def _normalize_cached_item(raw: object, source: dict[str, Any]) -> PromptLibraryItem | None:
    if not isinstance(raw, dict):
        return None
    projected = {field: raw.get(field) for field in PromptLibraryItem.model_fields if field in raw}
    projected.setdefault("source_id", source["id"])
    projected.setdefault("source_name", source["name"])
    projected.setdefault("author", "")
    projected.setdefault("created_at", _clean(raw.get("created_at") or raw.get("created")))
    projected.setdefault("tags", raw.get("tags") if isinstance(raw.get("tags"), list) else [])
    projected.setdefault(
        "reference_image_urls",
        raw.get("reference_image_urls") if isinstance(raw.get("reference_image_urls"), list) else [],
    )
    try:
        return PromptLibraryItem.model_validate(projected)
    except Exception:
        return None


def _normalize_bundled_item(raw: object, source: dict[str, Any]) -> PromptLibraryItem | None:
    if not isinstance(raw, dict):
        return None
    title = _clean_inline(raw.get("title") or raw.get("name"))
    prompt = _clean(raw.get("prompt") or raw.get("content"))
    if not title or not prompt:
        return None
    raw_id = _clean(raw.get("id"))
    if raw_id:
        item_id = f"{source['id']}:{raw_id}"
    else:
        digest = hashlib.sha256(f"{title}\n{prompt}".encode("utf-8")).hexdigest()[:16]
        item_id = f"{source['id']}:{digest}"
    preview = _absolute_url(source["upstream_url"], raw.get("preview") or raw.get("image"))
    references = tuple(
        url
        for value in _string_tuple(raw.get("reference_image_urls") or raw.get("reference_images"), max_items=12)
        if (url := _absolute_url(source["upstream_url"], value))
    )
    image_count = _int_or_none(raw.get("image_count") or raw.get("n"))
    return PromptLibraryItem(
        id=item_id[:160],
        source_id=source["id"],
        source_name=source["name"],
        title=title[:200],
        prompt=prompt,
        description=_clean_display_text(raw.get("description") or raw.get("summary"))[:700],
        preview=preview,
        link=_absolute_url(source["upstream_url"], raw.get("link")) or source["homepage"],
        author=_clean_inline(raw.get("author"))[:120],
        category=_clean_inline(raw.get("category"))[:80],
        sub_category=_clean_inline(raw.get("sub_category") or raw.get("subcategory"))[:80],
        tags=_string_tuple(raw.get("tags"), max_items=24),
        reference_image_urls=references,
        image_mode=_normalize_image_mode(raw.get("image_mode") or raw.get("mode")),
        image_model=_clean_inline(raw.get("image_model") or raw.get("model"))[:80],
        image_size=_clean_inline(raw.get("image_size") or raw.get("size"))[:40],
        image_count=image_count if image_count and image_count > 0 else None,
        created_at=_clean(raw.get("created_at") or raw.get("created")),
    )


FetchBytes = Callable[[str, int], bytes]


class PromptLibraryService:
    def __init__(
        self,
        repository: PromptLibraryRepository | None = None,
        *,
        database_url: str | None = None,
        bundled_path: Path = DEFAULT_PROMPT_LIBRARY_PATH,
        registry_base: str | None = None,
        fetch_bytes: FetchBytes | None = None,
    ) -> None:
        if repository is not None and database_url is not None:
            raise ValueError("provide repository or database_url, not both")
        self.repository = repository or PromptLibraryRepository(database_url)
        self.bundled_path = bundled_path
        self._registry_base = self._normalize_registry_base(
            registry_base or self._configured_registry_base()
        )
        self._fetch_bytes = fetch_bytes or self._fetch_url_bytes
        self._state_lock = RLock()
        self._mutation_lock = Lock()
        self._loaded = False
        self._settings: dict[str, dict[str, Any]] = {}
        self._registry_sources: list[dict[str, Any]] = _default_registry_sources()
        self._registry_revision = ""
        self._registry_generated_at = ""
        self._items_by_source: dict[str, tuple[PromptLibraryItem, ...]] = {}
        self._source_status: dict[str, dict[str, Any]] = {}
        self._cache_verified = False
        self._view: PromptLibraryView | None = None

    @staticmethod
    def _normalize_registry_base(value: str) -> str:
        base = _clean(value).rstrip("/")
        if base.endswith("/manifest.json"):
            base = base[: -len("/manifest.json")]
        if not base:
            raise ValueError("prompt registry URL is required")
        return base

    @classmethod
    def _configured_registry_base(cls) -> str:
        return cls._normalize_registry_base(
            os.getenv("PROMPT_LIBRARY_REGISTRY_URL") or _DEFAULT_REGISTRY_BASE
        )

    @staticmethod
    def _fetch_url_bytes(url: str, max_bytes: int) -> bytes:
        headers = {
            "Accept": "application/json,*/*;q=0.5",
            "User-Agent": "chatgpt2api-prompt-library/4.0",
        }
        if urlparse(url).netloc.lower() == "api.github.com":
            headers["Accept"] = "application/vnd.github.raw+json"
        response = curl_requests.get(url, headers=headers, timeout=PROMPT_REGISTRY_TIMEOUT_SECS)
        response.raise_for_status()
        content_length = _int_or_none(response.headers.get("content-length"))
        if content_length is not None and content_length > max_bytes:
            raise PromptRegistryError(f"registry response exceeds {max_bytes} bytes")
        payload = response.content
        if len(payload) > max_bytes:
            raise PromptRegistryError(f"registry response exceeds {max_bytes} bytes")
        return payload

    @staticmethod
    def _registry_url(base: str, path: str) -> str:
        return f"{base.rstrip('/')}/{_safe_registry_path(path)}"

    def _load_settings_locked(self) -> None:
        data = self.repository.load().settings
        raw_sources = data.get("sources", [])
        if not isinstance(raw_sources, list):
            raw_sources = []
        settings: dict[str, dict[str, Any]] = {}
        for index, raw in enumerate(raw_sources):
            if not isinstance(raw, dict):
                continue
            source_id = _clean(raw.get("id"))
            if not re.fullmatch(r"[a-z0-9-]+", source_id):
                continue
            defaults = _source_defaults(source_id)
            settings[source_id] = {
                "enabled": _bool(raw.get("enabled"), defaults["enabled"]),
                "sort_order": _int_or_none(raw.get("sort_order"))
                if _int_or_none(raw.get("sort_order")) is not None
                else index * 10,
                "updated_at": _clean(raw.get("updated_at")),
            }
        self._settings = settings

    def _load_cache_locked(self) -> None:
        data = self.repository.load().snapshot
        registry = data.get("registry") if isinstance(data.get("registry"), dict) else {}
        raw_registry_sources = registry.get("sources") if isinstance(registry.get("sources"), list) else []
        registry_sources = [
            source
            for raw in raw_registry_sources
            if (source := _normalize_cached_registry_source(raw)) is not None
        ]
        registry_source_ids = [source["id"] for source in registry_sources]
        registry_metadata_valid = (
            bool(registry_sources)
            and len(registry_sources) == len(raw_registry_sources)
            and len(registry_source_ids) == len(set(registry_source_ids))
        )
        if registry_metadata_valid:
            self._registry_sources = registry_sources
            self._registry_revision = _clean(registry.get("revision"))
            self._registry_generated_at = _clean(registry.get("generated_at"))

        raw_items_by_source = data.get("items_by_source")
        raw_status = data.get("source_status")
        if not isinstance(raw_items_by_source, dict):
            legacy_sources = data.get("sources")
            raw_items_by_source = {
                _clean(source_id): cache.get("items", [])
                for source_id, cache in legacy_sources.items()
                if isinstance(legacy_sources, dict) and isinstance(cache, dict)
            } if isinstance(legacy_sources, dict) else {}
            raw_status = legacy_sources if isinstance(legacy_sources, dict) else {}
        if not isinstance(raw_status, dict):
            raw_status = {}

        sources_by_id = {source["id"]: source for source in self._registry_sources}
        for source_id, raw_items in raw_items_by_source.items():
            normalized_id = _clean(source_id)
            source = sources_by_id.get(normalized_id)
            if source is None or not isinstance(raw_items, list):
                continue
            items = tuple(
                item
                for raw in raw_items
                if (item := _normalize_cached_item(raw, source)) is not None
            )
            self._items_by_source[normalized_id] = items
            status = raw_status.get(normalized_id)
            status = status if isinstance(status, dict) else {}
            self._source_status[normalized_id] = {
                "content_revision": _clean(status.get("content_revision")) or _content_revision(items),
                "last_sync_at": _clean(status.get("last_sync_at")),
                "last_error": _clean(status.get("last_error")),
                "last_fetch_ms": _nonnegative_int(status.get("last_fetch_ms"))
                if _int_or_none(status.get("last_fetch_ms")) is not None
                else None,
            }

        serialized_items = {
            source_id: [item.model_dump(mode="python") for item in items]
            for source_id, items in self._items_by_source.items()
        }
        expected_digest = _clean(data.get("snapshot_digest")).lower()
        actual_digest = _snapshot_content_digest(
            self._registry_sources,
            self._registry_revision,
            self._registry_generated_at,
            serialized_items,
        )
        self._cache_verified = (
            data.get("snapshot_verified") is True
            and registry_metadata_valid
            and bool(re.fullmatch(r"[a-f0-9]{64}", self._registry_revision))
            and bool(re.fullmatch(r"[a-f0-9]{64}", expected_digest))
            and expected_digest == actual_digest
        )

    def _seed_bundled_locked(self) -> bool:
        if self._items_by_source.get(DEFAULT_PROMPT_SOURCE_ID) or not self.bundled_path.exists():
            return False
        source = next(
            (source for source in self._registry_sources if source["id"] == DEFAULT_PROMPT_SOURCE_ID),
            _default_registry_sources()[0],
        )
        try:
            raw = json.loads(self.bundled_path.read_text(encoding="utf-8"))
            raw_items = raw.get("prompts", []) if isinstance(raw, dict) else raw
            if not isinstance(raw_items, list):
                raise ValueError("bundled prompt library must contain an array")
            items = tuple(
                item
                for value in raw_items
                if (item := _normalize_bundled_item(value, source)) is not None
            )
        except Exception as exc:
            self._source_status[source["id"]] = {
                "content_revision": "",
                "last_sync_at": "",
                "last_error": f"bundled snapshot failed: {exc}"[:500],
                "last_fetch_ms": 0,
            }
            return True
        if not items:
            return False
        modified_at = datetime.fromtimestamp(self.bundled_path.stat().st_mtime, timezone.utc).isoformat()
        self._items_by_source[source["id"]] = items
        self._source_status[source["id"]] = {
            "content_revision": _content_revision(items),
            "last_sync_at": modified_at,
            "last_error": "",
            "last_fetch_ms": 0,
        }
        return True

    def _ensure_loaded(self) -> None:
        with self._state_lock:
            if self._loaded:
                return
            self._load_settings_locked()
            self._load_cache_locked()
            seeded = self._seed_bundled_locked()
            self._view = self._build_view_locked()
            self._loaded = True
            if seeded:
                self._save_cache_locked()

    @staticmethod
    def _source_setting(
        settings: dict[str, dict[str, Any]],
        source_id: str,
        index: int,
    ) -> dict[str, Any]:
        configured = settings.get(source_id)
        defaults = _source_defaults(source_id)
        return {
            "enabled": configured.get("enabled") if configured is not None else defaults["enabled"],
            "sort_order": configured.get("sort_order") if configured is not None else index * 10,
            "updated_at": configured.get("updated_at", "") if configured is not None else "",
        }

    def _source_setting_locked(self, source_id: str, index: int) -> dict[str, Any]:
        return self._source_setting(self._settings, source_id, index)

    def _ordered_sources_locked(self) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        combined = [
            (source, self._source_setting_locked(source["id"], index))
            for index, source in enumerate(self._registry_sources)
        ]
        return sorted(
            combined,
            key=lambda pair: (
                _nonnegative_int(pair[1].get("sort_order"), 9999),
                pair[0]["name"].lower(),
                pair[0]["id"],
            ),
        )

    def _build_view_locked(self) -> PromptLibraryView:
        source_models: list[PromptSource] = []
        enabled_items: list[PromptLibraryItem] = []
        source_errors: list[PromptSourceError] = []
        revision_sources: list[dict[str, Any]] = []
        for source, setting in self._ordered_sources_locked():
            source_id = source["id"]
            items = self._items_by_source.get(source_id, ())
            status = self._source_status.get(source_id, {})
            enabled = bool(setting["enabled"])
            last_error = _clean(status.get("last_error"))
            last_sync_at = _clean(status.get("last_sync_at"))
            cached = bool(items)
            sync_state, sync_label, sync_message, sync_tone = _source_sync_projection(
                enabled=enabled,
                cached=cached,
                last_sync_at=last_sync_at,
                last_error=last_error,
            )
            if enabled:
                enabled_items.extend(items)
            if enabled and last_error:
                source_errors.append(PromptSourceError(id=source_id, name=source["name"], error=last_error))
            source_models.append(PromptSource(
                id=source_id,
                name=source["name"],
                url=source["upstream_url"],
                homepage=source["homepage"],
                enabled=enabled,
                built_in=True,
                sort_order=_nonnegative_int(setting.get("sort_order"), 9999),
                prompt_count=len(items),
                cached=cached,
                sync_state=sync_state,
                sync_label=sync_label,
                sync_message=sync_message,
                sync_tone=sync_tone,
                last_sync_at=last_sync_at,
                last_error=last_error,
                last_fetch_ms=_int_or_none(status.get("last_fetch_ms")),
            ))
            revision_sources.append({
                "id": source_id,
                "enabled": enabled,
                "sort_order": _nonnegative_int(setting.get("sort_order"), 9999),
                "content_revision": _clean(status.get("content_revision")),
                "last_error": last_error,
            })

        revision = hashlib.sha256(json.dumps(
            {
                "registry_revision": self._registry_revision,
                "sources": revision_sources,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()[:24]
        enabled_source_count = sum(1 for source in source_models if source.enabled)
        source_error_count = len(source_errors)
        prompt_count = len(enabled_items)
        return PromptLibraryView(
            generated_at=_now_iso(),
            revision=revision,
            registry_revision=self._registry_revision,
            registry_generated_at=self._registry_generated_at,
            synced=any(source.cached for source in source_models),
            prompt_count=prompt_count,
            source_count=len(source_models),
            enabled_source_count=enabled_source_count,
            cached_source_count=sum(1 for source in source_models if source.cached),
            source_error_count=source_error_count,
            sync_summary=_source_sync_summary(
                total=enabled_source_count,
                failed=source_error_count,
                prompt_count=prompt_count,
            ),
            source_errors=tuple(source_errors),
            items=tuple(enabled_items),
            sources=tuple(source_models),
        )

    @staticmethod
    def _cache_payload(
        registry_sources: list[dict[str, Any]],
        registry_revision: str,
        registry_generated_at: str,
        items_by_source: dict[str, tuple[PromptLibraryItem, ...]],
        source_status: dict[str, dict[str, Any]],
        snapshot_verified: bool,
    ) -> dict[str, Any]:
        serialized_items = {
            source_id: [item.model_dump(mode="python") for item in items]
            for source_id, items in items_by_source.items()
        }
        return {
            "schema_version": 1,
            "updated_at": _now_iso(),
            "snapshot_verified": snapshot_verified,
            "snapshot_digest": _snapshot_content_digest(
                registry_sources,
                registry_revision,
                registry_generated_at,
                serialized_items,
            ),
            "registry": {
                "revision": registry_revision,
                "generated_at": registry_generated_at,
                "sources": registry_sources,
            },
            "items_by_source": serialized_items,
            "source_status": source_status,
        }

    def _cache_payload_locked(self) -> dict[str, Any]:
        return self._cache_payload(
            self._registry_sources,
            self._registry_revision,
            self._registry_generated_at,
            self._items_by_source,
            self._source_status,
            self._cache_verified,
        )

    def _save_cache_locked(self) -> None:
        self.repository.replace_snapshot(self._cache_payload_locked())

    @classmethod
    def _settings_payload(
        cls,
        registry_sources: list[dict[str, Any]],
        settings: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        sources = []
        for index, source in enumerate(registry_sources):
            setting = cls._source_setting(settings, source["id"], index)
            sources.append({
                "id": source["id"],
                "enabled": bool(setting["enabled"]),
                "sort_order": _nonnegative_int(setting.get("sort_order"), index * 10),
                "updated_at": _clean(setting.get("updated_at")),
            })
        return {"schema_version": 1, "sources": sources}

    def _snapshot_is_complete_locked(self, manifest: dict[str, Any], sources: list[dict[str, Any]]) -> bool:
        if not self._cache_verified or self._registry_revision != manifest["revision"]:
            return False
        expected_ids = {source["id"] for source in sources}
        if {source["id"] for source in self._registry_sources} != expected_ids:
            return False
        if set(self._items_by_source) != expected_ids:
            return False
        if sum(len(items) for items in self._items_by_source.values()) != manifest["total"]:
            return False
        seen_ids: set[str] = set()
        for source in sources:
            source_id = source["id"]
            items = self._items_by_source.get(source_id, ())
            status = self._source_status.get(source_id, {})
            if len(items) != source["count"]:
                return False
            if _clean(status.get("content_revision")) != source["sha256"]:
                return False
            for item in items:
                if (
                    item.source_id != source_id
                    or not item.id.startswith(f"{source_id}:")
                    or item.id in seen_ids
                ):
                    return False
                seen_ids.add(item.id)
        return True

    def _fetch_registry_candidate(
        self,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, tuple[PromptLibraryItem, ...]] | None]:
        manifest_payload = self._fetch_bytes(
            self._registry_url(self._registry_base, "manifest.json"),
            PROMPT_REGISTRY_MANIFEST_MAX_BYTES,
        )
        manifest, sources, raw_sources = _normalize_registry_manifest(manifest_payload)
        with self._state_lock:
            if self._snapshot_is_complete_locked(manifest, sources):
                return manifest, sources, None
        prompt_payload = self._fetch_bytes(
            self._registry_url(self._registry_base, manifest["prompts_path"]),
            PROMPT_REGISTRY_PAYLOAD_MAX_BYTES,
        )
        items_by_source = _validate_registry_payload(
            manifest,
            sources,
            raw_sources,
            prompt_payload,
        )
        return manifest, sources, items_by_source

    def view(self) -> PromptLibraryView:
        self._ensure_loaded()
        with self._state_lock:
            assert self._view is not None
            return self._view

    def update_source(self, source_id: str, payload: dict[str, Any]) -> PromptLibraryView | None:
        self._ensure_loaded()
        normalized_id = _clean(source_id)
        with self._mutation_lock:
            with self._state_lock:
                if normalized_id not in {source["id"] for source in self._registry_sources}:
                    return None
                candidate_settings = {
                    item_id: dict(setting)
                    for item_id, setting in self._settings.items()
                }
                current = dict(candidate_settings.get(normalized_id) or _source_defaults(normalized_id))
                if "enabled" in payload and payload["enabled"] is not None:
                    current["enabled"] = bool(payload["enabled"])
                current["updated_at"] = _now_iso()
                candidate_settings[normalized_id] = current
                registry_sources = list(self._registry_sources)
                settings_payload = self._settings_payload(registry_sources, candidate_settings)
            self.repository.replace_settings(settings_payload)
            with self._state_lock:
                self._settings = candidate_settings
                self._view = self._build_view_locked()
                return self._view

    def refresh(self, source_id: str = "") -> PromptLibraryView | None:
        self._ensure_loaded()
        normalized_id = _clean(source_id)
        with self._mutation_lock:
            with self._state_lock:
                known_ids = {source["id"] for source in self._registry_sources}
                if normalized_id and normalized_id not in known_ids:
                    return None
            started = time.monotonic()
            try:
                manifest, sources, items_by_source = self._fetch_registry_candidate()
                elapsed_ms = int((time.monotonic() - started) * 1000)
                now = _now_iso()
                with self._state_lock:
                    candidate_items = (
                        items_by_source
                        if items_by_source is not None
                        else dict(self._items_by_source)
                    )
                candidate_status = {
                    source["id"]: {
                        "content_revision": source["sha256"],
                        "last_sync_at": now,
                        "last_error": "",
                        "last_fetch_ms": elapsed_ms,
                    }
                    for source in sources
                }
                cache_payload = self._cache_payload(
                    sources,
                    manifest["revision"],
                    manifest["generated_at"],
                    candidate_items,
                    candidate_status,
                    True,
                )
                self.repository.replace_snapshot(cache_payload)
                with self._state_lock:
                    previous = (
                        self._registry_sources,
                        self._registry_revision,
                        self._registry_generated_at,
                        self._items_by_source,
                        self._source_status,
                        self._cache_verified,
                        self._view,
                    )
                    self._registry_sources = sources
                    self._registry_revision = manifest["revision"]
                    self._registry_generated_at = manifest["generated_at"]
                    self._items_by_source = candidate_items
                    self._source_status = candidate_status
                    self._cache_verified = True
                    try:
                        self._view = self._build_view_locked()
                    except Exception:
                        (
                            self._registry_sources,
                            self._registry_revision,
                            self._registry_generated_at,
                            self._items_by_source,
                            self._source_status,
                            self._cache_verified,
                            self._view,
                        ) = previous
                        raise
                    return self._view
            except Exception as exc:
                elapsed_ms = int((time.monotonic() - started) * 1000)
                error = str(exc)[:500]
                with self._state_lock:
                    targets = {normalized_id} if normalized_id else {
                        source["id"]
                        for index, source in enumerate(self._registry_sources)
                        if bool(self._source_setting_locked(source["id"], index)["enabled"])
                    }
                    candidate_status = {
                        source_id: dict(status)
                        for source_id, status in self._source_status.items()
                    }
                    for target in targets:
                        status = dict(candidate_status.get(target) or {})
                        status["last_error"] = error
                        status["last_fetch_ms"] = elapsed_ms
                        candidate_status[target] = status
                    cache_state = (
                        list(self._registry_sources),
                        self._registry_revision,
                        self._registry_generated_at,
                        dict(self._items_by_source),
                        self._cache_verified,
                    )
                try:
                    (
                        cache_sources,
                        cache_revision,
                        cache_generated_at,
                        cache_items,
                        cache_verified,
                    ) = cache_state
                    self.repository.replace_snapshot(
                        self._cache_payload(
                            cache_sources,
                            cache_revision,
                            cache_generated_at,
                            cache_items,
                            candidate_status,
                            cache_verified,
                        )
                    )
                except Exception:
                    pass
                with self._state_lock:
                    self._source_status = candidate_status
                    self._view = self._build_view_locked()
                    return self._view


prompt_library_service = PromptLibraryService()

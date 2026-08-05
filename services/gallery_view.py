from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any, Literal, Mapping

from utils.timezone import beijing_now, parse_to_beijing_naive


GalleryMediaFilter = Literal["all", "image"]


def _text(value: object) -> str:
    return str(value or "").strip()


def _non_negative_int(value: object) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _positive_int_or_none(value: object) -> int | None:
    parsed = _non_negative_int(value)
    return parsed if parsed > 0 else None


def _format_size(size_bytes: int) -> str:
    size = _non_negative_int(size_bytes)
    if size <= 0:
        return "0 B"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.2f} GB"


def _unique_texts(values: object) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    return list(dict.fromkeys(text for value in values if (text := _text(value))))


def _storage(item: Mapping[str, object]) -> tuple[str, bool, bool]:
    local = bool(item.get("local", True))
    webdav = bool(item.get("webdav", False))
    explicit = _text(item.get("storage")).lower()
    if explicit not in {"local", "webdav", "both"}:
        explicit = "both" if local and webdav else ("webdav" if webdav else "local")
    return explicit, local, webdav


def _expiry(item: Mapping[str, object], retention_days: int) -> tuple[bool, str | None, int | None]:
    created = parse_to_beijing_naive(item.get("created_at"))
    if created is None:
        return False, None, None
    expires = created + timedelta(days=retention_days)
    remaining = int((expires - beijing_now().replace(tzinfo=None)).total_seconds())
    return remaining <= 0, expires.strftime("%Y-%m-%d %H:%M:%S"), max(0, remaining)


def _thumbnail_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/image-thumbnails/{path}"


def gallery_row(
    item: Mapping[str, object],
    *,
    base_url: str,
    tags: list[str],
    retention_days: int,
) -> dict[str, Any]:
    path = _text(item.get("path") or item.get("rel") or item.get("name"))
    filename = _text(item.get("name") or item.get("filename")) or Path(path).name
    storage, local, webdav = _storage(item)
    expired, expires_at, expires_in_seconds = (
        _expiry(item, retention_days) if local else (False, None, None)
    )
    return {
        "id": path,
        "path": path,
        "filename": filename,
        "url": _text(item.get("url")) or f"{base_url.rstrip('/')}/images/{path}",
        "thumbnail_url": _thumbnail_url(base_url, path),
        "size_bytes": _non_negative_int(item.get("size") or item.get("size_bytes")),
        "created_at": _text(item.get("created_at")),
        "date": _text(item.get("date")),
        "media_type": "image",
        "expired": expired,
        "expires_at": expires_at,
        "expires_in_seconds": expires_in_seconds,
        "tags": _unique_texts(tags),
        "storage": storage,
        "local": local,
        "webdav": webdav,
        "available": local or webdav,
        "width": _positive_int_or_none(item.get("width")),
        "height": _positive_int_or_none(item.get("height")),
    }


def _matches_search(item: Mapping[str, object], search: str) -> bool:
    keyword = search.strip().lower()
    if not keyword:
        return True
    values = [
        item.get("filename"),
        item.get("path"),
        item.get("created_at"),
        item.get("storage"),
        *list(item.get("tags") or []),
    ]
    return any(keyword in _text(value).lower() for value in values)


def _page_meta(total: int, limit: int, offset: int) -> tuple[int, int, int, int]:
    page_size = max(0, min(int(limit or 0), 500))
    safe_offset = max(0, int(offset or 0))
    if page_size <= 0:
        return 1, total, 1, 0
    page_count = max(1, (total + page_size - 1) // page_size)
    page = min(safe_offset // page_size + 1, page_count)
    safe_offset = (page - 1) * page_size
    return page, page_size, page_count, safe_offset


def gallery_page(
    raw_items: list[Mapping[str, object]],
    *,
    base_url: str,
    tags_by_path: Mapping[str, list[str]],
    retention_days: int,
    limit: int,
    offset: int,
    media_type: GalleryMediaFilter,
    tag: str = "",
    search: str = "",
) -> dict[str, Any]:
    rows = [
        gallery_row(
            item,
            base_url=base_url,
            tags=tags_by_path.get(_text(item.get("path") or item.get("rel")), []),
            retention_days=retention_days,
        )
        for item in raw_items
    ]
    selected_tag = tag.strip()
    filtered = [
        item
        for item in rows
        if (not selected_tag or selected_tag == "all" or selected_tag in item["tags"])
        and _matches_search(item, search)
    ]
    media_facets = {
        "all": len(filtered),
        "image": sum(1 for item in filtered if item["media_type"] == "image"),
    }
    selected = filtered if media_type == "all" else [
        item for item in filtered if item["media_type"] == media_type
    ]
    total = len(selected)
    page, page_size, page_count, safe_offset = _page_meta(total, limit, offset)
    page_items = selected if page_size <= 0 else selected[safe_offset:safe_offset + page_size]
    all_tags = sorted({tag for values in tags_by_path.values() for tag in _unique_texts(values)})
    return {
        "schema_version": 1,
        "generated_at": beijing_now().isoformat(timespec="seconds"),
        "items": page_items,
        "total": total,
        "total_size_bytes": sum(int(item["size_bytes"]) for item in selected),
        "retention_days": retention_days,
        "facets": {
            "media_types": media_facets,
            "tags": all_tags,
        },
        "media_type": media_type,
        "page": page,
        "page_size": page_size,
        "page_count": page_count,
        "has_more": page < page_count,
    }


def gallery_cleanup_result(result: Mapping[str, object]) -> dict[str, Any]:
    removed = _non_negative_int(result.get("removed"))
    return {
        "removed": removed,
        "removed_size_bytes": _non_negative_int(result.get("removed_size_bytes")),
        "retention_days": max(1, _non_negative_int(result.get("retention_days"))),
        "message": (
            f"已清理 {removed} 个过期本地副本；"
            "仍有 WebDAV 副本的图库记录已保留。"
        ),
    }


def gallery_compress_result(result: Mapping[str, object]) -> dict[str, Any]:
    compressed = _non_negative_int(result.get("compressed"))
    saved_bytes = _non_negative_int(result.get("saved_bytes"))
    return {
        "compressed": compressed,
        "saved_bytes": saved_bytes,
        "saved_mb": _non_negative_int(result.get("saved_mb")),
        "message": f"压缩完成：处理 {compressed} 张，节省 {_format_size(saved_bytes)}。",
    }


def gallery_cleanup_target_result(
    result: Mapping[str, object],
    *,
    target_free_mb: int,
    dry_run: bool,
) -> dict[str, Any]:
    removed = _non_negative_int(result.get("removed"))
    freed_mb = _non_negative_int(result.get("freed_mb"))
    current_free_mb = _non_negative_int(result.get("current_free_mb"))
    normalized_target = max(
        1,
        _non_negative_int(result.get("target_free_mb", target_free_mb)),
    )
    normalized_dry_run = bool(result.get("dry_run", dry_run))
    done = bool(result.get("done", False))
    current_label = _format_size(current_free_mb * 1024 * 1024)
    target_label = _format_size(normalized_target * 1024 * 1024)
    freed_label = _format_size(freed_mb * 1024 * 1024)
    target_status = (
        f"当前剩余 {current_label} / 目标 {target_label}。"
        if done
        else f"当前剩余 {current_label} / 目标 {target_label}，仍未达到目标。"
    )
    if normalized_dry_run and removed > 0:
        message = (
            f"预估会清理 {removed} 张，预计释放 {freed_label}。"
            f"{target_status}"
        )
    elif normalized_dry_run and done:
        message = f"无需清理：当前剩余 {current_label}，已达到目标 {target_label}。"
    elif removed > 0:
        message = (
            f"已清理 {removed} 张，释放 {freed_label}。"
            f"{target_status}"
        )
    elif done:
        message = (
            f"没有需要清理的图片。当前剩余 {current_label} / 目标 {target_label}。"
        )
    else:
        message = f"没有可清理的图片。{target_status}"
    return {
        "removed": removed,
        "freed_mb": freed_mb,
        "target_free_mb": normalized_target,
        "current_free_mb": current_free_mb,
        "done": done,
        "dry_run": normalized_dry_run,
        "message": message,
    }

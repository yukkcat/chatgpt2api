from __future__ import annotations

import io
import threading
import zipfile
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps

from services.config import config
from services.gallery_view import gallery_page
from services.image_storage_service import (
    ImageBatchDeleteError,
    image_local_path,
    image_storage_service,
    normalize_image_relative_path,
)
from services.image_tags_service import load_tags, remove_tags

THUMBNAIL_SIZE = (320, 320)


def _cleanup_empty_dirs(root: Path) -> None:
    for path in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass


def get_image_response(relative_path: str) -> FileResponse | Response:
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }
    if image_storage_service.has_local(relative_path):
        return FileResponse(
            image_local_path(relative_path, require_file=True),
            headers=headers,
        )
    return Response(content=image_storage_service.get_bytes(relative_path), media_type="image/png", headers=headers)


def _thumbnail_path(relative_path: str) -> Path:
    rel = normalize_image_relative_path(relative_path)
    return config.image_thumbnails_dir / f"{rel}.png"


def thumbnail_url(base_url: str, relative_path: str) -> str:
    rel = normalize_image_relative_path(relative_path)
    return f"{base_url.rstrip('/')}/image-thumbnails/{rel}"


def _image_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        return None


def ensure_thumbnail(relative_path: str) -> Path:
    target = _thumbnail_path(relative_path)
    source_mtime = 0.0
    source: Path | None = None
    if image_storage_service.has_local(relative_path):
        source = image_local_path(relative_path, require_file=True)
        source_mtime = source.stat().st_mtime
    if target.exists() and (not source_mtime or target.stat().st_mtime >= source_mtime):
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        image_source = source if source is not None else io.BytesIO(image_storage_service.get_bytes(relative_path))
        with Image.open(image_source) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            image.save(target, format="PNG", optimize=True)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="failed to create thumbnail") from exc
    return target


def get_thumbnail_response(relative_path: str) -> FileResponse:
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }
    return FileResponse(ensure_thumbnail(relative_path), headers=headers)


def get_image_download_response(relative_path: str) -> FileResponse:
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }
    if image_storage_service.has_local(relative_path):
        path = image_local_path(relative_path, require_file=True)
        headers = {**cors_headers, "Content-Disposition": f'attachment; filename="{path.name}"'}
        return FileResponse(path, filename=path.name, headers=headers)
    rel = normalize_image_relative_path(relative_path)
    headers = {
        **cors_headers,
        "Content-Disposition": f'attachment; filename="{Path(rel).name}"',
    }
    return Response(
        content=image_storage_service.get_bytes(rel),
        media_type="image/png",
        headers=headers,
    )


def cleanup_image_thumbnails() -> int:
    thumbnails_root = config.image_thumbnails_dir
    removed = 0
    candidates: dict[Path, str] = {}
    for path in thumbnails_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(thumbnails_root).as_posix()
        if not rel.endswith(".png"):
            path.unlink()
            removed += 1
            continue
        candidates[path] = rel[:-4]

    existing = image_storage_service.existing_paths(list(candidates.values()))
    for path, rel in candidates.items():
        if rel not in existing:
            path.unlink()
            removed += 1
    _cleanup_empty_dirs(thumbnails_root)
    return removed


def _retention_hours(value: int | float | str | None, fallback: int) -> int:
    try:
        return max(1, int(float(value or fallback)))
    except (TypeError, ValueError):
        return max(1, int(fallback))


def _retention_cleanup_targets(retention_hours: int) -> list[tuple[str, int]]:
    hours = _retention_hours(retention_hours, config.image_retention_hours)
    raw_items = image_storage_service.list_items("", refresh_index=True, verify_existing=True)
    projection = gallery_page(
        raw_items,
        base_url="",
        tags_by_path={},
        retention_hours=hours,
        limit=0,
        offset=0,
        media_type="all",
    )
    return [
        (str(item["path"]), int(item["size_bytes"]))
        for item in projection["items"]
        if item["expired"] and item["local"]
    ]


def preview_image_retention_cleanup(retention_hours: int | None = None) -> dict[str, int | bool]:
    hours = _retention_hours(retention_hours, config.image_retention_hours)
    targets = _retention_cleanup_targets(hours)
    return {
        "removed": len(targets),
        "removed_size_bytes": sum(size for _, size in targets),
        "retention_hours": hours,
        "dry_run": True,
    }


def cleanup_image_retention(retention_hours: int | None = None) -> dict[str, int | bool]:
    hours = _retention_hours(retention_hours, config.image_retention_hours)
    targets = _retention_cleanup_targets(hours)
    removed = 0
    removed_size_bytes = 0
    target_sizes = dict(targets)
    removed_local = image_storage_service.delete_local_copies(list(target_sizes))
    for rel, remote_remains in removed_local.items():
        removed += 1
        removed_size_bytes += target_sizes.get(rel, 0)
        if remote_remains:
            continue
        for thumbnail in (
            _thumbnail_path(rel),
            config.image_thumbnails_dir / normalize_image_relative_path(rel),
        ):
            if thumbnail.is_file():
                thumbnail.unlink()
        remove_tags(rel)
    cleanup_image_thumbnails()
    _cleanup_empty_dirs(config.images_dir)
    _cleanup_empty_dirs(config.image_thumbnails_dir)
    return {
        "removed": removed,
        "removed_size_bytes": removed_size_bytes,
        "retention_hours": hours,
        "dry_run": False,
    }


def cleanup_expired_images(retention_hours: int | None = None) -> dict[str, int]:
    from services.retention_cleanup_service import retention_cleanup_coordinator

    result = retention_cleanup_coordinator.run_images(retention_hours)
    return {
        "removed": int(result["removed"]),
        "removed_size_bytes": int(result["removed_size_bytes"]),
        "retention_hours": int(result["retention_hours"]),
    }


def list_images(
    base_url: str,
    start_date: str = "",
    end_date: str = "",
    *,
    limit: int = 0,
    offset: int = 0,
    media_type: str = "all",
    tag: str = "",
    search: str = "",
) -> dict[str, object]:
    paged = int(limit or 0) > 0
    raw_items = image_storage_service.list_items(
        base_url,
        start_date,
        end_date,
        refresh_index=not paged,
        verify_existing=not paged,
    )
    wanted_type = str(media_type or "all").strip().lower()
    if wanted_type not in {"all", "image"}:
        wanted_type = "all"
    genbox_push_settings = config.get_genbox_push_settings()
    return gallery_page(
        raw_items,
        base_url=base_url,
        tags_by_path=load_tags(),
        retention_hours=config.image_retention_hours,
        limit=limit,
        offset=offset,
        media_type=wanted_type,
        genbox_push_enabled=bool(genbox_push_settings.get("enabled")),
        tag=tag,
        search=search,
    )


def delete_images(paths: list[str] | None = None, start_date: str = "", end_date: str = "", all_matching: bool = False) -> dict[str, int]:
    root = config.images_dir.resolve()
    targets = [
        str(item["path"])
        for item in image_storage_service.list_items("", start_date=start_date, end_date=end_date)
    ] if all_matching else (paths or [])
    valid_targets: list[str] = []
    for item in targets:
        path = (root / item).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            continue
        valid_targets.append(item)

    terminal_error: Exception | None = None
    try:
        removed_paths = image_storage_service.delete_many(valid_targets)
        completed_targets = valid_targets
    except ImageBatchDeleteError as exc:
        removed_paths = set()
        completed_targets = list(exc.completed_rels)
        terminal_error = exc.cause

    for item in completed_targets:
        for thumbnail in (
            _thumbnail_path(item),
            config.image_thumbnails_dir / normalize_image_relative_path(item),
        ):
            if thumbnail.is_file():
                thumbnail.unlink()
        remove_tags(item)
    if terminal_error is not None:
        raise terminal_error
    _cleanup_empty_dirs(root)
    _cleanup_empty_dirs(config.image_thumbnails_dir)
    return {"removed": len(removed_paths)}


def download_images_zip(paths: list[str]) -> io.BytesIO:
    root = config.images_dir.resolve()
    buf = io.BytesIO()
    added = 0
    used_names: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in paths:
            rel = normalize_image_relative_path(item)
            path = (root / rel).resolve()
            payload: bytes | None = None
            try:
                path.relative_to(root)
            except ValueError:
                continue
            try:
                payload = image_storage_service.get_bytes(rel)
            except Exception:
                continue
            name = path.name
            if name in used_names:
                stem = path.stem
                suffix = path.suffix
                counter = 2
                while f"{stem}_{counter}{suffix}" in used_names:
                    counter += 1
                name = f"{stem}_{counter}{suffix}"
            used_names.add(name)
            zf.writestr(name, payload)
            added += 1
    if added == 0:
        raise HTTPException(status_code=404, detail="no images found")
    buf.seek(0)
    return buf
def storage_stats() -> dict:
    import shutil
    usage = shutil.disk_usage(config.images_dir)
    total_mb = usage.total // (1024 * 1024)
    used_mb = usage.used // (1024 * 1024)
    free_mb = usage.free // (1024 * 1024)

    image_count = 0
    image_size = 0
    for p in config.images_dir.rglob("*"):
        if p.is_file():
            image_count += 1
            image_size += p.stat().st_size

    return {
        "disk_total_mb": total_mb,
        "disk_used_mb": used_mb,
        "disk_free_mb": free_mb,
        "image_count": image_count,
        "image_size_mb": image_size // (1024 * 1024),
        "image_size_bytes": image_size,
    }


def compress_images(quality: int = 60) -> dict:
    """重新压缩所有图片，返回节省的空间"""
    return image_storage_service.compress_local_images(quality)


def delete_to_target(target_free_mb: int, dry_run: bool = False) -> dict:
    """删除最旧的图片直到剩余空间达到 target_free_mb"""
    import shutil
    usage = shutil.disk_usage(config.images_dir)
    mebibyte = 1024 * 1024
    target_free_bytes = max(0, int(target_free_mb)) * mebibyte
    current_free_bytes = int(usage.free)
    current_free = current_free_bytes // mebibyte
    if current_free_bytes >= target_free_bytes and not dry_run:
        return {"removed": 0, "current_free_mb": current_free, "target_free_mb": target_free_mb, "done": True}

    files = sorted(
        (p for p in config.images_dir.rglob("*.png") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
    )
    removals = image_storage_service.delete_local_copies_until(
        [p.relative_to(config.images_dir).as_posix() for p in files],
        max(0, target_free_bytes - current_free_bytes),
        dry_run=dry_run,
    )
    freed = sum(removal.size for removal in removals)
    for removal in removals:
        if dry_run:
            continue
        rel = removal.rel
        for thumbnail in (
            _thumbnail_path(rel),
            config.image_thumbnails_dir / normalize_image_relative_path(rel),
        ):
            if thumbnail.is_file():
                thumbnail.unlink()
        if not removal.remote_remains:
            remove_tags(rel)

    if not dry_run:
        _cleanup_empty_dirs(config.images_dir)
        _cleanup_empty_dirs(config.image_thumbnails_dir)

    return {
        "removed": len(removals),
        "freed_mb": freed // mebibyte,
        "target_free_mb": target_free_mb,
        "current_free_mb": (current_free_bytes + freed) // mebibyte,
        "done": current_free_bytes + freed >= target_free_bytes,
        "dry_run": dry_run,
    }

def _auto_cleanup_worker(stop_event: threading.Event) -> None:
    from services.retention_cleanup_service import retention_cleanup_coordinator

    retention_cleanup_coordinator.scheduler_worker(stop_event)


def start_image_cleanup_scheduler(stop_event: threading.Event) -> threading.Thread:
    from services.retention_cleanup_service import start_retention_cleanup_scheduler

    return start_retention_cleanup_scheduler(stop_event)

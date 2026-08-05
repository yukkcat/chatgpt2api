from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.call_contract import CallDetail, CallLogStatus, CallSummaryPage
from api.dashboard_contract import DashboardResponseView
from api.gallery_contract import (
    GalleryCleanupResult,
    GalleryCleanupTargetResult,
    GalleryCompressResult,
    GalleryGenBoxPushRequest,
    GalleryGenBoxPushResult,
    GalleryMediaFilter,
    GalleryPage,
)
from api.monitor_contract import MonitorRecordDetailView, RealtimeMonitorView
from contracts.auth import AuthView
from contracts.models import ModelCatalogView
from contracts.proxy import (
    ProxyDefaultsMutation,
    ProxyDefaultsRequest,
    ProxyGroupDeleteMutation,
    ProxyGroupMutation,
    ProxyGroupPatch,
    ProxyGroupTestResponse,
    ProxyNodeImportRequest,
    ProxyNodeImportResult,
    ProxyView,
)
from contracts.settings import (
    PublicThirdPartyAppsView,
    SettingsMutationResult,
    SettingsPatch,
    SettingsView,
)
from api.support import require_admin, require_identity, resolve_image_base_url
from services.account_service import account_service
from services.auth_view import build_auth_view
from services.backup_service import BackupError, backup_service
from services.config import config
from services.gallery_view import (
    gallery_cleanup_result,
    gallery_cleanup_target_result,
    gallery_compress_result,
)
from services.genbox_push_service import push_gallery_image
from services.image_service import (
    cleanup_expired_images,
    compress_images,
    delete_images,
    download_images_zip,
    get_image_download_response,
    get_image_response,
    get_thumbnail_response,
    list_images,
    storage_stats,
)
from services.dashboard_view import build_dashboard_view
from services.image_storage_service import ImageStorageError, image_storage_service
from services.image_tags_service import set_tags
from services.log_service import log_service
from services.model_catalog_service import get_model_catalog
from services.monitor_view import build_monitor_record_view, build_monitor_view
from services.proxy_management_service import (
    ProxyGroupInUseError,
    normalize_proxy_node_url,
    proxy_management_service,
)
from services.proxy_service import proxy_settings, test_clearance, test_proxy
from services.realtime_monitor_service import realtime_monitor_service
from services.retention_cleanup_service import retention_cleanup_coordinator
from services.settings_management_service import (
    SettingsRevisionConflictError,
    settings_management_service,
)


class ProxyTestRequest(BaseModel):
    url: str = ""


class ClearanceTestRequest(BaseModel):
    target_url: str = "https://chatgpt.com"


class ProxyGroupTestRequest(BaseModel):
    id: str = ""
    node_id: str = ""
    url: str = ""


class ImageDeleteRequest(BaseModel):
    paths: list[str] = []
    start_date: str = ""
    end_date: str = ""
    all_matching: bool = False

class ImageDownloadRequest(BaseModel):
    paths: list[str]

class ImageTagsRequest(BaseModel):
    path: str
    tags: list[str]

class LogDeleteRequest(BaseModel):
    ids: list[str] = []
class BackupDeleteRequest(BaseModel):
    key: str = ""


class RetentionCleanupRequest(BaseModel):
    log_retention_days: int | None = None
    image_retention_days: int | None = None


class AccountCleanupRequest(BaseModel):
    auto_remove_invalid_accounts: bool | None = None
    auto_remove_rate_limited_accounts: bool | None = None


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _settings_write_error_message(exc: OSError) -> str:
    return (
        "保存设置失败：后端无法写入 Application Database。"
        "请检查数据库连接、权限和磁盘空间。"
        f"原始错误：{exc}"
    )


def _retention_cleanup_payload(body: RetentionCleanupRequest | None = None, *, dry_run: bool) -> dict[str, Any]:
    body = body or RetentionCleanupRequest()
    log_days = body.log_retention_days or config.log_retention_days
    image_days = body.image_retention_days or config.image_retention_days
    return retention_cleanup_coordinator.run_retention(
        log_retention_days=log_days,
        image_retention_days=image_days,
        dry_run=dry_run,
    )


def _notify_retention_cleanup_if_changed(changed_fields: list[str]) -> None:
    retention_fields = {"log_retention_days", "image_retention_days"}
    if retention_fields.intersection(changed_fields):
        retention_cleanup_coordinator.notify_retention_change()


def _account_cleanup_payload(body: AccountCleanupRequest | None = None, *, dry_run: bool) -> dict[str, Any]:
    body = body or AccountCleanupRequest()
    kwargs = {
        "remove_invalid": body.auto_remove_invalid_accounts,
        "remove_rate_limited": body.auto_remove_rate_limited_accounts,
    }
    if dry_run:
        return account_service.preview_auto_remove_accounts(**kwargs)
    return account_service.cleanup_auto_remove_accounts(**kwargs)


def _proxy_group_id(value: object) -> str:
    raw = _clean_text(value)
    if raw.lower().startswith("group:"):
        raw = raw.split(":", 1)[1]
    return raw.strip()


def create_router(app_version: str) -> APIRouter:
    router = APIRouter()

    @router.post("/auth/login", response_model=AuthView)
    async def login(authorization: str | None = Header(default=None)):
        identity = require_identity(authorization)
        return build_auth_view(app_version, identity)

    @router.get("/auth/status", response_model=AuthView)
    async def auth_status(authorization: str | None = Header(default=None)):
        try:
            identity = require_identity(authorization)
        except HTTPException:
            return build_auth_view(app_version)
        return build_auth_view(app_version, identity)

    @router.get("/version")
    async def get_version():
        return {"version": app_version}

    @router.get("/api/settings", response_model=SettingsView)
    async def get_settings(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return await run_in_threadpool(settings_management_service.view)

    @router.get("/api/third-party-apps", response_model=PublicThirdPartyAppsView)
    async def get_third_party_apps(authorization: str | None = Header(default=None)):
        require_identity(authorization)
        return await run_in_threadpool(settings_management_service.public_third_party_apps_view)

    @router.patch("/api/settings", response_model=SettingsMutationResult)
    async def save_settings(body: SettingsPatch, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            result = await run_in_threadpool(settings_management_service.update, body)
            _notify_retention_cleanup_if_changed(result.changed_fields)
            return result
        except SettingsRevisionConflictError as exc:
            raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail={"error": _settings_write_error_message(exc)}) from exc

    @router.post("/api/settings/retention-cleanup/preview")
    async def preview_retention_cleanup(body: RetentionCleanupRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return await run_in_threadpool(_retention_cleanup_payload, body, dry_run=True)

    @router.post("/api/settings/retention-cleanup/run")
    async def run_retention_cleanup(body: RetentionCleanupRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return await run_in_threadpool(_retention_cleanup_payload, body, dry_run=False)

    @router.post("/api/settings/account-cleanup/preview")
    async def preview_account_cleanup(body: AccountCleanupRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return await run_in_threadpool(_account_cleanup_payload, body, dry_run=True)

    @router.post("/api/settings/account-cleanup/run")
    async def run_account_cleanup(body: AccountCleanupRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return await run_in_threadpool(_account_cleanup_payload, body, dry_run=False)

    @router.get("/api/model-catalog", response_model=ModelCatalogView)
    async def model_catalog(authorization: str | None = Header(default=None)):
        require_identity(authorization)
        return await run_in_threadpool(get_model_catalog)

    @router.get("/api/images", response_model=GalleryPage)
    async def get_images(
        request: Request,
        start_date: str = "",
        end_date: str = "",
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=24, ge=1, le=500),
        media_type: GalleryMediaFilter = Query(default="all"),
        tag: str = Query(default=""),
        search: str = Query(default=""),
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        return await run_in_threadpool(
            list_images,
            resolve_image_base_url(request),
            start_date=start_date.strip(),
            end_date=end_date.strip(),
            limit=page_size,
            offset=(page - 1) * page_size,
            media_type=media_type,
            tag=tag.strip(),
            search=search.strip(),
        )

    @router.post("/api/images/retention-cleanup", response_model=GalleryCleanupResult)
    async def cleanup_expired_images_endpoint(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        result = await run_in_threadpool(cleanup_expired_images)
        return gallery_cleanup_result(result)

    @router.get("/images/{image_path:path}", include_in_schema=False)
    async def get_image(image_path: str):
        return get_image_response(image_path)

    @router.get("/image-thumbnails/{image_path:path}", include_in_schema=False)
    async def get_image_thumbnail(image_path: str):
        return get_thumbnail_response(image_path)

    @router.post("/api/images/delete")
    async def delete_images_endpoint(body: ImageDeleteRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return delete_images(body.paths, start_date=body.start_date.strip(), end_date=body.end_date.strip(), all_matching=body.all_matching)

    @router.post("/api/images/download")
    async def download_images_endpoint(body: ImageDownloadRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        buf = download_images_zip(body.paths)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="images.zip"'},
        )

    @router.get("/api/images/download/{image_path:path}")
    async def download_single_image_endpoint(image_path: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return get_image_download_response(image_path)

    @router.post("/api/images/genbox-push", response_model=GalleryGenBoxPushResult)
    async def push_image_to_genbox(
        body: GalleryGenBoxPushRequest,
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        return await run_in_threadpool(push_gallery_image, body.path)

    @router.get("/api/logs", response_model=CallSummaryPage)
    async def get_logs(
        type: str = "",
        start_date: str = "",
        end_date: str = "",
        status: CallLogStatus = "",
        endpoint: str = "",
        model: str = "",
        account: str = "",
        conversation_id: str = "",
        search: str = "",
        limit: int = Query(default=200, ge=1, le=20000),
        offset: int = Query(default=0, ge=0),
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        return await run_in_threadpool(
            log_service.list_page,
            type=type.strip(),
            start_date=start_date.strip(),
            end_date=end_date.strip(),
            status=status.strip(),
            endpoint=endpoint.strip(),
            model=model.strip(),
            account=account.strip(),
            conversation_id=conversation_id.strip(),
            search=search.strip(),
            limit=limit,
            offset=offset,
        )

    @router.get("/api/logs/{log_id}", response_model=CallDetail)
    async def get_log_detail(log_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        detail = await run_in_threadpool(log_service.get_detail, log_id)
        if detail is None:
            raise HTTPException(status_code=404, detail={"error": "log not found"})
        return detail

    @router.post("/api/logs/delete")
    async def delete_logs(body: LogDeleteRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return await run_in_threadpool(log_service.delete, body.ids)

    @router.get(
        "/api/monitor/realtime",
        response_model=RealtimeMonitorView,
        response_model_exclude_none=True,
    )
    async def get_realtime_monitor(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return build_monitor_view(realtime_monitor_service.snapshot())

    @router.get(
        "/api/monitor/realtime/{call_id}",
        response_model=MonitorRecordDetailView,
        response_model_exclude_none=True,
    )
    async def get_realtime_monitor_call(
        call_id: str,
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        record = realtime_monitor_service.call_detail(call_id)
        if record is None:
            raise HTTPException(status_code=404, detail={"error": "monitor call not found"})
        return build_monitor_record_view(record)

    @router.post("/api/proxy/test")
    async def test_proxy_endpoint(body: ProxyTestRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        explicit_url = (body.url or "").strip()
        if explicit_url:
            try:
                candidate = normalize_proxy_node_url(explicit_url)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        else:
            candidate = proxy_settings.get_profile(upstream=True).proxy_url
        if not candidate:
            raise HTTPException(status_code=400, detail={"error": "proxy url is required"})
        return {"result": await run_in_threadpool(test_proxy, candidate)}

    @router.get("/api/proxy/view", response_model=ProxyView)
    async def get_proxy_view(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return await run_in_threadpool(proxy_management_service.view)

    @router.post("/api/proxy/defaults", response_model=ProxyDefaultsMutation)
    async def save_proxy_defaults(
        body: ProxyDefaultsRequest,
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        try:
            return await run_in_threadpool(
                proxy_management_service.save_defaults,
                body.default_reference,
                body.fallback_reference,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail={"error": _settings_write_error_message(exc)}) from exc

    @router.post("/api/proxy/groups", response_model=ProxyGroupMutation)
    async def save_proxy_group(body: ProxyGroupPatch, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            return await run_in_threadpool(proxy_management_service.save_group, body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail={"error": _settings_write_error_message(exc)}) from exc

    @router.post("/api/proxy/nodes/import", response_model=ProxyNodeImportResult)
    async def import_proxy_nodes(
        body: ProxyNodeImportRequest,
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        try:
            return await run_in_threadpool(
                proxy_management_service.import_nodes,
                body.text,
                body.existing_urls,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    @router.delete("/api/proxy/groups/{group_id}", response_model=ProxyGroupDeleteMutation)
    async def delete_proxy_group(group_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            return await run_in_threadpool(proxy_management_service.delete_group, group_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"error": str(exc.args[0])}) from exc
        except ProxyGroupInUseError as exc:
            raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail={"error": _settings_write_error_message(exc)}) from exc

    @router.post("/api/proxy/groups/test", response_model=ProxyGroupTestResponse)
    async def test_proxy_group_endpoint(body: ProxyGroupTestRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        explicit_url = (body.url or "").strip()
        if explicit_url:
            try:
                candidate = normalize_proxy_node_url(explicit_url)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
            result = await run_in_threadpool(test_proxy, candidate)
            return proxy_management_service.group_test_response([("", result)])

        group_id = _proxy_group_id(body.id)
        if not group_id:
            raise HTTPException(status_code=400, detail={"error": "proxy group id or url is required"})
        group_list = await run_in_threadpool(proxy_management_service.list_groups)
        group = next((item for item in group_list.groups if item.id == group_id), None)
        if group is None:
            raise HTTPException(status_code=404, detail={"error": "proxy group not found"})
        node_id = _clean_text(body.node_id)
        nodes = [
            node for node in group.nodes
            if node.enabled
            and node.url
            and (not node_id or node.id == node_id)
        ]
        if not nodes:
            raise HTTPException(status_code=400, detail={"error": "proxy group node url is required"})
        results = [
            (node.id, await run_in_threadpool(test_proxy, node.url))
            for node in nodes
        ]
        return proxy_management_service.group_test_response(results)

    @router.get("/api/proxy/runtime")
    async def get_proxy_runtime_endpoint(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return {
            "runtime": config.get_public_proxy_runtime_settings(),
            "status": proxy_settings.get_runtime_status(),
        }

    @router.post("/api/proxy/clearance/test")
    async def test_proxy_clearance_endpoint(body: ClearanceTestRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return {"result": await run_in_threadpool(test_clearance, body.target_url)}

    @router.get("/api/dashboard", response_model=DashboardResponseView)
    async def get_dashboard(
        authorization: str | None = Header(default=None),
        time_range: str = Query(default="24h", pattern="^(24h|7d|30d)$"),
    ):
        require_admin(authorization)
        return await run_in_threadpool(
            build_dashboard_view,
            app_version=app_version,
            selected_range=time_range,
        )

    @router.post("/api/backup/test")
    async def test_backup_connection(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            return {"result": await run_in_threadpool(backup_service.test_connection)}
        except BackupError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    @router.post("/api/image-storage/test")
    async def test_image_storage_endpoint(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return {"result": await run_in_threadpool(image_storage_service.test_webdav)}

    @router.post("/api/image-storage/sync")
    async def sync_image_storage_endpoint(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            return {"result": await run_in_threadpool(image_storage_service.sync_all)}
        except ImageStorageError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    @router.get("/api/backups")
    async def get_backups(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            return {
                "items": await run_in_threadpool(backup_service.list_backups),
                "state": backup_service.get_status(),
            }
        except BackupError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    @router.post("/api/backups/run")
    async def run_backup_endpoint(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            return {"result": await run_in_threadpool(backup_service.run_backup)}
        except BackupError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    @router.post("/api/backups/delete")
    async def delete_backup_endpoint(body: BackupDeleteRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            await run_in_threadpool(backup_service.delete_backup, body.key)
            return {"ok": True}
        except BackupError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    @router.post("/api/images/tags")
    async def update_image_tags(body: ImageTagsRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        rel = body.path.strip().lstrip("/")
        if not rel:
            raise HTTPException(status_code=400, detail={"error": "path is required"})
        tags = set_tags(rel, body.tags)
        return {"ok": True, "tags": tags}

    @router.get("/api/images/storage")
    async def get_image_storage(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return storage_stats()

    @router.post("/api/images/storage/compress", response_model=GalleryCompressResult)
    async def compress_all_images(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        result = await run_in_threadpool(compress_images)
        return gallery_compress_result(result)

    @router.post(
        "/api/images/storage/cleanup-to-target",
        response_model=GalleryCleanupTargetResult,
    )
    async def cleanup_to_target(
        target_free_mb: int = Query(default=500, ge=1),
        dry_run: bool = False,
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        result = await run_in_threadpool(
            retention_cleanup_coordinator.cleanup_images_to_target,
            target_free_mb,
            dry_run=dry_run,
        )
        return gallery_cleanup_target_result(
            result,
            target_free_mb=target_free_mb,
            dry_run=dry_run,
        )

    return router

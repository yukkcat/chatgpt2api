from __future__ import annotations

from services.account_service import account_service
from services.config import config
from services.dashboard_metrics_service import (
    DASHBOARD_METRICS_SCHEMA_VERSION,
    DASHBOARD_TIME_RANGES,
    dashboard_metrics_service,
)
from services.log_service import log_service
from utils.log import logger
from utils.timezone import beijing_now


DASHBOARD_VIEW_SCHEMA_VERSION = 1


def _image_storage_view() -> dict[str, object]:
    settings = config.get_image_storage_settings()
    return {
        "enabled": bool(settings.get("enabled")),
        "mode": str(settings.get("mode") or "local"),
        "status": "not_checked",
        "available": None,
        "image_count": None,
        "image_size_bytes": None,
    }


def build_dashboard_view(*, app_version: str, selected_range: str) -> dict:
    if selected_range not in DASHBOARD_TIME_RANGES:
        raise ValueError(f"Unsupported dashboard time range: {selected_range}")

    try:
        dashboard_metrics_service.sync_for_dashboard(log_service)
    except Exception as exc:
        logger.error({
            "event": "dashboard_metrics_request_sync_failed",
            "error": str(exc),
        })

    account_stats = account_service.get_stats()
    account_healthy = bool(account_stats.get("active")) or bool(
        account_stats.get("unlimited_quota_count")
    )
    snapshot = dashboard_metrics_service.snapshot_many()
    metrics = snapshot["metrics"]
    ranges = snapshot["ranges"]
    application_database = config.get_storage_backend().get_backend_info()
    image_storage = _image_storage_view()
    overall_healthy = account_healthy and bool(metrics.get("ready"))
    return {
        "status": "ok" if overall_healthy else "degraded",
        "healthy": overall_healthy,
        "version": app_version,
        "meta": {
            "schema_version": DASHBOARD_VIEW_SCHEMA_VERSION,
            "metrics_schema_version": DASHBOARD_METRICS_SCHEMA_VERSION,
            "generated_at": beijing_now().isoformat(timespec="seconds"),
            "selected_range": selected_range,
            "available_ranges": list(DASHBOARD_TIME_RANGES),
        },
        "metrics": metrics,
        "accounts": {
            **account_stats,
            "healthy": account_healthy,
        },
        "storage": {
            "application_database": application_database,
            "image_storage": image_storage,
        },
        "ranges": ranges,
        "logs": ranges[selected_range],
    }

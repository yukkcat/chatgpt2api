from __future__ import annotations

from contextlib import asynccontextmanager
from threading import Event

from anyio.to_thread import current_default_thread_limiter
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api import accounts, ai, image_tasks, prompts, system
from api.errors import install_exception_handlers
from api.support import resolve_web_asset, start_account_lifecycle_watcher
from services.account_service import account_service
from services.backup_service import backup_service
from services.config import config
from services.dashboard_metrics_service import dashboard_metrics_service
from services.image_task_service import image_task_service
from services.log_service import log_service
from services.realtime_monitor_service import realtime_monitor_service
from services.retention_cleanup_service import retention_cleanup_coordinator, start_retention_cleanup_scheduler
from services.runtime_configuration import DEFAULT_THREAD_TOKENS, env_int
from utils.log import logger


RETENTION_SHUTDOWN_TIMEOUT_SECS = 1.0


def _configure_threadpool() -> None:
    tokens = env_int("CHATGPT2API_THREAD_TOKENS", DEFAULT_THREAD_TOKENS)
    limiter = current_default_thread_limiter()
    previous = int(getattr(limiter, "total_tokens", 0) or 0)
    if previous != tokens:
        limiter.total_tokens = tokens
    realtime_monitor_service.set_threadpool(tokens=tokens, previous_tokens=previous)
    logger.info({
        "event": "runtime_threadpool_configured",
        "previous_tokens": previous,
        "tokens": tokens,
    })


def create_app() -> FastAPI:
    app_version = config.app_version

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        _configure_threadpool()
        image_task_service.start()
        try:
            cleanup_result = await run_in_threadpool(
                retention_cleanup_coordinator.run_startup_automatic,
                enforce_image_free_space=False,
            )
            cleanup_errors = cleanup_result.get("errors") or {}
            if cleanup_errors.get("logs"):
                logger.error({"event": "log_startup_cleanup_failed", "error": cleanup_errors["logs"]})
            if cleanup_errors.get("images"):
                logger.error({"event": "image_startup_cleanup_failed", "error": cleanup_errors["images"]})
        except Exception as exc:
            logger.error({"event": "retention_startup_cleanup_failed", "error": str(exc)})
        try:
            await run_in_threadpool(
                dashboard_metrics_service.sync_from_log_service,
                log_service,
            )
        except Exception as exc:
            logger.error({"event": "dashboard_metrics_startup_sync_failed", "error": str(exc)})
            try:
                await run_in_threadpool(dashboard_metrics_service.mark_ingest_failed)
            except Exception as marker_exc:
                logger.error({"event": "dashboard_metrics_startup_marker_failed", "error": str(marker_exc)})
        account_service.cleanup_auto_remove_accounts()
        stop_event = Event()
        thread = start_account_lifecycle_watcher(stop_event)
        cleanup_thread = start_retention_cleanup_scheduler(stop_event)
        backup_service.start()
        try:
            yield
        finally:
            stop_event.set()
            thread.join(timeout=1)
            await run_in_threadpool(cleanup_thread.join, RETENTION_SHUTDOWN_TIMEOUT_SECS)
            await run_in_threadpool(image_task_service.shutdown_cancel_pending_and_wait)
            try:
                await run_in_threadpool(
                    dashboard_metrics_service.sync_from_log_service,
                    log_service,
                )
            except Exception as exc:
                logger.error({"event": "dashboard_metrics_shutdown_sync_failed", "error": str(exc)})
            backup_service.stop()
    app = FastAPI(title="chatgpt2api", version=app_version, lifespan=lifespan)
    install_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Export-Requested", "X-Exported", "X-Skipped"],
    )
    app.include_router(ai.create_router())
    app.include_router(accounts.create_router())
    app.include_router(image_tasks.create_router())
    app.include_router(prompts.create_router())
    app.include_router(system.create_router(app_version))

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_web(full_path: str):
        asset = resolve_web_asset(full_path)
        if asset is None:
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(asset)

    return app

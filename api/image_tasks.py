from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from api.image_inputs import parse_image_edit_request, read_image_sources
from api.image_task_contract import ImageTaskPage, ImageTaskRow
from api.support import require_identity, resolve_image_base_url
from services.content_filter import check_request
from services.image_task_service import ImageTaskQueueFullError, image_task_service
from services.log_service import LoggedCall


class ImageGenerationTaskRequest(BaseModel):
    client_task_id: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)
    model: str = "gpt-image-2"
    n: int = Field(default=1, ge=1, le=4)
    size: str | None = None
    quality: str = "auto"


class ResumePollRequest(BaseModel):
    extra_timeout_secs: float = Field(default=30.0, ge=5.0, le=120.0)


def _parse_task_ids(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _queue_full_http_error(exc: ImageTaskQueueFullError) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"code": exc.code, "error": str(exc)},
    )


async def filter_or_log(call: LoggedCall, text: str) -> None:
    try:
        await run_in_threadpool(check_request, text)
    except HTTPException as exc:
        call.log("调用失败", status="failed", error=str(exc.detail))
        raise


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/image-tasks", response_model=ImageTaskPage)
    async def list_image_tasks(
        ids: str = Query(default=""),
        authorization: str | None = Header(default=None),
    ):
        identity = require_identity(authorization)
        return await run_in_threadpool(image_task_service.list_tasks, identity, _parse_task_ids(ids))

    @router.post("/api/image-tasks/generations", response_model=ImageTaskRow)
    async def create_generation_task(
        body: ImageGenerationTaskRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        identity = require_identity(authorization)
        await filter_or_log(LoggedCall(identity, "/api/image-tasks/generations", body.model, "文生图任务", request_text=body.prompt), body.prompt)
        try:
            return await run_in_threadpool(
                image_task_service.submit_generation,
                identity,
                client_task_id=body.client_task_id,
                prompt=body.prompt,
                model=body.model,
                n=body.n,
                size=body.size,
                quality=body.quality,
                base_url=resolve_image_base_url(request),
            )
        except ImageTaskQueueFullError as exc:
            raise _queue_full_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    @router.post("/api/image-tasks/edits", response_model=ImageTaskRow)
    async def create_edit_task(
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        identity = require_identity(authorization)
        payload, image_sources, mask_sources = await parse_image_edit_request(request)
        client_task_id = str(payload.get("client_task_id") or "").strip()
        if not client_task_id:
            raise HTTPException(status_code=400, detail={"error": "client_task_id is required"})
        prompt = str(payload["prompt"])
        model = str(payload["model"])
        await filter_or_log(LoggedCall(identity, "/api/image-tasks/edits", model, "图生图任务", request_text=prompt), prompt)
        reservation = None
        try:
            reservation = await run_in_threadpool(image_task_service.reserve_submission)
            images = await read_image_sources(image_sources)
            masks = await read_image_sources(mask_sources) if mask_sources else None
            return await run_in_threadpool(
                image_task_service.submit_edit,
                identity,
                client_task_id=client_task_id,
                prompt=prompt,
                model=model,
                n=payload.get("n", 1),
                size=payload["size"],
                quality=payload["quality"],
                base_url=resolve_image_base_url(request),
                images=images,
                masks=masks,
                reservation=reservation,
            )
        except ImageTaskQueueFullError as exc:
            raise _queue_full_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        finally:
            if reservation is not None:
                reservation.rollback()

    @router.post("/api/image-tasks/{task_id}/resume-poll", response_model=ImageTaskRow)
    async def resume_image_poll(
        task_id: str,
        body: ResumePollRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        identity = require_identity(authorization)
        try:
            return await run_in_threadpool(
                image_task_service.resume_poll,
                identity,
                task_id,
                body.extra_timeout_secs,
            )
        except ImageTaskQueueFullError as exc:
            raise _queue_full_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    return router

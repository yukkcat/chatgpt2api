from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.concurrency import run_in_threadpool

from api.support import require_admin, require_identity
from contracts.prompts import PromptLibraryView, PromptSourceRequest
from services.prompt_library_service import prompt_library_service


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/prompts", response_model=PromptLibraryView)
    async def list_prompts(authorization: str | None = Header(default=None)) -> PromptLibraryView:
        require_identity(authorization)
        return await run_in_threadpool(prompt_library_service.view)

    @router.post("/api/admin/prompt-sources/refresh", response_model=PromptLibraryView)
    async def admin_refresh_prompt_sources(
        authorization: str | None = Header(default=None),
    ) -> PromptLibraryView:
        require_admin(authorization)
        result = await run_in_threadpool(prompt_library_service.refresh)
        assert result is not None
        return result

    @router.post("/api/admin/prompt-sources/{source_id}/refresh", response_model=PromptLibraryView)
    async def admin_refresh_prompt_source(
        source_id: str,
        authorization: str | None = Header(default=None),
    ) -> PromptLibraryView:
        require_admin(authorization)
        result = await run_in_threadpool(prompt_library_service.refresh, source_id)
        if result is None:
            raise HTTPException(status_code=404, detail={"error": "prompt source not found"})
        return result

    @router.post("/api/admin/prompt-sources/{source_id}", response_model=PromptLibraryView)
    async def admin_update_prompt_source(
        source_id: str,
        body: PromptSourceRequest,
        authorization: str | None = Header(default=None),
    ) -> PromptLibraryView:
        require_admin(authorization)
        try:
            result = await run_in_threadpool(
                prompt_library_service.update_source,
                source_id,
                body.model_dump(mode="python", exclude_unset=True),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        if result is None:
            raise HTTPException(status_code=404, detail={"error": "prompt source not found"})
        return result

    return router

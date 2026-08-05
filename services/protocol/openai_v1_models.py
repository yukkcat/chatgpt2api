from __future__ import annotations

from typing import Any, Iterable

from services.model_catalog_service import get_model_catalog
from services.openai_backend_api import OpenAIBackendAPI


def _model_item(model: str) -> dict[str, Any]:
    return {
        "id": model,
        "object": "model",
        "created": 0,
        "owned_by": "chatgpt2api",
        "permission": [],
        "root": model,
        "parent": None,
    }


def _append_models(data: list[Any], seen: set[str], models: Iterable[object]) -> None:
    for model in models:
        model_id = str(model or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        data.append(_model_item(model_id))


def _append_upstream_models(data: list[Any], seen: set[str]) -> None:
    """Keep the public compatibility endpoint's upstream model discovery."""
    try:
        with OpenAIBackendAPI() as backend:
            result = backend.list_models()
    except Exception:
        return
    upstream_data = result.get("data")
    if not isinstance(upstream_data, list):
        return
    _append_models(
        data,
        seen,
        (item.get("id") for item in upstream_data if isinstance(item, dict)),
    )


def list_models() -> dict[str, Any]:
    catalog = get_model_catalog()
    data: list[Any] = []
    seen: set[str] = set()
    _append_models(data, seen, catalog.chat_models)
    _append_upstream_models(data, seen)
    _append_models(data, seen, catalog.image_models)
    return {"object": "list", "data": data}

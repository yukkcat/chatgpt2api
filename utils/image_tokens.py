from __future__ import annotations

import base64
import math
import re
from io import BytesIO
from typing import Any

from PIL import Image

DEFAULT_IMAGE_SIZE = (1024, 1024)
IMAGE_INPUT_TOKEN_MODEL = "gpt-5.4-mini"

PATCH_SIZE = 32
TILE_SIZE = 512
TILE_HIGH_SHORT_SIDE = 768

PATCH_1536_MODELS = (
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5.2",
    "gpt-5.3-codex",
    "gpt-5-codex-mini",
    "gpt-5.1-codex-mini",
    "gpt-5.2-codex",
    "gpt-5.2-chat-latest",
    "o4-mini",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
)

PATCH_MULTIPLIERS = {
    "gpt-5.4-mini": 1.62,
    "gpt-5.4-nano": 2.46,
    "gpt-5-mini": 1.62,
    "gpt-5-nano": 2.46,
    "gpt-4.1-mini": 1.62,
    "gpt-4.1-nano": 2.46,
    "o4-mini": 1.72,
}


def _model_name(model: str) -> str:
    return str(model or "").strip().lower()


def image_size_from_bytes(data: bytes) -> tuple[int, int] | None:
    if not data:
        return None
    try:
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return int(width), int(height)


def _decode_data_url(value: str) -> bytes:
    text = str(value or "").strip()
    payload = text.split(",", 1)[1] if text.startswith("data:") and "," in text else text
    return base64.b64decode(payload)


def image_size_from_data_url(value: str) -> tuple[int, int] | None:
    try:
        return image_size_from_bytes(_decode_data_url(value))
    except Exception:
        return None


def parse_image_size(size: object, default: tuple[int, int] = DEFAULT_IMAGE_SIZE) -> tuple[int, int]:
    if isinstance(size, (tuple, list)) and len(size) >= 2:
        try:
            width = int(size[0])
            height = int(size[1])
            if width > 0 and height > 0:
                return width, height
        except (TypeError, ValueError):
            pass
    match = re.search(r"(\d{2,5})\D+(\d{2,5})", str(size or ""))
    if not match:
        return default
    width, height = int(match.group(1)), int(match.group(2))
    return (width, height) if width > 0 and height > 0 else default


def _patch_count(width: float, height: float) -> int:
    return math.ceil(width / PATCH_SIZE) * math.ceil(height / PATCH_SIZE)


def _patch_multiplier(model: str) -> float:
    name = _model_name(model)
    for prefix, multiplier in PATCH_MULTIPLIERS.items():
        if name.startswith(prefix):
            return multiplier
    return 1.0


def _patch_limits(model: str, detail: str) -> tuple[int, int] | None:
    name = _model_name(model)
    if any(name.startswith(prefix) for prefix in PATCH_1536_MODELS):
        return 1536, 2048
    if name.startswith("gpt-5.5"):
        return (10000, 6000) if detail in {"auto", "original"} else (2500, 2048)
    if name.startswith("gpt-5.4"):
        return (10000, 6000) if detail == "original" else (2500, 2048)
    return None


def _patch_tokens(width: int, height: int, model: str, detail: str) -> int:
    multiplier = _patch_multiplier(model)
    if detail == "low":
        return math.ceil(256 * multiplier)

    limits = _patch_limits(model, detail)
    if limits is None:
        return 0
    patch_budget, max_dimension = limits
    scale = min(1.0, max_dimension / max(width, height))
    resized_width = width * scale
    resized_height = height * scale

    if _patch_count(resized_width, resized_height) > patch_budget:
        shrink_factor = math.sqrt((PATCH_SIZE * PATCH_SIZE * patch_budget) / (resized_width * resized_height))
        width_units = resized_width * shrink_factor / PATCH_SIZE
        height_units = resized_height * shrink_factor / PATCH_SIZE
        adjusted_shrink_factor = shrink_factor * min(
            math.floor(width_units) / width_units if width_units else 1,
            math.floor(height_units) / height_units if height_units else 1,
        )
        resized_width *= adjusted_shrink_factor
        resized_height *= adjusted_shrink_factor

    tokens = min(_patch_count(max(1, resized_width), max(1, resized_height)), patch_budget)
    return math.ceil(tokens * multiplier)


def _tile_rates(model: str) -> tuple[int, int]:
    name = _model_name(model)
    if name in {"gpt-5", "gpt-5-chat-latest"}:
        return 70, 140
    if name.startswith("gpt-4o-mini"):
        return 2833, 5667
    if name.startswith(("o1", "o1-pro", "o3")):
        return 75, 150
    if name.startswith("computer-use-preview"):
        return 65, 129
    return 85, 170


def _tile_tokens(width: int, height: int, model: str, detail: str) -> int:
    base_tokens, tile_tokens = _tile_rates(model)
    if detail == "low":
        return base_tokens

    scale = min(1.0, 2048 / max(width, height))
    resized_width = width * scale
    resized_height = height * scale
    short_side = min(resized_width, resized_height)
    if short_side > 0:
        scale = TILE_HIGH_SHORT_SIDE / short_side
        resized_width *= scale
        resized_height *= scale

    tiles = math.ceil(resized_width / TILE_SIZE) * math.ceil(resized_height / TILE_SIZE)
    return base_tokens + tiles * tile_tokens


def count_image_input_tokens(
    width: int,
    height: int,
    model: str,
    detail: str = "auto",
    input_fidelity: str = "low",
) -> int:
    if width <= 0 or height <= 0:
        return 0
    detail = str(detail or "auto").strip().lower() or "auto"
    return _patch_tokens(width, height, IMAGE_INPUT_TOKEN_MODEL, detail)


def _part_size(part: dict[str, Any]) -> tuple[int, int] | None:
    try:
        width = int(part.get("width") or 0)
        height = int(part.get("height") or 0)
    except (TypeError, ValueError):
        width = height = 0
    if width > 0 and height > 0:
        return width, height

    data = part.get("data")
    if isinstance(data, (bytes, bytearray)):
        return image_size_from_bytes(bytes(data))

    image_url = part.get("image_url")
    if isinstance(image_url, dict):
        image_url = image_url.get("url") or image_url.get("image_url")
    if isinstance(image_url, str) and image_url.startswith("data:"):
        return image_size_from_data_url(image_url)

    source = part.get("source")
    if isinstance(source, dict) and str(source.get("type") or "") == "base64":
        try:
            return image_size_from_bytes(base64.b64decode(str(source.get("data") or "")))
        except Exception:
            return None
    return None


def count_image_content_tokens(content: object, model: str, default_detail: str = "auto") -> int:
    if not isinstance(content, list):
        return 0
    total = 0
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = str(part.get("type") or "").strip()
        if part_type not in {"image", "image_url", "input_image"} and not part.get("source"):
            continue
        size = _part_size(part)
        if not size:
            continue
        total += count_image_input_tokens(
            size[0],
            size[1],
            model,
            str(part.get("detail") or default_detail or "auto"),
            str(part.get("input_fidelity") or part.get("inputFidelity") or "low"),
        )
    return total


def count_image_inputs_tokens(images: object, model: str, default_detail: str = "auto") -> int:
    if not images:
        return 0
    total = 0
    entries = images if isinstance(images, list) else [images]
    for image in entries:
        data = image[0] if isinstance(image, tuple) and image else image
        if not isinstance(data, (bytes, bytearray)):
            continue
        size = image_size_from_bytes(bytes(data))
        if size:
            total += count_image_input_tokens(size[0], size[1], model, default_detail)
    return total


def count_generated_image_tokens(width: int, height: int, quality: str = "auto") -> int:
    patches = _patch_count(width, height)
    quality = str(quality or "auto").strip().lower()
    if quality == "low":
        return math.ceil(patches * 17 / 64)
    if quality in {"high", "hd"}:
        return math.ceil(patches * 65 / 16)
    return math.ceil(patches * 33 / 32)


def count_image_output_tokens(size: object = None, quality: str = "auto", count: int = 1) -> int:
    width, height = parse_image_size(size)
    return max(0, int(count or 0)) * count_generated_image_tokens(width, height, quality)


def count_image_output_items_tokens(
    items: object,
    size: object = None,
    quality: str = "auto",
) -> int:
    if not isinstance(items, list) or not items:
        return 0
    fallback_size = parse_image_size(size)
    total = 0
    for item in items:
        image_size = None
        if isinstance(item, dict):
            b64_json = str(item.get("b64_json") or "").strip()
            if b64_json:
                try:
                    image_size = image_size_from_bytes(base64.b64decode(b64_json))
                except Exception:
                    image_size = None
        width, height = image_size or fallback_size
        total += count_generated_image_tokens(width, height, quality)
    return total


def token_usage(
    input_text_tokens: int = 0,
    input_image_tokens: int = 0,
    output_text_tokens: int = 0,
    output_image_tokens: int = 0,
) -> dict[str, Any]:
    input_tokens = max(0, int(input_text_tokens or 0)) + max(0, int(input_image_tokens or 0))
    output_tokens = max(0, int(output_text_tokens or 0)) + max(0, int(output_image_tokens or 0))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "input_tokens_details": {
            "text_tokens": max(0, int(input_text_tokens or 0)),
            "image_tokens": max(0, int(input_image_tokens or 0)),
            "cached_tokens": 0,
        },
        "output_tokens_details": {
            "text_tokens": max(0, int(output_text_tokens or 0)),
            "image_tokens": max(0, int(output_image_tokens or 0)),
            "reasoning_tokens": 0,
        },
    }


def image_usage(
    input_text_tokens: int = 0,
    input_image_tokens: int = 0,
    output_tokens: int = 0,
) -> dict[str, Any]:
    return token_usage(
        input_text_tokens=input_text_tokens,
        input_image_tokens=input_image_tokens,
        output_image_tokens=output_tokens,
    )


def chat_usage_from_image_usage(usage: dict[str, Any]) -> dict[str, Any]:
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    input_details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    output_details = usage.get("output_tokens_details") if isinstance(usage.get("output_tokens_details"), dict) else {}
    return {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "prompt_tokens_details": {
            "text_tokens": int(input_details.get("text_tokens") or 0),
            "image_tokens": int(input_details.get("image_tokens") or 0),
            "cached_tokens": int(input_details.get("cached_tokens") or 0),
        },
        "completion_tokens_details": {
            "text_tokens": int(output_details.get("text_tokens") or 0),
            "image_tokens": int(output_details.get("image_tokens") or 0),
            "reasoning_tokens": int(output_details.get("reasoning_tokens") or 0),
        },
    }

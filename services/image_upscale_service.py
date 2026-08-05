from __future__ import annotations

import io
import re
import shutil
import subprocess
import threading
from pathlib import Path

from PIL import Image, ImageOps

from services.config import config
from utils.diagnostics import diagnostic_excerpt
from utils.image_tokens import image_size_from_bytes
from utils.log import logger


_SHARP_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "image_upscale" / "upscale.mjs"
_UPSCALE_LOCK = threading.Lock()
_MAX_TARGET_DIMENSION = 8192


def _target_size(value: object) -> tuple[int, int] | None:
    text = str(value or "").strip().lower()
    if not text or text == "auto":
        return None
    match = re.fullmatch(r"(\d{2,5})\s*x\s*(\d{2,5})", text)
    if not match:
        return None
    width, height = int(match.group(1)), int(match.group(2))
    if width > _MAX_TARGET_DIMENSION or height > _MAX_TARGET_DIMENSION:
        return None
    return width, height


def _pillow_lanczos(image_data: bytes, target: tuple[int, int]) -> bytes:
    with Image.open(io.BytesIO(image_data)) as source:
        image_format = str(source.format or "PNG").upper()
        image = ImageOps.exif_transpose(source)
        resized = image.resize(target, Image.Resampling.LANCZOS, reducing_gap=3.0)
        output = io.BytesIO()
        save_options: dict[str, object] = {}
        if image_format in {"JPG", "JPEG"}:
            image_format = "JPEG"
            if resized.mode not in {"RGB", "L"}:
                resized = resized.convert("RGB")
            save_options.update(quality=95, subsampling=0)
        elif image_format == "WEBP":
            save_options.update(quality=95, method=4)
        elif image_format not in {"PNG", "WEBP"}:
            image_format = "PNG"
        resized.save(output, format=image_format, **save_options)
        return output.getvalue()


def _sharp_lanczos3(image_data: bytes, target: tuple[int, int]) -> bytes:
    node = shutil.which("node")
    if not node or not _SHARP_SCRIPT.is_file():
        raise RuntimeError("Sharp runtime is unavailable")
    completed = subprocess.run(
        [node, str(_SHARP_SCRIPT), str(target[0]), str(target[1])],
        input=image_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=180,
    )
    if completed.returncode != 0 or not completed.stdout:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"Sharp exited with code {completed.returncode}")
    return completed.stdout


def upscale_image_if_needed(image_data: bytes, requested_size: object) -> bytes:
    if not image_data or not config.image_upscale_enabled:
        return image_data
    target = _target_size(requested_size)
    source = image_size_from_bytes(image_data)
    if not target or not source:
        return image_data
    if source[0] >= target[0] and source[1] >= target[1]:
        return image_data

    engine = config.image_upscale_engine
    with _UPSCALE_LOCK:
        try:
            if engine == "sharp_lanczos3":
                try:
                    result = _sharp_lanczos3(image_data, target)
                except Exception as exc:
                    logger.warning({
                        "event": "image_upscale_sharp_fallback",
                        "source_size": list(source),
                        "target_size": list(target),
                        "error": diagnostic_excerpt(exc, 500),
                    })
                    result = _pillow_lanczos(image_data, target)
                    engine = "pillow_lanczos"
            else:
                result = _pillow_lanczos(image_data, target)
            logger.info({
                "event": "image_upscale_done",
                "engine": engine,
                "source_size": list(source),
                "target_size": list(target),
                "source_bytes": len(image_data),
                "result_bytes": len(result),
            })
            return result
        except Exception as exc:
            logger.warning({
                "event": "image_upscale_failed",
                "engine": engine,
                "source_size": list(source),
                "target_size": list(target),
                "error": diagnostic_excerpt(exc, 500),
            })
            return image_data

from __future__ import annotations

import base64
import binascii
import ipaddress
import mimetypes
import re
import socket
import threading
from pathlib import PurePosixPath
from urllib.parse import ParseResult, unquote, unquote_to_bytes, urljoin, urlparse

from curl_cffi import CurlOpt, requests
from fastapi import HTTPException

ImageInput = tuple[bytes, str, str]
MAX_IMAGE_REFERENCE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_REDIRECTS = 3
_IMAGE_FETCH_SLOTS = threading.BoundedSemaphore(8)


def _clean(value: object, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    return text or default


def _extension_from_mime(mime_type: str) -> str:
    """推导图片扩展名：把 MIME 类型转换为常见文件后缀。"""
    subtype = mime_type.split("/", 1)[1].split("+", 1)[0] if "/" in mime_type else "png"
    if subtype == "jpeg":
        return "jpg"
    return re.sub(r"[^a-z0-9]+", "", subtype.lower()) or "png"


def _safe_filename(name: str, mime_type: str, fallback: str) -> str:
    """生成安全文件名：清理 URL 文件名并补齐扩展名。"""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not cleaned:
        cleaned = fallback
    if "." not in cleaned:
        cleaned = f"{cleaned}.{_extension_from_mime(mime_type)}"
    return cleaned


def _image_size_limit_error(max_bytes: int) -> HTTPException:
    limit_mb = max(1, max_bytes // (1024 * 1024))
    return HTTPException(status_code=400, detail={"error": f"image URL exceeds {limit_mb}MB limit"})


def _decode_data_url(url: str, max_bytes: int = MAX_IMAGE_REFERENCE_BYTES) -> ImageInput:
    """解码 data URL：把内联图片转成标准图片输入元组。"""
    header, separator, payload = url.partition(",")
    if not separator:
        raise HTTPException(status_code=400, detail={"error": "invalid data image URL"})
    mime_type = header.split(";", 1)[0].removeprefix("data:") or "image/png"
    if not mime_type.startswith("image/"):
        raise HTTPException(status_code=400, detail={"error": "image_url must point to an image"})
    if ";base64" in header:
        encoded_limit = ((max_bytes + 2) // 3) * 4
        padding = len(payload) - len(payload.rstrip("="))
        decoded_size = (len(payload) // 4) * 3 - min(padding, 2)
        if len(payload) > encoded_limit or decoded_size > max_bytes:
            raise _image_size_limit_error(max_bytes)
    elif len(payload) > max_bytes * 3:
        raise _image_size_limit_error(max_bytes)
    try:
        data = base64.b64decode(payload, validate=True) if ";base64" in header else unquote_to_bytes(payload)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid data image URL"}) from exc
    if not data:
        raise HTTPException(status_code=400, detail={"error": "image URL is empty"})
    if len(data) > max_bytes:
        raise _image_size_limit_error(max_bytes)
    return data, f"image_url.{_extension_from_mime(mime_type)}", mime_type


def _response_mime_type(response: requests.Response, parsed_path: str) -> str:
    """识别下载图片类型：优先响应头，必要时按 URL 后缀推断。"""
    header_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    guessed_type = mimetypes.guess_type(parsed_path)[0] or ""
    if header_type.startswith("image/"):
        return header_type
    if header_type and header_type not in {"application/octet-stream", "binary/octet-stream"}:
        raise HTTPException(status_code=400, detail={"error": "image_url must point to an image"})
    if guessed_type.startswith("image/"):
        return guessed_type
    if not header_type or header_type in {"application/octet-stream", "binary/octet-stream"}:
        return "image/png"
    raise HTTPException(status_code=400, detail={"error": "image_url must point to an image"})


def _filename_from_url(parsed_path: str, mime_type: str) -> str:
    """生成 URL 图片文件名：从链接路径提取名称并做安全化。"""
    raw_name = PurePosixPath(unquote(parsed_path)).name
    return _safe_filename(raw_name, mime_type, "image_url")


def _validate_public_image_url(source: str) -> tuple[ParseResult, tuple[str, ...]]:
    """Validate a remote image URL before every network hop.

    Public image URLs are the supported contract. Resolving the hostname here
    blocks loopback, private, link-local, multicast, and other non-routable
    destinations that would otherwise make this endpoint an SSRF primitive.
    Redirects are validated independently by the caller.
    """
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail={"error": "image_url must be an http or https URL"})
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail={"error": "image_url must not include credentials"})
    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid image_url host"}) from exc
    if not hostname:
        raise HTTPException(status_code=400, detail={"error": "invalid image_url host"})
    normalized_host = hostname.rstrip(".").lower()
    if normalized_host in {"localhost", "localhost.localdomain"} or normalized_host.endswith(".local"):
        raise HTTPException(status_code=400, detail={"error": "image_url host is not publicly reachable"})
    try:
        literal = ipaddress.ip_address(normalized_host)
    except ValueError:
        literal = None
    addresses: list[str]
    if literal is not None:
        addresses = [str(literal)]
    else:
        try:
            addresses = [item[4][0] for item in socket.getaddrinfo(normalized_host, port, type=socket.SOCK_STREAM)]
        except OSError as exc:
            raise HTTPException(status_code=400, detail={"error": "image_url host could not be resolved"}) from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise HTTPException(status_code=400, detail={"error": "image_url host is not publicly reachable"})
    return parsed, tuple(dict.fromkeys(addresses))


def _image_fetch_curl_options(parsed: ParseResult, addresses: tuple[str, ...]) -> dict[CurlOpt, object]:
    """Pin the connection to the public addresses validated for this hop."""
    hostname = parsed.hostname or ""
    try:
        ipaddress.ip_address(hostname.rstrip("."))
    except ValueError:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        resolved = [
            f"{hostname}:{port}:{f'[{address}]' if ':' in address else address}"
            for address in addresses
        ]
    else:
        resolved = []
    options: dict[CurlOpt, object] = {CurlOpt.NOPROXY: "*"}
    if resolved:
        options[CurlOpt.RESOLVE] = resolved
    return options


def _read_response_limited(response: requests.Response, max_bytes: int = MAX_IMAGE_REFERENCE_BYTES) -> bytes:
    """Read a response without allowing an unbounded body allocation."""
    data = bytearray()
    total = 0
    iterator = getattr(response, "iter_content", None)
    try:
        if callable(iterator):
            for chunk in iterator(chunk_size=64 * 1024):
                if not chunk:
                    continue
                chunk_bytes = bytes(chunk)
                total += len(chunk_bytes)
                if total > max_bytes:
                    raise _image_size_limit_error(max_bytes)
                data.extend(chunk_bytes)
            if not data:
                raise HTTPException(status_code=400, detail={"error": "image_url returned empty content"})
        else:
            raise HTTPException(status_code=400, detail={"error": "image_url response cannot be streamed safely"})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error": f"image_url fetch failed: {exc}"}) from exc
    return bytes(data)


def _download_image_url(
    url: str,
    *,
    max_bytes: int = MAX_IMAGE_REFERENCE_BYTES,
    timeout_seconds: int = 60,
) -> ImageInput:
    """下载远程图片：把 http/https 图片链接转成标准图片输入元组。"""
    source = _clean(url)
    if source.startswith("data:"):
        return _decode_data_url(source, max_bytes=max_bytes)
    current = source
    for redirect_count in range(MAX_IMAGE_REDIRECTS + 1):
        parsed, addresses = _validate_public_image_url(current)
        acquired = False
        try:
            acquired = _IMAGE_FETCH_SLOTS.acquire(timeout=60)
            if not acquired:
                raise TimeoutError("image fetch concurrency limit reached")
            response = requests.get(
                current,
                headers={"Accept": "image/*,*/*;q=0.8", "User-Agent": "chatgpt2api image fetcher"},
                timeout=timeout_seconds,
                allow_redirects=False,
                stream=True,
                curl_options=_image_fetch_curl_options(parsed, addresses),
            )
        except HTTPException:
            if acquired:
                _IMAGE_FETCH_SLOTS.release()
            raise
        except Exception as exc:
            if acquired:
                _IMAGE_FETCH_SLOTS.release()
            raise HTTPException(status_code=400, detail={"error": f"image_url fetch failed: {exc}"}) from exc
        try:
            if 300 <= response.status_code < 400:
                if redirect_count >= MAX_IMAGE_REDIRECTS:
                    raise HTTPException(status_code=400, detail={"error": "image_url has too many redirects"})
                location = _clean(response.headers.get("location"))
                if not location:
                    raise HTTPException(status_code=400, detail={"error": "image_url redirect is missing a location"})
                current = urljoin(current, location)
                continue
            if not 200 <= response.status_code < 300:
                raise HTTPException(status_code=400, detail={"error": f"image_url fetch failed: HTTP {response.status_code}"})
            content_length = _clean(response.headers.get("content-length"))
            if content_length and content_length.isdigit() and int(content_length) > max_bytes:
                raise _image_size_limit_error(max_bytes)
            data = _read_response_limited(response, max_bytes=max_bytes)
            if not data:
                raise HTTPException(status_code=400, detail={"error": "image_url returned empty content"})
            mime_type = _response_mime_type(response, parsed.path)
            return data, _filename_from_url(parsed.path, mime_type), mime_type
        finally:
            try:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
            finally:
                _IMAGE_FETCH_SLOTS.release()
    raise HTTPException(status_code=400, detail={"error": "image_url has too many redirects"})

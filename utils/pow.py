import json
import random
import re
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any, Sequence

import pybase64

DEFAULT_POW_SCRIPT = "https://chatgpt.com/backend-api/sentinel/sdk.js"
from utils.helper import new_uuid


CORES = [8, 16, 24, 32]
DOCUMENT_KEYS = ["__reactContainer$fzelfjyxej8", "_reactListening5dehydibo78", "location"]
SCREEN_RESOLUTIONS = [[1920, 1080], [1440, 900], [2560, 1440], [3840, 2160]]


class ScriptSrcParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.script_sources: list[str] = []
        self.data_build = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return
        attrs_dict = dict(attrs)
        src = attrs_dict.get("src")
        if not src:
            return
        self.script_sources.append(src)
        match = re.search(r"c/[^/]*/_", src)
        if match:
            self.data_build = match.group(0)


def parse_pow_resources(html_content: str) -> tuple[list[str], str]:
    parser = ScriptSrcParser()
    parser.feed(html_content)
    script_sources = parser.script_sources or [DEFAULT_POW_SCRIPT]
    data_build = parser.data_build
    if not data_build:
        match = re.search(r'<html[^>]*data-build="([^"]*)"', html_content)
        if match:
            data_build = match.group(1)
    return script_sources, data_build


def _legacy_parse_time(tz_name: str = "") -> str:
    try:
        from utils.ip_timezone import get_pow_formatted_time
        return get_pow_formatted_time(tz_name)
    except Exception:
        now = datetime.now(timezone(timedelta(hours=-5)))
        return now.strftime("%a %b %d %Y %H:%M:%S") + " GMT-0500 (Eastern Standard Time)"


def build_pow_config(
    user_agent: str,
    script_sources: Sequence[str] | None = None,
    data_build: str = "",
    tz_name: str = "",
) -> list[Any]:
    navigator_key = random.choice([
        "registerProtocolHandler−function registerProtocolHandler() { [native code] }",
        "storage−[object StorageManager]",
        "locks−[object LockManager]",
        "appCodeName−Mozilla",
        "permissions−[object Permissions]",
        "share−function share() { [native code] }",
        "webdriver−false",
        "managed−[object NavigatorManagedData]",
        "canShare−function canShare() { [native code] }",
        "vendor−Google Inc.",
        "mediaDevices−[object MediaDevices]",
        "vibrate−function vibrate() { [native code] }",
        "storageBuckets−[object StorageBucketManager]",
        "mediaCapabilities−[object MediaCapabilities]",
        "cookieEnabled−true",
        "virtualKeyboard−[object VirtualKeyboard]",
        "product−Gecko",
        "presentation−[object Presentation]",
        "onLine−true",
        "mimeTypes−[object MimeTypeArray]",
        "credentials−[object CredentialsContainer]",
        "serviceWorker−[object ServiceWorkerContainer]",
        "keyboard−[object Keyboard]",
        "gpu−[object GPU]",
        "doNotTrack",
        "serial−[object Serial]",
        "pdfViewerEnabled−true",
        "language−zh-CN",
        "geolocation−[object Geolocation]",
        "userAgentData−[object NavigatorUAData]",
        "getUserMedia−function getUserMedia() { [native code] }",
        "sendBeacon−function sendBeacon() { [native code] }",
        "hardwareConcurrency−32",
        "windowControlsOverlay−[object WindowControlsOverlay]",
    ])
    window_key = random.choice([
        "0",
        "window",
        "self",
        "document",
        "name",
        "location",
        "customElements",
        "history",
        "navigation",
        "innerWidth",
        "innerHeight",
        "scrollX",
        "scrollY",
        "visualViewport",
        "screenX",
        "screenY",
        "outerWidth",
        "outerHeight",
        "devicePixelRatio",
        "screen",
        "chrome",
        "navigator",
        "onresize",
        "performance",
        "crypto",
        "indexedDB",
        "sessionStorage",
        "localStorage",
        "scheduler",
        "alert",
        "atob",
        "btoa",
        "fetch",
        "matchMedia",
        "postMessage",
        "queueMicrotask",
        "requestAnimationFrame",
        "setInterval",
        "setTimeout",
        "caches",
        "__NEXT_DATA__",
        "__BUILD_MANIFEST",
        "__NEXT_PRELOADREADY",
    ])
    script_source = random.choice(list(script_sources)) if script_sources else DEFAULT_POW_SCRIPT
    return [
        sum(random.choices(SCREEN_RESOLUTIONS, k=1)[0]),
        _legacy_parse_time(tz_name),
        4294705152,
        1,
        user_agent,
        script_source,
        data_build,
        "en-US",
        "en-US,en",
        random.random(),
        navigator_key,
        random.choice(DOCUMENT_KEYS),
        window_key,
        time.perf_counter() * 1000,
        new_uuid(),
        "",
        random.choice(CORES),
        time.time() * 1000 - (time.perf_counter() * 1000),
        0, 0, 0, 0, 0, 0,
        0,  # 0 = edge/chrome, 1 = firefox
    ]


def _fnv1a_32(text: str) -> str:
    """与线上 Sentinel SDK 一致的 FNV-1a 32 位 + avalanche 摘要（8 位小写十六进制）。

    对应 SDK 实现：
        e = 2166136261
        for ch in text: e ^= charCode; e = imul(e, 16777619) >>> 0
        e ^= e >>> 16; e = imul(e, 2246822507) >>> 0
        e ^= e >>> 13; e = imul(e, 3266489909) >>> 0
        e ^= e >>> 16
        return (e >>> 0).toString(16).padStart(8, "0")
    """
    h = 2166136261
    for ch in text:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    h ^= h >> 16
    h = (h * 2246822507) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 3266489909) & 0xFFFFFFFF
    h ^= h >> 16
    return format(h & 0xFFFFFFFF, "08x")


def _pow_generate(seed: str, difficulty: str, config: list[Any], limit: int = 500000) -> tuple[str, bool]:
    """按线上 SDK 语义求解 proof-of-work。

    SDK 每轮把 config[3] 设为计数器、config[9] 设为耗时毫秒，重新序列化后取
    `fnv1a(seed + base64(config))`，并与 difficulty 做“字符串前缀比较”，命中即返回
    `base64(config) + "~S"`。
    """
    difficulty = str(difficulty or "0")
    start = time.perf_counter()
    for i in range(limit):
        config[3] = i
        config[9] = int((time.perf_counter() - start) * 1000)
        encoded = pybase64.b64encode(
            json.dumps(config, separators=(",", ":"), ensure_ascii=False).encode()
        ).decode()
        if _fnv1a_32(seed + encoded)[: len(difficulty)] <= difficulty:
            return encoded + "~S", True
    fallback = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D" + pybase64.b64encode(f'"{seed}"'.encode()).decode()
    return fallback, False


def build_legacy_requirements_token(
    user_agent: str,
    script_sources: Sequence[str] | None = None,
    data_build: str = "",
    tz_name: str = "",
) -> str:
    config = build_pow_config(user_agent, script_sources=script_sources, data_build=data_build, tz_name=tz_name)
    # 需求令牌固定 config[3]=1、config[9]=极小的耗时毫秒，与线上 SDK 的 requirements 阶段一致。
    config[3] = 1
    config[9] = random.randint(0, 5)
    return "gAAAAAC" + pybase64.b64encode(
        json.dumps(config, separators=(",", ":"), ensure_ascii=False).encode()
    ).decode()


def build_proof_token(
    seed: str,
    difficulty: str,
    user_agent: str,
    script_sources: Sequence[str] | None = None,
    data_build: str = "",
    tz_name: str = "",
) -> str:
    config = build_pow_config(user_agent, script_sources=script_sources, data_build=data_build, tz_name=tz_name)
    answer, solved = _pow_generate(seed, difficulty, config)
    if not solved:
        raise RuntimeError(f"failed to solve proof token: difficulty={difficulty}")
    return "gAAAAAB" + answer

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

FALLBACK_TIMEZONE = "America/Los_Angeles"
CACHE_TTL_SECONDS = 600.0  # 缓存 10 分钟

_cache: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


def get_js_timezone_offset_min(tz_name: str) -> int:
    """计算 JavaScript 规范下的 getTimezoneOffset() 分钟数。
    定义：UTC 时间减去本地时间（UTC - Local）。
    例如：
    - UTC+8 (Asia/Shanghai) -> -480
    - UTC-7 (America/Los_Angeles 夏令时) -> 420
    - UTC-8 (America/Los_Angeles 冬令时) -> 480
    - UTC+9 (Asia/Tokyo) -> -540
    """
    try:
        tz = ZoneInfo(tz_name) if tz_name else ZoneInfo(FALLBACK_TIMEZONE)
    except Exception:
        tz = ZoneInfo(FALLBACK_TIMEZONE)
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(tz)
    offset_secs = now_local.utcoffset().total_seconds()
    return int(-offset_secs // 60)


def get_pow_formatted_time(tz_name: str = "") -> str:
    """生成对齐当前时区的 JavaScript new Date().toString() 格式时间字符串。
    例如：'Thu Oct 15 2026 01:23:45 GMT-0700 (PDT)'
    """
    try:
        tz = ZoneInfo(tz_name) if tz_name else ZoneInfo(FALLBACK_TIMEZONE)
    except Exception:
        tz = ZoneInfo(FALLBACK_TIMEZONE)
    now_local = datetime.now(tz)
    offset_secs = now_local.utcoffset().total_seconds()
    sign = "-" if offset_secs < 0 else "+"
    abs_secs = abs(int(offset_secs))
    hours = abs_secs // 3600
    minutes = (abs_secs % 3600) // 60
    tz_abbr = now_local.tzname() or "UTC"
    return now_local.strftime("%a %b %d %Y %H:%M:%S") + f" GMT{sign}{hours:02d}{minutes:02d} ({tz_abbr})"


COUNTRY_TIMEZONE_MAP = {
    "JP": "Asia/Tokyo",
    "SG": "Asia/Singapore",
    "TW": "Asia/Taipei",
    "KR": "Asia/Seoul",
    "HK": "Asia/Hong_Kong",
    "US": "America/Los_Angeles",
    "GB": "Europe/London",
    "DE": "Europe/Berlin",
    "FR": "Europe/Paris",
    "AU": "Australia/Sydney",
    "CA": "America/Toronto",
    "NL": "Europe/Amsterdam",
}


def _probe_ip_timezone(proxy_url: str = "", timeout: float = 4.0) -> str:
    """优先通过 chatgpt.com/cdn-cgi/trace 探测实际连接 ChatGPT 的出口 IP 与国家，避免分流欺骗。"""
    handler = None
    if proxy_url:
        handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        opener = urllib.request.build_opener(handler)
    else:
        opener = urllib.request.build_opener()

    # 1. 优先请求 chatgpt.com/cdn-cgi/trace 获取精准的出口 IP 与国家代码
    try:
        req = urllib.request.Request(
            "https://chatgpt.com/cdn-cgi/trace",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with opener.open(req, timeout=timeout) as resp:
            if resp.status == 200:
                text = resp.read().decode("utf-8", errors="ignore")
                data = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
                loc = str(data.get("loc") or "").upper().strip()
                ip = str(data.get("ip") or "").strip()
                if loc and loc in COUNTRY_TIMEZONE_MAP:
                    mapped_tz = COUNTRY_TIMEZONE_MAP[loc]
                    logger.info({"event": "ip_timezone_trace_hit", "loc": loc, "ip": ip, "timezone": mapped_tz})
                    return mapped_tz
    except Exception as exc:
        logger.debug({"event": "ip_timezone_trace_failed", "error": str(exc)})

    # 2. 备用通用 IP 接口
    endpoints = [
        ("https://ipwho.is/", lambda d: d.get("timezone", {}).get("id")),
        ("https://freeipapi.com/api/json", lambda d: (d.get("timeZones") or [None])[0]),
        ("https://ipapi.co/json/", lambda d: d.get("timezone")),
    ]

    for url, parser in endpoints:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            with opener.open(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    tz = parser(data)
                    if tz and isinstance(tz, str):
                        tz = tz.strip()
                        ZoneInfo(tz)
                        return tz
        except Exception:
            continue
    return ""


def get_runtime_timezone_info(proxy_url: str = "") -> Tuple[str, int]:
    """获取当前出口的时区名称与 JS 偏移分钟数，带 10 分钟内存缓存与自动降级。"""
    cache_key = proxy_url.strip() if proxy_url else "__direct__"
    now = time.time()

    with _lock:
        if cache_key in _cache:
            cached_tz, exp = _cache[cache_key]
            if now < exp:
                return cached_tz, get_js_timezone_offset_min(cached_tz)

    detected = ""
    try:
        detected = _probe_ip_timezone(proxy_url)
    except Exception as exc:
        logger.debug({"event": "ip_timezone_probe_error", "proxy": proxy_url, "error": str(exc)})

    final_tz = detected if detected else FALLBACK_TIMEZONE
    with _lock:
        _cache[cache_key] = (final_tz, now + CACHE_TTL_SECONDS)

    logger.info({
        "event": "ip_timezone_resolved",
        "proxy": proxy_url or "direct",
        "timezone": final_tz,
        "source": "probe" if detected else "fallback"
    })
    return final_tz, get_js_timezone_offset_min(final_tz)

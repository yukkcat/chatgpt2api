"""调用 sentinel 求解服务（sentinel_solver/）计算 Turnstile token。

2026-10-14 起 chatgpt.com 只接受在真实页面里算出的 Turnstile；缺失时对话接口返回 403，
低质量时返回伪装成 404 的 "Model not found"。求解服务未配置或调用失败时退回本地求解器，
本地求解器已跟不上新版挑战程序，只作兜底。
"""
from __future__ import annotations

import threading
import time

from curl_cffi import requests

from services.config import config
from utils.log import logger
from utils.turnstile import solve_turnstile_token

SOLVER_TIMEOUT_SECONDS = 20
USER_AGENT_CACHE_SECONDS = 600

_user_agent_lock = threading.Lock()
_user_agent_cache: dict[str, object] = {"url": "", "value": "", "expires_at": 0.0}


def _solver_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.sentinel_solver_key:
        headers["Authorization"] = f"Bearer {config.sentinel_solver_key}"
    return headers


def solver_user_agent() -> str:
    """求解页面使用的 UA；未配置求解服务或获取失败时返回空串。

    requirements/proof token 里编码的 UA 必须与算 Turnstile 的页面一致，
    否则对话接口返回伪装成 404 的 "Model not found"。
    """
    base_url = config.sentinel_solver_url
    if not base_url:
        return ""
    with _user_agent_lock:
        now = time.monotonic()
        if _user_agent_cache["url"] == base_url and now < float(_user_agent_cache["expires_at"]):
            return str(_user_agent_cache["value"])
        value = ""
        try:
            response = requests.get(f"{base_url}/health", headers=_solver_headers(), timeout=SOLVER_TIMEOUT_SECONDS)
            if response.status_code == 200:
                value = str((response.json() or {}).get("user_agent") or "")
        except Exception as exc:
            logger.warning({"event": "sentinel_solver_health_error", "error": str(exc)})
        # 失败时短暂缓存空值，避免每个请求都去探测一个挂掉的求解服务
        _user_agent_cache.update(url=base_url, value=value, expires_at=now + (USER_AGENT_CACHE_SECONDS if value else 30))
        return value


def solve_turnstile(dx: str, p: str) -> str:
    """dx 为 prepare 响应里的 turnstile.dx，p 为 prepare 请求提交的 requirements token。"""
    base_url = config.sentinel_solver_url
    if base_url:
        try:
            response = requests.post(
                f"{base_url}/v1/turnstile",
                headers=_solver_headers(),
                json={"dx": dx, "p": p},
                timeout=SOLVER_TIMEOUT_SECONDS,
            )
            if response.status_code == 200:
                token = str((response.json() or {}).get("token") or "")
                if token:
                    return token
            logger.warning({
                "event": "sentinel_solver_failed",
                "status": response.status_code,
                "body": str(response.text or "")[:200],
            })
        except Exception as exc:
            logger.warning({"event": "sentinel_solver_error", "error": str(exc)})
    return solve_turnstile_token(dx, p) or ""

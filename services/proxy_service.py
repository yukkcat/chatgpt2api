"""Global outbound proxy and Cloudflare clearance helpers."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import random
import re
import threading
import time
from typing import Callable, Mapping
from urllib import request as urllib_request
from urllib.parse import quote, urlparse

from curl_cffi.requests import Session

from services.config import config
from services.storage.configuration_repository import (
    ProxyConfigurationRepository,
    proxy_configuration_repository,
)


FlareSolverrRequestMethod = Callable[[str, bytes, dict[str, str], float], bytes]

DEFAULT_PROXY_NODE_IMAGE_CONCURRENCY_LIMIT = 30
MAX_PROXY_NODE_IMAGE_CONCURRENCY_LIMIT = 10000
PROXY_NODE_IMAGE_CONCURRENCY_FIELDS = (
    "image_concurrency_limit",
    "image_concurrency",
    "max_image_concurrency",
)


class ProxyReferenceUnavailableError(RuntimeError):
    """Raised when a configured proxy reference cannot provide its egress."""


class ImageEgressDeadlineError(RuntimeError):
    """Raised when image egress capacity cannot be acquired before its deadline."""


def normalize_proxy_url(url: str) -> str:
    """Normalize proxy URLs for curl_cffi.

    SOCKS proxies should use remote-DNS resolution by default, so generic
    ``socks://`` and ``socks5://`` inputs are upgraded to ``socks5h://``.
    HTTP/HTTPS/socks5h inputs are otherwise left untouched except trimming.
    """
    candidate = str(url or "").strip()
    if candidate and "://" not in candidate:
        candidate = _colon_proxy_to_url(candidate)
    lowered = candidate.lower()
    if lowered.startswith("socks://"):
        return "socks5h://" + candidate[len("socks://") :]
    if lowered.startswith("socks5://"):
        return "socks5h://" + candidate[len("socks5://") :]
    return candidate


@dataclass(frozen=True)
class ProxyRuntimeProfile:
    proxy_url: str = ""
    proxy_source: str = "direct"
    egress_key: str = "direct"
    egress_label: str = "direct"
    proxy_group_id: str = ""
    proxy_node_id: str = ""
    proxy_node_name: str = ""
    image_concurrency_limit: int = 0
    image_egress_reserved: bool = False
    image_egress_wait_ms: int = 0
    resource: bool = False
    runtime_enabled: bool = False
    egress_mode: str = "direct"
    skip_ssl_verify: bool = False
    reset_session_status_codes: tuple[int, ...] = field(default_factory=lambda: (403,))
    clearance: dict[str, object] = field(default_factory=dict, repr=False)

    @property
    def clearance_enabled(self) -> bool:
        return (
            self.runtime_enabled
            and bool(self.clearance.get("enabled"))
            and self.clearance_mode in {"manual", "flaresolverr"}
        )

    @property
    def clearance_mode(self) -> str:
        return str(self.clearance.get("mode") or "none").strip().lower()

    @property
    def refresh_interval(self) -> int:
        try:
            return max(0, int(self.clearance.get("refresh_interval") or 0))
        except (OverflowError, TypeError, ValueError):
            return 0

    @property
    def timeout_sec(self) -> int:
        try:
            return max(1, int(self.clearance.get("timeout_sec") or 60))
        except (OverflowError, TypeError, ValueError):
            return 60


@dataclass(frozen=True)
class ClearanceBundle:
    target_host: str
    proxy_url: str = ""
    cookies: dict[str, str] = field(default_factory=dict, repr=False)
    user_agent: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None

    def is_valid_for(self, target_host: str, proxy_url: str, *, now: float | None = None) -> bool:
        host = _normalize_host(target_host)
        if self.target_host and host and _normalize_host(self.target_host) != host:
            return False
        if normalize_proxy_url(self.proxy_url) != normalize_proxy_url(proxy_url):
            return False
        if self.expires_at is not None and (time.time() if now is None else now) >= self.expires_at:
            return False
        return bool(self.cookies or self.user_agent)

    def cookie_header(self) -> str:
        return _cookies_to_header(self.cookies)


@dataclass(frozen=True)
class ProxyGroupSelection:
    proxy_url: str = ""
    group_id: str = ""
    node_id: str = ""
    node_name: str = ""
    image_concurrency_limit: int = 0
    image_egress_reserved: bool = False
    image_egress_wait_ms: int = 0

    @property
    def egress_key(self) -> str:
        if self.group_id and self.node_id:
            return f"group:{self.group_id}:{self.node_id}"
        return _egress_key_for_proxy(self.proxy_url)

    @property
    def egress_label(self) -> str:
        if self.group_id and self.node_id:
            return f"{self.group_id}/{self.node_name or self.node_id}"
        return _egress_key_for_proxy(self.proxy_url)


@dataclass(frozen=True)
class ResolvedProxyReference:
    proxy_url: str = ""
    source: str = "direct"
    terminal: bool = False
    egress_key: str = "direct"
    egress_label: str = "direct"
    proxy_group_id: str = ""
    proxy_node_id: str = ""
    proxy_node_name: str = ""
    image_concurrency_limit: int = 0
    image_egress_reserved: bool = False
    image_egress_wait_ms: int = 0


class FlareSolverrClearanceProvider:
    def __init__(self, flaresolverr_url: str, request_method: FlareSolverrRequestMethod | None = None) -> None:
        self.flaresolverr_url = str(flaresolverr_url or "").strip().rstrip("/")
        self._request_method = request_method or self._urllib_post

    def get_clearance(self, target_url: str, proxy_url: str = "", timeout_sec: int = 60) -> ClearanceBundle | None:
        if not self.flaresolverr_url:
            return None

        timeout = _coerce_timeout(timeout_sec)
        payload: dict[str, object] = {
            "cmd": "request.get",
            "url": str(target_url or ""),
            "maxTimeout": int(timeout * 1000),
        }
        proxy_url = normalize_proxy_url(proxy_url)
        if proxy_url:
            payload["proxy"] = {"url": proxy_url}

        endpoint = f"{self.flaresolverr_url}/v1"
        try:
            body = json.dumps(payload).encode("utf-8")
            raw_response = self._request_method(
                endpoint,
                body,
                {"Content-Type": "application/json"},
                timeout,
            )
            data = json.loads(raw_response.decode("utf-8") if isinstance(raw_response, bytes) else raw_response)
        except Exception:
            return None

        if not isinstance(data, dict) or str(data.get("status") or "").lower() != "ok":
            return None
        solution = data.get("solution")
        if not isinstance(solution, dict):
            return None

        target_host = _host_from_url(target_url)
        cookies = _filter_flaresolverr_cookies(solution.get("cookies"), target_host)
        user_agent = str(solution.get("userAgent") or "").strip()
        if not cookies and not user_agent:
            return None
        return ClearanceBundle(
            target_host=target_host,
            proxy_url=proxy_url,
            cookies=cookies,
            user_agent=user_agent,
        )

    @staticmethod
    def _urllib_post(endpoint: str, body: bytes, headers: dict[str, str], timeout: float) -> bytes:
        req = urllib_request.Request(endpoint, data=body, headers=headers, method="POST")
        with urllib_request.urlopen(req, timeout=timeout) as response:
            return response.read()


class ProxySettingsStore:
    def __init__(
        self,
        config_store=None,
        clearance_provider_factory: Callable[[str], FlareSolverrClearanceProvider] | None = None,
        proxy_repository: ProxyConfigurationRepository | None = None,
    ) -> None:
        self._config = config_store or config
        self._proxy_repository = (
            proxy_repository
            or (config_store if config_store is not None else proxy_configuration_repository)
        )
        self._clearance_provider_factory = clearance_provider_factory or FlareSolverrClearanceProvider
        self._clearance_cache: dict[tuple[str, str], ClearanceBundle] = {}
        self._provider_cache: dict[str, FlareSolverrClearanceProvider] = {}
        self._flight_locks: dict[tuple[str, str], threading.Lock] = {}
        self._egress_inflight: dict[str, int] = {}
        self._lock = threading.RLock()
        self._egress_condition = threading.Condition(self._lock)

    def get_profile(
        self,
        account: dict | None = None,
        proxy: str = "",
        resource: bool = False,
        upstream: bool = False,
        reserve_image_egress: bool = False,
        deadline_monotonic: float | None = None,
    ) -> ProxyRuntimeProfile:
        runtime = self._get_runtime_settings()
        clearance = dict(runtime.get("clearance") if isinstance(runtime.get("clearance"), dict) else {})
        runtime_enabled = bool(runtime.get("enabled"))

        selected_proxy = ""
        source = "direct"
        terminal = False
        egress_key = "direct"
        egress_label = "direct"
        proxy_group_id = ""
        proxy_node_id = ""
        proxy_node_name = ""
        image_concurrency_limit = 0
        image_egress_reserved = False
        image_egress_wait_ms = 0

        account_proxy = _clean((account or {}).get("proxy") if isinstance(account, dict) else "")
        if account_proxy:
            resolved = self._resolve_proxy_reference(
                account_proxy,
                source="account",
                terminal_when_unresolved=True,
                reserve_image_egress=reserve_image_egress,
                deadline_monotonic=deadline_monotonic,
            )
            selected_proxy, source, terminal = resolved.proxy_url, resolved.source, resolved.terminal
            egress_key = resolved.egress_key
            egress_label = resolved.egress_label
            proxy_group_id = resolved.proxy_group_id
            proxy_node_id = resolved.proxy_node_id
            proxy_node_name = resolved.proxy_node_name
            image_concurrency_limit = resolved.image_concurrency_limit
            image_egress_reserved = resolved.image_egress_reserved
            image_egress_wait_ms = resolved.image_egress_wait_ms

        if not selected_proxy and not terminal:
            account_group_proxy = self._account_group_proxy_reference(account)
            if account_group_proxy:
                resolved = self._resolve_proxy_reference(
                    account_group_proxy,
                    source="account_group",
                    terminal_when_unresolved=False,
                    reserve_image_egress=reserve_image_egress,
                    deadline_monotonic=deadline_monotonic,
                )
                selected_proxy, source, terminal = resolved.proxy_url, resolved.source, resolved.terminal
                egress_key = resolved.egress_key
                egress_label = resolved.egress_label
                proxy_group_id = resolved.proxy_group_id
                proxy_node_id = resolved.proxy_node_id
                proxy_node_name = resolved.proxy_node_name
                image_concurrency_limit = resolved.image_concurrency_limit
                image_egress_reserved = resolved.image_egress_reserved
                image_egress_wait_ms = resolved.image_egress_wait_ms

        if not selected_proxy and not terminal:
            explicit_proxy = _clean(proxy)
            if explicit_proxy:
                resolved = self._resolve_proxy_reference(
                    explicit_proxy,
                    source="explicit",
                    terminal_when_unresolved=True,
                    reserve_image_egress=reserve_image_egress,
                    deadline_monotonic=deadline_monotonic,
                )
                selected_proxy, source, terminal = resolved.proxy_url, resolved.source, resolved.terminal
                egress_key = resolved.egress_key
                egress_label = resolved.egress_label
                proxy_group_id = resolved.proxy_group_id
                proxy_node_id = resolved.proxy_node_id
                proxy_node_name = resolved.proxy_node_name
                image_concurrency_limit = resolved.image_concurrency_limit
                image_egress_reserved = resolved.image_egress_reserved
                image_egress_wait_ms = resolved.image_egress_wait_ms

        if not selected_proxy and not terminal and upstream and resource and runtime_enabled:
            resource_proxy = _clean(runtime.get("resource_proxy_url"))
            if resource_proxy:
                resolved = self._resolve_proxy_reference(
                    resource_proxy,
                    source="resource",
                    terminal_when_unresolved=True,
                    reserve_image_egress=reserve_image_egress,
                    deadline_monotonic=deadline_monotonic,
                )
                selected_proxy, source, terminal = resolved.proxy_url, resolved.source, resolved.terminal
                egress_key = resolved.egress_key
                egress_label = resolved.egress_label
                proxy_group_id = resolved.proxy_group_id
                proxy_node_id = resolved.proxy_node_id
                proxy_node_name = resolved.proxy_node_name
                image_concurrency_limit = resolved.image_concurrency_limit
                image_egress_reserved = resolved.image_egress_reserved
                image_egress_wait_ms = resolved.image_egress_wait_ms

        if not selected_proxy and not terminal:
            legacy_proxy = _clean(self._proxy_configuration().get("proxy"))
            if legacy_proxy:
                resolved = self._resolve_proxy_reference(
                    legacy_proxy,
                    source="default",
                    terminal_when_unresolved=False,
                    reserve_image_egress=reserve_image_egress,
                    deadline_monotonic=deadline_monotonic,
                )
                selected_proxy, source, terminal = resolved.proxy_url, resolved.source, resolved.terminal
                egress_key = resolved.egress_key
                egress_label = resolved.egress_label
                proxy_group_id = resolved.proxy_group_id
                proxy_node_id = resolved.proxy_node_id
                proxy_node_name = resolved.proxy_node_name
                image_concurrency_limit = resolved.image_concurrency_limit
                image_egress_reserved = resolved.image_egress_reserved
                image_egress_wait_ms = resolved.image_egress_wait_ms

        return ProxyRuntimeProfile(
            proxy_url=normalize_proxy_url(selected_proxy),
            proxy_source=source,
            egress_key=egress_key or _egress_key_for_proxy(selected_proxy),
            egress_label=egress_label or source,
            proxy_group_id=proxy_group_id,
            proxy_node_id=proxy_node_id,
            proxy_node_name=proxy_node_name,
            image_concurrency_limit=max(0, int(image_concurrency_limit or 0)),
            image_egress_reserved=bool(image_egress_reserved),
            image_egress_wait_ms=max(0, int(image_egress_wait_ms or 0)),
            resource=bool(resource),
            runtime_enabled=runtime_enabled,
            egress_mode="proxy" if selected_proxy else "direct",
            skip_ssl_verify=bool(runtime.get("skip_ssl_verify")),
            reset_session_status_codes=_status_codes_tuple(runtime.get("reset_session_status_codes")),
            clearance=clearance,
        )

    def get_fallback_proxy_reference(self) -> str:
        reference = _clean(self._proxy_configuration().get("fallback_proxy"))
        return "" if reference.lower() == "global" else reference

    def get_fallback_profile(
        self,
        *,
        resource: bool = False,
        upstream: bool = False,
        reserve_image_egress: bool = False,
        deadline_monotonic: float | None = None,
    ) -> ProxyRuntimeProfile | None:
        reference = self.get_fallback_proxy_reference()
        if not reference:
            return None
        profile = self.get_profile(
            account=None,
            proxy=reference,
            resource=resource,
            upstream=upstream,
            reserve_image_egress=reserve_image_egress,
            deadline_monotonic=deadline_monotonic,
        )
        source = str(profile.proxy_source or "direct").strip() or "direct"
        if source.startswith("explicit"):
            source = "fallback" + source[len("explicit"):]
        elif not source.startswith("fallback"):
            source = f"fallback_{source}"
        label = str(profile.egress_label or "").strip()
        if not label or label.startswith("explicit"):
            label = "fallback" if profile.proxy_url else source
        return replace(profile, proxy_source=source, egress_label=label)

    def build_session_kwargs(
        self,
        account: dict | None = None,
        proxy: str = "",
        resource: bool = False,
        upstream: bool = False,
        **session_kwargs,
    ) -> dict[str, object]:
        profile = self.get_profile(account=account, proxy=proxy, resource=resource, upstream=upstream)
        if profile.proxy_url:
            session_kwargs["proxy"] = profile.proxy_url
        if profile.skip_ssl_verify:
            session_kwargs["verify"] = False
        return session_kwargs

    @staticmethod
    def build_session_kwargs_from_profile(
        profile: ProxyRuntimeProfile,
        **session_kwargs,
    ) -> dict[str, object]:
        if profile.proxy_url:
            session_kwargs["proxy"] = profile.proxy_url
        if profile.skip_ssl_verify:
            session_kwargs["verify"] = False
        return session_kwargs

    def build_headers(
        self,
        headers: Mapping[str, object] | None = None,
        target_url: str = "https://chatgpt.com",
        account: dict | None = None,
        proxy: str = "",
        resource: bool = False,
        upstream: bool = True,
    ) -> dict[str, object]:
        merged_headers: dict[str, object] = dict(headers or {})
        profile = self.get_profile(account=account, proxy=proxy, resource=resource, upstream=upstream)
        if not profile.clearance_enabled:
            return merged_headers

        target_host = _host_from_url(target_url)
        bundle = self._bundle_for_headers(profile, target_host)
        if bundle is None or not bundle.is_valid_for(target_host, profile.proxy_url):
            return merged_headers

        if bundle.user_agent and _find_header_key(merged_headers, "user-agent") is None:
            merged_headers["User-Agent"] = bundle.user_agent

        if bundle.cookies:
            cookie_key = _find_header_key(merged_headers, "cookie") or "Cookie"
            existing_cookie = str(merged_headers.get(cookie_key) or "")
            cookie_header = _merge_cookie_header(existing_cookie, bundle.cookies)
            if cookie_header:
                merged_headers[cookie_key] = cookie_header
        return merged_headers

    def refresh_clearance(
        self,
        target_url: str = "https://chatgpt.com",
        account: dict | None = None,
        proxy: str = "",
        resource: bool = False,
        force: bool = False,
        upstream: bool = True,
    ) -> ClearanceBundle | None:
        profile = self.get_profile(account=account, proxy=proxy, resource=resource, upstream=upstream)
        if not profile.clearance_enabled:
            return None

        target_host = _host_from_url(target_url)
        key = self._cache_key(profile.proxy_url, target_host)
        if profile.clearance_mode == "manual":
            bundle = self._build_manual_bundle(profile, target_host)
            if bundle is not None:
                self._set_cached_bundle(key, bundle)
            return bundle
        if profile.clearance_mode != "flaresolverr":
            return None

        cached_before = self._get_cached_bundle(key)
        if cached_before is not None and not force and cached_before.is_valid_for(target_host, profile.proxy_url):
            return cached_before

        lock = self._get_flight_lock(key)
        if not lock.acquire(blocking=False):
            with lock:
                pass
            return self._get_cached_bundle(key) or cached_before

        try:
            cached_now = self._get_cached_bundle(key)
            if cached_now is not None and not force and cached_now.is_valid_for(target_host, profile.proxy_url):
                return cached_now

            flaresolverr_url = str(profile.clearance.get("flaresolverr_url") or "").strip()
            provider = self._get_provider(flaresolverr_url)
            new_bundle = provider.get_clearance(target_url, proxy_url=profile.proxy_url, timeout_sec=profile.timeout_sec)
            if new_bundle is not None:
                expires_at = time.time() + profile.refresh_interval if profile.refresh_interval else None
                if (
                    not new_bundle.target_host
                    or normalize_proxy_url(new_bundle.proxy_url) != normalize_proxy_url(profile.proxy_url)
                    or new_bundle.expires_at != expires_at
                ):
                    new_bundle = replace(
                        new_bundle,
                        target_host=new_bundle.target_host or target_host,
                        proxy_url=profile.proxy_url,
                        expires_at=expires_at,
                    )
                self._set_cached_bundle(key, new_bundle)
                return new_bundle
            return cached_now or cached_before
        finally:
            lock.release()

    def invalidate_clearance(
        self,
        target_url: str = "https://chatgpt.com",
        account: dict | None = None,
        proxy: str = "",
        resource: bool = False,
        upstream: bool = True,
    ) -> None:
        profile = self.get_profile(account=account, proxy=proxy, resource=resource, upstream=upstream)
        target_host = _host_from_url(target_url)
        key = self._cache_key(profile.proxy_url, target_host)
        with self._lock:
            self._clearance_cache.pop(key, None)

    def get_runtime_status(self) -> dict[str, object]:
        profile = self.get_profile(upstream=True)
        with self._lock:
            cached_hosts = [host for _proxy, host in self._clearance_cache]
            cached_count = len(self._clearance_cache)
        return {
            "enabled": profile.runtime_enabled,
            "egress_mode": profile.egress_mode,
            "proxy_source": profile.proxy_source,
            "egress_key": profile.egress_key,
            "egress_label": profile.egress_label,
            "image_concurrency_limit": profile.image_concurrency_limit,
            "has_proxy": bool(profile.proxy_url),
            "skip_ssl_verify": profile.skip_ssl_verify,
            "clearance_enabled": profile.clearance_enabled,
            "clearance_mode": profile.clearance_mode,
            "has_clearance_bundle": cached_count > 0,
            "cached_clearance_hosts": sorted(set(cached_hosts)),
        }

    def should_skip_ssl_verify(self) -> bool:
        return bool(self._get_runtime_settings().get("skip_ssl_verify"))

    def acquire_image_egress(
        self,
        profile: ProxyRuntimeProfile,
        *,
        deadline_monotonic: float | None = None,
    ) -> int:
        if (
            deadline_monotonic is not None
            and deadline_monotonic > 0
            and time.monotonic() >= deadline_monotonic
        ):
            raise ImageEgressDeadlineError(
                "image request deadline exceeded before egress acquisition"
            )
        if bool(getattr(profile, "image_egress_reserved", False)):
            return max(0, int(getattr(profile, "image_egress_wait_ms", 0) or 0))
        limit = max(0, int(getattr(profile, "image_concurrency_limit", 0) or 0))
        if limit <= 0:
            return 0
        key = _clean(getattr(profile, "egress_key", "")) or _egress_key_for_proxy(profile.proxy_url)
        started = time.perf_counter()
        with self._egress_condition:
            while int(self._egress_inflight.get(key, 0)) >= limit:
                remaining = (
                    deadline_monotonic - time.monotonic()
                    if deadline_monotonic is not None and deadline_monotonic > 0
                    else None
                )
                if remaining is not None and remaining <= 0:
                    raise ImageEgressDeadlineError(
                        "image request deadline exceeded while waiting for egress capacity"
                    )
                self._egress_condition.wait(
                    timeout=min(1.0, remaining) if remaining is not None else 1.0
                )
            self._egress_inflight[key] = int(self._egress_inflight.get(key, 0)) + 1
        return int((time.perf_counter() - started) * 1000)

    def release_image_egress(self, profile: ProxyRuntimeProfile) -> None:
        limit = max(0, int(getattr(profile, "image_concurrency_limit", 0) or 0))
        if limit <= 0:
            return
        key = _clean(getattr(profile, "egress_key", "")) or _egress_key_for_proxy(profile.proxy_url)
        with self._egress_condition:
            current = int(self._egress_inflight.get(key, 0))
            if current <= 1:
                self._egress_inflight.pop(key, None)
            else:
                self._egress_inflight[key] = current - 1
            self._egress_condition.notify_all()

    def _get_runtime_settings(self) -> dict[str, object]:
        try:
            runtime = self._config.get_proxy_runtime_settings()
        except AttributeError:
            runtime = {}
        return runtime if isinstance(runtime, dict) else {}

    def _config_dict_list(self, key: str) -> list[dict]:
        data = getattr(self._config, "data", None)
        if not isinstance(data, dict):
            try:
                data = self._config.get()
            except AttributeError:
                data = {}
        raw = data.get(key) if isinstance(data, dict) else None
        if not isinstance(raw, list):
            return []
        return [dict(item) for item in raw if isinstance(item, dict)]

    def _proxy_configuration(self) -> dict[str, object]:
        try:
            value = self._proxy_repository.get()
        except AttributeError:
            value = getattr(self._proxy_repository, "data", None)
        return dict(value) if isinstance(value, dict) else {}

    def _proxy_dict_list(self, key: str) -> list[dict]:
        raw = self._proxy_configuration().get(key)
        if not isinstance(raw, list):
            return []
        return [dict(item) for item in raw if isinstance(item, dict)]

    def _account_group_proxy_reference(self, account: dict | None) -> str:
        if not isinstance(account, dict):
            return ""
        group_id = _clean(account.get("group_id"))
        if not group_id:
            return ""
        for group in self._config_dict_list("account_groups"):
            if _clean(group.get("id")) != group_id or group.get("enabled") is False:
                continue
            proxy = _clean(group.get("proxy"))
            if proxy:
                return proxy
            proxy_group_id = _clean(group.get("proxy_group_id"))
            return f"group:{proxy_group_id}" if proxy_group_id else ""
        return ""

    def _resolve_proxy_reference(
        self,
        value: object,
        *,
        source: str,
        terminal_when_unresolved: bool,
        reserve_image_egress: bool = False,
        deadline_monotonic: float | None = None,
    ) -> ResolvedProxyReference:
        raw = _clean(value)
        lower = raw.lower()
        if not raw or lower == "global":
            return ResolvedProxyReference(source=source)
        if lower == "direct":
            return ResolvedProxyReference(source=f"{source}_direct", terminal=True)
        if lower.startswith("profile:"):
            proxy = self._resolve_proxy_profile(raw.split(":", 1)[1])
            return ResolvedProxyReference(
                proxy_url=proxy,
                source=f"{source}_profile",
                terminal=bool(proxy) or terminal_when_unresolved,
                egress_key=_egress_key_for_proxy(proxy),
                egress_label=f"{source}_profile",
            )
        if lower.startswith("group:"):
            group_id = _clean(raw.split(":", 1)[1])
            selection = self._resolve_proxy_group(
                group_id,
                reserve_image_egress=reserve_image_egress,
                deadline_monotonic=deadline_monotonic,
            )
            if not selection.proxy_url:
                raise ProxyReferenceUnavailableError(
                    f"proxy group is unavailable: {group_id or '(missing id)'}"
                )
            return ResolvedProxyReference(
                proxy_url=selection.proxy_url,
                source=f"{source}_group",
                terminal=bool(selection.proxy_url) or terminal_when_unresolved,
                egress_key=selection.egress_key,
                egress_label=selection.egress_label,
                proxy_group_id=selection.group_id,
                proxy_node_id=selection.node_id,
                proxy_node_name=selection.node_name,
                image_concurrency_limit=selection.image_concurrency_limit,
                image_egress_reserved=selection.image_egress_reserved,
                image_egress_wait_ms=selection.image_egress_wait_ms,
            )
        return ResolvedProxyReference(
            proxy_url=raw,
            source=source,
            terminal=True,
            egress_key=_egress_key_for_proxy(raw),
            egress_label=source,
        )

    def _resolve_proxy_profile(self, profile_id: object) -> str:
        normalized = _clean(profile_id)
        if not normalized:
            return ""
        for profile in self._proxy_dict_list("proxy_profiles"):
            if _clean(profile.get("id")) == normalized and profile.get("enabled", True):
                return _clean(profile.get("proxy"))
        return ""

    def _resolve_proxy_group(
        self,
        group_id: object,
        *,
        reserve_image_egress: bool = False,
        deadline_monotonic: float | None = None,
    ) -> ProxyGroupSelection:
        normalized = _clean(group_id)
        if not normalized:
            return ProxyGroupSelection()
        for group in self._proxy_dict_list("proxy_groups"):
            if _clean(group.get("id")) != normalized or group.get("enabled") is False:
                continue
            nodes = [
                node for node in group.get("nodes", [])
                if isinstance(node, dict)
                and node.get("enabled", True)
                and _clean(node.get("url"))
            ]
            if not nodes:
                return ProxyGroupSelection()
            started = time.perf_counter()
            indexed_nodes = list(enumerate(nodes))
            with self._egress_condition:
                while True:
                    remaining = (
                        deadline_monotonic - time.monotonic()
                        if deadline_monotonic is not None and deadline_monotonic > 0
                        else None
                    )
                    if remaining is not None and remaining <= 0:
                        raise ImageEgressDeadlineError(
                            "image request deadline exceeded while selecting proxy group capacity"
                        )
                    available_nodes = [
                        (node_index, node)
                        for node_index, node in indexed_nodes
                        if self._proxy_node_has_image_capacity(normalized, node, node_index)
                    ]
                    if available_nodes:
                        selected_index, selected = random.choice(available_nodes)
                        selection = _proxy_group_selection(normalized, selected, selected_index)
                        if reserve_image_egress and selection.image_concurrency_limit > 0:
                            self._egress_inflight[selection.egress_key] = int(
                                self._egress_inflight.get(selection.egress_key, 0)
                            ) + 1
                            selection = replace(
                                selection,
                                image_egress_reserved=True,
                                image_egress_wait_ms=int((time.perf_counter() - started) * 1000),
                            )
                        return selection
                    if not reserve_image_egress:
                        selected_index, selected = min(
                            indexed_nodes,
                            key=lambda item: self._proxy_node_load_score(normalized, item[1], item[0]),
                        )
                        return _proxy_group_selection(normalized, selected, selected_index)
                    self._egress_condition.wait(
                        timeout=min(1.0, remaining) if remaining is not None else 1.0
                    )
        return ProxyGroupSelection()

    def _proxy_node_has_image_capacity(self, group_id: str, node: Mapping[str, object], index: int) -> bool:
        limit = proxy_node_image_concurrency_limit(node)
        if limit <= 0:
            return True
        key = _proxy_group_node_key(group_id, node, index)
        return int(self._egress_inflight.get(key, 0)) < limit

    def _proxy_node_load_score(self, group_id: str, node: Mapping[str, object], index: int) -> tuple[float, int]:
        key = _proxy_group_node_key(group_id, node, index)
        current = int(self._egress_inflight.get(key, 0))
        limit = proxy_node_image_concurrency_limit(node)
        if limit <= 0:
            return 0.0, current
        return current / max(1, limit), current

    def _bundle_for_headers(self, profile: ProxyRuntimeProfile, target_host: str) -> ClearanceBundle | None:
        key = self._cache_key(profile.proxy_url, target_host)
        if profile.clearance_mode == "manual":
            bundle = self._build_manual_bundle(profile, target_host)
            if bundle is not None:
                self._set_cached_bundle(key, bundle)
            return bundle
        if profile.clearance_mode == "flaresolverr":
            return self._get_cached_bundle(key)
        return None

    def _build_manual_bundle(self, profile: ProxyRuntimeProfile, target_host: str) -> ClearanceBundle | None:
        cookies = _parse_cookie_header(str(profile.clearance.get("cf_cookies") or ""))
        cf_clearance = str(profile.clearance.get("cf_clearance") or "").strip()
        if cf_clearance and "cf_clearance" not in cookies:
            cookies["cf_clearance"] = cf_clearance
        user_agent = str(profile.clearance.get("user_agent") or "").strip()
        if not cookies and not user_agent:
            return None

        now = time.time()
        expires_at = now + profile.refresh_interval if profile.refresh_interval else None
        return ClearanceBundle(
            target_host=target_host,
            proxy_url=profile.proxy_url,
            cookies=cookies,
            user_agent=user_agent,
            created_at=now,
            expires_at=expires_at,
        )

    def _get_provider(self, flaresolverr_url: str) -> FlareSolverrClearanceProvider:
        url = str(flaresolverr_url or "").strip().rstrip("/")
        with self._lock:
            provider = self._provider_cache.get(url)
            if provider is None:
                provider = self._clearance_provider_factory(url)
                self._provider_cache[url] = provider
            return provider

    def _get_flight_lock(self, key: tuple[str, str]) -> threading.Lock:
        with self._lock:
            lock = self._flight_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._flight_locks[key] = lock
            return lock

    def _get_cached_bundle(self, key: tuple[str, str]) -> ClearanceBundle | None:
        with self._lock:
            return self._clearance_cache.get(key)

    def _set_cached_bundle(self, key: tuple[str, str], bundle: ClearanceBundle) -> None:
        with self._lock:
            self._clearance_cache[key] = bundle

    @staticmethod
    def _cache_key(proxy_url: str, target_host: str) -> tuple[str, str]:
        return (normalize_proxy_url(proxy_url), _normalize_host(target_host))


def _clean(value: object) -> str:
    return str(value or "").strip()


def _colon_proxy_to_url(url: str) -> str:
    parts = url.split(":", 3)
    if len(parts) == 4 and parts[1].isdigit():
        host, port, username, password = parts
        return f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"
    if len(parts) == 2 and parts[1].isdigit():
        return f"http://{url}"
    return url


def _normalize_host(host: str) -> str:
    return str(host or "").strip().strip(".").lower()


def _host_from_url(url: str) -> str:
    candidate = str(url or "").strip()
    parsed = urlparse(candidate)
    if not parsed.hostname and candidate and "://" not in candidate:
        parsed = urlparse(f"https://{candidate}")
    return _normalize_host(parsed.hostname or "")


def _status_codes_tuple(value: object) -> tuple[int, ...]:
    source = value if isinstance(value, list) else [403]
    codes: list[int] = []
    for item in source:
        if isinstance(item, bool):
            continue
        try:
            code = int(item)
        except (OverflowError, TypeError, ValueError):
            continue
        if 100 <= code <= 599 and code not in codes:
            codes.append(code)
    return tuple(codes or [403])


def _egress_key_for_proxy(proxy_url: object) -> str:
    normalized = normalize_proxy_url(_clean(proxy_url))
    return f"proxy:{normalized}" if normalized else "direct"


def _proxy_node_id(node: Mapping[str, object], index: int) -> str:
    return _clean(node.get("id")) or _clean(node.get("name")) or f"node-{index + 1}"


def _proxy_group_node_key(group_id: str, node: Mapping[str, object], index: int) -> str:
    return f"group:{group_id}:{_proxy_node_id(node, index)}"


def proxy_node_image_concurrency_limit(
    node: Mapping[str, object],
    *,
    fallback: Mapping[str, object] | None = None,
) -> int:
    for source in (node, fallback):
        if source is None:
            continue
        for key in PROXY_NODE_IMAGE_CONCURRENCY_FIELDS:
            value = source.get(key)
            if value is None or value == "":
                continue
            try:
                return max(0, min(int(float(value)), MAX_PROXY_NODE_IMAGE_CONCURRENCY_LIMIT))
            except (OverflowError, TypeError, ValueError):
                return DEFAULT_PROXY_NODE_IMAGE_CONCURRENCY_LIMIT
    return DEFAULT_PROXY_NODE_IMAGE_CONCURRENCY_LIMIT


def _proxy_group_selection(group_id: str, node: Mapping[str, object], index: int) -> ProxyGroupSelection:
    node_id = _proxy_node_id(node, index)
    return ProxyGroupSelection(
        proxy_url=_clean(node.get("url")),
        group_id=group_id,
        node_id=node_id,
        node_name=_clean(node.get("name")) or node_id,
        image_concurrency_limit=proxy_node_image_concurrency_limit(node),
    )


def _coerce_timeout(value: object) -> float:
    try:
        timeout = float(value)
    except (OverflowError, TypeError, ValueError):
        timeout = 60.0
    return max(1.0, timeout)


def _is_valid_proxy_url(url: str) -> bool:
    parsed = urlparse(normalize_proxy_url(url))
    return parsed.scheme in {"http", "https", "socks5", "socks5h"} and bool(parsed.netloc)


def _domain_matches(host: str, domain: str) -> bool:
    normalized_host = _normalize_host(host)
    normalized_domain = _normalize_host(domain.lstrip("."))
    if not normalized_domain:
        return True
    return normalized_host == normalized_domain or normalized_host.endswith(f".{normalized_domain}")


def _filter_flaresolverr_cookies(raw_cookies: object, target_host: str) -> dict[str, str]:
    if not isinstance(raw_cookies, list):
        return {}

    filtered_cookies: dict[str, str] = {}
    for item in raw_cookies:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        value = str(item.get("value") or "")
        domain = str(item.get("domain") or "").strip()
        if not domain or _domain_matches(target_host, domain):
            filtered_cookies[name] = value
    return filtered_cookies


def _parse_cookie_header(header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in str(header or "").split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name:
            cookies[name.strip()] = value.strip()
    return cookies


def _cookies_to_header(cookies: Mapping[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items() if name)


def _merge_cookie_header(existing_header: str, cookies: Mapping[str, str]) -> str:
    existing = str(existing_header or "").strip()
    existing_names = set(_parse_cookie_header(existing).keys())
    additions = [f"{name}={value}" for name, value in cookies.items() if name and name not in existing_names]
    if existing and additions:
        return existing.rstrip("; ") + "; " + "; ".join(additions)
    if existing:
        return existing
    return "; ".join(additions)


def _find_header_key(headers: Mapping[str, object], name: str) -> str | None:
    target = name.lower()
    for key in headers:
        if str(key).lower() == target:
            return str(key)
    return None


def _redact_url_credentials(text: str) -> str:
    return re.sub(
        r"((?:https?|socks5h?|socks)://)([^\s/@:]+):([^\s/@]+)@",
        r"\1[REDACTED]@",
        str(text or ""),
        flags=re.IGNORECASE,
    )


def test_proxy(url: str = "", *, timeout: float = 15.0) -> dict:
    candidate = normalize_proxy_url(_clean(url))
    proxy_source = "input"
    if not candidate:
        profile = proxy_settings.get_profile(upstream=True)
        candidate = profile.proxy_url
        proxy_source = profile.proxy_source
    result_base = {"proxy_source": proxy_source, "has_proxy": bool(candidate)}
    if not candidate:
        return {
            "ok": False,
            "status": 0,
            "latency_ms": 0,
            "error": "no active proxy configured",
            **result_base,
        }
    if not _is_valid_proxy_url(candidate):
        return {
            "ok": False,
            "status": 0,
            "latency_ms": 0,
            "error": "invalid proxy url",
            **result_base,
        }
    session = Session(impersonate="edge101", verify=not proxy_settings.should_skip_ssl_verify(), proxy=candidate)
    started = time.perf_counter()
    try:
        response = session.get(
            "https://chatgpt.com/api/auth/csrf",
            headers={"user-agent": "Mozilla/5.0 (chatgpt2api proxy test)"},
            timeout=timeout,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": response.status_code < 500,
            "status": int(response.status_code),
            "latency_ms": latency_ms,
            "error": None if response.status_code < 500 else f"HTTP {response.status_code}",
            **result_base,
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "status": 0,
            "latency_ms": latency_ms,
            "error": _redact_url_credentials(str(exc) or exc.__class__.__name__),
            **result_base,
        }
    finally:
        session.close()


def test_clearance(target_url: str = "https://chatgpt.com") -> dict:
    target_url = str(target_url or "https://chatgpt.com").strip() or "https://chatgpt.com"
    started = time.perf_counter()
    status = proxy_settings.get_runtime_status()
    if not status.get("clearance_enabled"):
        return {
            "ok": False,
            "status": "disabled",
            "latency_ms": 0,
            "has_cookies": False,
            "user_agent": "",
            "error": "clearance is disabled",
            "runtime": status,
        }
    try:
        bundle = proxy_settings.refresh_clearance(target_url=target_url, force=True, upstream=True)
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "status": "error",
            "latency_ms": latency_ms,
            "has_cookies": False,
            "user_agent": "",
            "error": _redact_url_credentials(str(exc) or exc.__class__.__name__),
            "runtime": proxy_settings.get_runtime_status(),
        }

    latency_ms = int((time.perf_counter() - started) * 1000)
    runtime = proxy_settings.get_runtime_status()
    if bundle is None:
        return {
            "ok": False,
            "status": "failed",
            "latency_ms": latency_ms,
            "has_cookies": False,
            "user_agent": "",
            "error": "clearance refresh returned no bundle",
            "runtime": runtime,
        }
    return {
        "ok": True,
        "status": "ok",
        "latency_ms": latency_ms,
        "has_cookies": bool(bundle.cookies),
        "user_agent": bundle.user_agent or "",
        "error": None,
        "runtime": runtime,
    }


proxy_settings = ProxySettingsStore()

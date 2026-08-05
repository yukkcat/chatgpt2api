from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import threading
from typing import Any, Callable, Iterable, Literal, Mapping, TypeVar
from urllib.parse import urlparse

from contracts.proxy import (
    ProxyDefaultsMutation,
    ProxyEffectiveReference,
    ProxyGroup,
    ProxyGroupDeleteMutation,
    ProxyGroupList,
    ProxyGroupMutation,
    ProxyGroupPatch,
    ProxyGroupTestResponse,
    ProxyHealth,
    ProxyNode,
    ProxyNodeImportInvalidItem,
    ProxyNodeImportNode,
    ProxyNodeImportResult,
    ProxyNodeTestResult,
    ProxyReference,
    ProxyTestResult,
    ProxyTestSummary,
    ProxyView,
)
from services.config import config
from services.proxy_service import (
    DEFAULT_PROXY_NODE_IMAGE_CONCURRENCY_LIMIT,
    MAX_PROXY_NODE_IMAGE_CONCURRENCY_LIMIT,
    normalize_proxy_url,
    proxy_node_image_concurrency_limit,
)
from services.storage.configuration_repository import proxy_configuration_repository


PROXY_SCHEMA_VERSION = 1
_PROXY_GROUP_STRATEGIES = {"request_random", "time_window", "round_robin"}
_PROXY_URL_SCHEMES = {"http", "https", "socks5", "socks5h"}
_PROXY_NODE_IMPORT_MAX_LINES = 10_000
_MutationResultT = TypeVar("_MutationResultT")


@dataclass(frozen=True)
class ProxyAssignmentProjection:
    reference: str
    mode: Literal["inherit", "direct", "group", "custom", "profile"]
    group_id: str
    label: str


class ProxyGroupInUseError(ValueError):
    """Raised when deleting a group would change an active egress to direct."""


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _slug_id(value: object) -> str:
    raw = _clean_text(value).lower()
    chars: list[str] = []
    for char in raw:
        if char.isalnum() or char in {"-", "_"}:
            chars.append(char)
        elif char.isspace():
            chars.append("-")
    return "".join(chars).strip("-_")[:64]


def _group_reference_id(value: object) -> str:
    raw = _clean_text(value)
    if raw.lower().startswith("group:"):
        raw = raw.split(":", 1)[1].strip()
    return raw


def _custom_proxy_display(value: str) -> str:
    try:
        parsed = urlparse(value if "://" in value else f"http://{value}")
        host = parsed.hostname or ""
        if not host:
            return "自定义代理"
        display_host = f"[{host}]" if ":" in host else host
        port = f":{parsed.port}" if parsed.port else ""
        scheme = parsed.scheme if "://" in value else ""
        prefix = f"{scheme}://" if scheme else ""
        return f"{prefix}{display_host}{port}"
    except (TypeError, ValueError):
        return "自定义代理"


def project_proxy_assignment(
    value: object,
    *,
    legacy_group_id: object = "",
    group_names: Mapping[str, str] | None = None,
) -> ProxyAssignmentProjection:
    """Project a stored account or account-group Proxy Reference for callers."""
    raw = _clean_text(value)
    if raw.lower() == "global":
        raw = ""
    if not raw:
        fallback_group_id = _group_reference_id(legacy_group_id)
        raw = f"group:{fallback_group_id}" if fallback_group_id else ""

    lowered = raw.lower()
    if not raw:
        return ProxyAssignmentProjection(raw, "inherit", "", "使用默认出口")
    if lowered == "direct":
        return ProxyAssignmentProjection(raw, "direct", "", "强制直连")
    if lowered.startswith("group:"):
        group_id = _group_reference_id(raw)
        group_name = _clean_text((group_names or {}).get(group_id)) or group_id or "-"
        return ProxyAssignmentProjection(raw, "group", group_id, f"代理组：{group_name}")
    if lowered.startswith("profile:"):
        profile_id = _clean_text(raw.split(":", 1)[1])
        return ProxyAssignmentProjection(
            raw,
            "profile",
            "",
            f"历史代理：{profile_id or '-'}",
        )
    return ProxyAssignmentProjection(raw, "custom", "", _custom_proxy_display(raw))


def _stored_node_id(item: dict[str, Any], index: int) -> str:
    return (
        _clean_text(item.get("id"))
        or _clean_text(item.get("name"))
        or f"node-{index + 1}"
    )


def _coerce_rotation_minutes(value: object) -> float:
    try:
        minutes = float(value)
    except (OverflowError, TypeError, ValueError):
        minutes = 0.0
    return max(0.0, min(minutes, 1440.0))


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _unknown_health() -> ProxyHealth:
    return ProxyHealth(state="unknown")


def _normalized_proxy_node_url(value: object) -> tuple[str, str]:
    raw = _clean_text(value)
    if not raw:
        return "", "proxy node url is required"
    if any(char.isspace() for char in raw):
        return "", "proxy node url cannot contain whitespace"
    if "://" not in raw:
        return "", "proxy node url must start with http://, https://, socks5://, or socks5h://"

    try:
        parsed = urlparse(raw)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return "", "proxy node url has an invalid host or port"

    scheme = parsed.scheme.lower()
    if scheme not in _PROXY_URL_SCHEMES:
        return "", "proxy node url uses an unsupported scheme"
    if not host:
        return "", "proxy node url requires a host"
    if parsed.netloc.endswith(":") or port == 0:
        return "", "proxy node url has an invalid port"
    if parsed.path not in {"", "/"}:
        return "", "proxy node url cannot include a path"
    if parsed.params or parsed.query or parsed.fragment:
        return "", "proxy node url cannot include parameters, a query, or a fragment"

    normalized = normalize_proxy_url(raw)
    normalized_parsed = urlparse(normalized)
    normalized_scheme = normalized_parsed.scheme.lower()
    normalized_host = (normalized_parsed.hostname or "").lower()
    if ":" in normalized_host and not normalized_host.startswith("["):
        normalized_host = f"[{normalized_host}]"
    else:
        try:
            normalized_host = normalized_host.encode("idna").decode("ascii")
        except UnicodeError:
            return "", "proxy node url has an invalid internationalized host"
    userinfo = ""
    if "@" in normalized_parsed.netloc:
        userinfo = f"{normalized_parsed.netloc.rsplit('@', 1)[0]}@"
    normalized_port = normalized_parsed.port
    if (
        (normalized_scheme == "http" and normalized_port == 80)
        or (normalized_scheme == "https" and normalized_port == 443)
    ):
        normalized_port = None
    port_text = f":{normalized_port}" if normalized_port is not None else ""
    return f"{normalized_scheme}://{userinfo}{normalized_host}{port_text}", ""


def normalize_proxy_node_url(value: object) -> str:
    """Validate and canonicalize a configured proxy URL."""
    normalized, error = _normalized_proxy_node_url(value)
    if error:
        raise ValueError(error)
    return normalized


def proxy_node_url_error(value: object) -> str:
    """Return an admin-facing validation error for a configured proxy URL."""
    return _normalized_proxy_node_url(value)[1]


def _proxy_import_error_text(error: str) -> str:
    translations = {
        "proxy node url is required": "地址为空",
        "proxy node url cannot contain whitespace": "地址不能包含空白字符",
        "proxy node url must start with http://, https://, socks5://, or socks5h://": (
            "请填写以 http://、https://、socks5:// 或 socks5h:// 开头的地址"
        ),
        "proxy node url has an invalid host or port": "代理主机或端口格式无效",
        "proxy node url uses an unsupported scheme": "仅支持 HTTP、HTTPS 和 SOCKS5 代理",
        "proxy node url requires a host": "缺少代理主机",
        "proxy node url has an invalid port": "代理端口格式无效",
        "proxy node url cannot include a path": "代理地址不能包含路径",
        "proxy node url cannot include parameters, a query, or a fragment": (
            "代理地址不能包含参数、查询或片段"
        ),
        "proxy node url has an invalid internationalized host": "国际化域名格式无效",
    }
    return translations.get(error, error)


class ProxyManagementService:
    """Owns the admin proxy configuration contract without changing runtime egress selection."""

    def __init__(
        self,
        config_store: Any = None,
        *,
        account_provider: Callable[[], Iterable[dict[str, Any]]] | None = None,
        account_group_provider: Callable[[], Iterable[dict[str, Any]]] | None = None,
    ) -> None:
        self._config = config_store or proxy_configuration_repository
        self._account_provider = account_provider
        self._account_group_provider = account_group_provider
        if config_store is None and account_group_provider is None:
            self._account_group_provider = self._configured_account_groups
        self._mutation_lock = threading.RLock()

    @staticmethod
    def _configured_account_groups() -> Iterable[dict[str, Any]]:
        groups = config.get().get("account_groups")
        return groups if isinstance(groups, list) else ()

    def bind_account_provider(
        self,
        provider: Callable[[], Iterable[dict[str, Any]]],
    ) -> None:
        """Bind the process-wide Upstream Account snapshot provider once."""
        if not callable(provider):
            raise TypeError("account provider must be callable")
        with self._mutation_lock:
            if self._account_provider is not None:
                raise RuntimeError("account provider is already bound")
            self._account_provider = provider

    def view(self) -> ProxyView:
        return self._build_view(self._snapshot())

    def list_groups(self) -> ProxyGroupList:
        snapshot = self._snapshot()
        return ProxyGroupList(
            schema_version=PROXY_SCHEMA_VERSION,
            generated_at=_generated_at(),
            revision=self._revision(snapshot),
            groups=self._groups(snapshot),
        )

    def normalize_assignment_reference(
        self,
        value: object,
        *,
        legacy_group_id: object = "",
    ) -> str:
        """Normalize a Proxy Reference before assigning it to an account owner."""
        return self.mutate_assignment_references(
            [(value, legacy_group_id)],
            lambda normalized: normalized[0],
        )

    def mutate_assignment_references(
        self,
        references: Iterable[tuple[object, object]],
        mutation: Callable[[list[str]], _MutationResultT],
    ) -> _MutationResultT:
        """Validate Proxy References and persist their owners as one mutation."""
        requested = list(references)
        with self._mutation_lock:
            snapshot = self._snapshot()
            normalized = [
                self._normalize_assignment_reference(
                    value,
                    legacy_group_id=legacy_group_id,
                    snapshot=snapshot,
                )
                for value, legacy_group_id in requested
            ]
            return mutation(normalized)

    def _normalize_assignment_reference(
        self,
        value: object,
        *,
        legacy_group_id: object,
        snapshot: dict[str, Any],
    ) -> str:
        raw = _clean_text(value)
        if raw.lower() == "global":
            return ""
        if not raw and _clean_text(legacy_group_id):
            raw = f"group:{_clean_text(legacy_group_id)}"
        if not raw:
            return ""
        if raw.lower() == "direct":
            return "direct"
        if raw.lower().startswith("group:"):
            group_id = _group_reference_id(raw)
            if not group_id:
                raise ValueError("proxy group id is required")
            group = next(
                (group for group in self._groups(snapshot) if group.id == group_id),
                None,
            )
            if group is None:
                raise ValueError("proxy group not found")
            if not group.enabled or not any(
                node.enabled and node.url for node in group.nodes
            ):
                raise ValueError("proxy group is unavailable")
            return f"group:{group_id}"
        return normalize_proxy_node_url(raw)

    def save_defaults(
        self,
        default_reference: ProxyReference,
        fallback_reference: ProxyReference | None,
    ) -> ProxyDefaultsMutation:
        with self._mutation_lock:
            snapshot = self._snapshot()
            default_value = self._serialize_reference(
                default_reference,
                snapshot=snapshot,
            )
            fallback_value = ""
            if fallback_reference is not None:
                fallback_value = self._serialize_reference(
                    fallback_reference,
                    snapshot=snapshot,
                )
            updated = self._config.update({
                "proxy": default_value,
                "fallback_proxy": fallback_value,
            })
            view = self._build_view(updated)
            return ProxyDefaultsMutation(
                default_reference=view.default_reference,
                fallback_reference=view.fallback_reference,
                effective_default=view.effective_default,
                effective_fallback=view.effective_fallback,
                revision=view.revision,
            )

    def save_group(self, patch: ProxyGroupPatch) -> ProxyGroupMutation:
        values = patch.model_dump(mode="python", exclude_unset=True)
        with self._mutation_lock:
            snapshot = self._snapshot()
            raw_groups = self._raw_dict_list(snapshot, "proxy_groups")
            requested_id = _group_reference_id(values.get("id"))
            existing = next(
                (item for item in raw_groups if _clean_text(item.get("id")) == requested_id),
                None,
            )
            if bool(values.get("create_only")) and existing is not None:
                raise ValueError("proxy group already exists")
            group_id = (
                _clean_text(existing.get("id"))
                if existing is not None
                else _slug_id(requested_id or values.get("name"))
            )
            if not group_id:
                raise ValueError("proxy group id is required")
            if existing is None and any(
                _clean_text(item.get("id")) == group_id for item in raw_groups
            ):
                raise ValueError("proxy group already exists")

            base = dict(existing or {})
            strategy = _clean_text(
                values.get("strategy")
                if values.get("strategy") is not None
                else base.get("strategy")
            )
            strategy = strategy or "request_random"
            if strategy not in _PROXY_GROUP_STRATEGIES:
                raise ValueError("unsupported proxy group strategy")

            if "nodes" in values and values.get("nodes") is not None:
                node_values = values.get("nodes") or []
                nodes = self._storage_nodes(
                    node_values,
                    existing_nodes=base.get("nodes"),
                )
            else:
                nodes = [
                    dict(node)
                    for node in (base.get("nodes") or [])
                    if isinstance(node, dict)
                ]
            if not nodes:
                raise ValueError("proxy group requires at least one proxy node")

            item = {
                **base,
                "id": group_id,
                "name": (
                    _clean_text(values.get("name"))
                    if values.get("name") is not None
                    else _clean_text(base.get("name"))
                ) or group_id,
                "strategy": strategy,
                "rotation_interval_minutes": _coerce_rotation_minutes(
                    values.get("rotation_interval_minutes")
                    if values.get("rotation_interval_minutes") is not None
                    else base.get("rotation_interval_minutes")
                ),
                "enabled": (
                    bool(values.get("enabled"))
                    if "enabled" in values and values.get("enabled") is not None
                    else bool(base.get("enabled", True))
                ),
                "notes": (
                    _clean_text(values.get("notes"))
                    if values.get("notes") is not None
                    else _clean_text(base.get("notes"))
                ),
                "nodes": nodes,
            }
            next_groups = [
                group for group in raw_groups
                if _clean_text(group.get("id")) != group_id
            ]
            next_groups.append(item)
            updated = self._config.update({"proxy_groups": next_groups})
            group = next(
                group for group in self._groups(updated)
                if group.id == group_id
            )
            return ProxyGroupMutation(
                group=group,
                revision=self._revision(updated),
            )

    def delete_group(self, group_id: object) -> ProxyGroupDeleteMutation:
        stored_id = _group_reference_id(group_id)
        if not stored_id:
            raise ValueError("proxy group id is required")
        with self._mutation_lock:
            snapshot = self._snapshot()
            raw_groups = self._raw_dict_list(snapshot, "proxy_groups")
            next_groups = [
                group for group in raw_groups
                if _clean_text(group.get("id")) != stored_id
            ]
            if len(next_groups) == len(raw_groups):
                raise KeyError("proxy group not found")
            references = self._group_reference_map(snapshot).get(stored_id, [])
            if references:
                raise ProxyGroupInUseError(
                    "proxy group is in use: " + ", ".join(references)
                )
            updated = self._config.update({"proxy_groups": next_groups})
            return ProxyGroupDeleteMutation(
                deleted_id=stored_id,
                revision=self._revision(updated),
            )

    def _group_reference_map(self, snapshot: dict[str, Any]) -> dict[str, list[str]]:
        references: dict[str, list[str]] = {}

        def append(group_id: str, label: str) -> None:
            if not group_id:
                return
            labels = references.setdefault(group_id, [])
            if label not in labels:
                labels.append(label)

        append(self._configured_group_reference(snapshot.get("proxy")), "默认出口")
        append(self._configured_group_reference(snapshot.get("fallback_proxy")), "备用出口")

        account_groups = (
            self._account_group_provider()
            if self._account_group_provider is not None
            else self._raw_dict_list(snapshot, "account_groups")
        )
        for item in account_groups:
            if not isinstance(item, dict):
                continue
            item_id = _clean_text(item.get("id")) or _clean_text(item.get("name")) or "未知"
            append(self._item_group_reference(item), f"账号组 {item_id}")

        accounts = self._account_provider() if self._account_provider is not None else ()
        for item in accounts:
            if not isinstance(item, dict):
                continue
            item_id = (
                _clean_text(item.get("id"))
                or _clean_text(item.get("email"))
                or "未知"
            )
            append(self._item_group_reference(item), f"账号 {item_id}")
        return references

    @staticmethod
    def _item_group_reference(item: dict[str, Any]) -> str:
        proxy = _clean_text(item.get("proxy"))
        if proxy:
            return (
                _group_reference_id(proxy)
                if proxy.lower().startswith("group:")
                else ""
            )
        return _group_reference_id(item.get("proxy_group_id"))

    @staticmethod
    def _configured_group_reference(value: object) -> str:
        raw = _clean_text(value)
        return _group_reference_id(raw) if raw.lower().startswith("group:") else ""

    def import_nodes(
        self,
        text: object,
        existing_urls: Iterable[object] = (),
    ) -> ProxyNodeImportResult:
        """Parse normalized proxy-node draft additions behind one interface."""
        existing_keys: set[str] = set()
        for value in existing_urls:
            normalized, error = _normalized_proxy_node_url(value)
            if normalized and not error:
                existing_keys.add(normalized)

        lines = [
            (index, value.strip())
            for index, value in enumerate(str(text or "").splitlines(), start=1)
            if value.strip()
        ]
        if len(lines) > _PROXY_NODE_IMPORT_MAX_LINES:
            raise ValueError(f"一次最多导入 {_PROXY_NODE_IMPORT_MAX_LINES} 个代理节点")

        seen_urls: set[str] = set()
        nodes: list[ProxyNodeImportNode] = []
        invalid_items: list[ProxyNodeImportInvalidItem] = []
        duplicate_count = 0
        for index, raw in lines:
            parts = raw.split()
            if len(parts) > 2:
                invalid_items.append(ProxyNodeImportInvalidItem(
                    line=index,
                    raw=raw,
                    reason="格式应为：代理地址 [图片并发]",
                ))
                continue

            url_text = parts[0]
            concurrency_limit = DEFAULT_PROXY_NODE_IMAGE_CONCURRENCY_LIMIT
            if len(parts) == 2:
                concurrency_text = parts[1]
                if not concurrency_text.isdecimal():
                    invalid_items.append(ProxyNodeImportInvalidItem(
                        line=index,
                        raw=raw,
                        reason="图片并发必须是 0 到 10000 的整数",
                    ))
                    continue
                concurrency_limit = int(concurrency_text)
                if concurrency_limit > MAX_PROXY_NODE_IMAGE_CONCURRENCY_LIMIT:
                    invalid_items.append(ProxyNodeImportInvalidItem(
                        line=index,
                        raw=raw,
                        reason="图片并发必须是 0 到 10000 的整数",
                    ))
                    continue

            normalized, error = _normalized_proxy_node_url(url_text)
            if error:
                invalid_items.append(ProxyNodeImportInvalidItem(
                    line=index,
                    raw=raw,
                    reason=_proxy_import_error_text(error),
                ))
                continue
            if normalized in existing_keys or normalized in seen_urls:
                duplicate_count += 1
                continue
            seen_urls.add(normalized)
            nodes.append(ProxyNodeImportNode(
                url=normalized,
                image_concurrency_limit=concurrency_limit,
            ))

        return ProxyNodeImportResult(
            nodes=nodes,
            added_count=len(nodes),
            duplicate_count=duplicate_count,
            invalid_count=len(invalid_items),
            invalid_items=invalid_items,
        )

    @staticmethod
    def group_test_response(
        results: Iterable[tuple[str, dict[str, Any] | ProxyTestResult]],
    ) -> ProxyGroupTestResponse:
        rows: list[ProxyNodeTestResult] = []
        for node_id, raw_result in results:
            result = (
                raw_result
                if isinstance(raw_result, ProxyTestResult)
                else ProxyTestResult.model_validate(raw_result)
            )
            rows.append(ProxyNodeTestResult(node_id=_clean_text(node_id), result=result))

        succeeded = sum(1 for row in rows if row.result.ok)
        failed = len(rows) - succeeded
        if rows and failed == 0:
            status = "success"
            tone = "success"
        elif succeeded > 0:
            status = "partial"
            tone = "warning"
        else:
            status = "failed"
            tone = "danger"
        max_latency_ms = max((row.result.latency_ms for row in rows), default=0)
        if status == "success":
            label = "代理组可用"
            message = f"{len(rows)} 个节点全部可用，最慢 {max_latency_ms}ms"
        elif status == "partial":
            label = "代理组部分可用"
            message = f"{len(rows)} 个节点中 {succeeded} 个可用，{failed} 个失败"
        elif rows:
            label = "代理组不可用"
            message = f"{len(rows)} 个节点全部失败"
        else:
            label = "代理组无可测试节点"
            message = "当前代理组没有可用节点"
        summary = ProxyTestSummary(
            status=status,
            tone=tone,
            total=len(rows),
            succeeded=succeeded,
            failed=failed,
            max_latency_ms=max_latency_ms,
            label=label,
            message=message,
        )
        return ProxyGroupTestResponse(
            summary=summary,
            results=rows,
            result=rows[0].result if len(rows) == 1 else None,
        )

    def _snapshot(self) -> dict[str, Any]:
        value = self._config.get()
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _raw_dict_list(snapshot: dict[str, Any], key: str) -> list[dict[str, Any]]:
        value = snapshot.get(key)
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, dict)]

    def _build_view(self, snapshot: dict[str, Any]) -> ProxyView:
        default_reference = self._parse_reference(snapshot.get("proxy"), empty_is_direct=True)
        fallback_reference = self._parse_reference(snapshot.get("fallback_proxy"), empty_is_direct=False)
        return ProxyView(
            schema_version=PROXY_SCHEMA_VERSION,
            generated_at=_generated_at(),
            revision=self._revision(snapshot),
            default_reference=default_reference,
            fallback_reference=fallback_reference,
            effective_default=self._effective_reference(default_reference, snapshot),
            effective_fallback=self._effective_reference(fallback_reference, snapshot),
            groups=self._groups(snapshot),
        )

    def _groups(self, snapshot: dict[str, Any]) -> list[ProxyGroup]:
        references = self._group_reference_map(snapshot)
        groups = [
            group for item in self._raw_dict_list(snapshot, "proxy_groups")
            if (
                group := self._group(
                    item,
                    references=references.get(_group_reference_id(item.get("id")), []),
                )
            ) is not None
        ]
        return sorted(groups, key=lambda group: (group.name.casefold(), group.id.casefold()))

    def _group(
        self,
        item: dict[str, Any],
        *,
        references: Iterable[str] = (),
    ) -> ProxyGroup | None:
        group_id = _clean_text(item.get("id"))
        if not group_id:
            return None
        strategy = _clean_text(item.get("strategy"))
        if strategy not in _PROXY_GROUP_STRATEGIES:
            strategy = "request_random"
        nodes = [
            self._node(node, index)
            for index, node in enumerate(item.get("nodes") or [])
            if isinstance(node, dict)
        ]
        reference_labels = list(references)
        return ProxyGroup(
            id=group_id,
            name=_clean_text(item.get("name")) or group_id,
            strategy=strategy,
            rotation_interval_minutes=_coerce_rotation_minutes(item.get("rotation_interval_minutes")),
            enabled=item.get("enabled") is not False,
            notes=_clean_text(item.get("notes")),
            nodes=nodes,
            reference_text=f"group:{group_id}",
            health=_unknown_health(),
            can_delete=not reference_labels,
            references=reference_labels,
        )

    @staticmethod
    def _node(item: dict[str, Any], index: int) -> ProxyNode:
        node_id = _stored_node_id(item, index)
        return ProxyNode(
            id=node_id,
            name=_clean_text(item.get("name")) or node_id,
            url=_clean_text(item.get("url")),
            enabled=item.get("enabled") is not False,
            image_concurrency_limit=proxy_node_image_concurrency_limit(item),
            notes=_clean_text(item.get("notes")),
            health=_unknown_health(),
        )

    @staticmethod
    def _storage_nodes(
        values: object,
        *,
        existing_nodes: object = None,
    ) -> list[dict[str, Any]]:
        if not isinstance(values, list):
            return []
        existing_by_id = {
            _stored_node_id(item, index): dict(item)
            for index, item in enumerate(existing_nodes or [])
            if isinstance(item, dict)
        }
        nodes: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_urls: set[str] = set()
        for index, raw in enumerate(values):
            if not isinstance(raw, dict):
                continue
            requested_id = _clean_text(raw.get("id"))
            existing = existing_by_id.get(requested_id)
            node_id = (
                requested_id
                if existing is not None
                else _slug_id(requested_id or raw.get("name") or f"node-{index + 1}")
            )
            node_id = node_id or f"node-{index + 1}"
            if node_id in seen_ids:
                raise ValueError(f"duplicate proxy node id: {node_id}")
            raw_url = _clean_text(raw.get("url"))
            if not raw_url:
                raise ValueError(f"proxy node url is required: {node_id}")
            try:
                url = normalize_proxy_node_url(raw_url)
            except ValueError as exc:
                raise ValueError(f"{exc}: {node_id}") from exc
            if url in seen_urls:
                raise ValueError(f"duplicate proxy node url: {node_id}")
            seen_ids.add(node_id)
            seen_urls.add(url)
            nodes.append({
                **(existing or {}),
                "id": node_id,
                "name": _clean_text(raw.get("name")) or node_id,
                "url": url,
                "enabled": raw.get("enabled") is not False,
                "image_concurrency_limit": proxy_node_image_concurrency_limit(
                    raw,
                    fallback=existing,
                ),
                "notes": _clean_text(raw.get("notes")),
            })
        return nodes

    @staticmethod
    def _parse_reference(value: object, *, empty_is_direct: bool) -> ProxyReference | None:
        raw = _clean_text(value)
        lower = raw.lower()
        if not raw or lower == "global":
            return ProxyReference(mode="direct") if empty_is_direct else None
        if lower == "direct":
            return ProxyReference(mode="direct")
        if lower.startswith("group:"):
            group_id = _group_reference_id(raw)
            if group_id:
                return ProxyReference(mode="group", group_id=group_id)
            return ProxyReference(mode="direct") if empty_is_direct else None
        return ProxyReference(mode="custom", url=raw)

    def _serialize_reference(
        self,
        reference: ProxyReference,
        *,
        snapshot: dict[str, Any],
    ) -> str:
        if reference.mode == "direct":
            return "direct"
        if reference.mode == "group":
            group_id = _group_reference_id(reference.group_id)
            if not group_id:
                raise ValueError("proxy group id is required")
            group_ids = {
                _clean_text(group.get("id"))
                for group in self._raw_dict_list(snapshot, "proxy_groups")
            }
            if group_id not in group_ids:
                raise ValueError("proxy group not found")
            return f"group:{group_id}"
        url = _clean_text(reference.url)
        if not url:
            raise ValueError("proxy url is required")
        if url.lower().startswith("profile:"):
            profile_id = _clean_text(url.split(":", 1)[1])
            profile_ids = {
                _clean_text(profile.get("id"))
                for profile in self._raw_dict_list(snapshot, "proxy_profiles")
            }
            configured_references = {
                _clean_text(snapshot.get("proxy")),
                _clean_text(snapshot.get("fallback_proxy")),
            }
            if profile_id and (profile_id in profile_ids or url in configured_references):
                return f"profile:{profile_id}"
            raise ValueError("legacy proxy profile not found")
        return normalize_proxy_node_url(url)

    def _effective_reference(
        self,
        reference: ProxyReference | None,
        snapshot: dict[str, Any],
    ) -> ProxyEffectiveReference:
        if reference is None:
            return ProxyEffectiveReference(
                source="disabled",
                label="未启用",
                configured=False,
                available=True,
                has_proxy=False,
            )
        if reference.mode == "direct":
            return ProxyEffectiveReference(
                source="direct",
                label="直连",
                configured=True,
                available=True,
                has_proxy=False,
            )
        if reference.mode == "group":
            group = next(
                (group for group in self._groups(snapshot) if group.id == reference.group_id),
                None,
            )
            available = bool(
                group
                and group.enabled
                and any(node.enabled and node.url for node in group.nodes)
            )
            return ProxyEffectiveReference(
                source="group",
                label=(group.name if group else f"代理组 {reference.group_id}（不存在）"),
                configured=True,
                available=available,
                has_proxy=available,
                group_id=reference.group_id,
            )

        raw = _clean_text(reference.url)
        if raw.lower().startswith("profile:"):
            profile_id = _clean_text(raw.split(":", 1)[1])
            profile = next(
                (
                    item for item in self._raw_dict_list(snapshot, "proxy_profiles")
                    if _clean_text(item.get("id")) == profile_id
                ),
                None,
            )
            available = bool(
                profile
                and profile.get("enabled") is not False
                and _clean_text(profile.get("proxy"))
            )
            return ProxyEffectiveReference(
                source="profile",
                label=(
                    _clean_text(profile.get("name")) or profile_id
                    if profile
                    else f"历史代理配置 {profile_id}（不存在）"
                ),
                configured=True,
                available=available,
                has_proxy=available,
            )
        return ProxyEffectiveReference(
            source="custom",
            label="自定义代理",
            configured=True,
            available=bool(raw),
            has_proxy=bool(raw),
        )

    @staticmethod
    def _revision(snapshot: dict[str, Any]) -> str:
        relevant = {
            "proxy": snapshot.get("proxy"),
            "fallback_proxy": snapshot.get("fallback_proxy"),
            "proxy_profiles": snapshot.get("proxy_profiles"),
            "proxy_groups": snapshot.get("proxy_groups"),
        }
        encoded = json.dumps(
            relevant,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]


proxy_management_service = ProxyManagementService()

from __future__ import annotations

import copy
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from pydantic import ValidationError

from contracts.proxy import ProxyGroupPatch, ProxyNodeInput, ProxyReference
from services.proxy_management_service import ProxyManagementService
from services.proxy_service import ProxySettingsStore


class _ConfigStore:
    def __init__(self, data: dict | None = None) -> None:
        self.data = copy.deepcopy(data or {})
        self._lock = threading.RLock()

    def get(self) -> dict:
        with self._lock:
            return copy.deepcopy(self.data)

    def update(self, values: dict) -> dict:
        with self._lock:
            self.data.update(copy.deepcopy(values))
            return copy.deepcopy(self.data)

    def get_proxy_settings(self) -> str:
        return str(self.data.get("proxy") or "")

    def get_proxy_runtime_settings(self) -> dict:
        value = self.data.get("proxy_runtime")
        return copy.deepcopy(value) if isinstance(value, dict) else {}


def _node(node_id: str = "node-a", **overrides) -> dict:
    return {
        "id": node_id,
        "name": node_id,
        "url": f"http://{node_id}.example.test:8080",
        "enabled": True,
        "image_concurrency_limit": 30,
        "notes": "",
        **overrides,
    }


def _group(group_id: str = "pool-a", **overrides) -> dict:
    return {
        "id": group_id,
        "name": group_id,
        "strategy": "time_window",
        "rotation_interval_minutes": 15,
        "enabled": True,
        "notes": "keep me",
        "nodes": [_node()],
        **overrides,
    }


def _test_result(*, ok: bool, latency_ms: int = 10) -> dict:
    return {
        "ok": ok,
        "status": 200 if ok else 0,
        "latency_ms": latency_ms,
        "error": None if ok else "failed",
        "proxy_source": "input",
        "has_proxy": True,
    }


class ProxyManagementContractTests(unittest.TestCase):
    def test_empty_default_is_direct_and_ignores_legacy_runtime_proxy(self) -> None:
        store = _ConfigStore({
            "proxy": "",
            "fallback_proxy": "",
            "proxy_runtime": {
                "enabled": True,
                "egress_mode": "single_proxy",
                "proxy_url": "http://runtime.example.test:8080",
            },
        })
        service = ProxyManagementService(store)

        view = service.view()

        self.assertEqual(view.default_reference.mode, "direct")
        self.assertIsNone(view.fallback_reference)
        self.assertEqual(view.effective_default.source, "direct")
        self.assertFalse(view.effective_default.has_proxy)

        mutation = service.save_defaults(view.default_reference, view.fallback_reference)
        self.assertEqual(store.data.get("proxy"), "direct")
        self.assertEqual(mutation.default_reference.mode, "direct")
        self.assertEqual(mutation.effective_default.source, "direct")

    def test_reference_projection_supports_direct_group_custom_and_legacy_profile(self) -> None:
        store = _ConfigStore({
            "proxy_groups": [_group("pool-a")],
            "proxy_profiles": [{
                "id": "legacy",
                "name": "Legacy",
                "proxy": "http://legacy.example.test:8080",
                "enabled": True,
            }],
        })
        service = ProxyManagementService(store)

        cases = [
            ("direct", "direct", "direct"),
            ("group:pool-a", "group", "group"),
            ("http://custom.example.test:8080", "custom", "custom"),
            ("profile:legacy", "custom", "profile"),
        ]
        for raw, configured_mode, effective_source in cases:
            with self.subTest(raw=raw):
                store.data["proxy"] = raw
                view = service.view()
                self.assertEqual(view.default_reference.mode, configured_mode)
                self.assertEqual(view.effective_default.source, effective_source)
                self.assertTrue(view.effective_default.available)

    def test_partial_group_update_preserves_strategy_rotation_nodes_and_notes(self) -> None:
        store = _ConfigStore({"proxy_groups": [_group()]})
        service = ProxyManagementService(store)

        mutation = service.save_group(ProxyGroupPatch(id="pool-a", enabled=False))

        self.assertFalse(mutation.group.enabled)
        self.assertEqual(mutation.group.strategy, "time_window")
        self.assertEqual(mutation.group.rotation_interval_minutes, 15)
        self.assertEqual(mutation.group.notes, "keep me")
        self.assertEqual([node.id for node in mutation.group.nodes], ["node-a"])
        stored = store.data["proxy_groups"][0]
        self.assertEqual(stored["strategy"], "time_window")
        self.assertEqual(stored["rotation_interval_minutes"], 15)

    def test_group_write_normalizes_ranges_and_returns_unknown_health(self) -> None:
        service = ProxyManagementService(_ConfigStore())

        mutation = service.save_group(ProxyGroupPatch(
            id="Pool.One",
            name="Pool One",
            nodes=[ProxyNodeInput(
                id="Node.One",
                name="Node One",
                url="http://node.example.test:8080",
                image_concurrency_limit=20000,
            )],
            create_only=True,
        ))

        self.assertEqual(mutation.group.id, "poolone")
        self.assertEqual(mutation.group.nodes[0].id, "nodeone")
        self.assertEqual(mutation.group.nodes[0].image_concurrency_limit, 10000)
        self.assertEqual(mutation.group.health.state, "unknown")
        self.assertEqual(mutation.group.nodes[0].health.state, "unknown")
        self.assertEqual(mutation.group.reference_text, "group:poolone")

    def test_existing_group_and_node_ids_remain_runtime_exact(self) -> None:
        store = _ConfigStore({
            "proxy": "group:Pool.One",
            "proxy_groups": [_group(
                "Pool.One",
                nodes=[_node("Node.One", image_concurrency_limit=None, max_image_concurrency=7)],
            )],
        })
        service = ProxyManagementService(store)

        view = service.view()
        updated = service.save_group(ProxyGroupPatch(id="Pool.One", enabled=False))
        defaults = service.save_defaults(view.default_reference, None)

        self.assertEqual(view.groups[0].id, "Pool.One")
        self.assertEqual(view.groups[0].nodes[0].id, "Node.One")
        self.assertEqual(view.groups[0].nodes[0].image_concurrency_limit, 7)
        self.assertEqual(updated.group.id, "Pool.One")
        self.assertEqual(store.data["proxy_groups"][0]["id"], "Pool.One")
        self.assertEqual(store.data["proxy_groups"][0]["nodes"][0]["id"], "Node.One")
        self.assertEqual(store.data["proxy_groups"][0]["nodes"][0]["max_image_concurrency"], 7)
        self.assertEqual(defaults.default_reference.group_id, "Pool.One")
        self.assertEqual(store.data["proxy"], "group:Pool.One")

    def test_full_node_update_preserves_legacy_concurrency_value(self) -> None:
        store = _ConfigStore({
            "proxy_groups": [_group(
                "Pool.One",
                nodes=[_node("Node.One", image_concurrency_limit=None, max_image_concurrency=7)],
            )],
        })
        service = ProxyManagementService(store)

        updated = service.save_group(ProxyGroupPatch(
            id="Pool.One",
            nodes=[ProxyNodeInput(
                id="Node.One",
                name="Updated Node",
                url="http://updated.example.test:8080",
            )],
        ))

        self.assertEqual(updated.group.nodes[0].image_concurrency_limit, 7)
        self.assertEqual(
            store.data["proxy_groups"][0]["nodes"][0]["image_concurrency_limit"],
            7,
        )

    def test_create_rejects_canonical_group_id_collision(self) -> None:
        store = _ConfigStore({"proxy_groups": [_group("poolone")]})
        service = ProxyManagementService(store)

        with self.assertRaisesRegex(ValueError, "proxy group already exists"):
            service.save_group(ProxyGroupPatch(
                id="Pool.One",
                nodes=[ProxyNodeInput(url="http://new.example.test:8080")],
                create_only=True,
            ))

        self.assertEqual([group["id"] for group in store.data["proxy_groups"]], ["poolone"])

    def test_delete_uses_exact_stored_id_without_canonical_collision(self) -> None:
        store = _ConfigStore({
            "proxy_groups": [_group("Pool.One"), _group("poolone")],
        })
        service = ProxyManagementService(store)

        deleted = service.delete_group("Pool.One")

        self.assertEqual(deleted.deleted_id, "Pool.One")
        self.assertEqual([group["id"] for group in store.data["proxy_groups"]], ["poolone"])

    def test_reference_contract_rejects_ambiguous_fields(self) -> None:
        invalid_references = [
            {"mode": "direct", "url": "http://proxy.example.test:8080"},
            {"mode": "group", "group_id": ""},
            {"mode": "group", "group_id": "pool-a", "url": "http://proxy.example.test:8080"},
            {"mode": "custom", "url": "direct"},
            {"mode": "custom", "url": "group:pool-a"},
        ]
        for payload in invalid_references:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                ProxyReference.model_validate(payload)

    def test_group_mutations_return_only_affected_identity_and_revision(self) -> None:
        store = _ConfigStore({"proxy_groups": [_group()]})
        service = ProxyManagementService(store)

        saved = service.save_group(ProxyGroupPatch(id="pool-a", name="Updated"))
        deleted = service.delete_group("pool-a")

        self.assertEqual(saved.group.name, "Updated")
        self.assertTrue(saved.revision)
        self.assertEqual(deleted.deleted_id, "pool-a")
        self.assertTrue(deleted.revision)
        self.assertEqual(store.data["proxy_groups"], [])

    def test_concurrent_group_creates_do_not_overwrite_each_other(self) -> None:
        store = _ConfigStore()
        service = ProxyManagementService(store)

        def create(group_id: str) -> None:
            service.save_group(ProxyGroupPatch(
                id=group_id,
                nodes=[ProxyNodeInput(
                    id=f"{group_id}-node",
                    url=f"http://{group_id}.example.test:8080",
                )],
                create_only=True,
            ))

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(create, ["pool-a", "pool-b"]))

        self.assertEqual(
            {group["id"] for group in store.data["proxy_groups"]},
            {"pool-a", "pool-b"},
        )

    def test_group_test_summary_covers_success_partial_and_failure(self) -> None:
        success = ProxyManagementService.group_test_response([
            ("a", _test_result(ok=True, latency_ms=10)),
            ("b", _test_result(ok=True, latency_ms=20)),
        ])
        partial = ProxyManagementService.group_test_response([
            ("a", _test_result(ok=True, latency_ms=10)),
            ("b", _test_result(ok=False, latency_ms=30)),
        ])
        failed = ProxyManagementService.group_test_response([
            ("a", _test_result(ok=False, latency_ms=40)),
        ])

        self.assertEqual(success.summary.status, "success")
        self.assertEqual(success.summary.tone, "success")
        self.assertEqual(success.summary.max_latency_ms, 20)
        self.assertEqual(partial.summary.status, "partial")
        self.assertEqual(partial.summary.tone, "warning")
        self.assertEqual(partial.summary.succeeded, 1)
        self.assertEqual(partial.summary.failed, 1)
        self.assertEqual(failed.summary.status, "failed")
        self.assertEqual(failed.summary.tone, "danger")
        self.assertIsNotNone(failed.result)

    def test_legacy_runtime_proxy_cannot_supply_default_egress(self) -> None:
        store = _ConfigStore({
            "proxy": "",
            "proxy_runtime": {
                "enabled": True,
                "egress_mode": "single_proxy",
                "proxy_url": "http://runtime.example.test:8080",
            },
        })
        runtime = ProxySettingsStore(store)

        empty_default = runtime.get_profile(upstream=True)
        store.data["proxy"] = "direct"
        direct = runtime.get_profile(upstream=True)

        self.assertEqual(empty_default.proxy_url, "")
        self.assertEqual(empty_default.proxy_source, "direct")
        self.assertEqual(direct.proxy_url, "")
        self.assertEqual(direct.proxy_source, "default_direct")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from copy import deepcopy
import unittest

from pydantic import ValidationError

from contracts.proxy import ProxyGroupPatch, ProxyNodeInput, ProxyReference
from services.proxy_management_service import (
    ProxyManagementService,
    normalize_proxy_node_url,
    project_proxy_assignment,
    proxy_node_url_error,
)
from services.proxy_service import (
    ProxyReferenceUnavailableError,
    ProxySettingsStore,
    proxy_node_image_concurrency_limit,
)


class _MemoryConfig:
    def __init__(self) -> None:
        self.data: dict[str, object] = {"proxy_groups": []}
        self.update_count = 0

    def get(self) -> dict[str, object]:
        return deepcopy(self.data)

    def update(self, values: dict[str, object]) -> dict[str, object]:
        self.update_count += 1
        self.data.update(deepcopy(values))
        return self.get()

    def get_proxy_settings(self) -> str:
        return str(self.data.get("proxy") or "").strip()

    def get_proxy_fallback_settings(self) -> str:
        return str(self.data.get("fallback_proxy") or "").strip()

    def get_proxy_runtime_settings(self) -> dict[str, object]:
        value = self.data.get("proxy_runtime")
        return deepcopy(value) if isinstance(value, dict) else {}


class ProxyAssignmentProjectionTests(unittest.TestCase):
    def test_projection_centralizes_modes_labels_and_legacy_group_fallback(self) -> None:
        cases = (
            ("", "", "inherit", "", "使用默认出口"),
            ("direct", "legacy", "direct", "", "强制直连"),
            ("group:primary", "legacy", "group", "primary", "代理组：主出口"),
            ("", "legacy", "group", "legacy", "代理组：旧出口"),
            ("profile:old", "", "profile", "", "历史代理：old"),
        )
        names = {"primary": "主出口", "legacy": "旧出口"}
        for value, legacy_group_id, mode, group_id, label in cases:
            with self.subTest(value=value, legacy_group_id=legacy_group_id):
                projection = project_proxy_assignment(
                    value,
                    legacy_group_id=legacy_group_id,
                    group_names=names,
                )
                self.assertEqual(projection.mode, mode)
                self.assertEqual(projection.group_id, group_id)
                self.assertEqual(projection.label, label)

    def test_custom_projection_does_not_expose_proxy_credentials(self) -> None:
        projection = project_proxy_assignment(
            "http://proxy-user:proxy-password@[2001:db8::1]:8080"
        )

        self.assertEqual(projection.mode, "custom")
        self.assertEqual(projection.label, "http://[2001:db8::1]:8080")
        self.assertNotIn("proxy-user", projection.label)
        self.assertNotIn("proxy-password", projection.label)

class ProxyManagementServiceTests(unittest.TestCase):
    def test_account_provider_can_be_bound_after_construction_once(self) -> None:
        store = _MemoryConfig()
        store.data.update({
            "proxy_groups": [
                {"id": "used", "nodes": [{"url": "http://proxy.example"}]},
            ],
        })
        service = ProxyManagementService(store)
        service.bind_account_provider(
            lambda: [{"id": "account-1", "proxy": "group:used"}],
        )

        group = service.list_groups().groups[0]
        self.assertFalse(group.can_delete)
        self.assertEqual(group.references, ["账号 account-1"])
        with self.assertRaisesRegex(RuntimeError, "already bound"):
            service.bind_account_provider(lambda: ())

    def test_empty_and_legacy_global_defaults_project_as_direct(self) -> None:
        for stored_value in (None, "", "global"):
            with self.subTest(stored_value=stored_value):
                store = _MemoryConfig()
                if stored_value is not None:
                    store.data["proxy"] = stored_value
                view = ProxyManagementService(store).view()
                self.assertEqual(view.default_reference.mode, "direct")
                self.assertEqual(view.effective_default.source, "direct")
                self.assertFalse(view.effective_default.has_proxy)

    def test_default_reference_rejects_removed_inherit_mode(self) -> None:
        with self.assertRaises(ValidationError):
            ProxyReference(mode="inherit")  # type: ignore[arg-type]

    def test_saving_direct_default_persists_an_explicit_direct_reference(self) -> None:
        store = _MemoryConfig()
        response = ProxyManagementService(store).save_defaults(
            ProxyReference(mode="direct"),
            None,
        )
        self.assertEqual(store.data["proxy"], "direct")
        self.assertEqual(response.default_reference.mode, "direct")

    def test_legacy_runtime_proxy_cannot_supply_default_egress(self) -> None:
        store = _MemoryConfig()
        store.data.update({
            "proxy": "",
            "proxy_runtime": {
                "enabled": True,
                "egress_mode": "single_proxy",
                "proxy_url": "http://legacy-runtime.example:8080",
            },
        })

        profile = ProxySettingsStore(store).get_profile(upstream=True)

        self.assertEqual(profile.proxy_source, "direct")
        self.assertEqual(profile.proxy_url, "")

    def test_resource_proxy_is_used_only_for_explicit_resource_requests(self) -> None:
        store = _MemoryConfig()
        store.data.update({
            "proxy": "direct",
            "proxy_runtime": {
                "enabled": True,
                "resource_proxy_url": "http://resources.example:8080",
            },
        })
        proxy_store = ProxySettingsStore(store)

        normal = proxy_store.get_profile(upstream=True)
        resource = proxy_store.get_profile(upstream=True, resource=True)

        self.assertEqual(normal.proxy_source, "default_direct")
        self.assertEqual(normal.proxy_url, "")
        self.assertEqual(resource.proxy_source, "resource")
        self.assertEqual(resource.proxy_url, "http://resources.example:8080")

    def test_account_reference_to_missing_proxy_group_fails_closed(self) -> None:
        store = _MemoryConfig()
        proxy_store = ProxySettingsStore(store)

        with self.assertRaisesRegex(
            ProxyReferenceUnavailableError,
            "proxy group is unavailable: missing",
        ):
            proxy_store.get_profile(
                account={"proxy": "group:missing"},
                upstream=True,
            )

    def test_unavailable_proxy_groups_fail_closed_for_account_group_routing(self) -> None:
        unavailable_groups = (
            {"id": "target", "enabled": False, "nodes": [{"url": "http://proxy.example"}]},
            {"id": "target", "enabled": True, "nodes": []},
            {
                "id": "target",
                "enabled": True,
                "nodes": [{"url": "http://proxy.example", "enabled": False}],
            },
        )
        for group in unavailable_groups:
            with self.subTest(group=group):
                store = _MemoryConfig()
                store.data.update({
                    "proxy": "http://default.example:8080",
                    "proxy_groups": [group],
                    "account_groups": [
                        {"id": "writers", "proxy": "group:target", "enabled": True}
                    ],
                })

                with self.assertRaisesRegex(
                    ProxyReferenceUnavailableError,
                    "proxy group is unavailable: target",
                ):
                    ProxySettingsStore(store).get_profile(
                        account={"group_id": "writers"},
                        upstream=True,
                    )

    def test_direct_and_global_account_references_keep_their_routing_semantics(self) -> None:
        store = _MemoryConfig()
        store.data.update({
            "proxy": "http://default.example:8080",
            "account_groups": [
                {"id": "direct", "proxy": "direct", "enabled": True},
                {"id": "inherited", "proxy": "global", "enabled": True},
            ],
        })
        proxy_store = ProxySettingsStore(store)

        account_direct = proxy_store.get_profile(
            account={"proxy": "direct"},
            upstream=True,
        )
        account_inherited = proxy_store.get_profile(
            account={"proxy": "global"},
            upstream=True,
        )
        group_direct = proxy_store.get_profile(
            account={"group_id": "direct"},
            upstream=True,
        )
        group_inherited = proxy_store.get_profile(
            account={"group_id": "inherited"},
            upstream=True,
        )

        self.assertEqual((account_direct.proxy_source, account_direct.proxy_url), ("account_direct", ""))
        self.assertEqual((group_direct.proxy_source, group_direct.proxy_url), ("account_group_direct", ""))
        self.assertEqual(account_inherited.proxy_url, "http://default.example:8080")
        self.assertEqual(group_inherited.proxy_url, "http://default.example:8080")

    def test_unknown_proxy_group_cannot_be_assigned(self) -> None:
        service = ProxyManagementService(_MemoryConfig())

        with self.assertRaisesRegex(ValueError, "proxy group not found"):
            service.normalize_assignment_reference("group:missing")

    def test_explicit_global_assignment_ignores_stale_legacy_group_id(self) -> None:
        service = ProxyManagementService(_MemoryConfig())

        self.assertEqual(
            service.normalize_assignment_reference(
                "global",
                legacy_group_id="removed-group",
            ),
            "",
        )

    def test_supported_assignment_references_are_normalized(self) -> None:
        store = _MemoryConfig()
        store.data["proxy_groups"] = [
            {
                "id": "target",
                "enabled": True,
                "nodes": [{"url": "http://proxy.example:8080"}],
            }
        ]
        service = ProxyManagementService(store)

        self.assertEqual(service.normalize_assignment_reference("direct"), "direct")
        self.assertEqual(service.normalize_assignment_reference("global"), "")
        self.assertEqual(
            service.normalize_assignment_reference("", legacy_group_id="target"),
            "group:target",
        )
        self.assertEqual(
            service.normalize_assignment_reference("socks5://Proxy.Example:1080/"),
            "socks5h://proxy.example:1080",
        )

    def test_unavailable_proxy_group_cannot_be_assigned(self) -> None:
        unavailable_groups = (
            {"id": "target", "enabled": False, "nodes": [{"url": "http://proxy.example"}]},
            {"id": "target", "enabled": True, "nodes": []},
            {
                "id": "target",
                "enabled": True,
                "nodes": [{"url": "http://proxy.example", "enabled": False}],
            },
        )
        for group in unavailable_groups:
            with self.subTest(group=group):
                store = _MemoryConfig()
                store.data["proxy_groups"] = [group]

                with self.assertRaisesRegex(ValueError, "proxy group is unavailable"):
                    ProxyManagementService(store).normalize_assignment_reference(
                        "group:target"
                    )

    def test_proxy_node_image_concurrency_uses_one_compatibility_rule(self) -> None:
        self.assertEqual(proxy_node_image_concurrency_limit({}), 30)
        self.assertEqual(
            proxy_node_image_concurrency_limit({"image_concurrency_limit": 0}),
            0,
        )
        self.assertEqual(
            proxy_node_image_concurrency_limit({"image_concurrency": "12.9"}),
            12,
        )
        self.assertEqual(
            proxy_node_image_concurrency_limit({"max_image_concurrency": 20000}),
            10000,
        )
        self.assertEqual(
            proxy_node_image_concurrency_limit(
                {"name": "unchanged"},
                fallback={"image_concurrency_limit": 7},
            ),
            7,
        )

    def test_save_group_accepts_supported_proxy_urls_with_authentication(self) -> None:
        store = _MemoryConfig()
        service = ProxyManagementService(store)

        response = service.save_group(ProxyGroupPatch(
            id="imported",
            name="Imported",
            create_only=True,
            nodes=[
                ProxyNodeInput(id="http", url="http://user:password@proxy.example:8080"),
                ProxyNodeInput(id="https", url="https://proxy.example:8443"),
                ProxyNodeInput(id="socks", url="socks5://proxy.example:1080"),
                ProxyNodeInput(id="socks-auth", url="socks5h://user:password@proxy.example:1081"),
            ],
        ))

        self.assertEqual(store.update_count, 1)
        self.assertEqual(
            [node.url for node in response.group.nodes],
            [
                "http://user:password@proxy.example:8080",
                "https://proxy.example:8443",
                "socks5h://proxy.example:1080",
                "socks5h://user:password@proxy.example:1081",
            ],
        )

    def test_save_group_rejects_invalid_proxy_url_before_writing(self) -> None:
        invalid_urls = (
            "ftp://proxy.example:21",
            "proxy.example:8080",
            "http://proxy example:8080",
            "http://proxy.example:99999",
            "http://proxy.example:0",
            "http://proxy.example:",
            "https://proxy.example:/",
            "http://proxy.example:8080/path",
            "http://proxy.example:8080?mode=test",
        )

        for url in invalid_urls:
            with self.subTest(url=url):
                store = _MemoryConfig()
                service = ProxyManagementService(store)
                with self.assertRaisesRegex(ValueError, "proxy node url"):
                    service.save_group(ProxyGroupPatch(
                        id="invalid",
                        name="Invalid",
                        create_only=True,
                        nodes=[ProxyNodeInput(id="node", url=url)],
                    ))
                self.assertEqual(store.update_count, 0)

    def test_proxy_url_error_allows_normalized_socks5h_url(self) -> None:
        self.assertEqual(proxy_node_url_error("socks5h://proxy.example:1080"), "")

    def test_normalize_proxy_url_canonicalizes_scheme_host_default_port_and_root_path(self) -> None:
        self.assertEqual(
            normalize_proxy_node_url("HTTP://User:Pass@Example.COM:80/"),
            "http://User:Pass@example.com",
        )
        self.assertEqual(
            normalize_proxy_node_url("socks5://Proxy.Example:1080/"),
            "socks5h://proxy.example:1080",
        )
        self.assertEqual(
            normalize_proxy_node_url("http://例子.测试:8080"),
            "http://xn--fsqu00a.xn--0zwm56d:8080",
        )

    def test_import_nodes_uses_backend_canonicalization_defaults_and_duplicate_rules(self) -> None:
        service = ProxyManagementService(_MemoryConfig())

        result = service.import_nodes(
            "\n".join((
                "http://例子.测试:80 12",
                "http://xn--fsqu00a.xn--0zwm56d/ 25",
                "socks5://proxy.example:1080",
                "socks5h://existing.example:1080/ 0",
                "https://zero.example:443 0",
                "http://limit.example:8080 10001",
                "ftp://proxy.example:21",
            )),
            ["socks5://existing.example:1080"],
        )

        self.assertEqual(result.added_count, 3)
        self.assertEqual(result.duplicate_count, 2)
        self.assertEqual(result.invalid_count, 2)
        self.assertEqual(
            [(node.url, node.image_concurrency_limit) for node in result.nodes],
            [
                ("http://xn--fsqu00a.xn--0zwm56d", 12),
                ("socks5h://proxy.example:1080", 30),
                ("https://zero.example", 0),
            ],
        )
        self.assertEqual([item.line for item in result.invalid_items], [6, 7])
        self.assertEqual(
            [item.raw for item in result.invalid_items],
            ["http://limit.example:8080 10001", "ftp://proxy.example:21"],
        )

    def test_import_nodes_rejects_more_than_ten_thousand_non_empty_rows(self) -> None:
        service = ProxyManagementService(_MemoryConfig())

        with self.assertRaisesRegex(ValueError, "10000"):
            service.import_nodes(
                "\n".join(
                    f"http://proxy-{index}.example:8080"
                    for index in range(10_001)
                )
            )

    def test_delete_unreferenced_group_writes_once(self) -> None:
        store = _MemoryConfig()
        store.data = {
            "proxy_groups": [{"id": "unused", "nodes": [{"url": "http://proxy.example"}]}],
            "account_groups": [],
        }
        service = ProxyManagementService(store)

        response = service.delete_group("unused")

        self.assertEqual(response.deleted_id, "unused")
        self.assertEqual(store.update_count, 1)
        self.assertEqual(store.data["proxy_groups"], [])

    def test_delete_referenced_group_is_rejected_without_writing(self) -> None:
        references = (
            ({"proxy": "group:used"}, []),
            ({"fallback_proxy": "group:used"}, []),
            ({"account_groups": [{"id": "writers", "proxy": "group:used"}]}, []),
            ({}, [{"id": "account-1", "proxy": "group:used"}]),
            ({}, [{"id": "account-1", "proxy_group_id": "used"}]),
        )
        for config_values, accounts in references:
            with self.subTest(config_values=config_values, accounts=accounts):
                store = _MemoryConfig()
                store.data = {
                    "proxy_groups": [{"id": "used", "nodes": [{"url": "http://proxy.example"}]}],
                    "account_groups": [],
                    **config_values,
                }
                service = ProxyManagementService(
                    store,
                    account_provider=lambda: deepcopy(accounts),
                )

                with self.assertRaisesRegex(ValueError, "proxy group is in use"):
                    service.delete_group("used")

                self.assertEqual(store.update_count, 0)
                self.assertEqual(len(store.data["proxy_groups"]), 1)

    def test_group_projection_reports_delete_capability_and_references(self) -> None:
        store = _MemoryConfig()
        store.data = {
            "proxy": "group:used",
            "proxy_groups": [
                {"id": "used", "name": "Used", "nodes": [{"url": "http://proxy.example"}]},
                {"id": "unused", "name": "Unused", "nodes": [{"url": "http://unused.example"}]},
            ],
            "account_groups": [{"id": "writers", "proxy": "group:used"}],
        }
        service = ProxyManagementService(
            store,
            account_provider=lambda: [{"id": "account-1", "proxy": "group:used"}],
        )

        groups = {group.id: group for group in service.list_groups().groups}

        self.assertFalse(groups["used"].can_delete)
        self.assertEqual(
            groups["used"].references,
            ["默认出口", "账号组 writers", "账号 account-1"],
        )
        self.assertTrue(groups["unused"].can_delete)
        self.assertEqual(groups["unused"].references, [])

    def test_group_test_summary_owns_the_user_facing_result(self) -> None:
        response = ProxyManagementService.group_test_response([
            ("healthy", {"ok": True, "status": 200, "latency_ms": 80, "has_proxy": True}),
            ("failed", {"ok": False, "status": 502, "latency_ms": 120, "error": "timeout", "has_proxy": True}),
        ])

        self.assertEqual(response.summary.status, "partial")
        self.assertEqual(response.summary.label, "代理组部分可用")
        self.assertEqual(response.summary.message, "2 个节点中 1 个可用，1 个失败")

    def test_explicit_proxy_reference_overrides_stale_legacy_group_id(self) -> None:
        for proxy in (
            "direct",
            "global",
            "http://custom.example:8080",
            "group:other",
        ):
            for owner in ("account_group", "account"):
                with self.subTest(proxy=proxy, owner=owner):
                    item = {
                        "id": "owner-one",
                        "proxy": proxy,
                        "proxy_group_id": "used",
                    }
                    store = _MemoryConfig()
                    store.data = {
                        "proxy_groups": [
                            {"id": "used", "nodes": [{"url": "http://proxy.example"}]},
                            {"id": "other", "nodes": [{"url": "http://other.example"}]},
                        ],
                        "account_groups": [item] if owner == "account_group" else [],
                    }
                    service = ProxyManagementService(
                        store,
                        account_provider=(
                            (lambda: [deepcopy(item)])
                            if owner == "account"
                            else (lambda: [])
                        ),
                    )

                    response = service.delete_group("used")

                    self.assertEqual(response.deleted_id, "used")
                    self.assertEqual(
                        [group["id"] for group in store.data["proxy_groups"]],
                        ["other"],
                    )

    def test_save_group_rejects_equivalent_duplicate_proxy_urls(self) -> None:
        equivalents = (
            ("socks5://proxy.example:1080", "socks5h://proxy.example:1080/"),
            ("http://proxy.example:8080", "http://proxy.example:8080/"),
            ("http://proxy.example:80", "http://proxy.example/"),
        )

        for first, second in equivalents:
            with self.subTest(first=first, second=second):
                store = _MemoryConfig()
                service = ProxyManagementService(store)
                with self.assertRaisesRegex(ValueError, "duplicate proxy node url"):
                    service.save_group(ProxyGroupPatch(
                        id="duplicates",
                        name="Duplicates",
                        create_only=True,
                        nodes=[
                            ProxyNodeInput(id="first", url=first),
                            ProxyNodeInput(id="second", url=second),
                        ],
                    ))
                self.assertEqual(store.update_count, 0)

    def test_save_defaults_validates_and_normalizes_custom_urls(self) -> None:
        store = _MemoryConfig()
        service = ProxyManagementService(store)

        response = service.save_defaults(
            ProxyReference(mode="custom", url="socks5://Proxy.Example:1080/"),
            ProxyReference(mode="custom", url="HTTPS://Fallback.Example:443/"),
        )

        self.assertEqual(store.data["proxy"], "socks5h://proxy.example:1080")
        self.assertEqual(store.data["fallback_proxy"], "https://fallback.example")
        self.assertEqual(response.default_reference.url, "socks5h://proxy.example:1080")

        with self.assertRaisesRegex(ValueError, "unsupported scheme"):
            service.save_defaults(
                ProxyReference(mode="custom", url="ftp://proxy.example:21"),
                None,
            )

    def test_save_defaults_preserves_existing_legacy_profile_reference(self) -> None:
        store = _MemoryConfig()
        store.data.update({
            "proxy": "profile:legacy",
            "proxy_profiles": [],
        })
        service = ProxyManagementService(store)
        view = service.view()

        response = service.save_defaults(
            view.default_reference,
            view.fallback_reference,
        )

        self.assertEqual(store.data["proxy"], "profile:legacy")
        self.assertEqual(response.default_reference.url, "profile:legacy")

    def test_save_defaults_accepts_existing_legacy_profile(self) -> None:
        store = _MemoryConfig()
        store.data["proxy_profiles"] = [{"id": "configured"}]
        service = ProxyManagementService(store)

        response = service.save_defaults(
            ProxyReference(mode="custom", url="profile:configured"),
            None,
        )

        self.assertEqual(store.data["proxy"], "profile:configured")
        self.assertEqual(response.default_reference.url, "profile:configured")

    def test_save_defaults_rejects_unknown_injected_legacy_profile_reference(self) -> None:
        store = _MemoryConfig()
        service = ProxyManagementService(store)

        with self.assertRaisesRegex(ValueError, "legacy proxy profile not found"):
            service.save_defaults(
                ProxyReference(mode="custom", url="profile:unknown"),
                None,
            )


if __name__ == "__main__":
    unittest.main()

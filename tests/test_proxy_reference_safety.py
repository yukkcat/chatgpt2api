from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from threading import Event, Thread
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI

from api import accounts
from services.account_service import AccountService
from services.proxy_management_service import (
    ProxyGroupInUseError,
    ProxyManagementService,
)
from tests.support.account_repository import TestAccountRepository


class _MemoryConfig:
    def __init__(self, data: dict[str, object] | None = None) -> None:
        self.data = deepcopy(data or {"proxy_groups": [], "account_groups": []})
        self.update_count = 0

    def get(self) -> dict[str, object]:
        return deepcopy(self.data)

    def update(self, values: dict[str, object]) -> dict[str, object]:
        self.update_count += 1
        self.data.update(deepcopy(values))
        return self.get()


class _MutationBoundaryProbe:
    def __init__(self) -> None:
        self.active = False
        self.calls: list[list[tuple[object, object]]] = []

    def run(self, references, mutation):  # type: ignore[no-untyped-def]
        requested = list(references)
        self.calls.append(requested)
        normalized = []
        for value, legacy_group_id in requested:
            raw = str(value or "").strip()
            if raw.lower() == "global":
                normalized.append("")
            elif raw:
                normalized.append(raw)
            else:
                legacy = str(legacy_group_id or "").strip()
                normalized.append(f"group:{legacy}" if legacy else "")
        self.active = True
        try:
            return mutation(normalized)
        finally:
            self.active = False


class _BoundaryCheckingTestAccountRepository(TestAccountRepository):
    def __init__(self, file_path: Path, auth_keys_path: Path, probe: _MutationBoundaryProbe):
        super().__init__(file_path, auth_keys_path)
        self.probe = probe
        self.require_boundary = False

    def mutate_accounts(self, mutation):  # type: ignore[no-untyped-def]
        if self.require_boundary and not self.probe.active:
            raise AssertionError("account persistence escaped proxy assignment boundary")
        return super().mutate_accounts(mutation)


class _BlockingMutationTestAccountRepository(TestAccountRepository):
    def __init__(self, file_path: Path, auth_keys_path: Path):
        super().__init__(file_path, auth_keys_path)
        self.block_next_mutation = False
        self.mutation_entered = Event()
        self.allow_mutation = Event()

    def mutate_accounts(self, mutation):  # type: ignore[no-untyped-def]
        if self.block_next_mutation:
            self.block_next_mutation = False
            self.mutation_entered.set()
            if not self.allow_mutation.wait(timeout=5):
                raise TimeoutError("account storage test barrier timed out")
        return super().mutate_accounts(mutation)


class _BoundaryAwareConfig(_MemoryConfig):
    def __init__(self, data: dict[str, object] | None = None) -> None:
        super().__init__(data)
        self.boundary_active = lambda: False
        self.require_boundary = False

    def update(self, values: dict[str, object]) -> dict[str, object]:
        if self.require_boundary and not self.boundary_active():
            raise AssertionError("account-group persistence escaped proxy assignment boundary")
        return super().update(values)


class _BoundaryTrackingProxyManagementService(ProxyManagementService):
    def __init__(self, config_store) -> None:  # type: ignore[no-untyped-def]
        super().__init__(config_store)
        self.callback_active = False

    def mutate_assignment_references(self, references, mutation):  # type: ignore[no-untyped-def]
        def tracked(normalized):  # type: ignore[no-untyped-def]
            self.callback_active = True
            try:
                return mutation(normalized)
            finally:
                self.callback_active = False

        return super().mutate_assignment_references(references, tracked)


class ProxyReferenceSafetyHttpTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _app() -> FastAPI:
        app = FastAPI()
        app.include_router(accounts.create_router())
        return app

    async def test_account_group_rejects_unknown_proxy_group_without_writing(self) -> None:
        store = _MemoryConfig()
        proxy_management = ProxyManagementService(store)
        transport = httpx.ASGITransport(app=self._app())

        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts.config", store),
            patch("api.accounts.proxy_management_service", proxy_management),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/account-groups",
                    json={
                        "id": "writers",
                        "name": "Writers",
                        "proxy": "group:missing",
                    },
                )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["detail"]["error"], "proxy group not found")
        self.assertEqual(store.update_count, 0)

    async def test_account_rejects_unknown_proxy_group_without_updating(self) -> None:
        store = _MemoryConfig()
        transport = httpx.ASGITransport(app=self._app())
        mutation = ProxyManagementService(store).mutate_assignment_references
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            account_service = AccountService(
                TestAccountRepository(root / "accounts.json", root / "auth-keys.json"),
                proxy_reference_mutation=mutation,
            )
            account_service.add_accounts(["token-one"], return_items=False)
            account_id = account_service.list_accounts()[0]["management_id"]

            with (
                patch("api.accounts.require_admin"),
                patch("api.accounts.config", store),
                patch("api.accounts.account_service", account_service),
            ):
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.post(
                        "/api/accounts/update",
                        json={"id": account_id, "proxy": "group:missing"},
                    )

            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(response.json()["detail"]["error"], "proxy group not found")
            self.assertEqual(account_service.get_account("token-one")["proxy"], "")

    async def test_account_import_reports_unknown_proxy_group_as_bad_request(self) -> None:
        store = _MemoryConfig()
        transport = httpx.ASGITransport(app=self._app())
        mutation = ProxyManagementService(store).mutate_assignment_references
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            account_service = AccountService(
                TestAccountRepository(root / "accounts.json", root / "auth-keys.json"),
                proxy_reference_mutation=mutation,
            )

            with (
                patch("api.accounts.require_admin"),
                patch("api.accounts.account_service", account_service),
            ):
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.post(
                        "/api/accounts",
                        json={
                            "accounts": [
                                {
                                    "access_token": "token-one",
                                    "proxy": "group:missing",
                                }
                            ],
                            "sync_after_import": False,
                        },
                    )

            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(response.json()["detail"]["error"], "proxy group not found")
            self.assertEqual(account_service.list_accounts(), [])

    async def test_account_group_save_persists_inside_proxy_assignment_boundary(self) -> None:
        store = _BoundaryAwareConfig({
            "proxy_groups": [
                {"id": "target", "nodes": [{"url": "http://proxy.example"}]}
            ],
            "account_groups": [],
        })
        proxy_management = _BoundaryTrackingProxyManagementService(store)
        store.boundary_active = lambda: proxy_management.callback_active
        store.require_boundary = True
        transport = httpx.ASGITransport(app=self._app())

        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts.config", store),
            patch("api.accounts.proxy_management_service", proxy_management),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/account-groups",
                    json={
                        "id": "writers",
                        "name": "Writers",
                        "proxy": "group:target",
                    },
                )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(store.data["account_groups"][0]["proxy"], "group:target")


class ProxyReferenceSafetyMutationTests(unittest.TestCase):
    def test_proxy_assignment_boundary_blocks_group_deletion_until_save_finishes(self) -> None:
        store = _MemoryConfig({
            "proxy_groups": [
                {"id": "target", "nodes": [{"url": "http://proxy.example"}]}
            ],
            "account_groups": [],
        })
        persisted_accounts: list[dict[str, object]] = []
        service = ProxyManagementService(
            store,
            account_provider=lambda: deepcopy(persisted_accounts),
        )
        mutation_entered = Event()
        allow_save = Event()
        mutation_finished = Event()
        deletion_finished = Event()
        errors: dict[str, BaseException] = {}

        def persist(normalized: list[str]) -> None:
            mutation_entered.set()
            if not allow_save.wait(timeout=5):
                raise TimeoutError("proxy assignment test barrier timed out")
            persisted_accounts.append({"id": "account-one", "proxy": normalized[0]})

        def assign() -> None:
            try:
                service.mutate_assignment_references(
                    [("group:target", "")],
                    persist,
                )
            except BaseException as exc:  # pragma: no cover - asserted below
                errors["assign"] = exc
            finally:
                mutation_finished.set()

        def delete() -> None:
            try:
                service.delete_group("target")
            except BaseException as exc:  # pragma: no cover - asserted below
                errors["delete"] = exc
            finally:
                deletion_finished.set()

        assignment_thread = Thread(target=assign)
        assignment_thread.start()
        self.assertTrue(mutation_entered.wait(timeout=5))

        deletion_thread = Thread(target=delete)
        deletion_thread.start()
        self.assertFalse(deletion_finished.wait(timeout=0.1))

        allow_save.set()
        assignment_thread.join(timeout=5)
        deletion_thread.join(timeout=5)

        self.assertTrue(mutation_finished.is_set())
        self.assertTrue(deletion_finished.is_set())
        self.assertNotIn("assign", errors)
        self.assertIsInstance(errors.get("delete"), ProxyGroupInUseError)
        self.assertEqual(store.update_count, 0)

    def test_account_save_and_proxy_group_delete_cannot_both_succeed(self) -> None:
        proxy_store = _MemoryConfig({
            "proxy_groups": [
                {"id": "target", "nodes": [{"url": "http://proxy.example"}]}
            ],
            "account_groups": [],
        })
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backend = _BlockingMutationTestAccountRepository(
                root / "accounts.json",
                root / "auth-keys.json",
            )
            account_holder: dict[str, AccountService] = {}
            proxy_management = ProxyManagementService(
                proxy_store,
                account_provider=lambda: account_holder["service"].list_accounts(),
            )
            service = AccountService(
                backend,
                proxy_reference_mutation=proxy_management.mutate_assignment_references,
            )
            account_holder["service"] = service
            service.add_accounts(["token-one"], return_items=False)

            backend.block_next_mutation = True
            update_finished = Event()
            deletion_finished = Event()
            errors: dict[str, BaseException] = {}

            def update() -> None:
                try:
                    service.update_account(
                        "token-one",
                        {"proxy": "group:target"},
                    )
                except BaseException as exc:  # pragma: no cover - asserted below
                    errors["update"] = exc
                finally:
                    update_finished.set()

            def delete() -> None:
                try:
                    proxy_management.delete_group("target")
                except BaseException as exc:  # pragma: no cover - asserted below
                    errors["delete"] = exc
                finally:
                    deletion_finished.set()

            update_thread = Thread(target=update)
            update_thread.start()
            self.assertTrue(backend.mutation_entered.wait(timeout=5))

            deletion_thread = Thread(target=delete)
            deletion_thread.start()
            self.assertFalse(deletion_finished.wait(timeout=0.1))

            backend.allow_mutation.set()
            update_thread.join(timeout=5)
            deletion_thread.join(timeout=5)

            self.assertTrue(update_finished.is_set())
            self.assertTrue(deletion_finished.is_set())
            self.assertNotIn("update", errors)
            self.assertIsInstance(errors.get("delete"), ProxyGroupInUseError)
            self.assertEqual(
                service.get_account("token-one")["proxy"],
                "group:target",
            )

    def test_account_proxy_writes_persist_inside_injected_mutation_boundary(self) -> None:
        operations = ("single", "batch", "import")
        for operation in operations:
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                probe = _MutationBoundaryProbe()
                backend = _BoundaryCheckingTestAccountRepository(
                    root / "accounts.json",
                    root / "auth-keys.json",
                    probe,
                )
                service = AccountService(
                    backend,
                    proxy_reference_mutation=probe.run,
                )
                if operation != "import":
                    service.add_accounts(["token-one", "token-two"], return_items=False)
                backend.require_boundary = True

                if operation == "single":
                    service.update_account("token-one", {"proxy": "direct"})
                elif operation == "batch":
                    service.update_accounts(
                        ["token-one", "token-two"],
                        {"proxy": "direct"},
                    )
                else:
                    service.add_account_items(
                        [{"access_token": "token-one", "proxy": "direct"}],
                        return_items=False,
                    )

                self.assertEqual(len(probe.calls), 1)
                self.assertEqual(
                    {account["proxy"] for account in service.list_accounts()},
                    {"", "direct"} if operation == "single" else {"direct"},
                )

    def test_single_account_proxy_write_rejects_unknown_group(self) -> None:
        proxy_store = _MemoryConfig()
        mutation = ProxyManagementService(proxy_store).mutate_assignment_references
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = AccountService(
                TestAccountRepository(root / "accounts.json", root / "auth-keys.json"),
                proxy_reference_mutation=mutation,
            )
            service.add_accounts(["token-one"], return_items=False)

            with self.assertRaisesRegex(ValueError, "proxy group not found"):
                service.update_account("token-one", {"proxy": "group:missing"})

            self.assertEqual(service.get_account("token-one")["proxy"], "")

    def test_batch_account_proxy_write_rejects_unknown_group_atomically(self) -> None:
        proxy_store = _MemoryConfig()
        mutation = ProxyManagementService(proxy_store).mutate_assignment_references
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = AccountService(
                TestAccountRepository(root / "accounts.json", root / "auth-keys.json"),
                proxy_reference_mutation=mutation,
            )
            service.add_accounts(["token-one", "token-two"], return_items=False)

            with self.assertRaisesRegex(ValueError, "proxy group not found"):
                service.update_accounts(
                    ["token-one", "token-two"],
                    {"proxy": "group:missing"},
                )

            self.assertEqual(
                {account["proxy"] for account in service.list_accounts()},
                {""},
            )

    def test_account_import_rejects_unknown_proxy_group_before_writing(self) -> None:
        proxy_store = _MemoryConfig()
        mutation = ProxyManagementService(proxy_store).mutate_assignment_references
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = AccountService(
                TestAccountRepository(root / "accounts.json", root / "auth-keys.json"),
                proxy_reference_mutation=mutation,
            )

            with self.assertRaisesRegex(ValueError, "proxy group not found"):
                service.add_account_items(
                    [{"access_token": "token-one", "proxy": "group:missing"}],
                    return_items=False,
                )

            self.assertEqual(service.list_accounts(), [])


if __name__ == "__main__":
    unittest.main()

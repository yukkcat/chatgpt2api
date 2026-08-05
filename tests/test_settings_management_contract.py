from __future__ import annotations

import copy
import json
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from contracts.settings import SettingsPatch
from api import system
from services.application_database import dispose_database_engine
from services.config import ConfigStore
from services.settings_management_service import (
    SettingsManagementService,
    SettingsRevisionConflictError,
)
from services.storage.configuration_repository import (
    AccountGroupRepository,
    SystemSettingsRepository,
)


class _ConfigStore:
    def __init__(self, data: dict | None = None) -> None:
        self.data = copy.deepcopy(data or {})
        self._lock = threading.RLock()

    @property
    def base_url(self) -> str:
        return str(os.getenv("CHATGPT2API_BASE_URL") or self.data.get("base_url") or "").strip().rstrip("/")

    def get(self) -> dict:
        with self._lock:
            return copy.deepcopy(self.data)

    def update(self, values: dict) -> dict:
        with self._lock:
            self.data.update(copy.deepcopy(values))
            return copy.deepcopy(self.data)

    def get_proxy_runtime_settings(self) -> dict:
        value = self.data.get("proxy_runtime")
        return copy.deepcopy(value) if isinstance(value, dict) else {}


class _LocklessConfigStore:
    def __init__(self, data: dict | None = None) -> None:
        self.data = copy.deepcopy(data or {})

    @property
    def base_url(self) -> str:
        return str(os.getenv("CHATGPT2API_BASE_URL") or self.data.get("base_url") or "").strip().rstrip("/")

    def get(self) -> dict:
        return copy.deepcopy(self.data)

    def update(self, values: dict) -> dict:
        self.data.update(copy.deepcopy(values))
        return copy.deepcopy(self.data)


class _PausingSettingsService(SettingsManagementService):
    def __init__(self, config_store: _ConfigStore) -> None:
        super().__init__(config_store)
        self.merge_started = threading.Event()
        self.resume_merge = threading.Event()

    def _storage_updates(self, values, effective, stored):
        self.merge_started.set()
        if not self.resume_merge.wait(timeout=2):
            raise TimeoutError("test did not resume settings merge")
        return super()._storage_updates(values, effective, stored)


@contextmanager
def _database_config_store(config_path: Path):
    initial = json.loads(config_path.read_text(encoding="utf-8"))
    initial.pop("auth-key", None)
    database_url = f"sqlite:///{(config_path.parent / 'app.db').as_posix()}"
    settings_repository = SystemSettingsRepository(database_url)
    settings_repository.replace(initial)
    try:
        yield ConfigStore(
            config_path,
            settings_repository=settings_repository,
            groups_repository=AccountGroupRepository(database_url),
        )
    finally:
        dispose_database_engine(database_url)


def _sensitive_settings() -> dict:
    return {
        "ai_review": {
            "enabled": True,
            "api_key": "review-secret",
            "model": "review-model",
            "future_flag": "preserve-ai-review",
        },
        "image_storage": {
            "enabled": True,
            "mode": "webdav",
            "webdav_url": "https://dav.example.test",
            "webdav_password": "webdav-secret",
            "future_flag": "preserve-image-storage",
        },
        "backup": {
            "enabled": True,
            "secret_access_key": "r2-secret",
            "passphrase": "backup-secret",
            "bucket": "bucket-a",
            "include": {
                "images": True,
                "future_section": False,
            },
            "future_flag": "preserve-backup",
        },
        "proxy_runtime": {
            "enabled": True,
            "egress_mode": "single_proxy",
            "clearance": {
                "enabled": True,
                "mode": "manual",
                "cf_cookies": "cookie-secret",
                "cf_clearance": "clearance-secret",
                "browser": "chrome",
                "future_flag": "preserve-clearance",
            },
            "reset_session_status_codes": [403],
        },
    }


class SettingsManagementContractTests(unittest.TestCase):
    def test_view_contains_only_page_settings_and_redacts_every_secret(self) -> None:
        data = {
            **_sensitive_settings(),
            "quota_limits": {"enabled": True},
            "runtime_capacity": {"uvicorn_workers": 9},
            "image_generation": {"enabled": True},
            "chat_completion_cache": {"enabled": True},
            "basic": {"api_key": "do-not-return"},
            "proxy": "http://default.example.test",
            "fallback_proxy": "http://fallback.example.test",
            "proxy_groups": [{"id": "pool-a"}],
            "image_parallel_generation": False,
            "image_poll_interval_secs": 3,
        }
        service = SettingsManagementService(_ConfigStore(data))

        payload = service.view().model_dump(mode="python")
        settings = payload["settings"]

        for excluded in (
            "quota_limits",
            "runtime_capacity",
            "image_generation",
            "chat_completion_cache",
            "basic",
            "proxy",
            "fallback_proxy",
            "proxy_groups",
            "image_parallel_generation",
            "image_poll_interval_secs",
        ):
            self.assertNotIn(excluded, settings)
        self.assertEqual(settings["ai_review"]["api_key"], "")
        self.assertTrue(settings["ai_review"]["has_api_key"])
        self.assertEqual(settings["image_storage"]["webdav_password"], "")
        self.assertTrue(settings["image_storage"]["has_webdav_password"])
        self.assertEqual(settings["backup"]["secret_access_key"], "")
        self.assertTrue(settings["backup"]["has_secret_access_key"])
        self.assertEqual(settings["backup"]["passphrase"], "")
        self.assertTrue(settings["backup"]["has_passphrase"])
        clearance = settings["proxy_runtime"]["clearance"]
        self.assertEqual(clearance["cf_cookies"], "")
        self.assertTrue(clearance["has_cf_cookies"])
        self.assertEqual(clearance["cf_clearance"], "")
        self.assertTrue(clearance["has_cf_clearance"])
        self.assertNotIn("review-secret", repr(payload))
        self.assertNotIn("webdav-secret", repr(payload))
        self.assertNotIn("r2-secret", repr(payload))
        self.assertNotIn("backup-secret", repr(payload))
        self.assertNotIn("cookie-secret", repr(payload))
        self.assertNotIn("clearance-secret", repr(payload))

    def test_defaults_and_metadata_match_runtime_defaults(self) -> None:
        view = SettingsManagementService(_ConfigStore()).view()

        self.assertEqual(view.settings.image_retention_days, 30)
        self.assertEqual(view.settings.backup.interval_minutes, 360)
        self.assertEqual(view.fields["image_retention_days"].default, 30)
        self.assertEqual(view.fields["backup.interval_minutes"].default, 360)
        self.assertEqual(view.fields["image_account_concurrency"].min, 1)
        self.assertEqual(view.fields["image_account_concurrency"].max, 3)
        self.assertEqual(view.settings.account_processing_concurrency, 30)
        self.assertEqual(view.fields["account_processing_concurrency"].default, 30)
        self.assertEqual(view.fields["account_processing_concurrency"].min, 1)
        self.assertEqual(view.fields["account_processing_concurrency"].max, 100)
        self.assertEqual(
            view.fields["image_upscale_engine"].options,
            ["sharp_lanczos3", "pillow_lanczos"],
        )
        self.assertEqual(view.fields["image_retention_days"].source, "default")

    def test_retired_register_backup_setting_is_not_exposed(self) -> None:
        view = SettingsManagementService(_ConfigStore({
            "backup": {"include": {"register": True}},
        })).view()

        include = view.settings.backup.include.model_dump(mode="python", by_alias=True)
        self.assertNotIn("register", include)
        self.assertNotIn("backup.include.register", view.fields)

    def test_partial_nested_patch_preserves_known_and_unknown_siblings(self) -> None:
        store = _ConfigStore(_sensitive_settings())
        service = SettingsManagementService(store)

        mutation = service.update(SettingsPatch.model_validate({
            "revision": service.view().revision,
            "ai_review": {"enabled": False},
            "backup": {"include": {"images": False}},
            "proxy_runtime": {"clearance": {"timeout_sec": 90}},
        }))

        self.assertFalse(store.data["ai_review"]["enabled"])
        self.assertEqual(store.data["ai_review"]["model"], "review-model")
        self.assertEqual(store.data["ai_review"]["future_flag"], "preserve-ai-review")
        self.assertFalse(store.data["backup"]["include"]["images"])
        self.assertFalse(store.data["backup"]["include"]["future_section"])
        self.assertEqual(store.data["backup"]["future_flag"], "preserve-backup")
        self.assertEqual(store.data["proxy_runtime"]["clearance"]["timeout_sec"], 90)
        self.assertEqual(
            store.data["proxy_runtime"]["clearance"]["future_flag"],
            "preserve-clearance",
        )
        self.assertEqual(
            mutation.changed_fields,
            [
                "ai_review.enabled",
                "backup.include.images",
                "proxy_runtime.clearance.timeout_sec",
            ],
        )

    def test_blank_sensitive_patch_preserves_existing_values(self) -> None:
        store = _ConfigStore(_sensitive_settings())
        service = SettingsManagementService(store)

        mutation = service.update(SettingsPatch.model_validate({
            "revision": service.view().revision,
            "ai_review": {"api_key": ""},
            "image_storage": {"webdav_password": "   "},
            "backup": {"secret_access_key": "", "passphrase": ""},
            "proxy_runtime": {"clearance": {"cf_cookies": "", "cf_clearance": ""}},
        }))

        self.assertEqual(store.data["ai_review"]["api_key"], "review-secret")
        self.assertEqual(store.data["image_storage"]["webdav_password"], "webdav-secret")
        self.assertEqual(store.data["backup"]["secret_access_key"], "r2-secret")
        self.assertEqual(store.data["backup"]["passphrase"], "backup-secret")
        self.assertEqual(store.data["proxy_runtime"]["clearance"]["cf_cookies"], "cookie-secret")
        self.assertEqual(store.data["proxy_runtime"]["clearance"]["cf_clearance"], "clearance-secret")
        self.assertEqual(mutation.changed_fields, [])

    def test_non_empty_sensitive_patch_replaces_values_without_returning_them(self) -> None:
        store = _ConfigStore(_sensitive_settings())
        service = SettingsManagementService(store)
        before_revision = service.view().revision

        mutation = service.update(SettingsPatch.model_validate({
            "revision": before_revision,
            "ai_review": {"api_key": "new-review"},
            "image_storage": {"webdav_password": "new-webdav"},
            "backup": {"secret_access_key": "new-r2", "passphrase": "new-passphrase"},
            "proxy_runtime": {"clearance": {"cf_cookies": "new-cookie", "cf_clearance": "new-clearance"}},
        }))

        self.assertEqual(store.data["ai_review"]["api_key"], "new-review")
        self.assertEqual(store.data["image_storage"]["webdav_password"], "new-webdav")
        self.assertEqual(store.data["backup"]["secret_access_key"], "new-r2")
        self.assertEqual(store.data["backup"]["passphrase"], "new-passphrase")
        self.assertEqual(store.data["proxy_runtime"]["clearance"]["cf_cookies"], "new-cookie")
        self.assertEqual(store.data["proxy_runtime"]["clearance"]["cf_clearance"], "new-clearance")
        self.assertNotEqual(before_revision, mutation.revision)
        self.assertNotIn("new-review", repr(mutation.model_dump(mode="python")))
        self.assertNotIn("new-webdav", repr(mutation.model_dump(mode="python")))

    def test_contract_rejects_unknown_fields_nested_unknowns_ranges_and_enums(self) -> None:
        invalid_payloads = [
            {"unknown": True},
            {"ai_review": {"unknown": True}},
            {"image_account_concurrency": 0},
            {"image_account_concurrency": 4},
            {"account_processing_concurrency": 0},
            {"account_processing_concurrency": 101},
            {"image_max_account_attempts": 1},
            {"image_settle_secs": 0.1},
            {"backup": {"interval_minutes": 0}},
            {"proxy_runtime": {"clearance": {"refresh_interval": 59}}},
            {"image_upscale_engine": "nearest"},
            {"image_storage": {"mode": "s3"}},
            {"proxy_runtime": {"egress_mode": "random"}},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                SettingsPatch.model_validate({"revision": "test-revision", **payload})

    def test_revision_is_required_and_must_not_be_blank(self) -> None:
        for payload in ({"log_retention_days": 14}, {"revision": "   ", "log_retention_days": 14}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                SettingsPatch.model_validate(payload)

    def test_revision_is_stable_until_a_change_and_rejects_stale_writes(self) -> None:
        store = _ConfigStore({"image_retention_days": 30})
        service = SettingsManagementService(store)
        first = service.view()
        second = service.view()
        self.assertEqual(first.revision, second.revision)

        mutation = service.update(SettingsPatch(
            revision=first.revision,
            image_retention_days=31,
        ))
        self.assertEqual(mutation.schema_version, first.schema_version)
        self.assertEqual(mutation.settings.image_retention_days, 31)
        self.assertEqual(mutation.changed_fields, ["image_retention_days"])
        self.assertNotEqual(mutation.revision, first.revision)
        self.assertIn("image_retention_days", mutation.fields)

        with self.assertRaises(SettingsRevisionConflictError):
            service.update(SettingsPatch(
                revision=first.revision,
                image_retention_days=32,
            ))

    def test_patch_equal_to_effective_default_does_not_materialize_nested_defaults(self) -> None:
        store = _ConfigStore()
        service = SettingsManagementService(store)

        mutation = service.update(SettingsPatch.model_validate({
            "revision": service.view().revision,
            "ai_review": {"enabled": False},
        }))

        self.assertNotIn("ai_review", store.data)
        self.assertEqual(mutation.changed_fields, [])

    def test_environment_base_url_is_effective_read_only_value(self) -> None:
        store = _ConfigStore({"base_url": "https://stored.example.test"})
        service = SettingsManagementService(store)

        with patch.dict(os.environ, {"CHATGPT2API_BASE_URL": "https://env.example.test/"}):
            view = service.view()
            self.assertEqual(view.settings.base_url, "https://env.example.test")
            self.assertEqual(view.fields["base_url"].source, "environment")
            self.assertTrue(view.fields["base_url"].read_only)
            with self.assertRaisesRegex(ValueError, "read-only"):
                service.update(SettingsPatch(
                    revision=view.revision,
                    base_url="https://new.example.test",
                ))

    def test_blank_environment_base_url_does_not_hide_the_stored_value(self) -> None:
        store = _ConfigStore({"base_url": "https://stored.example.test"})
        service = SettingsManagementService(store)

        with patch.dict(os.environ, {"CHATGPT2API_BASE_URL": "   "}):
            view = service.view()
            self.assertEqual(view.settings.base_url, "https://stored.example.test")
            self.assertFalse(view.fields["base_url"].read_only)

            mutation = service.update(SettingsPatch(
                revision=view.revision,
                base_url="https://new.example.test",
            ))

        self.assertEqual(mutation.settings.base_url, "https://new.example.test")
        self.assertEqual(mutation.changed_fields, ["base_url"])

    def test_lockless_store_uses_the_same_contract(self) -> None:
        store = _LocklessConfigStore({"log_retention_days": 30})
        service = SettingsManagementService(store)

        mutation = service.update(SettingsPatch(
            revision=service.view().revision,
            log_retention_days=14,
        ))

        self.assertEqual(store.data["log_retention_days"], 14)
        self.assertEqual(mutation.changed_fields, ["log_retention_days"])

    def test_repeating_the_same_sensitive_value_is_a_noop(self) -> None:
        store = _ConfigStore(_sensitive_settings())
        service = SettingsManagementService(store)

        mutation = service.update(SettingsPatch.model_validate({
            "revision": service.view().revision,
            "ai_review": {"api_key": "review-secret"},
            "backup": {"secret_access_key": "r2-secret"},
        }))

        self.assertEqual(mutation.changed_fields, [])

    def test_settings_route_exposes_get_and_patch_only(self) -> None:
        methods = {
            method
            for route in system.create_router("test").routes
            if getattr(route, "path", "") == "/api/settings"
            for method in getattr(route, "methods", set())
        }
        self.assertEqual(methods, {"GET", "PATCH"})

    def test_public_third_party_apps_view_is_a_strict_projection(self) -> None:
        store = _ConfigStore({
            "base_url": "https://public.example.test/",
            "third_party_apps": {
                "infinite_canvas": {
                    "enabled": True,
                    "url": "https://canvas.example.test/",
                    "future_flag": "do-not-publish",
                },
                "future_app": {"enabled": True},
            },
        })

        payload = (
            SettingsManagementService(store)
            .public_third_party_apps_view()
            .model_dump(mode="python")
        )

        self.assertEqual(payload, {
            "api_base_url": "https://public.example.test",
            "third_party_apps": {
                "infinite_canvas": {
                    "enabled": True,
                    "url": "https://canvas.example.test",
                },
            },
        })


class SettingsManagementRouteContractTests(unittest.TestCase):
    def setUp(self) -> None:
        store = _ConfigStore({
            "base_url": "https://public.example.test/",
            "third_party_apps": {
                "infinite_canvas": {
                    "enabled": True,
                    "url": "https://canvas.example.test/",
                    "future_flag": "do-not-publish",
                },
                "future_app": {"enabled": True},
            },
        })
        self.service = SettingsManagementService(store)
        patchers = [
            patch.object(system, "settings_management_service", self.service),
            patch.object(system, "require_admin", lambda _authorization: {"id": "admin"}),
            patch.object(system, "require_identity", lambda _authorization: {"id": "user"}),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        app = FastAPI()
        app.include_router(system.create_router("test"))
        self.client = TestClient(app)

    def test_patch_requires_revision_and_old_post_is_not_available(self) -> None:
        missing_revision = self.client.patch(
            "/api/settings",
            json={"log_retention_days": 14},
        )
        old_post = self.client.post(
            "/api/settings",
            json={"log_retention_days": 14},
        )

        self.assertEqual(missing_revision.status_code, 422, missing_revision.text)
        self.assertEqual(old_post.status_code, 405, old_post.text)

    def test_third_party_apps_route_returns_only_the_public_projection(self) -> None:
        response = self.client.get("/api/third-party-apps")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {
            "api_base_url": "https://public.example.test",
            "third_party_apps": {
                "infinite_canvas": {
                    "enabled": True,
                    "url": "https://canvas.example.test",
                },
            },
        })


class SettingsConfigStoreIntegrationTests(unittest.TestCase):
    def test_real_store_preserves_unknown_siblings_and_secrets(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(json.dumps({
                "auth-key": "test-key",
                "ai_review": {
                    "enabled": True,
                    "api_key": "review-secret",
                    "future_flag": "keep-ai",
                },
                "image_storage": {
                    "enabled": False,
                    "webdav_password": "webdav-secret",
                    "future_flag": "keep-storage",
                },
                "backup": {
                    "secret_access_key": "r2-secret",
                    "passphrase": "backup-secret",
                    "include": {"images": True, "future_section": "keep-include"},
                    "future_flag": "keep-backup",
                },
                "proxy_runtime": {
                    "clearance": {
                        "cf_cookies": "cookie-secret",
                        "cf_clearance": "clearance-secret",
                        "future_flag": "keep-clearance",
                    },
                    "future_flag": "keep-runtime",
                },
                "third_party_apps": {
                    "infinite_canvas": {
                        "enabled": False,
                        "future_flag": "keep-canvas",
                    },
                    "future_app": {"enabled": True},
                },
            }), encoding="utf-8")
            with _database_config_store(config_path) as store:
                service = SettingsManagementService(store)

                service.update(SettingsPatch.model_validate({
                    "revision": service.view().revision,
                    "ai_review": {"enabled": False},
                    "image_storage": {"webdav_root_path": "images-v2"},
                    "backup": {"include": {"images": False}},
                    "proxy_runtime": {"clearance": {"timeout_sec": 90}},
                    "third_party_apps": {"infinite_canvas": {"enabled": True}},
                }))

                self.assertEqual(store.data["ai_review"]["future_flag"], "keep-ai")
                self.assertEqual(store.data["image_storage"]["future_flag"], "keep-storage")
                self.assertEqual(store.data["backup"]["future_flag"], "keep-backup")
                self.assertEqual(store.data["backup"]["include"]["future_section"], "keep-include")
                self.assertEqual(store.data["proxy_runtime"]["future_flag"], "keep-runtime")
                self.assertEqual(
                    store.data["proxy_runtime"]["clearance"]["future_flag"],
                    "keep-clearance",
                )
                self.assertEqual(
                    store.data["third_party_apps"]["infinite_canvas"]["future_flag"],
                    "keep-canvas",
                )
                self.assertTrue(store.data["third_party_apps"]["future_app"]["enabled"])
                self.assertEqual(store.data["ai_review"]["api_key"], "review-secret")
                self.assertEqual(store.data["image_storage"]["webdav_password"], "webdav-secret")
                self.assertEqual(store.data["backup"]["secret_access_key"], "r2-secret")
                self.assertEqual(store.data["backup"]["passphrase"], "backup-secret")
                self.assertEqual(
                    store.data["proxy_runtime"]["clearance"]["cf_cookies"],
                    "cookie-secret",
                )
                public_runtime = store.get_public_proxy_runtime_settings()
                self.assertNotIn("future_flag", public_runtime)
                self.assertNotIn("future_flag", public_runtime["clearance"])
                self.assertEqual(public_runtime["clearance"]["cf_cookies"], "")
                self.assertTrue(public_runtime["clearance"]["has_cf_cookies"])

    def test_changed_fields_reflect_persisted_normalized_values(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(json.dumps({
                "auth-key": "test-key",
                "image_storage": {
                    "enabled": False,
                    "mode": "local",
                },
            }), encoding="utf-8")
            with _database_config_store(config_path) as store:
                service = SettingsManagementService(store)
                before = service.view()

                mutation = service.update(SettingsPatch.model_validate({
                    "revision": before.revision,
                    "image_storage": {"mode": "webdav"},
                }))

                self.assertEqual(mutation.settings.image_storage.mode, "local")
                self.assertEqual(mutation.revision, service.view().revision)
                self.assertEqual(mutation.changed_fields, [])

    def test_settings_transaction_holds_the_store_lock_through_merge_and_update(self) -> None:
        store = _ConfigStore({"log_retention_days": 30})
        service = _PausingSettingsService(store)
        revision = service.view().revision
        settings_errors: list[BaseException] = []
        writer_started = threading.Event()
        writer_done = threading.Event()

        def update_settings() -> None:
            try:
                service.update(SettingsPatch(
                    revision=revision,
                    log_retention_days=14,
                ))
            except BaseException as exc:
                settings_errors.append(exc)

        def direct_write() -> None:
            writer_started.set()
            store.update({"external_change": True})
            writer_done.set()

        settings_thread = threading.Thread(target=update_settings)
        settings_thread.start()
        self.assertTrue(service.merge_started.wait(timeout=2))
        writer_thread = threading.Thread(target=direct_write)
        writer_thread.start()
        self.assertTrue(writer_started.wait(timeout=2))
        self.assertFalse(writer_done.wait(timeout=0.1))

        service.resume_merge.set()
        settings_thread.join(timeout=2)
        writer_thread.join(timeout=2)

        self.assertFalse(settings_thread.is_alive())
        self.assertFalse(writer_thread.is_alive())
        self.assertEqual(settings_errors, [])
        self.assertEqual(store.data["log_retention_days"], 14)
        self.assertTrue(store.data["external_change"])

    def test_failed_save_restores_previous_memory_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps({"auth-key": "test-key", "base_url": "https://old.example"}),
                encoding="utf-8",
            )
            with _database_config_store(config_path) as store:
                before = copy.deepcopy(store.data)

                with patch.object(
                    store._settings_repository,
                    "update",
                    side_effect=OSError("database unavailable"),
                ):
                    with self.assertRaises(OSError):
                        store.update({"base_url": "https://new.example"})

                self.assertEqual(store.data, before)


if __name__ == "__main__":
    unittest.main()

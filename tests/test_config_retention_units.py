from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from pydantic import ValidationError

from contracts.settings import SettingsValues
from contracts.settings_specification import (
    NUMERIC_SETTING_SPECS,
    normalize_float_setting,
    normalize_integer_setting,
    numeric_setting_spec,
)
from services.config import ConfigStore, _legacy_basic_from_settings, _promote_legacy_basic_settings
from services.application_database import dispose_database_engine
from services.settings_management_service import SettingsManagementService
from services.storage.configuration_repository import (
    AccountGroupRepository,
    SystemSettingsRepository,
)


class _MemoryConfig:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = data

    def get(self) -> dict[str, object]:
        return dict(self.data)

    @property
    def base_url(self) -> str:
        return ""


def _nested_setting_value(value: object, path: str) -> object:
    current = value
    for part in path.split("."):
        current = getattr(current, part)
    return current


def _nested_setting_payload(path: str, value: object) -> dict[str, object]:
    payload: object = value
    for part in reversed(path.split(".")):
        payload = {part: payload}
    return payload


@contextmanager
def _database_config_store(
    root: Path,
    settings: dict[str, object],
):
    database_url = f"sqlite:///{(root / 'app.db').as_posix()}"
    settings_repository = SystemSettingsRepository(database_url)
    settings_repository.replace(settings)
    bootstrap_path = root / "config.json"
    bootstrap_path.write_text(json.dumps({"auth-key": "test-key"}), encoding="utf-8")
    try:
        yield ConfigStore(
            bootstrap_path,
            settings_repository=settings_repository,
            groups_repository=AccountGroupRepository(database_url),
        )
    finally:
        dispose_database_engine(database_url)


class RetentionUnitCompatibilityTests(unittest.TestCase):
    def test_legacy_hours_are_rounded_up_to_retention_days(self) -> None:
        promoted = _promote_legacy_basic_settings({
            "basic": {"image_expire_hours": 25},
        })

        self.assertEqual(promoted["image_retention_days"], 2)

    def test_explicit_retention_days_are_not_overridden_by_legacy_hours(self) -> None:
        promoted = _promote_legacy_basic_settings({
            "image_retention_days": 7,
            "basic": {"image_expire_hours": 240},
        })

        self.assertEqual(promoted["image_retention_days"], 7)

    def test_canonical_days_are_projected_back_as_legacy_hours(self) -> None:
        basic = _legacy_basic_from_settings({}, {"image_retention_days": 7})

        self.assertEqual(basic["image_expire_hours"], 168)

    def test_image_min_free_mb_is_read_from_config_store(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with _database_config_store(
                Path(temp_dir),
                {"image_min_free_mb": 2048},
            ) as store:
                self.assertEqual(store.image_min_free_mb, 2048)
                self.assertEqual(store.get()["image_min_free_mb"], 2048)

    def test_refresh_interval_uses_one_specification_at_every_settings_seam(self) -> None:
        spec = numeric_setting_spec("refresh_account_interval_minute")
        store = _MemoryConfig({"auth-key": "test-key", "refresh_account_interval_minute": 0})
        view = SettingsManagementService(store).view()

        self.assertEqual(spec.default, 5)
        self.assertEqual(spec.minimum, 1)
        self.assertEqual(view.settings.refresh_account_interval_minute, 1)
        self.assertEqual(view.fields["refresh_account_interval_minute"].default, spec.default)
        self.assertEqual(view.fields["refresh_account_interval_minute"].min, spec.minimum)
        with self.assertRaises(ValidationError):
            SettingsValues(refresh_account_interval_minute=0)

    def test_all_numeric_settings_share_defaults_and_bounds_at_every_settings_seam(self) -> None:
        view = SettingsManagementService(_MemoryConfig({"auth-key": "test-key"})).view()
        defaults = SettingsValues()

        for name, spec in NUMERIC_SETTING_SPECS.items():
            with self.subTest(name=name):
                metadata = view.fields[name]
                self.assertEqual(_nested_setting_value(defaults, name), spec.default)
                self.assertEqual(metadata.default, spec.default)
                self.assertEqual(metadata.min, spec.minimum)
                self.assertEqual(metadata.max, spec.maximum)
                self.assertEqual(metadata.unit, spec.unit)

                normalize = (
                    normalize_float_setting
                    if spec.kind == "float"
                    else normalize_integer_setting
                )
                self.assertEqual(normalize(name, "invalid"), spec.default)
                self.assertEqual(normalize(name, spec.minimum - 1), spec.minimum)

                with self.assertRaises(ValidationError):
                    SettingsValues.model_validate(
                        _nested_setting_payload(name, spec.minimum - 1)
                    )

                if spec.maximum is not None:
                    self.assertEqual(normalize(name, spec.maximum + 1), spec.maximum)
                    with self.assertRaises(ValidationError):
                        SettingsValues.model_validate(
                            _nested_setting_payload(name, spec.maximum + 1)
                        )

    def test_config_store_clamps_non_positive_refresh_interval(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with _database_config_store(
                Path(temp_dir),
                {"refresh_account_interval_minute": -9},
            ) as store:
                self.assertEqual(store.refresh_account_interval_minute, 1)
                self.assertEqual(store.get()["refresh_account_interval_minute"], 1)

    def test_repeated_reads_inside_refresh_window_do_not_query_repository(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with _database_config_store(
                Path(temp_dir),
                {"image_min_free_mb": 2048},
            ) as store:
                repository = store._settings_repository
                with mock.patch.object(repository, "get", wraps=repository.get) as get:
                    self.assertEqual(store.image_min_free_mb, 2048)
                    self.assertEqual(store.image_min_free_mb, 2048)
                    self.assertEqual(store.get()["image_min_free_mb"], 2048)

                get.assert_not_called()

    def test_external_repository_update_is_visible_after_refresh_window(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with _database_config_store(
                Path(temp_dir),
                {"image_min_free_mb": 2048},
            ) as store:
                store._settings_repository.update({"image_min_free_mb": 4096})
                self.assertEqual(store.image_min_free_mb, 2048)

                store._last_repository_refresh_at = 0.0

                self.assertEqual(store.image_min_free_mb, 4096)

    def test_update_refreshes_same_process_data_immediately(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with _database_config_store(
                Path(temp_dir),
                {"image_min_free_mb": 2048},
            ) as store:
                result = store.update({"image_min_free_mb": 4096})

                self.assertEqual(result["image_min_free_mb"], 4096)
                self.assertEqual(store.image_min_free_mb, 4096)
                self.assertEqual(store._settings_repository.get()["image_min_free_mb"], 4096)

    def test_removed_refresh_policy_fields_are_not_projected(self) -> None:
        store = _MemoryConfig({
            "auth-key": "test-key",
            "image_auth_refresh_concurrency": 10,
            "image_preflight_token_refresh_enabled": True,
            "auto_relogin_after_refresh": True,
        })

        view = SettingsManagementService(store).view()
        settings = view.settings.model_dump()

        self.assertNotIn("image_auth_refresh_concurrency", settings)
        self.assertNotIn("image_preflight_token_refresh_enabled", settings)
        self.assertNotIn("auto_relogin_after_refresh", settings)
        self.assertNotIn("image_auth_refresh_concurrency", view.fields)
        self.assertNotIn("image_preflight_token_refresh_enabled", view.fields)
        self.assertNotIn("auto_relogin_after_refresh", view.fields)

    def test_removed_refresh_policy_fields_are_not_projected_by_config_store(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with _database_config_store(root, {
                    "image_auth_refresh_concurrency": 10,
                    "image_preflight_token_refresh_enabled": True,
                    "auto_relogin_after_refresh": True,
            }) as store:
                self.assertNotIn("image_auth_refresh_concurrency", store.get())
                self.assertNotIn("image_preflight_token_refresh_enabled", store.get())
                self.assertNotIn("auto_relogin_after_refresh", store.get())



if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import inspect

from contracts.proxy import ProxyGroupPatch, ProxyNodeInput, ProxyReference
from services.application_database import dispose_database_engine
from services.config import ConfigStore
from services.proxy_management_service import ProxyManagementService
from services.proxy_service import ProxySettingsStore
from services.storage.configuration_repository import (
    AccountGroupRepository,
    ProxyConfigurationRepository,
    SystemSettingsRepository,
)


def test_configuration_repositories_keep_domain_documents_separate() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        database_url = f"sqlite:///{(root / 'app.db').as_posix()}"
        try:
            settings = SystemSettingsRepository(database_url)
            proxies = ProxyConfigurationRepository(database_url)
            groups = AccountGroupRepository(database_url)

            settings.update({"base_url": "https://api.example.test"})
            proxies.update({"proxy": "direct"})
            groups.update({"items": [{"id": "team-a"}]})

            assert settings.get() == {"base_url": "https://api.example.test"}
            assert proxies.get() == {"proxy": "direct"}
            assert groups.get() == {"items": [{"id": "team-a"}]}
            table_names = set(inspect(settings.engine).get_table_names())
            assert {
                "system_settings",
                "proxy_configuration",
                "account_group_configuration",
            } <= table_names
            assert "application_documents" not in table_names
        finally:
            dispose_database_engine(database_url)


def test_system_settings_updates_are_serialized() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        database_url = f"sqlite:///{(root / 'app.db').as_posix()}"
        try:
            repository = SystemSettingsRepository(database_url)

            def write(index: int) -> None:
                SystemSettingsRepository(database_url).update({f"key_{index}": index})

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(write, range(24)))

            assert repository.get() == {f"key_{index}": index for index in range(24)}
        finally:
            dispose_database_engine(database_url)


def test_config_store_routes_settings_and_account_groups_without_proxy_ownership() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        database_url = f"sqlite:///{(root / 'app.db').as_posix()}"
        bootstrap = root / "config.json"
        bootstrap.write_text(json.dumps({"auth-key": "test-key"}), encoding="utf-8")
        try:
            settings = SystemSettingsRepository(database_url)
            groups = AccountGroupRepository(database_url)
            store = ConfigStore(
                bootstrap,
                settings_repository=settings,
                groups_repository=groups,
            )

            store.update({"base_url": "https://api.example.test"})
            store.update({"account_groups": [{"id": "team-a"}]})

            assert settings.get()["base_url"] == "https://api.example.test"
            assert groups.get()["items"] == [{"id": "team-a"}]
            with pytest.raises(ValueError, match="ProxyManagementService"):
                store.update({"proxy_groups": []})
        finally:
            dispose_database_engine(database_url)


def test_proxy_management_and_runtime_share_the_proxy_repository() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        database_url = f"sqlite:///{(root / 'app.db').as_posix()}"
        try:
            repository = ProxyConfigurationRepository(database_url)
            management = ProxyManagementService(repository)
            runtime = ProxySettingsStore(
                config_store=type(
                    "RuntimeSettings",
                    (),
                    {
                        "get_proxy_runtime_settings": lambda self: {},
                        "get": lambda self: {},
                    },
                )(),
                proxy_repository=repository,
            )

            management.save_group(ProxyGroupPatch(
                id="primary",
                name="Primary",
                create_only=True,
                nodes=[ProxyNodeInput(
                    id="node-a",
                    name="Node A",
                    url="http://127.0.0.1:7890",
                    enabled=True,
                )],
            ))
            management.save_defaults(
                ProxyReference(mode="group", group_id="primary"),
                None,
            )

            profile = runtime.get_profile(upstream=True)
            assert profile.proxy_url == "http://127.0.0.1:7890"
            assert profile.proxy_group_id == "primary"
            assert profile.proxy_node_id == "node-a"
        finally:
            dispose_database_engine(database_url)

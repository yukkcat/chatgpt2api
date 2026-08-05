from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from services.application_database import dispose_database_engine
from services.storage.remote_import_configuration_repository import (
    RemoteImportConfigurationRepository,
)


def test_remote_import_providers_are_isolated_and_values_are_copied() -> None:
    with TemporaryDirectory() as directory:
        database_url = f"sqlite:///{(Path(directory) / 'app.db').as_posix()}"
        try:
            repository = RemoteImportConfigurationRepository(database_url)
            cpa = [{"id": "cpa-1", "secret_key": "secret"}]
            repository.replace("cpa", cpa)
            repository.replace("sub2api", [{"id": "sub-1"}])
            cpa[0]["id"] = "mutated"

            assert repository.load("cpa") == [
                {"id": "cpa-1", "secret_key": "secret"}
            ]
            assert repository.load("sub2api") == [{"id": "sub-1"}]
        finally:
            dispose_database_engine(database_url)


def test_remote_import_configuration_updates_are_atomic() -> None:
    with TemporaryDirectory() as directory:
        database_url = f"sqlite:///{(Path(directory) / 'app.db').as_posix()}"
        try:
            def append(index: int) -> None:
                repository = RemoteImportConfigurationRepository(database_url)
                repository.update(
                    "cpa",
                    lambda current: [*current, {"id": f"pool-{index}"}],
                )

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(append, range(24)))

            items = RemoteImportConfigurationRepository(database_url).load("cpa")
            assert {item["id"] for item in items} == {
                f"pool-{index}" for index in range(24)
            }
        finally:
            dispose_database_engine(database_url)

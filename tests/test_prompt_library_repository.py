from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from services.application_database import dispose_database_engine
from services.storage.prompt_library_repository import PromptLibraryRepository


def test_prompt_library_state_keeps_settings_and_snapshot_independent() -> None:
    with TemporaryDirectory() as directory:
        database_url = f"sqlite:///{(Path(directory) / 'app.db').as_posix()}"
        try:
            repository = PromptLibraryRepository(database_url)
            repository.replace_settings({"sources": [{"id": "source-a"}]})
            repository.replace_snapshot({"items_by_source": {"source-a": []}})

            state = PromptLibraryRepository(database_url).load()
            assert state.settings == {"sources": [{"id": "source-a"}]}
            assert state.snapshot == {"items_by_source": {"source-a": []}}
            assert state.settings_revision == 1
            assert state.snapshot_revision == 1
        finally:
            dispose_database_engine(database_url)


def test_prompt_library_fields_do_not_overwrite_concurrently() -> None:
    with TemporaryDirectory() as directory:
        database_url = f"sqlite:///{(Path(directory) / 'app.db').as_posix()}"
        try:
            repository = PromptLibraryRepository(database_url)
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = (
                    executor.submit(repository.replace_settings, {"enabled": True}),
                    executor.submit(repository.replace_snapshot, {"revision": "one"}),
                )
                for future in futures:
                    future.result()

            state = repository.load()
            assert state.settings == {"enabled": True}
            assert state.snapshot == {"revision": "one"}
        finally:
            dispose_database_engine(database_url)

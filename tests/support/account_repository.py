from __future__ import annotations

from pathlib import Path

from services.storage.database_storage import DatabaseStorageBackend


class TestAccountRepository(DatabaseStorageBackend):
    """SQLite Account Repository with the path-shaped constructor used by tests."""

    __test__ = False

    def __init__(self, accounts_path: Path, _auth_keys_path: Path | None = None) -> None:
        accounts_path.parent.mkdir(parents=True, exist_ok=True)
        database_path = accounts_path.with_suffix(".test.db")
        super().__init__(f"sqlite:///{database_path.as_posix()}")

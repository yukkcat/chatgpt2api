from __future__ import annotations

from pathlib import Path

from services.application_database import display_database_url, resolve_database_url
from services.storage.base import StorageBackend
from services.storage.database_storage import DatabaseStorageBackend


def create_storage_backend(data_dir: Path) -> StorageBackend:
    """Create the Account Repository in the configured Application Database."""
    database_url = resolve_database_url(data_dir)
    print(f"[storage] Using application database: {display_database_url(database_url)}")
    return DatabaseStorageBackend(database_url)

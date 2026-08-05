from __future__ import annotations

from services.storage.base import (
    StorageBackend,
    StorageCapabilities,
    StorageMutation,
    StorageMutationResult,
    StorageRevisionConflictError,
    StorageSnapshot,
)
from services.storage.factory import create_storage_backend

__all__ = [
    "StorageBackend",
    "StorageCapabilities",
    "StorageMutation",
    "StorageMutationResult",
    "StorageRevisionConflictError",
    "StorageSnapshot",
    "create_storage_backend",
]

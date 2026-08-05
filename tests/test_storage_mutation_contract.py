from __future__ import annotations

import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from services.storage.base import (
    StorageBackend,
    StorageMutation,
    StorageRevisionConflictError,
)
from services.storage.database_storage import (
    AuthKeyModel,
    DatabaseStorageBackend,
)


class StorageMutationContractTests(unittest.TestCase):
    def _assert_mutation_contract(self, backend: StorageBackend) -> None:
        capabilities = backend.get_capabilities()
        self.assertTrue(capabilities.atomic_mutations)
        self.assertTrue(capabilities.compare_and_swap)
        self.assertTrue(capabilities.cross_process_safe)

        empty = backend.load_auth_keys_snapshot()
        first = {"id": "key-1", "name": "First", "role": "user"}
        created = backend.upsert_auth_key(first, expected_revision=empty.revision)
        self.assertEqual((created.inserted, created.updated, created.deleted), (1, 0, 0))
        self.assertNotEqual(created.revision, empty.revision)

        first["name"] = "Mutated by caller"
        self.assertEqual(backend.load_auth_keys()[0]["name"], "First")

        unchanged = backend.upsert_auth_key(
            {"id": "key-1", "name": "First", "role": "user"},
            expected_revision=created.revision,
        )
        self.assertFalse(unchanged.changed)
        self.assertEqual(unchanged.revision, created.revision)

        updated = backend.mutate_auth_keys(
            StorageMutation(
                upserts=(
                    {"id": "key-1", "name": "Renamed", "role": "user"},
                    {"id": "key-2", "name": "Second", "role": "admin"},
                ),
                expected_revision=unchanged.revision,
            )
        )
        self.assertEqual((updated.inserted, updated.updated, updated.deleted), (1, 1, 0))

        before_reorder = backend.load_auth_keys_snapshot()
        reordered = backend.replace_auth_keys(
            list(reversed(before_reorder.items)),
            expected_revision=before_reorder.revision,
        )
        self.assertFalse(reordered.changed)
        self.assertEqual(reordered.revision, before_reorder.revision)
        self.assertEqual(
            backend.load_auth_keys_snapshot().revision,
            before_reorder.revision,
        )

        with self.assertRaises(StorageRevisionConflictError):
            backend.delete_auth_key("key-1", expected_revision=empty.revision)
        self.assertEqual(
            {item["id"] for item in backend.load_auth_keys()},
            {"key-1", "key-2"},
        )

        deleted = backend.delete_auth_key(
            "key-1",
            expected_revision=updated.revision,
        )
        self.assertEqual((deleted.inserted, deleted.updated, deleted.deleted), (0, 0, 1))
        self.assertEqual([item["id"] for item in backend.load_auth_keys()], ["key-2"])

        account_snapshot = backend.load_accounts_snapshot()
        account_result = backend.upsert_account(
            {"access_token": "token-1", "status": "normal"},
            expected_revision=account_snapshot.revision,
        )
        self.assertEqual(account_result.inserted, 1)
        self.assertEqual(backend.load_accounts()[0]["access_token"], "token-1")

        with self.assertRaises(ValueError):
            backend.mutate_auth_keys(
                StorageMutation(
                    upserts=({"id": "same", "role": "user"},),
                    delete_keys=("same",),
                )
            )

    def test_database_adapter_satisfies_mutation_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "storage.db"
            backend = DatabaseStorageBackend(f"sqlite:///{database_path}")
            try:
                self._assert_mutation_contract(backend)
                self.assertTrue(backend.get_capabilities().transactional)
                self.assertFalse(backend.get_capabilities().distributed_safe)
            finally:
                backend.engine.dispose()

    def test_database_snapshot_replace_preserves_unchanged_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "storage.db"
            backend = DatabaseStorageBackend(f"sqlite:///{database_path}")
            try:
                backend.replace_auth_keys(
                    [
                        {"id": "key-1", "name": "First"},
                        {"id": "key-2", "name": "Second"},
                    ]
                )
                session = backend.Session()
                try:
                    original_ids = {
                        row.key_id: row.id for row in session.query(AuthKeyModel).all()
                    }
                finally:
                    session.close()

                backend.replace_auth_keys(
                    [
                        {"id": "key-1", "name": "Renamed"},
                        {"id": "key-2", "name": "Second"},
                        {"id": "key-3", "name": "Third"},
                    ]
                )
                session = backend.Session()
                try:
                    next_ids = {
                        row.key_id: row.id for row in session.query(AuthKeyModel).all()
                    }
                finally:
                    session.close()

                self.assertEqual(next_ids["key-1"], original_ids["key-1"])
                self.assertEqual(next_ids["key-2"], original_ids["key-2"])
            finally:
                backend.engine.dispose()

    def test_database_cas_allows_only_one_concurrent_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "storage.db"
            first = DatabaseStorageBackend(f"sqlite:///{database_path}")
            second = DatabaseStorageBackend(f"sqlite:///{database_path}")
            initial_revision = first.load_auth_keys_snapshot().revision
            barrier = threading.Barrier(2)

            def write(backend: DatabaseStorageBackend, key_id: str) -> str:
                barrier.wait(timeout=5)
                try:
                    backend.upsert_auth_key(
                        {"id": key_id, "role": "user"},
                        expected_revision=initial_revision,
                    )
                    return "applied"
                except StorageRevisionConflictError:
                    return "conflict"

            try:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(
                        executor.map(
                            lambda args: write(*args),
                            ((first, "key-1"), (second, "key-2")),
                        )
                    )
                self.assertCountEqual(results, ["applied", "conflict"])
                self.assertEqual(len(first.load_auth_keys()), 1)
            finally:
                first.engine.dispose()
                second.engine.dispose()

if __name__ == "__main__":
    unittest.main()

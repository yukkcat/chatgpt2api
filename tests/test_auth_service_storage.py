from __future__ import annotations

import hashlib
import tempfile
import threading
import unittest
from collections.abc import Callable
from pathlib import Path

from services.auth_service import AuthService
from services.storage.base import StorageMutation
from tests.support.account_repository import TestAccountRepository


def _stored_key(
    key_id: str,
    name: str,
    raw_key: str,
    *,
    enabled: bool = True,
) -> dict[str, object]:
    return {
        "id": key_id,
        "name": name,
        "role": "user",
        "key_hash": hashlib.sha256(raw_key.encode("utf-8")).hexdigest(),
        "enabled": enabled,
        "created_at": "2026-07-26T00:00:00+00:00",
        "last_used_at": None,
    }


class HookedTestAccountRepository(TestAccountRepository):
    def __init__(self, root: Path):
        super().__init__(root / "accounts.json", root / "auth_keys.json")
        self.before_next_auth_mutation: Callable[[HookedTestAccountRepository], None] | None = None
        self.auth_mutations: list[StorageMutation] = []
        self.compatibility_saves = 0
        self.snapshot_loads = 0
        self.block_next_snapshot = False
        self.block_after_next_snapshot = False
        self.snapshot_started = threading.Event()
        self.release_snapshot = threading.Event()
        self.fail_snapshot_loads = False

    def load_auth_keys_snapshot(self):  # type: ignore[no-untyped-def]
        self.snapshot_loads += 1
        if self.fail_snapshot_loads:
            raise OSError("snapshot unavailable")
        if self.block_next_snapshot:
            self.block_next_snapshot = False
            self.snapshot_started.set()
            if not self.release_snapshot.wait(timeout=5):
                raise TimeoutError("test snapshot was not released")
        snapshot = super().load_auth_keys_snapshot()
        if self.block_after_next_snapshot:
            self.block_after_next_snapshot = False
            self.snapshot_started.set()
            if not self.release_snapshot.wait(timeout=5):
                raise TimeoutError("test snapshot was not released")
        return snapshot

    def mutate_auth_keys(self, mutation: StorageMutation):  # type: ignore[no-untyped-def]
        self.auth_mutations.append(mutation)
        hook = self.before_next_auth_mutation
        self.before_next_auth_mutation = None
        if hook is not None:
            hook(self)
        return super().mutate_auth_keys(mutation)

    def mutate_directly(self, mutation: StorageMutation):  # type: ignore[no-untyped-def]
        return TestAccountRepository.mutate_auth_keys(self, mutation)

    def save_auth_keys(self, auth_keys: list[dict[str, object]]) -> None:
        self.compatibility_saves += 1
        super().save_auth_keys(auth_keys)


class AuthServiceStorageTests(unittest.TestCase):
    def test_crud_and_last_used_only_mutate_the_target_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = HookedTestAccountRepository(Path(temp_dir))
            service = AuthService(backend)

            created, raw_key = service.create_key(role="user", name="Studio")
            key_id = str(created["id"])
            updated = service.update_key(key_id, {"enabled": False}, role="user")
            self.assertIsNotNone(updated)
            service.update_key(key_id, {"enabled": True}, role="user")
            authenticated = service.authenticate(raw_key)
            deleted = service.delete_key(key_id, role="user")

            self.assertIsNotNone(authenticated)
            self.assertTrue(deleted)
            self.assertEqual(backend.compatibility_saves, 0)
            self.assertEqual(len(backend.auth_mutations), 5)
            for mutation in backend.auth_mutations[:4]:
                self.assertEqual(len(mutation.upserts), 1)
                self.assertEqual(mutation.delete_keys, ())
                self.assertEqual(mutation.upserts[0]["id"], key_id)
                self.assertIsNotNone(mutation.expected_revision)
            delete_mutation = backend.auth_mutations[4]
            self.assertEqual(delete_mutation.upserts, ())
            self.assertEqual(delete_mutation.delete_keys, (key_id,))
            self.assertIsNotNone(delete_mutation.expected_revision)

    def test_last_used_persistence_is_throttled_for_sixty_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = HookedTestAccountRepository(Path(temp_dir))
            raw_key = "sk-throttled"
            backend.replace_auth_keys([_stored_key("key-1", "Studio", raw_key)])
            service = AuthService(backend)

            self.assertIsNotNone(service.authenticate(raw_key))
            persisted_once = backend.load_auth_keys()[0]["last_used_at"]
            self.assertIsNotNone(service.authenticate(raw_key))

            self.assertEqual(len(backend.auth_mutations), 1)
            self.assertEqual(backend.load_auth_keys()[0]["last_used_at"], persisted_once)

    def test_authenticate_reuses_the_bounded_local_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = HookedTestAccountRepository(Path(temp_dir))
            raw_key = "sk-cached"
            backend.replace_auth_keys([_stored_key("key-1", "Studio", raw_key)])
            service = AuthService(backend)
            initial_loads = backend.snapshot_loads

            self.assertIsNotNone(service.authenticate(raw_key))
            self.assertIsNotNone(service.authenticate(raw_key))

            self.assertEqual(backend.snapshot_loads, initial_loads)

    def test_due_snapshot_refresh_does_not_hold_the_authentication_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = HookedTestAccountRepository(Path(temp_dir))
            raw_key = "sk-cached"
            backend.replace_auth_keys([_stored_key("key-1", "Studio", raw_key)])
            service = AuthService(backend)
            service._last_snapshot_refresh_attempt_at = 0.0
            backend.block_next_snapshot = True
            first_result: list[dict[str, object] | None] = []

            first = threading.Thread(
                target=lambda: first_result.append(service.authenticate(raw_key)),
                daemon=True,
            )
            first.start()
            self.assertTrue(backend.snapshot_started.wait(timeout=2))

            second = threading.Thread(
                target=lambda: first_result.append(service.authenticate(raw_key)),
                daemon=True,
            )
            second.start()
            second.join(timeout=1)

            self.assertFalse(second.is_alive())
            self.assertIsNotNone(first_result[0])
            backend.release_snapshot.set()
            first.join(timeout=2)
            self.assertFalse(first.is_alive())
            self.assertEqual(len(first_result), 2)

    def test_due_snapshot_refresh_observes_an_external_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = HookedTestAccountRepository(Path(temp_dir))
            raw_key = "sk-deleted"
            backend.replace_auth_keys([_stored_key("key-1", "Studio", raw_key)])
            service = AuthService(backend)
            backend.delete_auth_key("key-1")
            service._last_snapshot_refresh_attempt_at = 0.0

            self.assertIsNone(service.authenticate(raw_key))

    def test_expired_snapshot_fails_closed_when_refresh_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = HookedTestAccountRepository(Path(temp_dir))
            raw_key = "sk-revoked"
            backend.replace_auth_keys([_stored_key("key-1", "Studio", raw_key)])
            service = AuthService(backend)
            backend.delete_auth_key("key-1")
            backend.fail_snapshot_loads = True
            service._last_snapshot_refresh_attempt_at = 0.0
            service._last_snapshot_refresh_success_at = 0.0

            self.assertIsNone(service.authenticate(raw_key))

    def test_snapshot_refresh_does_not_overwrite_a_concurrent_local_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = HookedTestAccountRepository(Path(temp_dir))
            raw_key = "sk-existing"
            backend.replace_auth_keys([_stored_key("key-1", "Existing", raw_key)])
            service = AuthService(backend)
            self.assertIsNotNone(service.authenticate(raw_key))

            service._last_snapshot_refresh_attempt_at = 0.0
            backend.block_after_next_snapshot = True
            refresh_result: list[dict[str, object] | None] = []
            refresh = threading.Thread(
                target=lambda: refresh_result.append(service.authenticate(raw_key)),
                daemon=True,
            )
            refresh.start()
            self.assertTrue(backend.snapshot_started.wait(timeout=2))

            created, new_raw_key = service.create_key(role="user", name="Created locally")
            backend.release_snapshot.set()
            refresh.join(timeout=2)

            self.assertFalse(refresh.is_alive())
            self.assertIsNotNone(refresh_result[0])
            self.assertIsNotNone(service.authenticate(new_raw_key))
            self.assertIn(
                created["id"],
                {item["id"] for item in backend.load_auth_keys()},
            )

    def test_update_reloads_after_conflict_and_preserves_another_key_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = HookedTestAccountRepository(Path(temp_dir))
            first = _stored_key("key-1", "First", "sk-first")
            second = _stored_key("key-2", "Second", "sk-second")
            backend.replace_auth_keys([first, second])
            service = AuthService(backend)

            def update_other_key(storage: HookedTestAccountRepository) -> None:
                changed = dict(second)
                changed["name"] = "Changed elsewhere"
                storage.mutate_directly(StorageMutation(upserts=(changed,)))

            backend.before_next_auth_mutation = update_other_key
            updated = service.update_key("key-1", {"enabled": False}, role="user")

            self.assertIsNotNone(updated)
            stored = {item["id"]: item for item in backend.load_auth_keys()}
            self.assertFalse(stored["key-1"]["enabled"])
            self.assertEqual(stored["key-2"]["name"], "Changed elsewhere")
            self.assertEqual(len(backend.auth_mutations), 2)

    def test_name_uniqueness_is_revalidated_after_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = HookedTestAccountRepository(Path(temp_dir))
            first = _stored_key("key-1", "First", "sk-first")
            backend.replace_auth_keys([first])
            service = AuthService(backend)

            def insert_duplicate_name(storage: HookedTestAccountRepository) -> None:
                storage.mutate_directly(
                    StorageMutation(
                        upserts=(_stored_key("key-2", "Taken", "sk-second"),)
                    )
                )

            backend.before_next_auth_mutation = insert_duplicate_name
            with self.assertRaisesRegex(ValueError, "名称已经在使用"):
                service.update_key("key-1", {"name": "Taken"}, role="user")

            stored = {item["id"]: item for item in backend.load_auth_keys()}
            self.assertEqual(stored["key-1"]["name"], "First")
            self.assertEqual(stored["key-2"]["name"], "Taken")

    def test_key_hash_uniqueness_is_revalidated_after_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = HookedTestAccountRepository(Path(temp_dir))
            first = _stored_key("key-1", "First", "sk-first")
            second = _stored_key("key-2", "Second", "sk-second")
            backend.replace_auth_keys([first, second])
            service = AuthService(backend)
            replacement = "sk-replacement"

            def claim_replacement_key(storage: HookedTestAccountRepository) -> None:
                changed = dict(second)
                changed["key_hash"] = hashlib.sha256(replacement.encode("utf-8")).hexdigest()
                storage.mutate_directly(StorageMutation(upserts=(changed,)))

            backend.before_next_auth_mutation = claim_replacement_key
            with self.assertRaisesRegex(ValueError, "专用密钥已经存在"):
                service.update_key("key-1", {"key": replacement}, role="user")

            stored = {item["id"]: item for item in backend.load_auth_keys()}
            self.assertEqual(stored["key-1"]["key_hash"], first["key_hash"])
            self.assertEqual(
                stored["key-2"]["key_hash"],
                hashlib.sha256(replacement.encode("utf-8")).hexdigest(),
            )

    def test_stale_update_does_not_revive_a_concurrently_deleted_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = HookedTestAccountRepository(Path(temp_dir))
            backend.replace_auth_keys([_stored_key("key-1", "First", "sk-first")])
            service = AuthService(backend)

            backend.before_next_auth_mutation = lambda storage: storage.mutate_directly(
                StorageMutation(delete_keys=("key-1",))
            )
            updated = service.update_key("key-1", {"enabled": False}, role="user")

            self.assertIsNone(updated)
            self.assertEqual(backend.load_auth_keys(), [])

    def test_last_used_flush_does_not_revive_a_concurrently_deleted_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = HookedTestAccountRepository(Path(temp_dir))
            raw_key = "sk-first"
            backend.replace_auth_keys([_stored_key("key-1", "First", raw_key)])
            service = AuthService(backend)

            backend.before_next_auth_mutation = lambda storage: storage.mutate_directly(
                StorageMutation(delete_keys=("key-1",))
            )
            authenticated = service.authenticate(raw_key)

            self.assertIsNone(authenticated)
            self.assertEqual(backend.load_auth_keys(), [])

    def test_final_last_used_conflict_reloads_before_accepting_cached_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = HookedTestAccountRepository(Path(temp_dir))
            raw_key = "sk-first"
            first = _stored_key("key-1", "First", raw_key)
            other = _stored_key("key-2", "Other", "sk-other")
            backend.replace_auth_keys([first, other])
            service = AuthService(backend)
            conflict_count = 0

            def keep_conflicting(storage: HookedTestAccountRepository) -> None:
                nonlocal conflict_count
                conflict_count += 1
                if conflict_count < 4:
                    changed = dict(other)
                    changed["name"] = f"Other {conflict_count}"
                    storage.mutate_directly(StorageMutation(upserts=(changed,)))
                    storage.before_next_auth_mutation = keep_conflicting
                    return
                storage.mutate_directly(StorageMutation(delete_keys=("key-1",)))

            backend.before_next_auth_mutation = keep_conflicting

            self.assertIsNone(service.authenticate(raw_key))
            self.assertEqual(conflict_count, 4)
            self.assertNotIn(
                "key-1",
                {item["id"] for item in backend.load_auth_keys()},
            )


if __name__ == "__main__":
    unittest.main()

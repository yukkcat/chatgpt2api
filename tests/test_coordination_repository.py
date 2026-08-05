from __future__ import annotations

import threading
from pathlib import Path

import pytest

from services.storage.coordination_repository import (
    BackupExecutionStateRepository,
    RetentionCleanupRepository,
)


def _database_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'application.db').as_posix()}"


def test_coordination_domains_keep_independent_state(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    backup = BackupExecutionStateRepository(database_url)
    retention = RetentionCleanupRepository(database_url)

    backup.replace({"last_status": "success"})
    retention.replace({"wake_revision": 3})

    assert backup.load() == {"last_status": "success"}
    assert retention.load() == {"wake_revision": 3}


def test_state_edit_is_atomic_across_repository_instances(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    first = RetentionCleanupRepository(database_url)
    second = RetentionCleanupRepository(database_url)
    first.replace({"wake_revision": 0})

    def increment(repository: RetentionCleanupRepository) -> None:
        for _ in range(20):
            with repository.edit() as state:
                state["wake_revision"] = int(state.get("wake_revision") or 0) + 1

    threads = [
        threading.Thread(target=increment, args=(repository,))
        for repository in (first, second)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    assert all(not thread.is_alive() for thread in threads)
    assert first.load()["wake_revision"] == 40


def test_run_lock_excludes_other_repository_instances(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    first = RetentionCleanupRepository(database_url)
    second = RetentionCleanupRepository(database_url)

    with first.run_lock():
        with pytest.raises(TimeoutError):
            with second.run_lock(timeout_seconds=0):
                pass

    with second.run_lock(timeout_seconds=0):
        pass


def test_backup_and_retention_run_locks_are_independent(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    backup = BackupExecutionStateRepository(database_url)
    retention = RetentionCleanupRepository(database_url)

    with backup.run_lock(timeout_seconds=0):
        with retention.run_lock(timeout_seconds=0):
            pass


def test_scheduler_leader_lock_has_separate_ownership(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    first = RetentionCleanupRepository(database_url)
    second = RetentionCleanupRepository(database_url)

    with first.scheduler_leader_lock():
        with pytest.raises(TimeoutError):
            with second.scheduler_leader_lock():
                pass
        with second.run_lock(timeout_seconds=0):
            pass

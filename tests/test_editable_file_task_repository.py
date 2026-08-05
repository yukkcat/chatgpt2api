from __future__ import annotations

from pathlib import Path

from services.storage.editable_file_task_repository import EditableFileTaskRepository


def _database_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'application.db').as_posix()}"


def _task(*, owner_id: str = "user-1", task_id: str = "task-1", suffix: str = "1") -> dict[str, object]:
    return {
        "id": task_id,
        "storage_id": f"asset-00000000-0000-4000-8000-{suffix.zfill(12)}",
        "owner_id": owner_id,
        "status": "queued",
        "kind": "ppt",
        "model": "editable-file",
        "created_at": "2026-08-04 10:00:00",
        "updated_at": "2026-08-04 10:00:00",
        "created_ts": 1,
        "updated_ts": 1,
    }


def test_create_is_idempotent_per_owner_and_task_id(tmp_path: Path) -> None:
    repository = EditableFileTaskRepository(_database_url(tmp_path))

    first, created = repository.create(_task())
    duplicate, duplicate_created = repository.create(_task(suffix="2"))
    other_owner, other_created = repository.create(
        _task(owner_id="user-2", suffix="3")
    )

    assert created is True
    assert duplicate_created is False
    assert duplicate["storage_id"] == first["storage_id"]
    assert other_created is True
    assert other_owner["storage_id"] != first["storage_id"]


def test_owner_scoped_list_update_and_delete_are_shared(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    first = EditableFileTaskRepository(database_url)
    second = EditableFileTaskRepository(database_url)
    first.create(_task(task_id="older", suffix="1"))
    first.create(_task(task_id="newer", suffix="2"))
    first.create(_task(owner_id="user-2", task_id="hidden", suffix="3"))

    second.update(
        "user-1",
        "newer",
        status="success",
        updated_at="2026-08-04 11:00:00",
        updated_ts=2,
        result={"primary_url": "/files/result.pptx"},
    )

    assert [item["id"] for item in first.list_for_owner("user-1")] == ["newer", "older"]
    assert first.get("user-1", "newer")["result"] == {
        "primary_url": "/files/result.pptx"
    }
    assert second.delete("user-1", "newer") is True
    assert first.get("user-1", "newer") is None
    assert first.get("user-2", "hidden") is not None


def test_delete_pending_and_unfinished_queries_are_explicit(tmp_path: Path) -> None:
    repository = EditableFileTaskRepository(_database_url(tmp_path))
    repository.create(_task(task_id="queued", suffix="1"))
    repository.create(_task(task_id="pending", suffix="2"))
    repository.update("user-1", "pending", delete_pending=True)

    assert [item["id"] for item in repository.list_by_status({"queued", "running"})] == [
        "queued",
        "pending",
    ]
    assert [item["id"] for item in repository.list_delete_pending()] == ["pending"]

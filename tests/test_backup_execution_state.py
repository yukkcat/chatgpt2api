from __future__ import annotations

import io
import json
import sqlite3
import tarfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from services.backup_service import BackupError, BackupService
from services.storage.coordination_repository import BackupExecutionStateRepository


def _database_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'application.db').as_posix()}"


def test_successful_backup_persists_shared_execution_state(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    service = BackupService(database_url=database_url)

    with patch.object(
        service,
        "_run_backup_once",
        return_value={"key": "backups/example.tar.gz", "size": 3, "encrypted": False},
    ):
        result = service.run_backup()

    assert result["key"] == "backups/example.tar.gz"
    status = BackupService(database_url=database_url).get_status()
    assert status["running"] is False
    assert status["last_status"] == "success"
    assert status["last_object_key"] == "backups/example.tar.gz"
    assert status["last_started_at"]
    assert status["last_finished_at"]


def test_failed_backup_persists_error_without_losing_last_object(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    repository = BackupExecutionStateRepository(database_url)
    repository.replace({"last_status": "success", "last_object_key": "backups/old.tar.gz"})
    service = BackupService(repository=repository)

    with patch.object(service, "_run_backup_once", side_effect=RuntimeError("upload failed")):
        with pytest.raises(RuntimeError, match="upload failed"):
            service.run_backup()

    status = service.get_status()
    assert status["running"] is False
    assert status["last_status"] == "error"
    assert status["last_error"] == "upload failed"
    assert status["last_object_key"] == "backups/old.tar.gz"


def test_backup_run_lock_rejects_concurrent_process(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    service = BackupService(database_url=database_url)
    other = BackupExecutionStateRepository(database_url)

    with other.run_lock(timeout_seconds=0):
        with pytest.raises(BackupError, match="已有备份任务"):
            service.run_backup()


def test_service_recovers_execution_interrupted_by_restart(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    repository = BackupExecutionStateRepository(database_url)
    repository.replace({
        "last_started_at": "2026-08-04T00:00:00Z",
        "last_status": "running",
        "last_object_key": "backups/old.tar.gz",
    })

    status = BackupService(database_url=database_url).get_status()

    assert status["running"] is False
    assert status["last_status"] == "error"
    assert status["last_error"] == "备份执行被进程重启中断"
    assert status["last_object_key"] == "backups/old.tar.gz"


def test_sqlite_archive_always_contains_consistent_application_database(tmp_path: Path) -> None:
    service = BackupService(database_url=_database_url(tmp_path))

    payload = service._build_backup_archive(
        {"include": {"image_tasks": False, "editable_files": False, "images": False}},
        trigger="manual",
    )

    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        names = set(archive.getnames())
        metadata = json.loads(archive.extractfile("backup-metadata.json").read())
        database_bytes = archive.extractfile("data/application-database.sqlite3").read()

    assert metadata["version"] == 3
    assert metadata["database_backend"] == "sqlite"
    assert "data/application-database.sqlite3" in names
    assert not {
        "config.json",
        "data/cpa_config.json",
        "data/sub2api_config.json",
        "data/logs.jsonl",
        "data/dashboard_metrics.json",
        "snapshots/accounts.json",
        "snapshots/auth_keys.json",
    } & names

    snapshot_path = tmp_path / "snapshot.sqlite3"
    snapshot_path.write_bytes(database_bytes)
    with sqlite3.connect(snapshot_path) as connection:
        version = connection.execute(
            "SELECT version FROM application_schema_version WHERE id = 1"
        ).fetchone()
    assert version == (1,)


def test_postgresql_backup_uses_pg_dump_without_exposing_password_in_command(
    tmp_path: Path,
) -> None:
    service = BackupService(database_url=_database_url(tmp_path))
    service._repository.database_url = (
        "postgresql+psycopg2://app:secret@db.example:5433/chatgpt2api?sslmode=require"
    )

    with patch(
        "services.backup_service.subprocess.run",
        return_value=Mock(stdout=b"pg-dump", stderr=b""),
    ) as run:
        payload = service._postgresql_database_backup()

    assert payload == b"pg-dump"
    command = run.call_args.args[0]
    assert "secret" not in " ".join(command)
    assert command[-2:] == ["--dbname", "chatgpt2api"]
    assert run.call_args.kwargs["env"]["PGPASSWORD"] == "secret"
    assert run.call_args.kwargs["env"]["PGSSLMODE"] == "require"

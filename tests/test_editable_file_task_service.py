from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import ai
from services.editable_file_failure import EditableFileFailureError
from services.editable_file_task_service import (
    EditableFileTaskCleanupError,
    EditableFileTaskInvalidIdError,
    EditableFileTaskNotFoundError,
    EditableFileTaskNotTerminalError,
    EditableFileTaskService,
)
from services.image_failure import image_failure
from services.openai_backend_api import OpenAIBackendAPI


def _database_url(root: Path) -> str:
    return f"sqlite:///{(root / 'application.db').as_posix()}"


def _service(root: Path) -> EditableFileTaskService:
    return EditableFileTaskService(database_url=_database_url(root))


def _seed(service: EditableFileTaskService, tasks: list[dict[str, object]]) -> None:
    for task in tasks:
        service._repository.create(task)


class EditableFileTaskServiceTests(unittest.TestCase):
    def test_submit_rejects_unsafe_client_task_ids_before_creating_task(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _service(Path(temp_dir))

            for task_id in ("folder/task", ".", "..", "任务", "a" * 161):
                with self.subTest(task_id=task_id):
                    with self.assertRaises(EditableFileTaskInvalidIdError):
                        service.submit_ppt({"id": "user-1"}, client_task_id=task_id)

            self.assertEqual(service.list_tasks({"id": "user-1"}, [])["items"], [])

    def test_submit_uses_distinct_storage_ids_for_same_client_id_across_owners(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _service(root)

            with patch("services.editable_file_task_service.threading.Thread"):
                service.submit_ppt({"id": "user-1"}, client_task_id="shared.task-id_1")
                service.submit_ppt({"id": "user-2"}, client_task_id="shared.task-id_1")

            storage_ids = {
                task["storage_id"]
                for owner in ("user-1", "user-2")
                for task in service._repository.list_for_owner(owner)
            }
            self.assertEqual(len(storage_ids), 2)
            self.assertNotIn("shared.task-id_1", storage_ids)

    def test_service_does_not_import_legacy_json_task_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "editable_file_tasks.json"
            path.write_text('{"tasks": [{"id": "legacy"}]}', encoding="utf-8")
            service = _service(root)

            self.assertEqual(service.list_tasks({"id": "user-1"}, [])["items"], [])
            self.assertTrue(path.is_file())

    def test_list_tasks_returns_recent_owner_scoped_tasks_with_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tasks = [
                            {
                                "id": "owner-old",
                                "storage_id": "asset-00000000-0000-4000-8000-000000000001",
                                "owner_id": "user-1",
                                "status": "success",
                                "kind": "ppt",
                                "created_at": "2026-07-29 09:00:00",
                                "updated_at": "2026-07-29 09:00:00",
                                "created_ts": 1,
                                "updated_ts": 1,
                                "ended_ts": 2,
                                "result": {
                                    "conversation_id": "conversation-old",
                                    "primary_url": "/files/ppt/asset-00000000-0000-4000-8000-000000000001/result.pptx",
                                    "zip_url": "/files/ppt/asset-00000000-0000-4000-8000-000000000001/result.zip",
                                },
                            },
                            {
                                "id": "other-newest",
                                "storage_id": "asset-00000000-0000-4000-8000-000000000002",
                                "owner_id": "user-2",
                                "status": "success",
                                "kind": "ppt",
                                "created_at": "2026-07-29 12:00:00",
                                "updated_at": "2026-07-29 12:00:00",
                                "created_ts": 4,
                                "updated_ts": 4,
                                "ended_ts": 5,
                                "result": {
                                    "conversation_id": "conversation-other",
                                    "primary_url": "/files/ppt/asset-00000000-0000-4000-8000-000000000002/result.pptx",
                                    "zip_url": "/files/ppt/asset-00000000-0000-4000-8000-000000000002/result.zip",
                                },
                            },
                            {
                                "id": "owner-newest",
                                "storage_id": "asset-00000000-0000-4000-8000-000000000003",
                                "owner_id": "user-1",
                                "status": "success",
                                "kind": "psd",
                                "created_at": "2026-07-29 11:00:00",
                                "updated_at": "2026-07-29 11:00:00",
                                "created_ts": 3,
                                "updated_ts": 3,
                                "ended_ts": 4,
                                "result": {
                                    "conversation_id": "conversation-newest",
                                    "primary_url": "/files/psd/asset-00000000-0000-4000-8000-000000000003/result.psd",
                                    "zip_url": "/files/psd/asset-00000000-0000-4000-8000-000000000003/result.zip",
                                },
                            },
                            {
                                "id": "owner-middle",
                                "storage_id": "asset-00000000-0000-4000-8000-000000000004",
                                "owner_id": "user-1",
                                "status": "error",
                                "kind": "ppt",
                                "created_at": "2026-07-29 10:00:00",
                                "updated_at": "2026-07-29 10:00:00",
                                "created_ts": 2,
                                "updated_ts": 2,
                                "ended_ts": 3,
                                "error": "generation failed",
                            },
            ]
            service = _service(root)
            _seed(service, tasks)
            result = service.list_tasks({"id": "user-1"}, [], limit=2)

        self.assertEqual(
            [item["id"] for item in result["items"]],
            ["owner-newest", "owner-middle"],
        )
        for item in result["items"]:
            self.assertNotIn("taskId", item)
            self.assertNotIn("can_retry", item)
        self.assertEqual(result["missing_ids"], [])
        self.assertEqual(
            {
                "can_download": result["items"][0]["can_download"],
                "can_delete": result["items"][0]["can_delete"],
                "status_label": result["items"][0]["status_label"],
                "status_tone": result["items"][0]["status_tone"],
                "status_icon": result["items"][0]["status_icon"],
                "is_active": result["items"][0]["is_active"],
            },
            {
                "can_download": True,
                "can_delete": True,
                "status_label": "已完成",
                "status_tone": "success",
                "status_icon": "lucide:file-check-2",
                "is_active": False,
            },
        )
        self.assertEqual(
            {
                "can_download": result["items"][1]["can_download"],
                "can_delete": result["items"][1]["can_delete"],
                "status_label": result["items"][1]["status_label"],
                "status_tone": result["items"][1]["status_tone"],
                "status_icon": result["items"][1]["status_icon"],
                "is_active": result["items"][1]["is_active"],
            },
            {
                "can_download": False,
                "can_delete": True,
                "status_label": "失败",
                "status_tone": "danger",
                "status_icon": "lucide:circle-alert",
                "is_active": False,
            },
        )

    def test_delete_task_is_owner_scoped_and_removes_only_its_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_root = root / "files"
            tasks = [
                {
                    "id": "shared-client-id",
                    "storage_id": "asset-00000000-0000-4000-8000-000000000005",
                    "owner_id": "user-1",
                    "status": "success",
                    "kind": "ppt",
                    "created_at": "2026-07-29 10:00:00",
                    "updated_at": "2026-07-29 10:01:00",
                    "created_ts": 1,
                    "updated_ts": 2,
                    "ended_ts": 2,
                    "result": {
                        "conversation_id": "conversation-owner-1",
                        "primary_url": "/files/ppt/asset-00000000-0000-4000-8000-000000000005/result.pptx",
                        "zip_url": "/files/ppt/asset-00000000-0000-4000-8000-000000000005/result.zip",
                    },
                },
                {
                    "id": "shared-client-id",
                    "storage_id": "asset-00000000-0000-4000-8000-000000000006",
                    "owner_id": "user-2",
                    "status": "success",
                    "kind": "ppt",
                    "created_at": "2026-07-29 10:00:00",
                    "updated_at": "2026-07-29 10:01:00",
                    "created_ts": 1,
                    "updated_ts": 2,
                    "ended_ts": 2,
                    "result": {
                        "conversation_id": "conversation-owner-2",
                        "primary_url": "/files/ppt/asset-00000000-0000-4000-8000-000000000006/result.pptx",
                        "zip_url": "/files/ppt/asset-00000000-0000-4000-8000-000000000006/result.zip",
                    },
                },
            ]
            owner_dir = file_root / "ppt" / "asset-00000000-0000-4000-8000-000000000005"
            other_dir = file_root / "ppt" / "asset-00000000-0000-4000-8000-000000000006"
            owner_dir.mkdir(parents=True)
            other_dir.mkdir(parents=True)
            (owner_dir / "result.pptx").write_bytes(b"owner-1")
            (other_dir / "result.pptx").write_bytes(b"owner-2")

            with patch("services.editable_file_task_service.EDITABLE_FILE_ROOT", file_root):
                service = _service(root)
                _seed(service, tasks)
                with self.assertRaises(EditableFileTaskNotFoundError):
                    service.delete_task({"id": "user-3"}, "shared-client-id")

                result = service.delete_task({"id": "user-1"}, "shared-client-id")

                self.assertEqual(result, {"task_id": "shared-client-id", "deleted": True})
                self.assertFalse(owner_dir.exists())
                self.assertTrue(other_dir.exists())
                self.assertEqual(service.list_tasks({"id": "user-1"}, [])["items"], [])
                self.assertEqual(
                    [item["id"] for item in service.list_tasks({"id": "user-2"}, [])["items"]],
                    ["shared-client-id"],
                )

                reloaded = _service(root)
                self.assertEqual(reloaded.list_tasks({"id": "user-1"}, [])["items"], [])
                self.assertEqual(len(reloaded.list_tasks({"id": "user-2"}, [])["items"]), 1)

    def test_delete_task_rejects_running_task_and_keeps_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_root = root / "files"
            output_dir = file_root / "psd" / "asset-00000000-0000-4000-8000-000000000007"
            output_dir.mkdir(parents=True)
            (output_dir / "partial.psd").write_bytes(b"partial")

            with patch("services.editable_file_task_service.EDITABLE_FILE_ROOT", file_root):
                service = _service(root)
                _seed(service, [{
                        "id": "running-task",
                        "storage_id": "asset-00000000-0000-4000-8000-000000000007",
                        "owner_id": "user-1",
                        "status": "running",
                        "kind": "psd",
                        "created_at": "2026-07-29 10:00:00",
                        "updated_at": "2026-07-29 10:01:00",
                        "created_ts": 1,
                        "updated_ts": 2,
                }])

                with self.assertRaises(EditableFileTaskNotTerminalError):
                    service.delete_task({"id": "user-1"}, "running-task")

                self.assertTrue(output_dir.exists())
                item = service.list_tasks({"id": "user-1"}, ["running-task"])["items"][0]
                self.assertFalse(item["can_delete"])
                self.assertFalse(item["can_download"])
                self.assertEqual(item["status_label"], "生成中")
                self.assertEqual(item["status_tone"], "warning")
                self.assertEqual(item["status_icon"], "lucide:loader-circle")
                self.assertTrue(item["is_active"])

    def test_delete_task_keeps_record_when_artifact_cleanup_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_root = root / "files"
            task = {
                "id": "task-id",
                "storage_id": "asset-00000000-0000-4000-8000-00000000000a",
                "owner_id": "user-1",
                "status": "success",
                "kind": "ppt",
                "created_at": "2026-07-29 10:00:00",
                "updated_at": "2026-07-29 10:01:00",
                "created_ts": 1,
                "updated_ts": 2,
            }
            output_dir = file_root / "ppt" / "asset-00000000-0000-4000-8000-00000000000a"
            output_dir.mkdir(parents=True)
            (output_dir / "result.pptx").write_bytes(b"presentation")

            with (
                patch("services.editable_file_task_service.EDITABLE_FILE_ROOT", file_root),
                patch("services.editable_file_task_service.shutil.rmtree", side_effect=PermissionError("in use")),
            ):
                service = _service(root)
                _seed(service, [task])
                with self.assertRaises(EditableFileTaskCleanupError):
                    service.delete_task({"id": "user-1"}, "task-id")

                self.assertTrue(output_dir.exists())
                self.assertEqual(
                    [item["id"] for item in service.list_tasks({"id": "user-1"}, ["task-id"])["items"]],
                    ["task-id"],
                )

    def test_delete_task_can_retry_after_artifact_cleanup_conflict(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_root = root / "files"
            task = {
                "id": "task-id",
                "storage_id": "asset-00000000-0000-4000-8000-00000000000a",
                "owner_id": "user-1",
                "status": "success",
                "kind": "ppt",
                "created_at": "2026-07-29 10:00:00",
                "updated_at": "2026-07-29 10:01:00",
                "created_ts": 1,
                "updated_ts": 2,
                "result": {
                    "primary_url": "/files/ppt/asset-00000000-0000-4000-8000-00000000000a/result.pptx",
                },
            }
            output_dir = file_root / "ppt" / "asset-00000000-0000-4000-8000-00000000000a"
            output_dir.mkdir(parents=True)
            (output_dir / "result.pptx").write_bytes(b"presentation")

            with patch("services.editable_file_task_service.EDITABLE_FILE_ROOT", file_root):
                service = _service(root)
                _seed(service, [task])
                with (
                    patch(
                        "services.editable_file_task_service.shutil.rmtree",
                        side_effect=PermissionError("in use"),
                    ),
                    self.assertRaises(EditableFileTaskCleanupError),
                ):
                    service.delete_task({"id": "user-1"}, "task-id")

                pending = service.list_tasks({"id": "user-1"}, ["task-id"])["items"][0]
                result = service.delete_task({"id": "user-1"}, "task-id")

            self.assertFalse(pending["can_download"])
            self.assertEqual(result, {"task_id": "task-id", "deleted": True})
            self.assertFalse(output_dir.exists())
            self.assertEqual(service.list_tasks({"id": "user-1"}, [])["items"], [])

    def test_delete_task_does_not_touch_files_when_delete_marker_cannot_be_saved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_root = root / "files"
            task = {
                "id": "task-id",
                "storage_id": "asset-00000000-0000-4000-8000-00000000000a",
                "owner_id": "user-1",
                "status": "success",
                "kind": "ppt",
                "created_at": "2026-07-29 10:00:00",
                "updated_at": "2026-07-29 10:01:00",
                "created_ts": 1,
                "updated_ts": 2,
                "result": {
                    "primary_url": "/files/ppt/asset-00000000-0000-4000-8000-00000000000a/result.pptx",
                },
            }
            output_dir = file_root / "ppt" / "asset-00000000-0000-4000-8000-00000000000a"
            output_dir.mkdir(parents=True)
            (output_dir / "result.pptx").write_bytes(b"presentation")

            with patch("services.editable_file_task_service.EDITABLE_FILE_ROOT", file_root):
                service = _service(root)
                _seed(service, [task])
                with (
                    patch.object(service._repository, "update", side_effect=OSError("disk full")),
                    self.assertRaises(OSError),
                ):
                    service.delete_task({"id": "user-1"}, "task-id")

                item = service.list_tasks({"id": "user-1"}, ["task-id"])["items"][0]

            self.assertTrue(output_dir.is_dir())
            self.assertTrue(item["can_download"])

    def test_restart_finishes_delete_when_final_task_save_failed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_root = root / "files"
            task = {
                "id": "task-id",
                "storage_id": "asset-00000000-0000-4000-8000-00000000000a",
                "owner_id": "user-1",
                "status": "success",
                "kind": "ppt",
                "created_at": "2026-07-29 10:00:00",
                "updated_at": "2026-07-29 10:01:00",
                "created_ts": 1,
                "updated_ts": 2,
                "result": {
                    "primary_url": "/files/ppt/asset-00000000-0000-4000-8000-00000000000a/result.pptx",
                },
            }
            output_dir = file_root / "ppt" / "asset-00000000-0000-4000-8000-00000000000a"
            output_dir.mkdir(parents=True)
            (output_dir / "result.pptx").write_bytes(b"presentation")

            with patch("services.editable_file_task_service.EDITABLE_FILE_ROOT", file_root):
                service = _service(root)
                _seed(service, [task])

                with (
                    patch.object(service._repository, "delete", side_effect=OSError("disk full")),
                    self.assertRaises(OSError),
                ):
                    service.delete_task({"id": "user-1"}, "task-id")

                pending = service.list_tasks({"id": "user-1"}, ["task-id"])["items"][0]
                restarted = _service(root)

            self.assertFalse(output_dir.exists())
            self.assertFalse(pending["can_download"])
            self.assertEqual(restarted.list_tasks({"id": "user-1"}, [])["items"], [])

    def test_restart_marks_unfinished_task_failed_and_removes_unpublished_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_root = root / "files"
            task = {
                "id": "running-task",
                "storage_id": "asset-00000000-0000-4000-8000-000000000007",
                "owner_id": "user-1",
                "status": "running",
                "kind": "ppt",
                "created_at": "2026-07-29 10:00:00",
                "updated_at": "2026-07-29 10:01:00",
                "created_ts": 1,
                "updated_ts": 2,
            }
            staging_dir = file_root / ".staging" / "ppt" / "asset-00000000-0000-4000-8000-000000000007"
            output_dir = file_root / "ppt" / "asset-00000000-0000-4000-8000-000000000007"
            staging_dir.mkdir(parents=True)
            output_dir.mkdir(parents=True)
            (staging_dir / "partial.pptx").write_bytes(b"partial")
            (output_dir / "result.pptx").write_bytes(b"uncommitted")

            with patch("services.editable_file_task_service.EDITABLE_FILE_ROOT", file_root):
                seeder = _service(root)
                _seed(seeder, [task])
                service = _service(root)
                item = service.list_tasks({"id": "user-1"}, ["running-task"])["items"][0]

            self.assertEqual(item["status"], "error")
            self.assertFalse(staging_dir.exists())
            self.assertFalse(output_dir.exists())

    def test_public_file_path_serves_assets_without_task_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_root = root / "files"
            ppt_dir = file_root / "ppt" / "asset-00000000-0000-4000-8000-000000000008"
            psd_dir = file_root / "psd" / "asset-00000000-0000-4000-8000-000000000009"
            ppt_dir.mkdir(parents=True)
            psd_dir.mkdir(parents=True)
            ppt_path = ppt_dir / "result.pptx"
            zip_path = ppt_dir / "result.zip"
            psd_path = psd_dir / "result.psd"
            ppt_path.write_bytes(b"presentation")
            zip_path.write_bytes(b"archive")
            psd_path.write_bytes(b"photoshop")

            with patch("services.editable_file_task_service.EDITABLE_FILE_ROOT", file_root):
                service = _service(root)
                self.assertEqual(
                    service.public_file_path("ppt/asset-00000000-0000-4000-8000-000000000008/result.pptx"),
                    ppt_path.resolve(),
                )
                self.assertEqual(
                    service.public_file_path("ppt/asset-00000000-0000-4000-8000-000000000008/result.zip"),
                    zip_path.resolve(),
                )
                self.assertEqual(
                    service.public_file_path("psd/asset-00000000-0000-4000-8000-000000000009/result.psd"),
                    psd_path.resolve(),
                )

    def test_public_file_path_rejects_unsafe_or_unsupported_assets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_root = root / "files"
            output_dir = file_root / "ppt" / "asset-00000000-0000-4000-8000-00000000000a"
            output_dir.mkdir(parents=True)
            (output_dir / "notes.txt").write_bytes(b"private")
            (output_dir / "result.psd").write_bytes(b"wrong kind")
            (output_dir / "folder.pptx").mkdir()

            with patch("services.editable_file_task_service.EDITABLE_FILE_ROOT", file_root):
                service = _service(root)
                for rejected_path in (
                    "ppt/asset-00000000-0000-4000-8000-00000000000a/notes.txt",
                    "ppt/asset-00000000-0000-4000-8000-00000000000a/result.psd",
                    "ppt/asset-00000000-0000-4000-8000-00000000000a/missing.pptx",
                    "ppt/asset-00000000-0000-4000-8000-00000000000a/folder.pptx",
                    "ppt/asset-00000000-0000-4000-8000-00000000000a/nested/result.pptx",
                    "unknown/asset-00000000-0000-4000-8000-00000000000a/result.zip",
                    "ppt/invalid storage/result.pptx",
                    "ppt/" + "a" * 161 + "/result.pptx",
                    "ppt\\asset-00000000-0000-4000-8000-00000000000a\\result.pptx",
                    "ppt/asset-00000000-0000-4000-8000-00000000000a/result.pptx:secret.zip",
                    "ppt/asset-00000000-0000-4000-8000-00000000000a/CON.pptx",
                    "ppt/asset-00000000-0000-4000-8000-00000000000a/trailing.pptx.",
                    "ppt/asset-00000000-0000-4000-8000-00000000000a/trailing.pptx ",
                    "ppt/asset-00000000-0000-4000-8000-00000000000a/result\x00.pptx",
                    "../outside.txt",
                ):
                    with self.subTest(path=rejected_path):
                        with self.assertRaises(FileNotFoundError):
                            service.public_file_path(rejected_path)

    def test_public_file_path_maps_filesystem_errors_to_not_found(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_root = root / "files"
            output_dir = file_root / "ppt" / "asset-00000000-0000-4000-8000-00000000000a"
            output_dir.mkdir(parents=True)
            (output_dir / "result.pptx").write_bytes(b"presentation")

            with (
                patch("services.editable_file_task_service.EDITABLE_FILE_ROOT", file_root),
                patch.object(Path, "is_file", side_effect=OSError("unavailable")),
            ):
                service = _service(root)
                with self.assertRaises(FileNotFoundError):
                    service.public_file_path("ppt/asset-00000000-0000-4000-8000-00000000000a/result.pptx")

    def test_editable_filename_sanitizer_uses_public_asset_rules(self):
        self.assertEqual(
            OpenAIBackendAPI._sanitize_editable_filename("folder\\deck:final?.pptx"),
            "deck_final_.pptx",
        )
        self.assertEqual(
            OpenAIBackendAPI._sanitize_editable_filename("../CON.pptx"),
            "_CON.pptx",
        )

    def test_run_task_publishes_complete_artifacts_after_export(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_root = root / "files"
            service = _service(root)
            task = {
                "id": "task-id",
                "storage_id": "asset-00000000-0000-4000-8000-00000000000a",
                "owner_id": "user-1",
                "status": "queued",
                "kind": "ppt",
                "created_at": "2026-07-29 10:00:00",
                "updated_at": "2026-07-29 10:00:00",
                "created_ts": 1,
                "updated_ts": 1,
            }
            _seed(service, [task])

            def export_files(_images, _prompt, output_dir):
                export_dir = Path(output_dir)
                export_dir.mkdir(parents=True)
                primary_path = export_dir / "result.pptx"
                zip_path = export_dir / "result.zip"
                primary_path.write_bytes(b"presentation")
                zip_path.write_bytes(b"archive")
                return Mock(
                    conversation_id="conversation-id",
                    primary_path=primary_path,
                    zip_path=zip_path,
                )

            backend = Mock()
            backend.export_ppt_zip.side_effect = export_files
            backend_context = MagicMock()
            backend_context.__enter__.return_value = backend

            with (
                patch("services.editable_file_task_service.EDITABLE_FILE_ROOT", file_root),
                patch("services.editable_file_task_service._editable_access_token", return_value="token"),
                patch("services.editable_file_task_service.account_service.get_account", return_value={}),
                patch("services.editable_file_task_service.account_service.mark_text_used"),
                patch("services.editable_file_task_service.OpenAIBackendAPI", return_value=backend_context),
                patch.object(service, "_log_call"),
            ):
                service._run_task("user-1:task-id", "ppt", "prompt", [], {"id": "user-1"}, "")

                output_dir = file_root / "ppt" / "asset-00000000-0000-4000-8000-00000000000a"
                self.assertTrue((output_dir / "result.pptx").is_file())
                self.assertTrue((output_dir / "result.zip").is_file())
                self.assertFalse((file_root / ".staging" / "ppt" / "asset-00000000-0000-4000-8000-00000000000a").exists())
                item = service.list_tasks({"id": "user-1"}, ["task-id"])["items"][0]

            self.assertEqual(item["status"], "success")
            self.assertEqual(item["result"]["primary_url"], "/files/ppt/asset-00000000-0000-4000-8000-00000000000a/result.pptx")
            self.assertEqual(item["result"]["zip_url"], "/files/ppt/asset-00000000-0000-4000-8000-00000000000a/result.zip")

    def test_run_task_removes_partial_staging_after_export_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_root = root / "files"
            service = _service(root)
            task = {
                "id": "task-id",
                "storage_id": "asset-00000000-0000-4000-8000-00000000000a",
                "owner_id": "user-1",
                "status": "queued",
                "kind": "ppt",
                "created_at": "2026-07-29 10:00:00",
                "updated_at": "2026-07-29 10:00:00",
                "created_ts": 1,
                "updated_ts": 1,
            }
            _seed(service, [task])

            def fail_after_partial_download(_images, _prompt, output_dir):
                export_dir = Path(output_dir)
                export_dir.mkdir(parents=True)
                (export_dir / "partial.pptx").write_bytes(b"partial")
                raise RuntimeError("zip download failed")

            backend = Mock()
            backend.export_ppt_zip.side_effect = fail_after_partial_download
            backend_context = MagicMock()
            backend_context.__enter__.return_value = backend

            with (
                patch("services.editable_file_task_service.EDITABLE_FILE_ROOT", file_root),
                patch("services.editable_file_task_service._editable_access_token", return_value="token"),
                patch("services.editable_file_task_service.account_service.get_account", return_value={}),
                patch("services.editable_file_task_service.OpenAIBackendAPI", return_value=backend_context),
                patch.object(service, "_log_call"),
            ):
                service._run_task("user-1:task-id", "ppt", "prompt", [], {"id": "user-1"}, "")

                self.assertFalse((file_root / ".staging" / "ppt" / "asset-00000000-0000-4000-8000-00000000000a").exists())
                self.assertFalse((file_root / "ppt" / "asset-00000000-0000-4000-8000-00000000000a").exists())
                item = service.list_tasks({"id": "user-1"}, ["task-id"])["items"][0]

            self.assertEqual(item["status"], "error")
            self.assertEqual(item["error"], "zip download failed")

    def test_run_task_persists_editable_file_error_projection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_root = root / "files"
            service = _service(root)
            _seed(service, [{
                    "id": "task-id",
                    "storage_id": "asset-00000000-0000-4000-8000-00000000000a",
                    "owner_id": "user-1",
                    "status": "queued",
                    "kind": "ppt",
                    "created_at": "2026-07-29 10:00:00",
                    "updated_at": "2026-07-29 10:00:00",
                    "created_ts": 1,
                    "updated_ts": 1,
            }])

            backend = Mock()
            backend.export_ppt_zip.side_effect = EditableFileFailureError(
                failure=image_failure("auth_invalid")
            )
            backend_context = MagicMock()
            backend_context.__enter__.return_value = backend

            with (
                patch("services.editable_file_task_service.EDITABLE_FILE_ROOT", file_root),
                patch("services.editable_file_task_service._editable_access_token", return_value="token"),
                patch("services.editable_file_task_service.account_service.get_account", return_value={}),
                patch("services.editable_file_task_service.OpenAIBackendAPI", return_value=backend_context),
                patch.object(service, "_log_call"),
            ):
                service._run_task(
                    "user-1:task-id",
                    "ppt",
                    "prompt",
                    [],
                    {"id": "user-1"},
                    "",
                )
                item = service.list_tasks({"id": "user-1"}, ["task-id"])["items"][0]

            self.assertEqual(item["status"], "error")
            self.assertIn("editable file", item["error"].lower())
            self.assertNotIn("image generation", item["error"].lower())


class EditableFileTaskApiTests(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(ai.create_router())
        self.client = TestClient(app)
        self.identity = {"id": "user-1", "name": "User 1", "role": "user"}

    def test_delete_passes_authenticated_owner_to_service(self):
        service = Mock()
        service.delete_task.return_value = {"task_id": "task-1", "deleted": True}

        with (
            patch.object(ai, "require_identity", return_value=self.identity),
            patch.object(ai, "editable_file_task_service", service),
        ):
            response = self.client.delete(
                "/v1/editable-file-tasks/task-1",
                headers={"Authorization": "Bearer test-key"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"task_id": "task-1", "deleted": True})
        service.delete_task.assert_called_once_with(self.identity, "task-1")

    def test_delete_hides_tasks_owned_by_another_identity(self):
        service = Mock()
        service.delete_task.side_effect = EditableFileTaskNotFoundError(
            "editable file task not found"
        )

        with (
            patch.object(ai, "require_identity", return_value=self.identity),
            patch.object(ai, "editable_file_task_service", service),
        ):
            response = self.client.delete("/v1/editable-file-tasks/other-task")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {"detail": {"error": "editable file task not found"}},
        )

    def test_delete_rejects_non_terminal_task(self):
        service = Mock()
        service.delete_task.side_effect = EditableFileTaskNotTerminalError(
            "editable file task is not terminal"
        )

        with (
            patch.object(ai, "require_identity", return_value=self.identity),
            patch.object(ai, "editable_file_task_service", service),
        ):
            response = self.client.delete("/v1/editable-file-tasks/running-task")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {"detail": {"error": "editable file task is not terminal"}},
        )

    def test_delete_reports_artifact_cleanup_conflict(self):
        service = Mock()
        service.delete_task.side_effect = EditableFileTaskCleanupError(
            "editable file task files could not be removed"
        )

        with (
            patch.object(ai, "require_identity", return_value=self.identity),
            patch.object(ai, "editable_file_task_service", service),
        ):
            response = self.client.delete("/v1/editable-file-tasks/task-id")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {"detail": {"error": "editable file task files could not be removed"}},
        )

    def test_create_rejects_unsafe_client_task_id(self):
        service = Mock()
        service.submit_ppt.side_effect = EditableFileTaskInvalidIdError(
            "client_task_id must use safe characters"
        )

        with (
            patch.object(ai, "require_identity", return_value=self.identity),
            patch.object(ai, "filter_or_log", new=AsyncMock()),
            patch.object(ai, "editable_file_task_service", service),
        ):
            response = self.client.post(
                "/v1/editable-file-tasks",
                json={"kind": "ppt", "client_task_id": "folder/task"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"detail": {"error": "client_task_id must use safe characters"}},
        )

    def test_download_is_public_and_resolves_file_asset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result_path = Path(temp_dir) / "result.pptx"
            result_path.write_bytes(b"presentation")
            service = Mock()
            service.public_file_path.return_value = result_path

            with patch.object(ai, "editable_file_task_service", service):
                response = self.client.get("/files/ppt/asset-00000000-0000-4000-8000-00000000000a/result.pptx")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"presentation")
        service.public_file_path.assert_called_once_with(
            "ppt/asset-00000000-0000-4000-8000-00000000000a/result.pptx",
        )

    def test_download_returns_404_for_missing_file(self):
        service = Mock()
        service.public_file_path.side_effect = FileNotFoundError("result.pptx")

        with patch.object(ai, "editable_file_task_service", service):
            response = self.client.get("/files/ppt/asset-00000000-0000-4000-8000-00000000000a/result.pptx")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": {"error": "file not found"}})

if __name__ == "__main__":
    unittest.main()

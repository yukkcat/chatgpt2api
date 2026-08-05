from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

from api import image_tasks
from services.bounded_task_runner import BoundedTaskRunner
from services.image_task_service import ImageTaskQueueFullError, ImageTaskService
from services.storage.file_lock import interprocess_lock


class ImageTaskQueueTests(unittest.TestCase):
    def test_queue_full_rejects_new_task_without_persisting_it(self) -> None:
        started = threading.Event()
        release = threading.Event()
        completed = threading.Event()
        calls = 0
        calls_lock = threading.Lock()

        def handler(_: dict[str, object]) -> dict[str, object]:
            nonlocal calls
            with calls_lock:
                calls += 1
                call_number = calls
            if call_number == 1:
                started.set()
                release.wait(timeout=2)
            if call_number == 2:
                completed.set()
            return {"data": [{"url": f"https://example.test/{call_number}.png"}]}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image_tasks.json"
            runner = BoundedTaskRunner(name="image-test", max_workers=1, queue_size=1)
            service = ImageTaskService(path, generation_handler=handler, task_runner=runner)
            service._log_call = lambda *args, **kwargs: None  # type: ignore[method-assign]
            identity = {"id": "admin", "name": "Admin", "role": "admin"}

            service.submit_generation(identity, client_task_id="first", prompt="one", model="gpt-image-2")
            self.assertTrue(started.wait(timeout=1))
            service.submit_generation(identity, client_task_id="second", prompt="two", model="gpt-image-2")
            with self.assertRaises(ImageTaskQueueFullError):
                service.submit_generation(identity, client_task_id="third", prompt="three", model="gpt-image-2")

            stored_ids = {
                item["id"]
                for item in json.loads(path.read_text(encoding="utf-8"))["tasks"]
            }
            self.assertEqual(stored_ids, {"first", "second"})
            missing_page = service.list_tasks(identity, ["third"])
            self.assertEqual(missing_page["items"], [])
            self.assertEqual(missing_page["missing_ids"], ["third"])

            release.set()
            self.assertTrue(completed.wait(timeout=1))
            service.shutdown(wait=True)

    def test_queued_task_records_real_handler_queue_time(self) -> None:
        first_started = threading.Event()
        release = threading.Event()
        second_completed = threading.Event()
        logged_perf: list[dict[str, int]] = []
        calls = 0
        calls_lock = threading.Lock()

        def handler(_: dict[str, object]) -> dict[str, object]:
            nonlocal calls
            with calls_lock:
                calls += 1
                call_number = calls
            if call_number == 1:
                first_started.set()
                release.wait(timeout=2)
            else:
                second_completed.set()
            return {"data": [{"url": f"https://example.test/{call_number}.png"}]}

        with tempfile.TemporaryDirectory() as directory:
            runner = BoundedTaskRunner(name="image-test", max_workers=1, queue_size=1)
            service = ImageTaskService(
                Path(directory) / "image_tasks.json",
                generation_handler=handler,
                task_runner=runner,
            )

            def record_log(*args: object, **kwargs: object) -> None:
                perf = kwargs.get("perf")
                if isinstance(perf, dict):
                    logged_perf.append(perf)

            service._log_call = record_log  # type: ignore[method-assign]
            identity = {"id": "admin", "name": "Admin", "role": "admin"}
            service.submit_generation(identity, client_task_id="first", prompt="one", model="gpt-image-2")
            self.assertTrue(first_started.wait(timeout=1))
            service.submit_generation(identity, client_task_id="second", prompt="two", model="gpt-image-2")
            time.sleep(0.03)
            release.set()
            self.assertTrue(second_completed.wait(timeout=1))
            service.shutdown(wait=True)

            self.assertEqual(len(logged_perf), 2)
            self.assertGreaterEqual(logged_perf[1]["handler_queue_ms"], 20)

    def test_queued_edit_payload_is_spooled_and_removed_after_execution(self) -> None:
        first_started = threading.Event()
        release = threading.Event()
        edit_completed = threading.Event()
        received_images: list[tuple[bytes, str, str]] = []

        def generation_handler(_: dict[str, object]) -> dict[str, object]:
            first_started.set()
            release.wait(timeout=2)
            return {"data": [{"url": "https://example.test/generated.png"}]}

        def edit_handler(payload: dict[str, object]) -> dict[str, object]:
            received_images.extend(payload.get("images") or [])  # type: ignore[arg-type]
            edit_completed.set()
            return {"data": [{"url": "https://example.test/edited.png"}]}

        with tempfile.TemporaryDirectory() as directory:
            runner = BoundedTaskRunner(name="image-test", max_workers=1, queue_size=1)
            service = ImageTaskService(
                Path(directory) / "image_tasks.json",
                generation_handler=generation_handler,
                edit_handler=edit_handler,
                task_runner=runner,
            )
            service._log_call = lambda *args, **kwargs: None  # type: ignore[method-assign]
            identity = {"id": "admin", "name": "Admin", "role": "admin"}

            service.submit_generation(identity, client_task_id="first", prompt="one", model="gpt-image-2")
            self.assertTrue(first_started.wait(timeout=1))
            service.submit_edit(
                identity,
                client_task_id="edit",
                prompt="edit",
                model="gpt-image-2",
                images=[(b"queued-image", "source.png", "image/png")],
            )

            spool_files = list(service._spool_root.rglob("*.bin"))
            self.assertEqual(len(spool_files), 1)
            self.assertEqual(spool_files[0].read_bytes(), b"queued-image")

            release.set()
            self.assertTrue(edit_completed.wait(timeout=1))
            service.shutdown(wait=True)
            self.assertEqual(received_images, [(b"queued-image", "source.png", "image/png")])
            self.assertFalse(service._spool_root.exists())

    def test_task_save_failure_never_runs_or_leaves_in_memory_task(self) -> None:
        handler_called = threading.Event()

        def handler(_: dict[str, object]) -> dict[str, object]:
            handler_called.set()
            return {"data": [{"url": "https://example.test/unexpected.png"}]}

        with tempfile.TemporaryDirectory() as directory:
            runner = BoundedTaskRunner(name="image-test", max_workers=1, queue_size=1)
            service = ImageTaskService(
                Path(directory) / "image_tasks.json",
                generation_handler=handler,
                task_runner=runner,
            )
            identity = {"id": "admin", "name": "Admin", "role": "admin"}

            with patch.object(service, "_save_locked", side_effect=OSError("disk unavailable")):
                with self.assertRaisesRegex(OSError, "disk unavailable"):
                    service.submit_generation(
                        identity,
                        client_task_id="not-persisted",
                        prompt="one",
                        model="gpt-image-2",
                    )

            service.shutdown(wait=True)
            self.assertFalse(handler_called.is_set())
            self.assertNotIn("admin:not-persisted", service._tasks)

    def test_shutdown_during_initial_persist_never_starts_handler(self) -> None:
        save_started = threading.Event()
        allow_save = threading.Event()
        handler_called = threading.Event()
        submit_errors: list[BaseException] = []

        def handler(_: dict[str, object]) -> dict[str, object]:
            handler_called.set()
            return {"data": [{"url": "https://example.test/unexpected.png"}]}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image_tasks.json"
            runner = BoundedTaskRunner(name="image-test", max_workers=1, queue_size=1)
            service = ImageTaskService(path, generation_handler=handler, task_runner=runner)
            original_save = service._save_locked
            save_calls = 0

            def blocking_first_save() -> None:
                nonlocal save_calls
                save_calls += 1
                if save_calls == 1:
                    save_started.set()
                    allow_save.wait(timeout=2)
                original_save()

            service._save_locked = blocking_first_save  # type: ignore[method-assign]

            def submit() -> None:
                try:
                    service.submit_generation(
                        {"id": "admin"},
                        client_task_id="shutdown-race",
                        prompt="one",
                        model="gpt-image-2",
                    )
                except BaseException as exc:
                    submit_errors.append(exc)

            submit_thread = threading.Thread(target=submit)
            submit_thread.start()
            self.assertTrue(save_started.wait(timeout=1))
            shutdown_thread = threading.Thread(
                target=service.shutdown,
                kwargs={"wait": False},
            )
            shutdown_thread.start()
            try:
                deadline = time.time() + 1
                while time.time() < deadline and not runner.status()["closed"]:
                    time.sleep(0.01)
                self.assertTrue(runner.status()["closed"])
            finally:
                allow_save.set()
            submit_thread.join(timeout=1)
            shutdown_thread.join(timeout=1)
            service.shutdown(wait=True)

            self.assertFalse(submit_thread.is_alive())
            self.assertFalse(shutdown_thread.is_alive())
            self.assertFalse(handler_called.is_set())
            self.assertEqual(len(submit_errors), 1)
            self.assertIsInstance(submit_errors[0], ImageTaskQueueFullError)
            self.assertNotIn("admin:shutdown-race", service._tasks)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["tasks"], [])

    def test_non_waiting_shutdown_persists_all_queued_cancellations_once(self) -> None:
        active_started = threading.Event()
        release_active = threading.Event()

        def handler(payload: dict[str, object]) -> dict[str, object]:
            if payload.get("prompt") == "active":
                active_started.set()
                release_active.wait(timeout=2)
            return {"data": [{"url": "https://example.test/image.png"}]}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image_tasks.json"
            runner = BoundedTaskRunner(name="image-test", max_workers=1, queue_size=5)
            service = ImageTaskService(path, generation_handler=handler, task_runner=runner)
            service._log_call = lambda *args, **kwargs: None  # type: ignore[method-assign]
            identity = {"id": "admin", "name": "Admin", "role": "admin"}

            service.submit_generation(
                identity,
                client_task_id="active",
                prompt="active",
                model="gpt-image-2",
            )
            self.assertTrue(active_started.wait(timeout=1))
            for index in range(5):
                service.submit_generation(
                    identity,
                    client_task_id=f"queued-{index}",
                    prompt="queued",
                    model="gpt-image-2",
                )

            original_save = service._save_locked
            shutdown_save_calls = 0

            def counted_save() -> None:
                nonlocal shutdown_save_calls
                shutdown_save_calls += 1
                original_save()

            service._save_locked = counted_save  # type: ignore[method-assign]
            service.shutdown(wait=False)

            self.assertEqual(shutdown_save_calls, 1)
            for index in range(5):
                task = service._tasks[f"admin:queued-{index}"]
                self.assertEqual(task["status"], "error")
                self.assertEqual(task["error_code"], "task_interrupted")

            stored = {
                item["id"]: item
                for item in json.loads(path.read_text(encoding="utf-8"))["tasks"]
            }
            for index in range(5):
                self.assertEqual(stored[f"queued-{index}"]["status"], "error")
                self.assertEqual(stored[f"queued-{index}"]["error_code"], "task_interrupted")

            release_active.set()
            service.shutdown(wait=True)

    def test_cancel_pending_and_wait_finishes_active_and_releases_spool(self) -> None:
        active_started = threading.Event()
        release_active = threading.Event()

        def generation_handler(payload: dict[str, object]) -> dict[str, object]:
            self.assertEqual(payload.get("prompt"), "active")
            active_started.set()
            release_active.wait(timeout=2)
            return {"data": [{"url": "https://example.test/active.png"}]}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image_tasks.json"
            runner = BoundedTaskRunner(name="image-test", max_workers=1, queue_size=1)
            service = ImageTaskService(
                path,
                generation_handler=generation_handler,
                task_runner=runner,
            )
            service._log_call = lambda *args, **kwargs: None  # type: ignore[method-assign]
            identity = {"id": "admin", "name": "Admin", "role": "admin"}

            service.submit_generation(
                identity,
                client_task_id="active",
                prompt="active",
                model="gpt-image-2",
            )
            self.assertTrue(active_started.wait(timeout=1))
            service.submit_edit(
                identity,
                client_task_id="queued-edit",
                prompt="queued",
                model="gpt-image-2",
                images=[(b"queued-image", "source.png", "image/png")],
            )
            self.assertEqual(len(list(service._spool_root.rglob("*.bin"))), 1)

            shutdown_thread = threading.Thread(target=service.shutdown_cancel_pending_and_wait)
            shutdown_thread.start()
            deadline = time.time() + 1
            while time.time() < deadline:
                queued = service.list_tasks(identity, ["queued-edit"])["items"][0]
                if queued["status"] == "failed":
                    break
                time.sleep(0.01)

            self.assertTrue(shutdown_thread.is_alive())
            self.assertEqual(queued["status"], "failed")
            self.assertEqual(queued["error_code"], "task_interrupted")

            release_active.set()
            shutdown_thread.join(timeout=1)

            self.assertFalse(shutdown_thread.is_alive())
            rows = {
                item["id"]: item
                for item in service.list_tasks(identity, ["active", "queued-edit"])["items"]
            }
            self.assertEqual(rows["active"]["status"], "success")
            self.assertEqual(rows["queued-edit"]["status"], "failed")
            self.assertEqual(service.runtime_status()["active"], 0)
            self.assertFalse(service._spool_root.exists())

    def test_unexpected_worker_failure_marks_task_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = BoundedTaskRunner(name="image-test", max_workers=1, queue_size=1)
            service = ImageTaskService(Path(directory) / "image_tasks.json", task_runner=runner)
            identity = {"id": "admin", "name": "Admin", "role": "admin"}

            with patch.object(service, "_run_task", side_effect=RuntimeError("lifecycle failed")):
                service.submit_generation(
                    identity,
                    client_task_id="worker-failure",
                    prompt="one",
                    model="gpt-image-2",
                )
                deadline = time.time() + 1
                while time.time() < deadline:
                    row = service.list_tasks(identity, ["worker-failure"])["items"][0]
                    if row["status"] == "failed":
                        break
                    time.sleep(0.01)

            service.shutdown(wait=True)
            row = service.list_tasks(identity, ["worker-failure"])["items"][0]
            self.assertEqual(row["status"], "failed")

    def test_resume_queue_full_keeps_original_timeout_state(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def blocking_task() -> None:
            started.set()
            release.wait(timeout=2)

        with tempfile.TemporaryDirectory() as directory:
            runner = BoundedTaskRunner(name="image-test", max_workers=1, queue_size=1)
            service = ImageTaskService(Path(directory) / "image_tasks.json", task_runner=runner)
            identity = {"id": "admin", "name": "Admin", "role": "admin"}
            key = "admin:timed-out"
            with service._lock:
                service._tasks[key] = {
                    "id": "timed-out",
                    "owner_id": "admin",
                    "status": "error",
                    "mode": "generate",
                    "model": "gpt-image-2",
                    "n": 1,
                    "size": "",
                    "quality": "auto",
                    "created_at": "2026-01-01 00:00:00",
                    "updated_at": "2026-01-01 00:00:00",
                    "error": "timeout",
                    "error_code": "image_poll_timeout",
                    "conversation_id": "conversation-1",
                }
                service._save_locked()

            self.assertTrue(runner.submit(blocking_task))
            self.assertTrue(started.wait(timeout=1))
            self.assertTrue(runner.submit(lambda: None))
            with self.assertRaises(ImageTaskQueueFullError):
                service.resume_poll(identity, "timed-out")

            with service._lock:
                self.assertEqual(service._tasks[key]["status"], "error")
                self.assertEqual(service._tasks[key]["error_code"], "image_poll_timeout")
            release.set()
            service.shutdown(wait=True)

    def test_resume_persist_failure_releases_reserved_capacity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image_tasks.json"
            runner = BoundedTaskRunner(name="image-test", max_workers=1, queue_size=1)
            service = ImageTaskService(path, task_runner=runner)
            identity = {"id": "admin", "name": "Admin", "role": "admin"}
            key = "admin:timed-out"
            with service._lock:
                service._tasks[key] = {
                    "id": "timed-out",
                    "owner_id": "admin",
                    "status": "error",
                    "mode": "generate",
                    "model": "gpt-image-2",
                    "n": 1,
                    "size": "",
                    "quality": "auto",
                    "created_at": "2026-01-01 00:00:00",
                    "updated_at": "2026-01-01 00:00:00",
                    "error": "timeout",
                    "error_code": "image_poll_timeout",
                    "conversation_id": "conversation-1",
                }
                service._save_locked()

            with patch.object(service, "_save_locked", side_effect=OSError("disk unavailable")):
                with self.assertRaisesRegex(OSError, "disk unavailable"):
                    service.resume_poll(identity, "timed-out")

            status = runner.status()
            self.assertEqual(status["reserved"], 0)
            self.assertEqual(status["accepted"], 0)
            with service._lock:
                self.assertEqual(service._tasks[key]["status"], "error")
                self.assertEqual(service._tasks[key]["error_code"], "image_poll_timeout")
            service.shutdown(wait=True)

    def test_spool_cleanup_removes_only_roots_without_a_live_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image_tasks.json"
            spool_parent = path.parent / "image_task_spool"
            spool_parent.mkdir()
            active_root = spool_parent / f"{path.stem}-active"
            stale_root = spool_parent / f"{path.stem}-stale"
            legacy_root = spool_parent / f"{path.stem}-legacy"
            for root in (active_root, stale_root, legacy_root):
                root.mkdir()
                (root / "payload.bin").write_bytes(root.name.encode("utf-8"))

            stale_owner = interprocess_lock(stale_root / ".owner.lock", timeout_seconds=0)
            stale_owner.__enter__()
            stale_owner.__exit__(None, None, None)

            ready_path = Path(directory) / "owner-ready"
            owner_script = """
from pathlib import Path
import sys
from services.storage.file_lock import interprocess_lock

with interprocess_lock(Path(sys.argv[1]), timeout_seconds=2):
    Path(sys.argv[2]).write_text("ready", encoding="utf-8")
    sys.stdin.read(1)
"""
            owner_process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    owner_script,
                    str(active_root / ".owner.lock"),
                    str(ready_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.time() + 3
                while time.time() < deadline and not ready_path.exists():
                    if owner_process.poll() is not None:
                        _, stderr = owner_process.communicate()
                        self.fail(f"spool owner process exited early: {stderr}")
                    time.sleep(0.01)
                self.assertTrue(ready_path.exists(), "spool owner process did not acquire its lock")

                service = ImageTaskService(path)
                try:
                    self.assertTrue(active_root.exists())
                    self.assertFalse(stale_root.exists())
                    self.assertTrue(legacy_root.exists())
                finally:
                    service.shutdown(wait=True)
            finally:
                if (
                    owner_process.poll() is None
                    and owner_process.stdin is not None
                    and not owner_process.stdin.closed
                ):
                    try:
                        owner_process.stdin.write("x")
                        owner_process.stdin.flush()
                    except (BrokenPipeError, OSError):
                        pass
                try:
                    owner_process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    owner_process.kill()
                    owner_process.communicate()


class ImageTaskQueueHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_queue_full_maps_to_structured_503(self) -> None:
        app = FastAPI()
        app.include_router(image_tasks.create_router())
        transport = httpx.ASGITransport(app=app)
        with (
            patch("api.image_tasks.require_identity", return_value={"id": "admin"}),
            patch("api.image_tasks.filter_or_log", new=AsyncMock()),
            patch(
                "api.image_tasks.run_in_threadpool",
                new=AsyncMock(side_effect=ImageTaskQueueFullError()),
            ),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/image-tasks/generations",
                    json={
                        "client_task_id": "full",
                        "prompt": "test",
                        "model": "gpt-image-2",
                    },
                )

        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["code"], "image_task_queue_full")

    async def test_edit_queue_is_reserved_before_image_sources_are_read(self) -> None:
        app = FastAPI()
        app.include_router(image_tasks.create_router())
        transport = httpx.ASGITransport(app=app)
        with (
            patch("api.image_tasks.require_identity", return_value={"id": "admin"}),
            patch("api.image_tasks.filter_or_log", new=AsyncMock()),
            patch.object(
                image_tasks.image_task_service,
                "reserve_submission",
                side_effect=ImageTaskQueueFullError(),
            ),
            patch("api.image_tasks.read_image_sources", new=AsyncMock()) as read_sources,
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/image-tasks/edits",
                    json={
                        "client_task_id": "full-edit",
                        "prompt": "test",
                        "model": "gpt-image-2",
                        "image_url": "https://example.test/source.png",
                    },
                )

        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["code"], "image_task_queue_full")
        read_sources.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

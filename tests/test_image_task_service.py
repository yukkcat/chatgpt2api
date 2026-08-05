from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from services.image_failure import (
    IMAGE_TIMEOUT_PUBLIC_MESSAGE,
    IMAGE_TOOL_ERROR_PUBLIC_MESSAGE,
    ImageGenerationError,
    ImagePollTimeoutError,
    image_failure,
)
from services.image_task_service import ImageTaskService
from services.log_service import _image_error_response
from services.protocol.conversation import ImageOutput


RAW_POLL_TIMEOUT = "opaque upstream polling diagnostic"


def poll_timeout_error(message: str = RAW_POLL_TIMEOUT) -> ImageGenerationError:
    return ImageGenerationError(
        message,
        failure=image_failure("image_poll_timeout"),
        conversation_id="conversation-1",
        raw_error=message,
        upstream_error="upstream image queue timed out",
    )


def wait_for_terminal_task(
    service: ImageTaskService,
    identity: dict[str, object],
    task_id: str,
    *,
    timeout: float = 2.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    task: dict[str, object] = {}
    while time.monotonic() < deadline:
        items = service.list_tasks(identity, [task_id])["items"]
        if items:
            task = items[0]
            if task.get("terminal") is True:
                return task
        time.sleep(0.01)
    raise AssertionError(f"image task {task_id!r} did not finish: {task!r}")


class FailingResumeBackend:
    def __init__(self, message: str) -> None:
        self.message = message
        self.closed = False

    def _poll_image_results(self, _conversation_id: str, _timeout_secs: float):
        raise ImagePollTimeoutError(self.message)

    def close(self) -> None:
        self.closed = True


class ImageTaskPublicErrorTests(unittest.TestCase):
    def test_running_task_exposes_completed_images_before_batch_finishes(self) -> None:
        first_image_ready = threading.Event()
        finish_batch = threading.Event()

        def image_outputs(_request):
            yield ImageOutput(
                kind="result",
                model="gpt-image-2",
                index=1,
                total=2,
                data=[{"url": "/images/first.png"}],
            )
            first_image_ready.set()
            finish_batch.wait(timeout=2)
            yield ImageOutput(
                kind="result",
                model="gpt-image-2",
                index=2,
                total=2,
                data=[{"url": "/images/second.png"}],
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            service = ImageTaskService(Path(temp_dir) / "image_tasks.json")
            with (
                mock.patch(
                    "services.protocol.openai_v1_image_generations.stream_image_outputs_with_pool",
                    side_effect=image_outputs,
                ),
                mock.patch.object(service, "_log_call"),
                mock.patch("services.log_service.log_service.add"),
                mock.patch("services.image_task_service.realtime_monitor_service.start"),
                mock.patch("services.image_task_service.realtime_monitor_service.stage"),
            ):
                identity = {"id": "owner-1", "name": "Owner", "role": "admin"}
                try:
                    service.submit_generation(
                        identity,
                        client_task_id="task-partial",
                        prompt="draw two lighthouses",
                        model="gpt-image-2",
                        n=2,
                    )
                    self.assertTrue(first_image_ready.wait(timeout=1))

                    running = service.list_tasks(identity, ["task-partial"])["items"][0]
                    self.assertEqual(running["status"], "running")
                    self.assertFalse(running["terminal"])
                    self.assertEqual(
                        [item["url"] for item in running["results"]],
                        ["/images/first.png"],
                    )
                    self.assertEqual(running["requested_count"], 2)
                    self.assertEqual(running["succeeded_count"], 1)
                    self.assertEqual(running["pending_count"], 1)

                    finish_batch.set()
                    completed = wait_for_terminal_task(service, identity, "task-partial")

                    self.assertEqual(completed["status"], "success")
                    self.assertTrue(completed["terminal"])
                    self.assertEqual(
                        [item["url"] for item in completed["results"]],
                        ["/images/first.png", "/images/second.png"],
                    )
                    self.assertEqual(completed["succeeded_count"], 2)
                    self.assertEqual(completed["failed_count"], 0)
                finally:
                    finish_batch.set()
                    service.shutdown(wait=True)

    def test_service_restart_preserves_current_public_upstream_text(self) -> None:
        upstream_text = (
            "You've hit the Free plan limit for image generations requests. "
            "You can create more images when the limit resets in 2 hours."
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            task_path = Path(temp_dir) / "image_tasks.json"
            task_path.write_text(
                json.dumps({
                    "tasks": [{
                        "id": "task-current-message",
                        "owner_id": "owner-1",
                        "status": "error",
                        "mode": "generate",
                        "error": upstream_text,
                        "error_code": "image_tool_error",
                        "error_message_version": 1,
                    }]
                }),
                encoding="utf-8",
            )

            service = ImageTaskService(task_path)
            try:
                task = service.list_tasks(
                    {"id": "owner-1"},
                    ["task-current-message"],
                )["items"][0]
                persisted_task = json.loads(task_path.read_text(encoding="utf-8"))["tasks"][0]
            finally:
                service.shutdown(wait=True)

            self.assertEqual(task["public_error"], upstream_text)
            self.assertEqual(persisted_task["error"], upstream_text)

    def test_service_startup_migrates_legacy_fixed_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_path = Path(temp_dir) / "image_tasks.json"
            task_path.write_text(
                json.dumps({
                    "tasks": [{
                        "id": "task-legacy-message",
                        "owner_id": "owner-1",
                        "status": "error",
                        "mode": "generate",
                        "error": "The upstream service returned text instead of an image.",
                        "error_code": "upstream_text_reply",
                    }]
                }),
                encoding="utf-8",
            )

            service = ImageTaskService(task_path)
            try:
                persisted_task = json.loads(task_path.read_text(encoding="utf-8"))["tasks"][0]
            finally:
                service.shutdown(wait=True)
            self.assertEqual(persisted_task["error"], IMAGE_TOOL_ERROR_PUBLIC_MESSAGE)
            self.assertEqual(persisted_task["error_message_version"], 1)

    def test_service_startup_normalizes_stored_error_and_removes_private_details(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_path = Path(temp_dir) / "image_tasks.json"
            task_path.write_text(
                json.dumps({
                    "tasks": [{
                        "id": "task-legacy",
                        "owner_id": "owner-1",
                        "status": "error",
                        "mode": "generate",
                        "error": "legacy raw upstream timeout body",
                        "error_code": "image_poll_timeout",
                        "raw_error": "legacy private diagnostic",
                        "upstream_error": "legacy upstream response",
                    }]
                }),
                encoding="utf-8",
            )

            service = ImageTaskService(task_path)
            try:
                persisted_task = json.loads(task_path.read_text(encoding="utf-8"))["tasks"][0]
            finally:
                service.shutdown(wait=True)
            self.assertEqual(persisted_task["error_code"], "image_poll_timeout")
            self.assertEqual(persisted_task["error"], IMAGE_TIMEOUT_PUBLIC_MESSAGE)
            self.assertNotIn("raw_error", persisted_task)
            self.assertNotIn("upstream_error", persisted_task)

    def test_service_startup_normalizes_legacy_error_without_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_path = Path(temp_dir) / "image_tasks.json"
            task_path.write_text(
                json.dumps({
                    "tasks": [{
                        "id": "task-legacy-no-code",
                        "owner_id": "owner-1",
                        "status": "error",
                        "mode": "generate",
                        "error": "legacy raw upstream response",
                    }]
                }),
                encoding="utf-8",
            )

            service = ImageTaskService(task_path)
            try:
                persisted_task = json.loads(task_path.read_text(encoding="utf-8"))["tasks"][0]
            finally:
                service.shutdown(wait=True)
            self.assertEqual(persisted_task["error_code"], "upstream_error")
            self.assertEqual(persisted_task["error"], IMAGE_TOOL_ERROR_PUBLIC_MESSAGE)

    def test_service_restart_uses_structured_cancellation_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ImageTaskService(
                Path(temp_dir) / "image_tasks.json",
                generation_handler=lambda _body: {"data": []},
            )
            try:
                service._tasks = {
                    "owner-1:task-running": {
                        "id": "task-running",
                        "owner_id": "owner-1",
                        "status": "running",
                    }
                }

                changed = service._recover_unfinished_locked()
                task = service._tasks["owner-1:task-running"]
            finally:
                service.shutdown(wait=True)

            self.assertTrue(changed)
            self.assertEqual(task["status"], "error")
            self.assertEqual(task["error_code"], "task_interrupted")
            self.assertEqual(task["error"], IMAGE_TOOL_ERROR_PUBLIC_MESSAGE)

    def test_empty_result_is_not_misreported_as_account_quota_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ImageTaskService(
                Path(temp_dir) / "image_tasks.json",
                generation_handler=lambda _body: {"data": []},
            )
            with (
                mock.patch.object(service, "_log_call"),
                mock.patch("services.log_service.log_service.add"),
                mock.patch("services.image_task_service.realtime_monitor_service.start"),
                mock.patch("services.image_task_service.realtime_monitor_service.stage"),
            ):
                identity = {"id": "owner-1", "name": "Owner", "role": "admin"}
                try:
                    service.submit_generation(
                        identity,
                        client_task_id="task-empty",
                        prompt="draw a lighthouse",
                        model="gpt-image-2",
                    )
                    task = wait_for_terminal_task(service, identity, "task-empty")
                finally:
                    service.shutdown(wait=True)

            self.assertEqual(task["status"], "failed")
            self.assertEqual(task["error_code"], "no_image_generated")
            self.assertEqual(task["public_error"], IMAGE_TOOL_ERROR_PUBLIC_MESSAGE)

    def test_background_task_matches_openai_error_and_hides_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_path = Path(temp_dir) / "image_tasks.json"
            service = ImageTaskService(
                task_path,
                generation_handler=lambda _body: (_ for _ in ()).throw(poll_timeout_error()),
            )
            with (
                mock.patch.object(service, "_log_call") as log_call,
                mock.patch("services.log_service.log_service.add"),
                mock.patch("services.image_task_service.realtime_monitor_service.start"),
                mock.patch("services.image_task_service.realtime_monitor_service.stage"),
            ):
                identity = {"id": "owner-1", "name": "Owner", "role": "admin"}
                try:
                    service.submit_generation(
                        identity,
                        client_task_id="task-1",
                        prompt="draw a lighthouse",
                        model="gpt-image-2",
                    )
                    task = wait_for_terminal_task(service, identity, "task-1")
                    response = _image_error_response(poll_timeout_error())
                    api_error = json.loads(response.body)["error"]
                finally:
                    service.shutdown(wait=True)

            self.assertEqual(task["status"], "failed")
            self.assertEqual(task["public_error"], api_error["message"])
            self.assertEqual(task["error_code"], "image_poll_timeout")
            self.assertTrue(task["actions"]["resume_poll"])
            self.assertEqual(response.status_code, 502)
            self.assertNotIn("raw_error", task)
            self.assertNotIn("upstream_error", task)
            logged_details = log_call.call_args.kwargs["extra"]
            self.assertEqual(log_call.call_args.kwargs["error"], api_error["message"])
            self.assertEqual(logged_details["public_error"], api_error["message"])
            self.assertEqual(logged_details["status_code"], response.status_code)
            self.assertEqual(logged_details["error_type"], api_error["type"])
            self.assertTrue(logged_details["failure_account_failure"])
            self.assertEqual(logged_details["raw_error"], RAW_POLL_TIMEOUT)
            self.assertEqual(logged_details["upstream_error"], "upstream image queue timed out")
            persisted_task = json.loads(task_path.read_text(encoding="utf-8"))["tasks"][0]
            self.assertNotIn("raw_error", persisted_task)
            self.assertNotIn("upstream_error", persisted_task)

    def test_resume_poll_failure_remains_structurally_resumable(self) -> None:
        backend = FailingResumeBackend("continued polling returned no image result")
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ImageTaskService(
                Path(temp_dir) / "image_tasks.json",
                generation_handler=lambda _body: (_ for _ in ()).throw(poll_timeout_error()),
            )
            with (
                mock.patch("services.openai_backend_api.OpenAIBackendAPI", return_value=backend),
                mock.patch.object(service, "_log_call"),
                mock.patch("services.log_service.log_service.add"),
                mock.patch("services.image_task_service.realtime_monitor_service.start"),
                mock.patch("services.image_task_service.realtime_monitor_service.stage"),
            ):
                identity = {"id": "owner-1", "name": "Owner", "role": "admin"}
                try:
                    service.submit_generation(
                        identity,
                        client_task_id="task-1",
                        prompt="draw a lighthouse",
                        model="gpt-image-2",
                    )
                    wait_for_terminal_task(service, identity, "task-1")
                    service.resume_poll(identity, "task-1", 30)
                    task = wait_for_terminal_task(service, identity, "task-1")
                finally:
                    service.shutdown(wait=True)

            self.assertEqual(task["status"], "failed")
            self.assertEqual(task["error_code"], "image_poll_timeout")
            self.assertTrue(task["actions"]["resume_poll"])
            self.assertNotIn("raw_error", task)
            self.assertTrue(backend.closed)

    def test_natural_language_does_not_change_public_error_classification(self) -> None:
        response = _image_error_response(RuntimeError("insufficient_quota"))
        payload = json.loads(response.body)["error"]

        self.assertEqual(response.status_code, 500)
        self.assertEqual(payload["code"], "internal_error")
        self.assertEqual(payload["message"], IMAGE_TOOL_ERROR_PUBLIC_MESSAGE)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pydantic import ValidationError

from api.image_tasks import create_router
from api.image_task_contract import ImageTaskAsset, ImageTaskPage, ImageTaskRow
from services.bounded_task_runner import BoundedTaskRunner
from services.image_failure import ImageGenerationError, image_failure
from services.image_task_service import ImageTaskService
from services.image_task_view import image_task_page, image_task_row


class ImageTaskProjectionTests(unittest.TestCase):
    def test_projects_all_six_public_states_from_structured_fields(self) -> None:
        cases = (
            ({"status": "queued"}, "queued", False, "排队中"),
            ({"status": "running", "progress": "generating"}, "running", False, "上游生成中"),
            ({"status": "success", "data": [{"url": "/one.png"}]}, "success", True, "成功"),
            (
                {"status": "success", "n": 2, "data": [{"url": "/one.png"}]},
                "partial_success",
                True,
                "部分成功",
            ),
            ({"status": "error", "error_code": "image_poll_timeout"}, "failed", True, "失败"),
            ({"status": "error", "error_code": "upstream_text_reply"}, "text_review", True, "文本"),
        )

        for index, (raw, expected_status, terminal, stage_label) in enumerate(cases):
            with self.subTest(expected_status=expected_status):
                row = image_task_row({"id": f"task-{index}", **raw}, now_ts=100)
                self.assertEqual(row["status"], expected_status)
                self.assertEqual(row["terminal"], terminal)
                self.assertEqual(row["stage_label"], stage_label)
                ImageTaskRow.model_validate(row)

        status_code_row = image_task_row({
            "id": "task-status-code",
            "status": "error",
            "status_code": "400",
            "error_code": "unknown_code",
        })
        self.assertEqual(status_code_row["status"], "text_review")

    def test_counts_partial_results_without_treating_empty_assets_as_success(self) -> None:
        running = image_task_row({
            "id": "running",
            "status": "running",
            "n": 3,
            "data": [
                {},
                {"revised_prompt": "metadata only", "width": 1024},
                {"unknown": "not an image"},
                {"path": "stored-image.png"},
                {"url": "/one.png"},
            ],
        })
        self.assertEqual(running["succeeded_count"], 1)
        self.assertEqual(running["failed_count"], 0)
        self.assertEqual(running["pending_count"], 2)

        failed_empty_success = image_task_row({
            "id": "empty-success",
            "status": "success",
            "n": 2,
            "data": [{}, {"revised_prompt": "metadata only"}],
        })
        self.assertEqual(failed_empty_success["status"], "failed")
        self.assertEqual(failed_empty_success["succeeded_count"], 0)
        self.assertEqual(failed_empty_success["failed_count"], 2)
        self.assertEqual(failed_empty_success["pending_count"], 0)

        text_review = image_task_row({
            "id": "text-review",
            "status": "error",
            "n": 4,
            "error_code": "content_policy_violation",
        })
        self.assertEqual(text_review["failed_count"], 0)
        self.assertEqual(text_review["pending_count"], 0)

        capped = image_task_row({
            "id": "capped",
            "status": "success",
            "n": 99,
            "data": [{"url": f"/{index}.png"} for index in range(6)],
        })
        self.assertEqual(capped["requested_count"], 4)
        self.assertEqual(capped["succeeded_count"], 4)
        self.assertEqual(len(capped["results"]), 4)

    def test_elapsed_time_uses_state_specific_structured_timestamps(self) -> None:
        queued = image_task_row({
            "id": "queued",
            "status": "queued",
            "created_ts": 90.0,
        }, now_ts=100.0)
        running = image_task_row({
            "id": "running",
            "status": "running",
            "started_ts": 95.5,
            "updated_ts": 99.0,
            "created_ts": 80.0,
        }, now_ts=100.0)
        running_without_start = image_task_row({
            "id": "running-without-start",
            "status": "running",
            "updated_ts": 97.0,
            "created_ts": 80.0,
            "duration_ms": 12_345,
        }, now_ts=100.0)
        terminal = image_task_row({
            "id": "terminal",
            "status": "success",
            "duration_ms": 4321,
            "data": [{"url": "/done.png"}],
        }, now_ts=100.0)

        self.assertEqual(queued["elapsed_ms"], 10_000)
        self.assertEqual(running["elapsed_ms"], 4_500)
        self.assertIsNone(running_without_start["elapsed_ms"])
        self.assertEqual(terminal["duration_ms"], 4321)
        self.assertEqual(terminal["elapsed_ms"], 4321)

    def test_resume_poll_action_requires_a_failed_projected_state(self) -> None:
        failed = image_task_row({
            "id": "failed",
            "status": "error",
            "error_code": "image_poll_timeout",
            "can_resume_poll": True,
        })
        text_review = image_task_row({
            "id": "text",
            "status": "error",
            "error_code": "upstream_text_reply",
            "can_resume_poll": True,
        })
        running = image_task_row({
            "id": "running",
            "status": "running",
            "can_resume_poll": True,
        })

        self.assertTrue(failed["actions"]["resume_poll"])
        self.assertFalse(text_review["actions"]["resume_poll"])
        self.assertFalse(running["actions"]["resume_poll"])

    def test_assets_and_rows_have_stable_strict_field_whitelists(self) -> None:
        page = image_task_page(
            [{
                "id": "asset-task",
                "status": "success",
                "mode": "edit",
                "data": [{
                    "b64_json": "YWJj",
                    "width": "1024",
                    "private": "must not escape",
                }],
                "private_task_field": "must not escape",
            }],
            missing_ids=["missing", "missing", ""],
        )
        validated = ImageTaskPage.model_validate(page)
        row = page["items"][0]
        asset = row["results"][0]

        self.assertEqual(set(page), set(ImageTaskPage.model_fields))
        self.assertEqual(set(row), set(ImageTaskRow.model_fields))
        self.assertEqual(set(asset), set(ImageTaskAsset.model_fields))
        self.assertEqual(asset, {
            "url": "",
            "path": "",
            "b64_json": "YWJj",
            "revised_prompt": "",
            "width": 1024,
            "height": None,
        })
        self.assertEqual(validated.missing_ids, ["missing"])

        with self.assertRaises(ValidationError):
            ImageTaskAsset.model_validate({"url": "/one.png", "private": True})
        with self.assertRaises(ValidationError):
            ImageTaskRow.model_validate({**row, "private": True})


class ImageTaskServiceContractTests(unittest.TestCase):
    def test_list_is_owner_scoped_and_reports_foreign_ids_as_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ImageTaskService(Path(temp_dir) / "image_tasks.json")
            try:
                service._tasks = {
                    "owner-1:owned": {
                        "id": "owned",
                        "owner_id": "owner-1",
                        "status": "running",
                        "n": 1,
                    },
                    "owner-2:foreign": {
                        "id": "foreign",
                        "owner_id": "owner-2",
                        "status": "running",
                        "n": 1,
                    },
                }

                page = service.list_tasks(
                    {"id": "owner-1"},
                    ["owned", "foreign", "missing"],
                )
            finally:
                service.shutdown(wait=True)

        self.assertEqual([item["id"] for item in page["items"]], ["owned"])
        self.assertEqual(page["missing_ids"], ["foreign", "missing"])
        ImageTaskPage.model_validate(page)

    def test_create_and_list_share_the_same_row_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = BoundedTaskRunner(
                name="image-task-contract-test",
                max_workers=1,
                queue_size=1,
            )
            service = ImageTaskService(
                Path(temp_dir) / "image_tasks.json",
                generation_handler=lambda _body: {"data": [{"url": "/result.png"}]},
                task_runner=runner,
            )
            try:
                with (
                    mock.patch.object(service, "_log_call"),
                    mock.patch("services.image_task_service.realtime_monitor_service.start"),
                    mock.patch("services.image_task_service.realtime_monitor_service.stage"),
                ):
                    created = service.submit_generation(
                        {"id": "owner-1", "name": "Owner", "role": "admin"},
                        client_task_id="task-success",
                        prompt="draw a lighthouse",
                        model="gpt-image-2",
                    )
                    service.shutdown(wait=True)
                listed = service.list_tasks({"id": "owner-1"}, ["task-success"])["items"][0]
            finally:
                service.shutdown(wait=True)

        ImageTaskRow.model_validate(created)
        for field in ("id", "mode", "model", "requested_count"):
            self.assertEqual(created[field], listed[field])
        self.assertEqual(listed["status"], "success")
        ImageTaskRow.model_validate(listed)

    def test_submit_projects_partial_success_and_structured_text_review(self) -> None:
        text_error = ImageGenerationError(
            "Please revise the request.",
            failure=image_failure(
                "upstream_text_reply",
                raw_detail="Please revise the request.",
            ),
        )
        cases = (
            (
                lambda _body: {"data": [{"url": "/one.png"}]},
                2,
                "partial_success",
            ),
            (
                lambda _body: (_ for _ in ()).throw(text_error),
                1,
                "text_review",
            ),
        )

        for index, (handler, count, expected_status) in enumerate(cases):
            with self.subTest(expected_status=expected_status), tempfile.TemporaryDirectory() as temp_dir:
                runner = BoundedTaskRunner(
                    name=f"image-task-contract-test-{index}",
                    max_workers=1,
                    queue_size=1,
                )
                service = ImageTaskService(
                    Path(temp_dir) / "image_tasks.json",
                    generation_handler=handler,
                    task_runner=runner,
                )
                try:
                    with (
                        mock.patch.object(service, "_log_call"),
                        mock.patch("services.image_task_service.realtime_monitor_service.start"),
                        mock.patch("services.image_task_service.realtime_monitor_service.stage"),
                    ):
                        service.submit_generation(
                            {"id": "owner-1", "name": "Owner", "role": "admin"},
                            client_task_id=f"task-{index}",
                            prompt="draw a lighthouse",
                            model="gpt-image-2",
                            n=count,
                        )
                        service.shutdown(wait=True)
                    row = service.list_tasks({"id": "owner-1"}, [f"task-{index}"])["items"][0]
                finally:
                    service.shutdown(wait=True)

                self.assertEqual(row["status"], expected_status)
                self.assertTrue(row["terminal"])
                ImageTaskRow.model_validate(row)

    def test_router_publishes_task_models(self) -> None:
        routes = {
            (route.path, method): route.response_model
            for route in create_router().routes
            for method in route.methods
        }
        self.assertIs(routes[("/api/image-tasks", "GET")], ImageTaskPage)
        self.assertIs(routes[("/api/image-tasks/generations", "POST")], ImageTaskRow)
        self.assertIs(routes[("/api/image-tasks/edits", "POST")], ImageTaskRow)
        self.assertIs(routes[("/api/image-tasks/{task_id}/resume-poll", "POST")], ImageTaskRow)


if __name__ == "__main__":
    unittest.main()

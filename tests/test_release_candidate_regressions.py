from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from contracts.proxy import ProxyGroupPatch, ProxyNodeInput
from services.account_service import AccountService
from services.dashboard_metrics_service import DashboardMetricsService
from services.image_failure import image_failure
from services.log_service import (
    LOG_TYPE_CALL,
    LogService,
    LoggedCall,
)
from services.prompt_library_service import PromptLibraryService
from services.proxy_management_service import ProxyManagementService
from services.protocol import (
    conversation,
    openai_v1_chat_complete,
    openai_v1_image_generations,
    openai_v1_response,
)
from tests.support.account_repository import TestAccountRepository
from services.storage.prompt_library_repository import PromptLibraryRepository
from utils.timezone import beijing_now


class StructuredLogContractTests(unittest.TestCase):
    @staticmethod
    def _image_call() -> LoggedCall:
        return LoggedCall(
            {"id": "test-key", "name": "Test key", "role": "user"},
            "/v1/images/generations",
            "gpt-image-2",
            "文生图",
        )

    def test_image_success_uses_stable_summary_and_structured_result_fields(self) -> None:
        call = self._image_call()
        result = {
            "data": [{"url": "https://example.test/image.png"}],
        }

        with (
            patch("services.log_service.realtime_monitor_service.finish"),
            patch("services.log_service.log_service.add") as add_log,
        ):
            call.log("调用完成", result)

        add_log.assert_called_once()
        log_type, summary, detail = add_log.call_args.args
        self.assertEqual(log_type, LOG_TYPE_CALL)
        self.assertEqual(summary, "文生图调用完成")
        self.assertEqual(detail["status"], "success")
        self.assertEqual(detail["result_data_count"], 1)
        self.assertEqual(detail["result_url_count"], 1)

    def test_image_rate_limit_failure_keeps_stable_summary_and_429_fields(self) -> None:
        call = self._image_call()

        with (
            patch("services.log_service.realtime_monitor_service.finish"),
            patch("services.log_service.log_service.add") as add_log,
        ):
            call.log(
                "调用失败",
                status="failed",
                error="upstream rate limited",
                extra={
                    "status_code": 429,
                    "error_code": "upstream_rate_limited",
                },
            )

        add_log.assert_called_once()
        log_type, summary, detail = add_log.call_args.args
        self.assertEqual(log_type, LOG_TYPE_CALL)
        self.assertEqual(summary, "文生图调用失败")
        self.assertEqual(detail["status"], "failed")
        self.assertEqual(detail["status_code"], 429)
        self.assertEqual(detail["error_code"], "upstream_rate_limited")
        self.assertEqual(detail["error"], "upstream rate limited")


class ImageFailureAccountingTests(unittest.TestCase):
    def _account_service(self, root: Path) -> AccountService:
        storage = TestAccountRepository(root / "accounts.json")
        storage.save_accounts([
            {
                "access_token": "test-token",
                "quota": 5,
            }
        ])
        return AccountService(storage)

    def test_account_verification_is_nonblocking_and_coalesces_overlapping_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._account_service(Path(temp_dir))
            started = threading.Event()
            release = threading.Event()
            finished = threading.Event()
            calls: list[tuple[str, str]] = []

            def verify_pending_auth(access_token: str, event: str) -> None:
                calls.append((access_token, event))
                if len(calls) == 1:
                    started.set()
                    release.wait(timeout=2)
                    return
                service.update_account(
                    access_token,
                    {
                        "last_remote_check_result": "ok",
                        "pending_auth_remove_invalid": None,
                        "pending_auth_scope": None,
                    },
                    quiet=True,
                )
                finished.set()

            service._verify_pending_auth = verify_pending_auth  # type: ignore[method-assign]

            before = time.monotonic()
            service.mark_image_result(
                "test-token",
                False,
                failure=image_failure("image_tool_error"),
            )
            elapsed = time.monotonic() - before
            self.assertLess(elapsed, 0.5)
            self.assertTrue(started.wait(timeout=1))

            service.mark_image_result(
                "test-token",
                False,
                failure=image_failure("image_tool_error"),
            )
            self.assertEqual(calls, [("test-token", "image_failure")])

            release.set()
            self.assertTrue(finished.wait(timeout=1))
            self.assertEqual(
                calls,
                [
                    ("test-token", "image_failure"),
                    ("test-token", "image_failure"),
                ],
            )

    def test_each_image_attempt_is_finalized_once_when_no_result_is_returned(self) -> None:
        class FakeBackend:
            def __init__(self, **_kwargs: object) -> None:
                self.proxy_profile = SimpleNamespace(image_concurrency_limit=0)
                self.cancel_checker = None
                self.progress_callback = None

            def close(self) -> None:
                return None

        progress = conversation.ImageOutput(
            kind="progress",
            model="gpt-image-1",
            index=1,
            total=1,
        )
        request = conversation.ConversationRequest(model="gpt-image-1")
        selected_tokens = iter(("first-token", "second-token"))
        selection_exclusions: list[set[str]] = []

        def select_account(**kwargs: object) -> str:
            selection_exclusions.append(set(kwargs.get("excluded_tokens") or set()))
            return next(selected_tokens)

        with (
            patch.object(
                type(conversation.config),
                "image_account_retry_enabled",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(
                type(conversation.config),
                "image_max_account_attempts",
                new_callable=PropertyMock,
                return_value=2,
            ),
            patch.object(
                conversation.account_service,
                "get_available_access_token",
                side_effect=select_account,
            ),
            patch.object(
                conversation.account_service,
                "get_account",
                side_effect=lambda token: {"access_token": token},
            ),
            patch.object(conversation.account_service, "mark_image_result") as mark_result,
            patch.object(conversation, "OpenAIBackendAPI", FakeBackend),
            patch.object(conversation, "is_codex_image_model", return_value=False),
            patch.object(
                conversation,
                "stream_image_outputs",
                side_effect=lambda *_args, **_kwargs: iter([progress]),
            ),
            patch.object(conversation.proxy_settings, "acquire_image_egress", return_value=0),
        ):
            with self.assertRaises(conversation.ImageGenerationError) as raised:
                conversation._generate_single_image(request, 1, 1)

        self.assertEqual(selection_exclusions, [set(), {"first-token"}])
        self.assertEqual(mark_result.call_count, 2)
        self.assertEqual(
            [item.args for item in mark_result.call_args_list],
            [("first-token", False), ("second-token", False)],
        )
        for item in mark_result.call_args_list:
            self.assertEqual(item.kwargs["failure"].code, "no_image_generated")
            self.assertEqual(item.kwargs["capabilities"], {"auth", "image_generation"})
        self.assertEqual(len(raised.exception.image_attempts), 2)


class ImageResponseFormatTests(unittest.TestCase):
    def test_b64_json_response_does_not_also_expose_a_url(self) -> None:
        with (
            patch.object(
                conversation,
                "save_image_bytes",
                return_value="https://example.test/internal-image.png",
            ) as save_image,
            patch.object(conversation, "image_size_from_bytes", return_value=None),
        ):
            result = conversation.format_image_result(
                [{"b64_json": "aW1hZ2U=", "revised_prompt": "a cat"}],
                "cat",
                "b64_json",
            )

        self.assertEqual(len(result["data"]), 1)
        self.assertEqual(result["data"][0]["b64_json"], "aW1hZ2U=")
        self.assertNotIn("url", result["data"][0])
        save_image.assert_called_once_with(
            b"image",
            None,
            deadline_monotonic=None,
        )

    def test_url_response_does_not_also_expose_base64(self) -> None:
        with (
            patch.object(conversation, "save_image_bytes", return_value="https://example.test/image.png"),
            patch.object(conversation, "image_size_from_bytes", return_value=None),
        ):
            result = conversation.format_image_result(
                [{"b64_json": "aW1hZ2U=", "revised_prompt": "a cat"}],
                "cat",
                "url",
            )

        self.assertEqual(len(result["data"]), 1)
        self.assertEqual(result["data"][0]["url"], "https://example.test/image.png")
        self.assertNotIn("b64_json", result["data"][0])

    def test_distinct_images_remain_distinct_response_items(self) -> None:
        with (
            patch.object(conversation, "save_image_bytes"),
            patch.object(conversation, "image_size_from_bytes", return_value=None),
        ):
            result = conversation.format_image_result(
                [{"b64_json": "Zmlyc3Q="}, {"b64_json": "c2Vjb25k"}],
                "cat",
                "b64_json",
            )

        self.assertEqual(
            [item["b64_json"] for item in result["data"]],
            ["Zmlyc3Q=", "c2Vjb25k"],
        )

    def test_non_stream_generation_handler_returns_one_representation(self) -> None:
        def fake_outputs(request: conversation.ConversationRequest):
            data = conversation.format_image_result(
                [{"b64_json": "aW1hZ2U="}],
                request.prompt,
                request.response_format,
                request.base_url,
            )["data"]
            yield conversation.ImageOutput(
                kind="result",
                model=request.model,
                index=1,
                total=1,
                data=data,
            )

        with (
            patch.object(
                openai_v1_image_generations,
                "stream_image_outputs_with_pool",
                side_effect=fake_outputs,
            ),
            patch.object(
                conversation,
                "save_image_bytes",
                return_value="https://example.test/internal-image.png",
            ) as save_image,
            patch.object(conversation, "image_size_from_bytes", return_value=None),
        ):
            result = openai_v1_image_generations.handle({
                "model": "gpt-image-2",
                "prompt": "cat",
                "n": 1,
                "response_format": "b64_json",
            })

        self.assertIsInstance(result, dict)
        self.assertEqual(len(result["data"]), 1)
        self.assertEqual(set(result["data"][0]), {"b64_json", "revised_prompt"})
        save_image.assert_called_once_with(
            b"image",
            None,
            deadline_monotonic=None,
        )


class ImageStreamingProtocolTests(unittest.TestCase):
    @staticmethod
    def _output() -> conversation.ImageOutput:
        return conversation.ImageOutput(
            kind="result",
            model="gpt-image-2",
            index=1,
            total=1,
            data=[{"b64_json": "aW1hZ2U=", "revised_prompt": "cat"}],
        )

    def test_images_stream_emits_the_final_image_once(self) -> None:
        events = list(conversation.stream_image_chunks(
            [self._output()],
            partial_images=2,
        ))

        self.assertEqual(
            [event["type"] for event in events],
            ["image_generation.completed"],
        )
        self.assertEqual(events[0]["b64_json"], "aW1hZ2U=")

    def test_chat_stream_emits_the_image_content_once(self) -> None:
        events = list(openai_v1_chat_complete.stream_image_chat_completion(
            [self._output()],
            "gpt-image-2",
        ))
        content = "".join(
            str(event["choices"][0]["delta"].get("content") or "")
            for event in events
        )

        self.assertEqual(content.count("aW1hZ2U="), 1)

    def test_responses_stream_reuses_the_item_id_in_the_final_snapshot(self) -> None:
        events = list(openai_v1_response.stream_image_response(
            [self._output()],
            "cat",
            "gpt-image-2",
        ))
        item_done = next(event for event in events if event["type"] == "response.output_item.done")
        completed = next(event for event in events if event["type"] == "response.completed")
        final_item = completed["response"]["output"][0]

        self.assertEqual(item_done["item"]["id"], final_item["id"])
        self.assertEqual(item_done["item"]["result"], final_item["result"])


class DashboardMetricsConcurrencyTests(unittest.TestCase):
    def test_two_instances_do_not_double_count_concurrent_cursor_syncs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database_url = f"sqlite:///{(root / 'app.db').as_posix()}"
            logs = LogService(database_url=f"sqlite:///{(root / 'app.db').as_posix()}")
            DashboardMetricsService(database_url=database_url).sync_from_log_service(logs)
            started_at = beijing_now().isoformat()
            logs.append_item({
                "id": "call-a",
                "time": started_at,
                "type": LOG_TYPE_CALL,
                "detail": {
                    "started_at": started_at,
                    "status": "success",
                    "endpoint": "/v1/chat/completions",
                    "model": "gpt-test",
                    "duration_ms": 25,
                },
            })
            logs.append_item({
                "id": "call-b",
                "time": started_at,
                "type": LOG_TYPE_CALL,
                "detail": {
                    "started_at": started_at,
                    "status": "success",
                    "endpoint": "/v1/chat/completions",
                    "model": "gpt-test",
                    "duration_ms": 25,
                },
            })
            first = DashboardMetricsService(database_url=database_url)
            second = DashboardMetricsService(database_url=database_url)

            barrier = threading.Barrier(2)

            def sync(service: DashboardMetricsService) -> None:
                barrier.wait(timeout=1)
                service.sync_from_log_service(logs)

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(sync, service) for service in (first, second)]
                for future in futures:
                    future.result(timeout=5)

            summary = DashboardMetricsService(database_url=database_url).summary("24h")
            self.assertEqual(summary["total"], 2)
            self.assertEqual(summary["success"], 2)
            self.assertEqual(summary["by_model"], {"gpt-test": 2})


class PromptLibraryConcurrencyTests(unittest.TestCase):
    def test_bundled_seed_does_not_overwrite_an_existing_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_id = "banana-prompt-quicker"
            bundled_path = root / "bundled.json"
            database_url = f"sqlite:///{(root / 'app.db').as_posix()}"
            bundled_path.write_text(json.dumps({
                "prompts": [{"id": "bundled", "title": "Bundled", "prompt": "old"}],
            }), encoding="utf-8")
            PromptLibraryRepository(database_url).replace_snapshot({
                "registry": {
                    "sources": [{"id": source_id}],
                },
                "items_by_source": {
                    source_id: [{
                            "id": f"{source_id}:remote",
                            "source_id": source_id,
                            "source_name": "Remote",
                            "title": "Remote",
                            "prompt": "new",
                    }],
                },
                "source_status": {},
            })
            service = PromptLibraryService(
                database_url=database_url,
                bundled_path=bundled_path,
            )

            view = service.view()

            self.assertEqual([item.id for item in view.items], [f"{source_id}:remote"])
            self.assertEqual(view.items[0].prompt, "new")

    def test_cached_reads_do_not_wait_for_remote_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            refresh_started = threading.Event()
            release_refresh = threading.Event()

            def blocked_fetch(_url: str, _max_bytes: int) -> bytes:
                refresh_started.set()
                release_refresh.wait(timeout=2)
                raise TimeoutError("test refresh released")

            root = Path(temp_dir)
            service = PromptLibraryService(
                database_url=f"sqlite:///{(root / 'app.db').as_posix()}",
                bundled_path=root / "missing.json",
                registry_base="https://registry.example/dist",
                fetch_bytes=blocked_fetch,
            )
            initial = service.view()
            refresh_thread = threading.Thread(target=service.refresh, daemon=True)
            refresh_thread.start()
            self.assertTrue(refresh_started.wait(timeout=1))

            with ThreadPoolExecutor(max_workers=1) as executor:
                cached_future = executor.submit(service.view)
                try:
                    cached = cached_future.result(timeout=0.5)
                except TimeoutError:
                    self.fail("cached prompt reads blocked behind a remote refresh")
                finally:
                    release_refresh.set()

            refresh_thread.join(timeout=1)
            self.assertIs(cached, initial)
            self.assertEqual(cached.items, ())

if __name__ == "__main__":
    unittest.main()

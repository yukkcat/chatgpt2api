from __future__ import annotations

import queue
import threading
import time
import unittest
from concurrent.futures import Future

from curl_cffi.requests.exceptions import RequestException

from services.openai_backend_api import ChatRequirements, OpenAIBackendAPI
from utils.helper import iter_sse_payloads


class _FakeCurl:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class _RunningStreamResponse:
    def __init__(self) -> None:
        self.queue: queue.Queue[object] = queue.Queue()
        self.quit_now = threading.Event()
        self.stream_task: Future[None] = Future()
        self.curl = _FakeCurl()
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        if not self.stream_task.done():
            raise AssertionError("blocking response.close() called before stream task completed")


class ImageStreamTerminalTests(unittest.TestCase):
    def test_sse_timeout_closes_curl_once_without_blocking_response_close(self) -> None:
        response = _RunningStreamResponse()
        curl = response.curl
        stream_task = response.stream_task

        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            list(iter_sse_payloads(response, max_duration_secs=0.02))

        self.assertLess(time.monotonic() - started, 0.5)
        self.assertTrue(response.quit_now.is_set())
        self.assertEqual(response.close_calls, 0)
        self.assertEqual(curl.close_calls, 1)

        stream_task.set_result(None)
        self.assertEqual(curl.close_calls, 1)

    def test_stopping_after_terminal_payload_does_not_wait_for_transport(self) -> None:
        response = _RunningStreamResponse()
        curl = response.curl
        stream_task = response.stream_task
        response.queue.put(b'data: {"status":"finished_successfully"}\n\n')
        payloads = iter_sse_payloads(response, max_duration_secs=10)

        self.assertEqual(next(payloads), '{"status":"finished_successfully"}')
        started = time.monotonic()
        payloads.close()

        self.assertLess(time.monotonic() - started, 0.5)
        self.assertFalse(response.quit_now.is_set())
        self.assertEqual(response.close_calls, 1)
        self.assertEqual(curl.close_calls, 0)

        stream_task.set_result(None)
        self.assertEqual(curl.close_calls, 0)

    def test_transport_exception_cleanup_is_nonblocking(self) -> None:
        response = _RunningStreamResponse()
        curl = response.curl
        stream_task = response.stream_task
        response.queue.put(RequestException("transport failed"))

        started = time.monotonic()
        with self.assertRaises(RequestException):
            list(iter_sse_payloads(response, max_duration_secs=10))

        self.assertLess(time.monotonic() - started, 0.5)
        self.assertFalse(response.quit_now.is_set())
        self.assertGreaterEqual(response.close_calls, 1)
        self.assertEqual(curl.close_calls, 0)

        stream_task.set_result(None)
        self.assertEqual(curl.close_calls, 0)

    def test_curl_closes_after_existing_stream_cleanup_without_racing_it(self) -> None:
        response = _RunningStreamResponse()
        curl = response.curl
        stream_task = response.stream_task
        cleanup_started = threading.Event()
        cleanup_release = threading.Event()
        cleanup_finished = threading.Event()

        def cleanup(_future: Future[None]) -> None:
            cleanup_started.set()
            cleanup_release.wait(timeout=1.0)
            cleanup_finished.set()

        stream_task.add_done_callback(cleanup)
        response.queue.put(b'data: {"status":"finished_successfully"}\n\n')
        payloads = iter_sse_payloads(response, max_duration_secs=10)
        self.assertEqual(next(payloads), '{"status":"finished_successfully"}')

        started = time.monotonic()
        payloads.close()
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(response.close_calls, 1)

        complete = threading.Thread(target=stream_task.set_result, args=(None,))
        complete.start()
        try:
            self.assertTrue(cleanup_started.wait(timeout=1.0))
            self.assertEqual(curl.close_calls, 0)
        finally:
            cleanup_release.set()
            complete.join(timeout=1.0)
        self.assertFalse(complete.is_alive())
        self.assertTrue(cleanup_finished.is_set())
        self.assertEqual(curl.close_calls, 0)

    def test_finished_image_stream_payload_can_leave_sse_phase(self) -> None:
        payload = (
            '{"p":"","o":"patch","v":['
            '{"p":"/message/status","o":"replace","v":"finished_successfully"},'
            '{"p":"/message/metadata","o":"append","v":{"is_complete":true}}'
            ']}'
        )

        self.assertTrue(OpenAIBackendAPI._is_image_stream_terminal_payload(payload))

    def test_in_progress_image_stream_payload_keeps_sse_open(self) -> None:
        payload = '{"p":"","o":"patch","v":[{"p":"/message/status","o":"replace","v":"in_progress"}]}'

        self.assertFalse(OpenAIBackendAPI._is_image_stream_terminal_payload(payload))

    def test_picture_stream_stops_after_terminal_payload(self) -> None:
        terminal_payload = (
            '{"p":"","o":"patch","v":['
            '{"p":"/message/status","o":"replace","v":"finished_successfully"},'
            '{"p":"/message/metadata","o":"append","v":{"is_complete":true}}'
            ']}'
        )

        class FakeResponse:
            closed = False

            def close(self) -> None:
                self.closed = True

        class FakeBackend(OpenAIBackendAPI):
            def __init__(self) -> None:
                self.access_token = "token"
                self.deadline_monotonic = 0.0
                self.response = FakeResponse()

            def _report_progress(self, stage: str) -> None:
                pass

            def _upload_image(self, image: str, filename: str) -> dict:
                return {}

            def _bootstrap(self) -> None:
                pass

            def _get_chat_requirements(self) -> ChatRequirements:
                return ChatRequirements(token="requirements")

            def _prepare_image_conversation(self, prompt: str, requirements: ChatRequirements, model: str) -> str:
                return "conduit"

            def _start_image_generation(self, prompt: str, requirements: ChatRequirements, conduit_token: str, model: str, references: list[dict]) -> FakeResponse:
                return self.response

            def _iter_timed_sse_payloads(self, *args, **kwargs):
                yield terminal_payload
                yield '{"should":"not be consumed"}'

        backend = FakeBackend()

        self.assertEqual(list(backend._stream_picture_conversation("draw", "gpt-image-2", [])), [terminal_payload])
        self.assertTrue(backend.response.closed)


if __name__ == "__main__":
    unittest.main()

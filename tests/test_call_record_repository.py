from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from services.application_database import dispose_database_engine
from services.storage.call_record_repository import (
    CallRecordCursorMismatch,
    CallRecordQuery,
    CallRecordRepository,
    CallRecordWrite,
)


def _write(
    record_id: str,
    *,
    time: str,
    outcome: str = "success",
    endpoint: str = "/v1/chat/completions",
    model: str = "gpt-5",
    account: str = "user@example.test",
    business_kind: str = "text_chat",
) -> CallRecordWrite:
    payload = {
        "id": record_id,
        "time": time,
        "type": "call",
        "summary": record_id,
        "detail": {
            "status": outcome,
            "endpoint": endpoint,
            "model": model,
            "account_email": account,
        },
    }
    return CallRecordWrite(
        payload=payload,
        outcome=outcome,
        endpoint=endpoint,
        model=model,
        account_email=account,
        business_kind=business_kind,
        search_text=f"{record_id} {endpoint} {model} {account}",
    )


def test_call_record_repository_filters_pages_and_projects_facets() -> None:
    with TemporaryDirectory() as directory:
        database_url = f"sqlite:///{(Path(directory) / 'app.db').as_posix()}"
        try:
            repository = CallRecordRepository(database_url)
            repository.append(_write("old", time="2026-08-01 10:00:00"))
            repository.append(_write(
                "image-failed",
                time="2026-08-02 10:00:00",
                outcome="failed",
                endpoint="/v1/images/generations",
                model="gpt-image-2",
                account="image@example.test",
                business_kind="image_generation",
            ))
            repository.append(_write("new", time="2026-08-03 10:00:00"))

            page = repository.list_page(
                CallRecordQuery(search="image@example.test"),
                limit=20,
                offset=0,
            )

            assert page.total == 1
            assert [item["id"] for item in page.items] == ["image-failed"]
            assert page.outcomes == {"failed": 1}
            assert page.facets["models"] == {"gpt-image-2": 1}
            assert page.image_count == 1

            all_page = repository.list_page(CallRecordQuery(type="call"), limit=2, offset=1)
            assert all_page.total == 3
            assert [item["id"] for item in all_page.items] == ["image-failed", "old"]
        finally:
            dispose_database_engine(database_url)


def test_call_record_repository_cursor_is_invalidated_only_by_destructive_changes() -> None:
    with TemporaryDirectory() as directory:
        database_url = f"sqlite:///{(Path(directory) / 'app.db').as_posix()}"
        try:
            repository = CallRecordRepository(database_url)
            repository.append(_write("one", time="2026-08-01 10:00:00"))
            with repository.open_window() as (items, cursor):
                assert [item["id"] for item in items] == ["one"]

            repository.append(_write("two", time="2026-08-01 11:00:00"))
            with repository.open_window(cursor) as (items, next_cursor):
                assert [item["id"] for item in items] == ["two"]
            with repository.hold_cursor(next_cursor):
                pass

            assert repository.delete(["one"]) == 1
            with pytest.raises(CallRecordCursorMismatch):
                with repository.open_window(next_cursor):
                    pass
        finally:
            dispose_database_engine(database_url)


def test_call_record_repository_cleanup_is_transactional() -> None:
    with TemporaryDirectory() as directory:
        database_url = f"sqlite:///{(Path(directory) / 'app.db').as_posix()}"
        try:
            repository = CallRecordRepository(database_url)
            repository.append(_write("old", time="2026-07-01 10:00:00"))
            repository.append(_write("keep", time="2026-08-01 10:00:00"))

            preview = repository.cleanup_before("2026-08-01", dry_run=True)
            assert preview["removed"] == 1
            assert repository.get("old") is not None

            result = repository.cleanup_before("2026-08-01", dry_run=False)
            assert result["removed"] == 1
            assert result["kept"] == 1
            assert repository.get("old") is None
            assert repository.get("keep") is not None
        finally:
            dispose_database_engine(database_url)

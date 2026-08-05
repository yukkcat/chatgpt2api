from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

from services.call_view import (
    build_call_detail,
    build_call_summary,
    call_business_kind,
    call_outcome,
)
from services.storage.call_record_repository import (
    CallRecordQuery,
    CallRecordRepository,
    CallRecordWrite,
)
from utils.diagnostics import scrub_diagnostic_value
from utils.timezone import beijing_now, beijing_now_str


LOG_TYPE_CALL = "call"
LOG_TYPE_ACCOUNT = "account"


class CallRecordService:
    def __init__(
        self,
        repository: CallRecordRepository | None = None,
        *,
        database_url: str | None = None,
    ) -> None:
        if repository is not None and database_url is not None:
            raise ValueError("provide repository or database_url, not both")
        self.repository = repository or CallRecordRepository(database_url)

    @staticmethod
    def _clean(value: object) -> str:
        return str(value or "").strip()

    @staticmethod
    def _detail_value(item: dict[str, Any], key: str, default: object = "") -> object:
        detail = item.get("detail")
        if isinstance(detail, dict):
            value = detail.get(key)
            if value not in (None, ""):
                return value
        value = item.get(key)
        return default if value in (None, "") else value

    @classmethod
    def _search_text(cls, item: dict[str, Any]) -> str:
        return " ".join(
            cls._clean(value)
            for value in (
                item.get("id"),
                item.get("time"),
                item.get("type"),
                item.get("summary"),
                cls._detail_value(item, "endpoint"),
                cls._detail_value(item, "model"),
                cls._detail_value(item, "status"),
                cls._detail_value(item, "key_id"),
                cls._detail_value(item, "key_name"),
                cls._detail_value(item, "account_email"),
                cls._detail_value(item, "conversation_id"),
                cls._detail_value(item, "request_text"),
                cls._detail_value(item, "request_text_full"),
                cls._detail_value(item, "error"),
                cls._detail_value(item, "error_code"),
                cls._detail_value(item, "reason"),
                cls._detail_value(item, "stage"),
            )
        )

    def append_item(self, item: dict[str, Any]) -> dict[str, Any]:
        persisted = dict(item)
        persisted.setdefault("id", uuid4().hex)
        persisted.setdefault("time", beijing_now_str())
        if persisted.get("type") == LOG_TYPE_ACCOUNT:
            sanitized = scrub_diagnostic_value(persisted)
            persisted = sanitized if isinstance(sanitized, dict) else persisted
        return self.repository.append(CallRecordWrite(
            payload=persisted,
            outcome=call_outcome(persisted),
            endpoint=self._clean(self._detail_value(persisted, "endpoint")),
            model=self._clean(self._detail_value(persisted, "model")),
            account_email=self._clean(self._detail_value(persisted, "account_email")),
            conversation_id=self._clean(self._detail_value(persisted, "conversation_id")),
            business_kind=call_business_kind(persisted),
            search_text=self._search_text(persisted),
        ))

    def add(
        self,
        type: str,
        summary: str = "",
        detail: dict[str, Any] | None = None,
        **data: Any,
    ) -> None:
        self.append_item({
            "id": uuid4().hex,
            "time": beijing_now_str(),
            "type": type,
            "summary": summary,
            "detail": detail or data,
        })

    @staticmethod
    def _outcomes(status: str) -> tuple[str, ...]:
        normalized = str(status or "").strip().lower()
        if normalized == "success":
            return ("success", "partial_success")
        if normalized == "failed":
            return ("failed",)
        if normalized == "limited":
            return ("rate_limited",)
        return ()

    def _query(
        self,
        *,
        type: str = "",
        start_date: str = "",
        end_date: str = "",
        status: str = "",
        endpoint: str = "",
        model: str = "",
        account: str = "",
        conversation_id: str = "",
        search: str = "",
    ) -> CallRecordQuery:
        return CallRecordQuery(
            type=self._clean(type),
            start_date=self._clean(start_date),
            end_date=self._clean(end_date),
            outcomes=self._outcomes(status),
            endpoint=self._clean(endpoint),
            model=self._clean(model),
            account_email=self._clean(account),
            conversation_id=self._clean(conversation_id),
            search=self._clean(search),
        )

    def list(
        self,
        type: str = "",
        start_date: str = "",
        end_date: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        page = self.repository.list_page(
            self._query(type=type, start_date=start_date, end_date=end_date),
            limit=max(1, int(limit)),
            offset=0,
        )
        return page.items

    def list_page(
        self,
        *,
        type: str = "",
        start_date: str = "",
        end_date: str = "",
        status: str = "",
        endpoint: str = "",
        model: str = "",
        account: str = "",
        conversation_id: str = "",
        search: str = "",
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit or 200), 20000))
        safe_offset = max(0, int(offset or 0))
        precise = any(self._clean(value) for value in (
            start_date,
            end_date,
            status,
            endpoint,
            model,
            account,
            conversation_id,
            search,
        ))
        page = self.repository.list_page(
            self._query(
                type=type,
                start_date=start_date,
                end_date=end_date,
                status=status,
                endpoint=endpoint,
                model=model,
                account=account,
                conversation_id=conversation_id,
                search=search,
            ),
            limit=safe_limit,
            offset=safe_offset,
        )
        outcomes = page.outcomes
        total_scope = "filtered" if precise else ("type" if type else "all")
        return {
            "items": [build_call_summary(item) for item in page.items],
            "total": page.total,
            "limit": safe_limit,
            "offset": safe_offset,
            "has_more": safe_offset + len(page.items) < page.total,
            "facets": page.facets,
            "stats": {
                "total": page.total,
                "success": int(outcomes.get("success", 0)) + int(outcomes.get("partial_success", 0)),
                "text_review": int(outcomes.get("text_review", 0)),
                "failed": int(outcomes.get("failed", 0)),
                "limited": int(outcomes.get("rate_limited", 0)),
                "image": page.image_count,
            },
            "facets_scope": "filtered",
            "stats_scope": "filtered",
            "total_scope": total_scope,
        }

    def get_detail(self, log_id: str) -> dict[str, Any] | None:
        item = self.repository.get(self._clean(log_id))
        return build_call_detail(item) if item is not None else None

    def delete(self, ids: list[str]) -> dict[str, int]:
        return {"removed": self.repository.delete(ids)}

    def iter_items(self, *, type: str = "") -> Iterator[dict[str, Any]]:
        return self.repository.iter_records(type=self._clean(type))

    def iter_call_items_reverse(self) -> Iterator[dict[str, Any]]:
        return self.repository.iter_records(type=LOG_TYPE_CALL, newest_first=True)

    def open_call_window(self, cursor: dict[str, Any] | None = None):
        return self.repository.open_window(cursor)

    def hold_call_cursor(self, cursor: dict[str, Any]):
        return self.repository.hold_cursor(cursor)

    def _cleanup_old(self, retention_days: int, *, dry_run: bool) -> dict[str, int | bool]:
        try:
            days = max(1, int(retention_days))
        except (TypeError, ValueError):
            days = 30
        cutoff_day = (beijing_now().date() - timedelta(days=days)).isoformat()
        result = self.repository.cleanup_before(cutoff_day, dry_run=dry_run)
        return {**result, "dry_run": dry_run}

    def preview_cleanup_old(self, retention_days: int) -> dict[str, int | bool]:
        return self._cleanup_old(retention_days, dry_run=True)

    def cleanup_old(self, retention_days: int) -> dict[str, int | bool]:
        return self._cleanup_old(retention_days, dry_run=False)

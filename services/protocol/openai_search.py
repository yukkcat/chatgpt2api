from __future__ import annotations

from services.openai_backend_api import SEARCH_MODEL
from services.protocol.web_search_tool import run_web_search

MODEL = SEARCH_MODEL


def handle(body: dict[str, object]) -> dict[str, object]:
    def include_account(result: dict[str, object], account: dict[str, object]) -> None:
        result["_account_email"] = str(account.get("email") or "")

    return run_web_search(str(body["prompt"]), decorate=include_account)

from __future__ import annotations

import re
from typing import Any, Callable

from services.account_service import account_service
from services.openai_backend_api import OpenAIBackendAPI
from services.protocol.search_execution import execute_search

WEB_SEARCH_TOOL_TYPES = {"web_search", "web_search_preview", "web_search_preview_2025_03_11"}
SEARCH_CHAT_MODEL_PREFIXES = (
    "gpt-4o-search-preview",
    "gpt-4o-mini-search-preview",
    "gpt-5-search-api",
)


def _tool_type(tool: object) -> str:
    return str(tool.get("type") or "").strip() if isinstance(tool, dict) else ""


def has_web_search_tool(body: dict[str, Any]) -> bool:
    tools = body.get("tools")
    if isinstance(tools, list):
        return any(_tool_type(tool) in WEB_SEARCH_TOOL_TYPES for tool in tools)
    tool_choice = body.get("tool_choice")
    return _tool_type(tool_choice) in WEB_SEARCH_TOOL_TYPES


def is_web_search_chat_request(body: dict[str, Any]) -> bool:
    model = str(body.get("model") or "").strip()
    return (
        has_web_search_tool(body)
        or isinstance(body.get("web_search_options"), dict)
        or any(
            model == prefix or model.startswith(f"{prefix}-")
            for prefix in SEARCH_CHAT_MODEL_PREFIXES
        )
    )


def has_unsupported_tools(body: dict[str, Any], allowed_types: set[str]) -> bool:
    tools = body.get("tools")
    if not isinstance(tools, list):
        return False
    return any(_tool_type(tool) not in allowed_types for tool in tools if isinstance(tool, dict))


def message_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                text = str(item.get("text") or item.get("input_text") or "").strip()
            else:
                text = ""
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    return ""


def search_query_from_messages(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if str(message.get("role") or "").strip().lower() != "user":
            continue
        text = message_text(message.get("content"))
        if text:
            return text
    return ""


def _readable_annotation_part(parts: list[str]) -> str:
    for part in parts:
        value = part.strip()
        lower = value.lower()
        if value and not (
            lower.startswith(("turn", "source", "sources"))
            or re.fullmatch(r"\d+", value)
        ):
            return value
    return ""


def clean_search_text(text: str) -> str:
    def replace_annotation(match: re.Match[str]) -> str:
        parts = [part.strip() for part in match.group(1).split("\ue202")]
        kind = (parts[0] if parts else "").lower()
        data = parts[1:]
        if kind == "url":
            label = data[0] if data else ""
            url = data[1] if len(data) > 1 else ""
            if label and url.startswith(("http://", "https://")):
                return f"{label} ({url})"
            return label or url
        if kind == "cite":
            return _readable_annotation_part(data)
        return _readable_annotation_part(data)

    text = re.sub(r"\ue200([^\ue201]*)\ue201", replace_annotation, text)
    text = re.sub(r"\ue200[^\ue201]*$", "", text)
    return re.sub(r"\s+([.,;:!?])", r"\1", text).strip()


def normalized_sources(result: dict[str, Any]) -> list[dict[str, str]]:
    sources = result.get("sources")
    if not isinstance(sources, list):
        return []
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in sources:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        output.append({"title": title, "url": url, "snippet": snippet})
    return output


def text_with_url_citations(result: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    text = clean_search_text(str(result.get("answer") or ""))
    annotations: list[dict[str, Any]] = []
    sources = normalized_sources(result)
    if sources:
        text = text.rstrip()
        if text:
            text += "\n\n"
        text += "Sources:\n"
        for index, source in enumerate(sources, start=1):
            title = source["title"] or source["url"]
            line_prefix = f"{index}. {title}"
            text += line_prefix
            if source["url"]:
                if source["title"]:
                    text += " - "
                start = len(text)
                text += source["url"]
                annotations.append({
                    "type": "url_citation",
                    "start_index": start,
                    "end_index": len(text),
                    "url": source["url"],
                    "title": source["title"] or source["url"],
                })
            text += "\n"
    return text.strip(), annotations


def run_web_search(
    query: str,
    *,
    decorate: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    return execute_search(
        query,
        backend_factory=OpenAIBackendAPI,
        decorate=decorate,
    )

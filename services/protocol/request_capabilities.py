"""Reject request features that this compatibility backend would otherwise drop."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException

from services.protocol.web_search_tool import WEB_SEARCH_TOOL_TYPES

_TEXT_PARTS = {"text", "input_text", "output_text"}
_IMAGE_PARTS = {"image_url", "input_image", "image"}
_ANTHROPIC_TOOL_PARTS = {"tool_use", "tool_result"}
_RESPONSE_TOOLS = {*WEB_SEARCH_TOOL_TYPES, "image_generation"}


def _reject(capabilities: set[str]) -> None:
    if not capabilities:
        return
    names = sorted(capabilities)
    raise HTTPException(
        status_code=501,
        detail={
            "error": f"Unsupported capabilities: {', '.join(names)}.",
            "code": "unsupported_capability",
            "capabilities": names,
        },
    )


def _has_supported_image_source(value: dict[str, Any], part_type: str) -> bool:
    if part_type == "image_url":
        source = value.get("image_url") or value.get("url")
        if isinstance(source, dict):
            source = source.get("url") or source.get("image_url")
        if not isinstance(source, str):
            return False
        candidate = source.strip()
        if candidate.startswith("data:image/"):
            return ";base64," in candidate
        parsed = urlsplit(candidate)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    for key in ("image_url", "url"):
        source = value.get(key)
        if isinstance(source, dict):
            source = source.get("url") or source.get("image_url")
        if isinstance(source, str):
            candidate = source.strip()
            parsed = urlsplit(candidate)
            if candidate.startswith("data:image/") and ";base64," in candidate:
                return True
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return True
    if any(isinstance(value.get(key), str) and value[key].strip() for key in ("base64", "b64_json")):
        return True
    source = value.get("source")
    return (
        isinstance(source, dict)
        and str(source.get("type") or "") == "base64"
        and isinstance(source.get("data"), str)
        and bool(source["data"].strip())
    )


def _validate_content(value: object, capabilities: set[str], protocol: str, role: str = "user") -> None:
    if isinstance(value, dict):
        part_type = str(value.get("type") or "").strip()
        if part_type:
            if part_type in _TEXT_PARTS:
                return
            if part_type in _IMAGE_PARTS:
                if role == "user" and _has_supported_image_source(value, part_type):
                    return
                reason = f"content:{part_type}_unsupported_source" if role == "user" else f"content:{part_type}_outside_user_message"
                capabilities.add(reason)
                return
            if protocol == "anthropic" and part_type in _ANTHROPIC_TOOL_PARTS:
                expected_role = "assistant" if part_type == "tool_use" else "user"
                if role == expected_role:
                    if part_type == "tool_result":
                        _validate_content(value.get("content"), capabilities, protocol, "tool_result")
                    return
                capabilities.add(f"content:{part_type}_outside_{expected_role}_message")
                return
            capabilities.add(f"content:{part_type}")
        else:
            capabilities.add("content:unknown_block")
        return
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                continue
            if isinstance(item, dict):
                _validate_content(item, capabilities, protocol, role)
            else:
                capabilities.add("content:unknown_block")


def _validate_tools(body: dict[str, Any], capabilities: set[str], allowed: set[str], protocol: str) -> None:
    tools = body.get("tools")
    if tools is not None:
        if not isinstance(tools, list):
            capabilities.add("tools:invalid_shape")
        else:
            for tool in tools:
                if not isinstance(tool, dict):
                    capabilities.add("tools:unknown")
                    continue
                if protocol == "anthropic":
                    if not str(tool.get("name") or "").strip():
                        capabilities.add("tools:invalid_anthropic_tool")
                    continue
                tool_type = str(tool.get("type") or "").strip()
                if tool_type not in allowed:
                    capabilities.add(f"tool:{tool_type or 'unknown'}")

    choice = body.get("tool_choice")
    if protocol == "chat":
        if body.get("functions"):
            capabilities.add("legacy:functions")
        function_call = body.get("function_call")
        if function_call not in (None, "none"):
            capabilities.add("legacy:function_call")
        if isinstance(choice, dict):
            choice_type = str(choice.get("type") or "")
            if choice_type not in allowed:
                capabilities.add("tool_choice:forced_function")
            elif isinstance(tools, list) and not any(
                isinstance(tool, dict) and str(tool.get("type") or "") == choice_type for tool in tools
            ):
                capabilities.add("tool_choice:missing_tool")
        elif isinstance(choice, str) and choice not in {"auto", "none", "required"}:
            capabilities.add("tool_choice:unknown")
        elif choice == "required" and not (isinstance(tools, list) and tools):
            capabilities.add("tool_choice:required_without_tools")
        elif choice == "required" and isinstance(tools, list) and any(
            isinstance(tool, dict) and str(tool.get("type") or "") not in allowed for tool in tools
        ):
            capabilities.add("tool_choice:required_unsupported_tool")
    elif protocol == "responses":
        if isinstance(choice, dict):
            choice_type = str(choice.get("type") or "")
            if choice_type not in allowed:
                capabilities.add("tool_choice:forced_function")
            elif not isinstance(tools, list) or not any(
                isinstance(tool, dict) and str(tool.get("type") or "") == choice_type for tool in tools
            ):
                capabilities.add("tool_choice:missing_tool")
        elif isinstance(choice, str) and choice not in {"auto", "none", "required"}:
            capabilities.add("tool_choice:unknown")
        elif choice == "required" and not (isinstance(tools, list) and tools):
            capabilities.add("tool_choice:required_without_tools")


def validate_request_capabilities(body: dict[str, Any], protocol: str) -> None:
    """Fail before normalization, cache lookup, or inference if input would be lost."""
    capabilities: set[str] = set()
    if protocol == "chat":
        _validate_tools(body, capabilities, WEB_SEARCH_TOOL_TYPES, protocol)
        messages = body.get("messages")
        if isinstance(messages, list):
            for message in messages:
                if not isinstance(message, dict):
                    continue
                if message.get("role") in {"tool", "function"} or message.get("tool_calls") or message.get("function_call"):
                    capabilities.add("conversation:tool_call_history")
                _validate_content(message.get("content"), capabilities, protocol, str(message.get("role") or "user").lower())
    elif protocol == "responses":
        _validate_tools(body, capabilities, _RESPONSE_TOOLS, protocol)
        _validate_content(body.get("instructions"), capabilities, protocol, "system")
        input_value = body.get("input")
        items = input_value if isinstance(input_value, list) else [input_value]
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip()
            if not item_type and "image_url" in item:
                _validate_content({**item, "type": "image_url"}, capabilities, protocol, str(item.get("role") or "user").lower())
            elif not item_type and any(key in item for key in ("file_id", "file_data", "filename")):
                capabilities.add("response_item:file_reference_without_type")
            if item_type in {"function_call", "function_call_output", "computer_call", "computer_call_output"}:
                capabilities.add(f"response_item:{item_type}")
            if item_type in _TEXT_PARTS | _IMAGE_PARTS:
                _validate_content(item, capabilities, protocol, str(item.get("role") or "user").lower())
            else:
                _validate_content(item.get("content"), capabilities, protocol, str(item.get("role") or "user").lower())
                if item_type and item_type not in {"message", *_TEXT_PARTS, *_IMAGE_PARTS} and not item_type.startswith("function_"):
                    capabilities.add(f"response_item:{item_type}")
    elif protocol == "anthropic":
        _validate_tools(body, capabilities, set(), protocol)
        _validate_content(body.get("system"), capabilities, protocol, "system")
        choice = body.get("tool_choice")
        if isinstance(choice, dict) and str(choice.get("type") or "") != "auto":
            capabilities.add("tool_choice:unsupported_anthropic_mode")
        elif choice not in (None, "auto") and not isinstance(choice, dict):
            capabilities.add("tool_choice:unsupported_anthropic_mode")
        messages = body.get("messages")
        if isinstance(messages, list):
            for message in messages:
                if isinstance(message, dict):
                    if message.get("role") == "tool":
                        capabilities.add("conversation:tool_call_history")
                    _validate_content(message.get("content"), capabilities, protocol, str(message.get("role") or "user").lower())
    else:
        raise ValueError(f"Unknown protocol: {protocol}")
    _reject(capabilities)

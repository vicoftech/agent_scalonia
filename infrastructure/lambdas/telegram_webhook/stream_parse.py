"""Parseo de respuestas SSE/JSON del AgentCore + Strands → texto para Telegram."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

_THINKING_RE = re.compile(r"<thinking>.*?</thinking>\s*", re.DOTALL | re.IGNORECASE)

# Mistral/Strands a veces emiten tool calls como texto JSON en lugar de bloque toolUse.
_TOOL_CALL_TEXT_RE = re.compile(
    r'^\s*[\[{]\s*"?name"?\s*:\s*"[^"]+"\s*,\s*"?arguments"?\s*:',
    re.DOTALL,
)


@dataclass
class StreamParseState:
    deltas: list[str] = field(default_factory=list)
    assistant_texts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    tool_call_without_followup: bool = False


def strip_thinking(text: str) -> str:
    return _THINKING_RE.sub("", text).strip()


def _looks_like_tool_call_obj(obj: Any) -> bool:
    if isinstance(obj, dict):
        name = obj.get("name")
        if isinstance(name, str) and name:
            return "arguments" in obj or "input" in obj
        return False
    if isinstance(obj, list) and obj:
        return all(
            isinstance(item, dict) and _looks_like_tool_call_obj(item) for item in obj
        )
    return False


def is_tool_call_payload(text: str) -> bool:
    """Detecta JSON de invocación de tools que no debe mostrarse al usuario."""
    cleaned = strip_thinking(text)
    if not cleaned:
        return False
    if _TOOL_CALL_TEXT_RE.match(cleaned):
        return True
    if cleaned[0] not in "[{":
        return False
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return False
    return _looks_like_tool_call_obj(parsed)


def error_from_event(event: dict[str, Any]) -> str | None:
    if event.get("force_stop"):
        return str(event.get("force_stop_reason") or "force_stop")
    if event.get("error"):
        return str(event.get("message") or event.get("error_type") or event["error"])
    nested = event.get("event")
    if isinstance(nested, dict):
        exc = nested.get("modelStreamErrorException") or nested.get("internalServerException")
        if isinstance(exc, dict):
            return str(exc.get("message") or exc)
    return None


def message_had_tool_call_only(event: dict[str, Any]) -> bool:
    msg = event.get("message")
    if not isinstance(msg, dict):
        return False
    saw_tool = False
    saw_user_text = False
    for block in msg.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("toolUse") or block.get("tool_use"):
            saw_tool = True
            continue
        text = block.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        if is_tool_call_payload(text):
            saw_tool = True
        else:
            saw_user_text = True
    return saw_tool and not saw_user_text


def message_text_from_event(event: dict[str, Any]) -> str:
    msg = event.get("message")
    if not isinstance(msg, dict):
        return ""
    parts: list[str] = []
    for block in msg.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("toolUse") or block.get("tool_use"):
            continue
        text = block.get("text")
        if isinstance(text, str) and text and not is_tool_call_payload(text):
            parts.append(text)
    return strip_thinking("".join(parts)) if parts else ""


def delta_text_from_event(event: dict[str, Any]) -> str:
    nested = event.get("event")
    if isinstance(nested, dict):
        block = nested.get("contentBlockDelta")
        if isinstance(block, dict):
            delta = block.get("delta") or {}
            text = delta.get("text")
            if isinstance(text, str) and not is_tool_call_payload(text):
                return text
    return ""


def accumulate_stream_event(state: StreamParseState, event: dict[str, Any]) -> None:
    err = error_from_event(event)
    if err:
        state.errors.append(err)
        return
    if event.keys() <= {"init_event_loop"} or event.keys() <= {"start"} or event.keys() <= {"start_event_loop"}:
        return
    msg = message_text_from_event(event)
    if msg:
        state.tool_call_without_followup = False
        state.assistant_texts.append(msg)
    elif message_had_tool_call_only(event):
        state.tool_call_without_followup = True
    chunk = delta_text_from_event(event)
    if chunk:
        state.deltas.append(chunk)


def finalize_stream_text(state: StreamParseState, *, friendly_error) -> str:
    for text in reversed(state.assistant_texts):
        cleaned = text.strip()
        if cleaned and not is_tool_call_payload(cleaned):
            return cleaned
    if state.deltas:
        joined = strip_thinking("".join(state.deltas))
        if joined and not is_tool_call_payload(joined):
            return joined
    if state.tool_call_without_followup:
        return (
            "Consulté fuentes internas pero no llegó la respuesta final al chat. "
            "Intentá de nuevo en unos segundos."
        )
    if state.errors:
        return friendly_error(state.errors[-1])
    return ""


def iter_json_objects(raw: str):
    decoder = json.JSONDecoder()
    pos = 0
    while pos < len(raw):
        while pos < len(raw) and raw[pos].isspace():
            pos += 1
        if pos >= len(raw):
            break
        if raw[pos] != "{":
            next_obj = raw.find("{", pos + 1)
            if next_obj == -1:
                break
            pos = next_obj
            continue
        try:
            obj, idx = decoder.raw_decode(raw, pos)
        except json.JSONDecodeError:
            next_obj = raw.find("{", pos + 1)
            if next_obj == -1:
                break
            pos = next_obj
            continue
        yield obj
        pos += idx


def parse_agent_stream_payload(raw: str, *, friendly_error) -> str:
    state = StreamParseState()
    for event in iter_json_objects(raw):
        if isinstance(event, dict):
            accumulate_stream_event(state, event)
    return finalize_stream_text(state, friendly_error=friendly_error)


def parse_sse_events(stream, *, friendly_error) -> str:
    state = StreamParseState()
    for line in stream.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8").strip()
        if not decoded.startswith("data: "):
            continue
        payload = decoded[6:].strip()
        if not payload.startswith("{"):
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            accumulate_stream_event(state, event)
    return finalize_stream_text(state, friendly_error=friendly_error)

"""Parseo de respuestas SSE/JSON del AgentCore + Strands → texto para Telegram."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

_THINKING_RE = re.compile(r"<thinking>.*?</thinking>\s*", re.DOTALL | re.IGNORECASE)


@dataclass
class StreamParseState:
    deltas: list[str] = field(default_factory=list)
    final_message: str = ""
    errors: list[str] = field(default_factory=list)


def strip_thinking(text: str) -> str:
    return _THINKING_RE.sub("", text).strip()


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


def message_text_from_event(event: dict[str, Any]) -> str:
    msg = event.get("message")
    if not isinstance(msg, dict):
        return ""
    parts: list[str] = []
    for block in msg.get("content") or []:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return strip_thinking("".join(parts)) if parts else ""


def delta_text_from_event(event: dict[str, Any]) -> str:
    nested = event.get("event")
    if isinstance(nested, dict):
        block = nested.get("contentBlockDelta")
        if isinstance(block, dict):
            delta = block.get("delta") or {}
            if isinstance(delta.get("text"), str):
                return delta["text"]
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
        state.final_message = msg
    chunk = delta_text_from_event(event)
    if chunk:
        state.deltas.append(chunk)


def finalize_stream_text(state: StreamParseState, *, friendly_error) -> str:
    if state.final_message:
        return state.final_message
    if state.deltas:
        return strip_thinking("".join(state.deltas))
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

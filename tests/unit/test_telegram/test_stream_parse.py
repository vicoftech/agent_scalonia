"""Tests de parseo SSE AgentCore / Strands."""
import json
import os

os.environ.setdefault("AGENTCORE_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:123:runtime/test")
os.environ.setdefault("DYNAMODB_TABLE", "ProdeTable-test")

from infrastructure.lambdas.telegram_webhook.handler import _friendly_agent_error
from infrastructure.lambdas.telegram_webhook.stream_parse import (
    accumulate_stream_event,
    finalize_stream_text,
    parse_agent_stream_payload,
    parse_sse_events,
    StreamParseState,
)


class TestStreamParse:
    def test_message_event(self):
        raw = '{"message": {"role": "assistant", "content": [{"text": "Hola mundo"}]}}'
        assert (
            parse_agent_stream_payload(raw, friendly_error=_friendly_agent_error)
            == "Hola mundo"
        )

    def test_sse_tool_use_then_answer(self):
        lines = [
            'data: {"init_event_loop": true}',
            'data: {"event": {"contentBlockDelta": {"delta": {"text": "En 1962 "}}}}',
            'data: {"message": {"role": "assistant", "content": [{"text": "En 1962 Pelé se lesionó."}]}}',
            "data: {'type': 'tool_use_stream'}",
        ]

        class FakeStream:
            def iter_lines(self):
                for ln in lines:
                    yield ln.encode("utf-8")

        out = parse_sse_events(FakeStream(), friendly_error=_friendly_agent_error)
        assert "1962" in out
        assert "Pelé" in out

    def test_prefers_final_message_over_deltas(self):
        state = StreamParseState(deltas=["parcial "], final_message="respuesta final")
        assert (
            finalize_stream_text(state, friendly_error=_friendly_agent_error)
            == "respuesta final"
        )

    def test_deltas_when_no_final_message(self):
        state = StreamParseState(deltas=["a", "b"])
        assert finalize_stream_text(state, friendly_error=_friendly_agent_error) == "ab"

    def test_agentcore_error_event(self):
        raw = json.dumps(
            {
                "error": "EventLoopException",
                "error_type": "EventLoopException",
                "message": "tool use in streaming mode",
            }
        )
        out = parse_agent_stream_payload(raw, friendly_error=_friendly_agent_error)
        assert "herramientas" in out.lower() or "error" in out.lower()

    def test_force_stop_validation(self):
        raw = (
            '{"force_stop": true, "force_stop_reason": '
            '"ValidationException: model identifier is invalid"}'
        )
        out = parse_agent_stream_payload(raw, friendly_error=_friendly_agent_error)
        assert "modelo" in out.lower()

    def test_strips_thinking_tags(self):
        state = StreamParseState()
        accumulate_stream_event(
            state,
            {
                "message": {
                    "role": "assistant",
                    "content": [{"text": "<thinking>x</thinking>Visible"}],
                }
            },
        )
        assert finalize_stream_text(state, friendly_error=_friendly_agent_error) == "Visible"

"""tests/unit/test_guardrails — SPEC-2026-015 SC-01 a SC-06 (unit)."""
import asyncio
import logging
from pathlib import Path
from unittest.mock import patch

from agent.guardrails.constants import (
    GUARDRAIL_SECTION,
    OUT_OF_SCOPE_BLOCKED_INPUT,
    OUT_OF_SCOPE_BLOCKED_OUTPUT,
    OUT_OF_SCOPE_LLM_REPLY,
)
from agent.guardrails.detect import is_guardrail_block_event
from agent.guardrails.ssm_paths import (
    DEFAULT_PROJECT_NAME,
    guardrail_id_parameter,
    guardrail_version_parameter,
)
from agent.main import SYSTEM_PROMPT, _bedrock_model_kwargs

_TERRAFORM_GUARD = Path(__file__).resolve().parents[3] / "infrastructure/terraform/guardrails"


class TestGuardrailConstants:
    def test_sc03_mensaje_input_multilinea(self):
        assert "Prode Mundial 2026" in OUT_OF_SCOPE_BLOCKED_INPUT
        assert "fútbol y mundiales" in OUT_OF_SCOPE_BLOCKED_INPUT
        assert "\n" in OUT_OF_SCOPE_BLOCKED_INPUT

    def test_sc03_mensaje_output_multilinea(self):
        assert "fútbol y mundiales" in OUT_OF_SCOPE_BLOCKED_OUTPUT
        assert "\n" in OUT_OF_SCOPE_BLOCKED_OUTPUT

    def test_mensaje_fijo_llm_reply(self):
        assert "historia de los mundiales" in OUT_OF_SCOPE_LLM_REPLY
        assert "reglas del juego" in OUT_OF_SCOPE_LLM_REPLY

    def test_system_prompt_incluye_guardrail_section(self):
        assert GUARDRAIL_SECTION in SYSTEM_PROMPT
        assert "NO PODÉS responder" in SYSTEM_PROMPT
        assert "Lo que podés y no podés responder" in SYSTEM_PROMPT


class TestSsmPaths:
    def test_sc06_rutas_ssm_alineadas_con_terraform(self):
        assert guardrail_id_parameter("dev") == f"/{DEFAULT_PROJECT_NAME}/dev/guardrail_id"
        assert guardrail_version_parameter("staging") == f"/{DEFAULT_PROJECT_NAME}/staging/guardrail_version"


class TestTerraformGuardrailsModule:
    def test_sc06_modulo_guardrails_existe(self):
        assert (_TERRAFORM_GUARD / "main.tf").is_file()
        assert (_TERRAFORM_GUARD / "variables.tf").is_file()
        assert (_TERRAFORM_GUARD / "outputs.tf").is_file()
        main = (_TERRAFORM_GUARD / "main.tf").read_text()
        assert "aws_bedrock_guardrail" in main
        assert "aws_ssm_parameter" in main
        assert "GuardrailInvocationCount" in main


class TestBedrockModelGuardrailConfig:
    def test_sin_env_no_configura_guardrail(self, monkeypatch):
        monkeypatch.delenv("GUARDRAIL_ID", raising=False)
        monkeypatch.delenv("GUARDRAIL_VERSION", raising=False)
        kw = _bedrock_model_kwargs()
        assert "guardrail_id" not in kw

    def test_con_env_configura_guardrail(self, monkeypatch):
        monkeypatch.setenv("GUARDRAIL_ID", "abc123")
        monkeypatch.setenv("GUARDRAIL_VERSION", "1")
        kw = _bedrock_model_kwargs()
        assert kw["guardrail_id"] == "abc123"
        assert kw["guardrail_version"] == "1"
        assert kw["guardrail_trace"] == "enabled"
        assert kw["guardrail_redact_input_message"] == OUT_OF_SCOPE_BLOCKED_INPUT
        assert kw["guardrail_redact_output_message"] == OUT_OF_SCOPE_BLOCKED_OUTPUT


class TestGuardrailDetection:
    def test_sc04_detecta_redact_content(self):
        assert is_guardrail_block_event({"redactContent": {"redactUserContentMessage": "x"}})

    def test_sc04_detecta_trace_blocked(self):
        event = {
            "metadata": {
                "trace": {
                    "guardrail": {
                        "inputAssessment": {
                            "topic": {"action": "BLOCKED"},
                        }
                    }
                }
            }
        }
        assert is_guardrail_block_event(event)

    def test_sc01_evento_normal_no_es_bloqueo(self):
        assert not is_guardrail_block_event({"message": {"role": "assistant", "content": []}})
        assert not is_guardrail_block_event("text")


class TestAgentGuardrailLogging:
    def test_sc04_log_guardrail_blocked(self, caplog):
        from agent.main import agent_invocation

        caplog.set_level(logging.WARNING)

        class FakeAgent:
            def stream_async(self, _prompt):
                async def _gen():
                    yield {
                        "redactContent": {
                            "redactUserContentMessage": OUT_OF_SCOPE_BLOCKED_INPUT,
                        }
                    }

                return _gen()

        async def _run():
            events = []
            with patch("agent.main._build_agent", return_value=FakeAgent()):
                async for ev in agent_invocation(
                    {
                        "prompt": "hack",
                        "user_id": "user-uuid-1234",
                        "platform": "TELEGRAM",
                    }
                ):
                    events.append(ev)
            return events

        events = asyncio.run(_run())
        assert any("GuardrailBlocked" in r.message for r in caplog.records)
        assert len(events) == 1

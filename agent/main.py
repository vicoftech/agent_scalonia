"""
agent/main.py — Prode Mundial 2026
====================================
Entrypoint del agente en Bedrock AgentCore Runtime.
Deploy: agentcore deploy  |  Local: agentcore launch --local

Patrón oficial de streaming:
  @app.entrypoint async def + agent.stream_async() + yield
"""
import logging
import os
import sys
from pathlib import Path

from strands import Agent
from strands.models.bedrock import BedrockModel
from bedrock_agentcore import BedrockAgentCoreApp

# Repo root en sys.path (AgentCore ejecuta agent/main.py)
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from agent.guardrails.constants import (
    GUARDRAIL_SECTION,
    OUT_OF_SCOPE_BLOCKED_INPUT,
    OUT_OF_SCOPE_BLOCKED_OUTPUT,
)
from agent.guardrails.detect import is_guardrail_block_event
from agent.tools.echo_tool import echo_tool

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

_BASE_PROMPT = """
Sos el asistente del Prode Mundial 2026 ⚽
Ayudás a los usuarios a predecir partidos, consultar rankings, jugar trivia y explorar la historia de los mundiales.
Respondé siempre en el idioma del usuario. Sé conciso. Usá emojis con moderación.

Estado actual: MVP — agente base funcionando.
Las features de predicciones, rankings, grupos y trivia se habilitan sprint a sprint.
""".strip()

SYSTEM_PROMPT = f"{_BASE_PROMPT}\n\n{GUARDRAIL_SECTION}"

# Cuentas reseller: sin Anthropic. Nova Pro ≈ Sonnet.
_DEFAULT_MODEL = "us.amazon.nova-pro-v1:0"
_BEDROCK_REGION = "us-east-1"

app = BedrockAgentCoreApp()


def _bedrock_model_kwargs() -> dict:
    model_id = os.getenv("BEDROCK_MODEL_ID", _DEFAULT_MODEL)
    kwargs: dict = {"model_id": model_id, "region_name": _BEDROCK_REGION}
    guardrail_id = os.getenv("GUARDRAIL_ID", "").strip()
    guardrail_version = os.getenv("GUARDRAIL_VERSION", "").strip()
    if guardrail_id and guardrail_version:
        kwargs.update(
            guardrail_id=guardrail_id,
            guardrail_version=guardrail_version,
            guardrail_trace="enabled",
            guardrail_redact_input=True,
            guardrail_redact_input_message=OUT_OF_SCOPE_BLOCKED_INPUT,
            guardrail_redact_output=True,
            guardrail_redact_output_message=OUT_OF_SCOPE_BLOCKED_OUTPUT,
        )
    return kwargs


def _build_agent() -> Agent:
    model_kw = _bedrock_model_kwargs()
    logger.info(
        "Bedrock model_id=%s region=%s guardrail=%s",
        model_kw["model_id"],
        _BEDROCK_REGION,
        bool(model_kw.get("guardrail_id")),
    )
    return Agent(
        model=BedrockModel(**model_kw),
        system_prompt=SYSTEM_PROMPT,
        tools=[echo_tool],
    )


@app.entrypoint
async def agent_invocation(payload: dict):
    """
    Handler principal con streaming habilitado.

    payload esperado:
        prompt:     str   — mensaje del usuario
        user_id:    str   — UUID interno (no platform_id)
        platform:   str   — TELEGRAM | TEAMS
        session_id: str   — gestionado por AgentCore
    """
    prompt   = payload.get("prompt", "No encontré un mensaje. Enviá un JSON con la clave 'prompt'.")
    user_id  = payload.get("user_id", "anonymous")
    platform = payload.get("platform", "UNKNOWN")

    logger.info("Invocación | platform=%s | user_prefix=%s", platform, user_id[:8])

    # Nuevo Agent por invoke: evita microVM cacheado con modelo/código viejo.
    stream = _build_agent().stream_async(prompt)
    async for event in stream:
        if is_guardrail_block_event(event):
            logger.warning(
                "GuardrailBlocked | platform=%s | user_prefix=%s",
                platform,
                user_id[:8],
            )
        yield event


if __name__ == "__main__":
    app.run()

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

from agent.tools.echo_tool import echo_tool

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Sos el asistente del Prode Mundial 2026 ⚽
Ayudás a los usuarios a predecir partidos, consultar rankings, jugar trivia y explorar la historia de los mundiales.
Respondé siempre en el idioma del usuario. Sé conciso. Usá emojis con moderación.

Estado actual: MVP — agente base funcionando.
Las features de predicciones, rankings, grupos y trivia se habilitan sprint a sprint.
""".strip()

# Cuentas reseller: sin Anthropic. Nova Pro ≈ Sonnet.
_DEFAULT_MODEL = "us.amazon.nova-pro-v1:0"
_BEDROCK_REGION = "us-east-1"

app = BedrockAgentCoreApp()


def _build_agent() -> Agent:
    model_id = os.getenv("BEDROCK_MODEL_ID", _DEFAULT_MODEL)
    logger.info("Bedrock model_id=%s region=%s", model_id, _BEDROCK_REGION)
    return Agent(
        model=BedrockModel(model_id=model_id, region_name=_BEDROCK_REGION),
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
        yield event


if __name__ == "__main__":
    app.run()

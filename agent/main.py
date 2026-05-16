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

from strands import Agent
from bedrock_agentcore import BedrockAgentCoreApp

from tools.echo_tool import echo_tool
# Sprint 1+: descomenzar conforme se implementan
# from tools.prediction_tool  import prediction_tool
# from tools.ranking_tool     import ranking_tool
# from tools.group_tool       import group_tool
# from tools.scoring_tool     import scoring_tool
# from tools.trivia_tool      import trivia_tool
# from tools.kb_retrieval_tool import kb_retrieval_tool
# from tools.web_search_tool  import web_search_tool

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Sos el asistente del Prode Mundial 2026 ⚽
Ayudás a los usuarios a predecir partidos, consultar rankings, jugar trivia y explorar la historia de los mundiales.
Respondé siempre en el idioma del usuario. Sé conciso. Usá emojis con moderación.

Estado actual: MVP — agente base funcionando.
Las features de predicciones, rankings, grupos y trivia se habilitan sprint a sprint.
""".strip()

agent = Agent(
    model="us.anthropic.claude-sonnet-4-20250514",
    system_prompt=SYSTEM_PROMPT,
    tools=[echo_tool],   # agregar tools aquí conforme se implementan
)

app = BedrockAgentCoreApp()


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

    stream = agent.stream_async(prompt)
    async for event in stream:
        yield event


if __name__ == "__main__":
    app.run()

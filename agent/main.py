"""
agent/main.py — Prode Mundial 2026
====================================
Entrypoint del agente en Bedrock AgentCore Runtime.
Deploy: agentcore deploy  |  Local: agentcore launch --local
CI: deploy-dev.yml en push a dev.  # deploy-trigger: 2026-05-20

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
from agent.tools.invitation_tool import make_invitation_tool
from agent.tools.kb_retrieval_tool import kb_retrieval_tool
from agent.tools.match_tool import match_tool
from agent.tools.web_search_tool import web_search_tool
from src.services.onboarding_service import OnboardingService

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

_BASE_PROMPT = """
Sos el asistente del Prode Mundial 2026 ⚽
Ayudás a los usuarios a predecir partidos, consultar rankings, jugar trivia y explorar la historia de los mundiales.
Respondé siempre en el idioma del usuario. Sé conciso. Usá emojis con moderación.

Estado actual: MVP con fixture oficial en match_tool (72 partidos fase de grupos en DynamoDB).

REGLA CRÍTICA — PARTIDOS Y FIXTURE (única fuente: match_tool):
- Cualquier pregunta sobre partidos, rivales, horarios, fechas, sedes, grupos (equipos o fixture),
  "cuándo juega X", próximos partidos, calendario → SIEMPRE match_tool PRIMERO.
- NUNCA inventes partidos, horarios ni rivales desde memoria, KB o web.
- Si match_tool no devuelve datos, decí que no hay fixture cargado; no rellenes con KB/web.
- Equipos de un grupo: match_tool action=teams group_letter=X.
- Fixture de un grupo: match_tool action=group group_letter=X.
- Búsqueda por país/equipo: match_tool action=search team=...

JUGADORES Y ESTADÍSTICAS (Messi, Ronaldo, etc.):
- Siempre en scope. Usá kb_retrieval_tool y web_search_tool; nunca el mensaje genérico de "solo fútbol y mundiales".

CONOCIMIENTO — KB y web (orden obligatorio salvo fixture):
1) kb_retrieval_tool primero: historia, reglas, tácticas, cultura, datos ya en la KB.
   Esa tool hace fallback a web sola si la KB no alcanza.
2) web_search_tool cuando: comparativas (jugadores/selecciones), estadísticas, tendencias,
   noticias, resultados recientes, o si el prefetch/KB no respondió la pregunta.
   search_type=stats para comparativas/tendencias; news para noticias; result para marcadores.
3) PROHIBIDO responder solo "no está en la Knowledge Base" sin haber intentado web_search_tool
   (o sin recibir ya [Contexto web] en el mensaje).
4) NUNCA uses KB ni web para fixture/horarios/rivales — solo match_tool.
Si hay [Contexto Knowledge Base]: usalo si es relevante; si no alcanza → web_search_tool.
Si hay [Contexto web]: basá la respuesta ahí.
Si hay [Instrucción: ... web_search_tool]: debés invocar esa tool antes de dar por imposible la consulta.
Si piden link/código/invitación: SIEMPRE llamá invitation_tool (action=create o list).
El usuario ya fue validado como ACTIVE por Telegram; no le digas que no está activo.

ONBOARDING Y BIENVENIDA (no repetir /start):
- Telegram ya envió la bienvenida oficial en /start; NO la repitas ni te presentes ("Hola soy ProdeBot…").
- Si el usuario hace una pregunta concreta, PROHIBIDO responder solo con presentación o bienvenida genérica.
- Respondé con kb_retrieval_tool, web_search_tool o match_tool según la pregunta; knowledge_base y web están HABILITADAS.
- NO uses echo_tool para describir el MVP en lugar de responder la pregunta.
- Si onboarding_stage=M1_PENDING: respondé la consulta primero; como máximo UNA línea al final pidiendo alias (/listo = saltear).

Si el mensaje incluye [Fixture oficial — ...], respondé SOLO con esos datos (no KB ni web).
Si un día figura con "0 partido(s)" o "Sin partidos", decilo explícito; no niegues todo el rango.
Si el mensaje incluye [Contexto Knowledge Base], ignorá partidos/horarios ahí salvo que uses match_tool.
Si dice [Instrucción: consulta de PARTIDOS/FIXTURE], usá match_tool o el bloque [Fixture oficial].
También pueden usar /invitar [cupos] o /mis-invitaciones sin pasar por vos.
Las features de predicciones, rankings y trivia se habilitan sprint a sprint.
""".strip()

SYSTEM_PROMPT = f"{_BASE_PROMPT}\n\n{GUARDRAIL_SECTION}"

# Cuentas reseller: sin Anthropic. Dev: Mistral Pixtral (tool use). Nova: us.amazon.nova-pro-v1:0
_DEFAULT_MODEL = "us.mistral.pixtral-large-2502-v1:0"
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


def _build_agent(caller_user_id: str) -> Agent:
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
        tools=[
            echo_tool,
            match_tool,
            kb_retrieval_tool,
            web_search_tool,
            make_invitation_tool(caller_user_id),
        ],
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
    prompt = payload.get("prompt", "No encontré un mensaje. Enviá un JSON con la clave 'prompt'.")
    user_id = (
        payload.get("user_id")
        or payload.get("userId")
        or "anonymous"
    )
    platform = payload.get("platform", "UNKNOWN")

    logger.info(
        "Invocación | platform=%s | user_prefix=%s | dynamodb=%s",
        platform,
        user_id[:8] if user_id else "?",
        os.environ.get("DYNAMODB_TABLE", "?"),
    )

    agent_prompt = prompt
    if user_id not in ("anonymous", "unregistered", ""):
        session_ctx = OnboardingService().build_session_context(user_id)
        parts = [
            prompt,
            "[Sesión: usuario autenticado, podés usar invitation_tool para invitaciones.]",
        ]
        if session_ctx:
            parts.append(session_ctx)
        agent_prompt = "\n\n".join(parts)

    stream = _build_agent(user_id).stream_async(agent_prompt)
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

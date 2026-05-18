"""Contexto de onboarding para el agente — SPEC-019 / ISSUE-025."""
from __future__ import annotations

from src.dao.dynamo.user_dao import UserDAO

STAGE_M1_PENDING = "M1_PENDING"
STAGE_M1_COMPLETE = "M1_COMPLETE"
STAGE_M2_COMPLETE = "M2_COMPLETE"
STAGE_M3_COMPLETE = "M3_COMPLETE"

FIRST_POST_START_INSTRUCTION = (
    "[Instrucción: usuario recién registrado vía invitación; el bot ya le envió "
    "bienvenida fija por /start. NO repitas bienvenida ni te presentes como ProdeBot; "
    "respondé directamente su mensaje con kb_retrieval_tool, web_search_tool o match_tool "
    "según corresponda.]"
)


class OnboardingService:
    def __init__(self, user_dao: UserDAO | None = None):
        self._users = user_dao or UserDAO()

    def build_session_context(self, user_id: str) -> str:
        """Bloque para inyectar en el prompt del agente (perfil + reglas M1)."""
        if not user_id or user_id in ("anonymous", "unregistered"):
            return ""

        profile = self._users.get_profile(user_id)
        if not profile:
            return ""

        stage = profile.get("onboarding_stage", STAGE_M3_COMPLETE)
        alias = profile.get("alias", "Jugador")
        is_admin = bool(profile.get("is_admin"))

        lines = [
            f"[Perfil: alias={alias}, onboarding_stage={stage}, is_admin={is_admin}]",
        ]
        if stage == STAGE_M1_PENDING:
            lines.append(
                "[Onboarding M1: falta alias definitivo. Si el usuario hace una pregunta, "
                "respondé la pregunta primero con tools; como máximo una línea al final "
                "pidiendo cómo llamarlo en el ranking. /listo = saltear.]"
            )
        return "\n".join(lines)

"""agent/tools/trivia_tool.py — SPEC-2026-025 trivias."""
from __future__ import annotations

import json
import logging
from typing import Callable

from strands import tool

logger = logging.getLogger(__name__)


def _execute_trivia_tool(
    caller_user_id: str,
    action: str,
    *,
    level: str | None = None,
    topic: str | None = None,
    group_id: str | None = None,
    trivia_id: str | None = None,
    session_id: str | None = None,
    answer: str | None = None,
) -> str:
    from src.services.auth_service import INACTIVE_USER_MESSAGE
    from src.services.trivia_service import TriviaService

    if not caller_user_id or caller_user_id in ("anonymous", "unregistered"):
        return INACTIVE_USER_MESSAGE

    svc = TriviaService()
    action = (action or "play").strip().lower()

    try:
        if action == "play":
            result = svc.start_play(caller_user_id, level=level, topic=topic or "mundiales")
            return json.dumps(
                {
                    "message": result["message"],
                    "session_id": result["session_id"],
                    "note": "En Telegram el usuario responde con botones A-D.",
                },
                ensure_ascii=False,
            )

        if action == "answer":
            if session_id:
                return svc.answer_play_session(caller_user_id, session_id, answer or "")
            if trivia_id:
                return svc.answer_broadcast(caller_user_id, trivia_id, answer or "")
            return "Indicá session_id (ronda play) o trivia_id (trivia enviada)."

        if action == "send_admin":
            if not topic:
                return "Indicá topic (mundiales, records, jugadores, reglas, libre)."
            out = svc.create_and_send_general(
                caller_user_id,
                topic=topic,
                level=(level or "EXPERT").upper(),
            )
            n = len(out.get("delivery_targets") or [])
            return (
                f"Trivia {out['trivia_id']} creada en GLOBAL ({n} con Telegram listo para envío).\n"
                "Usá /trivia-admin en el bot para publicarla a todos.\n\n"
                f"{out['message']}"
            )

        if action == "create":
            draft = svc.create_group_trivia_draft(
                caller_user_id,
                group_id=group_id,
                topic=topic or "mundiales",
                level=svc.level_for_user(caller_user_id, level),
            )
            return draft["preview"] + f"\n\n(trivia_id={draft['trivia_id']} — confirmá con send_group)"

        if action == "send_group" and trivia_id:
            from src.dao.dynamo.group_dao import GroupDAO

            q = svc.generate_trivia_question(
                topic=topic or "mundiales",
                level=svc.level_for_user(caller_user_id, level),
            )
            gid = group_id or GroupDAO().get_owner_group_id(caller_user_id)
            if not gid:
                return "No tenés un grupo propio."
            out = svc.send_group_trivia(caller_user_id, trivia_id, q, gid)
            return f"Enviada a {out['recipient_count']} miembros.\n\n{out['message']}"

        if action == "stats" and trivia_id:
            return svc.stats_for_trivia(trivia_id)

        if action == "history":
            return "Historial de trivia: próximamente en Aurora v_user_prediction_history."

        return (
            "Acciones: play, answer, send_admin, create, send_group, stats. "
            "level=BASIC|MEDIUM|EXPERT, topic=mundiales|records|jugadores|reglas|libre."
        )
    except ValueError as exc:
        code = str(exc)
        if code == "DAILY_LIMIT":
            return "Ya jugaste tus 5 trivias de hoy. Volvé mañana 🌙"
        if code == "GENERATION_FAILED":
            return (
                "No pude generar una pregunta nueva ahora. "
                "Probá en unos minutos o con otro tema."
            )
        if code == "NOT_ADMIN":
            return "Solo el admin global puede enviar trivia general."
        if code == "NOT_OWNER":
            return "Solo el dueño del grupo puede crear trivia de grupo."
        if code == "NO_GROUP":
            return "No tenés un grupo propio. Creá uno con /crear-grupo."
        if code == "GROUP_TRIVIA_LIMIT":
            return "Ya hay 3 trivias activas en tu grupo. Esperá a que cierren."
        return f"No pude procesar la trivia: {code}"
    except Exception as exc:
        logger.warning("trivia_tool error: %s", exc, exc_info=True)
        return f"Error en trivia: {exc}"


def make_trivia_tool(caller_user_id: str) -> Callable:
    @tool
    def trivia_tool(
        action: str,
        level: str | None = None,
        topic: str | None = None,
        group_id: str | None = None,
        trivia_id: str | None = None,
        session_id: str | None = None,
        answer: str | None = None,
    ) -> str:
        """
        Trivias de fútbol y Mundial 2026 (múltiple choice A/B/C/D).

        action:
          play — nueva ronda personal (máx 5/día; nivel según perfil si level omitido)
          answer — responder (session_id de play o trivia_id de trivia enviada) + answer A|B|C|D
          send_admin — admin: trivia EXPERT a grupo GLOBAL (topic requerido)
          create — owner: vista previa trivia de grupo
          send_group — owner: enviar trivia_id al grupo
          stats — estadísticas de una trivia enviada
        """
        return _execute_trivia_tool(
            caller_user_id,
            action,
            level=level,
            topic=topic,
            group_id=group_id,
            trivia_id=trivia_id,
            session_id=session_id,
            answer=answer,
        )

    return trivia_tool

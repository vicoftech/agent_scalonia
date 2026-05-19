"""Comandos /trivia y callbacks A/B/C/D — SPEC-2026-025."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_TOPIC_MAP = {
    "mundiales": "mundiales",
    "historia": "mundiales",
    "records": "records",
    "récords": "records",
    "selecciones": "selecciones",
    "jugadores": "jugadores",
    "reglas": "reglas",
}


def handle_trivia_command(user_id: str, text: str) -> tuple[str | None, dict | None]:
    """
    Retorna (mensaje, reply_markup) o (None, None).
    """
    from src.services.trivia_service import TriviaService

    stripped = (text or "").strip()
    low = stripped.lower()
    svc = TriviaService()

    if low in ("/trivia", "trivia"):
        try:
            result = svc.start_play(user_id)
            return result["message"], result["keyboard"]
        except ValueError as exc:
            if str(exc) == "DAILY_LIMIT":
                return "Ya jugaste tus 5 rondas de trivia hoy. Volvé mañana 🌙", None
            raise

    if low.startswith("/trivia-admin"):
        parts = stripped.split(maxsplit=1)
        topic = _TOPIC_MAP.get((parts[1] if len(parts) > 1 else "records").lower(), "records")
        try:
            out = svc.create_and_send_general(user_id, topic=topic, level="EXPERT")
            return (
                f"✅ Trivia enviada a {out['recipient_count']} usuarios.\n\n{out['message']}",
                out["keyboard"],
            )
        except ValueError as exc:
            if str(exc) == "NOT_ADMIN":
                return "Solo el admin global puede usar /trivia-admin.", None
            raise

    if low.startswith("/trivia-grupo"):
        parts = stripped.split(maxsplit=1)
        topic = _TOPIC_MAP.get((parts[1] if len(parts) > 1 else "jugadores").lower(), "jugadores")
        try:
            draft = svc.create_group_trivia_draft(user_id, group_id=None, topic=topic, level="MEDIUM")
            sent = svc.send_group_trivia(user_id, draft["trivia_id"], draft["question"], draft["group_id"])
            return (
                f"✅ Trivia enviada a {sent['recipient_count']} miembros del grupo.\n\n{sent['message']}",
                sent["keyboard"],
            )
        except ValueError as exc:
            code = str(exc)
            if code == "NOT_OWNER":
                return "Solo el dueño del grupo puede crear trivia de grupo.", None
            if code == "NO_GROUP":
                return "No tenés un grupo propio.", None
            if code == "GROUP_TRIVIA_LIMIT":
                return "Ya hay 3 trivias activas en tu grupo.", None
            raise

    return None, None


def handle_trivia_callback(user_id: str, data: str) -> tuple[str, dict | None] | None:
    """trv:s:<session_id>:A o trv:t:<trivia_id>:B"""
    if not data.startswith("trv:"):
        return None

    from src.services.trivia_service import TriviaService

    parts = data.split(":")
    if len(parts) != 4:
        return None

    _, kind, ref, letter = parts
    svc = TriviaService()
    if kind == "s":
        return svc.answer_play_session(user_id, ref, letter), None
    if kind == "t":
        return svc.answer_broadcast(user_id, ref, letter), None
    return None

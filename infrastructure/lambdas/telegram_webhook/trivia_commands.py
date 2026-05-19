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


def _broadcast_admin_reply(out: dict, *, invoker_user_id: str) -> tuple[str, dict | None]:
    from handler import _get_token, _send_message
    from trivia_broadcast import broadcast_trivia_message

    targets = [
        t
        for t in (out.get("delivery_targets") or [])
        if t.get("user_id") != invoker_user_id
    ]
    token = _get_token()
    sent, _ = broadcast_trivia_message(
        delivery_targets=targets,
        message=out["message"],
        keyboard=out["keyboard"],
        token=token,
        send_message=_send_message,
    )
    pending = max(0, int(out.get("member_count", 0)) - len(out.get("delivery_targets") or []))
    lines = [
        f"✅ Trivia {out['trivia_id']} publicada.",
        f"📤 Enviada por Telegram a {sent} usuario(s).",
    ]
    if pending:
        lines.append(
            f"ℹ️ {pending} miembro(s) aún sin chat registrado "
            "(aparecerá al escribir al bot)."
        )
    lines.append("")
    lines.append(out["message"])
    return "\n".join(lines), out["keyboard"]


def _broadcast_group_reply(out: dict, *, invoker_user_id: str) -> tuple[str, dict | None]:
    from handler import _get_token, _send_message
    from trivia_broadcast import broadcast_trivia_message

    targets = [
        t
        for t in (out.get("delivery_targets") or [])
        if t.get("user_id") != invoker_user_id
    ]
    token = _get_token()
    sent, _ = broadcast_trivia_message(
        delivery_targets=targets,
        message=out["message"],
        keyboard=out["keyboard"],
        token=token,
        send_message=_send_message,
    )
    pending = max(0, int(out.get("member_count", 0)) - len(out.get("delivery_targets") or []))
    lines = [
        f"✅ Trivia {out['trivia_id']} publicada en tu grupo.",
        f"📤 Enviada por Telegram a {sent} miembro(s).",
    ]
    if pending:
        lines.append(f"ℹ️ {pending} sin chat registrado aún.")
    lines.append("")
    lines.append(out["message"])
    return "\n".join(lines), out["keyboard"]


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
            code = str(exc)
            if code == "DAILY_LIMIT":
                return "Ya jugaste tus 5 rondas de trivia hoy. Volvé mañana 🌙", None
            if code == "TRIVIA_BANK_EXHAUSTED":
                return (
                    "Por hoy no quedan preguntas nuevas para vos en el banco. "
                    "Volvé mañana o respondé las trivias publicadas del grupo."
                ), None
            raise

    if low.startswith("/trivia-admin"):
        parts = stripped.split(maxsplit=1)
        topic = _TOPIC_MAP.get((parts[1] if len(parts) > 1 else "records").lower(), "records")
        try:
            out = svc.create_and_send_general(user_id, topic=topic, level="EXPERT")
            return _broadcast_admin_reply(out, invoker_user_id=user_id)
        except ValueError as exc:
            code = str(exc)
            if code == "NOT_ADMIN":
                return "Solo el admin global puede usar /trivia-admin.", None
            if code == "TRIVIA_BANK_EXHAUSTED":
                return (
                    "Ya usamos todas las preguntas del banco para ese nivel/tema. "
                    "Probá otro tema o avisá al equipo para ampliar el banco."
                ), None
            raise

    if low.startswith("/trivia-grupo"):
        parts = stripped.split(maxsplit=1)
        topic = _TOPIC_MAP.get((parts[1] if len(parts) > 1 else "jugadores").lower(), "jugadores")
        try:
            draft = svc.create_group_trivia_draft(user_id, group_id=None, topic=topic, level="MEDIUM")
            sent = svc.send_group_trivia(user_id, draft["trivia_id"], draft["question"], draft["group_id"])
            return _broadcast_group_reply(sent, invoker_user_id=user_id)
        except ValueError as exc:
            code = str(exc)
            if code == "NOT_OWNER":
                return "Solo el dueño del grupo puede crear trivia de grupo.", None
            if code == "NO_GROUP":
                return "No tenés un grupo propio.", None
            if code == "GROUP_TRIVIA_LIMIT":
                return "Ya hay 3 trivias activas en tu grupo.", None
            if code == "TRIVIA_BANK_EXHAUSTED":
                return (
                    "Ya usamos todas las preguntas del banco para ese tema. "
                    "Probá otro tema en /trivia-grupo <tema>."
                ), None
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
    try:
        if kind == "s":
            return svc.answer_play_session(user_id, ref, letter)
        if kind == "t":
            return svc.answer_broadcast(user_id, ref, letter)
    except ValueError as exc:
        if str(exc) == "DAILY_LIMIT":
            return "Ya jugaste tus 5 rondas de trivia hoy. Volvé mañana 🌙"
    return None

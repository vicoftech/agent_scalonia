"""Menú de comandos de Telegram (setMyCommands) y texto /help."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

BOT_COMMANDS: list[dict[str, str]] = [
    {"command": "start", "description": "Registrarte o volver al inicio"},
    {"command": "help", "description": "Ver comandos disponibles"},
    {"command": "trivia", "description": "Jugar una trivia (máx. 5 por día)"},
    {"command": "invitar", "description": "Crear invitación (admin): /invitar 5"},
    {"command": "mis-invitaciones", "description": "Ver tus invitaciones activas"},
]

ADMIN_COMMANDS: list[dict[str, str]] = [
    {"command": "trivia-admin", "description": "Publicar trivia general (solo admin)"},
    {"command": "trivia-grupo", "description": "Trivia para tu grupo (dueño de grupo)"},
]

HELP_USER = """📖 Comandos del Prode Mundial 2026

/start — Registro o bienvenida
/help — Esta ayuda
/trivia — Una ronda de trivia con botones A B C D (máx. 5/día)

Invitaciones:
/invitar <cupos> — Solo admin: genera link de invitación
/mis-invitaciones — Tus invitaciones activas

También podés hablar con el agente en lenguaje natural sobre partidos, fixture y reglas."""

HELP_ADMIN_EXTRA = """
Solo admin:
/trivia-admin [tema] — Publica trivia Experto a todos (ej. records, jugadores)
  Temas: mundiales, records, jugadores, selecciones, reglas

Dueño de grupo:
/trivia-grupo [tema] — Trivia Intermedia a miembros del grupo"""


def register_bot_commands(token: str) -> None:
    from handler import TG_API, _post_json

    body = {"commands": BOT_COMMANDS}
    code, resp = _post_json(f"{TG_API}/bot{token}/setMyCommands", body, timeout=10)
    if code != 200 or not resp.get("ok"):
        logger.warning("setMyCommands failed code=%s resp=%s", code, resp)


def help_message(*, is_admin: bool = False, is_group_owner: bool = False) -> str:
    text = HELP_USER
    if is_admin or is_group_owner:
        text += HELP_ADMIN_EXTRA
    return text.strip()


def handle_help_command(user_id: str) -> str | None:
    from src.dao.dynamo.user_dao import UserDAO
    from src.dao.dynamo.group_dao import GroupDAO

    profile = UserDAO().get_profile(user_id) or {}
    is_admin = bool(profile.get("is_admin"))
    is_owner = bool(GroupDAO().get_owner_group_id(user_id))
    return help_message(is_admin=is_admin, is_group_owner=is_owner)

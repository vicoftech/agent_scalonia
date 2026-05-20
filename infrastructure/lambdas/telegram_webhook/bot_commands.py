"""Menú de comandos de Telegram (setMyCommands) y texto /help.

Telegram solo acepta nombres con a-z, 0-9 y _. Los handlers aceptan
también guiones (/crear-grupo, /trivia-admin) por compatibilidad.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Comandos visibles para todos (máx. descripción 256 chars, nombre ≤32)
BOT_COMMANDS: list[dict[str, str]] = [
    {"command": "start", "description": "Registrarte o volver al inicio"},
    {"command": "help", "description": "Ver comandos disponibles"},
    {"command": "grupos", "description": "Ver tus grupos"},
    {"command": "crear_grupo", "description": "Crear tu grupo (plan Free: 1 máx.)"},
    {"command": "editar_grupo", "description": "Administrar tu grupo (solo dueño)"},
    {"command": "miembros", "description": "Ver miembros de tu grupo"},
    {"command": "partidos", "description": "Ver partidos y predecir en tu grupo"},
    {"command": "predecir", "description": "Marcador — ej. /predecir ARG 2-0 ALG"},
    {"command": "completo", "description": "Variables opcionales de tu predicción"},
    {"command": "trivia", "description": "Jugar una trivia (máx. 5 por día)"},
    {"command": "trivia_grupo", "description": "Publicar trivia a tu grupo (dueño)"},
    {"command": "invitar", "description": "Crear invitación (elegís grupo destino)"},
    {"command": "mis_invitaciones", "description": "Ver tus invitaciones activas"},
    {"command": "unirme", "description": "Unirte con código — ej. /unirme abc12345"},
    {"command": "agregar_miembro", "description": "Sumar usuario por alias a tu grupo"},
]

# Solo admin global (scope chat del admin o menú ampliado)
ADMIN_COMMANDS: list[dict[str, str]] = [
    {"command": "trivia_admin", "description": "Trivia Experto para todos (solo admin)"},
    {"command": "admin_grupos", "description": "Panel de administración de grupos"},
    {
        "command": "crear_grupo_para",
        "description": "Crear grupo en nombre de un alias — ej. /crear_grupo_para vic",
    },
]


def commands_for_user(*, is_admin: bool = False) -> list[dict[str, str]]:
    """Lista única para setMyCommands según rol."""
    if is_admin:
        seen: set[str] = set()
        out: list[dict[str, str]] = []
        for cmd in BOT_COMMANDS + ADMIN_COMMANDS:
            if cmd["command"] not in seen:
                seen.add(cmd["command"])
                out.append(cmd)
        return out
    return list(BOT_COMMANDS)


HELP_USER = """📖 Comandos del Prode Mundial 2026

/start — Registro o bienvenida
/help — Esta ayuda
/grupos — Ver tus grupos
/crear-grupo (o /crear_grupo) — Crear tu grupo (plan Free: 1 máximo)
/editar-grupo — Administrar tu grupo (dueño)
/miembros — Ver miembros de tu grupo
/partidos — Fixture y botones para predecir (grupo activo)
/predecir ARG 2-0 ALG — Marcador rápido
/completo — Variables opcionales (expulsión, etc.)
/trivia — Una ronda de trivia con botones A B C D (máx. 5/día)
/trivia-grupo [tema] — Trivia a tu grupo (dueño)

Invitaciones:
/invitar <cupos> — Elegís grupo (admin: GLOBAL u otro) y generás el link
/mis_invitaciones — Tus invitaciones activas
/unirme <código> — Si ya tenés cuenta, unirte a un grupo con el código del link
/agregar-miembro <alias> — Sumar a alguien que ya usa el bot (dueño del grupo)

También podés hablar con el agente en lenguaje natural sobre partidos, fixture y reglas."""

HELP_ADMIN_EXTRA = """
Solo admin:
/trivia-admin [tema] — Publica trivia Experto a todos
/admin-grupos — Panel de administración de grupos
/crear-grupo-para <alias> — Crear grupo en nombre de otro usuario (nombre + avatar)"""


def register_bot_commands(
    token: str,
    *,
    chat_id: int | None = None,
    is_admin: bool = False,
) -> None:
    from handler import TG_API, _post_json

    default_cmds = commands_for_user(is_admin=False)
    body = {
        "commands": default_cmds,
        "scope": {"type": "all_private_chats"},
    }
    code, resp = _post_json(f"{TG_API}/bot{token}/setMyCommands", body, timeout=10)
    if code != 200 or not resp.get("ok"):
        logger.warning("setMyCommands default failed code=%s resp=%s", code, resp)
    else:
        logger.info("setMyCommands default ok (%s comandos)", len(default_cmds))

    if is_admin and chat_id is not None:
        admin_cmds = commands_for_user(is_admin=True)
        admin_body = {
            "commands": admin_cmds,
            "scope": {"type": "chat", "chat_id": int(chat_id)},
        }
        code2, resp2 = _post_json(
            f"{TG_API}/bot{token}/setMyCommands", admin_body, timeout=10
        )
        if code2 != 200 or not resp2.get("ok"):
            logger.warning("setMyCommands admin chat failed code=%s resp=%s", code2, resp2)
        else:
            logger.info("setMyCommands admin chat ok (%s comandos)", len(admin_cmds))


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

"""Menú de comandos de Telegram (setMyCommands) y texto /help.

Telegram solo acepta nombres con a-z, 0-9 y _. Los handlers aceptan
también guiones (/crear-grupo, /trivia-admin) por compatibilidad.

Menú público (botón /): atajos del teclado fijo + start, help, trivia.
Comandos de admin: solo en setMyCommands con scope del chat admin.
Otros (/predecir, /crear_grupo, invitaciones, etc.) siguen activos si se escriben.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Coinciden con telegram_keyboards.main_reply_keyboard (6 botones)
SHORTCUT_COMMANDS: list[dict[str, str]] = [
    {"command": "proximo", "description": "Próximos partidos del fixture"},
    {"command": "partidos", "description": "Partidos del Mundial y predecir"},
    {"command": "ask_ia", "description": "Consultá al agente IA sobre el Mundial"},
    {"command": "mi_puntuacion", "description": "Tu puntaje y predicciones"},
    {"command": "grupos", "description": "Ver y administrar tus grupos"},
    {"command": "reglas", "description": "Cómo predecir y puntuar"},
]

# Menú «/» para todos los usuarios (sin admin ni meta /menu)
MENU_COMMANDS: list[dict[str, str]] = SHORTCUT_COMMANDS + [
    {"command": "start", "description": "Registrarte o volver al inicio"},
    {"command": "help", "description": "Ayuda y lista de comandos"},
    {"command": "trivia", "description": "Jugar una trivia (máx. 5 por día)"},
]

ADMIN_COMMANDS: list[dict[str, str]] = [
    {"command": "trivia_admin", "description": "Trivia Experto para todos (solo admin)"},
    {"command": "admin_grupos", "description": "Panel de administración de grupos"},
    {
        "command": "crear_grupo_para",
        "description": "Crear grupo en nombre de un alias — ej. /crear_grupo_para vic",
    },
    {
        "command": "ia_otorgar",
        "description": "Otorgar consultas IA bonus — ej. /ia_otorgar alias 10",
    },
]

_COMMANDS_VERSION = os.environ.get("BOT_COMMANDS_VERSION", "7")


def commands_for_user(*, is_admin: bool = False) -> list[dict[str, str]]:
    """Lista para setMyCommands. Admin añade comandos solo en su chat (no menú global)."""
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    source = MENU_COMMANDS + (ADMIN_COMMANDS if is_admin else [])
    for cmd in source:
        if cmd["command"] not in seen:
            seen.add(cmd["command"])
            out.append(cmd)
    return out


HELP_USER = """📖 Comandos del Prode Mundial 2026

Menú / y teclado de abajo:
/proximo — Próximos partidos
/partidos — Fixture y predecir
/ask_ia — Consultas al agente IA (5/día gratis)
/mi_puntuacion — Tu puntaje
/grupos — Tus grupos
/reglas — Cómo predecir y puntuar
/start — Registro o bienvenida
/help — Esta ayuda
/trivia — Trivia con botones (máx. 5/día)

También podés escribir:
/predecir ARG 2-0 ALG — Marcador rápido
/completo — Variables extendidas de una predicción
/crear_grupo · /editar_grupo · /miembros · /invitar · /unirme

El agente IA solo responde dentro de /ask_ia (no texto libre suelto)."""

HELP_ADMIN_EXTRA = """
Solo admin global:
/trivia_admin [tema] — Trivia Experto a todos
/admin_grupos — Panel de grupos
/crear_grupo_para <alias> — Crear grupo para otro usuario
/ia_otorgar <alias> <cantidad> — Consultas IA bonus extra"""


def register_bot_commands(
    token: str,
    *,
    chat_id: int | None = None,
    is_admin: bool = False,
) -> None:
    from handler import TG_API, _post_json

    default_cmds = commands_for_user(is_admin=False)
    for scope in ({"type": "default"}, {"type": "all_private_chats"}):
        body = {"commands": default_cmds, "scope": scope}
        code, resp = _post_json(f"{TG_API}/bot{token}/setMyCommands", body, timeout=10)
        if code != 200 or not resp.get("ok"):
            logger.warning(
                "setMyCommands scope=%s failed code=%s resp=%s", scope, code, resp
            )
        else:
            logger.info(
                "setMyCommands scope=%s ok v=%s (%s cmds)",
                scope.get("type"),
                _COMMANDS_VERSION,
                len(default_cmds),
            )

    body_es = {
        "commands": default_cmds,
        "scope": {"type": "all_private_chats"},
        "language_code": "es",
    }
    _post_json(f"{TG_API}/bot{token}/setMyCommands", body_es, timeout=10)

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


def send_main_reply_keyboard(chat_id: int, token: str, *, hint: str | None = None) -> None:
    """Teclado fijo bajo el input (Partidos, Grupos, etc.)."""
    from handler import TG_API, _post_json
    from telegram_keyboards import main_reply_keyboard

    text = hint or "👇 Atajos — tocá un botón o el menú /"
    _post_json(
        f"{TG_API}/bot{token}/sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": main_reply_keyboard(),
        },
        timeout=10,
    )


def refresh_commands_for_chat(
    token: str, chat_id: int, *, is_admin: bool = False
) -> None:
    """Actualiza menú / + teclado fijo en el chat."""
    register_bot_commands(token, chat_id=chat_id, is_admin=is_admin)
    send_main_reply_keyboard(chat_id, token)


def rules_message() -> str:
    from src.services.prediction_rules import help_scoring_text

    return help_scoring_text()


def help_message(*, is_admin: bool = False) -> str:
    text = HELP_USER
    if is_admin:
        text += HELP_ADMIN_EXTRA
    return text.strip()


def handle_reglas_command(_user_id: str) -> str:
    return rules_message()


def handle_help_command(user_id: str) -> str | None:
    from src.dao.dynamo.user_dao import UserDAO

    profile = UserDAO().get_profile(user_id) or {}
    is_admin = bool(profile.get("is_admin"))
    return help_message(is_admin=is_admin)

"""Menú de comandos de Telegram (setMyCommands) y texto /help.

Telegram solo acepta nombres con a-z, 0-9 y _. Los handlers aceptan
también guiones (/crear-grupo) por compatibilidad.

Menú público (botón /): atajos del teclado + start, help, trivia.
Menú admin: scope «chat» del admin (mismos + trivia_admin, admin_grupos, etc.).
Comandos fuera del menú (/predecir, /invitar, …) siguen activos si se escriben.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# --- Teclado fijo (6 botones) = menú / ---
SHORTCUT_COMMANDS: list[dict[str, str]] = [
    {"command": "proximo", "description": "Próximos partidos del fixture"},
    {"command": "partidos", "description": "Partidos del Mundial y predecir"},
    {"command": "ask_ia", "description": "Consultá al agente IA (5/día gratis)"},
    {"command": "mi_puntuacion", "description": "Tu puntaje y predicciones"},
    {"command": "grupos", "description": "Ver y administrar tus grupos"},
    {"command": "reglas", "description": "Cómo predecir y puntuar"},
]

USER_MENU_COMMANDS: list[dict[str, str]] = SHORTCUT_COMMANDS + [
    {"command": "start", "description": "Registrarte o volver al inicio"},
    {"command": "help", "description": "Ayuda y lista de comandos"},
    {"command": "trivia", "description": "Jugar una trivia (máx. 5 por día)"},
]

ADMIN_MENU_EXTRA: list[dict[str, str]] = [
    {"command": "trivia_admin", "description": "Admin: trivia experto para todos"},
    {"command": "admin_grupos", "description": "Admin: panel de grupos"},
    {
        "command": "crear_grupo_para",
        "description": "Admin: crear grupo para un alias",
    },
    {
        "command": "ia_otorgar",
        "description": "Admin: otorgar consultas IA bonus",
    },
]

# Retrocompatibilidad con tests/docs
MENU_COMMANDS = USER_MENU_COMMANDS
ADMIN_COMMANDS = ADMIN_MENU_EXTRA

_COMMANDS_VERSION = os.environ.get("BOT_COMMANDS_VERSION", "8")

# Comandos con handler activo pero NO en el menú / (solo /help)
ACTIVE_UNLISTED_COMMANDS: tuple[str, ...] = (
    "predecir",
    "completo",
    "next",
    "crear_grupo",
    "editar_grupo",
    "miembros",
    "invitar",
    "mis_invitaciones",
    "unirme",
    "revocar",
    "agregar_miembro",
    "trivia_grupo",
    "cancel",
    "cancelar",
)

# Obsoletos: no deben aparecer en setMyCommands (forzar sync si el usuario los escribe)
DEPRECATED_COMMANDS: frozenset[str] = frozenset({
    "resultados",
    "mi_ranking",
})


def commands_for_user(*, is_admin: bool = False) -> list[dict[str, str]]:
    """Lista para setMyCommands."""
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    source = USER_MENU_COMMANDS + (ADMIN_MENU_EXTRA if is_admin else [])
    for cmd in source:
        name = cmd["command"]
        if name not in seen and name not in DEPRECATED_COMMANDS:
            seen.add(name)
            out.append(cmd)
    return out


def command_triggers_menu_sync(text: str) -> bool:
    """¿Actualizar menú / al usar este mensaje?"""
    raw = (text or "").strip().lower()
    if not raw.startswith("/"):
        return False
    name = raw.split("@")[0].split()[0].lstrip("/").replace("-", "_")
    if name in DEPRECATED_COMMANDS or name in ("menu", "ayuda"):
        return True
    public = {c["command"] for c in USER_MENU_COMMANDS}
    admin = {c["command"] for c in ADMIN_MENU_EXTRA}
    return name in public or name in admin


def _post_telegram_api(token: str, method: str, body: dict) -> tuple[int, dict]:
    from handler import TG_API, _post_json

    return _post_json(f"{TG_API}/bot{token}/{method}", body, timeout=10)


def _set_commands_for_scope(token: str, commands: list[dict], scope: dict) -> bool:
    code, resp = _post_telegram_api(
        token, "setMyCommands", {"commands": commands, "scope": scope}
    )
    if code != 200 or not resp.get("ok"):
        logger.warning(
            "setMyCommands scope=%s failed code=%s resp=%s", scope, code, resp
        )
        return False
    return True


def delete_chat_commands(token: str, chat_id: int) -> None:
    """Quita menú custom del chat; el usuario vuelve al menú global público."""
    code, resp = _post_telegram_api(
        token,
        "deleteMyCommands",
        {"scope": {"type": "chat", "chat_id": int(chat_id)}},
    )
    if code != 200 or not resp.get("ok"):
        logger.warning(
            "deleteMyCommands chat=%s failed code=%s resp=%s", chat_id, code, resp
        )
    else:
        logger.info("deleteMyCommands chat=%s ok", chat_id)


def register_global_commands(token: str) -> None:
    """Menú / para todos los chats privados (sin comandos admin)."""
    public_cmds = commands_for_user(is_admin=False)
    for scope in ({"type": "default"}, {"type": "all_private_chats"}):
        if _set_commands_for_scope(token, public_cmds, scope):
            logger.info(
                "setMyCommands scope=%s ok v=%s (%s cmds)",
                scope.get("type"),
                _COMMANDS_VERSION,
                len(public_cmds),
            )

    _post_telegram_api(
        token,
        "setMyCommands",
        {
            "commands": public_cmds,
            "scope": {"type": "all_private_chats"},
            "language_code": "es",
        },
    )


def sync_commands_for_chat(
    token: str, chat_id: int, *, is_admin: bool = False
) -> None:
    """
    - Siempre actualiza menú global (público).
    - Admin: menú extendido solo en su chat.
    - Usuario común: borra menú custom del chat (evita ver comandos admin viejos).
    """
    register_global_commands(token)

    if is_admin:
        admin_cmds = commands_for_user(is_admin=True)
        if _set_commands_for_scope(
            token,
            admin_cmds,
            {"type": "chat", "chat_id": int(chat_id)},
        ):
            logger.info(
                "setMyCommands admin chat=%s ok v=%s (%s cmds)",
                chat_id,
                _COMMANDS_VERSION,
                len(admin_cmds),
            )
    else:
        delete_chat_commands(token, chat_id)


def register_bot_commands(
    token: str,
    *,
    chat_id: int | None = None,
    is_admin: bool = False,
) -> None:
    """Compat: delega en sync_commands_for_chat."""
    if chat_id is not None:
        sync_commands_for_chat(token, int(chat_id), is_admin=is_admin)
    else:
        register_global_commands(token)


HELP_USER = """📖 Comandos del Prode Mundial 2026

Menú / (botón al lado del input):
/proximo — Próximos partidos
/partidos — Fixture y predecir
/ask_ia — Consultas al agente IA (5/día gratis)
/mi_puntuacion — Tu puntaje
/grupos — Tus grupos
/reglas — Cómo predecir y puntuar
/start — Registro o bienvenida
/help — Esta ayuda
/trivia — Trivia con botones (máx. 5/día)

También podés escribir (no están en el menú /):
/predecir ARG 2-0 ALG — Marcador rápido
/completo — Variables extendidas de una predicción
/crear_grupo · /editar_grupo · /miembros
/invitar · /unirme · /mis_invitaciones

El agente IA solo responde dentro de /ask_ia (no texto libre suelto)."""

HELP_ADMIN_EXTRA = """
Comandos admin (solo en tu menú / si sos admin global):
/trivia_admin [tema] — Trivia experto a todos
/admin_grupos — Panel de grupos
/crear_grupo_para <alias> — Crear grupo para otro usuario
/ia_otorgar <alias> <cantidad> — Consultas IA bonus extra"""


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
    """Actualiza menú / (global + scope chat) y teclado fijo."""
    sync_commands_for_chat(token, chat_id, is_admin=is_admin)
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


# Retrocompat tests
def should_refresh_bot_menu(text: str) -> bool:
    return command_triggers_menu_sync(text)

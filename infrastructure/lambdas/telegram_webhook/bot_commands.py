"""Menú de comandos de Telegram (setMyCommands) y texto /help.

Telegram solo acepta nombres con a-z, 0-9 y _. Los handlers aceptan
también guiones (/crear-grupo) por compatibilidad.

Menú público (botón /): atajos del teclado + start, help, trivia.
Menú admin: scope chat + language_code es (clientes en español).
Comandos fuera del menú (/predecir, /invitar, …) siguen activos si se escriben.
"""
from __future__ import annotations

import logging
import os
from typing import Any

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
    {
        "command": "ia_otorgar",
        "description": "Sumar consultas Ask IA: alias y cantidad",
    },
    {"command": "trivia_admin", "description": "Admin: trivia experto para todos"},
    {"command": "admin_grupos", "description": "Admin: panel de grupos"},
    {
        "command": "crear_grupo_para",
        "description": "Admin: crear grupo para un alias",
    },
    {"command": "noticia", "description": "Admin: buscar/publicar noticia"},
    {"command": "noticias_hoy", "description": "Admin: noticias enviadas hoy"},
]

MENU_COMMANDS = USER_MENU_COMMANDS
ADMIN_COMMANDS = ADMIN_MENU_EXTRA

_COMMANDS_VERSION = os.environ.get("BOT_COMMANDS_VERSION", "10")
_MENU_LANGUAGE = os.environ.get("BOT_COMMANDS_LANGUAGE", "es")


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


# Obsoletos: no deben aparecer en setMyCommands
DEPRECATED_COMMANDS: frozenset[str] = frozenset({
    "resultados",
    "mi_ranking",
})


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
    """HTTP a Telegram; no importa handler (evita env vars en scripts locales)."""
    import json
    import ssl
    import urllib.error
    import urllib.request

    tg_api = "https://api.telegram.org"
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{tg_api}/bot{token}/{method}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"ok": False, "description": raw}
        return e.code, data


def _private_chat_scopes(chat_id: int) -> list[dict[str, Any]]:
    """Scope chat en DM con el bot (chat_member no aplica en privados)."""
    return [{"type": "chat", "chat_id": int(chat_id)}]


def _set_commands_for_scope(
    token: str,
    commands: list[dict],
    scope: dict,
    *,
    language_code: str | None = None,
) -> bool:
    body: dict[str, Any] = {"commands": commands, "scope": scope}
    if language_code:
        body["language_code"] = language_code
    code, resp = _post_telegram_api(token, "setMyCommands", body)
    if code != 200 or not resp.get("ok"):
        logger.warning(
            "setMyCommands scope=%s lang=%s failed code=%s resp=%s",
            scope,
            language_code or "-",
            code,
            resp,
        )
        return False
    return True


def _delete_commands_for_scope(
    token: str, scope: dict, *, language_code: str | None = None
) -> None:
    body: dict[str, Any] = {"scope": scope}
    if language_code:
        body["language_code"] = language_code
    code, resp = _post_telegram_api(token, "deleteMyCommands", body)
    if code != 200 or not resp.get("ok"):
        logger.warning(
            "deleteMyCommands scope=%s lang=%s failed code=%s resp=%s",
            scope,
            language_code or "-",
            code,
            resp,
        )


def delete_chat_commands(token: str, chat_id: int) -> None:
    """Quita menús custom del chat; vuelve al menú global público."""
    for scope in _private_chat_scopes(chat_id):
        _delete_commands_for_scope(token, scope)
        _delete_commands_for_scope(token, scope, language_code=_MENU_LANGUAGE)
    logger.info("deleteMyCommands chat=%s ok", chat_id)


def _set_admin_chat_commands(token: str, chat_id: int, commands: list[dict]) -> bool:
    """
    Menú admin en chat privado.

    Telegram en español usa language_code=es; sin eso el menú global (9 cmds)
    pisa el scope chat y no aparecen ia_otorgar ni otros admin.
    """
    ok = False
    names = [c["command"] for c in commands]
    for scope in _private_chat_scopes(chat_id):
        if _set_commands_for_scope(token, commands, scope):
            ok = True
        if _set_commands_for_scope(
            token, commands, scope, language_code=_MENU_LANGUAGE
        ):
            ok = True
    if ok:
        logger.info(
            "admin menu chat=%s v=%s cmds=%s includes_ia_otorgar=%s",
            chat_id,
            _COMMANDS_VERSION,
            len(commands),
            "ia_otorgar" in names,
        )
    return ok


def register_global_commands(token: str) -> None:
    """Menú / público para todos los chats privados."""
    public_cmds = commands_for_user(is_admin=False)
    for scope in ({"type": "default"}, {"type": "all_private_chats"}):
        if _set_commands_for_scope(token, public_cmds, scope):
            logger.info(
                "setMyCommands scope=%s ok v=%s (%s cmds)",
                scope.get("type"),
                _COMMANDS_VERSION,
                len(public_cmds),
            )

    _set_commands_for_scope(
        token,
        public_cmds,
        {"type": "all_private_chats"},
        language_code=_MENU_LANGUAGE,
    )


def sync_commands_for_chat(
    token: str, chat_id: int, *, is_admin: bool = False
) -> None:
    register_global_commands(token)

    if is_admin:
        admin_cmds = commands_for_user(is_admin=True)
        _set_admin_chat_commands(token, chat_id, admin_cmds)
    else:
        delete_chat_commands(token, chat_id)


def register_bot_commands(
    token: str,
    *,
    chat_id: int | None = None,
    is_admin: bool = False,
) -> None:
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
Comandos admin (en tu menú /):
/ia_otorgar <alias> <cantidad> — Sumar consultas Ask IA (ej. /ia_otorgar toti 10)
/trivia_admin [tema] — Trivia experto a todos
/admin_grupos — Panel de grupos
/crear_grupo_para <alias> — Crear grupo para otro usuario
/noticia — Buscar noticia (Tavily) o publicar con URL/texto
/noticia_publicar — Publicar borrador
/noticias_hoy — Listado del día

Si no ves /ia_otorgar en el menú, mandá /menu para refrescar."""


def admin_menu_hint() -> str:
    return (
        "👑 Menú admin actualizado.\n\n"
        "Comandos extra en el botón /:\n"
        "· /ia_otorgar — sumar consultas Ask IA\n"
        "· /trivia_admin — trivia experto\n"
        "· /admin_grupos — panel grupos\n"
        "· /crear_grupo_para — grupo para otro alias\n"
        "· /noticia — noticias admin\n"
        "· /noticias_hoy — enviadas hoy"
    )


def send_main_reply_keyboard(chat_id: int, token: str, *, hint: str | None = None) -> None:
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
    sync_commands_for_chat(token, chat_id, is_admin=is_admin)
    hint = admin_menu_hint() if is_admin else None
    send_main_reply_keyboard(chat_id, token, hint=hint)


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


def should_refresh_bot_menu(text: str) -> bool:
    return command_triggers_menu_sync(text)

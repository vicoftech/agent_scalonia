"""Menú setMyCommands — público vs admin, sin comandos obsoletos."""
from unittest.mock import patch

from infrastructure.lambdas.telegram_webhook.bot_commands import (
    ADMIN_MENU_EXTRA,
    DEPRECATED_COMMANDS,
    USER_MENU_COMMANDS,
    command_triggers_menu_sync,
    commands_for_user,
    help_message,
    rules_message,
    should_refresh_bot_menu,
)


def test_shortcuts_are_first_in_menu():
    cmds = commands_for_user(is_admin=False)
    names = [c["command"] for c in cmds[:6]]
    assert names == [
        "proximo",
        "partidos",
        "ask_ia",
        "mi_puntuacion",
        "grupos",
        "reglas",
    ]


def test_public_menu_has_no_admin_or_legacy():
    public = {c["command"] for c in commands_for_user(is_admin=False)}
    admin_only = {c["command"] for c in ADMIN_MENU_EXTRA}
    assert not public & admin_only
    assert not public & DEPRECATED_COMMANDS
    assert "menu" not in public
    assert "predecir" not in public
    assert "resultados" not in public
    assert len(commands_for_user(is_admin=False)) == len(USER_MENU_COMMANDS)


def test_admin_menu_includes_admin_commands():
    admin = {c["command"] for c in commands_for_user(is_admin=True)}
    admin_list = commands_for_user(is_admin=True)
    assert admin_list[len(USER_MENU_COMMANDS)]["command"] == "ia_otorgar"
    assert "trivia_admin" in admin
    assert "admin_grupos" in admin
    assert "ia_otorgar" in admin
    assert "ask_ia" in admin
    assert "crear_grupo_para" in admin
    assert len(admin) == len(USER_MENU_COMMANDS) + len(ADMIN_MENU_EXTRA)


def test_admin_menu_extra_not_in_public():
    public_names = [c["command"] for c in commands_for_user(is_admin=False)]
    assert "trivia_admin" not in public_names


def test_help_mentions_ask_ia_not_free_agent():
    assert "/ask_ia" in help_message(is_admin=False)
    assert "texto libre" in help_message(is_admin=False).lower() or "solo responde" in help_message(
        is_admin=False
    ).lower()


def test_should_refresh_on_shortcuts_and_deprecated():
    assert command_triggers_menu_sync("/partidos")
    assert command_triggers_menu_sync("/ask_ia")
    assert command_triggers_menu_sync("/resultados")
    assert command_triggers_menu_sync("/menu")
    assert should_refresh_bot_menu("/proximo")
    assert not command_triggers_menu_sync("/predecir ARG 2-0 ALG")


def test_rules_message_has_scoring_not_commands():
    text = rules_message()
    assert "Básica" in text
    assert "/partidos" not in text


def test_help_admin_only_for_global_admin():
    assert "trivia_admin" not in help_message(is_admin=False)
    assert "trivia_admin" in help_message(is_admin=True)


@patch("infrastructure.lambdas.telegram_webhook.bot_commands.register_global_commands")
@patch("infrastructure.lambdas.telegram_webhook.bot_commands.delete_chat_commands")
@patch("infrastructure.lambdas.telegram_webhook.bot_commands._set_commands_for_scope")
def test_sync_admin_sets_chat_scope(mock_set, mock_delete, mock_global):
    from infrastructure.lambdas.telegram_webhook.bot_commands import sync_commands_for_chat

    mock_set.return_value = True
    sync_commands_for_chat("token", 12345, is_admin=True)
    mock_global.assert_called_once()
    mock_delete.assert_not_called()
    assert mock_set.call_count == 1
    scope = mock_set.call_args[0][2]
    assert scope["type"] == "chat"
    assert scope["chat_id"] == 12345


@patch("infrastructure.lambdas.telegram_webhook.bot_commands.register_global_commands")
@patch("infrastructure.lambdas.telegram_webhook.bot_commands.delete_chat_commands")
@patch("infrastructure.lambdas.telegram_webhook.bot_commands._set_commands_for_scope")
def test_sync_non_admin_deletes_chat_scope(mock_set, mock_delete, mock_global):
    from infrastructure.lambdas.telegram_webhook.bot_commands import sync_commands_for_chat

    sync_commands_for_chat("token", 99999, is_admin=False)
    mock_global.assert_called_once()
    mock_delete.assert_called_once_with("token", 99999)
    mock_set.assert_not_called()

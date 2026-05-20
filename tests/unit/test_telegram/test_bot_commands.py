"""Menú setMyCommands — atajos primero."""
from infrastructure.lambdas.telegram_webhook.bot_commands import (
    SHORTCUT_COMMANDS,
    commands_for_user,
)
from infrastructure.lambdas.telegram_webhook.shortcut_commands import (
    should_refresh_bot_menu,
)


def test_shortcuts_are_first_in_menu():
    cmds = commands_for_user(is_admin=False)
    names = [c["command"] for c in cmds[:4]]
    assert names == ["partidos", "mi_puntuacion", "grupos", "resultados"]


def test_menu_command_in_list():
    names = [c["command"] for c in commands_for_user()]
    assert "menu" in names
    assert len(SHORTCUT_COMMANDS) == 4


def test_should_refresh_on_shortcuts():
    assert should_refresh_bot_menu("/partidos")
    assert should_refresh_bot_menu("/mi_puntuacion")
    assert should_refresh_bot_menu("/menu")
    assert not should_refresh_bot_menu("/predecir ARG 2-0 ALG")

"""Menú setMyCommands — atajos primero."""
from infrastructure.lambdas.telegram_webhook.bot_commands import (
    SHORTCUT_COMMANDS,
    commands_for_user,
    rules_message,
)
from infrastructure.lambdas.telegram_webhook.shortcut_commands import (
    should_refresh_bot_menu,
)


def test_shortcuts_are_first_in_menu():
    cmds = commands_for_user(is_admin=False)
    names = [c["command"] for c in cmds[:6]]
    assert names == [
        "proximo",
        "partidos",
        "resultados",
        "mi_puntuacion",
        "grupos",
        "reglas",
    ]


def test_menu_not_in_shortcuts():
    shortcut_names = {c["command"] for c in SHORTCUT_COMMANDS}
    assert "menu" not in shortcut_names
    assert len(SHORTCUT_COMMANDS) == 6
    all_names = [c["command"] for c in commands_for_user()]
    assert "menu" in all_names


def test_should_refresh_on_shortcuts():
    assert should_refresh_bot_menu("/partidos")
    assert should_refresh_bot_menu("/proximo")
    assert should_refresh_bot_menu("/reglas")
    assert should_refresh_bot_menu("/menu")
    assert not should_refresh_bot_menu("/predecir ARG 2-0 ALG")


def test_rules_message_has_scoring_not_commands():
    text = rules_message()
    assert "Básica" in text
    assert "/partidos" not in text

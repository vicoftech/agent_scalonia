"""Menú setMyCommands — atajos primero, sin admin en menú global."""
from infrastructure.lambdas.telegram_webhook.bot_commands import (
    ADMIN_COMMANDS,
    MENU_COMMANDS,
    SHORTCUT_COMMANDS,
    commands_for_user,
    help_message,
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


def test_public_menu_has_no_admin_or_legacy_meta():
    public = {c["command"] for c in commands_for_user(is_admin=False)}
    admin_only = {c["command"] for c in ADMIN_COMMANDS}
    assert not public & admin_only
    assert "menu" not in public
    assert "predecir" not in public
    assert "crear_grupo" not in public
    assert len(commands_for_user(is_admin=False)) == len(MENU_COMMANDS)


def test_admin_menu_includes_admin_commands():
    admin = {c["command"] for c in commands_for_user(is_admin=True)}
    assert "trivia_admin" in admin
    assert "admin_grupos" in admin
    assert "partidos" in admin


def test_menu_matches_shortcut_count():
    assert len(SHORTCUT_COMMANDS) == 6


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


def test_help_admin_only_for_global_admin():
    assert "trivia_admin" not in help_message(is_admin=False)
    assert "trivia_admin" in help_message(is_admin=True)

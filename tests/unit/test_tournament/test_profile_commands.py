"""SPEC-048 — profile commands."""
from unittest.mock import MagicMock, patch

from infrastructure.lambdas.telegram_webhook.profile_commands import (  # noqa: PLC0415
    handle_perfil_command,
    matches_perfil_command,
)


def test_matches_perfil():
    assert matches_perfil_command("/perfil")
    assert matches_perfil_command("/perfil@ProdeBot")


@patch("infrastructure.lambdas.telegram_webhook.profile_commands.show_profile_hub")
def test_handle_perfil_command(mock_hub):
    mock_hub.return_value = ("hub", {"inline_keyboard": []})
    out = handle_perfil_command("u1", "/perfil")
    assert out == ("hub", {"inline_keyboard": []})

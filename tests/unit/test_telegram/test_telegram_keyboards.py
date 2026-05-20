from infrastructure.lambdas.telegram_webhook.telegram_keyboards import (
    normalize_reply_button,
    main_reply_keyboard,
)


def test_normalize_reply_button():
    assert normalize_reply_button("⚽ Partidos") == "/partidos"
    assert normalize_reply_button("📊 Mi puntaje") == "/mi_puntuacion"


def test_main_reply_keyboard_structure():
    kb = main_reply_keyboard()
    assert "keyboard" in kb
    assert len(kb["keyboard"]) >= 2

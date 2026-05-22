from infrastructure.lambdas.telegram_webhook.telegram_keyboards import (
    normalize_reply_button,
    main_reply_keyboard,
)


def test_normalize_reply_button():
    assert normalize_reply_button("⏭️ Próximo") == "/proximo"
    assert normalize_reply_button("⚽ Partidos") == "/partidos"
    assert normalize_reply_button("📊 Mi puntaje") == "/mi_puntuacion"
    assert normalize_reply_button("📖 Reglas") == "/reglas"


def test_main_reply_keyboard_structure():
    kb = main_reply_keyboard()
    assert "keyboard" in kb
    assert len(kb["keyboard"]) == 3
    labels = [btn["text"] for row in kb["keyboard"] for btn in row]
    assert "📖 Reglas" in labels
    assert "📋 Menú" not in labels

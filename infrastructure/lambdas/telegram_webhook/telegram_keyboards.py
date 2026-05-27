"""Teclado fijo (ReplyKeyboard) + mapeo a comandos."""
from __future__ import annotations

# Texto del botón → comando interno (clave en minúsculas)
REPLY_BUTTON_TO_COMMAND: dict[str, str] = {
    "⏭️ próximo": "/proximo",
    "⚽ partidos": "/partidos",
    "🤖 ask ia": "/ask_ia",
    "📊 mi puntaje": "/mi_puntuacion",
    "👥 grupos": "/grupos",
    "📖 reglas": "/reglas",
}


def main_reply_keyboard() -> dict:
    """Botones fijos bajo el campo de texto (persisten hasta remove)."""
    return {
        "keyboard": [
            [
                {"text": "⏭️ Próximo"},
                {"text": "⚽ Partidos"},
            ],
            [
                {"text": "🤖 Ask IA"},
                {"text": "📊 Mi puntaje"},
            ],
            [
                {"text": "👥 Grupos"},
                {"text": "📖 Reglas"},
            ],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "input_field_placeholder": "Elegí un atajo o /ask_ia para consultar",
    }


def normalize_reply_button(text: str) -> str | None:
    """Convierte tap en teclado fijo al comando equivalente."""
    key = (text or "").strip().lower()
    return REPLY_BUTTON_TO_COMMAND.get(key)


def merge_with_main_keyboard(inline_markup: dict | None) -> dict:
    """Prioriza inline; el reply keyboard ya quedó activo en el chat."""
    return inline_markup if inline_markup else main_reply_keyboard()

"""Teclados inline Ask IA — SPEC-2026-043."""


def post_response_keyboard(*, has_credits: bool) -> dict:
    rows: list[list[dict[str, str]]] = []
    if has_credits:
        rows.append([{"text": "💬 Otra consulta", "callback_data": "ia:more"}])
    else:
        rows.append([{"text": "☕ Más consultas", "callback_data": "ia:upgrade"}])
    rows.append([{"text": "🛑 Terminar", "callback_data": "ia:end"}])
    return {"inline_keyboard": rows}


def no_credits_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "☕ Más consultas", "callback_data": "ia:upgrade"}],
            [{"text": "🛑 Terminar", "callback_data": "ia:end"}],
        ]
    }


def upgrade_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🛑 Cancelar", "callback_data": "ia:end"}],
        ]
    }

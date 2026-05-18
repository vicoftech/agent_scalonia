"""Utilidades para deep links de Telegram (/start <payload>)."""


def parse_start_payload(text: str) -> str | None:
    """Extrae invite_id de '/start a3F9bC1d'. Retorna None si no hay payload."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) == 2 and parts[0] == "/start":
        payload = parts[1].strip()
        return payload if payload else None
    return None

"""Teclados inline Telegram — onboarding M1 (SPEC-019)."""
from __future__ import annotations

from src.fixtures.onboarding_teams import M1_TEAM_GRID

LANG_OPTIONS = [
    ("es", "🇦🇷 Español"),
    ("pt", "🇧🇷 Português"),
    ("en", "🇺🇸 English"),
    ("fr", "🇫🇷 Français"),
]


def team_keyboard() -> dict:
    rows: list[list[dict]] = []
    row: list[dict] = []
    for code, label in M1_TEAM_GRID:
        row.append({"text": label, "callback_data": f"onb:team:{code}"})
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{"text": "✏️ Otra / sin favorita", "callback_data": "onb:team:none"}])
    return {"inline_keyboard": rows}


def language_keyboard() -> dict:
    rows = [[{"text": label, "callback_data": f"onb:lang:{code}"}] for code, label in LANG_OPTIONS]
    rows.append([{"text": "✓ Confirmar Español", "callback_data": "onb:lang:es"}])
    return {"inline_keyboard": rows}

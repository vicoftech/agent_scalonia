"""UI Telegram — hub Perfil y wizard torneo (SPEC-2026-048)."""
from __future__ import annotations

from typing import Any

from src.services.onboarding_telegram_ui import LANG_OPTIONS
from src.services.tournament_prediction_service import WIZARD_FIELDS, WIZARD_LABELS
from src.services.team_flags import format_team_display

GOAL_OPTIONS = [
    ("competitive", "🏆 Ganar el prode"),
    ("social", "😄 Divertirme con amigos"),
    ("educational", "📚 Aprender sobre fútbol"),
]

TRIVIA_LEVEL_OPTIONS = [
    ("easy", "😊 Casual"),
    ("medium", "🔥 Fanático"),
    ("hard", "🧠 Enciclopedia"),
]


def profile_hub_keyboard(*, editable_torneo: bool) -> dict[str, Any]:
    rows = [
        [
            {"text": "🇦🇷 Cambiar hincha", "callback_data": "prf:edit:team"},
            {"text": "🌐 Cambiar idioma", "callback_data": "prf:edit:lang"},
        ],
        [
            {"text": "⭐ Cambiar jugador", "callback_data": "prf:edit:player"},
            {"text": "🧠 Nivel trivia", "callback_data": "prf:edit:trivia"},
        ],
        [
            {"text": "🎯 Cambiar objetivo", "callback_data": "prf:edit:goal"},
            {"text": "🏆 Predicciones torneo", "callback_data": "prf:edit:torneo"},
        ],
    ]
    return {"inline_keyboard": rows}


def m4_cta_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "Completar ahora", "callback_data": "prf:m4:start"}],
            [{"text": "Después", "callback_data": "prf:m4:later"}],
        ]
    }


def wizard_menu_keyboard(*, editable: bool) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    step_map = {
        1: "Campeón",
        2: "Finalista",
        3: "Mejor jugador",
        4: "Goleador",
        5: "Arquero",
        6: "Mejor joven",
        7: "Revelación",
    }
    for step, label in step_map.items():
        rows.append([{"text": f"{step}. {label}", "callback_data": f"prf:w:{step}"}])
    if editable:
        rows.append([{"text": "✅ Confirmar todo", "callback_data": "prf:confirm"}])
    rows.append(
        [
            {"text": "← Perfil", "callback_data": "prf:home"},
            {"text": "Omitir", "callback_data": "prf:skip"},
        ]
    )
    return {"inline_keyboard": rows}


def team_picker_keyboard(
    *,
    step: int,
    codes: list[str],
    page: int,
    total_pages: int,
) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    row: list[dict[str, str]] = []
    for code in codes:
        row.append(
            {
                "text": format_team_display(code)[:64],
                "callback_data": f"prf:pick:{step}:{code}",
            }
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav: list[dict[str, str]] = []
    if page > 0:
        nav.append({"text": "◀️", "callback_data": f"prf:tm:{step}:{page - 1}"})
    if page + 1 < total_pages:
        nav.append({"text": "▶️", "callback_data": f"prf:tm:{step}:{page + 1}"})
    if nav:
        rows.append(nav)
    rows.append([{"text": "← Wizard", "callback_data": "prf:edit:torneo"}])
    return {"inline_keyboard": rows}


def player_picker_keyboard(
    *,
    step: int,
    players: list[str],
) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    row: list[dict[str, str]] = []
    for name in players:
        row.append({"text": f"⚽ {name}", "callback_data": f"prf:pl:{step}:{name[:40]}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            {"text": "✏️ Escribir otro", "callback_data": f"prf:pl:{step}:__other__"},
            {"text": "← Wizard", "callback_data": "prf:edit:torneo"},
        ]
    )
    return {"inline_keyboard": rows}


def goal_keyboard() -> dict[str, Any]:
    rows = [[{"text": label, "callback_data": f"prf:goal:{code}"}] for code, label in GOAL_OPTIONS]
    rows.append([{"text": "← Perfil", "callback_data": "prf:home"}])
    return {"inline_keyboard": rows}


def trivia_level_keyboard() -> dict[str, Any]:
    rows = [
        [{"text": label, "callback_data": f"prf:trivia:{code}"}]
        for code, label in TRIVIA_LEVEL_OPTIONS
    ]
    rows.append([{"text": "← Perfil", "callback_data": "prf:home"}])
    return {"inline_keyboard": rows}


def profile_team_keyboard() -> dict[str, Any]:
    from src.fixtures.onboarding_teams import M1_TEAM_GRID

    rows: list[list[dict[str, str]]] = []
    row: list[dict[str, str]] = []
    for code, label in M1_TEAM_GRID:
        row.append({"text": label, "callback_data": f"prf:team:{code}"})
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{"text": "✏️ Sin favorita", "callback_data": "prf:team:none"}])
    rows.append([{"text": "← Perfil", "callback_data": "prf:home"}])
    return {"inline_keyboard": rows}


def profile_lang_keyboard() -> dict[str, Any]:
    rows = [[{"text": label, "callback_data": f"prf:lang:{code}"}] for code, label in LANG_OPTIONS]
    rows.append([{"text": "← Perfil", "callback_data": "prf:home"}])
    return {"inline_keyboard": rows}


def wizard_step_title(step: int) -> str:
    field = WIZARD_FIELDS[step - 1]
    return WIZARD_LABELS.get(field, f"Paso {step}")

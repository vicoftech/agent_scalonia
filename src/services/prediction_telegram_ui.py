"""Teclados inline predicciones — SPEC-2026-021."""
from __future__ import annotations

from typing import Any

from src.services.team_flags import flag_emoji

TELEGRAM_INLINE_BUTTON_TEXT_MAX = 64

KO_PHASES = frozenset(
    {"R16", "ROUND_OF_32", "ROUND_OF_16", "QF", "QUARTER_FINAL", "SF", "SEMI_FINAL", "FINAL", "THIRD_PLACE"}
)


def merge_button_rows(rows: list[list[dict[str, str]]]) -> dict:
    return {"inline_keyboard": rows}


def _fit_button_label(text: str, *, max_len: int = TELEGRAM_INLINE_BUTTON_TEXT_MAX) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def partido_list_button_label(
    match: dict,
    *,
    match_number: int,
    group_letter: str,
    date_label: str,
    has_prediction: bool,
    is_predictable: bool,
) -> str:
    """
    Etiqueta de un partido en /partidos (máx. 64 caracteres Telegram).
    Ej.: Match #1 🇦🇷 ARG vs 🇩🇿 ALG | Grupo J | 16/06 | ⏳
    """
    home = (match.get("home_team") or "???").upper()[:3]
    away = (match.get("away_team") or "???").upper()[:3]
    gl = (group_letter or "—").strip().upper()[:1]
    if has_prediction:
        status_icon = "✅"
    elif is_predictable:
        status_icon = "⏳"
    else:
        status_icon = "🔒"

    label = (
        f"Match #{match_number} {flag_emoji(home)} {home} vs "
        f"{flag_emoji(away)} {away} | Grupo {gl} | {date_label} | {status_icon}"
    )
    if len(label) <= TELEGRAM_INLINE_BUTTON_TEXT_MAX:
        return label

    compact = (
        f"#{match_number} {flag_emoji(home)}{home} v {flag_emoji(away)}{away} "
        f"| G{gl} | {date_label} | {status_icon}"
    )
    return _fit_button_label(compact)


def partidos_nav_keyboard(page: int, total_pages: int, grp8: str) -> list[dict[str, str]] | None:
    """Fila ◀️ página ▶️ para /partidos (fase de grupos)."""
    if total_pages <= 1:
        return None
    row: list[dict[str, str]] = []
    if page > 0:
        row.append({"text": "◀️ Anterior", "callback_data": f"prd:pg:{page - 1}:{grp8}"})
    row.append({"text": f"{page + 1}/{total_pages}", "callback_data": "prd:noop"})
    if page < total_pages - 1:
        row.append({"text": "Siguiente ▶️", "callback_data": f"prd:pg:{page + 1}:{grp8}"})
    return row


def no_group_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "➕ Crear mi grupo", "callback_data": "grp:list"}],
        ],
    }


def score_picker_keyboard(match: dict, match_number: int, grp8: str) -> dict:
    scores = ["2-0", "1-0", "3-1", "1-1", "0-1"]
    rows: list[list[dict[str, str]]] = []
    for sc in scores:
        rows.append(
            [{"text": sc, "callback_data": f"prd:s:{match_number}:{sc}:{grp8}"}]
        )
    rows.append(
        [{"text": "✏️ Otro marcador", "callback_data": f"prd:x:{match_number}:{grp8}"}]
    )
    return {"inline_keyboard": rows}


def change_existing_keyboard(match_number: int, grp8: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Sí, cambiar", "callback_data": f"prd:ch:{match_number}:{grp8}"},
                {"text": "No, mantener", "callback_data": "prd:noop"},
            ],
        ],
    }


def after_save_keyboard(match: dict, group_id: str) -> dict:
    g8 = group_id.replace("-", "")[:8]
    n = int(match.get("match_number", 0))
    return {
        "inline_keyboard": [
            [{"text": "⚡ Listo (solo resultado)", "callback_data": f"prd:done:{n}:{g8}"}],
            [{"text": "🎯 Predicción completa", "callback_data": f"prd:full:{n}:{g8}"}],
        ],
    }


def completo_wizard_red_keyboard(match_number: int, grp8: str) -> dict:
    n, g = match_number, grp8
    return {
        "inline_keyboard": [
            [{"text": "🟥 No habrá roja", "callback_data": f"prd:fw:rd:0:{n}:{g}"}],
            [{"text": "🟥 Sí habrá roja (+2)", "callback_data": f"prd:fw:rd:1:{n}:{g}"}],
            [{"text": "⏭️ Saltar este paso", "callback_data": f"prd:fw:skip:{n}:{g}"}],
            [{"text": "✅ Terminar", "callback_data": f"prd:fw:done:{n}:{g}"}],
        ],
    }


def completo_menu_keyboard(match_number: int, grp8: str) -> dict:
    """Atajo desde /completo (mismo wizard que prd:full)."""
    n, g = match_number, grp8
    return {
        "inline_keyboard": [
            [{"text": "🎯 Iniciar predicción completa", "callback_data": f"prd:full:{n}:{g}"}],
            [{"text": "🟥 Solo expulsión (rápido)", "callback_data": f"prd:rd:{n}:0:{g}"}],
            [{"text": "🟥 Sí habrá roja", "callback_data": f"prd:rd:{n}:1:{g}"}],
        ],
    }


def group_picker_keyboard(groups: list[dict[str, Any]]) -> dict:
    rows: list[list[dict[str, str]]] = []
    for g in groups:
        gid = g.get("group_id", "")
        g8 = gid.replace("-", "")[:8]
        label = f"{g.get('avatar', '⚽')} {(g.get('name') or gid)[:26]}"
        rows.append([{"text": label, "callback_data": f"prd:sg:{g8}"}])
    return {"inline_keyboard": rows}


def ko_playoff_keyboard(match: dict, match_number: int, score: str, grp8: str) -> dict:
    """Empate en KO: vía + ganador en un tap (prd:k:...)."""
    home = match.get("home_team", "LOC")
    away = match.get("away_team", "VIS")
    n, g = match_number, grp8
    return {
        "inline_keyboard": [
            [
                {"text": f"⏱️ ET → {home}", "callback_data": f"prd:k:{n}:{score}:ET:HOME:{g}"},
                {"text": f"⏱️ ET → {away}", "callback_data": f"prd:k:{n}:{score}:ET:AWAY:{g}"},
            ],
            [
                {"text": f"🥅 Pen → {home}", "callback_data": f"prd:k:{n}:{score}:PEN:HOME:{g}"},
                {"text": f"🥅 Pen → {away}", "callback_data": f"prd:k:{n}:{score}:PEN:AWAY:{g}"},
            ],
        ],
    }

"""Wizard de predicción — resultado obligatorio, opcionales omitibles."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.fixtures.onboarding_players import PLAYERS_BY_TEAM, GLOBAL_TOP_PLAYERS
from src.services.prediction_score_parse import parse_simple_score
from src.services.prediction_telegram_ui import KO_PHASES
from src.services.prediction_wizard_ui import (
    wizard_ko_keyboard,
    wizard_mvp_keyboard,
    wizard_red_keyboard,
    wizard_scorer_goals_keyboard,
    wizard_scorer_keyboard,
)

if TYPE_CHECKING:
    from src.services.prediction_service import PredictionService

STEP_SCORE = "score"
STEP_SCORE_CUSTOM = "score_custom"
STEP_KO = "ko"
STEP_RED = "red"
STEP_SCORER = "scorer"
STEP_SCORER_TEXT = "scorer_text"
STEP_SCORER_GOALS = "scorer_goals"
STEP_MVP = "mvp"
STEP_MVP_TEXT = "mvp_text"

OPTIONAL_STEPS = (STEP_RED, STEP_SCORER, STEP_SCORER_GOALS, STEP_MVP)
TOTAL_STEPS = 5  # score, red, scorer, scorer_goals (sub), mvp


def _g8(group_id: str) -> str:
    return group_id.replace("-", "")[:8]


def _wizard(profile: dict) -> dict | None:
    w = profile.get("prediction_wizard")
    return w if isinstance(w, dict) else None


def _set_wizard(svc: PredictionService, user_id: str, wizard: dict | None) -> None:
    svc._users.update_profile(
        user_id,
        prediction_wizard=wizard,
        prediction_awaiting_score=None,
        prediction_completo_pending=None,
    )


def _clear_wizard(svc: PredictionService, user_id: str) -> None:
    _set_wizard(svc, user_id, None)


def abort_wizard_for_slash_command(svc: PredictionService, user_id: str, text: str) -> bool:
    """Otros comandos (/partidos, etc.) cancelan el wizard sin mensaje."""
    low = (text or "").strip().lower()
    if not low.startswith("/") or low in ("/cancel", "/cancelar"):
        return False
    if not _wizard(svc._users.get_profile(user_id) or {}):
        return False
    _clear_wizard(svc, user_id)
    return True


def _players_for_match(match: dict, profile: dict) -> list[str]:
    home = (match.get("home_team") or "").upper()
    away = (match.get("away_team") or "").upper()
    fav = (profile.get("favorite_team") or "").upper()
    seen: set[str] = set()
    out: list[str] = []
    for code in (home, away, fav):
        if not code:
            continue
        for name in PLAYERS_BY_TEAM.get(code, []):
            if name not in seen:
                seen.add(name)
                out.append(name)
    for name in GLOBAL_TOP_PLAYERS:
        if name not in seen and len(out) < 6:
            seen.add(name)
            out.append(name)
    return out[:6]


def _step_label(step: str) -> tuple[int, str]:
    labels = {
        STEP_SCORE: (1, "Marcador (obligatorio)"),
        STEP_SCORE_CUSTOM: (1, "Marcador (obligatorio)"),
        STEP_KO: (1, "Definición en eliminatoria"),
        STEP_RED: (2, "Tarjeta roja (+2 pts)"),
        STEP_SCORER: (3, "Goleador (+3 pts)"),
        STEP_SCORER_TEXT: (3, "Goleador (+3 pts)"),
        STEP_SCORER_GOALS: (3, "Goles del goleador"),
        STEP_MVP: (4, "MVP del partido (+2 pts)"),
        STEP_MVP_TEXT: (4, "MVP del partido (+2 pts)"),
    }
    return labels.get(step, (1, "Predicción"))


def _header(svc: PredictionService, match: dict, group_id: str, step: str) -> str:
    gname = (svc._groups.get_group(group_id) or {}).get("name", group_id)
    n, title = _step_label(step)
    lines = [
        f"🎯 Predicción · paso {n}/{TOTAL_STEPS}",
        title,
        "",
        svc.format_match_title(match),
        f"Grupo {match.get('group_letter') or '—'}  ·  {svc._format_kickoff(match)}",
        f"👥 {gname}  ·  Veda en {svc._minutes_to_veda(match)}",
    ]
    phase = (match.get("phase") or "GROUP").upper()
    if phase in KO_PHASES and step in (STEP_SCORE, STEP_SCORE_CUSTOM):
        lines.append("")
        lines.append("💡 Si predís empate, elegís ganador en alargue o penales.")
    return "\n".join(lines)


def start_wizard(
    svc: PredictionService,
    user_id: str,
    match_number: int,
    group_id: str,
    *,
    initial_step: str = STEP_SCORE_CUSTOM,
) -> tuple[str, dict | None]:
    match = svc._matches.get_by_match_number(match_number)
    if not match:
        return "Partido no encontrado.", None
    if svc._veda_closed(match):
        return "⛔ La veda para este partido ya está activa.", None
    gid = group_id or svc.get_active_group_id(user_id)
    if not gid:
        return svc.no_group_message()
    profile = svc._users.get_profile(user_id) or {}
    _set_wizard(
        svc,
        user_id,
        {
            "match_number": match_number,
            "group_id": gid,
            "step": initial_step,
            "player_options": _players_for_match(match, profile),
        },
    )
    return render_step(svc, user_id)


def resume_wizard_after_score(
    svc: PredictionService, user_id: str, match_number: int, group_id: str
) -> tuple[str, dict | None]:
    """Continúa opcionales cuando ya hay marcador guardado (/completo)."""
    match = svc._matches.get_by_match_number(match_number)
    if not match:
        return "Partido no encontrado.", None
    p = svc._preds.get_active(user_id, match["match_id"], group_id)
    if not p:
        return start_wizard(svc, user_id, match_number, group_id)
    if svc._veda_closed(match):
        return "Veda activa.", None
    step = STEP_RED
    if p.get("has_red_card") is not None:
        step = STEP_SCORER if not p.get("scorer_name") else STEP_MVP
    if p.get("scorer_name") and p.get("scorer_goals") is None:
        step = STEP_SCORER_GOALS
    if p.get("scorer_name") and p.get("mvp_name") is None:
        step = STEP_MVP
    if p.get("mvp_name"):
        return finish_wizard(svc, user_id, match_number, group_id)
    profile = svc._users.get_profile(user_id) or {}
    _set_wizard(
        svc,
        user_id,
        {
            "match_number": match_number,
            "group_id": group_id,
            "step": step,
            "player_options": _players_for_match(match, profile),
        },
    )
    return render_step(svc, user_id)


def render_step(svc: PredictionService, user_id: str) -> tuple[str, dict | None]:
    profile = svc._users.get_profile(user_id) or {}
    w = _wizard(profile)
    if not w:
        return "No hay predicción en curso. Usá /partidos.", None
    num = int(w.get("match_number", 0))
    gid = w.get("group_id") or svc.get_active_group_id(user_id)
    match = svc._matches.get_by_match_number(num)
    if not match or not gid:
        _clear_wizard(svc, user_id)
        return "Sesión expirada. Volvé a /partidos.", None
    g8 = _g8(gid)
    step = w.get("step", STEP_SCORE)
    header = _header(svc, match, gid, step)

    if step in (STEP_SCORE, STEP_SCORE_CUSTOM):
        home = match.get("home_team", "LOC")
        away = match.get("away_team", "VIS")
        body = (
            f"Escribí el resultado ({home}–{away}), ej: 0-1, 0:1 o 2-1.\n"
            "Después podés terminar o seguir con roja, goleador y MVP.\n"
            "/cancel para salir."
        )
        return header + "\n\n" + body, None

    if step == STEP_KO:
        score = w.get("pending_score", "?-?")
        return (
            header + "\n\nEmpate en eliminatoria: ¿quién avanza y cómo?",
            wizard_ko_keyboard(match, num, score, g8),
        )

    if step == STEP_RED:
        p = svc._preds.get_active(user_id, match["match_id"], gid)
        sc = f"{p['home_goals']}-{p['away_goals']}" if p else "—"
        return (
            header + f"\n\n✅ Marcador guardado: {sc}\n\n¿Habrá tarjeta roja?",
            wizard_red_keyboard(num, g8),
        )

    if step in (STEP_SCORER, STEP_SCORER_TEXT):
        if step == STEP_SCORER_TEXT:
            return (
                header + "\n\n✏️ Escribí el nombre del goleador.\n/cancel para salir.",
                None,
            )
        players = w.get("player_options") or _players_for_match(match, profile)
        return (
            header + "\n\n¿Quién mete el gol decisivo?",
            wizard_scorer_keyboard(players, num, g8),
        )

    if step == STEP_SCORER_GOALS:
        name = w.get("pending_scorer", "el goleador")
        return (
            header + f"\n\n¿Cuántos goles hace {name}?",
            wizard_scorer_goals_keyboard(num, g8),
        )

    if step in (STEP_MVP, STEP_MVP_TEXT):
        if step == STEP_MVP_TEXT:
            return (
                header + "\n\n✏️ Escribí el nombre del MVP.\n/cancel para salir.",
                None,
            )
        players = w.get("player_options") or _players_for_match(match, profile)
        return (
            header + "\n\n¿Quién es el mejor jugador del partido?",
            wizard_mvp_keyboard(players, num, g8),
        )

    return finish_wizard(svc, user_id, num, gid)


def wizard_submit_score(
    svc: PredictionService,
    user_id: str,
    match_number: int,
    group_id: str,
    home_goals: int,
    away_goals: int,
    *,
    playoff_via: str | None = None,
    playoff_winner: str | None = None,
) -> tuple[str, dict | None]:
    match = svc._matches.get_by_match_number(match_number)
    if not match:
        _clear_wizard(svc, user_id)
        return "Partido no encontrado.", None
    profile = svc._users.get_profile(user_id) or {}
    if not _wizard(profile):
        _set_wizard(
            svc,
            user_id,
            {
                "match_number": match_number,
                "group_id": group_id,
                "step": STEP_SCORE_CUSTOM,
                "player_options": _players_for_match(match, profile),
            },
        )
    phase = (match.get("phase") or "GROUP").upper()
    if home_goals == away_goals and phase in KO_PHASES and not playoff_via:
        profile = svc._users.get_profile(user_id) or {}
        w = _wizard(profile) or {
            "match_number": match_number,
            "group_id": group_id,
            "player_options": _players_for_match(match, profile),
        }
        w["step"] = STEP_KO
        w["pending_score"] = f"{home_goals}-{away_goals}"
        _set_wizard(svc, user_id, w)
        return render_step(svc, user_id)

    msg = svc._persist_score(
        user_id,
        match["match_id"],
        group_id,
        home_goals,
        away_goals,
        playoff_via=playoff_via,
        playoff_winner=playoff_winner,
    )
    if "Marcador guardado" not in msg:
        return msg, None
    profile = svc._users.get_profile(user_id) or {}
    w = _wizard(profile) or {}
    w.update(
        match_number=match_number,
        group_id=group_id,
        step=STEP_RED,
        player_options=w.get("player_options") or _players_for_match(match, profile),
    )
    _set_wizard(svc, user_id, w)
    text, kb = render_step(svc, user_id)
    return f"{msg}\n\n{text}", kb


def wizard_begin_custom_score(
    svc: PredictionService, user_id: str, match_number: int, group_id: str
) -> tuple[str, dict | None]:
    profile = svc._users.get_profile(user_id) or {}
    w = _wizard(profile)
    if not w or int(w.get("match_number", 0)) != match_number:
        start_wizard(svc, user_id, match_number, group_id)
        profile = svc._users.get_profile(user_id) or {}
        w = _wizard(profile) or {}
    w["step"] = STEP_SCORE_CUSTOM
    w["group_id"] = group_id
    _set_wizard(svc, user_id, w)
    return render_step(svc, user_id)


def wizard_handle_text(
    svc: PredictionService, user_id: str, text: str
) -> tuple[str, dict | None] | None:
    if (text or "").strip().startswith("/"):
        return None
    profile = svc._users.get_profile(user_id) or {}
    w = _wizard(profile)
    if not w:
        return None
    step = w.get("step")
    if step not in (STEP_SCORE, STEP_SCORE_CUSTOM, STEP_SCORER_TEXT, STEP_MVP_TEXT):
        return None
    num = int(w.get("match_number", 0))
    gid = w.get("group_id") or svc.get_active_group_id(user_id)
    match = svc._matches.get_by_match_number(num)
    if not match or not gid:
        _clear_wizard(svc, user_id)
        return "Sesión expirada.", None

    if step in (STEP_SCORE, STEP_SCORE_CUSTOM):
        parsed = parse_simple_score(text)
        if not parsed:
            return "No entendí el marcador. Usá formato 0-1, 0:1 o 2-1.", None
        return wizard_submit_score(svc, user_id, num, gid, parsed[0], parsed[1])

    name = (text or "").strip()[:80]
    if len(name) < 2:
        return "Escribí al menos 2 caracteres o usá /cancel.", None
    if step == STEP_SCORER_TEXT:
        w["pending_scorer"] = name
        w["step"] = STEP_SCORER_GOALS
        _set_wizard(svc, user_id, w)
        return render_step(svc, user_id)
    if step == STEP_MVP_TEXT:
        svc._preds.update_optional_fields(
            user_id, match["match_id"], gid, mvp_name=name
        )
        return finish_wizard(svc, user_id, num, gid)
    return None


def wizard_advance_skip(svc: PredictionService, user_id: str) -> tuple[str, dict | None]:
    profile = svc._users.get_profile(user_id) or {}
    w = _wizard(profile)
    if not w:
        return "No hay wizard activo.", None
    step = w.get("step")
    next_map = {
        STEP_RED: STEP_SCORER,
        STEP_SCORER: STEP_MVP,
        STEP_SCORER_GOALS: STEP_MVP,
        STEP_MVP: None,
    }
    nxt = next_map.get(step)
    if nxt is None:
        return finish_wizard(
            svc, user_id, int(w["match_number"]), w["group_id"]
        )
    w["step"] = nxt
    _set_wizard(svc, user_id, w)
    return render_step(svc, user_id)


def wizard_set_red(
    svc: PredictionService,
    user_id: str,
    match_number: int,
    group_id: str,
    has_red: bool,
) -> tuple[str, dict | None]:
    match = svc._matches.get_by_match_number(match_number)
    if not match:
        return "Partido no encontrado.", None
    svc._preds.update_optional_fields(
        user_id, match["match_id"], group_id, has_red_card=has_red
    )
    profile = svc._users.get_profile(user_id) or {}
    w = _wizard(profile) or {
        "match_number": match_number,
        "group_id": group_id,
        "player_options": _players_for_match(match, profile),
    }
    w["step"] = STEP_SCORER
    _set_wizard(svc, user_id, w)
    label = "Sí habrá roja" if has_red else "No habrá roja"
    text, kb = render_step(svc, user_id)
    return f"🟥 {label} guardado.\n\n{text}", kb


def wizard_set_scorer(
    svc: PredictionService,
    user_id: str,
    match_number: int,
    group_id: str,
    idx: int,
) -> tuple[str, dict | None]:
    profile = svc._users.get_profile(user_id) or {}
    w = _wizard(profile) or {}
    players = w.get("player_options") or []
    if idx < 0 or idx >= len(players):
        return "Opción inválida.", None
    w["pending_scorer"] = players[idx]
    w["step"] = STEP_SCORER_GOALS
    _set_wizard(svc, user_id, w)
    return render_step(svc, user_id)


def wizard_set_scorer_goals(
    svc: PredictionService,
    user_id: str,
    match_number: int,
    group_id: str,
    goals: int,
) -> tuple[str, dict | None]:
    match = svc._matches.get_by_match_number(match_number)
    if not match:
        return "Partido no encontrado.", None
    profile = svc._users.get_profile(user_id) or {}
    w = _wizard(profile) or {}
    name = w.get("pending_scorer")
    if not name:
        return "Elegí goleador primero.", None
    svc._preds.update_optional_fields(
        user_id,
        match["match_id"],
        group_id,
        scorer_name=name,
        scorer_goals=goals,
    )
    w["step"] = STEP_MVP
    _set_wizard(svc, user_id, w)
    text, kb = render_step(svc, user_id)
    return f"⚽ {name} ({goals} gol{'es' if goals != 1 else ''}) guardado.\n\n{text}", kb


def wizard_set_mvp(
    svc: PredictionService,
    user_id: str,
    match_number: int,
    group_id: str,
    idx: int,
) -> tuple[str, dict | None]:
    profile = svc._users.get_profile(user_id) or {}
    w = _wizard(profile) or {}
    players = w.get("player_options") or []
    if idx < 0 or idx >= len(players):
        return "Opción inválida.", None
    match = svc._matches.get_by_match_number(match_number)
    if not match:
        return "Partido no encontrado.", None
    name = players[idx]
    svc._preds.update_optional_fields(
        user_id, match["match_id"], group_id, mvp_name=name
    )
    return finish_wizard(svc, user_id, match_number, group_id)


def wizard_goto_scorer_text(svc: PredictionService, user_id: str) -> tuple[str, dict | None]:
    profile = svc._users.get_profile(user_id) or {}
    w = _wizard(profile)
    if not w:
        return "No hay wizard activo.", None
    w["step"] = STEP_SCORER_TEXT
    _set_wizard(svc, user_id, w)
    return render_step(svc, user_id)


def wizard_goto_mvp_text(svc: PredictionService, user_id: str) -> tuple[str, dict | None]:
    profile = svc._users.get_profile(user_id) or {}
    w = _wizard(profile)
    if not w:
        return "No hay wizard activo.", None
    w["step"] = STEP_MVP_TEXT
    _set_wizard(svc, user_id, w)
    return render_step(svc, user_id)


def finish_wizard(
    svc: PredictionService, user_id: str, match_number: int, group_id: str
) -> tuple[str, dict | None]:
    match = svc._matches.get_by_match_number(match_number)
    _clear_wizard(svc, user_id)
    if not match:
        return "Listo.", None
    p = svc._preds.get_active(user_id, match["match_id"], group_id)
    if not p:
        return "Predicción guardada.", None
    icons = svc._pred_icons(p)
    extras = []
    if p.get("has_red_card") is True:
        extras.append("🟥 roja sí")
    elif p.get("has_red_card") is False:
        extras.append("🟥 roja no")
    if p.get("scorer_name"):
        sg = p.get("scorer_goals") or 1
        extras.append(f"⚽ {p['scorer_name']} ({sg})")
    if p.get("mvp_name"):
        extras.append(f"⭐ {p['mvp_name']}")
    extra_line = "\n".join(extras) if extras else "Solo marcador (podés completar antes de la veda con /completo)."
    gname = (svc._groups.get_group(group_id) or {}).get("name", group_id)
    return (
        f"✅ Predicción lista\n"
        f"{svc.format_match_title(match)}  →  {p['home_goals']}-{p['away_goals']}{icons}\n"
        f"👥 {gname}\n"
        f"{extra_line}\n\n"
        f"Veda en {svc._minutes_to_veda(match)}.",
        None,
    )


def wizard_cancel(svc: PredictionService, user_id: str) -> tuple[str, dict | None]:
    _clear_wizard(svc, user_id)
    return "Predicción cancelada.", None


def handle_wizard_callback(
    svc: PredictionService, user_id: str, parts: list[str]
) -> tuple[str, dict | None] | None:
    """parts[0]=='prd', parts[1]=='w', ..."""
    if len(parts) < 3 or parts[1] != "w":
        return None
    sub = parts[2]
    gid: str | None = None
    num = 0

    def _resolve_grp8(grp8: str) -> str | None:
        return svc.resolve_group_short(user_id, grp8) or svc.get_active_group_id(user_id)

    if sub == "custom" and len(parts) >= 5:
        num = int(parts[3])
        gid = _resolve_grp8(parts[4])
        if not gid:
            return svc.no_group_message()
        return wizard_begin_custom_score(svc, user_id, num, gid)

    if sub == "ko" and len(parts) >= 8:
        num = int(parts[3])
        score = parts[4]
        via = parts[5]
        side = parts[6]
        grp8 = parts[7]
        gid = _resolve_grp8(grp8)
        if not gid:
            return svc.no_group_message()
        match = svc._matches.get_by_match_number(num)
        if not match:
            return "Partido no encontrado.", None
        winner = match["home_team"] if side == "HOME" else match["away_team"]
        h_s, a_s = score.split("-", 1)
        return wizard_submit_score(
            svc, user_id, num, gid, int(h_s), int(a_s),
            playoff_via=via, playoff_winner=winner,
        )

    if sub == "skip" and len(parts) >= 5:
        num = int(parts[3])
        gid = _resolve_grp8(parts[4])
        if not gid:
            return svc.no_group_message()
        return wizard_advance_skip(svc, user_id)

    if sub == "done" and len(parts) >= 5:
        num = int(parts[3])
        gid = _resolve_grp8(parts[4])
        if not gid:
            return svc.no_group_message()
        return finish_wizard(svc, user_id, num, gid)

    if sub == "red" and len(parts) >= 6:
        has_red = parts[3] == "1"
        num = int(parts[4])
        gid = _resolve_grp8(parts[5])
        if not gid:
            return svc.no_group_message()
        return wizard_set_red(svc, user_id, num, gid, has_red)

    if sub == "sc" and len(parts) >= 6:
        idx = int(parts[3])
        num = int(parts[4])
        gid = _resolve_grp8(parts[5])
        if not gid:
            return svc.no_group_message()
        return wizard_set_scorer(svc, user_id, num, gid, idx)

    if sub == "scother" and len(parts) >= 5:
        return wizard_goto_scorer_text(svc, user_id)

    if sub == "sg" and len(parts) >= 6:
        goals = int(parts[3])
        num = int(parts[4])
        gid = _resolve_grp8(parts[5])
        if not gid:
            return svc.no_group_message()
        return wizard_set_scorer_goals(svc, user_id, num, gid, goals)

    if sub == "mvp" and len(parts) >= 6:
        idx = int(parts[3])
        num = int(parts[4])
        gid = _resolve_grp8(parts[5])
        if not gid:
            return svc.no_group_message()
        return wizard_set_mvp(svc, user_id, num, gid, idx)

    if sub == "mvpother":
        return wizard_goto_mvp_text(svc, user_id)

    return None

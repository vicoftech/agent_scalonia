"""Wizard de predicción — marcador obligatorio + extendidas Sí/No."""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.services.prediction_rules import (
    EXTENDED_STEPS,
    STEP_BY_ID,
    bool_label,
    extended_lines_from_prediction,
    first_extended_step_id,
    max_possible_points,
    next_extended_step_id,
    resume_step_id,
    step_number,
)
from src.services.prediction_score_parse import parse_simple_score
from src.services.prediction_telegram_ui import KO_PHASES
from src.services.prediction_wizard_ui import wizard_ko_keyboard, wizard_yes_no_keyboard

if TYPE_CHECKING:
    from src.services.prediction_service import PredictionService

STEP_SCORE = "score"
STEP_SCORE_CUSTOM = "score_custom"
STEP_KO = "ko"


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
    low = (text or "").strip().lower()
    if not low.startswith("/") or low in ("/cancel", "/cancelar"):
        return False
    if not _wizard(svc._users.get_profile(user_id) or {}):
        return False
    _clear_wizard(svc, user_id)
    return True


def _step_title(step: str) -> str:
    if step in (STEP_SCORE, STEP_SCORE_CUSTOM):
        return "Marcador a los 90 min (obligatorio)"
    if step == STEP_KO:
        return "Playoff — ganador en alargue o penales"
    ext = STEP_BY_ID.get(step)
    if ext:
        return ext.question
    return "Predicción"


def _header(svc: PredictionService, match: dict, group_id: str, step: str) -> str:
    gname = (svc._groups.get_group(group_id) or {}).get("name", group_id)
    n = step_number(step)
    lines = [
        f"🎯 Predicción · paso {n}/7",
        _step_title(step),
        "",
        svc.format_match_title(match),
        f"Grupo {match.get('group_letter') or '—'}  ·  {svc._format_kickoff(match)}",
        f"👥 {gname}  ·  Veda en {svc._minutes_to_veda(match)}",
    ]
    phase = (match.get("phase") or "GROUP").upper()
    if phase in KO_PHASES and step in (STEP_SCORE, STEP_SCORE_CUSTOM):
        lines.append("")
        lines.append("💡 Si predís empate en eliminatoria, elegís ganador en alargue o penales.")
    if step not in (STEP_SCORE, STEP_SCORE_CUSTOM, STEP_KO):
        lines.append("")
        lines.append(f"Cada acierto suma +1 pt · Podés saltar o terminar cuando quieras.")
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
    _set_wizard(
        svc,
        user_id,
        {"match_number": match_number, "group_id": gid, "step": initial_step},
    )
    return render_step(svc, user_id)


def resume_wizard_after_score(
    svc: PredictionService, user_id: str, match_number: int, group_id: str
) -> tuple[str, dict | None]:
    match = svc._matches.get_by_match_number(match_number)
    if not match:
        return "Partido no encontrado.", None
    p = svc._preds.get_active(user_id, match["match_id"], group_id)
    if not p:
        return start_wizard(svc, user_id, match_number, group_id)
    if svc._veda_closed(match):
        return "Veda activa.", None
    step = resume_step_id(p)
    _set_wizard(
        svc,
        user_id,
        {"match_number": match_number, "group_id": group_id, "step": step},
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
    step = w.get("step", STEP_SCORE_CUSTOM)
    header = _header(svc, match, gid, step)

    if step in (STEP_SCORE, STEP_SCORE_CUSTOM):
        home = match.get("home_team", "LOC")
        away = match.get("away_team", "VIS")
        body = (
            f"Escribí el resultado ({home}–{away}), ej: 0-1, 0:1 o 2-1.\n"
            "Luego podés sumar variables extendidas (Sí/No) o terminar.\n"
            "/cancel para salir."
        )
        return header + "\n\n" + body, None

    if step == STEP_KO:
        score = w.get("pending_score", "?-?")
        return (
            header + "\n\n¿Quién avanza si hay empate en 90 minutos?",
            wizard_ko_keyboard(match, num, score, g8),
        )

    ext = STEP_BY_ID.get(step)
    if ext:
        p = svc._preds.get_active(user_id, match["match_id"], gid)
        sc = f"{p['home_goals']}-{p['away_goals']}" if p else "—"
        return (
            header + f"\n\n✅ Marcador: {sc}\n\n{ext.question}",
            wizard_yes_no_keyboard(num, g8, step),
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
    if not _wizard(svc._users.get_profile(user_id) or {}):
        _set_wizard(
            svc,
            user_id,
            {
                "match_number": match_number,
                "group_id": group_id,
                "step": STEP_SCORE_CUSTOM,
            },
        )
    phase = (match.get("phase") or "GROUP").upper()
    if home_goals == away_goals and phase in KO_PHASES and not playoff_via:
        w = _wizard(svc._users.get_profile(user_id) or {}) or {}
        w.update(
            match_number=match_number,
            group_id=group_id,
            step=STEP_KO,
            pending_score=f"{home_goals}-{away_goals}",
        )
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
    w = _wizard(svc._users.get_profile(user_id) or {}) or {}
    w.update(
        match_number=match_number,
        group_id=group_id,
        step=first_extended_step_id(),
    )
    _set_wizard(svc, user_id, w)
    text, kb = render_step(svc, user_id)
    max_pts = max_possible_points(svc._preds.get_active(user_id, match["match_id"], group_id))
    return f"{msg}\nMáx. posible ahora: {max_pts} pts\n\n{text}", kb


def wizard_begin_custom_score(
    svc: PredictionService, user_id: str, match_number: int, group_id: str
) -> tuple[str, dict | None]:
    w = _wizard(svc._users.get_profile(user_id) or {})
    if not w or int(w.get("match_number", 0)) != match_number:
        start_wizard(svc, user_id, match_number, group_id)
        w = _wizard(svc._users.get_profile(user_id) or {}) or {}
    w["step"] = STEP_SCORE_CUSTOM
    w["group_id"] = group_id
    _set_wizard(svc, user_id, w)
    return render_step(svc, user_id)


def wizard_handle_text(
    svc: PredictionService, user_id: str, text: str
) -> tuple[str, dict | None] | None:
    if (text or "").strip().startswith("/"):
        return None
    w = _wizard(svc._users.get_profile(user_id) or {})
    if not w:
        return None
    if w.get("step") not in (STEP_SCORE, STEP_SCORE_CUSTOM):
        return None
    num = int(w.get("match_number", 0))
    gid = w.get("group_id") or svc.get_active_group_id(user_id)
    parsed = parse_simple_score(text)
    if not parsed:
        return "No entendí el marcador. Usá formato 0-1, 0:1 o 2-1.", None
    return wizard_submit_score(svc, user_id, num, gid, parsed[0], parsed[1])


def _advance_to_next_step(svc: PredictionService, user_id: str) -> tuple[str, dict | None]:
    w = _wizard(svc._users.get_profile(user_id) or {})
    if not w:
        return "No hay wizard activo.", None
    cur = w.get("step", "")
    nxt = next_extended_step_id(cur) if cur in STEP_BY_ID else None
    if nxt is None:
        return finish_wizard(svc, user_id, int(w["match_number"]), w["group_id"])
    w["step"] = nxt
    _set_wizard(svc, user_id, w)
    return render_step(svc, user_id)


def wizard_advance_skip(svc: PredictionService, user_id: str) -> tuple[str, dict | None]:
    return _advance_to_next_step(svc, user_id)


def wizard_set_extended(
    svc: PredictionService,
    user_id: str,
    match_number: int,
    group_id: str,
    step_id: str,
    value: bool,
) -> tuple[str, dict | None]:
    ext = STEP_BY_ID.get(step_id)
    if not ext:
        return "Paso inválido.", None
    match = svc._matches.get_by_match_number(match_number)
    if not match:
        return "Partido no encontrado.", None
    svc._preds.update_optional_fields(
        user_id, match["match_id"], group_id, **{ext.db_key: value}
    )
    w = _wizard(svc._users.get_profile(user_id) or {}) or {
        "match_number": match_number,
        "group_id": group_id,
    }
    nxt = next_extended_step_id(step_id)
    if nxt is None:
        return finish_wizard(svc, user_id, match_number, group_id)
    w["step"] = nxt
    _set_wizard(svc, user_id, w)
    text, kb = render_step(svc, user_id)
    return f"✅ {ext.short_label}: {bool_label(value)} guardado.\n\n{text}", kb


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
    gname = (svc._groups.get_group(group_id) or {}).get("name", group_id)
    icons = svc._pred_icons(p)
    extras = extended_lines_from_prediction(p)
    max_pts = max_possible_points(p)
    lines = [
        "✅ Predicción lista",
        f"{svc.format_match_title(match)}  →  {p['home_goals']}-{p['away_goals']}{icons}",
        f"👥 {gname}",
        "",
        "── Resumen ──",
        f"Marcador (90 min): hasta 5 pts según resultado",
    ]
    if p.get("playoff_via"):
        lines.append(
            f"Playoff: {p['playoff_via']} → {p.get('playoff_winner', '?')} "
            f"(+2 pts si acertás vía y ganador)"
        )
    if extras:
        lines.extend(extras)
    else:
        lines.append("Extendida: sin variables extra (solo marcador)")
    lines.append(f"\nMáx. posible: {max_pts} pts · Veda en {svc._minutes_to_veda(match)}")
    lines.append("\n📖 Reglas: /help → sección «Cómo predecir y puntuar»")
    return "\n".join(lines), None


def wizard_cancel(svc: PredictionService, user_id: str) -> tuple[str, dict | None]:
    _clear_wizard(svc, user_id)
    return "Predicción cancelada.", None


def handle_wizard_callback(
    svc: PredictionService, user_id: str, parts: list[str]
) -> tuple[str, dict | None] | None:
    if len(parts) < 3 or parts[1] != "w":
        return None
    sub = parts[2]

    def _resolve_grp8(grp8: str) -> str | None:
        return svc.resolve_group_short(user_id, grp8) or svc.get_active_group_id(user_id)

    if sub == "custom" and len(parts) >= 5:
        gid = _resolve_grp8(parts[4])
        if not gid:
            return svc.no_group_message()
        return wizard_begin_custom_score(svc, user_id, int(parts[3]), gid)

    if sub == "ko" and len(parts) >= 8:
        match = svc._matches.get_by_match_number(int(parts[3]))
        if not match:
            return "Partido no encontrado.", None
        gid = _resolve_grp8(parts[7])
        if not gid:
            return svc.no_group_message()
        winner = match["home_team"] if parts[6] == "HOME" else match["away_team"]
        h_s, a_s = parts[4].split("-", 1)
        return wizard_submit_score(
            svc, user_id, int(parts[3]), gid, int(h_s), int(a_s),
            playoff_via=parts[5], playoff_winner=winner,
        )

    if sub == "skip" and len(parts) >= 5:
        if not _resolve_grp8(parts[4]):
            return svc.no_group_message()
        return wizard_advance_skip(svc, user_id)

    if sub == "done" and len(parts) >= 5:
        gid = _resolve_grp8(parts[4])
        if not gid:
            return svc.no_group_message()
        return finish_wizard(svc, user_id, int(parts[3]), gid)

    if sub == "yn" and len(parts) >= 7:
        step_id = parts[3]
        val = parts[4] == "1"
        num = int(parts[5])
        gid = _resolve_grp8(parts[6])
        if not gid:
            return svc.no_group_message()
        return wizard_set_extended(svc, user_id, num, gid, step_id, val)

    # Compat: prd:w:red:0/1
    if sub == "red" and len(parts) >= 6:
        gid = _resolve_grp8(parts[5])
        if not gid:
            return svc.no_group_message()
        return wizard_set_extended(
            svc, user_id, int(parts[4]), gid, "red", parts[3] == "1"
        )

    return None

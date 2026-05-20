"""Callbacks prd:* — SPEC-2026-021."""
from __future__ import annotations

from src.services.prediction_service import PredictionService
from src.services.prediction_telegram_ui import ko_playoff_keyboard
from src.dao.dynamo.match_dao import MatchDAO


def handle_prediction_callback(user_id: str, data: str) -> tuple[str, dict | None] | None:
    if not data.startswith("prd:"):
        return None
    svc = PredictionService()

    if data == "prd:noop":
        return "Ok, se mantiene tu predicción.", None

    parts = data.split(":")
    if len(parts) < 2:
        return None

    if parts[1] == "o" and len(parts) >= 4:
        try:
            num = int(parts[2])
        except ValueError:
            return "Partido inválido.", None
        gid = svc.resolve_group_short(user_id, parts[3]) or svc.get_active_group_id(user_id)
        if not gid:
            return svc.no_group_message()
        return svc.open_match_picker(user_id, num, gid)

    if parts[1] == "s" and len(parts) >= 5:
        try:
            num = int(parts[2])
        except ValueError:
            return "Partido inválido.", None
        score = parts[3]
        grp8 = parts[4]
        if "-" not in score:
            return "Marcador inválido.", None
        h_s, a_s = score.split("-", 1)
        hg, ag = int(h_s), int(a_s)
        match = MatchDAO().get_by_match_number(num)
        if not match:
            return "Partido no encontrado.", None
        gid = svc.resolve_group_short(user_id, grp8) or svc.get_active_group_id(user_id)
        if not gid:
            return svc.no_group_message()
        phase = (match.get("phase") or "GROUP").upper()
        if hg == ag and phase in {
            "R16", "ROUND_OF_32", "ROUND_OF_16", "QF", "QUARTER_FINAL",
            "SF", "SEMI_FINAL", "FINAL", "THIRD_PLACE",
        }:
            return (
                "Predijiste empate en fase eliminatoria.\n\n¿Cómo se define y quién avanza?",
                ko_playoff_keyboard(match, num, score, grp8),
            )
        return svc.save_score(user_id, match["match_id"], gid, hg, ag)

    if parts[1] == "k" and len(parts) >= 7:
        num = int(parts[2])
        score = parts[3]
        via = parts[4]
        side = parts[5]
        grp8 = parts[6]
        match = MatchDAO().get_by_match_number(num)
        if not match:
            return "Partido no encontrado.", None
        winner = match["home_team"] if side == "HOME" else match["away_team"]
        gid = svc.resolve_group_short(user_id, grp8) or svc.get_active_group_id(user_id)
        if not gid:
            return svc.no_group_message()
        h_s, a_s = score.split("-", 1)
        return svc.save_score(
            user_id,
            match["match_id"],
            gid,
            int(h_s),
            int(a_s),
            playoff_via=via,
            playoff_winner=winner,
        )

    if parts[1] == "cg":
        return svc.group_picker_keyboard(user_id)

    if parts[1] == "sg" and len(parts) >= 3:
        gid = svc.resolve_group_short(user_id, parts[2])
        if not gid:
            return "Grupo no encontrado.", None
        name = svc.set_active_group(user_id, gid)
        return f'👥 Grupo activo: "{name}".\nUsá /partidos para ver el fixture.', None

    if parts[1] == "c" and len(parts) >= 4:
        return svc.format_completo_menu(user_id)

    if parts[1] == "rd" and len(parts) >= 5:
        num = int(parts[2])
        has_red = parts[3] == "1"
        grp8 = parts[4]
        gid = svc.resolve_group_short(user_id, grp8) or svc.get_active_group_id(user_id)
        if not gid:
            return svc.no_group_message()
        return svc.apply_completo_red_card(user_id, num, gid, has_red), None

    if parts[1] == "done":
        return "🎯 Predicción base lista. Más variables opcionales próximamente.", None

    if parts[1] == "x" and len(parts) >= 4:
        return (
            "Escribí con /predecir, por ejemplo:\n/predecir ARG 2-0 ALG",
            None,
        )

    return None

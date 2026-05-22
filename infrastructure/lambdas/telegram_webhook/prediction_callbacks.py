"""Callbacks prd:* — SPEC-2026-021 + wizard unificado."""
from __future__ import annotations

from src.dao.dynamo.match_dao import MatchDAO
from src.services.prediction_service import PredictionService
from src.services import prediction_wizard as pw


def handle_prediction_callback(user_id: str, data: str) -> tuple[str, dict | None] | None:
    if not data.startswith("prd:"):
        return None
    svc = PredictionService()

    if data == "prd:noop":
        return "Ok, se mantiene tu predicción.", None

    parts = data.split(":")
    if len(parts) < 2:
        return None

    if parts[1] == "w":
        result = pw.handle_wizard_callback(svc, user_id, parts)
        if result is not None:
            return result

    if parts[1] == "ch" and len(parts) >= 4:
        try:
            num = int(parts[2])
        except ValueError:
            return "Partido inválido.", None
        gid = svc.resolve_group_short(user_id, parts[3]) or svc.get_active_group_id(user_id)
        if not gid:
            return svc.no_group_message()
        return svc.start_prediction_wizard(user_id, num, gid)

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
        gid = svc.resolve_group_short(user_id, grp8) or svc.get_active_group_id(user_id)
        if not gid:
            return svc.no_group_message()
        return pw.wizard_submit_score(svc, user_id, num, gid, hg, ag)

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
        return pw.wizard_submit_score(
            svc, user_id, num, gid, int(h_s), int(a_s),
            playoff_via=via, playoff_winner=winner,
        )

    if parts[1] == "pg" and len(parts) >= 4:
        try:
            page = int(parts[2])
        except ValueError:
            page = 0
        gid = svc.resolve_group_short(user_id, parts[3]) or svc.get_active_group_id(user_id)
        if not gid:
            return svc.no_group_message()
        return svc.list_partidos_view(user_id, page=page)

    if parts[1] == "cg":
        return svc.group_picker_keyboard(user_id)

    if parts[1] == "sg" and len(parts) >= 3:
        gid = svc.resolve_group_short(user_id, parts[2])
        if not gid:
            return "Grupo no encontrado.", None
        name = svc.set_active_group(user_id, gid)
        return f'👥 Grupo activo: "{name}".\nUsá /partidos para ver el fixture.', None

    if parts[1] == "c" and len(parts) >= 4:
        try:
            num = int(parts[2])
        except ValueError:
            return "Partido inválido.", None
        gid = svc.resolve_group_short(user_id, parts[3]) or svc.get_active_group_id(user_id)
        if not gid:
            return svc.no_group_message()
        return svc.format_completo_menu(user_id, match_number=num, group_id=gid)

    if parts[1] == "full" and len(parts) >= 4:
        try:
            num = int(parts[2])
        except ValueError:
            return "Partido inválido.", None
        gid = svc.resolve_group_short(user_id, parts[3]) or svc.get_active_group_id(user_id)
        if not gid:
            return svc.no_group_message()
        return svc.start_completo_wizard(user_id, num, gid)

    if parts[1] == "fw" and len(parts) >= 5:
        sub = parts[2]
        try:
            if sub == "rd" and len(parts) >= 6:
                has_red = parts[3] == "1"
                num = int(parts[4])
                grp8 = parts[5]
                gid = svc.resolve_group_short(user_id, grp8) or svc.get_active_group_id(user_id)
                if not gid:
                    return svc.no_group_message()
                return pw.wizard_set_extended(
                    svc, user_id, num, gid, "red", has_red
                )
            if sub in ("skip", "done") and len(parts) >= 5:
                num = int(parts[3])
                grp8 = parts[4]
                gid = svc.resolve_group_short(user_id, grp8) or svc.get_active_group_id(user_id)
                if not gid:
                    return svc.no_group_message()
                if sub == "done":
                    return pw.finish_wizard(svc, user_id, num, gid)
                return pw.wizard_advance_skip(svc, user_id)
        except (IndexError, ValueError):
            return "Datos inválidos.", None

    if parts[1] == "rd" and len(parts) >= 5:
        num = int(parts[2])
        has_red = parts[3] == "1"
        grp8 = parts[4]
        gid = svc.resolve_group_short(user_id, grp8) or svc.get_active_group_id(user_id)
        if not gid:
            return svc.no_group_message()
        return pw.wizard_set_extended(svc, user_id, num, gid, "red", has_red)

    if parts[1] == "done" and len(parts) >= 4:
        num = int(parts[2])
        grp8 = parts[3]
        gid = svc.resolve_group_short(user_id, grp8) or svc.get_active_group_id(user_id)
        if not gid:
            return svc.no_group_message()
        return pw.finish_wizard(svc, user_id, num, gid)

    if parts[1] == "x" and len(parts) >= 4:
        try:
            num = int(parts[2])
        except ValueError:
            return "Partido inválido.", None
        grp8 = parts[3]
        gid = svc.resolve_group_short(user_id, grp8) or svc.get_active_group_id(user_id)
        if not gid:
            return svc.no_group_message()
        return svc.begin_custom_score(user_id, num, gid)

    return None

"""Comando /perfil y callbacks prf: — SPEC-2026-048."""
from __future__ import annotations

import re

from src.dao.dynamo.user_dao import UserDAO
from src.services.onboarding_service import (
    MOMENT_M3,
    STAGE_M3_COMPLETE,
    OnboardingService,
)
from src.services.profile_telegram_ui import (
    goal_keyboard,
    m4_cta_keyboard,
    player_picker_keyboard,
    profile_hub_keyboard,
    profile_lang_keyboard,
    profile_team_keyboard,
    team_picker_keyboard,
    trivia_level_keyboard,
    wizard_menu_keyboard,
    wizard_step_title,
)
from src.services.tournament_prediction_service import (
    TournamentPredictionService,
    WIZARD_FIELDS,
)

_PERFIL = re.compile(r"^/perfil(?:@[\w_]+)?\s*$", re.IGNORECASE)

_LANG_LABELS = {"es": "Español", "pt": "Português", "en": "English", "fr": "Français"}
_GOAL_LABELS = {
    "competitive": "Ganar el prode",
    "social": "Divertirme con amigos",
    "educational": "Aprender sobre fútbol",
}
_TRIVIA_LABELS = {"easy": "Casual", "medium": "Fanático", "hard": "Enciclopedia"}


def matches_perfil_command(text: str) -> bool:
    return bool(_PERFIL.match((text or "").strip()))


def _format_hub_message(user_id: str) -> str:
    profile = UserDAO().get_profile(user_id) or {}
    tps = TournamentPredictionService()
    tps.lock_if_needed(user_id)
    alias = profile.get("alias") or "Jugador"
    team = profile.get("favorite_team")
    team_txt = tps.format_team_value(team) if team else "Sin favorita"
    lang = _LANG_LABELS.get(profile.get("preferred_language", ""), profile.get("preferred_language") or "—")
    player = profile.get("favorite_player") or "—"
    trivia = _TRIVIA_LABELS.get(profile.get("football_knowledge", ""), profile.get("football_knowledge") or "—")
    goal = _GOAL_LABELS.get(profile.get("prode_goal", ""), profile.get("prode_goal") or "—")
    filled, total = tps.count_filled(user_id)
    torneo_line = f"🏆 Predicciones torneo: {filled}/{total}"
    if not tps.is_editable():
        torneo_line += " · veda cerrada"
    elif filled < total:
        torneo_line += " · editable hasta #72"
    else:
        torneo_line += " · completas"

    tournament_pts = int(profile.get("tournament_points") or 0)
    bonus_line = ""
    if tournament_pts:
        bonus_line = f"\n🏆 Bonus torneo: {tournament_pts} pts"
    elif not tps.is_editable() and filled:
        bonus_line = "\n📊 Puntos torneo: pendiente (post final #104)"

    return (
        "👤 Tu perfil\n\n"
        f"⚽ Alias: {alias}  (solo lectura)\n"
        f"🇦🇷 Hincha: {team_txt}\n"
        f"🌐 Idioma: {lang}\n"
        f"⭐ Jugador favorito: {player}\n"
        f"🧠 Trivia: {trivia}\n"
        f"🎯 Objetivo: {goal}\n"
        f"{torneo_line}"
        f"{bonus_line}\n\n"
        "El alias no se modifica desde acá."
    )


def show_profile_hub(user_id: str) -> tuple[str, dict]:
    profile = UserDAO().get_profile(user_id) or {}
    text = _format_hub_message(user_id)
    markup = profile_hub_keyboard(editable_torneo=TournamentPredictionService().is_editable())

    if (
        profile.get("onboarding_stage") == STAGE_M3_COMPLETE
        and not profile.get("onboarding_m4_done")
        and not profile.get("tournament_predictions_status")
    ):
        text = (
            "🏆 Predicciones del torneo\n"
            "Campeón, goleador, revelación y más — hasta 190 pts extra "
            "en todos tus grupos.\n\n"
            + text
        )
        return text, m4_cta_keyboard()

    return text, markup


def handle_perfil_command(user_id: str, text: str) -> tuple[str, dict | None] | None:
    if matches_perfil_command(text):
        return show_profile_hub(user_id)
    return None


def _wizard_team_step(user_id: str, step: int, page: int = 0) -> tuple[str, dict]:
    svc = TournamentPredictionService()
    draft = svc.get_wizard_draft(user_id)
    exclude: set[str] = set()
    if step == 2 and draft.get("champion_team"):
        exclude.add(draft["champion_team"])
    if step == 7:
        if draft.get("champion_team"):
            exclude.add(draft["champion_team"])
        if draft.get("finalist_team"):
            exclude.add(draft["finalist_team"])
    codes, total_pages = svc.team_picker_page(page=page, exclude=exclude)
    title = wizard_step_title(step)
    return (
        f"🏆 {title}\n\nElegí una selección:",
        team_picker_keyboard(step=step, codes=codes, page=page, total_pages=total_pages),
    )


def _wizard_player_step(user_id: str, step: int) -> tuple[str, dict]:
    svc = TournamentPredictionService()
    players = svc.suggest_players_for_user(user_id)
    title = wizard_step_title(step)
    return (
        f"🏆 {title}\n\nElegí un jugador o escribí otro:",
        player_picker_keyboard(step=step, players=players),
    )


def handle_profile_callback(user_id: str, data: str) -> tuple[str, dict | None] | None:
    if not data.startswith("prf:"):
        return None

    users = UserDAO()
    tps = TournamentPredictionService()
    onb = OnboardingService()

    if data == "prf:home":
        return show_profile_hub(user_id)

    if data == "prf:skip":
        users.update_profile(user_id, onboarding_m4_done=True)
        return "Listo. Podés completar tus predicciones del torneo cuando quieras desde 👤 Perfil.", profile_hub_keyboard(
            editable_torneo=tps.is_editable()
        )

    if data == "prf:m4:later":
        return "Ok. Cuando quieras: 👤 Perfil → 🏆 Predicciones del torneo.", profile_hub_keyboard(
            editable_torneo=tps.is_editable()
        )

    if data == "prf:m4:start":
        users.update_profile(user_id, onboarding_m4_done=True)
        return _show_wizard_menu(user_id)

    if data == "prf:edit:torneo":
        tps.lock_if_needed(user_id)
        if not tps.is_editable() and not tps.get_predictions(user_id):
            return (
                "⛔ Las predicciones del torneo ya están cerradas y no tenés ninguna guardada.",
                profile_hub_keyboard(editable_torneo=False),
            )
        if not tps.is_editable():
            return tps.format_predictions_summary(user_id), profile_hub_keyboard(editable_torneo=False)
        return _show_wizard_menu(user_id)

    if data == "prf:confirm":
        ok, msg = tps.confirm_predictions(user_id)
        if not ok:
            return msg, wizard_menu_keyboard(editable=tps.is_editable())
        return msg + "\n\n" + tps.format_predictions_summary(user_id), profile_hub_keyboard(
            editable_torneo=tps.is_editable()
        )

    if data == "prf:edit:team":
        return "¿De qué selección sos hincha?", profile_team_keyboard()

    if data == "prf:edit:lang":
        return "¿En qué idioma preferís que te responda?", profile_lang_keyboard()

    if data == "prf:edit:player":
        users.update_profile(user_id, profile_wizard_step="awaiting_favorite_player")
        return "Escribí tu jugador favorito (2–80 caracteres) o /listo para borrarlo:", None

    if data == "prf:edit:trivia":
        return "¿Qué tan difícil querés la trivia?", trivia_level_keyboard()

    if data == "prf:edit:goal":
        return "¿Qué te importa más del prode?", goal_keyboard()

    parts = data.split(":")
    if len(parts) < 3:
        return "Acción no reconocida.", profile_hub_keyboard(editable_torneo=tps.is_editable())

    action = parts[1]

    if action == "w" and len(parts) >= 3:
        step = int(parts[2])
        if step in (1, 2, 7):
            return _wizard_team_step(user_id, step)
        if step in (3, 4, 5, 6):
            return _wizard_player_step(user_id, step)
        return "Paso inválido.", wizard_menu_keyboard(editable=tps.is_editable())

    if action == "tm" and len(parts) >= 4:
        step = int(parts[2])
        page = int(parts[3])
        return _wizard_team_step(user_id, step, page)

    if action == "pick" and len(parts) >= 4:
        step = int(parts[2])
        code = parts[3]
        field = WIZARD_FIELDS[step - 1]
        try:
            tps.set_draft_field(user_id, field, code)
        except ValueError as exc:
            return str(exc), wizard_menu_keyboard(editable=tps.is_editable())
        return _show_wizard_menu(user_id)

    if action == "pl" and len(parts) >= 4:
        step = int(parts[2])
        value = ":".join(parts[3:])
        if value == "__other__":
            users.update_profile(user_id, profile_wizard_step=f"awaiting_torneo_player:{step}")
            return f"Escribí el nombre para «{wizard_step_title(step)}»:", None
        field = WIZARD_FIELDS[step - 1]
        try:
            tps.set_draft_field(user_id, field, value)
        except ValueError as exc:
            return str(exc), player_picker_keyboard(
                step=step, players=tps.suggest_players_for_user(user_id)
            )
        return _show_wizard_menu(user_id)

    if action == "team" and len(parts) >= 3:
        code = None if parts[2] == "none" else parts[2]
        onb.save_m1_team(user_id, code)
        return "✅ Hincha actualizado.\n\n" + _format_hub_message(user_id), profile_hub_keyboard(
            editable_torneo=tps.is_editable()
        )

    if action == "lang" and len(parts) >= 3:
        users.update_profile(user_id, preferred_language=parts[2][:2])
        return "✅ Idioma actualizado.\n\n" + _format_hub_message(user_id), profile_hub_keyboard(
            editable_torneo=tps.is_editable()
        )

    if action == "goal" and len(parts) >= 3:
        onb.complete_moment(user_id, MOMENT_M3, {"prode_goal": parts[2]})
        return "✅ Objetivo actualizado.\n\n" + _format_hub_message(user_id), profile_hub_keyboard(
            editable_torneo=tps.is_editable()
        )

    if action == "trivia" and len(parts) >= 3:
        users.update_profile(user_id, football_knowledge=parts[2])
        return "✅ Nivel de trivia actualizado.\n\n" + _format_hub_message(user_id), profile_hub_keyboard(
            editable_torneo=tps.is_editable()
        )

    return "Acción no reconocida.", profile_hub_keyboard(editable_torneo=tps.is_editable())


def _show_wizard_menu(user_id: str) -> tuple[str, dict]:
    tps = TournamentPredictionService()
    summary = tps.format_predictions_summary(user_id)
    return summary, wizard_menu_keyboard(editable=tps.is_editable())


def handle_profile_pending(user_id: str, profile: dict, text: str) -> tuple[str, dict | None] | None:
    step = profile.get("profile_wizard_step")
    if not step:
        return None
    stripped = (text or "").strip()
    if stripped.lower() in ("/listo", "listo", "/cancel", "cancel"):
        UserDAO().update_profile(user_id, profile_wizard_step=None)
        return show_profile_hub(user_id)

    users = UserDAO()
    tps = TournamentPredictionService()

    if step == "awaiting_favorite_player":
        if len(stripped) < 2:
            return "Nombre muy corto. Probá de nuevo:", None
        users.update_profile(
            user_id, favorite_player=stripped[:80], profile_wizard_step=None
        )
        return (
            "✅ Jugador favorito actualizado.\n\n" + _format_hub_message(user_id),
            profile_hub_keyboard(editable_torneo=tps.is_editable()),
        )

    if step.startswith("awaiting_torneo_player:"):
        wizard_step = int(step.split(":")[1])
        field = WIZARD_FIELDS[wizard_step - 1]
        try:
            tps.set_draft_field(user_id, field, stripped)
        except ValueError as exc:
            return str(exc), None
        users.update_profile(user_id, profile_wizard_step=None)
        return _show_wizard_menu(user_id)

    return None

"""Flujo M1 onboarding en Telegram (SPEC-019) — antes del agente."""
from __future__ import annotations

import logging

from src.services.onboarding_service import (
    M1_STEP_ALIAS,
    M1_STEP_LANG,
    M1_STEP_TEAM,
    STAGE_M1_PENDING,
    OnboardingService,
)

from src.services.onboarding_telegram_ui import language_keyboard, team_keyboard

logger = logging.getLogger(__name__)

_QUESTION_HINTS = (
    "?",
    "cuando",
    "cuándo",
    "partido",
    "fixture",
    "horario",
    "juega",
    "mundial",
    "argentina",
    "grupo",
)


def _looks_like_question(text: str) -> bool:
    low = text.lower()
    return any(h in low for h in _QUESTION_HINTS)


def m1_welcome_message(group_name: str | None = None) -> str:
    extra = f"\nTe uniste al grupo {group_name}." if group_name else ""
    return (
        "¡Bienvenido al Prode Mundial 2026! ⚽🌎\n"
        "Predecí partidos, acumulá puntos, competí con amigos."
        f"{extra}\n\n"
        "Para empezar: ¿cómo querés que te llame en el ranking?\n"
        "(Escribí tu alias o /listo para saltear)"
    )


def handle_onboarding_message(
    user_id: str,
    profile: dict,
    text: str,
) -> tuple[str | None, dict | None]:
    """
    Procesa mensajes M1_PENDING. Retorna (texto, reply_markup) o (None, None) si va al agente.
    """
    if profile.get("onboarding_stage") != STAGE_M1_PENDING:
        return None, None

    svc = OnboardingService()
    step = profile.get("m1_step") or M1_STEP_ALIAS
    stripped = (text or "").strip()

    if stripped.lower() in ("/listo", "listo"):
        result = svc.skip_current_moment(user_id)
        step = result.get("m1_step") or profile.get("m1_step")
        if step == M1_STEP_TEAM:
            return _team_prompt(), team_keyboard()
        if step == M1_STEP_LANG:
            return _lang_prompt(profile), language_keyboard()
        if result.get("card"):
            return result["card"], None
        return "Listo, seguimos.", None

    if step == M1_STEP_ALIAS:
        if stripped.startswith("/"):
            return None, None
        if _looks_like_question(stripped):
            return None, None
        saved = svc.save_m1_alias(user_id, stripped)
        if not saved.get("ok"):
            if saved.get("alias_taken"):
                alts = saved.get("alternatives", [])
                btns = [[{"text": a, "callback_data": f"onb:alias:{a}"}] for a in alts[:3]]
                btns.append([{"text": "Quiero otro", "callback_data": "onb:alias:retry"}])
                return (
                    "Ese alias ya está tomado 😅 ¿Alguna de estas?\n"
                    + " | ".join(alts),
                    {"inline_keyboard": btns},
                )
            return saved.get("error", "Alias inválido."), None
        if saved.get("used_temp"):
            return (
                f"Te asigné el alias temporal {saved['alias']}.\n\n" + _team_prompt(),
                team_keyboard(),
            )
        return f"Perfecto, {saved['alias']} 🙌\n\n" + _team_prompt(), team_keyboard()

    if step == M1_STEP_TEAM:
        return "Elegí tu selección con los botones de abajo 👇", team_keyboard()

    if step == M1_STEP_LANG:
        return _lang_prompt(profile), language_keyboard()

    return None, None


def handle_onboarding_callback(user_id: str, profile: dict, data: str) -> tuple[str, dict | None]:
    svc = OnboardingService()
    parts = data.split(":")
    if len(parts) < 3 or parts[0] != "onb":
        return "Acción no reconocida.", None

    kind = parts[1]
    value = parts[2]

    if kind == "alias" and value != "retry":
        saved = svc.save_m1_alias(user_id, value)
        if saved.get("ok"):
            return f"Perfecto, {value} 🙌\n\n" + _team_prompt(), team_keyboard()
        return "No pude usar ese alias. Escribí otro.", None

    if kind == "team":
        code = None if value == "none" else value
        svc.save_m1_team(user_id, code)
        return _lang_prompt(profile), language_keyboard()

    if kind == "lang":
        result = svc.save_m1_language(user_id, value)
        card = result.get("card") or svc.format_profile_card(user_id)
        return card + "\n\n[⚽ Podés preguntarme por partidos, trivia o invitaciones.]", None

    return "Listo.", None


def _team_prompt() -> str:
    return "¿De qué selección sos hincha? (un tap en el equipo)"


def _lang_prompt(profile: dict) -> str:
    alias = profile.get("alias", "Jugador")
    return f"Perfecto {alias} 🙌\n¿En qué idioma preferís que te responda?"

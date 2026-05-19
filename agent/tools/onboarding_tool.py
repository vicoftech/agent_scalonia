"""agent/tools/onboarding_tool.py — SPEC-2026-019 onboarding progresivo."""
from __future__ import annotations

import json
import logging
from typing import Callable

from strands import tool

logger = logging.getLogger(__name__)


def _execute_onboarding_tool(
    caller_user_id: str,
    action: str,
    *,
    alias: str | None = None,
    favorite_team: str | None = None,
    preferred_language: str | None = None,
    favorite_player: str | None = None,
    football_knowledge: str | None = None,
    prode_goal: str | None = None,
    event: str | None = None,
    moment: str | None = None,
    skip: bool = False,
) -> str:
    from src.services.onboarding_service import (
        EVENT_FIRST_PREDICTION,
        EVENT_FIRST_RANKING,
        EVENT_FIRST_TRIVIA,
        MOMENT_M2_PLAYER,
        MOMENT_M2_TRIVIA,
        MOMENT_M3,
        OnboardingService,
    )

    if not caller_user_id or caller_user_id in ("anonymous", "unregistered"):
        from src.services.auth_service import INACTIVE_USER_MESSAGE

        return INACTIVE_USER_MESSAGE

    svc = OnboardingService()
    action = (action or "").strip().lower()

    if action == "pending":
        ev = event or EVENT_FIRST_PREDICTION
        prompt = svc.get_pending_prompt(caller_user_id, ev)
        if prompt:
            return prompt
        trig = svc.should_trigger(caller_user_id, ev) if event else None
        return json.dumps(trig or {"moment": None}, ensure_ascii=False)

    if action == "skip" or skip:
        result = svc.skip_current_moment(caller_user_id)
        return json.dumps(result, ensure_ascii=False)

    if action == "validate_alias" and alias:
        ok, msg = svc.validate_alias(alias)
        if ok:
            return "ok"
        if msg == "alias_taken":
            alts = svc.suggest_alias_alternatives(alias)
            return f"Alias ocupado. Sugerencias: {', '.join(alts)}"
        return msg

    if action == "save_alias" and alias:
        return json.dumps(svc.save_m1_alias(caller_user_id, alias), ensure_ascii=False)

    if action == "save_team":
        return json.dumps(svc.save_m1_team(caller_user_id, favorite_team), ensure_ascii=False)

    if action == "save_language" and preferred_language:
        return json.dumps(svc.save_m1_language(caller_user_id, preferred_language), ensure_ascii=False)

    if action == "save_player":
        data = {"favorite_player": favorite_player} if favorite_player else {"skipped": True}
        return json.dumps(svc.complete_moment(caller_user_id, MOMENT_M2_PLAYER, data), ensure_ascii=False)

    if action == "save_trivia_level" and football_knowledge:
        return json.dumps(
            svc.complete_moment(
                caller_user_id,
                MOMENT_M2_TRIVIA,
                {"football_knowledge": football_knowledge},
            ),
            ensure_ascii=False,
        )

    if action == "save_goal" and prode_goal:
        return json.dumps(
            svc.complete_moment(caller_user_id, MOMENT_M3, {"prode_goal": prode_goal}),
            ensure_ascii=False,
        )

    if action == "record_event" and event:
        pending = svc.should_trigger(caller_user_id, event)
        prompt = svc.get_pending_prompt(caller_user_id, event)
        return json.dumps(
            {"pending": pending, "prompt": prompt},
            ensure_ascii=False,
        )

    if action == "complete" and moment:
        data = {}
        if alias:
            data["alias"] = alias
        if favorite_team is not None:
            data["favorite_team"] = favorite_team
        if preferred_language:
            data["preferred_language"] = preferred_language
        if favorite_player:
            data["favorite_player"] = favorite_player
        if football_knowledge:
            data["football_knowledge"] = football_knowledge
        if prode_goal:
            data["prode_goal"] = prode_goal
        return json.dumps(svc.complete_moment(caller_user_id, moment, data), ensure_ascii=False)

    if action == "profile_card":
        return svc.format_profile_card(caller_user_id, complete=True)

    return (
        "Acciones: pending, skip, validate_alias, save_player, save_trivia_level, "
        "save_goal, record_event (FIRST_PREDICTION|FIRST_TRIVIA|FIRST_RANKING), profile_card."
    )


def make_onboarding_tool(caller_user_id: str) -> Callable:
    @tool
    def onboarding_tool(
        action: str,
        alias: str | None = None,
        favorite_team: str | None = None,
        preferred_language: str | None = None,
        favorite_player: str | None = None,
        football_knowledge: str | None = None,
        prode_goal: str | None = None,
        event: str | None = None,
        moment: str | None = None,
        skip: bool = False,
    ) -> str:
        """
        Onboarding progresivo (M2/M3 en el agente; M1 lo hace Telegram).

        action:
          pending — texto de la pregunta pendiente (event=FIRST_PREDICTION|FIRST_TRIVIA|FIRST_RANKING)
          skip — /listo equivalente
          save_player, save_trivia_level, save_goal — persistir respuesta M2/M3
          record_event — consultar si hay momento pendiente tras predicción/trivia/ranking
          validate_alias — comprobar alias (M1 en Telegram)
          profile_card — tarjeta de perfil
        """
        return _execute_onboarding_tool(
            caller_user_id,
            action,
            alias=alias,
            favorite_team=favorite_team,
            preferred_language=preferred_language,
            favorite_player=favorite_player,
            football_knowledge=football_knowledge,
            prode_goal=prode_goal,
            event=event,
            moment=moment,
            skip=skip,
        )

    return onboarding_tool

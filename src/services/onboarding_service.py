"""Onboarding progresivo SPEC-2026-019 / ISSUE-025."""
from __future__ import annotations

import random
import re
import string
from datetime import datetime, timezone
from typing import Any

from src.dao.dynamo.user_dao import UserDAO
from src.fixtures.onboarding_players import suggest_players

STAGE_M1_PENDING = "M1_PENDING"
STAGE_M1_COMPLETE = "M1_COMPLETE"
STAGE_M2_COMPLETE = "M2_COMPLETE"
STAGE_M3_COMPLETE = "M3_COMPLETE"

M1_STEP_ALIAS = "awaiting_alias"
M1_STEP_TEAM = "awaiting_team"
M1_STEP_LANG = "awaiting_lang"

EVENT_FIRST_PREDICTION = "FIRST_PREDICTION"
EVENT_FIRST_TRIVIA = "FIRST_TRIVIA"
EVENT_FIRST_RANKING = "FIRST_RANKING"

MOMENT_M1 = "M1"
MOMENT_M2_PLAYER = "M2_PLAYER"
MOMENT_M2_TRIVIA = "M2_TRIVIA"
MOMENT_M3 = "M3"

_ALIAS_RE = re.compile(r"^[a-zA-Z0-9_-]{2,30}$")

FIRST_POST_START_INSTRUCTION = (
    "[Instrucción: usuario recién registrado vía invitación; el bot ya le envió "
    "bienvenida fija por /start. NO repitas bienvenida ni te presentes como ProdeBot; "
    "respondé directamente su mensaje con kb_retrieval_tool, web_search_tool o match_tool "
    "según corresponda. Si onboarding_stage=M1_PENDING, el flujo M1 lo maneja Telegram; "
    "no pidas alias salvo que el usuario pregunte por /perfil.]"
)

ONBOARDING_SECTION = """
## Onboarding progresivo (SPEC-019)

M1 (alias, selección, idioma) lo completa Telegram con botones; no repitas ese flujo.
Si onboarding_stage=M1_PENDING: no pidas alias ni equipo.

Tras M1_COMPLETE, en la primera predicción exitosa (prediction_tool): completá la predicción
PRIMERO y luego UNA pregunta por el jugador favorito (onboarding_tool action=pending o save).
Sugerí jugadores del favorite_team del perfil si existe.

Primera trivia: ANTES de la pregunta, pedí nivel (casual/fanático/enciclopedia) si falta
football_knowledge — onboarding_tool.

Primera consulta de ranking: mostrá el ranking y luego UNA pregunta por el objetivo del prode.

Reglas: /listo siempre aceptado; nunca insistir; máximo 1 pregunta de onboarding por turno;
la acción del usuario (predecir, trivia, ranking) siempre PRIMERO.
""".strip()

_LANG_LABELS = {
    "es": "Español",
    "pt": "Português",
    "en": "English",
    "fr": "Français",
}

_KNOWLEDGE_MAP = {
    "casual": "easy",
    "fanatic": "medium",
    "fanático": "medium",
    "encyclopedia": "hard",
    "enciclopedia": "hard",
    "easy": "easy",
    "medium": "medium",
    "hard": "hard",
}

_GOAL_MAP = {
    "win": "competitive",
    "social": "social",
    "learn": "educational",
    "competitive": "competitive",
    "educational": "educational",
}


class OnboardingService:
    def __init__(self, user_dao: UserDAO | None = None):
        self._users = user_dao or UserDAO()

    def validate_alias(self, alias: str) -> tuple[bool, str]:
        raw = (alias or "").strip()
        if len(raw) < 2 or len(raw) > 30:
            return False, "El alias debe tener entre 2 y 30 caracteres."
        if not _ALIAS_RE.match(raw):
            return False, "Solo letras, números, guiones y underscores."
        return True, ""

    def validate_alias_for_user(self, user_id: str, alias: str) -> tuple[bool, str]:
        ok, reason = self.validate_alias(alias)
        if not ok:
            return ok, reason
        if self._users.alias_taken(alias, exclude_user_id=user_id):
            return False, "alias_taken"
        return True, ""

    def suggest_alias_alternatives(self, alias: str) -> list[str]:
        base = re.sub(r"[^a-zA-Z0-9_-]", "", (alias or "Jugador")[:24]) or "Jugador"
        suffix = random.randint(10, 99)
        return [f"{base}1", f"{base}2", f"{base}{suffix}"]

    def generate_temp_alias(self) -> str:
        chars = string.ascii_uppercase + string.digits
        return "Jugador_" + "".join(random.choices(chars, k=4))

    def suggest_players(self, favorite_team: str | None) -> list[str]:
        return suggest_players(favorite_team)

    def infer_timezone(self, message_timestamp_utc: str | None) -> int | None:
        if not message_timestamp_utc:
            return None
        try:
            ts = int(message_timestamp_utc)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        except (TypeError, ValueError):
            try:
                dt = datetime.fromisoformat(message_timestamp_utc.replace("Z", "+00:00"))
            except ValueError:
                return None
        return int(dt.utcoffset().total_seconds() // 3600) if dt.utcoffset() else None

    def infer_country_from_language(self, lang_code: str) -> str | None:
        mapping = {
            "pt": "BRA",
            "nl": "NLD",
            "de": "DEU",
            "ja": "JPN",
            "ko": "KOR",
        }
        return mapping.get((lang_code or "").lower()[:2])

    def should_trigger(self, user_id: str, event: str) -> dict[str, Any] | None:
        profile = self._users.get_profile(user_id)
        if not profile:
            return None
        stage = profile.get("onboarding_stage", STAGE_M3_COMPLETE)
        if stage == STAGE_M3_COMPLETE:
            return None

        if stage == STAGE_M1_COMPLETE:
            if event == EVENT_FIRST_PREDICTION and not profile.get("onboarding_m2_player_done"):
                return {
                    "moment": MOMENT_M2_PLAYER,
                    "suggested_players": self.suggest_players(profile.get("favorite_team")),
                }
            if event == EVENT_FIRST_TRIVIA and not profile.get("onboarding_m2_trivia_done"):
                return {"moment": MOMENT_M2_TRIVIA}

        if stage == STAGE_M2_COMPLETE:
            if event == EVENT_FIRST_RANKING and not profile.get("onboarding_m3_done"):
                return {"moment": MOMENT_M3}

        return None

    def get_pending_prompt(self, user_id: str, event: str | None = None) -> str | None:
        pending = self.should_trigger(user_id, event) if event else None
        if not pending and event:
            return None
        if not pending:
            profile = self._users.get_profile(user_id)
            if not profile:
                return None
            stage = profile.get("onboarding_stage", STAGE_M3_COMPLETE)
            if stage != STAGE_M1_PENDING:
                return None
            return None

        moment = pending["moment"]
        if moment == MOMENT_M2_PLAYER:
            players = pending.get("suggested_players") or self.suggest_players(None)
            opts = " | ".join(players[:3])
            return (
                "⚽ ¿Tenés algún jugador favorito del Mundial? "
                f"Te cuento curiosidades cuando juegue.\nSugeridos: {opts} (o otro nombre). "
                "/listo para saltear."
            )
        if moment == MOMENT_M2_TRIVIA:
            return (
                "¿Qué tan difícil querés la trivia?\n"
                "😊 Casual (+1 pt) | 🔥 Fanático (+2 pts) | 🧠 Enciclopedia (+3 pts)"
            )
        if moment == MOMENT_M3:
            return (
                "¿Qué te importa más del prode?\n"
                "🏆 Ganar | 😄 Divertirme con amigos | 📚 Aprender sobre fútbol\n"
                "/listo para saltear."
            )
        return None

    def complete_moment(self, user_id: str, moment: str, data: dict[str, Any] | None = None) -> dict:
        data = data or {}
        profile = self._users.get_profile(user_id) or {}

        if moment == MOMENT_M1:
            updates: dict[str, Any] = {
                "onboarding_stage": STAGE_M1_COMPLETE,
                "m1_step": None,
            }
            if data.get("alias"):
                updates["alias"] = data["alias"]
            if "favorite_team" in data:
                updates["favorite_team"] = data.get("favorite_team")
            if data.get("preferred_language"):
                updates["preferred_language"] = data["preferred_language"]
            self._users.update_profile(user_id, **updates)
            return {"ok": True, "stage": STAGE_M1_COMPLETE, "card": self.format_profile_card(user_id)}

        if moment == MOMENT_M2_PLAYER:
            updates = {"onboarding_m2_player_done": True}
            if data.get("favorite_player"):
                updates["favorite_player"] = data["favorite_player"]
            if data.get("skipped"):
                updates["favorite_player_skipped"] = True
            self._users.update_profile(user_id, **updates)
            self._maybe_advance_to_m2_complete(user_id)
            return {"ok": True, "stage": self._users.get_profile(user_id).get("onboarding_stage")}

        if moment == MOMENT_M2_TRIVIA:
            level = data.get("football_knowledge") or data.get("level")
            mapped = _KNOWLEDGE_MAP.get(str(level or "").lower(), level)
            updates = {
                "onboarding_m2_trivia_done": True,
                "football_knowledge": mapped or "medium",
            }
            self._users.update_profile(user_id, **updates)
            self._maybe_advance_to_m2_complete(user_id)
            return {"ok": True, "stage": self._users.get_profile(user_id).get("onboarding_stage")}

        if moment == MOMENT_M3:
            goal = _GOAL_MAP.get(str(data.get("prode_goal", "")).lower(), data.get("prode_goal"))
            self._users.update_profile(
                user_id,
                prode_goal=goal or "social",
                onboarding_m3_done=True,
                onboarding_stage=STAGE_M3_COMPLETE,
            )
            return {
                "ok": True,
                "stage": STAGE_M3_COMPLETE,
                "card": self.format_profile_card(user_id, complete=True),
            }

        return {"ok": False, "error": "unknown_moment"}

    def skip_current_moment(self, user_id: str) -> dict[str, Any]:
        profile = self._users.get_profile(user_id) or {}
        stage = profile.get("onboarding_stage", STAGE_M3_COMPLETE)
        m1_step = profile.get("m1_step")

        if stage == STAGE_M1_PENDING:
            if m1_step == M1_STEP_ALIAS or not m1_step:
                temp = self.generate_temp_alias()
                self._users.update_profile(
                    user_id,
                    alias=temp,
                    m1_step=M1_STEP_TEAM,
                    alias_suggestions_shown=False,
                )
                return {"ok": True, "m1_step": M1_STEP_TEAM, "alias": temp}
            if m1_step == M1_STEP_TEAM:
                self._users.update_profile(
                    user_id,
                    favorite_team=None,
                    m1_step=M1_STEP_LANG,
                )
                return {"ok": True, "m1_step": M1_STEP_LANG}
            if m1_step == M1_STEP_LANG:
                return self.complete_moment(
                    user_id,
                    MOMENT_M1,
                    {"alias": profile.get("alias"), "preferred_language": "es"},
                )

        if stage == STAGE_M1_COMPLETE and not profile.get("onboarding_m2_player_done"):
            return self.complete_moment(user_id, MOMENT_M2_PLAYER, {"skipped": True})
        if stage == STAGE_M1_COMPLETE and not profile.get("onboarding_m2_trivia_done"):
            return self.complete_moment(
                user_id, MOMENT_M2_TRIVIA, {"football_knowledge": "medium", "skipped": True}
            )
        if stage == STAGE_M2_COMPLETE and not profile.get("onboarding_m3_done"):
            return self.complete_moment(user_id, MOMENT_M3, {"prode_goal": "social", "skipped": True})

        return {"ok": True, "stage": stage}

    def save_m1_alias(self, user_id: str, alias: str) -> dict[str, Any]:
        ok, reason = self.validate_alias_for_user(user_id, alias)
        if not ok:
            if reason == "alias_taken":
                alts = self.suggest_alias_alternatives(alias)
                profile = self._users.get_profile(user_id) or {}
                if profile.get("alias_suggestions_shown"):
                    temp = self.generate_temp_alias()
                    self._users.update_profile(
                        user_id,
                        alias=temp,
                        m1_step=M1_STEP_TEAM,
                    )
                    return {
                        "ok": True,
                        "alias": temp,
                        "m1_step": M1_STEP_TEAM,
                        "used_temp": True,
                    }
                self._users.update_profile(user_id, alias_suggestions_shown=True)
                return {"ok": False, "alias_taken": True, "alternatives": alts}
            return {"ok": False, "error": reason}
        self._users.update_profile(user_id, alias=alias.strip(), m1_step=M1_STEP_TEAM)
        return {"ok": True, "alias": alias.strip(), "m1_step": M1_STEP_TEAM}

    def save_m1_team(self, user_id: str, team_code: str | None) -> dict[str, Any]:
        code = (team_code or "").upper()[:3] if team_code else None
        self._users.update_profile(user_id, favorite_team=code, m1_step=M1_STEP_LANG)
        return {"ok": True, "m1_step": M1_STEP_LANG, "favorite_team": code}

    def save_m1_language(self, user_id: str, lang: str) -> dict[str, Any]:
        lang_code = (lang or "es").lower()[:2]
        profile = self._users.get_profile(user_id) or {}
        return self.complete_moment(
            user_id,
            MOMENT_M1,
            {
                "alias": profile.get("alias"),
                "favorite_team": profile.get("favorite_team"),
                "preferred_language": lang_code,
            },
        )

    def _maybe_advance_to_m2_complete(self, user_id: str) -> None:
        profile = self._users.get_profile(user_id) or {}
        if profile.get("onboarding_m2_player_done") and profile.get("onboarding_m2_trivia_done"):
            self._users.update_profile(user_id, onboarding_stage=STAGE_M2_COMPLETE)

    def format_profile_card(self, user_id: str, *, complete: bool = False) -> str:
        p = self._users.get_profile(user_id) or {}
        alias = p.get("alias", "Jugador")
        lines = [
            "🎉 ¡Perfecto! Ya estás listo para predecir." if not complete else "🏆 ¡Onboarding completo!",
            "",
            "┌──────────────────────────────┐",
            f"│ ⚽  {alias}",
            "│     Miembro del Prode 2026   │",
        ]
        if p.get("favorite_team"):
            lines.append(f"│ 🇦🇷 Hincha de {p['favorite_team']}      │".replace("🇦🇷", "🏳️"))
        if p.get("preferred_language"):
            label = _LANG_LABELS.get(p["preferred_language"], p["preferred_language"])
            lines.append(f"│ 🌐 Idioma: {label}")
        if complete:
            if p.get("favorite_player"):
                lines.append(f"│ ⚽ Jugador favorito: {p['favorite_player']}")
            if p.get("football_knowledge"):
                lines.append(f"│ 🧠 Trivia: {p['football_knowledge']}")
            if p.get("prode_goal"):
                lines.append(f"│ 🎯 Objetivo: {p['prode_goal']}")
        stage = p.get("onboarding_stage", STAGE_M1_PENDING)
        progress = {"M1_PENDING": "0/3", "M1_COMPLETE": "1/3", "M2_COMPLETE": "2/3", "M3_COMPLETE": "3/3"}.get(
            stage, "?"
        )
        lines.append(f"│ 📊 Onboarding: {progress} completo")
        lines.append("└──────────────────────────────┘")
        return "\n".join(lines)

    def build_session_context(self, user_id: str) -> str:
        if not user_id or user_id in ("anonymous", "unregistered"):
            return ""

        profile = self._users.get_profile(user_id)
        if not profile:
            return ""

        stage = profile.get("onboarding_stage", STAGE_M3_COMPLETE)
        alias = profile.get("alias", "Jugador")
        is_admin = bool(profile.get("is_admin"))
        fav = profile.get("favorite_team") or "—"
        lang = profile.get("preferred_language") or "—"

        lines = [
            f"[Perfil: alias={alias}, onboarding_stage={stage}, is_admin={is_admin}, "
            f"favorite_team={fav}, preferred_language={lang}]",
        ]
        if stage == STAGE_M1_PENDING:
            lines.append(
                "[Onboarding M1: Telegram guía alias/equipo/idioma; no repitas ese flujo en el chat.]"
            )
        elif stage == STAGE_M1_COMPLETE:
            lines.append(
                "[Onboarding: M1 listo. Tras primera predicción, UNA pregunta jugador favorito; "
                "/listo = saltear.]"
            )
        elif stage == STAGE_M2_COMPLETE:
            lines.append(
                "[Onboarding: tras primer ranking, UNA pregunta objetivo del prode; /listo = saltear.]"
            )
        return "\n".join(lines)

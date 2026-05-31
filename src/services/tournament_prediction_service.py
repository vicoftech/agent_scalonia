"""Predicciones globales del torneo — SPEC-2026-048."""
from __future__ import annotations

from typing import Any

from src.dao.dynamo.match_dao import MatchDAO
from src.dao.dynamo.tournament_prediction_dao import (
    STATUS_DRAFT,
    STATUS_LOCKED,
    STATUS_SCORED,
    TournamentPredictionDAO,
)
from src.dao.dynamo.user_dao import UserDAO
from src.fixtures.mundial2026_groups import all_world_cup_team_codes
from src.fixtures.onboarding_players import GLOBAL_TOP_PLAYERS, suggest_players
from src.services.team_flags import TEAM_DISPLAY_NAMES, format_team_display

MATCH_LOCK_NUMBER = 72

WIZARD_FIELDS = (
    "champion_team",
    "finalist_team",
    "best_player_name",
    "top_scorer_name",
    "best_goalkeeper_name",
    "best_young_player_name",
    "revelation_team",
)

WIZARD_LABELS = {
    "champion_team": "Campeón",
    "finalist_team": "Finalista",
    "best_player_name": "Mejor jugador",
    "top_scorer_name": "Goleador",
    "best_goalkeeper_name": "Mejor arquero",
    "best_young_player_name": "Mejor joven",
    "revelation_team": "Revelación",
}

POINTS_TABLE = {
    "champion_team": 40,
    "finalist_team": 25,
    "best_player_name": 30,
    "top_scorer_name": 30,
    "best_goalkeeper_name": 20,
    "best_young_player_name": 20,
    "revelation_team": 25,
}


class TournamentPredictionService:
    def __init__(
        self,
        *,
        prediction_dao: TournamentPredictionDAO | None = None,
        user_dao: UserDAO | None = None,
        match_dao: MatchDAO | None = None,
    ):
        self._preds = prediction_dao or TournamentPredictionDAO()
        self._users = user_dao or UserDAO()
        self._matches = match_dao or MatchDAO()

    def is_editable(self) -> bool:
        m72 = self._matches.get_by_match_number(MATCH_LOCK_NUMBER)
        if not m72 or m72.get("status") != "FINISHED":
            return True
        return False

    def valid_team_codes(self) -> set[str]:
        return set(all_world_cup_team_codes())

    def get_predictions(self, user_id: str) -> dict[str, Any] | None:
        return self._preds.get_by_user(user_id)

    def get_wizard_draft(self, user_id: str) -> dict[str, Any]:
        profile = self._users.get_profile(user_id) or {}
        draft = dict(profile.get("tournament_wizard_draft") or {})
        saved = self.get_predictions(user_id) or {}
        for field in WIZARD_FIELDS:
            if field not in draft and saved.get(field):
                draft[field] = saved[field]
        return draft

    def save_wizard_draft(self, user_id: str, draft: dict[str, Any]) -> None:
        self._users.update_profile(user_id, tournament_wizard_draft=draft)

    def clear_wizard_draft(self, user_id: str) -> None:
        self._users.update_profile(user_id, tournament_wizard_draft=None)

    def set_draft_field(self, user_id: str, field: str, value: str) -> dict[str, Any]:
        if field not in WIZARD_FIELDS:
            raise ValueError("Campo de wizard inválido.")
        draft = self.get_wizard_draft(user_id)
        if field.endswith("_team"):
            code = (value or "").strip().upper()
            if code not in self.valid_team_codes():
                raise ValueError("Selección no válida para el Mundial 2026.")
            draft[field] = code
        else:
            name = (value or "").strip()
            if len(name) < 2 or len(name) > 80:
                raise ValueError("Nombre de jugador inválido (2–80 caracteres).")
            draft[field] = name
        self.save_wizard_draft(user_id, draft)
        return draft

    def validate_complete(self, data: dict[str, Any]) -> tuple[bool, str]:
        champion = data.get("champion_team")
        finalist = data.get("finalist_team")
        revelation = data.get("revelation_team")
        if not all(data.get(f) for f in WIZARD_FIELDS):
            return False, "Completá las 7 predicciones antes de confirmar."
        if champion == finalist:
            return False, "El campeón y el finalista no pueden ser la misma selección."
        if revelation in (champion, finalist):
            return False, "La revelación debe ser distinta del campeón y del finalista."
        return True, ""

    def confirm_predictions(self, user_id: str) -> tuple[bool, str]:
        if not self.is_editable():
            return False, (
                "⛔ Las predicciones del torneo ya están cerradas "
                "(terminó la fase de grupos)."
            )
        draft = self.get_wizard_draft(user_id)
        ok, err = self.validate_complete(draft)
        if not ok:
            return False, err
        payload = {k: draft[k] for k in WIZARD_FIELDS}
        payload["status"] = STATUS_DRAFT
        self._preds.put(user_id, payload)
        self._users.update_profile(
            user_id,
            tournament_predictions_status=STATUS_DRAFT,
            onboarding_m4_done=True,
        )
        self.clear_wizard_draft(user_id)
        return True, "✅ Predicciones del torneo guardadas."

    def lock_if_needed(self, user_id: str) -> None:
        if self.is_editable():
            return
        item = self.get_predictions(user_id)
        if item and item.get("status") == STATUS_DRAFT:
            self._preds.lock_user(user_id)
            self._users.update_profile(user_id, tournament_predictions_status=STATUS_LOCKED)

    def count_filled(self, user_id: str) -> tuple[int, int]:
        item = self.get_predictions(user_id) or self.get_wizard_draft(user_id)
        filled = sum(1 for f in WIZARD_FIELDS if item.get(f))
        return filled, len(WIZARD_FIELDS)

    def format_team_value(self, code: str | None) -> str:
        if not code:
            return "—"
        return format_team_display(code)

    def format_predictions_summary(self, user_id: str) -> str:
        item = self.get_predictions(user_id) or self.get_wizard_draft(user_id)
        lines = ["🏆 Tus predicciones del torneo", ""]
        icons = {
            "champion_team": "🥇",
            "finalist_team": "🥈",
            "best_player_name": "⭐",
            "top_scorer_name": "⚽",
            "best_goalkeeper_name": "🧤",
            "best_young_player_name": "🌱",
            "revelation_team": "💫",
        }
        for field in WIZARD_FIELDS:
            val = item.get(field)
            label = WIZARD_LABELS[field]
            if field.endswith("_team"):
                display = self.format_team_value(val) if val else "—"
            else:
                display = val or "—"
            lines.append(f"{icons[field]} {label}: {display}")
        if self.is_editable():
            lines.append("")
            lines.append("⏱️ Podés cambiarlas hasta el fin del partido #72.")
            lines.append("Los puntos suman en TODOS tus grupos al cierre del torneo.")
        else:
            saved = self.get_predictions(user_id)
            if saved and saved.get("status") == STATUS_SCORED:
                pts = int(saved.get("points_earned") or 0)
                lines.append("")
                lines.append(f"🏆 Bonus torneo: {pts} pts")
            else:
                lines.append("")
                lines.append("⛔ Veda cerrada. Puntos pendientes hasta la final (#104).")
        return "\n".join(lines)

    def suggest_players_for_user(self, user_id: str) -> list[str]:
        profile = self._users.get_profile(user_id) or {}
        base = suggest_players(profile.get("favorite_team"))
        extra = [p for p in GLOBAL_TOP_PLAYERS if p not in base]
        return (base + extra)[:6]

    def team_picker_page(
        self,
        *,
        page: int,
        exclude: set[str] | None = None,
        page_size: int = 12,
    ) -> tuple[list[str], int]:
        codes = [c for c in sorted(self.valid_team_codes()) if c not in (exclude or set())]
        total_pages = max(1, (len(codes) + page_size - 1) // page_size)
        page = max(0, min(page, total_pages - 1))
        start = page * page_size
        return codes[start : start + page_size], total_pages

    def team_label(self, code: str) -> str:
        name = TEAM_DISPLAY_NAMES.get(code, code)
        return f"{format_team_display(code)}"

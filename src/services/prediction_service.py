"""Predicciones por grupo — SPEC-2026-021 (MVP Telegram)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from src.dao.dynamo.group_dao import GLOBAL_GROUP_ID, GroupDAO
from src.dao.dynamo.match_dao import MatchDAO
from src.dao.dynamo.prediction_dao import PredictionDAO
from src.dao.dynamo.user_dao import UserDAO
from src.services.auth_service import USER_STATUS_ACTIVE

DISPLAY_TZ = timezone(timedelta(hours=-3))
KO_PHASES = frozenset(
    {"R16", "ROUND_OF_32", "ROUND_OF_16", "QF", "QUARTER_FINAL", "SF", "SEMI_FINAL", "FINAL", "THIRD_PLACE"}
)
DEFAULT_SCORES = ["1-0", "2-0", "1-1", "2-1", "0-1"]
_PREDICT_CMD = re.compile(
    r"^/predecir(?:@[\w_]+)?\s+([A-Za-z]{3})\s+(\d+)\s*[-:]\s*(\d+)\s+([A-Za-z]{3})\s*$",
    re.IGNORECASE,
)


@dataclass
class ValidationResult:
    ok: bool
    code: str = "ok"
    message: str = ""


class PredictionService:
    def __init__(
        self,
        prediction_dao: PredictionDAO | None = None,
        match_dao: MatchDAO | None = None,
        group_dao: GroupDAO | None = None,
        user_dao: UserDAO | None = None,
    ):
        self._preds = prediction_dao or PredictionDAO()
        self._matches = match_dao or MatchDAO()
        self._groups = group_dao or GroupDAO()
        self._users = user_dao or UserDAO()

    def check_can_predict(self, user_id: str) -> tuple[bool, str]:
        profile = self._users.get_profile(user_id)
        if not profile or profile.get("status") != USER_STATUS_ACTIVE:
            return False, "USER_INACTIVE"
        for gid in self._groups.list_group_ids_for_user(user_id):
            g = self._groups.get_group(gid)
            if g and not g.get("is_global") and g.get("status") != "DELETED":
                return True, "ok"
        return False, "NO_GROUP_MEMBERSHIP"

    def no_group_message(self) -> tuple[str, dict]:
        from src.services.prediction_telegram_ui import no_group_keyboard

        return (
            "⚠️ Para predecir necesitás pertenecer a al menos un grupo.\n\n"
            "Creá el tuyo o unite con un link de invitación.",
            no_group_keyboard(),
        )

    def resolve_group_short(self, user_id: str, grp8: str) -> str | None:
        needle = (grp8 or "").strip().lower()
        if not needle:
            return None
        for gid in self._predictable_groups(user_id):
            compact = gid.replace("-", "").lower()
            if compact.startswith(needle) or gid.lower().startswith(needle):
                return gid
        return None

    def _predictable_groups(self, user_id: str) -> list[str]:
        ids: list[str] = []
        for gid in self._groups.list_group_ids_for_user(user_id):
            g = self._groups.get_group(gid)
            if not g or g.get("is_global") or g.get("status") == "DELETED":
                continue
            ids.append(gid)
        return ids

    def get_active_group_id(self, user_id: str) -> str | None:
        profile = self._users.get_profile(user_id) or {}
        gid = profile.get("prediction_group_id")
        if gid and gid in self._predictable_groups(user_id):
            return gid
        groups = self._predictable_groups(user_id)
        return groups[0] if groups else None

    def set_active_group(self, user_id: str, group_id: str) -> str | None:
        if group_id not in self._predictable_groups(user_id):
            return None
        g = self._groups.get_group(group_id) or {}
        self._users.update_profile(user_id, prediction_group_id=group_id)
        return g.get("name", group_id)

    def _parse_kickoff(self, iso: str) -> datetime:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))

    def _veda_closed(self, match: dict) -> bool:
        if match.get("veda_active"):
            return True
        kickoff = self._parse_kickoff(match.get("kickoff_utc", ""))
        return datetime.now(timezone.utc) >= kickoff - timedelta(minutes=5)

    def validate_save(
        self,
        user_id: str,
        match: dict,
        home_goals: int,
        away_goals: int,
        *,
        playoff_via: str | None = None,
        playoff_winner: str | None = None,
    ) -> ValidationResult:
        ok, code = self.check_can_predict(user_id)
        if not ok:
            msgs = {
                "USER_INACTIVE": "Tu cuenta no está activa.",
                "NO_GROUP_MEMBERSHIP": "Necesitás un grupo para predecir.",
            }
            return ValidationResult(False, code, msgs.get(code, code))
        if self._veda_closed(match):
            return ValidationResult(False, "VEDA_ACTIVE", "La veda está activa para este partido.")
        if home_goals < 0 or away_goals < 0:
            return ValidationResult(False, "INVALID_SCORE", "Marcador inválido.")
        phase = (match.get("phase") or "GROUP").upper()
        is_draw = home_goals == away_goals
        if phase in KO_PHASES and is_draw:
            if not playoff_via or not playoff_winner:
                return ValidationResult(
                    False,
                    "KO_TIE_NEEDS_PLAYOFF",
                    "En eliminatorias con empate indicá tiempo extra o penales y el ganador.",
                )
            if playoff_winner not in (match.get("home_team"), match.get("away_team")):
                return ValidationResult(False, "INVALID_WINNER", "Ganador inválido para este partido.")
        return ValidationResult(True)

    def save_score(
        self,
        user_id: str,
        match_id: str,
        group_id: str,
        home_goals: int,
        away_goals: int,
        *,
        playoff_via: str | None = None,
        playoff_winner: str | None = None,
    ) -> tuple[str, dict | None]:
        match = self._matches.get_match(match_id)
        if not match:
            return "Partido no encontrado.", None
        vr = self.validate_save(
            user_id,
            match,
            home_goals,
            away_goals,
            playoff_via=playoff_via,
            playoff_winner=playoff_winner,
        )
        if not vr.ok:
            return vr.message, None

        had = self._preds.get_active(user_id, match_id, group_id)
        self._preds.save_prediction(
            user_id=user_id,
            match_id=match_id,
            group_id=group_id,
            home_goals=home_goals,
            away_goals=away_goals,
            playoff_via=playoff_via if home_goals == away_goals else None,
            playoff_winner=playoff_winner if home_goals == away_goals else None,
        )
        gname = (self._groups.get_group(group_id) or {}).get("name", group_id)
        score_txt = f"{match['home_team']} {home_goals}-{away_goals} {match['away_team']}"
        prefix = "✅" if not had else "🔄"
        extra = " (actualizada)" if had else ""
        mins = self._minutes_to_veda(match)
        max_pts = self._max_possible_points(home_goals == away_goals and (match.get("phase") or "").upper() in KO_PHASES)
        from src.services.prediction_telegram_ui import after_save_keyboard

        msg = (
            f"{prefix} {score_txt} guardada{extra}\n"
            f"👥 {gname}\n"
            f"Veda en {mins}  ·  Máx posible: {max_pts} pts\n\n"
            "Para sumar hasta 8 pts extra: /completo"
        )
        return msg, after_save_keyboard(match, group_id)

    def _minutes_to_veda(self, match: dict) -> str:
        kickoff = self._parse_kickoff(match.get("kickoff_utc", ""))
        veda_at = kickoff - timedelta(minutes=30)
        delta = veda_at - datetime.now(timezone.utc)
        if delta.total_seconds() <= 0:
            return "cerrada"
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m = rem // 60
        if h:
            return f"{h}h {m}min"
        return f"{m}min"

    def _max_possible_points(self, ko_tie: bool) -> int:
        return 22 if ko_tie else 10

    def list_partidos_view(self, user_id: str) -> tuple[str, dict | None]:
        ok, code = self.check_can_predict(user_id)
        if not ok:
            if code == "NO_GROUP_MEMBERSHIP":
                return self.no_group_message()
            return "No podés predecir con esta cuenta.", None

        gid = self.get_active_group_id(user_id)
        if not gid:
            return self.no_group_message()

        g = self._groups.get_group(gid) or {}
        now = datetime.now(timezone.utc)
        window_end = now + timedelta(hours=48)
        rows: list[tuple[dict, dict | None, int]] = []

        for m in self._matches.list_matches():
            if m.get("status") == "FINISHED":
                continue
            ko = self._parse_kickoff(m.get("kickoff_utc", ""))
            if ko > window_end:
                continue
            pred = self._preds.get_active(user_id, m["match_id"], gid)
            closed = self._veda_closed(m)
            rows.append((m, pred, int(m.get("match_number", 0))))

        rows.sort(key=lambda x: (self._parse_kickoff(x[0]["kickoff_utc"]), x[2]))
        if not rows:
            return "No hay partidos próximos en las próximas 48 h.", None

        day_label = datetime.now(DISPLAY_TZ).strftime("%a %d %b")
        lines = [f"⚽ Próximos partidos — {day_label}", f"👥 Grupo activo: {g.get('name', gid)}", ""]
        buttons: list[list[dict[str, str]]] = []
        g8 = gid.replace("-", "")[:8]

        for idx, (m, pred, num) in enumerate(rows[:12], start=1):
            closed = self._veda_closed(m)
            gl = m.get("group_letter") or "—"
            kick_local = self._parse_kickoff(m["kickoff_utc"]).astimezone(DISPLAY_TZ)
            time_s = kick_local.strftime("%H:%M")
            if closed and not pred:
                status = "🔒 Sin predecir (veda)"
            elif pred:
                icons = self._pred_icons(pred)
                status = f"✅ {pred['home_goals']}-{pred['away_goals']}{icons}"
            else:
                status = "⏳ Sin predecir"
            lines.append(
                f"{idx}️⃣  {m['home_team']} vs {m['away_team']}  │ Grupo {gl} │ {time_s}  {status}"
            )
            if not closed:
                buttons.append(
                    [{"text": str(idx), "callback_data": f"prd:o:{num}:{g8}"}]
                )

        if len(self._predictable_groups(user_id)) > 1:
            buttons.append([{"text": "🔄 Cambiar grupo", "callback_data": f"prd:cg:{g8}"}])

        from src.services.prediction_telegram_ui import merge_button_rows

        return "\n".join(lines), merge_button_rows(buttons)

    def _pred_icons(self, pred: dict) -> str:
        parts = []
        if pred.get("scorer_name"):
            parts.append("⚽")
        if pred.get("has_red_card") is not None:
            parts.append("🟥")
        if pred.get("mvp_name"):
            parts.append("⭐")
        return " " + "".join(parts) if parts else ""

    def open_match_picker(
        self, user_id: str, match_number: int, group_id: str
    ) -> tuple[str, dict | None]:
        match = self._matches.get_by_match_number(match_number)
        if not match:
            return "Partido no encontrado.", None
        if self._veda_closed(match):
            return (
                f"⛔ La veda para {match['home_team']} vs {match['away_team']} está activa.",
                None,
            )
        gid = group_id or self.get_active_group_id(user_id)
        if not gid:
            return self.no_group_message()

        existing = self._preds.get_active(user_id, match["match_id"], gid)
        gname = (self._groups.get_group(gid) or {}).get("name", gid)
        g8 = gid.replace("-", "")[:8]
        num = int(match.get("match_number", 0))

        if existing:
            from src.services.prediction_telegram_ui import change_existing_keyboard

            mins = self._minutes_to_veda(match)
            return (
                f"🔄 {match['home_team']} vs {match['away_team']} — "
                f"tenés {existing['home_goals']}-{existing['away_goals']}\n"
                f"👥 {gname}\nVeda cierra en {mins}\n\n¿Querés cambiarla?",
                change_existing_keyboard(num, g8),
            )

        phase = (match.get("phase") or "GROUP").upper()
        ko_hint = ""
        if phase in KO_PHASES:
            ko_hint = "\n\n💡 Fase eliminatoria: si predís empate elegí definición (ET/penales)."

        lines = [
            f"{match['home_team']} vs {match['away_team']}",
            f"Grupo {match.get('group_letter') or '—'}  │  {match.get('venue', '')} · {match.get('city', '')}",
            f"{self._format_kickoff(match)} · Veda en {self._minutes_to_veda(match)}",
            f"👥 {gname}",
            "",
            "¿Cuánto terminan?",
        ]
        from src.services.prediction_telegram_ui import score_picker_keyboard

        return "\n".join(lines) + ko_hint, score_picker_keyboard(match, num, g8)

    def _format_kickoff(self, match: dict) -> str:
        dt = self._parse_kickoff(match["kickoff_utc"]).astimezone(DISPLAY_TZ)
        return dt.strftime("%H:%M ARG")

    def parse_predecir_command(self, text: str) -> tuple[str, int, int, str] | None:
        m = _PREDICT_CMD.match(text.strip())
        if not m:
            return None
        return m.group(1).upper(), int(m.group(2)), int(m.group(3)), m.group(4).upper()

    def save_predecir_command(
        self, user_id: str, home_code: str, home_goals: int, away_goals: int, away_code: str
    ) -> tuple[str, dict | None]:
        gid = self.get_active_group_id(user_id)
        if not gid:
            return self.no_group_message()
        match = None
        for m in self._matches.list_matches():
            if m.get("home_team") == home_code and m.get("away_team") == away_code:
                if not self._veda_closed(m):
                    match = m
                    break
        if not match:
            return (
                f"No encontré partido abierto {home_code} vs {away_code}. "
                "Usá /partidos para elegir desde la lista.",
                None,
            )
        return self.save_score(user_id, match["match_id"], gid, home_goals, away_goals)

    def format_completo_menu(self, user_id: str) -> tuple[str, dict | None]:
        gid = self.get_active_group_id(user_id)
        if not gid:
            return self.no_group_message()
        preds = self._preds.list_user_predictions(user_id, group_id=gid, status="ACTIVE")
        open_preds = []
        for p in preds:
            m = self._matches.get_match(p["match_id"])
            if m and not self._veda_closed(m):
                open_preds.append((m, p))
        if not open_preds:
            return "No tenés predicciones activas con veda abierta. Usá /partidos primero.", None
        m, p = open_preds[0]
        gname = (self._groups.get_group(gid) or {}).get("name", gid)
        g8 = gid.replace("-", "")[:8]
        num = int(m.get("match_number", 0))
        from src.services.prediction_telegram_ui import completo_menu_keyboard

        return (
            f"🎯 Completar — {m['home_team']} {p['home_goals']}-{p['away_goals']} {m['away_team']}\n"
            f"👥 {gname}\n\nVariables opcionales — hasta +8 pts extra:",
            completo_menu_keyboard(num, g8),
        )

    def apply_completo_red_card(
        self, user_id: str, match_number: int, group_id: str, has_red: bool
    ) -> str:
        match = self._matches.get_by_match_number(match_number)
        if not match:
            return "Partido no encontrado."
        if self._veda_closed(match):
            return "Veda activa."
        self._preds.update_optional_fields(
            user_id, match["match_id"], group_id, has_red_card=has_red
        )
        label = "Sí, habrá roja" if has_red else "No habrá roja"
        return f"✅ Expulsión: {label} guardado."

    def group_picker_keyboard(self, user_id: str) -> tuple[str, dict]:
        from src.services.prediction_telegram_ui import group_picker_keyboard

        groups = [
            self._groups.get_group(gid)
            for gid in self._predictable_groups(user_id)
        ]
        groups = [g for g in groups if g]
        return "Elegí el grupo activo para predecir:", group_picker_keyboard(groups)

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
from src.services.team_flags import format_team

DISPLAY_TZ = timezone(timedelta(hours=-3))
GROUP_PHASE = frozenset({"GROUP"})
PARTIDOS_PAGE_SIZE = 8
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

    def format_match_title(self, match: dict) -> str:
        return f"{format_team(match['home_team'])} vs {format_team(match['away_team'])}"

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

    def _kickoff_or_none(self, match: dict) -> datetime | None:
        raw = match.get("kickoff_utc")
        if not raw:
            return None
        try:
            return self._parse_kickoff(str(raw))
        except (ValueError, TypeError):
            return None

    def _group_stage_matches(self) -> list[tuple[datetime, dict]]:
        """Todos los partidos de fase de grupos, ordenados por fecha."""
        rows: list[tuple[datetime, dict]] = []
        for m in self._matches.list_matches():
            if (m.get("phase") or "").upper() not in GROUP_PHASE:
                continue
            ko = self._kickoff_or_none(m)
            sort_key = ko or datetime.max.replace(tzinfo=timezone.utc)
            rows.append((sort_key, m))
        rows.sort(key=lambda x: (x[0], int(x[1].get("match_number", 0))))
        return rows

    def _format_list_kickoff(self, match: dict) -> str:
        ko_dt = self._kickoff_or_none(match)
        if ko_dt is None:
            return "—"
        kick_local = ko_dt.astimezone(DISPLAY_TZ)
        today = datetime.now(DISPLAY_TZ).date()
        if kick_local.date() == today:
            return kick_local.strftime("%H:%M")
        return kick_local.strftime("%d/%m %H:%M")

    def _format_button_date(self, match: dict) -> str:
        """Fecha corta para botones inline (ej. 16/06)."""
        ko_dt = self._kickoff_or_none(match)
        if ko_dt is None:
            return "—"
        return ko_dt.astimezone(DISPLAY_TZ).strftime("%d/%m")

    def _match_list_status(self, match: dict, pred: dict | None) -> str:
        if (match.get("status") or "").upper() == "FINISHED":
            if pred:
                icons = self._pred_icons(pred)
                return f"✅ {pred['home_goals']}-{pred['away_goals']}{icons}"
            return "🏁 Finalizado"
        if self._veda_closed(match):
            if pred:
                icons = self._pred_icons(pred)
                return f"✅ {pred['home_goals']}-{pred['away_goals']}{icons}"
            return "🔒 Sin predecir (veda)"
        if pred:
            icons = self._pred_icons(pred)
            return f"✅ {pred['home_goals']}-{pred['away_goals']}{icons}"
        return "⏳ Sin predecir"

    def _veda_closed(self, match: dict) -> bool:
        if match.get("veda_active"):
            return True
        kickoff = self._kickoff_or_none(match)
        if kickoff is None:
            return False
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

    def _persist_score(
        self,
        user_id: str,
        match_id: str,
        group_id: str,
        home_goals: int,
        away_goals: int,
        *,
        playoff_via: str | None = None,
        playoff_winner: str | None = None,
    ) -> str | None:
        """Guarda marcador. None si OK; mensaje de error si falla."""
        match = self._matches.get_match(match_id)
        if not match:
            return "Partido no encontrado."
        vr = self.validate_save(
            user_id,
            match,
            home_goals,
            away_goals,
            playoff_via=playoff_via,
            playoff_winner=playoff_winner,
        )
        if not vr.ok:
            return vr.message

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
        score_txt = self.format_match_title(match) + f"  {home_goals}-{away_goals}"
        prefix = "✅" if not had else "🔄"
        extra = " (actualizada)" if had else ""
        mins = self._minutes_to_veda(match)
        ko_tie = home_goals == away_goals and (match.get("phase") or "").upper() in KO_PHASES
        max_pts = self._max_possible_points(ko_tie)
        return (
            f"{prefix} Marcador guardado{extra}\n"
            f"{score_txt}\n"
            f"👥 {gname}\n"
            f"Veda en {mins}  ·  Máx posible: {max_pts} pts"
        )

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
        from src.services import prediction_wizard as pw

        match = self._matches.get_match(match_id)
        if not match:
            return "Partido no encontrado.", None
        num = int(match.get("match_number", 0))
        return pw.wizard_submit_score(
            self,
            user_id,
            num,
            group_id,
            home_goals,
            away_goals,
            playoff_via=playoff_via,
            playoff_winner=playoff_winner,
        )

    def _minutes_to_veda(self, match: dict) -> str:
        kickoff = self._kickoff_or_none(match)
        if kickoff is None:
            return "—"
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

    def list_partidos_view(self, user_id: str, *, page: int = 0) -> tuple[str, dict | None]:
        ok, code = self.check_can_predict(user_id)
        if not ok:
            if code == "NO_GROUP_MEMBERSHIP":
                return self.no_group_message()
            return "No podés predecir con esta cuenta.", None

        gid = self.get_active_group_id(user_id)
        if not gid:
            return self.no_group_message()

        g = self._groups.get_group(gid) or {}
        all_rows = self._group_stage_matches()
        if not all_rows:
            return (
                "No hay partidos de fase de grupos cargados.\n"
                "Un admin debe ejecutar el ingest del fixture (scripts/ingest_matches.py).",
                None,
            )

        total = len(all_rows)
        page_size = PARTIDOS_PAGE_SIZE
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(0, min(page, total_pages - 1))
        slice_rows = all_rows[page * page_size : (page + 1) * page_size]

        lines = [
            "⚽ Fase de grupos",
            f"👥 Grupo activo: {g.get('name', gid)}",
            f"📄 Página {page + 1}/{total_pages} · {total} partidos",
            "",
            "Elegí un partido:",
            "⏳ sin predicción · ✅ ya predijiste · 🔒 veda o finalizado",
        ]
        buttons: list[list[dict[str, str]]] = []
        g8 = gid.replace("-", "")[:8]

        from src.services.prediction_telegram_ui import (
            merge_button_rows,
            partido_list_button_label,
            partidos_nav_keyboard,
        )

        for _idx, (_ko, m) in enumerate(slice_rows, start=1):
            pred = self._preds.get_active(user_id, m["match_id"], gid)
            num = int(m.get("match_number", 0))
            finished = (m.get("status") or "").upper() == "FINISHED"
            is_predictable = not self._veda_closed(m) and not finished
            label = partido_list_button_label(
                m,
                match_number=num,
                group_letter=str(m.get("group_letter") or "—"),
                date_label=self._format_button_date(m),
                has_prediction=pred is not None,
                is_predictable=is_predictable,
            )
            buttons.append(
                [{"text": label, "callback_data": f"prd:o:{num}:{g8}"}]
            )

        nav = partidos_nav_keyboard(page, total_pages, g8)
        if nav:
            buttons.append(nav)
        if len(self._predictable_groups(user_id)) > 1:
            buttons.append([{"text": "🔄 Cambiar grupo", "callback_data": f"prd:cg:{g8}"}])

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

    def _match_has_final_result(self, match: dict) -> bool:
        if (match.get("status") or "").upper() == "FINISHED":
            return True
        res = self._matches.get_result(match["match_id"])
        if not res:
            return False
        return (
            res.get("result_90min_home") is not None
            or res.get("result_final_home") is not None
        )

    def format_finished_match_view(
        self, user_id: str, match: dict, group_id: str
    ) -> tuple[str, dict | None]:
        gid = group_id or self.get_active_group_id(user_id)
        if not gid:
            return self.no_group_message()
        gname = (self._groups.get_group(gid) or {}).get("name", gid)
        pred = self._preds.get_for_group(user_id, match["match_id"], gid)
        result = self._matches.get_result(match["match_id"])
        from src.services.prediction_result_report import format_finished_match_report

        text = format_finished_match_report(
            match,
            group_name=gname,
            result=result,
            prediction=pred,
        )
        return text, None

    def open_match_picker(
        self, user_id: str, match_number: int, group_id: str
    ) -> tuple[str, dict | None]:
        match = self._matches.get_by_match_number(match_number)
        if not match:
            return "Partido no encontrado.", None

        gid = group_id or self.get_active_group_id(user_id)
        if not gid:
            return self.no_group_message()

        if self._match_has_final_result(match):
            return self.format_finished_match_view(user_id, match, gid)

        if self._veda_closed(match):
            return (
                f"⛔ La veda para {self.format_match_title(match)} está activa.",
                None,
            )

        existing = self._preds.get_active(user_id, match["match_id"], gid)
        gname = (self._groups.get_group(gid) or {}).get("name", gid)
        g8 = gid.replace("-", "")[:8]
        num = int(match.get("match_number", 0))

        if existing:
            from src.services.prediction_telegram_ui import change_existing_keyboard

            mins = self._minutes_to_veda(match)
            return (
                f"🔄 {self.format_match_title(match)} — "
                f"tenés {existing['home_goals']}-{existing['away_goals']}\n"
                f"👥 {gname}\nVeda cierra en {mins}\n\n¿Querés cambiarla?",
                change_existing_keyboard(num, g8),
            )

        from src.services import prediction_wizard as pw

        return pw.start_wizard(self, user_id, num, gid)

    def _format_kickoff(self, match: dict) -> str:
        ko = self._kickoff_or_none(match)
        if ko is None:
            return "—"
        return ko.astimezone(DISPLAY_TZ).strftime("%H:%M ARG")

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

    def format_completo_menu(
        self,
        user_id: str,
        *,
        match_number: int | None = None,
        group_id: str | None = None,
    ) -> tuple[str, dict | None]:
        gid = group_id or self.get_active_group_id(user_id)
        if not gid:
            return self.no_group_message()

        if match_number is not None:
            m = self._matches.get_by_match_number(match_number)
            if not m:
                return "Partido no encontrado.", None
            p = self._preds.get_active(user_id, m["match_id"], gid)
            if not p:
                from src.services import prediction_wizard as pw

                return pw.start_wizard(
                    self, user_id, match_number, gid
                )
            if self._veda_closed(m):
                return "La veda ya está activa para ese partido.", None
            from src.services import prediction_wizard as pw

            return pw.resume_wizard_after_score(self, user_id, match_number, gid)

        preds = self._preds.list_user_predictions(user_id, group_id=gid, status="ACTIVE")
        open_preds = []
        for p in preds:
            m = self._matches.get_match(p["match_id"])
            if m and not self._veda_closed(m):
                open_preds.append((m, p))
        if not open_preds:
            return "No tenés predicciones activas con veda abierta. Usá /partidos primero.", None
        if len(open_preds) == 1:
            m, _p = open_preds[0]
            from src.services import prediction_wizard as pw

            return pw.resume_wizard_after_score(
                self, user_id, int(m.get("match_number", 0)), gid
            )
        lines = ["🎯 Elegí qué predicción completar:", ""]
        from src.services.prediction_telegram_ui import merge_button_rows

        buttons: list[list[dict[str, str]]] = []
        g8 = gid.replace("-", "")[:8]
        for m, p in open_preds[:8]:
            num = int(m.get("match_number", 0))
            label = f"{self.format_match_title(m)} {p['home_goals']}-{p['away_goals']}"[:60]
            buttons.append(
                [{"text": label, "callback_data": f"prd:full:{num}:{g8}"}]
            )
        return "\n".join(lines), merge_button_rows(buttons)

    def apply_completo_red_card(
        self, user_id: str, match_number: int, group_id: str, has_red: bool
    ) -> str:
        match = self._matches.get_by_match_number(match_number)
        if not match:
            return "Partido no encontrado."
        if self._veda_closed(match):
            return "Veda activa."
        updated = self._preds.update_optional_fields(
            user_id, match["match_id"], group_id, has_red_card=has_red
        )
        if not updated:
            return "No tenés predicción guardada para ese partido. Usá /partidos primero."
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

    def begin_custom_score(
        self, user_id: str, match_number: int, group_id: str
    ) -> tuple[str, dict | None]:
        from src.services import prediction_wizard as pw

        return pw.wizard_begin_custom_score(self, user_id, match_number, group_id)

    def start_prediction_wizard(
        self, user_id: str, match_number: int, group_id: str
    ) -> tuple[str, dict | None]:
        from src.services import prediction_wizard as pw

        return pw.start_wizard(self, user_id, match_number, group_id)

    def handle_pending_message(
        self, user_id: str, text: str
    ) -> tuple[str, dict | None] | None:
        from src.services import prediction_wizard as pw

        profile = self._users.get_profile(user_id) or {}
        low = (text or "").strip().lower()
        if low in ("/cancel", "/cancelar"):
            if profile.get("prediction_wizard"):
                return pw.wizard_cancel(self, user_id)
            return None
        if (text or "").strip().startswith("/"):
            return None

        result = pw.wizard_handle_text(self, user_id, text)
        if result is not None:
            return result
        return None

    def start_completo_wizard(
        self, user_id: str, match_number: int, group_id: str
    ) -> tuple[str, dict | None]:
        from src.services import prediction_wizard as pw

        return pw.resume_wizard_after_score(self, user_id, match_number, group_id)

    def apply_completo_wizard_red(
        self, user_id: str, match_number: int, group_id: str, has_red: bool | None
    ) -> tuple[str, dict | None]:
        from src.services import prediction_wizard as pw

        if has_red is not None:
            return pw.wizard_set_red(self, user_id, match_number, group_id, has_red)
        return pw.wizard_advance_skip(self, user_id)

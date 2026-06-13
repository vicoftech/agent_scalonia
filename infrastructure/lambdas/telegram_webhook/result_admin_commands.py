"""Comandos admin resultados — wizard texto SPEC-2026-051."""
from __future__ import annotations

import logging
import re
from typing import Any

from src.dao.dynamo.match_dao import MatchDAO
from src.dao.dynamo.result_dao import ResultDAO
from src.models.match_result import MatchResult
from src.services.result_admin_notify import (
    WIZARD_STEPS,
    format_admin_pending_message,
    format_admin_preview_message,
    pending_result_keyboard,
    publish_confirm_keyboard,
    wizard_prompt_for_step,
)
from src.services.result_admin_service import ResultAdminService
from src.services.result_source_aggregator import AggregatedCandidate

logger = logging.getLogger(__name__)

_RESULTADO_PENDIENTES = re.compile(r"^/resultado_pendientes(?:@[\w_]+)?\s*$", re.I)
_RESULTADO_PUBLICADOS = re.compile(r"^/resultado_publicados(?:@[\w_]+)?\s*$", re.I)
_RESULTADO_RECOLECTAR = re.compile(
    r"^/resultado_recolectar(?:@[\w_]+)?\s+(\S+)\s+(\S+)\s*$",
    re.I,
)
_RESULTADO_EDITAR = re.compile(
    r"^/resultado_editar(?:@[\w_]+)?(?:\s+(\S+)\s+(\S+))?\s*$",
    re.I,
)

_SCORE_RE = re.compile(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$")
_SI_NO_RE = re.compile(r"^\s*(si|sí|no)\s*$", re.I)

_TOUCHED_KEY = "_touched"


def _admin_only(user_id: str) -> bool:
    from src.services.auth_service import AuthService

    return AuthService().is_admin_global(user_id)


def _resolve_match(teams: tuple[str, str] | None, match_id: str | None = None) -> dict[str, Any] | None:
    dao = MatchDAO()
    if match_id:
        return dao.get_match(match_id)
    if teams:
        return dao.find_by_teams(teams[0], teams[1])
    return None


def _get_wizard(profile: dict[str, Any]) -> dict[str, Any] | None:
    wiz = profile.get("result_admin_wizard")
    return wiz if isinstance(wiz, dict) else None


def _save_wizard(user_id: str, wizard: dict[str, Any] | None) -> None:
    from src.dao.dynamo.user_dao import UserDAO

    UserDAO().update_profile(user_id, result_admin_wizard=wizard)


def _touch_draft(draft: dict[str, Any], *fields: str) -> None:
    touched = set(draft.get(_TOUCHED_KEY) or [])
    touched.update(fields)
    draft[_TOUCHED_KEY] = sorted(touched)


def _draft_to_result(draft: dict[str, Any], match: dict[str, Any]) -> MatchResult:
    red = draft.get("red_cards", 0)
    return MatchResult(
        home_goals=int(draft.get("home_goals", 0)),
        away_goals=int(draft.get("away_goals", 0)),
        phase=match.get("phase", "GROUP"),
        mvp_name=None,
        red_cards=int(red) if isinstance(red, bool) else int(red or 0),
        goal_before_5min=draft.get("goal_before_5min"),
        var_used=draft.get("var_used"),
        free_kick_goal=draft.get("free_kick_goal"),
        penalty_saved=draft.get("penalty_saved"),
        penalty_scored=draft.get("penalty_scored"),
        source="web_search",
        match_id=match.get("match_id"),
    )


def _start_wizard(user_id: str, match: dict[str, Any]) -> tuple[str, None]:
    mid = match["match_id"]
    wizard = {
        "match_id": mid,
        "step_idx": 0,
        "draft": {_TOUCHED_KEY: []},
    }
    _save_wizard(user_id, wizard)
    return wizard_prompt_for_step(match, 0), None


def _parse_score(text: str) -> tuple[int, int] | None:
    m = _SCORE_RE.match((text or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _parse_si_no(text: str) -> bool | None:
    m = _SI_NO_RE.match((text or "").strip())
    if not m:
        return None
    return m.group(1).lower() in ("si", "sí")


def matches_result_admin_command(text: str) -> bool:
    stripped = (text or "").strip()
    return bool(
        _RESULTADO_PENDIENTES.match(stripped)
        or _RESULTADO_PUBLICADOS.match(stripped)
        or _RESULTADO_RECOLECTAR.match(stripped)
        or _RESULTADO_EDITAR.match(stripped)
    )


def is_wizard_active(profile: dict[str, Any]) -> bool:
    wiz = _get_wizard(profile)
    return bool(wiz and wiz.get("match_id"))


def handle_result_admin_wizard(
    user_id: str,
    profile: dict[str, Any],
    text: str,
) -> tuple[str | None, dict | None] | None:
    """Wizard secuencial: marcador → cada extendida (SI/NO)."""
    if not _admin_only(user_id):
        return None
    wiz = _get_wizard(profile)
    if not wiz or not wiz.get("match_id"):
        return None

    if (text or "").strip().lower() in ("/cancel", "/cancelar"):
        _save_wizard(user_id, None)
        return "Wizard cancelado.", None

    match_id = str(wiz["match_id"])
    match = MatchDAO().get_match(match_id)
    if not match:
        _save_wizard(user_id, None)
        return "Partido no encontrado.", None

    step_idx = int(wiz.get("step_idx", 0))
    if step_idx < 0 or step_idx >= len(WIZARD_STEPS):
        _save_wizard(user_id, None)
        return "Wizard inválido. Usá /resultado_editar HOME AWAY.", None

    field, _label = WIZARD_STEPS[step_idx]
    draft = dict(wiz.get("draft") or {})
    draft.setdefault(_TOUCHED_KEY, [])

    if field == "score":
        parsed = _parse_score(text)
        if not parsed:
            return (
                "Formato inválido. Ingresá el resultado así: 2-0",
                None,
            )
        draft["home_goals"], draft["away_goals"] = parsed
        _touch_draft(draft, "home_goals", "away_goals")
        step_idx += 1
    else:
        val = _parse_si_no(text)
        if val is None:
            return "Respondé solo SI o NO.", None
        if field == "red_cards":
            draft["red_cards"] = 1 if val else 0
        else:
            draft[field] = val
        _touch_draft(draft, field)
        step_idx += 1

    wiz["draft"] = draft
    wiz["step_idx"] = step_idx
    _save_wizard(user_id, wiz)

    if step_idx >= len(WIZARD_STEPS):
        result = _draft_to_result(draft, match)
        republish = ResultDAO().has_scores(match_id)
        preview = format_admin_preview_message(match, result, republish=republish)
        return preview, publish_confirm_keyboard(match_id)

    return wizard_prompt_for_step(match, step_idx), None


def handle_result_admin_command(
    user_id: str,
    text: str,
) -> tuple[str | None, dict | None]:
    stripped = (text or "").strip()
    if not matches_result_admin_command(stripped):
        return None, None
    if not _admin_only(user_id):
        return "Solo administradores pueden gestionar resultados.", None

    if _RESULTADO_PENDIENTES.match(stripped):
        return _list_pending(), None
    if _RESULTADO_PUBLICADOS.match(stripped):
        return _list_published(), None

    m = _RESULTADO_RECOLECTAR.match(stripped)
    if m:
        match = _resolve_match((m.group(1), m.group(2)))
        if not match:
            return "No encontré ese partido.", None
        cand = ResultAdminService().propose_result(match["match_id"], force_notify=True)
        if not cand:
            return "No pude recolectar un borrador. Reintentá más tarde.", None
        return format_admin_pending_message(match, cand), pending_result_keyboard(match["match_id"])

    m = _RESULTADO_EDITAR.match(stripped)
    if m:
        home_t, away_t = m.group(1), m.group(2)
        if not home_t:
            lines = [
                "Uso: /resultado_editar HOME AWAY",
                "Ejemplo: /resultado_editar CAN BIH",
            ]
            try:
                published = _list_published()
                if published:
                    lines.extend(["", published])
            except Exception:
                logger.exception("resultado_editar list_published failed")
            return "\n".join(lines), None
        match = _resolve_match((home_t, away_t))
        if not match:
            return "No encontré ese partido.", None
        return _start_wizard(user_id, match)

    return None, None


def handle_result_admin_callback(
    user_id: str,
    data: str,
    *,
    callback_query_id: str | None = None,
) -> tuple[str | None, dict | None]:
    from handler import _get_token, _post_json

    if not data.startswith("res:"):
        return None, None
    if not _admin_only(user_id):
        return "Solo administradores.", None

    token = _get_token()
    if callback_query_id:
        _post_json(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            {"callback_query_id": callback_query_id},
            timeout=5,
        )

    svc = ResultAdminService()
    parts = data.split(":")

    if len(parts) >= 4 and parts[1] == "pub":
        action = parts[2]
        match_id = parts[3]
        match = MatchDAO().get_match(match_id)
        if not match:
            return "Partido no encontrado.", None

        if action in ("wizard", "edit", "confirm"):
            return _start_wizard(user_id, match)

        if action == "reject":
            svc.reject_candidate(match_id, user_id)
            return "Borrador rechazado.", None

        if action == "recolect":
            cand = svc.propose_result(match_id, force_notify=True)
            if not cand:
                return "No pude recolectar de nuevo.", None
            return (
                format_admin_pending_message(match, cand),
                pending_result_keyboard(match_id),
            )

        if action == "cancel":
            _save_wizard(user_id, None)
            return "Publicación cancelada.", None

        if action == "publish":
            from src.dao.dynamo.user_dao import UserDAO

            profile = UserDAO().get_profile(user_id) or {}
            wiz = _get_wizard(profile)
            if not wiz or wiz.get("match_id") != match_id:
                return "No hay wizard activo. Usá /resultado_editar HOME AWAY.", None
            draft = wiz.get("draft") or {}
            if "home_goals" not in draft or "away_goals" not in draft:
                return "Completá el wizard antes de publicar.", None
            result = _draft_to_result(draft, match)
            if ResultDAO().has_scores(match_id):
                outcome = svc.republish_result(match_id, result, user_id)
            else:
                svc.update_candidate_from_admin(match_id, result, user_id)
                outcome = svc.confirm_and_publish(match_id, user_id)
            _save_wizard(user_id, None)
            if not outcome.published:
                return f"Error: {', '.join(outcome.errors)}", None
            label = "Republicado" if outcome.republish else "Publicado"
            return f"✅ {label} v{outcome.publish_version}.", None

        if action == "back":
            cand_raw = ResultDAO().get_candidate_raw(match_id)
            if not cand_raw:
                return "Sin borrador pendiente.", None
            proposed = ResultDAO.candidate_proposed_result(cand_raw)
            if not proposed:
                return "Borrador inválido.", None
            candidate = AggregatedCandidate(
                match_id=match_id,
                proposed=proposed,
                consensus_score=float(cand_raw.get("consensus_score", 0)),
                warnings=list(cand_raw.get("warnings") or []),
            )
            return (
                format_admin_pending_message(match, candidate),
                pending_result_keyboard(match_id),
            )

    return None, None


def _list_pending() -> str:
    items = ResultDAO().list_pending_candidates(limit=15)
    if not items:
        return "No hay resultados pendientes de revisión."
    lines = ["📋 Resultados pendientes:", ""]
    mdao = MatchDAO()
    for item in items:
        mid = item.get("match_id", "")
        m = mdao.get_match(mid) or {}
        pr = ResultDAO.candidate_proposed_result(item)
        score = f"{pr.home_goals}-{pr.away_goals}" if pr else "?"
        lines.append(
            f"• #{m.get('match_number', '?')} {m.get('home_team', '?')} vs "
            f"{m.get('away_team', '?')} → {score} "
            f"(consenso {int(float(item.get('consensus_score', 0)) * 100)}%)"
        )
    lines.append("")
    lines.append("Tocá «Ingresar resultado» en el mensaje o /resultado_editar HOME AWAY")
    return "\n".join(lines)


def _list_published() -> str:
    from boto3.dynamodb.conditions import Attr

    from src.dao.dynamo.table import get_table

    table = get_table()
    items: list[dict[str, Any]] = []
    scan_kwargs: dict[str, Any] = {
        "FilterExpression": Attr("sort_key").eq("RESULT") & Attr("published_at").exists(),
        "ProjectionExpression": "match_id, publish_version, home_goals_ft, away_goals_ft, published_at",
    }
    while True:
        resp = table.scan(**scan_kwargs)
        items.extend(resp.get("Items", []))
        if not resp.get("LastEvaluatedKey") or len(items) >= 20:
            break
        scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    if not items:
        return "Aún no hay resultados publicados."
    items.sort(key=lambda x: str(x.get("published_at", "")), reverse=True)
    lines = ["🏁 Resultados publicados (recientes):", ""]
    mdao = MatchDAO()
    for item in items[:15]:
        mid = item.get("match_id", "")
        m = mdao.get_match(mid) or {}
        h = item.get("home_goals_ft", "?")
        a = item.get("away_goals_ft", "?")
        ver = item.get("publish_version", 1)
        lines.append(
            f"• v{ver} #{m.get('match_number', '?')} "
            f"{m.get('home_team', '?')} {h}-{a} {m.get('away_team', '?')}"
        )
    lines.append("")
    lines.append("Corregir: /resultado_editar HOME AWAY")
    return "\n".join(lines)

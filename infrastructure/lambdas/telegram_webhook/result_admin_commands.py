"""Comandos admin resultados — SPEC-2026-051."""
from __future__ import annotations

import logging
import re
from typing import Any

from src.dao.dynamo.match_dao import MatchDAO
from src.dao.dynamo.result_dao import ResultDAO
from src.models.match_result import MatchResult
from src.services.result_admin_notify import (
    edit_extended_keyboard,
    edit_score_keyboard,
    format_admin_pending_message,
    format_admin_preview_message,
    pending_result_keyboard,
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
_RESULTADO_PUBLICAR = re.compile(
    r"^/resultado_publicar(?:@[\w_]+)?\s+(\S+)\s+(\S+)\s*$",
    re.I,
)
_RESULTADO_EDITAR = re.compile(
    r"^/resultado_editar(?:@[\w_]+)?(?:\s+(\S+)\s+(\S+)(?:\s+(\d+)-(\d+))?)?\s*$",
    re.I,
)

_EXT_CODES = {
    "gb5": "goal_before_5min",
    "var": "var_used",
    "fk": "free_kick_goal",
    "psv": "penalty_saved",
    "psc": "penalty_scored",
}


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


def _get_draft(profile: dict[str, Any]) -> dict[str, Any] | None:
    draft = profile.get("result_admin_draft")
    return draft if isinstance(draft, dict) else None


def _save_draft(user_id: str, draft: dict[str, Any] | None) -> None:
    from src.dao.dynamo.user_dao import UserDAO

    if draft is None:
        UserDAO().update_profile(user_id, result_admin_draft=None)
    else:
        UserDAO().update_profile(user_id, result_admin_draft=draft)


def _draft_to_result(draft: dict[str, Any], match: dict[str, Any]) -> MatchResult:
    return MatchResult(
        home_goals=int(draft.get("home_goals", 0)),
        away_goals=int(draft.get("away_goals", 0)),
        phase=match.get("phase", "GROUP"),
        mvp_name=draft.get("mvp_name"),
        red_cards=int(draft.get("red_cards", 0)),
        goal_before_5min=draft.get("goal_before_5min"),
        var_used=draft.get("var_used"),
        free_kick_goal=draft.get("free_kick_goal"),
        penalty_saved=draft.get("penalty_saved"),
        penalty_scored=draft.get("penalty_scored"),
        source="web_search",
        match_id=match.get("match_id"),
    )


def _result_to_draft(result: MatchResult) -> dict[str, Any]:
    return {
        "home_goals": result.home_goals,
        "away_goals": result.away_goals,
        "mvp_name": result.mvp_name,
        "red_cards": result.red_cards,
        "goal_before_5min": result.goal_before_5min,
        "var_used": result.var_used,
        "free_kick_goal": result.free_kick_goal,
        "penalty_saved": result.penalty_saved,
        "penalty_scored": result.penalty_scored,
    }


def matches_result_admin_command(text: str) -> bool:
    stripped = (text or "").strip()
    return bool(
        _RESULTADO_PENDIENTES.match(stripped)
        or _RESULTADO_PUBLICADOS.match(stripped)
        or _RESULTADO_RECOLECTAR.match(stripped)
        or _RESULTADO_PUBLICAR.match(stripped)
        or _RESULTADO_EDITAR.match(stripped)
    )


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
        svc = ResultAdminService()
        cand = svc.propose_result(match["match_id"], force_notify=True)
        if not cand:
            return "No pude recolectar un borrador. Reintentá más tarde.", None
        return format_admin_pending_message(match, cand), pending_result_keyboard(match["match_id"])

    m = _RESULTADO_PUBLICAR.match(stripped)
    if m:
        match = _resolve_match((m.group(1), m.group(2)))
        if not match:
            return "No encontré ese partido.", None
        outcome = ResultAdminService().confirm_and_publish(match["match_id"], user_id)
        if not outcome.published:
            return f"No publiqué: {', '.join(outcome.errors) or 'sin candidato'}", None
        return (
            f"✅ Publicado v{outcome.publish_version}. "
            f"Notificados: {outcome.notified_users}. Scoring encolado.",
            None,
        )

    m = _RESULTADO_EDITAR.match(stripped)
    if m:
        home_t, away_t = m.group(1), m.group(2)
        if not home_t:
            return "Uso: /resultado_editar HOME AWAY [marcador]", None
        match = _resolve_match((home_t, away_t))
        if not match:
            return "No encontré ese partido.", None
        mid = match["match_id"]
        rdao = ResultDAO()
        base = ResultAdminService().get_candidate_result(mid)
        if not base:
            published = rdao.get_result(mid)
            base = published
        if not base:
            return "Sin borrador ni resultado publicado para editar.", None
        draft = _result_to_draft(base)
        if m.group(3) is not None and m.group(4) is not None:
            draft["home_goals"] = int(m.group(3))
            draft["away_goals"] = int(m.group(4))
        draft["match_id"] = mid
        _save_draft(user_id, draft)
        return (
            f"Editá el marcador del partido #{match.get('match_number')} "
            f"({match['home_team']} vs {match['away_team']}):",
            edit_score_keyboard(mid),
        )

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
    # res:pub:confirm:<uuid>
    if len(parts) >= 4 and parts[1] == "pub":
        action = parts[2]
        match_id = parts[3]
        match = MatchDAO().get_match(match_id)
        if not match:
            return "Partido no encontrado.", None

        if action == "confirm":
            outcome = svc.confirm_and_publish(match_id, user_id)
            if not outcome.published:
                return f"No publiqué: {', '.join(outcome.errors)}", None
            return (
                f"✅ Publicado. Usuarios notificados: {outcome.notified_users}.",
                None,
            )
        if action == "reject":
            svc.reject_candidate(match_id, user_id)
            return "Borrador rechazado. Podés re-recolectar más tarde.", None
        if action == "recolect":
            cand = svc.propose_result(match_id, force_notify=True)
            if not cand:
                return "No pude recolectar de nuevo.", None
            return (
                format_admin_pending_message(match, cand),
                pending_result_keyboard(match_id),
            )
        if action == "edit":
            base = svc.get_candidate_result(match_id) or ResultDAO().get_result(match_id)
            if not base:
                return "Sin datos para editar.", None
            draft = _result_to_draft(base)
            draft["match_id"] = match_id
            _save_draft(user_id, draft)
            return "Elegí el marcador:", edit_score_keyboard(match_id)
        if action == "editext":
            return "Ajustá las extendidas:", edit_extended_keyboard(match_id)
        if action == "preview":
            from src.dao.dynamo.user_dao import UserDAO

            profile = UserDAO().get_profile(user_id) or {}
            draft = _get_draft(profile)
            if not draft or draft.get("match_id") != match_id:
                base = svc.get_candidate_result(match_id)
                if not base:
                    return "Primero editá el marcador.", None
                result = base
            else:
                result = _draft_to_result(draft, match)
            svc.update_candidate_from_admin(match_id, result, user_id)
            republish = ResultDAO().has_scores(match_id)
            preview = format_admin_preview_message(match, result, republish=republish)
            kb = {
                "inline_keyboard": [
                    [
                        {
                            "text": "✅ Publicar ahora",
                            "callback_data": f"res:pub:publish:{match_id}",
                        },
                    ],
                    [
                        {
                            "text": "← Editar marcador",
                            "callback_data": f"res:pub:edit:{match_id}",
                        },
                    ],
                ]
            }
            return preview, kb
        if action == "publish":
            from src.dao.dynamo.user_dao import UserDAO

            profile = UserDAO().get_profile(user_id) or {}
            draft = _get_draft(profile)
            result = svc.get_candidate_result(match_id)
            if draft and draft.get("match_id") == match_id:
                result = _draft_to_result(draft, match)
            if not result:
                return "Sin resultado para publicar.", None
            if ResultDAO().has_scores(match_id):
                outcome = svc.republish_result(match_id, result, user_id)
            else:
                svc.update_candidate_from_admin(match_id, result, user_id)
                outcome = svc.confirm_and_publish(match_id, user_id)
            _save_draft(user_id, None)
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

    # res:scr:<uuid>:<h>:<a>
    if len(parts) >= 5 and parts[1] == "scr":
        match_id = parts[2]
        match = MatchDAO().get_match(match_id)
        if not match:
            return "Partido no encontrado.", None
        from src.dao.dynamo.user_dao import UserDAO

        profile = UserDAO().get_profile(user_id) or {}
        draft = _get_draft(profile) or {"match_id": match_id}
        draft["match_id"] = match_id
        draft["home_goals"] = int(parts[3])
        draft["away_goals"] = int(parts[4])
        _save_draft(user_id, draft)
        return (
            f"Marcador {parts[3]}-{parts[4]}. Ajustá extendidas:",
            edit_extended_keyboard(match_id),
        )

    # res:ext:<uuid>:<code>:<val>
    if len(parts) >= 5 and parts[1] == "ext":
        match_id = parts[2]
        field = _EXT_CODES.get(parts[3])
        if not field:
            return "Campo inválido.", None
        val_raw = parts[4]
        if val_raw == "n":
            parsed_val = None
        else:
            parsed_val = val_raw == "1"
        from src.dao.dynamo.user_dao import UserDAO

        profile = UserDAO().get_profile(user_id) or {}
        draft = _get_draft(profile) or {"match_id": match_id, "home_goals": 0, "away_goals": 0}
        draft["match_id"] = match_id
        draft[field] = parsed_val
        _save_draft(user_id, draft)
        return "Extendida actualizada.", edit_extended_keyboard(match_id)

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
    lines.append("Usá los botones del mensaje o /resultado_publicar HOME AWAY")
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
        return "Aún no hay resultados publicados con metadata SPEC-051."
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

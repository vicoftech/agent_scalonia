"""Orquestador diario de briefs — SPEC-2026-045."""
from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

from src.dao.dynamo.brief_dao import MatchBriefDAO, TeamBriefDAO
from src.dao.dynamo.job_ctrl_dao import JobCtrlDAO
from src.dao.dynamo.match_dao import MatchDAO
from src.fixtures.mundial2026_groups import all_world_cup_team_codes
from src.services.brief_agent import make_invoke_agent
from src.services.brief_json import (
    extract_json_object,
    normalize_match_brief,
    normalize_team_brief,
)
from src.services.brief_generation import (
    fetch_team_context,
    match_brief_agent_prompt,
    team_brief_agent_prompt,
)
from src.services.match_brief_service import should_regenerate_match_brief
from src.services.team_flags import resolve_team_display_name

logger = logging.getLogger(__name__)

DISPLAY_TZ = timezone(timedelta(hours=-3))


def _today_job_date() -> str:
    return datetime.now(DISPLAY_TZ).date().isoformat()


def _agent_session_id(prefix: str) -> str:
    """AgentCore exige runtimeSessionId con longitud >= 33."""
    sid = f"{prefix}-{uuid.uuid4().hex}"
    if len(sid) < 33:
        sid = f"{prefix}-{uuid.uuid4().hex}-{uuid.uuid4().hex[:8]}"
    return sid[:64]


def _enabled() -> bool:
    return os.environ.get("ENABLE_DAILY_BRIEFS", "true").lower() in ("1", "true", "yes")


class BriefOrchestrator:
    def __init__(
        self,
        *,
        invoke_agent: Callable[[str, str], str] | None = None,
        team_briefs: TeamBriefDAO | None = None,
        match_briefs: MatchBriefDAO | None = None,
        matches: MatchDAO | None = None,
        job_ctrl: JobCtrlDAO | None = None,
        concurrency: int | None = None,
        overwrite: bool = False,
    ):
        brief_table = os.environ.get("BRIEF_TABLE")
        self._team_briefs = team_briefs or TeamBriefDAO(brief_table)
        self._match_briefs = match_briefs or MatchBriefDAO(brief_table)
        self._matches = matches or MatchDAO()
        self._job_ctrl = job_ctrl or JobCtrlDAO(brief_table)
        self._invoke = make_invoke_agent(invoke_agent)
        self._concurrency = concurrency or int(os.environ.get("BRIEF_CONCURRENCY", "5"))
        self._overwrite = overwrite
        self._teams_ok: set[str] = set()
        self._strict_team_run = True

    def run(
        self,
        *,
        team_filter: str | None = None,
        match_filter: str | None = None,
        matches_only: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        if not _enabled():
            return {"status": "SKIPPED", "reason": "ENABLE_DAILY_BRIEFS=false"}

        run_date = _today_job_date()
        if (
            not force
            and not self._overwrite
            and not team_filter
            and not match_filter
            and not matches_only
            and self._job_ctrl.is_processed("daily_team_brief", run_date)
        ):
            return {"status": "SKIPPED", "reason": "already_processed", "run_date": run_date}

        if matches_only or (match_filter and not team_filter):
            self._strict_team_run = False
            team_stats = {"generated": 0, "failed": 0, "skipped_phase": True}
        else:
            teams = [team_filter.upper()] if team_filter else all_world_cup_team_codes()
            team_stats = self._run_team_phase(teams)

        match_stats = self._run_match_phase(match_filter=match_filter)

        if not team_filter and not match_filter and not matches_only:
            self._job_ctrl.mark_processed(
                "daily_team_brief",
                run_date,
                meta={"teams_ok": len(self._teams_ok), **team_stats},
            )
            self._job_ctrl.mark_processed(
                "daily_match_brief",
                run_date,
                meta=match_stats,
            )

        return {
            "status": "OK",
            "run_date": run_date,
            "teams": team_stats,
            "matches": match_stats,
        }

    def _run_team_phase(self, teams: list[str]) -> dict[str, int]:
        ok = failed = 0
        with ThreadPoolExecutor(max_workers=self._concurrency) as pool:
            futures = {pool.submit(self._generate_team, code): code for code in teams}
            for fut in as_completed(futures):
                code = futures[fut]
                try:
                    if fut.result():
                        self._teams_ok.add(code)
                        ok += 1
                    else:
                        failed += 1
                except Exception:
                    logger.exception("team brief failed code=%s", code)
                    failed += 1
        logger.info("BriefsGenerated teams_ok=%s teams_failed=%s", ok, failed)
        return {"generated": ok, "failed": failed}

    def _generate_team(self, team_code: str) -> bool:
        code = team_code.strip().upper()
        name = resolve_team_display_name(code)
        session_id = _agent_session_id(f"brief-team-{code}")
        context = fetch_team_context(code)
        prompt = team_brief_agent_prompt(code, context=context)
        try:
            raw = self._invoke(prompt, session_id)
            data = extract_json_object(raw)
            normalized = normalize_team_brief(data, team_code=code, team_name=name)
            self._team_briefs.put_current(code, normalized)
            return True
        except Exception:
            logger.exception("generate_team_brief failed team=%s", code)
            return False

    def _run_match_phase(self, *, match_filter: str | None) -> dict[str, int]:
        generated = skipped = frozen = failed = 0
        matches = self._matches.list_matches()
        if match_filter:
            matches = [m for m in matches if m.get("match_id") == match_filter]

        workers = 1 if match_filter else min(3, self._concurrency)

        def _tally(result: str) -> None:
            nonlocal generated, skipped, frozen, failed
            if result == "generated":
                generated += 1
            elif result == "frozen":
                frozen += 1
            elif result == "failed":
                failed += 1
            else:
                skipped += 1

        if workers <= 1:
            for match in matches:
                _tally(self._process_match(match))
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(self._process_match, m): m for m in matches}
                for fut in as_completed(futures):
                    try:
                        _tally(fut.result())
                    except Exception:
                        mid = futures[fut].get("match_id", "")[:8]
                        logger.exception("match brief worker failed match=%s", mid)
                        failed += 1
        logger.info(
            "match briefs generated=%s skipped=%s frozen=%s failed=%s",
            generated,
            skipped,
            frozen,
            failed,
        )
        return {
            "generated": generated,
            "skipped": skipped,
            "frozen": frozen,
            "failed": failed,
        }

    def _process_match(self, match: dict[str, Any]) -> str:
        match_id = str(match.get("match_id", ""))
        if not should_regenerate_match_brief(match):
            logger.debug(
                "skip match brief %s status=%s phase=%s",
                match_id[:8],
                match.get("status"),
                match.get("phase"),
            )
            return "skipped"

        home = (match.get("home_team") or "").upper()
        away = (match.get("away_team") or "").upper()
        home_brief = self._team_briefs.get_current(home)
        away_brief = self._team_briefs.get_current(away)

        if self._strict_team_run:
            if home not in self._teams_ok or away not in self._teams_ok:
                logger.info(
                    "skip match brief %s — team brief missing from this run",
                    match_id[:8],
                )
                return "skipped"
        if not home_brief or not away_brief:
            return "skipped"

        last_raw = ""
        for attempt in range(2):
            session_id = _agent_session_id(
                f"brief-match-{match_id[:12]}-a{attempt}"
            )
            try:
                raw = self._invoke(
                    match_brief_agent_prompt(match, home_brief, away_brief),
                    session_id,
                )
                last_raw = raw
                data = extract_json_object(raw)
                normalized = normalize_match_brief(data, match_id=match_id, match=match)
                line = normalized.get("ia_prediction_line") or ""
                if not line.startswith("Dado el análisis previo me inclino por"):
                    home_name = resolve_team_display_name(home)
                    normalized["ia_prediction_line"] = (
                        f"Dado el análisis previo me inclino por {home_name} "
                        "como ganador del partido."
                    )
                normalized["team_brief_refs"] = {
                    "home": f"TEAM_BRIEF#{home}",
                    "away": f"TEAM_BRIEF#{away}",
                    "generated_at": home_brief.get("generated_at"),
                }
                normalized["brief_frozen"] = False
                self._match_briefs.put_current(match_id, normalized)
                return "generated"
            except Exception as exc:
                logger.warning(
                    "generate_match_brief attempt=%s match=%s err=%s preview=%s",
                    attempt + 1,
                    match_id[:8],
                    exc,
                    (last_raw or "")[:240].replace("\n", " "),
                )
        logger.exception("generate_match_brief failed match=%s", match_id[:8])
        return "failed"


def run_daily_brief_job(
    *,
    team: str | None = None,
    match_id: str | None = None,
    matches_only: bool = False,
    force: bool = False,
    invoke_agent: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    return BriefOrchestrator(invoke_agent=invoke_agent, overwrite=force).run(
        team_filter=team,
        match_filter=match_id,
        matches_only=matches_only,
        force=force,
    )

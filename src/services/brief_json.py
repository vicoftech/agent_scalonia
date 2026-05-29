"""Parseo y validación JSON de briefs (SPEC-2026-045)."""
from __future__ import annotations

import json
import re
from typing import Any

MAX_BRIEF_MARKDOWN = 2500


def extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty agent response")
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fence:
        raw = fence.group(1)
    elif "```json" in raw:
        start = raw.find("```json")
        end = raw.rfind("```")
        if start >= 0 and end > start:
            raw = raw[start + 7 : end].strip()
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    pos = 0
    while pos < len(raw):
        while pos < len(raw) and raw[pos].isspace():
            pos += 1
        if pos >= len(raw) or raw[pos] != "{":
            break
        try:
            obj, idx = decoder.raw_decode(raw, pos)
            if isinstance(obj, dict) and (
                "team_code" in obj or "match_id" in obj or "brief_markdown" in obj
            ):
                return obj
            pos += idx
        except json.JSONDecodeError:
            pos = raw.find("{", pos + 1)
            if pos == -1:
                break
    raise ValueError("no JSON object found in agent response")


def truncate_markdown(text: str, *, limit: int = MAX_BRIEF_MARKDOWN) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 3].rstrip() + "..."


def normalize_team_brief(data: dict[str, Any], *, team_code: str, team_name: str) -> dict[str, Any]:
    roster = data.get("roster") or []
    if not isinstance(roster, list):
        roster = []
    return {
        "team_code": (data.get("team_code") or team_code).strip().upper(),
        "team_name": data.get("team_name") or team_name,
        "brief_markdown": truncate_markdown(str(data.get("brief_markdown") or "")),
        "brief_sections": data.get("brief_sections") if isinstance(data.get("brief_sections"), dict) else {},
        "roster": roster,
        "recent_record": str(data.get("recent_record") or ""),
        "kb_chunks_used": int(data.get("kb_chunks_used") or 0),
        "web_queries_used": data.get("web_queries_used") if isinstance(data.get("web_queries_used"), list) else [],
        "roster_completeness": data.get("roster_completeness") or "FULL",
    }


def normalize_match_brief(
    data: dict[str, Any],
    *,
    match_id: str,
    match: dict[str, Any],
) -> dict[str, Any]:
    def _bullets(key: str) -> list[str]:
        val = data.get(key) or []
        if isinstance(val, str):
            return [val.strip()] if val.strip() else []
        return [str(x).strip() for x in val if str(x).strip()]

    return {
        "match_id": match_id,
        "home_team": match.get("home_team"),
        "away_team": match.get("away_team"),
        "kickoff_utc": match.get("kickoff_utc"),
        "home_strengths": _bullets("home_strengths"),
        "home_weaknesses": _bullets("home_weaknesses"),
        "away_strengths": _bullets("away_strengths"),
        "away_weaknesses": _bullets("away_weaknesses"),
        "ia_prediction_line": str(data.get("ia_prediction_line") or "").strip(),
        "ia_prediction_rationale": str(data.get("ia_prediction_rationale") or "").strip(),
        "brief_markdown": truncate_markdown(str(data.get("brief_markdown") or "")),
        "match_status_at_generation": (match.get("status") or "SCHEDULED").upper(),
        "brief_frozen": False,
    }

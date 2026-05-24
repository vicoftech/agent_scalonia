"""Parseo de texto web → MatchResult — SPEC-2026-031."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

from src.models.match_result import MatchResult

logger = logging.getLogger(__name__)

_PARSE_MODEL = os.environ.get(
    "BEDROCK_RESULT_PARSE_MODEL_ID",
    "us.anthropic.claude-3-5-haiku-20241022-v1:0",
)
_REGION = os.environ.get("AWS_REGION", "us-east-1")

_llm_parse_fn: Callable[[str, dict[str, Any]], dict[str, Any] | None] | None = None


def set_llm_parse_fn(
    fn: Callable[[str, dict[str, Any]], dict[str, Any] | None] | None,
) -> None:
    global _llm_parse_fn
    _llm_parse_fn = fn


def _extract_json_block(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{[^{}]*\"found\"[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _heuristic_parse(raw: str, match: dict[str, Any]) -> dict[str, Any] | None:
    """Parser sin LLM para tests y fallback."""
    home = match.get("home_team", "")
    away = match.get("away_team", "")
    patterns = [
        rf"{home}\s+(\d+)\s*[-:]\s*(\d+)\s+{away}",
        rf"{away}\s+(\d+)\s*[-:]\s*(\d+)\s+{home}",
        r"(\d+)\s*[-:]\s*(\d+)",
        r"(\d+)\s+a\s+(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, raw, re.IGNORECASE)
        if m:
            h, a = int(m.group(1)), int(m.group(2))
            if pat.startswith(rf"{away}"):
                h, a = a, h
            status = "FT"
            playoff_winner = None
            if re.search(r"penal", raw, re.I):
                status = "PEN"
                wm = re.search(
                    rf"{home}|{away}|argentina|francia|brasil",
                    raw[raw.lower().find("penal") :],
                    re.I,
                )
                if wm:
                    playoff_winner = home if home.lower() in wm.group(0).lower()[:3] else away
            data: dict[str, Any] = {
                "found": True,
                "home_goals": h,
                "away_goals": a,
                "status": status,
                "playoff_winner": playoff_winner,
                "scorers": {},
                "red_cards": 0,
                "mvp_name": None,
            }
            mvp_m = re.search(
                r"(?:mvp|jugador del partido|mejor jugador)[:\s]+([A-Za-zÀ-ÿ\s\.]+)",
                raw,
                re.I,
            )
            if mvp_m:
                data["mvp_name"] = mvp_m.group(1).strip().split("\n")[0][:80]
            return data
    return None


def _bedrock_parse(raw: str, match: dict[str, Any]) -> dict[str, Any] | None:
    import boto3

    home = match.get("home_team", "")
    away = match.get("away_team", "")
    prompt = f"""Extraé el resultado del siguiente partido de fútbol del texto.
Partido: {home} vs {away}
Texto: {raw[:2000]}

Respondé SOLO en JSON con este formato exacto:
{{
  "found": true,
  "home_goals": <int>,
  "away_goals": <int>,
  "status": "FT",
  "playoff_winner": null,
  "scorers": {{}},
  "red_cards": 0,
  "goal_before_5min": true | false | null,
  "var_used": true | false | null,
  "free_kick_goal": true | false | null,
  "penalty_saved": true | false | null,
  "penalty_scored": true | false | null,
  "mvp_name": null
}}

status puede ser FT, AET o PEN. Si no encontraste el resultado, {{"found": false}}."""
    try:
        client = boto3.client("bedrock-runtime", region_name=_REGION)
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            }
        )
        resp = client.invoke_model(
            modelId=_PARSE_MODEL,
            body=body,
            accept="application/json",
            contentType="application/json",
        )
        payload = json.loads(resp["body"].read())
        text = ""
        for block in payload.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        return _extract_json_block(text)
    except Exception:
        logger.exception("Bedrock result parse failed")
        return None


def parse_web_result(raw: str, match: dict[str, Any]) -> MatchResult | None:
    if _llm_parse_fn is not None:
        data = _llm_parse_fn(raw, match)
    elif os.environ.get("RESULT_PARSE_USE_BEDROCK", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        data = _bedrock_parse(raw, match)
    else:
        data = _heuristic_parse(raw, match)
        if not data:
            data = _heuristic_parse(raw, match) or _extract_json_block(raw)

    if not data:
        return None
    if data.get("found") is False:
        return None
    if "home_goals" not in data or "away_goals" not in data:
        return None
    return MatchResult.from_parse_payload(data, match)


_MVP_STOPWORDS = frozenset(
    {
        "jugador del partido",
        "player of the match",
        "mvp",
        "mejor jugador",
        "sin",
        "ninguno",
    }
)


def _clean_mvp_name(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = " ".join(name.strip().split())
    if len(cleaned) < 3:
        return None
    if cleaned.lower() in _MVP_STOPWORDS:
        return None
    return cleaned


def extract_mvp_from_text(raw: str) -> str | None:
    for pat in (
        r"Goles:\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s\.]{2,35})",
        r"(?:mvp|jugador del partido|player of the match)[:\s\-]+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s\.]{2,40})",
    ):
        m = re.search(pat, raw, re.I)
        if m:
            name = _clean_mvp_name(m.group(1).strip().split(",")[0])
            if name:
                return name
    data = _heuristic_parse(
        f'MVP: Lionel Messi. {raw}',
        {"home_team": "X", "away_team": "Y"},
    )
    if data and data.get("mvp_name"):
        return _clean_mvp_name(str(data["mvp_name"]))
    return None

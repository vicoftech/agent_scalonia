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


def _extract_red_card_count(raw: str) -> int | None:
    """Cuenta expulsiones si el texto lo explicita o repite rojas directas."""
    lower = raw.lower()
    explicit = (
        re.search(
            r"(?:three|tres|3)\s+(?:straight\s+)?(?:red\s+cards?|tarjetas?\s+rojas?|rojas?)",
            lower,
        )
        or re.search(r"(?:two|dos|2)\s+(?:straight\s+)?(?:red\s+cards?|tarjetas?\s+rojas?)", lower)
        or re.search(r"(?:one|una?|1)\s+(?:straight\s+)?(?:red\s+cards?|tarjetas?\s+rojas?)", lower)
    )
    if explicit:
        word = explicit.group(0)
        if re.search(r"\bthree\b|\btres\b|\b3\b", word):
            return 3
        if re.search(r"\btwo\b|\bdos\b|\b2\b", word):
            return 2
        return 1
    # "three red cards" como frase suelta
    if re.search(r"\bthree\s+red\s+cards?\b|\btres\s+tarjetas?\s+rojas?\b", lower):
        return 3
    # Conteo por eventos puntuales (cap a 5 para evitar ruido de tablas)
    events = len(
        re.findall(
            r"(?:straight\s+)?red\s+card|tarjeta\s+roja|sent\s+off|expulsad[oa]|"
            r"##\s*\d+\+?\d*'\s*-\s*red\s+card",
            raw,
            re.I,
        )
    )
    if events >= 3:
        return min(events, 5)
    if events > 0:
        return events
    if re.search(r"\bvar\b.*\bred\s+card\b|\bred\s+card\b.*\bvar\b", raw, re.I):
        return max(events, 1)
    return None


def _extract_bool_signal(
    raw: str,
    *,
    positive: tuple[str, ...],
    negative: tuple[str, ...],
) -> bool | None:
    lower = raw.lower()
    if any(re.search(p, lower) for p in negative):
        return False
    if any(re.search(p, lower) for p in positive):
        return True
    return None


def _extract_goal_before_5min(raw: str) -> bool | None:
    lower = raw.lower()
    if re.search(
        r"sin\s+goles?\s+antes\s+del\s+minuto\s+5|no\s+goal\s+before\s+(?:the\s+)?5",
        lower,
    ):
        return False
    if re.search(r"gol\s+antes\s+del\s+5|goal\s+before\s+(?:the\s+)?5", lower):
        return True
    if re.search(r"\bninth\s+minute\b|\bnoveno\s+minuto\b|\bin\s+the\s+ninth\s+minute\b", lower):
        return False
    # Primer gol del partido / torneo
    first_goal = re.search(
        r"(?:first\s+goal|primer\s+gol|primer gol del).{0,80}?"
        r"(?:(\d+)(?:th|º|°)?\s*minute|minuto\s+(\d+)|(\d+)\s*'|in\s+the\s+(\w+)\s+minute)",
        lower,
        re.I | re.DOTALL,
    )
    if first_goal:
        minute = next((int(g) for g in first_goal.groups() if g and g.isdigit()), None)
        if minute is None:
            word = next((g for g in first_goal.groups() if g and not g.isdigit()), None)
            ordinals = {
                "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
                "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
            }
            if word:
                minute = ordinals.get(word.lower())
        if minute is not None:
            return minute < 5
    # Cualquier gol explícito en minuto < 5
    early = re.findall(r"(?:^|[^\d])([1-4])\s*'|\bminuto\s+([1-4])\b", lower)
    if early and re.search(r"\bgoal\b|\bgol\b|scored", lower):
        return True
    # Gol conocido >= 5' implica que no hubo antes del 5'
    late = re.search(
        r"(?:ninth|noveno|(\d{2,}))\s*(?:th\s*)?minute|minuto\s+(\d+)|(\d+)\s*'\s*.*\b(?:goal|gol|scored)",
        lower,
        re.I,
    )
    if late:
        minute = next((int(g) for g in late.groups() if g), None)
        if minute is not None and minute >= 5:
            return False
    return None


def _extract_var_used(raw: str) -> bool | None:
    return _extract_bool_signal(
        raw,
        positive=(
            r"\bvar\s+review\b",
            r"\bvar\b.{0,40}\bred\s+card\b",
            r"following\s+a\s+var\s+review",
            r"intervención\s+del\s+var\b",
            r"hubo\s+intervención\s+del\s+var\b",
            r"revisión\s+var\b",
            r"var\s+screen\b",
            r"var\s+is\s+considering\b",
        ),
        negative=(
            r"sin\s+intervención\s+del\s+var\b",
            r"no\s+var\b",
        ),
    )


def _extract_penalty_kick(raw: str, kind: str) -> bool | None:
    """Penal durante el partido (no definición por penales)."""
    lower = raw.lower()
    neg = (
        r"sin\s+penal",
        r"no\s+penalty",
        r"almost\s+a\s+penalty",
        r"casi\s+un\s+penal",
        r"what\s+was\s+almost\s+a\s+penalty",
    )
    if any(re.search(p, lower) for p in neg):
        return False
    if kind == "scored":
        pos = (
            r"penalty\s+scored",
            r"penal\s+convertido",
            r"converted\s+(?:the\s+)?penalty",
            r"scored\s+(?:a\s+)?penalty",
        )
    else:
        pos = (
            r"penalty\s+saved",
            r"penal\s+atajado",
            r"saved\s+(?:the\s+)?penalty",
        )
    return _extract_bool_signal(raw, positive=pos, negative=neg)


def _extract_free_kick_goal(raw: str) -> bool | None:
    return _extract_bool_signal(
        raw,
        positive=(r"gol\s+de\s+tiro\s+libre", r"free\s+kick\s+goal", r"goal\s+from\s+(?:a\s+)?free\s+kick"),
        negative=(r"sin\s+gol\s+de\s+tiro\s+libre", r"no\s+free\s+kick\s+goal"),
    )


def _match_decided_on_penalties(raw: str) -> bool:
    """Eliminatorias definidas por penales — no confundir con casi-penal o VAR."""
    lower = raw.lower()
    if re.search(r"almost\s+a\s+penalty|casi\s+un\s+penal", lower):
        return False
    return bool(
        re.search(
            r"(?:won|gana|ganó|defeat).{0,40}penalt(?:y|ies)|"
            r"(?:after|tras)\s+penalt(?:y|ies)|"
            r"decided\s+on\s+penalt(?:y|ies)|"
            r"\bpenalt(?:y|ies)\s+shootout\b",
            lower,
        )
    )


def _enrich_heuristic_extended(data: dict[str, Any], raw: str) -> None:
    reds = _extract_red_card_count(raw)
    if reds is not None:
        data["red_cards"] = reds
    gb5 = _extract_goal_before_5min(raw)
    if gb5 is not None:
        data["goal_before_5min"] = gb5
    var_u = _extract_var_used(raw)
    if var_u is not None:
        data["var_used"] = var_u
    fk = _extract_free_kick_goal(raw)
    if fk is not None:
        data["free_kick_goal"] = fk
    ps = _extract_penalty_kick(raw, "scored")
    p_saved = _extract_penalty_kick(raw, "saved")
    if ps is not None:
        data["penalty_scored"] = ps
    if p_saved is not None:
        data["penalty_saved"] = p_saved
    # Sin evidencia de penal durante el 90' en fase de grupos → No
    if ps is None and p_saved is None and data.get("status") == "FT":
        has_penalty_event = bool(
            re.search(
                r"penalty\s+(?:scored|saved|converted|missed|awarded)|"
                r"penal\s+(?:convertido|atajado|errado|otorgado)|"
                r"scored\s+(?:a\s+)?penalty|saved\s+(?:the\s+)?penalty",
                raw,
                re.I,
            )
        )
        if not has_penalty_event:
            data["penalty_scored"] = False
            data["penalty_saved"] = False


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
            if _match_decided_on_penalties(raw):
                status = "PEN"
                wm = re.search(
                    rf"{home}|{away}|argentina|francia|brasil|mexico|méxico|south africa|sudáfrica",
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
            _enrich_heuristic_extended(data, raw)
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


_IN_PLAY_PATTERNS = (
    r"\ben\s+vivo\b",
    r"\blive\b",
    r"\bparcial\b",
    r"\bhalf\s*time\b",
    r"\bprimer\s+tiempo\b",
    r"\bsegundo\s+tiempo\b",
    r"\bminuto\s+\d{1,2}\b",
    r"\b\d{1,2}\s*'\s*(?:de\s+juego|played)\b",
    r"\bstill\s+playing\b",
    r"\bno\s+ha\s+terminado\b",
    r"\bmatch\s+in\s+progress\b",
)


def detect_in_play_signals(raw: str) -> bool:
    """True si el texto sugiere partido aún en curso (SPEC-051 AC-08)."""
    if not raw:
        return False
    lower = raw.lower()
    return any(re.search(p, lower) for p in _IN_PLAY_PATTERNS)


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

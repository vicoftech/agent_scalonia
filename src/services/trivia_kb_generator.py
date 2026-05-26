"""Genera preguntas de trivia pre-partido desde KB (+ Bedrock) — SPEC-025."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from src.services.trivia_question_bank import (
    is_meta_source_question,
    pick_curated_for_match_strict,
    question_fingerprint,
)

logger = logging.getLogger(__name__)

_BEDROCK_MODEL = os.environ.get(
    "BEDROCK_TRIVIA_MODEL_ID",
    "us.anthropic.claude-sonnet-4-6",
)
_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Nombres para búsqueda en KB (códigos FIFA solos suelen dar poco contexto)
FIFA_DISPLAY_NAMES: dict[str, tuple[str, ...]] = {
    "MEX": ("México", "Mexico", "MEX"),
    "RSA": ("Sudáfrica", "South Africa", "RSA", "Bafana"),
    "ARG": ("Argentina", "ARG"),
    "BRA": ("Brasil", "Brazil", "BRA"),
    "USA": ("Estados Unidos", "United States", "USA"),
    "CAN": ("Canadá", "Canada", "CAN"),
    "FRA": ("Francia", "France", "FRA"),
    "GER": ("Alemania", "Germany", "GER"),
    "ESP": ("España", "Spain", "ESP"),
    "ENG": ("Inglaterra", "England", "ENG"),
    "POR": ("Portugal", "POR"),
    "NED": ("Países Bajos", "Netherlands", "NED"),
    "URU": ("Uruguay", "URU"),
    "COL": ("Colombia", "COL"),
    "JPN": ("Japón", "Japan", "JPN"),
    "KOR": ("Corea del Sur", "Korea Republic", "KOR"),
    "AUS": ("Australia", "AUS"),
    "MAR": ("Marruecos", "Morocco", "MAR"),
    "SEN": ("Senegal", "SEN"),
    "CRO": ("Croacia", "Croatia", "CRO"),
    "BEL": ("Bélgica", "Belgium", "BEL"),
    "SUI": ("Suiza", "Switzerland", "SUI"),
    "ECU": ("Ecuador", "ECU"),
    "IRN": ("Irán", "Iran", "IRN"),
    "KSA": ("Arabia Saudita", "Saudi Arabia", "KSA"),
    "QAT": ("Qatar", "QAT"),
    "NZL": ("Nueva Zelanda", "New Zealand", "NZL"),
}


def _team_labels(code: str) -> tuple[str, ...]:
    up = (code or "").strip().upper()
    return FIFA_DISPLAY_NAMES.get(up, (up,))


def _match_fixture_blurb(match: dict[str, Any]) -> str:
    home = match.get("home_team", "")
    away = match.get("away_team", "")
    home_names = ", ".join(_team_labels(home))
    away_names = ", ".join(_team_labels(away))
    parts = [
        f"Partido Copa Mundial 2026: {home} ({home_names}) vs {away} ({away_names})",
    ]
    if match.get("group_letter"):
        parts.append(f"Grupo {match['group_letter']}")
    if match.get("venue") or match.get("city"):
        parts.append(f"Sede: {match.get('venue', '')} {match.get('city', '')}".strip())
    if match.get("kickoff_utc"):
        parts.append(f"Kickoff UTC: {match['kickoff_utc']}")
    return ". ".join(parts)


def fetch_pre_match_kb_context(match: dict[str, Any]) -> str:
    """Contexto KB (y web si hace falta) para ambos equipos del partido."""
    from src.kb.resolve import resolve_kb_then_web

    home = (match.get("home_team") or "").strip()
    away = (match.get("away_team") or "").strip()
    if not home or not away:
        return ""

    home_names = _team_labels(home)
    away_names = _team_labels(away)
    group = match.get("group_letter") or ""
    fixture = _match_fixture_blurb(match)

    sections: list[str] = [f"### Partido\n{fixture}"]
    queries = (
        (
            home,
            f"{home_names[0]} selección nacional Copa Mundial 2026 "
            f"historial jugadores clasificación grupo {group}",
        ),
        (
            away,
            f"{away_names[0]} selección nacional Copa Mundial 2026 "
            f"historial jugadores clasificación grupo {group}",
        ),
        (
            "encuentro",
            f"{home_names[0]} vs {away_names[0]} Copa Mundial 2026 "
            f"grupo {group} enfrentamiento selecciones",
        ),
    )
    for label, query in queries:
        try:
            result = resolve_kb_then_web(query, max_results=8, enqueue_on_web=False)
            text = (result.kb_text or "").strip()
            if len(text) < 80 and result.tavily_configured and result.web_text:
                text = (result.web_text or "").strip()
            if text:
                sections.append(f"### {label}\n{text[:2000]}")
                logger.info(
                    "pre_match kb label=%s kb_chunks=%s web=%s",
                    label,
                    result.kb_chunk_count,
                    result.web_fallback_used,
                )
        except Exception:
            logger.exception("pre_match kb fetch failed label=%s", label)

    return "\n\n".join(sections)[:6000]


def _question_references_match(question: str, home: str, away: str) -> bool:
    """La pregunta debe nombrar explícitamente a ambos equipos (no solo en opciones)."""
    q = question.upper()
    home_hit = any(term.upper() in q for term in _team_labels(home))
    away_hit = any(term.upper() in q for term in _team_labels(away))
    return home_hit and away_hit


def _extract_json_block(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def generate_question_from_kb(
    match: dict[str, Any],
    context: str,
    *,
    level: str = "EXPERT",
    exclude_fingerprints: set[str] | None = None,
) -> dict[str, Any] | None:
    """Pregunta verificable basada en contexto KB; None si no se pudo generar."""
    import boto3

    home = match.get("home_team", "")
    away = match.get("away_team", "")
    home_label = _team_labels(home)[0]
    away_label = _team_labels(away)[0]
    exclude = exclude_fingerprints or set()
    fixture = _match_fixture_blurb(match)

    prompt = f"""Sos un editor de trivia de Copa Mundial 2026.
Generá UNA pregunta de opción múltiple nivel {level} EXCLUSIVAMENTE sobre el partido:
{fixture}

Reglas estrictas:
- La pregunta DEBE mencionar a {home_label} y a {away_label} (o {home} y {away}).
- Debe ser sobre historial, jugadores, DT, grupo o datos del contexto de ESE cruce (no otro mundial genérico).
- Usá SOLO hechos del contexto (no inventes).
- 4 opciones A, B, C, D; exactamente una correcta en "correct".
- Sin referencias a knowledge base, Tavily ni Wikipedia.

Contexto:
{context[:4500]}

Respondé SOLO JSON:
{{"question": "...", "options": {{"A":"...","B":"...","C":"...","D":"..."}}, "correct": "A"}}"""

    try:
        client = boto3.client("bedrock-runtime", region_name=_REGION)
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 600,
                "temperature": 0.2,
                "messages": [{"role": "user", "content": prompt}],
            }
        )
        resp = client.invoke_model(
            modelId=_BEDROCK_MODEL,
            body=body,
            accept="application/json",
            contentType="application/json",
        )
        payload = json.loads(resp["body"].read())
        raw = ""
        for block in payload.get("content", []):
            if block.get("type") == "text":
                raw += block.get("text", "")
        data = _extract_json_block(raw)
        if not data:
            return None
        question = str(data.get("question") or "").strip()
        options = data.get("options") or {}
        correct = str(data.get("correct") or "").upper().strip()
        if not question or correct not in ("A", "B", "C", "D"):
            return None
        opts = {k: str(options.get(k, "")).strip() for k in ("A", "B", "C", "D")}
        if not all(opts.values()):
            return None
        if is_meta_source_question(question, opts):
            return None
        if not _question_references_match(question, home, away):
            logger.warning("Bedrock trivia rejected: no menciona ambos equipos")
            return None
        fp = question_fingerprint(question)
        if fp in exclude:
            return None
        return {
            "question": question,
            "options": opts,
            "correct": correct,
            "level": level,
            "topic": "pre_partido",
            "question_fp": fp,
            "source": "kb_bedrock",
        }
    except Exception:
        logger.exception("Bedrock trivia generation failed")
        return None


def _template_from_match_metadata(match: dict[str, Any]) -> dict[str, Any]:
    """Último recurso: pregunta anclada al fixture (sin KB)."""
    home = match.get("home_team", "")
    away = match.get("away_team", "")
    g = match.get("group_letter") or "?"
    question = (
        f"En el partido de grupo {g} entre {_team_labels(home)[0]} y "
        f"{_team_labels(away)[0]} en el Mundial 2026, ¿cuál es el código FIFA del local?"
    )
    return {
        "question": question,
        "options": {"A": home, "B": away, "C": "EMP", "D": "N/A"},
        "correct": "A",
        "level": "EXPERT",
        "topic": "pre_partido",
        "question_fp": question_fingerprint(question),
        "source": "fixture_template",
    }


def generate_pre_match_question(
    match: dict[str, Any],
    *,
    level: str = "EXPERT",
    exclude_fingerprints: set[str] | None = None,
) -> dict[str, Any]:
    """KB → Bedrock; fallback curado estricto; último recurso metadata del partido."""
    exclude = set(exclude_fingerprints or ())
    home = match.get("home_team", "")
    away = match.get("away_team", "")

    context = fetch_pre_match_kb_context(match)
    if len(context) >= 80:
        generated = generate_question_from_kb(
            match, context, level=level, exclude_fingerprints=exclude
        )
        if generated:
            logger.info(
                "pre_match trivia from KB match=%s fp=%s",
                str(match.get("match_id", ""))[:8],
                generated.get("question_fp"),
            )
            return generated
        logger.warning(
            "KB context ok pero Bedrock no generó pregunta válida match=%s",
            str(match.get("match_id", ""))[:8],
        )

    curated = pick_curated_for_match_strict(
        home=home, away=away, level=level, exclude_fingerprints=exclude
    )
    if curated:
        logger.warning(
            "pre_match trivia curated_fallback match=%s (revisar KB/Bedrock)",
            str(match.get("match_id", ""))[:8],
        )
        curated["source"] = "curated_fallback"
        return curated

    logger.warning(
        "pre_match trivia fixture_template match=%s",
        str(match.get("match_id", ""))[:8],
    )
    return _template_from_match_metadata(match)

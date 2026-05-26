"""Genera preguntas de trivia pre-partido desde KB (+ Bedrock) — SPEC-025."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from src.services.trivia_question_bank import (
    is_meta_source_question,
    pick_curated_for_teams,
    question_fingerprint,
)

logger = logging.getLogger(__name__)

_BEDROCK_MODEL = os.environ.get(
    "BEDROCK_TRIVIA_MODEL_ID",
    "us.anthropic.claude-3-5-haiku-20241022-v1:0",
)
_REGION = os.environ.get("AWS_REGION", "us-east-1")


def fetch_pre_match_kb_context(match: dict[str, Any]) -> str:
    """Contexto KB (y web si hace falta) para ambos equipos del partido."""
    from src.kb.resolve import resolve_kb_then_web

    home = (match.get("home_team") or "").strip()
    away = (match.get("away_team") or "").strip()
    if not home or not away:
        return ""

    sections: list[str] = []
    queries = (
        (home, f"{home} selección nacional Copa Mundial FIFA historial mundiales"),
        (away, f"{away} selección nacional Copa Mundial FIFA historial mundiales"),
        ("encuentro", f"{home} vs {away} Copa Mundial 2026 grupo fase"),
    )
    for label, query in queries:
        try:
            result = resolve_kb_then_web(query, enqueue_on_web=False)
            text = (result.kb_text or "").strip()
            if len(text) < 80 and result.tavily_configured:
                text = (result.web_text or text or "").strip()
            if text:
                sections.append(f"### {label}\n{text[:1800]}")
        except Exception:
            logger.exception("pre_match kb fetch failed label=%s", label)

    return "\n\n".join(sections)[:5000]


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
    exclude = exclude_fingerprints or set()

    prompt = f"""Sos un editor de trivia de Copa Mundial 2026.
Generá UNA pregunta de opción múltiple nivel {level} sobre {home} y/o {away}.
Reglas:
- Usá SOLO hechos presentes en el contexto (no inventes).
- La pregunta debe mencionar a {home} o {away} (o ambos).
- 4 opciones A, B, C, D; exactamente una correcta en el campo "correct".
- Sin referencias a "knowledge base", Tavily, Wikipedia ni fuentes.

Contexto:
{context[:4000]}

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


def generate_pre_match_question(
    match: dict[str, Any],
    *,
    level: str = "EXPERT",
    exclude_fingerprints: set[str] | None = None,
) -> dict[str, Any]:
    """KB → Bedrock; fallback banco curado por equipos."""
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

    curated = pick_curated_for_teams(
        home=home, away=away, level=level, exclude_fingerprints=exclude
    )
    if curated:
        curated["source"] = "curated_fallback"
        return curated

    from src.services.trivia_question_bank import pick_any_curated_question

    fallback = pick_any_curated_question(exclude_fingerprints=exclude)
    if not fallback:
        raise ValueError("TRIVIA_BANK_EXHAUSTED")
    fallback["source"] = "curated_any"
    return fallback

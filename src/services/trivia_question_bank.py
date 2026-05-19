"""Selección de preguntas curadas — sin meta-preguntas sobre fuentes/KB."""
from __future__ import annotations

import hashlib
import random
import re
from typing import Any

from src.fixtures.trivia_questions import FALLBACK_QUESTIONS

_META_SOURCE_PATTERN = re.compile(
    r"\b(knowledge\s*base|knowledgebase|base\s+de\s+conocimiento|"
    r"open\s*search|tavily|wikipedia|wiki\b|contexto\s+kb|"
    r"fragmento|según\s+el\s+contexto|información\s+es\s+más\s+precisa)\b",
    re.IGNORECASE,
)


def question_fingerprint(question: str) -> str:
    norm = re.sub(r"\s+", " ", (question or "").strip().lower())
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


def is_meta_source_question(question: str, options: dict[str, str]) -> bool:
    blob = f"{question} {' '.join(str(v) for v in options.values())}"
    return bool(_META_SOURCE_PATTERN.search(blob))


def pick_curated_question(
    *,
    topic: str,
    level: str,
    exclude_fingerprints: set[str] | None = None,
) -> dict[str, Any] | None:
    """Elige una pregunta del banco manual evitando hashes ya usados."""
    exclude = exclude_fingerprints or set()
    topic_key = (topic or "mundiales").lower()
    level = level.upper()

    def _matches(q: dict[str, Any]) -> bool:
        if q["level"] != level:
            return False
        if q["topic"] == topic_key:
            return True
        return topic_key == "libre"

    pool = [dict(q) for q in FALLBACK_QUESTIONS if _matches(q)]
    if not pool:
        pool = [
            dict(q)
            for q in FALLBACK_QUESTIONS
            if q["level"] == level and q["topic"] in (topic_key, "mundiales", "libre")
        ]
    return _pick_from_pool(pool, exclude)


def pick_any_curated_question(
    *,
    exclude_fingerprints: set[str] | None = None,
) -> dict[str, Any] | None:
    """Último recurso: cualquier pregunta del banco que no esté en exclude."""
    exclude = exclude_fingerprints or set()
    pool = [dict(q) for q in FALLBACK_QUESTIONS]
    return _pick_from_pool(pool, exclude)


def _pick_from_pool(pool: list[dict[str, Any]], exclude: set[str]) -> dict[str, Any] | None:
    random.shuffle(pool)
    for q in pool:
        fp = question_fingerprint(q["question"])
        if fp in exclude:
            continue
        if is_meta_source_question(q["question"], q.get("options") or {}):
            continue
        out = dict(q)
        out["question_fp"] = fp
        return out
    return None

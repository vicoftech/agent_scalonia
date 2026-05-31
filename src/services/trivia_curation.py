"""Validación de calidad para trivias curadas y generadas — SPEC-049."""
from __future__ import annotations

import re
from typing import Any

_PENALTY_WORDS = re.compile(
    r"\b("
    r"penales|penalti|penalty|shoot[- ]?out|"
    r"tanda\s+de\s+penales|definici[oó]n\s+por\s+penales"
    r")\b",
    re.IGNORECASE,
)
_SCORE_PATTERN = re.compile(r"\b\d+\s*[-–]\s*\d+\b")


def _answer_reflected(correct_text: str, question: str, explanation: str) -> bool:
    ct = (correct_text or "").strip().lower()
    if not ct or len(ct) < 2:
        return True
    blob = f"{question} {explanation}".lower()
    if ct in blob:
        return True
    tokens = [p for p in re.split(r"\s+", ct) if len(p) >= 4]
    return any(t in blob for t in tokens)


def validate_trivia_mcq(q: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Rechaza preguntas incoherentes (texto vs explicación vs respuesta correcta).
    Retorna (ok, reason_code).
    """
    question = str(q.get("question") or "").strip()
    explanation = str(q.get("explanation") or "").strip()
    correct = str(q.get("correct") or "").upper().strip()
    options = q.get("options") or {}

    if not question or correct not in ("A", "B", "C", "D"):
        return False, "empty_question_or_invalid_correct"

    opts = {k: str(options.get(k, "")).strip() for k in ("A", "B", "C", "D")}
    if not all(opts.values()):
        return False, "incomplete_options"

    correct_text = opts[correct]

    # Pregunta habla de penales pero la explicación da marcador en 90' sin penales.
    if _PENALTY_WORDS.search(question) and _SCORE_PATTERN.search(explanation):
        if not _PENALTY_WORDS.search(explanation):
            return False, "penalties_question_regular_time_explanation"

    # Explicación debe respaldar la opción correcta (evita respuestas «correctas» absurdas).
    if explanation and not _answer_reflected(correct_text, question, explanation):
        return False, "correct_answer_not_supported"

    return True, None


def filter_valid_mcq_pool(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filtra ítems del banco manual que no pasan curación."""
    valid: list[dict[str, Any]] = []
    for q in pool:
        ok, _ = validate_trivia_mcq(q)
        if ok:
            valid.append(q)
    return valid

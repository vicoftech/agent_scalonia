"""Detección de bloqueos Bedrock Guardrails en eventos de streaming."""

from __future__ import annotations

from typing import Any


def is_guardrail_block_event(event: object) -> bool:
    """True si el evento indica intervención del guardrail (sin loggear el prompt)."""
    if not isinstance(event, dict):
        return False
    if "redactContent" in event:
        return True
    trace = _trace_from_event(event)
    if not trace:
        return False
    guardrail = trace.get("guardrail")
    if not isinstance(guardrail, dict):
        return False
    return _has_blocked_assessment(guardrail)


def _trace_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("metadata", "message"):
        block = event.get(key)
        if isinstance(block, dict):
            trace = block.get("trace")
            if isinstance(trace, dict):
                return trace
    trace = event.get("trace")
    return trace if isinstance(trace, dict) else None


def _has_blocked_assessment(guardrail_data: dict[str, Any]) -> bool:
    for assessment in guardrail_data.get("inputAssessment", {}).values():
        if _policy_blocked(assessment):
            return True
    for assessments in guardrail_data.get("outputAssessments", {}).values():
        items = assessments if isinstance(assessments, list) else [assessments]
        for assessment in items:
            if isinstance(assessment, dict) and _policy_blocked(assessment):
                return True
    return False


def _policy_blocked(node: object) -> bool:
    if isinstance(node, dict):
        if node.get("action") == "BLOCKED" or node.get("detected") and node.get("blocked"):
            return True
        return any(_policy_blocked(v) for v in node.values())
    if isinstance(node, list):
        return any(_policy_blocked(item) for item in node)
    return False

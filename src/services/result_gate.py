"""Feature flag — SPEC-2026-051 gate de aprobación admin."""
from __future__ import annotations

import os


def is_admin_gate_enabled() -> bool:
    """Default true: recolección no publica hasta confirmación admin."""
    return os.environ.get("RESULT_ADMIN_GATE_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
    )

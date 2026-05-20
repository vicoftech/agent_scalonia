"""Parseo de marcador libre (2-1, 2:1, 2 1)."""
from __future__ import annotations

import re

_SCORE = re.compile(r"^\s*(\d{1,2})\s*[-:.\s]\s*(\d{1,2})\s*$", re.IGNORECASE)


def parse_simple_score(text: str) -> tuple[int, int] | None:
    m = _SCORE.match((text or "").strip())
    if not m:
        return None
    h, a = int(m.group(1)), int(m.group(2))
    if h > 15 or a > 15:
        return None
    return h, a

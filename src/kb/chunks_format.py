"""Formateo de chunks pgvector para prompts y respuestas."""
from __future__ import annotations


def format_kb_chunks(rows: list[dict]) -> str:
    if not rows:
        return ""
    parts: list[str] = []
    for row in rows:
        src = row.get("source_path", "")
        prefix = f"[{src}]\n" if src else ""
        parts.append(f"{prefix}{row.get('content', '')}")
    return "\n\n---\n\n".join(parts)

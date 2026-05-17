"""Partición de documentos markdown para la KB."""
from __future__ import annotations

import re

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150


def chunk_text(text: str) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if len(text) <= CHUNK_SIZE:
        return [text] if text else []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            split = text.rfind("\n\n", start, end)
            if split > start + CHUNK_SIZE // 2:
                end = split
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks

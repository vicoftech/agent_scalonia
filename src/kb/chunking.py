"""Partición de documentos markdown para la KB."""
from __future__ import annotations

import re

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150


def _chunk_by_size(text: str) -> list[str]:
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


def _chunk_by_sections(text: str) -> list[str] | None:
    """Un chunk por ## sección (calendario por sede, ediciones, etc.)."""
    parts = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    if len(parts) < 2:
        return None
    preamble = parts[0].strip()
    sections = [p.strip() for p in parts[1:] if p.strip()]
    if len(sections) < 2:
        return None
    chunks: list[str] = []
    for section in sections:
        body = f"{preamble}\n\n{section}" if preamble else section
        if len(body) <= CHUNK_SIZE:
            chunks.append(body)
        else:
            chunks.extend(_chunk_by_size(body))
    return chunks


def chunk_text(text: str) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not text:
        return []
    by_section = _chunk_by_sections(text)
    if by_section:
        return by_section
    return _chunk_by_size(text)

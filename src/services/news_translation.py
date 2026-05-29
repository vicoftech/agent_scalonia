"""Traducción ES de titular/resumen para noticias en inglés — SPEC-2026-046."""
from __future__ import annotations

import logging
import re
from typing import Callable

logger = logging.getLogger(__name__)

_REGION = __import__("os").environ.get("AWS_REGION", "us-east-1")

_translate_fn: Callable[[str, str], tuple[str, str] | None] | None = None

_SPANISH_MARKERS = re.compile(
    r"\b(el|la|los|las|del|al|de|en|que|con|por|para|una|uno|selección|seleccion|mundial|partido|gol|goles|anunció|anuncio|convocatoria)\b",
    re.I,
)
_ENGLISH_MARKERS = re.compile(
    r"\b(the|and|for|with|will|has|have|team|teams|cup|world|match|goal|goals|squad|injury|preview|draw|group|groups|roster|announced|schedule)\b",
    re.I,
)
_ENGLISH_TOPIC = re.compile(
    r"\b(FIFA|World Cup|draw|squad|roster|injury|preview|matchday|knockout|group stage)\b",
    re.I,
)


def set_translate_fn(fn: Callable[[str, str], tuple[str, str] | None] | None) -> None:
    global _translate_fn
    _translate_fn = fn


def looks_english(text: str) -> bool:
    blob = (text or "").strip()
    if not blob:
        return False
    if re.search(r"[áéíóúñ¿¡]", blob, re.I):
        return False
    if _SPANISH_MARKERS.search(blob):
        return False
    en = len(_ENGLISH_MARKERS.findall(blob))
    if en >= 1:
        return True
    if _ENGLISH_TOPIC.search(blob):
        return True
    letters = re.findall(r"[a-zA-Z]", blob)
    if not letters:
        return False
    ascii_ratio = sum(1 for c in letters if ord(c) < 128) / len(letters)
    return ascii_ratio > 0.98 and not _SPANISH_MARKERS.search(blob)


def _aws_translate_text(text: str) -> str | None:
    import boto3

    chunk = (text or "").strip()
    if not chunk:
        return None
    try:
        client = boto3.client("translate", region_name=_REGION)
        resp = client.translate_text(
            Text=chunk[:4500],
            SourceLanguageCode="auto",
            TargetLanguageCode="es",
        )
        out = (resp.get("TranslatedText") or "").strip()
        return out or None
    except Exception:
        logger.exception("news translate aws failed")
        return None


def translate_if_english(headline: str, summary: str) -> tuple[str, str]:
    """Traduce titular y resumen si el texto parece inglés (Amazon Translate)."""
    h, s = (headline or "").strip(), (summary or "").strip()
    blob = f"{h} {s}".strip()
    if not blob or not looks_english(blob):
        return h, s
    if _translate_fn:
        out = _translate_fn(h, s)
        if out:
            return out
    th = _aws_translate_text(h)
    ts = _aws_translate_text(s) if s else th
    if th:
        return th, ts or th
    return h, s

"""Traducción ES de titular/resumen para noticias en inglés — SPEC-2026-046."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

_REGION = os.environ.get("AWS_REGION", "us-east-1")
# Nova Lite: rápido, no Anthropic (cuenta reseller/dev).
_TRANSLATE_MODEL = os.environ.get(
    "BEDROCK_NEWS_TRANSLATE_MODEL_ID",
    "us.amazon.nova-lite-v1:0",
)

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


def _extract_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _response_text(payload: dict[str, Any]) -> str:
    out = payload.get("output") or {}
    msg = out.get("message") or {}
    parts: list[str] = []
    for block in msg.get("content") or []:
        if isinstance(block, dict) and block.get("text"):
            parts.append(str(block["text"]))
    return "".join(parts).strip()


def _bedrock_translate(headline: str, summary: str) -> tuple[str, str] | None:
    import boto3

    prompt = (
        "Traducí al español rioplatense el titular y el resumen de esta noticia del Mundial 2026.\n"
        "No inventes datos ni agregues información.\n"
        'Respondé SOLO JSON válido: {"headline":"...","summary":"..."}\n\n'
        f"TITULAR:\n{headline}\n\nRESUMEN:\n{summary}"
    )
    client = boto3.client("bedrock-runtime", region_name=_REGION)
    try:
        resp = client.converse(
            modelId=_TRANSLATE_MODEL,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 700, "temperature": 0},
        )
        data = _extract_json(_response_text(resp))
        if not data:
            logger.warning("news translate: no JSON in bedrock response model=%s", _TRANSLATE_MODEL)
            return None
        h = str(data.get("headline") or "").strip()
        s = str(data.get("summary") or "").strip()
        if h and s:
            logger.info("news translate ok model=%s", _TRANSLATE_MODEL)
            return h, s
    except Exception:
        logger.exception("news translate bedrock failed model=%s", _TRANSLATE_MODEL)
    return None


def translate_if_english(headline: str, summary: str) -> tuple[str, str]:
    """Traduce titular y resumen si el texto parece inglés (Bedrock Nova)."""
    h, s = (headline or "").strip(), (summary or "").strip()
    blob = f"{h} {s}".strip()
    if not blob or not looks_english(blob):
        return h, s
    if _translate_fn:
        out = _translate_fn(h, s)
        if out:
            return out
    out = _bedrock_translate(h, s)
    if out:
        return out
    return h, s

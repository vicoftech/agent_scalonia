"""Traducción ES de titular/resumen para noticias en inglés — SPEC-2026-046."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

_TRANSLATE_MODEL = os.environ.get(
    "BEDROCK_NEWS_TRANSLATE_MODEL_ID",
    "us.anthropic.claude-3-5-haiku-20241022-v1:0",
)
_REGION = os.environ.get("AWS_REGION", "us-east-1")

_translate_fn: Callable[[str, str], tuple[str, str] | None] | None = None

_SPANISH_MARKERS = re.compile(
    r"\b(el|la|los|las|del|al|una|uno|que|con|por|para|selección|seleccion|mundial|partido|gol|goles)\b",
    re.I,
)
_ENGLISH_MARKERS = re.compile(
    r"\b(the|and|for|with|will|has|have|team|teams|cup|world|match|goal|goals|squad|injury|preview)\b",
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
    es = len(_SPANISH_MARKERS.findall(blob))
    en = len(_ENGLISH_MARKERS.findall(blob))
    if en >= 2 and en > es:
        return True
    letters = re.findall(r"[a-zA-Z]", blob)
    if not letters:
        return False
    ascii_ratio = sum(1 for c in letters if ord(c) < 128) / len(letters)
    return ascii_ratio > 0.98 and en >= 1 and es == 0


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


def _bedrock_translate(headline: str, summary: str) -> tuple[str, str] | None:
    import boto3

    prompt = (
        "Traducí al español rioplatense solo el titular y el resumen de esta noticia del Mundial 2026.\n"
        "No inventes datos. Respondé SOLO JSON:\n"
        '{"headline":"...","summary":"..."}\n\n'
        f"TITULAR:\n{headline}\n\nRESUMEN:\n{summary}"
    )
    try:
        client = boto3.client("bedrock-runtime", region_name=_REGION)
        resp = client.invoke_model(
            modelId=_TRANSLATE_MODEL,
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 512,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ),
        )
        body = json.loads(resp["body"].read())
        text = body.get("content", [{}])[0].get("text", "")
        data = _extract_json(text)
        if not data:
            return None
        h = str(data.get("headline") or "").strip()
        s = str(data.get("summary") or "").strip()
        if h and s:
            return h, s
    except Exception:
        logger.exception("news translate bedrock failed")
    return None


def translate_if_english(headline: str, summary: str) -> tuple[str, str]:
    """Traduce titular y resumen si el texto parece inglés; si falla, devuelve original."""
    h, s = (headline or "").strip(), (summary or "").strip()
    if not looks_english(f"{h} {s}"):
        return h, s
    if _translate_fn:
        out = _translate_fn(h, s)
        if out:
            return out
    out = _bedrock_translate(h, s)
    if out:
        return out
    return h, s

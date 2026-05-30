"""Traducción ES de titular/resumen para noticias en inglés — SPEC-2026-046."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_REGION = os.environ.get("AWS_REGION", "us-east-1")
# amazon.* = modelo regional en us-east-1. us.amazon.* = inference profile (puede rutear a us-west-2).
_DEFAULT_MODELS = "amazon.nova-lite-v1:0,us.amazon.nova-lite-v1:0"
_TRANSLATE_MODELS = [
    m.strip()
    for m in os.environ.get("BEDROCK_NEWS_TRANSLATE_MODEL_ID", _DEFAULT_MODELS).split(",")
    if m.strip()
]

_translate_fn: Callable[[str, str], tuple[str, str] | None] | None = None

_ENGLISH_MARKERS = re.compile(
    r"\b(the|and|for|with|will|has|have|team|teams|cup|world|match|goal|goals|squad|injury|preview|draw|group|groups|roster|announced|schedule|confirmed|everything)\b",
    re.I,
)
_ENGLISH_TOPIC = re.compile(
    r"\b(FIFA|World Cup|draw|squad|roster|injury|preview|matchday|knockout|group stage)\b",
    re.I,
)
_ENGLISH_SOURCE_HINTS = (
    "fifa.com",
    "uefa.com",
    "bbc.com",
    "bbc.co.uk",
    "goal.com",
    "reuters.com",
    "theguardian.com",
    "skysports.com",
    "espn.com/",
)


def set_translate_fn(fn: Callable[[str, str], tuple[str, str] | None] | None) -> None:
    global _translate_fn
    _translate_fn = fn


def _headline_is_spanish(headline: str) -> bool:
    h = (headline or "").strip()
    if not h:
        return True
    if re.search(r"[áéíóúñ¿¡]", h):
        return True
    if re.match(
        r"^(el|la|los|las|argentina|selección|seleccion|mundial|convocatoria|plantel)\b",
        h,
        re.I,
    ):
        return True
    return False


def should_translate(headline: str, article_url: str = "") -> bool:
    """Decisión solo por titular + fuente (no mezclar resumen de Tavily)."""
    h = (headline or "").strip()
    if not h or _headline_is_spanish(h):
        return False
    url = (article_url or "").lower()
    if any(hint in url for hint in _ENGLISH_SOURCE_HINTS):
        return True
    if _ENGLISH_MARKERS.search(h) or _ENGLISH_TOPIC.search(h):
        return True
    letters = [c for c in h if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if ord(c) < 128) / len(letters) > 0.95


def looks_english(text: str) -> bool:
    first = (text or "").strip().split("\n", 1)[0]
    return should_translate(first)


def _extract_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if "```" in text:
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.I)
        if fenced:
            text = fenced.group(1).strip()
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


def _fields_from_json(data: dict[str, Any]) -> tuple[str, str] | None:
    h = str(
        data.get("headline")
        or data.get("titular")
        or data.get("title")
        or ""
    ).strip()
    s = str(
        data.get("summary")
        or data.get("resumen")
        or data.get("description")
        or ""
    ).strip()
    if h and s:
        return h, s
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
        'Respondé SOLO JSON válido con claves exactas: {"headline":"...","summary":"..."}\n\n'
        f"TITULAR:\n{headline}\n\nRESUMEN:\n{summary}"
    )
    client = boto3.client("bedrock-runtime", region_name=_REGION)
    last_err: Exception | None = None
    for model_id in _TRANSLATE_MODELS:
        try:
            resp = client.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 700, "temperature": 0},
            )
            raw = _response_text(resp)
            data = _extract_json(raw)
            if not data:
                logger.warning(
                    "news translate: no JSON model=%s raw=%s",
                    model_id,
                    raw[:200],
                )
                continue
            fields = _fields_from_json(data)
            if fields:
                logger.info("news translate ok model=%s", model_id)
                return fields
        except Exception as exc:
            last_err = exc
            logger.warning("news translate failed model=%s err=%s", model_id, exc)
    if last_err:
        logger.error("news translate bedrock exhausted models last_err=%s", last_err)
    return None


def translate_if_english(
    headline: str,
    summary: str,
    *,
    article_url: str = "",
) -> tuple[str, str]:
    """Traduce titular y resumen si corresponde (Bedrock Nova regional)."""
    h, s = (headline or "").strip(), (summary or "").strip()
    if not should_translate(h, article_url):
        logger.debug("news translate skip should_translate=false headline=%s", h[:60])
        return h, s
    if _translate_fn:
        out = _translate_fn(h, s)
        if out:
            return out
    out = _bedrock_translate(h, s)
    if out:
        return out
    logger.warning("news translate skipped: bedrock returned nothing headline=%s", h[:80])
    return h, s


def domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""

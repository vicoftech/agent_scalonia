"""Tokens HMAC para tracking de lecturas — SPEC-2026-046."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os


def _secret() -> str:
    return os.environ.get("NEWS_REDIRECT_SECRET", "dev-news-secret-change-me")


def encode_read_token(user_id: str, news_id: str) -> str:
    payload = f"{user_id}:{news_id}"
    sig = hmac.new(_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    raw = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_read_token(token: str, news_id: str) -> str | None:
    if not token:
        return None
    try:
        pad = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token + pad).decode()
        parts = raw.split(":")
        if len(parts) != 3:
            return None
        user_id, nid, sig = parts
        if nid != news_id:
            return None
        payload = f"{user_id}:{news_id}"
        expected = hmac.new(_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            return None
        return user_id
    except Exception:
        return None


def _tracking_enabled() -> bool:
    """Solo si el redirect GET /news/r/ está desplegado (Terraform enable_world_cup_news)."""
    return os.environ.get("NEWS_REDIRECT_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    )


def build_read_url(
    news_id: str,
    user_id: str,
    *,
    article_url: str | None = None,
) -> str:
    """
    URL del botón «Leer más».
    Sin redirect desplegado → artículo directo (evita 404 en API Gateway).
    """
    direct = (article_url or "").strip()
    if not _tracking_enabled():
        return direct or "https://www.fifa.com"
    base = (os.environ.get("NEWS_REDIRECT_BASE_URL") or "").rstrip("/")
    if not base:
        return direct or "https://www.fifa.com"
    token = encode_read_token(user_id, news_id)
    return f"{base}/news/r/{news_id}?t={token}"

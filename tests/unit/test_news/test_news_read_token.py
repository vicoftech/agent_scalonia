"""Tests token lectura — SPEC-2026-046."""
from __future__ import annotations

import os

from src.services.news_read_token import decode_read_token, encode_read_token


def test_read_token_roundtrip():
    os.environ["NEWS_REDIRECT_SECRET"] = "test-secret-046"
    uid = "user-abc-123"
    nid = "news-xyz-456"
    token = encode_read_token(uid, nid)
    assert decode_read_token(token, nid) == uid
    assert decode_read_token(token, "other") is None

"""Cliente Telegram Bot API — envíos proactivos (notify dispatcher, trivias)."""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

import boto3

logger = logging.getLogger(__name__)

TG_API = "https://api.telegram.org"
MAX_TG_LEN = 4096

_token_cache: str | None = None
_get_token_fn: Optional[Callable[[], str]] = None
_send_fn: Optional[Callable[[int, str, str], None]] = None


def set_token_provider(fn: Optional[Callable[[], str]]) -> None:
    global _get_token_fn, _token_cache
    _get_token_fn = fn
    _token_cache = None


def set_send_fn(fn: Optional[Callable[[int, str, str], None]]) -> None:
    global _send_fn
    _send_fn = fn


def _post_json(url: str, body: dict[str, Any], timeout: float = 15) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.getcode(), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8"))
        except Exception:
            payload = {}
        return e.code, payload


def get_bot_token() -> str:
    """Token desde TELEGRAM_BOT_TOKEN o Secrets Manager (TELEGRAM_SECRET_ID / ARN)."""
    global _token_cache
    if _get_token_fn is not None:
        return _get_token_fn()
    if _token_cache:
        return _token_cache

    direct = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if direct:
        _token_cache = direct
        return direct

    secret_id = (
        os.environ.get("TELEGRAM_SECRET_ARN", "").strip()
        or os.environ.get("TELEGRAM_SECRET_ID", "SCALONIA_TELEGRAM_BOT_TOKEN").strip()
    )
    if not secret_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN o TELEGRAM_SECRET_ID no configurado")

    region = os.environ.get("AWS_REGION", "us-east-1")
    raw = boto3.client("secretsmanager", region_name=region).get_secret_value(
        SecretId=secret_id
    )["SecretString"]
    if raw.startswith("{"):
        parsed = json.loads(raw)
        _token_cache = parsed.get("token") or parsed.get("bot_token") or raw
    else:
        _token_cache = raw
    return _token_cache


def send_telegram_message(
    chat_id: int,
    text: str,
    token: str,
    *,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    """Envía texto plano; fragmenta si supera 4096 caracteres."""
    if _send_fn is not None:
        _send_fn(chat_id, text, token)
        return

    chunks = [text[i : i + MAX_TG_LEN] for i in range(0, len(text), MAX_TG_LEN)] or [""]
    for idx, chunk in enumerate(chunks):
        for attempt in range(3):
            body: dict[str, Any] = {"chat_id": int(chat_id), "text": chunk}
            if reply_markup and idx == 0:
                body["reply_markup"] = reply_markup
            code, resp = _post_json(f"{TG_API}/bot{token}/sendMessage", body)
            if code == 200 and resp.get("ok"):
                break
            if code == 429:
                time.sleep(float(resp.get("parameters", {}).get("retry_after", 2)))
                continue
            desc = resp.get("description", resp)
            raise RuntimeError(f"Telegram sendMessage failed code={code}: {desc}")
        else:
            raise RuntimeError("Telegram sendMessage failed after retries")

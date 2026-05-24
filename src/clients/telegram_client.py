"""Cliente Telegram Bot API — envíos proactivos (notify dispatcher, trivias)."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Callable, Optional

import httpx

logger = logging.getLogger(__name__)

TG_API = "https://api.telegram.org"
MAX_TG_LEN = 4096

_token_cache: str | None = None
_get_token_fn: Optional[Callable[[], str]] = None
_send_fn: Optional[Callable[[int, str, str], None]] = None
_http_client: httpx.Client | None = None


def set_token_provider(fn: Optional[Callable[[], str]]) -> None:
    global _get_token_fn, _token_cache
    _get_token_fn = fn
    _token_cache = None


def set_send_fn(fn: Optional[Callable[[int, str, str], None]]) -> None:
    global _send_fn
    _send_fn = fn


def _ssl_verify() -> bool | str:
    """
    Verificación TLS para api.telegram.org.

    En Mac con proxy corporativo (cert self-signed en cadena), para scripts locales:
      export TELEGRAM_SSL_VERIFY=0
    O apuntar al bundle de la empresa:
      export TELEGRAM_SSL_CERT_FILE=/ruta/a/ca-bundle.pem
    """
    cert_file = os.environ.get("TELEGRAM_SSL_CERT_FILE", "").strip()
    if cert_file:
        return cert_file
    flag = os.environ.get("TELEGRAM_SSL_VERIFY", "true").strip().lower()
    if flag in ("0", "false", "no", "off"):
        logger.warning(
            "TELEGRAM_SSL_VERIFY desactivado — solo para desarrollo local"
        )
        return False
    return True


def _http() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(verify=_ssl_verify(), timeout=30.0)
    return _http_client


def _post_json(url: str, body: dict[str, Any], timeout: float = 15) -> tuple[int, dict[str, Any]]:
    resp = _http().post(url, json=body, timeout=timeout)
    try:
        payload = resp.json() if resp.content else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return resp.status_code, payload


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

    from src.dao.dynamo.table import get_session

    raw = get_session().client("secretsmanager").get_secret_value(
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
            try:
                code, resp = _post_json(f"{TG_API}/bot{token}/sendMessage", body)
            except httpx.HTTPError as exc:
                raise RuntimeError(f"Telegram HTTP error: {exc}") from exc
            if code == 200 and resp.get("ok"):
                break
            if code == 429:
                time.sleep(float(resp.get("parameters", {}).get("retry_after", 2)))
                continue
            desc = resp.get("description", resp)
            raise RuntimeError(f"Telegram sendMessage failed code={code}: {desc}")
        else:
            raise RuntimeError("Telegram sendMessage failed after retries")

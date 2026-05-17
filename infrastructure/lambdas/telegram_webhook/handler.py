"""
infrastructure/lambdas/telegram_webhook/handler.py
Recibe Updates de Telegram → invoca AgentCore Runtime → sendMessage.
SPEC: SPEC-2026-011 | TASK: TASK-000-003 | Modo: IA-Assisted
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

DYNAMODB_TABLE = os.environ["DYNAMODB_TABLE"]
AGENTCORE_RUNTIME_ARN = os.environ["AGENTCORE_RUNTIME_ARN"]
AGENTCORE_RUNTIME_QUALIFIER = os.environ.get("AGENTCORE_RUNTIME_QUALIFIER", "LIVE")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
TELEGRAM_SECRET = os.environ.get("TELEGRAM_SECRET_ID", "SCALONIA_TELEGRAM_BOT_TOKEN")
TG_API = "https://api.telegram.org"
MAX_TG_LEN = 4096

_dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
_secrets_mgr = boto3.client("secretsmanager", region_name=AWS_REGION)
_agentcore = boto3.client("bedrock-agentcore", region_name=AWS_REGION)
_tg_token: str | None = None


def _get_token() -> str:
    global _tg_token
    if not _tg_token:
        _tg_token = _secrets_mgr.get_secret_value(SecretId=TELEGRAM_SECRET)["SecretString"]
    return _tg_token


def _post_json(url: str, body: dict[str, Any], timeout: float = 10) -> tuple[int, dict[str, Any]]:
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


def _send_message(chat_id: int, text: str, token: str) -> None:
    """Envía en MarkdownV2. Parte si > 4096 chars. Retry en 429."""
    for chunk in [text[i : i + MAX_TG_LEN] for i in range(0, len(text), MAX_TG_LEN)]:
        for attempt in range(3):
            url = f"{TG_API}/bot{token}/sendMessage"
            code, j = _post_json(url, {"chat_id": chat_id, "text": chunk, "parse_mode": "MarkdownV2"})
            if code == 429:
                time.sleep(float(j.get("parameters", {}).get("retry_after", 2)))
                continue
            if code == 400 and attempt == 0:
                _post_json(url, {"chat_id": chat_id, "text": chunk})
            break


def _resolve_user_id(platform_id_hash: str) -> str | None:
    table = _dynamodb.Table(DYNAMODB_TABLE)
    try:
        resp = table.query(
            IndexName="GSI-1-platform",
            KeyConditionExpression=(
                boto3.dynamodb.conditions.Key("platform").eq("TELEGRAM")
                & boto3.dynamodb.conditions.Key("platform_id_hash").eq(platform_id_hash)
            ),
            Limit=1,
        )
        items = resp.get("Items", [])
        return items[0]["user_id"] if items else None
    except Exception:
        logger.exception("GSI-1 lookup error")
        return None


def _read_agent_stream(response: dict[str, Any]) -> str:
    """Acumula respuesta de invoke_agent_runtime (SSE o JSON)."""
    content_type = response.get("contentType", "")
    stream = response.get("response")
    if stream is None:
        return ""

    if "text/event-stream" in content_type:
        parts: list[str] = []
        for line in stream.iter_lines(chunk_size=1):
            if not line:
                continue
            decoded = line.decode("utf-8")
            if decoded.startswith("data: "):
                decoded = decoded[6:]
            if decoded.startswith('"') and decoded.endswith('"'):
                decoded = decoded[1:-1]
            decoded = decoded.replace("\\n", "\n")
            parts.append(decoded)
        return "".join(parts).strip()

    body = stream.read()
    if not body:
        return ""
    try:
        data = json.loads(body)
        if isinstance(data, str):
            return data.strip()
        return json.dumps(data, ensure_ascii=False)
    except json.JSONDecodeError:
        return body.decode("utf-8", errors="replace").strip()


def _invoke_agent(user_id: str, session_id: str, prompt: str) -> str:
    try:
        payload = json.dumps({
            "prompt": prompt,
            "user_id": user_id,
            "platform": "TELEGRAM",
            "session_id": session_id,
        }).encode("utf-8")

        response = _agentcore.invoke_agent_runtime(
            agentRuntimeArn=AGENTCORE_RUNTIME_ARN,
            qualifier=AGENTCORE_RUNTIME_QUALIFIER,
            runtimeSessionId=session_id,
            payload=payload,
            contentType="application/json",
        )
        text = _read_agent_stream(response)
        return text or "No pude generar una respuesta. Intentá de nuevo."
    except Exception:
        logger.exception("invoke_agent_runtime error")
        return "Hubo un error. Por favor intentá de nuevo en unos segundos."


def handler(event: dict, context) -> dict:
    """SIEMPRE retorna 200 a Telegram para evitar re-envíos."""
    ok = {"statusCode": 200, "body": "ok"}
    try:
        body = json.loads(event.get("body") or "{}")
        message = body.get("message") or body.get("edited_message", {})
        if not message:
            return ok

        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()
        if not chat_id or not text:
            return ok

        logger.info("Telegram update recibido")

        token = _get_token()
        try:
            _post_json(
                f"{TG_API}/bot{token}/sendChatAction",
                {"chat_id": chat_id, "action": "typing"},
                timeout=5,
            )
        except Exception:
            pass

        platform_id_hash = hashlib.sha256(str(chat_id).encode()).hexdigest()
        user_id = _resolve_user_id(platform_id_hash) or "unregistered"
        session_id = f"tg-{platform_id_hash[:32]}"

        response_text = _invoke_agent(user_id, session_id, text)
        _send_message(chat_id, response_text, token)

    except Exception:
        logger.exception("Webhook error")
    return ok

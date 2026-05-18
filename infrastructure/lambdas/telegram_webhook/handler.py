"""
infrastructure/lambdas/telegram_webhook/handler.py
Recibe Updates de Telegram → invoca AgentCore Runtime → sendMessage.
SPEC: SPEC-2026-011 | TASK: TASK-000-003 | Modo: IA-Assisted
# deploy-trigger: 2026-05-18
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
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
    """Texto plano (sin MarkdownV2) para no romper con respuestas del LLM."""
    for chunk in [text[i : i + MAX_TG_LEN] for i in range(0, len(text), MAX_TG_LEN)]:
        for attempt in range(3):
            url = f"{TG_API}/bot{token}/sendMessage"
            code, j = _post_json(url, {"chat_id": chat_id, "text": chunk})
            if code == 429:
                time.sleep(float(j.get("parameters", {}).get("retry_after", 2)))
                continue
            break


def _iter_json_objects(raw: str):
    """Varios eventos Strands/AgentCore vienen concatenados en un mismo chunk."""
    decoder = json.JSONDecoder()
    pos = 0
    while pos < len(raw):
        while pos < len(raw) and raw[pos].isspace():
            pos += 1
        if pos >= len(raw):
            break
        if raw[pos] != "{":
            next_obj = raw.find("{", pos + 1)
            if next_obj == -1:
                break
            pos = next_obj
            continue
        try:
            obj, idx = decoder.raw_decode(raw, pos)
        except json.JSONDecodeError:
            next_obj = raw.find("{", pos + 1)
            if next_obj == -1:
                break
            pos = next_obj
            continue
        yield obj
        pos += idx


_THINKING_RE = re.compile(r"<thinking>.*?</thinking>\s*", re.DOTALL | re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    return _THINKING_RE.sub("", text).strip()


def _message_text_from_event(event: dict[str, Any]) -> str:
    msg = event.get("message")
    if not isinstance(msg, dict):
        return ""
    parts: list[str] = []
    for block in msg.get("content") or []:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return _strip_thinking("".join(parts)) if parts else ""


def _delta_text_from_event(event: dict[str, Any]) -> str:
    nested = event.get("event")
    if isinstance(nested, dict):
        block = nested.get("contentBlockDelta")
        if isinstance(block, dict):
            delta = block.get("delta") or {}
            if isinstance(delta.get("text"), str):
                return delta["text"]
    return ""


def _error_from_event(event: dict[str, Any]) -> str | None:
    if event.get("error"):
        return str(event.get("message") or event["error"])
    if event.get("force_stop"):
        return str(event.get("force_stop_reason") or "force_stop")
    return None


def _friendly_agent_error(reason: str) -> str:
    low = reason.lower()
    if "model identifier is invalid" in low:
        return "El modelo de IA no está configurado correctamente. Avisá al administrador."
    if "accessdenied" in low or "not authorized" in low:
        return "Sin permisos para invocar el modelo. Avisá al administrador."
    return "Hubo un error procesando tu mensaje. Intentá de nuevo en unos segundos."


def _parse_agent_stream_payload(raw: str) -> str:
    deltas: list[str] = []
    final_message = ""
    errors: list[str] = []
    for event in _iter_json_objects(raw):
        if not isinstance(event, dict):
            continue
        err = _error_from_event(event)
        if err:
            errors.append(err)
            continue
        if event.keys() <= {"init_event_loop"} or event.keys() <= {"start"} or event.keys() <= {"start_event_loop"}:
            continue
        msg = _message_text_from_event(event)
        if msg:
            final_message = msg
        chunk = _delta_text_from_event(event)
        if chunk:
            deltas.append(chunk)
    if final_message:
        return final_message
    if deltas:
        return _strip_thinking("".join(deltas))
    if errors:
        return _friendly_agent_error(errors[-1])
    return ""


def _parse_sse_events(stream) -> str:
    """Un evento JSON por línea ``data: {...}`` (formato AgentCore)."""
    deltas: list[str] = []
    final_message = ""
    errors: list[str] = []
    for line in stream.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8").strip()
        if not decoded.startswith("data: "):
            continue
        payload = decoded[6:].strip()
        if not payload.startswith("{"):
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        err = _error_from_event(event)
        if err:
            errors.append(err)
            continue
        msg = _message_text_from_event(event)
        if msg:
            final_message = msg
        chunk = _delta_text_from_event(event)
        if chunk:
            deltas.append(chunk)
    if final_message:
        return final_message
    if deltas:
        return _strip_thinking("".join(deltas))
    if errors:
        return _friendly_agent_error(errors[-1])
    return ""


def _read_agent_stream(response: dict[str, Any]) -> str:
    """Extrae texto legible del stream Strands (ignora eventos internos)."""
    content_type = response.get("contentType", "")
    stream = response.get("response")
    if stream is None:
        return ""

    try:
        if "text/event-stream" in content_type:
            parsed = _parse_sse_events(stream)
        else:
            body = stream.read()
            parsed = _parse_agent_stream_payload(
                body.decode("utf-8", errors="replace") if body else ""
            )
    except Exception:
        logger.exception("stream parse error")
        return ""
    return parsed.strip()


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

        if text.startswith("/start"):
            from start_handler import handle_start_command

            start_reply = handle_start_command(chat_id, text)
            if start_reply:
                _send_message(chat_id, start_reply, token)
                return ok
        try:
            _post_json(
                f"{TG_API}/bot{token}/sendChatAction",
                {"chat_id": chat_id, "action": "typing"},
                timeout=5,
            )
        except Exception:
            pass

        platform_id_hash = hashlib.sha256(str(chat_id).encode()).hexdigest()

        from src.services.auth_service import AuthService

        user_id, block_message = AuthService().resolve_telegram_access(platform_id_hash)
        if block_message:
            _send_message(chat_id, block_message, token)
            return ok

        try:
            from invitation_commands import handle_invitation_command

            invite_reply = handle_invitation_command(user_id, text)
            if invite_reply:
                _send_message(chat_id, invite_reply, token)
                return ok
        except Exception:
            logger.exception("invitation_commands failed")
            _send_message(
                chat_id,
                "No pude procesar el comando de invitación. Intentá de nuevo en unos segundos.",
                token,
            )
            return ok

        session_id = f"tg-{platform_id_hash[:32]}"
        response_text = _invoke_agent(user_id, session_id, text)
        _send_message(chat_id, response_text, token)

    except Exception:
        logger.exception("Webhook error")
    return ok

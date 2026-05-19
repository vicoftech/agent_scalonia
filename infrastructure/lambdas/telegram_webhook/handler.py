"""
infrastructure/lambdas/telegram_webhook/handler.py
Recibe Updates de Telegram → invoca AgentCore Runtime → sendMessage.
SPEC: SPEC-2026-011 | TASK: TASK-000-003 | Modo: IA-Assisted
# deploy-trigger: 2026-05-20
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

# Permite `from stream_parse import …` en Lambda (cwd) y en tests desde repo root.
_TG_WEBHOOK_DIR = Path(__file__).resolve().parent
if str(_TG_WEBHOOK_DIR) not in sys.path:
    sys.path.insert(0, str(_TG_WEBHOOK_DIR))
import urllib.error
import urllib.request
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

DYNAMODB_TABLE = os.environ["DYNAMODB_TABLE"]
AGENTCORE_RUNTIME_ARN = os.environ["AGENTCORE_RUNTIME_ARN"]
AGENTCORE_RUNTIME_QUALIFIER = os.environ.get("AGENTCORE_RUNTIME_QUALIFIER", "LIVE")
AGENT_RUNTIME_VERSION = os.environ.get("AGENT_RUNTIME_VERSION", "0")
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


def _send_message(
    chat_id: int,
    text: str,
    token: str,
    *,
    reply_markup: dict | None = None,
) -> None:
    """Texto plano (sin MarkdownV2) para no romper con respuestas del LLM."""
    for chunk in [text[i : i + MAX_TG_LEN] for i in range(0, len(text), MAX_TG_LEN)]:
        for attempt in range(3):
            url = f"{TG_API}/bot{token}/sendMessage"
            body: dict[str, Any] = {"chat_id": chat_id, "text": chunk}
            if reply_markup and chunk == text[:MAX_TG_LEN]:
                body["reply_markup"] = reply_markup
            code, j = _post_json(url, body)
            if code == 429:
                time.sleep(float(j.get("parameters", {}).get("retry_after", 2)))
                continue
            break


def _friendly_agent_error(reason: str) -> str:
    low = reason.lower()
    if "model identifier is invalid" in low:
        return "El modelo de IA no está configurado correctamente. Avisá al administrador."
    if "accessdenied" in low or "not authorized" in low:
        return "Sin permisos para invocar el modelo. Avisá al administrador."
    if "tool use" in low and "streaming" in low:
        return (
            "El modelo de IA no pudo usar las herramientas (KB/web) en este momento. "
            "Intentá de nuevo en unos segundos."
        )
    if "conversestream" in low or "modelerrorexception" in low:
        return (
            "El modelo de IA tuvo un error temporal al procesar la consulta. "
            "Intentá de nuevo en unos segundos."
        )
    return "Hubo un error procesando tu mensaje. Intentá de nuevo en unos segundos."


def _parse_agent_stream_payload(raw: str) -> str:
    from stream_parse import parse_agent_stream_payload  # noqa: E402

    return parse_agent_stream_payload(raw, friendly_error=_friendly_agent_error)


def _parse_sse_events(stream) -> str:
    from stream_parse import parse_sse_events  # noqa: E402

    return parse_sse_events(stream, friendly_error=_friendly_agent_error)


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


def _handle_callback_query(callback: dict, ok: dict) -> dict:
    """Botones inline: trivia (trv:) y onboarding (onb:)."""
    try:
        data = callback.get("data") or ""
        chat_id = callback.get("message", {}).get("chat", {}).get("id")
        if not chat_id or not data:
            return ok

        platform_id_hash = hashlib.sha256(str(chat_id).encode()).hexdigest()
        from src.services.auth_service import AuthService

        user_id, block_message = AuthService().resolve_telegram_access(platform_id_hash)
        if block_message or not user_id:
            return ok

        from src.dao.dynamo.user_dao import UserDAO

        UserDAO().set_telegram_chat_id(user_id, int(chat_id))

        token = _get_token()

        if data.startswith("trv:"):
            from trivia_commands import handle_trivia_callback

            try:
                reply = handle_trivia_callback(user_id, data)
            except Exception:
                logger.exception("trivia_callback failed")
                reply = "No pude registrar tu respuesta. Intentá de nuevo."
            if reply:
                _send_message(chat_id, reply, token)
        elif data.startswith("onb:"):
            from src.dao.dynamo.user_dao import UserDAO
            from onboarding_handler import handle_onboarding_callback

            profile = UserDAO().get_profile(user_id) or {}
            reply, markup = handle_onboarding_callback(user_id, profile, data)
            _send_message(chat_id, reply, token, reply_markup=markup)
        else:
            return ok

        cb_id = callback.get("id")
        if cb_id:
            _post_json(
                f"{TG_API}/bot{token}/answerCallbackQuery",
                {"callback_query_id": cb_id},
                timeout=5,
            )
    except Exception:
        logger.exception("callback_query failed")
    return ok


def handler(event: dict, context) -> dict:
    """SIEMPRE retorna 200 a Telegram para evitar re-envíos."""
    ok = {"statusCode": 200, "body": "ok"}
    try:
        body = json.loads(event.get("body") or "{}")
        callback = body.get("callback_query")
        if callback:
            return _handle_callback_query(callback, ok)

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

            start_result = handle_start_command(chat_id, text)
            if start_result:
                start_reply, start_markup = start_result
                _send_message(chat_id, start_reply, token, reply_markup=start_markup)
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
            logger.info(
                "auth_blocked platform_hash_prefix=%s",
                platform_id_hash[:12],
            )
            _send_message(chat_id, block_message, token)
            return ok

        from src.dao.dynamo.user_dao import UserDAO
        from src.services.onboarding_service import FIRST_POST_START_INSTRUCTION

        users_dao = UserDAO()
        users_dao.set_telegram_chat_id(user_id, int(chat_id))
        profile = users_dao.get_profile(user_id) if user_id else None
        onboarding_stage = (profile or {}).get("onboarding_stage", "?")
        first_post_start = (
            users_dao.consume_pending_first_agent_turn(user_id) if user_id else False
        )
        logger.info(
            "auth_ok user_prefix=%s onboarding_stage=%s first_post_start=%s",
            user_id[:8] if user_id else "?",
            onboarding_stage,
            first_post_start,
        )

        if profile and profile.get("onboarding_stage") == "M1_PENDING":
            from onboarding_handler import handle_onboarding_message

            onb_text, onb_markup = handle_onboarding_message(user_id, profile, text)
            if onb_text is not None:
                _send_message(chat_id, onb_text, token, reply_markup=onb_markup)
                return ok

        try:
            from trivia_prefetch import try_deliver_daily_trivia

            daily = try_deliver_daily_trivia(user_id, profile or {}, text=text)
            if daily:
                daily_text, daily_markup = daily
                _send_message(chat_id, daily_text, token, reply_markup=daily_markup)
                return ok
        except Exception:
            logger.exception("daily_trivia_prefetch failed")

        try:
            from trivia_commands import handle_trivia_command

            trivia_reply, trivia_markup = handle_trivia_command(user_id, text)
            if trivia_reply:
                _send_message(chat_id, trivia_reply, token, reply_markup=trivia_markup)
                return ok
        except Exception:
            logger.exception("trivia_commands failed")
            _send_message(
                chat_id,
                "No pude procesar la trivia en este momento. "
                "Si acaba de desplegarse el bot, probá de nuevo en un minuto.",
                token,
            )
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

        # AgentCore exige runtimeSessionId ≥33 chars. Versión bustea sesión post-deploy.
        session_suffix = "-poststart" if first_post_start else ""
        session_id = f"tg-{platform_id_hash[:32]}-v{AGENT_RUNTIME_VERSION}{session_suffix}"
        from fixture_prefetch import enrich_prompt_with_fixture, try_direct_fixture_reply
        from kb_prefetch import enrich_prompt_with_kb, try_direct_knowledge_reply

        direct_fixture = try_direct_fixture_reply(text)
        if direct_fixture:
            logger.info("fixture_direct_reply user_prefix=%s", user_id[:8])
            _send_message(chat_id, direct_fixture, token)
            return ok

        direct_kb = try_direct_knowledge_reply(text)
        if direct_kb:
            logger.info("kb_direct_reply user_prefix=%s", user_id[:8])
            _send_message(chat_id, direct_kb, token)
            return ok

        agent_prompt, has_fixture = enrich_prompt_with_fixture(text)
        if has_fixture:
            logger.info("fixture_prefetch ok user_prefix=%s", user_id[:8])
            kb_chunks = 0
        else:
            agent_prompt, kb_chunks = enrich_prompt_with_kb(agent_prompt)
            if kb_chunks:
                logger.info("kb_prefetch chunks=%s user_prefix=%s", kb_chunks, user_id[:8])
        if first_post_start:
            agent_prompt = f"{agent_prompt}\n\n{FIRST_POST_START_INSTRUCTION}"
        response_text = _invoke_agent(user_id, session_id, agent_prompt)
        _send_message(chat_id, response_text, token)

    except Exception:
        logger.exception("Webhook error")
    return ok

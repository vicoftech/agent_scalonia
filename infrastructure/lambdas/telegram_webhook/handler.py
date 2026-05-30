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


def _send_photo(
    chat_id: int,
    photo: str,
    caption: str,
    token: str,
    *,
    reply_markup: dict | None = None,
) -> None:
    """sendPhoto con caption HTML — SPEC-2026-046."""
    cap = caption[:1024] if len(caption) > 1024 else caption
    body: dict[str, Any] = {
        "chat_id": chat_id,
        "photo": photo,
        "caption": cap,
        "parse_mode": "HTML",
    }
    if reply_markup:
        body["reply_markup"] = reply_markup
    for attempt in range(3):
        code, j = _post_json(f"{TG_API}/bot{token}/sendPhoto", body)
        if code == 429:
            time.sleep(float(j.get("parameters", {}).get("retry_after", 2)))
            continue
        if code >= 400:
            logger.warning("sendPhoto failed code=%s desc=%s", code, j.get("description"))
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
    except Exception as exc:
        logger.exception(
            "invoke_agent_runtime error type=%s msg=%s",
            type(exc).__name__,
            str(exc)[:500],
        )
        err = str(exc)
        if "initialization time exceeded" in err or "Runtime initialization" in err:
            return (
                "⏳ El agente IA está arrancando (la primera consulta del día puede "
                "tardar ~1 minuto).\n"
                "No se descontó una consulta. Esperá un momento y reenviá la misma pregunta."
            )
        return "Hubo un error. Por favor intentá de nuevo en unos segundos."


def _handle_callback_query(callback: dict, ok: dict) -> dict:
    """Botones inline: trivia (trv:), onboarding (onb:), grupos (grp:)."""
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

        if data.startswith("news:"):
            cb_id = callback.get("id")
            if data.startswith("news:like:"):
                from news_callbacks import handle_news_callback

                handle_news_callback(
                    user_id,
                    data,
                    callback_query_id=cb_id,
                    chat_id=int(chat_id),
                    message=callback.get("message") or {},
                )
            else:
                from news_commands import handle_news_admin_callback

                result = handle_news_admin_callback(
                    user_id,
                    data,
                    callback_query_id=cb_id,
                )
                if result:
                    reply, markup = result
                    if reply:
                        _send_message(chat_id, reply, token, reply_markup=markup)
            return ok
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
        elif data.startswith("inv:"):
            cb_id = callback.get("id")
            if cb_id:
                _post_json(
                    f"{TG_API}/bot{token}/answerCallbackQuery",
                    {"callback_query_id": cb_id},
                    timeout=5,
                )
            from invitation_callbacks import handle_invitation_callback

            result = handle_invitation_callback(user_id, data)
            if result:
                reply, markup = result
                _send_message(chat_id, reply, token, reply_markup=markup)
            return ok
        elif data.startswith("prd:"):
            cb_id = callback.get("id")
            if cb_id:
                _post_json(
                    f"{TG_API}/bot{token}/answerCallbackQuery",
                    {"callback_query_id": cb_id},
                    timeout=5,
                )
            from prediction_callbacks import handle_prediction_callback

            try:
                result = handle_prediction_callback(user_id, data)
                if result:
                    reply, markup = result
                    if reply:
                        _send_message(chat_id, reply, token, reply_markup=markup)
            except Exception:
                logger.exception("prediction_callback failed data=%s", data[:60])
                _send_message(
                    chat_id,
                    "No pude guardar la predicción. Probá de nuevo con /partidos.",
                    token,
                )
            return ok
        elif data.startswith("grp:"):
            cb_id = callback.get("id")
            if cb_id:
                _post_json(
                    f"{TG_API}/bot{token}/answerCallbackQuery",
                    {"callback_query_id": cb_id},
                    timeout=5,
                )
            from group_commands import handle_group_callback

            try:
                result = handle_group_callback(user_id, data)
                if result:
                    reply, markup = result
                    if reply:
                        _send_message(chat_id, reply, token, reply_markup=markup)
                    else:
                        logger.warning("grp callback empty reply data=%s", data[:40])
                else:
                    _send_message(
                        chat_id,
                        "No pude procesar esa acción. Probá de nuevo con /crear_grupo.",
                        token,
                    )
            except Exception:
                logger.exception("grp callback failed data=%s", data[:60])
                _send_message(
                    chat_id,
                    "Hubo un error al guardar el grupo. Intentá de nuevo con /crear_grupo.",
                    token,
                )
            return ok
        elif data.startswith("rnk:"):
            cb_id = callback.get("id")
            if cb_id:
                _post_json(
                    f"{TG_API}/bot{token}/answerCallbackQuery",
                    {"callback_query_id": cb_id},
                    timeout=5,
                )
            from ranking_callbacks import handle_ranking_callback

            try:
                result = handle_ranking_callback(user_id, data)
                if result:
                    reply, markup = result
                    if reply:
                        _send_message(chat_id, reply, token, reply_markup=markup)
            except Exception:
                logger.exception("ranking_callback failed data=%s", data[:60])
                _send_message(
                    chat_id,
                    "No pude cargar el ranking. Probá de nuevo con /mi_ranking.",
                    token,
                )
            return ok
        elif data.startswith("gup:"):
            cb_id = callback.get("id")
            if cb_id:
                _post_json(
                    f"{TG_API}/bot{token}/answerCallbackQuery",
                    {"callback_query_id": cb_id},
                    timeout=5,
                )
            from group_upgrade_commands import handle_group_upgrade_callback

            try:
                result = handle_group_upgrade_callback(user_id, data)
                if result:
                    reply, markup = result
                    if reply:
                        _send_message(chat_id, reply, token, reply_markup=markup)
            except Exception:
                logger.exception("group_upgrade_callback failed data=%s", data[:60])
                _send_message(
                    chat_id,
                    "No pude procesar la ampliación. Probá /ampliar_plan.",
                    token,
                )
            return ok
        elif data.startswith("ia:"):
            cb_id = callback.get("id")
            if cb_id:
                _post_json(
                    f"{TG_API}/bot{token}/answerCallbackQuery",
                    {"callback_query_id": cb_id},
                    timeout=5,
                )
            from ask_ia_commands import handle_ask_ia_callback

            try:
                result = handle_ask_ia_callback(user_id, data)
                if result:
                    reply, markup = result
                    _send_message(chat_id, reply, token, reply_markup=markup)
            except Exception:
                logger.exception("ask_ia callback failed data=%s", data[:40])
                _send_message(
                    chat_id,
                    "No pude procesar la acción de Ask IA. Probá /ask_ia.",
                    token,
                )
            return ok
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
        if not chat_id:
            return ok

        text = (message.get("text") or "").strip()

        logger.info("Telegram update recibido")

        token = _get_token()

        if text.startswith("/start"):
            from bot_commands import sync_commands_for_chat
            from start_handler import handle_start_command

            platform_id_hash_start = hashlib.sha256(str(chat_id).encode()).hexdigest()
            from src.dao.dynamo.user_dao import UserDAO as _UserDAOStart

            _prof_start = _UserDAOStart().get_by_platform_hash(
                "TELEGRAM", platform_id_hash_start
            )
            sync_commands_for_chat(
                token,
                int(chat_id),
                is_admin=bool(_prof_start and _prof_start.get("is_admin")),
            )
            start_result = handle_start_command(chat_id, text)
            if start_result:
                start_reply, start_markup = start_result
                _send_message(chat_id, start_reply, token, reply_markup=start_markup)
                from bot_commands import send_main_reply_keyboard

                send_main_reply_keyboard(int(chat_id), token)
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

        users_dao = UserDAO()
        users_dao.set_telegram_chat_id(user_id, int(chat_id))
        profile = users_dao.get_profile(user_id) if user_id else None

        photos = message.get("photo") or []
        document = message.get("document")
        if user_id and profile and profile.get("group_upgrade_purchase_pending"):
            if photos or document:
                if photos:
                    file_id = photos[-1].get("file_id", "")
                else:
                    file_id = document.get("file_id", "")
                if file_id:
                    from group_upgrade_commands import handle_group_upgrade_purchase_proof

                    proof_reply = handle_group_upgrade_purchase_proof(
                        user_id, file_id=file_id
                    )
                    if proof_reply:
                        _send_message(chat_id, proof_reply, token)
                return ok
            if not text:
                _send_message(
                    chat_id,
                    "Enviá el comprobante como foto o documento PDF en este chat.",
                    token,
                )
                return ok

        if user_id and profile and profile.get("ai_purchase_pending"):
            if photos or document:
                if photos:
                    file_id = photos[-1].get("file_id", "")
                    kind = "photo"
                else:
                    file_id = document.get("file_id", "")
                    kind = "document"
                if file_id:
                    from ask_ia_commands import handle_ask_ia_purchase_proof

                    proof_reply = handle_ask_ia_purchase_proof(
                        user_id, file_id=file_id, file_kind=kind
                    )
                    if proof_reply:
                        _send_message(chat_id, proof_reply, token)
                return ok
            if not text:
                _send_message(
                    chat_id,
                    "Enviá el comprobante como foto o documento PDF en este chat.",
                    token,
                )
                return ok

        if not text:
            return ok

        from telegram_keyboards import normalize_reply_button

        mapped = normalize_reply_button(text)
        if mapped:
            text = mapped

        if user_id and profile and text.startswith("/"):
            from bot_commands import command_triggers_menu_sync, refresh_commands_for_chat

            if command_triggers_menu_sync(text):
                refresh_commands_for_chat(
                    token,
                    int(chat_id),
                    is_admin=bool(profile.get("is_admin")),
                )

        low_text = text.strip().lower()
        if low_text in ("/help", "help", "/ayuda", "ayuda"):
            from bot_commands import handle_help_command, help_message

            help_text = handle_help_command(user_id) if user_id else help_message()
            _send_message(chat_id, help_text, token)
            if user_id and profile:
                from bot_commands import send_main_reply_keyboard

                send_main_reply_keyboard(int(chat_id), token)
            return ok

        try:
            from shortcut_commands import handle_shortcut_command

            shortcut_reply = handle_shortcut_command(user_id, text)
            if shortcut_reply:
                stext, smarkup = shortcut_reply
                _send_message(chat_id, stext, token, reply_markup=smarkup)
                return ok
        except Exception:
            logger.exception("shortcut_commands failed")
            if text.strip().lower().startswith(("/ask_ia", "/ask-ia")):
                _send_message(
                    chat_id,
                    "No pude iniciar Ask IA en este momento. Intentá de nuevo en un minuto.",
                    token,
                )
                return ok

        onboarding_stage = (profile or {}).get("onboarding_stage", "?")
        logger.info(
            "auth_ok user_prefix=%s onboarding_stage=%s",
            user_id[:8] if user_id else "?",
            onboarding_stage,
        )

        if profile and profile.get("onboarding_stage") == "M1_PENDING":
            from onboarding_handler import handle_onboarding_message

            onb_text, onb_markup = handle_onboarding_message(user_id, profile, text)
            if onb_text is not None:
                _send_message(chat_id, onb_text, token, reply_markup=onb_markup)
                return ok

        try:
            from group_upgrade_commands import handle_group_upgrade_command

            gup_reply = handle_group_upgrade_command(user_id, text)
            if gup_reply:
                gup_text, gup_markup = gup_reply
                _send_message(chat_id, gup_text, token, reply_markup=gup_markup)
                return ok
        except Exception:
            logger.exception("group_upgrade_commands failed")

        try:
            from group_commands import handle_group_command

            group_reply = handle_group_command(user_id, text)
            if group_reply:
                grp_text, grp_markup = group_reply
                _send_message(chat_id, grp_text, token, reply_markup=grp_markup)
                return ok
        except Exception:
            logger.exception("group_commands failed")
            _send_message(
                chat_id,
                "No pude procesar el comando de grupos. Intentá de nuevo en unos segundos.",
                token,
            )
            return ok

        if profile and profile.get("prediction_wizard"):
            from src.services.prediction_service import PredictionService
            from src.services.prediction_wizard import abort_wizard_for_slash_command

            pred_svc = PredictionService()
            if not abort_wizard_for_slash_command(pred_svc, user_id, text):
                try:
                    pred_pending = pred_svc.handle_pending_message(user_id, text)
                    if pred_pending:
                        ptext, pmarkup = pred_pending
                        _send_message(chat_id, ptext, token, reply_markup=pmarkup)
                    else:
                        _send_message(
                            chat_id,
                            "Seguís en una predicción. Escribí el marcador (ej: 0-1, 0:1) "
                            "o enviá /cancel para salir.",
                            token,
                        )
                    return ok
                except Exception:
                    logger.exception("prediction_pending_message failed")
                    _send_message(
                        chat_id,
                        "No pude guardar la predicción. Probá de nuevo o /cancel.",
                        token,
                    )
                    return ok

        if profile and (
            profile.get("group_create_step")
            or profile.get("group_edit_pending")
            or profile.get("group_add_member_group_id")
        ):
            from group_commands import handle_group_pending_message

            grp_result = handle_group_pending_message(user_id, profile, text)
            if grp_result and grp_result[0]:
                grp_text, grp_markup = grp_result
                _send_message(chat_id, grp_text, token, reply_markup=grp_markup)
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

        _news_cmd = (text or "").strip().lower().split()[0].split("@")[0]
        _is_news_admin_cmd = _news_cmd in (
            "/noticia",
            "/noticia_publicar",
            "/noticias_hoy",
        )
        try:
            from news_commands import handle_news_command

            news_reply, news_markup = handle_news_command(user_id, text)
            if news_reply:
                _send_message(chat_id, news_reply, token, reply_markup=news_markup)
                return ok
        except Exception:
            logger.exception("news_commands failed")
            if _is_news_admin_cmd:
                _send_message(
                    chat_id,
                    "No pude procesar el comando de noticias. "
                    "Probá /noticia https://… o reintentá en un minuto.",
                    token,
                )
                return ok
        if _is_news_admin_cmd:
            _send_message(
                chat_id,
                "No pude procesar /noticia. Revisá que seas admin global "
                "y que el bot esté actualizado (último deploy).",
                token,
            )
            return ok

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
            from prediction_commands import handle_prediction_command

            pred_reply = handle_prediction_command(user_id, text)
            if pred_reply:
                pred_text, pred_markup = pred_reply
                _send_message(chat_id, pred_text, token, reply_markup=pred_markup)
                return ok
        except Exception:
            logger.exception("prediction_commands failed")
            _send_message(
                chat_id,
                "No pude procesar el comando de predicciones. Intentá /partidos.",
                token,
            )
            return ok

        try:
            from ask_ia_commands import handle_ask_ia_command

            ia_cmd = handle_ask_ia_command(user_id, text)
            if ia_cmd:
                ia_cmd_text, ia_cmd_markup = ia_cmd
                _send_message(chat_id, ia_cmd_text, token, reply_markup=ia_cmd_markup)
                return ok
        except Exception:
            logger.exception("ask_ia_commands failed")

        try:
            from invitation_commands import handle_invitation_command

            invite_reply = handle_invitation_command(user_id, text)
            if invite_reply:
                if isinstance(invite_reply, tuple):
                    inv_text, inv_markup = invite_reply
                else:
                    inv_text, inv_markup = invite_reply, None
                _send_message(chat_id, inv_text, token, reply_markup=inv_markup)
                return ok
        except Exception:
            logger.exception("invitation_commands failed")
            _send_message(
                chat_id,
                "No pude procesar el comando de invitación. Intentá de nuevo en unos segundos.",
                token,
            )
            return ok

        try:
            from ask_ia_commands import (
                handle_ask_ia_pending_text,
                invalid_command_message,
            )

            ia_pending = handle_ask_ia_pending_text(user_id, text)
            if ia_pending:
                ia_text, ia_markup = ia_pending
                _send_message(chat_id, ia_text, token, reply_markup=ia_markup)
                return ok
        except Exception:
            logger.exception("ask_ia_pending failed")

        # Marcador suelto (2-1) sin wizard activo.
        try:
            from src.services.prediction_score_parse import looks_like_simple_score

            if looks_like_simple_score(text):
                _send_message(
                    chat_id,
                    "Para predecir un resultado, elegí un partido con /partidos "
                    "y seguí los pasos del asistente.",
                    token,
                )
                return ok
        except Exception:
            logger.exception("prediction_score_guard failed")

        from ask_ia_commands import invalid_command_message

        _send_message(chat_id, invalid_command_message(), token)

    except Exception:
        logger.exception("Webhook error")
    return ok

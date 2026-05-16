"""
infrastructure/lambdas/telegram_webhook/handler.py
Recibe Updates de Telegram → invoca AgentCore → sendMessage.
SPEC: SPEC-2026-011 | TASK: TASK-000-003 | Modo: IA-Assisted
"""
import hashlib, json, logging, os
import boto3, httpx

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

DYNAMODB_TABLE   = os.environ["DYNAMODB_TABLE"]
AGENTCORE_AGENT_ID    = os.environ["AGENTCORE_AGENT_ID"]
AGENTCORE_AGENT_ALIAS = os.environ.get("AGENTCORE_AGENT_ALIAS", "LIVE")
AWS_REGION       = os.environ.get("AWS_REGION", "us-east-1")
TELEGRAM_SECRET  = "TELEGRAM_BOT_TOKEN"
TG_API           = "https://api.telegram.org"
MAX_TG_LEN       = 4096

_dynamodb    = boto3.resource("dynamodb", region_name=AWS_REGION)
_secrets_mgr = boto3.client("secretsmanager", region_name=AWS_REGION)
_agentcore   = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)
_tg_token: str | None = None


def _get_token() -> str:
    global _tg_token
    if not _tg_token:
        _tg_token = _secrets_mgr.get_secret_value(SecretId=TELEGRAM_SECRET)["SecretString"]
    return _tg_token


def _send_message(chat_id: int, text: str, token: str) -> None:
    """Envía en MarkdownV2. Parte si > 4096 chars. Retry en 429."""
    for chunk in [text[i:i+MAX_TG_LEN] for i in range(0, len(text), MAX_TG_LEN)]:
        for attempt in range(3):
            try:
                r = httpx.post(f"{TG_API}/bot{token}/sendMessage",
                               json={"chat_id": chat_id, "text": chunk, "parse_mode": "MarkdownV2"},
                               timeout=10)
                if r.status_code == 429:
                    import time; time.sleep(r.json().get("parameters", {}).get("retry_after", 2))
                    continue
                if r.status_code == 400 and attempt == 0:
                    httpx.post(f"{TG_API}/bot{token}/sendMessage",
                               json={"chat_id": chat_id, "text": chunk}, timeout=10)
                break
            except Exception as e:
                logger.error("sendMessage error: %s", type(e).__name__)


def _resolve_user_id(platform_id_hash: str) -> str | None:
    table = _dynamodb.Table(DYNAMODB_TABLE)
    try:
        resp = table.query(
            IndexName="GSI-1-platform",
            KeyConditionExpression=(
                boto3.dynamodb.conditions.Key("platform").eq("TELEGRAM") &
                boto3.dynamodb.conditions.Key("platform_id_hash").eq(platform_id_hash)
            ),
            Limit=1,
        )
        items = resp.get("Items", [])
        return items[0]["user_id"] if items else None
    except Exception as e:
        logger.error("GSI-1 lookup error: %s", type(e).__name__)
        return None


def _invoke_agent(user_id: str, session_id: str, prompt: str) -> str:
    try:
        response = _agentcore.invoke_agent(
            agentId=AGENTCORE_AGENT_ID, agentAliasId=AGENTCORE_AGENT_ALIAS,
            sessionId=session_id, inputText=prompt,
            sessionState={"sessionAttributes": {"user_id": user_id, "platform": "TELEGRAM"}},
        )
        text = ""
        for event in response.get("completion", []):
            chunk = event.get("chunk", {})
            if "bytes" in chunk:
                text += chunk["bytes"].decode("utf-8")
        return text.strip() or "No pude generar una respuesta. Intentá de nuevo."
    except Exception as e:
        logger.error("invoke_agent error: %s", type(e).__name__)
        return "Hubo un error. Por favor intentá de nuevo en unos segundos."


def handler(event: dict, context) -> dict:
    """SIEMPRE retorna 200 a Telegram para evitar re-envíos."""
    ok = {"statusCode": 200, "body": "ok"}
    try:
        body    = json.loads(event.get("body") or "{}")
        message = body.get("message") or body.get("edited_message", {})
        if not message:
            return ok

        chat_id = message.get("chat", {}).get("id")
        text    = message.get("text", "").strip()
        if not chat_id or not text:
            return ok

        logger.info("Telegram update recibido")  # NUNCA loggear chat_id

        token = _get_token()
        # send_chat_action typing
        try:
            httpx.post(f"{TG_API}/bot{token}/sendChatAction",
                       json={"chat_id": chat_id, "action": "typing"}, timeout=5)
        except Exception:
            pass

        platform_id_hash = hashlib.sha256(str(chat_id).encode()).hexdigest()
        user_id          = _resolve_user_id(platform_id_hash) or "unregistered"
        session_id       = f"tg-{platform_id_hash[:32]}"

        response_text = _invoke_agent(user_id, session_id, text)
        _send_message(chat_id, response_text, token)

    except Exception as e:
        logger.error("Webhook error: %s", type(e).__name__)
    return ok

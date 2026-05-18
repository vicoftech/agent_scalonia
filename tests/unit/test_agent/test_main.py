"""tests/unit/test_agent/test_main.py — Tests MVP del agente."""
import os
os.environ.setdefault("DYNAMODB_TABLE", "ProdeTable-test")
os.environ.setdefault("AGENTCORE_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/test")
os.environ.setdefault("AGENTCORE_RUNTIME_QUALIFIER", "LIVE")


class TestEchoTool:
    def test_echo_retorna_mensaje(self):
        from agent.tools.echo_tool import echo_tool
        result = echo_tool("hola mundo")
        assert result["echo"] == "hola mundo"
        assert "timestamp" in result
        assert "MVP operativo" in result["status"]

    def test_echo_features_pendientes(self):
        from agent.tools.echo_tool import echo_tool
        result = echo_tool("test")
        assert "predicciones" in result["features_pending"]
        assert "rankings" in result["features_pending"]
        assert "knowledge_base" not in result["features_pending"]
        assert "knowledge_base" in result["features_enabled"]
        assert "web_search" in result["features_enabled"]


class TestOnboardingContext:
    def test_build_session_context_injected_for_m1(self):
        from unittest.mock import MagicMock, patch

        from src.services.onboarding_service import OnboardingService

        with patch.object(OnboardingService, "__init__", lambda self, user_dao=None: None):
            svc = OnboardingService()
            svc._users = MagicMock()
            svc._users.get_profile.return_value = {
                "alias": "Jugador",
                "onboarding_stage": "M1_PENDING",
                "is_admin": False,
            }
            ctx = svc.build_session_context("uuid-1")
        assert "M1_PENDING" in ctx


class TestAgentEntrypoint:
    def test_app_es_bedrock_agentcore(self):
        from agent.main import app
        from bedrock_agentcore import BedrockAgentCoreApp
        assert isinstance(app, BedrockAgentCoreApp)

    def test_agent_tiene_echo_tool(self):
        from agent.main import _build_agent
        agent = _build_agent("test-user")
        tools = getattr(agent, "tools", None) or getattr(agent, "tool", [])
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        assert any("echo" in n.lower() for n in tool_names)


class TestTelegramStreamParser:
    def test_extrae_texto_desde_message_event(self):
        from infrastructure.lambdas.telegram_webhook.handler import _parse_agent_stream_payload

        raw = (
            '{"message": {"role": "assistant", "content": [{"text": "Hola mundo"}]}}'
        )
        assert _parse_agent_stream_payload(raw) == "Hola mundo"

    def test_error_modelo_amigable(self):
        from infrastructure.lambdas.telegram_webhook.handler import _parse_agent_stream_payload

        raw = (
            '{"force_stop": true, "force_stop_reason": '
            '"ValidationException: model identifier is invalid"}'
        )
        assert "modelo" in _parse_agent_stream_payload(raw).lower()


class TestTelegramWebhook:
    def test_retorna_200_con_update_vacio(self):
        from infrastructure.lambdas.telegram_webhook.handler import handler
        assert handler({"body": "{}"}, None)["statusCode"] == 200

    def test_retorna_200_sin_body(self):
        from infrastructure.lambdas.telegram_webhook.handler import handler
        assert handler({}, None)["statusCode"] == 200

    def test_retorna_200_con_excepcion(self):
        from infrastructure.lambdas.telegram_webhook.handler import handler
        assert handler({"body": "not-json"}, None)["statusCode"] == 200

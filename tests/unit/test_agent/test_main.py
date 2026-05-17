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
        assert "rankings"     in result["features_pending"]


class TestAgentEntrypoint:
    def test_app_es_bedrock_agentcore(self):
        from agent.main import app
        from bedrock_agentcore import BedrockAgentCoreApp
        assert isinstance(app, BedrockAgentCoreApp)

    def test_agent_tiene_echo_tool(self):
        from agent.main import _build_agent
        tool_names = [getattr(t, "__name__", str(t)) for t in _build_agent().tools]
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

"""Tools activas del agente: retornan str (parseables por Bedrock tool results)."""
import json
import inspect

import pytest

from agent.main import _build_agent


@pytest.fixture
def tool_names():
    agent = _build_agent("00000000-0000-4000-8000-000000000001")
    return set(agent.tool_registry.get_all_tools_config().keys())


def test_solo_tools_esperadas(tool_names):
    assert tool_names == {
        "echo_tool",
        "match_tool",
        "kb_retrieval_tool",
        "web_search_tool",
        "invitation_tool",
    }


@pytest.mark.parametrize(
    "module_path,func_name",
    [
        ("agent.tools.echo_tool", "echo_tool"),
        ("agent.tools.match_tool", "match_tool"),
        ("agent.tools.kb_retrieval_tool", "kb_retrieval_tool"),
        ("agent.tools.web_search_tool", "web_search_tool"),
    ],
)
def test_tool_return_annotation_str(module_path, func_name):
    import importlib

    mod = importlib.import_module(module_path)
    fn = getattr(mod, func_name)
    sig = inspect.signature(fn)
    ret = sig.return_annotation
    assert ret is str or ret == inspect.Signature.empty or "str" in str(ret)


def test_echo_tool_returns_valid_json_str():
    from agent.tools.echo_tool import echo_tool

    raw = echo_tool("ping")
    assert isinstance(raw, str)
    data = json.loads(raw)
    assert data["echo"] == "ping"

from src.services.match_query_intent import is_match_fixture_query


def test_fixture_horario_equipo():
    assert is_match_fixture_query("¿Cuándo juega Argentina el próximo partido?")


def test_fixture_grupo():
    assert is_match_fixture_query("partidos del grupo A mundial 2026")


def test_not_fixture_historia():
    assert not is_match_fixture_query("goles de Maradona en el mundial 1986")


def test_kb_retrieval_redirect():
    from agent.tools.kb_retrieval_tool import kb_retrieval_tool

    out = kb_retrieval_tool("horarios de Mexico en el mundial 2026")
    assert "match_tool" in out.lower()

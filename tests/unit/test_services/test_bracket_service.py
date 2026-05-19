"""tests/unit/test_services/test_bracket_service.py"""
import os

os.environ.setdefault("DYNAMODB_TABLE", "ProdeTable-test")

from src.services.bracket_service import BracketService, decode_slot
from src.services.match_query_intent import is_fixture_bracket_query, is_match_fixture_query


class TestBracketIntent:
    def test_argentina_16vos_grupo_j(self):
        q = (
            "Que cruces podría enfrentar argentina en 16vos "
            "según su clasificación en el grupo J?"
        )
        assert is_fixture_bracket_query(q)
        assert is_match_fixture_query(q)

    def test_horario_simple_no_es_bracket(self):
        q = "cuando juega argentina"
        assert not is_fixture_bracket_query(q)


class TestBracketService:
    def test_decode_slot_2h(self):
        text = decode_slot("2H")
        assert "Grupo H" in text
        assert "ESP" in text or "URU" in text

    def test_argentina_primer_puesto_r32(self):
        body = BracketService().format_bracket_scenarios("argentina", group_letter="J")
        assert "1J" in body or "1° del grupo" in body
        assert "#86" in body
        assert "2H" in body or "Grupo H" in body
        assert "#95" in body

    def test_argentina_segundo_puesto_r32_84(self):
        body = BracketService().format_bracket_scenarios("ARG", group_letter="J")
        assert "#84" in body
        assert "1H" in body or "Grupo H" in body

"""
tests/unit/test_scoring/test_scoring_engine.py
23 tests cubriendo todos los Scenarios de SPEC-2026-013.
Fallan hasta que se implemente scoring_engine.calculate_points() en TASK-010.
"""
import pytest
from src.scoring.scoring_engine import calculate_points, calculate_trivia_points


class TestGrupos:
    def test_exacto_basico(self):
        r = calculate_points(2, 1, 2, 1, "GROUP")
        assert r.points == 5 and r.reason == "EXACT_SCORE"

    def test_exacto_0_0(self):
        r = calculate_points(0, 0, 0, 0, "GROUP")
        assert r.points == 5 and r.reason == "EXACT_SCORE"

    def test_ganador_y_diferencia(self):
        r = calculate_points(2, 0, 3, 1, "GROUP")
        assert r.points == 3 and r.reason == "CORRECT_WINNER_AND_DIFF"

    def test_ganador_visitante_diferencia(self):
        r = calculate_points(0, 2, 1, 3, "GROUP")
        assert r.points == 3 and r.reason == "CORRECT_WINNER_AND_DIFF"

    def test_solo_ganador(self):
        r = calculate_points(2, 0, 1, 0, "GROUP")
        assert r.points == 1 and r.reason == "CORRECT_WINNER_ONLY"

    def test_incorrecto(self):
        r = calculate_points(2, 0, 0, 1, "GROUP")
        assert r.points == 0 and r.reason == "INCORRECT"

    def test_empate_exacto(self):
        r = calculate_points(1, 1, 1, 1, "GROUP")
        assert r.points == 5 and r.reason == "EXACT_SCORE"

    def test_empate_correcto_marcador_diferente(self):
        r = calculate_points(0, 0, 2, 2, "GROUP")
        assert r.points == 1 and r.reason == "CORRECT_WINNER_ONLY"

    def test_empate_predicho_ganador_real(self):
        r = calculate_points(1, 1, 2, 0, "GROUP")
        assert r.points == 0 and r.reason == "INCORRECT"

    def test_victoria_predicha_empate_real(self):
        r = calculate_points(1, 0, 0, 0, "GROUP")
        assert r.points == 0 and r.reason == "INCORRECT"


@pytest.mark.parametrize("phase", ["R16", "QF", "SF", "FINAL", "THIRD_PLACE"])
class TestEliminatorias:
    def test_90min_empate_exacto(self, phase):
        r = calculate_points(0, 0, 0, 0, phase)
        assert r.points == 5 and r.reason == "EXACT_SCORE"

    def test_90min_victoria_exacta(self, phase):
        r = calculate_points(2, 1, 2, 1, phase)
        assert r.points == 5

    def test_90min_incorrecto(self, phase):
        r = calculate_points(2, 0, 0, 0, phase)
        assert r.points == 0


class TestTrivia:
    def test_easy(self):   assert calculate_trivia_points("easy")   == 1
    def test_medium(self): assert calculate_trivia_points("medium") == 2
    def test_hard(self):   assert calculate_trivia_points("hard")   == 3


@pytest.mark.parametrize("ph,pa,ah,aa,phase,pts,reason", [
    (2, 0, 2, 0, "GROUP", 5, "EXACT_SCORE"),
    (0, 1, 0, 1, "GROUP", 5, "EXACT_SCORE"),
    (2, 0, 3, 1, "GROUP", 3, "CORRECT_WINNER_AND_DIFF"),
    (0, 2, 0, 4, "GROUP", 1, "CORRECT_WINNER_ONLY"),
    (2, 0, 1, 0, "GROUP", 1, "CORRECT_WINNER_ONLY"),
    (0, 1, 0, 3, "GROUP", 1, "CORRECT_WINNER_ONLY"),
    (1, 1, 2, 2, "GROUP", 1, "CORRECT_WINNER_ONLY"),
    (0, 0, 3, 3, "GROUP", 1, "CORRECT_WINNER_ONLY"),
    (2, 0, 0, 1, "GROUP", 0, "INCORRECT"),
    (1, 0, 0, 0, "GROUP", 0, "INCORRECT"),
    (1, 1, 2, 0, "GROUP", 0, "INCORRECT"),
])
def test_tabla_completa(ph, pa, ah, aa, phase, pts, reason):
    r = calculate_points(ph, pa, ah, aa, phase)
    assert r.points == pts and r.reason == reason

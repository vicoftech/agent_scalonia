from datetime import date

from src.services.match_date_parse import parse_dates_from_query


def test_multi_day_july():
    q = "hay partidos del mundial los dias 8, 9 o 10 de Julio"
    got = parse_dates_from_query(q)
    assert got == [date(2026, 7, 8), date(2026, 7, 9), date(2026, 7, 10)]


def test_single_day():
    q = "partidos el 9 de julio de 2026"
    got = parse_dates_from_query(q)
    assert got == [date(2026, 7, 9)]

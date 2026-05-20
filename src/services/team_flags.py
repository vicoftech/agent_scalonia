"""Banderas emoji por código FIFA (3 letras) — Telegram."""
from __future__ import annotations

# ISO2 derivado para códigos sin entrada explícita
_FIFA_ISO2: dict[str, str] = {
    "ARG": "AR",
    "ALG": "DZ",
    "AUT": "AT",
    "JOR": "JO",
    "MEX": "MX",
    "CAN": "CA",
    "RSA": "ZA",
    "KOR": "KR",
    "BIH": "BA",
    "QAT": "QA",
    "SUI": "CH",
    "CZE": "CZ",
    "BRA": "BR",
    "MAR": "MA",
    "HAI": "HT",
    "SCO": "GB",
    "USA": "US",
    "PAR": "PY",
    "AUS": "AU",
    "TUR": "TR",
    "GER": "DE",
    "CUW": "CW",
    "CIV": "CI",
    "ECU": "EC",
    "NED": "NL",
    "JPN": "JP",
    "SWE": "SE",
    "TUN": "TN",
    "BEL": "BE",
    "EGY": "EG",
    "IRN": "IR",
    "NZL": "NZ",
    "ESP": "ES",
    "CPV": "CV",
    "KSA": "SA",
    "URU": "UY",
    "FRA": "FR",
    "SEN": "SN",
    "IRQ": "IQ",
    "NOR": "NO",
    "POR": "PT",
    "COD": "CD",
    "UZB": "UZ",
    "COL": "CO",
    "ENG": "GB",
    "CRO": "HR",
    "GHA": "GH",
    "PAN": "PA",
}

# Overrides / alias con bandera explícita (mejor render en clientes)
_FLAG_OVERRIDE: dict[str, str] = {
    "ENG": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "SCO": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
}


def _iso2_flag(iso2: str) -> str:
    iso2 = iso2.upper()[:2]
    if len(iso2) != 2 or not iso2.isalpha():
        return "🏳️"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2)


def flag_emoji(team_code: str) -> str:
    code = (team_code or "").strip().upper()
    if not code:
        return "🏳️"
    if code in _FLAG_OVERRIDE:
        return _FLAG_OVERRIDE[code]
    iso2 = _FIFA_ISO2.get(code)
    if iso2:
        return _iso2_flag(iso2)
    return "🏳️"


def format_team(team_code: str) -> str:
    return f"{flag_emoji(team_code)} {team_code}"

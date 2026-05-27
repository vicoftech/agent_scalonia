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


# Nombres para UI (español); si el partido trae home_team_name en Dynamo, tiene prioridad.
TEAM_DISPLAY_NAMES: dict[str, str] = {
    "MEX": "México",
    "CAN": "Canadá",
    "RSA": "Sudáfrica",
    "KOR": "Corea del Sur",
    "BIH": "Bosnia y Herzegovina",
    "QAT": "Catar",
    "SUI": "Suiza",
    "CZE": "República Checa",
    "BRA": "Brasil",
    "MAR": "Marruecos",
    "HAI": "Haití",
    "SCO": "Escocia",
    "USA": "Estados Unidos",
    "PAR": "Paraguay",
    "AUS": "Australia",
    "TUR": "Turquía",
    "GER": "Alemania",
    "CUW": "Curaçao",
    "CIV": "Costa de Marfil",
    "ECU": "Ecuador",
    "NED": "Países Bajos",
    "JPN": "Japón",
    "SWE": "Suecia",
    "TUN": "Túnez",
    "BEL": "Bélgica",
    "EGY": "Egipto",
    "IRN": "Irán",
    "NZL": "Nueva Zelanda",
    "ESP": "España",
    "CPV": "Cabo Verde",
    "KSA": "Arabia Saudita",
    "URU": "Uruguay",
    "FRA": "Francia",
    "SEN": "Senegal",
    "IRQ": "Irak",
    "NOR": "Noruega",
    "ARG": "Argentina",
    "ALG": "Argelia",
    "AUT": "Austria",
    "JOR": "Jordania",
    "POR": "Portugal",
    "COD": "República Democrática del Congo",
    "UZB": "Uzbekistán",
    "COL": "Colombia",
    "ENG": "Inglaterra",
    "CRO": "Croacia",
    "GHA": "Ghana",
    "PAN": "Panamá",
}


def resolve_team_display_name(
    team_code: str,
    *,
    match: dict | None = None,
    side: str | None = None,
) -> str:
    """Nombre legible: Dynamo (home_team_name) o catálogo FIFA; fallback sigla."""
    code = (team_code or "").strip().upper()
    name: str | None = None
    if match and side == "home":
        code = (match.get("home_team") or code).strip().upper()
        raw = match.get("home_team_name")
        name = str(raw).strip() if raw else None
    elif match and side == "away":
        code = (match.get("away_team") or code).strip().upper()
        raw = match.get("away_team_name")
        name = str(raw).strip() if raw else None
    if name:
        return name
    return TEAM_DISPLAY_NAMES.get(code, code or "?")


def format_team(team_code: str) -> str:
    """Compacto: bandera + sigla FIFA (listas / botones)."""
    return f"{flag_emoji(team_code)} {team_code}"


def format_team_display(
    team_code: str,
    *,
    match: dict | None = None,
    side: str | None = None,
) -> str:
    """Detalle de partido: bandera + nombre completo."""
    code = (team_code or "").strip().upper()
    if match and side == "home":
        code = (match.get("home_team") or code).strip().upper()
    elif match and side == "away":
        code = (match.get("away_team") or code).strip().upper()
    return f"{flag_emoji(code)} {resolve_team_display_name(code, match=match, side=side)}"


def format_match_heading(match: dict) -> str:
    """Título para brief / wizard / resultado: nombres completos."""
    return (
        f"{format_team_display(match.get('home_team', ''), match=match, side='home')} vs "
        f"{format_team_display(match.get('away_team', ''), match=match, side='away')}"
    )

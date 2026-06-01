"""Formato consistente de respuestas IA para Telegram — Ask IA y análisis de predicciones."""
from __future__ import annotations

import html
import logging
import os
import re
from typing import Any, Literal

from src.services.team_flags import TEAM_DISPLAY_NAMES, flag_emoji

logger = logging.getLogger(__name__)

OutputMode = Literal["html", "plain"]

MAX_TG_MESSAGE = 4096

AI_RESPONSE_FORMAT_PROMPT = (
    "[Formato Telegram — obligatorio]\n"
    "- Separá ideas en párrafos (línea en blanco entre bloques).\n"
    "- Usá títulos cortos con ## o **negrita** para lo importante.\n"
    "- Listas con viñetas (- o •); tablas con columnas | si comparás datos.\n"
    "- Emojis solo al inicio de títulos o bullets (⚽ 🏆 📊 👥 🎯).\n"
    "- Español rioplatense, claro y escaneable."
)

_SYSTEM_SKIP_MARKERS = (
    "Comando no válido",
    "No pude iniciar",
    "No pude generar",
    "No se descontó",
    "Hubo un error",
    "El agente no está",
    "⛔ Usaste todas",
    "Sesión de IA cerrada",
    "Escribí tu siguiente pregunta",
    "Tenés ",
    " consultas disponibles",
    "Transferí $",
    "Para enviar un comprobante",
)

_SECTION_EMOJI: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"fortaleza", re.I), "💪"),
    (re.compile(r"debilidad|weakness", re.I), "⚠️"),
    (re.compile(r"predicci|prediction|inclino por", re.I), "🎯"),
    (re.compile(r"análisis|analisis|contexto ia", re.I), "📊"),
    (re.compile(r"plantel|nómina|nomina|jugador", re.I), "👥"),
    (re.compile(r"historia|récord|record", re.I), "📜"),
    (re.compile(r"resultado|marcador", re.I), "🏁"),
    (re.compile(r"grupo|fixture|partido", re.I), "⚽"),
    (re.compile(r"web|knowledge base|kb", re.I), "🌐"),
]

_HEADER_RE = re.compile(r"^#{1,3}\s+(.+)$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_MD_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_LIST_RE = re.compile(r"^(\s*)([-•*]|\d+[.)])\s+")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}")
_CREDITS_FOOTER_RE = re.compile(
    r"\n\nConsultas restantes:\s*\d+\s*$",
    re.I,
)
_KB_PREFIX_RE = re.compile(
    r"^(📚 Según la Knowledge Base del Prode:|🌐 Información verificada(?: \(web \+ Knowledge Base\)| \(búsqueda web\))?:)\s*\n*",
    re.I,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿\"(])")
_LIST_INTRO_RE = re.compile(
    r"(?i)(figuras|jugadores|delanteros|mediocampistas|defensores|arqueros|plantel|convocatoria)"
    r"(?: como|:)?\s+(.+?)(?:\.|$)"
)
_GROUP_RE = re.compile(r"\b(Grupo [A-H])\b", re.I)
_BEDROCK_FORMAT_MODELS = [
    m.strip()
    for m in os.environ.get(
        "AI_FORMAT_BEDROCK_MODELS",
        "amazon.nova-lite-v1:0,amazon.nova-pro-v1:0",
    ).split(",")
    if m.strip()
]


def escape_html(text: str) -> str:
    return html.escape(text or "", quote=False)


def _section_emoji(title: str) -> str:
    for pattern, emoji in _SECTION_EMOJI:
        if pattern.search(title):
            return emoji
    return "📌"


def _should_light_format(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if len(stripped) < 220 and any(m in stripped for m in _SYSTEM_SKIP_MARKERS):
        return True
    return False


def _split_blocks(text: str) -> list[str]:
    normalized = (text or "").replace("\r\n", "\n").strip()
    if not normalized:
        return []
    parts = re.split(r"\n\s*\n", normalized)
    return [p.strip() for p in parts if p.strip()]


def _detect_team_topics(text: str) -> list[tuple[str, str]]:
    lower = (text or "").lower()
    hits: list[tuple[int, str, str]] = []
    for code, name in TEAM_DISPLAY_NAMES.items():
        idx_name = lower.find(name.lower())
        idx_code = lower.find(code.lower())
        idx = -1
        if idx_name >= 0:
            idx = idx_name
        elif idx_code >= 0:
            idx = idx_code
        if idx >= 0:
            hits.append((idx, code, name))
    hits.sort(key=lambda x: x[0])
    return [(code, name) for _, code, name in hits]


def _normalize_source_prefix(text: str) -> tuple[str, str | None]:
    m = _KB_PREFIX_RE.match(text.strip())
    if not m:
        return text, None
    prefix = m.group(1).strip().rstrip(":")
    body = text[m.end() :].strip()
    if prefix.startswith("📚"):
        return body, "📚 Knowledge Base"
    return body, "🌐 Fuentes verificadas"


def _comma_list_to_bullets(fragment: str) -> list[str]:
    parts = re.split(r",\s*|\s+y\s+", fragment.strip())
    return [p.strip() for p in parts if p.strip()]


def _extract_inline_lists(text: str) -> tuple[str, list[str]]:
    bullets: list[str] = []
    for m in _LIST_INTRO_RE.finditer(text):
        label = m.group(1).strip().capitalize()
        items = _comma_list_to_bullets(m.group(2))
        if len(items) >= 2:
            bullets.extend(f"- 👤 {item}" for item in items[:6])
    return text, bullets


def _bold_key_phrases(text: str) -> str:
    out = _GROUP_RE.sub(r"**\1**", text)
    out = re.sub(
        r"(?i)\b((?:DT|director técnico)[:\s]+[^.!?]+)",
        r"**\1**",
        out,
    )
    out = re.sub(
        r"(?i)\b(La Celeste|Selección(?: uruguaya| argentina| mexicana)?)\b",
        r"**\1**",
        out,
    )
    return out


def _split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text.strip()) if p.strip()]
    return parts or [text.strip()]


def _group_sentences(sentences: list[str], *, size: int = 2) -> list[str]:
    if not sentences:
        return []
    groups: list[str] = []
    for i in range(0, len(sentences), size):
        chunk = " ".join(sentences[i : i + size]).strip()
        if chunk:
            groups.append(chunk)
    return groups


def _has_rich_structure(text: str) -> bool:
    if re.search(r"^#{1,3}\s", text, re.M):
        return True
    if _LIST_RE.search(text):
        return True
    if _is_table_block(text):
        return True
    return text.count("\n\n") >= 2


def _prose_to_structured_markdown(body: str) -> str:
    body, source_title = _normalize_source_prefix(body)
    body, inline_bullets = _extract_inline_lists(body)
    body = _bold_key_phrases(body)

    sections: list[str] = []
    if source_title:
        sections.append(f"## {source_title}")

    teams = _detect_team_topics(body)
    if teams and not source_title:
        code, name = teams[0]
        sections.append(f"## {flag_emoji(code)} {name}")

    if _has_rich_structure(body):
        sections.append(body)
    else:
        paragraphs = _group_sentences(_split_sentences(body), size=2)
        sections.extend(paragraphs)

    if inline_bullets:
        sections.append("\n".join(inline_bullets))

    return "\n\n".join(s for s in sections if s)


def _needs_bedrock_polish(html_out: str, raw_body: str) -> bool:
    if os.environ.get("AI_FORMAT_BEDROCK", "true").lower() in ("0", "false", "no"):
        return False
    if len(raw_body) < 160:
        return False
    if "<b>" in html_out and html_out.count("\n\n") >= 2:
        return False
    return True


def _bedrock_response_text(payload: dict[str, Any]) -> str:
    out = payload.get("output") or {}
    msg = out.get("message") or {}
    parts: list[str] = []
    for block in msg.get("content") or []:
        if isinstance(block, dict) and block.get("text"):
            parts.append(str(block["text"]))
    return "".join(parts).strip()


def _sanitize_telegram_html(text: str) -> str:
    cleaned = re.sub(r"<(?!/?(?:b|i|pre|code)\b)[^>]+>", "", text or "")
    return cleaned.strip()


def _bedrock_polish_html(raw_body: str) -> str | None:
    import boto3

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    prompt = (
        "Reformateá este texto para Telegram usando SOLO HTML válido "
        "(tags permitidos: <b>, <i>, <pre>).\n"
        "Reglas:\n"
        "- Título inicial con emoji y <b>negrita</b>.\n"
        "- Párrafos separados por línea en blanco.\n"
        "- Listas con prefijo ▫️ (sin <ul>).\n"
        "- Tablas comparativas en <pre> si aplica.\n"
        "- Resaltá datos clave (DT, grupo, figuras) con <b>.\n"
        "- NO inventes datos; conservá el contenido original.\n"
        "- Español rioplatense.\n\n"
        "Respondé SOLO el HTML final, sin explicación.\n\n"
        f"TEXTO:\n{raw_body[:3600]}"
    )
    client = boto3.client("bedrock-runtime", region_name=region)
    for model_id in _BEDROCK_FORMAT_MODELS:
        try:
            resp = client.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 1200, "temperature": 0.1},
            )
            raw = _bedrock_response_text(resp)
            if raw:
                cleaned = _sanitize_telegram_html(raw)
                if "<b>" in cleaned or cleaned.count("\n\n") >= 2:
                    logger.info("ai format bedrock ok model=%s", model_id)
                    return cleaned
        except Exception as exc:
            logger.warning("ai format bedrock failed model=%s err=%s", model_id, exc)
    return None


def _is_table_block(block: str) -> bool:
    lines = [ln for ln in block.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    pipe_lines = sum(1 for ln in lines if "|" in ln)
    return pipe_lines >= 2 and (pipe_lines / len(lines)) >= 0.5


def _parse_table_rows(block: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or _TABLE_SEP_RE.match(stripped):
            continue
        if "|" not in stripped:
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells:
            rows.append(cells)
    return rows


def _format_table(rows: list[list[str]], *, mode: OutputMode) -> str:
    if not rows:
        return ""
    col_count = max(len(r) for r in rows)
    widths = [0] * col_count
    for row in rows:
        for i, cell in enumerate(row):
            if i < col_count:
                widths[i] = max(widths[i], len(cell))

    def _pad_row(row: list[str]) -> str:
        padded = []
        for i in range(col_count):
            cell = row[i] if i < len(row) else ""
            padded.append(cell.ljust(widths[i]))
        return "  ".join(padded).rstrip()

    grid_lines = [_pad_row(row) for row in rows]
    if mode == "html":
        body = "\n".join(escape_html(line) for line in grid_lines)
        return f"<pre>{body}</pre>"
    return "\n".join(grid_lines)


def _inline_to_html(text: str) -> str:
    out = escape_html(text)
    out = _BOLD_RE.sub(r"<b>\1</b>", out)
    out = _ITALIC_MD_RE.sub(r"<i>\1</i>", out)
    return out


def _inline_to_plain(text: str) -> str:
    out = _BOLD_RE.sub(r"\1", text)
    out = _ITALIC_MD_RE.sub(r"\1", out)
    out = re.sub(r"^#{1,3}\s+", "", out, flags=re.M)
    return out.strip()


def _format_header(title: str, *, mode: OutputMode) -> str:
    clean = _inline_to_plain(title)
    emoji = _section_emoji(clean)
    if mode == "html":
        return f"<b>{emoji} {_inline_to_html(clean)}</b>"
    return f"{emoji} {clean}"


def _format_list_block(block: str, *, mode: OutputMode) -> str:
    lines = block.splitlines()
    formatted: list[str] = []
    for line in lines:
        m = _LIST_RE.match(line)
        if not m:
            formatted.append(_inline_to_html(line) if mode == "html" else _inline_to_plain(line))
            continue
        item = line[m.end() :].strip()
        bullet = "▫️"
        if mode == "html":
            formatted.append(f"{bullet} {_inline_to_html(item)}")
        else:
            formatted.append(f"• {_inline_to_plain(item)}")
    return "\n".join(formatted)


def _format_block(block: str, *, mode: OutputMode) -> str:
    if _is_table_block(block):
        return _format_table(_parse_table_rows(block), mode=mode)

    lines = block.splitlines()
    first = lines[0].strip()
    header_match = _HEADER_RE.match(first)
    if header_match:
        header = _format_header(header_match.group(1), mode=mode)
        rest = "\n".join(lines[1:]).strip()
        if not rest:
            return header
        body = _format_block(rest, mode=mode) if rest else ""
        return f"{header}\n\n{body}" if body else header

    if all(_LIST_RE.match(ln) or not ln.strip() for ln in lines):
        return _format_list_block(block, mode=mode)

    if len(first) < 80 and first.endswith(":") and len(lines) > 1:
        label = _format_header(first[:-1], mode=mode)
        rest = _format_list_block("\n".join(lines[1:]), mode=mode)
        return f"{label}\n{rest}"

    if mode == "html":
        return _inline_to_html(block)
    return _inline_to_plain(block)


def format_ai_telegram_response(
    text: str,
    *,
    mode: OutputMode = "html",
    variant: str = "general",
) -> str:
    """
    Normaliza respuestas IA: párrafos, títulos, emojis, grillas y énfasis.
    variant: general | prediction | kb_direct
    """
    raw = (text or "").strip()
    if not raw:
        return ""

    if _should_light_format(raw):
        if mode == "html":
            return _inline_to_html(raw)
        return raw

    footer_match = _CREDITS_FOOTER_RE.search(raw)
    footer = footer_match.group(0).strip() if footer_match else ""
    body = _CREDITS_FOOTER_RE.sub("", raw).strip()

    if not _has_rich_structure(body):
        body = _prose_to_structured_markdown(body)

    blocks = _split_blocks(body)
    if not blocks:
        blocks = [body]

    formatted_blocks: list[str] = []
    for block in blocks:
        formatted_blocks.append(_format_block(block, mode=mode))

    out = "\n\n".join(formatted_blocks)
    if mode == "html" and _needs_bedrock_polish(out, body):
        polished = _bedrock_polish_html(body)
        if polished:
            out = polished
    if variant == "prediction" and mode == "plain":
        out = f"📊 Contexto IA\n\n{out}"
    if footer:
        if mode == "html":
            footer_plain = footer.replace("Consultas restantes:", "").strip()
            m = re.search(r"(\d+)", footer_plain)
            n = m.group(1) if m else "?"
            out = f"{out}\n\n<i>💬 Consultas restantes: {escape_html(n)}</i>"
        else:
            out = f"{out}\n\n💬 {footer}"
    return out[:MAX_TG_MESSAGE]


def format_prediction_analysis(
    match_brief: dict[str, Any],
    *,
    mode: OutputMode = "plain",
) -> str:
    """Bloque de análisis IA en wizard / brief de predicción."""
    line = (match_brief.get("ia_prediction_line") or "").strip()
    if not line:
        return ""

    home = match_brief.get("home_team") or ""
    away = match_brief.get("away_team") or ""

    def _bullets(label: str, items: list[Any], emoji: str) -> str:
        if not items:
            return ""
        rows = [f"- {emoji} {label}: {x}" for x in items[:4]]
        return "\n".join(rows)

    sections = [
        f"## Análisis del partido {home} vs {away}",
        f"🎯 {line}",
        _bullets(f"Fortalezas {home}", match_brief.get("home_strengths") or [], "💪"),
        _bullets(f"Debilidades {home}", match_brief.get("home_weaknesses") or [], "⚠️"),
        _bullets(f"Fortalezas {away}", match_brief.get("away_strengths") or [], "💪"),
        _bullets(f"Debilidades {away}", match_brief.get("away_weaknesses") or [], "⚠️"),
        "_Análisis informativo; no es recomendación de apuesta ni marcador exacto._",
    ]
    raw = "\n\n".join(s for s in sections if s)
    return format_ai_telegram_response(raw, mode=mode, variant="prediction")

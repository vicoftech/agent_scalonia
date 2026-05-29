"""Comandos admin /noticia — SPEC-2026-046."""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_NOTICIA = re.compile(r"^/noticia(?:@[\w_]+)?(?:\s+(.+))?$", re.IGNORECASE | re.DOTALL)
_NOTICIA_PUBLICAR = re.compile(r"^/noticia_publicar(?:@[\w_]+)?\s*$", re.IGNORECASE)
_NOTICIAS_HOY = re.compile(r"^/noticias_hoy(?:@[\w_]+)?\s*$", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+", re.I)


def _admin_only(user_id: str) -> bool:
    from src.services.auth_service import AuthService

    return AuthService().is_admin_global(user_id)


def _get_draft(profile: dict[str, Any]) -> dict[str, Any] | None:
    draft = profile.get("news_admin_draft")
    return draft if isinstance(draft, dict) else None


def _save_draft(user_id: str, draft: dict[str, Any] | None) -> None:
    from src.dao.dynamo.user_dao import UserDAO

    if draft is None:
        UserDAO().update_profile(user_id, news_admin_draft=None)
    else:
        UserDAO().update_profile(user_id, news_admin_draft=draft)


def _preview_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Publicar", "callback_data": "news:pub:confirm"},
                {"text": "🔄 Otra", "callback_data": "news:pub:refresh"},
            ],
            [
                {"text": "✏️ Editar", "callback_data": "news:pub:edit"},
                {"text": "Cancelar", "callback_data": "news:pub:cancel"},
            ],
        ]
    }


def handle_news_command(user_id: str, text: str) -> tuple[str | None, dict | None]:
    if not _admin_only(user_id):
        return "Solo administradores pueden publicar noticias.", None
    stripped = (text or "").strip()
    if _NOTICIAS_HOY.match(stripped):
        return _format_today_list(), None
    if _NOTICIA_PUBLICAR.match(stripped):
        return _publish_draft(user_id)
    m = _NOTICIA.match(stripped)
    if not m:
        return None, None
    arg = (m.group(1) or "").strip()
    if not arg:
        return _curate_admin_draft(user_id)
    url_m = _URL_RE.search(arg)
    if url_m:
        return _start_url_draft(user_id, url_m.group(0))
    return _start_text_draft(user_id, arg)


def handle_news_admin_callback(
    user_id: str,
    data: str,
    *,
    callback_query_id: str | None = None,
) -> tuple[str | None, dict | None]:
    from handler import _get_token, _post_json

    if not _admin_only(user_id):
        return None, None
    token = _get_token()
    if callback_query_id:
        _post_json(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            {"callback_query_id": callback_query_id},
            timeout=5,
        )
    if data == "news:pub:cancel":
        _save_draft(user_id, None)
        return "Publicación cancelada.", None
    if data == "news:pub:edit":
        return (
            "Reenviá /noticia (busca sola), /noticia https://… o texto con /noticia …",
            None,
        )
    if data == "news:pub:refresh":
        return _curate_admin_draft(user_id, refresh=True)
    if data == "news:pub:confirm":
        return _publish_draft(user_id)
    return None, None


def _local_today_iso() -> str:
    from datetime import datetime

    from src.services.match_service import DISPLAY_TZ

    return datetime.now(DISPLAY_TZ).date().isoformat()


def _exclude_for_admin(user_id: str, *, refresh: bool = False) -> tuple[set[str], set[str]]:
    from src.dao.dynamo.news_dao import NewsDAO
    from src.dao.dynamo.user_dao import UserDAO
    from src.services.news_curation_service import headline_fingerprint

    run_date = _local_today_iso()
    items = NewsDAO().list_published_on_date(run_date)
    url_hashes = {n.get("url_hash") for n in items if n.get("url_hash")}
    headline_fps = {
        headline_fingerprint(str(n.get("headline") or ""))
        for n in items
        if n.get("headline")
    }
    if refresh:
        profile = UserDAO().get_profile(user_id) or {}
        draft = _get_draft(profile)
        if draft:
            if draft.get("url_hash"):
                url_hashes.add(draft["url_hash"])
            if draft.get("headline"):
                headline_fps.add(headline_fingerprint(str(draft["headline"])))
    return url_hashes, headline_fps


def _curate_admin_draft(user_id: str, *, refresh: bool = False) -> tuple[str, dict | None]:
    from src.services.news_curation_service import NewsCurationService
    from src.services.news_telegram_format import format_news_caption
    from src.web.tavily_search import is_tavily_configured

    if not is_tavily_configured():
        return (
            "No hay búsqueda web configurada (Tavily). "
            "Usá /noticia https://… o pegá el texto de la noticia.",
            None,
        )
    exclude_urls, exclude_fps = _exclude_for_admin(user_id, refresh=refresh)
    curated = NewsCurationService().curate_fresh(
        exclude_url_hashes=exclude_urls,
        exclude_headline_fps=exclude_fps,
    )
    if not curated:
        return (
            "No encontré una noticia nueva en fuentes confiables.\n"
            "Probá 🔄 Otra, /noticia con una URL, o pegá el texto.",
            _preview_keyboard() if refresh else None,
        )
    from src.services.news_translation import translate_if_english

    url = curated.get("article_url") or ""
    h, s = translate_if_english(
        str(curated.get("headline") or ""),
        str(curated.get("summary") or ""),
        article_url=url,
    )
    curated = {**curated, "headline": h, "summary": s}
    _save_draft(user_id, curated)
    caption = format_news_caption({**curated, "source_type": "ADMIN"}, include_footer=True)
    prefix = "🔎 Otra sugerida" if refresh else "🔎 Noticia sugerida"
    return (
        f"{prefix} (revisá antes de publicar):\n\n{caption}",
        _preview_keyboard(),
    )


def _start_url_draft(user_id: str, url: str) -> tuple[str, dict | None]:
    from src.services.news_curation_service import NewsCurationService
    from src.services.news_telegram_format import format_news_caption

    og = NewsCurationService().fetch_og_article(url)
    if not og:
        return "No pude leer esa URL. Probá con otro enlace o pegá el texto.", None
    _save_draft(user_id, og)
    caption = format_news_caption({**og, "source_type": "ADMIN"}, include_footer=True)
    return f"Vista previa:\n\n{caption}", _preview_keyboard()


def _start_text_draft(user_id: str, text: str) -> tuple[str, dict | None]:
    from src.services.news_telegram_format import format_news_caption

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    headline = lines[0][:200] if lines else "Noticia Prode"
    summary = " ".join(lines[1:]) if len(lines) > 1 else headline
    draft = {
        "headline": headline,
        "summary": summary[:600],
        "article_url": "https://www.fifa.com",
        "category": "Mundial 2026",
        "subcategory": "#Noticias",
        "source_label": "Admin · texto",
        "relevance_score": 80,
        "image_url": "",
    }
    _save_draft(user_id, draft)
    caption = format_news_caption({**draft, "source_type": "ADMIN"}, include_footer=True)
    return f"Vista previa:\n\n{caption}", _preview_keyboard()


def _publish_draft(user_id: str) -> tuple[str, dict | None]:
    from src.dao.dynamo.user_dao import UserDAO

    profile = UserDAO().get_profile(user_id) or {}
    draft = _get_draft(profile)
    if not draft:
        return "No hay borrador. Usá /noticia con una URL o texto.", None
    try:
        from handler import _get_token, _send_photo
        from news_broadcast import broadcast_news_message
        from src.services.world_cup_news_service import WorldCupNewsService

        def _broadcast(**kwargs: Any) -> tuple[int, int]:
            targets = WorldCupNewsService().list_delivery_targets()
            return broadcast_news_message(
                delivery_targets=targets,
                news_id=kwargs["news_id"],
                caption=kwargs["caption"],
                image_url=kwargs["image_url"],
                like_count=kwargs["like_count"],
                article_url=kwargs.get("article_url"),
                token=_get_token(),
                send_photo=_send_photo,
            )

        svc = WorldCupNewsService(broadcast_fn=_broadcast)
        out = svc.publish_admin(user_id, draft)
        _save_draft(user_id, None)
        return (
            f"✅ Noticia publicada.\n"
            f"ID: {out.get('news_id', '')[:8]}…\n"
            f"📤 Enviada a {out.get('sent_count', 0)} usuario(s).\n"
            f"Título: {out.get('headline', '')[:80]}",
            None,
        )
    except Exception:
        logger.exception("publish_admin failed")
        return "No pude publicar la noticia. Revisá los logs.", None


def _format_today_list() -> str:
    from src.services.world_cup_news_service import WorldCupNewsService

    items = WorldCupNewsService().list_today_for_admin()
    if not items:
        return "📰 No hay noticias publicadas hoy (ART)."
    lines = ["📰 Noticias de hoy", ""]
    for it in items:
        slot = it.get("automated_slot") or it.get("source_type", "")
        lines.append(
            f"· {it.get('news_id', '')[:8]}… | {slot} | 👍{int(it.get('like_count') or 0)} "
            f"👁{int(it.get('read_count') or 0)} | {str(it.get('headline') or '')[:50]}"
        )
    return "\n".join(lines)

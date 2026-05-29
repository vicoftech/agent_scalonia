"""Orquestación noticias Mundial — SPEC-2026-046."""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from src.dao.dynamo.job_ctrl_dao import JobCtrlDAO
from src.dao.dynamo.match_dao import MatchDAO
from src.dao.dynamo.news_dao import NewsDAO
from src.dao.dynamo.user_dao import UserDAO
from src.jobs import world_cup_news_schedule as sched
from src.services.news_curation_service import NewsCurationService
from src.services.news_telegram_format import format_news_caption

logger = logging.getLogger(__name__)

JOB_PRE = "WC_NEWS_PRE"
JOB_LIVE = "WC_NEWS_LIVE"


def _enabled() -> bool:
    return os.environ.get("ENABLE_WORLD_CUP_NEWS", "true").lower() in ("1", "true", "yes")


def _fallback_image() -> str:
    return os.environ.get(
        "NEWS_FALLBACK_IMAGE_URL",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6e/Football_%28soccer_ball%29.svg/240px-Football_%28soccer_ball%29.svg.png",
    )


class WorldCupNewsService:
    def __init__(
        self,
        *,
        news: NewsDAO | None = None,
        users: UserDAO | None = None,
        matches: MatchDAO | None = None,
        job_ctrl: JobCtrlDAO | None = None,
        curation: NewsCurationService | None = None,
        broadcast_fn: Callable[..., tuple[int, int]] | None = None,
    ):
        self._news = news or NewsDAO()
        self._users = users or UserDAO()
        self._matches = matches or MatchDAO()
        self._job_ctrl = job_ctrl or JobCtrlDAO()
        self._curation = curation or NewsCurationService(news=self._news)
        self._broadcast_fn = broadcast_fn

    def list_delivery_targets(self) -> list[dict[str, Any]]:
        return self._users.list_news_delivery_targets()

    def run_pre_slot(
        self,
        slot: str,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        if not _enabled():
            return {"status": "SKIPPED", "reason": "disabled"}
        matches = self._matches.list_matches()
        if sched.news_phase(matches) != "PRE":
            return {"status": "SKIPPED", "reason": "not_pre_phase"}
        if not force and not sched.pre_slot_window_ok(slot):  # type: ignore[arg-type]
            return {"status": "SKIPPED", "reason": "outside_window"}
        run_date = sched.local_today_iso()
        ctrl_key = sched.job_ctrl_slot_key(run_date, slot)
        if not force and self._job_ctrl.is_processed(JOB_PRE, ctrl_key):
            return {"status": "SKIPPED", "reason": "already_processed", "slot": slot}
        automated_slot = f"PRE:{slot}"
        return self._publish_automated(
            slot=slot,
            automated_slot=automated_slot,
            job_name=JOB_PRE,
            ctrl_key=ctrl_key,
            run_date=run_date,
            force=force,
        )

    def run_live_poll(self, *, force: bool = False) -> dict[str, Any]:
        if not _enabled():
            return {"status": "SKIPPED", "reason": "disabled"}
        matches = self._matches.list_matches()
        if sched.news_phase(matches) != "LIVE":
            return {"status": "SKIPPED", "reason": "not_live_phase"}
        day_sched = sched.compute_live_day_schedule(matches)
        if not day_sched:
            return {"status": "SKIPPED", "reason": "no_matches_today"}
        results: list[dict[str, Any]] = []
        if force or sched.should_publish_pre_matchday(day_sched):
            ctrl_key = sched.job_ctrl_slot_key(day_sched.idempotency_date, "PRE_MATCHDAY")
            if force or not self._job_ctrl.is_processed(JOB_LIVE, ctrl_key):
                results.append(
                    self._publish_automated(
                        slot="PRE_MATCHDAY",
                        automated_slot="LIVE:PRE_MATCHDAY",
                        job_name=JOB_LIVE,
                        ctrl_key=ctrl_key,
                        run_date=day_sched.idempotency_date,
                        force=force,
                    )
                )
            else:
                results.append({"status": "SKIPPED", "slot": "PRE_MATCHDAY", "reason": "already_processed"})
        if force or sched.should_publish_post_matchday(day_sched):
            ctrl_key = sched.job_ctrl_slot_key(day_sched.idempotency_date, "POST_MATCHDAY")
            if force or not self._job_ctrl.is_processed(JOB_LIVE, ctrl_key):
                results.append(
                    self._publish_automated(
                        slot="POST_MATCHDAY",
                        automated_slot="LIVE:POST_MATCHDAY",
                        job_name=JOB_LIVE,
                        ctrl_key=ctrl_key,
                        run_date=day_sched.idempotency_date,
                        force=force,
                    )
                )
            else:
                results.append({"status": "SKIPPED", "slot": "POST_MATCHDAY", "reason": "already_processed"})
        if not results:
            return {"status": "SKIPPED", "reason": "outside_live_windows"}
        return {"status": "OK", "results": results}

    def _publish_automated(
        self,
        *,
        slot: str,
        automated_slot: str,
        job_name: str,
        ctrl_key: str,
        run_date: str,
        force: bool,
    ) -> dict[str, Any]:
        exclude = {n.get("url_hash") for n in self._news.list_published_on_date(run_date) if n.get("url_hash")}
        curated = self._curation.curate_for_slot(
            slot,
            exclude_url_hashes=exclude,
            run_date=run_date,
        )
        if not curated:
            return {"status": "SKIPPED", "reason": "no_candidate", "slot": slot}
        news_id = str(uuid.uuid4())
        item = {
            **curated,
            "news_id": news_id,
            "source_type": "AUTOMATED",
            "automated_slot": automated_slot,
            "published_by": "SYSTEM",
        }
        return self._finalize_publish(
            news_id,
            item,
            job_name=job_name,
            ctrl_key=ctrl_key,
            force=force,
        )

    def publish_admin(self, admin_user_id: str, draft: dict[str, Any]) -> dict[str, Any]:
        news_id = str(uuid.uuid4())
        url = (draft.get("article_url") or "").strip()
        if not url:
            raise ValueError("article_url required")
        item = {
            "news_id": news_id,
            "headline": draft.get("headline") or "Noticia",
            "summary": draft.get("summary") or "",
            "article_url": url,
            "url_hash": draft.get("url_hash"),
            "image_url": draft.get("image_url") or _fallback_image(),
            "category": draft.get("category") or "Mundial 2026",
            "subcategory": draft.get("subcategory") or "#Noticias",
            "source_label": draft.get("source_label") or "Admin",
            "relevance_score": int(draft.get("relevance_score") or 90),
            "source_type": "ADMIN",
            "run_date": sched.local_today_iso(),
            "published_by": admin_user_id,
        }
        return self._finalize_publish(news_id, item, job_name=None, ctrl_key=None, force=True)

    def _finalize_publish(
        self,
        news_id: str,
        item: dict[str, Any],
        *,
        job_name: str | None,
        ctrl_key: str | None,
        force: bool,
    ) -> dict[str, Any]:
        url = item["article_url"]
        if self._news.is_url_published(url) and not force:
            return {"status": "SKIPPED", "reason": "url_dedup", "news_id": news_id}
        if not item.get("url_hash"):
            from src.dao.dynamo.news_dao import url_hash as uh

            item["url_hash"] = uh(url)
        if not item.get("image_url"):
            item["image_url"] = _fallback_image()
        self._news.put_details(news_id, item)
        self._news.mark_url_published(url, news_id)
        caption = format_news_caption(item)
        sent = 0
        if self._broadcast_fn:
            sent, _skipped = self._broadcast_fn(
                news_id=news_id,
                caption=caption,
                image_url=item["image_url"],
                like_count=0,
            )
            self._news.set_broadcast_sent(news_id, sent)
        if job_name and ctrl_key:
            self._job_ctrl.mark_processed(
                job_name,
                ctrl_key,
                meta={"news_id": news_id, "sent": sent},
            )
        return {
            "status": "OK",
            "news_id": news_id,
            "sent_count": sent,
            "headline": item.get("headline"),
        }

    def record_like(self, user_id: str, news_id: str) -> tuple[bool, int]:
        if not self._news.get_details(news_id):
            return False, 0
        created = self._news.put_like(news_id, user_id)
        if created:
            count = self._news.increment_like_count(news_id, 1)
            return True, count
        return False, int((self._news.get_details(news_id) or {}).get("like_count") or 0)

    def record_read(self, user_id: str, news_id: str) -> bool:
        if not self._news.get_details(news_id):
            return False
        created = self._news.put_read(news_id, user_id)
        if created:
            self._news.increment_read_count(news_id, 1)
        return True

    def list_today_for_admin(self) -> list[dict[str, Any]]:
        run_date = sched.local_today_iso()
        items = self._news.list_published_on_date(run_date)
        items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
        return items

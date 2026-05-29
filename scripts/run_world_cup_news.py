#!/usr/bin/env python3
"""Dry-run / dev — noticias Mundial SPEC-2026-046.

  python3 scripts/run_world_cup_news.py --profile asap_dev --env dev --slot MORNING
  python3 scripts/run_world_cup_news.py --live-poll --force
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


def main() -> None:
    p = argparse.ArgumentParser(description="World Cup News job")
    p.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "asap_dev"))
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--env", default="dev")
    p.add_argument("--slot", choices=("MORNING", "EVENING", "PRE_MATCHDAY", "POST_MATCHDAY"))
    p.add_argument("--live-poll", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="Solo curación, sin broadcast ni JOB_CTRL")
    args = p.parse_args()

    from src.dao.dynamo.table import configure_aws
    from src.services.news_curation_service import NewsCurationService
    from src.services.world_cup_news_service import WorldCupNewsService

    configure_aws(profile=args.profile, region=args.region)
    os.environ.setdefault("ENV", args.env)
    os.environ.setdefault("DYNAMODB_TABLE", f"ProdeTable-{args.env}")
    os.environ.setdefault("ENABLE_WORLD_CUP_NEWS", "true")

    if args.dry_run:
        slot = args.slot or "MORNING"
        curated = NewsCurationService().curate_for_slot(slot)
        print(json.dumps(curated, indent=2, ensure_ascii=False))
        return

    def _broadcast(**kwargs) -> tuple[int, int]:
        from src.services.news_broadcast import broadcast_news_to_targets

        targets = WorldCupNewsService().list_delivery_targets()
        print(f"targets={len(targets)}", file=sys.stderr)
        return broadcast_news_to_targets(
            delivery_targets=targets,
            news_id=kwargs["news_id"],
            caption=kwargs["caption"],
            image_url=kwargs["image_url"],
            like_count=kwargs["like_count"],
        )

    svc = WorldCupNewsService(broadcast_fn=_broadcast)
    if args.live_poll:
        result = svc.run_live_poll(force=args.force)
    elif args.slot in ("MORNING", "EVENING"):
        result = svc.run_pre_slot(args.slot, force=args.force)
    else:
        p.error("--slot MORNING|EVENING o --live-poll")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

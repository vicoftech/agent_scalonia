"""GroupUpgradeService — SPEC-2026-044."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.services.group_upgrade_service import GroupUpgradeService, PROMO_PRICES, UNIT_LIST_PRICE


def test_quote_promo_table():
    svc = GroupUpgradeService(matches=MagicMock())
    with patch.object(svc, "is_promo_period", return_value=True):
        total, promo, _ = svc.quote_units(2)
    assert promo is True
    assert total == PROMO_PRICES[2]


def test_quote_full_price_after_promo():
    svc = GroupUpgradeService(matches=MagicMock())
    with patch.object(svc, "is_promo_period", return_value=False):
        total, promo, _ = svc.quote_units(2)
    assert promo is False
    assert total == 2 * UNIT_LIST_PRICE


def test_max_owned_groups_with_extra_slots():
    svc = GroupUpgradeService()
    assert svc.max_owned_groups({"extra_owned_group_slots": 2}) == 3


def test_allocation_units_count():
    svc = GroupUpgradeService()
    alloc = [
        {"type": "NEW_GROUP"},
        {"type": "MEMBER_PACK", "group_id": "g1", "packs": 2},
    ]
    assert svc._allocation_units(alloc) == 3


def test_apply_allocation_member_pack():
    groups = MagicMock()
    users = MagicMock()
    groups.get_group.return_value = {
        "name": "Scaloneta",
        "owner_id": "u1",
        "max_members": 5,
        "is_global": False,
    }
    users.get_profile.return_value = {
        "pending_group_upgrade_units": 1,
        "extra_owned_group_slots": 0,
    }
    svc = GroupUpgradeService(groups=groups, users=users)
    summary = svc.apply_allocation(
        "u1",
        [{"type": "MEMBER_PACK", "group_id": "g1", "packs": 1}],
    )
    groups.update_group.assert_called_once_with("g1", max_members=10)
    assert "10" in summary


def test_is_promo_when_mex_rsa_not_veda():
    matches = MagicMock()
    matches.find_by_teams.return_value = {"veda_active": False}
    svc = GroupUpgradeService(matches=matches)
    assert svc.is_promo_period() is True

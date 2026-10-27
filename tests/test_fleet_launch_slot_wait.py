"""Regression coverage for the provisional fleet launcher's slot-wait bound."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONFIG = _REPO_ROOT / "fleet-launch" / "config.sh"
_DISPATCH = _REPO_ROOT / "fleet-launch" / "dispatch-dual.sh"


def test_slot_wait_defaults_to_one_day() -> None:
    config = _CONFIG.read_text(encoding="utf-8")

    assert ': "${FLEET_LAUNCH_MAX_WAIT_S:=86400}"' in config


def test_slot_wait_give_up_names_item_and_queue_ticket() -> None:
    dispatch = _DISPATCH.read_text(encoding="utf-8")

    assert "give_up() {" in dispatch
    assert (
        "no slot within ${FLEET_LAUNCH_MAX_WAIT_S}s: give up "
        "item=$ITEM queue-ticket=${ticket:-none}"
    ) in dispatch
    assert dispatch.count("no slot within ${FLEET_LAUNCH_MAX_WAIT_S}s: give up") == 1

"""Tests for the ID generator."""

import re

from livespec_orchestrator_beads_fabro._ids import new_work_item_id


def test_new_work_item_id_uses_configured_prefix() -> None:
    """bd enforces that an issue id's prefix equals the tenant DB name
    (the `prefix == database` rule), so a hardcoded `li-` id is rejected
    with `prefix mismatch`. The generator must mint `<prefix>-<suffix>`
    using the configured tenant prefix.
    """
    assert re.fullmatch(r"livespec-[a-z2-7]{6}", new_work_item_id(prefix="livespec")) is not None


def test_work_item_id_honors_a_different_prefix() -> None:
    assert new_work_item_id(prefix="otherrepo").startswith("otherrepo-")


def test_work_item_id_is_not_hardcoded_li() -> None:
    """The legacy hardcoded `li-` prefix must NOT appear when a different
    tenant prefix is configured.
    """
    assert not new_work_item_id(prefix="acme").startswith("li-")


def test_ids_are_distinct_across_calls() -> None:
    seen = {new_work_item_id(prefix="livespec") for _ in range(100)}
    assert len(seen) == 100  # collision probability is astronomically low


def test_suffix_is_six_base32_chars_preserved() -> None:
    """The legacy random-suffix generation (6 lowercase base32 chars) is
    preserved; only the prefix changed.
    """
    work_id = new_work_item_id(prefix="livespec")
    suffix = work_id.split("-", 1)[1]
    assert re.fullmatch(r"[a-z2-7]{6}", suffix) is not None

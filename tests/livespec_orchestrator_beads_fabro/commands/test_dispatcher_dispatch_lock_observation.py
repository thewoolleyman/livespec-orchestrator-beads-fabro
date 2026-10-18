"""The FOUR answers one dispatch-lock location can give.

`live_dispatch_lock` beside it answers two, and the collapse is correct for
its caller: the WIP-cap accounting over-counts when in doubt, which is the
safe direction there. A claim RELEASE has the opposite asymmetry — an
unreadable lock read as an absent one hands a live dispatch's item back to the
queue — so the richer reading is its own surface over the same reader.

ONE CASE IS THE DISCRIMINATOR and the rest are its controls: a lock file whose
PARENT is missing and a lock file that will not parse are both `None` through
the two-valued reader, and they must not be the same answer here.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    LOCK_ABSENT,
    LOCK_DEAD,
    LOCK_LIVE,
    LOCK_UNREADABLE,
    dispatch_lock_path,
    live_dispatch_lock,
    observe_dispatch_lock,
)

_ITEM_ID = "bd-ib-lockobs"


def _write(*, repo: Path, payload: object) -> None:
    path = dispatch_lock_path(repo=repo, work_item_id=_ITEM_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    _ = path.write_text(text, encoding="utf-8")


def test_an_absent_lock_and_an_unparseable_one_are_different_answers(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    missing.mkdir()
    broken = tmp_path / "broken"
    broken.mkdir()
    _write(repo=broken, payload="not json")

    assert observe_dispatch_lock(repo=missing, work_item_id=_ITEM_ID) == LOCK_ABSENT
    assert observe_dispatch_lock(repo=broken, work_item_id=_ITEM_ID) == LOCK_UNREADABLE
    # The two-valued reader beside it cannot tell them apart, which is exactly
    # why this surface exists.
    assert live_dispatch_lock(repo=missing, work_item_id=_ITEM_ID) is None
    assert live_dispatch_lock(repo=broken, work_item_id=_ITEM_ID) is None


@pytest.mark.parametrize(
    "payload",
    [
        [1, 2],
        {"work_item_id": "bd-ib-other", "pid": 1, "started_at_epoch": 1.0},
        {"work_item_id": _ITEM_ID, "pid": 0, "started_at_epoch": 1.0},
        {"work_item_id": _ITEM_ID, "pid": "one", "started_at_epoch": 1.0},
        {"work_item_id": _ITEM_ID, "pid": 1, "started_at_epoch": "soon"},
    ],
)
def test_every_payload_whose_shape_cannot_be_read_is_unreadable(
    *, tmp_path: Path, payload: object
) -> None:
    _write(repo=tmp_path, payload=payload)

    assert observe_dispatch_lock(repo=tmp_path, work_item_id=_ITEM_ID) == LOCK_UNREADABLE


def test_a_readable_lock_reports_whether_its_holder_is_alive(tmp_path: Path) -> None:
    alive = tmp_path / "alive"
    alive.mkdir()
    gone = tmp_path / "gone"
    gone.mkdir()
    _write(
        repo=alive,
        payload={
            "work_item_id": _ITEM_ID,
            "pid": os.getpid(),
            "started_at_epoch": time.time(),
            "dispatch_id": "01DISPATCH",
        },
    )
    _write(
        repo=gone,
        payload={
            "work_item_id": _ITEM_ID,
            # A pid no Linux host assigns, so the holder cannot be alive.
            "pid": 2**31 - 1,
            "started_at_epoch": time.time(),
            "dispatch_id": "01DISPATCH",
        },
    )

    assert observe_dispatch_lock(repo=alive, work_item_id=_ITEM_ID) == LOCK_LIVE
    assert observe_dispatch_lock(repo=gone, work_item_id=_ITEM_ID) == LOCK_DEAD


def test_a_lock_path_that_is_a_directory_is_unreadable_rather_than_absent(
    tmp_path: Path,
) -> None:
    """The OSError arm that is not FileNotFoundError, which must not read as absent."""
    path = dispatch_lock_path(repo=tmp_path, work_item_id=_ITEM_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir()

    assert observe_dispatch_lock(repo=tmp_path, work_item_id=_ITEM_ID) == LOCK_UNREADABLE

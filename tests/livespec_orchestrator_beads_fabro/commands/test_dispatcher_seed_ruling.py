"""The operator's durable ruled-seed instruction.

Scenario 185 requires a plain recovery dispatch to be able to use a preserved
tree explicitly chosen by a coordinator.  The body is its durable ledger
carrier, so it has a stable marker and names every fact an independently
running dispatcher needs to verify the ruling.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import dispatcher

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling"
_ITEM = "bd-ib-ltlg4i"
_REF = "refs/heads/needs-human/older-run"
_COMMIT = "a" * 40
_INSTANT = "2026-11-05T18:00:00Z"


def _module_path() -> Path:
    """The seed-ruling concern is a cohesive command helper module."""
    return Path(dispatcher.__file__).parent / "_dispatcher_seed_ruling.py"


def test_a_seed_ruling_comment_has_its_marker_and_every_durable_fact() -> None:
    """A later checkout can recover the ruling from the item's ledger comments."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)

    body = module.seed_ruling_comment_body(
        work_item_id=_ITEM,
        preservation_ref=_REF,
        commit_sha=_COMMIT,
        invoker="coordinator",
        reason="retain the older Red-Green tree",
        instant=_INSTANT,
    )

    assert body.splitlines()[0] == "livespec-seed-ruling"
    for fact in (_ITEM, _REF, _COMMIT, "coordinator", "retain the older Red-Green tree", _INSTANT):
        assert fact in body


def test_the_latest_unconsumed_ruling_is_the_next_recovery_seed_instruction() -> None:
    """A second coordinator decision supersedes an earlier unconsumed one."""
    module = importlib.import_module(_MODULE)
    first = module.seed_ruling_comment_body(
        work_item_id=_ITEM,
        preservation_ref="refs/heads/needs-human/first",
        commit_sha="b" * 40,
        invoker="first-coordinator",
        reason="older decision",
        instant="2026-11-05T18:01:00Z",
    )
    latest = module.seed_ruling_comment_body(
        work_item_id=_ITEM,
        preservation_ref=_REF,
        commit_sha=_COMMIT,
        invoker="coordinator",
        reason="newer decision",
        instant=_INSTANT,
    )

    ruling = module.latest_unconsumed_seed_ruling(
        comments=(first, latest),
        consumed_instants=frozenset(),
    )

    assert ruling is not None
    assert (ruling.preservation_ref, ruling.commit_sha, ruling.instant) == (_REF, _COMMIT, _INSTANT)

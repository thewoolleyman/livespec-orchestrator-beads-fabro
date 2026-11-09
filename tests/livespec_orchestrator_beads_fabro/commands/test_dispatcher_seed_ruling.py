"""The operator's durable ruled-seed instruction.

Scenario 185 requires a plain recovery dispatch to be able to use a preserved
tree explicitly chosen by a coordinator. The body is its durable ledger
carrier, so it has a stable marker and names every fact an independently
running dispatcher needs to verify the ruling.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

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


def test_a_ruling_is_verified_only_when_origin_still_names_its_exact_commit() -> None:
    """A stale or absent ref is a hold, never permission to select another tree."""
    module = importlib.import_module(_MODULE)

    class _Runner:
        def run(self, **_kwargs: object) -> CommandResult:
            return CommandResult(exit_code=0, stdout=f"{_COMMIT}\t{_REF}\n", stderr="")

    assert hasattr(module, "verify_seed_ruling")
    verified = module.verify_seed_ruling(
        runner=_Runner(),
        repo=Path("/repo"),
        ruling=module.SeedRuling(
            work_item_id=_ITEM,
            preservation_ref=_REF,
            commit_sha=_COMMIT,
            invoker="coordinator",
            reason="retain the older Red-Green tree",
            instant=_INSTANT,
        ),
    )

    assert verified == _COMMIT


def test_a_verified_ruling_is_written_to_both_durable_surfaces() -> None:
    """The command's success path leaves a ledger carrier and a journal row."""
    module = importlib.import_module(_MODULE)
    written_comments: list[str] = []
    journaled: list[dict[str, object]] = []
    ruling = module.SeedRuling(
        work_item_id=_ITEM,
        preservation_ref=_REF,
        commit_sha=_COMMIT,
        invoker="coordinator",
        reason="retain the older Red-Green tree",
        instant=_INSTANT,
    )

    result = module.record_verified_seed_ruling(
        ruling=ruling,
        verified_commit=_COMMIT,
        append_comment=written_comments.append,
        append_journal=journaled.append,
    )

    assert result is None
    assert written_comments == [module.seed_ruling_comment_body(**vars(ruling))]
    assert journaled == [
        {
            "stage": "seed-ruling",
            "work_item_id": _ITEM,
            "preservation_ref": _REF,
            "commit_sha": _COMMIT,
            "reason": "retain the older Red-Green tree",
            "instant": _INSTANT,
        }
    ]

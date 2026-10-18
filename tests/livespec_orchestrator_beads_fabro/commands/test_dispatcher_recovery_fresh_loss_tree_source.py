"""The checkpoint-failed published tree, as a source a loss record must account for.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work": "A confirmed absence of
preserved work permits a plain dispatch from the default branch, with that loss
recorded. An unreadable reference is not confirmed absence."

WHY THIS SOURCE NEEDS ITS OWN CASE. The preference order carries a FOURTH source —
the tree a checkpoint-failed run published to a preservation ref, which nothing
else carries, because such a run never reached the `needs_human` node that would
have preserved its terminal tree. The loss record's asked-source list is a count
of the round trips a reading actually spent, so a build that asks four sources
while naming three reports a measurement it did not take, in the one direction
that matters: an operator who finds preserved work after a `fresh` route reads
that list to tell a source that answered nothing from a source this build never
asked, and the source missing from the list is exactly the one carrying work no
other source could have held.

WHY THE CONTROL IS THE LOAD-BEARING CASE, as it is for the sibling module. A build
that appended this source's name UNCONDITIONALLY satisfies the first case exactly
as well as one that reports what it asked — and it is the more natural
implementation, because the source sits unconditionally in the order. But the
round trip is spent only for an item whose journal NAMES a published tree: with no
such row there is no ref the source could exist at, and a reading that recorded it
anyway would claim a fourth round trip where three were taken. The two cases are
therefore read off the same journal shape with only that row differing, and each
asserts the recorded list against the `ls-remote` calls the pass actually made
rather than against a list this file also hardcodes in isolation.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

import pytest

# Import order is load-bearing; see `test_dispatcher_recovery_routing_resume.py`
# for the cycle this leading import breaks.
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission as _admission,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_recovery_launch as launch,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_recovery_routing as routing,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    PRESERVED_TREE_STAGE,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ = _admission

_ITEM_ID = "bd-ib-kn7ktk"
_RUN = "01M52R2WND7Y0000000000000Z"
_DISPATCH = "c1d2e3f405968788a9babbcbddcedfe0"

_ROUTE_STAGE = "recovery-route"
_ROUTE_FRESH = "fresh"
_PRESERVED_ABSENT = "absent"

# The four preserved-work sources, in the clause's own preference order, as the
# stable tokens the loss row names them by. Spelled as literals for the reason the
# sibling module records: this module's Red predates the name that carries the
# fourth one, and a Red's test bytes are fixed across its Red-to-Green pair.
_SOURCE_TERMINAL_TREE = "needs-human-terminal-tree"
_SOURCE_CHECKPOINT_FAILED_PUBLISHED_TREE = "checkpoint-failed-published-tree"
_SOURCE_PUBLISHED_HEAD = "observed-published-head"
_SOURCE_EARLIER_PRESERVED_PUBLISH_REF = "earlier-preserved-publish-ref"

# The published tree's own ref, and the base commit that tree was taken against.
# The ref ENDS in the published commit, which is what lets this source's probe be
# told apart from the earlier-preserved-publish-ref probe below: the two share one
# ref namespace and nothing in a ref NAME distinguishes them, so the needles must.
_PUBLISHED_TREE_COMMIT = "c" * 40
_BASE_COMMIT = "5d511335aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_TREE_REF = f"refs/livespec/preserved-publish/{_ITEM_ID}/{_PUBLISHED_TREE_COMMIT}"

# What each source name is read off in the pass's own command log, which is what
# makes the recorded list a measurement rather than a second hardcoded constant.
# The last two are deliberately NOT substrings of one another: the glob carries a
# trailing `*` that no exact ref does.
_SOURCE_PROBES = {
    _SOURCE_TERMINAL_TREE: "refs/heads/needs-human/",
    _SOURCE_CHECKPOINT_FAILED_PUBLISHED_TREE: _TREE_REF,
    _SOURCE_PUBLISHED_HEAD: f"refs/heads/feat/{_ITEM_ID}",
    _SOURCE_EARLIER_PRESERVED_PUBLISH_REF: f"refs/livespec/preserved-publish/{_ITEM_ID}/*",
}


class _Shell:
    """A scripted seam that answers an empty exit 0 for anything it is not told about.

    An empty success is the RIGHT default here, as it is for the sibling module:
    both cases are about sources that were asked and named NOTHING, which is
    exactly what an empty `ls-remote` listing is. `calls` is class state because
    every party in the pass builds its own runner, and it is what lets each
    recorded source name be checked against a round trip that actually happened.
    """

    answers: ClassVar[dict[str, CommandResult]] = {}
    calls: ClassVar[list[str]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        joined = " ".join(argv)
        _Shell.calls.append(joined)
        for needle, result in _Shell.answers.items():
            if needle in joined:
                return result
        return CommandResult(exit_code=0, stdout="", stderr="")


def _work_item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="A released item whose failed run preserved nothing",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _journal(*, tmp_path: Path, records: Sequence[dict[str, object]]) -> JournalFile:
    """A journal written directly, because `append` stamps an invoker no writer supplies."""
    journal = JournalFile(path=tmp_path / "fabro-dispatch-journal.jsonl")
    _ = journal.path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8"
    )
    return journal


def _rows(*, journal: JournalFile, stage: str) -> tuple[dict[str, Any], ...]:
    written = (
        json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line
    )
    return tuple(record for record in written if record.get("stage") == stage)


def _args(*, repo: Path, journal: JournalFile) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(journal.path),
        workflow_name="implement-work-item",
        fabro_bin="/usr/local/bin/fabro",
    )


def _released(*, published_tree: bool) -> tuple[dict[str, object], ...]:
    """One released history, optionally naming a published tree for this item.

    The `preserved-tree` row is the ONLY difference between the two cases, which
    is what makes the second one a control: everything else that decides the route
    is held identical.
    """
    history: list[dict[str, object]] = [
        {"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": _DISPATCH},
        {"stage": "fabro-run", "work_item_id": _ITEM_ID, "run_id": _RUN},
        {"stage": "provider-limit-release", "work_item_id": _ITEM_ID, "run_id": _RUN},
    ]
    if published_tree:
        history.insert(
            2,
            {
                "stage": PRESERVED_TREE_STAGE,
                "work_item_id": _ITEM_ID,
                "run_id": _RUN,
                "factory": "hp",
                "base_commit": _BASE_COMMIT,
                "preservation_ref": _TREE_REF,
                "preservation_commit": _PUBLISHED_TREE_COMMIT,
            },
        )
    return tuple(history)


def _route_row(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    records: Sequence[dict[str, object]],
) -> dict[str, Any]:
    """Route the one released candidate, journal its route, and return that one row.

    The route is journaled through the launch's own writer rather than assembled
    here, because the row an operator greps is the one that writer produces.
    """
    journal = _journal(tmp_path=tmp_path, records=records)
    _Shell.answers = {"gh pr list": CommandResult(exit_code=0, stdout="[]", stderr="")}
    _Shell.calls = []
    monkeypatch.setattr(ShellCommandRunner, "run", _Shell.run)

    routed = routing.route_recovery(
        args=_args(repo=tmp_path, journal=journal),
        repo=tmp_path,
        candidates=[_work_item()],
        journal=journal,
    )
    launch.journal_recovery_route(route=routed.route_for(work_item_id=_ITEM_ID), journal=journal)
    rows = _rows(journal=journal, stage=_ROUTE_STAGE)
    assert len(rows) == 1
    return rows[0]


def _asked() -> tuple[str, ...]:
    """Which of the four sources this pass actually spent a round trip on."""
    return tuple(
        name
        for name, probe in _SOURCE_PROBES.items()
        if any(probe in call and "ls-remote" in call for call in _Shell.calls)
    )


def test_a_loss_record_names_the_published_tree_source_it_asked_and_found_nothing_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All four sources asked, all four named, in the clause's own preference order.

    The item's journal names a published tree, so origin IS asked whether that ref
    still stands; it answers nothing, which is absence at that source rather than
    an unreadable reference, so the search falls through to confirmed absence. The
    loss row must account for the round trip that was spent there.
    """
    row = _route_row(
        tmp_path=tmp_path, monkeypatch=monkeypatch, records=_released(published_tree=True)
    )

    assert _asked() == (
        _SOURCE_TERMINAL_TREE,
        _SOURCE_CHECKPOINT_FAILED_PUBLISHED_TREE,
        _SOURCE_PUBLISHED_HEAD,
        _SOURCE_EARLIER_PRESERVED_PUBLISH_REF,
    )
    assert row["route"] == _ROUTE_FRESH
    assert row["preserved_work"] == _PRESERVED_ABSENT
    assert row["source_run_id"] == _RUN
    assert row["preservation_sources_asked"] == list(_asked())


def test_an_item_naming_no_published_tree_records_no_round_trip_for_that_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: this source's name is a reading, not a fixture of the order.

    With no `preserved-tree` row there is no ref the source could exist at, so the
    round trip is never spent. A build that named it unconditionally would pass the
    case above, which is why this one has to sit beside it.
    """
    row = _route_row(
        tmp_path=tmp_path, monkeypatch=monkeypatch, records=_released(published_tree=False)
    )

    assert _SOURCE_CHECKPOINT_FAILED_PUBLISHED_TREE not in _asked()
    assert _asked() == (
        _SOURCE_TERMINAL_TREE,
        _SOURCE_PUBLISHED_HEAD,
        _SOURCE_EARLIER_PRESERVED_PUBLISH_REF,
    )
    assert row["route"] == _ROUTE_FRESH
    assert row["preservation_sources_asked"] == list(_asked())

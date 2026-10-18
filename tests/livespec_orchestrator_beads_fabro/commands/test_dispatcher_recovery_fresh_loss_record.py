"""The loss a `fresh`-after-absence route records: whose work, and what was asked.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work": "A confirmed absence of
preserved work permits a plain dispatch from the default branch, with that loss
recorded. An unreadable reference is not confirmed absence."

WHY THE ROW NEEDS MORE THAN THE WORD `absent`. `fresh`-after-absence is the one
route that DISCARDS a dead run's work, and the row is the only durable account of
it. A row saying nothing but "absent" leaves an operator who finds preserved work
afterwards unable to tell which of the two things went wrong: the run whose tree
was lost is unnamed, so they cannot look it up on the factory, and the sources
that were asked are unnamed, so they cannot tell a source that answered nothing
from a source this build never asked. `source_run_id` answers the first and the
asked-source list answers the second, which is what makes the row a measurement
rather than a conclusion.

WHY THE SECOND CASE IS THE LOAD-BEARING ONE. A build that wrote the three source
names as a CONSTANT satisfies the first case exactly as well as one that reports
what it asked — and it is the more natural implementation, because confirmed
absence normally means all three were asked. The terminal source is per RUN, so
an item naming no earlier run identifier has no ref it could exist at and that
round trip is never spent; a reading that recorded three sources there would be
recording a round trip that did not happen. The two cases are therefore read off
the SAME journal shape with only the identifier history differing, and each
asserts the asked-source list against the `ls-remote` calls the pass actually
made rather than against a list this file also hardcodes in isolation.
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
from livespec_orchestrator_beads_fabro.types import WorkItem

_ = _admission

_ITEM_ID = "bd-ib-kn7ktk"
_RUN = "01M52R2WND7Y0000000000000Z"
_DISPATCH = "c1d2e3f405968788a9babbcbddcedfe0"

# The journal stage and the two field values this file reads. Spelled as literals
# because this module's Red predates the names that carry them, and a Red's test
# bytes are fixed across its Red-to-Green pair.
_ROUTE_STAGE = "recovery-route"
_ROUTE_FRESH = "fresh"
_PRESERVED_ABSENT = "absent"

# The three preserved-work sources, in the clause's own preference order, as the
# stable tokens the loss row names them by.
_SOURCE_TERMINAL_TREE = "needs-human-terminal-tree"
_SOURCE_PUBLISHED_HEAD = "observed-published-head"
_SOURCE_EARLIER_PRESERVED_PUBLISH_REF = "earlier-preserved-publish-ref"

# What each source name is read off in the pass's own command log, which is what
# makes the recorded list a measurement rather than a second hardcoded constant.
_SOURCE_PROBES = {
    _SOURCE_TERMINAL_TREE: "refs/heads/needs-human/",
    _SOURCE_PUBLISHED_HEAD: f"refs/heads/feat/{_ITEM_ID}",
    _SOURCE_EARLIER_PRESERVED_PUBLISH_REF: f"refs/livespec/preserved-publish/{_ITEM_ID}/*",
}

_ROUTE_ROW_KEYS = (
    "stage",
    "work_item_id",
    "route",
    "preserved_work",
    "source_run_id",
    "remote",
    "commit_sha",
    "preservation_ref",
    "preservation_sources_asked",
)


class _Shell:
    """A scripted seam that answers an empty exit 0 for anything it is not told about.

    An empty success is the RIGHT default here, unlike the wave modules' seams:
    both cases below are about sources that were asked and named NOTHING, which
    is exactly what an empty `ls-remote` listing is. `calls` is class state for
    the reason the sibling modules record — every party in the pass builds its
    own runner — and it is what lets each recorded source name be checked against
    a round trip that actually happened.
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


def _route_row(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    records: Sequence[dict[str, object]],
) -> dict[str, Any]:
    """Route the one released candidate, journal its route, and return that one row.

    The route is journaled through the launch's own writer rather than assembled
    here, because the row an operator greps is the one that writer produces: a
    case that built the record itself would pass for a build whose launch path
    never carried the loss into it.
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
    """Which of the three sources this pass actually spent a round trip on."""
    return tuple(
        name
        for name, probe in _SOURCE_PROBES.items()
        if any(probe in call and "ls-remote" in call for call in _Shell.calls)
    )


def test_a_fresh_route_after_confirmed_absence_names_the_lost_run_and_every_asked_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole loss record, for a released item whose three sources all named nothing.

    The row names the earlier run under `source_run_id` — the identifier an
    operator looks the dead run up on its factory by — and lists all three
    preservation sources, each of which the command log shows was genuinely
    asked.
    """
    row = _route_row(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        records=(
            {"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": _DISPATCH},
            {"stage": "fabro-run", "work_item_id": _ITEM_ID, "run_id": _RUN},
            {"stage": "provider-limit-release", "work_item_id": _ITEM_ID, "run_id": _RUN},
        ),
    )

    assert _asked() == (
        _SOURCE_TERMINAL_TREE,
        _SOURCE_PUBLISHED_HEAD,
        _SOURCE_EARLIER_PRESERVED_PUBLISH_REF,
    )
    # `get` rather than indexing, so a key the row does not carry fails as the
    # assertion it is rather than as a `KeyError` that reads like a broken test.
    assert {key: row.get(key) for key in _ROUTE_ROW_KEYS} == {
        "stage": _ROUTE_STAGE,
        "work_item_id": _ITEM_ID,
        "route": _ROUTE_FRESH,
        "preserved_work": _PRESERVED_ABSENT,
        "source_run_id": _RUN,
        "remote": None,
        "commit_sha": None,
        "preservation_ref": None,
        "preservation_sources_asked": list(_asked()),
    }


def test_an_item_naming_no_earlier_run_records_only_the_sources_it_could_ask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the asked-source list is a reading, not a constant.

    The terminal-tree ref is per RUN, so an item whose history names no run
    identifier has no ref that source could exist at and the round trip is never
    spent. A build writing the three names unconditionally would report a
    measurement it never took — and it would pass the case above, which is why
    this one has to sit beside it. `source_run_id` is empty for the same reason
    the seed's own leading-identifier helper leaves it empty: there is no run to
    name, and a record whose other fields are present says more than no record.
    """
    row = _route_row(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        records=({"stage": "provider-limit-release", "work_item_id": _ITEM_ID},),
    )

    assert _asked() == (_SOURCE_PUBLISHED_HEAD, _SOURCE_EARLIER_PRESERVED_PUBLISH_REF)
    assert row["route"] == _ROUTE_FRESH
    assert row["preserved_work"] == _PRESERVED_ABSENT
    assert row["source_run_id"] == ""
    assert row["preservation_sources_asked"] == list(_asked())

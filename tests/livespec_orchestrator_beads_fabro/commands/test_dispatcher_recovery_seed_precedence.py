"""One table over every preserved-work source recovery routing seeds from, and which wins.

WHY A TABLE, AND WHY ONE. Two fixes each kept their own rule's tests green while
silently reordering the other's: `bd-ib-v6br5b` ranked the latest run's
highest-numbered work-in-progress capture over the observed published head and
over every preservation ref of an earlier run, and `bd-ib-so6fef` then widened the
needs-human lookup to every earlier run and dropped the latest-run scope of the
checkpoint-failed tree row, which put an earlier run's ref back above that
capture. A rule asserted by a test of its own cannot notice another rule moving
underneath it; a pair asserted in one place can. Every row below names the sources
that stand on origin and the ref routing must take, so a change to ONE rule that
reorders ANOTHER turns exactly one row red.

THE ORDER, HIGHEST FIRST, as the recovery clause of `contracts.md` (the ACP
fallback priority section, on the failed run's preserved work) states it for the
sources `verified_preserved_seed` ranks:

1. a needs-human ref or failed-checkpoint preservation ref published at the LATEST
   run's ending;
2. the latest run's highest-numbered work-in-progress ref;
3. an earlier run's needs-human ref or failed-checkpoint preservation ref, which
   outranks the observed published head only when its run is the head's run or a
   later one;
4. the observed published head;
5. a preserved-publish ref an earlier reclaim left behind.

A non-fallback refusal, a current ruling and an admitted resume rank above all of
them and are decided before this function is asked (`_dispatcher_recovery_routing`
grades them first), so they have no row here.

Every row also stands the LOWER-ranked sources on origin beside the winner: a row
whose origin held only the winner would be satisfied by a build that ignored every
other source. The WIP captures are numbered 1, 9 and 10 so that a reading that
orders them as text takes 9.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    PRESERVED_TREE_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    verified_preserved_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed

_ITEM = "bd-ib-prec"
_EARLIER = "01EARLIERRUN0000000000000A"
_LATEST = "01LATESTRUN00000000000000B"

_NH_EARLIER = f"refs/heads/needs-human/{_EARLIER}"
_NH_LATEST = f"refs/heads/needs-human/{_LATEST}"
_NH_EARLIER_COMMIT = "a1" * 20
_NH_LATEST_COMMIT = "a2" * 20

_WIP = f"refs/livespec/wip/{_ITEM}/{_LATEST}"
_WIP_COMMITS = {1: "b1" * 20, 9: "b9" * 20, 10: "b0" * 20}

_PREFIX = f"refs/livespec/preserved-publish/{_ITEM}"
_TREE_EARLIER_COMMIT = "c1" * 20
_TREE_LATEST_COMMIT = "c2" * 20
_TREE_EARLIER = f"{_PREFIX}/{_TREE_EARLIER_COMMIT}"
_TREE_LATEST = f"{_PREFIX}/{_TREE_LATEST_COMMIT}"
_BASE = "d0" * 20

_BRANCH = f"refs/heads/feat/{_ITEM}"
_HEAD = "e0" * 20
_HEAD_PRESERVED = f"{_PREFIX}/{_HEAD}"
_OLD_HEAD = "e1" * 20
_OLD_HEAD_PRESERVED = f"{_PREFIX}/{_OLD_HEAD}"


@dataclass(kw_only=True)
class _Origin:
    """A scripted origin: the refs it carries, answered by `ls-remote` pattern."""

    refs: dict[str, str]
    calls: list[str] = field(default_factory=list[str])

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(" ".join(argv))
        # Every flow the table drives asks origin about refs and nothing else: one
        # rank never holds two needs-human refs, so no committer time or ancestry
        # is ever read.
        assert argv[:3] == ["git", "ls-remote", "origin"]
        lines = [
            f"{commit}\t{ref}"
            for ref, commit in sorted(self.refs.items())
            if any(fnmatch.fnmatchcase(ref, pattern) for pattern in argv[3:])
        ]
        return CommandResult(exit_code=0, stdout="\n".join(lines), stderr="")


@dataclass(frozen=True, kw_only=True)
class _Row:
    """The sources that stand on origin, the journal that dates them, and the winner."""

    refs: dict[str, str]
    wins: str
    tree_run: str | None = None
    head_run: str | None = None
    passed_over: tuple[str, ...] = ()


def _wip() -> dict[str, str]:
    return {f"{_WIP}/{number}": commit for number, commit in _WIP_COMMITS.items()}


_ROWS: dict[str, _Row] = {
    "wip beats an earlier run's needs-human ref": _Row(
        refs={**_wip(), _NH_EARLIER: _NH_EARLIER_COMMIT},
        wins=f"{_WIP}/10",
        passed_over=(_NH_EARLIER,),
    ),
    "wip beats an earlier run's failed-checkpoint preservation ref": _Row(
        refs={**_wip(), _TREE_EARLIER: _TREE_EARLIER_COMMIT},
        tree_run=_EARLIER,
        wins=f"{_WIP}/10",
    ),
    "wip beats the observed published head": _Row(
        refs={**_wip(), _BRANCH: _HEAD},
        head_run=_LATEST,
        wins=f"{_WIP}/10",
    ),
    "wip beats an earlier run's ref and the head together": _Row(
        refs={
            **_wip(),
            _NH_EARLIER: _NH_EARLIER_COMMIT,
            _TREE_EARLIER: _TREE_EARLIER_COMMIT,
            _BRANCH: _HEAD,
        },
        tree_run=_EARLIER,
        head_run=_EARLIER,
        wins=f"{_WIP}/10",
        passed_over=(_NH_EARLIER,),
    ),
    "the latest run's needs-human ref beats its wip": _Row(
        refs={**_wip(), _NH_LATEST: _NH_LATEST_COMMIT, _NH_EARLIER: _NH_EARLIER_COMMIT},
        wins=_NH_LATEST,
        passed_over=(_NH_EARLIER,),
    ),
    "the latest run's failed-checkpoint preservation ref beats its wip": _Row(
        refs={**_wip(), _TREE_LATEST: _TREE_LATEST_COMMIT},
        tree_run=_LATEST,
        wins=_TREE_LATEST,
    ),
    "an earlier run's needs-human ref beats a head its own run published": _Row(
        refs={_NH_EARLIER: _NH_EARLIER_COMMIT, _BRANCH: _HEAD},
        head_run=_EARLIER,
        wins=_NH_EARLIER,
    ),
    "an earlier run's needs-human ref loses to a later run's head": _Row(
        refs={_NH_EARLIER: _NH_EARLIER_COMMIT, _BRANCH: _HEAD},
        head_run=_LATEST,
        wins=_HEAD_PRESERVED,
        passed_over=(_NH_EARLIER,),
    ),
    "an earlier run's preservation ref loses to a later run's head": _Row(
        refs={_TREE_EARLIER: _TREE_EARLIER_COMMIT, _BRANCH: _HEAD},
        tree_run=_EARLIER,
        head_run=_LATEST,
        wins=_HEAD_PRESERVED,
    ),
    "the observed published head beats an earlier reclaim's preserved head": _Row(
        refs={_BRANCH: _HEAD, _OLD_HEAD_PRESERVED: _OLD_HEAD},
        wins=_HEAD_PRESERVED,
    ),
    "an earlier reclaim's preserved head is the last source": _Row(
        refs={_OLD_HEAD_PRESERVED: _OLD_HEAD},
        wins=_OLD_HEAD_PRESERVED,
    ),
}


def _journal(*, row: _Row) -> tuple[dict[str, object], ...]:
    """The dispatch journal in the order the dispatches happened, oldest run first.

    Each run's tree row and published head sit beside THAT run's own record: the
    journal is append-only, so a row for an earlier run written after the latest
    run's record would make the earlier run the newest one the journal names.
    """
    records: list[dict[str, object]] = []
    for run, ref in ((_EARLIER, _TREE_EARLIER), (_LATEST, _TREE_LATEST)):
        records.append({"work_item_id": _ITEM, "run_id": run})
        if row.tree_run == run:
            records.append(
                {
                    "stage": PRESERVED_TREE_STAGE,
                    "work_item_id": _ITEM,
                    "run_id": run,
                    "base_commit": _BASE,
                    "preservation_ref": ref,
                }
            )
        if row.head_run == run:
            records.append({"work_item_id": _ITEM, "run_id": run, "published_head": _HEAD})
    return tuple(records)


@pytest.mark.parametrize("name", list(_ROWS))
def test_the_source_routing_takes_is_the_one_the_precedence_table_names(*, name: str) -> None:
    row = _ROWS[name]
    seed = verified_preserved_seed(
        runner=_Origin(refs=row.refs),
        repo=Path("/repo"),
        work_item_id=_ITEM,
        earlier_run_ids=(_LATEST, _EARLIER),
        journal_records=_journal(row=row),
    )
    assert isinstance(seed, RecoverySeed)
    assert seed.preservation_ref == row.wins
    assert {ref for ref, _ in seed.passed_over_needs_human} == set(row.passed_over)

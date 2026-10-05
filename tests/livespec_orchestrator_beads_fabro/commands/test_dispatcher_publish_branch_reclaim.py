"""Recovering a dead run's publish branch without discarding what it published.

A run that dies AFTER publishing its branch leaves that branch on origin, and the
re-dispatch meant to recover it cannot publish: `publish_draft` pushes a plain
fast-forward, the new run's HEAD is not a descendant of the dead run's tip, and
origin refuses it under `LIVESPEC_PUBLISH_DRAFT_PUSH_FAILED`. That sentinel's own
remedy — clear the stale publish branch and re-dispatch — is what discards the
dead run's published head, so the one documented recovery costs the proof it was
meant to rescue. Measured 2026-10-05 on `bd-ib-qm4luz`: run
01M44F9E56XCEWZNMVJX4M14Z6 published pull request 2581, captured and verified its
Proof of Done there and was approved, then died at the `pr` stage; re-dispatch
01M44PQW4DAJF5J6N1XQNYVKX3 was refused at `publish_draft`, non-fast-forward. In
the same hour `bd-ib-gp2nt5` needed its publish branch preserved and deleted BY
HAND before a re-dispatch could publish.

WHAT IS ASSERTED, AND WHY EACH HALF NEEDS THE OTHER. A valve that cleared every
surviving publish branch would satisfy the dead-run case perfectly well, so the
LIVE-run hold is its control; and a valve that cleared nothing would satisfy that
hold just as well, so the dead-run reclaim is the hold's control. Between them
sits the ordering that makes the act safe: the preserve push is asserted to
precede the delete, because a delete that ran first would discard exactly what
this valve exists to keep.

A FIRST DISPATCH IS ASSERTED TO ASK ORIGIN NOTHING AT ALL. Only an item the
journal has already dispatched can have a previous run's publish branch, so the
question has no possible yes on a first dispatch and the probe is not made —
which is the same early return the proof-assets gate beside it takes for an item
carrying no `factory_captured` assertion, and for the same reason: a remote probe
on a path that needs no answer turns a forge outage into a dispatch-time event.
That early return is what this file asserts, rather than merely the absence of a
mutation, because a valve that probed and then declined would pass the weaker
test.

THE RECLAIM NEVER REWRITES A REF, AND THAT IS ASSERTED DIRECTLY. The ratified
stages clause of `SPECIFICATION/contracts.md` grants a lease-guarded force push
to the `pr` node ALONE and says `publish_draft` "MUST NOT rewrite any other
ref"; the node's own comment in the graph records why a force push must not be
added there to smooth this case over. So every argv this valve issues is
inspected for a force-push spelling, which is what keeps the recovery from being
bought with the capability the graph deliberately withheld.
"""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_reclaim"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_publish_branch_reclaim.py"
)

_ITEM_ID = "bd-ib-qm4luz"
_BRANCH = f"feat/{_ITEM_ID}"
# The head the dead run published, and the one the preserved ref must carry.
_DEAD_HEAD = "9f1c2d3e4f506172839a0b1c2d3e4f5061728394"
# Another item's branch, present in the same `ls-remote` answer: `feat/bd-ib-qm4`
# is a PREFIX of this item's branch, so a suffix or prefix match would attribute
# one item's branch to the other.
_OTHER_BRANCH_LINE = "aaaa000011112222333344445555666677778888\trefs/heads/feat/bd-ib-qm4"

_FORCE_SPELLINGS = ("--force", "--force-with-lease", "-f")
# Every stage this valve writes starts here, which is what lets a pre-seeded
# dispatch history share one journal file with the records under assertion.
_RECLAIM_STAGE_PREFIX = "publish-branch-reclaim"


def _reclaim() -> Any:
    """Import the reclaim module, asserting the file exists first.

    The `is_file()` assertion is what makes this a genuine failing assertion
    before the module is written, rather than a collection-time import error that
    proves only unimportability.
    """
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE)


@dataclass(kw_only=True)
class _Runner:
    """A scripted subprocess seam: one answer per argv substring, exit 0 otherwise.

    Keyed by substring rather than by exact argv so a test states only the thing
    it is scripting, and records every argv in order so the ORDERING assertions
    below read the real sequence rather than a count.
    """

    answers: dict[str, CommandResult] = field(default_factory=dict)
    argvs: list[list[str]] = field(default_factory=list)

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
        self.argvs.append(list(argv))
        joined = " ".join(argv)
        for needle, result in self.answers.items():
            if needle in joined:
                return result
        return CommandResult(exit_code=0, stdout="", stderr="")


def _ls_remote(*, head: str = _DEAD_HEAD) -> CommandResult:
    """An `ls-remote` answer carrying this item's branch and another item's."""
    return CommandResult(
        exit_code=0,
        stdout=f"{_OTHER_BRANCH_LINE}\n{head}\trefs/heads/{_BRANCH}\n",
        stderr="",
    )


def _args() -> argparse.Namespace:
    """The dispatch namespace the valve reads its factory client off.

    `fabro_factory_target` absent is the shape every non-dispatching caller has,
    and the one the valve must tolerate rather than raise on.
    """
    return argparse.Namespace(fabro_bin="/usr/local/bin/fabro")


def _work_item(*, item_id: str) -> WorkItem:
    """A selected candidate, carrying nothing the valve reads but its id."""
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="A run that dies after publishing has no recovery that keeps its proof",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-05T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _journal(*, tmp_path: Path, name: str = "fabro-dispatch-journal.jsonl") -> JournalFile:
    """A journal file carrying nothing: the shape a FIRST dispatch of an item has."""
    return JournalFile(path=tmp_path / name)


def _journal_after_a_previous_dispatch(
    *, tmp_path: Path, name: str = "fabro-dispatch-journal.jsonl", item_ids: Sequence[str]
) -> JournalFile:
    """A journal recording one previous dispatch per named item.

    The record SHAPES are the production ones — the `dispatch-id` stage record
    written before launch and the `fabro-run` record carrying the run id — because
    the valve reads the same file the Dispatcher writes, and a shape invented here
    would prove nothing about the file it reads in production. Written directly
    rather than through `append`, which stamps an invoker no writer may supply.
    """
    journal = _journal(tmp_path=tmp_path, name=name)
    lines = [
        json.dumps(record)
        for item_id in item_ids
        for record in (
            {"stage": "dispatch-id", "work_item_id": item_id, "dispatch_id": f"d-{item_id}"},
            {"stage": "fabro-run", "work_item_id": item_id, "run_id": f"01M44{item_id}"},
        )
    ]
    _ = journal.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return journal


def _records(*, journal: JournalFile) -> tuple[dict[str, Any], ...]:
    """This valve's own records, in order, with any pre-seeded history filtered out."""
    if not journal.path.is_file():
        return ()
    written = (
        json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line
    )
    return tuple(
        record for record in written if str(record.get("stage")).startswith(_RECLAIM_STAGE_PREFIX)
    )


def _issued(*, runner: _Runner, needle: str) -> list[list[str]]:
    return [argv for argv in runner.argvs if needle in " ".join(argv)]


def test_a_dead_runs_publish_branch_is_preserved_by_reference_then_cleared(
    tmp_path: Path,
) -> None:
    """The recovery: the dead run's head survives on a ref, the branch does not.

    Clearing the branch is what lets the re-dispatch's PLAIN push succeed and
    reach proof capture, so the two assertions that matter are that the delete
    was issued and that the preserve push reached origin BEFORE it. The preserved
    ref carries the dead head in its own name, so a second reclaim of the same
    head is idempotent rather than a rewrite.
    """
    module = _reclaim()
    runner = _Runner(answers={"ls-remote": _ls_remote()})
    journal = _journal_after_a_previous_dispatch(tmp_path=tmp_path, item_ids=(_ITEM_ID,))

    module.reclaim_stale_publish_branch(
        args=_args(),
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        journal=journal,
        journal_path=journal.path,
        runner=runner,
    )

    preserved = module.preserved_publish_ref(work_item_id=_ITEM_ID, head=_DEAD_HEAD)
    assert preserved == f"refs/livespec/preserved-publish/{_ITEM_ID}/{_DEAD_HEAD}"
    assert _issued(runner=runner, needle="ls-remote") == [
        ["git", "ls-remote", "origin", f"refs/heads/{_BRANCH}"]
    ]
    # The preserve push and the delete, in that order and no other.
    pushes = _issued(runner=runner, needle="push")
    assert pushes == [
        ["git", "push", "origin", f"{preserved}:{preserved}"],
        ["git", "push", "origin", "--delete", f"refs/heads/{_BRANCH}"],
    ]
    # The head reached the local ref before it was pushed anywhere.
    assert _issued(runner=runner, needle="fetch") == [
        ["git", "fetch", "origin", f"+refs/heads/{_BRANCH}:{preserved}"]
    ]
    assert runner.argvs.index(pushes[0]) > runner.argvs.index(
        ["git", "fetch", "origin", f"+refs/heads/{_BRANCH}:{preserved}"]
    )
    # No ref is REWRITTEN to buy this: the force-push capability stays with `pr`.
    assert [argv for argv in runner.argvs if set(argv) & set(_FORCE_SPELLINGS)] == []
    assert [
        {key: record[key] for key in ("stage", "work_item_id", "branch", "head", "preserved_ref")}
        for record in _records(journal=journal)
    ] == [
        {
            "stage": module.PUBLISH_BRANCH_RECLAIM_STAGE,
            "work_item_id": _ITEM_ID,
            "branch": _BRANCH,
            "head": _DEAD_HEAD,
            "preserved_ref": preserved,
        }
    ]


def test_a_first_dispatch_of_an_item_asks_origin_nothing(tmp_path: Path) -> None:
    """No previous dispatch, no possible surviving branch, so no probe is made.

    Asserted as "NO argv at all" rather than "no mutation", because a valve that
    asked origin and then declined would satisfy the weaker form while still
    putting a remote round trip on the critical path of every first dispatch —
    and turning a forge outage into a dispatch-time event is the failure mode the
    neighbouring proof-assets gate's own early return exists to avoid.
    """
    module = _reclaim()
    runner = _Runner(answers={"ls-remote": _ls_remote()})
    journal = _journal(tmp_path=tmp_path)

    module.reclaim_stale_publish_branch(
        args=_args(),
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        journal=journal,
        journal_path=journal.path,
        runner=runner,
    )

    assert runner.argvs == []
    assert _records(journal=journal) == ()


def test_an_item_whose_publish_branch_origin_does_not_carry_is_left_alone(
    tmp_path: Path,
) -> None:
    """The ordinary first dispatch: one question asked, nothing done, nothing said.

    The `ls-remote` answer deliberately carries ANOTHER item's branch whose name
    is a prefix of this one's, so a valve matching on anything looser than the
    full ref would reclaim a branch belonging to a different item.
    """
    module = _reclaim()
    runner = _Runner(
        answers={
            "ls-remote": CommandResult(exit_code=0, stdout=f"{_OTHER_BRANCH_LINE}\n", stderr="")
        }
    )
    journal = _journal_after_a_previous_dispatch(tmp_path=tmp_path, item_ids=(_ITEM_ID,))

    module.reclaim_stale_publish_branch(
        args=_args(),
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        journal=journal,
        journal_path=journal.path,
        runner=runner,
    )

    assert _issued(runner=runner, needle="ls-remote") != []
    assert _issued(runner=runner, needle="push") == []
    assert _records(journal=journal) == ()


def test_an_unaskable_origin_holds_the_reclaim_and_journals_why(tmp_path: Path) -> None:
    """A gauge that cannot see must not act, and must say that it could not see.

    "Origin did not answer" and "origin carries no such branch" are different
    facts, and the valve must not report the first as the second: a dispatch that
    walked into `publish_draft`'s refusal should carry the measurement that
    stopped the reclaim, rather than look like one that found nothing to do.
    """
    module = _reclaim()
    runner = _Runner(
        answers={"ls-remote": CommandResult(exit_code=128, stdout="", stderr="no origin")}
    )
    journal = _journal_after_a_previous_dispatch(tmp_path=tmp_path, item_ids=(_ITEM_ID,))

    module.reclaim_stale_publish_branch(
        args=_args(),
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        journal=journal,
        journal_path=journal.path,
        runner=runner,
    )

    assert _issued(runner=runner, needle="push") == []
    records = _records(journal=journal)
    assert [record["stage"] for record in records] == [module.PUBLISH_BRANCH_RECLAIM_HELD_STAGE]
    assert records[0]["reason"] == module.HELD_ORIGIN_UNOBSERVABLE
    assert "128" in str(records[0]["detail"])


def test_a_preserve_that_failed_leaves_the_branch_standing(tmp_path: Path) -> None:
    """Preserve THEN reclaim: a failed preserve must not be followed by a delete.

    Both legs of the preserve are tried, because a valve that checked only the
    local fetch would delete the branch whose copy never reached origin — and
    that is the one arm where a hold costs a stalled recovery while proceeding
    costs the published head itself.
    """
    module = _reclaim()
    failed = CommandResult(exit_code=1, stdout="", stderr="")
    # The local fetch failing, then the push of the preserved ref to origin
    # failing: two different ways the copy can fail to become durable.
    failures = ({"fetch": failed}, {f"push origin {module.PRESERVED_PUBLISH_REF_PREFIX}": failed})

    for index, answers in enumerate(failures):
        runner = _Runner(answers={"ls-remote": _ls_remote(), **answers})
        journal = _journal_after_a_previous_dispatch(
            tmp_path=tmp_path, name=f"journal-{index}.jsonl", item_ids=(_ITEM_ID,)
        )

        module.reclaim_stale_publish_branch(
            args=_args(),
            repo=tmp_path,
            work_item_id=_ITEM_ID,
            journal=journal,
            journal_path=journal.path,
            runner=runner,
        )

        assert _issued(runner=runner, needle="--delete") == []
        records = _records(journal=journal)
        assert [record["stage"] for record in records] == [module.PUBLISH_BRANCH_RECLAIM_HELD_STAGE]
        assert records[0]["reason"] == module.HELD_PRESERVE_FAILED
        assert records[0]["head"] == _DEAD_HEAD


def test_a_delete_that_failed_is_reported_rather_than_read_as_a_reclaim(
    tmp_path: Path,
) -> None:
    """The branch still stands, so the record must not claim it was reclaimed.

    This arm is the one an operator acts on by hand, and a reclaim record here
    would tell them the branch is gone while `publish_draft` still refuses.
    """
    module = _reclaim()
    runner = _Runner(
        answers={
            "ls-remote": _ls_remote(),
            "--delete": CommandResult(exit_code=1, stdout="", stderr="protected"),
        }
    )
    journal = _journal_after_a_previous_dispatch(tmp_path=tmp_path, item_ids=(_ITEM_ID,))

    module.reclaim_stale_publish_branch(
        args=_args(),
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        journal=journal,
        journal_path=journal.path,
        runner=runner,
    )

    records = _records(journal=journal)
    assert [record["stage"] for record in records] == [module.PUBLISH_BRANCH_RECLAIM_HELD_STAGE]
    assert records[0]["reason"] == module.HELD_DELETE_FAILED
    assert records[0]["branch"] == _BRANCH


def test_the_wall_entry_point_reclaims_once_per_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shape both pre-dispatch walls call: one reclaim per selected candidate.

    A publish branch is PER ITEM, so a wave entry point that asked about one
    candidate would leave every other candidate's recovery stuck — and the drain
    is the path that selects more than one. The subprocess seam is monkeypatched
    rather than injected, because the walls hand this function no runner: it is
    the one place the production seam is constructed, and a test that could not
    reach it would leave that construction unexercised.
    """
    module = _reclaim()
    runner = _Runner(answers={"ls-remote": CommandResult(exit_code=0, stdout="", stderr="")})
    monkeypatch.setattr(module, "ShellCommandRunner", lambda: runner)
    journal = _journal_after_a_previous_dispatch(
        tmp_path=tmp_path, item_ids=(_ITEM_ID, "bd-ib-gp2nt5")
    )

    module.reclaim_stale_publish_branches(
        args=_args(),
        repo=tmp_path,
        items=(_work_item(item_id=_ITEM_ID), _work_item(item_id="bd-ib-gp2nt5")),
        journal=journal,
    )

    assert _issued(runner=runner, needle="ls-remote") == [
        ["git", "ls-remote", "origin", f"refs/heads/{_BRANCH}"],
        ["git", "ls-remote", "origin", "refs/heads/feat/bd-ib-gp2nt5"],
    ]


def test_the_surviving_head_is_read_off_the_full_ref_and_nothing_looser(
    tmp_path: Path,
) -> None:
    """The parse, directly: the full ref matches and every near miss does not."""
    module = _reclaim()
    _ = tmp_path

    assert (
        module.surviving_head_from_ls_remote(
            stdout=f"{_OTHER_BRANCH_LINE}\n{_DEAD_HEAD}\trefs/heads/{_BRANCH}\n",
            branch=_BRANCH,
        )
        == _DEAD_HEAD
    )
    # A longer branch name sharing this one's prefix, a tag of the same name, a
    # blank line and a malformed row are each NOT this branch.
    assert (
        module.surviving_head_from_ls_remote(
            stdout=(
                f"{_DEAD_HEAD}\trefs/heads/{_BRANCH}-2\n"
                f"{_DEAD_HEAD}\trefs/tags/{_BRANCH}\n"
                "\n"
                f"{_DEAD_HEAD}\n"
            ),
            branch=_BRANCH,
        )
        is None
    )

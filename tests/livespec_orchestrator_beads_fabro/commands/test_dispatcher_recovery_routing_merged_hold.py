"""A merged pull request holds a released item and keeps its own remedy.

Scenario 185's sixth scenario. The `contracts.md` section
"Factory-configurable ACP fallback priority" → "Recovery from the failed run's
preserved work" names this refusal among the non-fallback ones and carries its
remedy with it: "the pull request is merged (its remedy stays `reconcile-merged
--item`)"; and "A non-fallback refusal takes precedence over every
fallback-permitting one, so a merged pull request is never treated as a missing
anchor".

WHY THE PARENTHESIS IS THE WHOLE POINT. Every fallback-permitting refusal ends
in "dispatch it plainly instead", and a plain dispatch is what the `seeded` and
`fresh` routes do — so for those the Dispatcher may carry out the refusal's own
advice unattended. A merged pull request names a DIFFERENT remedy, and taking
the plain one against it cuts a fresh branch over work that has already landed
and spends an `acceptance_rework_cap` attempt failing. The resume's own refusal
module already keeps these two apart; this case is about routing honouring that
distinction rather than collapsing it back.

WHY THE FIXTURE AGAIN SUPPLIES A COMPLETE `seeded` ROUTE. The scenario says the
route is "held, neither seeded nor fresh", so both of the routes it must not
take have to be reachable: origin carries the needs-human ref the dying run
pushed, which makes `seeded` available, and a build that found no preserved work
would reach `fresh`. Either would be a well-formed, green, entirely wrong
dispatch.

WHY THE PULL REQUEST'S HEAD MATCHES THE ANCHOR. A moved head is itself a
refusal, and a fallback-permitting one. Leaving the two shas different would
let a build pass this case by grading the WRONG refusal — the merged state would
never have to be classified at all. Matching them makes the merged refusal the
only one this observation carries, which is what the assertion on a
single-element refusal list then pins.

WHY THE WAVE-MATE IS THE CONTROL. A build that withheld the whole selection from
the valve, or journaled a hold for every candidate, would satisfy the held half
perfectly. The second item has no journaled history, so it is routed `fresh`
without any remote measurement, is offered, and launches in the same pass.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import pytest

# Import order is load-bearing; see `test_dispatcher_recovery_routing_resume.py`.
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission as admission,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_loop_wave as loop_wave,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import ReworkPass
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "bd-ib-qgcpoc"
_BRANCH = f"feat/{_ITEM_ID}"
_RUN = "01M509HNX5KGKSRV04VQEYVWH6"
_DISPATCH = "a7395318d0c945589105940e7936139f"
_PUBLISHED_HEAD = "db9feb3900000000000000000000000000000001"
_PRESERVED_COMMIT = "216c811200000000000000000000000000000002"
_PULL_REQUEST = 2601

# The wave-mate: no journaled history, so nothing released it.
_FRESH_ID = "bd-ib-3snvbf"

# Spelled as literals because this file's Red predates the module that exports
# them, and a Red's test bytes are fixed across its Red-to-Green pair.
_HELD_STAGE = "recovery-held"
_ROUTE_STAGE = "recovery-route"
_RECLAIM_STAGE_PREFIX = "publish-branch-reclaim"


class _Shell:
    """A scripted subprocess seam; an unscripted argv FAILS rather than answering."""

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
        message = f"unscripted command reached the shell seam: {joined}"
        raise AssertionError(message)


def test_the_shell_seam_refuses_a_command_no_case_scripted() -> None:
    """The instrument's own control; see the resume module for the argument."""
    _Shell.answers = {}
    _Shell.calls = []

    with pytest.raises(AssertionError, match="unscripted command"):
        _ = _Shell().run(
            argv=["git", "ls-remote", "origin", "refs/heads/x"],
            cwd=Path("/repo"),
            timeout_seconds=1.0,
        )


def _arm(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A world whose only resume refusal is that the publication already merged.

    The listing names a MERGED pull request at exactly the head the cancel
    record anchors, so the moved-head arm stays silent; the pull request carries
    no Proof of Done record, which is read and answered rather than failing; the
    factory answers and holds nothing alive; origin carries the preservation ref;
    and both of the reclaim's forge calls are scripted so a build that fell
    through to `seeded` would run to completion.
    """
    _Shell.answers = {
        f"gh pr list --head {_BRANCH}": CommandResult(
            exit_code=0,
            stdout=json.dumps(
                [{"number": _PULL_REQUEST, "state": "MERGED", "headRefOid": _PUBLISHED_HEAD}]
            ),
            stderr="",
        ),
        f"gh pr view {_PULL_REQUEST} --json comments": CommandResult(
            exit_code=0, stdout=json.dumps({"comments": []}), stderr=""
        ),
        "ps -a --json": CommandResult(exit_code=0, stdout="[]", stderr=""),
        "ls-remote origin refs/heads/needs-human/": CommandResult(
            exit_code=0,
            stdout=f"{_PRESERVED_COMMIT}\trefs/heads/needs-human/{_RUN}\n",
            stderr="",
        ),
        f"ls-remote origin refs/heads/{_BRANCH}": CommandResult(
            exit_code=0, stdout=f"{_PUBLISHED_HEAD}\trefs/heads/{_BRANCH}\n", stderr=""
        ),
        "gh api --method POST": CommandResult(exit_code=0, stdout="", stderr=""),
        "gh api --method DELETE": CommandResult(exit_code=0, stdout="", stderr=""),
    }
    _Shell.calls = []
    monkeypatch.setattr(ShellCommandRunner, "run", _Shell.run)


def _work_item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="A released item whose publish branch already merged",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-17T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _journal(*, tmp_path: Path) -> JournalFile:
    """A journal whose newest dispatch of the item ended in a first-stall release."""
    journal = JournalFile(path=tmp_path / "fabro-dispatch-journal.jsonl")
    records: Sequence[dict[str, object]] = (
        {
            "stage": "dispatch-id",
            "work_item_id": _ITEM_ID,
            "dispatch_id": _DISPATCH,
            "workflow_name": "implement-work-item",
        },
        {"stage": "fabro-run", "work_item_id": _ITEM_ID, "run_id": _RUN},
        {
            "stage": "watchdog-stall-cancel",
            "work_item_id": _ITEM_ID,
            "dispatch_id": _DISPATCH,
            "run_id": _RUN,
            "factory": "hp",
            "executing_stage": "proof_capture",
            "published_head": _PUBLISHED_HEAD,
        },
        {"stage": "stall-cancel-release", "work_item_id": _ITEM_ID, "status": "ready"},
    )
    _ = journal.path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8"
    )
    return journal


def _rows(*, journal: JournalFile, stage_prefix: str) -> tuple[dict[str, Any], ...]:
    written = (
        json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line
    )
    return tuple(record for record in written if str(record.get("stage")).startswith(stage_prefix))


def _args(*, repo: Path, journal: JournalFile) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(journal.path),
        item=None,
        items=None,
        budget=2,
        parallel=1,
        as_json=False,
        dry_run=False,
        skip_ledger_check=True,
        workflow_name=None,
        fabro_bin="/usr/local/bin/fabro",
    )


@dataclass(kw_only=True)
class _Wave:
    journal: JournalFile
    offered: list[str]
    launched: list[str]
    outcomes: list[DispatchOutcome]


def _drive_wave(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Wave:
    """One wave over the merged released candidate and an unreleased wave-mate."""
    journal = _journal(tmp_path=tmp_path)
    items = [_work_item(item_id=_ITEM_ID), _work_item(item_id=_FRESH_ID)]
    offered: list[str] = []
    launched: list[str] = []

    _arm(monkeypatch=monkeypatch)
    monkeypatch.setattr(loop_wave, "await_usable_credential", lambda **_kwargs: None)
    monkeypatch.setattr(loop_wave, "resolve_acp_preflight", lambda **_kwargs: None)

    def _admit(**kwargs: Any) -> admission.Admission:
        candidates: list[WorkItem] = kwargs["candidates"]
        offered.extend(one.id for one in candidates)
        return admission.Admission(admitted=list(candidates), deferred=[], refused=[])

    monkeypatch.setattr(loop_wave, "admit_and_select", _admit)
    monkeypatch.setattr(
        loop_wave, "args_with_dispatch_factory_target", lambda **kwargs: kwargs["args"]
    )
    monkeypatch.setattr(
        loop_wave, "args_with_dispatch_workflow_name", lambda **kwargs: kwargs["args"]
    )

    def _launch(**kwargs: Any) -> DispatchOutcome:
        item_id = str(kwargs["item"].id)
        launched.append(item_id)
        return DispatchOutcome(
            work_item_id=item_id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="merged",
        )

    monkeypatch.setattr(loop_wave, "dispatch_one", _launch)
    outcomes = loop_wave.dispatch_loop_wave(
        args=_args(repo=tmp_path, journal=journal),
        repo=tmp_path,
        items=items,
        selected_candidates=items,
        journal=journal,
        janitor=None,
        rework=ReworkPass(scope_ids=frozenset()),
    )
    return _Wave(journal=journal, offered=offered, launched=launched, outcomes=outcomes)


def test_a_merged_pull_request_holds_the_item_and_keeps_the_reconcile_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route is `held`, and the hold carries the merged refusal's own remedy.

    The remedy is asserted VERBATIM from the resume's own arm rather than
    paraphrased, because the clause requires the held record to carry "every
    applicable non-fallback refusal with its EXISTING remedy": two renderings of
    one refusal are free to drift, and the journal would then say something the
    refusal an operator reads does not.
    """
    wave = _drive_wave(monkeypatch=monkeypatch, tmp_path=tmp_path)

    # Never offered to the valve, so the item keeps its `ready` status.
    assert wave.offered == [_FRESH_ID]
    assert wave.launched == [_FRESH_ID]
    # Neither `seeded` nor `fresh`: it took no route at all, while the wave-mate
    # that was never released took the `fresh` one.
    assert [
        (record["work_item_id"], record["route"])
        for record in _rows(journal=wave.journal, stage_prefix=_ROUTE_STAGE)
    ] == [(_FRESH_ID, "fresh")]
    held = _rows(journal=wave.journal, stage_prefix=_HELD_STAGE)
    assert [record["work_item_id"] for record in held] == [_ITEM_ID]
    # Every read answered, so this hold is a refusal and names no measurement.
    assert held[0]["measurements"] == []
    assert held[0]["details"] == []
    refusals = [str(one) for one in held[0]["refusals"]]
    assert len(refusals) == 1
    assert f"pull request #{_PULL_REQUEST} is already merged" in refusals[0]
    assert f"reconcile-merged --item {_ITEM_ID}" in refusals[0]
    # And nothing on origin for the held item: the branch carrying the merge is
    # still standing, and neither of the reclaim's scripted forge calls ran.
    assert _rows(journal=wave.journal, stage_prefix=_RECLAIM_STAGE_PREFIX) == ()
    assert [call for call in _Shell.calls if "gh api" in call] == []


def test_the_merged_hold_rides_the_wave_report_as_a_deferred_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drain reports the hold rather than silently losing the candidate.

    The detail carries the refusal, so an operator reading the drain's report
    is sent to `reconcile-merged --item` without having to open the journal —
    which matters here more than for a measurement hold, because this one does
    NOT clear on its own and no later pass will retry it into existence.
    """
    wave = _drive_wave(monkeypatch=monkeypatch, tmp_path=tmp_path)

    assert sorted((one.work_item_id, one.status) for one in wave.outcomes) == [
        (_FRESH_ID, "green"),
        (_ITEM_ID, "capacity-deferred"),
    ]
    held = next(one for one in wave.outcomes if one.work_item_id == _ITEM_ID)
    assert held.stage == _HELD_STAGE
    assert f"reconcile-merged --item {_ITEM_ID}" in str(held.detail)

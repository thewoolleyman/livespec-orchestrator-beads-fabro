"""A capacity-deferred released item costs nothing: no record, no remote change.

Scenario 185's third scenario. The `contracts.md` section
"Factory-configurable ACP fallback priority" → "Recovery from the failed run's
preserved work": "A route is valid only for the pass that measured it: an item
the valve defers for capacity carries no route into the next pass, which measures
it afresh."

WHY THE `resume` RECORD IS THE THING THAT MUST NOT BE WRITTEN. That record is not
a note about what routing decided — it is the ATTRIBUTION LINK the acceptance pass
reads: "the acceptance pass MUST attribute a record carrying any identifier so
linked to the resumed dispatch, so a `verified` record the earlier run published
grades the resumed run's merge." Written for a dispatch that never ran, it makes
the earlier run's proof grade whatever merges next, and it counts against the
two-resume chain bound — so the next attempt is silently one closer to refusal,
with the journal reading as though a resume had happened. The record therefore
belongs to the LAUNCH, after the capacity decision, and not to the measurement.

WHY THE REMOTE IS ASSERTED AS WELL. This is the same defect `bd-ib-huoyk7`
repaired one layer down: a destructive act taken before the capacity decision
spends a deferred item's publication for a run that never starts. Here the act is
the reclaim, which for a `resume`-routed item must not run at all — so its absence
is asserted twice over, once as the missing journal rows and once as the
`ls-remote` origin was never asked.

WHY THE RESUME IS FULLY AVAILABLE IN THIS FIXTURE. The forge names an OPEN pull
request at exactly the head the item's cancel record anchors, so routing DOES
assign the resume route and there is a record for a build to write. A fixture whose
resume was refused would pass this file against any build at all.
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
_PR = 3001
_PUBLISHED_HEAD = "db9feb3900000000000000000000000000000001"

# Spelled as literals because this file's Red predates the modules that export
# them, and a Red's test bytes are fixed across its Red-to-Green pair.
_RESUME_STAGE = "resume"
_ROUTE_STAGE = "recovery-route"
# The route row's own `route` value for a resume. The same word as the journal
# stage above, which is deliberate and is why it is named separately here.
_RESUME_ROUTE = "resume"
_HELD_STAGE = "recovery-held"
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
    """A world where the resume is fully available and the branch still stands.

    The branch `ls-remote` and the reclaim's two forge calls are DELIBERATELY
    unscripted: the seam fails an unscripted argv, so a build that reclaimed for
    this item is caught at the call rather than only in the journal.
    """
    _Shell.answers = {
        f"gh pr list --head {_BRANCH}": CommandResult(
            exit_code=0,
            stdout=json.dumps([{"number": _PR, "state": "OPEN", "headRefOid": _PUBLISHED_HEAD}]),
            stderr="",
        ),
        f"gh pr view {_PR} --json comments": CommandResult(
            exit_code=0, stdout=json.dumps({"comments": []}), stderr=""
        ),
        "ps -a --json": CommandResult(exit_code=0, stdout="[]", stderr=""),
    }
    _Shell.calls = []
    monkeypatch.setattr(ShellCommandRunner, "run", _Shell.run)


def _work_item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="ready",
        title="A released item the valve defers for capacity",
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
        budget=1,
        parallel=1,
        as_json=False,
        dry_run=False,
        skip_ledger_check=True,
        workflow_name=None,
        fabro_bin="/usr/local/bin/fabro",
    )


def _capacity_deferred() -> admission.Admission:
    """The valve's answer when a full cap left this pass's one candidate behind.

    The detail is the production shape, abridged from the 2026-10-14 dispatch
    `test_dispatcher_publish_branch_reclaim_after_capacity.py` is written around.
    """
    return admission.Admission(
        admitted=[],
        deferred=[
            DispatchOutcome(
                work_item_id=_ITEM_ID,
                status="capacity-deferred",
                stage="capacity-deferred",
                pr_number=None,
                merge_sha=None,
                detail="capacity deferred: active_count=11 wip_cap=10 free_slots=0",
            )
        ],
        refused=[],
    )


@dataclass(kw_only=True)
class _Wave:
    journal: JournalFile
    launched: list[str]
    outcomes: list[DispatchOutcome]


def _admitted(*, items: list[WorkItem]) -> admission.Admission:
    """The valve's answer when the one candidate did get a slot."""
    return admission.Admission(admitted=list(items), deferred=[], refused=[])


def _drive_wave(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    defer: bool,
) -> _Wave:
    """One wave over the released candidate, with the valve's answer chosen."""
    journal = _journal(tmp_path=tmp_path)
    items = [_work_item()]
    launched: list[str] = []

    _arm(monkeypatch=monkeypatch)
    monkeypatch.setattr(loop_wave, "await_usable_credential", lambda **_kwargs: None)
    monkeypatch.setattr(loop_wave, "resolve_acp_preflight", lambda **_kwargs: None)
    monkeypatch.setattr(
        loop_wave,
        "admit_and_select",
        lambda **_kwargs: _capacity_deferred() if defer else _admitted(items=items),
    )
    monkeypatch.setattr(
        loop_wave, "args_with_dispatch_factory_target", lambda **kwargs: kwargs["args"]
    )
    monkeypatch.setattr(
        loop_wave, "args_with_dispatch_workflow_name", lambda **kwargs: kwargs["args"]
    )

    def _launch(**kwargs: Any) -> DispatchOutcome:
        launched.append(str(kwargs["item"].id))
        return DispatchOutcome(
            work_item_id=_ITEM_ID,
            status="green",
            stage="done",
            pr_number=_PR,
            merge_sha="deadbeef",
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
    return _Wave(journal=journal, launched=launched, outcomes=outcomes)


def test_an_admitted_resume_routed_item_does_record_its_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control for the case below, on the SAME fixture and the same route.

    Without it, a build that had simply stopped writing the two records would
    satisfy the deferred case perfectly — and would have broken the attribution
    the acceptance pass depends on for every resume that DOES launch. The only
    difference between the two cases is the valve's answer, which is what makes
    the comparison about the capacity decision rather than about the fixture.
    """
    wave = _drive_wave(monkeypatch=monkeypatch, tmp_path=tmp_path, defer=False)

    assert wave.launched == [_ITEM_ID]
    resumed = _rows(journal=wave.journal, stage_prefix=_RESUME_STAGE)
    assert [record["work_item_id"] for record in resumed] == [_ITEM_ID]
    routed = _rows(journal=wave.journal, stage_prefix=_ROUTE_STAGE)
    assert [record["route"] for record in routed] == [_RESUME_ROUTE]


def test_a_capacity_deferred_resume_routed_item_is_left_exactly_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing launched, nothing recorded about the route, nothing touched on origin.

    The valve DID defer — the outcome is read back to prove the fixture reached
    the decision this case is about — and the resume WAS available, so a build
    that journaled at measurement time has a record to have written here.
    """
    wave = _drive_wave(monkeypatch=monkeypatch, tmp_path=tmp_path, defer=True)

    assert wave.launched == []
    assert [(one.work_item_id, one.status) for one in wave.outcomes] == [
        (_ITEM_ID, "capacity-deferred")
    ]
    # Neither the attribution link nor a route record nor a hold.
    assert _rows(journal=wave.journal, stage_prefix=_RESUME_STAGE) == ()
    assert _rows(journal=wave.journal, stage_prefix=_ROUTE_STAGE) == ()
    assert _rows(journal=wave.journal, stage_prefix=_HELD_STAGE) == ()
    # And nothing on origin: the publish branch was never even asked about, so
    # neither it nor the pull request open on it could have changed.
    assert _rows(journal=wave.journal, stage_prefix=_RECLAIM_STAGE_PREFIX) == ()
    assert [call for call in _Shell.calls if "ls-remote" in call] == []
    assert [call for call in _Shell.calls if "gh api" in call] == []

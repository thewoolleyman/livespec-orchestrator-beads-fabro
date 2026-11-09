"""Integration-tier acceptance for a merge wait handed off and later completed.

Binds SPECIFICATION/scenarios.md "Scenario 220 — An exhausted merge-poll budget
hands an armed, passing pull request to reconciliation": the dispatch that hands
the pull request off, and the Dispatcher's next stranded-claim pass that completes
the item from what the forge then reports.

THE JOURNEY IS THE REAL ONE. The production engine (`run_dispatch`) ends its merge
wait on an armed pull request whose required check is still running, the production
post-run disposition (`post_run_dispositions`) records the handoff against the
in-memory tenant, and the production survey (`survey_stranded_claims`) reads the
dispatch journal that same dispatch wrote. Only the subprocess seam, the Fabro
launcher and the `reconcile-merged` valve's own janitor run are stood in; the valve
is stood in at its command function because its subject is the acceptance path, not
this scenario's.

EACH ENDING SITS BESIDE ITS CONTROL. The same journal and claim are surveyed first
while the pull request is still open and passing, where the claim must be HELD with
the item untouched, so a pass that completed every handed-off claim could not satisfy
the merged and failed-check cases.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimStamp, record_claim_stamp
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_stranded_claim_handoff_recovery as recovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    dispatch_exit_code,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    FabroRunResult,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    post_run_dispositions,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_survey import (
    FactoryInventory,
    StrandedClaimInputs,
    StrandedClaimSurvey,
    survey_stranded_claims,
)
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-bacahf"
_RUN_ID = "01M6VNKFXRA85Q8WF0JV23204B"
_HOST = "owning-host"
_FACTORY = "petri"
_SERVER = "https://petri.example:32276"
_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'
_TENANT_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {
      "tenant": "livespec-impl-beads",
      "prefix": "bd",
      "server_user": "livespec-impl-beads",
      "database": "livespec-impl-beads",
      "bd_path": "bd",
      "fake": true
    }
  }
}
"""
_REQUIRED = json.dumps(
    {
        "data": {
            "repository": {
                "pullRequest": {
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "statusCheckRollup": {
                                        "contexts": {
                                            "nodes": [
                                                {"name": "check-coverage", "isRequired": True}
                                            ]
                                        }
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        }
    }
)


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()


def _store() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A dispatched pull request whose CI outlasts the merge-poll budget",
        description="The merge wait ended with the pull request armed and its checks running.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-08T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_ITEM_ID,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text=_DECLARED_CONFIG,
        default_branch="master",
        fabro_factory_name=_FACTORY,
    )


@dataclass(kw_only=True)
class _Forge:
    """A forge whose one pull request changes state between the dispatch and the pass."""

    state: str = "OPEN"
    check: dict[str, object] = field(
        default_factory=lambda: {
            "name": "check-coverage",
            "status": "IN_PROGRESS",
            "conclusion": None,
        }
    )
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
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        if argv[:3] == ["gh", "api", "graphql"]:
            return CommandResult(exit_code=0, stdout=_REQUIRED, stderr="")
        if argv[:3] != ["gh", "pr", "view"]:
            return CommandResult(exit_code=0, stdout="[]", stderr="")
        return CommandResult(
            exit_code=0,
            stdout=json.dumps(
                {
                    "number": 4615,
                    "state": self.state,
                    "autoMergeRequest": None if self.state == "MERGED" else {"enabledAt": "now"},
                    "mergeStateStatus": "BLOCKED",
                    "mergeCommit": {"oid": "cafe05"} if self.state == "MERGED" else None,
                    "headRefOid": "8ad6cd7b2",
                    "baseRefOid": "1c0ffee",
                    "statusCheckRollup": [self.check],
                }
            ),
            stderr="",
        )


@dataclass(kw_only=True)
class _Launcher:
    def launch(self, *, plan: DispatchPlan, runner: object, journal: object) -> FabroRunResult:
        _ = (plan, runner, journal)
        return FabroRunResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""), run_id=_RUN_ID
        )


def _dispatch(*, repo: Path, forge: _Forge) -> tuple[DispatchOutcome, JournalFile]:
    _ = (repo / ".livespec.jsonc").write_text(_TENANT_CONFIG, encoding="utf-8")
    append_work_item(path=_store(), item=_item())
    record_claim_stamp(
        path=_store(),
        work_item_id=_ITEM_ID,
        stamp=ClaimStamp(
            dispatch_id="01DISPATCH",
            dispatching_host=_HOST,
            run_id=_RUN_ID,
            factory_name=_FACTORY,
            factory_server=_SERVER,
        ),
    )
    journal = JournalFile(path=repo / "tmp" / "journal.jsonl")
    journal.path.parent.mkdir(parents=True, exist_ok=True)
    journal.append(record={"stage": "dispatch-id", "work_item_id": _ITEM_ID})
    outcome = run_dispatch(
        plan=_plan(repo=repo),
        runner=forge,
        journal=journal,
        sleep=lambda _: None,
        poll=PollPolicy(attempts=2, interval_seconds=0.0),
        fabro_launcher=_Launcher(),
    )
    disposed = post_run_dispositions(
        args=argparse.Namespace(close_on_merge=False),
        repo=repo,
        item=_item(),
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=1.0,
        dispatch_context_size=10,
        token_supplier=lambda: "token",
    )
    return disposed, journal


def _next_pass(*, repo: Path, journal: JournalFile, forge: _Forge) -> StrandedClaimSurvey:
    return survey_stranded_claims(
        inputs=StrandedClaimInputs(
            repo=repo,
            items=tuple(item for item in read_work_items(path=_store()) if item.id == _ITEM_ID),
            journal=journal,
            runner=forge,
            inventories=(
                FactoryInventory(
                    name=_FACTORY,
                    server_url=_SERVER,
                    fabro_bin="fabro",
                    surveyed=True,
                    status_kinds={_RUN_ID: "succeeded"},
                ),
            ),
            this_host=_HOST,
            now_iso="2026-11-08T09:00:00Z",
        )
    )


def _stored() -> WorkItem:
    return next(one for one in read_work_items(path=_store()) if one.id == _ITEM_ID)


def test_a_handed_off_pull_request_that_merges_is_accepted_by_the_next_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    forge = _Forge()
    outcome, journal = _dispatch(repo=tmp_path, forge=forge)
    reconciled: list[str] = []

    def _reconcile(*, args: argparse.Namespace) -> int:
        reconciled.append(args.item)
        return 0

    monkeypatch.setattr(recovery, "reconcile_merged_for_claim", _reconcile)

    assert (outcome.status, dispatch_exit_code(outcomes=[outcome])) == ("handed-off", 0)
    assert (_stored().status, _stored().assignee) == ("active", "fabro")

    still_open = _next_pass(repo=tmp_path, journal=journal, forge=forge)

    assert still_open.recovered == ()
    assert [
        (h.hold_reason, "merge-wait-handed-off" in (h.detail or "")) for h in still_open.held
    ] == [("run-succeeded", True)]
    assert reconciled == []
    assert _stored().status == "active"

    forge.state = "MERGED"
    merged = _next_pass(repo=tmp_path, journal=journal, forge=forge)

    assert merged.held == ()
    assert [(r.work_item_id, r.route) for r in merged.recovered] == [
        (_ITEM_ID, "merge-wait-handoff-reconcile-merged")
    ]
    assert reconciled == [_ITEM_ID]
    assert not any("resume" in " ".join(argv) for argv in forge.argvs)
    assert _stored().blocked_reason is None


def test_a_handed_off_pull_request_whose_required_check_fails_is_routed_as_a_failed_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    forge = _Forge()
    _, journal = _dispatch(repo=tmp_path, forge=forge)

    forge.check = {"name": "check-coverage", "status": "COMPLETED", "conclusion": "failure"}
    failed = _next_pass(repo=tmp_path, journal=journal, forge=forge)

    assert failed.held == ()
    assert [r.work_item_id for r in failed.recovered] == [_ITEM_ID]
    assert (_stored().status, _stored().blocked_reason) == ("blocked", "needs-human")


def test_a_handed_off_pull_request_closed_without_merging_rests_with_the_exhausted_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    forge = _Forge()
    _, journal = _dispatch(repo=tmp_path, forge=forge)

    forge.state = "CLOSED"
    closed = _next_pass(repo=tmp_path, journal=journal, forge=forge)

    assert closed.held == ()
    assert [r.work_item_id for r in closed.recovered] == [_ITEM_ID]
    assert (_stored().status, _stored().blocked_reason) == ("blocked", "needs-human")

"""Integration-tier acceptance for an exhausted merge-poll budget on an open pull request.

Binds SPECIFICATION/scenarios.md "Scenario 220 — An exhausted merge-poll budget
on an open pull request rests the item for resume" and the final sentences of the
`contracts.md` paragraph "Armed pull request overtaken by the default branch".

THE JOURNEY IS THE REAL ONE. The production engine (`run_dispatch`: confirm the
pull request, poll for its merge, take the final read) produces the outcome, and
the production post-run disposition (`post_run_dispositions`: the durable ledger
comment, then the needs-human rest) applies it to the in-memory tenant. Only the
subprocess seam and the Fabro launcher are stood in, so a build that rested the
item anywhere other than through the ratified transition would show here.

EACH CASE CARRIES A CONTROL THAT RETURNS THE OTHER ANSWER. The same scripted
forge reports the pull request MERGED at the final read in one case and OPEN in
the other, and a conflicting pull request is read through the identical journey,
so a build that rested every exhausted wait could not satisfy the second case and
a build that rested none could not satisfy the first.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    post_run_dispositions,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-sufca7"
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
_MARKER = "livespec-merge-poll-budget-exhausted"


@pytest.fixture(autouse=True)
def _fresh_tenant() -> None:
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
        title="A succeeded run whose pull request failed its required check",
        description="The merge wait ended with the pull request still open.",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-29T00:00:00Z",
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
        fabro_factory_name="petri",
    )


def _view(*, state: str, merge_state: str) -> str:
    return json.dumps(
        {
            "number": 3913,
            "state": state,
            "autoMergeRequest": {"enabledAt": "now"},
            "mergeStateStatus": merge_state,
            "mergeCommit": {"oid": "cafe05"} if state == "MERGED" else None,
            "statusCheckRollup": [],
            "headRefOid": "8ad6cd7b2",
            "baseRefOid": "1c0ffee",
        }
    )


@dataclass(kw_only=True)
class _Forge:
    """A forge reporting the pull request OPEN until `open_reads` views are spent.

    Every read after the budgeted ones sees `final_state`, which is the whole
    experimental variable: the final read is the only one the clause lets decide.
    """

    open_reads: int
    final_state: str
    merge_state: str = "BLOCKED"
    views: int = 0
    calls: list[list[str]] = field(default_factory=list)

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
        self.calls.append(argv)
        if argv[:3] != ["gh", "pr", "view"]:
            return CommandResult(exit_code=0, stdout="", stderr="")
        self.views += 1
        state = "OPEN" if self.views <= self.open_reads else self.final_state
        return CommandResult(
            exit_code=0, stdout=_view(state=state, merge_state=self.merge_state), stderr=""
        )


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)
    path: Path | None = None

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _Launcher:
    def launch(self, *, plan: DispatchPlan, runner: object, journal: object) -> FabroRunResult:
        _ = (plan, runner, journal)
        return FabroRunResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""), run_id="01M62WN80GEF"
        )


def _journey(*, repo: Path, forge: _Forge) -> tuple[DispatchOutcome, _Journal]:
    _ = (repo / ".livespec.jsonc").write_text(_TENANT_CONFIG, encoding="utf-8")
    append_work_item(path=_store(), item=_item())
    journal = _Journal()
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
        journal=journal,  # type: ignore[arg-type]
        wall_clock_seconds=1.0,
        dispatch_context_size=10,
        token_supplier=lambda: "token",
    )
    return disposed, journal


def _rested() -> WorkItem:
    return next(one for one in read_work_items(path=_store()) if one.id == _ITEM_ID)


def test_an_open_non_conflicting_pull_request_at_expiry_rests_the_item_for_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    # Three OPEN reads cover the confirmation and both polls; the final read is OPEN too.
    forge = _Forge(open_reads=99, final_state="OPEN")

    outcome, journal = _journey(repo=tmp_path, forge=forge)

    assert (outcome.status, outcome.stage) == ("blocked", "merge-poll")
    assert "merge-poll-budget-exhausted" in outcome.detail
    chain = f"`resolve-blocked:{_ITEM_ID}:ready`"
    assert chain in outcome.detail
    assert outcome.detail.index(chain) < outcome.detail.index(f"`resume --item {_ITEM_ID}`")
    assert dispatch_exit_code(outcomes=[outcome]) == 4
    rested = _rested()
    assert (rested.status, rested.blocked_reason) == ("blocked", "needs-human")
    comments = read_work_item_comments(path=_store(), work_item_id=_ITEM_ID)
    assert [c.text.splitlines()[0] for c in comments] == [_MARKER]
    assert [r for r in journal.records if r.get("stage") == "needs-human-blocked"] != []


def test_a_pull_request_merged_on_the_final_read_is_not_rested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    forge = _Forge(open_reads=3, final_state="MERGED", merge_state="CLEAN")

    outcome, journal = _journey(repo=tmp_path, forge=forge)

    assert outcome.stage != "merge-poll"
    assert outcome.status != "blocked"
    assert outcome.pr_number == 3913
    assert _rested().status == "active"
    assert read_work_item_comments(path=_store(), work_item_id=_ITEM_ID) == ()
    assert [r for r in journal.records if r.get("stage") == "needs-human-blocked"] == []


def test_a_conflicting_pull_request_keeps_the_overtaken_arming_ending_and_its_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    forge = _Forge(open_reads=99, final_state="OPEN", merge_state="DIRTY")

    outcome, _ = _journey(repo=tmp_path, forge=forge)

    assert (outcome.status, outcome.stage) == ("blocked", "merge-poll")
    assert "base-advanced-after-arming" in outcome.detail

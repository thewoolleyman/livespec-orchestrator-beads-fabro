"""The stranded-claim pass completes an item whose merge wait was handed off.

Binds the reconciliation half of `SPECIFICATION/scenarios.md` Scenario 220 ("A
handed-off pull request that merges is accepted by the next reconciliation
pass", "... whose required check fails is routed as a failed check", "... closed
without merging rests for a human") and the `run-succeeded` hold of
`contracts.md` (its stranded-claim release subsection), for work-item `bd-ib-bacahf`.

THE CLAIM SURVEYED IS THE ONE A HANDOFF LEAVES: `active` under the `fabro`
assignee, its run terminal and succeeded, no live owner, and a
`merge-wait-handed-off` row in the newest dispatch's journal segment. Before the
handoff existed such a claim was held as `run-succeeded` and a person ran
`reconcile-merged` by hand.

EVERY ROUTE SITS BESIDE ITS CONTROL. The same succeeded claim WITHOUT a handoff
row, with a handoff row of an earlier dispatch, and with a handoff row of another
run is held exactly as it always was, so a pass that completed every succeeded
claim cannot satisfy the merged case. And the open, armed, passing pull request is
held rather than completed, so a pass that completed every handed-off claim
cannot either.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimStamp, record_claim_stamp
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_survey import (
    FactoryInventory,
    StrandedClaimInputs,
    survey_stranded_claims,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_RECOVERY_MODULE = (
    "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_handoff_recovery"
)
_ITEM_ID = "bd-ib-handoffpass"
_RUN_ID = "01HANDOFFRUN"
_OTHER_RUN_ID = "01OTHERRUN"
_HOST = "owning-host"
_FACTORY = "hp"
_SERVER = "https://hp.example:32276"
_PR = 4615
_HANDOFF_ACTION = "merge-wait-handoff-reconcile-merged"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A dispatched slice whose merge wait was handed off",
        description="Implement the slice.",
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


def _stamp() -> ClaimStamp:
    return ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host=_HOST,
        run_id=_RUN_ID,
        factory_name=_FACTORY,
        factory_server=_SERVER,
    )


def _handoff_row(*, run_id: str = _RUN_ID) -> dict[str, object]:
    return {
        "stage": "merge-wait-handed-off",
        "work_item_id": _ITEM_ID,
        "run_id": run_id,
        "pr_number": _PR,
        "pr_head": "head1111",
        "waited_seconds": 2400,
        "running_checks": ["check-coverage"],
    }


def _journal(*, repo: Path, rows: list[dict[str, object]]) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return JournalFile(path=path)


_LAUNCH = {"stage": "dispatch-id", "work_item_id": _ITEM_ID}


def _view(
    *,
    state: str = "OPEN",
    armed: bool = True,
    rollup: list[dict[str, object]] | None = None,
) -> str:
    return json.dumps(
        {
            "number": _PR,
            "state": state,
            "autoMergeRequest": {"enabledAt": "now"} if armed else None,
            "mergeStateStatus": "BLOCKED",
            "mergeCommit": {"oid": "cafe05"} if state == "MERGED" else None,
            "headRefOid": "head1111",
            "baseRefOid": "base2222",
            "statusCheckRollup": [] if rollup is None else rollup,
        }
    )


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

_RUNNING = [{"name": "check-coverage", "status": "IN_PROGRESS", "conclusion": None}]
_FAILED = [{"name": "check-coverage", "status": "COMPLETED", "conclusion": "failure"}]


class _Forge:
    """A fake subprocess seam answering by argv, and remembering every call."""

    def __init__(self, *, view: CommandResult) -> None:
        self.view = view
        self.argvs: list[list[str]] = []

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
        if argv[:3] == ["gh", "pr", "view"]:
            return self.view
        if argv[:3] == ["gh", "api", "graphql"]:
            return CommandResult(exit_code=0, stdout=_REQUIRED, stderr="")
        return CommandResult(exit_code=0, stdout="[]", stderr="")


def _ok(*, stdout: str) -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _pass(
    *, repo: Path, journal: JournalFile, forge: _Forge
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    append_work_item(path=_config(), item=_item())
    record_claim_stamp(path=_config(), work_item_id=_ITEM_ID, stamp=_stamp())
    survey = survey_stranded_claims(
        inputs=StrandedClaimInputs(
            repo=repo,
            items=(_item(),),
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
    return survey.recovered, survey.held


def _stored() -> WorkItem:
    return next(iter(read_work_items(path=_config())))


def _recovery_module() -> Any:
    module_path = _COMMANDS / "_dispatcher_stranded_claim_handoff_recovery.py"
    assert module_path.is_file(), f"{module_path} does not exist yet"
    return importlib.import_module(_RECOVERY_MODULE)


def _stub_reconcile(*, monkeypatch: pytest.MonkeyPatch, exit_code: int) -> list[argparse.Namespace]:
    calls: list[argparse.Namespace] = []

    def _reconcile(*, args: argparse.Namespace) -> int:
        calls.append(args)
        return exit_code

    monkeypatch.setattr(_recovery_module(), "reconcile_merged_for_claim", _reconcile)
    return calls


def test_a_handed_off_claim_whose_pull_request_merged_is_reconciled_in_the_same_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_reconcile(monkeypatch=monkeypatch, exit_code=0)
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo, rows=[_LAUNCH, _handoff_row()])
    forge = _Forge(view=_ok(stdout=_view(state="MERGED", armed=False)))

    recovered, held = _pass(repo=repo, journal=journal, forge=forge)

    assert held == ()
    assert [(r.work_item_id, r.route) for r in recovered] == [(_ITEM_ID, _HANDOFF_ACTION)]
    assert len(calls) == 1
    assert (calls[0].item, calls[0].regrade) == (_ITEM_ID, False)
    assert calls[0].repo == str(repo)
    assert not any("resume" in " ".join(argv) for argv in forge.argvs)
    assert _stored().status == "active"
    assert read_work_item_comments(path=_config(), work_item_id=_ITEM_ID) == ()


def test_a_reconcile_the_valve_refuses_leaves_the_claim_held_and_names_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_reconcile(monkeypatch=monkeypatch, exit_code=3)
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo, rows=[_LAUNCH, _handoff_row()])
    forge = _Forge(view=_ok(stdout=_view(state="MERGED", armed=False)))

    recovered, held = _pass(repo=repo, journal=journal, forge=forge)

    assert recovered == ()
    assert [h.hold_reason for h in held] == ["run-succeeded"]
    assert "merge-wait-handed-off" in (held[0].detail or "")
    assert "reconcile-merged" in (held[0].detail or "")
    assert len(calls) == 1
    assert _stored().status == "active"


def test_a_handed_off_claim_with_a_failed_required_check_rests_as_a_failed_check(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo, rows=[_LAUNCH, _handoff_row()])
    forge = _Forge(view=_ok(stdout=_view(rollup=_FAILED)))

    recovered, held = _pass(repo=repo, journal=journal, forge=forge)

    assert held == ()
    assert [r.work_item_id for r in recovered] == [_ITEM_ID]
    stored = _stored()
    assert (stored.status, stored.blocked_reason) == ("blocked", "needs-human")
    rows = [json.loads(line) for line in journal.path.read_text().splitlines()]
    assert "needs-human-blocked" in [row.get("stage") for row in rows]
    announced = [r for r in rows if r.get("stage") == "stranded-claim-merge-wait-handoff"]
    assert [r["reason"] for r in announced] == ["required-check-failed"]
    markers = [
        c.text.splitlines()[0]
        for c in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
    ]
    assert "livespec-merge-poll-budget-exhausted" not in markers


@pytest.mark.parametrize(
    "view",
    [_view(state="CLOSED", armed=False), _view(armed=False)],
    ids=["closed-without-merging", "auto-merge-no-longer-armed"],
)
def test_a_handed_off_claim_the_forge_will_not_merge_rests_with_the_exhausted_budget_cause(
    tmp_path: Path, view: str
) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo, rows=[_LAUNCH, _handoff_row()])

    recovered, held = _pass(repo=repo, journal=journal, forge=_Forge(view=_ok(stdout=view)))

    assert held == ()
    assert [r.work_item_id for r in recovered] == [_ITEM_ID]
    stored = _stored()
    assert (stored.status, stored.blocked_reason) == ("blocked", "needs-human")
    markers = [
        c.text.splitlines()[0]
        for c in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
    ]
    assert "livespec-merge-poll-budget-exhausted" in markers


def test_an_armed_open_pull_request_with_running_checks_stays_held_naming_the_handoff(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo, rows=[_LAUNCH, _handoff_row()])
    forge = _Forge(view=_ok(stdout=_view(rollup=_RUNNING)))

    recovered, held = _pass(repo=repo, journal=journal, forge=forge)

    assert recovered == ()
    assert [h.hold_reason for h in held] == ["run-succeeded"]
    assert "merge-wait-handed-off" in (held[0].detail or "")
    assert (_stored().status, _stored().assignee) == ("active", "fabro")


def test_an_unreadable_pull_request_leaves_a_handed_off_claim_held(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo, rows=[_LAUNCH, _handoff_row()])
    forge = _Forge(view=CommandResult(exit_code=1, stdout="", stderr="gh failed"))

    recovered, held = _pass(repo=repo, journal=journal, forge=forge)

    assert recovered == ()
    assert [h.hold_reason for h in held] == ["run-succeeded"]
    assert "merge-wait-handed-off" in (held[0].detail or "")
    assert _stored().status == "active"


@pytest.mark.parametrize(
    "rows",
    [
        [_LAUNCH],
        [_LAUNCH, _handoff_row(run_id=_OTHER_RUN_ID)],
        [_handoff_row(), _LAUNCH],
    ],
    ids=["no-handoff-row", "handoff-row-of-another-run", "handoff-row-of-an-earlier-dispatch"],
)
def test_a_succeeded_claim_without_a_handoff_of_its_own_dispatch_is_held_as_before(
    tmp_path: Path, rows: list[dict[str, object]]
) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo, rows=rows)
    forge = _Forge(view=_ok(stdout=_view(state="MERGED", armed=False)))

    recovered, held = _pass(repo=repo, journal=journal, forge=forge)

    assert recovered == ()
    assert [h.hold_reason for h in held] == ["run-succeeded"]
    assert held[0].detail is None
    assert not any(argv[:3] == ["gh", "pr", "view"] for argv in forge.argvs)
    assert _stored().status == "active"

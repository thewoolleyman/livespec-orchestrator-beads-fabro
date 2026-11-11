"""The stranded-claim pass completes a rework re-dispatch whose merge wait was handed off.

Binds `SPECIFICATION/scenarios.md` Scenario 337 and the survey clause of
`contracts.md` (its stranded-claim release subsection) for work-item `bd-ib-if5luo`.

A REWORK RE-DISPATCH THAT HANDS ITS MERGE WAIT OFF LEAVES THE ITEM `active` UNDER
`rework:pending`, and the survey used to skip every marked row before it read the
claim, so the promise the handoff comment makes (the next stranded-claim pass
accepts the item when the pull request merges) was never kept. A HANDED-OFF
REWORK is now surveyed like any other claim; a PARKED rework stays outside it.

EVERY ROUTE SITS BESIDE ITS CONTROL. The merged case is paired with the open case
(held, never completed) and with three parked reworks, each of which holds a
`merge-wait-handed-off` row that a looser reading would mistake for the rework's
own: the ORIGINAL dispatch's handoff, which sits before the rework admission; a
rework admitted whose dispatch has not opened; and a rework dispatch that opened
and died before publishing.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimStamp, record_claim_stamp
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged import (
    run_reconcile_merged_command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_handoff_recovery import (
    reconcile_merged_for_claim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_survey import (
    FactoryInventory,
    StrandedClaimInputs,
    survey_stranded_claims,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_RECOVERY_MODULE = (
    "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_handoff_recovery"
)
_ITEM_ID = "bd-ib-reworkhandoff"
_RUN_ID = "01REWORKRUN"
_HOST = "owning-host"
_FACTORY = "hp"
_SERVER = "https://hp.example:32276"
_PR = 4726
_HANDOFF_ACTION = "merge-wait-handoff-reconcile-merged"
_REWORK_PENDING_LABEL = "rework:pending"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
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
        (
            '{"livespec-orchestrator-beads-fabro": {'
            '"connection": {"prefix": "bd-ib"}, '
            '"compat": {"pinned": "master"}, '
            '"dispatcher": {"acceptance_mode": "ai-only"}'
            "}}"
        ),
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A rework re-dispatch whose merge wait was handed off",
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
        admission_policy="auto",
        acceptance_policy="ai-only",
        rework_pending=True,
    )


def _stamp() -> ClaimStamp:
    return ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host=_HOST,
        run_id=_RUN_ID,
        factory_name=_FACTORY,
        factory_server=_SERVER,
    )


def _handoff_row() -> dict[str, object]:
    return {
        "stage": "merge-wait-handed-off",
        "work_item_id": _ITEM_ID,
        "run_id": _RUN_ID,
        "pr_number": _PR,
        "pr_head": "head1111",
        "waited_seconds": 2400,
        "running_checks": ["check-coverage"],
    }


_LAUNCH = {"stage": "dispatch-id", "work_item_id": _ITEM_ID}
_REWORK_ADMIT = {"stage": "ledger-rework-admit", "work_item_id": _ITEM_ID, "rework_pending": True}

# The original dispatch handed off and merged; acceptance failed; the rework was
# admitted, opened its own dispatch, and handed its own merge wait off.
_HANDED_OFF_REWORK_ROWS = [_LAUNCH, _handoff_row(), _REWORK_ADMIT, _LAUNCH, _handoff_row()]


def _journal(*, repo: Path, rows: list[dict[str, object]]) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return JournalFile(path=path)


def _view(*, state: str, armed: bool) -> str:
    return json.dumps(
        {
            "number": _PR,
            "state": state,
            "autoMergeRequest": {"enabledAt": "now"} if armed else None,
            "mergeStateStatus": "BLOCKED",
            "mergeCommit": {"oid": "cafe05"} if state == "MERGED" else None,
            "headRefOid": "head1111",
            "baseRefOid": "base2222",
            "statusCheckRollup": [],
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


class _Forge:
    """A fake subprocess seam answering by argv, and remembering every call."""

    def __init__(self, *, view: str) -> None:
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
            return CommandResult(exit_code=0, stdout=self.view, stderr="")
        return CommandResult(exit_code=0, stdout=_REQUIRED, stderr="")


def _pass(
    *, repo: Path, journal: JournalFile, forge: _Forge
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    append_work_item(path=_config(), item=_item())
    make_beads_client(config=_config()).update_issue(
        issue_id=_ITEM_ID, add_labels=[_REWORK_PENDING_LABEL]
    )
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
            now_iso="2026-11-09T09:00:00Z",
        )
    )
    return survey.recovered, survey.held


def _stub_reconcile(*, monkeypatch: pytest.MonkeyPatch, exit_code: int) -> list[argparse.Namespace]:
    calls: list[argparse.Namespace] = []

    def _reconcile(*, args: argparse.Namespace) -> int:
        calls.append(args)
        return exit_code

    monkeypatch.setattr(f"{_RECOVERY_MODULE}.reconcile_merged_for_claim", _reconcile)
    return calls


def test_a_merged_handed_off_rework_is_completed_by_the_next_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_reconcile(monkeypatch=monkeypatch, exit_code=0)
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo, rows=_HANDED_OFF_REWORK_ROWS)
    forge = _Forge(view=_view(state="MERGED", armed=False))

    recovered, held = _pass(repo=repo, journal=journal, forge=forge)

    assert held == ()
    assert [(r.work_item_id, r.route) for r in recovered] == [(_ITEM_ID, _HANDOFF_ACTION)]
    assert len(calls) == 1
    assert (calls[0].item, calls[0].regrade, calls[0].handed_off_rework) == (
        _ITEM_ID,
        False,
        True,
    )


def test_the_completion_of_a_handed_off_rework_moves_it_on_and_clears_the_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo, rows=_HANDED_OFF_REWORK_ROWS)
    append_work_item(path=_config(), item=_item())
    make_beads_client(config=_config()).update_issue(
        issue_id=_ITEM_ID, add_labels=[_REWORK_PENDING_LABEL]
    )
    monkeypatch.setattr(
        _dispatcher_completion, "run_acceptance_pass", lambda **_: _PassingAcceptancePass()
    )

    exit_code = run_reconcile_merged_command(
        args=argparse.Namespace(
            repo=str(repo),
            item=_ITEM_ID,
            janitor=None,
            journal=str(journal.path),
            invoker=None,
            force=True,
            regrade=False,
            handed_off_rework=True,
            as_json=False,
        ),
        runner=_ValveRunner(),
    )

    stored = materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]
    assert exit_code == 0
    assert stored.status in {"acceptance", "done"}
    assert stored.rework_pending is False


def test_the_valve_still_refuses_a_marked_item_that_is_not_a_handed_off_rework(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())
    make_beads_client(config=_config()).update_issue(
        issue_id=_ITEM_ID, add_labels=[_REWORK_PENDING_LABEL]
    )
    exit_code = reconcile_merged_for_claim(
        args=argparse.Namespace(
            repo=str(repo),
            item=_ITEM_ID,
            janitor=None,
            journal=str(repo / "tmp" / "journal.jsonl"),
            invoker=None,
            force=True,
            regrade=False,
            as_json=False,
        )
    )

    assert exit_code == 3
    stored = materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]
    assert (stored.status, stored.rework_pending) == ("active", True)


def test_an_open_handed_off_rework_is_held_with_a_named_reason(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo, rows=_HANDED_OFF_REWORK_ROWS)
    forge = _Forge(view=_view(state="OPEN", armed=True))

    recovered, held = _pass(repo=repo, journal=journal, forge=forge)

    assert recovered == ()
    assert [(h.work_item_id, h.hold_reason) for h in held] == [(_ITEM_ID, "run-succeeded")]
    assert "merge-wait-handed-off" in (held[0].detail or "")


@pytest.mark.parametrize(
    "rows",
    [
        # The ORIGINAL dispatch handed off and merged; the rework has not been admitted.
        [_LAUNCH, _handoff_row()],
        # The rework was admitted, and its dispatch has not opened yet.
        [_LAUNCH, _handoff_row(), _REWORK_ADMIT],
        # The rework dispatch opened and died before it published anything.
        [_LAUNCH, _handoff_row(), _REWORK_ADMIT, _LAUNCH],
    ],
    ids=["original-handoff", "admitted-not-opened", "died-before-publishing"],
)
def test_a_parked_rework_is_never_surveyed(tmp_path: Path, rows: list[dict[str, object]]) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(repo=repo, rows=rows)
    forge = _Forge(view=_view(state="MERGED", armed=False))

    recovered, held = _pass(repo=repo, journal=journal, forge=forge)

    assert (recovered, held) == ((), ())
    assert forge.argvs == []


@dataclass(kw_only=True)
class _ValveRunner:
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        self.calls.append(argv)
        if argv[:3] == ["gh", "pr", "view"]:
            return CommandResult(
                exit_code=0,
                stdout=_view(state="MERGED", armed=False),
                stderr="",
            )
        return CommandResult(exit_code=0, stdout="origin/master", stderr="")


@dataclass(frozen=True, kw_only=True)
class _PassingAcceptancePass:
    proof: None = None
    verdict: str = "PASS"
    absent_evidence: tuple[str, ...] = ()

    def journal_record(self, *, work_item_id: str, policy: str) -> dict[str, object]:
        return {
            "stage": "acceptance-ai-pass",
            "work_item_id": work_item_id,
            "verdict": self.verdict,
            "acceptance_policy": policy,
        }

"""What a resume measures about an `active` claim, and the remedy that follows.

Scenario 221 of `SPECIFICATION/scenarios.md`, driven through the real gather
(`gather_resume`) and the real ladder (`resume_refusals`) rather than through a
hand-built observation, because the defect was a disagreement between the two:
the ladder named `reconcile-runs` for every `active` item, and the gather had
never told it whether the claim's run succeeded.

THE FACTORY LISTING CARRIES THE RUN'S STATUS, and it is the only source the
gather has for "the run succeeded". The same fixture with the run `failed` is the
control: it must keep naming `reconcile-runs`, which is the release for a claim
whose run did not succeed. The label cases run against the in-memory tenant, so
a held item is held in the ledger and not in the observation the test wrote.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_merge_hold import update_work_item_merge_hold
from livespec_orchestrator_beads_fabro._store_rework_mutations import (
    update_work_item_rework_pending,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_resume_observation as observation_module,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import (
    gather_resume,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    resume_refusals,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-sufca7"
_HEAD = "f" * 40
_RUN = "01M62WN80GEFPBFVFT5XHZN27P"
_PR = 3913
_TENANT = """{
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


@dataclass(kw_only=True)
class _Runner:
    answers: dict[str, CommandResult]
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
        key = argv[2] if Path(argv[0]).name == "gh" else argv[1]
        return self.answers.get(key, CommandResult(exit_code=1, stdout="", stderr=""))


def _ok(*, stdout: str) -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _runner(*, run_status: str, pr_state: str = "OPEN", forge_ok: bool = True) -> _Runner:
    body = (
        f"Proof of Done — verified — run {_RUN} — 2026-10-29T05:10:00Z\n\n"
        f"## Assertion 1 — It merges.\n\nPublish-branch head: {_HEAD}\n\n"
        "Proof mode: factory_captured.\n"
    )
    listing = [{"number": _PR, "state": pr_state, "headRefOid": _HEAD}]
    return _Runner(
        answers={
            "list": _ok(stdout=json.dumps(listing))
            if forge_ok
            else CommandResult(exit_code=1, stdout="", stderr="forge down"),
            "view": _ok(stdout=json.dumps({"comments": [{"body": body, "url": "https://x/c/1"}]})),
            "ps": _ok(
                stdout=json.dumps(
                    [{"run_id": _RUN, "status": run_status, "goal": f"Work-item: {_ITEM_ID}"}]
                )
            ),
            "inspect": _ok(stdout=json.dumps([{"status": run_status, "checkpoints": []}])),
        }
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A succeeded run whose merge wait ran out",
        description="## Definition of Done\n\n- It merges.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-29T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _first_refusal(*, repo: Path, runner: _Runner, tenant: bool = True) -> str:
    (repo / "tmp").mkdir(exist_ok=True)
    if tenant:
        _ = (repo / ".livespec.jsonc").write_text(_TENANT, encoding="utf-8")
        append_work_item(path=_store(), item=_item())
    journal = repo / "tmp" / "journal.jsonl"
    _ = journal.write_text(
        json.dumps({"stage": "run-stamp", "work_item_id": _ITEM_ID, "run_id": _RUN}) + "\n",
        encoding="utf-8",
    )
    gather = gather_resume(
        args=argparse.Namespace(fabro_bin="fabro", fabro_factory_target=None),
        repo=repo,
        item=_item(),
        journal_path=journal,
        runner=runner,
    )
    return resume_refusals(observation=gather.observation)[0]


def test_a_succeeded_run_with_an_open_pull_request_is_released_by_the_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    refusal = _first_refusal(repo=tmp_path, runner=_runner(run_status="succeeded"))

    assert f"move:{_ITEM_ID}:ready" in refusal
    assert "reconcile-runs" not in refusal


def test_a_succeeded_run_with_a_merged_pull_request_is_closed_out_by_reconcile_merged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    refusal = _first_refusal(
        repo=tmp_path, runner=_runner(run_status="succeeded", pr_state="MERGED")
    )

    assert "reconcile-merged" in refusal
    assert "reconcile-runs" not in refusal


def test_a_failed_run_keeps_the_reconcile_runs_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    refusal = _first_refusal(repo=tmp_path, runner=_runner(run_status="failed"))

    assert "reconcile-runs" in refusal
    assert f"move:{_ITEM_ID}:ready" not in refusal


def test_an_unreadable_forge_offers_no_status_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    refusal = _first_refusal(repo=tmp_path, runner=_runner(run_status="succeeded", forge_ok=False))

    assert "forge" in refusal
    assert f"move:{_ITEM_ID}:ready" not in refusal


@pytest.mark.parametrize("label", ["merge-hold", "rework:pending"])
def test_an_item_carrying_a_route_keeping_label_is_not_offered_the_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: str
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tmp").mkdir()
    _ = (tmp_path / ".livespec.jsonc").write_text(_TENANT, encoding="utf-8")
    append_work_item(path=_store(), item=_item())
    if label == "merge-hold":
        update_work_item_merge_hold(path=_store(), item_id=_ITEM_ID, value=True)
    else:
        update_work_item_rework_pending(path=_store(), item_id=_ITEM_ID, value=True)

    refusal = _first_refusal(repo=tmp_path, runner=_runner(run_status="succeeded"), tenant=False)

    assert label in refusal
    assert f"move:{_ITEM_ID}:ready" not in refusal
    assert "reconcile-runs" not in refusal


def test_an_unreadable_label_record_offers_no_status_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        observation_module, "read_dispatch_labels", lambda **_: "ledger label read failed"
    )

    refusal = _first_refusal(repo=tmp_path, runner=_runner(run_status="succeeded"))

    assert "labels-unreadable" in refusal
    assert f"move:{_ITEM_ID}:ready" not in refusal

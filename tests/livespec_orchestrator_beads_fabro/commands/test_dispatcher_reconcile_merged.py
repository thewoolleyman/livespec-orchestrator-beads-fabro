"""Tests for the Dispatcher's active-merged reconcile valve."""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import janitor_checkout_path
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


@dataclass(frozen=True, kw_only=True)
class _AcceptancePass:
    verdict: str

    def journal_record(self, *, work_item_id: str, policy: str) -> dict[str, object]:
        return {
            "stage": "acceptance-ai-pass",
            "work_item_id": work_item_id,
            "verdict": self.verdict,
            "acceptance_policy": policy,
        }


@dataclass(kw_only=True)
class _Runner:
    queue: list[CommandResult]
    calls: list[tuple[list[str], Path]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (timeout_seconds, env)
        self.calls.append((argv, cwd))
        return self.queue.pop(0)


def test_reconcile_merged_active_item_runs_post_merge_janitor_then_accepts(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    repo = _repo(tmp_path=tmp_path)
    item = _item(status="active", acceptance_policy="ai-only")
    append_work_item(path=_config(), item=item)
    runner = _Runner(
        queue=[_ok(stdout=_pr_json(number=1381, state="MERGED", sha="0bd9ce1"))] + [_ok()] * 8
    )
    _patch_runner(monkeypatch=monkeypatch, runner=runner)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _AcceptancePass(verdict="PASS"),
    )

    exit_code = main(
        argv=[
            "reconcile-merged",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == [
        {
            "work_item_id": item.id,
            "status": "green",
            "stage": "done",
            "pr_number": 1381,
            "merge_sha": "0bd9ce1",
            "detail": "merged, post-merge janitor green",
            "fabro_run_id": None,
        }
    ]
    stored = materialize_work_items(records=read_work_items(path=_config()))[item.id]
    assert (stored.status, stored.resolution) == ("done", "completed")
    assert stored.audit is not None
    assert (stored.audit.pr_number, stored.audit.merge_sha) == (1381, "0bd9ce1")
    records = _journal_records(repo=repo)
    stages = [record["stage"] for record in records]
    assert "fabro-run" not in stages
    assert stages == [
        "reconcile-pr-view-branch",
        "pull-primary",
        "janitor-checkout-preclean",
        "janitor-checkout-add",
        "janitor-checkout-trust",
        "janitor-checkout-bootstrap",
        "janitor-core-provision",
        "janitor-post-merge",
        "janitor-checkout-remove",
        "ledger-complete",
        "acceptance-ai-pass",
        "ledger-accept",
        "auto-disposition",
        "outcome",
    ]


def test_reconcile_merged_resolves_merged_pr_by_title_search(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    repo = _repo(tmp_path=tmp_path)
    item = _item(status="active")
    append_work_item(path=_config(), item=item)
    runner = _Runner(
        queue=[
            CommandResult(exit_code=1, stdout="", stderr="not found"),
            _ok(stdout=json.dumps([_list_pr(number=17, title=f"fix {item.id}", sha="abc777")])),
            *[_ok() for _ in range(8)],
        ]
    )
    _patch_runner(monkeypatch=monkeypatch, runner=runner)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _AcceptancePass(verdict="PASS"),
    )

    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", item.id, "--json"])

    assert exit_code == 0
    stored = materialize_work_items(records=read_work_items(path=_config()))[item.id]
    assert stored.audit is not None
    assert (stored.audit.pr_number, stored.audit.merge_sha) == (17, "abc777")
    stages = [record["stage"] for record in _journal_records(repo=repo)]
    assert stages[:2] == ["reconcile-pr-view-branch", "reconcile-pr-list-merged"]


def test_reconcile_merged_janitor_red_leaves_item_active(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    repo = _repo(tmp_path=tmp_path)
    item = _item(status="active")
    append_work_item(path=_config(), item=item)
    runner = _Runner(
        queue=[
            _ok(stdout=_pr_json(number=9, state="MERGED", sha="badc0de")),
            _ok(),
            _ok(),
            _ok(),
            _ok(),
            _ok(),
            _ok(),
            CommandResult(exit_code=1, stdout="", stderr="janitor failed"),
        ]
    )
    _patch_runner(monkeypatch=monkeypatch, runner=runner)

    exit_code = main(
        argv=[
            "reconcile-merged",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--json",
        ]
    )

    assert exit_code == 1
    assert json.loads(capsys.readouterr().out)[0]["stage"] == "janitor-post-merge"
    stored = materialize_work_items(records=read_work_items(path=_config()))[item.id]
    assert stored.status == "active"
    stages = [record["stage"] for record in _journal_records(repo=repo)]
    assert "ledger-complete" not in stages
    assert stages[-1] == "outcome"


def test_reconcile_merged_refuses_live_dispatch_lock_before_pr_resolution(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    repo = _repo(tmp_path=tmp_path)
    item = _item(status="active")
    append_work_item(path=_config(), item=item)
    runner = _Runner(
        queue=[_ok(stdout=_pr_json(number=9, state="MERGED", sha="badc0de"))] + [_ok()] * 8
    )
    _patch_runner(monkeypatch=monkeypatch, runner=runner)
    _write_dispatch_lock(
        repo=repo,
        item_id=item.id,
        pid=os.getpid(),
        started_at=1.0,
        dispatch_id="dispatch-live",
    )

    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", item.id])

    assert exit_code == 3
    err = capsys.readouterr().err
    assert "dispatch lock is held by live pid" in err
    assert "fabro ps" in err
    assert "age" in err
    assert runner.calls == []
    assert not (repo / "tmp" / "fabro-dispatch-journal.jsonl").exists()


@pytest.mark.parametrize("pid", [None, 999_999_999])
def test_reconcile_merged_proceeds_when_dispatch_lock_absent_or_stale(
    pid: int | None,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    repo = _repo(tmp_path=tmp_path)
    item = _item(status="active")
    append_work_item(path=_config(), item=item)
    if pid is not None:
        _write_dispatch_lock(
            repo=repo,
            item_id=item.id,
            pid=pid,
            started_at=1.0,
            dispatch_id="dispatch-stale",
        )
    runner = _Runner(
        queue=[_ok(stdout=_pr_json(number=10, state="MERGED", sha="abc010"))] + [_ok()] * 8
    )
    _patch_runner(monkeypatch=monkeypatch, runner=runner)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _AcceptancePass(verdict="PASS"),
    )

    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", item.id])

    assert exit_code == 0
    assert runner.calls[0][0][:3] == ["gh", "pr", "view"]
    assert "post-merge janitor green" in capsys.readouterr().out


def test_reconcile_merged_uses_checkout_path_distinct_from_loop_janitor(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    module = _reconcile_module()
    repo = _repo(tmp_path=tmp_path)
    item = _item(id="bd-ib-path")

    plan = module.reconcile_plan(repo=repo, item=item, janitor=None)

    assert plan.janitor_checkout != janitor_checkout_path(repo=repo, work_item_id=item.id)
    assert plan.janitor_checkout.name == f"janitor-reconcile-{item.id}"


@pytest.mark.parametrize("status", ["ready", "acceptance"])
def test_reconcile_merged_refuses_non_active_items(
    status: str,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    repo = _repo(tmp_path=tmp_path)
    item = _item(status=status)
    append_work_item(path=_config(), item=item)

    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", item.id])

    assert exit_code == 3
    assert "expected active" in capsys.readouterr().err


def test_reconcile_merged_refuses_unknown_repo_and_item(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    missing_repo = tmp_path / "missing"

    missing_repo_exit = main(
        argv=["reconcile-merged", "--repo", str(missing_repo), "--item", "bd-ib-missing"]
    )
    repo = _repo(tmp_path=tmp_path)
    missing_item_exit = main(
        argv=["reconcile-merged", "--repo", str(repo), "--item", "bd-ib-missing"]
    )

    assert (missing_repo_exit, missing_item_exit) == (3, 3)
    err = capsys.readouterr().err
    assert "--repo does not exist" in err
    assert "work-item bd-ib-missing not found" in err


def test_reconcile_merged_refuses_bad_janitor_argv(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    repo = _repo(tmp_path=tmp_path)
    item = _item(status="active")
    append_work_item(path=_config(), item=item)

    exit_code = main(
        argv=["reconcile-merged", "--repo", str(repo), "--item", item.id, "--janitor", "not-json"]
    )

    assert exit_code == 2
    assert "--janitor must be a JSON array of strings" in capsys.readouterr().err


def test_reconcile_merged_refuses_when_no_merged_pr_resolves(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    repo = _repo(tmp_path=tmp_path)
    item = _item(status="active")
    append_work_item(path=_config(), item=item)
    runner = _Runner(
        queue=[
            CommandResult(exit_code=1, stdout="", stderr="not found"),
            _ok(stdout="[]"),
        ]
    )
    _patch_runner(monkeypatch=monkeypatch, runner=runner)

    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", item.id])

    assert exit_code == 3
    assert "no merged PR found" in capsys.readouterr().err


def test_reconcile_merged_refuses_ambiguous_title_search_candidates(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    repo = _repo(tmp_path=tmp_path)
    item = _item(id="bd-ib-target", status="active")
    append_work_item(path=_config(), item=item)
    runner = _Runner(
        queue=[
            CommandResult(exit_code=1, stdout="", stderr="not found"),
            _ok(
                stdout=json.dumps(
                    [
                        _list_pr(number=4, title=f"fix {item.id}", sha="ddd"),
                        _list_pr(number=5, title=f"follow-up {item.id}", sha="eee"),
                    ]
                )
            ),
        ]
    )
    _patch_runner(monkeypatch=monkeypatch, runner=runner)

    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", item.id])

    assert exit_code == 3
    err = capsys.readouterr().err
    assert "ambiguous merged PR candidates" in err
    assert "#4 ddd" in err
    assert "#5 eee" in err
    assert not (repo / "tmp" / "fabro-dispatch-journal.jsonl").exists()


def test_parse_merged_pr_list_accepts_branch_or_title_and_rejects_unusable_shapes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    module = _reconcile_module()
    item = _item(id="bd-ib-target")

    assert (
        module.parse_merged_pr_list(stdout="not json", item=item, branch="feat/bd-ib-target") == ()
    )
    assert module.parse_merged_pr_list(stdout="{}", item=item, branch="feat/bd-ib-target") == ()
    matches = module.parse_merged_pr_list(
        stdout=json.dumps(
            [
                "bad",
                _list_pr(number=1, title="other", sha="aaa", state="OPEN"),
                _list_pr(number=2, title="other", sha="bbb", head="feat/other"),
                _list_pr(number="bad", title="bd-ib-target", sha="ccc"),
                _list_pr(number=3, title="bd-ib-target", sha=None),
                _list_pr(number=4, title="other", sha="ddd", head="feat/bd-ib-target"),
                _list_pr(number=5, title="fix bd-ib-target", sha="eee"),
            ]
        ),
        item=item,
        branch="feat/bd-ib-target",
    )

    assert [(match.number, match.merge_sha) for match in matches] == [(4, "ddd"), (5, "eee")]


def test_reconcile_merged_does_not_relax_forbidden_move_targets(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    from livespec_orchestrator_beads_fabro.commands._drive_policy_valves import move_item

    result = move_item(
        config=_config(),
        aid="move:bd-ib-active:acceptance",
        item=_item(id="bd-ib-active", status="active"),
        target_status="acceptance",
    )

    assert result["status"] == "failed"
    assert result["domain_error"] == "forbidden-move-target"
    assert "guarded paths" in str(result["summary"])


def _assert_reconcile_command_registered(*, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(argv=["--help"])
    assert "reconcile-merged" in capsys.readouterr().out


def _patch_runner(*, monkeypatch: pytest.MonkeyPatch, runner: _Runner) -> None:
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged.ShellCommandRunner",
        lambda: runner,
    )


def _reconcile_module() -> ModuleType:
    return importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged"
    )


def _write_dispatch_lock(
    *, repo: Path, item_id: str, pid: int, started_at: float, dispatch_id: str
) -> None:
    path = repo / "tmp" / f"fabro-dispatch-{item_id}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps(
            {
                "work_item_id": item_id,
                "pid": pid,
                "started_at_epoch": started_at,
                "dispatch_id": dispatch_id,
            }
        ),
        encoding="utf-8",
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        (
            '{"livespec-orchestrator-beads-fabro": {'
            '"connection": {"prefix": "bd-ib"}, '
            '"dispatcher": {"acceptance_mode": "ai-only"}'
            "}}"
        ),
        encoding="utf-8",
    )
    return repo


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-lza6",
        type="task",
        status="active",
        title="Merged active item",
        description="Reconcile the already merged PR.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-07-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _ok(*, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _pr_json(*, number: int, state: str, sha: str | None) -> str:
    return json.dumps(
        {
            "number": number,
            "state": state,
            "autoMergeRequest": {},
            "mergeStateStatus": "CLEAN",
            "mergeCommit": {"oid": sha},
            "statusCheckRollup": [],
        }
    )


def _list_pr(
    *, number: object, title: str, sha: str | None, state: str = "MERGED", head: str = "branch"
) -> dict[str, object]:
    return {
        "number": number,
        "title": title,
        "headRefName": head,
        "state": state,
        "mergeCommit": {"oid": sha},
    }


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]

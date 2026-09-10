"""Tests for the Dispatcher's active-merged reconcile valve."""

from __future__ import annotations

import importlib
import json
import os
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_completion,
    _dispatcher_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import janitor_checkout_path
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


@pytest.fixture(autouse=True)
def _isolated_worktree_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Give each test its own `$HOME` so the janitor checkout lock is per-test.

    `janitor_reconcile_checkout_path` resolves under `Path.home()/.worktrees`,
    and its `.lock` sibling is a REAL file the reconcile valve claims for
    exclusive access. Every test here reuses the repo dir name `repo` and the
    item id `bd-ib-lza6`, so `tmp_path` isolation alone does NOT separate them:
    the lock path is identical across the module. Under `pytest -n` two of
    these tests land on different xdist workers at once, the second loses the
    claim, and the valve correctly reports `janitor-env-degraded` with exit 1 —
    a flake whose message describes a host-environment problem rather than the
    test collision that caused it. Scrubbing `$HOME` is the idiom the other
    janitor-driving suites already use.
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


@dataclass(frozen=True, kw_only=True)
class _AcceptancePass:
    verdict: str
    absent_evidence: tuple[str, ...] = ()

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
        queue=[
            *_plan_build_probe(),
            _ok(stdout=_pr_json(number=1381, state="MERGED", sha="0bd9ce1")),
            _ok(),
            *_venue_resolution(),
            *[_ok()] * 8,
        ]
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
        "janitor-checkout-bootstrap-in-checkout",
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
            *_plan_build_probe(),
            CommandResult(exit_code=1, stdout="", stderr="not found"),
            _ok(stdout=json.dumps([_list_pr(number=17, title=f"fix {item.id}", sha="abc777")])),
            _ok(),
            *_venue_resolution(),
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


@pytest.mark.parametrize("status", ["backlog", "ready", "blocked"])
def test_reconcile_merged_accepts_merge_verified_parked_items(
    status: str,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    repo = _repo(tmp_path=tmp_path)
    item = _item(status=status)
    append_work_item(path=_config(), item=item)
    runner = _Runner(
        queue=[
            *_plan_build_probe(),
            _ok(stdout=_pr_json(number=1654, state="MERGED", sha="33b230b6")),
            _ok(),
            *_venue_resolution(),
            *[_ok()] * 8,
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
    assert (stored.status, stored.resolution) == ("done", "completed")
    assert stored.audit is not None
    assert (stored.audit.pr_number, stored.audit.merge_sha) == (1654, "33b230b6")
    stages = [record["stage"] for record in _journal_records(repo=repo)]
    assert "fabro-run" not in stages
    assert stages[:2] == ["reconcile-pr-view-branch", "pull-primary"]


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
            *_plan_build_probe(),
            _ok(stdout=_pr_json(number=9, state="MERGED", sha="badc0de")),
            _ok(),
            *_venue_resolution(),
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


def test_dispatch_lock_stays_live_when_process_start_time_is_unobservable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item_id = "bd-ib-lock"
    _write_dispatch_lock(
        repo=repo,
        item_id=item_id,
        pid=os.getpid(),
        started_at=1.0,
        dispatch_id="dispatch-live",
    )
    monkeypatch.setattr(
        _dispatcher_dispatch_lock,
        "process_started_at_epoch",
        lambda **_: None,
    )

    assert _dispatcher_dispatch_lock.live_dispatch_lock(repo=repo, work_item_id=item_id)


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
        queue=[
            *_plan_build_probe(),
            _ok(stdout=_pr_json(number=9, state="MERGED", sha="badc0de")),
            _ok(),
            *_venue_resolution(),
            *[_ok()] * 8,
        ]
    )
    _patch_runner(monkeypatch=monkeypatch, runner=runner)
    _write_dispatch_lock(
        repo=repo,
        item_id=item.id,
        pid=os.getpid(),
        started_at=time.time(),
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
        queue=[
            *_plan_build_probe(),
            _ok(stdout=_pr_json(number=10, state="MERGED", sha="abc010")),
            _ok(),
            *_venue_resolution(),
            *[_ok()] * 8,
        ]
    )
    _patch_runner(monkeypatch=monkeypatch, runner=runner)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _AcceptancePass(verdict="PASS"),
    )

    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", item.id])

    assert exit_code == 0
    # calls[0] is plan build's default-branch probe; the PR read follows it.
    assert runner.calls[1][0][:3] == ["gh", "pr", "view"]
    assert "post-merge janitor green" in capsys.readouterr().out


def test_reconcile_merged_uses_checkout_path_distinct_from_loop_janitor(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    module = _reconcile_module()
    repo = _repo(tmp_path=tmp_path)
    item = _item(id="bd-ib-path")

    plan = module.reconcile_plan(
        repo=repo, item=item, janitor=None, runner=_Runner(queue=[*_plan_build_probe()])
    )

    assert plan.janitor_checkout != janitor_checkout_path(repo=repo, work_item_id=item.id)
    assert plan.janitor_checkout.name == f"janitor-reconcile-{item.id}"


def test_reconcile_plan_uses_resolved_fabro_bin(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    module = _reconcile_module()
    repo = _repo(tmp_path=tmp_path)
    item = _item(id="bd-ib-fabro")
    fabro_bin = tmp_path / "resolved-fabro"
    _ = fabro_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fabro_bin.chmod(0o755)
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", str(fabro_bin))

    plan = module.reconcile_plan(
        repo=repo, item=item, janitor=None, runner=_Runner(queue=[*_plan_build_probe()])
    )

    assert plan.fabro_bin == str(fabro_bin)
    assert plan.fabro_bin != "fabro"


@pytest.mark.parametrize("status", ["acceptance", "done"])
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
    assert "expected active or parked" in capsys.readouterr().err


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


def test_reconcile_merged_refuses_an_unattributed_invocation_before_the_tenant_read(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`require_invoker` refuses this valve at startup, naming both inputs.

    The item is deliberately NEVER filed: if the refusal fired after the tenant
    read, this invocation would have died on "work-item not found" instead, so
    the assertion on the refusal TEXT is what proves the ordering.
    """
    _assert_reconcile_command_registered(capsys=capsys)
    monkeypatch.delenv("LIVESPEC_INVOKER", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"require_invoker": true}}}',
        encoding="utf-8",
    )

    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", "bd-ib-unfiled"])

    assert exit_code == 3
    err = capsys.readouterr().err
    assert "--invoker" in err
    assert "LIVESPEC_INVOKER" in err
    assert "not found" not in err


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
            *_plan_build_probe(),
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
    shared_journal = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    shared_journal.parent.mkdir(parents=True, exist_ok=True)
    unrelated_record = {
        "stage": "dispatch-id",
        "work_item_id": "bd-other",
        "dispatch_id": "dispatch-other",
    }
    _ = shared_journal.write_text(json.dumps(unrelated_record) + "\n", encoding="utf-8")
    runner = _Runner(
        queue=[
            *_plan_build_probe(),
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
    assert shared_journal.exists()
    records = _journal_records(repo=repo)
    assert unrelated_record in records
    assert [record["stage"] for record in records] == [
        "dispatch-id",
        "reconcile-pr-view-branch",
        "reconcile-pr-list-merged",
    ]


def test_parse_merged_pr_list_accepts_branch_or_title_and_rejects_unusable_shapes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    module = _reconcile_module()
    item = _item(id="bd-ib-target")

    assert (
        module.parse_merged_pr_list(
            stdout="not json", item=item, branch="feat/bd-ib-target", default_branch="trunk"
        )
        == ()
    )
    assert (
        module.parse_merged_pr_list(
            stdout="{}", item=item, branch="feat/bd-ib-target", default_branch="trunk"
        )
        == ()
    )
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
        default_branch="trunk",
    )

    assert [(match.number, match.merge_sha) for match in matches] == [(4, "ddd"), (5, "eee")]


def test_reconcile_merged_declares_the_regrade_option(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The arm is reachable at all: `--regrade` is on the subcommand's surface."""
    with pytest.raises(SystemExit):
        main(argv=["reconcile-merged", "--help"])

    assert "--regrade" in capsys.readouterr().out


def test_regrade_pass_closes_the_item_and_clears_rework_pending(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The PASS arm, driven through the REAL acceptance pass.

    Nothing about the verdict is stood in: the criteria are the item's own
    field, the merged diff is what `gh pr diff` returns, and the grade is the
    shipped `criteria_checks`. Stubbing the pass here would assert only that a
    PASS closes an item, which is the half that was never in doubt.
    """
    repo = _repo(tmp_path=tmp_path)
    item = _item(acceptance_criteria="- The regrade arm reconciles a stranded merge.\n")
    append_work_item(path=_config(), item=item)
    _seed_rework_pending(item_id=item.id, failed_ai_passes=1)
    runner = _Runner(
        queue=[
            *_plan_build_probe(),
            _ok(stdout=_pr_json(number=2459, state="MERGED", sha="51d99744")),
            # `git merge-base --is-ancestor <sha> origin/master` answers yes.
            _ok(),
            _ok(stdout=_regrade_diff()),
        ]
    )
    _patch_runner(monkeypatch=monkeypatch, runner=runner)

    exit_code = main(
        argv=["reconcile-merged", "--repo", str(repo), "--item", item.id, "--regrade", "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["status"] == "green"
    assert payload[0]["stage"] == "done"
    assert payload[0]["merge_sha"] == "51d99744"
    stored = materialize_work_items(records=read_work_items(path=_config()))[item.id]
    assert (stored.status, stored.resolution) == ("done", "completed")
    assert stored.rework_pending is False
    stages = [record["stage"] for record in _journal_records(repo=repo)]
    # No Fabro run and no janitor: the arm re-grades a merge that already landed.
    assert "fabro-run" not in stages
    assert not [stage for stage in stages if str(stage).startswith("janitor-")]
    assert stages == [
        "reconcile-pr-view-branch",
        "regrade-merge-containment",
        "acceptance-ai-pass",
        "ledger-regrade-accept",
        "outcome",
    ]
    # The containment probe asked about the resolved merge against the tip.
    assert runner.calls[2][0][-3:] == ["--is-ancestor", "51d99744", "origin/master"]


def test_regrade_fail_leaves_status_labels_and_failed_passes_untouched(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The FAIL arm writes NOTHING — the re-grade must not cost the item.

    `acceptance_failed_ai_passes` is seeded to the value the original failing
    disposition wrote, because an arm that re-charged the rework cap for a
    second look would burn exactly the item this recovery exists to rescue,
    and an unseeded metadata field could not observe that.
    """
    repo = _repo(tmp_path=tmp_path)
    item = _item(acceptance_criteria="- The merged diff carries a wholly unrelated subject.\n")
    append_work_item(path=_config(), item=item)
    _seed_rework_pending(item_id=item.id, failed_ai_passes=1)
    runner = _Runner(
        queue=[
            *_plan_build_probe(),
            _ok(stdout=_pr_json(number=2459, state="MERGED", sha="51d99744")),
            _ok(),
            _ok(stdout=_regrade_diff()),
        ]
    )
    _patch_runner(monkeypatch=monkeypatch, runner=runner)

    exit_code = main(
        argv=["reconcile-merged", "--repo", str(repo), "--item", item.id, "--regrade", "--json"]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)[0]["stage"] == "regrade"
    assert "left unchanged" in captured.err
    stored = materialize_work_items(records=read_work_items(path=_config()))[item.id]
    assert (stored.status, stored.resolution) == ("active", None)
    assert stored.rework_pending is True
    ledger_row = make_beads_client(config=_config()).show_issue(issue_id=item.id)
    assert ledger_row["metadata"]["acceptance_failed_ai_passes"] == 1
    stages = [record["stage"] for record in _journal_records(repo=repo)]
    assert "ledger-regrade-accept" not in stages


def test_regrade_refuses_every_merge_it_cannot_prove(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each way the unfabricatable evidence can fail, refusing on its own.

    The three legs are: no merged PR resolves at all; several do, so the arm
    cannot say WHICH merge it would be closing the item against; and one
    resolves whose merge commit this repository cannot show on the default
    branch. Any leg alone would leave the others unproven, and all three must
    refuse BEFORE the acceptance pass runs — the whole point of the arm is that
    it grades a merge it has established, never one it was told about.
    """
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    _seed_rework_pending(item_id=item.id, failed_ai_passes=1)
    unmerged = _Runner(
        queue=[
            *_plan_build_probe(),
            CommandResult(exit_code=1, stdout="", stderr="not found"),
            _ok(stdout="[]"),
        ]
    )
    _patch_runner(monkeypatch=monkeypatch, runner=unmerged)

    unmerged_exit = main(
        argv=["reconcile-merged", "--repo", str(repo), "--item", item.id, "--regrade"]
    )

    ambiguous = _Runner(
        queue=[
            *_plan_build_probe(),
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
    _patch_runner(monkeypatch=monkeypatch, runner=ambiguous)

    ambiguous_exit = main(
        argv=["reconcile-merged", "--repo", str(repo), "--item", item.id, "--regrade"]
    )

    uncontained = _Runner(
        queue=[
            *_plan_build_probe(),
            _ok(stdout=_pr_json(number=2459, state="MERGED", sha="51d99744")),
            CommandResult(exit_code=1, stdout="", stderr=""),
        ]
    )
    _patch_runner(monkeypatch=monkeypatch, runner=uncontained)

    uncontained_exit = main(
        argv=["reconcile-merged", "--repo", str(repo), "--item", item.id, "--regrade"]
    )

    assert (unmerged_exit, ambiguous_exit, uncontained_exit) == (3, 3, 3)
    err = capsys.readouterr().err
    assert "no merged PR resolves" in err
    assert "ambiguous merged PR candidates" in err
    assert "is not an ancestor of origin/master" in err
    stored = materialize_work_items(records=read_work_items(path=_config()))[item.id]
    assert (stored.status, stored.rework_pending) == ("active", True)
    stages = [record["stage"] for record in _journal_records(repo=repo)]
    assert "acceptance-ai-pass" not in stages


def test_regrade_is_refused_on_an_item_carrying_no_rework_marker(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _assert_reconcile_command_registered(capsys=capsys)
    repo = _repo(tmp_path=tmp_path)
    item = _item(status="active")
    append_work_item(path=_config(), item=item)

    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", item.id, "--regrade"])

    assert exit_code == 3
    assert "does not carry rework:pending" in capsys.readouterr().err


def test_reconcile_merged_keeps_the_rework_pending_refusal_without_regrade(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The unchanged default: a marked item is still refused, and told the arm."""
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    _seed_rework_pending(item_id=item.id, failed_ai_passes=1)

    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", item.id])

    assert exit_code == 3
    err = capsys.readouterr().err
    assert "carries rework:pending" in err
    assert "--force does not bypass this refusal" in err
    assert "--regrade" in err
    assert not (repo / "tmp" / "fabro-dispatch-journal.jsonl").exists()


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
            # The governed repository DECLARES the livespec core its janitor
            # provisions; an undeclared pin degrades post-merge provisioning.
            '"compat": {"pinned": "master"}, '
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


def _seed_rework_pending(*, item_id: str, failed_ai_passes: int) -> None:
    """Seed the ledger state a FAILING acceptance disposition leaves behind.

    Written through the raw label and the raw metadata key the store
    materializes those two fields FROM, so the fixture states the ledger fact
    rather than borrowing either writer. `append_work_item` cannot seed the
    marker at all — only the two entries the rework-pending contract names may
    stamp it — so passing `rework_pending=True` to the item would read back
    False and the arm under test would never be reached.

    The metadata is MERGED rather than replaced: the fake's `update_issue`
    overwrites the whole column, and the rank the append just wrote lives
    there.
    """
    client = make_beads_client(config=_config())
    metadata = dict(client.show_issue(issue_id=item_id).get("metadata", {}))
    metadata["acceptance_failed_ai_passes"] = failed_ai_passes
    client.update_issue(issue_id=item_id, add_labels=["rework:pending"], metadata=metadata)


def _regrade_diff() -> str:
    """A merged patch carrying the PASS criterion's vocabulary and not the FAIL's."""
    return (
        "diff --git a/commands/_dispatcher_reconcile_regrade.py "
        "b/commands/_dispatcher_reconcile_regrade.py\n"
        "--- a/commands/_dispatcher_reconcile_regrade.py\n"
        "+++ b/commands/_dispatcher_reconcile_regrade.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+# The regrade arm reconciles a stranded merge.\n"
        "+REGRADE_STAGE = 'regrade'\n"
    )


def _plan_build_probe() -> list[CommandResult]:
    """The ONE read `reconcile_plan` takes before anything else: the ratified
    default-branch probe, whose answer rides the plan's resolved integration
    contract and is what the venue later names its tip from."""
    return [_ok(stdout="origin/master")]


def _venue_resolution() -> list[CommandResult]:
    """The ONE venue read between pull-primary and the preclean: the reconcile
    janitor provisions at the default-branch TIP that contains the merge, so it
    probes for merge containment. The branch itself came off the contract."""
    return [_ok()]


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

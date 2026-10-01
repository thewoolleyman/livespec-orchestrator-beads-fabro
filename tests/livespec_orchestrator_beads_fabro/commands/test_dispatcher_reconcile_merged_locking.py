"""Locking and stale-heartbeat tests for reconcile-merged."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_completion,
    _dispatcher_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


@dataclass(frozen=True, kw_only=True)
class _AcceptancePass:
    # The proof leg the real pass carries. `None` is what a legacy-source item
    # resolves to, and it is the right stand-in here: these cases are about the
    # DISPOSITION the verdict routes to, and the pointer write skips an item
    # with no record rather than changing which branch runs.
    proof: None = None
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


def test_reconcile_merged_allows_stale_dispatch_lock(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item(status="active")
    append_work_item(path=_config(), item=item)
    _write_dispatch_lock(repo=repo, item_id=item.id, pid=999_999_999, started_at=1.0)
    runner = _Runner(
        queue=[
            *_plan_build_probe(),
            _ok(stdout=_pr_json(number=11, state="MERGED", sha="abc111")),
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


def test_reconcile_merged_force_bypasses_live_dispatch_lock(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item(status="active")
    append_work_item(path=_config(), item=item)
    _write_dispatch_lock(repo=repo, item_id=item.id, pid=os.getpid(), started_at=1.0)
    runner = _Runner(
        queue=[
            *_plan_build_probe(),
            _ok(stdout=_pr_json(number=12, state="MERGED", sha="abc222")),
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
            "--force",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["stage"] == "done"
    stored = materialize_work_items(records=read_work_items(path=_config()))[item.id]
    assert stored.status == "done"


def test_dispatch_lock_ignores_malformed_payloads(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    item_id = "bd-ib-lock"
    path = repo / "tmp" / f"fabro-dispatch-{item_id}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)

    for payload in (
        "[]",
        json.dumps({"work_item_id": "other", "pid": os.getpid(), "started_at_epoch": 1.0}),
        json.dumps({"work_item_id": item_id, "pid": True, "started_at_epoch": 1.0}),
        json.dumps({"work_item_id": item_id, "pid": os.getpid(), "started_at_epoch": True}),
        json.dumps(
            {
                "work_item_id": item_id,
                "pid": os.getpid(),
                "started_at_epoch": 1.0,
                "dispatch_id": 7,
            }
        ),
    ):
        _ = path.write_text(payload, encoding="utf-8")
        assert _dispatcher_dispatch_lock.live_dispatch_lock(repo=repo, work_item_id=item_id) is None


def test_dispatch_lock_rejects_reused_live_pid(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    item_id = "bd-ib-lock"
    lock_started_at = 1_000.0
    _write_dispatch_lock(
        repo=repo,
        item_id=item_id,
        pid=os.getpid(),
        started_at=lock_started_at,
    )

    assert _dispatcher_dispatch_lock.live_dispatch_lock(repo=repo, work_item_id=item_id) is None


def test_dispatch_lock_written_by_current_process_stays_live(tmp_path: Path) -> None:
    item_id = "bd-ib-lock"

    _ = _dispatcher_dispatch_lock.write_dispatch_lock(
        repo=tmp_path,
        work_item_id=item_id,
        dispatch_id="dispatch-live",
    )

    assert _dispatcher_dispatch_lock.live_dispatch_lock(repo=tmp_path, work_item_id=item_id)


def test_write_dispatch_lock_refuses_to_overwrite_existing_claim(tmp_path: Path) -> None:
    item_id = "bd-ib-lock"
    path = _dispatcher_dispatch_lock.write_dispatch_lock(
        repo=tmp_path,
        work_item_id=item_id,
        dispatch_id="dispatch-a",
    )
    first_payload = path.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError):
        _ = _dispatcher_dispatch_lock.write_dispatch_lock(
            repo=tmp_path,
            work_item_id=item_id,
            dispatch_id="dispatch-b",
        )

    assert path.read_text(encoding="utf-8") == first_payload


def test_write_dispatch_lock_reclaims_dead_holder_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item_id = "bd-ib-lock"
    dead_pid = 999_999_999
    _write_dispatch_lock(repo=tmp_path, item_id=item_id, pid=dead_pid, started_at=1.0)

    def report_dead(*args: object) -> None:
        _ = args
        raise ProcessLookupError

    monkeypatch.setattr(_dispatcher_dispatch_lock.os, "kill", report_dead)

    path = _dispatcher_dispatch_lock.write_dispatch_lock(
        repo=tmp_path,
        work_item_id=item_id,
        dispatch_id="dispatch-new",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["pid"] == os.getpid()
    assert isinstance(payload["started_at_epoch"], float)
    assert payload["dispatch_id"] == "dispatch-new"


def test_write_dispatch_lock_refuses_live_holder_claim(tmp_path: Path) -> None:
    item_id = "bd-ib-lock"
    path = _dispatcher_dispatch_lock.write_dispatch_lock(
        repo=tmp_path,
        work_item_id=item_id,
        dispatch_id="dispatch-a",
    )
    first_payload = path.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError):
        _ = _dispatcher_dispatch_lock.write_dispatch_lock(
            repo=tmp_path,
            work_item_id=item_id,
            dispatch_id="dispatch-b",
        )

    assert path.read_text(encoding="utf-8") == first_payload


def test_write_dispatch_lock_preserves_live_replacement_when_stale_reclaim_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item_id = "bd-ib-lock"
    stale_pid = 999_999_999
    stale_payload = {
        "work_item_id": item_id,
        "pid": stale_pid,
        "started_at_epoch": 1.0,
        "dispatch_id": "dispatch-stale",
    }
    live_payload = {
        "work_item_id": item_id,
        "pid": os.getpid(),
        "started_at_epoch": 2.0,
        "dispatch_id": "dispatch-live-replacement",
    }
    path = tmp_path / "tmp" / f"fabro-dispatch-{item_id}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stale_payload), encoding="utf-8")
    live_bytes = json.dumps(live_payload, sort_keys=True).encode() + b"\n"

    def replace_stale_with_live(*args: object) -> None:
        _ = args
        path.write_bytes(live_bytes)
        raise ProcessLookupError

    monkeypatch.setattr(_dispatcher_dispatch_lock.os, "kill", replace_stale_with_live)

    with pytest.raises(FileExistsError):
        _ = _dispatcher_dispatch_lock.write_dispatch_lock(
            repo=tmp_path,
            work_item_id=item_id,
            dispatch_id="dispatch-racing-claimant",
        )

    assert path.read_bytes() == live_bytes


def test_parse_merged_pr_list_rejects_a_base_other_than_the_resolved_default(
    tmp_path: Path,
) -> None:
    """The base compared against is RESOLVED, so the same entry flips on it alone.

    Both legs run the identical record and differ only in the default branch
    handed in, which is what makes the rejection evidence about the resolution
    rather than about a branch name this fleet happens to use. The accepting leg
    is the positive control: without it a parser that rejected EVERYTHING would
    pass the rejecting leg for entirely the wrong reason.
    """
    _ = tmp_path
    from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_merged

    item = _item(id="bd-ib-target")
    stdout = json.dumps(
        [
            {
                "number": 31,
                "title": f"fix {item.id}",
                "headRefName": "branch",
                "baseRefName": "release",
                "state": "MERGED",
                "mergeCommit": {"oid": "def031"},
            }
        ]
    )

    rejected = _dispatcher_reconcile_merged.parse_merged_pr_list(
        stdout=stdout, item=item, branch="feat/bd-ib-target", default_branch="trunk"
    )
    accepted = _dispatcher_reconcile_merged.parse_merged_pr_list(
        stdout=stdout, item=item, branch="feat/bd-ib-target", default_branch="release"
    )

    assert rejected == ()
    assert [match.number for match in accepted] == [31]


def _write_dispatch_lock(*, repo: Path, item_id: str, pid: int, started_at: float) -> None:
    path = repo / "tmp" / f"fabro-dispatch-{item_id}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps(
            {
                "work_item_id": item_id,
                "pid": pid,
                "started_at_epoch": started_at,
                "dispatch_id": "dispatch-test",
            }
        ),
        encoding="utf-8",
    )


def _patch_runner(*, monkeypatch: pytest.MonkeyPatch, runner: _Runner) -> None:
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged.ShellCommandRunner",
        lambda: runner,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = {
        "livespec-orchestrator-beads-fabro": {
            "connection": {"prefix": "bd-ib"},
            # The governed repository DECLARES the livespec core its janitor
            # provisions; an undeclared pin degrades post-merge provisioning.
            "compat": {"pinned": "master"},
            "dispatcher": {"acceptance_mode": "ai-only"},
        }
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
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


def _plan_build_probe() -> list[CommandResult]:
    """The ONE read `reconcile_plan` takes before anything else: the ratified
    default-branch probe, whose answer rides the plan's resolved integration
    contract and is what the venue later names its tip from."""
    return [_ok(stdout="origin/master")]


def _venue_resolution() -> list[CommandResult]:
    """The ONE venue read between pull-primary and the preclean: the reconcile
    janitor probes the tip for merge containment; the branch came off the
    contract."""
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

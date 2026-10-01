"""Integration-tier acceptance for reconcile-merged's rework-pending handling.

Drives BOTH branches of the ratified refusal through the real
`dispatcher reconcile-merged` supervisor and the real store/client seam against
the in-memory `FakeBeadsClient` (the hermetic CI backend). Only the shell
`CommandRunner` and the acceptance pass are stood in, so the preflight decision,
the ledger reads, and the ledger writes are production code paths.

- A marked item is REFUSED whatever `--force` says, and the refusal names the
  fix-forward rework re-dispatch as the remedy. This valve exists for a dispatch
  that died mid-flight; a marked item's dispatch COMPLETED its post-run
  disposition and that disposition chose rework, so reconciling it would re-run
  a disposition that already ran.
- An unmarked merged item still reconciles all the way to `done`, because that
  is the recovery this valve exists for. Without this control the refusal could
  be over-broad and nothing would say so.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_EXIT_PRECONDITION_ERROR = 3
# Seeded through the raw label the store materializes the field from, so the
# fixture states the ledger fact rather than borrowing the writer under test.
_REWORK_PENDING_LABEL = "rework:pending"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> object:
    """Resolve the store onto the in-memory fake, fresh per case.

    There is no shared conftest at this tier, so each case owns both halves: the
    `LIVESPEC_BEADS_FAKE` resolution the production `store_config` reader
    consults, and the process-singleton reset. `$HOME` is scrubbed too, because
    the janitor checkout path resolves under `Path.home()/.worktrees` and its
    `.lock` sibling is a real file this module's reconciling case claims.
    """
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    reset_fake_singleton()
    yield
    reset_fake_singleton()


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


@dataclass(frozen=True, kw_only=True)
class _PassingAcceptancePass:
    # The proof leg the real pass carries. `None` is what a legacy-source item
    # resolves to, and it is the right stand-in here: these cases are about the
    # DISPOSITION the verdict routes to, and the pointer write skips an item
    # with no record rather than changing which branch runs.
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


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
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
            # A governed repository DECLARES the livespec core its janitor
            # provisions; an undeclared pin degrades the post-merge flow before
            # the reconcile valve's janitor can run.
            '"compat": {"pinned": "master"}, '
            '"dispatcher": {"acceptance_mode": "ai-only"}'
            "}}"
        ),
        encoding="utf-8",
    )
    return repo


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="active",
        title="A dispatched slice whose PR already merged",
        description="Reconcile the already merged PR.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-08-28T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _pr_json(*, number: int, sha: str) -> str:
    return json.dumps(
        {
            "number": number,
            "state": "MERGED",
            "autoMergeRequest": {},
            "mergeStateStatus": "CLEAN",
            "mergeCommit": {"oid": sha},
            "statusCheckRollup": [],
        }
    )


def _stored(*, item_id: str) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))[item_id]


@pytest.mark.parametrize("force_argv", [(), ("--force",)], ids=["default", "forced"])
def test_marked_item_is_refused_and_force_does_not_bypass_it(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    force_argv: tuple[str, ...],
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item(item_id="bd-ib-reconcile-marked")
    append_work_item(path=_config(), item=item)
    make_beads_client(config=_config()).update_issue(
        issue_id=item.id, add_labels=[_REWORK_PENDING_LABEL]
    )
    # A queue that would let an UNREFUSED run reach its own "no merged PR"
    # refusal, so a passing exit code cannot be mistaken for the refusal here.
    runner = _Runner(
        queue=[CommandResult(exit_code=1, stdout="", stderr="not found"), _ok(stdout="[]")]
    )
    _patch_runner(monkeypatch=monkeypatch, runner=runner)
    argv = ["reconcile-merged", "--repo", str(repo), "--item", item.id, *force_argv]

    exit_code = main(argv=argv)

    stderr = capsys.readouterr().err
    assert _REWORK_PENDING_LABEL in stderr
    # The refusal NAMES the remedy rather than only rejecting the invocation.
    assert "rework re-dispatch" in stderr
    assert "--force does not bypass this refusal" in stderr
    assert exit_code == _EXIT_PRECONDITION_ERROR
    # Refused before any half of the reconcile ran: no shell command, no
    # journal, and the item left exactly as the disposition parked it.
    assert runner.calls == []
    assert not (repo / "tmp" / "fabro-dispatch-journal.jsonl").exists()
    assert _stored(item_id=item.id).status == "active"


def test_unmarked_merged_item_still_reconciles_to_done(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item(item_id="bd-ib-reconcile-plain")
    append_work_item(path=_config(), item=item)
    # The merged-PR view, pull-primary, then the venue resolution -- the
    # reconcile janitor provisions at the default-branch TIP naming itself here,
    # not at the merge sha the PR view just reported -- and every stage after it.
    runner = _Runner(
        queue=[
            # Plan build takes the ratified default-branch probe FIRST; the venue
            # later names its tip off the contract that answer resolved into.
            _ok(stdout="origin/master"),
            _ok(stdout=_pr_json(number=1381, sha="0bd9ce1")),
            _ok(),
        ]
        + [_ok()] * 9
    )
    _patch_runner(monkeypatch=monkeypatch, runner=runner)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _PassingAcceptancePass(),
    )

    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", item.id, "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload[0]["status"] == "green"
    stored = _stored(item_id=item.id)
    assert (stored.status, stored.resolution) == ("done", "completed")
    assert stored.rework_pending is False


def _ok(*, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _patch_runner(*, monkeypatch: pytest.MonkeyPatch, runner: _Runner) -> None:
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged.ShellCommandRunner",
        lambda: runner,
    )

"""Scenario 245 — reconcile-merged closes a merged, locally built item.

`SPECIFICATION/contracts.md` section "Dispatcher loop invocation surface" (v216,
work-item bd-ib-acxptq). An item built outside the factory never passes through
dispatch, so it is never `active`: it rests at `pending-approval`, or at a plain
`ready`. The valve accepts it from that resting status when a merged pull request
identifies it by head ref or title, runs the same post-merge janitor, and moves it
to `acceptance`. A pull request that only mentions the item in its body does not
resolve it, and a red janitor leaves it where it rested.

The incident is bd-ib-y7372n (2026-10-25): built locally, merged as PR #3616 while
resting at `pending-approval`, and closable only after a hand-written move to
`active`, because the valve refused every status it now accepts here.

Everything but the valve's shell seam and the acceptance pass is production code:
the real `dispatcher.main(argv=["reconcile-merged", ...])` supervisor runs over
the real store against the in-memory fake ledger and writes a real journal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-locallybuilt"
_RUNNER_SEAM = (
    "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged.ShellCommandRunner"
)
# The janitor arm's commands after the venue read: provisioning, then the
# check suite last. Eight green results carry a green janitor through.
_GREEN_JANITOR_STEPS = 8


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> object:
    """Resolve the store onto the in-memory fake, fresh per case, with `$HOME` scrubbed."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(frozen=True, kw_only=True)
class _AcceptancePass:
    """A PASS verdict carrying the leg fields the disposition reads."""

    proof: None = None
    verdict: str = "PASS"
    absent_evidence: tuple[str, ...] = ()
    diff_reason: str = "merged diff read"
    telemetry_reason: str = "green merged dispatch with PR and merge sha"
    criteria: tuple[object, ...] = ()

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
        _ = cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        return self.queue.pop(0)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(*, status: str) -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status=status,
        title="A locally built item",
        description="Built in-session and merged without a dispatch.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-25T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
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


def _ok(*, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _not_found() -> CommandResult:
    return CommandResult(exit_code=1, stdout="", stderr="no pull requests found")


def _branch_pr_merged(*, number: int, sha: str) -> CommandResult:
    return _ok(
        stdout=json.dumps(
            {
                "number": number,
                "state": "MERGED",
                "autoMergeRequest": {},
                "mergeStateStatus": "CLEAN",
                "mergeCommit": {"oid": sha},
                "statusCheckRollup": [],
            }
        )
    )


def _merged_list(*entries: dict[str, object]) -> CommandResult:
    return _ok(stdout=json.dumps(list(entries)))


def _listed(*, number: int, title: str, body: str, sha: str) -> dict[str, object]:
    return {
        "number": number,
        "title": title,
        "body": body,
        "headRefName": f"local-build-{number}",
        "baseRefName": "master",
        "state": "MERGED",
        "mergeCommit": {"oid": sha},
    }


def _janitor_green() -> list[CommandResult]:
    """pull-primary, the venue read, then a green janitor."""
    return [_ok(), _ok(), *[_ok() for _ in range(_GREEN_JANITOR_STEPS)]]


def _janitor_red() -> list[CommandResult]:
    """pull-primary, the venue read, provisioning, then a red check suite."""
    return [
        _ok(),
        _ok(),
        *[_ok() for _ in range(_GREEN_JANITOR_STEPS - 2)],
        CommandResult(exit_code=1, stdout="", stderr="janitor failed"),
    ]


def _reconcile(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    after_probe: list[CommandResult],
) -> tuple[int, Path]:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(status=status))
    runner = _Runner(queue=[_ok(stdout="origin/master"), *after_probe])
    monkeypatch.setattr(_RUNNER_SEAM, lambda: runner)
    monkeypatch.setattr(
        _dispatcher_completion, "run_acceptance_pass", lambda **_: _AcceptancePass()
    )
    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", _ITEM_ID, "--json"])
    return exit_code, repo


def _stored() -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]


def _stages(*, repo: Path) -> list[object]:
    text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    return [json.loads(line)["stage"] for line in text.splitlines()]


def test_a_pending_approval_item_with_a_merged_branch_pull_request_enters_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sub-scenario: pending-approval, head-ref match, green janitor -> acceptance, then the pass.

    The PASS verdict carries it on to `done`, which is the acceptance pass having run.
    """
    exit_code, repo = _reconcile(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        status="pending-approval",
        after_probe=[_branch_pr_merged(number=3616, sha="5abc9046"), *_janitor_green()],
    )

    assert exit_code == 0
    stored = _stored()
    assert (stored.status, stored.resolution) == ("done", "completed")
    assert stored.audit is not None
    assert (stored.audit.pr_number, stored.audit.merge_sha) == (3616, "5abc9046")
    assert "ledger-complete" in _stages(repo=repo)


def test_a_ready_item_with_a_merged_title_match_enters_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sub-scenario: plain ready, title match beside a body mention -> acceptance, then the pass."""
    exit_code, _ = _reconcile(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        status="ready",
        after_probe=[
            _not_found(),
            _merged_list(
                _listed(number=41, title=f"feat: the change ({_ITEM_ID})", body="", sha="title41"),
                _listed(number=42, title="docs: notes", body=f"See {_ITEM_ID}.", sha="body42"),
            ),
            *_janitor_green(),
        ],
    )

    assert exit_code == 0
    stored = _stored()
    assert stored.status == "done"
    assert stored.audit is not None
    assert (stored.audit.pr_number, stored.audit.merge_sha) == (41, "title41")


@pytest.mark.parametrize("status", ["pending-approval", "ready"])
def test_a_body_mention_alone_does_not_close_a_locally_built_item(
    status: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sub-scenario: only a body mention -> refused naming the missing merged PR, status kept."""
    exit_code, repo = _reconcile(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        status=status,
        after_probe=[
            _not_found(),
            _merged_list(
                _listed(number=43, title="docs: notes", body=f"Follows {_ITEM_ID}.", sha="body43")
            ),
        ],
    )

    assert exit_code == 3
    assert "no merged PR found" in capsys.readouterr().err
    assert _stored().status == status
    assert "ledger-complete" not in _stages(repo=repo)


def test_a_red_janitor_leaves_a_pending_approval_item_where_it_rested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sub-scenario: red janitor -> status kept, and the outcome names the janitor stage."""
    exit_code, repo = _reconcile(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        status="pending-approval",
        after_probe=[_branch_pr_merged(number=3616, sha="5abc9046"), *_janitor_red()],
    )

    assert exit_code == 1
    assert json.loads(capsys.readouterr().out)[0]["stage"] == "janitor-post-merge"
    assert _stored().status == "pending-approval"
    assert "ledger-complete" not in _stages(repo=repo)


def test_an_active_item_still_resolves_a_hand_carried_body_mention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control: the body-only refusal is scoped to the locally built entry statuses.

    An `active` item keeps the body tier, because a hand-carried merge of a
    dispatched item is the case that tier exists for.
    """
    exit_code, _ = _reconcile(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        status="active",
        after_probe=[
            _not_found(),
            _merged_list(
                _listed(number=44, title="fix: launch", body=f"Implements {_ITEM_ID}.", sha="b44")
            ),
            *_janitor_green(),
        ],
    )

    assert exit_code == 0
    stored = _stored()
    assert stored.status == "done"
    assert replace(stored).audit is not None

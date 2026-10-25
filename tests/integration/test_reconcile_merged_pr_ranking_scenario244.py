"""Scenario 244 — reconcile-merged ranks how a merged PR names an item.

The valve runs through the real dispatcher command and fake ledger.  Only the
GitHub command runner and the acceptance pass are seams: that leaves the
resolution, refusal, journal, and status effects under test together.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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

_ITEM_ID = "bd-ib-ranking"
_RUNNER_SEAM = (
    "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged.ShellCommandRunner"
)
_GREEN_JANITOR_STEPS = 8


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> object:
    """Give each scenario a fresh fake tenant and janitor-lock root."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(frozen=True, kw_only=True)
class _AcceptancePass:
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


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="Rank merged pull request candidates",
        description="Resolve the carrier before mentions.",
        origin="freeform",
        gap_id=None,
        rank="a0",
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


def _listed(*, number: int, title: str, body: str, sha: str, head: str) -> dict[str, object]:
    return {
        "number": number,
        "title": title,
        "body": body,
        "headRefName": head,
        "baseRefName": "master",
        "state": "MERGED",
        "mergeCommit": {"oid": sha},
    }


def _janitor_green() -> list[CommandResult]:
    return [_ok(), _ok(), *[_ok() for _ in range(_GREEN_JANITOR_STEPS)]]


def _reconcile(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    candidates: list[dict[str, object]],
) -> tuple[int, Path]:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())
    runner = _Runner(
        queue=[
            _ok(stdout="origin/master"),
            _not_found(),
            _ok(stdout=json.dumps(candidates)),
            *_janitor_green(),
        ]
    )
    monkeypatch.setattr(_RUNNER_SEAM, lambda: runner)
    monkeypatch.setattr(
        _dispatcher_completion, "run_acceptance_pass", lambda **_: _AcceptancePass()
    )
    exit_code = main(argv=["reconcile-merged", "--repo", str(repo), "--item", _ITEM_ID])
    return exit_code, repo


def _stored() -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]


def test_a_head_ref_match_outranks_title_and_body_mentions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exit_code, _ = _reconcile(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        candidates=[
            _listed(
                number=71,
                title="feat: carrier",
                body="",
                sha="head71",
                head=f"feat/{_ITEM_ID}",
            ),
            _listed(
                number=72,
                title=f"follow-up for {_ITEM_ID}",
                body="",
                sha="title72",
                head="feat/follow-up",
            ),
            _listed(
                number=73,
                title="docs: notes",
                body=f"Follow-up to {_ITEM_ID}.",
                sha="body73",
                head="docs/notes",
            ),
        ],
    )

    assert exit_code == 0
    assert _stored().audit is not None
    assert (_stored().audit.pr_number, _stored().audit.merge_sha) == (71, "head71")


def test_a_single_title_match_outranks_body_mentions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exit_code, _ = _reconcile(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        candidates=[
            _listed(
                number=74,
                title=f"fix: {_ITEM_ID}",
                body="",
                sha="title74",
                head="fix/carrier",
            ),
            _listed(
                number=75,
                title="docs: notes",
                body=f"Follows {_ITEM_ID}.",
                sha="body75",
                head="docs/notes",
            ),
        ],
    )

    assert exit_code == 0
    assert _stored().audit is not None
    assert (_stored().audit.pr_number, _stored().audit.merge_sha) == (74, "title74")


def test_a_single_body_mention_resolves_without_a_stronger_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exit_code, _ = _reconcile(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        candidates=[
            _listed(
                number=76,
                title="docs: notes",
                body=f"Implements {_ITEM_ID}.",
                sha="body76",
                head="docs/notes",
            )
        ],
    )

    assert exit_code == 0
    assert _stored().audit is not None
    assert (_stored().audit.pr_number, _stored().audit.merge_sha) == (76, "body76")


def test_a_tie_in_the_highest_tier_refuses_without_changing_the_item(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_code, _ = _reconcile(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        candidates=[
            _listed(
                number=77,
                title="feat: carrier one",
                body="",
                sha="head77",
                head=f"feat/{_ITEM_ID}",
            ),
            _listed(
                number=78,
                title="feat: carrier two",
                body="",
                sha="head78",
                head=f"feat/{_ITEM_ID}",
            ),
            _listed(
                number=79,
                title=f"follow-up for {_ITEM_ID}",
                body="",
                sha="title79",
                head="feat/follow-up",
            ),
            _listed(
                number=80,
                title="docs: notes",
                body=f"Follows {_ITEM_ID}.",
                sha="body80",
                head="docs/notes",
            ),
        ],
    )

    assert exit_code == 3
    error = capsys.readouterr().err
    assert "ambiguous merged PR candidates" in error
    assert "#77 head77" in error
    assert "#78 head78" in error
    assert "#79 title79" not in error
    assert "#80 body80" not in error
    assert _stored().status == "active"

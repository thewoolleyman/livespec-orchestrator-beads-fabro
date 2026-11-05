"""Scenario 244 — reconcile-merged ranks how a merged PR names an item.

The valve runs through the real dispatcher command and fake ledger.  Only the
GitHub command runner and the acceptance pass are seams: that leaves the
resolution, refusal, journal, and status effects under test together.
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


def _reconcile_selected(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selected: dict[str, object],
) -> tuple[int, Path]:
    """Run the selector route, whose direct PR read bypasses ranking."""
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())
    runner = _Runner(
        queue=[
            _ok(stdout="origin/master"),
            _ok(stdout=json.dumps(selected)),
            *_janitor_green(),
        ]
    )
    monkeypatch.setattr(_RUNNER_SEAM, lambda: runner)
    monkeypatch.setattr(
        _dispatcher_completion, "run_acceptance_pass", lambda **_: _AcceptancePass()
    )
    exit_code = main(
        argv=[
            "reconcile-merged",
            "--repo",
            str(repo),
            "--item",
            _ITEM_ID,
            "--pr",
            str(selected["number"]),
        ]
    )
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


def test_an_explicit_selector_chooses_one_title_match_without_ranking_its_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exit_code, repo = _reconcile_selected(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        selected=_listed(
            number=81,
            title=f"fix: {_ITEM_ID}",
            body="",
            sha="selected81",
            head="fix/hand-landed",
        ),
    )

    assert exit_code == 0
    assert _stored().audit is not None
    assert (_stored().audit.pr_number, _stored().audit.merge_sha) == (81, "selected81")
    records = [
        json.loads(line)
        for line in (repo / "tmp" / "fabro-dispatch-journal.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert {
        "stage": "reconcile-pr-selected",
        "work_item_id": _ITEM_ID,
        "pr_number": 81,
        "merge_sha": "selected81",
    }.items() <= records[2].items()


@pytest.mark.parametrize(
    "selected",
    [
        _listed(
            number=82,
            title=f"fix: {_ITEM_ID}",
            body="",
            sha="open82",
            head="fix/hand-landed",
        )
        | {"state": "OPEN"},
        _listed(
            number=83,
            title="fix: unrelated",
            body=f"mentions {_ITEM_ID}",
            sha="unrelated83",
            head="fix/unrelated",
        ),
    ],
)
def test_a_selector_rejects_an_unmerged_or_nonidentifying_pr(
    selected: dict[str, object],
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())
    runner = _Runner(queue=[_ok(stdout="origin/master"), _ok(stdout=json.dumps(selected))])
    monkeypatch.setattr(_RUNNER_SEAM, lambda: runner)

    exit_code = main(
        argv=[
            "reconcile-merged",
            "--repo",
            str(repo),
            "--item",
            _ITEM_ID,
            "--pr",
            str(selected["number"]),
        ]
    )

    assert exit_code == 3
    assert f"PR #{selected['number']}" in capsys.readouterr().err
    assert _stored().status == "active"


def test_a_selector_refuses_when_its_merged_pr_differs_from_green_janitor_evidence(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An acceptance re-run cannot switch away from the PR its janitor proved."""
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=replace(_item(), status="acceptance"))
    journal = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir()
    _ = journal.write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "stage": "reconcile-pr-selected",
                        "work_item_id": _ITEM_ID,
                        "pr_number": 81,
                        "merge_sha": "janitor81",
                    }
                ),
                json.dumps(
                    {
                        "stage": "janitor-post-merge",
                        "work_item_id": _ITEM_ID,
                        "pr_number": 81,
                        "merge_sha": "janitor81",
                        "exit_code": 0,
                    }
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    runner = _Runner(
        queue=[
            _ok(stdout="origin/master"),
            _ok(
                stdout=json.dumps(
                    _listed(
                        number=82,
                        title=f"fix: {_ITEM_ID}",
                        body="",
                        sha="selected82",
                        head="fix/another-merge",
                    )
                )
            ),
        ]
    )
    acceptance_calls: list[object] = []
    monkeypatch.setattr(_RUNNER_SEAM, lambda: runner)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **kwargs: acceptance_calls.append(kwargs) or _AcceptancePass(),
    )

    exit_code = main(
        argv=[
            "reconcile-merged",
            "--repo",
            str(repo),
            "--item",
            _ITEM_ID,
            "--pr",
            "82",
        ]
    )

    assert exit_code == 3
    error = capsys.readouterr().err
    assert "janitor" in error
    assert "#81" in error
    assert "#82" in error
    assert acceptance_calls == []
    assert _stored().status == "acceptance"

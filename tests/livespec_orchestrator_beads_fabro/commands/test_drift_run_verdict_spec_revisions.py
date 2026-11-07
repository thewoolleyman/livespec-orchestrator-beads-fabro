"""The drift pass keys its durable verdicts by the ratified spec tree."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._drift_run import DriftRunSeams, run_drift_pass
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ANCHOR = "bd-ib-anchor"
_MERGES = ("aaaaaaa1", "bbbbbbb2")
_TARGET = "## Governing heading"


@dataclass(kw_only=True)
class _GitRunner:
    """A branch whose changed merges and subjects are fixed for this test."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        if argv[1] == "symbolic-ref":
            return CommandResult(exit_code=0, stdout="origin/master\n", stderr="")
        if argv[1] == "rev-list":
            return CommandResult(exit_code=0, stdout="\n".join(_MERGES) + "\n", stderr="")
        return CommandResult(exit_code=0, stdout=f"subject for {argv[-1]}\n", stderr="")


@dataclass(kw_only=True)
class _Judge:
    """An unstated verdict whose prompt count is the model-spend evidence."""

    prompts: list[str] = field(default_factory=list)

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return (
            '{"kind": "unstated", "stated_by": [], '
            f'"generalization_target": "{_TARGET}", "rationale": "r"}}'
        )


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> None:
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="t", prefix="bd-ib", server_user="u", database="d", bd_path="bd", fake=True
    )


def _seed_anchor() -> None:
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=_ANCHOR,
            type="task",
            status="backlog",
            title="anchor",
            description="d",
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee=None,
            depends_on=(),
            captured_at="2026-08-01T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            blocked_reason=None,
            factory_safety=None,
            admission_policy=None,
            acceptance_policy=None,
            spec_commitment_hint=None,
        ),
    )


def _project(*, root: Path, cap: int) -> None:
    spec = root / "SPECIFICATION"
    (spec / "proposed_changes").mkdir(parents=True)
    (spec / "history" / "v001" / "proposed_changes").mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(f"{_TARGET}\n\ntext\n", encoding="utf-8")
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "t",
                        "prefix": "bd-ib",
                        "server_user": "u",
                        "database": "d",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "detection_coverage_anchor": _ANCHOR,
                        "drift_proposal_queue_cap": cap,
                    },
                }
            }
        ),
        encoding="utf-8",
    )


def _run(*, root: Path, judge: _Judge) -> None:
    _ = run_drift_pass(
        project_root=root,
        frontier="deadbeef",
        seams=DriftRunSeams(runner=_GitRunner(), judge=judge, now=lambda: "2026-10-25T00:00:00Z"),
    )


def test_newer_ratified_spec_revision_requires_new_verdicts(tmp_path: Path) -> None:
    _project(root=tmp_path, cap=5)
    _seed_anchor()
    judge = _Judge()

    _run(root=tmp_path, judge=judge)
    _run(root=tmp_path, judge=judge)
    _ = (tmp_path / "SPECIFICATION" / "contracts.md").write_text(
        f"{_TARGET}\n\nratified revision two\n", encoding="utf-8"
    )
    _run(root=tmp_path, judge=judge)

    assert len(judge.prompts) == len(_MERGES) * 2


def test_held_findings_do_not_rejudge_merges_behind_the_frontier(tmp_path: Path) -> None:
    _project(root=tmp_path, cap=1)
    _seed_anchor()
    judge = _Judge()

    _run(root=tmp_path, judge=judge)
    _run(root=tmp_path, judge=judge)

    assert len(judge.prompts) == len(_MERGES)

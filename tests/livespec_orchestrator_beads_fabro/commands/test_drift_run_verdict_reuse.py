"""The drift run reuses only verdicts taken against the current spec tree."""

from __future__ import annotations

import importlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._detection_coverage import (
    DRIFT_CAPTURE_OPERATION,
    DetectionRun,
    record_detection_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._drift_run import DriftRunSeams
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

if TYPE_CHECKING:
    from collections.abc import Iterator


_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_ANCHOR = "bd-ib-anchor"
_MERGES = ("aaaaaaa1", "bbbbbbb2", "ccccccc3")


@dataclass(kw_only=True)
class _GitRunner:
    """A three-merge branch whose diffs can be judged without git."""

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
    """An unstated verdict whose call count proves whether a model was spent."""

    prompts: list[str] = field(default_factory=list)

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return (
            '{"kind": "unstated", "stated_by": [], "generalization_target": null, "rationale": "r"}'
        )


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> Iterator[None]:
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
    _ = record_detection_run(
        path=_config(),
        anchor=_ANCHOR,
        run=DetectionRun(
            operation=DRIFT_CAPTURE_OPERATION,
            scope="baseline",
            invoker="human:maintainer",
            outcome="succeeded",
            exit_code=0,
            coverage_point="deadbeef",
        ),
    )


def _project(*, root: Path) -> None:
    spec = root / "SPECIFICATION"
    (spec / "proposed_changes").mkdir(parents=True)
    (spec / "history" / "v001" / "proposed_changes").mkdir(parents=True)
    _ = (spec / "contracts.md").write_text("## A heading\n\ntext\n", encoding="utf-8")
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
                        "drift_proposal_queue_cap": 1,
                    },
                }
            }
        ),
        encoding="utf-8",
    )


def _run(*, root: Path, judge: _Judge) -> None:
    lane = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_drift_lane"
    )
    _ = lane.run_drift_lane(
        repo=root,
        invoker="drift-job:test",
        seams=DriftRunSeams(runner=_GitRunner(), judge=judge, now=lambda: "2026-10-25T00:00:00Z"),
    )


def test_a_repeated_unchanged_run_reuses_each_recorded_verdict(tmp_path: Path) -> None:
    assert (_COMMANDS / "_drift_run_verdicts.py").is_file()
    _project(root=tmp_path)
    _seed_anchor()
    judge = _Judge()

    _run(root=tmp_path, judge=judge)
    _run(root=tmp_path, judge=judge)

    assert len(judge.prompts) == len(_MERGES)

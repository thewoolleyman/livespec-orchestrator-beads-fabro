"""Integration-tier acceptance for Scenario 207 and Scenario 82's drift case.

Drives the per-merge drift run end to end rather than against hand-built
fixtures: the lane resolves the frontier off the real detection-coverage anchor
through the store/client seam against the in-memory `FakeBeadsClient`, files
real proposal documents into a real spec tree, and the staleness fact is then
read off the actual `needs-attention` composition.

That pairing is the point, and it is assertion 5 of `bd-ib-yvjxo4`: "After a
pass that advances the frontier, the drift-staleness fact reports the merges
after the frontier only, and the pass never accepts a proposal." Neither half
is observable from the lane alone — the first needs the fact composed AFTER the
record landed, and the second is a claim about what the pass did NOT do to the
spec tree and the ledger.

WHAT "NEVER ACCEPTS" IS ASSERTED AS. Acceptance of a proposal is a revise act
with three artifacts: a `history/vNNN/` snapshot, a `<topic>-revision.md`
carrying a `decision:`, and the proposal leaving the open queue. The pass is
asserted to have produced NONE of them while having filed a proposal that IS in
the open queue — so "took no decision" is read off the artifacts a decision
would have left, not off the absence of a word.

AND WHAT IT WROTE TO THE LEDGER. The self-bookkeeping exception admits the
drift run's records on the designated anchor "and nothing else", so a bystander
work-item is asserted to carry no comment and the issue set to be unchanged.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._detection_coverage import (
    COMPLETED_MARKER_PREFIX,
    DRIFT_CAPTURE_OPERATION,
    DetectionRun,
    record_detection_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_drift_lane import (
    run_drift_lane,
)
from livespec_orchestrator_beads_fabro.commands._drift_run import DriftRunSeams
from livespec_orchestrator_beads_fabro.commands._needs_attention_detection_staleness import (
    DetectionStalenessSeams,
    detection_staleness_items,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

if TYPE_CHECKING:
    from collections.abc import Iterator

_ANCHOR = "bd-ib-anchor"
_BYSTANDER = "bd-ib-bystander"
_TARGET = "## A governing heading"
_BASELINE = "0000000baseline"
_OLDER = "aaaaaaa1"
_NEWER = "bbbbbbb2"
_DRIFT_FACT_ID = "hygiene:drift-staleness:repo"


@dataclass(kw_only=True)
class _GitRunner:
    """A `CommandRunner` recording the ranges it was asked about.

    `rev-list --count` answers the number of merges the range actually spans,
    derived from this fixture's own history, so the fact's figure is a reading
    of the range it asked for rather than a constant that would agree with any
    range at all.
    """

    history: tuple[str, ...] = (_BASELINE, _OLDER, _NEWER)
    argvs: list[list[str]] = field(default_factory=list)

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
        self.argvs.append(argv)
        if argv[1] == "symbolic-ref":
            return CommandResult(exit_code=0, stdout="origin/master\n", stderr="")
        if argv[1] == "rev-list":
            return CommandResult(exit_code=0, stdout=self._range(argv=argv), stderr="")
        return CommandResult(exit_code=0, stdout=f"a subject\n+ hunk {argv[-1]}\n", stderr="")

    def _range(self, *, argv: list[str]) -> str:
        since = argv[-1].split("..")[0] if ".." in argv[-1] else None
        after = (
            list(self.history)[self.history.index(since) + 1 :]
            if since in self.history
            else list(self.history)
        )
        return str(len(after)) + "\n" if "--count" in argv else "\n".join(after) + "\n"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> Iterator[None]:
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="t", prefix="bd-ib", server_user="u", database="d", bd_path="bd", fake=True
    )


def _seed(*, id_: str) -> None:
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=id_,
            type="task",
            status="backlog",
            title=id_,
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


def _unstated(prompt: str) -> str:
    _ = prompt
    return (
        f'{{"kind": "unstated", "stated_by": [], '
        f'"generalization_target": "{_TARGET}", "rationale": "r"}}'
    )


def _project(*, root: Path) -> Path:
    spec_root = root / "SPECIFICATION"
    (spec_root / "proposed_changes").mkdir(parents=True)
    (spec_root / "history" / "v001" / "proposed_changes").mkdir(parents=True)
    _ = (spec_root / "contracts.md").write_text(f"{_TARGET}\n\ntext\n", encoding="utf-8")
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
                        "drift_capture_merge_threshold": 1,
                    },
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return spec_root


def _advance_a_pass(*, root: Path, runner: _GitRunner) -> object:
    _ = record_detection_run(
        path=_config(),
        anchor=_ANCHOR,
        run=DetectionRun(
            operation=DRIFT_CAPTURE_OPERATION,
            scope=_BASELINE,
            invoker="human:maintainer",
            outcome="succeeded",
            exit_code=0,
            coverage_point=_BASELINE,
        ),
    )
    return run_drift_lane(
        repo=root,
        invoker="reconcile-pass:test",
        seams=DriftRunSeams(runner=runner, judge=_unstated, now=lambda: "2026-10-22T00:00:00Z"),
    )


def _drift_fact(*, root: Path, runner: _GitRunner) -> str:
    composed = {
        item.id: item.summary + "\n" + item.handoff.command
        for item in detection_staleness_items(
            project_root=root,
            repo="repo",
            config=_config(),
            seams=DetectionStalenessSeams(runner=runner),
        )
    }
    return composed.get(_DRIFT_FACT_ID, "")


def test_the_drift_fact_reports_the_merges_after_the_advanced_frontier_only(
    tmp_path: Path,
) -> None:
    _ = _project(root=tmp_path)
    _seed(id_=_ANCHOR)
    lane_runner = _GitRunner()
    outcome = _advance_a_pass(root=tmp_path, runner=lane_runner)

    fact_runner = _GitRunner()
    rendered = _drift_fact(root=tmp_path, runner=fact_runner)

    assert outcome.advanced is True  # pyright: ignore[reportAttributeAccessIssue]
    # The fact asked about the range AFTER the newly recorded frontier, and
    # therefore reports no merge at all: both merges of that pass are now
    # accounted for. A fact still counting from the baseline would report two.
    counted = next(argv for argv in fact_runner.argvs if argv[1] == "rev-list")
    assert counted[-1] == f"{_NEWER}..origin/master"
    assert rendered == ""


def test_merges_after_the_frontier_still_surface_the_fact_naming_them(tmp_path: Path) -> None:
    _ = _project(root=tmp_path)
    _seed(id_=_ANCHOR)
    _ = _advance_a_pass(root=tmp_path, runner=_GitRunner())

    # A third merge lands after the frontier: the fact fires again, naming the
    # merges after THAT frontier rather than every merge on the branch, and it
    # invokes no detector — the reconcile pass is what runs the drift pass.
    rendered = _drift_fact(
        root=tmp_path, runner=_GitRunner(history=(_BASELINE, _OLDER, _NEWER, "ccccccc3"))
    )

    assert "1 default-branch merge(s)" in rendered
    assert _NEWER in rendered
    assert "the reconcile pass" in rendered


def test_the_pass_files_a_proposal_it_never_accepts(tmp_path: Path) -> None:
    spec_root = _project(root=tmp_path)
    _seed(id_=_ANCHOR)

    _ = _advance_a_pass(root=tmp_path, runner=_GitRunner())

    open_queue = sorted((spec_root / "proposed_changes").glob("*.md"))
    assert len(open_queue) == 2
    # No revision record, no new history snapshot, and the proposals are still
    # in the open queue: every artifact a decision would have left is absent.
    assert sorted(path.name for path in (spec_root / "history").iterdir()) == ["v001"]
    assert list((spec_root / "history" / "v001" / "proposed_changes").glob("*.md")) == []
    for path in open_queue:
        assert "decision:" not in path.read_text(encoding="utf-8")


def test_the_pass_writes_nothing_to_the_ledger_but_the_anchor(tmp_path: Path) -> None:
    _ = _project(root=tmp_path)
    _seed(id_=_ANCHOR)
    _seed(id_=_BYSTANDER)
    client = make_beads_client(config=_config())
    before = json.dumps(client.list_issues(), sort_keys=True)

    _ = _advance_a_pass(root=tmp_path, runner=_GitRunner())

    assert json.dumps(client.list_issues(), sort_keys=True) == before
    assert client.list_comments(issue_id=_BYSTANDER) == []
    anchor_bodies = [str(comment["text"]) for comment in client.list_comments(issue_id=_ANCHOR)]
    assert len([body for body in anchor_bodies if body.startswith(COMPLETED_MARKER_PREFIX)]) == 2

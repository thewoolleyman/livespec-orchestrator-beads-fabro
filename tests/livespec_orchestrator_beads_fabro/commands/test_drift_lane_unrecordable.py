"""The drift lane's four arms that record nothing, and what each one reports.

Every case here is a repository state in which the lane CANNOT move the
frontier, and the four are not interchangeable — they have four remedies, and a
lane that collapsed them would send an operator to fix the wrong thing.

NO TENANT CONNECTION: the lane cannot read the recorded frontier at all, so it
does not run the pass. Judging merges against an unknown frontier would mean
judging the whole branch on every tick and filing proposals for behaviour the
specification has already absorbed.

NO COMMITTED ANCHOR: the frontier reads as "none on record", so the pass runs
over every merge — correctly — but the record has nowhere to go. The lane
reports the RECORDER's own refusal detail rather than wording of its own, so an
operator comparing this report against the journal sees one condition rather
than two descriptions of it.

NO RECORDED BASELINE FRONTIER: the anchor exists and carries no completed drift
coverage point, so there is no range "after a frontier" at all. The lane judges
nothing rather than reading that as the whole branch, which on this repository
is thousands of commits at one model call each — and rather than capping the
enumeration, which would record a frontier covering merges nobody judged. The
baseline is separately owned work; see the lane module's own docstring.

AN UNENUMERABLE RANGE: git did not answer, so the attempt record names that
measurement instead of a merge. The scope detail is the only place an operator
can see which instrument stopped the pass, and an attempt record carrying the
bare range would read as a pass that found nothing to do.
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
    ATTEMPT_MARKER_PREFIX,
    DRIFT_CAPTURE_OPERATION,
    DetectionRun,
    record_detection_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_drift_lane import (
    run_drift_lane,
)
from livespec_orchestrator_beads_fabro.commands._drift_run import (
    CAUSE_MERGES_UNREADABLE,
    DriftRunSeams,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

if TYPE_CHECKING:
    from collections.abc import Iterator

_ANCHOR = "bd-ib-anchor"
_TARGET = "## A governing heading"


@dataclass(kw_only=True)
class _GitRunner:
    """A `CommandRunner` whose enumeration can be made to fail outright."""

    enumerable: bool = True
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
            if not self.enumerable:
                return CommandResult(exit_code=128, stdout="", stderr="bad revision")
            return CommandResult(exit_code=0, stdout="aaaaaaa1\n", stderr="")
        return CommandResult(exit_code=0, stdout="a subject\n+ hunk\n", stderr="")


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> Iterator[None]:
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="t", prefix="bd-ib", server_user="u", database="d", bd_path="bd", fake=True
    )


def _stated(prompt: str) -> str:
    _ = prompt
    return '{"kind": "stated", "stated_by": [], "generalization_target": null, "rationale": "r"}'


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


def _record_baseline() -> None:
    """The completed coverage point every judging pass needs to have a range."""
    _ = record_detection_run(
        path=_config(),
        anchor=_ANCHOR,
        run=DetectionRun(
            operation=DRIFT_CAPTURE_OPERATION,
            scope="deadbeef",
            invoker="human:maintainer",
            outcome="succeeded",
            exit_code=0,
            coverage_point="deadbeef",
        ),
    )


def _project(*, root: Path, anchor: str | None) -> None:
    spec_root = root / "SPECIFICATION"
    (spec_root / "proposed_changes").mkdir(parents=True)
    (spec_root / "history" / "v001" / "proposed_changes").mkdir(parents=True)
    _ = (spec_root / "contracts.md").write_text(f"{_TARGET}\n\ntext\n", encoding="utf-8")
    dispatcher: dict[str, object] = {}
    if anchor is not None:
        dispatcher["detection_coverage_anchor"] = anchor
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
                    "dispatcher": dispatcher,
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_no_tenant_connection_runs_no_pass_and_advances_nothing(tmp_path: Path) -> None:
    # No `.livespec.jsonc` at all: the connection block does not resolve.
    runner = _GitRunner()

    outcome = run_drift_lane(
        repo=tmp_path,
        invoker="reconcile-pass:test",
        seams=DriftRunSeams(runner=runner, judge=_stated, now=lambda: "2026-10-22T00:00:00Z"),
    )

    assert outcome.advanced is False
    assert outcome.withheld_reason == "no-tenant-connection"
    assert outcome.merges == ()
    # And no git read was spent: there is no frontier to judge merges against.
    assert runner.argvs == []


def test_no_committed_anchor_reports_the_recorders_own_refusal(tmp_path: Path) -> None:
    _project(root=tmp_path, anchor=None)

    outcome = run_drift_lane(
        repo=tmp_path,
        invoker="reconcile-pass:test",
        seams=DriftRunSeams(runner=_GitRunner(), judge=_stated, now=lambda: "2026-10-22T00:00:00Z"),
    )

    assert outcome.advanced is False
    assert outcome.records is None
    assert outcome.withheld_reason is not None
    assert "detection_coverage_anchor" in outcome.withheld_reason


def test_no_recorded_baseline_frontier_judges_nothing(tmp_path: Path) -> None:
    _project(root=tmp_path, anchor=_ANCHOR)
    _seed_anchor()
    runner = _GitRunner()

    outcome = run_drift_lane(
        repo=tmp_path,
        invoker="reconcile-pass:test",
        seams=DriftRunSeams(runner=runner, judge=_stated, now=lambda: "2026-10-22T00:00:00Z"),
    )

    assert outcome.advanced is False
    assert outcome.withheld_reason == "no-recorded-drift-frontier"
    # Not one git read, and so not one model call: the whole branch is not the
    # range, and judging it would cost one judgement per commit in history.
    assert runner.argvs == []
    assert outcome.records is not None
    assert "baseline frontier" in outcome.records.attempt


def test_an_unenumerable_range_names_that_measurement_in_the_attempt_record(
    tmp_path: Path,
) -> None:
    _project(root=tmp_path, anchor=_ANCHOR)
    _seed_anchor()
    _record_baseline()

    outcome = run_drift_lane(
        repo=tmp_path,
        invoker="reconcile-pass:test",
        seams=DriftRunSeams(
            runner=_GitRunner(enumerable=False),
            judge=_stated,
            now=lambda: "2026-10-22T00:00:00Z",
        ),
    )

    attempts = [
        str(comment["text"])
        for comment in make_beads_client(config=_config()).list_comments(issue_id=_ANCHOR)
        if str(comment["text"]).startswith(ATTEMPT_MARKER_PREFIX)
    ]
    assert outcome.advanced is False
    # Two attempt records: the baseline's own completed pass, then this one.
    assert len(attempts) == 2
    assert CAUSE_MERGES_UNREADABLE in attempts[-1]


def test_a_scope_with_no_findings_at_all_advances_to_its_newest_merge(tmp_path: Path) -> None:
    _project(root=tmp_path, anchor=_ANCHOR)
    _seed_anchor()
    _record_baseline()

    outcome = run_drift_lane(
        repo=tmp_path,
        invoker="reconcile-pass:test",
        seams=DriftRunSeams(runner=_GitRunner(), judge=_stated, now=lambda: "2026-10-22T00:00:00Z"),
    )

    # The positive control for the three refusals above: a merge the ratified
    # text already states carries no finding, so the scope closes with nothing
    # filed and the frontier moves. Without this case a lane that never
    # advanced would satisfy every other assertion in this module.
    assert outcome.advanced is True
    assert outcome.frontier == "aaaaaaa1"
    assert outcome.withheld_reason is None

"""An inert drift lane records its state ONCE, not once per reconcile tick.

The lane's no-baseline arm judges nothing — there is no range "after a
frontier" to enumerate — and until this module it nonetheless appended a
`failed` attempt record on every pass. The root `reconcile-runs` timer fires
every ten minutes, so that is roughly 144 identical records a day on a tenant
that already carries heavy comment volume, and `bd comments` offers no edit and
no delete: every one of them is permanent.

THE INERT STATE IS NOT A FAILED ATTEMPT, which is why de-duplicating it is a
correctness fix and not a volume one. Nothing was attempted: the lane refused
before running a single pass, so each of those records described a failure that
never happened, and an operator reading the anchor saw a lane failing every ten
minutes rather than a repository awaiting its baseline.

ONE RECORD IS STILL WRITTEN, and the first pass is the one that writes it. A
lane that recorded NOTHING would leave the state nowhere on the anchor at all,
and the anchor is where the detection contract puts a run's bookkeeping; the
record also names the missing baseline and its owner, which is the only durable
place that remedy is written down.

AND THE DE-DUPLICATION IS SCOPED TO THAT ARM. The third test here is the
positive control, and without it a lane that stopped recording altogether would
satisfy every other assertion in this module: once a baseline is on record each
pass IS a drift run over a real range, so each one owes its own attempt record
exactly as the contract's Records rule says.

THE COUNT IS SCOPED TO THE DRIFT OPERATION, which is why the first test seeds a
GAP-CAPTURE record on the same anchor. One anchor carries every detection
operation's bookkeeping, so a reading that counted every record on it would
report a repository whose gap captures are running as one whose drift lane is
accruing records — and a de-duplication graded on that reading would be graded
on the wrong population.
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
    COMPLETED_MARKER_PREFIX,
    DRIFT_CAPTURE_OPERATION,
    GAP_CAPTURE_OPERATION,
    DetectionRun,
    record_detection_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_drift_lane import (
    run_drift_lane,
)
from livespec_orchestrator_beads_fabro.commands._drift_run import DriftRunSeams
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

if TYPE_CHECKING:
    from collections.abc import Iterator

_ANCHOR = "bd-ib-anchor"
_TARGET = "## A governing heading"
_MARKERS = (ATTEMPT_MARKER_PREFIX, COMPLETED_MARKER_PREFIX)


@dataclass(kw_only=True)
class _GitRunner:
    """A `CommandRunner` answering one merge, so a baselined pass has a range."""

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


def _seams(*, runner: _GitRunner) -> DriftRunSeams:
    return DriftRunSeams(runner=runner, judge=_stated, now=lambda: "2026-10-22T00:00:00Z")


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


def _record_gap_capture() -> None:
    """A record of the OTHER detection operation, on the same anchor.

    One anchor carries both operations' bookkeeping, so this is what a count
    scoped to the drift operation has to leave out.
    """
    _ = record_detection_run(
        path=_config(),
        anchor=_ANCHOR,
        run=DetectionRun(
            operation=GAP_CAPTURE_OPERATION,
            scope="v001",
            invoker="human:maintainer",
            outcome="succeeded",
            exit_code=0,
            coverage_point="v001",
        ),
    )


def _project(*, root: Path) -> None:
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
                    "dispatcher": {"detection_coverage_anchor": _ANCHOR},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _drift_records(*, marker: str | None = None) -> list[dict[str, object]]:
    """The anchor's drift-capture records, oldest first, optionally of one kind.

    Filtered on the recorded OPERATION rather than counted by marker alone: one
    anchor carries every detection operation's bookkeeping, so a count that
    trusted this fixture to write drift records exclusively would read a
    gap-capture record as one of this lane's.
    """
    found: list[dict[str, object]] = []
    for comment in make_beads_client(config=_config()).list_comments(issue_id=_ANCHOR):
        text = str(comment["text"])
        for one in _MARKERS if marker is None else (marker,):
            if not text.startswith(one):
                continue
            fields: dict[str, object] = json.loads(text.removeprefix(one))
            if fields.get("operation") == DRIFT_CAPTURE_OPERATION:
                found.append(fields)
    return found


def test_consecutive_inert_passes_leave_the_drift_record_count_unchanged(tmp_path: Path) -> None:
    _project(root=tmp_path)
    _seed_anchor()
    _record_gap_capture()

    counts: list[int] = []
    for _tick in range(3):
        _ = run_drift_lane(
            repo=tmp_path, invoker="reconcile-pass:test", seams=_seams(runner=_GitRunner())
        )
        counts.append(len(_drift_records()))

    # The first pass writes the one record that names the missing baseline;
    # every tick after it adds nothing, so the anchor stops accruing a `failed`
    # attempt for a pass that was never attempted. The seeded gap-capture
    # records are on the same anchor and in none of these counts.
    assert counts == [1, 1, 1]


def test_every_inert_pass_still_reports_the_missing_baseline(tmp_path: Path) -> None:
    _project(root=tmp_path)
    _seed_anchor()

    reasons = [
        run_drift_lane(
            repo=tmp_path, invoker="reconcile-pass:test", seams=_seams(runner=_GitRunner())
        ).withheld_reason
        for _tick in range(3)
    ]

    # De-duplicating the record must not silence the state: the lane's report is
    # what the reconcile pass renders, and a tick that said nothing would read
    # as a lane that had advanced.
    assert reasons == ["no-recorded-drift-frontier"] * 3


def test_a_baselined_pass_still_appends_its_own_attempt_record_each_tick(tmp_path: Path) -> None:
    _project(root=tmp_path)
    _seed_anchor()
    _record_baseline()
    before = len(_drift_records(marker=ATTEMPT_MARKER_PREFIX))

    counts: list[int] = []
    for _tick in range(2):
        _ = run_drift_lane(
            repo=tmp_path, invoker="reconcile-pass:test", seams=_seams(runner=_GitRunner())
        )
        counts.append(len(_drift_records(marker=ATTEMPT_MARKER_PREFIX)) - before)

    # The positive control for the two assertions above: with a baseline on
    # record each pass IS a drift run over a real range, so each one owes its
    # own attempt record and the de-duplication must not reach it.
    assert counts == [1, 2]

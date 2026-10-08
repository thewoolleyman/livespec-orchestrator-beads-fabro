"""The branch-versus-base diff size, recorded when a run's pull request opens.

Plan slice S4 (`bd-ib-tbgxm4`). `merged_pr_diff_size` is read only for a GREEN
outcome carrying a pull-request number, so it is present by construction on
exactly the runs whose outcome is already known to be good. Measured across
445 of this repository's calibration records (plan research,
`plan/factory-test-first-enforcement/research/opening-research-2026-09-30.md`):
present on all 292 converged runs and on ZERO of the 153 non-converged ones,
which makes it unusable as a predictor — the thing it would predict is the
thing that decides whether it exists.

The repair records the size at the moment the Dispatcher first CONFIRMS the
pull request, which is before it decides anything about merging. The value is
then on the journal whatever terminal the run later reaches, so a run that
fails after its pull request opened carries the same measurement a merged one
does.

Two properties are asserted deliberately. The size is read off the pull-request
view the Dispatcher ALREADY takes, so no second forge round trip is spent and
no probe can disagree with the view the engine routed on. And an unreported
size records as an explicit null rather than a zero — a zero-churn pull request
and one whose size the forge did not report support opposite readings.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    build_plan,
    parse_pr_view,
    pr_view_argv,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_pr_open_diff"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_pr_open_diff.py"
)
_CALIBRATION_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_calibration"
_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'
_WORK_ITEM_ID = "x-1"
# The stage the engine journals the measurement under, and the key it carries.
_STAGE = "pr-open-diff-size"
_SIZE_KEY = "pr_open_diff_size"

# The committed connection block the host's CURRENT-merge-hold read resolves
# (`_dispatcher_current_merge_hold`). Any fixture that drives `run_dispatch` PAST the
# pull-request confirmation needs it: without it `resolve_store_config` raises on the
# absent `connection.prefix`, the hold reads `unreadable`, and the boundary fails
# CLOSED at `merge-hold-authority` rather than reaching the merge poll. The item id
# is deliberately NOT appended — an id absent from the held set reads `unheld`, which
# is the ordinary path these size tests are about.
_TENANT_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {
      "tenant": "livespec-impl-beads",
      "prefix": "bd",
      "server_user": "livespec-impl-beads",
      "database": "livespec-impl-beads",
      "bd_path": "bd",
      "fake": true
    }
  }
}
"""


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _calibration() -> ModuleType:
    """The calibration derivation module, reached by name.

    By NAME rather than by import, for the same reason `_module` is: the
    derivation under test is added in the same change as the module above, and a
    top-level import of a name that does not exist yet makes the Red a
    collection error rather than a failed assertion.
    """
    return importlib.import_module(_CALIBRATION_MODULE_NAME)


@dataclass(kw_only=True)
class _FakeRunner:
    """Scripted CommandRunner: consumes queued results, logs invocations."""

    queue: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        assert timeout_seconds > 0
        assert isinstance(cwd, Path)
        _ = (env, stdin)
        self.calls.append(argv)
        return self.queue.pop(0)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_WORK_ITEM_ID,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text=_DECLARED_CONFIG,
        default_branch="master",
    )


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-tbgxm4",
        type="feature",
        status="active",
        title="Repair factory sizing telemetry",
        description="## Definition of Done\n\n- The size rides the journal.\n",
        origin="freeform",
        gap_id=None,
        rank="a3",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _pr_json(
    *,
    state: str = "OPEN",
    sha: str | None = None,
    additions: int | None = 120,
    deletions: int | None = 25,
) -> str:
    payload: dict[str, object] = {
        "number": 7,
        "state": state,
        "autoMergeRequest": {"enabledAt": "now"},
        "mergeStateStatus": "CLEAN",
        "mergeCommit": {"oid": sha} if sha is not None else None,
        "statusCheckRollup": [],
    }
    if additions is not None:
        payload["additions"] = additions
    if deletions is not None:
        payload["deletions"] = deletions
    return json.dumps(payload)


def _pr_association() -> CommandResult:
    return _ok(stdout=json.dumps([{"number": 7}]))


def _venue_resolution() -> list[CommandResult]:
    return [_ok(stdout="master"), _ok(stdout="master")]


def _readable_unheld_tenant(*, repo: Path) -> None:
    """Give the host's hold read a connection block to resolve, naming no held item."""
    _ = (repo / ".livespec.jsonc").write_text(_TENANT_CONFIG, encoding="utf-8")


def _dispatch(
    *, runner: _FakeRunner, repo: Path, attempts: int = 3
) -> tuple[DispatchOutcome, _RecordingJournal]:
    journal = _RecordingJournal()
    outcome = run_dispatch(
        plan=_plan(repo=repo),
        runner=runner,
        journal=journal,
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=attempts, interval_seconds=0.5),
    )
    return outcome, journal


def _stages(*, journal: _RecordingJournal) -> list[object]:
    return [record.get("stage") for record in journal.records]


def _diff_records(*, journal: _RecordingJournal) -> list[dict[str, object]]:
    return [record for record in journal.records if record.get("stage") == _STAGE]


# --- the measurement rides the view the engine already takes ---------------


def test_the_pull_request_view_asks_the_forge_for_the_branch_versus_base_size() -> None:
    """One view answers routing AND sizing; a second probe could disagree."""
    _ = _module()

    argv = pr_view_argv(plan=_plan(repo=Path("/repo")))

    assert "additions,deletions" in argv[-1]


def test_the_parsed_view_carries_the_branch_versus_base_churn() -> None:
    """Additions plus deletions is the churn the forge computes against base."""
    _ = _module()

    view = parse_pr_view(stdout=_pr_json(additions=120, deletions=25))

    assert view is not None
    # Through `asdict` rather than the attribute: the field is added in this
    # same change, and an attribute read would make the Red a type error.
    assert asdict(view)["diff_size"] == 145


def test_an_unreported_size_parses_as_absent_rather_than_zero() -> None:
    """A forge payload missing either field is unobservable, never zero churn."""
    _ = _module()

    partial = parse_pr_view(stdout=_pr_json(additions=120, deletions=None))
    absent = parse_pr_view(stdout=_pr_json(additions=None, deletions=None))

    assert partial is not None
    assert absent is not None
    assert asdict(partial)["diff_size"] is None
    assert asdict(absent)["diff_size"] is None


def test_the_journal_record_names_the_stage_the_item_and_the_pull_request() -> None:
    """The record is self-describing: which item, which pull request, what size."""
    module = _module()

    record = module.pr_open_diff_record(work_item_id="bd-ib-tbgxm4", pr_number=7, diff_size=145)

    assert record["stage"] == _STAGE
    assert record["work_item_id"] == "bd-ib-tbgxm4"
    assert record["pr_number"] == 7
    assert record[_SIZE_KEY] == 145


# --- the engine records it before any merge disposition --------------------


def test_a_merged_run_records_the_size_before_its_merge_disposition(tmp_path: Path) -> None:
    """The record lands between the pull-request confirmation and the merge poll."""
    _ = _module()
    _readable_unheld_tenant(repo=tmp_path)
    runner = _FakeRunner(
        queue=[
            _ok(stdout="fabro done"),
            _ok(stdout=_pr_json()),
            _ok(stdout=_pr_json(state="MERGED", sha="cafe01")),
            _pr_association(),
            _ok(),  # pull-primary
            *_venue_resolution(),
            *[_ok() for _ in range(8)],  # the janitor-checkout lifecycle
        ]
    )

    outcome, journal = _dispatch(runner=runner, repo=tmp_path)

    assert outcome.status == "green"
    stages = _stages(journal=journal)
    assert stages.count(_STAGE) == 1
    # BEFORE the merge disposition: the second `pr-view` is the merge poll, and
    # everything that decides the merge comes after it.
    assert stages.index(_STAGE) < stages.index("janitor-post-merge")
    assert stages.index(_STAGE) == stages.index("pr-view") + 1
    assert _diff_records(journal=journal)[0][_SIZE_KEY] == 145


def test_a_run_that_fails_after_its_pull_request_opened_still_carries_the_size(
    tmp_path: Path,
) -> None:
    """The repair's whole point: the metric no longer requires a green terminal."""
    _ = _module()
    _readable_unheld_tenant(repo=tmp_path)
    runner = _FakeRunner(
        queue=[
            _ok(stdout="fabro done"),
            _ok(stdout=_pr_json()),
            _ok(stdout=_pr_json()),
        ]
    )

    outcome, journal = _dispatch(runner=runner, repo=tmp_path, attempts=1)

    assert (outcome.status, outcome.stage) == ("failed", "merge-poll")
    assert _diff_records(journal=journal)[0][_SIZE_KEY] == 145


def test_a_run_with_no_pull_request_records_no_size_at_all(tmp_path: Path) -> None:
    """No pull request, no measurement — and no fabricated record claiming one."""
    _ = _module()
    runner = _FakeRunner(queue=[_ok(stdout="fabro done"), _ok(stdout="not json")])

    outcome, journal = _dispatch(runner=runner, repo=tmp_path)

    assert (outcome.status, outcome.stage) == ("failed", "pr-view")
    assert _diff_records(journal=journal) == []


# --- terminal calibration reads it back off the journal -------------------


def test_calibration_reads_the_recorded_size_off_this_item_s_journal() -> None:
    """Derived from the record the observing stage wrote, like the fix-loop count."""
    calibration = _calibration()
    records = (
        {"work_item_id": _WORK_ITEM_ID, "stage": "pr-view"},
        {"work_item_id": "other", "stage": _STAGE, _SIZE_KEY: 9999},
        {"work_item_id": _WORK_ITEM_ID, "stage": _STAGE, _SIZE_KEY: 145},
    )

    assert calibration.pr_open_diff_size(records=records, work_item_id=_WORK_ITEM_ID) == 145


def test_calibration_reads_the_most_recent_record_for_a_redispatched_item() -> None:
    """A journal accumulates across dispatches; the newest record is this run's."""
    calibration = _calibration()
    records = (
        {"work_item_id": _WORK_ITEM_ID, "stage": _STAGE, _SIZE_KEY: 40},
        {"work_item_id": _WORK_ITEM_ID, "stage": _STAGE, _SIZE_KEY: 145},
    )

    assert calibration.pr_open_diff_size(records=records, work_item_id=_WORK_ITEM_ID) == 145


def test_calibration_reports_absence_rather_than_zero_for_every_unobservable_shape() -> None:
    """No record, a null size, a boolean, and a non-numeric all read as absent."""
    calibration = _calibration()

    assert calibration.pr_open_diff_size(records=(), work_item_id=_WORK_ITEM_ID) is None
    for unusable in (None, True, "145"):
        records = ({"work_item_id": _WORK_ITEM_ID, "stage": _STAGE, _SIZE_KEY: unusable},)
        assert calibration.pr_open_diff_size(records=records, work_item_id=_WORK_ITEM_ID) is None


def test_the_calibration_record_and_journal_carry_the_recorded_size() -> None:
    """The proxy reaches the record and the journal under its own key."""
    calibration = _calibration()
    records = ({"work_item_id": "bd-ib-tbgxm4", "stage": _STAGE, _SIZE_KEY: 145},)
    item = _item()

    record = calibration.build_calibration_record(
        item=item,
        outcome=DispatchOutcome(
            work_item_id="bd-ib-tbgxm4",
            status="failed",
            stage="merge-poll",
            pr_number=7,
            merge_sha=None,
            detail="PR did not reach MERGED within the poll budget",
        ),
        repo_name="repo",
        journal_records=records,
        wall_clock_seconds=12.5,
        token_cost_micros=None,
        dispatch_context_size=900,
        merged_pr_diff_size=None,
    )
    journal = calibration.calibration_journal_record(record=record)

    # A failed post-PR run: the merged size is absent and the PR-open one is not.
    assert journal["merged_pr_diff_size"] is None
    assert journal[_SIZE_KEY] == 145

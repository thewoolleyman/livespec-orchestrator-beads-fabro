"""Gathering one dispatch's TDD order signals at calibration time.

This is the IO half of plan slice S3: the `gh pr view --json commits` probe,
the per-dispatch commit-series filter, the order-sink read, and the adapter
lookup, assembled into the `TddSignals` the terminal calibration span carries.

The correlation is per DISPATCH, not per item, and the mechanism is the same
id on both ends: the Dispatcher's `dispatch_id` is written into the sandbox
clone's `livespec.factoryRunId` git config, which is what stamps the
`Factory-Run-Id` trailer onto every commit the run authors. Filtering the
pull request's commits by that trailer is therefore an exact per-run
selection, and a re-dispatch of the same item cannot contribute commits to
it. The tests below assert exactly that, and assert that every unobservable
arm reports absence rather than a zero.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_tdd_probe.py"
)

_DISPATCH_ID = "5fe8e3dfbfd54faa979e85364d8e9863"
_OTHER_DISPATCH_ID = "0000e8dfbfd54faa979e85364d8e9863"


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


@dataclass(kw_only=True)
class _Runner:
    """Scripted CommandRunner: returns the queued result, logs the argv."""

    stdout: str = ""
    exit_code: int = 0
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        assert timeout_seconds > 0
        assert isinstance(cwd, Path)
        assert env is None
        self.calls.append(argv)
        return CommandResult(exit_code=self.exit_code, stdout=self.stdout, stderr="")


def _item(**overrides: object) -> WorkItem:
    base: dict[str, object] = {
        "id": "bd-ib-3h5vfq",
        "type": "feature",
        "status": "active",
        "title": "Publish factory TDD calibration signals",
        "description": "Do the thing.",
        "origin": "freeform",
        "gap_id": None,
        "rank": "a2",
        "assignee": "fabro",
        "depends_on": (),
        "captured_at": "2026-10-02T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
        "acceptance_criteria": "- One assertion.\n- Two assertions.\n",
    }
    base.update(overrides)
    return WorkItem(**base)  # pyright: ignore[reportArgumentType]


def _outcome(*, status: str = "green", pr_number: int | None = 4242) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-3h5vfq",
        status=status,
        stage="done",
        pr_number=pr_number,
        merge_sha="abc123",
        detail="merged",
    )


def _dispatch_id_record(*, dispatch_id: str = _DISPATCH_ID) -> dict[str, object]:
    return {
        "stage": "dispatch-id",
        "work_item_id": "bd-ib-3h5vfq",
        "dispatch_id": dispatch_id,
    }


def _commits_payload(*, commits: list[tuple[str, str]]) -> str:
    return json.dumps(
        {
            "commits": [
                {"messageHeadline": headline, "messageBody": body} for headline, body in commits
            ]
        }
    )


def _cycle_body(*, run_id: str, red: str, green: str) -> str:
    return (
        "Body prose.\n"
        f"TDD-Red-Captured-At: {red}\n"
        f"Factory-Run-Id: {run_id}\n"
        f"TDD-Green-Verified-At: {green}\n"
    )


# --- the dispatch id, read off the journal ---------------------------------


def test_the_dispatch_id_comes_from_this_items_journal_record() -> None:
    module = _module()

    assert (
        module.dispatch_id_for(
            records=(
                {"stage": "dispatch-id", "work_item_id": "bd-ib-other", "dispatch_id": "nope"},
                _dispatch_id_record(),
            ),
            work_item_id="bd-ib-3h5vfq",
        )
        == _DISPATCH_ID
    )


def test_an_absent_or_malformed_dispatch_id_record_reads_as_none() -> None:
    module = _module()

    assert module.dispatch_id_for(records=(), work_item_id="bd-ib-3h5vfq") is None
    assert (
        module.dispatch_id_for(
            records=({"stage": "outcome", "work_item_id": "bd-ib-3h5vfq"},),
            work_item_id="bd-ib-3h5vfq",
        )
        is None
    )
    assert (
        module.dispatch_id_for(
            records=({"stage": "dispatch-id", "work_item_id": "bd-ib-3h5vfq", "dispatch_id": 7},),
            work_item_id="bd-ib-3h5vfq",
        )
        is None
    )


# --- the commit series, selected per dispatch ------------------------------


def test_only_commits_carrying_this_runs_factory_trailer_are_counted() -> None:
    module = _module()
    runner = _Runner(
        stdout=_commits_payload(
            commits=[
                (
                    "feat: ours",
                    _cycle_body(
                        run_id=_DISPATCH_ID,
                        red="2026-10-01T20:00:00Z",
                        green="2026-10-01T20:05:00Z",
                    ),
                ),
                (
                    "feat: an earlier dispatch of the same item",
                    _cycle_body(
                        run_id=_OTHER_DISPATCH_ID,
                        red="2026-09-01T20:00:00Z",
                        green="2026-09-01T20:00:02Z",
                    ),
                ),
            ]
        )
    )

    signals = module.commit_signals_for_dispatch(
        repo=Path("/repo"),
        outcome=_outcome(),
        dispatch_id=_DISPATCH_ID,
        runner=runner,
    )

    assert signals is not None
    assert signals.red_commit_count == 1
    assert signals.green_commit_count == 1
    assert signals.red_green_gap_seconds_median == 300.0
    assert runner.calls == [
        ["gh", "pr", "view", "4242", "--json", "commits"],
    ]


def test_a_pull_request_carrying_none_of_this_runs_commits_is_unobservable() -> None:
    module = _module()
    runner = _Runner(
        stdout=_commits_payload(
            commits=[
                (
                    "feat: someone else's",
                    _cycle_body(
                        run_id=_OTHER_DISPATCH_ID,
                        red="2026-09-01T20:00:00Z",
                        green="2026-09-01T20:00:02Z",
                    ),
                )
            ]
        )
    )

    assert (
        module.commit_signals_for_dispatch(
            repo=Path("/repo"),
            outcome=_outcome(),
            dispatch_id=_DISPATCH_ID,
            runner=runner,
        )
        is None
    )


def test_every_unobservable_commit_series_arm_reads_as_none() -> None:
    module = _module()

    # No PR number: nothing published, so no series exists.
    assert (
        module.commit_signals_for_dispatch(
            repo=Path("/repo"),
            outcome=_outcome(pr_number=None),
            dispatch_id=_DISPATCH_ID,
            runner=_Runner(),
        )
        is None
    )
    # No dispatch id: a series could be read but not attributed to THIS run,
    # and a per-item aggregate is not what this field means.
    assert (
        module.commit_signals_for_dispatch(
            repo=Path("/repo"),
            outcome=_outcome(),
            dispatch_id=None,
            runner=_Runner(),
        )
        is None
    )
    # A failing probe.
    assert (
        module.commit_signals_for_dispatch(
            repo=Path("/repo"),
            outcome=_outcome(),
            dispatch_id=_DISPATCH_ID,
            runner=_Runner(exit_code=1, stdout="gh: not found"),
        )
        is None
    )
    # An unparseable payload.
    assert (
        module.commit_signals_for_dispatch(
            repo=Path("/repo"),
            outcome=_outcome(),
            dispatch_id=_DISPATCH_ID,
            runner=_Runner(stdout="not json"),
        )
        is None
    )


def test_a_non_green_outcome_still_reads_its_published_series() -> None:
    module = _module()
    runner = _Runner(
        stdout=_commits_payload(
            commits=[
                (
                    "feat: published but not merged",
                    _cycle_body(
                        run_id=_DISPATCH_ID,
                        red="2026-10-01T20:00:00Z",
                        green="2026-10-01T20:04:00Z",
                    ),
                )
            ]
        )
    )

    signals = module.commit_signals_for_dispatch(
        repo=Path("/repo"),
        outcome=_outcome(status="failed"),
        dispatch_id=_DISPATCH_ID,
        runner=runner,
    )

    assert signals is not None
    assert signals.red_commit_count == 1


# --- the assembled signals -------------------------------------------------


def test_the_gathered_signals_join_commits_order_and_adapter(tmp_path: Path) -> None:
    module = _module()
    from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import (
        CLAUDE_AGENT_ID,
        builtin_agent_catalog,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_order_sink import TddOrderSink

    sink = TddOrderSink(path=tmp_path / "tdd-order.json")
    _ = sink.record_decision(
        span={
            "name": "tdd.order.decision",
            "attributes": [
                {"key": "tdd.decision", "value": {"stringValue": "refuse"}},
                {"key": "tdd.head_state", "value": {"stringValue": "closed"}},
                {"key": "livespec.dispatch.id", "value": {"stringValue": _DISPATCH_ID}},
            ],
        },
        resource_attrs={"service.name": "livespec-tdd-order-guard"},
        at=1.0,
    )
    runner = _Runner(
        stdout=_commits_payload(
            commits=[
                (
                    "feat: ours",
                    _cycle_body(
                        run_id=_DISPATCH_ID,
                        red="2026-10-01T20:00:00Z",
                        green="2026-10-01T20:03:17Z",
                    ),
                )
            ]
        )
    )

    signals = module.gather_tdd_signals(
        repo=Path("/repo"),
        item=_item(),
        outcome=_outcome(),
        records=(
            _dispatch_id_record(),
            {
                "stage": "acp-nodes",
                "work_item_id": "bd-ib-3h5vfq",
                "acp_nodes": {
                    "implement": {"adapter": builtin_agent_catalog()[CLAUDE_AGENT_ID].command}
                },
            },
        ),
        sink=sink,
        runner=runner,
    )

    assert signals.red_commit_count == 1
    assert signals.green_commit_count == 1
    assert signals.red_green_gap_seconds_median == 197
    assert signals.order_refusals == 1
    assert signals.first_product_write_before_red is True
    assert signals.assertion_count == 2
    assert signals.adapter == CLAUDE_AGENT_ID


def test_a_dispatch_with_nothing_observable_gathers_only_the_assertion_count(
    tmp_path: Path,
) -> None:
    module = _module()
    from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_order_sink import TddOrderSink

    signals = module.gather_tdd_signals(
        repo=Path("/repo"),
        item=_item(),
        outcome=_outcome(pr_number=None),
        records=(),
        sink=TddOrderSink(path=tmp_path / "absent.json"),
        runner=_Runner(),
    )

    assert signals.red_commit_count is None
    assert signals.green_commit_count is None
    assert signals.suite_green_count is None
    assert signals.red_green_gap_seconds_median is None
    assert signals.order_refusals is None
    assert signals.first_product_write_before_red is None
    assert signals.adapter is None
    assert signals.assertion_count == 2

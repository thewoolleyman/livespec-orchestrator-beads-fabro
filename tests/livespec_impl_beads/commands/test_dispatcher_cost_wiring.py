"""Tests for wiring the fail-closed cost gate into the dispatch wave (5v9).

Covers `_dispatcher_cost.gate_wave` (the post-verdict stage the dispatcher
calls after the wave's outcomes are computed, alongside `reflect` /
`_alarm`) and `_dispatcher_plan.parse_run_id_for_work_item` (the
status-agnostic run-id matcher used to find the terminal run for a
dispatched item in `fabro ps -a --json`).

The load-bearing facts under test: `gate_wave` journals one `cost-gate`
record per launched (green) run carrying the leak-free verdict, and
returns the refusal events for the wave-level notify alarm. In autonomous
mode an unobservable cost is a `refuse`; in shadow mode it is a `warn`;
an outcome that never launched a run (e.g. a host-only refusal) is not
cost-gated. `gate_wave` is fail-open like the other post-verdict stages:
the verdict / exit code is already final, so a probe failure is journaled
and swallowed, never raised.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from livespec_impl_beads.commands._dispatcher_cost import gate_wave
from livespec_impl_beads.commands._dispatcher_engine import DispatchOutcome
from livespec_impl_beads.commands._dispatcher_plan import parse_run_id_for_work_item


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _green(work_item_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=work_item_id,
        status="green",
        stage="done",
        pr_number=7,
        merge_sha="abc123",
        detail="merged, post-merge janitor green",
    )


def _host_only_refused(work_item_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=work_item_id,
        status="failed",
        stage="host-only-refused",
        pr_number=None,
        merge_sha=None,
        detail="host-route this item",
    )


# A `fabro ps -a --json` array whose run goal embeds the work-item id (the
# render_goal shape) with a null cost — the canonical 5v9 dark-cost case.
_PS_JSON_NULL = (
    '[{"run_id": "01RUNZZZ", "status": {"kind": "succeeded"}, '
    '"goal": "Work-item: item-aaa\\nRepo: /x", "total_usd_micros": null}]'
)


def test_parse_run_id_for_work_item_matches_terminal_run() -> None:
    """The matcher finds a run by the goal-embedded id, status-agnostic."""
    run_id = parse_run_id_for_work_item(ps_json=_PS_JSON_NULL, work_item_id="item-aaa")
    assert run_id == "01RUNZZZ"


def test_parse_run_id_for_work_item_none_when_absent() -> None:
    """No matching run yields None (not a crash)."""
    run_id = parse_run_id_for_work_item(ps_json=_PS_JSON_NULL, work_item_id="item-missing")
    assert run_id is None


def test_parse_run_id_for_work_item_skips_non_dict_entries() -> None:
    """A non-dict array entry is skipped, then the matching dict run is found."""
    ps_json = (
        '["junk-not-a-dict", {"run_id": "01RUNXYZ", '
        '"goal": "Work-item: item-aaa\\nRepo: /x", "total_usd_micros": null}]'
    )
    run_id = parse_run_id_for_work_item(ps_json=ps_json, work_item_id="item-aaa")
    assert run_id == "01RUNXYZ"


def test_parse_run_id_for_work_item_none_when_matching_run_lacks_run_id() -> None:
    """A goal-matching run whose run_id is empty/absent yields None, not a crash."""
    ps_json = '[{"run_id": "", "goal": "Work-item: item-aaa\\nRepo: /x", "total_usd_micros": null}]'
    run_id = parse_run_id_for_work_item(ps_json=ps_json, work_item_id="item-aaa")
    assert run_id is None


def test_gate_wave_autonomous_refuses_and_journals_on_dark_cost() -> None:
    """Autonomous + unobservable cost → a refusal event + a cost-gate record.

    The enforce-mode 5v9 behavior (the `report` default never refuses).
    """
    journal = _RecordingJournal()
    refusals = gate_wave(
        mode="autonomous",
        outcomes=(_green("item-aaa"),),
        ps_json=_PS_JSON_NULL,
        journal=journal,
        cost_mode="enforce",
    )
    assert refusals == ("item-aaa",)
    gate_records = [r for r in journal.records if r.get("stage") == "cost-gate"]
    assert len(gate_records) == 1
    record = gate_records[0]
    assert record["work_item_id"] == "item-aaa"
    assert record["severity"] == "critical"
    assert record["refuse"] is True
    assert record["observable"] is False


def test_gate_wave_shadow_warns_and_does_not_refuse() -> None:
    """Shadow + unobservable cost → a warn cost-gate record, no refusal (enforce)."""
    journal = _RecordingJournal()
    refusals = gate_wave(
        mode="shadow",
        outcomes=(_green("item-aaa"),),
        ps_json=_PS_JSON_NULL,
        journal=journal,
        cost_mode="enforce",
    )
    assert refusals == ()
    gate_records = [r for r in journal.records if r.get("stage") == "cost-gate"]
    assert len(gate_records) == 1
    assert gate_records[0]["severity"] == "warn"
    assert gate_records[0]["refuse"] is False


def test_gate_wave_skips_outcomes_that_never_launched_a_run() -> None:
    """A host-only-refused outcome has no fabro run, so it is not cost-gated."""
    journal = _RecordingJournal()
    refusals = gate_wave(
        mode="autonomous",
        outcomes=(_host_only_refused("item-bbb"),),
        ps_json=_PS_JSON_NULL,
        journal=journal,
    )
    assert refusals == ()
    assert [r for r in journal.records if r.get("stage") == "cost-gate"] == []


def test_gate_wave_is_fail_open_on_unparseable_ps_json() -> None:
    """A run with no resolvable id (unparseable ps) journals a skip, never raises.

    A green outcome whose run id cannot be resolved from `fabro ps` is
    journaled as `cost-gate-skipped` (the cost cannot be observed for an
    unknown run) and contributes no refusal — the verdict is already final.
    """
    journal = _RecordingJournal()
    refusals = gate_wave(
        mode="autonomous",
        outcomes=(_green("item-aaa"),),
        ps_json="not json {",
        journal=journal,
    )
    assert refusals == ()
    assert any(r.get("stage") == "cost-gate-skipped" for r in journal.records)

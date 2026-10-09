"""The terminal calibration journal and span agree on the cycle observations.

Scenario 165 requires terminal calibration to expose the per-cycle observations
or their explicit absence diagnostics, the effective assertion count, the
completed-cycle count and whether a progress deficit or an adopted cycle ceiling
contributed to the bounce — and requires the two projections to AGREE, with an
absent numeric observation left null in the journal and OMITTED from the span,
its reason travelling beside it on both.

THE READING IS READ BACK, NOT RETAKEN. The boundary that evaluated it journaled
it, and calibration projects that record, for the reason `pr_open_diff_size` is
read back rather than re-probed: a second observation could not be shown to
agree with the one the boundary recorded, and a disagreement between them would
be invisible because both readings produce a well-formed record.

So the discriminating assertions are the ones a single projection would pass
anyway: that a key held as a null on the journal is ABSENT from the span rather
than shipped as the string `"None"`, that its reason survives on both, and that a
dispatch whose boundary recorded no reading at all journals explicit nulls rather
than a healthy-looking set of zeros.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration_emit import emit_calibration
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_gate import (
    RUNTIME_CONVERGENCE_STAGE,
    TERMINAL_BOUNDARY,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_projection import (
    CYCLE_PROJECTED_KEYS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._otel_scrub import ATTRIBUTE_ALLOWLIST
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "bd-ib-z2y4ca"


@dataclass(kw_only=True)
class _SilentRunner:
    """A runner whose every probe fails soft, so calibration does no network IO."""

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
        assert env is None or isinstance(env, dict)
        self.calls.append(argv)
        return CommandResult(exit_code=1, stdout="", stderr="unavailable")


def _item() -> WorkItem:
    return WorkItem(  # pyright: ignore[reportArgumentType]
        id=_ITEM_ID,
        type="feature",
        status="active",
        title="Feed per-cycle progress signals into the bounce",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a5",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-09T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_criteria="- One assertion.\n- Two assertions.\n",
    )


def _outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="green",
        stage="done",
        pr_number=None,
        merge_sha=None,
        detail="merged, post-merge janitor green",
    )


def _terminal_reading_record(
    *,
    cycles: list[dict[str, object | None]] | None,
    completed: int | None,
    assertions: int | None,
    contributors: list[str],
    series_reason: str | None = None,
    progress_reason: str | None = None,
) -> dict[str, object]:
    """One `runtime-convergence` journal record, as the terminal boundary writes it."""
    return {
        "stage": RUNTIME_CONVERGENCE_STAGE,
        "work_item_id": _ITEM_ID,
        "boundary": TERMINAL_BOUNDARY,
        "fix_loop_count": 3,
        "fix_loop_cap": 3,
        "ceiling_policy_unresolved": None,
        "cycle_observations": cycles,
        "completed_cycle_count": completed,
        "effective_assertion_count": assertions,
        "bounce_contributors": contributors,
        "cycle_series_unobserved_reason": series_reason,
        "cycle_progress_unobserved_reason": progress_reason,
        "cycle_measurement_method": "product-logical-lines-added-plus-removed",
    }


def _cycle(*, ordinal: int, lloc: int | None, seconds: int | None) -> dict[str, object | None]:
    return {
        "ordinal": ordinal,
        "pair_id": f"sha256:{ordinal:064d}@2026-10-01T1{ordinal}:00:00Z",
        "commit": f"{ordinal:040d}",
        "product_lloc_changed": lloc,
        "product_lloc_unobserved_reason": None if lloc is not None else "unsupported-counting",
        "elapsed_seconds": seconds,
        "elapsed_unobserved_reason": (
            None if seconds is not None else "invalid-or-reversed-timestamps"
        ),
    }


def _emit(
    *, tmp_path: Path, seed: dict[str, object] | None
) -> tuple[dict[str, object], list[dict]]:
    """Run the calibration stage over a journal seeded with `seed`; read both back."""
    journal_file = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_file)
    if seed is not None:
        journal.append(record=seed)
    args = argparse.Namespace(journal=str(journal_file))

    emit_calibration(
        args=args,
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(),
        journal=journal,
        wall_clock_seconds=12.5,
        dispatch_context_size=4096,
        runner=_SilentRunner(),
    )

    records = [json.loads(line) for line in journal_file.read_text(encoding="utf-8").splitlines()]
    calibration = [record for record in records if record["stage"] == "calibration"]
    assert len(calibration) == 1, f"expected one calibration record, got {len(calibration)}"
    spans_file = journal_file.with_name(f"{journal_file.stem}-calibration-spans.jsonl")
    attributes = [
        attribute
        for line in spans_file.read_text(encoding="utf-8").splitlines()
        for attribute in json.loads(line)["resourceSpans"][0]["scopeSpans"][0]["spans"][0][
            "attributes"
        ]
    ]
    return calibration[0], attributes


def _value(*, attributes: list[dict], key: str) -> object | None:
    for attribute in attributes:
        if attribute["key"] == key:
            return next(iter(attribute["value"].values()))
    return None


def _keys(*, attributes: list[dict]) -> set[str]:
    return {attribute["key"] for attribute in attributes}


def test_the_calibration_journal_and_span_agree_on_an_observed_cycle_series(
    tmp_path: Path,
) -> None:
    calibration, attributes = _emit(
        tmp_path=tmp_path,
        seed=_terminal_reading_record(
            cycles=[
                _cycle(ordinal=1, lloc=12, seconds=7),
                _cycle(ordinal=2, lloc=20, seconds=15),
            ],
            completed=2,
            assertions=2,
            contributors=[],
        ),
    )

    # Every projected key reaches the calibration journal record...
    for key in CYCLE_PROJECTED_KEYS:
        assert key in calibration, f"calibration record is missing {key!r}"
    assert calibration["completed_cycle_count"] == 2
    assert calibration["effective_assertion_count"] == 2
    assert calibration["bounce_contributors"] == []
    # ...and the journal keeps the per-cycle observations STRUCTURALLY, which is
    # what makes it the replay surface the clause asks calibration to retain.
    observations = calibration["cycle_observations"]
    assert isinstance(observations, list)
    assert [entry["ordinal"] for entry in observations] == [1, 2]
    assert [entry["product_lloc_changed"] for entry in observations] == [12, 20]
    assert [entry["elapsed_seconds"] for entry in observations] == [7, 15]
    # The span agrees on every queryable scalar.
    assert _value(attributes=attributes, key="completed_cycle_count") == "2"
    assert _value(attributes=attributes, key="effective_assertion_count") == "2"
    assert (
        _value(attributes=attributes, key="cycle_measurement_method")
        == (calibration["cycle_measurement_method"])
    )


def test_an_absent_numeric_observation_is_null_on_the_journal_and_absent_on_the_span(
    tmp_path: Path,
) -> None:
    calibration, attributes = _emit(
        tmp_path=tmp_path,
        seed=_terminal_reading_record(
            cycles=None,
            completed=None,
            assertions=2,
            contributors=[],
            series_reason="provenance-unreadable",
            progress_reason="provenance-unreadable",
        ),
    )

    # The journal records having looked and found nothing...
    assert calibration["completed_cycle_count"] is None
    assert calibration["cycle_observations"] is None
    # ...while the span OMITS the attribute rather than shipping the string
    # "None" into a column a derived column compares numerically.
    assert "completed_cycle_count" not in _keys(attributes=attributes)
    assert "cycle_observations" not in _keys(attributes=attributes)
    # The reason travels with the absence on BOTH surfaces, which is the half
    # most easily dropped: an omitted attribute alone is indistinguishable from
    # a signal nobody tried to measure.
    assert calibration["cycle_series_unobserved_reason"] == "provenance-unreadable"
    assert _value(attributes=attributes, key="cycle_series_unobserved_reason") == (
        "provenance-unreadable"
    )
    assert _value(attributes=attributes, key="cycle_progress_unobserved_reason") == (
        "provenance-unreadable"
    )


def test_a_bounce_contributor_reaches_both_surfaces(tmp_path: Path) -> None:
    calibration, attributes = _emit(
        tmp_path=tmp_path,
        seed=_terminal_reading_record(
            cycles=[_cycle(ordinal=1, lloc=400, seconds=9000)],
            completed=1,
            assertions=3,
            contributors=["completed-cycle-deficit", "adopted-cycle-ceiling"],
        ),
    )

    assert calibration["bounce_contributors"] == [
        "completed-cycle-deficit",
        "adopted-cycle-ceiling",
    ]
    assert _value(attributes=attributes, key="bounce_contributors") == (
        "completed-cycle-deficit,adopted-cycle-ceiling"
    )


def test_a_dispatch_whose_boundary_recorded_nothing_journals_explicit_nulls(
    tmp_path: Path,
) -> None:
    calibration, attributes = _emit(tmp_path=tmp_path, seed=None)

    # No reading was taken, so every observation is an explicit null — never a
    # zero completed-cycle count, which would read as a measured total deficit.
    for key in CYCLE_PROJECTED_KEYS:
        assert key in calibration, f"calibration record is missing {key!r}"
    assert calibration["completed_cycle_count"] is None
    assert calibration["effective_assertion_count"] is None
    assert calibration["cycle_observations"] is None
    assert calibration["bounce_contributors"] is None
    # And the span says WHY it carries no cycle numbers.
    assert "completed_cycle_count" not in _keys(attributes=attributes)
    assert isinstance(calibration["cycle_series_unobserved_reason"], str)
    assert isinstance(_value(attributes=attributes, key="cycle_series_unobserved_reason"), str)


def test_every_cycle_span_attribute_is_allowlisted_for_egress() -> None:
    """An unnamed key is dropped by the enrich stage with no error at all.

    So the projection and the allowlist have to be checked against each other
    rather than each against itself: a key present on the span and absent from
    the allowlist produces a span that looks complete here and arrives empty.
    """
    assert set(CYCLE_PROJECTED_KEYS) <= ATTRIBUTE_ALLOWLIST

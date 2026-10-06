"""The engine-cost arithmetic behind one workflow's execution allowance.

WHY THESE ARE UNIT CASES over the public functions rather than driven through
the resolver. Two of `commit_timeout_seconds`'s arms are UNREACHABLE from
`resolve_credential_lifetime_requirement`, and that is a property of the
resolution order rather than dead code: the resolver calls
`workflow_graph_path` first, which parses the same document, so a run config
that is not TOML at all is already reported as declaring no `[workflow]` graph
before any checkpoint budget is read. The arm still has to be right, because
this is a PUBLIC function whose contract says what it does with each kind of
unusable declaration, and a caller reaching it another way must not get the
engine's stock default.

WHAT THE STOCK-DEFAULT ARM IS FOR, since it is the one that looks like
carelessness. An ABSENT `[run.checkpoint] commit_timeout` is a complete,
ordinary run config, and the engine's own documented thirty seconds is the
correct reading. Every OTHER unusable shape refuses instead, because the
checkpoint enters the allowance multiplied by three and billed per attempt, so
substituting the stock default for a declaration the reader could not use grades
the credential against materially less time than the configuration asks for --
silently, since the smaller figure is just as well-formed.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_allowance import (
    commit_timeout_seconds,
    per_attempt_overhead_seconds,
    requirement_detail,
)

_TEN_MINUTES = 600
_STOCK = 30


def test_a_declared_duration_is_read_in_seconds() -> None:
    """The ordinary case: a quoted duration resolves to its own seconds."""
    text = '[run.checkpoint]\ncommit_timeout = "10m"\n'

    assert commit_timeout_seconds(committed_text=text) == _TEN_MINUTES


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        pytest.param('"45"', 45, id="bare-seconds"),
        pytest.param('"45s"', 45, id="seconds"),
        pytest.param('"2m"', 120, id="minutes"),
        pytest.param('"2h"', 7200, id="hours"),
    ],
)
def test_every_supported_duration_unit_resolves(declared: str, expected: int) -> None:
    """Each unit the reader supports, so a unit silently dropped is caught."""
    text = f"[run.checkpoint]\ncommit_timeout = {declared}\n"

    assert commit_timeout_seconds(committed_text=text) == expected


def test_an_absent_declaration_takes_the_engines_own_stock_budget() -> None:
    """The one case where defaulting is correct, and why it is not a refusal.

    A run config declaring no `[run.checkpoint]` is complete and ordinary, and
    thirty seconds is the ENGINE's documented default rather than a figure
    invented here.
    """
    text = '[workflow]\ngraph = "workflow.fabro"\n'

    assert commit_timeout_seconds(committed_text=text) == _STOCK


def test_a_declared_non_string_refuses_rather_than_taking_the_stock_budget() -> None:
    """Declared-but-not-a-string names what it found and refuses."""
    refusal = commit_timeout_seconds(committed_text="[run.checkpoint]\ncommit_timeout = 600\n")

    assert isinstance(refusal, str), refusal
    assert "commit_timeout" in refusal
    assert "stock budget is NOT used in its place" in refusal


def test_a_declared_string_that_is_not_a_duration_refuses() -> None:
    """A string in no supported unit cannot be accounted for, so it refuses.

    Distinct from the non-string arm: this one IS a string and the reader
    returned it, so the refusal comes from the duration grammar rather than from
    the TOML read.
    """
    refusal = commit_timeout_seconds(committed_text='[run.checkpoint]\ncommit_timeout = "10x"\n')

    assert isinstance(refusal, str), refusal
    assert "not a whole number of seconds, minutes or hours" in refusal


def test_a_run_config_that_is_not_toml_refuses_rather_than_defaulting() -> None:
    """An unparseable document says nothing about what it declares.

    Unreachable from the resolver, which reports the missing graph first — see
    the module docstring. Asserted here because the contract of this public
    function is what a caller reaching it another way depends on, and the one
    forbidden answer is the stock default.
    """
    refusal = commit_timeout_seconds(committed_text='[run.checkpoint\ncommit_timeout = "10m"\n')

    assert isinstance(refusal, str), refusal
    assert "not valid TOML" in refusal


def test_the_per_attempt_overhead_bills_the_checkpoint_three_times() -> None:
    """The checkpoint is spent per git call, which is what makes it threefold.

    Asserted as a RELATION between two budgets rather than against a literal
    sum: the fixed engine costs beside it are measured values that may be
    re-measured, while the threefold dependence on the configured budget is the
    structural claim — `sandbox_git.rs` spends `commit_timeout_ms` independently
    on `git add`, `git diff --cached` and `git commit`.
    """
    base = per_attempt_overhead_seconds(commit_timeout_seconds=_STOCK)
    raised = per_attempt_overhead_seconds(commit_timeout_seconds=_TEN_MINUTES)

    assert raised - base == 3 * (_TEN_MINUTES - _STOCK)


def test_the_overhead_exceeds_the_checkpoint_alone() -> None:
    """The fixed costs outside the node timeout are counted too.

    The control against an overhead that had quietly become the checkpoint and
    nothing else: the changed-file scans, the turn-entry mint and the retry
    backoff all sit outside a node timeout.
    """
    assert per_attempt_overhead_seconds(commit_timeout_seconds=_STOCK) > 3 * _STOCK


def test_the_detail_names_the_inputs_the_figure_read() -> None:
    """The inputs are NAMED, because they are what a per-item label can move.

    An operator comparing a status reading against a dispatch refusal needs to
    see whether the two read the same cap; a bare number cannot tell them.
    """
    detail = requirement_detail(
        workflow_name="implement-work-item",
        allowance_seconds=1000,
        overhead_seconds=285,
        inputs={"review_fix_visit_cap": 4},
    )

    assert "implement-work-item" in detail
    assert "review_fix_visit_cap=4" in detail
    assert "1000 seconds" in detail
    assert "285 seconds per attempt" in detail
    # The figure is an ALLOWANCE made a maximum by enforcement, and the detail
    # must not claim to be a measured wall clock.
    assert "NOT the graph's" in detail


def test_the_detail_reports_no_inputs_rather_than_an_empty_list() -> None:
    """A graph guarding no edge on an input still renders a readable detail."""
    detail = requirement_detail(
        workflow_name="fixture",
        allowance_seconds=10,
        overhead_seconds=1,
        inputs={},
    )

    assert "graph inputs none" in detail

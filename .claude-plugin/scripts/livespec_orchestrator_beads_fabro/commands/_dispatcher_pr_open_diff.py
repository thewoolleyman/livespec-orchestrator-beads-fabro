"""The branch-versus-base diff size, as a pull request opens.

Plan slice S4 (`bd-ib-tbgxm4`). The merged-PR diff size beside it is read only
for a GREEN outcome carrying a pull-request number, so it exists on exactly the
runs whose outcome is already known to be good: measured across 445 of this
repository's own calibration records (plan research,
`plan/factory-test-first-enforcement/research/opening-research-2026-09-30.md`),
present on all 292 converged runs and on ZERO of the 153 non-converged ones. A
size proxy whose PRESENCE is decided by the outcome it would predict cannot
predict that outcome, which is why the calibration pass had nothing to correlate
on the failing side.

This module carries the pieces of the repaired measurement that are pure: the
churn read off a forge payload, and the journal record the engine appends when
it first CONFIRMS the run's pull request. That moment is before any merge
disposition, so the value is on the journal whatever terminal the run later
reaches — a merge-poll timeout, a terminal required-check failure, a post-merge
janitor failure, or a bounce that arrived after publication all keep it. The
engine's own `confirm_pr` view supplies the number, so no second forge round
trip is spent and no probe can disagree with the view the engine routed on.

ABSENCE IS `None`, NEVER ZERO. A forge payload that reports neither field, or
only one of them, is unobservable; a pull request with genuinely zero churn is a
finding (the empty-diff refusal exists for it). Collapsing the two would make
the analysis pass read a dropped field as the sharpest possible small-slice
signal.

This module is PURE: no IO, no environment reads, and it never raises.
"""

from __future__ import annotations

from typing import cast

from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "PR_OPEN_DIFF_SIZE_KEY",
    "PR_OPEN_DIFF_STAGE",
    "parse_pr_diff_size",
    "pr_diff_size_of",
    "pr_open_diff_record",
]

# The journal stage the engine appends, and the key the size rides under. One
# literal each, shared by the producer (`_dispatcher_engine.run_dispatch`) and
# the consumer (`_dispatcher_calibration.pr_open_diff_size`), for the same
# reason `NON_CONVERGED_MARKER` is shared across its own two ends.
PR_OPEN_DIFF_STAGE = "pr-open-diff-size"
PR_OPEN_DIFF_SIZE_KEY = "pr_open_diff_size"


def pr_diff_size_of(*, payload: dict[str, object]) -> int | None:
    """Sum `additions` + `deletions` from an already-parsed forge payload.

    The churn the forge computed for the branch against its base. `None` when
    either field is absent or non-integer — a partial payload is unobservable,
    never a false zero. Shared by the string-parsing entry point below and by
    `parse_pr_view`, which holds the decoded payload already: two
    implementations of one sum is how the view and the probe would come to
    report different sizes for the same pull request.
    """
    additions = payload.get("additions")
    deletions = payload.get("deletions")
    if not isinstance(additions, int) or not isinstance(deletions, int):
        return None
    return additions + deletions


def parse_pr_diff_size(*, stdout: str) -> int | None:
    """Sum additions + deletions from a `gh pr view --json` payload; None if absent.

    Pure parse: returns the churn total when both integer fields are
    present, else `None` (an unparseable or partial payload is unobservable,
    never a false zero).
    """
    parsed = parse_json(text=stdout)
    if isinstance(parsed, JsonParseFailure):
        return None
    if not isinstance(parsed, dict):
        return None
    return pr_diff_size_of(payload=cast("dict[str, object]", parsed))


def pr_open_diff_record(
    *, work_item_id: str, pr_number: int, diff_size: int | None
) -> dict[str, object]:
    """The journal record naming the item, its pull request, and the churn.

    The pull-request number rides along because the size alone cannot be
    re-checked against anything: an operator reading the journal needs to know
    WHICH pull request was measured, and a re-dispatch of the same item opens a
    different one.
    """
    return {
        "stage": PR_OPEN_DIFF_STAGE,
        "work_item_id": work_item_id,
        "pr_number": pr_number,
        PR_OPEN_DIFF_SIZE_KEY: diff_size,
    }

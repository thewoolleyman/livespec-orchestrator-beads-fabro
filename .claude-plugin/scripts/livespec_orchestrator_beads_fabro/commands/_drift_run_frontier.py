"""The CONTIGUOUS coverage frontier one pass reached, and whether its scope closed.

PURE. The detection coverage-record contract defines the drift coverage point
as "the FRONTIER: the newest default-branch merge SHA such that it and every
earlier merge after the previous frontier has been processed with every finding
durably disposed", which for the Dispatcher's drift run means FILED — "and
which a held finding never is".

CONTIGUITY IS THE WHOLE OF IT, and it is the repair the independent review of
this plan's scoping required (research note 005, finding 3). The frontier is
the end of the ALL-FILED PREFIX, not the newest merge that happened to be
filed: a later merge's success "MUST NOT advance past" an earlier merge whose
pass failed, because advancing past it means the next pass never enumerates it
again and its behaviour is never proposed. A scan that took the newest filed
merge would skip the failed one silently, and both the record and the next
pass's enumeration would look perfectly healthy.

A MERGE IS "FILED" ONLY WHEN THREE THINGS HOLD, and each one has a different
way of being wrong:

- its pass did not FAIL — an unreadable merge or an unparseable judgement is a
  merge nobody processed;
- its judgement actually produced a VERDICT — a merge with no verdict carries
  no findings, so a set-equality test alone would read it as a merge whose every
  finding is filed, which is the exact reading that advances the frontier over
  an unprocessed merge;
- and every finding it carries IS filed — a HELD finding is not disposed of, so
  a merge carrying one stops the frontier even though its pass succeeded.

`scope_is_closed` is the ALL-OR-NOTHING question the Records rule asks on top of
that: "only when every one of them is processed with every finding filed does it
write a completed record". It is separate from the frontier because the two are
answered differently on a partial scope — the frontier names the prefix that DID
close, which is information, while the record must not be written at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from livespec_orchestrator_beads_fabro.commands._drift_run import MergeOutcome

__all__: list[str] = [
    "contiguous_frontier",
    "merge_is_filed",
    "scope_is_closed",
]


def merge_is_filed(*, outcome: MergeOutcome) -> bool:
    """Whether ONE merge was processed with every finding of it filed.

    See the module docstring for why all three conditions are checked and what
    each one catches on its own.
    """
    if outcome.failure is not None or outcome.verdict is None:
        return False
    return {finding.identity for finding in outcome.findings} == set(outcome.filed)


def contiguous_frontier(*, judged: Sequence[MergeOutcome]) -> str | None:
    """The newest merge of the ALL-FILED PREFIX, or None when the prefix is empty.

    None is also the answer for an empty scope, and the two coincide for a
    reason rather than by accident: in both cases there is no merge the frontier
    may advance to, and inventing one would record a coverage point the pass
    never earned.
    """
    reached: str | None = None
    for outcome in judged:
        if not merge_is_filed(outcome=outcome):
            return reached
        reached = outcome.merge
    return reached


def scope_is_closed(*, judged: Sequence[MergeOutcome]) -> bool:
    """Whether EVERY merge of the scope was processed with every finding filed.

    False for an empty scope as well, which is deliberate: a pass with nothing
    to judge has no coverage point to claim, and the contract's completed record
    carries one or is not written.
    """
    return bool(judged) and all(merge_is_filed(outcome=outcome) for outcome in judged)

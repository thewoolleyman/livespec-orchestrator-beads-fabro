"""The merge wait's ending for an armed pull request the default branch overtook.

The v145 "Armed pull request overtaken by the default branch" clause of
`SPECIFICATION/contracts.md`, exercised by Scenario 184. A run arms auto-merge
for the head its latest proof record names and then ends; a later
default-branch commit conflicts with that head; the forge keeps the auto-merge
request standing on a pull request it can no longer merge. Nothing in the run
is left to notice, so the Dispatcher's own merge wait is the only surface that
can, and the ending it takes is a REST rather than a repair: the clause forbids
the Dispatcher from disarming, closing or rewriting the pull request, because
the resumed run's `pr_refresh` is what disarms it before refreshing.

PURE, which is what makes each of the three decisions below testable on its
own: whether one poll REPORTS the condition, how many such reports the ending
takes, and what the outcome detail says. The wait that counts them lives in
`_dispatcher_engine_merge`.

THREE PROPERTIES AN EDITOR MUST NOT INVERT.

The reading requires an ARMED pull request, and that term is load-bearing
rather than incidental. An unarmed pull request in conflict with its base is an
ordinary one nobody has asked the forge to merge, and resting it at
needs-human would convert every conflicting draft into a human decision. The
clause scopes the whole paragraph with "After a run arms auto-merge".

`DIRTY` is the forge's conflicting reading and `BEHIND` is NOT. They look
adjacent -- both say the base moved -- and they have opposite remedies: the
wait already repairs a `BEHIND` pull request with `update-branch`, which is the
non-conflicting advance the clause leaves alone, while `DIRTY` is the advance
no refresh of the base can absorb. Reading them together would end a routinely
refreshable pull request at needs-human.

And the ending takes TWO CONSECUTIVE reports, never one. The forge computes
mergeability asynchronously, so a single reading taken while it is recomputing
can report a conflict that does not survive the next poll; requiring two
consecutive reports is what keeps a transient recomputation from resting a
healthy pull request. A poll whose view could not be READ is not a report in
either direction, so it breaks the streak rather than extending it -- the
clause asks for two polls that REPORT the condition, and an absent reading
reports nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "BASE_ADVANCED_AFTER_ARMING",
    "CONSECUTIVE_CONFLICTING_REPORTS",
    "BaseAdvancedAfterArming",
    "base_advanced_detail",
    "reports_base_advanced_after_arming",
]

BASE_ADVANCED_AFTER_ARMING = "base-advanced-after-arming"

# "When two consecutive polls report the pull request OPEN and in conflict with
# the default branch, the wait MUST stop before the poll budget."
CONSECUTIVE_CONFLICTING_REPORTS = 2

_OPEN = "OPEN"
_CONFLICTING = "DIRTY"


def reports_base_advanced_after_arming(
    *,
    state: str,
    auto_merge_armed: bool,
    merge_state_status: str,
) -> bool:
    """Does ONE poll report an armed, OPEN pull request conflicting with its base?

    Takes the three readings rather than a whole view, so the decision cannot
    reach for anything else the view happens to carry and the module stays a
    leaf of the engine's type graph.
    """
    return state == _OPEN and auto_merge_armed and merge_state_status == _CONFLICTING


@dataclass(frozen=True, kw_only=True)
class BaseAdvancedAfterArming:
    """The three measurements the ending's ledger comment names, as the poll read them.

    Carried as a typed field on the outcome rather than left for the record
    writer to re-derive, for the seam reason `dead_implementer_condition` and
    `provider_usage_limit_provider` are: the writer runs in the post-run
    disposition sequence, long after the poll that took these readings, and the
    only other way to reach them there is to re-match the rendered detail
    prose — which is exactly what this field set exists to stop.

    THE RUN ID AND THE PULL-REQUEST NUMBER ARE DELIBERATELY NOT HERE. Both
    already ride the outcome, and two accounts of one measurement is how a
    record comes to disagree with the result printed beside it.

    `pr_head` and `default_branch_tip` are `None` when the forge's view did not
    report them — NOT when the pull request has no head, and not as a sentinel
    a comparison would accept. The record states such a reading as unreported
    rather than silently omitting it, because an omitted line and a line
    reporting an unpassable name are different facts with different remedies.
    """

    factory: str
    pr_head: str | None
    default_branch_tip: str | None


def base_advanced_detail(*, work_item_id: str) -> str:
    """The outcome detail, naming the cause and then the recovery chain.

    It says the pull request is left AS IT STANDS, because the clause forbids
    the Dispatcher from disarming, closing or rewriting it: a reader who sees
    the ending must not go looking for a disarm that deliberately did not
    happen, and must not perform one by hand before the resumed run's
    `pr_refresh` takes it.

    THE CHAIN'S ORDER IS LOAD-BEARING, not stylistic. `resolve-blocked` is what
    releases the item, and a `resume` issued before it meets an item that is
    still blocked; naming them the other way round reads as a two-step recipe
    whose first step cannot work.
    """
    return (
        f"{BASE_ADVANCED_AFTER_ARMING}: the default branch advanced after this run armed "
        "auto-merge, and two consecutive merge-wait polls reported the pull request OPEN and "
        "conflicting with it, so the armed request can no longer merge the head a proof record "
        "names; the pull request is left as it stands. Recover with "
        f"`resolve-blocked:{work_item_id}:ready`, then `resume --item {work_item_id}`, which "
        "re-enters pr_refresh and disarms the pull request before refreshing it."
    )

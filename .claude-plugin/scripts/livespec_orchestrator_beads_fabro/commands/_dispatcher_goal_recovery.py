"""What a seeded dispatch's goal brief says about the tree its sandbox starts on.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" pairs the placement with its
narration in one sentence: "The new sandbox MUST check out the recorded SHA, and
the goal brief MUST name that commit as an interrupted prior attempt whose current
state the agent inspects before continuing."

WHY THIS IS NOT A BRANCH INSIDE `_dispatcher_goal`. That module's concern is the
item's OWN brief — its ledger fields, its riders, its ratified lessons — and every
line of it is untrusted prose routed through the MiniJinja escaper. This section
is about the DISPATCH's recovery placement, read off the invocation's resume
attributes and authored by the Dispatcher, so it shares neither input nor
provenance with anything there. Keeping it here is also what keeps that module
free of a dependency on `_dispatcher_resume_entry`, which owns the attribute names
and which the brief assembler otherwise has no business reading.

WHY BOTH ATTRIBUTES ARE REQUIRED, AND WHY THAT IS THE WHOLE DISCRIMINATOR. A
`resume` route sets `resume_head` and NO `resume_fetch_ref`: its head is on the
publish branch by construction, the run re-enters at the node it stopped at, and
the tree is that dispatch's own continuation. A `seeded` route sets BOTH, because
its commit lives on a preservation ref rather than on the branch — and the clause
attaches this requirement to the seed. So a renderer keyed on the head alone would
narrate every resumed run's own publication as somebody else's interrupted attempt
and send a run that enters at `pr` off to audit the work it had already proved.

WHY THE SECTION IS BLUNT ABOUT WHAT THE TREE IS NOT. A seeded sandbox is placed
on a commit the agent never made, and the placement is otherwise SILENT: the
prepare step fetches the ref and detaches onto the commit, and the brief that
arrives afterwards reads exactly like a fresh dispatch's. Both ways of being wrong
about it are expensive. Measured 2026-10-16 on this repository's own
`bd-ib-26deyw`, a plain re-dispatch after a provider-limit ending started from
master and discarded about eighty minutes of implement work — the loss the seed
exists to prevent — while an agent that read the seeded tree as a reviewed
baseline would build on work nobody graded. So the section names the commit, says
whose work it is, says what it is not, and states the inspection the clause
requires before continuing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    RESUME_FETCH_REF_ARG,
    RESUME_HEAD_ARG,
)

__all__: list[str] = [
    "InterruptedAttempt",
    "interrupted_attempt_for",
    "interrupted_attempt_section",
]


@dataclass(frozen=True, kw_only=True)
class InterruptedAttempt:
    """The commit a seeded recovery placed the sandbox on, and the ref carrying it.

    BOTH, because the brief names both: the commit is what the agent inspects,
    and the ref is where it came from — which is how an operator reading the
    brief afterwards can tell a needs-human terminal tree from a preserved
    publish head without going back to the journal.
    """

    commit_sha: str
    fetch_ref: str


def interrupted_attempt_for(*, args: argparse.Namespace) -> InterruptedAttempt | None:
    """The placement this dispatch is seeded onto, or `None` for every other route.

    Read DEFENSIVELY through the shared constants, exactly as `resume_checkout_for`
    reads the same two attributes and for the same reason: every dispatch entry
    point reaches the brief through this seam and only a recovery route sets them,
    so a respelling at either end resolves absent, the brief renders as a plain
    one, and nothing in the output says the placement went unnarrated.

    An attribute that is present but EMPTY yields `None` rather than a placement
    naming nothing: an empty head reaches `git checkout --detach ''`, which fails
    the run in preparation, and a brief that had already told the agent to inspect
    that commit would be describing a placement which never happened.
    """
    head = getattr(args, RESUME_HEAD_ARG, None)
    fetch_ref = getattr(args, RESUME_FETCH_REF_ARG, None)
    if not isinstance(head, str) or not head:
        return None
    if not isinstance(fetch_ref, str) or not fetch_ref:
        return None
    return InterruptedAttempt(commit_sha=head, fetch_ref=fetch_ref)


def interrupted_attempt_section(*, attempt: InterruptedAttempt | None) -> str:
    """The brief's account of that placement, or `""` for a dispatch without one.

    `""` leaves the brief byte-identical to what it was before this existed, which
    is what keeps every ordinary dispatch — and every resume — untouched by the
    seeded path.
    """
    if attempt is None:
        return ""
    return (
        "\nInterrupted prior attempt:\n"
        f"Your sandbox has already been placed on commit {attempt.commit_sha},"
        f" fetched from {attempt.fetch_ref}. That commit is the UNFINISHED work of"
        " an earlier attempt at this same work-item which was interrupted before it"
        " could publish. It is NOT a reviewed baseline, NOT merged, and NOT work"
        " anyone has graded — parts of it may be half-done or wrong.\n"
        "INSPECT ITS CURRENT STATE BEFORE CONTINUING: read what that commit"
        " changed, run the repository's own checks against it, and establish which"
        " of this work-item's requirements it already satisfies and which it does"
        " not. Then continue from there rather than starting over, and correct what"
        " it got wrong rather than assuming it is right.\n"
    )

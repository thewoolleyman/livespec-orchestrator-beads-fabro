"""Whether one item's LATEST journaled dispatch released it for recovery.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" opens on this one question: "An
item is *released for recovery* when its latest journaled dispatch ended in a
first-stall release (the Dispatcher progress watchdog's own), a
`provider-limit-release` record, or an `adapter-launch-release` record."

WHY THE READING IS "LATEST DISPATCH", NOT "EVER RELEASED". An item can be
released, re-dispatched, and finish green; a lifetime reading would then route
the NEXT dispatch of that item through a recovery measurement whose subject no
longer exists — and the measurement would succeed, because a surviving publish
branch and an open pull request are exactly what a green merge leaves behind for
the few minutes before the janitor closes them. The clause's own word is
"latest", and the journal already carries the discriminator: `dispatch-id` is
written at every launch, so a release row that is followed by one belongs to a
dispatch the item has moved past.

WHY `adapter-launch-release` IS READ THOUGH NOTHING WRITES IT YET. The clause
names three releases and this repository implements two of them; the adapter
launch release is its own ratified work. Reading all three is what makes this
module right when the third lands rather than silently excluding it — the cost is
one literal, and the alternative is a release class that routes `fresh` with no
indication that the route was decided by an omission.

WHY EVERY UNREADABLE SHAPE IS "NOT RELEASED". A journal row is JSON an earlier
build wrote, so a stage may be absent or of the wrong type. Reading such a row as
a release would route an ordinary dispatch into a recovery measurement it has no
subject for; reading it as a plain dispatch loses at most one automatic recovery,
which the next dispatch of a genuinely released item takes anyway, because the
release row is still there.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_records import (
    PROVIDER_LIMIT_RELEASE_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_disposition import (
    STALL_RELEASE_STAGE,
)

__all__: list[str] = [
    "ADAPTER_LAUNCH_RELEASE_STAGE",
    "RELEASE_STAGES",
    "released_for_recovery",
]

# The release the adapter-launch clause journals. A LITERAL rather than an
# import, because nothing in this repository defines it yet: the clause that
# writes it is separate ratified work, and a module that cannot name the stage
# until its writer exists would route that whole release class `fresh` the day it
# lands, with nothing saying so.
ADAPTER_LAUNCH_RELEASE_STAGE = "adapter-launch-release"

# The three releases the clause enumerates. The other two are IMPORTED from the
# modules that write them, so a rename moves both ends together.
RELEASE_STAGES = frozenset(
    {
        STALL_RELEASE_STAGE,
        PROVIDER_LIMIT_RELEASE_STAGE,
        ADAPTER_LAUNCH_RELEASE_STAGE,
    }
)

# The stage every dispatch writes at launch, which is how this reading learns
# that a LATER dispatch has superseded an earlier release. Spelled here rather
# than imported for the reason `_dispatcher_resume_cancel_anchor` gives about the
# same literal: its writer keeps it private, and recognising the row is all this
# reading needs.
_DISPATCH_ID_STAGE = "dispatch-id"

_STAGE_KEY = "stage"
_WORK_ITEM_KEY = "work_item_id"


def released_for_recovery(*, records: Sequence[Mapping[str, object]], work_item_id: str) -> bool:
    """Whether the item's newest journaled dispatch ended in one of the releases.

    A single forward pass, because the journal is append-only and its order is
    the order the dispatches happened in: a launch row CLEARS the answer and a
    release row SETS it, so whatever the last of the two was is what the latest
    dispatch ended with. An item the journal never mentions reaches the end with
    the answer unset, which is the right reading for a first dispatch.
    """
    released = False
    for record in records:
        if record.get(_WORK_ITEM_KEY) != work_item_id:
            continue
        stage = record.get(_STAGE_KEY)
        if stage == _DISPATCH_ID_STAGE:
            released = False
        elif stage in RELEASE_STAGES:
            released = True
    return released

"""The session-headroom admission screen, run ahead of the expensive pre-dispatch rows.

The headroom assessment's refusal is correct and designed; its POSITION was the
defect (`bd-ib-tsrkqf`). It ran inside the admission valve, which every dispatch
reaches only after the whole pre-dispatch wall, so a dispatch the assessment was
going to refuse first spent the App reach probe, the Definition-of-Done
judgement (a model call), the proof-asset store and the Codex credential gate --
measured at about 14 minutes per attempt on 2026-10-28, with a launcher held in
the factory queue throughout. This screen asks the same question first.

IT ADDS NO DECISION. It resolves the verdict through the admission valve's own
builder and, when headroom emptied an admission-required node, journals through
the valve's own filter, so the rows, their fields and the scheduled reevaluation
are the ones the valve would have written. The floor, the horizon and the
projection are untouched.

IT REFUSES ONLY A HEADROOM-GOVERNED VERDICT. A chain emptied by a hold, an
unobservable source or a configuration fault keeps its existing position and its
existing cost; moving those is a different change with its own ordering argument.

A DISPATCH THE SCREEN PASSES JOURNALS NOTHING FROM IT, and spends no second
usage request. The verdict rides the invocation's arguments to the valve, which
reuses it while it is fresh (`SCREENED_VERDICT_REUSE_SECONDS`) and repeats the
assessment when the rows between the two have run long enough to make it stale --
the clause requires the assessment before claim. The valve's own record stays the
single account of a dispatch that proceeds.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    headroom_refusal_fields,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import (
    admission_acp_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_eligibility import (
    filter_eligible_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_screened_verdict import (
    SCREENED_VERDICT_ARG,
    stamp_screened_verdict,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "session_headroom_screen_refusal",
]


def session_headroom_screen_refusal(
    *, args: argparse.Namespace, repo: Path, items: Sequence[WorkItem], journal: JournalFile
) -> str | None:
    """The refusal text for a selection headroom has emptied a node for, else `None`.

    An EMPTY selection returns before any reading: the drain's idle pass has
    nothing to refuse, and a provider request per idle poll would be a cost with
    no dispatch behind it.

    Every item of a refused selection is journaled, because the verdict is a fact
    about the repository's nodes rather than about any one item, so each is
    refused identically -- the same one-refusal-per-row accounting the valve gives
    a wave.
    """
    if not items:
        return None
    verdict = admission_acp_verdict(repo=repo, journal=journal, evaluated=tuple(items))
    if verdict.viable or not headroom_refusal_fields(verdict=verdict):
        setattr(args, SCREENED_VERDICT_ARG, stamp_screened_verdict(verdict=verdict))
        return None
    _, refused = filter_eligible_candidates(
        repo=repo, preflight=verdict, candidates=list(items), journal=journal
    )
    return "\n".join(outcome.detail for outcome in refused)

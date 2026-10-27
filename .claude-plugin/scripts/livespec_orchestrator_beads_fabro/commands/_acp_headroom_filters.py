"""The TWO provider headroom filters: the last two of the six, by cohesion.

`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance", paragraph "Admission filters candidates by projected
Claude session headroom", and section "Provider spend containment", paragraph
"Admission filters Codex candidates by projected usage-window headroom". Each
says the same thing about its own provider: "Before claim and final per-node
selection, the Dispatcher MUST assess every otherwise-selectable covered
candidate on an admission-required ACP node", and each requires its one reading
to be reused across every node and candidate sharing the credential.

PURE, AND HANDED NO JOURNAL -- so "A reading creates NO observed availability
record and retires none" holds structurally for both clauses: there is no
parameter a ledger could arrive through.

SPLIT OUT OF `_acp_candidate_preflight` BY COHESION. That module owns the ORDER
of the filters, which IS the precedence rule, and a reader following that order
should find one line per filter rather than two filter BODIES for the last two.
The pair came out together rather than the Codex one alone, because they are one
concern read twice -- same shape, same memo discipline, same clause sentence --
and splitting them across two modules is how the two come to disagree about
when a reading is recorded.

THE READING IS RECORDED BEFORE THE SKIP IS DECIDED, in both. That is what makes
an above-floor reading journalable: each clause requires every assessment to be
journaled for each affected work-item, not only the ones that refused
something, so a filter that appended only on the refusing arm would leave the
journal silent on exactly the dispatches that went through.

ONE SKIP PER PROVIDER, WHATEVER THE SHORTFALL, and that is each clause in as
many words -- "A projection skip has exactly the semantics of a floor skip", and
"Every skip this clause defines has exactly the semantics of a Claude floor
skip". So the level, the weekly allowance, the provider's own refusal and the
projection all produce ONE `SkippedCandidate` under ONE reason, with the KIND
recorded on it. Every surface downstream (the governing-condition precedence,
the availability wait, the idle-factory projection) keys on that reason, so a
second token per shortfall would leave an emptied chain unnamed by all three.

THE TWO POPULATIONS ARE DISJOINT, which is why the order BETWEEN them is free
while their position below the probe is not. A candidate's resolved agent id is
`claude-acp` or `codex-acp`, never both, so the two filters cannot disagree
about one candidate; both sit below the probe because "a successful
credential-usability probe MUST NOT override a headroom skip" and because each
costs a round trip whose answer is discarded at the end of the evaluation.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom import (
    CodexHeadroomPolicy,
    CodexUsageReading,
    codex_headroom_covers_candidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom_projection import (
    codex_headroom_skip_kind,
)
from livespec_orchestrator_beads_fabro.commands._acp_preflight_skips import (
    HEADROOM_SKIP,
    CodexHeadroomShortfall,
    HeadroomShortfall,
    PreflightInputs,
    SkippedCandidate,
    codex_headroom_skip,
    ephemeral_skip,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    SessionHeadroomReading,
    headroom_covers_candidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_projection import (
    headroom_skip_kind,
)

__all__: list[str] = [
    "claude_headroom_skip_for",
    "codex_headroom_skip_for",
]


def claude_headroom_skip_for(
    *,
    candidate: AcpCandidate,
    inputs: PreflightInputs,
    assessments: list[SessionHeadroomReading],
) -> SkippedCandidate | None:
    """Assess a COVERED candidate's projected credential, and skip only a shortfall.

    THREE SHORTFALLS, ONE SKIP, which is the clause's own equivalence. WHICH of
    them decided it is recoverable from the KIND the skip carries, so the record
    surfaces can name a projection skip as a projection skip without a second
    skip reason that every consumer would have to learn.
    """
    policy = inputs.headroom
    if policy is None or not headroom_covers_candidate(
        candidate=candidate, builtin_pairs=inputs.builtin_pairs
    ):
        return None
    reading = policy.read()
    if reading not in assessments:
        assessments.append(reading)
    kind = headroom_skip_kind(reading=reading, floor_percent=policy.floor_percent)
    if kind is None:
        return None
    return ephemeral_skip(
        candidate=candidate,
        reason=HEADROOM_SKIP,
        shortfall=HeadroomShortfall(
            reading=reading,
            floor_percent=policy.floor_percent,
            horizon_minutes=policy.horizon_minutes,
            kind=kind,
        ),
    )


def codex_headroom_skip_for(
    *,
    candidate: AcpCandidate,
    policy: CodexHeadroomPolicy | None,
    assessments: list[CodexUsageReading],
) -> SkippedCandidate | None:
    """Assess a COVERED candidate's Codex usage window, and skip only a shortfall.

    `assessments` is MUTATED rather than returned, exactly as its Claude
    sibling's is: the readings belong to the NODE being filtered and the caller
    accumulates them across its whole chain, so a return value would make a
    candidate's survival and its reading two answers the caller had to
    recombine.

    An ABSENT policy and an UNCOVERED candidate are ONE arm, because neither
    owes a reading and both must leave the candidate exactly as selectable as
    it was. That is what makes the whole clause a total no-op for every surface
    which composes a verdict without a policy -- wait attention and
    idle-factory, whose verdict must reach no provider at all.
    """
    if policy is None or not codex_headroom_covers_candidate(candidate=candidate):
        return None
    reading = policy.read()
    if reading not in assessments:
        assessments.append(reading)
    kind = codex_headroom_skip_kind(reading=reading, floor_percent=policy.floor_percent)
    if kind is None:
        return None
    return codex_headroom_skip(
        candidate=candidate,
        shortfall=CodexHeadroomShortfall(
            reading=reading,
            floor_percent=policy.floor_percent,
            horizon_minutes=policy.horizon_minutes,
            kind=kind,
        ),
    )

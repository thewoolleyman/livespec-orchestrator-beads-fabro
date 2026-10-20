"""The three real mutation barriers, and the four facts that only look like one.

PURE. `contracts.md` section "Launch obligations and consumed recovery": "A
legitimate human HOLD MUST name authority, reason, owner and release condition
while retaining the original obligation/deadline history. Running commits/hooks
and open Red-Green pairs MUST be visible mutation barriers. ... Idle state, an
ack, prose deadline or stale diagnostic alone MUST NOT count as a HOLD."

WHY A HOLD IS GRADED ON ALL FOUR FIELDS AND NOT ON ITS PRESENCE. A hold that
names no release condition cannot be released — it is an indefinite stop wearing
the shape of a decision — and one that names no authority cannot be audited. The
clause enumerates the four, so an incomplete one is NOT a barrier; it is a
finding, reported through the diagnostic so the operator who wrote it can see why
it is not stopping anything.

WHY THE FOUR IMITATIONS ARE CARRIED IN THE STATE AT ALL. They are the facts an
incident actually presents — the 2026-10-07 stall had an idle session, an
unanswered notification, a prose 14:25 deadline and a pointer to a completed
diagnostic, and NO human blocker. A consumer that read any of them as a hold
would do exactly what that incident did: nothing, indefinitely, while reporting a
reason. So they are observed, reported, and never obeyed; "expiry triggers
authorized diagnosis" is what happens instead.

WHY THE HOLD OUTRANKS THE OTHER TWO BARRIERS. All three defer equally, so the
order decides only WHICH ONE IS REPORTED — and a deferral is actionable only in
so far as a reader can tell when it clears. A hold carries its own release
condition; a commit hook and a Red-Green pair clear on their own. Reporting the
hook while a hold stood would tell an operator to wait for something that was
never the reason.

WHY NOTHING HERE TOUCHES THE OBLIGATION. The grade is a function of the safety
state alone, so it cannot shorten a deadline, clear a transition or interrupt a
worker: "No boundary may bypass spec/admission valves, interrupt a commit, close
another session's pane or break a Red-Green pair to meet a timing bound" holds
because there is no such reach in this module to begin with.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "BARRIER_COMMIT_HOOK",
    "BARRIER_HUMAN_HOLD",
    "BARRIER_RED_GREEN_PAIR",
    "DIAGNOSTIC_HOLD_INCOMPLETE",
    "DIAGNOSTIC_NO_BARRIER_FROM_IDLE_FACTS",
    "MUTATION_DEFERRED",
    "MUTATION_PERMITTED",
    "SAFETY_BARRIERS",
    "HumanHold",
    "SafetyState",
    "SafetyVerdict",
    "safety_verdict",
]

BARRIER_HUMAN_HOLD = "human-hold"
BARRIER_COMMIT_HOOK = "active-commit-hook"
BARRIER_RED_GREEN_PAIR = "open-red-green-pair"

# CLOSED, in the order a deferral reports them. There is deliberately no member
# for an idle session or an unanswered notification: the omission is what keeps
# those facts from being able to defer anything.
SAFETY_BARRIERS: tuple[str, ...] = (
    BARRIER_HUMAN_HOLD,
    BARRIER_COMMIT_HOOK,
    BARRIER_RED_GREEN_PAIR,
)

MUTATION_PERMITTED = "permitted"
MUTATION_DEFERRED = "deferred"

DIAGNOSTIC_HOLD_INCOMPLETE = "hold-incomplete"
DIAGNOSTIC_NO_BARRIER_FROM_IDLE_FACTS = "no-barrier-from-idle-facts"


@dataclass(frozen=True, kw_only=True)
class HumanHold:
    """A human HOLD, as the clause requires one to be recorded."""

    authority: str
    reason: str
    owner: str
    release_condition: str

    @property
    def valid(self) -> bool:
        """Whether all four fields carry a real value.

        Whitespace does not count: a reason that is a run of spaces names no
        reason, and a non-empty test would admit it.
        """
        return all(
            value.strip() != ""
            for value in (self.authority, self.reason, self.owner, self.release_condition)
        )


@dataclass(frozen=True, kw_only=True)
class SafetyState:
    """Every safety fact a consumer observed before deciding to mutate.

    The last four are the imitations. They are fields rather than omissions
    because a consumer that observed them must be able to REPORT them — see the
    module docstring on the incident they came from.
    """

    hold: HumanHold | None
    commit_hook_running: bool
    red_green_pair_open: bool
    session_idle: bool
    notification_unanswered: bool
    prose_deadline: str | None
    stale_diagnostic: str | None


@dataclass(frozen=True, kw_only=True)
class SafetyVerdict:
    """Whether mutation may proceed, and the barrier that defers it.

    `hold` is populated only when the HOLD is the deferring barrier, so a
    reader can act on its release condition without having to re-derive which
    barrier the verdict was about.
    """

    state: str
    barrier: str | None
    hold: HumanHold | None
    diagnostics: tuple[str, ...]

    @property
    def mutation_permitted(self) -> bool:
        return self.state == MUTATION_PERMITTED


def safety_verdict(*, state: SafetyState) -> SafetyVerdict:
    """Grade one safety state: permitted, or deferred behind one named barrier."""
    diagnostics = _diagnostics(state=state)
    if state.hold is not None and state.hold.valid:
        return SafetyVerdict(
            state=MUTATION_DEFERRED,
            barrier=BARRIER_HUMAN_HOLD,
            hold=state.hold,
            diagnostics=diagnostics,
        )
    barrier = _mechanical_barrier(state=state)
    if barrier is not None:
        return SafetyVerdict(
            state=MUTATION_DEFERRED, barrier=barrier, hold=None, diagnostics=diagnostics
        )
    return SafetyVerdict(state=MUTATION_PERMITTED, barrier=None, hold=None, diagnostics=diagnostics)


def _mechanical_barrier(*, state: SafetyState) -> str | None:
    """The barrier that clears on its own, or `None` while neither stands."""
    if state.commit_hook_running:
        return BARRIER_COMMIT_HOOK
    if state.red_green_pair_open:
        return BARRIER_RED_GREEN_PAIR
    return None


def _diagnostics(*, state: SafetyState) -> tuple[str, ...]:
    """What the consumer observed that did NOT decide the verdict.

    Both diagnostics are about things that look like a barrier and are not: an
    incomplete hold, and the four idle facts. They are reported on EVERY verdict
    rather than only on a permitted one, because a run deferred behind a commit
    hook while an unreleasable hold sits beside it is a state an operator needs
    to see whole.
    """
    found: list[str] = []
    if state.hold is not None and not state.hold.valid:
        found.append(DIAGNOSTIC_HOLD_INCOMPLETE)
    if _idle_facts_present(state=state):
        found.append(DIAGNOSTIC_NO_BARRIER_FROM_IDLE_FACTS)
    return tuple(found)


def _idle_facts_present(*, state: SafetyState) -> bool:
    """Whether any of the four non-barrier facts the clause names was observed."""
    return any(
        (
            state.session_idle,
            state.notification_unanswered,
            state.prose_deadline is not None,
            state.stale_diagnostic is not None,
        )
    )

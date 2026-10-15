"""Grading a host's independent recovery coverage, and the refusal it owes.

`contracts.md` section "Launch obligations and consumed recovery" makes this a
runtime measurement rather than a setting: "A protected-host coverage
declaration MUST be visible through inventory/check and bind the runtime and
version, terminal backend/version and instance, independent service identity
and generation, authorized recovery route, maximum observation interval and
takeover/launch budget, and installed proof artifact identity. Those measured
timing budgets together MUST fit the 60-second bound." It adds the two
sentences this module exists to enforce: "a PID or self-declaration alone MUST
NOT establish verified coverage", and "This declaration is runtime evidence,
not a user-selectable exemption."

PURE, and that is load-bearing rather than tidy. The decision is a function of
one declaration, so every state it distinguishes can be exercised without a
host — and a grade that reached for the host itself could only be tested on
whichever host the test ran on, which is the one place a coverage claim must
not come from.

WHY THERE ARE THREE STATES AND NOT TWO. `unmonitored` is a CONFIDENT NEGATIVE:
the declaration was read and found wanting. `unobservable` is the absence of a
measurement, and the same section requires them apart — "A host whose
independent coverage cannot be verified MUST explicitly refuse/report
unmonitored coverage, and MUST NOT count that result as autonomous prevention",
while "Missing/unreadable authority MUST be unobservable, not no obligations".
Collapsing them reports a broken instrument as a finding about the host, or a
real finding as a broken instrument; the remedies differ in both directions.

WHY NEITHER NEGATIVE STATE IS AN EXEMPTION. Both refuse. There is deliberately
no fourth state meaning "uncovered but proceed anyway": the clause says this
negative case "may only satisfy the explicit refusal control, never that
positive assertion", so a caller that wanted to launch regardless would have to
change the declaration — which is the change a reviewer sees.

WHY THE LADDER IS ORDERED AS IT IS, each rung reporting what it measured. A
blank bound identity comes first, because an identity nobody filled in is not a
declaration about anything and every later rung would be grading a placeholder.
The PID-shaped service identity comes next, since it is a SHAPE of identity and
the clause names it specifically; it must not be reported as an unsupported
route, which points at the wrong remedy. The route follows, because an
unsupported route cannot be rescued by any budget. The budgets come last, as
they are the only rung an operator can fix by reconfiguring an otherwise
sound owner.

WHY THE BUDGETS ARE SUMMED. The clause says the measured budgets "together
MUST fit the 60-second bound", so each one passing on its own proves nothing:
an observation interval of 45 seconds and a takeover budget of 30 cannot
produce a recovery within 60, and both are individually under it.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

__all__: list[str] = [
    "AUTHORIZED_RECOVERY_ROUTES",
    "COVERAGE_UNMONITORED",
    "COVERAGE_UNOBSERVABLE",
    "COVERAGE_VERIFIED",
    "DIAGNOSTIC_BUDGET_EXCEEDS_BOUND",
    "DIAGNOSTIC_COVERAGE_UNREADABLE",
    "DIAGNOSTIC_IDENTITY_UNBOUND",
    "DIAGNOSTIC_OWNER_ABSENT",
    "DIAGNOSTIC_ROUTE_UNSUPPORTED",
    "DIAGNOSTIC_SELF_DECLARED",
    "RECOVERY_BOUND_SECONDS",
    "CoverageDeclaration",
    "CoverageReading",
    "CoverageVerdict",
    "coverage_verdict",
]

COVERAGE_VERIFIED = "verified"
COVERAGE_UNMONITORED = "unmonitored"
COVERAGE_UNOBSERVABLE = "unobservable"

DIAGNOSTIC_COVERAGE_UNREADABLE = "coverage-unreadable"
DIAGNOSTIC_OWNER_ABSENT = "coverage-owner-absent"
DIAGNOSTIC_IDENTITY_UNBOUND = "coverage-identity-unbound"
DIAGNOSTIC_SELF_DECLARED = "coverage-self-declared"
DIAGNOSTIC_ROUTE_UNSUPPORTED = "coverage-route-unsupported"
DIAGNOSTIC_BUDGET_EXCEEDS_BOUND = "coverage-budget-exceeds-bound"

# The bound every measured budget must fit inside, from the same section's
# "Terminal target observation or original deadline expiry MUST schedule actual
# authorized diagnosis/recovery within 60 seconds".
RECOVERY_BOUND_SECONDS = 60.0

# The CLOSED set of routes a declaration may name. Closed for the reason the
# result grammar is: the clause licenses "the existing service recovery or
# authorized takeover path" and no new daemon, so a route this build does not
# know is refused exactly as a typo is — which is what keeps an operator from
# naming an ad-hoc nudge and having it graded as coverage.
AUTHORIZED_RECOVERY_ROUTES: tuple[str, ...] = ("overseer-supervised-service",)


@dataclass(frozen=True, kw_only=True)
class CoverageDeclaration:
    """The identities and budgets a protected host declares, as declared.

    Every field is bound rather than optional: the clause enumerates them as
    the things the declaration MUST bind, and an optional one would let a
    declaration that named half of them grade as coverage of the whole.
    """

    runtime: str
    runtime_version: str
    terminal_backend: str
    terminal_version: str
    terminal_instance: str
    service_identity: str
    service_generation: str
    recovery_route: str
    max_observation_interval_seconds: float
    takeover_budget_seconds: float
    proof_artifact: str


@dataclass(frozen=True, kw_only=True)
class CoverageReading:
    """One attempt to read the declaration: what it found, or why it could not.

    The two fields are INDEPENDENT of each other on purpose. A reading carrying
    a diagnostic is a failure to observe whatever the declaration field happens
    to hold, so the diagnostic is tested first; a reading with neither is a host
    that genuinely declares no owner.
    """

    declaration: CoverageDeclaration | None
    diagnostic: str | None = None


@dataclass(frozen=True, kw_only=True)
class CoverageVerdict:
    """The graded state, and the one measurement that produced it."""

    state: str
    diagnostic: str | None

    @property
    def verified(self) -> bool:
        return self.state == COVERAGE_VERIFIED

    def record_payload(self) -> dict[str, object]:
        """The projection a launch obligation persists beside its intent.

        The VERDICT travels onto the record rather than the declaration, so the
        record carries what was actually established about coverage instead of
        a copy of the host's claim about itself.
        """
        return {"diagnostic": self.diagnostic, "state": self.state}


def coverage_verdict(*, reading: CoverageReading) -> CoverageVerdict:
    """Grade one coverage reading as verified, unmonitored or unobservable."""
    if reading.diagnostic is not None:
        return CoverageVerdict(state=COVERAGE_UNOBSERVABLE, diagnostic=reading.diagnostic)
    declaration = reading.declaration
    if declaration is None:
        return CoverageVerdict(state=COVERAGE_UNMONITORED, diagnostic=DIAGNOSTIC_OWNER_ABSENT)
    refusal = _refusal(declaration=declaration)
    if refusal is not None:
        return CoverageVerdict(state=COVERAGE_UNMONITORED, diagnostic=refusal)
    return CoverageVerdict(state=COVERAGE_VERIFIED, diagnostic=None)


def _refusal(*, declaration: CoverageDeclaration) -> str | None:
    """The first rung this declaration fails, or `None` when it is coverage."""
    if not _identities_bound(declaration=declaration):
        return DIAGNOSTIC_IDENTITY_UNBOUND
    if declaration.service_identity.strip().isdigit():
        return DIAGNOSTIC_SELF_DECLARED
    if declaration.recovery_route not in AUTHORIZED_RECOVERY_ROUTES:
        return DIAGNOSTIC_ROUTE_UNSUPPORTED
    if not _budgets_fit_bound(declaration=declaration):
        return DIAGNOSTIC_BUDGET_EXCEEDS_BOUND
    return None


def _identities_bound(*, declaration: CoverageDeclaration) -> bool:
    """Whether every identity the clause enumerates carries a real value.

    Whitespace does not count as a value: a declaration whose terminal instance
    is a run of spaces names no instance, and a non-empty test would admit it.
    """
    return all(
        value.strip() != ""
        for value in (
            declaration.runtime,
            declaration.runtime_version,
            declaration.terminal_backend,
            declaration.terminal_version,
            declaration.terminal_instance,
            declaration.service_identity,
            declaration.service_generation,
            declaration.proof_artifact,
        )
    )


def _budgets_fit_bound(*, declaration: CoverageDeclaration) -> bool:
    """Whether the declared budgets TOGETHER fit the recovery bound.

    A non-finite or non-positive budget fails here rather than being treated as
    unbounded or as zero: an infinite interval is a gauge that never looks
    again, and a zero one is a claim no host can keep, so both are refused in
    the direction a timing bound must fail.
    """
    budgets = (
        declaration.max_observation_interval_seconds,
        declaration.takeover_budget_seconds,
    )
    if not all(isfinite(budget) and budget > 0 for budget in budgets):
        return False
    return sum(budgets) <= RECOVERY_BOUND_SECONDS

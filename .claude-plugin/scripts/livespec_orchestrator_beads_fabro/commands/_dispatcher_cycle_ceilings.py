"""The two adopted per-cycle runtime ceilings, and what counts as a breach.

Plan slice S6 (`bd-ib-z2y4ca`). `SPECIFICATION/contracts.md` adopts
`dispatcher.adopted_cycle_product_lloc_ceiling` and
`dispatcher.adopted_cycle_duration_seconds_ceiling` as COMMITTED-ONLY settings,
"absent by default and excluded from API-configurable policy", each "a positive
integer excluding booleans", with "invalid policy MUST refuse before claim or
lifecycle mutation".

NEITHER VALUE IS ADOPTED BY THIS MODULE, AND THAT IS THE POINT. "Each setting
MUST remain inactive until a maintainer separately adopts its numeric value
through a reviewed committed change", and "neither calibration analysis nor this
specification adopts a numeric value". So this module holds the two KEY NAMES,
the grammar a value must satisfy, and the comparison — and no number. The
numeric adoption is deferred until the repaired dataset carries roughly fifty
useful runs, which is the work-item's own recorded condition.

WHY THE BREACH IS STRICT, SPELLED AS ITS OWN RULE. "Equality MUST NOT be a
breach." A ceiling is the largest value still acceptable, so `observed == limit`
is the boundary case an adopter chose, and reporting it as a breach would make
every adopted figure one lower than the figure written down. The comparison is
therefore `>` and never `>=`, and the paired test pins both sides of the
boundary rather than one.

WHY AN UNOBSERVED MEASUREMENT YIELDS NO BREACH RATHER THAN A ZERO OR A PASS.
"Absent adoption or an unobserved measurement MUST NOT manufacture a breach."
An absent measurement supports no comparison in EITHER direction: it cannot
breach, and it equally cannot certify that the cycle was within the ceiling.
This module returns the breaches it can prove and says nothing else, which is
what leaves the absence diagnostics on the cycle record as the honest account.
An UNREADABLE series reaches the same answer by holding no cycles at all.

WHY THE BREACH CARRIES FOUR FACTS. The clause requires a breach to name "the
setting, adopted value, observed value and cycle identity", because each answers
a different question an operator has: which knob, what it was set to, what was
measured, and WHICH cycle — the last being the one a record that reported only a
count could never recover, since a run has several cycles and only some of them
breach.

WHY THE REFUSAL IS A STRING RATHER THAN AN EXCEPTION. The caller is a
pre-dispatch wall that must refuse before any claim, and it renders the
diagnostic itself; a raised exception there would be a bug-class escape from
inside a path whose whole purpose is to report a configuration fault
actionably. The shape matches `_node_timeouts`, which refuses an invalid
`stall_timeout_seconds` the same way and for the same reason.

This module is PURE: no IO, no environment reads, and it never raises. The
config read that supplies `block` lives in `_config.resolve_adopted_cycle_ceilings`.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    CompletedCycleSeries,
)

__all__: list[str] = [
    "ADOPTED_CYCLE_DURATION_SECONDS_CEILING_KEY",
    "ADOPTED_CYCLE_PRODUCT_LLOC_CEILING_KEY",
    "COMMITTED_ONLY_RUNTIME_CEILING_KEYS",
    "NO_ADOPTED_CYCLE_CEILINGS",
    "AdoptedCycleCeilings",
    "CycleCeilingBreach",
    "adopted_cycle_ceilings",
    "cycle_ceiling_breaches",
]

# The two setting names, spelled ONCE. Every surface that must recognize them —
# the config resolution, the pre-dispatch refusal, the bounce reason, and the
# public API policy surface that must REFUSE them — reads the spelling from
# here, so a key cannot be honoured by one surface and unknown to another.
ADOPTED_CYCLE_PRODUCT_LLOC_CEILING_KEY = "adopted_cycle_product_lloc_ceiling"
ADOPTED_CYCLE_DURATION_SECONDS_CEILING_KEY = "adopted_cycle_duration_seconds_ceiling"
COMMITTED_ONLY_RUNTIME_CEILING_KEYS: tuple[str, ...] = (
    ADOPTED_CYCLE_PRODUCT_LLOC_CEILING_KEY,
    ADOPTED_CYCLE_DURATION_SECONDS_CEILING_KEY,
)

# The configuration block both settings live under, for the refusal's own
# prose: a diagnostic naming a bare key leaves an operator hunting for where to
# write it.
_DISPATCHER_BLOCK = "dispatcher"


@dataclass(frozen=True, kw_only=True)
class AdoptedCycleCeilings:
    """The two ceilings as this repository has (or has not) adopted them.

    `None` per field is the DEFAULT state — nobody has adopted that ceiling —
    and it is a distinct state from a ceiling adopted at some large value: the
    first permits no comparison at all, while the second permits one that
    happens not to fire.
    """

    product_lloc: int | None
    duration_seconds: int | None

    @property
    def adopted(self) -> bool:
        """Whether EITHER ceiling has been adopted.

        Read by the surfaces that must not even look at the measurements when no
        ceiling is in force — "absence of adoption leaves size and duration
        observational" is a property of the whole evaluation, not of one field.
        """
        return self.product_lloc is not None or self.duration_seconds is not None


# What a repository that has adopted neither ceiling resolves to. It is the
# default on every caller, so a path that does not resolve configuration
# evaluates no ceiling rather than inventing one.
NO_ADOPTED_CYCLE_CEILINGS = AdoptedCycleCeilings(product_lloc=None, duration_seconds=None)


@dataclass(frozen=True, kw_only=True)
class CycleCeilingBreach:
    """One completed cycle measured strictly above one adopted ceiling."""

    setting: str
    limit: int
    observed: int
    cycle_ordinal: int
    pair_id: str
    commit: str

    def as_reason(self) -> str:
        """The one sentence the bounce surfaces for this breach.

        It names all four required facts in the order an operator reads them:
        which setting, what was observed, what the adopted limit is, and which
        cycle — identified by the pair identity AND the commit, because a rebase
        does not preserve the sha the forge showed while the pair identity
        survives it.
        """
        return (
            f"cycle {self.cycle_ordinal} (pair {self.pair_id}, commit {self.commit}) "
            f"measured {self.observed} against adopted "
            f"{_DISPATCHER_BLOCK}.{self.setting} = {self.limit}"
        )


def adopted_cycle_ceilings(*, block: dict[str, object]) -> AdoptedCycleCeilings | str:
    """Resolve both ceilings from a dispatcher configuration block, or refuse.

    An ABSENT key adopts nothing. A PRESENT key must hold a positive integer
    that is not a boolean, and anything else returns the refusal string naming
    the setting, what was found and the domain — the first refusal wins, in the
    declaration order above, so one message does not try to describe two faults.

    PRESENCE is tested by MEMBERSHIP, not by a `None` lookup: a committed
    `"adopted_cycle_product_lloc_ceiling": null` is a value an adopter WROTE,
    and reading it as absence would silently accept a declaration that adopts
    nothing while looking like an adoption. That is the one invalid form a
    `.get()` ladder cannot see.
    """
    resolved: dict[str, int | None] = {}
    for key in COMMITTED_ONLY_RUNTIME_CEILING_KEYS:
        if key not in block:
            resolved[key] = None
            continue
        raw = block[key]
        value = _positive_int(value=raw)
        if value is None:
            return (
                f"{_DISPATCHER_BLOCK}.{key} must be a positive integer "
                f"(a boolean is not an integer for this setting); got {raw!r}"
            )
        resolved[key] = value
    return AdoptedCycleCeilings(
        product_lloc=resolved[ADOPTED_CYCLE_PRODUCT_LLOC_CEILING_KEY],
        duration_seconds=resolved[ADOPTED_CYCLE_DURATION_SECONDS_CEILING_KEY],
    )


def cycle_ceiling_breaches(
    *, series: CompletedCycleSeries, ceilings: AdoptedCycleCeilings
) -> tuple[CycleCeilingBreach, ...]:
    """Every completed cycle measured strictly above an adopted ceiling.

    Empty whenever no comparison is possible — no adoption, no observed
    measurement, or an unreadable series — rather than reporting a breach or a
    pass. Both ceilings are evaluated per cycle, so a cycle over BOTH yields two
    breaches: the two settings are independent knobs and collapsing them would
    hide one of the two facts an operator has to act on.
    """
    found: list[CycleCeilingBreach] = []
    for cycle in series.cycles:
        for setting, limit, observed in (
            (
                ADOPTED_CYCLE_PRODUCT_LLOC_CEILING_KEY,
                ceilings.product_lloc,
                cycle.product_lloc_changed,
            ),
            (
                ADOPTED_CYCLE_DURATION_SECONDS_CEILING_KEY,
                ceilings.duration_seconds,
                cycle.elapsed_seconds,
            ),
        ):
            if limit is None or observed is None or observed <= limit:
                continue
            found.append(
                CycleCeilingBreach(
                    setting=setting,
                    limit=limit,
                    observed=observed,
                    cycle_ordinal=cycle.ordinal,
                    pair_id=cycle.pair_id,
                    commit=cycle.commit,
                )
            )
    return tuple(found)


def _positive_int(*, value: object) -> int | None:
    """The value as a positive int, or None when it is neither.

    `bool` is excluded explicitly because it is an `int` subclass in Python, so
    `true` would otherwise adopt a ceiling of one — a value that both passes
    validation and bounces every cycle that changed more than a single line.
    The same exclusion, for the same reason, as `_node_timeouts._positive_int`.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None

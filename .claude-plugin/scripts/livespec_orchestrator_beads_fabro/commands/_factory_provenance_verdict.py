"""The factory-provenance verdict: its grounds, its exit code and its rendering.

Three grounds admit a pull request that changes product Python, in this order
of trust: the forge says the factory GitHub App authored it; the canonical
incident-authority reader returned a retained receipt binding exactly this
repository, pull request, head and landed commit set to an expedited repair or
emergency revert; or the pull request carries the declared `factory-override`
label, the ordinary in-session exception the bypass audit counts.  The label
is refused for one carrier the ledger names: the normal factory repayment of
an incident, which must earn normal provenance.  Nothing a caller controls —
a label, an environment variable, a trailer, a marker — produces a receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_scoped_check_vacuity import (
    ScopedCheckOutcome,
    gate_exit_code,
    gate_tally,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._incident_provenance import IncidentReceipt

__all__: list[str] = [
    "FACTORY_APP_LOGINS",
    "FACTORY_OVERRIDE_LABEL",
    "ProvenanceVerdict",
    "exit_code",
    "permits_merge",
    "render_verdict",
]

# BOTH spellings the forge uses for the one factory GitHub App. The webhook
# payload emits the `[bot]`-suffixed form; `gh` emits the `app/`-prefixed one.
FACTORY_APP_LOGINS = (
    "app/thewoolleyman-factory-bot",
    "thewoolleyman-factory-bot[bot]",
)
# The declared-exception label. Its REASON belongs in the pull request body,
# where a reviewer and the bypass audit can both read it.
FACTORY_OVERRIDE_LABEL = "factory-override"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProvenanceVerdict:
    """One pull request's factory-provenance outcome, and the evidence behind it."""

    outcome: ScopedCheckOutcome
    author_login: str
    product_paths: tuple[str, ...]
    judged_path_count: int
    factory_authored: bool
    override_labeled: bool
    incident_receipt: IncidentReceipt | None = None
    repayment_carrier: IncidentReceipt | None = None


def exit_code(*, verdict: ProvenanceVerdict) -> int:
    """The gate's exit code: non-zero ONLY on observed failing provenance evidence."""
    return gate_exit_code(tally=gate_tally(outcomes=(verdict.outcome,)))


def permits_merge(*, verdict: ProvenanceVerdict) -> bool:
    """True iff this verdict leaves the pull request mergeable on provenance grounds."""
    return exit_code(verdict=verdict) == 0


def _routes_out() -> str:
    """The sanctioned ways past this wall, named in the failure itself."""
    return (
        "Routes out:\n"
        "1. Dispatch the work item through the factory, so the factory GitHub "
        f"App ({FACTORY_APP_LOGINS[0]}) authors the pull request.\n"
        f"2. Apply the `{FACTORY_OVERRIDE_LABEL}` label and record the reason "
        "for the in-session change in the pull request body; a normal incident "
        "repayment carrier cannot take this route.\n"
        "An incident exception is admitted only by the retained exact incident "
        "receipt the canonical incident-authority reader returns for a named "
        "`--incident-item`; an arbitrary label, trailer, marker or invocation "
        "environment cannot confer one."
    )


def _ground(*, verdict: ProvenanceVerdict) -> str:
    """Which of the three grounds admitted the change."""
    if verdict.factory_authored:
        return "its author is the factory GitHub App"
    receipt = verdict.incident_receipt
    if receipt is not None:
        owed = "outstanding" if receipt.repayment_outstanding else "recorded as repaid"
        return (
            f"it matches the retained exact incident receipt of {receipt.item_id} "
            f"({receipt.phase}: deferred verification, normal repayment {owed})"
        )
    return f"it carries the `{FACTORY_OVERRIDE_LABEL}` label"


def _refusal(*, verdict: ProvenanceVerdict) -> str:
    """Why a non-factory author was refused: the ordinary wall, or a repayment carrier."""
    carrier = verdict.repayment_carrier
    if carrier is not None:
        return (
            f"this pull request is the retained normal repayment carrier of incident "
            f"{carrier.item_id} ({carrier.phase}), which requires normal factory "
            "provenance; a label, trailer, marker or invocation environment is "
            "insufficient authorization"
        )
    return (
        f"this pull request carries no `{FACTORY_OVERRIDE_LABEL}` label and matches "
        "no retained exact incident receipt"
    )


def render_verdict(*, verdict: ProvenanceVerdict) -> str:
    """The gate's operator-facing message, naming the evidence it judged."""
    if verdict.outcome == "vacuous-match":
        return (
            f"vacuous-match: the product-Python scope matched zero of the "
            f"{verdict.judged_path_count} file(s) in this pull request, so this check "
            "OBSERVED NOTHING. That is not a pass — a gate counts it toward neither "
            "passing nor failing. The pull request is not blocked on factory-provenance "
            "grounds."
        )
    paths = "\n".join(f"- {path}" for path in verdict.product_paths)
    if verdict.outcome == "pass":
        return (
            f"Factory-provenance check: pass — @{verdict.author_login} may change "
            f"product Python because {_ground(verdict=verdict)}.\n{paths}"
        )
    return (
        "Factory-provenance check: FAIL — this pull request may not merge.\n\n"
        f"Author: @{verdict.author_login} is not the factory GitHub App, and "
        f"{_refusal(verdict=verdict)}.\n\n"
        f"Product Python it changes:\n{paths}\n\n"
        f"{_routes_out()}"
    )

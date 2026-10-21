"""The ONE projection of a credential requirement both operator surfaces report.

WHY ONE RENDERER AND NOT TWO, which is the whole reason this is a module rather
than a helper inside either command. The worker-credential-projection clause
requires that "the status and manual-renewal surfaces MUST report the same
figure and name which of the two figures governed". `codex-cred-status` and
`codex-cred-refresh` already duplicate their shared status projection, so two
independently-written requirement projections would be the obvious next step --
and the failure that follows is the invisible kind: both surfaces keep emitting
a well-formed figure, and only an operator comparing a status reading against a
renewal reading discovers they disagree about which key to edit. A shared
renderer makes the agreement structural rather than a convention two call sites
are trusted to keep.

WHY ALL FIVE FIGURES RIDE IT, and not just the one the gate enforces. The
governing figure alone is not actionable: it says how much lifetime is demanded
and never which configuration to change. So the projection carries both
candidates beside the figure that won, and the QUEUE ALLOWANCE separately from
the window it is half of -- because a reader cannot recover an addend from a
sum, and the queue allowance is the comparand the clause requires queue time
consumed to be reported against.

WHY THE QUEUE-TIME FIELD IS NOT HERE. "For a dispatch in flight they MUST also
report the queue time consumed" is a fact about a RUN, not about a requirement:
it needs the projection instant the host stamped and an observation of when that
run first began using the credential, neither of which a requirement carries.
This renderer projects what is known before any run exists; the in-flight
reading is appended by the surface that resolved it, so a reading nobody took
cannot be rendered as a zero.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_deadline import (
    CredentialLifetimeRequirement,
)

__all__: list[str] = [
    "CREDENTIAL_REQUIREMENT_PAYLOAD_KEY",
    "credential_requirement_human_lines",
    "credential_requirement_payload",
]

# The key both surfaces nest this projection under, so a reader joining a status
# reading to a renewal reading indexes one name rather than two.
CREDENTIAL_REQUIREMENT_PAYLOAD_KEY = "credential_requirement"


def credential_requirement_payload(
    *, requirement: CredentialLifetimeRequirement
) -> dict[str, object]:
    """Project one resolved requirement for an operator surface's JSON payload."""
    return {
        "governing_budget_seconds": requirement.allowance_seconds,
        "governing_figure": requirement.governing_figure,
        "required_remaining_seconds": requirement.required_seconds,
        "execution_allowance_seconds": requirement.execution_allowance_seconds,
        "credential_use_window_seconds": requirement.credential_use_window_seconds,
        "credential_queue_allowance_seconds": requirement.credential_queue_allowance_seconds,
    }


def _queue_allowance_line(*, payload: dict[str, object]) -> str:
    """The queue-allowance line, named so its long label stays on one f-string.

    Its own function rather than an implicit concatenation inside the tuple: the
    label and the line-length limit do not both fit, and pyright strict forbids
    the two-literal form.
    """
    return f"credential_queue_allowance_seconds: {payload['credential_queue_allowance_seconds']}"


def credential_requirement_human_lines(*, payload: dict[str, object]) -> tuple[str, ...]:
    """The same projection as the human rendering's lines, in the payload's order.

    Rendered FROM THE PAYLOAD rather than from the requirement, so the two
    renderings cannot report different figures: a human line computed from the
    requirement a second time is a second derivation, and the one thing this
    module exists to prevent is two derivations of one figure.
    """
    return (
        f"governing_figure: {payload['governing_figure']}",
        f"governing_budget_seconds: {payload['governing_budget_seconds']}",
        f"required_remaining_seconds: {payload['required_remaining_seconds']}",
        f"execution_allowance_seconds: {payload['execution_allowance_seconds']}",
        f"credential_use_window_seconds: {payload['credential_use_window_seconds']}",
        _queue_allowance_line(payload=payload),
    )

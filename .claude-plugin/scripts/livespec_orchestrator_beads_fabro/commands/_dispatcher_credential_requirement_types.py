"""Outcome types shared by credential-requirement resolution surfaces."""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = ["WorkflowFaultDeferral"]


@dataclass(frozen=True, kw_only=True)
class WorkflowFaultDeferral:
    """A requirement unresolvable because the WORKFLOW ITSELF is faulty.

    Returned INSTEAD of a refusal string when the reason no allowance could be
    derived is that the selected workflow is unregistered, unreadable, declares
    no graph, or carries an invalid node timeout -- faults that a LATER, more
    specific dispatch stage already owns and already reports with its own
    diagnostic and its own exit code.

    WHY THIS IS A SEPARATE TYPE rather than a string the caller inspects. The
    credential wall runs EARLY, so when it treated these faults as its own
    refusal it answered FIRST and the owning stage never spoke: Scenario 89's
    invalid node timeout reported a credential refusal at
    `EXIT_PRECONDITION_ERROR` instead of a timeout refusal at the dispatch exit
    code, and a registry fault wrote no outcome record at all because the wall
    returned before the stage that writes one. The fault was never a credential
    fault; the credential derivation merely NOTICED it first. Discriminating by
    substring over the refusal prose would make the classification a property of
    wording that any later edit silently breaks, which is the same defect class
    as deriving a bound from a graph comment -- so the class is decided AT THE
    SITE THAT KNOWS IT and carried in the type.

    DEFERRING HERE CANNOT ADMIT UNGRADED CREDENTIAL USE, which is the property
    that makes it safe rather than merely quieter. Every fault routed this way is
    a fault in the workflow configuration a dispatch must read before it can
    launch anything, so the owning stage refuses BEFORE any Fabro run exists and
    no credential is ever projected into a sandbox -- which is exactly what the
    two scenario tests guarding this assert by name ("refuses before any run
    exists"). A bound that genuinely cannot be established for a READABLE,
    well-formed workflow -- an unbounded cycle, an unknown `retry_policy`, an
    unparseable checkpoint declaration -- is NOT routed here: it stays a refusal
    string and still refuses at the gate, which is what preserves Scenario 19.
    """

    message: str

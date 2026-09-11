"""What one candidate attempt reported, and what outranks configured matching.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" names a closed list of failures that are "non-eligible before
configured matching and MUST terminate with their original identity":
authentication, command-not-found, cancellation, node deadline or stall
expiry, generic HTTP 400/404, remote-compaction 404, malformed
command/configuration, signal exit, unattributed sandbox/DNS/transport
failure, code/test/review/tool failure, and non-convergence. It closes
with "A mere pre-turn failure is not provider evidence."

THE ORDER OF THE TWO DETECTION ROUTES IS THE DESIGN. Some of these
classes are STRUCTURAL FACTS the caller already holds and this module
could only guess at: only the workflow knows a node failed its tests,
only the engine knows a deadline expired or a turn was cancelled. Those
arrive as `declared_class` and are believed. The rest are TEXT FACTS
readable from the diagnostic itself, and those are matched here through
the same normalized conjunction configured signatures use, so a
non-eligible marker and a configured literal can never be compared by
two different rules.

AN UNRECOGNIZED DECLARED CLASS IS STILL NON-ELIGIBLE. The caller asserted
a terminal class this module does not model; re-labelling it as one that
IS modelled would put a fabricated identity on the record, and treating
it as absent would let a failure the caller already classified fall
through to provider matching. `declared_non_eligible` says exactly what
is known: something terminal was declared, and it was not this module's
to name.

GENERIC HTTP 400/404 IS DELIBERATELY NOT DETECTED HERE, even though the
contract lists it alongside the rest. "Generic" is defined by Scenario
127 as "with no exact eligible discriminator", so whether a 400 is
generic is not knowable until matching has run. `_acp_failure_matching`
owns that reason and `_acp_failure_classifier` applies it after the match
attempt; both reasons still live in the one closed vocabulary below.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_failure_text import matches_any_conjunction

__all__: list[str] = [
    "NON_ELIGIBLE_REASONS",
    "AcpFailureSignal",
    "declared_non_eligible_reason",
    "non_eligible_reason",
]

# Every reason a classification can be non-eligible: the guard classes
# below, the two generic-status reasons `_acp_failure_matching` derives,
# and the three verdicts the classifier itself reaches.
NON_ELIGIBLE_REASONS: tuple[str, ...] = (
    "ambiguous",
    "authentication",
    "cancellation",
    "code_test_review_or_tool_failure",
    "command_not_found",
    "declared_non_eligible",
    "generic_http_400",
    "generic_http_404",
    "identity_absent",
    "malformed_configuration",
    "node_deadline",
    "non_convergence",
    "pre_turn_without_provider_evidence",
    "remote_compaction_404",
    "signal_exit",
    "stall_expiry",
    "unattributed_sandbox_or_transport",
    "unmatched",
)

# Exit statuses that ARE their own classification. The signature grammar
# bounds a configured `exit_code` to 1-125 for exactly this reason, so
# these three cannot collide with a configured refinement.
_NOT_EXECUTABLE_EXIT = 126
_NOT_FOUND_EXIT = 127
_SIGNAL_EXIT_FLOOR = 128

# The text-readable guard classes, each a tuple of conjunctions; a class
# fires when ANY one of its conjunctions matches in full.
#
# The remote-compaction 404 conjunction is the measured one already used
# by `_fabro_port_records._is_remote_compaction_404` -- three literals,
# not one, because "404 not found" alone is the generic status the
# contract keeps non-eligible on its own terms.
_GUARD_MARKERS: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = (
    (
        "remote_compaction_404",
        (("error running remote compact task", "404 not found", "responses/compact"),),
    ),
    (
        "authentication",
        (
            ("401 unauthorized",),
            ("authentication_error",),
            ("invalid api key",),
            ("invalid bearer token",),
            ("oauth token has expired",),
        ),
    ),
    (
        "command_not_found",
        (
            ("command not found",),
            ("executable file not found",),
            ("no such file or directory",),
        ),
    ),
    (
        "cancellation",
        (("operation was cancelled",), ("cancelled by the operator",)),
    ),
    (
        "node_deadline",
        (("node deadline exceeded",), ("deadline exceeded",), ("node timeout",)),
    ),
    (
        "stall_expiry",
        (("stall timeout",), ("no progress for",)),
    ),
    (
        "malformed_configuration",
        (
            ("failed to parse config",),
            ("invalid configuration",),
            ("malformed command",),
            ("malformed configuration",),
        ),
    ),
    (
        "unattributed_sandbox_or_transport",
        (
            ("connection refused",),
            ("connection reset by peer",),
            ("could not resolve host",),
            ("dns error",),
            ("temporary failure in name resolution",),
            ("tls handshake",),
        ),
    ),
    (
        "non_convergence",
        (("non-convergence",), ("did not converge",)),
    ),
)


@dataclass(frozen=True, kw_only=True)
class AcpFailureSignal:
    """One candidate attempt's terminal report, as the classifier reads it.

    THREE READABLE FIELDS AND NOTHING ELSE, which is the contract's
    "never an arbitrary exec-output tail, agent response, prompt,
    tool/test/review output, or run log" made structural: a caller
    holding a run log has nowhere to put it.

    `original_identity` is the failure's own name, carried so a
    non-eligible verdict can terminate WITH it rather than replacing it
    with a provider cause nobody measured.

    `turn_started` is False for a pre-turn failure. `declared_class` is a
    terminal class the caller already established structurally; see the
    module docstring for why it is believed rather than re-derived.
    """

    original_identity: str
    machine_code: str | None = None
    protocol_message: str | None = None
    terminal_diagnostic: str | None = None
    exit_code: int | None = None
    turn_started: bool = False
    declared_class: str | None = None

    @property
    def has_provider_evidence(self) -> bool:
        """Whether the provider said anything at all on any readable field."""
        return any(
            text is not None and text.strip() != ""
            for text in (self.machine_code, self.protocol_message, self.terminal_diagnostic)
        )


def declared_non_eligible_reason(*, declared_class: str) -> str:
    """The reason a caller-declared terminal class resolves to."""
    if declared_class in NON_ELIGIBLE_REASONS:
        return declared_class
    return "declared_non_eligible"


def non_eligible_reason(*, signal: AcpFailureSignal) -> str | None:
    """The guard class that outranks configured matching, or `None`.

    Ordered most-decisive first: a class the caller DECLARED, then the
    exit statuses that are their own classification, then the text
    markers. A declared class wins over the text because the caller
    observed the mechanism while this module can only read what the
    mechanism printed.
    """
    if signal.declared_class is not None:
        return declared_non_eligible_reason(declared_class=signal.declared_class)
    exit_reason = _exit_status_reason(exit_code=signal.exit_code)
    if exit_reason is not None:
        return exit_reason
    return _marker_reason(signal=signal)


def _exit_status_reason(*, exit_code: int | None) -> str | None:
    """The class an exit status names by itself, or `None`."""
    if exit_code is None:
        return None
    if exit_code >= _SIGNAL_EXIT_FLOOR:
        return "signal_exit"
    if exit_code in (_NOT_EXECUTABLE_EXIT, _NOT_FOUND_EXIT):
        return "command_not_found"
    return None


def _marker_reason(*, signal: AcpFailureSignal) -> str | None:
    """The first guard class whose conjunction matches a readable field."""
    for field_text in (signal.protocol_message, signal.terminal_diagnostic):
        if field_text is None:
            continue
        for reason, conjunctions in _GUARD_MARKERS:
            if matches_any_conjunction(conjunctions=conjunctions, text=field_text):
                return reason
    return None

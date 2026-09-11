"""How one declared signature is compared against one observed diagnostic.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" says text matching "reads only the named ACP protocol field or
separately captured terminal adapter startup/termination diagnostic,
never an arbitrary exec-output tail, agent response, prompt,
tool/test/review output, or run log."

THE FIELD IS CHOSEN BY `source`, NOT SEARCHED FOR. `_field` maps each of
the three ratified sources onto exactly one attribute of the observed
signal, so there is no path on which a literal declared for
`protocol.message` can be satisfied by a terminal diagnostic, and no path
at all onto an exec-output tail -- `AcpFailureSignal` simply carries no
such field. That is the structural half of the "never an arbitrary output
tail" clause; the prose half would be a rule somebody has to remember.

WHY A GENERIC STATUS NEEDS AN EXTRA DISCRIMINATOR. The same section makes
a generic HTTP 400/404 non-eligible while keeping the measured
model-naming 400 eligible, and Scenario 127 spells out the distinction:
"a generic HTTP 400 or 404 with no exact eligible discriminator
terminates with its original identity". A configured signature listing
only status vocabulary -- `400`, `bad request` -- would otherwise claim
every 400 a provider ever returns as an availability failure, which is
the exact false fallback the non-eligible list exists to prevent. So on a
diagnostic carrying a 400/404 marker, a text signature counts only when
it names something OUTSIDE that vocabulary. A machine-code signature is
exempt: an exact structured code IS the discriminator.

GENERIC-STATUS DETECTION CANNOT LIVE WITH THE OTHER GUARDS, and that is
why this reason is derived here rather than in `_acp_failure_signals`:
every other non-eligible class is decidable from the diagnostic alone,
while "generic" is defined by the ABSENCE of a matching discriminator and
is therefore only knowable after the match attempt has run.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_candidate_signatures import (
    AcpAvailabilitySignature,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_signals import AcpFailureSignal
from livespec_orchestrator_beads_fabro.commands._acp_failure_text import (
    conjunction_matches,
    matches_any_conjunction,
    normalized,
)

__all__: list[str] = [
    "GENERIC_STATUS_LITERALS",
    "MACHINE_CODE_SOURCE",
    "generic_status_reason",
    "signature_discriminates",
    "signature_matches",
]

MACHINE_CODE_SOURCE = "protocol.machine_code"
_MESSAGE_SOURCE = "protocol.message"

# The vocabulary a bare HTTP 400/404 already contains. A signature naming
# nothing else is claiming the status itself, which the contract forbids.
GENERIC_STATUS_LITERALS: frozenset[str] = frozenset(
    {
        "400",
        "404",
        "bad request",
        "http 400",
        "http 404",
        "http status 400",
        "http status 404",
        "not found",
        "status 400",
        "status 404",
    }
)

# What makes a diagnostic an HTTP 400 or 404 AT ALL. The bare digits are
# deliberately absent: "400" alone appears in token counts, byte sizes and
# model names, so keying on it would report half the factory's failures as
# generic status responses.
_STATUS_MARKERS: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = (
    (
        "generic_http_400",
        (("http 400",), ("status 400",), ("400 bad request",), ("bad request",)),
    ),
    (
        "generic_http_404",
        (("http 404",), ("status 404",), ("404 not found",)),
    ),
)


def signature_matches(*, signature: AcpAvailabilitySignature, signal: AcpFailureSignal) -> bool:
    """Whether this signature matches this observed failure.

    The optional `exit_code` REFINES whichever discriminator the source
    requires and is never consulted alone: a signature declaring one fails
    to match when the observed status differs, and a signature declaring
    none is unaffected by the status entirely.
    """
    if signature.exit_code is not None and signature.exit_code != signal.exit_code:
        return False
    observed = _field(source=signature.source, signal=signal)
    if observed is None:
        return False
    if signature.source == MACHINE_CODE_SOURCE:
        code = signature.machine_code
        return code is not None and code.strip() == observed.strip()
    return conjunction_matches(literals=signature.all_literals, text=observed)


def signature_discriminates(*, signature: AcpAvailabilitySignature) -> bool:
    """Whether this signature names anything beyond bare HTTP status vocabulary."""
    if signature.source == MACHINE_CODE_SOURCE:
        return True
    return any(
        normalized(text=literal) not in GENERIC_STATUS_LITERALS
        for literal in signature.all_literals
    )


def generic_status_reason(*, signal: AcpFailureSignal) -> str | None:
    """The non-eligible reason for an HTTP 400/404 diagnostic, or `None`.

    Both readable text fields are scanned because a status arrives on
    either transport: the protocol message carries it when the adapter
    speaks ACP, the terminal diagnostic when the adapter dies at startup.
    """
    for field_text in (signal.protocol_message, signal.terminal_diagnostic):
        if field_text is None:
            continue
        for reason, conjunctions in _STATUS_MARKERS:
            if matches_any_conjunction(conjunctions=conjunctions, text=field_text):
                return reason
    return None


def _field(*, source: str, signal: AcpFailureSignal) -> str | None:
    """The ONE observed field this source names, or `None` when it is absent."""
    if source == MACHINE_CODE_SOURCE:
        return signal.machine_code
    if source == _MESSAGE_SOURCE:
        return signal.protocol_message
    return signal.terminal_diagnostic

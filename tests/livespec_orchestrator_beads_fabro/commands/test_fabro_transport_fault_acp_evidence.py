"""The turn-timeout family needs ACP evidence, not just the word "timeout".

`transport_fault_from_cause` keys on three markers, and two of them are
MEASURED engine wordings specific enough to stand alone: `continued in
background` and `exited before protocol completed`. The third is the bare words
`timed out` / `timeout`, which belong to no component in particular — and the
classifier applied it to any cause carrying them.

That over-reach matters because of what the classification ASSERTS. Naming a
cause `turn-timed-out` says the ACP CARRIER between the engine and the agent
broke, and the detail then tells the operator that no agent asked anything and
no answer is owed. Said about a merge gate that timed out waiting for checks,
or about a provider request that expired, it names the wrong subsystem; said
about an agent that genuinely asked for a decision and happened to mention a
timeout while asking, it DENIES A PENDING QUESTION — which is the precise
failure the whole transport-fault split exists to prevent, reached from the
opposite direction.

So the loose marker is admitted only alongside evidence that the cause is about
ACP at all. The cases below are the negative controls that constraint needs:
each one carries a timeout word, none of them is an ACP transport fault, and
every one of them classified as `turn-timed-out` before.

Note what is NOT used as evidence: the fixed `ACP protocol error` wrapper. The
classifier is handed the INNERMOST cause, so the wrapper is out of scope by
construction — and admitting it would re-open the over-reach, since every ACP
cause chain carries it whatever the real fault was.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._fabro_transport_fault import (
    BACKGROUNDED_TOOL,
    TURN_TIMED_OUT,
    transport_fault_from_cause,
)

# Causes that carry a timeout word and are NOT an ACP transport fault.
_NOT_TRANSPORT = (
    pytest.param(
        "the merge gate timed out waiting for required checks to report",
        id="merge-gate-timeout",
    ),
    pytest.param(
        "provider request timed out after 60s; no response body was returned",
        id="provider-request-timeout",
    ),
    pytest.param(
        "janitor script exited 1: pytest timeout exceeded in tests/integration",
        id="suite-timeout",
    ),
    pytest.param(
        "the agent asks whether to raise the janitor timeout or split the suite; "
        "a human decision is needed before continuing",
        id="genuine-request-mentioning-a-timeout",
    ),
    pytest.param(
        "git push timed out contacting origin",
        id="network-timeout",
    ),
)


@pytest.mark.parametrize("cause", _NOT_TRANSPORT)
def test_a_timeout_word_without_acp_evidence_is_not_a_transport_fault(cause: str) -> None:
    """None is a first-class answer: the caller renders each under its own account."""
    assert transport_fault_from_cause(cause=cause) is None


def test_an_acp_turn_timeout_still_classifies() -> None:
    """The positive control, so the constraint is not merely disabling the family."""
    fault = transport_fault_from_cause(cause="ACP turn timed out after 14400s")

    assert fault is not None
    assert fault.family == TURN_TIMED_OUT


def test_acp_evidence_is_matched_as_a_word_and_not_as_a_substring() -> None:
    """`acp` inside another word is not evidence about the ACP carrier.

    Without the word boundary, any cause containing a token like `backacp` or a
    path segment spelling those letters would re-admit the whole over-reach
    through the back door.
    """
    assert transport_fault_from_cause(cause="hadacped the request; timed out") is None
    assert transport_fault_from_cause(cause="the acp session timed out") is not None


def test_the_specific_markers_are_unchanged_by_the_constraint() -> None:
    """Backgrounded and adapter-exit recognition is MEASURED and must not move.

    These two are the families with remedies attached, so a constraint aimed at
    the loose marker must not narrow them: neither wording mentions ACP in the
    way the timeout arm now requires, and both must still classify.
    """
    backgrounded = transport_fault_from_cause(
        cause="tool call toolu_01 (git push -u origin HEAD) continued in background as task b9"
    )
    assert backgrounded is not None
    assert backgrounded.family == BACKGROUNDED_TOOL
    assert backgrounded.command == "git push -u origin HEAD"

    adapter = transport_fault_from_cause(cause="the adapter exited before protocol completed")
    assert adapter is not None
    assert adapter.family != TURN_TIMED_OUT


def test_a_backgrounded_cause_mentioning_a_timeout_is_still_backgrounded() -> None:
    """The ordering guarantee survives: the family with the remedy wins."""
    fault = transport_fault_from_cause(
        cause="ACP tool call (sleep 600) continued in background after its 120s timeout"
    )

    assert fault is not None
    assert fault.family == BACKGROUNDED_TOOL

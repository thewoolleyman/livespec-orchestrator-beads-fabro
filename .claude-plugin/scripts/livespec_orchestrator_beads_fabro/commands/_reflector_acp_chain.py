"""Ordered candidate selection for the reflector's ACP host judgement."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate

__all__: list[str] = ["first_verdict"]

CandidateInvoker = Callable[..., str | None]
VerdictParser = Callable[[str], bool]


def first_verdict(
    *,
    candidates: Sequence[AcpCandidate],
    invoke: CandidateInvoker,
    is_verdict: VerdictParser,
) -> str | None:
    """Return the first candidate reply that parses as a verdict."""
    for candidate in candidates:
        reply = invoke(candidate=candidate)
        if reply is not None and is_verdict(reply):
            return reply
    return None

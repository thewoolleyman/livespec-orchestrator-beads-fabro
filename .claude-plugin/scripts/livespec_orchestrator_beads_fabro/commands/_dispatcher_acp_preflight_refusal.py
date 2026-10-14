"""The two consumers that ACT on an ACP preflight verdict.

Split out of `_dispatcher_acp_preflight` along the seam that module's own
docstring already named: it "reads the committed chain configuration, the
workflow graph, and the live availability records, hands them to the pure
verdict ... and offers the two consumers that ACT on it -- the admission
refusal, and the gate on the legacy credential re-probe wait". RESOLVING a
verdict and ACTING on one are two concerns; this file owns the second, and
holds the journal stage both the refusal and its readers key on.

Both functions are PURE over the verdict except for the one journal append,
which is what lets the admission ladder call the refusal per candidate row
without re-resolving anything: the verdict was resolved once for the whole
pass, so a refusal here reads a decision rather than re-deciding it.
"""

from __future__ import annotations

from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome

__all__: list[str] = [
    "ACP_PREFLIGHT_REFUSAL_STAGE",
    "JournalWriter",
    "acp_preflight_refusal",
    "credential_reprobe_wait_applies",
]

# The journal stage a before-claim preflight refusal is recorded under.
ACP_PREFLIGHT_REFUSAL_STAGE = "acp-preflight-refusal"


class JournalWriter(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


def acp_preflight_refusal(
    *,
    work_item_id: str,
    verdict: AcpPreflightVerdict,
    journal: JournalWriter,
) -> DispatchOutcome | None:
    """Refuse one candidate before claim when a success-critical chain is gone.

    Returns `None` for a viable verdict, which is every verdict a repository
    with no fallback configuration can produce. The refusal names the verdict's
    own deterministic explanation rather than re-deriving one, so the journal
    line and the operator-visible detail cannot disagree.
    """
    if verdict.viable:
        return None
    outcome = DispatchOutcome(
        work_item_id=work_item_id,
        status="failed",
        stage=ACP_PREFLIGHT_REFUSAL_STAGE,
        pr_number=None,
        merge_sha=None,
        detail=f"acp preflight refusal: {verdict.detail}",
    )
    journal.append(
        record={
            "stage": ACP_PREFLIGHT_REFUSAL_STAGE,
            "work_item_id": work_item_id,
            "detail": verdict.detail,
            "success_critical": list(verdict.success_critical),
            "exhausted": list(verdict.exhausted),
            "unobservable_observations": len(verdict.unobservable),
        }
    )
    return outcome


def credential_reprobe_wait_applies(*, verdict: AcpPreflightVerdict) -> bool:
    """Whether the legacy credential re-probe wait may hold the loop.

    "The re-probe wait applies to a legacy single candidate and a genuinely
    exhausted fallback chain, never a primary-only probe refusal with a viable
    fallback." Both admitted cases are read straight off the verdict: a
    repository with no fallback configuration is the legacy single candidate,
    and a non-viable verdict is the genuinely exhausted chain. The forbidden
    case -- fallback enabled and still viable -- is the one remaining
    combination, so it needs no condition of its own.
    """
    return not verdict.fallback_enabled or not verdict.viable

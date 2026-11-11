"""The hold record for a recovery route that exhausted its recapture bound."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoveryHold

__all__: list[str] = ["recapture_exhausted_hold", "recapture_exhausted_refusal"]


def recapture_exhausted_hold(
    *,
    work_item_id: str,
    pull_request: int | None,
    head: str | None,
    preserved: tuple[str, str] | None,
) -> RecoveryHold:
    """Return the non-automatic route that preserves a bounded proof attempt."""
    return RecoveryHold(
        refusals=(
            recapture_exhausted_refusal(
                work_item_id=work_item_id,
                pull_request=pull_request,
                head=head,
                preserved=preserved,
            ),
        )
    )


def recapture_exhausted_refusal(
    *,
    work_item_id: str,
    pull_request: int | None,
    head: str | None,
    preserved: tuple[str, str] | None,
) -> str:
    """Render the explicit, proof-rider route for a bounded recapture hold."""
    if pull_request is not None and head is not None:
        implementation = f"implementation preserved on #{pull_request} at {head}"
    elif preserved is not None:
        implementation = f"implementation preserved on {preserved[0]} at {preserved[1]}"
    else:
        implementation = "no preserved implementation observed"
    return (
        f"recapture-exhausted: {implementation} ; resume --item {work_item_id} at"
        " proof_capture with a proof rider"
    )

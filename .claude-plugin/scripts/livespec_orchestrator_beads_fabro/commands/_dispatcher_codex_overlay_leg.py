"""The Codex credential one dispatch projects, and the bound it is projected under.

Split from `_dispatcher_credentials` by cohesion. That module assembles every
projection input the overlay renderer takes; these four steps are ONE question
asked in sequence and answered as a unit -- how long this dispatch may run, what
the host's Codex credential looks like graded against that budget, the three
enforcement inputs the sandbox's credential-use guard needs, and whether the
selected graph's launches actually reach that guard.

The ORDER inside this leg is load-bearing and is why it travels together. The
requirement sizes the grade, the grade produces the snapshot the enforcement
inputs are stamped from, and the route check runs LAST among them -- but still
before the caller mints anything -- because protection is owed from the moment a
credential exists and a refusal after a mint would leave a live provider
credential behind.

It renews NOTHING. The bounded in-place renewal belongs to the pre-claim gate,
which has already run for the item by the time this leg is reached; a renewal
here could only extend a credential whose shortfall can no longer be reported
before a claim.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth import (
    CodexProjectionRefusal,
    project_host_codex_auth,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_requirement import (
    REVIEW_FIX_VISIT_CAP_INPUT,
    WorkflowFaultDeferral,
    credential_lifetime_requirement_for,
    requirement_refusal_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_projection import (
    CredentialUseProjection,
    credential_use_projection_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_routes import (
    selected_graph_launch_refusal,
)

__all__: list[str] = ["CodexOverlayLeg", "project_codex_overlay_leg"]


@dataclass(frozen=True, kw_only=True)
class CodexOverlayLeg:
    """The two projection inputs this leg resolves for the overlay renderer."""

    snapshot: str
    credential_use: CredentialUseProjection


def project_codex_overlay_leg(
    *,
    committed: Path,
    block: dict[str, Any],
    review_fix_visit_cap: int,
    graph_override: Path | None,
    adapter_inputs: frozenset[str],
    clock: Callable[[], int],
) -> CodexOverlayLeg | str:
    """Resolve this dispatch's Codex projection, or the FIRST refusal in the leg."""
    # The requirement for the workflow THIS dispatch resolved, derived from the
    # very file about to be overlaid and from the review-fix guard the plan
    # renders — not re-resolved from configuration, which would let the
    # projection size itself against a second read nothing can prove agrees with
    # the gate's.
    # The workflow is named by the DIRECTORY `workflow_toml` resolved rather than
    # by the registry name, which `RecordedDispatch` deliberately does not carry
    # down to the launch half. The name is a label on a diagnostic here — the
    # committed path below is what the figure is actually derived from — and the
    # directory is the more truthful label for "which workflow ran" anyway.
    requirement = credential_lifetime_requirement_for(
        committed=committed,
        block=block,
        workflow_name=committed.parent.name,
        policy_inputs={REVIEW_FIX_VISIT_CAP_INPUT: review_fix_visit_cap},
    )
    if isinstance(requirement, str | WorkflowFaultDeferral):
        return requirement_refusal_text(outcome=requirement)
    # Graded, never renewed. The bounded in-place renewal belongs to the
    # pre-claim gate, which has already run for this item; this surface is
    # downstream of the claim, so a renewal here could only extend a credential
    # whose shortfall can no longer be reported before one.
    codex_snapshot = project_host_codex_auth(
        clock=clock, run_budget_seconds=requirement.allowance_seconds
    )
    if isinstance(codex_snapshot, CodexProjectionRefusal):
        return codex_snapshot.message
    # The three enforcement inputs the sandbox needs, stamped ONCE from this
    # dispatch's own measurements: the absolute credential-use deadline (capped at the
    # observed expiry minus the documented margin), that observed expiry, and the
    # lifetime this dispatch requires. Composed in the projection module, which owns
    # what they mean; this leg owns only WHEN they are taken, which is here —
    # after the claim and before anything is written.
    credential_use = credential_use_projection_for(
        codex_snapshot=codex_snapshot,
        allowance_seconds=requirement.allowance_seconds,
        margin_seconds=requirement.margin_seconds,
        now_epoch=clock(),
    )
    # PROTECTION IS OWED FROM HERE, so the launches this workflow declares must be
    # ones the guard actually reaches. Wrapping the adapter inputs covers every launch
    # in the graphs this repository ships, but NOT every graph a dispatch could
    # select: a node declaring a literal `acp.command`, an `acp.config`, or a late
    # duplicate declaration overriding the command never consumes the wrapped input,
    # and a control measured exactly that running 1.003s past the deadline. Refused
    # BEFORE the proof-credential mint in the caller, so it leaves no live credential
    # behind.
    route_refusal = selected_graph_launch_refusal(
        committed=committed, graph_override=graph_override, adapter_inputs=adapter_inputs
    )
    if route_refusal is not None:
        return route_refusal
    return CodexOverlayLeg(snapshot=codex_snapshot, credential_use=credential_use)

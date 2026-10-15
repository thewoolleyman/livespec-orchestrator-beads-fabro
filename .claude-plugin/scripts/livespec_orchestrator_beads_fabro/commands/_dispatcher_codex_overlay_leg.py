"""WHAT one dispatch projects into its sandbox `$CODEX_HOME`, and under what bound.

Split from `_dispatcher_credentials` by cohesion. That module assembles every
projection input the overlay renderer takes; these four steps are ONE question
asked in sequence and answered as a unit -- how long this dispatch may run, what
the host's Codex credential looks like graded against that budget, the three
enforcement inputs the sandbox's credential-use guard needs, and whether the
selected graph's launches actually reach that guard.

THE TELEMETRY TABLE IS RESOLVED HERE TOO, beside the credential rather than back
in the materializer, and that is the repair of a measured defect rather than
tidiness. Both projections write into `$CODEX_HOME`, and the CREDENTIAL half is
the only one that declares that variable -- so the moment the credential became
conditional, a telemetry step rendered on its own scoping opened with
`mkdir -p "$CODEX_HOME"` against an unassigned variable, which runs as
`mkdir -p ""`, exits non-zero and ABORTS PREPARATION for every all-Claude
dispatch. Two projections into one directory, scoped by two decisions in two
modules, is the shape that produced it; one decision at one site is what keeps
them from diverging again.

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

WHICH DISPATCHES IT ASKS THAT QUESTION FOR, which is NOT all of them. A dispatch
routing no node to the `codex-acp` agent projects no Codex credential, so all
four steps above are about a credential that is not in the run: there is no
lifetime to size, nothing to grade, no observed expiry to stamp a deadline from,
and no credential whose use the graph's launches must reach a guard to bound.
Such a dispatch is passed over before ANY of them runs -- which is why the
`committed` file is never read on that path -- and the leg answers with the
host's explicit declaration that it projected nothing. It projects no telemetry
table either: that table is read by a Codex process, and such a dispatch
launches none.

SCOPING THE PRE-CLAIM GATE ALONE WOULD HAVE BEEN WORSE THAN DOING NOTHING, which
is why this leg is scoped by the SAME routing rather than left to that gate. The
gate sits BEFORE the claim precisely so an insufficient credential can be
reported while there is still nothing to strand; this leg sits after it. A build
that skipped the pre-claim grade for an all-Claude dispatch while this leg still
graded would therefore not have removed those refusals -- it would have MOVED
each one from the only position that can report it safely into the position that
leaves the row `active` with no factory run.
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_otel_config import (
    codex_otel_config_toml,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_routing import CodexRouting
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_requirement import (
    REVIEW_FIX_VISIT_CAP_INPUT,
    WorkflowFaultDeferral,
    credential_lifetime_requirement_for,
    requirement_refusal_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_projection import (
    CredentialUseDeclaration,
    UnprotectedCredentialUse,
    credential_use_projection_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_routes import (
    selected_graph_launch_refusal,
)

__all__: list[str] = ["CodexOverlayLeg", "project_codex_overlay_leg"]


@dataclass(frozen=True, kw_only=True)
class CodexOverlayLeg:
    """The three projection inputs this leg resolves for the overlay renderer.

    `snapshot` is None for a dispatch that routes no node to Codex, which is
    what renders no Codex auth into the sandbox at all. It is paired with an
    `UnprotectedCredentialUse` declaration rather than with None, because the
    overlay renderer treats a snapshot beside a non-projection as BROKEN
    protection and declines to render -- so the two carry the same routing in
    opposite spellings, and the two constructor sites below are what keep the
    other combination from arising (the field TYPES permit it).

    `otel_config` is None on that same path and for the same reason the snapshot
    is: the table it would carry is written into `$CODEX_HOME`, which only the
    credential projection declares, and it is read by a Codex process the
    dispatch does not launch. The three fields therefore move TOGETHER -- see the
    module docstring on the preparation abort that scoping them apart produced.
    """

    snapshot: str | None
    credential_use: CredentialUseDeclaration
    otel_config: str | None


def project_codex_overlay_leg(  # noqa: PLR0913 — kw-only projection leg; each is an independent input.
    *,
    committed: Path,
    block: dict[str, Any],
    review_fix_visit_cap: int,
    graph_override: Path | None,
    adapter_inputs: frozenset[str],
    clock: Callable[[], int],
    codex_routing: CodexRouting,
    sandbox_otel_endpoint: str,
    work_item_id: str,
    dispatch_id: str,
) -> CodexOverlayLeg | str:
    """Resolve this dispatch's Codex projection, or the FIRST refusal in the leg.

    `codex_routing` is this dispatch's RESOLVED routing and is REQUIRED rather
    than defaulted. The pre-claim gate takes the same answer as an optional
    thunk, because the drain reaches that gate on every idle pass and must not
    pay for a question it has already declined to ask; this leg is reached only
    for a dispatch that is going ahead, so there is nothing to defer — and a
    default here would be a silent one. A caller that forgot to wire a default
    would grade a credential no node will use and stamp a deadline nothing
    needs, which is the whole defect this parameter exists to retire, so the
    type system refusing the call is better than an arm nobody notices.

    `sandbox_otel_endpoint`, `work_item_id` and `dispatch_id` are the telemetry
    table's three inputs, forwarded rather than resolved here: the endpoint is
    the same host-receiver reading the Claude-Code OTel overlay is rendered
    from, and the correlation pair is what the caller was handed. A second
    resolution here could not be proven to agree with that one, and a dispatch
    whose two exports disagreed about either id would still produce two
    well-formed sets of spans.
    """
    # ROUTING DECIDES WHETHER THERE IS A CREDENTIAL TO PROJECT, and it is asked
    # FIRST — before the requirement, the grade, the stamp and the route check —
    # because every one of those is about a credential this dispatch does not
    # project. Answered with the host's explicit declaration rather than with
    # None: None is what a caller passes when it says nothing at all, and the
    # sandbox guard must keep refusing on silence, since silence is how a broken
    # projection looks. The declaration is the one statement that may disarm the
    # deadline, and `_acp_node_layers` plus `_dispatcher_credential_use_routes`
    # both refuse a launch that tries to make it for itself.
    if not codex_routing.routes_codex:
        return CodexOverlayLeg(
            snapshot=None, credential_use=UnprotectedCredentialUse(), otel_config=None
        )
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
    # Codex honors no `OTEL_*` variable, so the sandbox's Claude-Code OTel
    # overlay reaches Claude Code only. Codex resolves its exporters from
    # `$CODEX_HOME/config.toml` alone, and projecting that file is what makes
    # Codex spend telemetry exist at all (work-item bd-ib-dbzp). Rendered on
    # THIS arm, which is the arm that declares the `$CODEX_HOME` it is written
    # into.
    return CodexOverlayLeg(
        snapshot=codex_snapshot,
        credential_use=credential_use,
        otel_config=codex_otel_config_toml(
            endpoint=sandbox_otel_endpoint,
            work_item_id=work_item_id,
            dispatch_id=dispatch_id,
        ),
    )

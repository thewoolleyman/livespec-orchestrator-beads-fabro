"""The run-config overlay projection for one dispatch, as its own leg.

`_dispatcher_credentials.materialize_overlay` WRITES the mode-600 overlay; this
assembles the ~seventeen-argument call that tells it what one dispatch's run
config must declare. The seam is worth a module because every argument here is
already RESOLVED -- onto `DispatchPlan` by `_dispatcher_plan_build`, or onto
`RecordedDispatch` by `_dispatcher_loop_record` -- so nothing in this leg reads
configuration, resolves a factory, or re-measures a version. It projects
already-settled values, which is exactly the resolve-once-project-everywhere
discipline the integration contract states, and the per-argument comments
explaining WHY each one is read off the plan rather than re-derived are the
substance of the leg.

WHAT DELIBERATELY STAYED BEHIND, because this is the half most likely to be
"tidied" here later: the REFUSAL arm. `materialize_dispatch_overlay` returns the
error STRING and never a `DispatchOutcome`, so the
`failed_dispatch_outcome(stage="run-config-overlay")` return stays in
`_dispatch_one_locked` beside the other pre-launch refusals. That ordering is
load-bearing rather than stylistic -- `_dispatcher_proof_credential_lease`
carries the full reasoning: the credential revoke is the RUN's own teardown, so
a return added between the mint and the launch leaks a live provider credential
plus the overlay carrying its value. The sequence of returns in that window has
to stay readable in ONE function, so moving a refusal out of it is the one
change this split must not make.

WHY THIS LEG AND NOT THE LAUNCH LEG. `_dispatcher_loop` was brought to exactly
the 250-LLOC hard ceiling by collapsing two untouched `failed_dispatch_outcome`
calls onto one physical line each, recovering exactly the six lines the
admission-verdict threading cost. `file_lloc` counts PHYSICAL lines carrying
code tokens, so that recovered the COUNTER while leaving the file resting on
the ceiling -- the condition the ceiling exists to catch, reported as
compliant. Decomposition is what actually buys the headroom. The launch leg
(the watched run plus its dispositions) was the other candidate and is equally
cohesive, but `run_dispatch` is the injection seam THIRTY test files
monkeypatch on `_dispatcher_loop`; moving it would have retargeted roughly 141
patch sites to buy headroom this cut buys by moving two.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    contract_prompt_variables,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_record import RecordedDispatch
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_grade_program import (
    proof_grade_assertions_env_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    journaled_proof_rendering,
    publish_branch_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_metadata import (
    publication_metadata_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    resume_checkout_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_worktree_pack import (
    fleet_toolchain_is_the_sandbox_gate_premise,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import VaultSecretSink
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "DispatchOverlay",
    "materialize_dispatch_overlay",
]


@dataclass(frozen=True, kw_only=True)
class DispatchOverlay:
    """The already-resolved inputs one dispatch's overlay is projected from.

    A CARRIER rather than a parameter list, for the reason every other
    multi-input seam in this tree is one: each field is settled at a different
    point of one dispatch, so this leg can neither default nor re-derive any of
    them. `recorded` and `plan` travel as the WHOLE resolved values rather than
    as the handful of fields read off them, because the projection's own
    comments are about which resolution each value came from -- destructuring
    them at the call site would move that provenance away from the argument it
    explains.

    `secret_sink` is the sink the caller already built and already registered a
    release guard for; this leg stores through it and owns neither its lifetime
    nor its teardown.
    """

    args: argparse.Namespace
    repo: Path
    item: WorkItem
    journal: JournalFile
    recorded: RecordedDispatch
    overlay_file: Path
    dispatch_id: str
    # The App-token SUPPLIER, not a token value: an installation token outlives
    # neither the run nor the `pr` stage, so the overlay is handed something it
    # can re-ask rather than a string that has already begun expiring.
    token: Callable[[], str]
    secret_sink: VaultSecretSink


def materialize_dispatch_overlay(*, overlay: DispatchOverlay) -> str | None:
    """Project and write this dispatch's run-config overlay; return any error.

    Returns the error STRING rather than a `DispatchOutcome`, deliberately: the
    caller owns the refusal, for the pre-launch ordering reason this module's
    docstring gives.
    """
    plan = overlay.recorded.plan
    return materialize_overlay(
        committed=overlay.recorded.committed_workflow,
        overlay=overlay.overlay_file,
        repo=overlay.repo,
        work_item_id=overlay.item.id,
        dispatch_id=overlay.dispatch_id,
        token=overlay.token,
        # The review-fix guard THIS plan renders, so the overlay's credential
        # requirement is derived from the loop bound this dispatch actually runs
        # rather than from the committed default a bare `fabro run` would see.
        review_fix_visit_cap=plan.review_fix_visit_cap,
        graph_override=overlay.recorded.payload.graph,
        # The client build the record MEASURED for this plan's factory binary,
        # which decides how the written config may name that graph: a Petri-era
        # client collects the package the config sits in, and refuses an
        # absolute inline reference in it. Read off the plan rather than
        # re-measured, for the resolve-once reason the integration contract
        # gives — a second `--version` read cannot be proven to agree with the
        # one the dispatch record journaled, and the launch shape is chosen from
        # that same reading.
        fabro_version=plan.fabro_version,
        # The publish branch and head a RESUME puts the sandbox clone on, built
        # from the head the anchoring record names rather than from the branch
        # tip: a tip read at prepare time may have moved since the record was
        # published, which is the state the head-moved refusal exists to catch.
        resume_checkout=resume_checkout_for(
            args=overlay.args, branch=publish_branch_for(work_item_id=overlay.item.id)
        ),
        # The ONE contract the plan already resolved, projected once more: the
        # committed run config's prepare commands template these values as
        # `{{ inputs.* }}`, and the pinned engine renders that site for the
        # graph but not for `run.prepare`.
        prepare_inputs=contract_prompt_variables(resolved=plan.integration),
        # Whether the gitignored worktree-discipline pack is a premise of THIS
        # sandbox, read off the SAME resolved contract the inputs above are
        # projected from. The pack is this fleet's own dev-tooling artifact and
        # only this fleet's check suite reads it, so a repository that declared
        # its own sandbox gate is imposed no recipe it may not have.
        provision_worktree_pack=fleet_toolchain_is_the_sandbox_gate_premise(
            resolved=plan.integration
        ),
        git_author=overlay.recorded.git_author,
        # This repository's proof-asset rendering, as the pre-dispatch gate
        # MEASURED and journaled it. Read back from that record rather than
        # re-probed: the overlay is materialized on every dispatch, offline
        # included, so the measurement travels through the journal and the
        # projection stays pure (bd-ib-pa73qh).
        proof_rendering=journaled_proof_rendering(
            journal_path=overlay.journal.path, repository=overlay.repo.name
        ),
        # The adapter inputs this dispatch WRAPS, so the route check grades the
        # graph against what is actually guarded rather than against a convention.
        adapter_inputs=(
            frozenset() if plan.acp_nodes is None else frozenset(plan.acp_nodes.inputs.values())
        ),
        # WHICH factory this dispatch launches at, and that factory's own vault.
        # Both read off the plan's already-resolved target rather than from a
        # second configuration read, for the resolve-once reason the integration
        # contract gives: a credential stored in one server's vault while the run
        # launched against another's resolves to nothing.
        factory_name=plan.fabro_factory_name,
        secret_sink=overlay.secret_sink,
        # WHERE this dispatch's sandbox image comes from, read off the plan's
        # single resolution for the same resolve-once reason the integration
        # contract gives: the dispatch record already named that decision, so a
        # second read here could disagree with the record without either
        # surface showing it.
        sandbox_image=plan.sandbox_image,
        # The pull-request title and body the scripted `pr` stage applies. This
        # is the ONE call site that holds the work-item, which is why the
        # rendering happens here and travels down as a value: `pr` is a command
        # node, so it cannot read the rendered goal the retired `pr` prompt did,
        # and without this projection it falls back to the publish branch name
        # as its title and keeps `publish_draft`'s placeholder body.
        publication_metadata=publication_metadata_for(item=overlay.item),
        # The item's `factory_captured` assertions, for the sandbox's own
        # per-assertion grade of the verified record. Rendered HERE for the same
        # reason the publication metadata above is: this is the one call site
        # holding the work-item, `proof_grade` is a command node that cannot read
        # the rendered goal, and judging a record against the assertions the
        # RECORD happens to list is the fail-open this grade exists to close
        # (bd-ib-kcq6pu).
        proof_grade_env=proof_grade_assertions_env_lines(item=overlay.item),
    )

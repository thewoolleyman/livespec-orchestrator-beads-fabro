"""One dispatch's run-scoped credential projection: mint the lease, write the overlay.

Split out of `_dispatcher_loop` by COHESION. These two stages are one concern —
putting this dispatch's run-scoped credentials where the sandbox will read them —
and they are sequential rather than merely adjacent: the overlay is the channel
that carries a minted value in, so the mint has to resolve before the overlay is
rendered and the lease has to survive both. The caller's remaining job is the
dispatch pipeline's refusal sequencing, which is a different responsibility.

Both stages route an expected failure as DATA, through one `RunCredentialRefusal`
carrying the stage that earned it. That mirrors `MaterializationRefusal` beside
it rather than inventing a second convention, and it is what keeps the STAGE
NAMES with the code that can produce them: the caller journals whatever stage it
is handed instead of knowing which faults live here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    contract_prompt_variables,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_materialize import (
    MaterializedDispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credential_providers import (
    ProofCredentialLease,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credentials import (
    mint_declared_proof_credentials,
)

__all__: list[str] = [
    "RunCredentialRefusal",
    "project_run_credentials",
]


@dataclass(frozen=True, kw_only=True)
class RunCredentialRefusal:
    """A pre-run refusal from one of these two stages, carrying the stage it names.

    The stage rides on the value rather than being inferred by the caller,
    because both faults return the same TYPE and only the stage distinguishes
    them — a caller that guessed would journal a mint failure as an overlay one,
    which is precisely the mis-attribution the per-stage journal exists to
    prevent.
    """

    stage: str
    detail: str


def project_run_credentials(  # noqa: PLR0913 — kw-only projection seam; `repo`, `work_item_id`, `identity`, `overlay_file` and `token` are five independent per-dispatch facts, and `materialized`/`plan` are already the two aggregates that collapse the rest, so there is nothing left to group.
    *,
    repo: Path,
    work_item_id: str,
    identity: DispatchJournalIdentity,
    materialized: MaterializedDispatch,
    plan: DispatchPlan,
    overlay_file: Path,
    token: Callable[[], str],
) -> ProofCredentialLease | RunCredentialRefusal:
    """Mint this dispatch's proof-credential lease, then write the run-config overlay.

    Returns the LEASE on success, because that is the one thing the caller still
    needs afterwards: it rides into the run so the teardown can revoke it when
    the run returns. The overlay itself is a file on disk and needs no handle.

    THE MINT RUNS FIRST AND REFUSES THE DISPATCH, rather than letting the overlay
    fall back to the host's own copy of a provider-backed credential. That
    fallback is the tempting shape and it is the wrong one: it would silently undo
    the proof-credential-projection clause's minting requirement for exactly the
    declarations it governs, and the dispatch would look perfectly healthy while a
    long-lived credential sat in the sandbox.

    `materialized` and `plan` are passed as the ALREADY-RESOLVED values the caller
    holds rather than as their individual fields, which keeps this seam's coupling
    to two objects the pipeline has anyway. The integration contract in particular
    is resolved ONCE, in the plan build, and projected from there — a second
    resolution here could not be proven to agree with the first, and the
    disagreement would be invisible because both produce a well-formed contract.
    """
    lease = mint_declared_proof_credentials(repo=repo, dispatch_id=identity.dispatch_id)
    if isinstance(lease, str):
        return RunCredentialRefusal(stage="proof-credential-mint", detail=lease)
    overlay_error = materialize_overlay(
        committed=materialized.committed_workflow,
        overlay=overlay_file,
        repo=repo,
        work_item_id=work_item_id,
        dispatch_id=identity.dispatch_id,
        token=token,
        graph_override=materialized.payload.graph,
        # This dispatch's minted set, so a provider-backed declaration projects
        # the scoped credential issued for THIS run rather than the host's.
        proof_credential_lease=lease,
        # The ONE contract the plan already resolved, projected once more: the
        # committed run config's prepare commands template these values as
        # `{{ inputs.* }}`, and the pinned engine renders that site for the
        # graph but not for `run.prepare`.
        prepare_inputs=contract_prompt_variables(resolved=plan.integration),
        git_author=materialized.git_author,
    )
    if overlay_error is not None:
        return RunCredentialRefusal(stage="run-config-overlay", detail=overlay_error)
    return lease

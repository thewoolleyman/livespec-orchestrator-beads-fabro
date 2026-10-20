"""The release outcome one terminated run yields, read off its own records.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Provider-limit release and re-dispatch" (`bd-ib-6itdjz`,
Scenario 127). `_dispatcher_provider_limit_classify` owns the DECISION and is
pure; this owns the READING that feeds it -- which attempt failed, which
entitlement ran it, and which signatures grade it -- plus the outcome the
terminal mapper returns. The split is the usual one in this tree: a decision
that reached for configuration itself could not be exercised without a
repository on disk.

WHICH ATTEMPT. The clause requires "the unrecovered failure responsible for
the run's terminal disposition", and `terminal_evidence` already answers that
from the run's own terminal checkpoint: `current_predecessor` is the last
failed non-terminal node in the engine's completed order. An earlier attempt
that later SUCCEEDED is not in `failed_stages`, so the clause's "MUST NOT
release a successful run or override a subsequent unrelated failure" holds
because of what that reading returns rather than because of a rule here.

WHICH ENTITLEMENT, AND WHY IT COMES OFF THE PLAN. `AcpNodeResolution.
candidates` is the identity this dispatch SELECTED per node, and it is the
very value `_dispatcher_run_labels` stamped the run's
`livespec.acp.<node>.availability` and `.candidate` labels from. So reading it
here and reading the run's labels are the same answer from one source, and the
release cannot name an entitlement the factory's own records contradict. The
alternative -- re-reading today's configuration for the identity -- would
answer about the chain as it stands now rather than as the dispatch resolved
it, which diverges silently whenever configuration moved mid-run.

WHICH SIGNATURES, AND WHY THOSE DO COME FROM CONFIGURATION. The plan carries
identities, not signature tables, so the grading metadata is resolved through
`resolve_dispatch_candidates` -- the same resolution admission takes -- and
matched to the selected identity by its entitlement PAIR. That resolution also
supplies the `builtin` provenance flag, which `effective_signatures` requires
and refuses to derive from a key's spelling: a repository is free to name its
own `availability_key` "codex" for an adapter this build never rendered, and
lending it the measured Codex table would classify its failures against
diagnostics its adapter never emits.

AN UNREADABLE RESOLUTION RELEASES NOTHING, and that is the fail-closed
direction rather than an oversight. `resolve_dispatch_candidates` answers
`None` for a resolution it could not READ -- deliberately not the empty tuple
-- and a mapper that released there would release on every repository whose
adapters it never observed, leaving a record that reads exactly like a healthy
release. The same reasoning as `covering_provider_exhaustion`'s own blinded
arm, pointed the other way: there the unreadable arm must refuse, here it must
decline to release.

THE READ IS SPENT ONLY ON A FAILING TERMINAL. Every arm that can answer
without touching configuration does so first -- no inspect payload, no
recorded failure, no failing node, no selected identity -- so a green run and
an ordinary failure pay nothing, and the configuration read happens only where
a release is genuinely possible.

THE RECOVERY SOURCE IS THE TERMINAL'S OWN THREE-WAY STATEMENT. The clause asks
for "the preserved-work reference the release observed (the published head or
preservation ref) or its confirmed absence", and
`needs_human_terminal_preservation` is already exactly that invariant: a
positive sentinel names the ref, an explicit negative sentinel says the push
failed, and the absence of both says UNKNOWN. Re-deriving a ref from the run
id instead would be this module's guess about what another component did.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidateIdentity
from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import RenderedCandidate
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    resolve_dispatch_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import tail
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_failure import (
    fabro_failure_outcome_detail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_detail import (
    needs_human_terminal_preservation,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify import (
    ProviderLimitRelease,
    classified_release,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_records import (
    PROVIDER_LIMIT_RELEASE_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_events import (
    terminal_event_output,
)
from livespec_orchestrator_beads_fabro.commands._fabro_executed_candidate import graph_node_id
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence import terminal_evidence

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        DispatchOutcome,
    )

__all__: list[str] = [
    "PROVIDER_LIMIT_RELEASE_STATUS",
    "provider_limit_release_outcome",
]

# The outcome STATUS a provider-limit release reports. Its own status rather
# than `failed` or `blocked`, and that choice is load-bearing on three
# surfaces: `escalate_needs_human_block` fires on `blocked` and would park the
# very item this clause releases; `is_non_convergence_outcome` fires on
# `failed` and would bounce the slice to `backlog`; and the acceptance valve
# fires on `green`. The clause forbids all three -- a release "MUST NOT consume
# any budget of the three rework caps" and "MUST NOT be surfaced as a
# needs-human decision" -- so none of those predicates may match, which is a
# property of the status rather than of a guard added to each of them.
# It mirrors `provider-exhaustion` next door, where the status and the stage
# are likewise one name.
PROVIDER_LIMIT_RELEASE_STATUS = PROVIDER_LIMIT_RELEASE_STAGE


def _provider_limit_release(
    *,
    plan: DispatchPlan,
    inspect: FabroInspectResult | None,
    run_id: str | None,
    text: str,
) -> ProviderLimitRelease | None:
    """The release this terminated run owes, or `None` for an unchanged route."""
    if inspect is None:
        return None
    failure = inspect.failure
    if failure is None:
        return None
    node = _failing_node(inspect=inspect)
    if node is None:
        return None
    identity = _selected_identity(plan=plan, node=node)
    return classified_release(
        failure=failure,
        rendered=_rendered_for(repo=plan.repo, identity=identity),
        node_attempt=node,
        factory=plan.fabro_factory_name,
        run_id=run_id,
        recovery_source=needs_human_terminal_preservation(text=text),
    )


def _provider_limit_release_detail(
    *, release: ProviderLimitRelease, recorded_cause: str | None
) -> str:
    """The operator-facing line a released terminal reports.

    It states that NO human decision is owed, because that is the question a
    triager arrives with: this ending looks like the `blocked / needs-human`
    rest it replaces, and an operator who reads it as a gate goes hunting for
    a question no agent asked.

    THE PROVIDER'S OWN SENTENCE IS QUOTED, not merely the classified cause, and
    the two are not redundant: the classified cause says WHICH RULE fired while
    the recorded diagnostic says what the provider actually refused with and
    when it resets. It is also what renders a ceiling AS a ceiling rather than
    as a transport fault -- the carrier worked and the model declined, one
    label and one remedy each -- which
    `test_dispatcher_needs_human_provider_limit` has asserted since v107 and
    which this release path inherits rather than retires.
    """
    matched = release.matched
    cause = release.legacy_provider if matched is None else matched.cause
    scope = "legacy-provider" if matched is None else matched.scope
    return (
        f"run {release.run_id} on factory {release.factory} failed at stage "
        f"{release.node_attempt} on a provider availability limit "
        f"(cause={cause} scope={scope}): {recorded_cause}; the item was "
        "released to `ready` for the ordinary admission valve to re-dispatch, "
        "no rework-cap budget was consumed, and NO human decision is owed. "
        f"Preserved work: {release.recovery_source}"
    )


def _failing_node(*, inspect: FabroInspectResult) -> str | None:
    """The graph node id of the attempt responsible for the terminal.

    Normalized through `graph_node_id` because the two engines spell the key
    differently -- the pinned engine keys its outcome map `implement`, the
    Petri-era engine keys its stage map `002-implement@1` -- while the
    selected-identity map is keyed on the graph node id alone.
    """
    evidence = terminal_evidence(payload=inspect.payload)
    if evidence is None or evidence.current_predecessor is None:
        return None
    return graph_node_id(node=evidence.current_predecessor) or None


def _selected_identity(*, plan: DispatchPlan, node: str) -> AcpCandidateIdentity | None:
    """The entitlement this dispatch selected for one node, or `None`.

    ``acp_nodes`` is optional plan metadata.  Older proof and recovery callers
    that supply the terminal's minimal plan shape therefore have no selected
    identity, rather than losing the terminal cause while this optional lookup
    raises before the ordinary provider-limit classifier can run.
    """
    resolution = getattr(plan, "acp_nodes", None)
    if resolution is None:
        return None
    return resolution.candidates.get(node)


def _rendered_for(*, repo: Path, identity: AcpCandidateIdentity | None) -> RenderedCandidate | None:
    """The resolved candidate carrying that identity's signatures and provenance.

    `None` whenever the question cannot be answered -- no identity was
    selected, the resolution could not be read, or no resolved candidate
    carries that entitlement pair -- because each of them leaves the caller
    with no signature table to grade against and none of them is evidence
    about a provider.
    """
    if identity is None:
        return None
    rendered = resolve_dispatch_candidates(repo=repo)
    if rendered is None:
        return None
    for entry in rendered:
        candidate_identity = entry.candidate.identity
        if candidate_identity is not None and candidate_identity.pair == identity.pair:
            return entry
    return None


def provider_limit_release_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    inspect: FabroInspectResult | None,
    stderr: str,
) -> DispatchOutcome | None:
    """Map an eligible provider-limit terminal onto the RELEASE outcome.

    The structured failure fields are carried exactly as the two mappings
    below carry them, and the two PROVIDER fields are load-bearing rather than
    decorative: `record_provider_exhaustion_if_observed` keys on
    `provider_usage_limit_provider` alone, so a usage-limit release that
    dropped it would write no legacy provider observation and the next
    dispatch would burn the same exhausted credential.

    They are carried AS OBSERVED and never set because a release happened,
    which is the contract's own rule: the typed provider-usage-limit flag
    "remains specific to usage or spend ceilings and MUST NOT be set merely
    because another eligible availability cause triggers release". So a
    candidate-scoped `model_unsupported` release leaves the flag false, and
    does so because nothing here writes it rather than because a branch
    excludes it.

    The recovery source is read on ALL THREE channels the needs-human mapping
    reads, and none of them is optional. The terminal's stage event carries its
    emitted output on the Petri-era engine; the raw `fabro run` stderr carries
    it on the pinned engine; and the structured failure detail carries it when
    the engine lifted the node's stderr into `conclusion.failure.detail`. A
    reader aimed at fewer of them returns a clean "preservation UNKNOWN" for a
    tree the terminal demonstrably preserved -- measured here on the Petri-era
    fixture, where the sentinel lives only in the structured detail.
    """
    failure = None if inspect is None else inspect.failure
    failure_detail = fabro_failure_outcome_detail(failure=failure, fallback=tail(text=stderr))
    emitted = terminal_event_output(payload=None if inspect is None else inspect.events_payload)
    release = _provider_limit_release(
        plan=plan,
        inspect=inspect,
        run_id=run_id,
        text=f"{emitted}\n{stderr}\n{failure_detail}",
    )
    if release is None:
        return None
    return outcome_type(
        work_item_id=plan.work_item_id,
        status=PROVIDER_LIMIT_RELEASE_STATUS,
        stage=PROVIDER_LIMIT_RELEASE_STAGE,
        pr_number=None,
        merge_sha=None,
        detail=_provider_limit_release_detail(
            release=release, recorded_cause=None if failure is None else failure.cause
        ),
        fabro_run_id=run_id,
        fabro_failure_cause=None if failure is None else failure.cause,
        fabro_failure_category=None if failure is None else failure.category,
        fabro_failure_signature=None if failure is None else failure.signature,
        provider_usage_limit=False if failure is None else failure.provider_usage_limit,
        provider_usage_limit_provider=(
            None if failure is None else failure.provider_usage_limit_provider
        ),
        provider_limit_release=release,
    )

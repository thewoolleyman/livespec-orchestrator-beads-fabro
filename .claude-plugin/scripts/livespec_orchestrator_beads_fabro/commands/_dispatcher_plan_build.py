"""DispatchPlan dataclass and per-item plan construction.

PLAN BUILD IS WHERE THE REPOSITORY INTEGRATION CONTRACT IS RESOLVED, EXACTLY
ONCE. `SPECIFICATION/contracts.md`'s resolve-once-project-everywhere clause puts
the single resolution here, on the host, and requires every seam downstream --
the host janitor argv, the `fabro run` inputs, the prompt variables, the
prepare-step parameters, the janitor venue's default branch -- to be a
PROJECTION of the frozen object this module hangs on the plan. Nothing after
this point re-reads `.livespec.jsonc` or re-probes the default branch, because
re-deriving at a later point is how the journaled dispatch record and the run
come to disagree -- the same reasoning that already put the resolved ACP
adapters on the plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_node_layers import AcpNodeResolution
from livespec_orchestrator_beads_fabro.commands._dispatcher_check_suite_view import (
    janitor_check_suite_from_contract,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_core_provisioning_view import (
    janitor_core_provisioning_from_contract,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import (
    janitor_argv,
    janitor_core_checkout_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_contract import (
    ResolvedIntegrationContract,
    resolve_integration_contract,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_declaration import (
    declaration_from_config_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    contract_run_inputs,
    contract_workflow_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_schema import (
    DEFAULT_BRANCH_KEY,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_output_retention import (
    JanitorRetention,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
    review_fix_visit_cap_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_MERGE_ON_REVIEW_CAP,
    DEFAULT_REVIEW_FIX_CAP,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    DEFAULT_FABRO_TIMEOUT_SECONDS,
)

__all__: list[str] = [
    "UNDECLARED_INTEGRATION_CONTRACT",
    "DispatchPlan",
    "build_plan",
    "resolve_repo_integration_contract",
]

_MERGE_ON_REVIEW_CAP_DISABLED_OUTCOME = "__merge_on_review_cap_disabled__"


def resolve_repo_integration_contract(
    *, config_text: str, default_branch: str | None
) -> ResolvedIntegrationContract:
    """Resolve one governed repository's WHOLE contract from its two declaration sources.

    The committed `.livespec.jsonc` answers every key an adopter writes; the
    repository's own git/forge state answers the default branch, which is why
    the probed value is spliced into the declaration under the schema's
    deliberately-uncommitted `default_branch` path rather than resolved beside
    it. A probe that stayed silent contributes NO key, so the required field
    earns the same absent-key refusal every other unresolvable point does
    instead of a local `is None` convention of its own.
    """
    declaration = dict(declaration_from_config_text(config_text=config_text))
    if default_branch is not None:
        declaration[DEFAULT_BRANCH_KEY] = default_branch
    return resolve_integration_contract(declaration=declaration)


# What a plan built with NO declaration carries: the contract a repository that
# declares nothing resolves to. It is the fail-closed answer rather than a
# convenience -- `compat.pinned` and the default branch are REQUIRED fields, so
# this object is defective on both and every seam reading it degrades naming the
# missing declaration instead of provisioning from a value nobody wrote.
UNDECLARED_INTEGRATION_CONTRACT = resolve_repo_integration_contract(
    config_text="", default_branch=None
)


@dataclass(frozen=True, kw_only=True)
class DispatchPlan:
    """Everything one work-item dispatch needs, resolved up front.

    `branch` is the PUBLISH branch (`feat/<work-item-id>`) the phase
    graph's pr stage pushes and the engine polls — the Fabro-managed
    run branch inside the sandbox is run-internal and never leaves it.
    `workflow_toml` is the MATERIALIZED run-config overlay path (the
    committed config plus the credential env table), not the committed
    file itself. `janitor_checkout` is the path the engine provisions
    as a FRESH detached worktree of the merged ref and runs the
    post-merge janitor in — never the host primary's working tree,
    whose environment rot (stale `.venv` shebangs, stale `.coverage`,
    ghost `__pycache__` dirs) once false-redded a confirmed-green
    merge (work-item livespec-impl-beads-cgd).
    """

    repo: Path
    work_item_id: str
    branch: str
    workflow_toml: Path
    goal_file: Path
    fabro_bin: str
    fabro_factory_name: str
    fabro_factory_server: str | None
    fabro_factory_dev_token: str | None
    janitor: tuple[str, ...]
    janitor_checkout: Path
    janitor_core_checkout: Path
    janitor_core_repo_url: str
    janitor_core_ref: str
    review_fix_visit_cap: int
    merge_on_review_cap_outcome: str
    # This item's effective merge hold — the per-item hold `contracts.md`
    # ratifies — resolved host-side HERE, at
    # plan-build time, and journaled with the dispatch record. It rides the plan
    # for the reason the ACP adapters and the integration contract do: TWO seams
    # read it -- the `merge_hold` workflow input the sandbox's pr stage reads,
    # and this host's own auto-merge argv -- and a value re-derived at either
    # point is how the record and the run come to disagree. Neither seam is
    # authoritative, so a hold reaching only one of them would not hold.
    merge_hold: bool = False
    # Every ACP node's adapter, already resolved through the workflow /
    # repository / per-dispatch layers (`_acp_node_layers`). It rides the
    # plan rather than being re-resolved at launch because BOTH launchers
    # render the `--input` pairs from it, and because the resolution is
    # what the dispatch record already journaled -- re-deriving it at
    # launch is how the record and the run come to disagree.
    #
    # None is NOT a provider fallback: it means this plan carried no
    # resolution, so the dispatch passes NO adapter `--input` at all and
    # the workflow's own declared defaults stand. That is layer 1 doing
    # its job through fabro rather than through us, which is why no
    # adapter string survives anywhere in this package as a literal.
    acp_nodes: AcpNodeResolution | None = None
    # The repository integration contract, resolved ONCE for this dispatch and
    # journaled with the dispatch record. Every seam that needs an integration
    # value projects it off this object; none of them resolves one of its own.
    integration: ResolvedIntegrationContract = UNDECLARED_INTEGRATION_CONTRACT
    # The `--input name=value` pairs the resolved contract projects into this
    # dispatch's `fabro run`, already INTERSECTED with the input names the
    # dispatched workflow declares -- fabro rejects an input a workflow does not
    # declare, so the intersection is taken here, once, beside the resolution
    # that produced the values.
    integration_inputs: tuple[str, ...] = ()
    # The `fabro run` subprocess ceiling, DERIVED from this dispatch's
    # resolved node timeouts and stall timeout rather than fixed by a
    # constant — so lengthening a node cannot outrun the poller and
    # shortening one is not masked. Both launchers read it from here, which
    # is what keeps the watched and synchronous paths on one number.
    fabro_timeout_seconds: float = DEFAULT_FABRO_TIMEOUT_SECONDS
    # WHERE this invocation retains a FAILED post-merge janitor command's
    # complete captured output, and under which identity. It rides the plan
    # because the venue is per-INVOCATION state resolved up front -- the
    # dispatch id, or the reconcile-merged valve's own journaled identifier --
    # while the stages that consume it sit two call layers down inside the
    # post-merge flow, which has no other access to either.
    #
    # None is not "retention off by default": it is an invocation that minted
    # no identity, whose janitor rows then carry their bounded excerpt alone.
    janitor_retention: JanitorRetention | None = None


def build_plan(  # noqa: PLR0913 — kw-only plan resolver; each field is an independent caller input.
    *,
    repo: Path,
    work_item_id: str,
    workflow_toml: Path,
    goal_file: Path,
    fabro_bin: str,
    fabro_factory_name: str = "default",
    fabro_factory_server: str | None = None,
    fabro_factory_dev_token: str | None = None,
    janitor: tuple[str, ...] | None,
    janitor_checkout: Path,
    # The two declaration sources the contract resolves from. `config_text` is
    # the target's committed `.livespec.jsonc`; `default_branch` is what the
    # ratified two-route probe answered about the repository's own state, or
    # None where both routes were silent.
    config_text: str = "",
    default_branch: str | None = None,
    # The dispatched workflow's committed run config, read ONLY for which input
    # names it declares -- never for an integration VALUE, which comes from the
    # contract.
    committed_workflow_text: str = "",
    review_fix_cap: int = DEFAULT_REVIEW_FIX_CAP,
    merge_on_review_cap: bool = DEFAULT_MERGE_ON_REVIEW_CAP,
    # The hold has NO repository-level default, so there is no setting to fall
    # through to: False is the absence of a hold, not a configured value.
    merge_hold: bool = False,
    fabro_timeout_seconds: float = DEFAULT_FABRO_TIMEOUT_SECONDS,
    acp_nodes: AcpNodeResolution | None = None,
) -> DispatchPlan:
    """Resolve the per-item dispatch plan (publish branch, argv config, contract)."""
    integration = resolve_repo_integration_contract(
        config_text=config_text, default_branch=default_branch
    )
    core = janitor_core_provisioning_from_contract(resolved=integration)
    return DispatchPlan(
        repo=repo,
        work_item_id=work_item_id,
        branch=f"feat/{work_item_id}",
        workflow_toml=workflow_toml,
        goal_file=goal_file,
        fabro_bin=fabro_bin,
        fabro_factory_name=fabro_factory_name,
        fabro_factory_server=fabro_factory_server,
        fabro_factory_dev_token=fabro_factory_dev_token,
        janitor=janitor_argv(
            check_suite=janitor_check_suite_from_contract(resolved=integration, janitor=janitor)
        ),
        janitor_checkout=janitor_checkout,
        janitor_core_checkout=janitor_core_checkout_path(janitor_checkout=janitor_checkout),
        # The clone repository has a fleet default because an ABSENT `core_repo`
        # declaration is a complete answer; the REF has none, so an unresolved
        # pin lands here as the sentinel and the post-merge provisioning
        # degrades naming the key rather than cloning a moving branch tip.
        janitor_core_repo_url=core.repo_url,
        janitor_core_ref=core.ref,
        review_fix_visit_cap=review_fix_visit_cap_for(review_fix_cap=review_fix_cap),
        merge_on_review_cap_outcome=(
            "succeeded" if merge_on_review_cap else _MERGE_ON_REVIEW_CAP_DISABLED_OUTCOME
        ),
        merge_hold=merge_hold,
        fabro_timeout_seconds=fabro_timeout_seconds,
        acp_nodes=acp_nodes,
        integration=integration,
        integration_inputs=contract_run_inputs(
            resolved=integration,
            declared=contract_workflow_inputs(committed_text=committed_workflow_text),
        ),
    )

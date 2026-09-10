"""Materialize WHAT one dispatch will run, before any Fabro run exists.

Split out of `_dispatcher_loop` by cohesion. Three questions share one
answer here and nowhere else: WHICH named workflow variant this dispatch
runs, which committed workflow config that variant resolves to, and what
that workflow resolves to once this target's configuration is applied to it
-- the graph with its node timeouts written in as literal durations, and
every ACP node's adapter resolved through the three configuration layers.
`_dispatcher_loop` is left with the other concern, driving the dispatch and
routing each pre-run refusal.

EVERY STEP REFUSES BEFORE ANY RUN EXISTS, which is why they belong
together. A registry naming a variant that is not there, a non-positive
timeout, and a node named in `dispatcher.acp_nodes` that the workflow does
not declare are the same KIND of fault -- a config typo whose only honest
discovery point is the dispatch that would otherwise have gone out carrying
a value nobody chose. Each refusal keeps its own journal stage, so the
record still says which step failed.

THE ORDER IS LOAD-BEARING. The variant resolves FIRST because everything
after it reads the directory it chose: the payload copy, the node-timeout
render and the ACP adapter layers all run against the SELECTED variant, so
a registered variant is held to exactly the parity the reserved workflow is
rather than being validated against the bundle it is not running.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_node_layers import AcpNodeResolution
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import (
    ACP_NODES_STAGE,
    prepare_acp_nodes,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import (
    GitAuthor,
    read_dispatch_git_author,
    workflow_git_author_error,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_draft import (
    approved_groom_draft_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_plan import (
    workflow_payload_dir,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config, workflow_toml
from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
    WorkflowPayload,
    prepare_workflow_payload,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_variant import (
    WorkflowVariantRefusal,
    prepare_workflow_variant,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    WorkItemNotFoundError,
)

__all__: list[str] = [
    "MaterializationRefusal",
    "MaterializedDispatch",
    "approved_groom_draft_pin",
    "materialize_dispatch",
]

_LEDGER_ERRORS = (
    WorkItemNotFoundError,
    ConnectionPrefixMissingError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

_WORKFLOW_PAYLOAD_STAGE = "workflow-payload"
_GIT_AUTHOR_STAGE = "git-author"


@dataclass(frozen=True, kw_only=True)
class MaterializedDispatch:
    """Everything one dispatch runs, resolved from the committed workflow."""

    committed_workflow: Path
    workflow_name: str
    payload: WorkflowPayload
    acp_nodes: AcpNodeResolution
    git_author: GitAuthor


@dataclass(frozen=True, kw_only=True)
class MaterializationRefusal:
    """A pre-run refusal, carrying the journal stage that produced it."""

    stage: str
    detail: str


def materialize_dispatch(
    *,
    args: argparse.Namespace,
    repo: Path,
    work_item_id: str,
    journal: JournalWriter,
) -> MaterializedDispatch | MaterializationRefusal:
    """Resolve this dispatch's workflow variant, payload and ACP adapters, or refuse."""
    # WHICH named workflow this dispatch runs, before WHERE its config file
    # is: the dispatch target may register variants under
    # `dispatcher.workflows`, and a registry this Dispatcher cannot honour
    # refuses here rather than quietly running the reserved graph under the
    # selected variant's name. Every step below keys on the directory that
    # resolves — the payload copy, the graph render and the ACP adapter
    # layers all read the SELECTED variant, never the bundle.
    #
    # `workflow_name` is read defensively for the reason `acp_node` below is:
    # only the dispatching subparsers define the argument, and the two
    # dispatch command paths overwrite it with the LEDGER-PINNED name before
    # reaching here, so a retry selects what the first attempt ran.
    variant = prepare_workflow_variant(
        repo=repo,
        name=getattr(args, "workflow_name", None),
        approved_groom_draft=approved_groom_draft_pin(repo=repo, work_item_id=work_item_id),
    )
    if isinstance(variant, WorkflowVariantRefusal):
        return MaterializationRefusal(stage=variant.stage, detail=variant.detail)
    # Resolved once and journaled: `workflow_toml` picks the selected
    # variant's directory, else the dispatch target's OWN committed workflow
    # over the plugin's bundled default, and that config carries the sandbox
    # image pin — so which file won is the first thing to read when a
    # dispatch dies on a missing toolchain. The payload materializer then
    # renders THIS dispatch's resolved node timeouts into a per-run copy of
    # that workflow's graph as literal durations; a config typo refuses here,
    # before any Fabro run exists.
    committed_workflow = workflow_toml(args=args, variant_directory=variant.directory)
    author_policy = read_dispatch_git_author(repo=repo)
    if isinstance(author_policy, str):
        return MaterializationRefusal(stage=_GIT_AUTHOR_STAGE, detail=author_policy)
    committed_text = attempt(
        action=lambda: committed_workflow.read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    if not isinstance(committed_text, AttemptFailure):
        author_error = workflow_git_author_error(
            committed_text=committed_text,
            author=author_policy.operator,
        )
        if author_error is not None:
            return MaterializationRefusal(stage=_GIT_AUTHOR_STAGE, detail=author_error)
    payload = prepare_workflow_payload(
        repo=repo,
        committed=committed_workflow,
        payload_dir=workflow_payload_dir(work_item_id=work_item_id),
        journal=journal,
        work_item_id=work_item_id,
    )
    if isinstance(payload, str):
        return MaterializationRefusal(stage=_WORKFLOW_PAYLOAD_STAGE, detail=payload)
    # Every ACP node's adapter, resolved through the workflow's own declared
    # defaults, the target's `dispatcher.acp_nodes` / `codex_models` block and
    # this dispatch's `--acp-node` arguments, then journaled with the layer
    # behind each field. A node named in configuration but absent from the
    # workflow refuses HERE, before any Fabro run exists — the alternative is
    # a run that silently carries the default the operator meant to replace.
    #
    # `acp_node` is read defensively: only the dispatching subparsers define
    # it, and the reconcile and check subcommands reach this code with a
    # Namespace that never carried the argument.
    acp_nodes = prepare_acp_nodes(
        repo=repo,
        committed=committed_workflow,
        overrides=tuple(getattr(args, "acp_node", None) or ()),
        journal=journal,
        work_item_id=work_item_id,
    )
    if isinstance(acp_nodes, str):
        return MaterializationRefusal(stage=ACP_NODES_STAGE, detail=acp_nodes)
    return MaterializedDispatch(
        committed_workflow=committed_workflow,
        workflow_name=variant.name,
        payload=payload,
        acp_nodes=acp_nodes,
        git_author=author_policy.operator,
    )


def approved_groom_draft_pin(*, repo: Path, work_item_id: str) -> str | None:
    """The variant that drafted this item's approved cut, if it carries one.

    Fail-soft, and the reason it is SAFE to be fail-soft here is a property of
    the sequence rather than of this function: an unreadable ledger yields None,
    the apply gate is not armed, and the dispatch proceeds -- to
    `_dispatcher_loop`'s own `read_dispatch_comments` step a few lines later,
    which reads the SAME comments and refuses the dispatch under the
    `ledger-comments` stage when it cannot. So no run is ever launched on a
    ledger this could not read; what a raise here would cost instead is the
    refusal's own stage, replaced by an exception on the dispatch path.
    """
    read = attempt(
        action=lambda: approved_groom_draft_for(
            path=store_config(repo=repo), work_item_id=work_item_id
        ),
        exceptions=_LEDGER_ERRORS,
    )
    return None if isinstance(read, AttemptFailure) else read

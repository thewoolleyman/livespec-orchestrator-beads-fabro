"""Dispatcher workflow-variant ledger pinning.

The peer of `_dispatcher_factory_ledger`, and deliberately the same shape: a
per-dispatch choice resolves most-specific-first, and the resolved answer is
written back onto the work-item so the NEXT attempt at the same item makes the
same choice. `SPECIFICATION/contracts.md` section "Named workflow variants"
sets the order -- an explicit `--workflow-name` argument, then the name a
prior dispatch of this item recorded in its `dispatch_workflow` metadata
provided that name is still registered or reserved, then
`dispatcher.default_workflow`, then the reserved `implement-work-item`.

WHY A RETRY MUST REUSE THE RECORDED NAME. Without the pin, a target that
changed `dispatcher.default_workflow` between attempts would move a
half-finished item onto a different graph mid-flight, with the item's own
record saying nothing about it. Pinning makes the second attempt re-run what
the first one ran; a name that has since left the registry is the one case
where that is impossible, and it falls through to the default rather than
refusing, exactly as `_dispatcher_factory_ledger` does for a renamed-away
factory.

WHY THERE IS NO ENVIRONMENT LAYER, where the factory ledger has one. The
selector is a recorded ARGUMENT by contract: an ad-hoc shell MUST NOT be able
to change which graph the factory runs with nothing in the committed record or
the journal to show for it. `_explicit_workflow_name` therefore reads the
Namespace and nothing else.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_dispatch_workflow import (
    dispatch_workflow_for,
    record_dispatch_workflow,
)
from livespec_orchestrator_beads_fabro.commands._config import (
    dispatcher_block,
    resolve_workflow_variant,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._workflow_variants import (
    RESERVED_WORKFLOW_NAME,
    WorkflowVariant,
    workflow_registry,
)

__all__: list[str] = [
    "args_with_dispatch_workflow_name",
    "previewed_workflow_variant",
    "resolve_dispatch_workflow_name",
]


def previewed_workflow_variant(
    *,
    repo: Path,
    work_item_id: str,
    name: str | None = None,
) -> WorkflowVariant:
    """The variant one dispatch WOULD run, resolved without writing the pin.

    The whole precedence and NONE of the persistence, so a surface that has to
    know which graph a pending dispatch will run -- the pre-dispatch
    acceptance-criteria wall, which sits before the launch that pins -- asks the
    question without answering it in the ledger. A wall that pinned would record
    a dispatch that its own refusal then prevented from happening.

    `resolve_dispatch_workflow_name` is written ON TOP of this rather than
    beside it: the preview and the pinning resolution are the same precedence,
    and two copies of it is exactly how the wall and the launch would come to
    disagree about which variant one dispatch runs.
    """
    recorded = dispatch_workflow_for(path=store_config(repo=repo), work_item_id=work_item_id)
    selected = name or _usable_recorded_name(repo=repo, recorded=recorded)
    return resolve_workflow_variant(cwd=repo, name=selected)


def resolve_dispatch_workflow_name(
    *,
    args: argparse.Namespace,
    repo: Path,
    work_item_id: str,
) -> str:
    """Resolve and persist the workflow-variant name for one dispatch.

    The recorded name is offered to `resolve_workflow_variant` as if it had
    been given explicitly, so the registry-and-default precedence stays in the
    ONE place that owns it rather than being restated here; this module
    decides only WHICH name to offer, and writes back what came out.
    """
    resolved = previewed_workflow_variant(
        repo=repo,
        work_item_id=work_item_id,
        name=_explicit_workflow_name(args=args),
    ).name
    record_dispatch_workflow(
        path=store_config(repo=repo), work_item_id=work_item_id, workflow=resolved
    )
    return resolved


def args_with_dispatch_workflow_name(
    *,
    args: argparse.Namespace,
    repo: Path,
    work_item_id: str,
) -> argparse.Namespace:
    """Return an args clone carrying the ledger-pinned workflow-variant name."""
    cloned = argparse.Namespace(**vars(args))
    cloned.workflow_name = resolve_dispatch_workflow_name(
        args=args,
        repo=repo,
        work_item_id=work_item_id,
    )
    return cloned


def _explicit_workflow_name(*, args: argparse.Namespace) -> str | None:
    """The `--workflow-name` argument, read defensively and from nowhere else.

    Only the dispatching subparsers define the argument, so the reconcile and
    check entry points reach this code with a Namespace that never carried it.
    There is deliberately no environment fallback here -- see the module
    docstring.
    """
    name = getattr(args, "workflow_name", None)
    if isinstance(name, str) and name != "":
        return name
    return None


def _usable_recorded_name(*, repo: Path, recorded: str | None) -> str | None:
    """The recorded name when it still names something this target can run.

    A name that has left the registry yields None, which hands the choice back
    to `dispatcher.default_workflow`. The reserved name is always usable: it is
    defined whether or not a registry exists, and it is never read from one.
    """
    if recorded is None or recorded == RESERVED_WORKFLOW_NAME:
        return recorded
    if recorded in workflow_registry(block=dispatcher_block(cwd=repo)):
        return recorded
    return None

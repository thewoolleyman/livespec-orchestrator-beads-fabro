"""Credential-lifetime policy for the selection a dispatch would claim."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_deadline import (
    CredentialLifetimeRequirement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_requirement import (
    WorkflowFaultDeferral,
    effective_policy_inputs,
    resolve_credential_lifetime_requirement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_item_ledger_reads import (
    read_dispatch_labels,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
    effective_review_fix_cap,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_REVIEW_FIX_CAP,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["selection_credential_requirement"]


def selection_credential_requirement(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: Sequence[WorkItem],
) -> CredentialLifetimeRequirement | str | WorkflowFaultDeferral:
    """The credential requirement covering EVERY item this pass would claim.

    One host credential covers the whole wave, so the figure has to cover the
    WIDEST review-fix loop in it: the widest loop is the longest execution the
    credential may have to outlive, and sizing against a narrower item would
    admit a credential the widest one cannot finish on. The cap is the item's
    EFFECTIVE one, so a `review-fix-cap:<n>` label raises this selection's floor
    exactly as it raises what the dispatch renders.

    A ledger label read that FAILS degrades to the repository-level default,
    which is the same degradation `_dispatcher_loop_plan` makes when it renders
    the input (`.value_or(DEFAULT_REVIEW_FIX_CAP)`). That identity is the point:
    the two surfaces are wrong together or right together, and a figure derived
    here that the dispatch then contradicted would be worse than either.
    """
    return resolve_credential_lifetime_requirement(
        repo=repo,
        workflow_override=getattr(args, "workflow", None),
        workflow_name=getattr(args, "workflow_name", None),
        policy_inputs=effective_policy_inputs(
            review_fix_cap=_widest_review_fix_cap(repo=repo, items=items)
        ),
    )


def _widest_review_fix_cap(*, repo: Path, items: Sequence[WorkItem]) -> int:
    """The largest effective review-fix cap across the selection.

    An EMPTY selection takes the repository default. The credential gate returns
    before grading anything on an empty selection, so this value is never used
    there; it exists so this function is total rather than relying on a caller's
    ordering to stay correct.
    """
    caps = [_review_fix_cap(repo=repo, item=item) for item in items]
    return max(caps) if caps else DEFAULT_REVIEW_FIX_CAP


def _review_fix_cap(*, repo: Path, item: WorkItem) -> int:
    """One item's effective cap, degrading to the default on an unreadable read.

    The label read is wrapped because it resolves the ledger CONNECTION before it
    reaches the ledger, and that resolution raises on a repository whose
    `connection.prefix` is unset or whose `.livespec.jsonc` is unreadable —
    errors `read_dispatch_labels` does not route as data because its own
    `exceptions` tuple covers only the beads calls past that point. Unwrapped,
    those escaped the credential derivation as a traceback from inside the
    pre-dispatch wall, which is a BUG-class escape on the path whose whole
    purpose is rendering actionable refusals.
    """
    labels = attempt(
        action=lambda: read_dispatch_labels(repo=repo, item=item),
        exceptions=(ConnectionPrefixMissingError, LivespecConfigUnreadableError),
    )
    resolved = () if isinstance(labels, AttemptFailure | str) else labels
    return unsafe_perform_io(
        effective_review_fix_cap(
            item=item,
            cwd=repo,
            raw_labels=resolved,
        ).value_or(DEFAULT_REVIEW_FIX_CAP)
    )

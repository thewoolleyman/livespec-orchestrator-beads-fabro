"""The orphaned-factory-runs attention lane, read from the reconciler's dry run.

An orphan holds a Fabro scheduler slot for work the ledger says nothing is
waiting on. Until the automatic pass reaches it — or on a host that never runs
the dispatcher at all — nothing tells an operator the slot is gone, because a
run that no dispatcher process is watching is invisible to every surface keyed
on this repo's own records.

The projection is the reconciler's OWN `--dry-run`, not a second join. A lane
with its own orphan rule would be free to disagree with the command whose name
it prints as the remedy, and the disagreement would surface as an operator
running a remedy that finds nothing.

Reading must not be an act, and that guarantee is STRUCTURAL here rather than a
convention: the seams handed to the reconciler are `InertJournal` and
`InertLedger`, which cannot write. A dry run does not journal or comment today;
if that ever changed, this lane would still write nothing.

Each factory is surveyed through its own declared server target, resolved by
`reconcile_factory_targets` — never a bare `FabroTarget`, which would answer for
whichever server the client happens to default to and report another host's
inventory as this one's.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_bin
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs import (
    reconcile_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    read_journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_factories import (
    reconcile_factory_targets,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_records import (
    ReconciledRun,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp import repo_run_attribution
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import (
    reconcile_runs_command,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "InertJournal",
    "InertLedger",
    "orphan_run_items",
]

_DISPATCHER_JOURNAL_PATH = Path("tmp") / "fabro-dispatch-journal.jsonl"
_ABSENT_ITEM_STATUS = "absent from the ledger"

# Same absorbed set as the wired dispatch-path pass: an unreadable config or an
# unreachable tenant makes this lane report nothing, never break the envelope
# every OTHER lane rides in.
_RECOVERABLE: tuple[type[Exception], ...] = (
    OSError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)


@dataclass(frozen=True, kw_only=True)
class InertJournal:
    """The journal seam a read-only projection is handed: it records nothing."""

    def append(self, *, record: dict[str, object]) -> None:
        """Discard one journal record."""
        _ = record


@dataclass(frozen=True, kw_only=True)
class InertLedger:
    """The ledger seam a read-only projection is handed: it writes nothing."""

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        """Report no comments rather than reaching the tenant."""
        _ = issue_id
        return []

    def add_comment(self, *, issue_id: str, body: str) -> None:
        """Discard one comment body."""
        _ = (issue_id, body)


def orphan_run_items(
    *,
    project_root: Path,
    repo: str,
    items: list[WorkItem],
    runner: CommandRunner | None = None,
) -> list[AttentionItem]:
    """Render one lane entry per orphaned factory run the reconciler would act on."""
    orphans = _projection(project_root=project_root, items=items, runner=runner)
    return [_orphan_item(project_root=project_root, repo=repo, run=run) for run in orphans]


def _projection(
    *,
    project_root: Path,
    items: list[WorkItem],
    runner: CommandRunner | None,
) -> tuple[ReconciledRun, ...]:
    surveyed = attempt(
        action=lambda: _survey(project_root=project_root, items=items, runner=runner),
        exceptions=_RECOVERABLE,
    )
    if isinstance(surveyed, AttemptFailure):
        return ()
    return surveyed


def _survey(
    *,
    project_root: Path,
    items: list[WorkItem],
    runner: CommandRunner | None,
) -> tuple[ReconciledRun, ...]:
    summary = reconcile_runs(
        inputs=ReconcileInputs(
            repo=project_root,
            fabro_bin=resolve_fabro_bin(cwd=project_root),
            id_prefix=store_config(repo=project_root).prefix,
            items=items,
            journaled=read_journaled_runs(path=project_root / _DISPATCHER_JOURNAL_PATH),
            runner=runner if runner is not None else ShellCommandRunner(),
            journal=InertJournal(),
            ledger=InertLedger(),
            attribution=repo_run_attribution(repo=project_root),
        ),
        factories=reconcile_factory_targets(repo=project_root),
        dry_run=True,
    )
    return summary.reconciled


def _orphan_item(*, project_root: Path, repo: str, run: ReconciledRun) -> AttentionItem:
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:orphaned-factory-run:{run.run_id}",
        kind="hygiene",
        urgency="high",
        summary=(
            f"Orphaned factory run {run.run_id} on factory {run.factory_name} "
            f"({run.factory_server_url}) is {run.status_kind} while work-item "
            f"{run.work_item_id} is "
            f"{run.work_item_status if run.work_item_status is not None else _ABSENT_ITEM_STATUS}"
            f"; orphan reason {run.orphan_reason}. It holds a Fabro scheduler "
            "slot the ledger says nothing is waiting on."
        ),
        source_ref=SourceRef(repo=repo, work_item=run.work_item_id),
        handoff=Handoff(
            kind="shell",
            command=reconcile_runs_command(project_root=project_root, factory=run.factory_name),
        ),
    )

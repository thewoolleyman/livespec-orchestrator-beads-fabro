"""The two model-fallback attention lanes, read from the dispatch journal.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" names both facts and they are deliberately DIFFERENT KINDS OF
CLAIM, which is why one module composing both is the honest shape:

- `hygiene:model-fallback-projection:<repo>:<run>:<node>` says a run's
  event stream was never read, at `high` urgency, and while it stands an
  unattended loop "MUST stop further picking for that repository". It is
  a statement about an UNREAD surface.
- `hygiene:model-fallback:<repo>:<node>` says a non-primary candidate
  actually ran. It "never refuses or disposes work", so it rides at
  `medium` urgency and hands over a read-only inspection.

Emitting one without the other would be the silent-absence failure this
whole clause exists to close: a repository whose projection is broken
shows NO fallback warnings, and without the projection fact beside them
that emptiness reads as "nothing fell back" rather than "nobody looked".

BOTH ARE PURE READS OF THE COMMITTED JOURNAL. Nothing here fetches
events, reaches a factory, or writes a line -- the projection itself is
performed by the dispatch and the reconciler, and this lane only
reports what those already recorded. Two invocations over an unchanged
journal therefore render byte-identical rows, which is what the
machine-envelope contract asks of every fact.
"""

from __future__ import annotations

from pathlib import Path

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_ledger import (
    ModelFallbackWarningLedger,
    newest_warning_per_node,
    read_model_fallback_warnings,
)
from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_records import (
    ModelFallbackWarning,
)
from livespec_orchestrator_beads_fabro.commands._acp_projection_failure import (
    unresolved_projection_failures,
)
from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_bin
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import (
    fabro_events_command,
    model_fallback_journal_command,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import LivespecConfigUnreadableError

__all__: list[str] = [
    "MODEL_FALLBACK_FACT_PREFIX",
    "dispatch_journal_path_for",
    "model_fallback_items",
    "model_fallback_projection_items",
    "model_fallback_warning_items",
]

MODEL_FALLBACK_FACT_PREFIX = "hygiene:model-fallback"

_JOURNAL_SUBPATH = ("tmp", "fabro-dispatch-journal.jsonl")
_JOURNAL_SOURCE_PATH = "tmp/fabro-dispatch-journal.jsonl"

# The warning is informational by contract -- it "never refuses or
# disposes work" -- so it sits below the projection fact's `high`. A
# `high` warning would compete for attention with the fact that stops the
# drain, and an operator who learns to dismiss one dismisses both.
_WARNING_URGENCY = "medium"


def dispatch_journal_path_for(*, project_root: Path) -> Path:
    """The dispatch journal both lanes read, resolved the way every seam does."""
    return project_root.joinpath(*_JOURNAL_SUBPATH)


def model_fallback_items(*, project_root: Path, repo: str) -> list[AttentionItem]:
    """Every model-fallback row this repository's journal currently supports."""
    journal = dispatch_journal_path_for(project_root=project_root)
    return model_fallback_projection_items(
        project_root=project_root, repo=repo, journal_path=journal
    ) + model_fallback_warning_items(project_root=project_root, repo=repo, journal_path=journal)


def model_fallback_projection_items(
    *, project_root: Path, repo: str, journal_path: Path
) -> list[AttentionItem]:
    """One high-urgency row per run and node whose events were never read."""
    context = ConformanceContext(project_root=project_root, repo=repo)
    fabro_bin = _fabro_bin(project_root=project_root)
    return [
        context.candidate(
            id=failure.fact_id,
            kind="hygiene",
            urgency="high",
            summary=failure.summary,
            source_ref=SourceRef(repo=repo, path=_JOURNAL_SOURCE_PATH),
            handoff=Handoff(
                kind="shell",
                command=fabro_events_command(
                    fabro_bin=fabro_bin,
                    run_id=failure.run_id,
                    server_url=failure.factory_server_url,
                ),
            ),
        )
        for failure in unresolved_projection_failures(journal_path=journal_path)
    ]


def model_fallback_warning_items(
    *, project_root: Path, repo: str, journal_path: Path
) -> list[AttentionItem]:
    """One aggregate row per node that actually ran a non-primary candidate."""
    ledger = read_model_fallback_warnings(journal_path=journal_path)
    context = ConformanceContext(project_root=project_root, repo=repo)
    newest = newest_warning_per_node(ledger=ledger)
    return [
        context.candidate(
            id=f"{MODEL_FALLBACK_FACT_PREFIX}:{repo}:{node}",
            kind="hygiene",
            urgency=_WARNING_URGENCY,
            summary=_warning_summary(warning=newest[node], ledger=ledger),
            source_ref=SourceRef(
                repo=repo,
                work_item=newest[node].work_item_id or None,
                path=_JOURNAL_SOURCE_PATH,
            ),
            handoff=Handoff(
                kind="shell",
                command=model_fallback_journal_command(project_root=project_root, node=node),
            ),
        )
        for node in sorted(newest)
    ]


def _warning_summary(*, warning: ModelFallbackWarning, ledger: ModelFallbackWarningLedger) -> str:
    """The deterministic line the NEWEST unresolved observation supplies.

    Aggregate, not per-observation: the fact is "one aggregate attention
    fact per repository/node", so the count of live observations for the
    node rides in the sentence while the newest one supplies the
    identities. Every value is read off stored records, so two renders
    over an unchanged journal are byte-identical.
    """
    live = sum(1 for entry in ledger.warnings if entry.node == warning.node)
    repeats = "" if live == 1 else f" ({live} unresolved observations)"
    return (
        f"ACP node {warning.node} ran non-primary candidate "
        f"{warning.candidate_display_name} (candidate {warning.candidate_index}, key "
        f"{warning.candidate_key}) after its primary failed {warning.cause} at "
        f"{warning.scope} scope on hold key {warning.hold_key}, at {warning.occurred_at}"
        f"{repeats}. The warning stands until the same primary generation "
        f"{warning.primary_generation} starts later and succeeds."
    )


def _fabro_bin(*, project_root: Path) -> str:
    """The engine binary the inspection handoff names, degrading to a bare name.

    An unreadable `.livespec.jsonc` must not cost the operator the fact:
    the row's value is the run and server it names, and a bare `fabro`
    still resolves on any host that has one on `PATH`.
    """
    resolved = attempt(
        action=lambda: resolve_fabro_bin(cwd=project_root),
        exceptions=(OSError, LivespecConfigUnreadableError),
    )
    if isinstance(resolved, AttemptFailure):
        return "fabro"
    return resolved

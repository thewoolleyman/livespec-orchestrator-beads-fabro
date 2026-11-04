"""The model-fallback attention lane, read from the dispatch journal.

`SPECIFICATION/contracts.md` names exactly ONE fact for this lane:
"one aggregate attention fact per repository/node with id
`hygiene:model-fallback:<repo>:<node>`", saying a non-primary candidate
actually ran. It "never refuses or disposes work", so it rides at
`medium` urgency and hands over a read-only inspection.

THERE WAS A SECOND FACT HERE AND ITS ABSENCE IS DELIBERATE. v127 deleted
`hygiene:model-fallback-projection:<repo>:<run>:<node>` together with the
`agent.acp.failover` projection that minted it. The two were composed in
one module because each was a check on the other: a repository whose
projection was broken showed NO fallback warnings, and without the
projection fact beside them that emptiness read as "nothing fell back"
rather than "nobody looked". That reasoning retires WITH the projection,
because the warning is now sourced from the Dispatcher's own selection
records -- a surface the Dispatcher writes itself and cannot fail to read
-- so an empty lane has only one meaning again.

A JOURNAL STILL CARRYING THOSE RETIRED RECORDS COMPOSES NOTHING FROM
THEM, which is a property of the fold rather than a filter: the lane
reads the warning stages and no other, so an `acp-projection-failure`
line is passed over exactly as any unknown stage is.

THIS IS A PURE READ OF THE COMMITTED JOURNAL. Nothing here fetches
events, reaches a factory, or writes a line -- the dispatch records the
selection it rendered, and this lane only reports what it already
recorded. Two invocations over an unchanged journal therefore render
byte-identical rows, which is what the machine-envelope contract asks of
every fact.
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
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import (
    model_fallback_journal_command,
)

__all__: list[str] = [
    "MODEL_FALLBACK_FACT_PREFIX",
    "dispatch_journal_path_for",
    "model_fallback_items",
    "model_fallback_warning_items",
]

MODEL_FALLBACK_FACT_PREFIX = "hygiene:model-fallback"

_JOURNAL_SUBPATH = ("tmp", "fabro-dispatch-journal.jsonl")
_JOURNAL_SOURCE_PATH = "tmp/fabro-dispatch-journal.jsonl"

# The warning is informational by contract -- it "never refuses or
# disposes work" -- so it rides below the `high` band the facts that DO
# gate something occupy. An operator who learns to dismiss a `high` row
# dismisses every `high` row.
_WARNING_URGENCY = "medium"


def dispatch_journal_path_for(*, project_root: Path) -> Path:
    """The dispatch journal this lane reads, resolved the way every seam does."""
    return project_root.joinpath(*_JOURNAL_SUBPATH)


def model_fallback_items(*, project_root: Path, repo: str) -> list[AttentionItem]:
    """Every model-fallback row this repository's journal currently supports."""
    return model_fallback_warning_items(
        project_root=project_root,
        repo=repo,
        journal_path=dispatch_journal_path_for(project_root=project_root),
    )


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

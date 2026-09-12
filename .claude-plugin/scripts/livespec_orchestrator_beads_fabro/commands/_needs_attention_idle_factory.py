"""The one attention row an idle factory produces, and the dispatch that starts it.

An idle factory with a full ready queue is the quietest failure this repository
has: every surface reports healthy, nothing is stranded, no wait is held, and no
work moves. The ratified idle-factory clause among the orchestrator-owned
attention facts in `SPECIFICATION/contracts.md` is the counterweight — one row
that says the factory could be dispatching and is not, carrying the exact
dispatch that would start it.

Three properties are load-bearing rather than incidental.

The trigger conditions are CONJUNCTIVE and each one clears the row on its
own. Ready work must be admission-eligible under the admission valve's
non-capacity conditions, the capacity verdict must report ZERO counted claims,
no unexpired provider-exhaustion record may be held, and the per-node fallback
preflight must leave at least one candidate for every success-critical ACP
node. A busy factory is not idle, a factory with nothing dispatchable is not
idle either, and a provider wait already composes its own row under the
provider spend-containment clause of `SPECIFICATION/contracts.md` — a second
row for the same wait would double-report one condition.

The ACP condition reads the SAME verdict admission reads, through
`acp_chain_wait_active`, and supplies it no credential probe. That is the
clause's requirement literally: a factory held back because a success-critical
chain is exhausted is not idle, it is waiting, and the row must not claim
otherwise.

The counted-claim read goes through `claimed_active_projection`, the
SIDE-EFFECT-FREE half of the accounting pair. Its sibling
`claimed_active_accounting` records abandonment as it reads, which is correct for
the dispatch path and wrong for a snapshot: composing attention must not move the
ledger, and a surface that wrote while reporting would make two invocations
against an unchanged store disagree.

Nothing here probes a credential or reaches the network. The clause derives this
fact from this repository's own ledger, journal and capacity verdict alone, so
the row can be composed on an offline host and two invocations against an
unchanged store emit a byte-identical row. In particular the eligible set is
filtered by `is_host_only_item` over the item's own materialized fields rather
than by the dispatch path's label-reading refusal, which journals as it refuses.
That makes this filter CONSERVATIVE at exactly one edge: an item whose
workflow-scope override lives in a ledger label reads as host-only here, so the
row can only ever be withheld, never falsely emitted.
"""

from __future__ import annotations

from pathlib import Path

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_reclaim import (
    claimed_active_projection,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_only import is_host_only_item
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import ready_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    plan_admissions,
    resolve_assignee,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import drive_command
from livespec_orchestrator_beads_fabro.commands._needs_attention_waits import (
    acp_chain_wait_active,
    provider_exhaustion_wait_active,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "admission_eligible_ready_items",
    "idle_factory_items",
]

_DISPATCHER_JOURNAL_PATH = Path("tmp") / "fabro-dispatch-journal.jsonl"


def idle_factory_items(
    *,
    project_root: Path,
    repo: str,
    items: list[WorkItem],
) -> list[AttentionItem]:
    """The single idle-factory row, or nothing when any trigger condition fails.

    The conditions are checked cheapest-refusal-first, but the order carries no
    meaning beyond that: all three must hold, so any one of them returning the
    empty list is the whole answer.
    """
    if provider_exhaustion_wait_active(project_root=project_root):
        return []
    if acp_chain_wait_active(project_root=project_root):
        return []
    if counted_claims(project_root=project_root, items=items) != 0:
        return []
    eligible = admission_eligible_ready_items(project_root=project_root, items=items)
    if not eligible:
        return []
    return [_idle_factory_item(project_root=project_root, repo=repo, eligible=eligible)]


def counted_claims(*, project_root: Path, items: list[WorkItem]) -> int:
    """This repository's counted claims, read through the side-effect-free projection.

    The single-authority capacity verdict is `ActiveClaimAccounting.active_count`
    — the accounting's OWN count, not a re-derivation from the `active` rows.
    Re-deriving it here would put a second authority on the one question the
    capacity clause reserves to the accounting.
    """
    return claimed_active_projection(
        repo=project_root,
        items=items,
        journal=JournalFile(path=project_root / _DISPATCHER_JOURNAL_PATH),
    ).active_count


def admission_eligible_ready_items(
    *,
    project_root: Path,
    items: list[WorkItem],
) -> list[WorkItem]:
    """The ready candidates the admission valve would admit if capacity allowed.

    Composed from the drain's OWN two stages rather than from a look-alike
    predicate: `ready_items` supplies the dispatch-candidate set in the
    Dispatcher's ranked order, and `plan_admissions` — run with as many free
    slots as there are candidates, which is what "capacity excepted" means —
    drops each candidate it would hold for a manual approval or an unresolvable
    assignee. What survives is exactly the drain's non-capacity eligibility, in
    the drain's order, so the first element is the first ranked such item.
    """
    candidates = [
        item
        for item in ready_items(items=items, repo=project_root)
        if not is_host_only_item(item=item)
    ]
    plan = plan_admissions(
        ready_items=candidates,
        free_slots=len(candidates),
        cwd=project_root,
        resolve_assignee=resolve_assignee,
    )
    return [item for item, _assignee in plan.admitted]


def _idle_factory_item(
    *,
    project_root: Path,
    repo: str,
    eligible: list[WorkItem],
) -> AttentionItem:
    first = eligible[0].id
    action_id = f"impl:{first}"
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:idle-factory:{repo}",
        kind="hygiene",
        urgency="high",
        summary=_summary(repo=repo, eligible=eligible),
        source_ref=SourceRef(repo=repo, work_item=first),
        handoff=Handoff(
            kind="drive",
            command=drive_command(project_root=project_root, action_id=action_id),
            action_id=action_id,
        ),
    )


def _summary(*, repo: str, eligible: list[WorkItem]) -> str:
    """Name the count and the first ranked id, and nothing that varies per pass.

    Deterministic by construction: both subjects are read off the ranked eligible
    set itself, so two invocations against an unchanged store render the same
    bytes. No clock, no dwell, and no run id appears here.
    """
    first = eligible[0].id
    return (
        f"Factory idle for {repo}: {len(eligible)} admission-eligible ready work-items "
        f"and zero counted claims, with no provider-exhaustion record held. "
        f"Dispatch the first ranked item {first} with impl:{first}."
    )

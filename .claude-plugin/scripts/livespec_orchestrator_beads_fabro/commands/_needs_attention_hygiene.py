"""Compose the orchestrator-owned hygiene facts from one attention snapshot.

The command binding owns core attention and transport. This module owns hygiene
composition, including the shared hold reads, ambient readers and their clock.
Individual lanes retain their conformance boundaries and existing ordering.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from livespec_runtime.attention_item import AttentionItem
from livespec_runtime.cross_repo.types import CrossRepoManifest, RefStatus
from livespec_runtime.hygiene_scan import scan_hygiene

from livespec_orchestrator_beads_fabro._store_merge_hold import read_merge_held_work_item_ids
from livespec_orchestrator_beads_fabro._store_pre_admission_dod import read_pre_admission_holds
from livespec_orchestrator_beads_fabro.commands._needs_attention_capacity import (
    capacity_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
    conformant_lane,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_currency_staleness import (
    currency_staleness_items,
    default_currency_staleness_seams,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_definition_of_done import (
    advisory_definition_of_done_items,
    held_definition_of_done_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_detection_staleness import (
    detection_staleness_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_idle_factory import (
    idle_factory_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_merge_hold import (
    merge_hold_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_missing_pointer import (
    missing_proof_pointer_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_model_fallback import (
    model_fallback_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_orphan_runs import (
    orphan_run_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_proof import (
    pending_host_leg_items,
    pending_human_attestation_items,
    stale_proof_pointer_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_ready_aging import (
    ReadyAgingContext,
    ReadyAgingSeams,
    ready_aging_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_ready_aging import (
    utc_now_iso as _ready_aging_utc_now_iso,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_release_adoption import (
    default_release_adoption_bases,
    release_adoption_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_unrunnable_acceptance import (
    unrunnable_acceptance_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_untriaged_backlog import (
    untriaged_backlog_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_work_items import (
    auto_admission_items,
    host_only_items,
    live_dispatch_lock_lookup,
    provider_exhaustion_items,
    stranded_dispatch_items,
    watchable_fabro_run_item_ids,
)
from livespec_orchestrator_beads_fabro.store import (
    read_intake_triage_records,
    read_ready_dwell_instants,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "gather_hygiene_items",
]


def gather_hygiene_items(
    *,
    materialized: list[WorkItem],
    config: StoreConfig,
    manifest: CrossRepoManifest,
    sibling_status_lookup: Callable[[str, str], RefStatus],
    include_hygiene: bool,
    context: ConformanceContext,
) -> list[AttentionItem]:
    """Gather each hygiene lane without changing the shared attention snapshot."""
    project_root = context.project_root
    repo_name = context.repo
    # One narrow raw read of the `merge-hold:` label for the whole pass, threaded
    # into BOTH surfaces the ratified hold binds: the row that reports a hold and
    # the stranded lane that must not. Two independent reads would be two
    # authorities on one question, and disagreeing would report a held item as
    # stranded AND as held in the same snapshot.
    held_work_item_ids = read_merge_held_work_item_ids(path=config)
    # Every candidate crosses a conformance boundary before it reaches the wire: a
    # runtime-validator rejection surfaces as a visible failure item rather than
    # shortening the list OR aborting the pass, because a manufacturable absence
    # reads as resolution downstream (the machine-envelope contract in
    # SPECIFICATION/contracts.md). The lanes this repository composes DIRECTLY
    # carry that boundary at their own construction; the hygiene scan builds its
    # items inside the runtime, so it crosses the lane-granular one here.
    hygiene_scan = (
        conformant_lane(
            context=context,
            subject=f"hygiene scan of {repo_name}",
            key=f"hygiene-scan-{repo_name}",
            compose=partial(scan_hygiene, repo_path=project_root, repo_name=repo_name),
        )
        if include_hygiene
        else []
    )
    return (
        auto_admission_items(project_root=project_root, repo=repo_name, items=materialized)
        + provider_exhaustion_items(project_root=project_root, repo=repo_name, items=materialized)
        + host_only_items(project_root=project_root, repo=repo_name, items=materialized)
        + stranded_dispatch_items(
            project_root=project_root,
            repo=repo_name,
            items=materialized,
            held_work_item_ids=held_work_item_ids,
        )
        # A hold parks an item in exactly the shape every other lane here is
        # taught to ignore, so this row is the one thing standing between a
        # deliberate merge window and an invisible one.
        + merge_hold_items(
            project_root=project_root,
            repo=repo_name,
            items=materialized,
            held_work_item_ids=held_work_item_ids,
        )
        + capacity_items(project_root=project_root, repo=repo_name, items=materialized)
        # The mirror image of the capacity fact above: that one reports a
        # factory too busy to take more, this one a factory taking nothing
        # while dispatchable work waits. An idle queue is silent on every
        # other lane here — nothing is stranded, held, or aging past a
        # bound — so without this row it is visible only by being noticed.
        + idle_factory_items(project_root=project_root, repo=repo_name, items=materialized)
        # The other half of that pair, and the one the idle-factory fact cannot
        # report: an item resting in `ready` that NO dispatch will ever take,
        # because the shared eligibility decision refuses it. Such a row is
        # silent on every lane here — nothing is stranded, held, or aging — so
        # without it an unrunnable item is visible only by being noticed.
        + unrunnable_acceptance_items(project_root=project_root, repo=repo_name, items=materialized)
        # The row that lane CANNOT produce, and the asymmetry is the point: it
        # fires on the shared eligibility decision refusing an item, while an
        # advisory Definition-of-Done finding is forbidden from refusing anything.
        # Such an item is dispatchable, is silent on every lane here, and becomes
        # visible only through the sandbox it spends discovering the finding.
        + advisory_definition_of_done_items(
            project_root=project_root, repo=repo_name, items=materialized
        )
        + held_definition_of_done_items(
            project_root=project_root,
            repo=repo_name,
            items=materialized,
            holds=read_pre_admission_holds(path=config),
        )
        # The three Proof of Done hygiene rows. A parked item awaiting its host
        # replay or its human attestation is otherwise indistinguishable from any
        # other parked acceptance, and a stale pointer is silent on every lane
        # here, so without these the first two are visible only by reading the
        # item's Definition of Done and the third only by reading its pull
        # request. The two pending legs are SEPARATE rows because different
        # parties clear them: an agent session on an operator host captures and a
        # second session replays the host leg, while a human attests the other.
        + pending_host_leg_items(project_root=project_root, repo=repo_name, items=materialized)
        + pending_human_attestation_items(
            project_root=project_root, repo=repo_name, items=materialized
        )
        + stale_proof_pointer_items(project_root=project_root, repo=repo_name, items=materialized)
        # The THIRD pointer row, and the one neither of the two above can produce:
        # both read a pointer the item already carries, so an item with none is
        # invisible to them — which is exactly the state the first merged
        # proof-chain item has rested in since 2026-10-01.
        + missing_proof_pointer_items(project_root=project_root, repo=repo_name, items=materialized)
        # A run the ledger disowns holds a factory scheduler slot, and no
        # surface keyed on THIS repo's records can see it: the projection is
        # the reconciler's own dry run, so the lane and the remedy it prints
        # can never disagree about what an orphan is.
        + orphan_run_items(project_root=project_root, repo=repo_name, items=materialized)
        # The two ACP fallback rows. They are composed TOGETHER because the
        # absence of one changes what the other means: a repository whose
        # event projection is broken shows no model-fallback warnings, and
        # that emptiness reads as "nothing fell back" unless the
        # projection-failure row is standing beside it saying nobody looked.
        + model_fallback_items(project_root=project_root, repo=repo_name)
        # Detection recency is a REPOSITORY property computed from the
        # completed coverage records on the committed anchor. Neither fact
        # invokes a detector: both are surfaced triggers naming the skill.
        + detection_staleness_items(project_root=project_root, repo=repo_name, config=config)
        # Ambient plugin-currency staleness is SURFACED here and nowhere
        # else: the dispatch-admission gate lost its blocking authority over
        # it in v089, so this fact is what carries the freshness pressure.
        # It never gates a dispatch — only a committed
        # `dispatcher.minimum_release` floor can refuse on currency.
        + currency_staleness_items(
            project_root=project_root,
            repo=repo_name,
            seams=default_currency_staleness_seams(),
        )
        # Adoption is a HOST fact, not a tenant fact: the pin is a moving
        # branch, so the only per-repo evidence that a release actually
        # arrived lives in this machine's install records.
        + release_adoption_items(
            project_root=project_root,
            repo=repo_name,
            bases=default_release_adoption_bases(),
        )
        + ready_aging_items(
            context=ReadyAgingContext(
                project_root=project_root,
                repo=repo_name,
                manifest=manifest,
            ),
            items=materialized,
            ready_dwell_instants=read_ready_dwell_instants(path=config.work_items_path),
            sibling_status_lookup=sibling_status_lookup,
            seams=ReadyAgingSeams(
                live_lock_lookup=live_dispatch_lock_lookup,
                watchable_run_item_ids=watchable_fabro_run_item_ids,
                now_iso=_utc_now_iso(),
            ),
        )
        # A second raw read of the tenant: the triage marker is a label and the
        # urgency tier is the beads-native `priority` column, and the
        # materialized `WorkItem` above carries neither (labels are decoded into
        # named fields; `priority` was dropped for `rank`). Same shape as the
        # other narrow raw read, `read_work_item_native_priorities`.
        + untriaged_backlog_items(
            project_root=project_root,
            repo=repo_name,
            records=read_intake_triage_records(path=config.work_items_path),
        )
        + hygiene_scan
    )


def _utc_now_iso() -> str:
    return _ready_aging_utc_now_iso()

"""Thin needs-attention binding over this plugin's gather primitives."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from functools import partial
from pathlib import Path

from livespec_runtime.attention_item import AttentionItem
from livespec_runtime.hygiene_scan import scan_hygiene

from livespec_orchestrator_beads_fabro._store_answer_disposition import (
    read_answer_disposition_labels,
)
from livespec_orchestrator_beads_fabro._store_merge_hold import read_merge_held_work_item_ids
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._cross_repo import load_manifest
from livespec_orchestrator_beads_fabro.commands._needs_attention_capacity import (
    capacity_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
    composed_conformant,
    conformant_lane,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_currency_staleness import (
    currency_staleness_items,
    default_currency_staleness_seams,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_detection_staleness import (
    detection_staleness_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_envelope import (
    render_envelope_markdown,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import (
    plans,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_idle_factory import (
    idle_factory_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_merge_hold import (
    merge_hold_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_orphan_runs import (
    orphan_run_items,
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
from livespec_orchestrator_beads_fabro.commands._needs_attention_spec_next_run import (
    spec_next,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_untriaged_backlog import (
    untriaged_backlog_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_work_items import (
    auto_admission_items,
    host_only_items,
    human_valves,
    impl_next,
    live_dispatch_lock_lookup,
    provider_exhaustion_items,
    stranded_dispatch_items,
    watchable_fabro_run_item_ids,
)
from livespec_orchestrator_beads_fabro.commands._sibling_status_lookup import (
    make_sibling_status_lookup,
)
from livespec_orchestrator_beads_fabro.io import write_stdout
from livespec_orchestrator_beads_fabro.store import (
    materialize_work_items,
    read_intake_triage_records,
    read_ready_dwell_instants,
    read_work_items,
)

__all__: list[str] = [
    "build_attention",
    "main",
    "render_json",
    "render_markdown",
]


def main(*, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="needs-attention")
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    _ = parser.add_argument("--work-items-path", dest="work_items_path", default=None)
    _ = parser.add_argument("--repo-name", dest="repo_name", default=None)
    _ = parser.add_argument("--skip-hygiene", dest="skip_hygiene", action="store_true")
    args = parser.parse_args(argv)
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    repo_name = args.repo_name if args.repo_name is not None else project_root.name
    attention = build_attention(
        project_root=project_root,
        repo_name=repo_name,
        work_items_path=args.work_items_path,
        include_hygiene=not args.skip_hygiene,
    )
    if args.as_json:
        _ = write_stdout(text=render_json(attention=attention))
    else:
        _ = write_stdout(text=render_markdown(attention=attention))
    return 0


def build_attention(
    *,
    project_root: Path,
    repo_name: str,
    work_items_path: str | None = None,
    include_hygiene: bool = True,
) -> list[AttentionItem]:
    config = resolve_store_config(cwd=project_root, work_items_arg=work_items_path)
    items = list(read_work_items(path=config.work_items_path))
    manifest = load_manifest(project_root=project_root)
    materialized = list(materialize_work_items(records=iter(items)).values())
    index = {item.id: item for item in materialized}
    # One cross-tenant sibling resolver for this whole attention pass, threaded
    # into every readiness/lane consumer so the impl-next pick and the
    # human-valve lanes agree with the dispatcher on closed-sibling items
    # (qiqz6b Part B).
    sibling_status_lookup = make_sibling_status_lookup(project_root=project_root)
    # One narrow raw read of the `merge-hold:` label for the whole pass, threaded
    # into BOTH surfaces the ratified hold binds: the row that reports a hold and
    # the stranded lane that must not. Two independent reads would be two
    # authorities on one question, and disagreeing would report a held item as
    # stranded AND as held in the same snapshot.
    held_work_item_ids = read_merge_held_work_item_ids(path=config)
    # The same narrow-raw-read shape, for the `answer:` per-item override of the
    # ratified answer disposition: one read for the whole pass, so every parked
    # item's reported disposition comes from one authority rather than from a
    # per-lane re-read that could disagree with the next row down.
    answer_disposition_labels = read_answer_disposition_labels(path=config)
    # Every candidate crosses a conformance boundary before it reaches the wire: a
    # runtime-validator rejection surfaces as a visible failure item rather than
    # shortening the list OR aborting the pass, because a manufacturable absence
    # reads as resolution downstream (the machine-envelope contract in
    # SPECIFICATION/contracts.md). The lanes this repository composes DIRECTLY
    # carry that boundary at their own construction; the hygiene scan builds its
    # items inside the runtime, so it crosses the lane-granular one here.
    context = ConformanceContext(project_root=project_root, repo=repo_name)
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
    return composed_conformant(
        context=context,
        spec_next=spec_next(project_root=project_root),
        impl_next=impl_next(
            project_root=project_root,
            items=materialized,
            manifest=manifest,
            sibling_status_lookup=sibling_status_lookup,
        ),
        human_valve_lanes=human_valves(
            project_root=project_root,
            items=materialized,
            index=index,
            manifest=manifest,
            sibling_status_lookup=sibling_status_lookup,
            answer_disposition_labels=answer_disposition_labels,
        ),
        plan_threads=plans(project_root=project_root, config=config, items=materialized),
    ) + (
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
        # A run the ledger disowns holds a factory scheduler slot, and no
        # surface keyed on THIS repo's records can see it: the projection is
        # the reconciler's own dry run, so the lane and the remedy it prints
        # can never disagree about what an orphan is.
        + orphan_run_items(project_root=project_root, repo=repo_name, items=materialized)
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


def render_json(*, attention: list[AttentionItem]) -> str:
    return (
        json.dumps({"attention": [asdict(item) for item in attention]}, indent=2, sort_keys=True)
        + "\n"
    )


def render_markdown(*, attention: list[AttentionItem]) -> str:
    """Render the operator Markdown by consuming this producer's OWN wire envelope.

    The consumer-tolerance posture binds this repository's own consuming
    surfaces, so the operator view is not rendered from the in-memory
    composition: it is rendered from exactly the bytes a downstream consumer
    receives, through the same tolerant per-item parse. That is what makes the
    posture executable here rather than merely advertised — a malformed item can
    only ever cost itself, and an unknown `kind` renders generically.
    """
    return render_envelope_markdown(envelope=render_json(attention=attention))

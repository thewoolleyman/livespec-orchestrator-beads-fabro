"""Thin needs-attention binding over this plugin's gather primitives."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from livespec_runtime.attention_item import AttentionItem

from livespec_orchestrator_beads_fabro._store_answer_disposition import (
    read_answer_disposition_labels,
)
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._cross_repo import load_manifest
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
    composed_conformant,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_envelope import (
    render_envelope_markdown,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import (
    plans,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_hygiene import gather_hygiene_items
from livespec_orchestrator_beads_fabro.commands._needs_attention_spec_next_run import (
    spec_next,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_work_items import (
    human_valves,
    impl_next,
)
from livespec_orchestrator_beads_fabro.commands._sibling_status_lookup import (
    make_sibling_status_lookup,
)
from livespec_orchestrator_beads_fabro.io import write_stdout
from livespec_orchestrator_beads_fabro.store import (
    materialize_work_items,
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
    # The same narrow-raw-read shape, for the `answer:` per-item override of the
    # ratified answer disposition: one read for the whole pass, so every parked
    # item's reported disposition comes from one authority rather than from a
    # per-lane re-read that could disagree with the next row down.
    answer_disposition_labels = read_answer_disposition_labels(path=config)
    context = ConformanceContext(project_root=project_root, repo=repo_name)
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
    ) + gather_hygiene_items(
        materialized=materialized,
        config=config,
        manifest=manifest,
        sibling_status_lookup=sibling_status_lookup,
        include_hygiene=include_hygiene,
        context=context,
    )


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

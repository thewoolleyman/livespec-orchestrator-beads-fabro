"""Path and config-resolution helpers for the Dispatcher."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    parse_pr_files,
    pr_files_argv,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "cost_report_spans_path",
    "cost_sink_path",
    "heartbeat_path",
    "is_writable_orchestrator_checkout",
    "journal_path",
    "plugin_root",
    "reflector_oob_spans_path",
    "resolve_merged_paths",
    "spans_path",
    "store_config",
    "workflow_toml",
]

_PR_FILES_PROBE_TIMEOUT_SECONDS = 60.0
_CHECKOUT_PROBE_TIMEOUT_SECONDS = 60.0

# The slug the self-update canary requires the promotion target's `origin`
# to carry: the candidate must be a checkout of THIS orchestrator, never a
# stray sibling repo the plugin happens to sit inside.
_ORCHESTRATOR_REPO_SLUG = "livespec-orchestrator-beads-fabro"


def store_config(*, repo: Path) -> StoreConfig:
    return resolve_store_config(cwd=repo, work_items_arg=None)


def workflow_toml(*, args: argparse.Namespace) -> Path:
    if args.workflow is not None:
        return Path(args.workflow)
    return plugin_root() / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"


def journal_path(*, args: argparse.Namespace, repo: Path) -> Path:
    if args.journal is not None:
        return Path(args.journal)
    return repo / "tmp" / "fabro-dispatch-journal.jsonl"


def spans_path(*, args: argparse.Namespace, repo: Path) -> Path:
    """Where the mechanical reflection stage appends its OTLP/JSON spans.

    Co-located with the journal (one `<base>-reflection-spans.jsonl`
    sibling) so a future one-shot replay finds both in the same place;
    one `ExportTraceServiceRequest` per line (the family capture format).
    """
    journal = journal_path(args=args, repo=repo)
    return journal.with_name(f"{journal.stem}-reflection-spans.jsonl")


def reflector_oob_spans_path(*, args: argparse.Namespace, repo: Path) -> Path:
    """Where the out-of-band reflector appends its `gen_ai.evaluation.result` spans.

    Co-located with the journal (a `<base>-reflector-oob-spans.jsonl`
    sibling next to the mechanical-reflection spans file) so the verdict
    spans ride the SAME established local-span-file -> enrich egress path;
    one `ExportTraceServiceRequest` per line (the family capture format).
    """
    journal = journal_path(args=args, repo=repo)
    return journal.with_name(f"{journal.stem}-reflector-oob-spans.jsonl")


def heartbeat_path(*, args: argparse.Namespace, repo: Path) -> Path:
    """Where the live receiver writes the per-run metrics heartbeat.

    Co-located with the journal (a `<base>-otel-heartbeat.json` sibling) so
    the liveness probe reads it out of process next to the rest of the
    dispatch's tmp artifacts.
    """
    journal = journal_path(args=args, repo=repo)
    return journal.with_name(f"{journal.stem}-otel-heartbeat.json")


def cost_sink_path(*, args: argparse.Namespace, repo: Path) -> Path:
    """Where the live receiver writes the per-dispatch CC-token cost.

    Co-located with the journal (a `<base>-otel-cost.json` sibling next to
    the heartbeat file) so the cost gate reads the derived per-dispatch
    cost out of process, exactly as the liveness probe reads the heartbeat.
    The receiver accrues each per-API-call token vector here keyed by
    `work.item.id` / `livespec.dispatch.id`.
    """
    journal = journal_path(args=args, repo=repo)
    return journal.with_name(f"{journal.stem}-otel-cost.json")


def cost_report_spans_path(*, args: argparse.Namespace, repo: Path) -> Path:
    """Where report mode appends its `cost.report` OTLP spans."""
    journal = journal_path(args=args, repo=repo)
    return journal.with_name(f"{journal.stem}-cost-report-spans.jsonl")


def plugin_root() -> Path:
    """The plugin root, resolving in BOTH the source tree and the flattened cache.

    In source this module lives at
    `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_paths.py`,
    so the plugin root is `parents[3]` (the `.claude-plugin/` dir). The Claude
    install flattens that dir to the cache root and exports
    `CLAUDE_PLUGIN_ROOT`; when that env var is set and non-empty it wins. Both
    the `.fabro/` workflow payload and the `scripts/bin/` wrappers ship UNDER
    this root, so a cache-installed plugin resolves them with no repo checkout
    present.
    """
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parents[3]


def resolve_merged_paths(*, repo: Path, runner: CommandRunner) -> tuple[str, ...]:
    """Read the merged PR's changed paths; () on any unobservable signal."""
    head = runner.run(
        argv=["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        timeout_seconds=_PR_FILES_PROBE_TIMEOUT_SECONDS,
    )
    branch = head.stdout.strip() if head.exit_code == 0 else "master"
    files = runner.run(
        argv=pr_files_argv(branch=branch),
        cwd=repo,
        timeout_seconds=_PR_FILES_PROBE_TIMEOUT_SECONDS,
    )
    return parse_pr_files(stdout=files.stdout) if files.exit_code == 0 else ()


def is_writable_orchestrator_checkout(*, root: Path, runner: CommandRunner) -> bool:
    """True only when `root` is inside a git work-tree whose origin is this orchestrator."""
    inside = runner.run(
        argv=["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        cwd=Path.cwd(),
        timeout_seconds=_CHECKOUT_PROBE_TIMEOUT_SECONDS,
    )
    if inside.exit_code != 0 or inside.stdout.strip() != "true":
        return False
    origin = runner.run(
        argv=["git", "-C", str(root), "remote", "get-url", "origin"],
        cwd=Path.cwd(),
        timeout_seconds=_CHECKOUT_PROBE_TIMEOUT_SECONDS,
    )
    return origin.exit_code == 0 and _ORCHESTRATOR_REPO_SLUG in origin.stdout

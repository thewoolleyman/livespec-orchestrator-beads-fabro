"""Path and config-resolution helpers for the Dispatcher."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._workflow_variants import (
    RESERVED_WORKFLOW_NAME,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "calibration_spans_path",
    "cost_report_spans_path",
    "cost_sink_path",
    "executing_payload_root",
    "heartbeat_path",
    "journal_path",
    "plugin_root",
    "reflector_oob_spans_path",
    "run_turn_sink_path",
    "spans_path",
    "state_root",
    "store_config",
    "tdd_order_sink_path",
    "workflow_toml",
]

# The manifest file every workflow directory carries, whether it is the
# reserved workflow or a registered variant. A variant's directory comes from
# the registry, so only the FILENAME is constant for it.
_WORKFLOW_MANIFEST = "workflow.toml"

# Where the RESERVED workflow sits under whichever root carries it — the plugin
# root for the bundled default, or a dispatch target's own checkout for the
# repo-local override. The variant-name segment is the reserved name itself
# rather than a repeated literal, so a registry that renamed it could not leave
# this path pointing at a directory nothing else refers to.
_RESERVED_WORKFLOW_SUBPATH = (
    ".fabro",
    "workflows",
    RESERVED_WORKFLOW_NAME,
    _WORKFLOW_MANIFEST,
)
_RUN_TURN_DATASET = "fabro"


def store_config(*, repo: Path) -> StoreConfig:
    return resolve_store_config(cwd=repo, work_items_arg=None)


def workflow_toml(*, args: argparse.Namespace, variant_directory: str | None = None) -> Path:
    """The committed Fabro workflow config this dispatch runs, by precedence.

    1. An explicit `--workflow <path>` always wins — the raw-path escape
       hatch, which outranks every registry choice.
    2. Otherwise `variant_directory`, the registry-declared directory of the
       named variant this dispatch selected, resolved under the dispatch
       target's repo root. A variant is a WHOLE directory: there is no
       target-local-then-bundle fallback for one, because a variant that is
       not where the registry says it is has no second candidate location to
       try. `_dispatcher_workflow_variant` has already refused a directory
       missing its manifest or graph, so this step does not re-probe.
    3. Otherwise the RESERVED `implement-work-item` workflow: the DISPATCH
       TARGET's own committed
       `<repo>/.fabro/workflows/implement-work-item/workflow.toml` when it
       exists. The workflow config carries the sandbox image pin, so a
       consumer repo whose toolchain differs from the orchestrator's own
       (a Rust repo needing the `python-rust-agent-` layer, against the
       orchestrator's Python-only pin) governs its own execution substrate
       rather than silently inheriting one that cannot build it.
    4. Otherwise the plugin's bundled workflow — the default for every
       dispatch target that commits none. Resolved under
       `executing_payload_root`, NOT `plugin_root`: this is an asset read, and
       it has to keep working after the harness evicts the installation this
       invocation launched from.

    `args` is not guaranteed to carry a `repo` attribute: only the
    dispatch-common subparsers define `--repo`, so BOTH repo-anchored steps
    read it defensively and degrade to the bundled default. A variant
    directory with no repo to anchor it is that same degradation rather than
    a refusal: the surfaces reaching here without `--repo` (the reconcile and
    check subcommands) never select a variant in the first place.
    """
    if args.workflow is not None:
        return Path(args.workflow)
    repo: object = getattr(args, "repo", None)
    if repo is not None:
        repo_root = Path(str(repo))
        if variant_directory is not None:
            return repo_root / variant_directory / _WORKFLOW_MANIFEST
        repo_local = repo_root.joinpath(*_RESERVED_WORKFLOW_SUBPATH)
        if repo_local.is_file():
            return repo_local
    return executing_payload_root().joinpath(*_RESERVED_WORKFLOW_SUBPATH)


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


def run_turn_sink_path(*, args: argparse.Namespace, repo: Path) -> Path:
    """Where any host receiver records successful Fabro `run_turn` exports.

    The OTLP receiver binds one host-global port, so a different repo's
    dispatcher may own the live receiver that successfully exports this repo's
    Fabro spans. Keep the marker host-global and dataset-scoped so the
    timestamp-bounded guard reads the same signal whichever repo owns :4318.
    """
    _ = (args, repo)
    return (
        state_root()
        / "livespec-orchestrator-beads-fabro"
        / "run-turn-exports"
        / f"{_RUN_TURN_DATASET}.json"
    )


def state_root() -> Path:
    """The per-user root for host-local dispatcher state, repo-independent.

    `XDG_STATE_HOME` when set, else `~/.local/state` — the freedesktop
    convention. PUBLIC because more than one surface needs the SAME root
    resolved the same way: the run-turn export marker above, and the
    tenant-checkout registry that makes the WIP-cap counted-claim bound
    tenant-scoped rather than per-checkout. Two checkouts of one tenant
    resolve an identical root, which is the whole point — a per-repo root
    could not be shared between a worktree and a fresh clone.
    """
    state_home = os.environ.get("XDG_STATE_HOME")
    return Path(state_home) if state_home else Path.home() / ".local" / "state"


def cost_report_spans_path(*, args: argparse.Namespace, repo: Path) -> Path:
    """Where report mode appends its `cost.report` OTLP spans."""
    journal = journal_path(args=args, repo=repo)
    return journal.with_name(f"{journal.stem}-cost-report-spans.jsonl")


def calibration_spans_path(*, args: argparse.Namespace, repo: Path) -> Path:
    """Where calibration emission appends its `dispatcher.calibration` OTLP spans."""
    journal = journal_path(args=args, repo=repo)
    return journal.with_name(f"{journal.stem}-calibration-spans.jsonl")


def tdd_order_sink_path(*, args: argparse.Namespace, repo: Path) -> Path:
    """Where the live receiver accrues the sandbox order guard's decisions.

    Co-located with the journal (a `<base>-tdd-order.json` sibling next to the
    cost and heartbeat files) so calibration reads the per-dispatch order
    aggregate out of process, exactly as the cost gate reads the cost sink.
    """
    journal = journal_path(args=args, repo=repo)
    return journal.with_name(f"{journal.stem}-tdd-order.json")


def executing_payload_root() -> Path:
    """The root of the payload THIS process is executing its own code out of.

    Distinct from `plugin_root` on purpose, and the distinction is the whole
    point. `plugin_root` answers "which installation is present", which is the
    question the self-update canary and the currency findings ask — and the
    answer has to keep being the INSTALLED tree, because a newer build landing
    there mid-run is exactly what they exist to discover. This function answers
    "where is the code that is running", and after `bin/_payload.py` has copied
    a harness-managed release aside, those are two different trees.

    Packaged ASSET reads resolve through here. Derived from `__file__` rather
    than from an environment variable, so it cannot disagree with where the
    importing module actually came from: whichever tree this module was loaded
    out of is the tree its sibling assets sit in. The layout is the same in
    both cases — in source this module is at
    `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_paths.py`,
    and a retained payload is a whole-tree copy — so `parents[3]` is the root
    either way.
    """
    return Path(__file__).resolve().parents[3]


def plugin_root() -> Path:
    """The INSTALLED plugin root, resolving in BOTH the source tree and the flattened cache.

    In source this module lives at
    `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_paths.py`,
    so the plugin root is `parents[3]` (the `.claude-plugin/` dir). The Claude
    install flattens that dir to the cache root and exports
    `CLAUDE_PLUGIN_ROOT`; when that env var is set and non-empty it wins.

    This is the INSTALLATION, which is not necessarily where this process's
    code came from — see `executing_payload_root`. Keep the two apart: the
    self-update canary reads THIS root late, so that a newer build installed
    mid-run is discovered as a candidate, and the minimum-release floor and
    registered-install currency finding identify the executing build through
    it. Pointing it at a retained copy makes every one of those comparisons
    the running build against itself. Packaged ASSET reads therefore go
    through `executing_payload_root` instead, so they survive the
    installation being evicted.
    """
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parents[3]

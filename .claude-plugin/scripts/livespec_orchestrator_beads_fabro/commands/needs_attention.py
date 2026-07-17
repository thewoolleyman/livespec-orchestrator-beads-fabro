"""Thin needs-attention binding over this plugin's gather primitives."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from livespec_runtime.attention_item import AttentionItem
from livespec_runtime.hygiene_scan import scan_hygiene
from livespec_runtime.needs_attention import (
    SpecNextOutput,
    compose_needs_attention,
)

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._cross_repo import load_manifest
from livespec_orchestrator_beads_fabro.commands._needs_attention_core_roots import (
    default_core_root_bases,
    resolve_spec_next_command,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import (
    plan_threads,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_spec_next_adapt import (
    adapt_top_candidate,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_work_items import (
    human_valves,
    impl_next,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.io import write_stdout
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items
from livespec_orchestrator_beads_fabro.types import WorkItem

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
    items = _load_work_items(project_root=project_root, work_items_path=work_items_path)
    manifest = load_manifest(project_root=project_root)
    materialized = list(materialize_work_items(records=iter(items)).values())
    index = {item.id: item for item in materialized}
    hygiene_scan = (
        scan_hygiene(repo_path=project_root, repo_name=repo_name) if include_hygiene else []
    )
    return (
        compose_needs_attention(
            repo=repo_name,
            spec_next=_spec_next(project_root=project_root),
            impl_next=impl_next(project_root=project_root, items=materialized, manifest=manifest),
            human_valve_lanes=human_valves(
                project_root=project_root,
                items=materialized,
                index=index,
                manifest=manifest,
            ),
            plan_threads=plan_threads(project_root=project_root),
            hygiene_scan=(),
        )
        + hygiene_scan
    )


def render_json(*, attention: list[AttentionItem]) -> str:
    return (
        json.dumps({"attention": [asdict(item) for item in attention]}, indent=2, sort_keys=True)
        + "\n"
    )


def render_markdown(*, attention: list[AttentionItem]) -> str:
    if not attention:
        return "No attention items.\n"
    lines = ["# Needs Attention", ""]
    for item in attention:
        lines.extend(
            [
                f"- `{item.id}` [{item.urgency}] {item.summary}",
                f"  - Handoff: `{item.handoff.command}`",
            ]
        )
    return "\n".join(lines) + "\n"


def _load_work_items(*, project_root: Path, work_items_path: str | None) -> list[WorkItem]:
    config = resolve_store_config(cwd=project_root, work_items_arg=work_items_path)
    return list(read_work_items(path=config.work_items_path))


_SPEC_NEXT_TIMEOUT_SECONDS = 60


@dataclass(frozen=True, slots=True, kw_only=True)
class _SpecNextResult:
    """Captured stdout + exit code from the spec-`next` CLI runner seam."""

    stdout: str
    returncode: int


class _ResolveSpecNextCommand(Protocol):
    """Seam: resolve the runnable spec-`next` argv, or None when unresolvable."""

    def __call__(self, *, project_root: Path) -> list[str] | None: ...


class _RunSpecNextCli(Protocol):
    """Seam: run a resolved argv and capture its stdout + exit code."""

    def __call__(self, *, argv: list[str]) -> _SpecNextResult: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class SpecNextSeam:
    """The injectable side-effecting seams of spec-`next` (defaulted to production).

    Mirrors `livespec_runtime.github_auth.mint.MintSeams`: a frozen bundle of
    the impure callables, defaulted to the real ones and overridden in unit
    tests so the adapt / fail-soft logic is covered without a live CORE
    checkout. The production defaults are integration-covered by the live
    `needs-attention` exercise, not by the hermetic unit suite.
    """

    resolve_command: _ResolveSpecNextCommand
    run: _RunSpecNextCli


def _default_resolve_command(*, project_root: Path) -> list[str] | None:  # pragma: no cover
    """The production `resolve_command` seam: resolve over the real HOME bases."""
    return resolve_spec_next_command(project_root=project_root, bases=default_core_root_bases())


def _run_spec_next_cli(*, argv: list[str]) -> _SpecNextResult:  # pragma: no cover
    """Production `run` seam: shell out to CORE's spec-`next` CLI.

    Mirrors `_beads_client._invoke` — the whole body is `# pragma: no cover`
    (integration-covered): it cannot run hermetically without a live CORE
    checkout. Fail-soft — any OS / subprocess error becomes a non-zero result.
    """
    completed = attempt(
        action=lambda: subprocess.run(  # noqa: S603
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=_SPEC_NEXT_TIMEOUT_SECONDS,
        ),
        exceptions=(OSError, subprocess.SubprocessError),
    )
    if isinstance(completed, AttemptFailure):
        return _SpecNextResult(stdout="", returncode=1)
    return _SpecNextResult(stdout=completed.stdout, returncode=completed.returncode)


DEFAULT_SPEC_NEXT_SEAM = SpecNextSeam(
    resolve_command=_default_resolve_command,
    run=_run_spec_next_cli,
)


def _spec_next(
    *,
    project_root: Path,
    seam: SpecNextSeam = DEFAULT_SPEC_NEXT_SEAM,
) -> SpecNextOutput | None:
    """Invoke CORE's spec-`next` CLI cross-plane and adapt its top candidate.

    Fail-soft by design: when CORE is unresolvable, the runner raises / exits
    non-zero, its stdout is unparseable, or the ranking is empty / only `none`,
    return None so `compose_needs_attention` drops the spec item entirely
    rather than emitting a useless "go run it yourself" pointer. `seam` is
    injectable (mirroring `MintSeams`) so unit tests exercise the adapt /
    fail-soft logic without a live CORE checkout.
    """
    result = attempt(
        action=lambda: _run_resolved_spec_next(seam=seam, project_root=project_root),
        exceptions=(OSError, subprocess.SubprocessError),
    )
    if isinstance(result, AttemptFailure) or result is None:
        return None
    if result.returncode != 0:
        return None
    return adapt_top_candidate(stdout=result.stdout, project_root=project_root)


def _run_resolved_spec_next(*, seam: SpecNextSeam, project_root: Path) -> _SpecNextResult | None:
    command = seam.resolve_command(project_root=project_root)
    if command is None:
        return None
    return seam.run(argv=[*command, "--project-root", str(project_root)])

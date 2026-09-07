"""Detection-staleness attention lanes derived from completed coverage points.

Two facts, both COMPUTED from the completed coverage records on the anchor and
never from a remembered "last run" timestamp:

- **Gap-capture staleness**, when the newest ratified spec revision is newer
  than the last completed gap-capture coverage point.
- **Drift staleness**, when default-branch merges since the last completed
  drift coverage point stand at or past the effective
  `dispatcher.drift_capture_merge_threshold`.

⛔ NEITHER FACT RUNS A DETECTOR, AND THAT IS A CONTRACT, NOT AN OPTIMISATION.
Both `capture-impl-gaps` and `capture-spec-drift` are consent-gated attended
dialogues; a composition that invoked one would convert an operator's owned
trigger into a headless run nobody consented to. What this module emits is a
SURFACED TRIGGER carrying a handoff that NAMES the skill to run — the operator
runs it, or does not.

The gap fact is deliberately a BACKSTOP, never a second binding. livespec
core's revise Step 13 post-step remains the one every-revise binding; this fact
exists for the runs Step 13 cannot guarantee — a skipped, interrupted or
bypassed post-step — and it clears the moment a complete pass records its
coverage point.

MERGE COUNTING EXCLUDES NOTHING SILENTLY. The count below is every commit on
the default branch since the coverage SHA, with no filter of any kind, and the
fact states that in its own summary. The wording is load-bearing under this
repository's rebase-merge discipline, where a landed pull request appears as
its rebased series rather than as one merge commit: a reader who assumed
"merges" meant merge commits would otherwise read a correct number as the
wrong quantity.

Both lanes fail SOFT on an unreadable input — an unresolvable default branch,
a git invocation that does not answer — rather than guessing a count. An
absent coverage point is a different thing and is NOT a failure: it means no
complete pass is on record, every revision and every merge is unaccounted for,
and the facts must fire.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._detection_coverage import (
    DRIFT_CAPTURE_OPERATION,
    GAP_CAPTURE_OPERATION,
    completed_coverage_point,
    detection_coverage_anchor,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    DEFAULT_DRIFT_CAPTURE_MERGE_THRESHOLD,
    resolve_drift_capture_merge_threshold,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.spec_reader import current_specification_version

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "DEFAULT_DETECTION_STALENESS_SEAMS",
    "DetectionStalenessSeams",
    "detection_staleness_items",
]

_SPEC_DIRNAME = "SPECIFICATION"
_GIT_TIMEOUT_SECONDS = 30.0
_MERGE_COUNTING_NOTE = (
    "Merge counting is every commit on the default branch since that point, "
    "with no class of commit excluded."
)


@dataclass(frozen=True, kw_only=True)
class DetectionStalenessSeams:
    """The impure seam this lane needs, defaulted to the production runner."""

    runner: CommandRunner


DEFAULT_DETECTION_STALENESS_SEAMS = DetectionStalenessSeams(runner=ShellCommandRunner())


def detection_staleness_items(
    *,
    project_root: Path,
    repo: str,
    config: StoreConfig,
    seams: DetectionStalenessSeams = DEFAULT_DETECTION_STALENESS_SEAMS,
) -> list[AttentionItem]:
    """Compose the gap-capture and drift staleness facts for this repository."""
    anchor = detection_coverage_anchor(cwd=project_root)
    return _gap_items(
        project_root=project_root, repo=repo, config=config, anchor=anchor
    ) + _drift_items(
        project_root=project_root, repo=repo, config=config, anchor=anchor, seams=seams
    )


def _gap_items(
    *, project_root: Path, repo: str, config: StoreConfig, anchor: str | None
) -> list[AttentionItem]:
    ratified = current_specification_version(spec_root=project_root / _SPEC_DIRNAME)
    recorded = completed_coverage_point(path=config, anchor=anchor, operation=GAP_CAPTURE_OPERATION)
    covered = _version_number(point=recorded)
    if ratified == 0 or ratified <= covered:
        return []
    summary = (
        f"Gap-capture coverage is stale for {repo}: ratified spec revision "
        f"v{ratified:03d} is newer than the last completed gap-capture coverage point "
        f"({recorded or 'none on record'}); stale range v{covered + 1:03d}..v{ratified:03d}. "
        "Run capture-impl-gaps over that range. This fact is the backstop to revise "
        "Step 13, never a second binding, and it never runs the detector itself."
    )
    return [
        _item(
            project_root=project_root,
            key="gap-capture-staleness",
            repo=repo,
            summary=summary,
            command=_handoff_command(
                project_root=project_root,
                operation=GAP_CAPTURE_OPERATION,
                argument=f"--since-version v{covered:03d}" if covered else "",
            ),
        )
    ]


def _drift_items(
    *,
    project_root: Path,
    repo: str,
    config: StoreConfig,
    anchor: str | None,
    seams: DetectionStalenessSeams,
) -> list[AttentionItem]:
    recorded = completed_coverage_point(
        path=config, anchor=anchor, operation=DRIFT_CAPTURE_OPERATION
    )
    threshold = unsafe_perform_io(
        resolve_drift_capture_merge_threshold(cwd=project_root).value_or(
            DEFAULT_DRIFT_CAPTURE_MERGE_THRESHOLD
        )
    )
    merges = _merge_count(project_root=project_root, runner=seams.runner, since=recorded)
    if merges is None or merges < threshold:
        return []
    summary = (
        f"Drift coverage is stale for {repo}: {merges} default-branch merge(s) since the "
        f"last completed drift coverage point ({recorded or 'none on record'}), at or past "
        f"the effective drift_capture_merge_threshold of {threshold}. Run capture-spec-drift; "
        f"the consent-gated dialogue stays the only way the detector runs. {_MERGE_COUNTING_NOTE}"
    )
    return [
        _item(
            project_root=project_root,
            key="drift-staleness",
            repo=repo,
            summary=summary,
            command=_handoff_command(
                project_root=project_root, operation=DRIFT_CAPTURE_OPERATION, argument=""
            ),
        )
    ]


def _version_number(*, point: str | None) -> int:
    if point is None:
        return 0
    digits = point.removeprefix("v")
    return int(digits) if digits.isdecimal() else 0


def _default_branch_ref(*, project_root: Path, runner: CommandRunner) -> str | None:
    """The local `origin/<default>` ref, resolved WITHOUT touching the forge.

    Deliberately not `resolve_default_branch`, whose second route shells out to
    `gh repo view`. That route is right for a dispatch preflight, which is
    already talking to the forge and can afford a network round trip; it is
    wrong HERE. This lane runs inside every `needs-attention` composition — an
    interactive operator surface — so a forge call would put an unbounded
    network wait in front of an inbox render, on behalf of one fact. A clone
    whose `refs/remotes/origin/HEAD` is unset simply yields no drift fact.
    """
    result = runner.run(
        argv=["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        cwd=project_root,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    resolved = result.stdout.strip()
    if result.exit_code != 0 or resolved == "":
        return None
    return resolved


def _merge_count(*, project_root: Path, runner: CommandRunner, since: str | None) -> int | None:
    ref = _default_branch_ref(project_root=project_root, runner=runner)
    if ref is None:
        return None
    argv = ["git", "rev-list", "--count", f"{since}..{ref}" if since else ref]
    result = runner.run(argv=argv, cwd=project_root, timeout_seconds=_GIT_TIMEOUT_SECONDS)
    counted = result.stdout.strip()
    if result.exit_code != 0 or not counted.isdecimal():
        return None
    return int(counted)


def _item(*, project_root: Path, key: str, repo: str, summary: str, command: str) -> AttentionItem:
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:{key}:{repo}",
        kind="hygiene",
        urgency="medium",
        summary=summary,
        source_ref=SourceRef(repo=repo),
        handoff=Handoff(kind="shell", command=command),
    )


def _handoff_command(*, project_root: Path, operation: str, argument: str) -> str:
    invocation = f"livespec-orchestrator-beads-fabro:{operation} {argument}".strip()
    return (
        f"cd {shlex.quote(str(project_root))} && codex exec {shlex.quote(invocation)} < /dev/null"
    )

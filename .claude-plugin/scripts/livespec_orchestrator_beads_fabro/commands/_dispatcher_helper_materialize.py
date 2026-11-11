"""The sandbox half of the helper fetch: compose, verify, then write every helper program.

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch", paragraph
"Helper programs are fetched in the sandbox from the dispatching build's own
commit". This module RUNS INSIDE THE SANDBOX, from a checkout of this plugin at
the manifest's commit: the helper-fetch setup step (`_dispatcher_helper_fetch`)
fetches that commit and calls `main` from it. So it is the FETCHED build's
materializer that composes the fetched build's helpers, through the fetched
build's own registry (`_dispatcher_helper_registry`), and the manifest the
Dispatcher wrote is the only thing it trusts from the run configuration.

NOTHING IS WRITTEN UNTIL EVERYTHING VERIFIES. Every manifest entry is composed and
digested first; the first entry that cannot be composed, or whose digest or mode
differs, ends the step with `LIVESPEC_PREPARE_PAYLOAD_DIGEST_MISMATCH: <helper>:
<reason>` and no file written. A registry entry the manifest does not name fails
the same way, because a helper the Dispatcher did not digest is one nothing
vouches for. Only then are the files written, each through a temporary file
renamed into place, and each written file's mode is read back.

A ROOT INSIDE THE RUN'S WORKTREE IS HIDDEN FROM IT FIRST. On the Petri-era engine
the run's clone IS `/workspace`, and each setup step is a graph node whose
checkpoint stages what the step left in the worktree, so a helper written under
`/workspace/...` would be committed into the run branch unless the clone's own
`info/exclude` names it before the step ends (`_dispatcher_sandbox_worktree_exclude`
records the incidents). Each written FILE is named, never its directory: the entry
lands in a governed repository's clone, and excluding a directory that repository
could track would hide its own content from git.
"""

from __future__ import annotations

import importlib
import json
import os
import stat
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner
from livespec_orchestrator_beads_fabro.io import write_stderr

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_registry import Helper

__all__: list[str] = [
    "HELPER_DIGEST_MISMATCH_CAUSE",
    "MaterializeRefusal",
    "main",
    "materialize",
    "parse_roots",
]

HELPER_DIGEST_MISMATCH_CAUSE = "LIVESPEC_PREPARE_PAYLOAD_DIGEST_MISMATCH"
_REGISTRY_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_helper_registry"
_MANIFEST_HELPER = "helper-manifest"
_GIT_TIMEOUT_SECONDS = 30.0
_MODE_BITS = 0o7777


@dataclass(frozen=True, kw_only=True)
class MaterializeRefusal:
    """Why one helper could not be materialized, in the setup step's failure-cause form."""

    helper: str
    reason: str

    def line(self) -> str:
        """`LIVESPEC_PREPARE_PAYLOAD_DIGEST_MISMATCH: <helper>: <reason>`."""
        return f"{HELPER_DIGEST_MISMATCH_CAUSE}: {self.helper}: {self.reason}"


@dataclass(frozen=True, kw_only=True)
class _Planned:
    name: str
    target: Path
    mode: int
    composed: bytes


def parse_roots(*, argv: Sequence[str]) -> dict[str, Path] | MaterializeRefusal:
    """`name=path` arguments into the named sandbox roots, each an absolute path."""
    roots: dict[str, Path] = {}
    for argument in argv:
        name, separator, path = argument.partition("=")
        if not separator or not name or not path.startswith("/"):
            return MaterializeRefusal(
                helper=_MANIFEST_HELPER,
                reason=f"sandbox root argument {argument!r} is not name=/absolute/path",
            )
        roots[name] = Path(path)
    return roots


def main(*, argv: Sequence[str], manifest_text: str) -> int:
    """Materialize the manifest read from standard input; 0 when every helper verified."""
    roots = parse_roots(argv=argv)
    outcome = (
        roots
        if isinstance(roots, MaterializeRefusal)
        else materialize(manifest_text=manifest_text, roots=roots)
    )
    if isinstance(outcome, MaterializeRefusal):
        write_stderr(text=outcome.line() + "\n")
        return 1
    write_stderr(text=f"livespec helper fetch: wrote and verified {outcome} helper programs\n")
    return 0


def materialize(*, manifest_text: str, roots: Mapping[str, Path]) -> int | MaterializeRefusal:
    """Compose and verify every manifest helper, then write them; the count written."""
    manifest = _manifest(text=manifest_text)
    if isinstance(manifest, MaterializeRefusal):
        return manifest
    commit = str(manifest["commit"])
    try:
        registry = importlib.import_module(_REGISTRY_MODULE)
    except ImportError as error:
        return MaterializeRefusal(
            helper="helper-registry",
            reason=f"the helper registry does not import at commit {commit}: {error}",
        )
    composed_helpers = cast("tuple[Helper, ...]", registry.helper_registry())
    planned = _plan(
        entries=cast("list[dict[str, Any]]", manifest["helpers"]),
        helpers={helper.name: helper for helper in composed_helpers},
        roots=roots,
        commit=commit,
        digest=cast("Callable[..., str]", registry.helper_digest),
    )
    if isinstance(planned, MaterializeRefusal):
        return planned
    _exclude_from_worktrees(targets=[entry.target for entry in planned])
    for entry in planned:
        refusal = _write(entry=entry)
        if refusal is not None:
            return refusal
    return len(planned)


def _manifest(*, text: str) -> dict[str, Any] | MaterializeRefusal:
    try:
        loaded = json.loads(text)
    except ValueError as error:
        return MaterializeRefusal(helper=_MANIFEST_HELPER, reason=f"is not JSON: {error}")
    document = cast("dict[str, Any]", loaded) if isinstance(loaded, dict) else {}
    if not isinstance(document.get("commit"), str) or not isinstance(document.get("helpers"), list):
        return MaterializeRefusal(
            helper=_MANIFEST_HELPER, reason="names no commit and no helper list"
        )
    return document


def _plan(
    *,
    entries: list[dict[str, Any]],
    helpers: Mapping[str, Helper],
    roots: Mapping[str, Path],
    commit: str,
    digest: Callable[..., str],
) -> list[_Planned] | MaterializeRefusal:
    """Every helper composed and checked against its manifest entry, or the first refusal."""
    planned: list[_Planned] = []
    for entry in entries:
        name = str(entry.get("name"))
        helper = helpers.get(name)
        if helper is None:
            return MaterializeRefusal(
                helper=name, reason=f"source path missing at commit {commit}: no such helper"
            )
        refusal = _entry_refusal(entry=entry, helper=helper, roots=roots)
        if refusal is not None:
            return refusal
        try:
            composed: bytes = helper.compose()
        except OSError as error:
            return MaterializeRefusal(
                helper=name, reason=f"source path missing at commit {commit}: {error}"
            )
        composed_digest = digest(composed=composed)
        if composed_digest != entry.get("sha256"):
            return MaterializeRefusal(
                helper=name,
                reason=(
                    f"composed digest {composed_digest} at commit {commit} differs from"
                    f" the manifest's {entry.get('sha256')}"
                ),
            )
        planned.append(
            _Planned(
                name=name,
                target=roots[helper.root] / helper.path,
                mode=helper.mode,
                composed=composed,
            )
        )
    named = {str(entry.get("name")) for entry in entries}
    unnamed = [name for name in helpers if name not in named]
    if unnamed:
        return MaterializeRefusal(
            helper=unnamed[0], reason=f"composed at commit {commit} but not in the helper manifest"
        )
    return planned


def _entry_refusal(
    *, entry: Mapping[str, Any], helper: Helper, roots: Mapping[str, Path]
) -> MaterializeRefusal | None:
    """Whether the manifest's root, path and mode for a helper are the registry's own."""
    name = str(entry.get("name"))
    if (entry.get("root"), entry.get("path")) != (helper.root, helper.path):
        return MaterializeRefusal(
            helper=name,
            reason=(
                f"manifest places it at {entry.get('root')}:{entry.get('path')}, the"
                f" registry at {helper.root}:{helper.path}"
            ),
        )
    if entry.get("mode") != helper.mode:
        return MaterializeRefusal(
            helper=name,
            reason=(
                f"manifest mode {entry.get('mode')!r} differs from the registry's {helper.mode:o}"
            ),
        )
    if helper.root not in roots:
        return MaterializeRefusal(
            helper=name, reason=f"its sandbox root {helper.root!r} was not resolved"
        )
    return None


def _write(*, entry: _Planned) -> MaterializeRefusal | None:
    """Write one helper through a renamed temporary file, then read its mode back."""
    entry.target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=entry.target.parent, prefix=".livespec-helper-")
    with os.fdopen(descriptor, "wb") as handle:
        _ = handle.write(entry.composed)
    written_path = Path(temporary)
    written_path.chmod(entry.mode)
    _ = written_path.replace(entry.target)
    written = stat.S_IMODE(entry.target.stat().st_mode) & _MODE_BITS
    if written != entry.mode:
        return MaterializeRefusal(
            helper=entry.name,
            reason=f"written with mode {written:o}, not the manifest's {entry.mode:o}",
        )
    return None


def _exclude_from_worktrees(*, targets: Sequence[Path]) -> None:
    """Name every target that lands inside a git worktree in that worktree's exclude file."""
    by_parent: dict[Path, list[Path]] = {}
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        by_parent.setdefault(target.parent.resolve(), []).append(target)
    exclude_files: dict[Path, Path | None] = {}
    for parent, members in by_parent.items():
        top = _worktree_top(directory=parent)
        if top is None:
            continue
        if top not in exclude_files:
            exclude_files[top] = _exclude_file(top=top)
        exclude_file = exclude_files[top]
        if exclude_file is None:
            continue
        for member in members:
            _append_entry(
                exclude_file=exclude_file, entry="/" + str((parent / member.name).relative_to(top))
            )


def _git(*, directory: Path, args: Sequence[str]) -> str | None:
    completed = ShellCommandRunner().run(
        argv=["git", "-C", str(directory), *args],
        cwd=directory,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    answer = completed.stdout.strip()
    return answer if completed.exit_code == 0 and answer else None


def _worktree_top(*, directory: Path) -> Path | None:
    top = _git(directory=directory, args=("rev-parse", "--show-toplevel"))
    return None if top is None else Path(top).resolve()


def _exclude_file(*, top: Path) -> Path | None:
    common = _git(directory=top, args=("rev-parse", "--git-common-dir"))
    if common is None:
        return None
    info = (top / common).resolve() / "info"
    info.mkdir(parents=True, exist_ok=True)
    return info / "exclude"


def _append_entry(*, exclude_file: Path, entry: str) -> None:
    present = (
        exclude_file.read_text(encoding="utf-8").splitlines() if exclude_file.is_file() else []
    )
    if entry in present:
        return
    with exclude_file.open("a", encoding="utf-8") as handle:
        _ = handle.write(entry + "\n")

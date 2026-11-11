"""WHICH build a dispatch's helper programs are fetched from, and whether the forge has it.

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch", paragraph
"Helper programs are fetched in the sandbox from the dispatching build's own
commit". The sandbox no longer receives the helper programs' source; it fetches
this plugin at one commit and composes them there. That commit is a fact about
the INSTALLED BUILD the Dispatcher executes, and this module owns reading it and
asking the forge for it.

THE IDENTITY IS THE INSTALL RECORD'S `gitCommitSha`, NOT `git rev-parse`. A
harness-installed build is a cache directory, a flattened copy of the commit's
`.claude-plugin/` tree that is not a git checkout, so `git rev-parse HEAD` there
answers for whatever repository happens to enclose it, or not at all. The record
whose `installPath` is the tree this process executes from names the commit
directly, and every cached install records one. The tree a retained payload was
copied from (`LIVESPEC_INSTALLED_PLUGIN_ROOT`) is tried second, because a copy
aside is not itself registered. Only a tree that is genuinely a checkout's
`.claude-plugin/` falls back to `git rev-parse HEAD`, and the prefix test is what
keeps an enclosing repository, a dotfiles checkout of `$HOME` for one, from
answering for a cache directory. A tree with none of the three has no identity,
and its dispatch is refused: there is no commit the sandbox could fetch.

THE PROBE IS A COMMIT-ONLY FETCH, NOT `ls-remote`. `git ls-remote <repo> <sha>`
matches REF NAMES, so it fails for every commit and refuses every dispatch. The
probe fetches exactly the commit object, with no trees and no tags, into a
scratch bare repository, measured at 0.52 s against the forge (research note
004); an unknown commit fails with `upload-pack: not our ref`. Any failure
refuses, including a network fault: the sandbox's own fetch of the same commit
would then fail too, after the claim, so refusing here is the cheaper outcome of
the same fault.

THE REFUSAL LANDS BEFORE THE CLAIM. `helper_build_reach_refusal` is a row of the
pre-dispatch wall, which runs after selection and before admission writes
`ready -> active`, so a build the sandbox could not fetch never strands a claimed
item. Its journal record names the repository and the commit, per item.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    RELEASE_REPOSITORY_URL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    INSTALLED_ROOT_ENV,
    executing_payload_root,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_install_registry import (
    default_plugin_install_registry,
    installed_build_commit,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "HELPER_BUILD_REACH_STAGE",
    "BuildReachReading",
    "HelperSource",
    "helper_build_reach_refusal",
    "probe_build_commit",
    "read_helper_source",
]

HELPER_BUILD_REACH_STAGE = "helper-build-reach"
# The checkout prefix a source tree's executing root must have for `git rev-parse`
# to be answering for THIS plugin's tree rather than for an enclosing repository.
_CHECKOUT_PREFIX = ".claude-plugin/"
_GIT_TIMEOUT_SECONDS = 30.0
_PROBE_TIMEOUT_SECONDS = 60.0
_DETAIL_CHARS = 400


@dataclass(frozen=True, kw_only=True)
class HelperSource:
    """The forge repository and the exact commit a dispatch's helpers are fetched from."""

    repository: str
    commit: str


@dataclass(frozen=True, kw_only=True)
class BuildReachReading:
    """Whether the forge serves one commit, and the probe's own words when it does not."""

    reachable: bool
    detail: str


def read_helper_source(
    *,
    runner: CommandRunner,
    environ: Mapping[str, str] | None = None,
    payload_root: Path | None = None,
    install_record: Path | None = None,
) -> HelperSource | None:
    """The installed build's repository and commit, or None when it has no identity.

    Each argument defaults to the production value and exists so a test can point
    the read at a registry and a tree of its own.
    """
    env = os.environ if environ is None else environ
    root = executing_payload_root() if payload_root is None else payload_root
    registry = default_plugin_install_registry() if install_record is None else install_record
    recorded = env.get(INSTALLED_ROOT_ENV, "").strip()
    roots = (root, Path(recorded)) if recorded else (root,)
    commit = installed_build_commit(install_roots=roots, install_record=registry)
    if commit is None:
        commit = _checkout_commit(root=root, runner=runner)
    if commit is None:
        return None
    return HelperSource(repository=RELEASE_REPOSITORY_URL, commit=commit)


def _checkout_commit(*, root: Path, runner: CommandRunner) -> str | None:
    """`HEAD` of the checkout whose `.claude-plugin/` tree `root` is, else None."""
    if not root.is_dir():
        return None
    answered = runner.run(
        argv=["git", "-C", str(root), "rev-parse", "--show-prefix", "HEAD"],
        cwd=root,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    lines = answered.stdout.splitlines()
    if answered.exit_code != 0 or len(lines) != 2 or lines[0] != _CHECKOUT_PREFIX:  # noqa: PLR2004 — the two lines `--show-prefix HEAD` prints.
        return None
    return lines[1].strip() or None


def probe_build_commit(*, source: HelperSource, runner: CommandRunner) -> BuildReachReading:
    """Fetch exactly `source.commit` from `source.repository` into a scratch bare repository."""
    with tempfile.TemporaryDirectory(prefix="livespec-build-reach-") as scratch:
        scratch_path = Path(scratch)
        initialized = runner.run(
            argv=["git", "init", "--bare", "--quiet", scratch],
            cwd=scratch_path,
            timeout_seconds=_GIT_TIMEOUT_SECONDS,
        )
        if initialized.exit_code != 0:
            return BuildReachReading(
                reachable=False, detail=f"no scratch repository: {initialized.stderr.strip()}"
            )
        fetched = runner.run(
            argv=[
                "git",
                "-C",
                scratch,
                "fetch",
                "--quiet",
                "--depth=1",
                "--filter=tree:0",
                "--no-tags",
                source.repository,
                source.commit,
            ],
            cwd=scratch_path,
            timeout_seconds=_PROBE_TIMEOUT_SECONDS,
            env={"GIT_TERMINAL_PROMPT": "0"},
        )
    detail = (fetched.stderr.strip() or fetched.stdout.strip())[-_DETAIL_CHARS:]
    return BuildReachReading(reachable=fetched.exit_code == 0, detail=detail)


def helper_build_reach_refusal(*, items: Sequence[WorkItem], journal: JournalFile) -> str | None:
    """The wall-facing row: one identity, one probe, one refusal, one record per item.

    An EMPTY selection returns before anything is read, because the drain reaches
    the wall on every idle pass and a forge read there answers nothing.
    """
    if not items:
        return None
    runner = ShellCommandRunner()
    source = read_helper_source(runner=runner)
    if source is None:
        refusal = (
            "livespec-orchestrator-beads-fabro dispatcher: refusing dispatch: the installed"
            " plugin build records no commit (no install record names the tree it executes"
            f" from, {executing_payload_root()}, and that tree is no checkout), so the"
            " sandbox has no commit to fetch its helper programs from"
        )
        _journal(items=items, journal=journal, source=None, detail=refusal)
        return refusal
    reading = probe_build_commit(source=source, runner=runner)
    if reading.reachable:
        return None
    _journal(items=items, journal=journal, source=source, detail=reading.detail)
    return (
        "livespec-orchestrator-beads-fabro dispatcher: refusing dispatch: the installed"
        f" plugin build commit {source.commit} is not reachable on the forge at"
        f" {source.repository}, so the sandbox could not fetch its helper programs"
        f" from it: {reading.detail}"
    )


def _journal(
    *,
    items: Sequence[WorkItem],
    journal: JournalFile,
    source: HelperSource | None,
    detail: str,
) -> None:
    for item in items:
        journal.append(
            record={
                "stage": HELPER_BUILD_REACH_STAGE,
                "work_item_id": item.id,
                "repository": None if source is None else source.repository,
                "commit": None if source is None else source.commit,
                "reachable": False,
                "detail": detail,
            }
        )

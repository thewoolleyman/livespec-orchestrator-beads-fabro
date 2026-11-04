"""Run one host Definition-of-Done judge without its interactive setup.

The executable is resolved from the invoking environment BEFORE the candidate is
isolated.  That order is material: a host's Codex command can be a wrapper in
the operator's home directory.  The candidate can then use its private home
without preventing the launcher from finding that executable.

The candidate itself runs from an empty scratch directory that is not inside any
Git worktree.  The governed repository is therefore available only through the
explicit ``--add-dir`` grant.  Codex receives a fresh ``CODEX_HOME`` containing
at most its copied ``auth.json``, so none of the invoking profile's
configuration, skills or project instructions reach the judgement.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.effects import attempt

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__: list[str] = ["IsolatedLaunch", "isolated_launch", "resolve_codex_path"]

_CODEX_EXECUTABLE = "codex"
_PROMPT_FILE_PREFIX = "livespec-dod-gate-"
_SCRATCH_PARENT_NAMES = ("tmp", "var/tmp")
_NO_SCRATCH_DIRECTORY = "no non-repository scratch directory is available for host judgement"
_PROFILE_ENVIRONMENT = (
    "BASH_ENV",
    "ENV",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
)


def resolve_codex_path(*, environ: dict[str, str]) -> str:
    """Resolve Codex on the invoking PATH before its configuration is isolated."""
    found = shutil.which(_CODEX_EXECUTABLE, path=environ.get("PATH"))
    return found if found is not None else _CODEX_EXECUTABLE


@dataclass(frozen=True, kw_only=True)
class IsolatedLaunch:
    """Where and how one isolated candidate is launched."""

    cwd: Path
    environ: dict[str, str]
    stdin: int


@contextmanager
def isolated_launch(
    *,
    is_codex: bool,
    prompt: str,
    candidate_environ: dict[str, str],
    ambient_environ: dict[str, str],
) -> Iterator[IsolatedLaunch]:
    """Yield the scratch working directory, environment and prompt descriptor.

    The scratch directory and the prompt file live only for the duration of the
    ``with`` block.
    """
    with _non_repository_scratch_directory() as scratch:
        environ = _isolated_environ(
            is_codex=is_codex,
            environ=candidate_environ,
            ambient_environ=ambient_environ,
            scratch=scratch,
        )
        prompt_path = scratch / "prompt.txt"
        _ = prompt_path.write_text(prompt, encoding="utf-8")
        with prompt_path.open("rb") as handle:
            yield IsolatedLaunch(cwd=scratch, environ=environ, stdin=handle.fileno())


@contextmanager
def _non_repository_scratch_directory() -> Iterator[Path]:
    """Yield scratch storage outside every Git worktree, despite an ambient TMPDIR."""
    for parent in _scratch_parent_candidates():
        try:
            scratch = tempfile.TemporaryDirectory(prefix=_PROMPT_FILE_PREFIX, dir=parent)
        except OSError:
            continue
        try:
            scratch_path = Path(scratch.name)
            if _inside_git_worktree(directory=scratch_path):
                continue
            yield scratch_path
            return
        finally:
            scratch.cleanup()
    raise RuntimeError(_NO_SCRATCH_DIRECTORY)


def _scratch_parent_candidates() -> tuple[Path, ...]:
    """Return distinct usable standard temporary parents before the ambient one."""
    standard = tuple(Path(os.sep) / name for name in _SCRATCH_PARENT_NAMES)
    candidates = (*standard, Path(tempfile.gettempdir()))
    return tuple(dict.fromkeys(parent for parent in candidates if parent.is_dir()))


def _inside_git_worktree(*, directory: Path) -> bool:
    """Whether Git finds a worktree at or above ``directory`` by parent traversal."""
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "-C", str(directory), "rev-parse", "--is-inside-work-tree"],  # noqa: S607
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def _isolated_environ(
    *,
    is_codex: bool,
    environ: dict[str, str],
    ambient_environ: dict[str, str],
    scratch: Path,
) -> dict[str, str]:
    """Return one candidate environment with the required private state."""
    isolated = dict(environ)
    private_home = scratch / "home"
    private_home.mkdir()
    isolated["HOME"] = str(private_home)
    isolated["ZDOTDIR"] = str(private_home)
    for name in _PROFILE_ENVIRONMENT:
        _ = isolated.pop(name, None)
    if not is_codex:
        return isolated
    codex_home = scratch / "codex-home"
    codex_home.mkdir()
    _copy_codex_auth(ambient_environ=ambient_environ, destination=codex_home / "auth.json")
    isolated["CODEX_HOME"] = str(codex_home)
    return isolated


def _copy_codex_auth(*, ambient_environ: dict[str, str], destination: Path) -> None:
    """Copy only the invoking Codex authentication file when it exists."""
    configured_home = ambient_environ.get("CODEX_HOME", "").strip()
    source_home = (
        Path(configured_home)
        if configured_home
        else Path(ambient_environ.get("HOME", str(Path.home()))) / ".codex"
    )
    source = source_home / "auth.json"
    if source.is_file():
        _ = attempt(
            action=lambda: shutil.copyfile(source, destination),
            exceptions=(OSError,),
        )

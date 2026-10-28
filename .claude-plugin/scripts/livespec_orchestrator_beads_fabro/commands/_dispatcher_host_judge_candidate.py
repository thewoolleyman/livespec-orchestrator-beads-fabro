"""Run one host Definition-of-Done judge without its interactive setup.

The executable is resolved from the invoking environment BEFORE the candidate is
isolated.  That order is material: a host's Codex command can be a wrapper in
the operator's home directory, and replacing ``HOME`` before resolving or
starting it turns an otherwise valid judge into an exit-127 fallback.

The candidate itself runs from an empty scratch directory.  The governed
repository is therefore available only through the explicit ``--add-dir``
grant.  Codex receives a fresh ``CODEX_HOME`` containing at most its copied
``auth.json``; Claude's command-line switches decline all interactive settings,
MCP configuration, slash commands, and session persistence.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    select_factory_credential,
)
from livespec_orchestrator_beads_fabro.effects import attempt

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandResult,
        CommandRunner,
    )

__all__: list[str] = [
    "judgement_argv",
    "resolve_judge_path",
    "run_host_judge_candidate",
]

_CLAUDE_AGENT = "claude-acp"
_CODEX_AGENT = "codex-acp"
_CODEX_EXECUTABLE = "codex"
_CODEX_SANDBOX_SETTINGS = frozenset({"sandbox_mode", "approval_policy"})
_CODEX_ISOLATION_SETTINGS = (
    "project_doc_max_bytes=0",
    "features.skills=false",
    "features.multi_agent=false",
)
_JUDGE_EXECUTABLE = "claude"
_JUDGE_PATH_ENV = "LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH"
_CONVENTIONAL_JUDGE_PATH = "~/.local/bin/claude"
_ALLOWED_TOOLS = "Read,Grep,Glob"
_PROMPT_FILE_PREFIX = "livespec-dod-gate-"
_SCRATCH_PARENT_NAMES = ("tmp", "var/tmp")
_NO_SCRATCH_DIRECTORY = "no non-repository scratch directory is available for host judgement"


def judgement_argv(*, judge_path: str, model: str) -> list[str]:
    """The Claude host-judge invocation, with its prompt supplied on standard input."""
    return [
        judge_path,
        "-p",
        "--allowedTools",
        _ALLOWED_TOOLS,
        "--model",
        model,
    ]


def resolve_judge_path(
    *,
    environ: dict[str, str],
    which: Callable[[str], str | None] = shutil.which,
    conventional: Path | None = None,
) -> str:
    """Resolve Claude from the invoking environment before candidate isolation."""
    override = environ.get(_JUDGE_PATH_ENV, "").strip()
    if override:
        return override
    found = which(_JUDGE_EXECUTABLE)
    if found is not None:
        return found
    local_bin = (
        Path(_CONVENTIONAL_JUDGE_PATH).expanduser() if conventional is None else conventional
    )
    if local_bin.is_file():
        return str(local_bin)
    return _JUDGE_EXECUTABLE


def run_host_judge_candidate(
    *,
    candidate: AcpCandidate,
    prompt: str,
    allowed_directory: Path,
    runner: CommandRunner,
    environ: dict[str, str],
    timeout_seconds: float,
) -> CommandResult:
    """Run one resolved candidate from a non-repository scratch directory."""
    argv, candidate_environ = _candidate_command(
        candidate=candidate,
        environ=environ,
        allowed_directory=allowed_directory,
    )
    with _non_repository_scratch_directory() as scratch_path:
        judge_environ = _isolated_judge_environ(
            candidate=candidate,
            environ=candidate_environ,
            ambient_environ=environ,
            scratch=scratch_path,
        )
        prompt_path = scratch_path / "prompt.txt"
        _ = prompt_path.write_text(prompt, encoding="utf-8")
        with prompt_path.open("rb") as handle:
            return runner.run(
                argv=argv,
                cwd=scratch_path,
                timeout_seconds=timeout_seconds,
                env=judge_environ,
                stdin=handle.fileno(),
            )


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


def _candidate_command(
    *, candidate: AcpCandidate, environ: dict[str, str], allowed_directory: Path
) -> tuple[list[str], dict[str, str]]:
    """Build one candidate command while its ambient executable remains available."""
    judge_environ = {**environ, **candidate.adapter.env}
    if candidate.agent_id == _CODEX_AGENT:
        settings = _codex_settings(candidate=candidate)
        model = settings.pop("model", "")
        argv = [resolve_codex_path(environ=environ), "exec", "-m", model]
        for key, value in settings.items():
            argv.extend(("-c", f"{key}={json.dumps(value)}"))
        for setting in _CODEX_ISOLATION_SETTINGS:
            argv.extend(("-c", setting))
        argv.extend(
            (
                "--add-dir",
                str(allowed_directory),
                "-s",
                "read-only",
                "--skip-git-repo-check",
            )
        )
        return argv, judge_environ
    if candidate.agent_id == _CLAUDE_AGENT:
        model = candidate.adapter.env.get("ANTHROPIC_MODEL", "")
        credential = select_factory_credential(
            environ=environ,
            home=Path(environ.get("HOME", str(Path.home()))),
            warn=lambda message: sys.stderr.write(f"{message}\n"),
        )
        judge_environ[CLAUDE_OAUTH_TOKEN_ENV] = environ.get(credential.env_name, "")
        argv = judgement_argv(judge_path=resolve_judge_path(environ=environ), model=model)
        argv.extend(
            (
                "--add-dir",
                str(allowed_directory),
                "--setting-sources",
                "",
                "--managed-settings",
                "{}",
                "--disable-slash-commands",
                "--strict-mcp-config",
                "--no-session-persistence",
            )
        )
        return argv, judge_environ
    return [candidate.adapter.command, *candidate.adapter.args], judge_environ


def _isolated_judge_environ(
    *,
    candidate: AcpCandidate,
    environ: dict[str, str],
    ambient_environ: dict[str, str],
    scratch: Path,
) -> dict[str, str]:
    """Return one candidate environment without replacing its executable's HOME."""
    isolated = dict(environ)
    if candidate.agent_id != _CODEX_AGENT:
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


def resolve_codex_path(*, environ: dict[str, str]) -> str:
    """Resolve Codex on the invoking PATH before its configuration is isolated."""
    found = shutil.which(_CODEX_EXECUTABLE, path=environ.get("PATH"))
    return found if found is not None else _CODEX_EXECUTABLE


def _codex_settings(*, candidate: AcpCandidate) -> dict[str, str]:
    """Read the candidate's string Codex settings, excluding sandbox-local ones."""
    raw = candidate.adapter.env.get("CODEX_CONFIG", "")
    try:
        decoded: object = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    payload = cast("dict[str, object]", decoded)
    return {
        key: value
        for key, value in payload.items()
        if key not in _CODEX_SANDBOX_SETTINGS and isinstance(value, str)
    }

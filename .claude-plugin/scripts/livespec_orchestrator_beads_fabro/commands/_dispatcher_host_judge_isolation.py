"""Isolation of one-shot host judgement candidates from interactive agent state."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.effects import attempt

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate

__all__: list[str] = [
    "CLAUDE_AGENT_ID",
    "CODEX_AGENT_ID",
    "CODEX_ISOLATION_SETTINGS",
    "copy_codex_auth",
    "isolated_judge_environ",
    "resolve_judge_path",
]

CLAUDE_AGENT_ID = "claude-acp"
CODEX_AGENT_ID = "codex-acp"
CODEX_ISOLATION_SETTINGS = (
    "project_doc_max_bytes=0",
    "features.skills=false",
    "features.multi_agent=false",
)
_JUDGE_PATH_ENV = "LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH"
_JUDGE_EXECUTABLE = "claude"
_CONVENTIONAL_JUDGE_PATH = "~/.local/bin/claude"


def resolve_judge_path(
    *,
    environ: dict[str, str],
    which: Callable[[str], str | None] = shutil.which,
    conventional: Path | None = None,
) -> str:
    """Resolve the host judge executable without separately probing its health."""
    override = environ.get(_JUDGE_PATH_ENV, "").strip()
    if override:
        return override
    found = which(_JUDGE_EXECUTABLE)
    if found is not None:
        return found
    local_bin = (
        Path(_CONVENTIONAL_JUDGE_PATH).expanduser() if conventional is None else conventional
    )
    return str(local_bin) if local_bin.is_file() else _JUDGE_EXECUTABLE


def isolated_judge_environ(
    *, candidate: AcpCandidate, environ: dict[str, str], scratch: Path
) -> dict[str, str]:
    """Return the candidate environment rooted in a fresh per-taking agent home.

    A host judge may retain its authentication but not its interactive state. Its
    empty home and agent-specific configuration directory make user-level hooks,
    plugins, MCP registrations, sessions and instructions unreachable; the
    candidate command grants the governed repository explicitly for the read-only
    tools the judgement names.
    """
    isolated = dict(environ)
    home = scratch / "home"
    home.mkdir()
    isolated["HOME"] = str(home)
    if candidate.agent_id == CLAUDE_AGENT_ID:
        claude_config = scratch / "claude-config"
        claude_config.mkdir()
        isolated["CLAUDE_CONFIG_DIR"] = str(claude_config)
    if candidate.agent_id == CODEX_AGENT_ID:
        codex_home = scratch / "codex-home"
        codex_home.mkdir()
        copy_codex_auth(environ=environ, destination=codex_home / "auth.json")
        isolated["CODEX_HOME"] = str(codex_home)
    return isolated


def copy_codex_auth(*, environ: dict[str, str], destination: Path) -> None:
    """Copy only the ambient Codex credential into an otherwise empty home."""
    configured_home = environ.get("CODEX_HOME", "")
    source_home = Path(configured_home) if configured_home else Path.home() / ".codex"
    source = source_home / "auth.json"
    if source.is_file():
        _ = attempt(
            action=lambda: shutil.copyfile(source, destination),
            exceptions=(OSError,),
        )

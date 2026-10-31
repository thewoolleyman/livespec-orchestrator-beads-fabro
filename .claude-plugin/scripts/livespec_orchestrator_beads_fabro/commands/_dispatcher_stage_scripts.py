"""Build-pinned delivery of the committed publication-stage scripts."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import plugin_root

__all__: list[str] = [
    "resolve_stage_scripts_build_sha",
    "stage_scripts_prepare_steps_block",
]

_REPOSITORY = "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git"
_SHA = re.compile(r"^[0-9a-f]{40}$")


def resolve_stage_scripts_build_sha() -> str | None:  # pragma: no cover - host-install seam
    """Resolve the executing plugin build, refusing an unidentifiable install."""
    root = plugin_root().resolve()
    registry = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    try:
        decoded: object = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        decoded = {}
    payload = cast("dict[str, object]", decoded) if isinstance(decoded, dict) else {}
    plugins = payload.get("plugins")
    if isinstance(plugins, dict):
        for key, entries in cast("dict[str, object]", plugins).items():
            if key.split("@", 1)[0] != "livespec-orchestrator-beads-fabro":
                continue
            if not isinstance(entries, list):
                continue
            for entry in cast("list[object]", entries):
                if not isinstance(entry, dict):
                    continue
                entry_fields = cast("dict[str, object]", entry)
                install = entry_fields.get("installPath")
                sha = entry_fields.get("gitCommitSha")
                if (
                    isinstance(install, str)
                    and isinstance(sha, str)
                    and _same_path(left=Path(install), right=root)
                    and _SHA.fullmatch(sha)
                ):
                    return sha
    return _clean_checkout_sha(root=root)


def stage_scripts_prepare_steps_block(*, build_sha: str | None) -> str | None:
    """Fetch this build's four committed scripts into the sandbox, or refuse."""
    if build_sha == "":
        return ""
    if build_sha is None or _SHA.fullmatch(build_sha) is None:
        return None
    script = (
        "set -eu\n"
        "mkdir -p /livespec-stage-scripts\n"
        "git init -q /livespec-stage-scripts.git\n"
        "GIT_TERMINAL_PROMPT=0 git -C /livespec-stage-scripts.git fetch -q --depth 1 "
        f"{_REPOSITORY} {build_sha}\n"
        "git -C /livespec-stage-scripts.git archive FETCH_HEAD "
        ".claude-plugin/.fabro/workflows/implement-work-item/stages | "
        "tar -x --strip-components=5 -C /livespec-stage-scripts\n"
        "chmod 700 /livespec-stage-scripts/*.sh"
    )
    return "\n[[run.prepare.steps]]\nscript = " + json.dumps(script) + "\n"


def _same_path(*, left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right
    except OSError:  # pragma: no cover - a broken host path cannot be constructed portably
        return False


def _clean_checkout_sha(*, root: Path) -> str | None:  # pragma: no cover - host-install seam
    status = _git(root=root, args=("status", "--porcelain"))
    if status is None or status != "":
        return None
    sha = _git(root=root, args=("rev-parse", "HEAD"))
    if sha is None or _SHA.fullmatch(sha) is None:
        return None
    remote = _git(root=root, args=("ls-remote", "origin", sha))
    return sha if remote is not None and remote.startswith(sha) else None


def _git(
    *, root: Path, args: tuple[str, ...]
) -> str | None:  # pragma: no cover - host-install seam
    done = subprocess.run(  # noqa: S603 - fixed executable and validated local Git arguments
        ["/usr/bin/git", "-C", str(root), *args], capture_output=True, check=False, text=True
    )
    return done.stdout.strip() if done.returncode == 0 else None

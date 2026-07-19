"""Local gate for the codex-YOLO SessionStart re-apply hook.

The re-apply hook mutates a third-party plugin cache, so it must be ON only for
repos the maintainer intentionally covers: fleet members, official adopters, or
an explicit local operator override. SessionStart must stay local-only and
fail-open, so fleet membership is read from a committed marker in
`.livespec.jsonc`; the manifest-derived refresh path is explicit and tested.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal, cast

try:
    from livespec_dev_tooling.fleet._context import resolve_owner
    from livespec_dev_tooling.fleet.contract import parse_manifest
except ImportError:  # pragma: no cover - deployments may lack dev tooling.
    resolve_owner = None  # type: ignore[assignment]
    parse_manifest = None  # type: ignore[assignment]

__all__: list[str] = [
    "CONFIG_FILENAME",
    "ENV_OVERRIDE",
    "GateState",
    "derive_fleet_listed",
    "gate_state",
    "main",
    "owning_repo_root",
    "read_marker",
    "remote_url_for_repo",
    "repo_name_from_remote_url",
    "with_marker",
]

GateState = Literal["on", "off"]

CONFIG_FILENAME: str = ".livespec.jsonc"
ENV_OVERRIDE: str = "LIVESPEC_CODEX_FULL_ACCESS"
_MARKER_KEY: str = "codex_full_access"
_FLEET_LISTED_KEY: str = "fleet_listed"
_REMOTE_URL_PATTERN = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:)(?:[^/]+)/([^/]+?)(?:\.git)?/?$"
)


def owning_repo_root() -> Path:
    """The consuming project root for the SessionStart hook.

    A repo-local hook can infer the project from this module's file path, but a
    plugin-shipped hook cannot: `__file__` lives in Claude's plugin cache, not
    the project that enabled the plugin. Claude already supplies the consuming
    project root as `CLAUDE_PROJECT_DIR`, so prefer that seam and keep the old
    file-anchored path only as the no-env fallback.
    """
    return _project_root_from_env(env=dict(os.environ)) or _repo_local_root_from_file()


def gate_state(*, env: dict[str, str] | None = None, repo: Path | None = None) -> GateState:
    """Return whether the codex full-access patch is locally enabled."""
    environment = env if env is not None else dict(os.environ)
    override = _truthy_or_falsey(value=environment.get(ENV_OVERRIDE))
    if override is True:
        return "on"
    if override is False:
        return "off"
    marker_repo = repo if repo is not None else (_project_root_from_env(env=environment) or owning_repo_root())
    return "on" if read_marker(repo=marker_repo) else "off"


def read_marker(*, repo: Path) -> bool:
    """Read the committed `.livespec.jsonc` marker; malformed or absent is OFF."""
    config = repo / CONFIG_FILENAME
    try:
        raw = config.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        root = json.loads(_strip_jsonc_comments(text=raw))
    except json.JSONDecodeError:
        return False
    if not isinstance(root, dict):
        return False
    block = cast("dict[str, Any]", root).get(_MARKER_KEY)
    if not isinstance(block, dict):
        return False
    return _truthy_or_falsey(value=block.get(_FLEET_LISTED_KEY)) is True


def derive_fleet_listed(*, manifest_source: str, owner: str | None, repo: str | None) -> bool:
    """Derive the local marker value from the core fleet manifest contract."""
    if parse_manifest is None or owner is None or repo is None:
        return False
    manifest = parse_manifest(source=manifest_source)
    if manifest is None or owner != manifest.owner:
        return False
    listed = set(manifest.member_names())
    listed.update(adopter.repo for adopter in manifest.adopters)
    return repo in listed


def repo_name_from_remote_url(*, remote_url: str) -> str | None:
    """Return the GitHub repo name from a canonical origin URL, or None."""
    match = _REMOTE_URL_PATTERN.match(remote_url.strip())
    if match is None:
        return None
    return match.group(1)


def with_marker(*, config_text: str, fleet_listed: bool) -> str:
    """Return `config_text` with an up-to-date top-level codex marker block."""
    block = (
        '  "codex_full_access": {\n'
        f'    "fleet_listed": {str(fleet_listed).lower()}\n'
        "  }"
    )
    existing = re.compile(r'(?ms)^  "codex_full_access": \{\n.*?^  \}(,?)\n')
    if existing.search(config_text):
        return existing.sub(f"{block}\\1\n", config_text, count=1)
    marker = '  "implementation":'
    index = config_text.find(marker)
    if index == -1:
        return _insert_before_final_brace(config_text=config_text, block=block)
    line_end = config_text.find("\n", index)
    if line_end == -1:
        return _insert_before_final_brace(config_text=config_text, block=block)
    implementation_line = config_text[index : line_end + 1]
    suffix = config_text[line_end + 1 :]
    prefix_comma = "" if implementation_line.rstrip().endswith(",") else ","
    suffix_comma = "" if suffix.lstrip().startswith("}") else ","
    return f"{config_text[:line_end]}{prefix_comma}\n{block}{suffix_comma}\n{suffix}"


def main(*, argv: list[str] | None = None) -> int:
    """Refresh the local marker from a checked-out core manifest."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "refresh":
        return 2
    repo = Path.cwd()
    manifest_path = Path(args[1])
    try:
        manifest_source = manifest_path.read_text(encoding="utf-8")
        remote_url = remote_url_for_repo(repo=repo)
        config_path = repo / CONFIG_FILENAME
        config_text = config_path.read_text(encoding="utf-8")
    except OSError:
        return 0
    owner = None if resolve_owner is None else resolve_owner(cwd=repo)
    listed = derive_fleet_listed(
        manifest_source=manifest_source,
        owner=owner,
        repo=repo_name_from_remote_url(remote_url=remote_url),
    )
    _ = config_path.write_text(with_marker(config_text=config_text, fleet_listed=listed), encoding="utf-8")
    return 0


def _truthy_or_falsey(*, value: object) -> bool | None:
    """Map accepted gate tokens to bool; unknown values mean unset."""
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true"}:
        return True
    if normalized in {"0", "false"}:
        return False
    return None


def _project_root_from_env(*, env: dict[str, str]) -> Path | None:
    """Resolve Claude's consuming-project root env var without raising."""
    raw = env.get("CLAUDE_PROJECT_DIR")
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve()
    except (OSError, RuntimeError):
        return Path(raw).expanduser()


def _repo_local_root_from_file() -> Path:
    """Best-effort repo-local fallback for non-plugin/manual execution."""
    try:
        return Path(__file__).resolve().parents[2]
    except (IndexError, OSError, RuntimeError):
        try:
            return Path.cwd()
        except OSError:
            return Path(".")


def _strip_jsonc_comments(*, text: str) -> str:
    """Remove `//` comments while preserving comment-like text in strings."""
    result: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            index = text.find("\n", index)
            if index == -1:
                break
            result.append("\n")
            index += 1
            continue
        result.append(char)
        index += 1
    return "".join(result)


def _insert_before_final_brace(*, config_text: str, block: str) -> str:
    """Insert the marker before the final top-level brace."""
    index = config_text.rfind("}")
    if index == -1:
        return config_text
    prefix = config_text[:index].rstrip()
    separator = "," if prefix.endswith("}") or prefix.endswith('"') else ""
    suffix = config_text[index:]
    return f"{prefix}{separator}\n{block}\n{suffix}"


def remote_url_for_repo(*, repo: Path, run: Any = subprocess.run) -> str:
    """Return `git remote get-url origin` output, or an empty string on failure."""
    completed = run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(repo),
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())

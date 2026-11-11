"""Pinned, digest-checked dispatch helpers.

The overlay carries this manifest and a short fetch command, never a helper's
source.  The sandbox checks out the exact dispatcher build, invokes the same
composers that made the manifest, and refuses before an agent stage when the
bytes differ.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, TypedDict, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_carry_forward_program import (
    CARRY_FORWARD_PROGRAM_FILENAME,
    carry_forward_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_limit_program import (
    HOOK_LIMIT_PROGRAM_FILENAME,
    hook_limit_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_implement_commit_programs import (
    COMMIT_GREEN_PROGRAM_FILENAME,
    COMMIT_RED_PROGRAM_FILENAME,
    commit_green_program_source,
    commit_red_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import executing_payload_root
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    PrepareStep,
    render_prepare_step,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_grade_program import (
    PROOF_GRADE_PROGRAM_FILENAME,
    PROOF_GRADE_READER_DIRECTORY,
    proof_grade_program_source,
    proof_record_reader_sources,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_head import (
    PROOF_HEAD_PROGRAM_FILENAME,
    proof_head_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    PUBLICATION_PUSH_PROGRAM_FILENAME,
    publication_push_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_merge import (
    RECORD_FILE_MERGE_PROGRAM_FILENAME,
    record_file_merge_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_regeneration import (
    RECORD_FILE_PROGRAM_FILENAME,
    record_file_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_guard import (
    REVIEW_GUARD_PROGRAM_FILENAME,
    review_guard_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)

__all__: list[str] = [
    "HELPER_DIGEST_MISMATCH_CAUSE",
    "HELPER_MANIFEST_ENV",
    "HelperSource",
    "dispatch_helper_source",
    "helper_fetch_prepare_steps_block",
    "helper_manifest",
    "helper_source_is_reachable",
    "materialize_helpers",
    "materialize_helpers_from_environment",
]

HELPER_DIGEST_MISMATCH_CAUSE = "LIVESPEC_PREPARE_PAYLOAD_DIGEST_MISMATCH"
HELPER_MANIFEST_ENV = "LIVESPEC_DISPATCH_HELPER_MANIFEST"


@dataclass(frozen=True, kw_only=True)
class _Helper:
    path: str
    source: str
    mode: int


@dataclass(frozen=True, kw_only=True)
class HelperSource:
    """The forge identity of the installed dispatcher build."""

    repository: str
    commit: str


class _ManifestHelper(TypedDict):
    """The source-free identity and mode of one materialized helper."""

    path: str
    sha256: str
    mode: int


class _HelperManifest(TypedDict):
    """The run-scoped record passed to the sandbox prepare process."""

    repository: str
    commit: str
    helpers: list[_ManifestHelper]


class _HelperMaterializationError(Exception):
    """A manifest or composed helper cannot be trusted."""

    def __init__(self, *, path: str, reason: str) -> None:
        super().__init__(f"{HELPER_DIGEST_MISMATCH_CAUSE}: {path}: {reason}")


def _helpers() -> tuple[_Helper, ...]:
    """Compose every fixed plugin-root helper in its dispatcher-owned order."""
    root = "plugins"
    fixed = (
        _Helper(
            path=f"{root}/{CARRY_FORWARD_PROGRAM_FILENAME}",
            source=carry_forward_program_source(),
            mode=0o644,
        ),
        _Helper(
            path=f"{root}/{COMMIT_RUNNER_PROGRAM_FILENAME}",
            source=commit_runner_program_source(),
            mode=0o644,
        ),
        _Helper(
            path=f"{root}/{HOOK_LIMIT_PROGRAM_FILENAME}",
            source=hook_limit_program_source(),
            mode=0o644,
        ),
        _Helper(
            path=f"{root}/{COMMIT_RED_PROGRAM_FILENAME}",
            source=commit_red_program_source(),
            mode=0o700,
        ),
        _Helper(
            path=f"{root}/{COMMIT_GREEN_PROGRAM_FILENAME}",
            source=commit_green_program_source(),
            mode=0o700,
        ),
        _Helper(
            path=f"{root}/{PROOF_HEAD_PROGRAM_FILENAME}",
            source=proof_head_program_source(),
            mode=0o644,
        ),
        _Helper(
            path=f"{root}/{PUBLICATION_PUSH_PROGRAM_FILENAME}",
            source=publication_push_program_source(),
            mode=0o700,
        ),
        _Helper(
            path=f"{root}/{RECORD_FILE_PROGRAM_FILENAME}",
            source=record_file_program_source(),
            mode=0o644,
        ),
        _Helper(
            path=f"{root}/{RECORD_FILE_MERGE_PROGRAM_FILENAME}",
            source=record_file_merge_program_source(),
            mode=0o644,
        ),
        _Helper(
            path=f"{root}/{REVIEW_GUARD_PROGRAM_FILENAME}",
            source=review_guard_program_source(),
            mode=0o644,
        ),
        _Helper(
            path=f"{root}/{PROOF_GRADE_PROGRAM_FILENAME}",
            source=proof_grade_program_source(),
            mode=0o644,
        ),
    )
    readers = tuple(
        _Helper(path=f"{root}/{PROOF_GRADE_READER_DIRECTORY}/{name}", source=source, mode=0o644)
        for name, source in proof_record_reader_sources()
    )
    return fixed + readers


def helper_manifest(*, repository: str, commit: str) -> _HelperManifest:
    """Return the source-free identity record a dispatch embeds in its overlay."""
    return {
        "repository": repository,
        "commit": commit,
        "helpers": [
            {
                "path": helper.path,
                "sha256": hashlib.sha256(helper.source.encode()).hexdigest(),
                "mode": helper.mode,
            }
            for helper in _helpers()
        ],
    }


def dispatch_helper_source(*, runner: CommandRunner) -> HelperSource | None:
    """Read the executing build's forge URL and immutable commit, if available."""
    root = executing_payload_root()
    repository = _git_value(root=root, args=("remote", "get-url", "origin"), runner=runner)
    commit = _git_value(root=root, args=("rev-parse", "HEAD"), runner=runner)
    if repository is None or commit is None:
        return None
    return HelperSource(repository=repository, commit=commit)


def helper_source_is_reachable(*, source: HelperSource, runner: CommandRunner) -> bool:
    """Probe the forge before a dispatch can claim work for an absent revision."""
    result = runner.run(
        argv=["git", "ls-remote", "--exit-code", source.repository, source.commit],
        cwd=executing_payload_root(),
        timeout_seconds=30.0,
    )
    return result.exit_code == 0


def helper_fetch_prepare_steps_block(*, source: HelperSource) -> str:
    """Fetch one pinned source tree and materialize every fixed helper from it."""
    manifest = json.dumps(
        helper_manifest(repository=source.repository, commit=source.commit),
        separators=(",", ":"),
    )
    script = "\n".join(
        (
            "set -eu",
            'checkout="$(mktemp -d)"',
            "trap \"rm -rf '$checkout'\" EXIT",
            'git init --quiet "$checkout"',
            'git -C "$checkout" sparse-checkout set --no-cone .claude-plugin/scripts',
            f'git -C "$checkout" remote add origin {json.dumps(source.repository)}',
            (
                f'if ! git -C "$checkout" fetch --quiet --depth=1 --filter=blob:none '
                f"origin {json.dumps(source.commit)}; then "
                f'echo "{HELPER_DIGEST_MISMATCH_CAUSE}: helper-manifest: '
                f'commit {source.commit} cannot be fetched" >&2; exit 1; fi'
            ),
            'git -C "$checkout" checkout --quiet --detach FETCH_HEAD',
            (
                'PYTHONPATH="$checkout/.claude-plugin/scripts" '
                "python3 -c 'import sys; from livespec_orchestrator_beads_fabro.commands."
                "_dispatcher_helper_manifest import materialize_helpers_from_environment; "
                "error = materialize_helpers_from_environment(); "
                "assert error is None, error'"
            ),
        )
    )
    step = PrepareStep(script=script, env={HELPER_MANIFEST_ENV: manifest})
    return (
        "\n# --- Dispatcher-fetched, digest-verified helper programs ---\n"
        + render_prepare_step(step=step)
    )


def materialize_helpers(*, manifest: _HelperManifest) -> None:
    """Write and verify the manifest helpers below the sandbox plugins root."""
    expected = {helper["path"]: helper for helper in manifest["helpers"]}
    root = Path(
        os.environ.get(SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR, Path.home() / ".claude/plugins")
    )
    for helper in _helpers():
        entry = expected.get(helper.path)
        if entry is None:
            _fail(path=helper.path, reason="missing from helper manifest")
        digest = hashlib.sha256(helper.source.encode()).hexdigest()
        if digest != entry["sha256"]:
            _fail(path=helper.path, reason="composed digest differs from manifest")
        target = root / Path(helper.path).relative_to("plugins")
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(helper.source, encoding="utf-8")
        target.chmod(int(entry["mode"]))
        if stat.S_IMODE(target.stat().st_mode) != int(entry["mode"]):
            _fail(path=helper.path, reason="written file mode differs from manifest")


def _fail(*, path: str, reason: str) -> NoReturn:
    raise _HelperMaterializationError(path=path, reason=reason)


def _git_value(*, root: Path, args: tuple[str, ...], runner: CommandRunner) -> str | None:
    """Return one Git value without treating an uninstalled build as a checkout."""
    result = runner.run(argv=["git", *args], cwd=root, timeout_seconds=30.0)
    value = result.stdout.strip()
    return value if result.exit_code == 0 and value else None


def materialize_helpers_from_environment() -> str | None:
    """Materialize the delivered manifest and return its named failure, if any."""
    try:
        manifest = cast(_HelperManifest, json.loads(os.environ[HELPER_MANIFEST_ENV]))
        materialize_helpers(manifest=manifest)
    except (KeyError, TypeError, ValueError, _HelperMaterializationError) as error:
        return f"{HELPER_DIGEST_MISMATCH_CAUSE}: helper-manifest: {error}"
    return None

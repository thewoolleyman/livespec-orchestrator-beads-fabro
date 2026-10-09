"""Comment-body builders for Fabro preserve-by-reference records.

A pointer body is READ by an operator and by
`_dispatcher_preserve_reference_check`, so two of its conventions are
load-bearing rather than cosmetic.

First, a body that could not compute a digest says SO, and says why, on
its own `sha256 unavailable because:` line. The branch where a pointer is
most likely to be dangling — the export itself failed — is exactly the
branch with no digest, so a bare placeholder there reads as "someone
forgot" rather than as the honest "no artifact bytes ever reached this
host". The reader keys off that line to report `unverifiable` instead of
silently treating an undigested pointer as intact.

Second, the retrieval command prints the RESOLVED `fabro` path the module
itself invokes, not the bare binary name. The fleet credential wrapper
sanitizes PATH, so a bare `fabro` is not on it: an operator following a
bare printed command gets a not-installed error that names the wrong
problem.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    escape_minijinja_literal,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroCommand

__all__: list[str] = [
    "DIGEST_UNAVAILABLE_PREFIX",
    "FABRO_DIFF_ARTIFACT_GLOB",
    "PRESERVE_POINTER_MARKER",
    "artifact_pointer_body",
    "dump_failed_body",
    "error_pointer_body",
    "missing_artifact_body",
]

FABRO_DIFF_ARTIFACT_GLOB = "stages/*/diff.patch"
PRESERVE_POINTER_MARKER = "livespec-preserve-by-reference"
DIGEST_UNAVAILABLE_PREFIX = "sha256 unavailable because: "
_MAX_STDERR_CHARS = 1000


def artifact_pointer_body(
    *,
    run_id: str,
    server_url: str,
    artifacts: tuple[Path, ...],
    export_dir: Path,
    fabro_bin: str,
) -> tuple[str, str]:
    artifact_lines: list[str] = []
    verification_lines: list[str] = []
    digests: list[str] = []
    for artifact in artifacts:
        data = artifact.read_bytes()
        relative_path = artifact.relative_to(export_dir).as_posix()
        digest = hashlib.sha256(data).hexdigest()
        digests.append(digest)
        artifact_lines.append(f"stage artifact path: {relative_path}")
        artifact_lines.append(f"byte size: {len(data)}")
        artifact_lines.append(f"sha256: {digest}")
        verification_lines.append(f"sha256sum <export-dir>/{relative_path} # must equal {digest}")
    return (
        "\n".join(
            [
                PRESERVE_POINTER_MARKER,
                "",
                f"run id: {run_id}",
                f"factory server url: {server_url}",
                *artifact_lines,
                "",
                "retrieval command:",
                _retrieval_command(fabro_bin=fabro_bin, run_id=run_id, server_url=server_url),
                "",
                "After retrieval, verify:",
                *verification_lines,
                "",
                (
                    "If the dump no longer resolves, the factory run storage may have "
                    "been pruned or the factory may be temporarily unreachable; the "
                    "recorded sha256 is the integrity check for any recovered artifact."
                ),
            ]
        ),
        ",".join(digests),
    )


def missing_artifact_body(*, run_id: str, server_url: str, fabro_bin: str) -> tuple[str, str]:
    digest = "(not recorded; artifact missing)"
    return (
        "\n".join(
            [
                PRESERVE_POINTER_MARKER,
                "",
                f"run id: {run_id}",
                f"factory server url: {server_url}",
                f"stage artifact path: {FABRO_DIFF_ARTIFACT_GLOB} (none found)",
                "artifact: run produced no checkpointed diff artifact",
                "byte size: (not recorded; artifact missing)",
                f"sha256: {digest}",
                (
                    f"{DIGEST_UNAVAILABLE_PREFIX}the export succeeded but matched no "
                    f"{FABRO_DIFF_ARTIFACT_GLOB} artifact, so there were no bytes to digest"
                ),
                "",
                "retrieval command:",
                _retrieval_command(fabro_bin=fabro_bin, run_id=run_id, server_url=server_url),
            ]
        ),
        digest,
    )


def dump_failed_body(
    *,
    run_id: str,
    server_url: str,
    # The `FabroCommand` protocol rather than the engine's concrete
    # `CommandResult`: the export now arrives through `FabroPort.dump`, which
    # reports the protocol, and the three fields read here are all of it.
    command: FabroCommand,
    fabro_bin: str,
) -> tuple[str, str]:
    digest = "(not recorded; dump failed)"
    return (
        "\n".join(
            [
                PRESERVE_POINTER_MARKER,
                "",
                f"run id: {run_id}",
                f"factory server url: {server_url}",
                f"stage artifact path: {FABRO_DIFF_ARTIFACT_GLOB} (unverified)",
                f"artifact: fabro dump failed with exit code {command.exit_code}",
                f"stderr: {comment_safe_external_text(text=command.stderr)}",
                "byte size: (not recorded; dump failed)",
                f"sha256: {digest}",
                (
                    f"{DIGEST_UNAVAILABLE_PREFIX}the export failed (fabro dump exit "
                    f"{command.exit_code}), so no artifact bytes reached this host to digest"
                ),
                (
                    "resolution: retry the command below; if the same run/path remains "
                    "unavailable while the factory is reachable, treat the reference as dangling."
                ),
                "",
                "retrieval command:",
                _retrieval_command(fabro_bin=fabro_bin, run_id=run_id, server_url=server_url),
            ]
        ),
        digest,
    )


def error_pointer_body(
    *,
    run_id: str,
    server_url: str,
    error: Exception,
) -> tuple[str, str]:
    digest = "(not recorded; preserve step failed)"
    return (
        "\n".join(
            [
                PRESERVE_POINTER_MARKER,
                "",
                f"run id: {run_id}",
                f"factory server url: {server_url}",
                f"stage artifact path: {FABRO_DIFF_ARTIFACT_GLOB} (unverified)",
                f"artifact: preserve reference failed with {type(error).__name__}",
                f"error: {comment_safe_external_text(text=str(error))}",
                "byte size: (not recorded; preserve step failed)",
                f"sha256: {digest}",
                (
                    f"{DIGEST_UNAVAILABLE_PREFIX}the preserve step failed with "
                    f"{type(error).__name__} before any artifact could be read"
                ),
            ]
        ),
        digest,
    )


def _retrieval_command(*, fabro_bin: str, run_id: str, server_url: str) -> str:
    return f"{fabro_bin} dump {run_id} --server {server_url} -o <export-dir>"


def comment_safe_external_text(*, text: str) -> str:
    stripped = text.strip()
    bounded = stripped
    if len(stripped) > _MAX_STDERR_CHARS:
        bounded = f"{stripped[:_MAX_STDERR_CHARS]}\n[truncated]"
    escaped = escape_minijinja_literal(text=bounded)
    return escaped.replace("{{", "[[").replace("{%", "[%").replace("{#", "[#")

"""Publish drift-origin proposal documents from an isolated worktree.

The Dispatcher drift job is permitted to FILE proposals but never to leave
them in its caller's checkout.  This module owns the forge boundary: the
caller creates and populates an isolated worktree, then this module commits
its proposal documents, pushes one ``spec/`` branch, and opens one pull
request.  A failed command means that no durable filing occurred.

Open drift-run pull requests are also part of the filing state.  Their bodies
carry the stable finding identities so a later run can see documents that are
not yet on the fetched default branch without writing or fetching into the
primary checkout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "drift_pull_request_body",
    "open_drift_run_proposals",
    "publish_drift_proposals",
]

_BODY_HEADER = "Drift-origin proposals filed by the Dispatcher drift job."
_IDENTITIES_HEADER = "Finding identities:"
_PROPOSALS_PATH = "SPECIFICATION/proposed_changes"
_TIMEOUT_SECONDS = 60.0


def drift_pull_request_body(*, finding_identities: tuple[str, ...]) -> str:
    """Render the machine-readable identities carried by one drift-run pull request."""
    if not finding_identities:
        return _BODY_HEADER
    lines = [_BODY_HEADER, "", _IDENTITIES_HEADER, *(f"- {one}" for one in finding_identities)]
    return "\n".join(lines)


def open_drift_run_proposals(*, repo: Path, runner: CommandRunner) -> frozenset[str]:
    """Read finding identities on every open drift-run pull request.

    A forge read failure answers the empty set: it cannot establish an existing
    filing, so the caller must not treat it as a durable one.  The subsequent
    publication still creates at most one pull request for this invocation.
    """
    result = runner.run(
        argv=["gh", "pr", "list", "--state", "open", "--json", "body", "--limit", "100"],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return frozenset()
    try:
        loaded = json.loads(result.stdout)
    except json.JSONDecodeError:
        return frozenset()
    if not isinstance(loaded, list):
        return frozenset()
    identities: set[str] = set()
    for record in cast(list[object], loaded):
        if not isinstance(record, dict):
            continue
        typed_record = cast(dict[str, object], record)
        for key, value in typed_record.items():
            if key == "body" and isinstance(value, str):
                identities.update(_identities_from_body(body=value))
    return frozenset(identities)


def publish_drift_proposals(
    *, repo: Path, worktree: Path, branch: str, default_branch: str, runner: CommandRunner
) -> bool:
    """Commit and publish the worktree's proposal documents as one pull request.

    ``repo`` is deliberately not a command working directory.  Keeping every
    mutation in ``worktree`` is the executable form of the primary-checkout
    cleanliness guarantee.
    """
    identities = _worktree_finding_identities(worktree=worktree)
    body = drift_pull_request_body(finding_identities=identities)
    commands = (
        ["git", "add", _PROPOSALS_PATH],
        ["git", "commit", "-m", "docs(spec): file drift proposals"],
        ["git", "push", "origin", f"HEAD:{branch}"],
        [
            "gh",
            "pr",
            "create",
            "--base",
            default_branch,
            "--head",
            branch,
            "--title",
            "docs(spec): file drift proposals",
            "--body",
            body,
        ],
    )
    _ = repo
    for argv in commands:
        if runner.run(argv=argv, cwd=worktree, timeout_seconds=_TIMEOUT_SECONDS).exit_code != 0:
            return False
    return True


def _identities_from_body(*, body: str) -> tuple[str, ...]:
    """Parse identities from this module's own pull-request body format."""
    lines = body.splitlines()
    try:
        start = lines.index(_IDENTITIES_HEADER) + 1
    except ValueError:
        return ()
    return tuple(line[2:] for line in lines[start:] if line.startswith("- ") and line[2:])


def _worktree_finding_identities(*, worktree: Path) -> tuple[str, ...]:
    """Read stable identities from the documents this invocation will publish."""
    identities: list[str] = []
    for path in sorted((worktree / _PROPOSALS_PATH).glob("*.md")):
        try:
            document = path.read_text(encoding="utf-8")
        except OSError:
            continue
        identity = _front_matter_value(document=document, field="finding_identity")
        if identity is not None:
            identities.append(identity)
    return tuple(identities)


def _front_matter_value(*, document: str, field: str) -> str | None:
    """Return a front-matter value without mistaking proposal prose for metadata."""
    lines = document.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    prefix = f"{field}:"
    value: str | None = None
    for line in lines[1:]:
        if line.strip() == "---":
            return value
        if line.startswith(prefix):
            value = line[len(prefix) :].strip() or None
    return None

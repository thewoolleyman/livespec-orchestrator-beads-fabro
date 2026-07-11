"""Sandbox sibling-clone provisioning for the Dispatcher."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    SiblingClones,
    parse_fleet_members,
)

__all__: list[str] = [
    "fetch_fleet_manifest_text",
    "resolve_sibling_clones",
]

# Where the canonical fleet member registry lives: .livespec-fleet-manifest.jsonc
# on livespec master (livespec non-functional-requirements.md). Fetched
# HOST-SIDE at run-config generation
# time via `gh api` raw content — the same consume-from-master pattern
# the other family consumers (fleet conformance, release fan-out) use.
# This pins the manifest LOCATION, not the member list: the list itself
# is always read fresh. An unreachable/absent manifest renders an EMPTY
# sibling projection (the non-fleet adopter path); a present-but-malformed
# manifest fails the dispatch fast rather than falling back to a stale
# hardcoded set.
_FLEET_MANIFEST_API_PATH = "repos/thewoolleyman/livespec/contents/.livespec-fleet-manifest.jsonc"
_FLEET_MANIFEST_FETCH_TIMEOUT_SECONDS = 60.0

# In-sandbox directory the sibling clones land under; projected into
# the sandbox env as LIVESPEC_SIBLING_CLONES_ROOT. `/workspace` is the
# fabro docker sandbox's workspace root (the target repo's clone sits
# at /workspace/<repo>), so the siblings root never collides with it.
_SIBLING_CLONES_ROOT = "/workspace/siblings"


def fetch_fleet_manifest_text() -> str | None:
    """Fetch .livespec-fleet-manifest.jsonc raw text from livespec master via `gh api`.

    HOST-SIDE read at run-config generation time (the Dispatcher's own
    environment has an authenticated `gh`; the sandbox does not).
    Returns the raw JSONC text, or None on any failure (no `gh`, no
    manifest, a non-fleet adopter) — the caller renders an EMPTY sibling
    projection so the dispatch proceeds.
    """
    result = ShellCommandRunner().run(
        argv=[
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github.raw",
            _FLEET_MANIFEST_API_PATH,
        ],
        cwd=Path.cwd(),
        timeout_seconds=_FLEET_MANIFEST_FETCH_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0 or result.stdout.strip() == "":
        return None
    return result.stdout


def resolve_sibling_clones(*, repo: Path) -> SiblingClones | str:
    """Resolve the sandbox sibling-clone plan from the fleet manifest.

    Returns the plan (fleet members minus the dispatch target, keyed by
    the `--repo` basename — primary checkouts are named after their
    repo). When NO fleet manifest is present/fetchable (no `gh`, a
    non-fleet adopter), returns an EMPTY plan so the dispatch PROCEEDS
    with no sibling clones — the projection is OPTIONAL for adopters per
    the self-contained plugin dispatch contract. When a manifest IS
    present but MALFORMED, returns an actionable error string routed as
    data (the dispatch fails at the `run-config-overlay` stage): a broken
    fleet member registry is a real config error worth refusing, and a
    hardcoded fallback list would rot as the fleet changes.
    """
    manifest_text = fetch_fleet_manifest_text()
    if manifest_text is None:
        # No fleet manifest is present/fetchable — no `gh`, or a non-fleet
        # adopter consuming the self-contained plugin. That is NOT a
        # dispatch-blocking condition: render an EMPTY sibling set so the
        # dispatch PROCEEDS with no sibling clones (the projection is
        # optional for adopters), rather than refusing. A fleet member's
        # dispatcher host has an authenticated `gh`, so it still fetches
        # the manifest and gets the full projection below. `owner` is
        # never spliced when `repos` is empty.
        return SiblingClones(owner="", repos=(), clones_root=_SIBLING_CLONES_ROOT)
    members = parse_fleet_members(manifest_text=manifest_text)
    if members is None:
        return (
            "sibling-clone provisioning refused: .livespec-fleet-manifest.jsonc "
            "fetched from livespec master did not parse into an owner "
            "plus a non-empty members list of GitHub-slug-shaped repo "
            "names. Fix the manifest on livespec master (it is the "
            "canonical fleet member registry), then retry the dispatch."
        )
    return SiblingClones(
        owner=members.owner,
        repos=tuple(name for name in members.repos if name != repo.name),
        clones_root=_SIBLING_CLONES_ROOT,
    )

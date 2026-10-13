"""Sandbox sibling-clone provisioning for the Dispatcher."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_siblings import (
    SiblingClones,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import parse_fleet_members

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
# the sandbox env as LIVESPEC_SIBLING_CLONES_ROOT.
#
# IT SITS OUTSIDE `/workspace`, AND THAT IS THE WHOLE POINT. It was
# `/workspace/siblings`, written on the premise that the target repository's
# clone sits at `/workspace/<repo>` — true on the pinned 0.254 engine, where
# `/workspace/<repo>` is a symlink to the clone and the siblings root is that
# clone's PEER. The Petri-era engine checks the target repository out AT the
# mount (its hooks log `site=Sandbox("/workspace")`), which made every sibling
# clone a directory INSIDE the target repository's own tree: a whole-tree check
# then reads the siblings' files, so the commit hooks refuse on a sibling and no
# Red commit can land. Measured 2026-10-13 on hp-candidate run 01M4SNYP3GT2,
# where the implement stage spent 15 minutes and failed with no Red.
#
# ONE OVERLAY SERVES BOTH ENGINES and nothing in it learns which layout the run
# will land in, so a root outside the mount is what makes it outside the clone
# under EITHER layout — there is no in-sandbox clone path to derive it from.
#
# A FILESYSTEM-ROOT path rather than one under `/tmp`: the prepare step's own
# `mkdir -p` has to succeed or the run dies at launch with no work done, and the
# sandbox image family declares no `USER` in any of its stages, so a dispatched
# sandbox runs as uid 0 on a writable overlay root (measured in-sandbox
# 2026-10-13: `uid=0(root)`, `/` an `rw` overlay mount). `/tmp` would have been
# the more permissive choice but `ruff`'s S108 refuses a hardcoded `/tmp` path
# outright, and a waiver is not something to spend on a directory that has an
# unobjectionable spelling. The sandbox is per-run and discarded with the
# container, so the clones need no life beyond it.
_SIBLING_CLONES_ROOT = "/livespec-siblings"


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

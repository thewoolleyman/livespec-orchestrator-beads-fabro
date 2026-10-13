"""Where a dispatched sandbox's sibling clones land, on BOTH engine layouts.

The root was `/workspace/siblings`, written on the premise that the target
repository's clone sits at `/workspace/<repo>` — true on the pinned 0.254
engine, where `/workspace/<repo>` is a symlink to the clone and
`/workspace/siblings` is that clone's PEER. The Petri-era engine checks the
target repository out AT `/workspace` (its hooks log
`site=Sandbox("/workspace")`), which put every sibling clone INSIDE the target
repository's own tree: a whole-tree `ruff` scan then read the siblings' files
and the commit hooks refused, so the implement stage could not land one Red
commit (measured 2026-10-13 on hp-candidate run 01M4SNYP3GT2, which spent 15
minutes and failed with no Red).

The Dispatcher renders ONE overlay for both engines and learns nothing about
which layout it will land in, so the root has to sit outside the workspace
mount altogether — which is what makes it outside the clone under EITHER
layout. That RELATION is what these tests assert, not the spelling of the
path: a replacement root that is merely a different name under `/workspace`
would re-open the measured defect while satisfying any literal pinned here.

The root is read through `resolve_sibling_clones`, the one producer of a
`SiblingClones` plan, because that is the value a real dispatch projects. The
third test closes the loop at the rendered artifact: a root outside the clone
is worth nothing if the env key the in-sandbox cross-repo checks read names a
different directory than the prepare steps actually clone into.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_sibling_clones
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_siblings import (
    SIBLING_CLONES_ROOT_ENV_VAR,
    SiblingClones,
)

# A canned fleet manifest, so the resolved plan carries members (and therefore
# rendered clone steps) without reaching for the host's `gh`.
_FLEET_MANIFEST_TEXT = (
    "// .livespec-fleet-manifest.jsonc — canned test copy\n"
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "fleet": [\n'
    '    { "repo": "livespec", "class": "core" },\n'
    '    { "repo": "livespec-dev-tooling", "class": "enforcement-suite" },\n'
    '    { "repo": "repo", "class": "impl-plugin" }\n'
    "  ]\n"
    "}\n"
)

# The fabro sandbox's own mount, plus the TWO sites the two engines check the
# target repository's clone out at: the Petri-era engine uses the mount itself,
# the pinned 0.254 engine uses a subdirectory of it named after the repo.
_SANDBOX_WORKSPACE_MOUNT = PurePosixPath("/workspace")
_CLONE_AT_WORKSPACE_ROOT = _SANDBOX_WORKSPACE_MOUNT
_CLONE_IN_WORKSPACE_SUBDIRECTORY = _SANDBOX_WORKSPACE_MOUNT / "livespec-orchestrator-beads-fabro"

_FAKE_OVERLAY_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"

_ENV_LINE_PATTERN = re.compile(rf'{SIBLING_CLONES_ROOT_ENV_VAR} = "([^"]+)"')
_CLONE_DESTINATION_PATTERN = re.compile(r"git clone --quiet --depth 1 \S+ (\S+) \|\|")


def _resolved_plan(*, monkeypatch: pytest.MonkeyPatch) -> SiblingClones:
    """The sibling-clone plan one real dispatch of this repo would project."""
    monkeypatch.setattr(
        _dispatcher_sibling_clones,
        "fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    plan = _dispatcher_sibling_clones.resolve_sibling_clones(repo=Path("repo"))
    assert isinstance(plan, SiblingClones)
    return plan


def _committed_implement_workflow_text() -> str:
    """The SHIPPED implement-work-item workflow, as every dispatch renders it."""
    repo_root = Path(__file__).resolve().parents[3]
    workflow_toml = (
        repo_root
        / ".claude-plugin"
        / ".fabro"
        / "workflows"
        / "implement-work-item"
        / "workflow.toml"
    )
    return workflow_toml.read_text(encoding="utf-8")


def test_the_clones_root_is_outside_a_clone_checked_out_at_the_workspace_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Petri-era layout: `/workspace` IS the target repository's clone.

    A root under the mount is a directory inside that clone, so every
    whole-tree check the repository runs — `ruff format --check .` first among
    them — scans the siblings, and the commit hooks refuse on a sibling's
    files. No Red commit can land, which is the failure this repairs.
    """
    root = PurePosixPath(_resolved_plan(monkeypatch=monkeypatch).clones_root)
    assert not root.is_relative_to(_CLONE_AT_WORKSPACE_ROOT)


def test_the_clones_root_is_outside_a_clone_checked_out_in_a_workspace_subdirectory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pinned 0.254 layout: the clone is `<mount>/<repo>`, a symlink.

    This arm held before the move and must keep holding after it — the
    Dispatcher renders one overlay for both engines, so a root that fixes the
    Petri-era layout by landing inside the 0.254 clone has only moved the
    defect to the other engine.
    """
    root = PurePosixPath(_resolved_plan(monkeypatch=monkeypatch).clones_root)
    assert not root.is_relative_to(_CLONE_IN_WORKSPACE_SUBDIRECTORY)


def test_the_projected_env_key_names_the_directory_the_prepare_steps_clone_into(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """One directory, named twice in the rendered overlay — it must be the same one.

    `LIVESPEC_SIBLING_CLONES_ROOT` is what the in-sandbox cross-repo checks
    resolve siblings through, and the prepare steps are what put them on disk.
    The two are read from one plan today; asserting the rendered artifact is
    what keeps a later change to either surface from silently pointing the
    checks at an empty directory.
    """
    plan = _resolved_plan(monkeypatch=monkeypatch)
    rendered = render_run_config_overlay(
        committed_text=_committed_implement_workflow_text(),
        workflow_dir=tmp_path,
        token=_FAKE_OVERLAY_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=plan,
    )
    assert rendered is not None
    projected = _ENV_LINE_PATTERN.search(rendered)
    assert projected is not None
    destinations = [match.group(1) for match in _CLONE_DESTINATION_PATTERN.finditer(rendered)]
    assert len(destinations) == len(plan.repos)
    assert {str(PurePosixPath(destination).parent) for destination in destinations} == {
        projected.group(1)
    }

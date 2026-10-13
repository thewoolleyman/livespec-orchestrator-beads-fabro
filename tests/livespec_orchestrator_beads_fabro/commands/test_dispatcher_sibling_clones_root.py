"""Where a dispatched sandbox's sibling clones land — outside the target clone.

THE ROOT HAS TO SIT OUTSIDE THE TARGET REPOSITORY'S CLONE, AND THE TWO ENGINES
PUT THAT CLONE IN DIFFERENT PLACES. The pinned 0.254 layout checks the target
repository out at `/workspace/<repo>` (a symlink to the real clone), so a root
at `/workspace/siblings` sat beside the clone. The Petri-era engine checks it
out AT the workspace root — its hooks log `site=Sandbox("/workspace")` — which
turns that same root into a directory INSIDE the clone, and every whole-tree
check the repository runs then scans nine sibling checkouts. Measured
2026-10-13 on hp-candidate run 01M4SNYP3GT2 (fabro 0.382.0-nightly.0): the
implement stage spent fifteen minutes and could not land one Red commit,
because the commit hooks kept failing on a sibling's own files.

So the two layout assertions below are not one assertion written twice. Each
names a clone location an engine actually uses, and the root must be outside
BOTH — which is why it is anchored off `/workspace` entirely rather than
relocated one level down.

THE THIRD ASSERTION IS THE ONE THAT WOULD BREAK SILENTLY. The clones land
wherever the prepare steps put them, while every in-sandbox consumer finds them
through `LIVESPEC_SIBLING_CLONES_ROOT`; those are two renderings of one plan,
and a root that moved in one of them would leave the other naming an empty
directory. A consumer reading it does not fail — it reports the siblings as
absent, which reads as a non-fleet adopter rather than as a broken projection.
So the test reads the projected value OUT of the rendered run config and
compares the clone destinations against that, never against a literal.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_siblings import (
    SIBLING_CLONES_ROOT_ENV_VAR,
    SiblingClones,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones import (
    resolve_sibling_clones,
)

# The fabro sandbox's workspace root — the mount both engines hand the run.
_SANDBOX_WORKSPACE = PurePosixPath("/workspace")
_TARGET_REPO = "livespec-orchestrator-beads-fabro"

_FLEET_MANIFEST_TEXT = (
    "// .livespec-fleet-manifest.jsonc — canned test copy\n"
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "fleet": [\n'
    '    { "repo": "livespec", "class": "core" },\n'
    '    { "repo": "livespec-dev-tooling", "class": "enforcement-suite" },\n'
    f'    {{ "repo": "{_TARGET_REPO}", "class": "impl-plugin" }}\n'
    "  ]\n"
    "}\n"
)

# Stand-in credentials for the overlay render. Their VALUES are irrelevant
# here — this file asserts where the sibling clones land — but the renderer
# refuses to project anything without them.
_FAKE_OAUTH_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)


def _resolved_plan(*, monkeypatch: pytest.MonkeyPatch) -> SiblingClones:
    """The sibling-clone plan a fleet dispatch of this repository resolves."""
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands"
        "._dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    plan = resolve_sibling_clones(repo=_SANDBOX_WORKSPACE / _TARGET_REPO)
    assert isinstance(plan, SiblingClones)
    return plan


def test_the_clones_root_is_outside_a_clone_that_sits_at_the_workspace_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Petri-era layout: the clone IS `/workspace`, so a root under it is inside it."""
    root = PurePosixPath(_resolved_plan(monkeypatch=monkeypatch).clones_root)
    assert not root.is_relative_to(_SANDBOX_WORKSPACE)


def test_the_clones_root_is_outside_a_clone_that_sits_in_a_workspace_subdirectory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pinned 0.254 layout: the clone is `/workspace/<repo>`, beside the root."""
    root = PurePosixPath(_resolved_plan(monkeypatch=monkeypatch).clones_root)
    assert not root.is_relative_to(_SANDBOX_WORKSPACE / _TARGET_REPO)


def test_the_projected_env_var_names_the_directory_the_prepare_steps_clone_into(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One plan, two renderings: the env key must name the clones' own destination."""
    plan = _resolved_plan(monkeypatch=monkeypatch)
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_OAUTH_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=plan,
    )
    assert rendered is not None
    projected = re.search(
        rf'^{SIBLING_CLONES_ROOT_ENV_VAR} = "(?P<root>[^"]+)"$',
        rendered,
        re.MULTILINE,
    )
    assert projected is not None
    root = projected.group("root")
    # The canned manifest registers two members besides the dispatch target, so
    # there ARE clone steps to compare the projection against.
    assert plan.repos == ("livespec", "livespec-dev-tooling")
    assert f"mkdir -p {root} ||" in rendered
    for member in plan.repos:
        destination = f"https://github.com/{plan.owner}/{member}.git {root}/{member}"
        assert f"git clone --quiet --depth 1 {destination}" in rendered

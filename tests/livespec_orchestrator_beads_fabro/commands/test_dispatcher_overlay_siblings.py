"""The sibling-clone surface, after it moved out of the overlay.

`_dispatcher_overlay_siblings` was carved out of `_dispatcher_overlay` by
cohesion when the overlay crossed its file-size ceiling: the overlay renders a
run config, while this module answers one narrower question — which family repos
a dispatched sandbox clones, where they land, and which env keys point at them.

WHAT THIS FILE ASSERTS, AND WHY IT IS NOT REDUNDANT WITH THE OVERLAY'S OWN TESTS.
Those tests reach these two functions THROUGH `render_run_config_overlay`, so
they assert the rendered run config. This file asserts the extracted surface
directly, which is what makes the extraction checkable as a pure move: the
per-member failure tolerance and the `GIT_TERMINAL_PROMPT=0` hardening are each
the repair of a real incident, and each would still be reachable-but-unasserted
if only the composed output were checked.

THE CORE-PLUGIN PROJECTION'S GUARD IS THE ONE MOST LIKELY TO BE SIMPLIFIED AWAY.
It renders nothing unless the livespec CORE sibling is actually among the cloned
repos, because the path it would otherwise name does not exist inside the
sandbox — and a non-existent `LIVESPEC_CORE_PLUGIN_ROOT` is worse than an absent
one: a janitor reading it reports core as broken rather than as unconfigured.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_siblings import (
    CORE_PLUGIN_ROOT_ENV_VAR,
    SIBLING_CLONES_ROOT_ENV_VAR,
    SiblingClones,
    core_plugin_env_line,
    sibling_clone_steps_block,
)

_CLONES_ROOT = "/workspace/.livespec-siblings"


def _siblings(*, repos: tuple[str, ...]) -> SiblingClones:
    return SiblingClones(owner="thewoolleyman", repos=repos, clones_root=_CLONES_ROOT)


def test_the_two_env_var_names_are_the_ones_the_sandbox_reads() -> None:
    """Both keys are read inside the sandbox, so their spelling is the contract."""
    assert SIBLING_CLONES_ROOT_ENV_VAR == "LIVESPEC_SIBLING_CLONES_ROOT"
    assert CORE_PLUGIN_ROOT_ENV_VAR == "LIVESPEC_CORE_PLUGIN_ROOT"


def test_one_prepare_step_is_rendered_per_member() -> None:
    """The dispatch target is excluded upstream, so every member here gets a step."""
    block = sibling_clone_steps_block(siblings=_siblings(repos=("livespec", "livespec-overseer")))
    assert block.count("[[run.prepare.steps]]") == 2
    assert "livespec-overseer.git" in block
    assert _CLONES_ROOT in block


def test_each_step_tolerates_its_own_members_failure() -> None:
    """A member registered before it exists must not kill every fleet dispatch."""
    block = sibling_clone_steps_block(siblings=_siblings(repos=("livespec",)))
    assert "exit 0" in block
    assert "repository not reachable" in block
    assert "clone failed after a successful" in block


def test_both_git_invocations_disable_the_credential_prompt() -> None:
    """Without it, an unreachable repo reads as an auth failure — a real misdiagnosis."""
    block = sibling_clone_steps_block(siblings=_siblings(repos=("livespec",)))
    assert block.count("GIT_TERMINAL_PROMPT=0") == 2


def test_the_core_plugin_line_is_projected_when_core_is_among_the_siblings() -> None:
    """The janitor's only route to core inside a fail-closed sandbox env."""
    line = core_plugin_env_line(siblings=_siblings(repos=("livespec", "livespec-overseer")))
    assert line.startswith(f"{CORE_PLUGIN_ROOT_ENV_VAR} = ")
    assert f"{_CLONES_ROOT}/livespec/.claude-plugin" in line


def test_no_core_sibling_projects_no_core_plugin_line() -> None:
    """A path that does not exist reads as core BROKEN rather than unconfigured."""
    assert core_plugin_env_line(siblings=_siblings(repos=("livespec-overseer",))) == ""


def test_no_siblings_at_all_projects_no_core_plugin_line() -> None:
    """The same guard covers a dispatch that clones nothing."""
    assert core_plugin_env_line(siblings=None) == ""

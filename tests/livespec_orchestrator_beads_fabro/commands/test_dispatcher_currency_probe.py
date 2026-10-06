"""The currency gate's build-IDENTITY and ref-PROBE layer, extracted by cohesion.

`_dispatcher_staleness_gate` carries two different kinds of thing: the
DECISION layer, which assembles warnings and refusals out of
`DispatcherStalenessDecision` values, and underneath it a layer that answers
plain factual questions — is this plugin root a git checkout, is its name a
release-cache build id, what sha does a remote ref point at, does a build id
match a sha. That lower layer traffics only in strings, booleans and argv
tuples; it names none of the decision types.

Threading the executing-payload root through the gate pushed the file past its
250 LLOC hard ceiling, and the honest remedy is to cut along that seam rather
than shave lines. This test pins the cut: the probe module exists, its names
are public there (nothing private crosses a module boundary), and the gate no
longer defines them.

The gate keeps `latest_release_ref_argv` and `master_ref_argv` in its own
`__all__` — they are part of its published surface and callers import them
from it — so those are re-exported rather than relocated out of reach.
"""

from __future__ import annotations

import importlib
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_currency_probe.py"
)
_PROBE_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_currency_probe"
_GATE_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_staleness_gate"

# Everything the cut moves, as the PUBLIC name it must carry afterwards. A
# `_`-prefixed name imported across a module boundary is rejected by both
# pyright strict and the private-calls check, so each has to be promoted.
_PROMOTED = (
    "build_matches_ref",
    "executing_cache_build_id",
    "git_checkout_head",
    "latest_release_ref_argv",
    "master_ref_argv",
    "remote_ref_sha",
)


def test_the_probe_module_exists_at_its_expected_path() -> None:
    """Asserted first, so this file's Red is a genuine assertion failure.

    A top-level import of a module that does not exist yet dies at COLLECTION,
    which proves only unimportability — not that the cut has not been made.
    """
    assert _MODULE_PATH.is_file(), f"the probe module has not been extracted to {_MODULE_PATH}"


def test_every_moved_name_is_public_in_the_probe_module() -> None:
    probe = importlib.import_module(_PROBE_MODULE)
    for name in _PROMOTED:
        assert hasattr(probe, name), f"{name} did not move to the probe module"
    assert sorted(probe.__all__) == sorted(
        _PROMOTED
    ), f"the probe module's published surface is not the moved set: {probe.__all__}"


def test_the_gate_no_longer_defines_the_moved_names_itself() -> None:
    """The cut has to REMOVE them, not copy them.

    Two definitions of one rule is the drift this extraction exists to avoid,
    so the gate's source must no longer carry these `def`s even though it
    still calls them.
    """
    gate_source = (_MODULE_PATH.parent / "_dispatcher_staleness_gate.py").read_text(
        encoding="utf-8"
    )
    for name in ("_remote_ref_sha", "_executing_cache_build_id", "_build_matches_ref"):
        assert f"def {name}(" not in gate_source, f"{name} is still defined in the gate"
    assert "def _git_checkout_head(" not in gate_source


def test_the_gate_still_publishes_the_two_ref_argv_builders() -> None:
    """Its published surface is unchanged by a pure refactor."""
    gate = importlib.import_module(_GATE_MODULE)
    for name in ("latest_release_ref_argv", "master_ref_argv"):
        assert name in gate.__all__, f"the gate stopped publishing {name}"
        assert callable(getattr(gate, name))


def test_the_moved_identity_predicates_still_answer_the_same_way(tmp_path: Path) -> None:
    """A moved function is the same function: the behaviour rides along."""
    probe = importlib.import_module(_PROBE_MODULE)
    assert probe.executing_cache_build_id(plugin_root=tmp_path / "abc1234") == "abc1234"
    assert probe.executing_cache_build_id(plugin_root=tmp_path / "not-a-sha") is None
    assert probe.executing_cache_build_id(plugin_root=tmp_path / "abc") is None
    assert probe.build_matches_ref(build_id="abc1234", ref_sha="abc1234def") is True
    assert probe.build_matches_ref(build_id="abc1234", ref_sha="fed4321abc") is False
    assert probe.latest_release_ref_argv()[:2] == ("git", "ls-remote")
    assert probe.master_ref_argv()[:2] == ("git", "ls-remote")

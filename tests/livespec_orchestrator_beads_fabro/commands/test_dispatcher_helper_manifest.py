"""The dispatch helper manifest is the only helper payload the overlay carries."""

from __future__ import annotations

import importlib
from pathlib import Path


def test_manifest_names_each_composed_helper_without_shipping_its_source() -> None:
    """A manifest carries immutable identities and digests, never source bytes."""
    module_path = (
        Path(__file__).parents[3]
        / ".claude-plugin"
        / "scripts"
        / "livespec_orchestrator_beads_fabro"
        / "commands"
        / "_dispatcher_helper_manifest.py"
    )
    assert module_path.is_file()

    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_helper_manifest"
    )
    manifest = module.helper_manifest(
        repository="https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git",
        commit="a" * 40,
    )

    assert manifest["repository"].endswith("livespec-orchestrator-beads-fabro.git")
    assert manifest["commit"] == "a" * 40
    assert manifest["helpers"]
    assert all(set(helper) == {"path", "sha256", "mode"} for helper in manifest["helpers"])
    assert all(len(helper["sha256"]) == 64 for helper in manifest["helpers"])

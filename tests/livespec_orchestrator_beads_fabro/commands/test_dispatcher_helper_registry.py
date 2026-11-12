"""The one registry of helper programs, and the manifest the Dispatcher writes from it.

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch", paragraph
"Helper programs are fetched in the sandbox from the dispatching build's own
commit", and Scenario 336's "A dispatch's run configuration carries a helper
manifest and no helper source". The manifest names the repository, the commit and
one sha256 per helper, digested over the bytes the registry composes, and never
carries a helper's source.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands import _dispatcher_helper_registry as registry
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    GUARD_SCRIPT_PATH,
    guard_script_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_gate_preview_program import (
    GATE_PREVIEW_PROGRAM_FILENAME,
    gate_preview_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    GH_MINT_HELPER_RELPATH,
    gh_mint_helper_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    PLUGIN_GATE_PROGRAM_FILENAME,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_wip_capture import (
    WIP_CAPTURE_PROGRAM_FILENAME,
    wip_capture_program_source,
)

_REPOSITORY = "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git"
_COMMIT = "37e012335ed23ecba9bbcbb829e0fc90f2fdaf3b"
_SCRIPTS = Path(__file__).resolve().parents[3] / ".claude-plugin" / "scripts"


def _by_name() -> dict[str, registry.Helper]:
    return {helper.name: helper for helper in registry.helper_registry()}


def test_every_helper_has_a_unique_name_and_a_unique_place() -> None:
    helpers = registry.helper_registry()
    assert len(helpers) > 100
    assert len({helper.name for helper in helpers}) == len(helpers)
    assert len({(helper.root, helper.path) for helper in helpers}) == len(helpers)
    assert {helper.root for helper in helpers} == set(registry.HELPER_ROOTS)
    assert all(not helper.path.startswith("/") for helper in helpers)


def test_the_registry_composes_each_helper_from_its_owning_module() -> None:
    helpers = _by_name()
    runner = helpers["commit-runner"]
    assert (runner.root, runner.path) == (registry.PLUGINS_ROOT, COMMIT_RUNNER_PROGRAM_FILENAME)
    assert runner.compose() == commit_runner_program_source().encode("utf-8")
    preview = helpers["implement-gate-preview"]
    assert (preview.root, preview.path, preview.mode) == (
        registry.PLUGINS_ROOT,
        GATE_PREVIEW_PROGRAM_FILENAME,
        0o755,
    )
    assert preview.compose() == gate_preview_program_source().encode("utf-8")
    guard = helpers["credential-use-guard"]
    assert f"{registry.LIVESPEC_SANDBOX_ROOT_PATH}/{guard.path}" == GUARD_SCRIPT_PATH
    assert guard.compose() == guard_script_text().encode("utf-8")
    assert guard.mode == 0o700
    mint = helpers["gh-mint-helper"]
    assert (mint.root, mint.path, mint.mode) == (
        registry.GH_REFRESH_ROOT,
        GH_MINT_HELPER_RELPATH,
        0o755,
    )
    assert mint.compose() == gh_mint_helper_source().encode("utf-8")
    assert helpers["plugin-cache-gate"].path == PLUGIN_GATE_PROGRAM_FILENAME
    assert helpers["plugin-cache-gate"].compose().endswith(b"\n")


def test_the_wip_capture_program_is_a_digest_verified_gh_refresh_helper() -> None:
    """Scenario 317's capture binary lands beside the credentialed push helper."""
    helpers = _by_name()

    assert "gh-wip-capture" in helpers
    capture = helpers["gh-wip-capture"]

    assert (capture.root, capture.path, capture.mode) == (
        registry.GH_REFRESH_ROOT,
        f"bin/{WIP_CAPTURE_PROGRAM_FILENAME}",
        0o755,
    )
    assert capture.compose() == wip_capture_program_source().encode("utf-8")


def test_the_gh_refresh_support_bundle_is_copied_file_by_file() -> None:
    support = [h for h in registry.helper_registry() if h.name.startswith("gh-refresh-support/")]
    assert len(support) > 50
    typing_extensions = next(h for h in support if h.path == "_vendor/typing_extensions.py")
    assert typing_extensions.compose() == (_SCRIPTS / "_vendor/typing_extensions.py").read_bytes()
    assert all("__pycache__" not in h.path and h.path.startswith("_vendor/") for h in support)


def test_the_proof_capture_launcher_and_hooks_are_helpers() -> None:
    names = set(_by_name())
    assert {
        "proof-capture/proof-capture-bin/git",
        "proof-capture/proof-capture-hooks/pre-commit",
        "proof-capture/proof-capture-hooks/pre-push",
    } <= names


def test_the_manifest_digests_every_composed_helper_and_carries_no_source() -> None:
    manifest = registry.helper_manifest(repository=_REPOSITORY, commit=_COMMIT)
    assert (manifest["repository"], manifest["commit"]) == (_REPOSITORY, _COMMIT)
    entries = cast("list[dict[str, object]]", manifest["helpers"])
    helpers = _by_name()
    assert [entry["name"] for entry in entries] == list(helpers)
    for entry in entries:
        helper = helpers[entry["name"]]
        assert set(entry) == {"name", "root", "path", "mode", "sha256"}
        assert entry["sha256"] == hashlib.sha256(helper.compose()).hexdigest()
        assert (entry["root"], entry["path"], entry["mode"]) == (
            helper.root,
            helper.path,
            helper.mode,
        )
    text = registry.helper_manifest_text(repository=_REPOSITORY, commit=_COMMIT)
    assert json.loads(text) == manifest
    assert "def main" not in text
    assert "import " not in text


def test_a_registry_read_from_another_tree_digests_that_tree(tmp_path: Path) -> None:
    vendor = tmp_path / "_vendor"
    (vendor / "livespec_runtime" / "github_auth").mkdir(parents=True)
    (vendor / "returns").mkdir()
    for relative in (
        "livespec_runtime/__init__.py",
        "livespec_runtime/github_auth/config.py",
        "returns/pipeline.py",
        "typing_extensions.py",
    ):
        _ = (vendor / relative).write_text(f"# {relative}\n", encoding="utf-8")
    helpers = registry.helper_registry(scripts_root=tmp_path)
    support = {h.path: h for h in helpers if h.name.startswith("gh-refresh-support/")}
    assert sorted(support) == [
        "_vendor/livespec_runtime/__init__.py",
        "_vendor/livespec_runtime/github_auth/config.py",
        "_vendor/returns/pipeline.py",
        "_vendor/typing_extensions.py",
    ]
    assert support["_vendor/returns/pipeline.py"].compose() == b"# returns/pipeline.py\n"
    manifest = registry.helper_manifest(repository=_REPOSITORY, commit=_COMMIT, helpers=helpers)
    assert len(manifest["helpers"]) == len(helpers)  # type: ignore[arg-type]

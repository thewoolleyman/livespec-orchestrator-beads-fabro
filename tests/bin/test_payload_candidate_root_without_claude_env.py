"""The installed root stays the CANDIDATE even when no harness exports it.

`test_payload_candidate_and_credential_boundary.py` already requires that
`plugin_root()` keep naming the INSTALLED tree while packaged assets resolve
inside the payload. It establishes that through `CLAUDE_PLUGIN_ROOT`, which it
sets on every child — so it only ever exercises the Claude path, where the
harness exports the installation for us.

Normal Codex does NOT export `CLAUDE_PLUGIN_ROOT`. On that path `plugin_root()`
falls through to `Path(__file__).resolve().parents[3]`, and once the launcher
has copied the release aside, the module doing the resolving was loaded FROM
the payload — so the fall-through names the payload. The candidate root and the
execution path collapse into one tree, which is the thing `plugin_root()`'s own
docstring warns about: "Pointing it at a retained copy makes every one of those
comparisons the running build against itself."

Measured 2026-10-06 against the unmodified launcher, with a real child spawned
through the real `bootstrap()` and `CLAUDE_PLUGIN_ROOT` absent:

    plugin_root            = /tmp/...-payload-7.1.0-46ij91l5/payload
    executing_payload_root = /tmp/...-payload-7.1.0-46ij91l5/payload
    running_release        = 7.1.0

while the actual installation sat at `/tmp/probe-codex-root-.../0123abc` and
was named by NEITHER. The concrete costs, each of which the work-item's fifth
assertion names:

- the self-update canary compares available against running, and both now come
  from the same immutable copy, so it can never validate the update it exists
  for;
- the registered-install currency finding compares the registry against the
  payload rather than against the install;
- a minimum-release floor refusal names the PAYLOAD as "the installation to
  update", pointing the operator at a disposable directory under `/tmp`
  instead of at the install they must act on;
- `executing_cache_build_id` reads `plugin_root.name`, which is the fixed
  string `payload` rather than a hex build id, so the ambient currency finding
  reports "undetermined" permanently on this path.

The remedy keeps the two roots separate the way the module already intends:
the launcher, which is the only thing that knows the installation, records it
when it provisions, and `plugin_root()` consults that record after
`CLAUDE_PLUGIN_ROOT` and before the `__file__` fall-through. Nothing moves a
running Dispatcher to another payload — assets keep resolving through
`executing_payload_root`, which is unchanged and still derived from `__file__`.

The three controls below are the behaviours the fix must NOT disturb: the
Claude path still wins when the harness exports it, packaged assets still come
from the payload, and this project's own source checkout — which is never
retained — still resolves to itself with no environment help at all.

Real child processes are the only way to ask any of this, so this file is
listed in `pyproject.toml`'s `subprocess_spawn_allowlist` and scrubs the
coverage subprocess hooks exactly as an allowlisted spawn must.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = _REPO_ROOT / ".claude-plugin"

_CHILD_TIMEOUT_SECONDS = 300.0
_PLACEHOLDER_SECRET = "test-not-a-real-secret"
_INSTALLED_RELEASE = "7.1.0"
# A flattened-cache shape: a hex build-id directory name, which is what makes
# the tree harness-managed rather than a checkout.
_BUILD_ID = "0123abc"
_THIS_PROJECT = '[project]\nname = "livespec-orchestrator-beads-fabro"\n'

# Reports both roots from inside a process that went through the real launcher.
# No in-process call can stand in: the question is what a SECOND process
# resolves after its own code was copied aside.
_CHILD = """
import json, os, sys
from pathlib import Path

sys.path.insert(0, {bin_dir!r})
from _bootstrap import bootstrap

bootstrap()

from livespec_orchestrator_beads_fabro.commands import _dispatcher_paths as paths

print(json.dumps({{
    "claude_plugin_root_set": bool(os.environ.get("CLAUDE_PLUGIN_ROOT")),
    "plugin_root": str(paths.plugin_root()),
    "executing_payload_root": str(paths.executing_payload_root()),
    "workflow_asset_parent": str(paths.executing_payload_root() / ".fabro" / "workflows"),
}}))
"""


@pytest.fixture(name="install_parent")
def _install_parent() -> Iterator[Path]:
    """An installation directory OUTSIDE any git worktree.

    A `.git` at the pytest basetemp root makes every `tmp_path` resolve as a
    worktree, which changes how the plugin root is classified. A
    harness-managed plugin cache is not inside a worktree, and this is that
    shape.
    """
    parent = Path(tempfile.mkdtemp(prefix="livespec-candidate-root-"))
    try:
        yield parent
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def _install(*, root: Path) -> Path:
    _ = shutil.copytree(_PLUGIN_ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
    _ = (root / "plugin.json").write_text(
        json.dumps({"name": "livespec-orchestrator-beads-fabro", "version": _INSTALLED_RELEASE}),
        encoding="utf-8",
    )
    return root


def _resolve_roots(*, plugin_root: Path, tmp_path: Path, export_claude_root: bool):
    """Run the real bootstrap in a child and report the roots it resolves."""
    child = tmp_path / "report_roots.py"
    _ = child.write_text(
        _CHILD.format(bin_dir=str(plugin_root / "scripts" / "bin")),
        encoding="utf-8",
    )

    scrubbed = ("PYTHONPATH", "COVERAGE_PROCESS_START")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in scrubbed and not key.startswith("COV_CORE_")
    }
    # The normal Codex shape: the harness exports neither of these.
    _ = env.pop("CLAUDE_PLUGIN_ROOT", None)
    _ = env.pop("LIVESPEC_RETAINED_PAYLOAD_ROOT", None)
    if export_claude_root:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    env["LIVESPEC_BEADS_FAKE"] = "1"
    env["BEADS_DOLT_PASSWORD"] = _PLACEHOLDER_SECRET

    completed = subprocess.run(
        [sys.executable, str(child)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        check=False,
        timeout=_CHILD_TIMEOUT_SECONDS,
    )
    assert (
        completed.returncode == 0
    ), f"the child did not complete the real launcher:\n{completed.stdout}\n{completed.stderr}"
    lines = completed.stdout.strip().splitlines()
    assert lines, f"the child reported nothing:\n{completed.stderr}"
    return json.loads(lines[-1])


def test_the_installed_root_is_the_candidate_when_no_harness_exports_it(
    tmp_path: Path, install_parent: Path
) -> None:
    """The normal Codex path: no `CLAUDE_PLUGIN_ROOT`, and a retained payload."""
    install_root = _install(root=install_parent / _BUILD_ID)

    report = _resolve_roots(plugin_root=install_root, tmp_path=tmp_path, export_claude_root=False)

    assert report["claude_plugin_root_set"] is False, "fixture: the Claude root leaked in"
    assert report["executing_payload_root"] != str(install_root), (
        "fixture: no payload was retained, so the candidate question cannot "
        f"diverge from the execution path: {report}"
    )
    assert report["plugin_root"] == str(install_root), (
        "the candidate root collapsed onto the retained execution path, so every "
        "currency comparison is now the running build against itself and a floor "
        f"refusal would name a disposable /tmp directory: {report}"
    )
    assert (
        report["plugin_root"] != report["executing_payload_root"]
    ), f"the candidate root and the execution path are the same tree: {report}"


def test_an_exported_claude_plugin_root_still_wins(tmp_path: Path, install_parent: Path) -> None:
    """Control: the Claude path is unchanged, and still takes precedence."""
    install_root = _install(root=install_parent / _BUILD_ID)

    report = _resolve_roots(plugin_root=install_root, tmp_path=tmp_path, export_claude_root=True)

    assert report["claude_plugin_root_set"] is True
    assert report["plugin_root"] == str(install_root)
    assert report["plugin_root"] != report["executing_payload_root"]


def test_packaged_assets_still_resolve_inside_the_payload(
    tmp_path: Path, install_parent: Path
) -> None:
    """Control: nothing moves a running Dispatcher's assets to another tree.

    This is the half of the split that must NOT follow the candidate root. The
    workflow asset directory has to sit inside the payload, because that is the
    tree which survives the installation being evicted.
    """
    install_root = _install(root=install_parent / _BUILD_ID)

    report = _resolve_roots(plugin_root=install_root, tmp_path=tmp_path, export_claude_root=False)

    payload_root = report["executing_payload_root"]
    assert report["workflow_asset_parent"].startswith(
        payload_root
    ), f"packaged assets no longer resolve inside the payload: {report}"
    assert not report["workflow_asset_parent"].startswith(
        str(install_root)
    ), f"packaged assets resolve inside the evictable installation: {report}"


def test_this_projects_own_checkout_still_resolves_to_itself(tmp_path: Path) -> None:
    """Control: a source checkout is never retained, so both roots coincide.

    With no environment help at all. If the fix made the candidate root depend
    on a launcher record, a tree that never provisions one must still resolve
    normally — otherwise every in-repo CLI run changes behaviour.
    """
    checkout_parent = tmp_path / "checkout"
    checkout_parent.mkdir()
    _ = (checkout_parent / "pyproject.toml").write_text(_THIS_PROJECT, encoding="utf-8")
    checkout = _install(root=checkout_parent / ".claude-plugin")

    report = _resolve_roots(plugin_root=checkout, tmp_path=tmp_path, export_claude_root=False)

    assert report["plugin_root"] == str(
        checkout
    ), f"a source checkout no longer resolves to itself: {report}"
    assert report["executing_payload_root"] == str(
        checkout
    ), f"a source checkout was retained when it must not be: {report}"

"""Concurrent invocations each run their OWN release, for code and for assets.

Two installed payloads can carry the SAME `plugin.json` version and still be
different trees: a cache rebuilt at the same release, a locally-installed
marketplace copy, a release re-cut from a different commit, or simply an
earlier run of this very test. Version TEXT is not content provenance, so a
payload keyed by version alone and ADOPTED when it already exists lets one
invocation execute a different source's code — silently, because the adopted
tree is complete and imports cleanly.

This test makes the two installs distinguishable WITHOUT waiting for a second
real release: both keep the repository's own manifest version, and each gets
its own marker in two places the invocation must resolve independently — a
packaged module (deferred CODE) and the bundled workflow manifest (a packaged
ASSET read through the public `workflow_toml` resolution).

Both children complete the real `bootstrap()` and park. The OLDER install is
then deleted, both are released, and each must report its own marker from both
places. A shared payload fails this however the publish race lands: whichever
invocation loses adopts the other's tree and reports the other's marker.

Real child processes are the only way to ask this — two of them, concurrently,
with one source tree removed between launch and use — so this file is listed
in `pyproject.toml`'s `subprocess_spawn_allowlist` and scrubs the coverage
subprocess hooks exactly as an allowlisted spawn must.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import IO, cast

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = _REPO_ROOT / ".claude-plugin"

_LAUNCHER_FINISHED = "launcher-finished"
_RELEASE_CHILD = "go\n"
_DEFERRED_TIMEOUT_SECONDS = 300.0

# The two distinguishable installs. The names describe their ROLE in the
# scenario — the older one is the tree the harness evicts — not a version
# difference: both carry the repository's own manifest version, which is the
# whole point.
_OLDER = "older-install"
_NEWER = "newer-install"

_MARKER_MODULE = "_retention_fixture_marker"
_ASSET_MARKER_PREFIX = "# retention-fixture-marker: "
_ASSET_RELPATH = (".fabro", "workflows", "implement-work-item", "workflow.toml")
_MARKER_RELPATH = ("scripts", "livespec_orchestrator_beads_fabro", "commands")

# Runs inside each spawned child. argv is [install_root, result_path]. Every
# import and read below happens AFTER the handshake, so none of it was resolved
# while the evicted install still existed.
_PROBE = """
import argparse
import importlib
import json
import sys
from pathlib import Path

install_root, result_path = sys.argv[1:3]

sys.path.insert(0, str(Path(install_root) / "scripts" / "bin"))
import _bootstrap

_bootstrap.bootstrap()

sys.stdout.write("launcher-finished\\n")
sys.stdout.flush()
_ = sys.stdin.readline()

marker = importlib.import_module(
    "livespec_orchestrator_beads_fabro.commands._retention_fixture_marker"
)
paths = importlib.import_module("livespec_orchestrator_beads_fabro.commands._dispatcher_paths")

manifest = paths.workflow_toml(args=argparse.Namespace(workflow=None))
asset_lines = manifest.read_text(encoding="utf-8").strip().splitlines()

Path(result_path).write_text(
    json.dumps(
        {
            "code_marker": marker.MARKER,
            "code_file": marker.__file__,
            "asset_marker": asset_lines[-1],
            "manifest": str(manifest),
        }
    ),
    encoding="utf-8",
)
"""


def _install(*, root: Path, marker: str) -> Path:
    """A disposable installed payload, marked in its CODE and in its ASSET.

    The manifest is left exactly as the repository ships it, so both installs
    report the same release and a version-keyed payload is guaranteed to
    collide.
    """
    _ = shutil.copytree(_PLUGIN_ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
    _ = root.joinpath(*_MARKER_RELPATH, f"{_MARKER_MODULE}.py").write_text(
        f'MARKER = "{marker}"\n', encoding="utf-8"
    )
    asset = root.joinpath(*_ASSET_RELPATH)
    _ = asset.write_text(
        f"{asset.read_text(encoding='utf-8')}\n{_ASSET_MARKER_PREFIX}{marker}\n",
        encoding="utf-8",
    )
    return root


def _child_env(*, install_root: Path) -> dict[str, str]:
    scrubbed = ("PYTHONPATH", "COVERAGE_PROCESS_START")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in scrubbed and not key.startswith("COV_CORE_")
    }
    env["CLAUDE_PLUGIN_ROOT"] = str(install_root)
    env["BEADS_DOLT_PASSWORD"] = "test-not-a-real-secret"
    return env


def _launch(*, install_root: Path, result_path: Path, cwd: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-c", _PROBE, str(install_root), str(result_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_child_env(install_root=install_root),
        cwd=str(cwd),
    )


def test_concurrent_invocations_each_use_their_own_release_for_code_and_assets(
    tmp_path: Path,
) -> None:
    older_install = _install(root=tmp_path / _OLDER, marker=_OLDER)
    newer_install = _install(root=tmp_path / _NEWER, marker=_NEWER)
    older_result = tmp_path / "older-result.json"
    newer_result = tmp_path / "newer-result.json"

    older = _launch(install_root=older_install, result_path=older_result, cwd=tmp_path)
    newer = _launch(install_root=newer_install, result_path=newer_result, cwd=tmp_path)
    # Both launchers finish BEFORE either is released, so both have provisioned
    # whatever they are going to provision while both installs still existed.
    older_handshake = cast("IO[str]", older.stdout).readline()
    newer_handshake = cast("IO[str]", newer.stdout).readline()
    shutil.rmtree(older_install)
    older_stdout, older_stderr = older.communicate(
        input=_RELEASE_CHILD, timeout=_DEFERRED_TIMEOUT_SECONDS
    )
    newer_stdout, newer_stderr = newer.communicate(
        input=_RELEASE_CHILD, timeout=_DEFERRED_TIMEOUT_SECONDS
    )

    assert (
        older_handshake.strip() == _LAUNCHER_FINISHED
    ), f"the older invocation's launcher did not finish:\n{older_stdout}\n{older_stderr}"
    assert (
        newer_handshake.strip() == _LAUNCHER_FINISHED
    ), f"the newer invocation's launcher did not finish:\n{newer_stdout}\n{newer_stderr}"
    assert not older_install.exists(), "the older installation was not actually removed"
    assert (
        older.returncode == 0
    ), f"the older invocation did not complete:\n{older_stdout}\n{older_stderr}"
    assert (
        newer.returncode == 0
    ), f"the newer invocation did not complete:\n{newer_stdout}\n{newer_stderr}"

    older_record = json.loads(older_result.read_text(encoding="utf-8"))
    newer_record = json.loads(newer_result.read_text(encoding="utf-8"))
    assert older_record["code_marker"] == _OLDER, (
        "the older invocation executed another release's CODE — its payload was "
        f"not its own: {older_record}"
    )
    assert newer_record["code_marker"] == _NEWER, (
        "the newer invocation executed another release's CODE — its payload was "
        f"not its own: {newer_record}"
    )
    assert (
        older_record["asset_marker"] == f"{_ASSET_MARKER_PREFIX}{_OLDER}"
    ), f"the older invocation read another release's ASSET: {older_record}"
    assert (
        newer_record["asset_marker"] == f"{_ASSET_MARKER_PREFIX}{_NEWER}"
    ), f"the newer invocation read another release's ASSET: {newer_record}"
    assert older_record["manifest"] != newer_record["manifest"], (
        "both invocations resolved the SAME payload, so neither is private to "
        f"its own invocation: {older_record} {newer_record}"
    )

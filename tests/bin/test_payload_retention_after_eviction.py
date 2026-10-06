"""Regression guard: one retained payload survives plugin-cache eviction mid-invocation.

The host incident this guards (work-item `bd-ib-mtuqxb`): PID 1894716 was
still running an installed Codex cache's `scripts/bin/drive.py` while that
cache directory had already disappeared, and `bd-ib-3ftj` records the real
`_dispatcher_cost_wave` `ModuleNotFoundError` that shape produces. A plugin
launcher that leaves `sys.path` and `CLAUDE_PLUGIN_ROOT` pointing INTO the
harness-managed cache loses its deferred code, its packaged assets and its
`scripts/bin/` helpers the moment the harness evicts that cache — hours into
a dispatch, long after any startup-completeness check has passed.

This test reproduces the eviction faithfully rather than simulating it. It
copies the real plugin root into a DISPOSABLE fixture installation, launches
a real child process that calls the real `bin/_bootstrap.bootstrap()` from
that installation, waits for the child to signal that the launcher finished,
then DELETES the whole fixture installation. Only then does it release the
child to do the deferred work an invocation does hours in:

- import the packaged drive implementation route
  (`livespec_orchestrator_beads_fabro.commands.drive`) and the packaged
  Dispatcher entry route (`...commands.dispatcher`) for the first time;
- read a packaged asset through the public bundled-workflow resolution
  (`_dispatcher_paths.workflow_toml`);
- execute a `scripts/bin/` helper as a real subprocess.

Nothing here is importable in-process: the question is definitionally about
what a SECOND process sees after its source tree is gone, so the spawn is
listed in `pyproject.toml`'s `subprocess_spawn_allowlist` and scrubs the
coverage subprocess hooks exactly as an allowlisted spawn must.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = _REPO_ROOT / ".claude-plugin"

# How long the parent waits for the child's startup handshake, and how long it
# then allows the deferred work to finish. Bounded so a wedged child fails the
# test instead of hanging the suite.
_HANDSHAKE_TIMEOUT_SECONDS = 120.0
_DEFERRED_TIMEOUT_SECONDS = 180.0
_POLL_SECONDS = 0.05

# Runs inside the spawned child. argv is
# [install_root, ready_path, go_path, result_path].
#
# The launcher under test is `bin/_bootstrap.bootstrap()` — the one chokepoint
# every `bin/*.py` wrapper calls before any packaged import. Everything after
# the handshake is DEFERRED work: none of these modules, assets or helpers has
# been touched while the fixture installation still existed.
_PROBE = """
import argparse
import importlib
import json
import subprocess
import sys
import time
from pathlib import Path

install_root, ready_path, go_path, result_path = sys.argv[1:5]

bin_dir = str(Path(install_root) / "scripts" / "bin")
if bin_dir not in sys.path:
    sys.path.insert(0, bin_dir)
import _bootstrap

_bootstrap.bootstrap()

Path(ready_path).write_text("ready", encoding="utf-8")
deadline = time.monotonic() + 300.0
while not Path(go_path).exists():
    if time.monotonic() > deadline:
        raise SystemExit("child timed out waiting for the eviction handshake")
    time.sleep(0.05)

drive = importlib.import_module("livespec_orchestrator_beads_fabro.commands.drive")
dispatcher = importlib.import_module("livespec_orchestrator_beads_fabro.commands.dispatcher")
paths = importlib.import_module(
    "livespec_orchestrator_beads_fabro.commands._dispatcher_paths"
)

manifest = paths.workflow_toml(args=argparse.Namespace(workflow=None))
manifest_text = manifest.read_text(encoding="utf-8")

helper = Path(drive.__file__).resolve().parents[2] / "bin" / "next.py"
completed = subprocess.run(
    [sys.executable, str(helper), "--help"],
    capture_output=True,
    text=True,
    check=False,
)

Path(result_path).write_text(
    json.dumps(
        {
            "drive_file": drive.__file__,
            "dispatcher_file": dispatcher.__file__,
            "manifest": str(manifest),
            "manifest_length": len(manifest_text),
            "helper": str(helper),
            "helper_returncode": completed.returncode,
            "helper_stdout_length": len(completed.stdout),
        }
    ),
    encoding="utf-8",
)
"""


def _child_env(*, install_root: Path) -> dict[str, str]:
    """The child's environment: the fixture installation as the plugin cache.

    `CLAUDE_PLUGIN_ROOT` is what a native plugin install exports, so the
    fixture sets it to the disposable installation — the tree this test
    deletes mid-invocation. The coverage subprocess hooks are scrubbed per
    the `subprocess_spawn_allowlist` contract, `PYTHONPATH` so no inherited
    path leaks the repo's own tree back in, and a placeholder tenant secret
    keeps the credential self-heal on its `Proceed` arm (this guard is about
    payload lifetime, not credentials).
    """
    scrubbed = ("PYTHONPATH", "COVERAGE_PROCESS_START")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in scrubbed and not key.startswith("COV_CORE_")
    }
    env["CLAUDE_PLUGIN_ROOT"] = str(install_root)
    env["BEADS_DOLT_PASSWORD"] = "test-not-a-real-secret"
    return env


def _wait_for(*, path: Path, timeout: float, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            message = f"child exited early (rc={process.returncode})\n{stdout}\n{stderr}"
            raise AssertionError(message)
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out after {timeout}s waiting for {path}")
        time.sleep(_POLL_SECONDS)


def test_deferred_work_runs_from_the_retained_payload_after_the_install_is_removed(
    tmp_path: Path,
) -> None:
    install_root = tmp_path / "install"
    shutil.copytree(_PLUGIN_ROOT, install_root, ignore=shutil.ignore_patterns("__pycache__"))
    ready_path = tmp_path / "ready"
    go_path = tmp_path / "go"
    result_path = tmp_path / "result.json"

    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _PROBE,
            str(install_root),
            str(ready_path),
            str(go_path),
            str(result_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_child_env(install_root=install_root),
        cwd=str(tmp_path),
    )
    try:
        _wait_for(path=ready_path, timeout=_HANDSHAKE_TIMEOUT_SECONDS, process=process)
        shutil.rmtree(install_root)
        assert not install_root.exists(), "the fixture installation was not actually removed"
        go_path.write_text("go", encoding="utf-8")
        stdout, stderr = process.communicate(timeout=_DEFERRED_TIMEOUT_SECONDS)
    finally:
        if process.poll() is None:
            process.kill()
            _ = process.communicate()

    assert process.returncode == 0, (
        "deferred work did NOT complete after the plugin installation was removed "
        "mid-invocation — the launcher left this process depending on the evicted "
        f"cache instead of retaining its own complete payload:\n{stdout}\n{stderr}"
    )
    record = json.loads(result_path.read_text(encoding="utf-8"))
    assert not record["drive_file"].startswith(
        f"{install_root}{os.sep}"
    ), f"the drive implementation was imported from the removed install: {record}"
    assert not record["dispatcher_file"].startswith(
        f"{install_root}{os.sep}"
    ), f"the Dispatcher entry route was imported from the removed install: {record}"
    assert record["manifest_length"] > 0, f"the packaged workflow asset read empty: {record}"
    assert (
        record["helper_returncode"] == 0
    ), f"the scripts/bin helper subprocess did not run from the payload: {record}"
    assert record["helper_stdout_length"] > 0, f"the helper produced no output: {record}"

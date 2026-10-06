"""A payload is released at completion — and not one moment before.

The retention has a lifetime, and both ends of it matter. One dispatch spans a
`drive` process, the `dispatcher.py` child it spawns, and the helpers that
child spawns in turn; every one of them has to keep reading the SAME payload,
so a child must REUSE its parent's rather than copy the copy. And when the
invocation finishes, its private tree has to go: a factory host that leaks one
payload per dispatch fills its disk.

What must not be collateral damage, and is what makes "only after" load-bearing:

- a helper the invocation owns, which must have run successfully FROM that
  payload while it still existed;
- a DIFFERENT invocation that is still live, whose own payload must survive
  the first one's cleanup untouched;
- the harness-managed installation itself, which the launcher only ever reads
  — a fresh invocation from it must still work afterwards.

Two concurrent children plus a grandchild, with one of them exiting while the
other is parked, is the whole question here, so this file is listed in
`pyproject.toml`'s `subprocess_spawn_allowlist` and scrubs the coverage
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

# Runs inside each spawned child. argv is [install_root, result_path].
#
# After the handshake it spawns a HELPER through the packaged launcher from its
# own payload — the shape `drive` uses when it starts `dispatcher.py`, and then
# `dispatcher.py` uses for its own helpers — and reports which payload that
# helper resolved. It writes NOTHING into the payload: a running invocation
# reads its own artifact and never modifies it.
_PROBE = """
import importlib
import json
import subprocess
import sys
from pathlib import Path

install_root, result_path = sys.argv[1:3]

sys.path.insert(0, str(Path(install_root) / "scripts" / "bin"))
import _bootstrap

_bootstrap.bootstrap()

paths = importlib.import_module("livespec_orchestrator_beads_fabro.commands._dispatcher_paths")
payload_root = Path(paths.__file__).resolve().parents[3]

sys.stdout.write("launcher-finished\\n")
sys.stdout.flush()
_ = sys.stdin.readline()

helper_result = Path(result_path).with_suffix(".helper.json")
completed = subprocess.run(
    [sys.executable, "-c", HELPER_SOURCE, str(payload_root), str(helper_result)],
    capture_output=True,
    text=True,
    check=False,
    timeout=120,
)

Path(result_path).write_text(
    json.dumps(
        {
            "payload_root": str(payload_root),
            "helper_returncode": completed.returncode,
            "helper_stderr": completed.stderr,
            "helper_result": str(helper_result),
        }
    ),
    encoding="utf-8",
)
"""

# Runs inside the HELPER grandchild. argv is [payload_root, result_path]. It
# enters through the same packaged launcher and reports which payload IT ended
# up executing, which is how "the child reuses its parent's payload" is
# observed rather than assumed.
_HELPER = """
import importlib
import json
import sys
from pathlib import Path

payload_root, result_path = sys.argv[1:3]

sys.path.insert(0, str(Path(payload_root) / "scripts" / "bin"))
import _bootstrap

_bootstrap.bootstrap()

paths = importlib.import_module("livespec_orchestrator_beads_fabro.commands._dispatcher_paths")
Path(result_path).write_text(
    json.dumps(
        {
            "payload_root": str(Path(paths.__file__).resolve().parents[3]),
            "module_file": paths.__file__,
        }
    ),
    encoding="utf-8",
)
"""


def _install(*, root: Path) -> Path:
    _ = shutil.copytree(_PLUGIN_ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
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
    source = f"HELPER_SOURCE = {_HELPER!r}\n{_PROBE}"
    return subprocess.Popen(
        [sys.executable, "-c", source, str(install_root), str(result_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_child_env(install_root=install_root),
        cwd=str(cwd),
    )


def test_a_completed_invocation_releases_its_payload_and_nothing_else(tmp_path: Path) -> None:
    finishing_install = _install(root=tmp_path / "finishing-install")
    parked_install = _install(root=tmp_path / "parked-install")
    finishing_result = tmp_path / "finishing.json"
    parked_result = tmp_path / "parked.json"

    finishing = _launch(install_root=finishing_install, result_path=finishing_result, cwd=tmp_path)
    parked = _launch(install_root=parked_install, result_path=parked_result, cwd=tmp_path)
    finishing_handshake = cast("IO[str]", finishing.stdout).readline()
    parked_handshake = cast("IO[str]", parked.stdout).readline()
    # Only the FIRST invocation is released, so it completes and cleans up
    # while the second is still parked with a live payload of its own.
    finishing_stdout, finishing_stderr = finishing.communicate(
        input=_RELEASE_CHILD, timeout=_DEFERRED_TIMEOUT_SECONDS
    )

    assert (
        finishing_handshake.strip() == _LAUNCHER_FINISHED
    ), f"the finishing launcher did not finish:\n{finishing_stdout}\n{finishing_stderr}"
    assert parked_handshake.strip() == _LAUNCHER_FINISHED, "the parked launcher did not finish"
    assert (
        finishing.returncode == 0
    ), f"the finishing invocation did not complete:\n{finishing_stdout}\n{finishing_stderr}"

    record = json.loads(finishing_result.read_text(encoding="utf-8"))
    assert (
        record["helper_returncode"] == 0
    ), f"the owned helper did not run from the payload:\n{record['helper_stderr']}"
    helper = json.loads(Path(record["helper_result"]).read_text(encoding="utf-8"))
    assert helper["payload_root"] == record["payload_root"], (
        "the owned helper did not REUSE its parent's payload — it provisioned a "
        f"copy of the copy: {helper} vs {record}"
    )

    finished_payload = Path(record["payload_root"])
    assert (
        not finished_payload.exists()
    ), f"the completed invocation leaked its private payload: {finished_payload}"

    # Everything the cleanup must NOT have touched.
    parked_stdout, parked_stderr = parked.communicate(
        input=_RELEASE_CHILD, timeout=_DEFERRED_TIMEOUT_SECONDS
    )
    assert parked.returncode == 0, (
        "the still-live invocation was broken by the other one's cleanup:\n"
        f"{parked_stdout}\n{parked_stderr}"
    )
    parked_record = json.loads(parked_result.read_text(encoding="utf-8"))
    assert parked_record["payload_root"] != record["payload_root"]
    assert parked_install.is_dir(), "the harness-managed installation was removed"

    fresh_result = tmp_path / "fresh.json"
    fresh = _launch(install_root=parked_install, result_path=fresh_result, cwd=tmp_path)
    fresh_handshake = cast("IO[str]", fresh.stdout).readline()
    fresh_stdout, fresh_stderr = fresh.communicate(
        input=_RELEASE_CHILD, timeout=_DEFERRED_TIMEOUT_SECONDS
    )
    assert fresh_handshake.strip() == _LAUNCHER_FINISHED, "a fresh invocation could not launch"
    assert (
        fresh.returncode == 0
    ), f"a fresh invocation from the installation failed:\n{fresh_stdout}\n{fresh_stderr}"

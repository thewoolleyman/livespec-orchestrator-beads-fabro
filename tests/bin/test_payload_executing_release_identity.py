"""The EXECUTING release is read from the retained bytes, not from the install path.

Cycle 5 kept `plugin_root()` naming the INSTALLED tree so the self-update
canary could still discover a newer build. That is necessary and it is not
sufficient: two surfaces ask "which release am I EXECUTING", and both still
resolved it through that same installed path, which the harness owns and may
delete or overwrite at any moment.

- `_dispatcher_self_update._RUNNING_RELEASE_VERSION` is captured at the module's
  FIRST import, which for a dispatch is deferred well past the launcher. Read
  through `plugin_root()` it has two wrong answers available: `None`, when the
  original cache has been deleted by then; and the REPLACEMENT's release, when
  the harness has installed a newer build at the same path. The second is the
  dangerous one — the canary compares running against available, so a running
  release that reports as the replacement makes the two equal and the canary
  can never fire for the very update it exists to validate.
- `_dispatcher_loop_selection.prepare` hands `plugin_root()` to the
  minimum-release floor, whose `released_payload_version(root=...)` decides
  whether the EXECUTING build clears a committed floor. Reading the
  replacement there silently passes a floor for a build that does not meet it,
  which is the one blocking currency form the contract has.

The retained payload is immutable for the lifetime of the invocation, so it is
the only thing that can answer this question stably. The cases below drive the
real launcher in a real child, let the LAUNCHER finish, then mutate the
installation exactly as the harness would — delete it, or replace its manifest
at the same path — and only then trigger the deferred first import.

The frozen `test_payload_candidate_and_credential_boundary.py` reads
`executing_release` but asserts nothing about it after deletion, and its
candidate assertion is on the canary TARGET PATH rather than on a canary
outcome against a genuinely newer candidate. Those are the gaps here; that
file is untouched.

Real child processes are the only way to ask this — the question is what a
module-level constant captures at a deferred import, after the filesystem has
changed underneath a live process — so this file is listed in
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
_TIMEOUT_SECONDS = 300.0
# The release the fixture installs, and the NEWER one a replacement lands at
# the same path. Both are far from any real version so a stale read is obvious.
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_INSTALLED_RELEASE = "7.1.0"
_REPLACEMENT_RELEASE = "9.9.9"

# Runs inside the child. argv is [install_root, result_path].
#
# Everything after the handshake is a DEFERRED FIRST IMPORT — the shape a
# dispatch has, where the self-update module is not touched until long after
# the launcher finished and the installation may already have changed.
_PROBE = """
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

paths = importlib.import_module("livespec_orchestrator_beads_fabro.commands._dispatcher_paths")
self_update = importlib.import_module(
    "livespec_orchestrator_beads_fabro.commands._dispatcher_self_update"
)
decision = importlib.import_module(
    "livespec_orchestrator_beads_fabro.commands._dispatcher_self_update_decision"
)
floor = importlib.import_module(
    "livespec_orchestrator_beads_fabro.commands._dispatcher_minimum_release_floor"
)

# The production inputs of the canary, read exactly as
# `self_update_after_verdict` reads them.
running = self_update.running_release_version(
    running_release=self_update._RUNNING_RELEASE_VERSION
)
available = self_update.released_payload_version(root=paths.plugin_root())
canary = decision.release_update_decision(running_release=running, available_release=available)

verdict = floor.minimum_release_verdict(plugin_root=paths.plugin_root(), cwd=Path.cwd())

Path(result_path).write_text(
    json.dumps(
        {
            "running_release": self_update._RUNNING_RELEASE_VERSION,
            "available_release": available,
            "canary_update_required": canary.update_required,
            "canary_reason": canary.reason,
            "floor_configured": verdict is not None,
            "floor_refusal": None if verdict is None else verdict.refusal_detail,
            "floor_undetermined": None if verdict is None else verdict.undetermined_detail,
            "plugin_root": str(paths.plugin_root()),
            "payload_root": str(Path(paths.__file__).resolve().parents[3]),
        }
    ),
    encoding="utf-8",
)
"""


def _install(*, root: Path, release: str) -> Path:
    _ = shutil.copytree(_PLUGIN_ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
    _ = (root / "plugin.json").write_text(
        json.dumps({"name": "livespec-orchestrator-beads-fabro", "version": release}),
        encoding="utf-8",
    )
    return root


def _target_repo(*, root: Path, minimum_release: str | None = None) -> Path:
    (root / ".beads").mkdir(parents=True)
    _ = (root / ".beads" / "config.yaml").write_text("dolt.mode: server\n", encoding="utf-8")
    # The floor is read at `<plugin-block>.dispatcher.minimum_release`, NOT at
    # the top level. A top-level `dispatcher` block configures NO floor, the
    # verdict comes back `None`, and a floor assertion then proves nothing —
    # which is exactly how the first draft of this case asserted nothing at all.
    config: dict[str, object] = {}
    if minimum_release is not None:
        config[_PLUGIN_BLOCK] = {"dispatcher": {"minimum_release": minimum_release}}
    _ = (root / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    return root


def _launch(*, install_root: Path, repo: Path, result_path: Path) -> subprocess.Popen[str]:
    scrubbed = ("PYTHONPATH", "COVERAGE_PROCESS_START")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in scrubbed and not key.startswith("COV_CORE_")
    }
    env["CLAUDE_PLUGIN_ROOT"] = str(install_root)
    env["BEADS_DOLT_PASSWORD"] = "test-not-a-real-secret"
    return subprocess.Popen(
        [sys.executable, "-c", _PROBE, str(install_root), str(result_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(repo),
    )


def _drive(*, install_root: Path, repo: Path, result_path: Path, mutate) -> dict[str, object]:
    """Run the launcher, mutate the installation as the harness would, then report."""
    process = _launch(install_root=install_root, repo=repo, result_path=result_path)
    handshake = cast("IO[str]", process.stdout).readline()
    mutate()
    stdout, stderr = process.communicate(input=_RELEASE_CHILD, timeout=_TIMEOUT_SECONDS)
    assert (
        handshake.strip() == _LAUNCHER_FINISHED
    ), f"the launcher did not finish:\n{handshake}\n{stdout}\n{stderr}"
    assert (
        process.returncode == 0
    ), f"the deferred first import did not complete:\n{stdout}\n{stderr}"
    return cast("dict[str, object]", json.loads(result_path.read_text(encoding="utf-8")))


def test_the_executing_release_survives_deletion_of_the_installation(tmp_path: Path) -> None:
    """A deferred first import after eviction must still know which build is running."""
    install_root = _install(root=tmp_path / "install", release=_INSTALLED_RELEASE)
    repo = _target_repo(root=tmp_path / "repo")

    record = _drive(
        install_root=install_root,
        repo=repo,
        result_path=tmp_path / "result.json",
        mutate=lambda: shutil.rmtree(install_root),
    )

    assert not install_root.exists()
    assert record["running_release"] == _INSTALLED_RELEASE, (
        "the executing release was read from the deleted installation, so the "
        f"running build is now unknown: {record}"
    )


def test_a_replacement_at_the_same_path_is_not_reported_as_the_executing_release(
    tmp_path: Path,
) -> None:
    """The dangerous direction: the canary comparing the replacement against itself.

    When the harness installs a NEWER build over the same path, a running
    release read from that path reports the newcomer. Running and available
    then match, the canary records "no update required", and the one mechanism
    that would have validated the new build never runs.
    """
    install_root = _install(root=tmp_path / "install", release=_INSTALLED_RELEASE)
    repo = _target_repo(root=tmp_path / "repo")

    def _replace_with_newer() -> None:
        _ = (install_root / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "livespec-orchestrator-beads-fabro",
                    "version": _REPLACEMENT_RELEASE,
                }
            ),
            encoding="utf-8",
        )

    record = _drive(
        install_root=install_root,
        repo=repo,
        result_path=tmp_path / "result.json",
        mutate=_replace_with_newer,
    )

    assert (
        record["available_release"] == _REPLACEMENT_RELEASE
    ), f"fixture precondition: the candidate must be the newer build: {record}"
    assert record["running_release"] == _INSTALLED_RELEASE, (
        "the executing release was read from the REPLACEMENT, so the running "
        f"build misreports itself as the newcomer: {record}"
    )
    assert record["canary_update_required"] is True, (
        "the canary sees no update to validate because running and available "
        f"collapsed onto the same replacement: {record}"
    )


def test_the_minimum_release_floor_judges_the_executing_release_not_the_replacement(
    tmp_path: Path,
) -> None:
    """A committed floor must refuse a build that does not meet it.

    The floor is the ONE blocking currency form in the contract. With the
    executing release read from the install path, a replacement landing at that
    path satisfies the floor on the newcomer's behalf while the old build keeps
    dispatching — a silent pass for exactly the build the operator committed
    the floor to stop.
    """
    install_root = _install(root=tmp_path / "install", release=_INSTALLED_RELEASE)
    repo = _target_repo(root=tmp_path / "repo", minimum_release=_REPLACEMENT_RELEASE)

    def _replace_with_the_floor_build() -> None:
        _ = (install_root / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "livespec-orchestrator-beads-fabro",
                    "version": _REPLACEMENT_RELEASE,
                }
            ),
            encoding="utf-8",
        )

    record = _drive(
        install_root=install_root,
        repo=repo,
        result_path=tmp_path / "result.json",
        mutate=_replace_with_the_floor_build,
    )

    assert record["floor_configured"] is True, (
        "fixture precondition: no floor was configured, so this case proves "
        f"nothing — the key is nested under the plugin block: {record}"
    )
    assert (
        record["floor_undetermined"] is None
    ), f"the floor could not be evaluated at all: {record}"
    assert record["floor_refusal"] is not None, (
        "the committed floor passed for a build that does not meet it — it was "
        f"judged against the replacement, not the executing release: {record}"
    )
    assert _INSTALLED_RELEASE in cast(
        "str", record["floor_refusal"]
    ), f"the refusal does not name the executing release it refused: {record}"


def test_an_untouched_installation_reports_itself_and_clears_its_floor(
    tmp_path: Path,
) -> None:
    """The control: none of the above may be achieved by always reading the payload wrong.

    With nothing mutated, the executing release, the candidate and the floor
    must all agree on the installed build — so a fix cannot pass the cases
    above by reporting some other release.
    """
    install_root = _install(root=tmp_path / "install", release=_INSTALLED_RELEASE)
    repo = _target_repo(root=tmp_path / "repo", minimum_release=_INSTALLED_RELEASE)

    record = _drive(
        install_root=install_root,
        repo=repo,
        result_path=tmp_path / "result.json",
        mutate=lambda: None,
    )

    assert record["running_release"] == _INSTALLED_RELEASE
    assert record["available_release"] == _INSTALLED_RELEASE
    assert (
        record["canary_update_required"] is False
    ), f"an untouched installation must offer no candidate: {record}"
    assert (
        record["floor_configured"] is True
    ), f"fixture precondition: the control's floor must be configured: {record}"
    assert record["floor_refusal"] is None, f"the floor refused its own build: {record}"
    assert record["floor_undetermined"] is None, f"the floor was unobservable: {record}"

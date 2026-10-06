"""Both NAMED public routes keep running after their installation is evicted.

Work-item `bd-ib-mtuqxb`'s first assertion names two entry points: "the
packaged drive implementation route or the packaged Dispatcher entry point".
The other regressions in this directory enter through `bin/_bootstrap.bootstrap`
or through a fixture wrapper; this one enters through the two SHIPPED
executables an operator and the factory actually invoke, `bin/drive.py` and
`bin/dispatcher.py`, and requires each to complete after its own installation
has been deleted mid-invocation.

The eviction is triggered where a real one can be observed on a route with no
test hook in it: the credential self-heal re-execs the process through the
project's `credential_wrapper`, so a wrapper double deletes the installation
and scrubs the payload environment variable the way `sudo` does, and the
re-executed CLI then does all of its remaining work with the installation
gone.

Both invocations are side-effect-free by construction. The ledger is the
in-memory fake (`LIVESPEC_BEADS_FAKE=1`), `ledger-check` is a read-only
surface, and the `impl:` action names an item that does not exist, so the
Dispatcher refuses at its factory-binary gate before anything is claimed and
no factory run is started. The drive route is still the real one end to end:
it resolves its `scripts/bin/dispatcher.py` helper, SPAWNS it as a real
subprocess, and reports that helper's path and exit code back in its own JSON
envelope — which is what makes "the helper ran from the original release"
observable rather than assumed.

Packaged ASSET reads after eviction are proven on a packaged `bin/` wrapper by
`test_payload_candidate_and_credential_boundary.py` and by the frozen
`test_payload_retention_after_eviction.py`; neither public route above reaches
a `.fabro/` asset without starting a factory run, which a test must not do.

This file is NOT the Red of a Red-Green pair, and should not be read as one.
It was authored after the five pairs that implement work-item `bd-ib-mtuqxb`,
to cover the two entry points its first assertion NAMES but none of those
pairs invoked, so it passed the moment it was written. What makes it a guard
rather than a tautology is a measured CONTROL, run 2026-10-06: pointed at the
pre-fix plugin tree (`f62f2f73`, which carries no `bin/_payload.py`), BOTH
cases fail — each CLI exits 2 having never produced any output, because after
the eviction the interpreter cannot open the script the credential wrapper was
asked to run. Re-point `_PLUGIN_ROOT` at an extract of that commit to
reproduce it.

Real child processes are the only way to ask any of this, so this file is
listed in `pyproject.toml`'s `subprocess_spawn_allowlist` and scrubs the
coverage subprocess hooks exactly as an allowlisted spawn must.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = _REPO_ROOT / ".claude-plugin"

_CLI_TIMEOUT_SECONDS = 300.0
_PLACEHOLDER_SECRET = "test-not-a-real-secret"
_WRAPPER_SEPARATOR = "--"
_MISSING_ITEM = "bd-pb-does-not-exist"

# Injects the secret the self-heal is re-execing to obtain, EVICTS the
# installation, and scrubs the payload hand-down variable exactly as the real
# wrapper's `sudo` stage does — so the re-executed process has to reach a
# usable tree from its own argv.
_WRAPPER_DOUBLE = f"""#!/bin/sh
[ "$1" = "{_WRAPPER_SEPARATOR}" ] && shift
printf 'invoked\\n' > "$LIVESPEC_TEST_WRAPPER_MARKER"
rm -rf "$LIVESPEC_TEST_EVICT"
unset LIVESPEC_RETAINED_PAYLOAD_ROOT
export BEADS_DOLT_PASSWORD={_PLACEHOLDER_SECRET}
exec "$@"
"""

# A dispatch target with a hermetic in-memory ledger. `fake` plus
# `LIVESPEC_BEADS_FAKE` keeps every store read and write in process.
_TARGET_CONFIG = {
    "livespec-orchestrator-beads-fabro": {
        "connection": {
            "tenant": "probe-tenant",
            "prefix": "bd-pb",
            "database": "probe-tenant",
            "server_user": "probe-tenant",
            "fake": True,
        }
    }
}


def _install(*, root: Path) -> Path:
    _ = shutil.copytree(_PLUGIN_ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def _target_repo(*, root: Path) -> Path:
    (root / ".beads").mkdir(parents=True)
    # The FLAT dotted form `bd` uses, and the one the launcher's server-mode
    # marker matches — a nested mapping does not, which would make the secret
    # optional and the re-exec never happen.
    _ = (root / ".beads" / "config.yaml").write_text("dolt.mode: server\n", encoding="utf-8")
    return root


def _run_evicting(*, install_root: Path, repo: Path, argv: list[str], tmp_path: Path):
    """Run one packaged CLI, evicting its installation at the credential re-exec."""
    marker = tmp_path / "wrapper-invoked"
    wrapper = tmp_path / "with-livespec-env-double.sh"
    _ = wrapper.write_text(_WRAPPER_DOUBLE, encoding="utf-8")
    wrapper.chmod(0o755)
    config = dict(_TARGET_CONFIG)
    config["credential_wrapper"] = [str(wrapper), _WRAPPER_SEPARATOR]
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")

    scrubbed = ("PYTHONPATH", "COVERAGE_PROCESS_START")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in scrubbed and not key.startswith("COV_CORE_")
    }
    _ = env.pop("BEADS_DOLT_PASSWORD", None)
    _ = env.pop("LIVESPEC_CREDENTIAL_REEXEC", None)
    env["CLAUDE_PLUGIN_ROOT"] = str(install_root)
    env["LIVESPEC_BEADS_FAKE"] = "1"
    env["LIVESPEC_TEST_WRAPPER_MARKER"] = str(marker)
    env["LIVESPEC_TEST_EVICT"] = str(install_root)

    completed = subprocess.run(
        [sys.executable, *argv],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo),
        check=False,
        timeout=_CLI_TIMEOUT_SECONDS,
    )
    return completed, marker


def test_the_packaged_dispatcher_entry_point_completes_after_eviction(tmp_path: Path) -> None:
    """`bin/dispatcher.py ledger-check` — the direct Dispatcher entry route."""
    install_root = _install(root=tmp_path / "install")
    repo = _target_repo(root=tmp_path / "repo")

    completed, marker = _run_evicting(
        install_root=install_root,
        repo=repo,
        argv=[str(install_root / "scripts" / "bin" / "dispatcher.py"), "ledger-check"],
        tmp_path=tmp_path,
    )

    assert marker.exists(), (
        "the credential wrapper was never invoked, so the installation was never "
        f"evicted mid-invocation:\n{completed.stdout}\n{completed.stderr}"
    )
    assert not install_root.exists(), "the wrapper did not actually evict the installation"
    assert completed.returncode == 0, (
        "the packaged Dispatcher entry point did not complete after its "
        f"installation was evicted:\n{completed.stdout}\n{completed.stderr}"
    )
    assert (
        "ledger findings" in completed.stdout
    ), f"the Dispatcher produced no ledger-check result:\n{completed.stdout}"


def test_the_packaged_drive_route_runs_its_helper_from_the_payload_after_eviction(
    tmp_path: Path,
) -> None:
    """`bin/drive.py --action impl:<id>` — the packaged drive implementation route.

    Its helper is the thing under observation: drive resolves
    `scripts/bin/dispatcher.py` out of the tree its own module was loaded
    from, spawns it, and reports both the argv and the helper's exit code. A
    helper path under the evicted installation could not have run at all.
    """
    install_root = _install(root=tmp_path / "install")
    repo = _target_repo(root=tmp_path / "repo")

    completed, marker = _run_evicting(
        install_root=install_root,
        repo=repo,
        argv=[
            str(install_root / "scripts" / "bin" / "drive.py"),
            "--repo",
            str(repo),
            "--action",
            f"impl:{_MISSING_ITEM}",
            "--invoker",
            "test:public-route",
            "--json",
        ],
        tmp_path=tmp_path,
    )

    assert marker.exists(), (
        "the credential wrapper was never invoked, so the installation was never "
        f"evicted mid-invocation:\n{completed.stdout}\n{completed.stderr}"
    )
    assert not install_root.exists(), "the wrapper did not actually evict the installation"
    assert completed.stdout.strip(), (
        "the packaged drive route produced no result at all after its "
        f"installation was evicted:\nexit={completed.returncode}\n{completed.stderr}"
    )
    payload = json.loads(completed.stdout)
    assert (
        payload["action_id"] == f"impl:{_MISSING_ITEM}"
    ), f"the drive route did not produce its own result envelope: {payload}"
    helper_argv = payload["dispatcher"]["argv"]
    assert not helper_argv[1].startswith(f"{install_root}{os.sep}"), (
        "the drive route resolved its Dispatcher helper inside the evicted "
        f"installation, so the helper could not have run: {helper_argv}"
    )
    assert isinstance(
        payload["dispatcher"]["exit_code"], int
    ), f"the helper subprocess never ran to completion: {payload}"
    # The domain answer for an item that does not exist, reached through a
    # refusal rather than a claim: the Dispatcher stops at its factory-binary
    # gate, so nothing was claimed and no factory run was started.
    assert payload["status"] == "failed", f"unexpected drive status: {payload}"

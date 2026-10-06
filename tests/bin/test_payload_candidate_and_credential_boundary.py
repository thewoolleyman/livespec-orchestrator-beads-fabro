"""Retention must not move the Dispatcher, nor blind the surfaces that watch builds.

Retention changes WHERE an invocation reads its code and assets. It must not
change WHICH BUILD the invocation believes it is, nor which build it believes
is newest — those are two different questions that both resolve through
`_dispatcher_paths.plugin_root`, and collapsing them breaks the machinery that
exists to notice a stale session:

- `_dispatcher_self_update.self_update_after_verdict` compares the release
  captured at import against the one `plugin_root()` reports LATER, precisely
  so a newer build installed mid-run is discovered as a CANDIDATE. Point
  `plugin_root()` at the retained copy and that comparison is the retained
  build against itself: equal, forever, so the canary can never fire and the
  `candidate_dispatcher_bin()` it would exercise is the old build.
- `minimum_release_floor` and the registered-install currency finding read the
  same root to answer "which build is executing".

So `plugin_root()` keeps naming the INSTALLED tree, and the packaged ASSET
reads move to the payload instead. The first test pins both halves at once:
the installed root is still the installed root, and the bundled workflow
manifest nevertheless resolves inside the payload.

The second test covers the other boundary retention must not break. The
credential self-heal re-execs this process through the project's
`credential_wrapper`, and it builds that command from `sys.argv` — which names
the ORIGINAL cache path. If the cache is evicted around the re-exec, the
interpreter cannot even open the script it was asked to run: the invocation
dies before any application code, for exactly the reason retention exists. The
wrapper double here evicts the installation and scrubs the payload environment
variable the way `sudo` does, so the re-executed process has to reach a usable
tree from its own argv.

Both questions are about what a SECOND process sees, so this file is listed in
`pyproject.toml`'s `subprocess_spawn_allowlist` and scrubs the coverage
subprocess hooks exactly as an allowlisted spawn must.
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

# A shebang wrapper, written INTO the fixture installation so `sys.argv[0]`
# names a real packaged script — which is what the credential re-exec rebuilds
# its command from. It reports where it ended up executing.
_PROBE_WRAPPER = '''#!/usr/bin/env python3
"""Fixture wrapper: reports the build identities the launcher resolved."""

import importlib
import json
import os
import sys
from pathlib import Path

from _bootstrap import bootstrap

bootstrap()

paths = importlib.import_module("livespec_orchestrator_beads_fabro.commands._dispatcher_paths")
self_update = importlib.import_module(
    "livespec_orchestrator_beads_fabro.commands._dispatcher_self_update"
)

import argparse

manifest = paths.workflow_toml(args=argparse.Namespace(workflow=None))
Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "plugin_root": str(paths.plugin_root()),
            "payload_root": str(Path(paths.__file__).resolve().parents[3]),
            "manifest": str(manifest),
            "manifest_length": len(manifest.read_text(encoding="utf-8")),
            "candidate_dispatcher_bin": str(self_update.candidate_dispatcher_bin()),
            "executing_release": self_update.released_payload_version(root=paths.plugin_root()),
            "secret_present": bool(os.environ.get("BEADS_DOLT_PASSWORD")),
        }
    ),
    encoding="utf-8",
)
'''

# The credential-wrapper double. It reproduces the two behaviours of the real
# `with-livespec-env.sh` that matter here — it injects the tenant secret, and
# its `sudo` stage SCRUBS the environment — and it also evicts the
# installation, which is the condition under test.
_WRAPPER_DOUBLE = f"""#!/bin/sh
[ "$1" = "{_WRAPPER_SEPARATOR}" ] && shift
printf 'invoked\\n' > "$LIVESPEC_TEST_WRAPPER_MARKER"
rm -rf "$LIVESPEC_TEST_EVICT"
unset LIVESPEC_RETAINED_PAYLOAD_ROOT
export BEADS_DOLT_PASSWORD={_PLACEHOLDER_SECRET}
exec "$@"
"""


def _install(*, root: Path) -> Path:
    _ = shutil.copytree(_PLUGIN_ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
    probe = root / "scripts" / "bin" / "payload_probe.py"
    _ = probe.write_text(_PROBE_WRAPPER, encoding="utf-8")
    return root


def _base_env(*, install_root: Path) -> dict[str, str]:
    scrubbed = ("PYTHONPATH", "COVERAGE_PROCESS_START")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in scrubbed and not key.startswith("COV_CORE_")
    }
    env["CLAUDE_PLUGIN_ROOT"] = str(install_root)
    return env


def _installed_release(*, install_root: Path) -> str:
    manifest = json.loads((install_root / "plugin.json").read_text(encoding="utf-8"))
    return str(manifest["version"])


def test_the_installed_root_stays_the_candidate_while_assets_come_from_the_payload(
    tmp_path: Path,
) -> None:
    """Two questions, two answers: which build am I, and where is my code."""
    install_root = _install(root=tmp_path / "install")
    result_path = tmp_path / "result.json"
    env = _base_env(install_root=install_root)
    env["BEADS_DOLT_PASSWORD"] = _PLACEHOLDER_SECRET

    completed = subprocess.run(
        [
            sys.executable,
            str(install_root / "scripts" / "bin" / "payload_probe.py"),
            str(result_path),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        check=False,
        timeout=_CLI_TIMEOUT_SECONDS,
    )

    assert completed.returncode == 0, f"the probe failed:\n{completed.stdout}\n{completed.stderr}"
    record = json.loads(result_path.read_text(encoding="utf-8"))
    assert record["plugin_root"] == str(install_root), (
        "retention MOVED the plugin root onto the retained copy, so the "
        "self-update canary now compares the running build against itself and "
        f"can never discover a newer installed one: {record}"
    )
    assert record["candidate_dispatcher_bin"] == str(
        install_root / "scripts" / "bin" / "dispatcher.py"
    ), f"the canary target is no longer the INSTALLED build: {record}"
    assert record["executing_release"] == _installed_release(
        install_root=install_root
    ), f"the executing build's release is no longer readable: {record}"
    assert record["payload_root"] != str(
        install_root
    ), f"no payload was retained, so nothing survives eviction: {record}"
    assert record["manifest"].startswith(f"{record['payload_root']}{os.sep}"), (
        "the packaged asset resolved OUTSIDE the retained payload, so it would "
        f"vanish with the cache: {record}"
    )
    assert record["manifest_length"] > 0, f"the packaged asset read empty: {record}"


def test_the_credential_re_exec_survives_eviction_of_its_own_installation(
    tmp_path: Path,
) -> None:
    """The wrapper must still be invoked, and the wrapped process must still run."""
    install_root = _install(root=tmp_path / "install")
    result_path = tmp_path / "result.json"
    marker = tmp_path / "wrapper-invoked"
    wrapper = tmp_path / "with-livespec-env-double.sh"
    _ = wrapper.write_text(_WRAPPER_DOUBLE, encoding="utf-8")
    wrapper.chmod(0o755)
    # The secret is REQUIRED here (server-mode ledger) and absent from the
    # environment, so the self-heal must re-exec through the wrapper.
    (tmp_path / ".beads").mkdir()
    # The FLAT dotted form `bd` actually uses, and the one the launcher's
    # server-mode marker matches — a nested `dolt:`/`  mode: server` mapping
    # does NOT match it, and a fixture written that way makes the secret
    # optional, so no re-exec happens and the test passes vacuously.
    _ = (tmp_path / ".beads" / "config.yaml").write_text("dolt.mode: server\n", encoding="utf-8")
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"credential_wrapper": [str(wrapper), _WRAPPER_SEPARATOR]}), encoding="utf-8"
    )

    env = _base_env(install_root=install_root)
    _ = env.pop("BEADS_DOLT_PASSWORD", None)
    _ = env.pop("LIVESPEC_CREDENTIAL_REEXEC", None)
    env["LIVESPEC_TEST_WRAPPER_MARKER"] = str(marker)
    env["LIVESPEC_TEST_EVICT"] = str(install_root)

    completed = subprocess.run(
        [
            sys.executable,
            str(install_root / "scripts" / "bin" / "payload_probe.py"),
            str(result_path),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        check=False,
        timeout=_CLI_TIMEOUT_SECONDS,
    )

    assert marker.exists(), (
        "the credential wrapper was never invoked, so this proves nothing about "
        f"that boundary:\n{completed.stdout}\n{completed.stderr}"
    )
    assert not install_root.exists(), "the wrapper did not actually evict the installation"
    assert completed.returncode == 0, (
        "the re-executed process could not run after its installation was "
        "evicted around the credential re-exec — the wrapper command still "
        f"names the evicted cache:\n{completed.stdout}\n{completed.stderr}"
    )
    record = json.loads(result_path.read_text(encoding="utf-8"))
    assert record["secret_present"] is True, f"the wrapper did not inject the secret: {record}"
    assert not record["payload_root"].startswith(
        f"{install_root}{os.sep}"
    ), f"the wrapped process ran out of the evicted installation: {record}"
    assert (
        record["manifest_length"] > 0
    ), f"the wrapped process could not read its packaged assets: {record}"

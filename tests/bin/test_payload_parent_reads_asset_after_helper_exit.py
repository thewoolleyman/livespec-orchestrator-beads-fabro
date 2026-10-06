"""A parent reads a packaged asset AFTER its helper exits, before its cleanup.

NOT a Red, and it must not be cited as one. This is a supplemental NATIVE
control for an evidence gap in an accepted Red, raised by a read-only review of
cycle 11 on 2026-10-06. It passed the moment it was written, and the accepted
Red it supplements — `tests/bin/test_payload_inherited_source_identity.py`,
bytes `d29539aef39c5c5ef7824d2b500c19c3ad532dda6a1b33fece17fcf5b2ba6270` —
is deliberately left byte-identical.

WHAT THE ACCEPTED RED DOES AND DOES NOT ESTABLISH. Its fourth case,
`test_a_helper_that_finishes_leaves_the_payload_readable_by_its_parent`, calls
`release_payload(payload=helper)` SYNCHRONOUSLY IN ONE PROCESS. That is
sufficient for what it claims about OWNERSHIP — an inherited payload carries no
`holder`, so releasing it removes nothing, and the creator's own release does
remove the holder. It is NOT by itself proof of the real LIFETIME ORDERING,
because no child process ever started or exited: an in-process function call
cannot demonstrate that a parent still reads its packaged assets after a
genuine child has terminated.

So this file supplies the ordering, natively:

1. a real child goes through the real `bootstrap()` and retains a payload;
2. its INSTALLATION is then deleted, so nothing but the payload can serve;
3. it spawns a real HELPER through the packaged launcher and WAITS for that
   helper to exit, recording the exit status;
4. only THEN does it read an actual packaged asset's CONTENT out of the
   payload — the bundled `.fabro/workflows/implement-work-item/workflow.toml`,
   33KB of committed run config, plus the release manifest;
5. and only after that does it release its OWN payload.

The ordering is RECORDED rather than inferred. Each step appends to an
`events` list the parent emits, so the assertion reads the sequence the process
actually performed instead of trusting that statements ran in the order they
are written.

The helper's `source_root` is the RETAINED PAYLOAD PATH, not the original
install path. That is not a convenience here — it is the real shape, and
`tests/bin/test_payload_lifetime_release.py` has spawned it that way since
cycle 4: a `scripts/bin/` helper resolves its own plugin root to the tree it
was loaded from, which for an owned helper is the payload. It is also exactly
the case `_payload_serves`'s second clause exists for; omitting that clause
made every owned helper copy the copy, which is the regression cycle 11's
Green had to repair. This file keeps that real reuse under test while the
accepted Red keeps an explicitly-named DIFFERENT installation rejected.

Scope is the declared lifetime/ownership assertion and nothing more. No
cache-manager behaviour, no integrity claim beyond "the asset this parent read
is the committed one", and no second release path.

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
_BUILD_ID = "0123abc"

# The committed asset the parent reads back, and two structural tokens that
# cannot appear unless the real file was opened. Chosen over a byte count alone
# because a truncated or substituted file can still have a plausible length.
_ASSET_RELATIVE = (".fabro", "workflows", "implement-work-item", "workflow.toml")
_ASSET_TOKENS = ("[workflow]", "[run]")

# Spawned by the parent, from the PAYLOAD, with the payload as its source root
# — the shape an owned `scripts/bin/` helper really has. It reads its own
# resolved payload root back out and writes NOTHING into the tree.
_HELPER = """
import importlib
import json
import sys
from pathlib import Path

source_root, result_path = sys.argv[1:3]
sys.path.insert(0, str(Path(source_root) / "scripts" / "bin"))
import _bootstrap

_bootstrap.bootstrap()

paths = importlib.import_module("livespec_orchestrator_beads_fabro.commands._dispatcher_paths")
Path(result_path).write_text(
    json.dumps({"payload_root": str(Path(paths.__file__).resolve().parents[3])}),
    encoding="utf-8",
)
"""

# The parent. argv is [install_root, helper_source_path, result_path].
_PARENT = """
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

install_root, helper_source_path, result_path = sys.argv[1:4]
events = []

sys.path.insert(0, str(Path(install_root) / "scripts" / "bin"))
import _bootstrap
import _payload as payload_module

_bootstrap.bootstrap()
events.append("launcher-finished")

paths = importlib.import_module("livespec_orchestrator_beads_fabro.commands._dispatcher_paths")
payload_root = Path(paths.__file__).resolve().parents[3]

# EVICT the installation: from here only the payload can serve.
shutil.rmtree(install_root, ignore_errors=True)
events.append("installation-evicted")

helper_result = Path(result_path).with_suffix(".helper.json")
completed = subprocess.run(
    [sys.executable, helper_source_path, str(payload_root), str(helper_result)],
    capture_output=True,
    text=True,
    check=False,
    timeout=120,
)
events.append("helper-exited")

# AFTER the helper has exited: read an actual packaged asset's CONTENT.
asset = payload_root.joinpath(*{asset_relative!r})
asset_text = asset.read_text(encoding="utf-8")
manifest = json.loads((payload_root / "plugin.json").read_text(encoding="utf-8"))
events.append("asset-read")

own = payload_module.retain_payload(
    source_root=payload_root, environ=dict(os.environ)
)
holder_before = own.holder is not None or payload_root.parent.is_dir()
payload_module.release_payload(
    payload=payload_module.RetainedPayload(
        root=payload_root,
        scripts_root=payload_root / "scripts",
        vendor_root=payload_root / "scripts" / "_vendor",
        retained=True,
        holder=payload_root.parent,
    )
)
events.append("payload-released")

Path(result_path).write_text(
    json.dumps({{
        "events": events,
        "payload_root": str(payload_root),
        "installation_present_after_eviction": Path(install_root).exists(),
        "helper_returncode": completed.returncode,
        "helper_stderr": completed.stderr,
        "helper_result": str(helper_result),
        "asset_bytes": len(asset_text),
        "asset_has_tokens": all(token in asset_text for token in {asset_tokens!r}),
        "manifest_release": manifest.get("version"),
        "holder_existed_before_release": holder_before,
        "holder_present_after_release": payload_root.parent.exists(),
    }}),
    encoding="utf-8",
)
"""


@pytest.fixture(name="install_parent")
def _install_parent() -> Iterator[Path]:
    """An installation directory OUTSIDE any git worktree.

    A `.git` at the pytest basetemp root makes every `tmp_path` resolve as a
    worktree, which changes how a plugin root is classified. A harness-managed
    plugin cache is not inside one, and this is that shape.
    """
    parent = Path(tempfile.mkdtemp(prefix="livespec-helper-exit-"))
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


def test_the_parent_reads_a_packaged_asset_after_its_helper_has_exited(
    tmp_path: Path, install_parent: Path
) -> None:
    """The real ordering: helper exits, parent reads an asset, parent cleans up."""
    install_root = _install(root=install_parent / _BUILD_ID)
    helper_source = tmp_path / "owned_helper.py"
    _ = helper_source.write_text(_HELPER, encoding="utf-8")
    parent_source = tmp_path / "owning_parent.py"
    _ = parent_source.write_text(
        _PARENT.format(asset_relative=_ASSET_RELATIVE, asset_tokens=_ASSET_TOKENS),
        encoding="utf-8",
    )
    result_path = tmp_path / "parent.json"

    scrubbed = ("PYTHONPATH", "COVERAGE_PROCESS_START")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in scrubbed and not key.startswith("COV_CORE_")
    }
    env["CLAUDE_PLUGIN_ROOT"] = str(install_root)
    env["LIVESPEC_BEADS_FAKE"] = "1"
    env["BEADS_DOLT_PASSWORD"] = _PLACEHOLDER_SECRET
    _ = env.pop("LIVESPEC_RETAINED_PAYLOAD_ROOT", None)

    completed = subprocess.run(
        [
            sys.executable,
            str(parent_source),
            str(install_root),
            str(helper_source),
            str(result_path),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        check=False,
        timeout=_CHILD_TIMEOUT_SECONDS,
    )

    assert (
        completed.returncode == 0
    ), f"the owning parent did not complete:\n{completed.stdout}\n{completed.stderr}"
    record = json.loads(result_path.read_text(encoding="utf-8"))

    # The ORDERING, read off the sequence the process actually performed.
    assert record["events"] == [
        "launcher-finished",
        "installation-evicted",
        "helper-exited",
        "asset-read",
        "payload-released",
    ], f"the lifetime steps did not happen in the required order: {record['events']}"

    assert (
        record["installation_present_after_eviction"] is False
    ), "the installation survived, so the payload was never the only server"
    assert (
        record["helper_returncode"] == 0
    ), f"the owned helper did not run from the payload:\n{record['helper_stderr']}"
    helper = json.loads(Path(record["helper_result"]).read_text(encoding="utf-8"))
    assert helper["payload_root"] == record["payload_root"], (
        "the owned helper did not REUSE its parent's payload after the "
        f"installation was evicted — it copied the copy: {helper} vs {record}"
    )

    # The ASSET, read after that helper had exited.
    assert record["asset_bytes"] > 0, "the parent read an empty packaged asset"
    assert (
        record["asset_has_tokens"] is True
    ), f"the asset the parent read is not the committed run config: {record}"
    assert (
        record["manifest_release"] == _INSTALLED_RELEASE
    ), f"the parent read a release manifest from the wrong tree: {record}"

    # And only then the creator's own cleanup.
    assert record["holder_existed_before_release"] is True
    assert (
        record["holder_present_after_release"] is False
    ), f"the creator's own release did not remove the holder it owns: {record}"

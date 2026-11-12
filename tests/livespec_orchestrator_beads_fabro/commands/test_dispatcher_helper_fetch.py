"""The helper-fetch setup step as rendered: a short script, the manifest in its env.

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch", paragraph
"Helper programs are fetched in the sandbox from the dispatching build's own
commit": the setup step's own script stays short and inlines no helper source,
because the engine renders a completed command stage's script into the prompt of
every later agent stage. `tests/integration/test_helper_fetch_scenario336.py`
runs this step for real against a local repository.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest
import tomli
from livespec_orchestrator_beads_fabro.commands import _dispatcher_helper_fetch as subject
from livespec_orchestrator_beads_fabro.commands import _dispatcher_helper_registry as registry
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_build import HelperSource
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

_SOURCE = HelperSource(
    repository="https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git",
    commit="37e012335ed23ecba9bbcbb829e0fc90f2fdaf3b",
)
_MAX_SCRIPT_CHARS = 2000
# The bound the step puts on the sandbox's forge fetch, spelled as a literal: the
# setup node's own limit is 1800 s, so an unbounded stuck fetch waits that out
# before the run learns anything, and the cause it then reports is the node's.
_FETCH_BOUND_SECONDS = 120
# Every child runs without the repository-selecting `GIT_*` variables and the
# coverage hooks, as in Scenario 336's consumer test: a commit hook's
# `GIT_INDEX_FILE` would otherwise point the step's `git init` at the outer repo.
_SCRUBBED_PREFIXES = ("GIT_", "COVERAGE_PROCESS_START", "COV_CORE_")


def test_the_step_fetches_the_commit_sparse_and_shallow_and_carries_no_source() -> None:
    step = subject.helper_fetch_prepare_step(source=_SOURCE)
    assert len(step.script) <= _MAX_SCRIPT_CHARS
    assert "sparse-checkout set --no-cone /.claude-plugin/scripts/ /.claude-plugin/.fabro/" in (
        step.script
    )
    assert f"fetch -q --depth=1 --filter=blob:none --no-tags origin {_SOURCE.commit}" in step.script
    assert "checkout -q --detach FETCH_HEAD" in step.script
    assert f"remote add origin {_SOURCE.repository}" in step.script
    assert "LIVESPEC_PREPARE_PAYLOAD_DIGEST_MISMATCH: helper-manifest:" in step.script
    for helper in registry.helper_registry()[:13]:
        assert helper.compose().decode("utf-8")[:200] not in step.script


def test_the_manifest_rides_the_steps_env_and_reaches_the_materializer_on_stdin() -> None:
    step = subject.helper_fetch_prepare_step(source=_SOURCE)
    assert set(step.env) == {subject.HELPER_MANIFEST_ENV}
    assert json.loads(step.env[subject.HELPER_MANIFEST_ENV]) == registry.helper_manifest(
        repository=_SOURCE.repository, commit=_SOURCE.commit
    )
    assert f'printf %s "${subject.HELPER_MANIFEST_ENV}" | (cd "$c"' in step.script


def test_each_root_is_resolved_as_its_consumers_resolve_it() -> None:
    roots = subject.default_helper_roots(environ={"LIVESPEC_SANDBOX_GH_REFRESH_ROOT": "/gh"})
    assert roots == {
        registry.PLUGINS_ROOT: sandbox_plugins_root_expansion(),
        registry.GH_REFRESH_ROOT: "/gh",
        registry.LIVESPEC_ROOT: "/workspace/.livespec",
    }
    script = subject.helper_fetch_prepare_step(source=_SOURCE).script
    assert f'"plugins={sandbox_plugins_root_expansion()}"' in script
    assert '"livespec=/workspace/.livespec"' in script


def test_the_block_renders_one_overlay_step() -> None:
    block = subject.helper_fetch_prepare_steps_block(
        source=_SOURCE, roots={registry.PLUGINS_ROOT: "/p"}
    )
    steps = tomli.loads(block)["run"]["prepare"]["steps"]
    assert len(steps) == 1
    assert '"plugins=/p"' in steps[0]["script"]
    assert _SOURCE.commit in block.splitlines()[2]


def test_the_fetch_is_bounded_by_a_named_timeout() -> None:
    """A stuck fetch ends at the step's own bound, not at the setup node's 1800 s."""
    assert getattr(subject, "HELPER_FETCH_TIMEOUT_SECONDS", None) == _FETCH_BOUND_SECONDS
    script = subject.helper_fetch_prepare_step(source=_SOURCE).script
    assert f'timeout {_FETCH_BOUND_SECONDS} git -C "$c" fetch -q' in script
    assert len(script) <= _MAX_SCRIPT_CHARS


def test_a_fetch_that_hangs_fails_at_the_bound_naming_the_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The step is RUN, against a `git` whose fetch never returns.

    Every other `git` call reaches the real binary, so the init, the sparse
    pattern and the remote are the shipped ones. The stand-in EXECs its sleep, so
    the process `timeout` signals is the one holding the pipe: a shell parent
    killed over a live `sleep` child would leave that child holding stdout, and
    the run would then measure the orphan rather than the bound. The cause must
    name the timeout, because "cannot be fetched" would send an operator to the
    forge for a commit it does serve.
    """
    bound = 2
    monkeypatch.setattr(subject, "HELPER_FETCH_TIMEOUT_SECONDS", bound, raising=False)
    shim = tmp_path / "bin"
    shim.mkdir()
    real_git = subprocess.run(
        ["sh", "-c", "command -v git"], check=True, capture_output=True, text=True
    ).stdout.strip()
    stand_in = shim / "git"
    stand_in.write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do [ "$a" = fetch ] && exec sleep 30; done\n'  # real-time-required: the fetch never returns, and the step's wall-clock bound is the subject
        f'exec {real_git} "$@"\n',
        encoding="utf-8",
    )
    stand_in.chmod(0o755)
    step = subject.helper_fetch_prepare_step(source=_SOURCE, roots={"plugins": str(tmp_path)})
    env = {
        **{
            name: value
            for name, value in os.environ.items()
            if not name.startswith(_SCRUBBED_PREFIXES)
        },
        **step.env,
        "PATH": f"{shim}{os.pathsep}{os.environ['PATH']}",
        "TMPDIR": str(tmp_path),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }

    started = time.monotonic()  # real-time-required: how long the step ran is the subject
    done = subprocess.run(
        ["sh", "-c", step.script], env=env, capture_output=True, text=True, timeout=60, check=False
    )
    elapsed = time.monotonic() - started  # real-time-required: as above

    assert done.returncode != 0
    assert elapsed < 20, f"the step ran {elapsed:.1f} s, past its {bound} s fetch bound"
    assert (
        "LIVESPEC_PREPARE_PAYLOAD_DIGEST_MISMATCH: helper-manifest: "
        f"fetch of commit {_SOURCE.commit} from {_SOURCE.repository} timed out after {bound} s"
    ) in done.stderr
    assert "cannot be fetched" not in done.stderr

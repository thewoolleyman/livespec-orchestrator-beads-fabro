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

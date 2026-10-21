"""Every node that runs the declared check suite re-enters the plugin-cache gate first.

THE MEASURED CAUSE, established 2026-10-21 from THIS repository's own live Fabro
sandbox (container HOME `/root`, orchestrator build `36616e3a5ab3`) rather than
inferred from code. Earlier readings -- the 2026-09-09 correction on `bd-ib-3f79`
and the 2026-10-21 recurrence -- both measured a registry record without a cache
and neither established WHY, so the fix shape was being chosen blind.

The Claude Agent SDK's session start does not run an INSTALLER. It runs a
registry SYNC, and the bundled engine says so in its own log vocabulary:
"Syncing installed_plugins.json with enabledPlugins from all settings.json
files", "Looking up plugin <p> in marketplace <m>", "Using git SHA for <p>",
"Sync completed: <n> updated in installed_plugins.json". For each
`enabledPlugins` entry of any `settings.json` -- this repository's committed
`.claude/settings.json` supplies four -- that sync resolves the plugin in its
already-cloned marketplace, derives the version from THAT CLONE'S git HEAD, and
writes a record whose `installPath` is the COMPUTED cache location
`cache/<marketplace>/<plugin>/<sha12>`. Materializing that directory belongs to
the loader, not to the sync: the engine's own text says a ref-tracked entry is
recorded "without a version so the loader re-clones it each load". A record is
therefore a DECLARATION OF WHERE A CACHE COPY WOULD LIVE, never evidence that
one exists, and the sync has no cache-completeness precondition for a
marketplace-resolved plugin -- it has one only for an external plugin
("External plugin <p> not in cache, skipping").

The measurement, in the order the clock recorded it:

- 11:30:33.246 the prepare-step gate program lands; 11:30:33.277 it records the
  pin as `{"builds": {}, "marketplaces": {}}`, because neither
  `known_marketplaces.json` nor `installed_plugins.json` exists yet.
- 11:30:41.170 .. 11:30:47.520 the four marketplace clones appear -- 8 to 14
  seconds AFTER the gate's prepare pass ran.
- 11:33:01.365 all four registry records are written in ONE millisecond, each
  with `installedAt == lastUpdated` and each `gitCommitSha` equal to its own
  marketplace clone's HEAD (verified clone by clone).
- `/root/.claude/plugins/cache` does not exist at all, while this run's plugin
  skills and hooks are live and `~/.claude/plugins/data/` carries a per-plugin
  data directory.

So there was never an install to fail. That rules the atomic-install fix shape
OUT for us -- the write happens inside the closed-source engine, before any
surface this repository owns -- and leaves re-entry as the shape that can work.
Run against a copy of that live registry shaped exactly as production (records
naming cache directories below the root's own `cache/`), the SHIPPED gate
program already detects all four, drops all four records and exits 0. The gate
was never the missing piece. The missing piece is that nothing re-entered it:
`pr_refresh` did, and the janitor -- which is where the 2026-10-21 recurrence
went red on check-nextest, check-coverage, check-e2e-tmux and
check-real-store-smoke -- never did.

WHAT RE-ENTRY DOES TO A GOVERNED REPOSITORY'S TESTS, stated because it is a
behaviour change and not only a repair: the gate's repair DROPS the record
rather than materializing the cache, so a live-source test that branches on the
ambient registry takes its designed SKIP path instead of resolving a plugin root
that does not exist. That is the intended outcome -- a skip is a declared
no-evidence result, where the live path was erroring on an absent directory.

WHY `publish_draft` CARRIES NO RE-ENTRY OF ITS OWN, and why that is asserted
here rather than assumed. It runs the declared suite twice over -- once inside
the pre-push hook, once in its push-failure arm -- but `janitor` is its ONLY
in-edge, and no agent session runs between the two, so the registry it finds is
the one the janitor left. The structural fact is what makes that true, so the
last case measures the fact rather than trusting it: a second in-edge would
retire the argument silently.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    PLUGIN_BUILD_ADVANCED_MARKER,
    PLUGIN_CACHE_UNMATERIALIZED_MARKER,
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
    plugin_cache_gate_script,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

_CHECK_SUITE_TOKEN = "{{ inputs.sandbox_check_suite }}"

# The gate program's own filename, as the NODE SCRIPTS spell it. Asserted
# against the materialized name rather than imported into the rendering, because
# the thing under test is that the shipped bytes name the program the prepare
# pass lands -- an import would make a node that named nothing still pass.
_GATE_PROGRAM = "livespec-run-plugin-gate.py"

# The registry record under repair, carried from the live sandbox measured in
# this module's docstring so the fixture is the observed shape rather than an
# invented one.
_PLUGIN = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
_MARKETPLACE = "livespec-orchestrator-beads-fabro"
_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"
_BUILD_SHA = "36616e3a5ab3ff2d9bcded3d947f4de95b45bdfd"
_BUILD = _BUILD_SHA[:12]

# The one `required_paths` entry every measured failure named, and the only one
# this fixture declares: a manifest naming exactly the path under test is what
# makes a passing case evidence about completeness rather than about the
# manifest's length.
_REQUIRED_PATH = "scripts/bin"

# What the stand-in declared suite records, and what it is given. The arguments
# are asserted because a declared suite is an ARGV: a rendering that collapsed
# it to one word would still create the marker, so the marker alone proves the
# gate did not block the suite but not that the suite ran as declared.
#
# NEITHER ARGUMENT CONTAINS A SPACE, deliberately. The janitor's seam is a bare
# `eval` of the interpolation, which joins bash's already-unquoted tokens and so
# cannot round-trip a quoted argv ELEMENT on the raw renderer -- a known,
# documented property of that node (see the `pr_refresh` comment in the graph,
# and `test_workflow_janitor_check_suite_execution.py`, which owns the seam
# question and uses the same unquoted shape). Asserting a quoted element here
# would fail for a reason this module is not about.
_FIRST_ARGUMENT = "alpha"
_SECOND_ARGUMENT = "gamma"

# The two input renderings, named so a failure reports which engine it modelled.
_RENDERINGS = (
    pytest.param(False, id="raw-text-substitution"),
    pytest.param(True, id="petri-shell-quoted-input"),
)


@dataclass(frozen=True, kw_only=True)
class _Sandbox:
    """A prepared plugins root, its registry, and the stand-in declared suite."""

    plugins_root: Path
    home: Path
    suite: Path
    ran_marker: Path

    def registry(self) -> Path:
        return self.plugins_root / "installed_plugins.json"

    def cache_dir(self) -> Path:
        return self.plugins_root / "cache" / _MARKETPLACE / _PLUGIN_NAME / _BUILD

    def recorded_builds(self) -> list[str]:
        """Every build the registry still names for the plugin under repair."""
        payload = json.loads(self.registry().read_text(encoding="utf-8"))
        records = payload["plugins"].get(_PLUGIN, [])
        return [str(record.get("version")) for record in records]


def _node_script(*, node: str) -> str:
    """The shipped node's `script` attribute, through the canonical parser."""
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes[node]["script"]
    return script


def _rendered_janitor(*, suite_argv: str, shell_quoted_input: bool) -> str:
    script = _node_script(node="janitor")
    assert script.count(_CHECK_SUITE_TOKEN) == 1
    replacement = shlex.quote(suite_argv) if shell_quoted_input else suite_argv
    return script.replace(_CHECK_SUITE_TOKEN, replacement)


def _child_env(*, box: _Sandbox) -> dict[str, str]:
    """The child environment, EXPLICIT rather than inherited.

    An inherited `LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT` would point every case
    at the ENCLOSING factory run's own plugins root, so a case meant to poison a
    fixture registry would poison the live run's instead. Building the mapping
    from nothing also withholds `COVERAGE_PROCESS_START` and `COV_CORE_*` by
    construction, so no child self-instruments and races the coverage run.
    """
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(box.home),
        SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(box.plugins_root),
    }


def _write_registry(*, box: _Sandbox, install_path: Path) -> None:
    _ = box.registry().write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    _PLUGIN: [
                        {
                            "scope": "project",
                            "installPath": str(install_path),
                            "version": _BUILD,
                            "gitCommitSha": _BUILD_SHA,
                        }
                    ]
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _materialize_complete_cache(*, box: _Sandbox) -> None:
    """Write a COMPLETE cache copy of the build, manifest and required path.

    Complete, never incomplete: the one case that needs an incomplete copy
    removes the required path AFTER the prepare pass has pinned the build,
    because a copy that was incomplete already would be dropped at prepare time
    and the re-entry would then have nothing left to measure.
    """
    cache_dir = box.cache_dir()
    cache_dir.mkdir(parents=True)
    _ = (cache_dir / "plugin.json").write_text(json.dumps({"name": _PLUGIN_NAME}), encoding="utf-8")
    _ = (cache_dir / "cache-manifest.json").write_text(
        json.dumps({"required_paths": [_REQUIRED_PATH]}), encoding="utf-8"
    )
    (cache_dir / _REQUIRED_PATH).mkdir(parents=True)


def _suite(*, tmp_path: Path, marker: Path, exit_status: int) -> Path:
    """A stand-in declared suite that records its own arguments when it runs."""
    path = tmp_path / "declared-check-suite"
    _ = path.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n%s\\n" "$1" "$2" > "{marker}"\n'
        f"exit {exit_status}\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _prepare(*, box: _Sandbox) -> None:
    """Run the gate's OWN prepare-step body, exactly as a dispatch prepares.

    The pin this records is the real one, so a later re-entry is the ENFORCEMENT
    arm rather than a first recording -- and running the shipped body rather than
    restating it is what makes the gate under test the gate the Dispatcher ships.
    """
    script = box.home.parent / "install-plugin-gate.sh"
    _ = script.write_text(plugin_cache_gate_script(), encoding="utf-8")
    _ = subprocess.run(
        ["bash", str(script)],
        check=True,
        capture_output=True,
        text=True,
        env=_child_env(box=box),
    )


def _sandbox(*, tmp_path: Path, exit_status: int = 0) -> _Sandbox:
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    marker = tmp_path / "suite-ran"
    return _Sandbox(
        plugins_root=plugins_root,
        home=home,
        suite=_suite(tmp_path=tmp_path, marker=marker, exit_status=exit_status),
        ran_marker=marker,
    )


def _run_janitor(*, box: _Sandbox, shell_quoted_input: bool) -> subprocess.CompletedProcess[str]:
    """Execute the shipped janitor bytes, with only the engine's own token bound.

    `sandbox_check_suite` is a per-repository DECLARATION, so standing a
    controlled command in for it stands in for the declaration rather than for
    the stage. Both renderings are driven because the two engines disagree about
    quoting and a substring assertion over the script cannot tell a suite that
    RAN from one whose command line was looked up as a name.
    """
    suite_argv = f"{box.suite} {_FIRST_ARGUMENT} {_SECOND_ARGUMENT}"
    return subprocess.run(
        [
            "bash",
            "-c",
            _rendered_janitor(suite_argv=suite_argv, shell_quoted_input=shell_quoted_input),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=_child_env(box=box),
    )


@pytest.mark.parametrize("shell_quoted_input", _RENDERINGS)
def test_the_janitor_drops_a_pinned_build_whose_cache_lost_its_required_path(
    *, tmp_path: Path, shell_quoted_input: bool
) -> None:
    """A PRESENT-but-incomplete cache of a PINNED build is dropped, then the suite runs.

    This is the item's own headline condition and the arm pin enforcement cannot
    reach: the build IS the one this run resolved at prepare time, so nothing but
    a `required_paths` reading can disqualify it. The cache is complete when the
    prepare pass pins it and loses `scripts/bin` afterwards, which is the live
    `installPath is missing required path scripts/bin` shape rather than the
    cheaper absent-directory one.
    """
    box = _sandbox(tmp_path=tmp_path)
    _materialize_complete_cache(box=box)
    _write_registry(box=box, install_path=box.cache_dir())
    _prepare(box=box)
    assert box.recorded_builds() == [_BUILD]
    (box.cache_dir() / _REQUIRED_PATH).rmdir()

    completed = _run_janitor(box=box, shell_quoted_input=shell_quoted_input)

    assert completed.returncode == 0, completed.stderr
    assert f"is missing required path {_REQUIRED_PATH}" in completed.stderr
    assert PLUGIN_CACHE_UNMATERIALIZED_MARKER in completed.stderr
    # The isolation this case exists for: the record went because its cache was
    # incomplete, NOT because the pin disowned the build.
    assert PLUGIN_BUILD_ADVANCED_MARKER not in completed.stderr
    assert box.recorded_builds() == []
    assert box.ran_marker.read_text(encoding="utf-8") == (
        f"{_FIRST_ARGUMENT}\n{_SECOND_ARGUMENT}\n"
    )


@pytest.mark.parametrize("shell_quoted_input", _RENDERINGS)
def test_the_janitor_drops_a_record_naming_a_cache_that_was_never_materialized(
    *, tmp_path: Path, shell_quoted_input: bool
) -> None:
    """The 2026-10-21 recurrence shape: a record written after prepare, no cache at all."""
    box = _sandbox(tmp_path=tmp_path)
    _prepare(box=box)
    _write_registry(box=box, install_path=box.cache_dir())
    assert box.recorded_builds() == [_BUILD]
    assert not box.cache_dir().exists()

    completed = _run_janitor(box=box, shell_quoted_input=shell_quoted_input)

    assert completed.returncode == 0, completed.stderr
    assert PLUGIN_CACHE_UNMATERIALIZED_MARKER in completed.stderr
    assert box.recorded_builds() == []
    assert box.ran_marker.is_file()


@pytest.mark.parametrize("shell_quoted_input", _RENDERINGS)
def test_the_janitor_refuses_before_the_declared_suite_when_the_gate_cannot_repair(
    *, tmp_path: Path, shell_quoted_input: bool
) -> None:
    """An unrepairable registry refuses, and the suite is NEVER reached.

    The absent marker is the ORDERING proof, and it is the assertion the
    pre-repair bytes could not satisfy: a janitor that is only `eval <suite>`
    runs the suite against the poisoned registry and exits on the suite's own
    status, so the marker exists and the return code is the suite's.
    """
    box = _sandbox(tmp_path=tmp_path)
    _prepare(box=box)
    outside = box.plugins_root / "not-the-cache" / _BUILD
    _write_registry(box=box, install_path=outside)

    completed = _run_janitor(box=box, shell_quoted_input=shell_quoted_input)

    assert completed.returncode != 0
    assert not box.ran_marker.exists()
    assert "LIVESPEC_JANITOR_PLUGIN_GATE_FAILED" in completed.stderr


def test_the_janitor_names_the_materialized_gate_program() -> None:
    """The janitor re-enters the program the prepare pass lands, before the suite."""
    script = _node_script(node="janitor")
    assert _GATE_PROGRAM in script

    assert script.index(_GATE_PROGRAM) < script.index(_CHECK_SUITE_TOKEN)


def test_pr_refresh_re_enters_the_plugin_gate_before_it_runs_the_declared_suite() -> None:
    """`pr_refresh`'s re-entry precedes its post-rebase gate, not only its push.

    Ordering is read off the shipped bytes rather than executed here because
    `test_scripted_refresh_execution.py` already drives this node's script
    against a real origin; what that module cannot show is WHICH SIDE of the
    declared gate the re-entry falls on, and that is the whole defect -- a
    re-entry after the suite observes the mutation too late to stop it.
    """
    script = _node_script(node="pr_refresh")
    assert script.count(_GATE_PROGRAM) == 1
    invocation = "gate_out=$(livespec_declared_gate"
    assert script.count(invocation) == 1

    assert script.index(_GATE_PROGRAM) < script.index(invocation)


def test_the_janitor_is_the_only_entry_to_the_stage_that_pushes_through_the_suite() -> None:
    """`publish_draft` inherits the janitor's re-entry because nothing else reaches it.

    Measured rather than assumed: a second in-edge would mean a path to the
    pre-push hook that no gate re-entry covers, and nothing else in this module
    would notice.
    """
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph

    sources = {edge.source for edge in graph.edges if edge.destination == "publish_draft"}

    assert sources == {"janitor"}

"""Consumer-tier acceptance for SPECIFICATION/scenarios.md Scenario 336.

Binds "## Scenario 336 — A sandbox checks a tree with the tooling release that tree
pins, and works in the latest clones". The scenario's four Given/When/Then blocks map
to the cases below. The run-from clone is produced by a Dispatcher-materialized
program the sandbox executes, so these tests EXECUTE that program for real: against
local bare repositories standing in for the forge, in a project directory standing in
for the governed tree, never against a mock of the program.

WHAT THIS FILE CANNOT PROVE, AND WHY IT SAYS SO. Whether a write by the run's agent is
REFUSED depends on the capabilities the sandbox image grants uid 0, which a hermetic
run does not have: measured in a family sandbox, a root process holds
CAP_DAC_OVERRIDE (mode bits do not bind it) and neither CAP_LINUX_IMMUTABLE nor
CAP_SYS_ADMIN (no immutable flag, no read-only bind mount). So the write-refusal is
captured on a real sandbox. What is asserted here is the part the program owns: that
it strips every write bit, that it asks for the immutable flag, and that it REPORTS the
protection it achieved rather than claiming one it did not.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import os
import runpy
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_siblings import (
    SiblingClones,
    core_plugin_env_line,
    sibling_clone_steps_block,
)

from tests.prepare_step_support import runnable_script, steps_in

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_run_from_clones"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_run_from_clones.py"
)
_WORKFLOW_DIR = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_OWNER = "thewoolleyman"
# Every child is spawned with the repository-selecting `GIT_*` variables and the coverage
# hooks removed: this suite can itself run under a commit hook, whose `GIT_INDEX_FILE`
# would otherwise point a fixture's commits at the outer repository, and a child that
# self-instruments races concurrent coverage runs.
_SCRUBBED_PREFIXES = ("GIT_", "COVERAGE_PROCESS_START", "COV_CORE_")
_GIT_ENV = {
    **{
        name: value for name, value in os.environ.items() if not name.startswith(_SCRUBBED_PREFIXES)
    },
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}
_STABLE_RELEASES = ("v0.9.0", "v0.10.0", "v0.47.1", "v0.47.2")
_PRERELEASE = "v1.0.0-rc.1"
_FAKE_GITHUB_TOKEN = "ghs_fake_installation_token"


def _module() -> ModuleType:
    """The new module, imported INSIDE the test so its absence is an assertion, not a collection error."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _git(*args: str, cwd: Path) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=_GIT_ENV
    )
    return done.stdout.strip()


def _publish(*, remotes: Path, name: str, releases: tuple[str, ...]) -> None:
    """A bare `<remotes>/<owner>/<name>.git` whose tip is one commit past its last release."""
    work = remotes / "work" / name
    work.mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=work)
    for release in releases:
        (work / "VERSION").write_text(release)
        _git("add", ".", cwd=work)
        _git("commit", "-q", "-m", release, cwd=work)
        _git("tag", "-a", release, "-m", release, cwd=work)
    (work / "VERSION").write_text("tip")
    _git("add", ".", cwd=work)
    _git("commit", "-q", "-m", "tip", cwd=work)
    bare = remotes / _OWNER / f"{name}.git"
    bare.parent.mkdir(parents=True, exist_ok=True)
    _git("clone", "-q", "--bare", str(work), str(bare), cwd=remotes)


def _remotes(
    *, tmp_path: Path, releases: tuple[str, ...] = (*_STABLE_RELEASES, _PRERELEASE)
) -> Path:
    remotes = tmp_path / "remotes"
    _publish(remotes=remotes, name="livespec", releases=releases)
    return remotes


def _project(*, tmp_path: Path, pinned: str | None) -> Path:
    """A governed tree whose `.livespec.jsonc` is real JSONC: comments and trailing commas."""
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    pinned_line = "" if pinned is None else f'      "pinned": "{pinned}",\n'
    (project / ".livespec.jsonc").write_text(
        "// the governed tree\n"
        "{\n"
        "  /* this plugin's block */\n"
        '  "livespec-orchestrator-beads-fabro": {\n'
        '    "compat": {\n'
        '      "livespec": ">=0.1.0,<1.0.0", // the range\n'
        f"{pinned_line}"
        "    },\n"
        "  },\n"
        "}\n"
    )
    return project


@dataclass(frozen=True, kw_only=True)
class _Done:
    returncode: int
    stderr: str


def _run_program(
    *,
    tmp_path: Path,
    url_base: str,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, str] | None = None,
) -> _Done:
    """Run the materialized program in-process, in `project`, the way the sandbox runs it."""
    source = _module().run_from_program_source(
        url_base=url_base, root=str(tmp_path / "run-from"), repos=("livespec",)
    )
    program = tmp_path / "livespec-run-from-clones.py"
    program.write_text(source)
    _ = [
        monkeypatch.delenv(name) for name in list(os.environ) if name.startswith(_SCRUBBED_PREFIXES)
    ]
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)
    monkeypatch.chdir(project)
    stderr = io.StringIO()
    returncode = 0
    with contextlib.redirect_stderr(stderr):
        try:
            runpy.run_path(str(program), run_name="__main__")
        except SystemExit as raised:
            returncode = int(raised.code or 0)
    return _Done(returncode=returncode, stderr=stderr.getvalue())


def _file_url_base(*, tmp_path: Path) -> str:
    return f"file://{tmp_path / 'remotes' / _OWNER}"


def _clone(*, tmp_path: Path) -> Path:
    return tmp_path / "run-from" / "livespec"


def _version(*, tmp_path: Path) -> str:
    return (_clone(tmp_path=tmp_path) / "VERSION").read_text()


def _is_shallow(*, clone: Path) -> bool:
    return _git("rev-parse", "--is-shallow-repository", cwd=clone) == "true"


def test_an_executed_tool_runs_from_a_pinned_shallow_clone_apart_from_the_work_clones(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 336, first block: the checker runs at the pinned release, not the tip."""
    module = _module()
    _remotes(tmp_path=tmp_path)
    project = _project(tmp_path=tmp_path, pinned="v0.47.1")

    done = _run_program(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        url_base=_file_url_base(tmp_path=tmp_path),
        project=project,
    )

    assert done.returncode == 0, done.stderr
    assert _version(tmp_path=tmp_path) == "v0.47.1"
    assert _is_shallow(clone=_clone(tmp_path=tmp_path))
    siblings = SiblingClones(owner=_OWNER, repos=("livespec",), clones_root="/livespec-siblings")
    value = core_plugin_env_line(siblings=siblings)
    assert value == 'LIVESPEC_CORE_PLUGIN_ROOT = "/livespec-run-from/livespec/.claude-plugin"\n'
    assert module.RUN_FROM_CLONES_ROOT == "/livespec-run-from"
    assert not module.RUN_FROM_CLONES_ROOT.startswith(siblings.clones_root)


def test_the_run_from_clone_is_stripped_of_write_bits_and_reports_the_protection_it_got(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 336: it asks for the immutable flag and says what it achieved, never more."""
    module = _module()
    _remotes(tmp_path=tmp_path)
    project = _project(tmp_path=tmp_path, pinned="v0.47.1")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "chattr.log"
    chattr = fake_bin / "chattr"
    chattr.write_text(f'#!/bin/sh\necho "$@" >> {log}\nexit 0\n')
    chattr.chmod(0o755)

    done = _run_program(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        url_base=_file_url_base(tmp_path=tmp_path),
        project=project,
        env={"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
    )

    assert done.returncode == 0, done.stderr
    clone = _clone(tmp_path=tmp_path)
    for path in (clone, clone / "VERSION", clone / ".git" / "HEAD"):
        assert stat.S_IMODE(path.stat().st_mode) & 0o222 == 0, path
    assert log.read_text().split() == ["-R", "+i", str(clone)]
    enforced = os.geteuid() != 0
    assert (module.RUN_FROM_READ_ONLY_MARKER in done.stderr) is enforced
    assert (module.RUN_FROM_WRITABLE_MARKER in done.stderr) is not enforced


def test_a_refresh_onto_a_tree_pinning_a_different_release_reclones_at_that_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 336, second block: the next check runs from a clone at the newly pinned release."""
    _remotes(tmp_path=tmp_path)
    url_base = _file_url_base(tmp_path=tmp_path)
    project = _project(tmp_path=tmp_path, pinned="v0.47.1")
    assert (
        _run_program(
            monkeypatch=monkeypatch, tmp_path=tmp_path, url_base=url_base, project=project
        ).returncode
        == 0
    )
    assert _version(tmp_path=tmp_path) == "v0.47.1"

    unchanged = _clone(tmp_path=tmp_path).stat().st_ino
    assert (
        _run_program(
            monkeypatch=monkeypatch, tmp_path=tmp_path, url_base=url_base, project=project
        ).returncode
        == 0
    )
    assert _clone(tmp_path=tmp_path).stat().st_ino == unchanged

    _project(tmp_path=tmp_path, pinned="v0.47.2")
    done = _run_program(
        monkeypatch=monkeypatch, tmp_path=tmp_path, url_base=url_base, project=project
    )

    assert done.returncode == 0, done.stderr
    assert _version(tmp_path=tmp_path) == "v0.47.2"
    assert _is_shallow(clone=_clone(tmp_path=tmp_path))
    assert stat.S_IMODE(_clone(tmp_path=tmp_path).stat().st_mode) & 0o222 == 0
    assert not (tmp_path / "run-from" / ".livespec.staging").exists()


def test_a_declaration_the_refresh_cannot_satisfy_leaves_the_current_clone_and_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed re-clone never leaves the run on a clone of some other release."""
    module = _module()
    _remotes(tmp_path=tmp_path)
    url_base = _file_url_base(tmp_path=tmp_path)
    project = _project(tmp_path=tmp_path, pinned="v0.47.1")
    assert (
        _run_program(
            monkeypatch=monkeypatch, tmp_path=tmp_path, url_base=url_base, project=project
        ).returncode
        == 0
    )

    _project(tmp_path=tmp_path, pinned="v9.9.9")
    done = _run_program(
        monkeypatch=monkeypatch, tmp_path=tmp_path, url_base=url_base, project=project
    )

    assert done.returncode == 1
    assert module.RUN_FROM_FAILED_MARKER in done.stderr
    assert "livespec" in done.stderr
    assert "v9.9.9" in done.stderr
    assert _version(tmp_path=tmp_path) == "v0.47.1"


def test_a_repository_with_no_declared_release_runs_from_its_newest_release_tag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 336, third block: newest release tag, never the tip, never a prerelease."""
    _remotes(tmp_path=tmp_path)
    url_base = _file_url_base(tmp_path=tmp_path)
    undeclared = _project(tmp_path=tmp_path, pinned=None)

    done = _run_program(
        monkeypatch=monkeypatch, tmp_path=tmp_path, url_base=url_base, project=undeclared
    )

    assert done.returncode == 0, done.stderr
    assert _version(tmp_path=tmp_path) == "v0.47.2"
    assert _is_shallow(clone=_clone(tmp_path=tmp_path))


def test_a_governed_tree_with_no_config_file_declares_no_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absent `.livespec.jsonc` declares nothing, so the newest release tag governs."""
    _remotes(tmp_path=tmp_path)
    bare = tmp_path / "bare-project"
    bare.mkdir()

    done = _run_program(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        url_base=_file_url_base(tmp_path=tmp_path),
        project=bare,
    )

    assert done.returncode == 0, done.stderr
    assert _version(tmp_path=tmp_path) == "v0.47.2"


def test_a_declared_branch_is_honored_verbatim_like_the_host_janitors_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repository may CHOOSE `main`; the Dispatcher never substitutes a tag for it."""
    _remotes(tmp_path=tmp_path)
    project = _project(tmp_path=tmp_path, pinned="main")

    done = _run_program(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        url_base=_file_url_base(tmp_path=tmp_path),
        project=project,
    )

    assert done.returncode == 0, done.stderr
    assert _version(tmp_path=tmp_path) == "tip"


def test_a_repository_that_publishes_no_release_and_is_declared_none_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing to run from is a failure, because the tip is exactly what must not be run."""
    module = _module()
    _remotes(tmp_path=tmp_path, releases=())
    project = _project(tmp_path=tmp_path, pinned=None)

    done = _run_program(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        url_base=_file_url_base(tmp_path=tmp_path),
        project=project,
    )

    assert done.returncode == 1
    assert module.RUN_FROM_FAILED_MARKER in done.stderr
    assert not _clone(tmp_path=tmp_path).exists()


def test_an_unreachable_repository_is_skipped_like_an_unborn_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Registration precedes birth: one absent repository must not kill the dispatch."""
    project = _project(tmp_path=tmp_path, pinned="v0.47.1")

    done = _run_program(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        url_base=f"file://{tmp_path / 'nowhere'}",
        project=project,
    )

    assert done.returncode == 0, done.stderr
    assert "not reachable" in done.stderr
    assert not _clone(tmp_path=tmp_path).exists()


def test_the_work_clones_are_full_history_default_branch_clones() -> None:
    """Scenario 336, fourth block: each sibling work clone is non-shallow and the latest."""
    siblings = SiblingClones(
        owner=_OWNER, repos=("livespec", "livespec-overseer"), clones_root="/livespec-siblings"
    )

    block = sibling_clone_steps_block(siblings=siblings)

    assert "--depth" not in block
    assert block.count("git clone --quiet") == 2
    assert "--branch" not in block
    assert "/livespec-siblings/livespec " in block


def test_the_steps_block_materializes_the_program_and_runs_it_for_the_planned_repos(
    tmp_path: Path,
) -> None:
    """The rendered prepare step, executed the way the engine does, lands the clone."""
    module = _module()
    _remotes(tmp_path=tmp_path)
    project = _project(tmp_path=tmp_path, pinned="v0.47.1")
    siblings = SiblingClones(
        owner=_OWNER, repos=("livespec", "livespec-overseer"), clones_root="/livespec-siblings"
    )

    block = module.run_from_clone_steps_block(
        siblings=siblings,
        remote_base=f"file://{tmp_path / 'remotes'}",
        run_from_root=str(tmp_path / "run-from"),
    )

    (step,) = steps_in(block=block)
    plugins = tmp_path / "plugins"
    done = subprocess.run(
        ["bash", "-c", runnable_script(step=step)],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
        env={**_GIT_ENV, "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins)},
    )
    assert done.returncode == 0, done.stderr
    assert (plugins / module.RUN_FROM_PROGRAM_FILENAME).is_file()
    assert _version(tmp_path=tmp_path) == "v0.47.1"
    assert not (tmp_path / "run-from" / "livespec-overseer").exists()


def test_no_livespec_among_the_siblings_renders_no_step_and_no_env_lines() -> None:
    """The target IS livespec, or the fleet has none: nothing to run from, nothing projected."""
    module = _module()
    for repos in ((), ("livespec-overseer",)):
        siblings = SiblingClones(owner=_OWNER, repos=repos, clones_root="/livespec-siblings")
        assert module.run_from_clone_steps_block(siblings=siblings) == ""
        assert module.run_from_clones_env_line(siblings=siblings) == ""
        assert core_plugin_env_line(siblings=siblings) == ""
    assert module.run_from_clones_env_line(siblings=None) == ""


def test_the_env_line_names_the_run_from_root_when_livespec_is_planned() -> None:
    module = _module()
    siblings = SiblingClones(owner=_OWNER, repos=("livespec",), clones_root="/livespec-siblings")

    assert (
        module.run_from_clones_env_line(siblings=siblings)
        == 'LIVESPEC_RUN_FROM_CLONES_ROOT = "/livespec-run-from"\n'
    )


def test_the_overlay_projects_the_run_from_clone_and_no_core_path_under_the_siblings() -> None:
    """The materialized run config carries the step and both env lines, and no work-clone core."""
    module = _module()
    siblings = SiblingClones(
        owner=_OWNER, repos=("livespec", "livespec-overseer"), clones_root="/livespec-siblings"
    )

    overlay_token = "test-oauth-token"
    rendered = render_run_config_overlay(
        committed_text=(_WORKFLOW_DIR / "workflow.toml").read_text(encoding="utf-8"),
        workflow_dir=_WORKFLOW_DIR,
        token=overlay_token,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=siblings,
    )

    assert rendered is not None
    env_table_at = rendered.index("[environments.livespec-ci.env]")
    for line in (
        'LIVESPEC_CORE_PLUGIN_ROOT = "/livespec-run-from/livespec/.claude-plugin"',
        'LIVESPEC_RUN_FROM_CLONES_ROOT = "/livespec-run-from"',
    ):
        assert rendered.index(line) > env_table_at
    assert "/livespec-siblings/livespec/.claude-plugin" not in rendered
    assert module.RUN_FROM_PROGRAM_FILENAME in rendered


def test_every_node_that_checks_a_refreshed_tree_refreshes_the_run_from_clones_first() -> None:
    """Scenario 336, second block, at the graph: janitor, publish_draft and pr_refresh."""
    module = _module()
    graph = parse_dot_graph(text=(_WORKFLOW_DIR / "workflow.fabro").read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph

    janitor = graph.nodes["janitor"]["script"]
    assert (
        janitor.index("livespec-run-plugin-gate.py")
        < janitor.index(module.RUN_FROM_PROGRAM_FILENAME)
        < janitor.index("{{ inputs.sandbox_check_suite }}")
    )
    assert "LIVESPEC_JANITOR_RUN_FROM_CLONE_FAILED" in janitor
    for node in ("publish_draft", "pr_refresh"):
        script = graph.nodes[node]["script"]
        gate = script.index("livespec_declared_gate() {")
        assert (
            gate
            < script.index(module.RUN_FROM_PROGRAM_FILENAME, gate)
            < script.index("{{ inputs.sandbox_check_suite }}", gate)
        ), node

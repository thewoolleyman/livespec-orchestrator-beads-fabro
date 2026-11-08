"""A refresh-repair brief for a failed gate carries each failed target's own output.

WHAT THIS BINDS. `SPECIFICATION/contracts.md` section "Refresh repair" requires a
refresh-repair brief to name each failed gate target, and a fix visit entered from
a red janitor receives the janitor's failure output. The three stages that record
a failed-gate brief -- `janitor`, `publish_draft` and `pr_refresh` -- used to cut
the gate output down to its last 2000 bytes. The aggregate runner writes each
target's own section first and its summary, the per-target wall-time table, the
`Failed targets` list and the failure digest last, so on a full aggregate those
2000 bytes were always the summary tail and no failed target's own lines reached
the fix turn (measured 2026-11-08 on bd-ib-ofvsr3 run 01M6X173QWS677D3PHAMBEAZ89).

EVERY CASE EXECUTES THE SHIPPED SCRIPT BYTES against a real throwaway origin and
clone, with a stand-in for the repository's declared suite that prints an
aggregate-shaped output. Only the engine's own template tokens are substituted.
"""

from __future__ import annotations

import os
import shlex
import stat
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    plugin_cache_gate_prepare_step,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    PUBLICATION_PUSH_PROGRAM_FILENAME,
    publication_push_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_state import (
    PUBLICATION_STATE_GIT_PATH,
    PUBLISH_HEAD_STATE_FILENAME,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_merge import (
    RECORD_FILE_MERGE_PROGRAM_FILENAME,
    record_file_merge_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_regeneration import (
    RECORD_FILE_PROGRAM_FILENAME,
    record_file_program_source,
)

from tests.prepare_step_support import runnable_script

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_DEFAULT_BRANCH = "master"
_BRANCH = "feat/bd-ib-w423x7"
_BRIEF_FILENAME = "livespec-refresh-repair-brief"
_FAILED_GATE_LABEL = "failed-gate-targets: "
_COVERAGE_ENV_PREFIXES = ("COVERAGE_PROCESS_START", "COV_CORE_")
_NODES = ("janitor", "publish_draft", "pr_refresh")
_GH_UNARMED_STUB = "#!/bin/sh\necho null\n"


def _aggregate_output(*, with_summary: bool) -> str:
    """An aggregate-shaped output: sections first, then the summary tail."""
    alpha = [f"alpha-own-line-{n}" for n in range(1, 6)]
    gamma = [f"gamma-line-{n}" for n in range(1, 101)] + ["gamma-final-error"]
    table = [f"  {n}.0s  check-row-{n}" for n in range(95)]
    lines = [
        "",
        "::: just check-alpha [FAILED, wall: 1.0s]",
        *alpha,
        "",
        "::: just check-beta [ok, wall: 1.0s]",
        "beta-passing-line",
        "",
        "::: just check-gamma [FAILED, wall: 2.0s]",
        *gamma,
    ]
    if with_summary:
        lines += [
            "",
            "--- parallel check summary ---",
            "passed: 1, failed: 2, skipped: 0",
            "",
            "per-target wall times (longest first):",
            *table,
            "",
            "Failed targets (2):",
            "  - check-alpha",
            "  - check-gamma",
            "digest-line: failed without a structured failure_mode",
        ]
    return "\n".join(lines) + "\n"


def _suite(*, root: Path, with_summary: bool) -> str:
    """The declared-suite stand-in: prints the aggregate-shaped output and fails."""
    output = root / "aggregate-output.txt"
    _ = output.write_text(_aggregate_output(with_summary=with_summary), encoding="utf-8")
    script = root / "declared-check-suite"
    _ = script.write_text(f"#!/bin/sh\ncat {shlex.quote(str(output))}\nexit 1\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return str(script)


def _env() -> dict[str, str]:
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(_COVERAGE_ENV_PREFIXES)
    } | {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }


def _git(*argv: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv], cwd=cwd, check=True, capture_output=True, text=True, env=_env()
    )


def _commit(*, cwd: Path, path: str, text: str, subject: str) -> None:
    _ = (cwd / path).write_text(text, encoding="utf-8")
    _ = _git("add", path, cwd=cwd)
    _ = _git("commit", "--quiet", "-m", subject, cwd=cwd)


def _node_script(*, node: str, check_suite: str) -> str:
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes[node]["script"]
    return (
        script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH)
        .replace("{{ inputs.sandbox_check_suite }}", check_suite)
        .replace("{{ inputs.conformance_hook_install }}", "")
        .replace(
            "dev-tooling/refresh-before-janitor.sh",
            str(_REPO_ROOT / "dev-tooling" / "refresh-before-janitor.sh"),
        )
    )


def _build_world(*, root: Path) -> tuple[Path, Path]:
    """A bare origin and a clone on a run branch carrying one owned-file commit."""
    origin = root / "origin.git"
    origin.mkdir()
    _ = _git("init", "--bare", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=origin)
    seed = root / "seed"
    seed.mkdir()
    _ = _git("init", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=seed)
    _commit(cwd=seed, path="shared.txt", text="base\n", subject="chore: seed")
    _ = _git("push", "--quiet", str(origin), f"HEAD:refs/heads/{_DEFAULT_BRANCH}", cwd=seed)
    clone = root / "clone"
    _ = _git("clone", "--quiet", str(origin), str(clone), cwd=root)
    _ = _git("switch", "--quiet", "-c", "fabro/run/test", cwd=clone)
    _ = _git("config", "user.email", "t@example.invalid", cwd=clone)
    _ = _git("config", "user.name", "Test", cwd=clone)
    _commit(cwd=clone, path="owned.txt", text="run\n", subject="feat: run work")
    mover = root / "mover"
    _ = _git("clone", "--quiet", str(origin), str(mover), cwd=root)
    _commit(cwd=mover, path="shared.txt", text="moved\n", subject="feat: advance")
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_DEFAULT_BRANCH}", cwd=mover)
    return origin, clone


def _plugins(*, root: Path) -> Path:
    plugins = root / "plugins"
    plugins.mkdir()
    gate = plugins / "livespec-run-plugin-gate.py"
    _ = gate.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    gate.chmod(gate.stat().st_mode | stat.S_IXUSR)
    _ = (plugins / RECORD_FILE_MERGE_PROGRAM_FILENAME).write_text(
        record_file_merge_program_source(), encoding="utf-8"
    )
    _ = (plugins / RECORD_FILE_PROGRAM_FILENAME).write_text(
        record_file_program_source(), encoding="utf-8"
    )
    push_program = plugins / PUBLICATION_PUSH_PROGRAM_FILENAME
    _ = push_program.write_text(publication_push_program_source(), encoding="utf-8")
    push_program.chmod(0o700)
    bin_dir = root / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    _ = gh.write_text(_GH_UNARMED_STUB, encoding="utf-8")
    gh.chmod(0o755)
    return plugins


def _stage_env(*, root: Path, plugins: Path) -> dict[str, str]:
    return {
        "PATH": f"{root / 'bin'}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(root / "home"),
        "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
        "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(root / "no-gh-refresh"),
        "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins),
    }


def _prepare_published(*, root: Path, clone: Path, plugins: Path) -> None:
    """Give `pr_refresh` the publication provenance it demands."""
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=clone)
    state = clone / ".git" / PUBLICATION_STATE_GIT_PATH
    state.mkdir(parents=True, exist_ok=True)
    head = _git("rev-parse", "HEAD", cwd=clone).stdout.strip()
    _ = (state / PUBLISH_HEAD_STATE_FILENAME).write_text(head, encoding="utf-8")
    installer = root / "install-plugin-gate.sh"
    _ = installer.write_text(
        runnable_script(step=plugin_cache_gate_prepare_step()), encoding="utf-8"
    )
    _ = subprocess.run(
        ["bash", str(installer)],
        check=True,
        capture_output=True,
        text=True,
        env=_stage_env(root=root, plugins=plugins),
    )


def _refuse_every_push(*, clone: Path) -> None:
    hook = clone / ".git" / "hooks" / "pre-push"
    hook.parent.mkdir(parents=True, exist_ok=True)
    _ = hook.write_text(
        "#!/bin/sh\nprintf '%s\\n' 'the repository gate refused this head' >&2\nexit 1\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)


def _failed_gate_line(*, node: str, root: Path, with_summary: bool) -> str:
    """Run one node against a red declared suite and return its brief's gate line."""
    _, clone = _build_world(root=root)
    plugins = _plugins(root=root)
    if node == "pr_refresh":
        _prepare_published(root=root, clone=clone, plugins=plugins)
    if node == "publish_draft":
        _refuse_every_push(clone=clone)
    suite = _suite(root=root, with_summary=with_summary)
    result = subprocess.run(
        ["bash", "-c", _node_script(node=node, check_suite=suite)],
        cwd=clone,
        check=False,
        capture_output=True,
        text=True,
        env=_stage_env(root=root, plugins=plugins),
    )
    assert result.returncode != 0, result.stdout
    brief_path = clone / ".git" / PUBLICATION_STATE_GIT_PATH / _BRIEF_FILENAME
    assert brief_path.is_file(), result.stderr
    lines = [
        line
        for line in brief_path.read_text(encoding="utf-8").splitlines()
        if line.startswith(_FAILED_GATE_LABEL)
    ]
    assert len(lines) == 1, lines
    return lines[0]


@pytest.mark.parametrize("node", _NODES)
def test_the_brief_carries_each_failed_targets_own_failure_lines(
    *, node: str, tmp_path: Path
) -> None:
    line = _failed_gate_line(node=node, root=tmp_path, with_summary=True)

    assert "alpha-own-line-1 " in line
    assert "alpha-own-line-5 " in line
    assert "gamma-final-error " in line
    assert "gamma-line-100 " in line


@pytest.mark.parametrize("node", _NODES)
def test_the_brief_carries_at_most_the_last_80_lines_of_each_failed_section(
    *, node: str, tmp_path: Path
) -> None:
    line = _failed_gate_line(node=node, root=tmp_path, with_summary=True)

    assert "gamma-line-22 " in line
    assert "gamma-line-21 " not in line
    assert "gamma-line-1 " not in line


@pytest.mark.parametrize("node", _NODES)
def test_the_brief_leaves_out_passing_targets_and_the_summary_tail(
    *, node: str, tmp_path: Path
) -> None:
    line = _failed_gate_line(node=node, root=tmp_path, with_summary=True)

    assert "beta-passing-line" not in line
    assert "check-row-" not in line


@pytest.mark.parametrize("node", _NODES)
def test_the_brief_still_names_each_failed_gate_target(*, node: str, tmp_path: Path) -> None:
    line = _failed_gate_line(node=node, root=tmp_path, with_summary=True)

    assert "check-alpha" in line
    assert "check-gamma" in line


@pytest.mark.parametrize("node", _NODES)
def test_an_output_with_no_failed_targets_summary_keeps_its_last_80_lines(
    *, node: str, tmp_path: Path
) -> None:
    line = _failed_gate_line(node=node, root=tmp_path, with_summary=False)

    assert "gamma-final-error" in line
    assert "gamma-line-22 " in line
    assert "gamma-line-21 " not in line
    assert "alpha-own-line-1 " not in line

"""Scenario 305 refreshes the run before the janitor's aggregate.

The stage scripts are exercised against real throwaway repositories because a
stubbed rebase cannot establish which head the janitor checked or which head
``publish_draft`` pushed.  The forge remains doubled: Scenario 305 is about
the branch and the repository gate, not GitHub's pull-request API.
"""

from __future__ import annotations

import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_merge import (
    RECORD_FILE_MERGE_PROGRAM_FILENAME,
    record_file_merge_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_regeneration import (
    RECORD_FILE_PROGRAM_FILENAME,
    record_file_program_source,
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
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"
_JANITOR_REFRESH = _REPO_ROOT / "dev-tooling" / "refresh-before-janitor.sh"
_DEFAULT_BRANCH = "master"
_PUBLISH_BRANCH = "feat/bd-ib-fvgkw4"
_STATE_DIRECTORY = ".git/livespec-publication"


def _git(*argv: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv],
        check=True,
        capture_output=True,
        cwd=cwd,
        text=True,
    )


def _commit(*, cwd: Path, path: str, text: str, subject: str) -> str:
    target = cwd / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _ = _git("add", path, cwd=cwd)
    _ = _git("commit", "-m", subject, cwd=cwd)
    return _git("rev-parse", "HEAD", cwd=cwd).stdout.strip()


def _script(*, node: str, check_suite: str) -> str:
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes[node]["script"]
    return (
        script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH)
        .replace("{{ inputs.sandbox_check_suite }}", check_suite)
        .replace(r"\"", '"')
    )


def _world(
    *, root: Path, conflicting: bool = False, default_advances: bool = True
) -> tuple[Path, Path]:
    origin = root / "origin.git"
    _ = _git("init", "--bare", "--initial-branch=master", str(origin), cwd=root)
    seed = root / "seed"
    seed.mkdir()
    _ = _git("init", "--initial-branch=master", cwd=seed)
    _ = _git("config", "user.name", "Test", cwd=seed)
    _ = _git("config", "user.email", "test@example.invalid", cwd=seed)
    _ = _commit(cwd=seed, path="shared.txt", text="base\n", subject="chore: seed")
    _ = _git("remote", "add", "origin", str(origin), cwd=seed)
    _ = _git("push", "-u", "origin", _DEFAULT_BRANCH, cwd=seed)

    run = root / "run"
    _ = _git("clone", str(origin), str(run), cwd=root)
    _ = _git("config", "user.name", "Test", cwd=run)
    _ = _git("config", "user.email", "test@example.invalid", cwd=run)
    _ = _git("switch", "-c", "fabro/run/test", cwd=run)
    run_path = "shared.txt" if conflicting else "owned.txt"
    _ = _commit(cwd=run, path=run_path, text="run\n", subject="feat: run work")

    default = root / "default"
    _ = _git("clone", str(origin), str(default), cwd=root)
    _ = _git("config", "user.name", "Test", cwd=default)
    _ = _git("config", "user.email", "test@example.invalid", cwd=default)
    if default_advances:
        default_path = "shared.txt"
        _ = _commit(cwd=default, path=default_path, text="default\n", subject="feat: default move")
        _ = _git("push", "origin", _DEFAULT_BRANCH, cwd=default)
    return run, default


def _plugins(*, root: Path) -> Path:
    plugins = root / "plugins"
    plugins.mkdir()
    gate = plugins / "livespec-run-plugin-gate.py"
    gate.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    gate.chmod(gate.stat().st_mode | stat.S_IXUSR)
    _ = (plugins / RECORD_FILE_MERGE_PROGRAM_FILENAME).write_text(
        record_file_merge_program_source(), encoding="utf-8"
    )
    _ = (plugins / RECORD_FILE_PROGRAM_FILENAME).write_text(
        record_file_program_source(), encoding="utf-8"
    )
    bin_dir = plugins / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'if test "$1 $2" = "pr create"; then echo "https://example.invalid/pull/1"; fi\n',
        encoding="utf-8",
    )
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    just = bin_dir / "just"
    just.write_text(
        "#!/bin/sh\n"
        'echo "$LIVESPEC_FACTORY_REFRESH_MERGE $*" >> "$(dirname "$0")/just-calls"\n'
        'exit "$(cat "$(dirname "$0")/just-exit" 2>/dev/null || echo 0)"\n',
        encoding="utf-8",
    )
    just.chmod(just.stat().st_mode | stat.S_IXUSR)
    return plugins


def _just_calls(*, plugins: Path) -> list[str]:
    log = plugins / "bin" / "just-calls"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _environment(*, plugins: Path) -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE")
    } | {
        "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins),
        "LIVESPEC_PUBLISH_BRANCH": _PUBLISH_BRANCH,
        "PATH": f"{plugins / 'bin'}:{os.environ['PATH']}",
    }


def _subprocess_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE")
    }


def _install_janitor_refresh_helper(*, cwd: Path) -> None:
    for source in (
        _JANITOR_REFRESH,
        _REPO_ROOT / "dev-tooling" / "record-refresh-merge-evidence.sh",
    ):
        target = cwd / source.relative_to(_REPO_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_bytes(source.read_bytes())
        target.chmod(source.stat().st_mode)


def _run(
    *, node: str, cwd: Path, plugins: Path, check_suite: str
) -> subprocess.CompletedProcess[str]:
    if node == "janitor":
        _install_janitor_refresh_helper(cwd=cwd)
    return subprocess.run(
        ["sh", "-c", _script(node=node, check_suite=check_suite)],
        check=False,
        capture_output=True,
        cwd=cwd,
        env=_environment(plugins=plugins),
        text=True,
    )


def _suite(*, root: Path, body: str) -> Path:
    path = root / "suite"
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _brief(*, run: Path) -> str:
    return (run / _STATE_DIRECTORY / "livespec-refresh-repair-brief").read_text(encoding="utf-8")


def test_scenario305_refreshes_before_janitor_and_pushes_that_exact_green_head(
    *, tmp_path: Path
) -> None:
    run, default = _world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    checked = tmp_path / "checked-head"
    suite = _suite(
        root=tmp_path,
        body=f"git write-tree > {shlex.quote(str(checked))}",
    )

    janitor = _run(node="janitor", cwd=run, plugins=plugins, check_suite=str(suite))

    assert janitor.returncode == 0, janitor.stderr
    green_head = _git("rev-parse", "HEAD", cwd=run).stdout.strip()
    advanced = _git("rev-parse", "HEAD", cwd=default).stdout.strip()
    assert _git("merge-base", "--is-ancestor", advanced, green_head, cwd=run).returncode == 0
    assert _git("rev-list", "--parents", "-n", "1", green_head, cwd=run).stdout.split() == [
        green_head,
        advanced,
    ]
    assert (
        checked.read_text(encoding="utf-8").strip()
        == _git("rev-parse", "HEAD^{tree}", cwd=run).stdout.strip()
    )
    marker = run / _STATE_DIRECTORY / "livespec-janitor-passed-head"
    assert marker.read_text(encoding="utf-8").strip() == green_head

    _ = _commit(cwd=default, path="later.txt", text="later\n", subject="feat: later default move")
    _ = _git("push", "origin", _DEFAULT_BRANCH, cwd=default)
    pushed = _run(node="publish_draft", cwd=run, plugins=plugins, check_suite="false")

    assert pushed.returncode == 0, pushed.stderr
    assert _git("rev-parse", "HEAD", cwd=run).stdout.strip() == green_head
    remote = _git("ls-remote", "origin", f"refs/heads/{_PUBLISH_BRANCH}", cwd=run)
    assert remote.stdout.split()[0] == green_head
    assert "LIVESPEC_PUBLISH_DRAFT_REFRESH_SKIPPED" in pushed.stderr


def test_scenario305_preserves_an_existing_publish_branch_during_janitor_refresh(
    *, tmp_path: Path
) -> None:
    run, _ = _world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    published_anchor = _git("rev-parse", "HEAD", cwd=run).stdout.strip()
    _ = _git(
        "push",
        "origin",
        f"HEAD:refs/heads/{_PUBLISH_BRANCH}",
        cwd=run,
    )

    janitor = _run(node="janitor", cwd=run, plugins=plugins, check_suite="true")

    assert janitor.returncode == 0, janitor.stderr
    janitor_passed_head = _git("rev-parse", "HEAD", cwd=run).stdout.strip()
    assert _just_calls(plugins=plugins) == []
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", published_anchor, janitor_passed_head],
            check=False,
            cwd=run,
        ).returncode
        == 0
    )

    pushed = _run(node="publish_draft", cwd=run, plugins=plugins, check_suite="true")

    assert pushed.returncode == 0, pushed.stderr
    remote = _git("ls-remote", "origin", f"refs/heads/{_PUBLISH_BRANCH}", cwd=run)
    assert remote.stdout.split()[0] == janitor_passed_head


def test_scenario305_janitor_refresh_merge_refused_by_aggregate_restores_and_briefs(
    *, tmp_path: Path
) -> None:
    """A merged index the janitor aggregate refuses is never committed."""
    run, _ = _world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    before = _git("rev-parse", "HEAD", cwd=run).stdout.strip()
    _ = _git("push", "origin", f"HEAD:refs/heads/{_PUBLISH_BRANCH}", cwd=run)

    janitor = _run(
        node="janitor", cwd=run, plugins=plugins, check_suite="echo red-target >&2; exit 3"
    )

    assert janitor.returncode == 3
    assert _git("rev-parse", "HEAD", cwd=run).stdout.strip() == before
    assert f"pre-refresh-head: {before}" in _brief(run=run)
    assert "failed-gate-targets: red-target" in _brief(run=run)
    assert "LIVESPEC_REFRESH_REPAIR" in janitor.stderr


def test_scenario305_noop_janitor_refresh_skips_evidence_and_merge_commit(
    *, tmp_path: Path
) -> None:
    """A contained default branch leaves the janitor no merge to evidence or commit."""
    run, _ = _world(root=tmp_path, default_advances=False)
    plugins = _plugins(root=tmp_path)
    before = _git("rev-parse", "HEAD", cwd=run).stdout.strip()
    _ = _git("push", "origin", f"HEAD:refs/heads/{_PUBLISH_BRANCH}", cwd=run)

    janitor = _run(node="janitor", cwd=run, plugins=plugins, check_suite="true")

    assert janitor.returncode == 0, janitor.stderr
    assert _git("rev-parse", "HEAD", cwd=run).stdout.strip() == before
    assert _just_calls(plugins=plugins) == []


def test_scenario305_noop_preserved_refresh_skips_evidence_and_merge_commit(
    *, tmp_path: Path
) -> None:
    """A contained default branch leaves no merge to evidence or commit."""
    run, _ = _world(root=tmp_path, default_advances=False)
    plugins = _plugins(root=tmp_path)
    before = _git("rev-parse", "HEAD", cwd=run).stdout.strip()
    _ = _git("push", "origin", f"HEAD:refs/heads/{_PUBLISH_BRANCH}", cwd=run)

    pushed = _run(node="publish_draft", cwd=run, plugins=plugins, check_suite="false")

    assert pushed.returncode == 0, pushed.stderr
    assert _git("rev-parse", "HEAD", cwd=run).stdout.strip() == before
    remote = _git("ls-remote", "origin", f"refs/heads/{_PUBLISH_BRANCH}", cwd=run)
    assert remote.stdout.split()[0] == before


def test_scenario305_conflicting_pre_aggregate_refresh_restores_and_briefs_for_fix(
    *, tmp_path: Path
) -> None:
    run, _ = _world(root=tmp_path, conflicting=True)
    plugins = _plugins(root=tmp_path)
    before = _git("rev-parse", "HEAD", cwd=run).stdout.strip()

    janitor = _run(node="janitor", cwd=run, plugins=plugins, check_suite="true")

    assert janitor.returncode != 0
    assert _git("rev-parse", "HEAD", cwd=run).stdout.strip() == before
    brief = _brief(run=run)
    assert f"pre-refresh-head: {before}" in brief
    assert "conflicted-paths: shared.txt" in brief
    assert "LIVESPEC_REFRESH_REPAIR" in janitor.stderr


def test_scenario305_conflicting_merge_refresh_restores_and_briefs_for_fix(
    *, tmp_path: Path
) -> None:
    run, _ = _world(root=tmp_path, conflicting=True)
    plugins = _plugins(root=tmp_path)
    before = _git("rev-parse", "HEAD", cwd=run).stdout.strip()
    _ = _git(
        "push",
        "origin",
        f"HEAD:refs/heads/{_PUBLISH_BRANCH}",
        cwd=run,
    )

    janitor = _run(node="janitor", cwd=run, plugins=plugins, check_suite="true")

    assert janitor.returncode != 0
    assert _git("rev-parse", "HEAD", cwd=run).stdout.strip() == before
    brief = _brief(run=run)
    assert f"pre-refresh-head: {before}" in brief
    assert "conflicted-paths: shared.txt" in brief
    assert "LIVESPEC_REFRESH_REPAIR" in janitor.stderr


def test_scenario305_red_refreshed_aggregate_restores_and_briefs_for_fix(*, tmp_path: Path) -> None:
    run, _ = _world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    before = _git("rev-parse", "HEAD", cwd=run).stdout.strip()
    suite = _suite(root=tmp_path, body="echo red-target >&2\nexit 7")

    janitor = _run(node="janitor", cwd=run, plugins=plugins, check_suite=str(suite))

    assert janitor.returncode == 7
    assert _git("rev-parse", "HEAD", cwd=run).stdout.strip() == before
    brief = _brief(run=run)
    assert f"pre-refresh-head: {before}" in brief
    assert "failed-gate-targets: red-target" in brief
    assert "LIVESPEC_REFRESH_REPAIR" in janitor.stderr


def test_scenario305_refresh_merge_reuses_the_janitor_aggregate_evidence() -> None:
    """The janitor gates the merged index once before ordinary commit hooks run."""
    workflow = _WORKFLOW.read_text(encoding="utf-8")
    lefthook = _LEFTHOOK.read_text(encoding="utf-8")
    refresh = _JANITOR_REFRESH.read_text(encoding="utf-8")

    assert "bash dev-tooling/refresh-before-janitor.sh" in workflow
    assert refresh.count("LIVESPEC_FACTORY_REFRESH_MERGE=true git merge --no-commit --no-ff") == 1
    assert "check-refresh-merge-pre-commit" not in refresh
    assert "record-refresh-merge-evidence.sh" in refresh
    assert "GIT_EDITOR=true LIVESPEC_FACTORY_REFRESH_MERGE=true git commit --no-edit" in refresh
    assert "pre-merge-commit:" not in lefthook


def test_scenario305_commit_refuse_install_removes_the_lefthook_merge_wrapper(
    *, tmp_path: Path
) -> None:
    """The factory's real hook-install order cannot carry refresh behavior."""
    repo = tmp_path / "hook-order"
    repo.mkdir()
    _ = _git("init", cwd=repo)
    _ = (repo / "lefthook.yml").write_text(
        _LEFTHOOK.read_text(encoding="utf-8")
        + "\npre-merge-commit:\n  commands:\n    00-test-wrapper:\n      run: true\n",
        encoding="utf-8",
    )

    lefthook = subprocess.run(
        ["lefthook", "install"],
        check=False,
        capture_output=True,
        cwd=repo,
        env=_subprocess_environment(),
        text=True,
    )
    assert lefthook.returncode == 0, lefthook.stderr
    merge_hook = repo / ".git" / "hooks" / "pre-merge-commit"
    assert merge_hook.is_file()

    installed = subprocess.run(
        [sys.executable, "-m", "livespec_dev_tooling.install_commit_refuse_hooks"],
        check=False,
        capture_output=True,
        cwd=repo,
        env=_subprocess_environment(),
        text=True,
    )

    assert installed.returncode == 0, installed.stderr
    assert not merge_hook.exists()


_ROUTE = "janitor_refresh_route"


def _edges(*, source: str) -> list[tuple[str, dict[str, str]]]:
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return [
        (edge.destination, dict(edge.attributes)) for edge in graph.edges if edge.source == source
    ]


def test_scenario305_a_red_janitor_reaches_refresh_repair_through_the_brief_route() -> None:
    red = [
        destination
        for destination, attributes in _edges(source="janitor")
        if attributes.get("condition") == "outcome!=succeeded"
    ]
    assert red == [_ROUTE]
    arms = {
        attributes.get("condition", ""): destination
        for destination, attributes in _edges(source=_ROUTE)
    }
    assert arms["preferred_label=refresh_repair"] == "refresh_repair"
    assert arms[""] == "fix"


def _route_label(*, run: Path, plugins: Path) -> str:
    done = _run(node=_ROUTE, cwd=run, plugins=plugins, check_suite="true")
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def test_scenario305_the_route_sends_only_a_janitor_brief_to_refresh_repair(
    *, tmp_path: Path
) -> None:
    run, _ = _world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    state = run / _STATE_DIRECTORY
    state.mkdir(parents=True)
    brief = state / "livespec-refresh-repair-brief"

    assert '"preferred_next_label":"fix"' in _route_label(run=run, plugins=plugins)

    _ = brief.write_text("LIVESPEC_REFRESH_REPAIR_BRIEF\nstage: publish_draft\n", encoding="utf-8")
    assert '"preferred_next_label":"fix"' in _route_label(run=run, plugins=plugins)

    _ = brief.write_text("LIVESPEC_REFRESH_REPAIR_BRIEF\nstage: janitor\n", encoding="utf-8")
    assert '"preferred_next_label":"refresh_repair"' in _route_label(run=run, plugins=plugins)


def test_scenario305_a_janitor_visit_drops_the_previous_janitor_brief_only(
    *, tmp_path: Path
) -> None:
    run, _ = _world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    state = run / _STATE_DIRECTORY
    state.mkdir(parents=True)
    brief = state / "livespec-refresh-repair-brief"

    _ = brief.write_text("LIVESPEC_REFRESH_REPAIR_BRIEF\nstage: publish_draft\n", encoding="utf-8")
    _ = _run(node="janitor", cwd=run, plugins=plugins, check_suite="true")
    assert "stage: publish_draft" in brief.read_text(encoding="utf-8")

    _ = _git("reset", "--hard", "HEAD", cwd=run)
    _ = brief.write_text("LIVESPEC_REFRESH_REPAIR_BRIEF\nstage: janitor\n", encoding="utf-8")
    _ = _run(node="janitor", cwd=run, plugins=plugins, check_suite="true")
    assert not brief.exists()


def test_scenario305_an_empty_checkpoint_after_the_janitor_still_takes_the_skip(
    *, tmp_path: Path
) -> None:
    run, default = _world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    janitor = _run(node="janitor", cwd=run, plugins=plugins, check_suite="true")
    assert janitor.returncode == 0, janitor.stderr
    green_tree = _git("rev-parse", "HEAD^{tree}", cwd=run).stdout.strip()
    _ = _git("commit", "--allow-empty", "-m", "fabro: checkpoint", cwd=run)
    _ = _commit(cwd=default, path="later.txt", text="later\n", subject="feat: later default move")
    _ = _git("push", "origin", _DEFAULT_BRANCH, cwd=default)

    pushed = _run(node="publish_draft", cwd=run, plugins=plugins, check_suite="false")

    assert pushed.returncode == 0, pushed.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_REFRESH_SKIPPED" in pushed.stderr
    assert _git("rev-parse", "HEAD^{tree}", cwd=run).stdout.strip() == green_tree
    remote = _git("ls-remote", "origin", f"refs/heads/{_PUBLISH_BRANCH}", cwd=run)
    pushed_head = remote.stdout.split()[0]
    assert _git("rev-parse", f"{pushed_head}^{{tree}}", cwd=run).stdout.strip() == green_tree
    empties = _git(
        "rev-list", "--no-merges", "--max-count=1", "--min-parents=1", pushed_head, cwd=run
    )
    assert _git(
        "diff-tree", "--no-commit-id", "--name-only", "-r", empties.stdout.strip(), cwd=run
    ).stdout.strip()

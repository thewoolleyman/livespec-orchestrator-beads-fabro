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


def _script(*, node: str, check_suite: str, conformance_hook_install: str = "") -> str:
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes[node]["script"]
    return (
        script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH)
        .replace("{{ inputs.sandbox_check_suite }}", check_suite)
        .replace("{{ inputs.conformance_hook_install }}", conformance_hook_install)
        .replace(r"\"", '"')
    )


def _world(*, root: Path, conflicting: bool = False) -> tuple[Path, Path]:
    origin = root / "origin.git"
    _ = _git("init", "--bare", "--initial-branch=master", str(origin), cwd=root)
    seed = root / "seed"
    seed.mkdir()
    _ = _git("init", "--initial-branch=master", cwd=seed)
    _ = _git("config", "user.name", "Test", cwd=seed)
    _ = _git("config", "user.email", "test@example.invalid", cwd=seed)
    _ = _commit(cwd=seed, path="shared.txt", text="base\n", subject="chore: seed")
    _ = _commit(
        cwd=seed,
        path="canonical-hook-body",
        text="old canonical hook body\n",
        subject="chore: seed canonical hook body",
    )
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
    return plugins


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


def _run(
    *,
    node: str,
    cwd: Path,
    plugins: Path,
    check_suite: str,
    conformance_hook_install: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "sh",
            "-c",
            _script(
                node=node,
                check_suite=check_suite,
                conformance_hook_install=conformance_hook_install,
            ),
        ],
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
        body=f"git rev-parse HEAD > {shlex.quote(str(checked))}",
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
    assert checked.read_text(encoding="utf-8").strip() == green_head
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


def test_scenario305_janitor_reinstalls_conformance_hooks_after_a_clean_refresh(
    *, tmp_path: Path
) -> None:
    """The aggregate sees the hook body from the tree janitor just rebased onto."""
    run, default = _world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    # The run's hook body is deliberately stale once the separate default clone
    # advances. The suite below checks the installed bytes rather than merely
    # counting installer calls, so it distinguishes a pre-refresh install from
    # the required post-refresh install.
    _ = _commit(
        cwd=default,
        path="canonical-hook-body",
        text="new canonical hook body\n",
        subject="chore: update canonical hook body",
    )
    _ = _git("push", "origin", _DEFAULT_BRANCH, cwd=default)
    trace = tmp_path / "conformance-hook-installs"
    installer = tmp_path / "install-conformance-hooks"
    installer.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' install >> {shlex.quote(str(trace))}\n"
        "body=$(cat canonical-hook-body)\n"
        "for hook in pre-commit pre-push commit-msg; do\n"
        "    printf '#!/bin/sh\\n# canonical: %s\\n' \"$body\" > .git/hooks/$hook\n"
        "    chmod 755 .git/hooks/$hook\n"
        "done\n",
        encoding="utf-8",
    )
    installer.chmod(installer.stat().st_mode | stat.S_IXUSR)
    _ = subprocess.run([str(installer)], cwd=run, check=True, capture_output=True, text=True)
    suite = _suite(
        root=tmp_path,
        body=(
            "body=$(cat canonical-hook-body)\n"
            "for hook in pre-commit pre-push commit-msg; do\n"
            '    grep -qxF "# canonical: $body" .git/hooks/$hook || exit 1\n'
            "done"
        ),
    )

    janitor = _run(
        node="janitor",
        cwd=run,
        plugins=plugins,
        check_suite=str(suite),
        conformance_hook_install=shlex.quote(str(installer)),
    )

    assert janitor.returncode == 0, janitor.stderr
    assert trace.read_text(encoding="utf-8") == "install\ninstall\n"
    for hook in ("pre-commit", "pre-push", "commit-msg"):
        assert "# canonical: new canonical hook body" in (run / ".git" / "hooks" / hook).read_text(
            encoding="utf-8"
        )


def test_scenario305_refresh_repair_restores_the_pre_refresh_hook_body(*, tmp_path: Path) -> None:
    """A red refreshed suite leaves hooks matching the head fix receives."""
    run, default = _world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    before = _git("rev-parse", "HEAD", cwd=run).stdout.strip()
    _ = _commit(
        cwd=default,
        path="canonical-hook-body",
        text="new canonical hook body\n",
        subject="chore: update canonical hook body",
    )
    _ = _git("push", "origin", _DEFAULT_BRANCH, cwd=default)
    trace = tmp_path / "conformance-hook-installs"
    installer = tmp_path / "install-conformance-hooks"
    installer.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' install >> {shlex.quote(str(trace))}\n"
        "body=$(cat canonical-hook-body)\n"
        "for hook in pre-commit pre-push commit-msg; do\n"
        "    printf '#!/bin/sh\\n# canonical: %s\\n' \"$body\" > .git/hooks/$hook\n"
        "    chmod 755 .git/hooks/$hook\n"
        "done\n",
        encoding="utf-8",
    )
    installer.chmod(installer.stat().st_mode | stat.S_IXUSR)
    _ = subprocess.run([str(installer)], cwd=run, check=True, capture_output=True, text=True)
    suite = _suite(
        root=tmp_path,
        body=(
            "body=$(cat canonical-hook-body)\n"
            "for hook in pre-commit pre-push commit-msg; do\n"
            '    grep -qxF "# canonical: $body" .git/hooks/$hook || exit 1\n'
            "done\n"
            "exit 23"
        ),
    )

    janitor = _run(
        node="janitor",
        cwd=run,
        plugins=plugins,
        check_suite=str(suite),
        conformance_hook_install=shlex.quote(str(installer)),
    )

    assert janitor.returncode == 23, janitor.stderr
    assert _git("rev-parse", "HEAD", cwd=run).stdout.strip() == before
    assert trace.read_text(encoding="utf-8") == "install\ninstall\ninstall\n"
    for hook in ("pre-commit", "pre-push", "commit-msg"):
        assert "# canonical: old canonical hook body" in (run / ".git" / "hooks" / hook).read_text(
            encoding="utf-8"
        )


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

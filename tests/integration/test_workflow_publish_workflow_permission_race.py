"""A default branch that moves its workflow files mid-publication loses no run.

Binds work-item ``bd-ib-cvge``.  GitHub refuses a GitHub App push whose branch
carries workflow files that differ from the default branch's CURRENT tip, and
this fleet's default branches edit workflow files several times a day (every
dev-tooling pin bump).  ``publish_draft`` refreshes its base before pushing,
but the pre-push hook runs between that refresh and the forge's comparison, so
a bump landing inside that window still refuses a run that changed no workflow
file.  The same refusal used to sink the ``needs_human`` preservation push,
leaving the fabro dump as the only copy of verified work.

Every case executes the committed node scripts against a real bare origin
whose ``pre-receive`` hook reproduces the forge's comparison; ``gh`` is the
only other doubled boundary.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_merge import (
    RECORD_FILE_MERGE_PROGRAM_FILENAME,
    record_file_merge_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)

_WORKFLOW = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
_PUBLISH_BRANCH = "feat/bd-ib-cvge"
_RUN_ID = "01WORKFLOWRACE"
_CI = ".github/workflows/ci.yml"
_RECORD_JSON = "record.json"
_DECLARATION = """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "record_files": [
        {"path": "record.json", "format": "json-array", "key": ["id"]}
      ]
    }
  }
}
"""
_SCRIPT = re.compile(r'script="(?P<value>(?:[^"\\]|\\.)*)"')
_FORGE_REFUSAL = "refusing to allow a GitHub App to create or update workflow"


def _git(cwd: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv],
        cwd=str(cwd),
        check=True,
        text=True,
        capture_output=True,
    )


def _node_script(*, node: str, check_suite: str = "true") -> str:
    text = _WORKFLOW.read_text(encoding="utf-8")
    block = re.search(
        rf"^\s*{node}\s*\[(?P<body>.*?)^\s*\]",
        text,
        re.DOTALL | re.MULTILINE,
    )
    assert block is not None
    attr = _SCRIPT.search(block.group("body"))
    assert attr is not None
    return (
        re.sub(r"\\(?P<escaped>.)", r"\g<escaped>", attr.group("value"))
        .replace("{{ inputs.default_branch }}", "master")
        .replace("{{ inputs.sandbox_check_suite }}", check_suite)
    )


def _configure(*, repo: Path) -> None:
    _git(repo, "config", "user.name", "workflow-race-test")
    _git(repo, "config", "user.email", "workflow-race-test@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")


def _commit(*, repo: Path, path: str, content: str, message: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _executable(*, path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _forge(*, tmp_path: Path) -> Path:
    """A bare origin refusing any branch whose workflow files differ from master."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "master", str(origin))
    _executable(
        path=origin / "hooks" / "pre-receive",
        body=(
            "#!/bin/sh\n"
            "while read -r old_revision new_revision ref; do\n"
            '    if test "$ref" = refs/heads/master; then continue; fi\n'
            '    files=$(git diff --name-only refs/heads/master "$new_revision"'
            " -- .github/workflows)\n"
            '    if test -n "$files"; then\n'
            f'        echo "{_FORGE_REFUSAL} $files without workflows permission" >&2\n'
            "        exit 1\n"
            "    fi\n"
            "done\n"
            "exit 0\n"
        ),
    )
    return origin


def _run_behind_master(*, tmp_path: Path) -> tuple[Path, Path, Path]:
    """A run with ordinary work whose base master later advances a workflow file."""
    origin = _forge(tmp_path=tmp_path)
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "master")
    _configure(repo=seed)
    _commit(
        repo=seed,
        path=".livespec.jsonc",
        content=_DECLARATION,
        message="declare shared records",
    )
    _commit(
        repo=seed,
        path=_RECORD_JSON,
        content='[{"id": "seed"}]\n',
        message="seed record",
    )
    _commit(repo=seed, path=_CI, content="pin: v1\n", message="initial workflow")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-u", "origin", "master")

    run = tmp_path / "run"
    _git(tmp_path, "clone", str(origin), str(run))
    _configure(repo=run)
    _git(run, "config", "core.hooksPath", str(tmp_path / "run-hooks"))
    (tmp_path / "run-hooks").mkdir()
    _git(run, "switch", "-c", "fabro/run/workflow-race")
    _commit(repo=run, path="src/work.txt", content="verified work\n", message="run work")

    default = tmp_path / "default"
    _git(tmp_path, "clone", str(origin), str(default))
    _configure(repo=default)
    return run, origin, default


def _refuse_every_branch(*, origin: Path) -> None:
    """A forge whose default branch never settles: every non-master ref is refused."""
    _executable(
        path=origin / "hooks" / "pre-receive",
        body=(
            "#!/bin/sh\n"
            "while read -r _old_revision _new_revision ref; do\n"
            '    if test "$ref" = refs/heads/master; then continue; fi\n'
            f'    echo "{_FORGE_REFUSAL} {_CI} without workflows permission" >&2\n'
            "    exit 1\n"
            "done\n"
            "exit 0\n"
        ),
    )


def _bump(*, default: Path, pin: str) -> str:
    _git(default, "pull", "--quiet", "--rebase", "origin", "master")
    sha = _commit(repo=default, path=_CI, content=f"pin: {pin}\n", message=f"bump {pin}")
    _git(default, "push", "--quiet", "origin", "master")
    return sha


def _bump_during_push(
    *, tmp_path: Path, default: Path, times: int, record_content: str | None = None
) -> None:
    """A pre-push hook that lands a pin bump while the push is in flight."""
    counter = tmp_path / "bumps"
    counter.write_text("0\n", encoding="utf-8")
    record_write = ""
    paths_to_add = _CI
    if record_content is not None:
        record_write = (
            f"    printf '%s\\n' '{record_content.rstrip()}' > \"{default / _RECORD_JSON}\"\n"
        )
        paths_to_add = f"{_CI} {_RECORD_JSON}"
    _executable(
        path=tmp_path / "run-hooks" / "pre-push",
        body=(
            "#!/bin/sh\n"
            f'count=$(cat "{counter}")\n'
            f'if test "$count" -lt {times}; then\n'
            "    count=$((count + 1))\n"
            f'    printf "%s\\n" "$count" > "{counter}"\n'
            f'    cd "{default}" || exit 1\n'
            "    unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE\n"
            "    git pull --quiet --rebase origin master >/dev/null 2>&1 || exit 1\n"
            f'    printf "pin: race-%s\\n" "$count" > "{default / _CI}"\n'
            + record_write
            + f"    git add {paths_to_add} && git commit --quiet -m race >/dev/null 2>&1 || exit 1\n"
            "    git push --quiet origin master >/dev/null 2>&1 || exit 1\n"
            "fi\n"
            "exit 0\n"
        ),
    )


def _env(*, tmp_path: Path, plugins_root: Path | None = None) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    _executable(
        path=bin_dir / "gh",
        body=(
            "#!/bin/sh\n"
            'if test "$1 $2" = "pr create"; then : > "$GH_DRAFT_CREATED"; fi\n'
            "exit 0\n"
        ),
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE")
    }
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
            "GH_DRAFT_CREATED": str(tmp_path / "draft-created"),
            "LIVESPEC_GIT_AUTHOR_NAME": "Workflow Race Test",
            "LIVESPEC_GIT_AUTHOR_EMAIL": "workflow-race-test@example.invalid",
            "LIVESPEC_PUBLISH_BRANCH": _PUBLISH_BRANCH,
            "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(tmp_path / "no-push-helper"),
        }
    )
    if plugins_root is not None:
        env[SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR] = str(plugins_root)
    return env


def _record_merge_plugins(*, tmp_path: Path) -> Path:
    """Materialize the production resolver where the shipped stage looks for it."""
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    program = plugins_root / RECORD_FILE_MERGE_PROGRAM_FILENAME
    program.write_text(record_file_merge_program_source(), encoding="utf-8")
    program.chmod(0o700)
    return plugins_root


def _recording_gate(*, tmp_path: Path, exit_status: int) -> tuple[str, Path]:
    """A declared gate whose marker proves `publish_draft` reached the call."""
    record = tmp_path / "declared-gate-ran"
    program = tmp_path / "declared-gate"
    _executable(
        path=program,
        body=("#!/bin/sh\n" f"printf 'ran\\n' > \"{record}\"\n" f"exit {exit_status}\n"),
    )
    return f'"{program}"', record


def _node(
    *, node: str, run: Path, env: dict[str, str], stdin: str = "", check_suite: str = "true"
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", _node_script(node=node, check_suite=check_suite)],
        cwd=str(run),
        env=env,
        text=True,
        capture_output=True,
        input=stdin,
        check=False,
    )


def _plan(*, repo: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=repo,
        work_item_id="bd-ib-cvge",
        branch=_PUBLISH_BRANCH,
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server=None,
        fabro_factory_dev_token=None,
        janitor=("just", "check"),
        janitor_checkout=repo / ".janitor",
        janitor_core_checkout=repo / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _remote_tip(*, repo: Path, ref: str) -> str:
    line = _git(repo, "ls-remote", "origin", ref).stdout
    return line.split()[0] if line else ""


def test_publish_draft_refreshes_again_when_master_moves_a_workflow_mid_push(
    tmp_path: Path,
) -> None:
    run, _, default = _run_behind_master(tmp_path=tmp_path)
    _bump_during_push(tmp_path=tmp_path, default=default, times=1)
    env = _env(tmp_path=tmp_path)

    published = _node(node="publish_draft", run=run, env=env)

    assert published.returncode == 0, published.stderr
    assert _FORGE_REFUSAL in published.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_WORKFLOW_RACE" in published.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_FAILED" not in published.stderr
    _git(run, "fetch", "origin", "master")
    head = _git(run, "rev-parse", "HEAD").stdout.strip()
    assert _remote_tip(repo=run, ref=f"refs/heads/{_PUBLISH_BRANCH}") == head
    master = _git(run, "rev-parse", "origin/master").stdout.strip()
    assert _git(run, "merge-base", "HEAD", "origin/master").stdout.strip() == master
    assert (run / _CI).read_text(encoding="utf-8") == "pin: race-1\n"
    assert (tmp_path / "draft-created").exists()


def test_publish_draft_retry_merges_a_declared_record_conflict_after_a_workflow_race(
    tmp_path: Path,
) -> None:
    """The workflow-race retry takes the same declared-record arm as first refreshes.

    The initial refresh is deliberately conflict-free.  The pre-push hook then
    advances both a workflow and the declared JSON record, so the forge refuses
    the first push for its workflow comparison and ONLY the retry sees the
    record conflict.  That separates the retry from the ordinary refresh arm:
    a resolver that is present only before the first push leaves this case in a
    stopped rebase instead of publishing the merged head.
    """
    run, _, default = _run_behind_master(tmp_path=tmp_path)
    _commit(
        repo=run,
        path=_RECORD_JSON,
        content='[{"id": "seed"}, {"id": "run"}]\n',
        message="add run record",
    )
    _bump(default=default, pin="v2")
    _bump_during_push(
        tmp_path=tmp_path,
        default=default,
        times=1,
        record_content='[{"id": "seed"}, {"id": "default"}]',
    )

    published = _node(
        node="publish_draft",
        run=run,
        env=_env(tmp_path=tmp_path, plugins_root=_record_merge_plugins(tmp_path=tmp_path)),
    )

    assert published.returncode == 0, published.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_WORKFLOW_RACE" in published.stderr
    assert "LIVESPEC_RECORD_FILE_REFRESH_RESOLVED: publish_draft" in published.stderr
    assert "LIVESPEC_REFRESH_REPAIR" not in published.stderr
    assert (run / _RECORD_JSON).read_text(encoding="utf-8") == (
        '[\n  {\n    "id": "seed"\n  },\n  {\n    "id": "default"\n  },\n'
        '  {\n    "id": "run"\n  }\n]\n'
    )
    assert (
        _remote_tip(repo=run, ref=f"refs/heads/{_PUBLISH_BRANCH}")
        == _git(run, "rev-parse", "HEAD").stdout.strip()
    )


def test_publish_draft_gates_a_merged_declared_record_before_republishing(
    tmp_path: Path,
) -> None:
    """A failed declared gate returns the post-merge head to refresh repair."""
    run, _, default = _run_behind_master(tmp_path=tmp_path)
    _commit(
        repo=run,
        path=_RECORD_JSON,
        content='[{"id": "seed"}, {"id": "run"}]\n',
        message="add run record",
    )
    _bump(default=default, pin="v2")
    _bump_during_push(
        tmp_path=tmp_path,
        default=default,
        times=1,
        record_content='[{"id": "seed"}, {"id": "default"}]',
    )
    gate, gate_record = _recording_gate(tmp_path=tmp_path, exit_status=1)

    published = _node(
        node="publish_draft",
        run=run,
        env=_env(tmp_path=tmp_path, plugins_root=_record_merge_plugins(tmp_path=tmp_path)),
        check_suite=gate,
    )

    assert published.returncode == 1, published.stderr
    assert gate_record.read_text(encoding="utf-8") == "ran\n"
    assert "LIVESPEC_PUBLISH_DRAFT_GATE_REJECTED" in published.stderr
    assert "LIVESPEC_REFRESH_REPAIR" in published.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_PUBLISHED" not in published.stderr


def test_publish_draft_names_the_workflow_race_when_master_never_settles(
    tmp_path: Path,
) -> None:
    run, origin, default = _run_behind_master(tmp_path=tmp_path)
    _bump_during_push(tmp_path=tmp_path, default=default, times=99)
    env = _env(tmp_path=tmp_path)

    published = _node(node="publish_draft", run=run, env=env)

    assert published.returncode != 0
    assert "LIVESPEC_PUBLISH_DRAFT_WORKFLOW_PERMISSION" in published.stderr
    assert "did not change" in published.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_FAILED" not in published.stderr
    assert "non-fast-forward" not in published.stderr
    assert _remote_tip(repo=run, ref=f"refs/heads/{_PUBLISH_BRANCH}") == ""
    assert not (tmp_path / "draft-created").exists()
    reason = Path(
        run, _git(run, "rev-parse", "--git-path", "livespec-needs-human-reason").stdout.strip()
    ).read_text(encoding="utf-8")
    assert "workflows permission" in reason
    assert "did not change" in reason

    # The terminal's preservation pushes deliberately no longer run the
    # repository's pre-push hook (work-item bd-ib-3vn3mu), so the
    # bump-during-push mechanism above cannot reach them — master simply stops
    # moving while the node pushes, and both of its attempts would be accepted.
    # The forge double therefore carries the never-settling condition AS THE NODE
    # EXPERIENCES IT, refusing every non-master ref for workflows permission,
    # which is the condition this leg has always measured. `publish_draft`'s half
    # above is untouched and still drives the real mid-push bump through its own
    # hook, which is why it stays the leg that proves the race is reachable.
    _refuse_every_branch(origin=origin)

    terminal = _node(node="needs_human", run=run, env=env, stdin=f"{_RUN_ID}\n")

    assert "LIVESPEC_NEEDS_HUMAN_WORKFLOWS_RESET" in terminal.stderr
    assert "LIVESPEC_NEEDS_HUMAN_PUSH_FAILED" in terminal.stderr
    assert _remote_tip(repo=run, ref=f"refs/heads/needs-human/{_RUN_ID}") == ""
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=run),
        run_id=_RUN_ID,
        inspect=None,
        exit_code=1,
        stderr=f"{published.stderr}\n{terminal.stderr}",
    )
    assert outcome is not None
    assert outcome.status == "blocked"
    assert "did not change" in outcome.detail
    assert "tree was not pushed" in outcome.detail


def test_needs_human_preserves_a_tree_whose_base_master_has_since_bumped(
    tmp_path: Path,
) -> None:
    run, origin, default = _run_behind_master(tmp_path=tmp_path)
    _bump(default=default, pin="v2")
    env = _env(tmp_path=tmp_path)

    terminal = _node(node="needs_human", run=run, env=env, stdin=f"{_RUN_ID}\n")

    assert terminal.returncode != 0
    ref = f"refs/heads/needs-human/{_RUN_ID}"
    assert f"LIVESPEC_NEEDS_HUMAN_PRESERVED: {ref}" in terminal.stderr
    assert "LIVESPEC_NEEDS_HUMAN_WORKFLOWS_RESET" in terminal.stderr
    assert "LIVESPEC_NEEDS_HUMAN_PUSH_FAILED" not in terminal.stderr
    preserved = _remote_tip(repo=run, ref=ref)
    assert preserved
    assert _git(origin, "show", f"{preserved}:src/work.txt").stdout == "verified work\n"
    assert _git(origin, "show", f"{preserved}:{_CI}").stdout == "pin: v2\n"
    assert _git(origin, "show", f"{preserved}~1:src/work.txt").stdout == "verified work\n"


def test_needs_human_preserves_without_a_reset_when_the_forge_accepts(
    tmp_path: Path,
) -> None:
    run, origin, _ = _run_behind_master(tmp_path=tmp_path)
    env = _env(tmp_path=tmp_path)

    terminal = _node(node="needs_human", run=run, env=env, stdin=f"{_RUN_ID}\n")

    ref = f"refs/heads/needs-human/{_RUN_ID}"
    assert f"LIVESPEC_NEEDS_HUMAN_PRESERVED: {ref}" in terminal.stderr
    assert "LIVESPEC_NEEDS_HUMAN_WORKFLOWS_RESET" not in terminal.stderr
    assert _remote_tip(repo=run, ref=ref) == _git(run, "rev-parse", "HEAD").stdout.strip()
    assert _git(origin, "show", f"{_remote_tip(repo=run, ref=ref)}:{_CI}").stdout == "pin: v1\n"

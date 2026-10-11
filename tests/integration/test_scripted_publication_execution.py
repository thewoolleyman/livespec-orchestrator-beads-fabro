"""Execute the rendered publication commands against controlled boundaries.

The text-level contract tests keep the recipes legible.  These tests hand the
same graph to the production renderer and parser, then execute the resulting
script bytes.  Git uses a local bare remote; only the forge process is replaced.
"""

from __future__ import annotations

import fcntl
import json
import os
import shlex
import stat
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    render_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    plugin_cache_gate_script,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_head import (
    PROOF_HEAD_PROGRAM_FILENAME,
    proof_head_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    PUBLICATION_PUSH_PROGRAM_FILENAME,
    publication_push_program_source,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import default_node_timeouts

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_BRANCH = "feat/bd-ib-c3txja"


@dataclass(frozen=True, kw_only=True)
class _RefreshRepository:
    work: Path
    actor: Path
    remote: Path
    published: str


def _run(
    *, argv: list[str], cwd: Path, env: dict[str, str] | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        raise AssertionError(
            f"command failed ({completed.returncode}): {argv!r}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def _git(*, repo: Path, argv: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(argv=["git", *argv], cwd=repo, check=check)


def test_command_runner_reports_a_failed_boundary(tmp_path: Path) -> None:
    """A failed controlled command carries its argv and exit status to the test."""
    with pytest.raises(AssertionError, match=r"command failed \(17\).+exit 17"):
        _run(argv=["sh", "-c", "exit 17"], cwd=tmp_path)


def _write(*, path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(*, repo: Path, path: str, text: str, message: str) -> str:
    _write(path=repo / path, text=text)
    _git(repo=repo, argv=["add", path])
    _git(repo=repo, argv=["commit", "-m", message])
    return _git(repo=repo, argv=["rev-parse", "HEAD"]).stdout.strip()


def _clone(*, remote: Path, destination: Path) -> None:
    _run(
        argv=["git", "clone", str(remote), str(destination)],
        cwd=destination.parent,
    )
    _git(repo=destination, argv=["config", "user.name", "Publication Test"])
    _git(repo=destination, argv=["config", "user.email", "publication@example.com"])


def _refresh_repository(*, root: Path, conflict: bool = False) -> _RefreshRepository:
    root.mkdir(parents=True)
    remote = root / "remote.git"
    seed = root / "seed"
    work = root / "work"
    actor = root / "actor"
    _run(argv=["git", "init", "--bare", str(remote)], cwd=root)
    _run(argv=["git", "init", "-b", "master", str(seed)], cwd=root)
    _git(repo=seed, argv=["config", "user.name", "Publication Test"])
    _git(repo=seed, argv=["config", "user.email", "publication@example.com"])
    _commit(repo=seed, path="shared.txt", text="base\n", message="base")
    _git(repo=seed, argv=["remote", "add", "origin", str(remote)])
    _git(repo=seed, argv=["push", "-u", "origin", "master"])
    _git(repo=seed, argv=["switch", "-c", _BRANCH])
    published = _commit(
        repo=seed,
        path="shared.txt" if conflict else "feature.txt",
        text="feature\n",
        message="feature",
    )
    _git(repo=seed, argv=["push", "-u", "origin", _BRANCH])
    _clone(remote=remote, destination=work)
    _git(repo=work, argv=["switch", _BRANCH])
    _clone(remote=remote, destination=actor)
    _git(repo=seed, argv=["switch", "master"])
    _commit(
        repo=seed,
        path="shared.txt" if conflict else "default.txt",
        text="default\n" if conflict else "advanced\n",
        message="advance default",
    )
    _git(repo=seed, argv=["push", "origin", "master"])
    return _RefreshRepository(work=work, actor=actor, remote=remote, published=published)


def _workflow_graph() -> DotGraph:
    rendered = render_workflow_graph(
        committed_text=_GRAPH.read_text(encoding="utf-8"),
        timeouts=default_node_timeouts(),
    )
    assert not isinstance(rendered, str), rendered
    parsed = parse_dot_graph(text=rendered.text)
    assert not isinstance(parsed, str), parsed
    return parsed


def _script(*, node: str, replacements: dict[str, str]) -> str:
    raw = _workflow_graph().nodes[node]["script"]
    for token, value in replacements.items():
        raw = raw.replace(token, value)
    assert "{{ inputs." not in raw
    return raw


def _remote_head(*, remote: Path, branch: str) -> str:
    return _run(
        argv=["git", "ls-remote", "--heads", str(remote), f"refs/heads/{branch}"],
        cwd=remote.parent,
    ).stdout.split()[0]


def _refresh_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    } | {"LIVESPEC_PUBLISH_BRANCH": _BRANCH}


def _state_files() -> tuple[Path, ...]:
    return (
        Path("/tmp/livespec-publish-head"),
        Path("/tmp/livespec-pr-refresh-count"),
        Path("/tmp/livespec-pr-refresh-changed"),
    )


@contextmanager
def _publication_state() -> Iterator[tuple[Path, ...]]:
    """Serialize controls and restore production state exactly after each one."""
    lock_path = Path("/tmp/livespec-publication-execution-test.lock")
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state_files = _state_files()
        backup_root = Path(tempfile.mkdtemp(prefix="livespec-publication-state-", dir="/tmp"))
        backups: dict[Path, Path] = {}
        for index, path in enumerate(state_files):
            if path.exists() or path.is_symlink():
                backup = backup_root / str(index)
                path.replace(backup)
                backups[path] = backup
        try:
            yield state_files
        finally:
            for path in state_files:
                path.unlink(missing_ok=True)
                backup = backups.get(path)
                if backup is not None:
                    backup.replace(path)
            backup_root.rmdir()
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _gate(*, path: Path, body: str) -> Path:
    _write(path=path, text=f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _refresh_script(*, gate: Path) -> str:
    return _script(
        node="pr_refresh",
        replacements={
            "{{ inputs.default_branch }}": "master",
            "{{ inputs.sandbox_check_suite }}": shlex.quote(str(gate)),
        },
    )


def _execute_refresh(
    *, repository: _RefreshRepository, gate: Path
) -> subprocess.CompletedProcess[str]:
    plugins = repository.work / ".publication-plugins"
    push = plugins / PUBLICATION_PUSH_PROGRAM_FILENAME
    _write(path=push, text=publication_push_program_source())
    push.chmod(push.stat().st_mode | stat.S_IXUSR)
    env = _refresh_env() | {"LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins)}
    _run(
        argv=["bash", "-c", plugin_cache_gate_script()],
        cwd=repository.work,
        env=env,
    )
    return _run(
        argv=["bash", "-c", _refresh_script(gate=gate)],
        cwd=repository.work,
        env=env,
        check=False,
    )


def _record_published(*, head: str) -> None:
    _state_files()[0].write_text(head + "\n", encoding="utf-8")


def _assert_success_and_unchanged(*, tmp_path: Path, state_files: tuple[Path, ...]) -> Path:
    repository = _refresh_repository(root=tmp_path / "success")
    _record_published(head=repository.published)
    gate_log = tmp_path / "gate-head"
    gate = _gate(
        path=tmp_path / "gate.sh",
        body=f"git rev-parse HEAD > {shlex.quote(str(gate_log))}",
    )
    hook_log = tmp_path / "pre-push-ran"
    hook = repository.work / ".git" / "hooks" / "pre-push"
    _write(path=hook, text=f"#!/bin/sh\n: > {shlex.quote(str(hook_log))}\n")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    completed = _execute_refresh(repository=repository, gate=gate)
    assert completed.returncode == 0, completed.stderr
    refreshed = _git(repo=repository.work, argv=["rev-parse", "HEAD"]).stdout.strip()
    assert refreshed != repository.published
    assert _remote_head(remote=repository.remote, branch=_BRANCH) == refreshed
    assert gate_log.read_text(encoding="utf-8").strip() == refreshed
    assert hook_log.is_file()
    assert state_files[2].is_file()
    base = _remote_head(remote=repository.remote, branch="master")
    assert (
        _git(
            repo=repository.work,
            argv=["merge-base", "--is-ancestor", base, refreshed],
            check=False,
        ).returncode
        == 0
    )
    gate_log.unlink()
    hook_log.unlink()
    unchanged = _execute_refresh(repository=repository, gate=gate)
    assert unchanged.returncode == 0
    assert "LIVESPEC_PR_REFRESH_UNCHANGED" in unchanged.stderr
    assert _remote_head(remote=repository.remote, branch=_BRANCH) == refreshed
    assert not gate_log.exists() and not hook_log.exists() and not state_files[2].exists()
    return gate


def _assert_provenance_gate_and_conflict_refusals(*, tmp_path: Path, gate: Path) -> None:
    foreign = _refresh_repository(root=tmp_path / "foreign")
    _record_published(head="0" * 40)
    foreign_result = _execute_refresh(repository=foreign, gate=gate)
    assert foreign_result.returncode != 0
    assert "LIVESPEC_PR_REFRESH_FOREIGN_HEAD" in foreign_result.stderr
    assert _remote_head(remote=foreign.remote, branch=_BRANCH) == foreign.published
    failed_gate = _refresh_repository(root=tmp_path / "failed-gate")
    _record_published(head=failed_gate.published)
    rejecting_gate = _gate(path=tmp_path / "reject.sh", body="exit 17")
    gate_result = _execute_refresh(repository=failed_gate, gate=rejecting_gate)
    assert gate_result.returncode != 0
    assert "LIVESPEC_PR_REFRESH_GATE_FAILED" in gate_result.stderr
    assert _remote_head(remote=failed_gate.remote, branch=_BRANCH) == failed_gate.published
    conflicted = _refresh_repository(root=tmp_path / "conflict", conflict=True)
    _record_published(head=conflicted.published)
    conflict_result = _execute_refresh(repository=conflicted, gate=gate)
    assert conflict_result.returncode != 0
    assert "LIVESPEC_PR_REFRESH_CONFLICT" in conflict_result.stderr
    assert _remote_head(remote=conflicted.remote, branch=_BRANCH) == conflicted.published
    assert _git(repo=conflicted.work, argv=["rev-parse", "HEAD"]).stdout.strip() == (
        conflicted.published
    )


def _assert_cap_and_lease_refusals(
    *, tmp_path: Path, gate: Path, state_files: tuple[Path, ...]
) -> None:
    capped = _refresh_repository(root=tmp_path / "capped")
    _record_published(head=capped.published)
    state_files[1].write_text("3\n", encoding="utf-8")
    cap_result = _execute_refresh(repository=capped, gate=gate)
    assert cap_result.returncode != 0
    assert "LIVESPEC_PR_REFRESH_NON_CONVERGED" in cap_result.stderr
    assert _remote_head(remote=capped.remote, branch=_BRANCH) == capped.published
    state_files[1].unlink()
    raced = _refresh_repository(root=tmp_path / "lease-race")
    _record_published(head=raced.published)
    racing_gate = _gate(
        path=tmp_path / "race.sh",
        body="\n".join(
            (
                f"git -C {shlex.quote(str(raced.actor))} fetch origin {_BRANCH}",
                f"git -C {shlex.quote(str(raced.actor))} switch -C race FETCH_HEAD",
                f"printf 'race\\n' > {shlex.quote(str(raced.actor / 'race.txt'))}",
                f"git -C {shlex.quote(str(raced.actor))} add race.txt",
                f"git -C {shlex.quote(str(raced.actor))} commit -m race",
                f"git -C {shlex.quote(str(raced.actor))} push origin HEAD:refs/heads/{_BRANCH}",
            )
        ),
    )
    race_result = _execute_refresh(repository=raced, gate=racing_gate)
    assert race_result.returncode != 0
    assert "LIVESPEC_PR_REFRESH_LEASE_FAILED" in race_result.stderr
    assert _remote_head(remote=raced.remote, branch=_BRANCH) != raced.published


def test_refresh_executes_success_and_fail_closed_paths(tmp_path: Path) -> None:
    """Real Git covers changed/unchanged, provenance, gate, conflict, cap and lease."""
    with _publication_state() as state_files:
        gate = _assert_success_and_unchanged(tmp_path=tmp_path, state_files=state_files)
        _assert_provenance_gate_and_conflict_refusals(tmp_path=tmp_path, gate=gate)
        _assert_cap_and_lease_refusals(
            tmp_path=tmp_path,
            gate=gate,
            state_files=state_files,
        )


def _forge_stub(*, directory: Path) -> Path:
    stub = directory / "gh"
    _write(
        path=stub,
        text="""#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["LIVESPEC_GH_LOG"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(args) + "\\n")
state = os.environ["LIVESPEC_GH_STATE"]
head = os.environ["LIVESPEC_GH_HEAD"]
number = os.environ.get("LIVESPEC_GH_NUMBER", "17")
if args[:2] == ["pr", "list"]:
    requested = args[args.index("--state") + 1]
    if requested == "all" or state == "OPEN":
        print(number)
elif args[:2] == ["pr", "view"]:
    field = args[args.index("--json") + 1]
    if field == "state":
        print(state)
    elif field == "headRefOid":
        print(head)
    elif field == "mergeCommit":
        print(os.environ.get("LIVESPEC_GH_MERGE_SHA", "f" * 40))
    elif field == "isDraft":
        print(os.environ.get("LIVESPEC_GH_DRAFT", "false"))
    elif field == "autoMergeRequest":
        print(os.environ.get("LIVESPEC_GH_AUTO_MERGE", "null"))
    elif field == "comments":
        record = "Publish-branch head: " + head
        print(json.dumps({"comments": [
            {"body": "Proof of Done — captured — run capture\\n\\n" + record},
            {"body": "Proof of Done — verified — run replay\\n\\n" + record},
        ]}))
elif args[:2] == ["pr", "merge"]:
    raise SystemExit(int(os.environ.get("LIVESPEC_GH_MERGE_EXIT", "0")))
raise SystemExit(0)
""",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return stub


def _pr_environment(
    *, tmp_path: Path, stub: Path, log: Path, head: str, state: str, draft: bool
) -> dict[str, str]:
    plugins = tmp_path / "plugins"
    plugins.mkdir(exist_ok=True)
    _write(
        path=plugins / PROOF_HEAD_PROGRAM_FILENAME,
        text=proof_head_program_source(),
    )
    body = tmp_path / "body.md"
    _write(path=body, text="Body with `code` and $(touch never-runs)\n")
    return _refresh_env() | {
        "PATH": f"{stub.parent}{os.pathsep}{os.environ['PATH']}",
        "LIVESPEC_GH_LOG": str(log),
        "LIVESPEC_GH_STATE": state,
        "LIVESPEC_GH_HEAD": head,
        "LIVESPEC_GH_DRAFT": str(draft).lower(),
        "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins),
        "LIVESPEC_PR_TITLE": "Title 'quoted' $(touch title-never-runs)",
        "LIVESPEC_PR_BODY_FILE": str(body),
    }


def _execute_pr(
    *, tmp_path: Path, env: dict[str, str], merge_hold: bool
) -> subprocess.CompletedProcess[str]:
    return _run(
        argv=[
            "bash",
            "-c",
            _script(
                node="pr",
                replacements={
                    "{{ inputs.merge_mode }}": "rebase",
                    "{{ inputs.merge_hold }}": str(merge_hold).lower(),
                },
            ),
        ],
        cwd=tmp_path,
        env=env,
        check=False,
    )


def _logged_commands(*, log: Path) -> list[list[str]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _assert_ready_and_draft(*, tmp_path: Path, env: dict[str, str], log: Path) -> None:
    ready = _execute_pr(tmp_path=tmp_path, env=env, merge_hold=False)
    assert ready.returncode == 0, ready.stderr
    assert f"PR_NUMBER={env.get('LIVESPEC_GH_NUMBER', '17')}" in ready.stdout
    assert "LIVESPEC_PR_ALREADY_READY" in ready.stderr
    commands = _logged_commands(log=log)
    assert ["pr", "ready", "17"] not in commands
    assert ["pr", "merge", "--rebase", "--auto", "--delete-branch", "17"] in commands
    edit = next(command for command in commands if command[:2] == ["pr", "edit"])
    assert edit == [
        "pr",
        "edit",
        "17",
        "--title",
        env["LIVESPEC_PR_TITLE"],
        "--body-file",
        env["LIVESPEC_PR_BODY_FILE"],
    ]
    assert not (tmp_path / "title-never-runs").exists()
    assert not (tmp_path / "never-runs").exists()
    log.unlink()
    draft_env = env | {"LIVESPEC_GH_DRAFT": "true"}
    draft = _execute_pr(tmp_path=tmp_path, env=draft_env, merge_hold=False)
    assert draft.returncode == 0, draft.stderr
    assert ["pr", "ready", "17"] in _logged_commands(log=log)


def _assert_hold(*, tmp_path: Path, env: dict[str, str], log: Path) -> None:
    log.unlink()
    held = _execute_pr(
        tmp_path=tmp_path,
        env=env | {"LIVESPEC_GH_DRAFT": "true"},
        merge_hold=True,
    )
    assert held.returncode == 0, held.stderr
    assert "PR_NUMBER=17" in held.stdout
    assert "MERGE_HOLD=held" in held.stdout
    held_commands = _logged_commands(log=log)
    assert not any(command[:2] == ["pr", "merge"] for command in held_commands)
    assert any("autoMergeRequest" in command for command in held_commands)


def _assert_terminal_states(*, tmp_path: Path, env: dict[str, str], log: Path) -> None:
    forbidden = (["pr", "edit"], ["pr", "ready"], ["pr", "merge"])
    log.unlink()
    merged = _execute_pr(
        tmp_path=tmp_path,
        env=env | {"LIVESPEC_GH_STATE": "MERGED"},
        merge_hold=False,
    )
    assert merged.returncode == 0, merged.stderr
    assert "PR_NUMBER=17" in merged.stdout
    assert f"MERGE_LANDED={'f' * 40}" in merged.stdout
    assert not any(command[:2] in forbidden for command in _logged_commands(log=log))
    log.unlink()
    closed = _execute_pr(
        tmp_path=tmp_path,
        env=env | {"LIVESPEC_GH_STATE": "CLOSED"},
        merge_hold=False,
    )
    assert closed.returncode != 0
    assert "LIVESPEC_PR_CLOSED_UNMERGED" in closed.stderr
    assert not any(command[:2] in forbidden for command in _logged_commands(log=log))


def test_finalizer_executes_draft_ready_merged_closed_and_hold_paths(tmp_path: Path) -> None:
    """The actual command is idempotent, proof-bound, held, and injection-safe."""
    with _publication_state():
        head = "a" * 40
        _record_published(head=head)
        stub = _forge_stub(directory=tmp_path)
        log = tmp_path / "gh.log"
        env = _pr_environment(
            tmp_path=tmp_path,
            stub=stub,
            log=log,
            head=head,
            state="OPEN",
            draft=False,
        )
        _assert_ready_and_draft(tmp_path=tmp_path, env=env, log=log)
        _assert_hold(tmp_path=tmp_path, env=env, log=log)
        _assert_terminal_states(tmp_path=tmp_path, env=env, log=log)

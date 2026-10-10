"""Draft publication refreshes its base without claiming workflow ownership.

Binds work-item ``bd-ib-qustjx``.  GitHub compares a new branch's workflow
files with the default branch at push time, so a run based on an older default
tip can look like it changed a workflow even when none of its commits did.  The
cases here execute the committed ``publish_draft`` shell body against a real
throwaway origin; the forge itself is the only doubled boundary.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_PUBLISH_BRANCH = "feat/bd-ib-qustjx"
_CALL_END = "--end-of-call--"
_NODE = re.compile(
    r"^\s*publish_draft\s*\[(?P<body>.*?)^\s*\]",
    re.DOTALL | re.MULTILINE,
)
_SCRIPT = re.compile(r'script="(?P<value>(?:[^"\\]|\\.)*)"')


@dataclass(frozen=True, kw_only=True)
class _Published:
    result: subprocess.CompletedProcess[str]
    calls: tuple[tuple[str, ...], ...]
    draft_created: bool


def _git(cwd: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv],
        cwd=str(cwd),
        check=True,
        text=True,
        capture_output=True,
    )


def _configure(*, repo: Path) -> None:
    _git(repo, "config", "user.name", "publish-draft-test")
    _git(repo, "config", "user.email", "publish-draft-test@example.invalid")


def _commit(*, repo: Path, path: str, content: str, message: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _stale_run(*, tmp_path: Path) -> tuple[Path, str, str]:
    """A run with ordinary work, while master advances a workflow file."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "master", str(origin))

    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "master")
    _configure(repo=seed)
    base = _commit(
        repo=seed,
        path=".github/workflows/ci.yml",
        content="name: old\n",
        message="initial workflow",
    )
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-u", "origin", "master")

    run = tmp_path / "run"
    _git(tmp_path, "clone", str(origin), str(run))
    _configure(repo=run)
    _git(run, "switch", "-c", "fabro/run/test")
    _commit(repo=run, path="src/change.txt", content="run work\n", message="run work")

    default = tmp_path / "default"
    _git(tmp_path, "clone", str(origin), str(default))
    _configure(repo=default)
    current = _commit(
        repo=default,
        path=".github/workflows/ci.yml",
        content="name: current\n",
        message="advance workflow",
    )
    _git(default, "push", "origin", "master")
    return run, base, current


def _publish_script() -> str:
    block = _NODE.search(_WORKFLOW.read_text(encoding="utf-8"))
    assert block is not None
    attr = _SCRIPT.search(block.group("body"))
    assert attr is not None
    return attr.group("value").replace(r"\"", '"').replace("{{ inputs.default_branch }}", "master")


def _forge_double(*, tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'for arg in "$@"; do printf \'%s\\n\' "$arg" >> "$GH_CALLS"; done\n'
        f"printf '%s\\n' '{_CALL_END}' >> \"$GH_CALLS\"\n"
        'if test "$1 $2" = "pr create"; then : > "$GH_DRAFT_CREATED"; fi\n'
        "exit 0\n",
        encoding="utf-8",
    )
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _calls(*, path: Path) -> tuple[tuple[str, ...], ...]:
    calls: list[tuple[str, ...]] = []
    current: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == _CALL_END:
            calls.append(tuple(current))
            current = []
        else:
            current.append(line)
    return tuple(calls)


def _publish(*, tmp_path: Path, run: Path) -> _Published:
    calls = tmp_path / "gh-calls"
    created = tmp_path / "draft-created"
    bin_dir = _forge_double(tmp_path=tmp_path)
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE")
    }
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
            "GH_CALLS": str(calls),
            "GH_DRAFT_CREATED": str(created),
            "LIVESPEC_PUBLISH_BRANCH": _PUBLISH_BRANCH,
        }
    )
    result = subprocess.run(
        ["sh", "-c", _publish_script()],
        cwd=str(run),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return _Published(result=result, calls=_calls(path=calls), draft_created=created.is_file())


def test_stale_base_is_refreshed_before_a_workflow_clean_branch_is_published(
    tmp_path: Path,
) -> None:
    run, stale_base, current_base = _stale_run(tmp_path=tmp_path)

    published = _publish(tmp_path=tmp_path, run=run)
    _git(run, "fetch", "origin", "master")

    assert published.result.returncode == 0, published.result.stderr
    assert _git(run, "merge-base", "HEAD", "origin/master").stdout.strip() == current_base
    assert _git(run, "merge-base", "--is-ancestor", stale_base, "HEAD").returncode == 0
    remote_head = _git(run, "ls-remote", "origin", f"refs/heads/{_PUBLISH_BRANCH}").stdout.split()[
        0
    ]
    assert remote_head == _git(run, "rev-parse", "HEAD").stdout.strip()
    assert published.draft_created is True
    create = next(call for call in published.calls if call[:2] == ("pr", "create"))
    assert "--draft" in create
    assert create[create.index("--base") + 1] == "master"
    assert create[create.index("--head") + 1] == _PUBLISH_BRANCH

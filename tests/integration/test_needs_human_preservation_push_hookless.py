"""The needs-human preservation push is not gated on the repository's check suite.

Binds work-item bd-ib-3vn3mu against the SPECIFICATION/contracts.md rule that a
factory run never awaits a human (ratified v093, Scenario 103): a needs-human
outcome MUST preserve the run's work by reference BEFORE terminating.

THE NODE EXISTS TO PRESERVE WORK THAT BY DEFINITION DID NOT FINISH, so gating
its push on the checks that work may be failing defeats it. The sandbox's
prepare chain installs the governed repository's lefthook hooks, so the node's
plain `git push` ran the full pre-push aggregate first. Measured on hp-candidate
(fabro 0.382.0-nightly.0 adeefec): canary 5 (run 01M4NWARSD8T) and canary 6 (run
01M4PBFW4MP8) reached `needs_human` on a RED tree and ended
`LIVESPEC_NEEDS_HUMAN_PUSH_FAILED` — the hook refused the very tree the node was
preserving; canary 8 (run 01M4Q45S5AGK) reached it on a GREEN tree and the node
ran 634 s against its 600 s timeout and was cancelled with no output, so nothing
was preserved at all (`publish_draft`'s identical hook run on legacy run
01M4PPN7RX2M took 473 s). A red tree fails the hook and a green one outlasts the
node; either way the preservation push never happens.

`publish_draft` is the deliberate counterpart and KEEPS its hook: it publishes a
branch a reviewer and the merge path will read, so the aggregate is load-bearing
there. SPECIFICATION/contracts.md reserves its "Hooks MUST run normally" rule
for the scripted-publication nodes and says nothing of the kind about the
preservation ref.

THE FIXTURE'S HOOK IS NOT A STAND-IN FOR THE SUITE'S VERDICT — it is a stand-in
for the suite RUNNING AT ALL. Each case installs a real `.git/hooks` hook that
records that it ran and then refuses, and every case that asserts a hook did NOT
run first runs a CONTROL — a plain `git`-write of the same kind in the same
fixture — that MUST record the hook and MUST be refused. Without that control an
absent marker is equally consistent with "the node skipped the hook" and with "a
hook was never wired", and nothing in the output distinguishes them.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

_WORKFLOW = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
_SCRIPT_ATTR = re.compile(r'script="(?P<value>(?:[^"\\]|\\.)*)"')
_GIT_INVOCATION = re.compile(r"\bgit (?P<options>(?:-c \S+ )*)(?P<verb>[a-z][a-z-]*)")
_HOOKLESS_OPTION = "-c core.hooksPath=/dev/null"
_RUN_ID = "01M4HOOKLESSPRESERVE"
_REF = f"refs/heads/needs-human/{_RUN_ID}"
_PRESERVED = "LIVESPEC_NEEDS_HUMAN_PRESERVED"
_SENTINEL = "LIVESPEC_NEEDS_HUMAN"
_WIP = "in-progress.txt"
_WIP_BODY = "the unfinished work the preservation node exists to save\n"
_PUBLISH_BRANCH = "feat/bd-ib-3vn3mu"
_OPERATOR_NAME = "Chad Woolley"
_OPERATOR_EMAIL = "thewoolleyman@gmail.com"


def test_the_preservation_push_does_not_run_the_repository_pre_push_check_suite(
    tmp_path: Path,
) -> None:
    """Assertion 1: the push of the preserved tree runs no pre-push hook."""
    work, origin, marker = _sandbox(tmp_path=tmp_path)
    _control_push_is_refused_by_the_hook(work=work, marker=marker)

    completed = _run_needs_human(work=work, run_id=_RUN_ID)

    assert _pushed_refs(origin=origin) == [_REF], completed.stderr
    assert "pre-push" not in _hooks_that_ran(marker=marker)
    assert f"{_PRESERVED}: {_REF}" in completed.stderr


def test_a_tree_that_fails_the_check_suite_still_reaches_the_needs_human_ref(
    tmp_path: Path,
) -> None:
    """Assertion 2: the WORK reaches the ref, not merely the ref.

    The tree this node preserves is UNCOMMITTED by construction, so a refusing
    pre-commit hook leaves the push creating the ref at the last engine
    checkpoint — present, plausible, and missing exactly the work the node exists
    to save. "The ref exists" therefore passes for the failure, which is why this
    case reads the preserved BLOB rather than the ref.
    """
    work, origin, marker = _sandbox(tmp_path=tmp_path)
    _control_commit_is_refused_by_the_hook(work=work, marker=marker)

    completed = _run_needs_human(work=work, run_id=_RUN_ID)

    assert _pushed_refs(origin=origin) == [_REF], completed.stderr
    assert _preserved_blob(origin=origin, ref=_REF, path=_WIP) == _WIP_BODY
    assert "pre-commit" not in _hooks_that_ran(marker=marker)


def test_the_publish_draft_push_still_runs_the_repository_pre_push_check_suite(
    tmp_path: Path,
) -> None:
    """Assertion 3: the counterpart node is untouched — its push is still hook-gated."""
    work, origin, marker = _publish_sandbox(tmp_path=tmp_path)

    completed = _run_publish_draft(work=work)

    assert completed.returncode != 0
    assert "pre-push" in marker.read_text(encoding="utf-8")
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_FAILED" in completed.stderr
    assert _pushed_refs(origin=origin) == ["refs/heads/master"]


def test_the_node_still_terminates_non_green_with_the_needs_human_marker(
    tmp_path: Path,
) -> None:
    """Assertion 4: preservation is the only thing that changed about the node."""
    work, _origin, _marker = _sandbox(tmp_path=tmp_path)

    completed = _run_needs_human(work=work, run_id=_RUN_ID)

    assert completed.returncode == 1
    assert f"{_PRESERVED}: {_REF}" in completed.stderr
    assert f"{_SENTINEL}: loop cannot auto-resolve this work-item" in completed.stderr


def test_the_hookless_form_is_per_invocation_and_scoped_to_the_preservation_node() -> None:
    """Neither banned bypass appears, and `publish_draft` carries no bypass at all.

    `--no-verify` and a `LEFTHOOK=0` assignment are the two forms this repo's
    footgun guard refuses outright (`.claude/hooks/livespec_footgun_guard.py`),
    and both are process-wide in effect. A `-c core.hooksPath` option is scoped
    to the ONE invocation it is written on, which is what keeps this change from
    becoming a standing bypass the next reader inherits.
    """
    needs_human = _node_script(node="needs_human")
    publish_draft = _node_script(node="publish_draft")

    writes = [
        invocation
        for verb in ("commit", "push")
        for invocation in _git_writes(script=needs_human, verb=verb)
    ]
    assert len(writes) == 4, writes
    for invocation in writes:
        assert _HOOKLESS_OPTION in invocation, invocation
    assert "--no-verify" not in needs_human
    assert not re.search(r"\bLEFTHOOK=", needs_human)
    assert "core.hooksPath" not in publish_draft
    assert "--no-verify" not in publish_draft


def _node_script(*, node: str) -> str:
    """The node's OWN script, unescaped from the DOT attribute — never a paraphrase."""
    text = _WORKFLOW.read_text(encoding="utf-8")
    block = re.search(rf"^\s*{node}\s*\[(?P<body>.*?)^\s*\]", text, re.DOTALL | re.MULTILINE)
    assert block is not None, node
    attr = _SCRIPT_ATTR.search(block.group("body"))
    assert attr is not None, node
    unescaped = re.sub(r"\\(?P<escaped>.)", r"\g<escaped>", attr.group("value"))
    # The declared check suite is bound to a PASSING command, which is what
    # isolates the arm these cases are about. Since v134 `publish_draft` consults
    # that gate to classify a failed push — a gate that refused the refreshed
    # head takes the refresh-repair route instead of failing closed — so leaving
    # the token unbound would let the shell's own "not found" stand in for a gate
    # rejection and route the push failure to `fix`. With the gate passing, the
    # only remaining cause is the push itself, which is this case's subject.
    return unescaped.replace("{{ inputs.default_branch }}", "master").replace(
        "{{ inputs.sandbox_check_suite }}", "true"
    )


def _git_writes(*, script: str, verb: str) -> list[str]:
    return [
        match.group(0) for match in _GIT_INVOCATION.finditer(script) if match.group("verb") == verb
    ]


def _git(repo: Path, *argv: str) -> None:
    subprocess.run(["git", *argv], cwd=str(repo), check=True, text=True, capture_output=True)


def _install_refusing_hook(*, repo: Path, hook: str, marker: Path) -> None:
    """A stand-in for the repository's check suite: record that it ran, then refuse."""
    path = repo / ".git" / "hooks" / hook
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "{hook}" >> "{marker}"\n'
        f'echo "{hook}: the repository check suite refuses this tree" >&2\n'
        "exit 1\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _sandbox(*, tmp_path: Path) -> tuple[Path, Path, Path]:
    """A sandbox-shaped checkout with unfinished work, a real bare origin, live hooks."""
    origin = _origin(tmp_path=tmp_path)
    work = tmp_path / "work"
    work.mkdir(parents=True)
    _configure(repo=work, initial_branch="master")
    (work / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(work, "add", "seed.txt")
    _git(work, "commit", "--quiet", "-m", "seed")
    _git(work, "remote", "add", "origin", str(origin))
    (work / _WIP).write_text(_WIP_BODY, encoding="utf-8")
    marker = tmp_path / "hooks-that-ran.txt"
    _install_refusing_hook(repo=work, hook="pre-commit", marker=marker)
    _install_refusing_hook(repo=work, hook="pre-push", marker=marker)
    return work, origin, marker


def _publish_sandbox(*, tmp_path: Path) -> tuple[Path, Path, Path]:
    """A run branch ahead of a published `master`, with a refusing pre-push hook."""
    origin = _origin(tmp_path=tmp_path)
    seed = tmp_path / "seed"
    seed.mkdir(parents=True)
    _configure(repo=seed, initial_branch="master")
    (seed / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(seed, "add", "seed.txt")
    _git(seed, "commit", "--quiet", "-m", "seed")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "--quiet", "-u", "origin", "master")

    work = tmp_path / "run"
    subprocess.run(
        ["git", "clone", "--quiet", str(origin), str(work)],
        check=True,
        text=True,
        capture_output=True,
    )
    _configure(repo=work, initial_branch=None)
    _git(work, "switch", "--quiet", "-c", "fabro/run/hookless")
    (work / "src.txt").write_text("the run's work\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "--quiet", "-m", "run work")
    marker = tmp_path / "publish-hooks-that-ran.txt"
    _install_refusing_hook(repo=work, hook="pre-push", marker=marker)
    return work, origin, marker


def _origin(*, tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--quiet", "--bare", "--initial-branch=master", str(origin)],
        check=True,
        text=True,
        capture_output=True,
    )
    return origin


def _configure(*, repo: Path, initial_branch: str | None) -> None:
    if initial_branch is not None:
        _git(repo, "init", "--quiet", f"--initial-branch={initial_branch}")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "Fixture")
    _git(repo, "config", "commit.gpgsign", "false")


def _env() -> dict[str, str]:
    """The node's environment, with the FORMER run-id source stripped."""
    env = {key: value for key, value in os.environ.items() if key != "FABRO_RUN_ID"}
    env["LIVESPEC_GIT_AUTHOR_NAME"] = _OPERATOR_NAME
    env["LIVESPEC_GIT_AUTHOR_EMAIL"] = _OPERATOR_EMAIL
    return env


def _run_needs_human(*, work: Path, run_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", _node_script(node="needs_human")],
        cwd=str(work),
        env=_env(),
        check=False,
        text=True,
        capture_output=True,
        input=f"{run_id}\n",
    )


def _run_publish_draft(*, work: Path) -> subprocess.CompletedProcess[str]:
    env = _env()
    env["LIVESPEC_PUBLISH_BRANCH"] = _PUBLISH_BRANCH
    return subprocess.run(
        ["sh", "-c", _node_script(node="publish_draft")],
        cwd=str(work),
        env=env,
        check=False,
        text=True,
        capture_output=True,
        input="",
    )


def _control_push_is_refused_by_the_hook(*, work: Path, marker: Path) -> None:
    """Prove this fixture's pre-push hook CAN fire and CAN refuse a push."""
    completed = subprocess.run(
        ["git", "push", "origin", "HEAD:refs/heads/control"],
        cwd=str(work),
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode != 0, completed.stdout
    assert "pre-push" in marker.read_text(encoding="utf-8")
    marker.unlink()


def _control_commit_is_refused_by_the_hook(*, work: Path, marker: Path) -> None:
    """Prove this fixture's pre-commit hook CAN fire and CAN refuse a commit.

    The staging is undone afterwards so the node reaches an index in the same
    state production hands it — the node does its own `git add -A`.
    """
    _git(work, "add", "-A")
    completed = subprocess.run(
        ["git", "commit", "--quiet", "-m", "control"],
        cwd=str(work),
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode != 0, completed.stdout
    assert "pre-commit" in marker.read_text(encoding="utf-8")
    marker.unlink()
    _git(work, "reset", "--quiet")


def _preserved_blob(*, origin: Path, ref: str, path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=str(origin),
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def _hooks_that_ran(*, marker: Path) -> str:
    return marker.read_text(encoding="utf-8") if marker.exists() else ""


def _pushed_refs(*, origin: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)", "refs/"],
        cwd=str(origin),
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.split()

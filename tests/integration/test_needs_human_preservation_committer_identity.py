"""The needs-human preservation commit's COMMITTER on a clone with no identity.

Binds the third Definition-of-Done assertion of work-item bd-ib-lsr3vf against
`SPECIFICATION/scenarios.md` section "Scenario 176": with no global or system git
identity configured, the `needs_human` node's preservation commit is created with
the projected operator identity as both author AND committer.

THE NODE SUPPLIES ONLY AN AUTHOR, DELIBERATELY. Its commit sets
`GIT_AUTHOR_NAME` and `GIT_AUTHOR_EMAIL` from the projected pair and leaves the
COMMITTER to git, which is what lets a transport identity remain the committer
where one is in force — the property
`test_dispatcher_git_author.test_needs_human_commit_forces_the_resolved_author_but_preserves_committer_identity`
pins. On the Petri engine nothing is in force: the engine applies its
`git_identity` to its own per-node checkpoint commits only, so the clone carries
no `user.name` and no `user.email`, no `GIT_COMMITTER_*` reaches a script node,
and the commit dies on "Committer identity unknown" — silently, because the
invocation ends in `|| true`.

SO THE IDENTITY HAS TO BE IN THE CLONE, and these cases read it there. The
Dispatcher's rendered identity prepare steps write the SAME projected pair into
the clone's repository-local config, so git resolves the committer from it and
the two halves agree by construction rather than by a second hardcoded
assignment on the commit line — which would also overwrite the transport
committer the sibling case requires be left alone.

THE CONTROL IS THE MEASURED FAILURE, and it is the expensive shape rather than a
visible one: with the steps withheld, `git add -A` still succeeds, the commit
fails under `|| true`, and the push creates the run-scoped ref AT THE LAST
COMMIT THE CLONE ALREADY HAD. The ref exists, the sentinel says `PRESERVED`, and
the work is gone — so the control asserts the preserved BLOB, not the ref.

THE CHILD ENVIRONMENT CARRIES NO `GIT_COMMITTER_*` AND NO `GIT_AUTHOR_*`, and
both `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` are `/dev/null`. That is the
work-item's own precondition; inherited from the runner, the host's own identity
would make both cases pass for a reason neither is measuring.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_provenance import (
    FACTORY_RUN_ID_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import render_run_config_overlay

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

_OPERATOR = GitAuthor(name="Dana O'Brien", email="dana@example.invalid")
_DEFAULT_BRANCH = "trunk"
_DISPATCH_ID = "5f1b3c7a94d1402fa4e6c0b8d2713e55"
_REF = f"refs/heads/needs-human/{_DISPATCH_ID}"
_WIP = "in-progress.txt"
_WIP_BODY = "the unfinished work the preservation node exists to save\n"
_PRESERVED = "LIVESPEC_NEEDS_HUMAN_PRESERVED"
_NODE_EXIT = 1
_MATERIALIZED_MARKER = "# --- Dispatcher-materialized"
_GIT_CONFIG_STEP_RE = re.compile(r'^script = ("git config .*")$', re.MULTILINE)
_OAUTH_TOKEN = "oauth-token-value-that-must-not-leak"
_GITHUB_TOKEN = "github-token-value-that-must-not-leak"
_COMMITTED_RUN_CONFIG = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)


def test_the_preservation_commit_carries_the_operator_as_author_and_committer(
    tmp_path: Path,
) -> None:
    """Assertion 3: both identities on the preserved commit are the projected pair.

    Author and committer are read in ONE `git show` so the two cannot be compared
    against different commits, and the work's blob is read off the same ref: a
    commit carrying the right identities is worth nothing if it is not the commit
    that saved the tree.
    """
    sandbox = _provision(tmp_path=tmp_path, render_identity=True)

    completed = _needs_human(sandbox=sandbox)

    assert completed.returncode == _NODE_EXIT, completed.stderr
    assert f"{_PRESERVED}: {_REF}" in completed.stderr, completed.stderr
    assert _identities(sandbox=sandbox) == (
        f"{_OPERATOR.name} <{_OPERATOR.email}>|{_OPERATOR.name} <{_OPERATOR.email}>"
    )
    assert _preserved_blob(sandbox=sandbox) == _WIP_BODY


def test_without_the_rendered_identity_the_ref_exists_and_the_work_is_gone(
    tmp_path: Path,
) -> None:
    """The measured failure, reproduced: the control for the case above.

    `PRESERVED` is asserted PRESENT here, which is the point: the node reports a
    successful preservation either way, so the ref and the sentinel cannot
    discriminate and only the blob can. The committer assertion is the mirror
    image of the case above and establishes that the fixture really did reach the
    unknown-committer state rather than some other failure.
    """
    sandbox = _provision(tmp_path=tmp_path, render_identity=False)

    completed = _needs_human(sandbox=sandbox)

    assert completed.returncode == _NODE_EXIT, completed.stderr
    assert f"{_PRESERVED}: {_REF}" in completed.stderr, completed.stderr
    assert _OPERATOR.email not in _identities(sandbox=sandbox)
    assert _preserved_blob(sandbox=sandbox) is None


@dataclass(frozen=True, kw_only=True)
class _Sandbox:
    """The provisioned clone, its bare origin, and the child environment."""

    clone: Path
    origin: Path
    env: dict[str, str]


def _provision(*, tmp_path: Path, render_identity: bool) -> _Sandbox:
    """A sandbox-shaped clone holding uncommitted work and NO identity anywhere.

    The seed commit is made with a per-invocation `git -c` identity, so the
    clone's local config stays empty until the rendered steps write it — a
    provisioning `git config user.name` would be the agent-set identity whose
    accidental presence is what made the defect intermittent in production.

    The dispatch correlation id goes into the LOCAL config under the key the
    Dispatcher's own prepare step writes, which is how the node names the
    run-scoped ref on both engines.
    """
    env = _child_env(tmp_path=tmp_path)
    origin = tmp_path / "origin.git"
    _run(argv=["git", "init", "--quiet", "--bare", "-b", _DEFAULT_BRANCH, str(origin)], env=env)

    clone = tmp_path / "clone"
    clone.mkdir()
    _run(argv=["git", "init", "--quiet", "-b", _DEFAULT_BRANCH, "."], cwd=clone, env=env)
    _run(argv=["git", "remote", "add", "origin", str(origin)], cwd=clone, env=env)
    _ = (clone / "seed.txt").write_text("seed\n", encoding="utf-8")
    _run(argv=["git", "add", "-A"], cwd=clone, env=env)
    _run(
        argv=[
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            "seed",
        ],
        cwd=clone,
        env=env,
    )
    _run(argv=["git", "config", "--local", FACTORY_RUN_ID_MARKER, _DISPATCH_ID], cwd=clone, env=env)
    _ = (clone / _WIP).write_text(_WIP_BODY, encoding="utf-8")

    if render_identity:
        for step in _materialized_git_config_steps(rendered=_rendered_overlay(tmp_path=tmp_path)):
            _run(argv=["/bin/sh", "-c", step], cwd=clone, env=env)
    return _Sandbox(clone=clone, origin=origin, env=env)


def _rendered_overlay(*, tmp_path: Path) -> str:
    """The run config a dispatch carrying this operator pair actually submits."""
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_RUN_CONFIG,
        workflow_dir=tmp_path,
        token=_OAUTH_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
        git_author=_OPERATOR,
    )
    assert rendered is not None
    return rendered


def _materialized_git_config_steps(*, rendered: str) -> list[str]:
    """Every `git config`-shaped step the DISPATCHER rendered, decoded from TOML.

    Scoped to the materialized region so a committed step cannot be mistaken for a
    rendered one, and scoped to `git config` because this caller EXECUTES what it
    returns and the surrounding blocks provision things this fixture is not about.
    """
    materialized = rendered[rendered.index(_MATERIALIZED_MARKER) :]
    decoded: list[str] = []
    for literal in _GIT_CONFIG_STEP_RE.findall(materialized):
        script = json.loads(literal)
        assert isinstance(script, str)
        decoded.append(script)
    return decoded


def _needs_human(*, sandbox: _Sandbox) -> subprocess.CompletedProcess[str]:
    """Run the shipped `needs_human` terminal's script in the provisioned clone."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script = graph.nodes["needs_human"]["script"]
    assert "{{ inputs.default_branch }}" in script, script
    return subprocess.run(
        ["/bin/sh", "-c", script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH)],
        cwd=sandbox.clone,
        env=sandbox.env,
        capture_output=True,
        text=True,
        check=False,
        input="",
    )


def _identities(*, sandbox: _Sandbox) -> str:
    """The preserved commit's author and committer, read in one `git show`."""
    return _capture(
        argv=[
            "git",
            "--git-dir",
            str(sandbox.origin),
            "show",
            "-s",
            "--format=%an <%ae>|%cn <%ce>",
            _REF,
        ],
        env=sandbox.env,
    )


def _preserved_blob(*, sandbox: _Sandbox) -> str | None:
    """The unfinished work as the preserved ref carries it, or None when absent."""
    completed = subprocess.run(
        ["git", "--git-dir", str(sandbox.origin), "show", f"{_REF}:{_WIP}"],
        env=sandbox.env,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout if completed.returncode == 0 else None


def _child_env(*, tmp_path: Path) -> dict[str, str]:
    """An EXPLICIT child environment: the work-item's own no-identity precondition.

    No `GIT_AUTHOR_*` and no `GIT_COMMITTER_*`, because either would decide the
    answer before the clone's config was consulted, and the Petri-era engine
    supplies neither to a script node. `LIVESPEC_SANDBOX_GH_REFRESH_ROOT` is
    pointed at a path that does not exist so the node's `livespec_push` wrapper
    falls through to a plain `git push`: left unset it resolves
    `/workspace/.livespec-gh-refresh`, which EXISTS inside a real dispatch.
    """
    home = tmp_path / "home"
    home.mkdir()
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LIVESPEC_GIT_AUTHOR_NAME": _OPERATOR.name,
        "LIVESPEC_GIT_AUTHOR_EMAIL": _OPERATOR.email,
        "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(tmp_path / "absent-gh-refresh-root"),
    }


def _run(*, argv: list[str], env: dict[str, str], cwd: Path | None = None) -> None:
    """Run a provisioning command for its EFFECT; a non-zero exit is a broken fixture."""
    _ = subprocess.run(argv, cwd=cwd, env=env, check=True, capture_output=True, text=True)


def _capture(*, argv: list[str], env: dict[str, str], cwd: Path | None = None) -> str:
    """Run a provisioning command for its OUTPUT; a non-zero exit is a broken fixture."""
    completed = subprocess.run(argv, cwd=cwd, env=env, check=True, capture_output=True, text=True)
    return completed.stdout.strip()

"""The git identity a Petri-era sandbox clone needs before any node commits.

Binds work-item bd-ib-lsr3vf (plan `fabro-currency`, epic bd-ib-6tcjfx) against
`SPECIFICATION/scenarios.md` section "Scenario 176", whose green run has to be
repaired and published rather than ending at needs-human.

WHAT WAS MEASURED. On the Petri engine the sandbox clone at `/workspace` carries
no `user.name` and no `user.email`. The engine records a `git_identity` and uses
it for its OWN per-node checkpoint commits, so a SCRIPT node that creates commits
itself has no committer. `publish_draft`'s first refresh runs
`git rebase origin/<default>`, which must create commits whenever the default
branch has advanced -- and a rebase with no committer identity exits 128 on
"Committer identity unknown". Measured 2026-10-15 on hp-candidate canary 13 (run
01M4YV4YJ30J5ABBGJWR4KYWKX, item bd-ib-o6aeji): implement and janitor succeeded,
`publish_draft@1` then failed at 04:46:52Z carrying that message, `refresh_repair`
found no repair brief, and the run ended at needs_human.

THE CONTROL IS WHY THE CAUSE IS SETTLED RATHER THAN PLAUSIBLE. Canary 12 (run
01M4Y7EJWTQWK5CWWS0NKDHY7T) passed `publish_draft` TWICE, and before its second
refresh -- the one that had commits to create -- an agent tool call had run
`git config user.name` / `git config user.email`. So the passing run passed
because an agent happened to configure the identity, which is not something a
graph may rely on.

WHY THESE CASES EXECUTE RATHER THAN MATCH TEXT. The assertion is that the REBASE
COMPLETES, and no reading of a rendered prepare step can establish that: a step
that writes the right keys in the wrong scope, or after the node that needs them,
renders identically to one that works. So each case provisions a real bare origin
and a real clone, runs the ACTUALLY RENDERED prepare steps in it, and then runs
the shipped `publish_draft` node script read verbatim out of the committed graph.

THE FIXTURE LEAVES THE CLONE WITHOUT AN IDENTITY IN EVERY SCOPE. `GIT_CONFIG_GLOBAL`
and `GIT_CONFIG_SYSTEM` are pointed at `/dev/null` so the runner's own identity
cannot stand in for the projected one, and every provisioning commit supplies its
identity per invocation with `git -c` so the clone's local config stays as empty as
the Petri sandbox's is. That is the "no identity set by any agent" half of the
work-item, and without it the host's `~/.gitconfig` would make every case pass.

THE MEASURED FAILURE IS ITSELF A CASE, because the positive case alone cannot say
the fixture is capable of failing: a rebase that never had a commit to create would
satisfy it just as well. `_provision` therefore asserts the default branch really
did advance past the run's head, and the control withholds only the rendered
identity steps and requires exit 128 on "Committer identity unknown".
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import render_run_config_overlay

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUNDLE = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GRAPH = _BUNDLE / "workflow.fabro"

# The operator pair a dispatch resolves from the governed repository's
# `git_author` declaration. The apostrophe is deliberate: the rendered step is a
# shell command line, so a name carrying a shell metacharacter is what says the
# value is quoted rather than merely interpolated.
_OPERATOR = GitAuthor(name="Dana O'Brien", email="dana@example.invalid")
# Never this fleet's own `master`: an implementation that spelled it would pass
# here and leave every adopter on another default branch broken.
_DEFAULT_BRANCH = "trunk"
_PUBLISH_BRANCH = "feat/bd-ib-lsr3vf"
_RUN_BRANCH = "fabro/run/01M4Z5F55K07XFCZNWZK2TPBX5"
_UNKNOWN_COMMITTER = "Committer identity unknown"
_REFRESH = "LIVESPEC_PUBLISH_DRAFT_REFRESH:"
_REFRESH_FAILED = "LIVESPEC_PUBLISH_DRAFT_REFRESH_FAILED"
_DRAFT_EXISTS = "LIVESPEC_PUBLISH_DRAFT_EXISTS"
_IDENTITY_UNKNOWN_EXIT = 128
_OAUTH_TOKEN = "oauth-token-value-that-must-not-leak"
_GITHUB_TOKEN = "github-token-value-that-must-not-leak"
# Every block the overlay appends opens with this marker, so the first occurrence
# is the boundary between what the dispatched workflow COMMITTED and what the
# Dispatcher RENDERED. Keying on it is what lets a case assert the identity is
# written by a Dispatcher-rendered step rather than by one a fork happens to carry.
_MATERIALIZED_MARKER = "# --- Dispatcher-materialized"
_GIT_CONFIG_STEP_RE = re.compile(r'^script = ("git config .*")$', re.MULTILINE)
_AUTHOR_ENV_RE = re.compile(r'^(LIVESPEC_GIT_AUTHOR_(?:NAME|EMAIL)) = (".*")$', re.MULTILINE)
_COMMITTED_RUN_CONFIG = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)
# The forge the stage asks whether a pull request is already open for the publish
# branch. Answering with a number ends the stage at `LIVESPEC_PUBLISH_DRAFT_EXISTS`
# -- the arm that opens nothing -- which keeps these cases about the refresh.
_GH_STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$LIVESPEC_FAKE_FORGE_CALLS"
if test "$1 $2" = "pr list"; then echo 4242; exit 0; fi
echo "unstubbed gh invocation: $*" >&2
exit 2
"""


def test_the_prepared_clone_carries_the_projected_identity_in_its_local_config(
    tmp_path: Path,
) -> None:
    """Assertion 1: the clone's REPOSITORY-LOCAL identity is the projected pair.

    Both halves are read back off the rendered overlay's own env table rather than
    off this module's constant, because the work-item states the equality against
    `LIVESPEC_GIT_AUTHOR_NAME` and `LIVESPEC_GIT_AUTHOR_EMAIL` -- the values the
    needs_human node's emergency commit reads. Compared with a constant, a renderer
    that projected one pair into the env table and a different one into the config
    would pass.

    The global/system control is what makes the positive reading evidence: with the
    runner's own `~/.gitconfig` reachable, `git config --get user.name` answers for
    a clone no prepare step ever touched.
    """
    rendered = _rendered_overlay(tmp_path=tmp_path)
    projected = _projected_author_env(rendered=rendered)
    sandbox = _provision(tmp_path=tmp_path, render_identity=True)

    local_name = _config(sandbox=sandbox, scope="--local", key="user.name")
    local_email = _config(sandbox=sandbox, scope="--local", key="user.email")

    assert _config(sandbox=sandbox, scope="--global", key="user.name") == ""
    assert _config(sandbox=sandbox, scope="--system", key="user.name") == ""
    assert local_name == projected["LIVESPEC_GIT_AUTHOR_NAME"]
    assert local_email == projected["LIVESPEC_GIT_AUTHOR_EMAIL"]


def test_publish_draft_refreshes_onto_an_advanced_default_branch_with_no_agent_identity(
    tmp_path: Path,
) -> None:
    """Assertion 2: the refresh rebase COMPLETES, and it really had commits to create.

    The ancestry assertion is the one that keeps this from passing on a refresh that
    did nothing: `_provision` leaves the run head behind origin's default branch, so
    a rebase that was skipped would leave that head unreachable from HEAD.
    """
    sandbox = _provision(tmp_path=tmp_path, render_identity=True)

    completed = _publish_draft(sandbox=sandbox)

    assert _UNKNOWN_COMMITTER not in completed.stderr, completed.stderr
    assert _REFRESH_FAILED not in completed.stderr, completed.stderr
    assert _REFRESH in completed.stderr, completed.stderr
    assert _DRAFT_EXISTS in completed.stderr, completed.stderr
    assert completed.returncode == 0, completed.stderr
    assert _contains(sandbox=sandbox, commit=sandbox.default_branch_head)


def test_without_the_rendered_identity_the_refresh_dies_on_an_unknown_committer(
    tmp_path: Path,
) -> None:
    """The measured failure, reproduced: the control for the case above.

    Identical fixture; the ONE thing varied is whether the Dispatcher-rendered
    identity steps ran. Both the exit code and the message are asserted, because the
    stage fails closed on any non-zero rebase status and the code alone would not say
    that git refused for want of a committer.
    """
    sandbox = _provision(tmp_path=tmp_path, render_identity=False)

    completed = _publish_draft(sandbox=sandbox)

    assert completed.returncode == _IDENTITY_UNKNOWN_EXIT, completed.stderr
    assert _UNKNOWN_COMMITTER in completed.stderr, completed.stderr
    assert _REFRESH_FAILED in completed.stderr, completed.stderr


@dataclass(frozen=True, kw_only=True)
class _Sandbox:
    """The provisioned clone, the child environment, and origin's advanced head."""

    clone: Path
    env: dict[str, str]
    default_branch_head: str


def _provision(*, tmp_path: Path, render_identity: bool) -> _Sandbox:
    """Build a Petri-shaped sandbox: a clone with run work and NO identity anywhere.

    The default branch ADVANCES after the clone is taken, which is what any merge to
    the default branch does while a run is in flight and what gives the refresh
    rebase a commit to create. The fixture asserts that advance rather than assuming
    it: a clone already containing origin's head would make the rebase a no-op, and
    the positive case would then pass with the defect fully present.

    Every provisioning commit carries its identity PER INVOCATION via `git -c`, so
    the clone's local config stays empty until the rendered steps write it. A
    provisioning `git config user.name` would be the agent-set identity canary 12
    passed on.
    """
    env = _child_env(tmp_path=tmp_path)
    origin = tmp_path / "origin.git"
    _run(argv=["git", "init", "--quiet", "--bare", "-b", _DEFAULT_BRANCH, str(origin)], env=env)

    seed = tmp_path / "seed"
    seed.mkdir()
    _run(argv=["git", "init", "--quiet", "-b", _DEFAULT_BRANCH, "."], cwd=seed, env=env)
    _ = (seed / "seed.txt").write_text("seed\n", encoding="utf-8")
    _commit(repo=seed, env=env, message="seed")
    _run(argv=["git", "push", "--quiet", str(origin), _DEFAULT_BRANCH], cwd=seed, env=env)

    clone = tmp_path / "clone"
    _run(argv=["git", "clone", "--quiet", origin.as_uri(), str(clone)], env=env)
    _run(argv=["git", "switch", "--quiet", "-c", _RUN_BRANCH], cwd=clone, env=env)
    _ = (clone / "implemented.txt").write_text("the run's work\n", encoding="utf-8")
    _commit(repo=clone, env=env, message="fix: the run's work")
    run_head = _capture(argv=["git", "rev-parse", "HEAD"], cwd=clone, env=env)

    _ = (seed / "advanced.txt").write_text("merged while the run was in flight\n", encoding="utf-8")
    _commit(repo=seed, env=env, message="advance the default branch")
    _run(argv=["git", "push", "--quiet", str(origin), _DEFAULT_BRANCH], cwd=seed, env=env)
    default_branch_head = _capture(argv=["git", "rev-parse", "HEAD"], cwd=seed, env=env)

    sandbox = _Sandbox(clone=clone, env=env, default_branch_head=default_branch_head)
    assert not _contains(sandbox=sandbox, commit=default_branch_head)
    assert run_head != default_branch_head

    if render_identity:
        for step in _materialized_git_config_steps(rendered=_rendered_overlay(tmp_path=tmp_path)):
            _run(argv=["/bin/sh", "-c", step], cwd=clone, env=env)
    return sandbox


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
    returns: the surrounding blocks provision a tmux root, a credential helper and
    the plugin-cache gate, none of which this fixture is about.
    """
    materialized = rendered[rendered.index(_MATERIALIZED_MARKER) :]
    decoded: list[str] = []
    for literal in _GIT_CONFIG_STEP_RE.findall(materialized):
        script = json.loads(literal)
        assert isinstance(script, str)
        decoded.append(script)
    return decoded


def _projected_author_env(*, rendered: str) -> dict[str, str]:
    """The two `LIVESPEC_GIT_AUTHOR_*` values off the rendered env table."""
    projected = {name: json.loads(literal) for name, literal in _AUTHOR_ENV_RE.findall(rendered)}
    assert sorted(projected) == ["LIVESPEC_GIT_AUTHOR_EMAIL", "LIVESPEC_GIT_AUTHOR_NAME"]
    return projected


def _publish_draft(*, sandbox: _Sandbox) -> subprocess.CompletedProcess[str]:
    """Run the shipped `publish_draft` node script in the provisioned clone."""
    return subprocess.run(
        ["/bin/sh", "-c", _publish_draft_script()],
        cwd=sandbox.clone,
        env=sandbox.env,
        capture_output=True,
        text=True,
        check=False,
        input="",
    )


def _publish_draft_script() -> str:
    """The node's own bytes, read through the canonical parser with inputs bound.

    The declared check suite is bound to a PASSING command: since v134 the stage
    consults that gate to classify a FAILED push, and an unbound token would let the
    shell's own "not found" stand in for a gate rejection. Nothing else is touched.
    """
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script = graph.nodes["publish_draft"]["script"]
    assert "{{ inputs.default_branch }}" in script, script
    return script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH).replace(
        "{{ inputs.sandbox_check_suite }}", "true"
    )


def _child_env(*, tmp_path: Path) -> dict[str, str]:
    """An EXPLICIT child environment: no host git identity, no inherited LIVESPEC_*.

    The two `GIT_CONFIG_*` redirects are the work-item's own precondition -- "no
    global or system git identity configured" -- and they also keep the enclosing
    factory run's config out of the measurement. `LIVESPEC_SANDBOX_GH_REFRESH_ROOT`
    is pointed at a path that does not exist so the stage's `livespec_push` wrapper
    falls through to a plain `git push`: left unset it resolves
    `/workspace/.livespec-gh-refresh`, which EXISTS inside a real dispatch and would
    make the result depend on the run executing the test.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "gh"
    _ = stub.write_text(_GH_STUB, encoding="utf-8")
    stub.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    return {
        "PATH": f"{bin_dir}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LIVESPEC_FAKE_FORGE_CALLS": str(tmp_path / "forge-calls.txt"),
        "LIVESPEC_PUBLISH_BRANCH": _PUBLISH_BRANCH,
        "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(tmp_path / "absent-gh-refresh-root"),
    }


def _commit(*, repo: Path, env: dict[str, str], message: str) -> None:
    """Commit the worktree with a PER-INVOCATION identity, leaving the config empty."""
    _run(argv=["git", "add", "-A"], cwd=repo, env=env)
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
            message,
        ],
        cwd=repo,
        env=env,
    )


def _config(*, sandbox: _Sandbox, scope: str, key: str) -> str:
    """One config value in ONE scope, empty when the scope does not carry it."""
    completed = subprocess.run(
        ["git", "config", scope, "--get", key],
        cwd=sandbox.clone,
        env=sandbox.env,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip()


def _contains(*, sandbox: _Sandbox, commit: str) -> bool:
    """Whether the clone's HEAD descends from `commit`."""
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=sandbox.clone,
        env=sandbox.env,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _run(*, argv: list[str], env: dict[str, str], cwd: Path | None = None) -> None:
    """Run a provisioning command for its EFFECT; a non-zero exit is a broken fixture."""
    _ = subprocess.run(argv, cwd=cwd, env=env, check=True, capture_output=True, text=True)


def _capture(*, argv: list[str], env: dict[str, str], cwd: Path | None = None) -> str:
    """Run a provisioning command for its OUTPUT; a non-zero exit is a broken fixture."""
    completed = subprocess.run(argv, cwd=cwd, env=env, check=True, capture_output=True, text=True)
    return completed.stdout.strip()

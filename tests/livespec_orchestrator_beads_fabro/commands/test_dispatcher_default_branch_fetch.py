"""The dispatch base a source-staged sandbox diffs against (bd-ib-xlblgr, Scenario 61).

Since the Dispatcher began staging each run on a disposable `livespec/source/<id>`
branch, the sandbox clone is SINGLE-BRANCH: its `remote.origin.fetch` refspec names
that staged branch and nothing else. The committed prepare chain opens with
`git fetch --unshallow`, which fetches the CONFIGURED refspec -- so it deepens the
staged branch and brings in no other ref -- and nothing else in the rendered
sequence fetched the default branch. `implementation_diff`'s script is
`git diff --quiet origin/<default_branch>...HEAD`, so it needs that ref.

MEASURED 2026-10-14, in the orchestrator's OWN sandbox for this work-item:
`git rev-parse --verify origin/master` exited 128 and
`git config --get-all remote.origin.fetch` named only the staged branch. The ref is
therefore absent in EVERY repository, not only in the dolt-server run that reported
it (run 01M4Y28FVEBC6B2HH6J4QHRFKH on hp: `implement` succeeded carrying a 5-file
diff, `implementation_diff` then exited 128 on `fatal: ambiguous argument
'origin/master...HEAD'`, and `dead_implementer` reported an unchanged tree). The
orchestrator runs that passed did so because their implementer session happened to
fetch the ref itself -- the implement prompt asks for
`git log origin/<default_branch>..HEAD` -- which is not something the prepare
sequence may rely on.

ALSO MEASURED: `git fetch origin <default_branch>` in a single-branch clone writes
`FETCH_HEAD` and does NOT create `refs/remotes/origin/<default_branch>`, because git
updates a remote-tracking ref only for a refspec its own configuration names. An
EXPLICIT destination refspec is load-bearing here rather than decoration.

WHY THIS MODULE EXECUTES RATHER THAN MATCHES TEXT. The assertion is that the diff
RESOLVES, and a rendered-text check cannot tell a refspec that creates the ref from
one that only writes `FETCH_HEAD`: the two differ by nothing a reader of the string
would flag. So each case provisions real repositories, runs the ACTUALLY RENDERED
prepare steps, and then runs the `implementation_diff` node script read verbatim out
of the shipped graph.

THE DEFAULT BRANCH IS `trunk` AND NEVER `master`. An implementation that spelled
this fleet's own branch name would pass against `master` and fail every adopter,
which is the half of the defect the work-item states as "for every repository and
not only for livespec-orchestrator-beads-fabro".

THE CONTROL IS THE MEASURED FAILURE: the same fixture with the Dispatcher-rendered
dispatch-base steps withheld, which must exit 128 carrying
LIVESPEC_DEAD_IMPLEMENTER_CHECK_FAILED. Without it a node script that exited 0 for
any reason at all would satisfy the positive case alone. The third case keeps the
breaker itself honest: an UNCHANGED tree must still exit 1 on the
LIVESPEC_DEAD_IMPLEMENTER sentinel, so making the diff resolvable cannot be mistaken
for making it always pass.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)

_BUNDLE = Path(".claude-plugin/.fabro/workflows/implement-work-item")
_DIFF_NODE = "implementation_diff"
# The engine binds a graph node's `inputs.*` tokens itself; the test stands in for
# that binding, and asserts the token was present so the substitution cannot
# silently become a no-op against a graph that stopped projecting the field.
_DEFAULT_BRANCH_TOKEN = "{{ inputs.default_branch }}"
_DEFAULT_BRANCH = "trunk"
_STAGED_BRANCH = "livespec/source/92ab7ab9b68647419e9501460d6c2231"
_SEED_COMMITS = 3
_OAUTH_TOKEN = "oauth-token-value-that-must-not-leak"
_GITHUB_TOKEN = "github-token-value-that-must-not-leak"
_CHECK_FAILED_SENTINEL = "LIVESPEC_DEAD_IMPLEMENTER_CHECK_FAILED"
_UNCHANGED_SENTINEL = "LIVESPEC_DEAD_IMPLEMENTER:"
_AMBIGUOUS_ARGUMENT_EXIT = 128
_UNCHANGED_TREE_EXIT = 1
# Every block the overlay appends opens with this marker, so the first occurrence is
# the boundary between what the dispatched workflow COMMITTED and what the Dispatcher
# RENDERED. Keying on it is what lets a case assert the dispatch-base fetch is a
# Dispatcher-rendered step rather than merely a step that happens to be present.
_MATERIALIZED_MARKER = "# --- Dispatcher-materialized"
_FETCH_STEP_RE = re.compile(r'^script = ("git fetch .*")$', re.MULTILINE)


def test_a_changed_tree_passes_implementation_diff_against_the_projected_dispatch_base(
    tmp_path: Path,
) -> None:
    """The work-item's two assertions, taken together on one real clone.

    The ref is asserted to NAME origin's own default-branch head rather than merely
    to exist. The fixture advanced that branch after staging, so the head is a
    commit the clone did not have: a refspec whose source half named the staged
    branch, or any other ref, resolves to a different commit and fails here while
    still leaving the diff perfectly resolvable.
    """
    sandbox = _provision(tmp_path=tmp_path, render_dispatch_base=True)

    resolved = _resolve_ref(sandbox=sandbox, ref=f"origin/{_DEFAULT_BRANCH}")
    assert resolved.returncode == 0, resolved.stderr
    assert resolved.stdout.strip() == sandbox.default_branch_head

    _commit_implementer_change(sandbox=sandbox)
    completed = _implementation_diff(sandbox=sandbox)

    assert completed.returncode == 0, completed.stderr
    assert _CHECK_FAILED_SENTINEL not in completed.stderr
    assert _UNCHANGED_SENTINEL not in completed.stderr


def test_without_the_dispatch_base_fetch_the_diff_cannot_resolve(tmp_path: Path) -> None:
    """The measured failure, reproduced: the control for the case above.

    Identical fixture; the one thing varied is whether the Dispatcher-rendered
    dispatch-base steps ran. The exit code and the sentinel are both asserted
    because the node script fails closed on ANY non-zero/non-one status, so the
    code alone would not say that git could not resolve the revision.
    """
    sandbox = _provision(tmp_path=tmp_path, render_dispatch_base=False)

    _commit_implementer_change(sandbox=sandbox)
    completed = _implementation_diff(sandbox=sandbox)

    assert completed.returncode == _AMBIGUOUS_ARGUMENT_EXIT
    assert _CHECK_FAILED_SENTINEL in completed.stderr


def test_an_unchanged_tree_still_reports_the_dead_implementer(tmp_path: Path) -> None:
    """Resolving the dispatch base must not retire the breaker it feeds.

    A fetch that made every diff non-empty -- a tracking ref at the wrong commit,
    say -- would satisfy the positive case while silently disarming the
    cross-vendor-burn rule of `SPECIFICATION/contracts.md` section "No cross-vendor
    burn on a dead implementer".
    """
    sandbox = _provision(tmp_path=tmp_path, render_dispatch_base=True)

    completed = _implementation_diff(sandbox=sandbox)

    assert completed.returncode == _UNCHANGED_TREE_EXIT
    assert _UNCHANGED_SENTINEL in completed.stderr
    assert _CHECK_FAILED_SENTINEL not in completed.stderr


@dataclass(frozen=True, kw_only=True)
class _Sandbox:
    """The provisioned clone, its environment, and origin's default-branch head."""

    clone: Path
    env: dict[str, str]
    default_branch_head: str


def _provision(*, tmp_path: Path, render_dispatch_base: bool) -> _Sandbox:
    """Reproduce a source-staged sandbox, then run the rendered fetch steps in it.

    THE STAGED TIP IS NEVER AHEAD OF THE DEFAULT BRANCH, so the fixture does not
    put it there. `source_checkout_preflight` refuses a dispatch whose checkout
    HEAD is not an ANCESTOR of some `origin/*` ref, and
    `SourceStagingRunner._staging_base` then stages at the freshly fetched
    default-branch head whenever the checkout sits strictly behind it. The measured
    incident agrees: run 01M4Y28FVEBC6B2HH6J4QHRFKH's base sha `f5cbe5e9` WAS
    dolt-server's own origin/master head.

    THE DEFAULT BRANCH THEN ADVANCES, which is what makes the fixture able to fail
    for the right reasons. A staged tip equal to a static default-branch head is
    already in the clone, so `origin/<default_branch>` could be pointed at the
    staged branch and every assertion here would still hold. Advancing origin by
    one commit after staging -- what any merge to the default branch does while a
    run is queued -- makes the dispatch base a commit the depth-1 clone does NOT
    have, so the ref equality below discriminates and the fetch has to bring real
    history rather than re-label a commit already present.

    The clone is `--depth 1` against three seed commits, so it is genuinely shallow
    and the committed `git fetch --unshallow` has work to do rather than refusing
    with "on a complete repository does not make sense" -- which is what a depth
    covering the whole fixture history would produce.
    """
    env = _scrubbed_env()
    origin = tmp_path / "origin.git"
    _run(argv=["git", "init", "--quiet", "--bare", "-b", _DEFAULT_BRANCH, str(origin)], env=env)
    seed = tmp_path / "seed"
    seed.mkdir()
    _run(argv=["git", "init", "--quiet", "-b", _DEFAULT_BRANCH, "."], cwd=seed, env=env)
    _run(argv=["git", "config", "user.email", "factory@example.invalid"], cwd=seed, env=env)
    _run(argv=["git", "config", "user.name", "Factory"], cwd=seed, env=env)
    for index in range(_SEED_COMMITS):
        _ = (seed / f"seed-{index}.txt").write_text(f"seed {index}\n", encoding="utf-8")
        _run(argv=["git", "add", "."], cwd=seed, env=env)
        _run(argv=["git", "commit", "--quiet", "-m", f"seed {index}"], cwd=seed, env=env)
    _run(argv=["git", "push", "--quiet", str(origin), _DEFAULT_BRANCH], cwd=seed, env=env)
    _run(
        argv=["git", "push", "--quiet", str(origin), f"HEAD:refs/heads/{_STAGED_BRANCH}"],
        cwd=seed,
        env=env,
    )
    _ = (seed / "advanced.txt").write_text("merged while the run was queued\n", encoding="utf-8")
    _run(argv=["git", "add", "."], cwd=seed, env=env)
    _run(argv=["git", "commit", "--quiet", "-m", "advanced"], cwd=seed, env=env)
    _run(argv=["git", "push", "--quiet", str(origin), _DEFAULT_BRANCH], cwd=seed, env=env)
    default_branch_head = _capture(argv=["git", "rev-parse", "HEAD"], cwd=seed, env=env)

    clone = tmp_path / "clone"
    _run(
        argv=[
            "git",
            "clone",
            "--quiet",
            "--depth",
            "1",
            "--branch",
            _STAGED_BRANCH,
            origin.as_uri(),
            str(clone),
        ],
        env=env,
    )
    _run(argv=["git", "config", "user.email", "implementer@example.invalid"], cwd=clone, env=env)
    _run(argv=["git", "config", "user.name", "Implementer"], cwd=clone, env=env)
    sandbox = _Sandbox(clone=clone, env=env, default_branch_head=default_branch_head)

    rendered = _rendered_overlay(tmp_path=tmp_path)
    steps = _fetch_steps(text=_committed_region(rendered=rendered))
    if render_dispatch_base:
        steps += _fetch_steps(text=_materialized_region(rendered=rendered))
    for step in steps:
        _run(argv=["/bin/bash", "-c", step], cwd=clone, env=env)
    return sandbox


def _rendered_overlay(*, tmp_path: Path) -> str:
    """The run config a dispatch of a `trunk`-defaulted repository actually submits."""
    rendered = render_run_config_overlay(
        committed_text=_committed_run_config(),
        workflow_dir=tmp_path,
        token=_OAUTH_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
        prepare_inputs={"default_branch": _DEFAULT_BRANCH},
    )
    assert rendered is not None
    return rendered


def _committed_run_config() -> str:
    """A minimal run config carrying the SHIPPED unshallow step, read not retyped.

    The unshallow is what gives the staged branch its full history, so the executed
    sequence has to include it or the dispatch-base fetch would be measured against
    a shape no dispatch ever runs. Copying the script out of the shipped payload
    keeps this fixture following that step rather than pinning a paraphrase of it.
    """
    shipped = _fetch_steps(text=(_BUNDLE / "workflow.toml").read_text(encoding="utf-8"))
    assert len(shipped) == 1, f"expected one committed fetch step, got {shipped}"
    assert "--unshallow" in shipped[0], shipped[0]
    return (
        "_version = 1\n"
        "\n"
        "[workflow]\n"
        'graph = "workflow.fabro"\n'
        "\n"
        "[run.environment]\n"
        'id = "livespec-ci"\n'
        "\n"
        "[[run.prepare.steps]]\n"
        f"script = {json.dumps(shipped[0])}\n"
    )


def _committed_region(*, rendered: str) -> str:
    return rendered[: rendered.index(_MATERIALIZED_MARKER)]


def _materialized_region(*, rendered: str) -> str:
    return rendered[rendered.index(_MATERIALIZED_MARKER) :]


def _fetch_steps(*, text: str) -> list[str]:
    """Every `git fetch`-shaped prepare step, decoded from its TOML basic string.

    Scoped to `git fetch` deliberately: the surrounding blocks provision a tmux
    root, a credential helper and the plugin-cache gate, and this caller EXECUTES
    what it returns against the runner's own environment.
    """
    decoded: list[str] = []
    for literal in _FETCH_STEP_RE.findall(text):
        script = json.loads(literal)
        assert isinstance(script, str)
        decoded.append(script)
    return decoded


def _implementation_diff(*, sandbox: _Sandbox) -> subprocess.CompletedProcess[str]:
    """Run the shipped `implementation_diff` node script in the provisioned clone."""
    return subprocess.run(
        ["/bin/bash", "-c", _implementation_diff_script()],
        cwd=sandbox.clone,
        env=sandbox.env,
        capture_output=True,
        text=True,
        check=False,
    )


def _implementation_diff_script() -> str:
    """The node's script, read out of the shipped graph with its input bound."""
    graph = parse_dot_graph(text=(_BUNDLE / "workflow.fabro").read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script = graph.nodes[_DIFF_NODE]["script"]
    assert _DEFAULT_BRANCH_TOKEN in script, script
    return script.replace(_DEFAULT_BRANCH_TOKEN, _DEFAULT_BRANCH)


def _commit_implementer_change(*, sandbox: _Sandbox) -> None:
    _ = (sandbox.clone / "implemented.txt").write_text("the implementer's work\n", encoding="utf-8")
    _run(argv=["git", "add", "."], cwd=sandbox.clone, env=sandbox.env)
    _run(
        argv=["git", "commit", "--quiet", "-m", "fix: implementer work"],
        cwd=sandbox.clone,
        env=sandbox.env,
    )


def _resolve_ref(*, sandbox: _Sandbox, ref: str) -> subprocess.CompletedProcess[str]:
    """Read one ref WITHOUT raising, so an absent ref is an assertion and not a trace."""
    return subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=sandbox.clone,
        env=sandbox.env,
        capture_output=True,
        text=True,
        check=False,
    )


def _scrubbed_env() -> dict[str, str]:
    """The child environment: no coverage self-instrumentation, no host git config.

    The git config redirects keep the runner's own global and system config -- which
    may carry a credential helper, a default branch name or an `insteadOf` rewrite
    of its own -- out of the measurement.
    """
    env = {key: value for key, value in os.environ.items() if not key.startswith("COV")}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _run(*, argv: list[str], env: dict[str, str], cwd: Path | None = None) -> None:
    """Run a provisioning command for its EFFECT; a non-zero exit is a broken fixture."""
    _ = subprocess.run(argv, cwd=cwd, env=env, check=True, capture_output=True, text=True)


def _capture(*, argv: list[str], env: dict[str, str], cwd: Path | None = None) -> str:
    """Run a provisioning command for its OUTPUT; a non-zero exit is a broken fixture."""
    completed = subprocess.run(argv, cwd=cwd, env=env, check=True, capture_output=True, text=True)
    return completed.stdout.strip()

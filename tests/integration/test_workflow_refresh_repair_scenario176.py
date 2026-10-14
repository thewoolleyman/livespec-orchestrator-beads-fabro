"""The refresh-repair route of `SPECIFICATION/scenarios.md` Scenario 176.

WHAT THIS BINDS. `SPECIFICATION/contracts.md` section "Definition-of-Done and
Proof-of-Done stages" gained two paragraphs at v134 -- "Refresh repair" and
"Refresh-repair accounting". A `publish_draft` or `pr_refresh` stage that cannot
refresh the run onto an advanced default branch, because the rebase conflicts or
because the repository-declared gate rejects the refreshed head, must restore its
pre-refresh head, record a brief and route to the existing `fix` node instead of
ending the run at `needs_human`.

WHY THE MEASUREMENT MATTERS MORE THAN THE SHAPE HERE. Every arm this touches is
SHELL, and a substring assertion cannot tell a restoration arm that RUNS from one
sitting behind an earlier `exit`. The measured motivation is the same
distinction: on hp on 2026-10-13 seven janitor-green runs lost 30.0 slot-hours to
`publish_draft` rebase conflicts, and run 01M4T2KEGPQPAR1XS1KEK91P0E lost 3.3
hours to a pre-push gate failure after a refresh that applied cleanly. So every
behavioural case below executes the shipped script bytes against a REAL throwaway
origin and asserts what happened to real refs; the ROUTING claim is read off the
graph instead, because the stage's own exit says nothing about where the graph
sends it.

THE SCRIPT BYTES ARE READ THROUGH THE CANONICAL PARSER, never retyped: a module
carrying its own copy of the recipe would pass while the shipped stage did
something else. Only the engine's own template tokens are bound, because the
pinned engine owns that expansion rather than this repository, and
`sandbox_check_suite` is a per-repository DECLARATION -- standing a controlled
command in for it stands in for the declaration, not for the stage.

THE ENCLOSING RUN'S STATE IS NEVER TOUCHED. Each case builds its own origin and
clone under `tmp_path`, and the stages resolve their state directory inside THAT
clone's `$GIT_DIR`, which is what makes a nested execution structurally unable to
name the live run's own counters.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_publication_state
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_state import (
    PUBLICATION_STATE_GIT_PATH,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GRAPH_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

_REPAIR_NODE = "refresh_repair"
_DEFAULT_BRANCH = "master"
_BRANCH = "feat/bd-ib-5guqmt"
# The path BOTH sides edit, which is what makes the refresh conflict, and a
# second path only the run touches, so the commit the rebase is applying when it
# stops is NOT the head the stage restores. Were they the same commit, the
# brief's `run-commit` and `pre-refresh-head` fields could not be told apart.
_SHARED_FILE = "shared.txt"
_OWNED_FILE = "owned.txt"
_COVERAGE_ENV_PREFIXES = ("COVERAGE_PROCESS_START", "COV_CORE_")

# The two state filenames the repair writes, spelled as LITERALS here and bound
# to the package's exported names by the case below. A Red's test bytes are fixed
# across its Red-to-Green pair, so a top-level import of a name this change
# INTRODUCES would make the Red a collection error -- which proves the name is
# absent and nothing about the behaviour. The binding assertion is what keeps the
# literals from drifting away from the product.
_BRIEF_FILENAME = "livespec-refresh-repair-brief"
_REPAIR_COUNT_FILENAME = "livespec-refresh-repair-count"


def _graph_text() -> str:
    return _GRAPH_PATH.read_text(encoding="utf-8")


def _successors() -> dict[str, list[tuple[str, str | None]]]:
    """Every node's outgoing `(destination, condition)` pairs, parsed not grepped."""
    graph = parse_dot_graph(text=_graph_text())
    assert not isinstance(graph, str), graph
    edges: dict[str, list[tuple[str, str | None]]] = {name: [] for name in graph.nodes}
    for edge in graph.edges:
        edges[edge.source].append((edge.destination, edge.attributes.get("condition")))
    return edges


def _acyclic_routes(
    *, edges: dict[str, list[tuple[str, str | None]]], start: str, end: str
) -> list[list[str]]:
    """Every acyclic route from `start` to `end`, so an ORDER claim can be graded.

    A reachability test alone cannot express "passes janitor, then publish_draft,
    then proof_capture": a graph routing the repair straight back to publication
    would still reach `pr`. Enumerating the acyclic routes is what makes the order
    assertable, and this graph is small enough that the enumeration is exhaustive
    rather than sampled.
    """
    found: list[list[str]] = []

    def walk(*, node: str, seen: list[str]) -> None:
        if node == end:
            found.append([*seen, node])
            return
        for destination, _ in edges.get(node, []):
            if destination not in seen:
                walk(node=destination, seen=[*seen, node])

    walk(node=start, seen=[])
    return found


def _fixture_env() -> dict[str, str]:
    """The fixture git environment, coverage-scrubbed, with an explicit identity.

    The identity is stated rather than inherited because the factory sandbox
    carries one that differs from a developer's, and a commit with no identity
    fails outright.
    """
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(_COVERAGE_ENV_PREFIXES)
    }
    return {**env, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@example.invalid"}


def _git(*argv: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=_fixture_env(),
    )


def _commit(*, cwd: Path, path: str, text: str, subject: str) -> str:
    """Write one file and commit it, returning the resulting head."""
    _ = _git("config", "user.email", "t@example.invalid", cwd=cwd)
    _ = _git("config", "user.name", "Test", cwd=cwd)
    _ = (cwd / path).write_text(text, encoding="utf-8")
    _ = _git("add", path, cwd=cwd)
    _ = _git("commit", "--quiet", "-m", subject, cwd=cwd)
    return _git("rev-parse", "HEAD", cwd=cwd).stdout.strip()


@dataclass(frozen=True, kw_only=True)
class _World:
    """One case's throwaway world: a real bare origin and a real clone on a run branch."""

    origin: Path
    clone: Path

    def state_dir(self) -> Path:
        return self.clone / ".git" / PUBLICATION_STATE_GIT_PATH

    def state(self, *, name: str) -> str | None:
        path = self.state_dir() / name
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def head(self) -> str:
        return _git("rev-parse", "HEAD", cwd=self.clone).stdout.strip()

    def remote_head(self, *, ref: str) -> str:
        """Origin's own answer for one ref, or the empty string when it holds none."""
        listed = subprocess.run(
            ["git", "ls-remote", "--heads", str(self.origin), f"refs/heads/{ref}"],
            check=True,
            capture_output=True,
            text=True,
            env=_fixture_env(),
        )
        return listed.stdout.split("\t")[0] if listed.stdout.strip() else ""


def _world(*, root: Path) -> _World:
    """An origin carrying the default branch, and a clone on this run's own branch."""
    origin = root / "origin.git"
    origin.mkdir(parents=True)
    _ = _git("init", "--bare", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=origin)
    seed = root / "seed"
    seed.mkdir()
    _ = _git("init", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=seed)
    _ = _commit(cwd=seed, path=_SHARED_FILE, text="base\n", subject="chore: seed")
    _ = _git("push", "--quiet", str(origin), f"HEAD:refs/heads/{_DEFAULT_BRANCH}", cwd=seed)
    clone = root / "clone"
    _ = _git("clone", "--quiet", str(origin), str(clone), cwd=root)
    _ = _git("switch", "--quiet", "-c", "fabro/run/test", cwd=clone)
    return _World(origin=origin, clone=clone)


def _advance_default(*, world: _World, path: str, text: str) -> str:
    """Move origin's default branch through a SEPARATE clone.

    Separate so the case's own clone learns nothing about the movement until the
    stage's own fetch, which is the state a real dispatch is in when the default
    branch advances underneath it.

    The PATH is the case's own choice, and it is what decides whether the refresh
    conflicts: moving the file the run also edited conflicts, and moving any other
    file applies cleanly. Both shapes are needed, because the clause's two repair
    routes differ in exactly that.
    """
    mover = world.clone.parent / "mover"
    _ = _git("clone", "--quiet", str(world.origin), str(mover), cwd=world.clone.parent)
    advanced = _commit(cwd=mover, path=path, text=text, subject=f"feat: advance {path}")
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_DEFAULT_BRANCH}", cwd=mover)
    return advanced


def _refuse_every_push(*, world: _World) -> None:
    """Install a repository pre-push hook that refuses, as a red gate does.

    This repository's declared gate RUNS IN THE PRE-PUSH HOOK, so "the gate
    rejects the refreshed head" reaches the stage as a failed push and nothing
    else. Standing a refusing hook in for it is standing in for the repository's
    own hook configuration, not for the stage: the push really runs, git really
    consults the hook, and the stage really sees the failure it has to classify.
    """
    hook = world.clone / ".git" / "hooks" / "pre-push"
    hook.parent.mkdir(parents=True, exist_ok=True)
    _ = hook.write_text(
        "#!/bin/sh\nprintf '%s\\n' 'the repository gate refused this head' >&2\nexit 1\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)


def _publish_draft_script(*, check_suite: str) -> str:
    graph = parse_dot_graph(text=_graph_text())
    assert not isinstance(graph, str), graph
    script: str = graph.nodes["publish_draft"]["script"]
    return script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH).replace(
        "{{ inputs.sandbox_check_suite }}", check_suite
    )


def _run_publish_draft(
    *, world: _World, check_suite: str = "true", extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Execute the shipped `publish_draft` bytes in this world's clone.

    The environment is EXPLICIT rather than inherited: the subprocess-spawn
    allowlist requires it, and an inherited `LIVESPEC_*` from the enclosing
    factory run could otherwise satisfy a guard the case meant to exercise.
    """
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(world.clone.parent / "home"),
        "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
        # The push-time credential helper's root, pointed at a directory that
        # holds no helper. The sandbox this suite runs inside DOES carry the
        # production helper at the default path, and a case that reached it would
        # measure that helper's own host policy rather than the stage -- and
        # would then measure something different on a CI runner, which carries
        # none. Naming an empty root makes every case take the inline fallback,
        # identically on both.
        "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(world.clone.parent / "no-gh-refresh"),
    }
    return subprocess.run(
        ["bash", "-c", _publish_draft_script(check_suite=check_suite)],
        cwd=world.clone,
        capture_output=True,
        text=True,
        check=False,
        env=env if extra_env is None else {**env, **extra_env},
    )


def _brief_fields(*, world: _World) -> dict[str, str]:
    """The recorded brief as `label -> value`, asserted present as it is read.

    Present rather than defaulted: a reader answering `{}` for an absent brief
    would make "the brief names no such field" and "there is no brief at all"
    produce the identical failure, and those have different causes.
    """
    recorded = world.state(name=_BRIEF_FILENAME)
    assert recorded is not None, "the stage recorded no refresh-repair brief"
    return {
        line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip()
        for line in recorded.splitlines()
        if ":" in line
    }


@dataclass(frozen=True, kw_only=True)
class _Conflicted:
    """A conflicted `publish_draft` refresh, and the four shas that describe it."""

    world: _World
    result: subprocess.CompletedProcess[str]
    janitor_head: str
    applied_commit: str
    advanced_default: str


def _conflicted_draft_refresh(*, root: Path) -> _Conflicted:
    """A janitor-green run whose default branch moved with a conflicting commit.

    The run carries TWO commits and the conflict is in the FIRST, so the commit
    the rebase stops on differs from the head the stage must restore -- which is
    what makes the brief's two sha fields separately assertable.
    """
    world = _world(root=root)
    applied = _commit(
        cwd=world.clone,
        path=_SHARED_FILE,
        text="this run's edit\n",
        subject="feat: edit the shared file",
    )
    janitor_head = _commit(
        cwd=world.clone,
        path=_OWNED_FILE,
        text="this run's own file\n",
        subject="feat: add this run's own file",
    )
    advanced = _advance_default(world=world, path=_SHARED_FILE, text="a conflicting default edit\n")
    return _Conflicted(
        world=world,
        result=_run_publish_draft(world=world),
        janitor_head=janitor_head,
        applied_commit=applied,
        advanced_default=advanced,
    )


def test_a_repair_round_re_earns_janitor_publish_draft_and_capture_before_pr() -> None:
    """The repair round routes through the ordinary fix loop, not around it.

    THE ROUTE IS THE FIRST THING THE CLAUSE REQUIRES, and it is the one claim no
    execution can establish: the stage's own exit says nothing about where the
    graph sends it. So this case grades the committed graph, and it grades the
    ORDER rather than mere reachability -- a repair routed straight back to
    `publish_draft` would reach `pr` just as well while publishing a head no
    janitor had passed and no proof had been captured on.

    The classifier's own two arms are asserted beside it because the order claim
    is vacuous if nothing reaches the route: a node with no `fix` arm has no
    acyclic route to `pr` at all, and an empty enumeration would satisfy a
    universally-quantified assertion. The UNCONDITIONAL arm is the terminal
    deliberately -- a failure the classifier cannot account for must reach a
    human, so entering `fix` requires a positive reading rather than a default.
    """
    edges = _successors()

    assert _REPAIR_NODE in edges, "the graph declares no refresh-repair classifier"
    arms = {condition or "": destination for destination, condition in edges[_REPAIR_NODE]}
    assert arms.get("outcome=succeeded") == "fix"
    assert arms.get("") == "needs_human", "the classifier carries no unconditional arm"

    routes = _acyclic_routes(edges=edges, start=_REPAIR_NODE, end="pr")
    assert routes, "no acyclic route reaches pr from the repair classifier"
    for route in routes:
        for earlier, later in (("janitor", "publish_draft"), ("publish_draft", "proof_capture")):
            assert earlier in route, f"{route} reaches pr without {earlier}"
            assert later in route, f"{route} reaches pr without {later}"
            assert route.index(earlier) < route.index(later), route


def test_a_conflicted_draft_refresh_restores_the_head_janitor_passed(tmp_path: Path) -> None:
    """The conflict is UNDONE, not merely reported, and nothing is published.

    Four instruments, because "it exited non-zero" is what the pre-v134 stage did
    too and is therefore no evidence at all. The working branch must be back at
    the head the janitor passed; no rebase may be left in progress, which would
    wedge every later stage including the `fix` turn this failure now routes to;
    the conflicted file must carry no merge markers, the shape a build that
    resolved by taking one side would leave; and the brief must exist, since the
    classifier routes on it and a restoration that recorded nothing would reach
    needs_human exactly as the old stage did.

    Origin is asserted to carry NO publish branch, which is the claim that
    separates this from a stage that pushed a half-rebased tree: a repair round
    hands the `fix` turn a tree nobody else has seen.
    """
    module = _dispatcher_publication_state
    assert getattr(module, "REFRESH_REPAIR_BRIEF_STATE_FILENAME", None) == _BRIEF_FILENAME
    assert getattr(module, "REFRESH_REPAIR_COUNT_STATE_FILENAME", None) == _REPAIR_COUNT_FILENAME
    assert _BRIEF_FILENAME in module.publication_state_filenames()
    assert _REPAIR_COUNT_FILENAME in module.publication_state_filenames()

    conflicted = _conflicted_draft_refresh(root=tmp_path)
    world = conflicted.world

    assert conflicted.result.returncode != 0, conflicted.result.stdout
    assert "LIVESPEC_REFRESH_REPAIR" in conflicted.result.stderr
    assert world.head() == conflicted.janitor_head
    assert not (world.clone / ".git" / "rebase-merge").exists()
    assert not (world.clone / ".git" / "rebase-apply").exists()
    assert "<<<<<<<" not in (world.clone / _SHARED_FILE).read_text(encoding="utf-8")
    assert world.state(name=_BRIEF_FILENAME) is not None
    assert world.state(name=_REPAIR_COUNT_FILENAME) == "1\n"
    assert world.remote_head(ref=_BRANCH) == ""


def test_the_conflicted_refresh_brief_names_every_field_the_fix_turn_needs(
    tmp_path: Path,
) -> None:
    """Five fields, each read as a VALUE rather than as the presence of a label.

    The clause fixes what the brief must name: the stage, the pre-refresh head,
    the default-branch commit the refresh targeted, each conflicted path, and the
    run commit being applied. A brief carrying the right labels and the wrong
    shas is a work order that sends the `fix` turn at the wrong tree, so every
    field is compared against the sha the fixture itself created.

    The two sha fields are what the fixture's two-commit shape exists for: the
    rebase stops on the FIRST commit while the stage restores the SECOND, so a
    build that reported HEAD for both would agree with a correct one on any
    single-commit run.
    """
    conflicted = _conflicted_draft_refresh(root=tmp_path)
    fields = _brief_fields(world=conflicted.world)

    assert fields.get("stage") == "publish_draft"
    assert fields.get("pre-refresh-head") == conflicted.janitor_head
    assert fields.get("refresh-target") == conflicted.advanced_default
    assert fields.get("run-commit") == conflicted.applied_commit
    assert _SHARED_FILE in (fields.get("conflicted-paths") or "")


def _clean_refresh_world(*, root: Path) -> tuple[_World, str, str]:
    """A janitor-green run whose default branch moved WITHOUT conflicting.

    The run edits the shared file and the default branch adds a different one, so
    the refresh applies cleanly -- which is the precondition both of the cases
    below need, because each is about what happens AFTER a successful refresh.
    """
    world = _world(root=root)
    janitor_head = _commit(
        cwd=world.clone,
        path=_SHARED_FILE,
        text="this run's edit\n",
        subject="feat: edit the shared file",
    )
    advanced = _advance_default(world=world, path=_OWNED_FILE, text="the default's own file\n")
    return world, janitor_head, advanced


def test_a_refreshed_head_the_gate_rejects_is_restored_and_repaired(tmp_path: Path) -> None:
    """A clean refresh whose gate refuses is repaired, not parked.

    This is the SECOND repair route and it is the one most easily left out: the
    refresh succeeded, so there is no conflict to abort and no in-progress
    operation to notice -- the only evidence is that the publishing push was
    refused. Run 01M4T2KEGPQPAR1XS1KEK91P0E lost 3.3 hours to exactly this shape.

    The restoration is the discriminating assertion. A build that routed the
    failure to `fix` without resetting would hand the repair turn the REFRESHED
    head, which is the tree whose gate just failed and which no janitor has
    passed; HEAD back at the janitor-green head is what says the clause's
    "reset the run's working branch" ran. The brief must name the failed gate
    target, because the fix turn cannot reproduce a gate failure it is not told
    about, and the target name is read as a VALUE so a brief carrying the label
    and nothing after it cannot pass.
    """
    world, janitor_head, advanced = _clean_refresh_world(root=tmp_path)
    _refuse_every_push(world=world)

    result = _run_publish_draft(
        world=world,
        check_suite="sh -c 'printf %s\\\\n check-coverage-refused >&2; exit 1'",
    )
    fields = _brief_fields(world=world)

    assert result.returncode != 0, result.stdout
    assert "LIVESPEC_REFRESH_REPAIR" in result.stderr
    assert world.head() == janitor_head
    assert world.remote_head(ref=_BRANCH) == ""
    assert fields.get("stage") == "publish_draft"
    assert fields.get("pre-refresh-head") == janitor_head
    assert fields.get("refresh-target") == advanced
    assert "check-coverage-refused" in (fields.get("failed-gate-targets") or "")
    assert world.state(name=_REPAIR_COUNT_FILENAME) == "1\n"


def test_an_authentication_failure_keeps_its_push_failure_cause(tmp_path: Path) -> None:
    """The one push failure that must NOT be repaired, with the gate red too.

    THE CLAUSE REQUIRES THE STAGE TO DISTINGUISH a gate rejection from a push
    origin refused and from an authentication failure, and this case is what
    makes that a positive reading rather than a residual category. The declared
    gate is deliberately FAILING here: a build that inferred "gate rejection"
    from a failed push plus a failed gate would repair an unreachable origin and
    send the fix turn to resolve a conflict that does not exist, while the real
    cause -- a credential the sandbox never received -- went unreported.

    Three instruments, because the exit code is shared by every arm. The
    existing sentinel must be the one reported; NO brief may exist, since the
    classifier routes on its presence and a brief here is what would enter the
    fix node; and the repair counter must be untouched, because a round that
    spent budget without repairing anything would shorten the next real
    repair's.
    """
    world, janitor_head, _ = _clean_refresh_world(root=tmp_path)
    _ = _git(
        "remote", "set-url", "--push", "origin", "https://example.invalid/repo.git", cwd=world.clone
    )

    result = _run_publish_draft(
        world=world, check_suite="false", extra_env={"GITHUB_APP_ID": "123456"}
    )

    assert result.returncode != 0, result.stdout
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_FAILED" in result.stderr
    assert "LIVESPEC_PUSH_AUTH_ABSENT" in result.stderr, "the push did not fail on credentials"
    assert "LIVESPEC_REFRESH_REPAIR" not in result.stderr
    assert world.state(name=_BRIEF_FILENAME) is None
    assert world.state(name=_REPAIR_COUNT_FILENAME) is None
    assert world.remote_head(ref=_BRANCH) == ""
    # And the tree was NOT restored, which is the mirror of the repair arm's own
    # assertion: a build that reset here took the route this case forbids, and
    # the reset is the one observable that separates the two arms once both have
    # exited non-zero.
    assert world.head() != janitor_head

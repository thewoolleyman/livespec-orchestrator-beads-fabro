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

WHAT v146 ADDED, AND WHY IT IS THE SAME HEADING. The repair round above reaches
`publish_draft` with a head the fix turn REBASED, which makes the run's own
published head a non-ancestor BY CONSTRUCTION -- so the divergent-prior-run
guard refused the very work the repair had just integrated, and three
janitor-green, review-approved runs ended at `needs_human` on released build
v0.201.0 on 2026-10-15 (runs 01M504QX5PJF0VM35DMZT99S2D,
01M504S9SB8A and 01M50903PF06Y07STKF2G0M0K6). v146 narrows that guard: on the
visit that follows a refresh-repair round, a non-ancestor tip EQUAL to the head
this run published is republished under an explicit lease against it, and every
OTHER non-ancestor tip still fails closed. The cases from
`test_a_repaired_refresh_republishes_over_this_run_s_own_published_head` down
bind that narrowing and Scenario 144's mirrored "with no refresh-repair round
before it" sub-scenario.

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
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    PUBLICATION_PUSH_PROGRAM_FILENAME,
    publication_push_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_state import (
    PUBLICATION_STATE_GIT_PATH,
    PUBLISH_HEAD_STATE_FILENAME,
    REFRESH_COUNT_STATE_FILENAME,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
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

# The one edge condition this module grades. Spelled once, because the routing
# claims below are claims about WHICH arm carries it.
_FAILED = "outcome=failed"

# The forge double's body, as LINES rather than one concatenated literal: the
# repository bans implicit string concatenation, and a shell program assembled
# by `+` is one missing newline away from a script that runs a different
# command. `pr list` deliberately prints NOTHING, which is what routes the
# stage onto `pr create` and exercises the draft-opening arm.
_GH_DOUBLE_LINES = (
    "#!/bin/sh",
    'if test "$1 $2" = "pr create"; then',
    "    printf '%s\\n' 'https://example.invalid/o/r/pull/7'",
    "fi",
    "exit 0",
    "",
)


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


def _arms(*, source: str) -> list[tuple[str, dict[str, str]]]:
    """One node's outgoing arms in DECLARATION ORDER, with every attribute.

    `_successors` above projects away everything but the condition, which is all
    a reachability claim needs. An ORDER claim needs the sequence itself, and a
    MIRRORING claim needs the attributes -- two edges that merely share a
    destination and a condition are not the same edge.
    """
    graph = parse_dot_graph(text=_graph_text())
    assert not isinstance(graph, str), graph
    return [
        (edge.destination, dict(edge.attributes)) for edge in graph.edges if edge.source == source
    ]


def _routed(*, source: str, outcome: str) -> str:
    """The successor the graph DETERMINES for one node's reported outcome.

    A matching conditional arm outranks the unconditional fallthrough, and the
    match must be UNIQUE. Declaration order is not something the engine reads,
    so a node carrying two arms with one condition determines no route at all,
    and this reader REFUSES rather than answering with whichever was declared
    first. Answering the first is how this helper reported the repaired route
    while the engine took the other arm (work-item bd-ib-nyovwv): a proof of
    the repaired route built on the old reader would have passed before that
    fix exactly as readily as after it, which makes the refusal the
    load-bearing half of this function rather than a guard on it.

    Nothing here models a term beyond `outcome=`, because the two nodes this
    grades -- a command stage and the classifier -- report nothing else, and a
    richer evaluator would be an evaluator this module never exercises.
    """
    arms = _arms(source=source)
    conditional = [
        destination
        for destination, attributes in arms
        if attributes.get("condition") == f"outcome={outcome}"
    ]
    fallthrough = [destination for destination, attributes in arms if "condition" not in attributes]
    assert fallthrough, f"{source} declares no unconditional fallthrough"
    assert len(conditional) <= 1, (
        f"{source} declares {len(conditional)} arms carrying outcome={outcome}, "
        f"so this graph determines no route for that outcome: {arms}"
    )
    return conditional[0] if conditional else fallthrough[0]


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


def _unarmed_forge_bin(*, world: _World) -> Path:
    """A `gh` on PATH reporting the publish branch's pull request as UNARMED.

    `pr_refresh` reads the auto-merge request before it rebases (v145) and fails
    closed when it cannot, so every case that drives the stage needs a forge that
    answers. Reporting `null` is the state these cases are about: the repair
    route is what is under test here, not the disarm, and an ARMED fixture would
    add a forge write to every assertion about what the repair rewrote. The
    disarm itself is driven in `test_scripted_refresh_execution.py`.
    """
    bin_dir = world.clone.parent / "forge-bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "gh"
    _ = stub.write_text("#!/bin/sh\nprintf 'null\\n'\n", encoding="utf-8")
    stub.chmod(0o755)
    return bin_dir


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


def test_pr_refresh_declares_exactly_one_failed_arm_and_it_is_the_classifier() -> None:
    """ONE failure arm, targeting the classifier, with `needs_human` one node on.

    THIS CASE REPLACES A FALSIFIED ASSUMPTION, which is why it grades a set
    rather than an order. v134's successor (work-item bd-ib-5oc2d3) added the
    `refresh_repair` arm and KEPT the older `pr_refresh -> needs_human` arm
    behind it, on the reading that conditional arms are consulted in
    declaration order so the first matching one wins. The engine does not read
    declaration order. Measured on hp, run 01M4ZMNCDR7FN8SKCC5J3YWPTF: the
    rebase conflicted in four files, the stage restored its pre-refresh head,
    wrote the brief and printed that it expected the fix node, and the engine's
    own `edge.selected` event then read `from_node pr_refresh, to_node
    needs_human, label "Refresh failed or did not converge", reason condition`
    -- the SECOND of the two identically-conditioned arms. The run ended about
    50 seconds later having repaired nothing.

    So the assertion is UNIQUENESS. Two arms carrying one condition leave the
    route undetermined, and an ORDER assertion over such a node grades a
    property the engine never consults -- it passes while the run takes the
    other arm, which is precisely how the defect reached a release. The arms
    carrying `outcome=failed` are therefore compared as a whole against the one
    destination they may hold.

    `needs_human` is asserted ABSENT from `pr_refresh`'s destinations
    altogether, and nothing fail-closed is lost by that: the classifier deletes
    no cause, because `pr_refresh` clears any stale brief at its start and the
    classifier routes to `needs_human` whenever no brief exists, so a missing
    branch, a foreign head, a rejected lease, a failed gate and the
    non-convergence bound all still reach the terminal carrying this stage's own
    cause -- one node later, through an arm this module's sibling case drives.

    The unconditional fallthrough is asserted UNCHANGED beside it, because that
    is the arm an edge removal is most likely to disturb: a node whose every
    outgoing edge carries a condition is the `all_conditional_edges` shape the
    pinned engine rejects outright, before any node runs.
    """
    arms = _arms(source="pr_refresh")
    failed = [
        destination for destination, attributes in arms if attributes.get("condition") == _FAILED
    ]

    assert failed == [_REPAIR_NODE], arms
    assert "needs_human" not in {destination for destination, _ in arms}, arms
    assert [destination for destination, attributes in arms if "condition" not in attributes] == [
        "pr_refresh_head"
    ]


def test_both_refreshing_stages_declare_the_same_failed_outcome_arm() -> None:
    """One classifier, entered the same way from both stages the clause names.

    The clause names `publish_draft` or `pr_refresh` in one breath and the
    classifier is shared, so the two entries have to be the SAME edge rather than
    two edges that happen to agree on a destination -- a differing condition
    would route one stage's conflict to repair and the other's to the terminal
    while every reachability assertion stayed green. The attribute mappings are
    therefore compared whole.

    `publish_draft`'s arms are asserted UNCHANGED, in order, as the control: the
    clause requires the already-shipped half to be untouched, and "both stages
    declare the arm" is satisfied just as well by a change that rewrote the
    working one into agreement with a new mistake.
    """
    draft = _arms(source="publish_draft")
    refresh = _arms(source="pr_refresh")
    entries = {
        source: [attributes for destination, attributes in arms if destination == _REPAIR_NODE]
        for source, arms in (("publish_draft", draft), ("pr_refresh", refresh))
    }

    assert len(entries["publish_draft"]) == 1, draft
    assert len(entries["pr_refresh"]) == 1, refresh
    assert entries["pr_refresh"][0] == entries["publish_draft"][0]
    assert draft == [
        (_REPAIR_NODE, {"label": "Blocked", "condition": _FAILED}),
        ("proof_capture", {}),
    ]


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


def _node_attribute(*, node: str, attribute: str) -> str:
    """One node's attribute value, parsed rather than grepped out of the text."""
    graph = parse_dot_graph(text=_graph_text())
    assert not isinstance(graph, str), graph
    value: str = graph.nodes[node][attribute]
    return value


def _pr_refresh_script(*, check_suite: str) -> str:
    graph = parse_dot_graph(text=_graph_text())
    assert not isinstance(graph, str), graph
    script: str = graph.nodes["pr_refresh"]["script"]
    return script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH).replace(
        "{{ inputs.sandbox_check_suite }}", check_suite
    )


def _published_run(*, root: Path) -> tuple[_World, str, str]:
    """A run whose proof was verified on a head origin's publish branch carries.

    This is the state `pr_refresh` is entered in: the branch exists on origin at
    the head this run published, and the run's own publication record names it --
    which is what the stage establishes its pre-refresh head from, and therefore
    what it must restore.
    """
    world = _world(root=root)
    published = _commit(
        cwd=world.clone,
        path=_SHARED_FILE,
        text="this run's edit\n",
        subject="feat: edit the shared file",
    )
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=world.clone)
    world.state_dir().mkdir(parents=True, exist_ok=True)
    _ = (world.state_dir() / PUBLISH_HEAD_STATE_FILENAME).write_text(published, encoding="utf-8")
    advanced = _advance_default(world=world, path=_SHARED_FILE, text="a conflicting default edit\n")
    return world, published, advanced


def test_a_conflicted_pr_refresh_restores_its_published_head_and_counts_a_refresh(
    tmp_path: Path,
) -> None:
    """The second refreshing stage repairs too, and its visit still counts.

    `pr_refresh` restores a DIFFERENT head from `publish_draft`: the clause names
    the run's previously published head, established from its publication record,
    rather than the head a janitor passed -- which is what also covers a resumed
    run with no janitor visit of its own. The brief's `pre-refresh-head` is
    therefore compared against the head origin's publish branch carries.

    THE COUNTED REFRESH IS THE ASSERTION MOST EASILY LEFT OUT, and leaving it out
    is unbounded: the accounting paragraph counts each `pr_refresh` visit that
    refreshes onto an advanced default WHETHER OR NOT the refresh succeeded, so a
    repair that skipped the increment would let a run alternate repair and
    refresh past the three-refresh non-convergence bound forever. The two
    counters are read separately, because they bound different things and a build
    that incremented one in place of the other would satisfy a single reading.

    Origin's publish branch is asserted UNMOVED, which is what says the repair
    rewrote nothing a reviewer or the merge path can see.
    """
    world, published, advanced = _published_run(root=tmp_path)

    result = subprocess.run(
        ["bash", "-c", _pr_refresh_script(check_suite="true")],
        cwd=world.clone,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{_unarmed_forge_bin(world=world)}:/usr/local/bin:/usr/bin:/bin",
            "HOME": str(world.clone.parent / "home"),
            "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
            "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(world.clone.parent / "no-gh-refresh"),
        },
    )
    fields = _brief_fields(world=world)

    assert result.returncode != 0, result.stdout
    assert "LIVESPEC_REFRESH_REPAIR" in result.stderr
    assert world.head() == published
    assert not (world.clone / ".git" / "rebase-merge").exists()
    assert not (world.clone / ".git" / "rebase-apply").exists()
    assert fields.get("stage") == "pr_refresh"
    assert fields.get("pre-refresh-head") == published
    assert fields.get("refresh-target") == advanced
    assert _SHARED_FILE in (fields.get("conflicted-paths") or "")
    assert world.state(name=_REPAIR_COUNT_FILENAME) == "1\n"
    assert world.state(name=REFRESH_COUNT_STATE_FILENAME) == "1\n"
    assert world.remote_head(ref=_BRANCH) == published


def _refresh_repair_script() -> str:
    """The shipped classifier's own script bytes; it consumes no engine token."""
    graph = parse_dot_graph(text=_graph_text())
    assert not isinstance(graph, str), graph
    script: str = graph.nodes[_REPAIR_NODE]["script"]
    assert "{{" not in script, script
    return script


def _run_refresh_repair(*, world: _World) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", _refresh_repair_script()],
        cwd=world.clone,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(world.clone.parent / "home")},
    )


def test_a_conflicted_pr_refresh_resolves_through_the_classifier_to_fix(tmp_path: Path) -> None:
    """END TO END across the seam the defect sat in: stage, route, classifier, route.

    Neither half can establish this alone, which is why they are composed here
    rather than asserted apart. The stage's own exit says nothing about where the
    graph sends it -- the measured failure is a stage that did everything right
    and was routed to the terminal anyway -- and the graph says nothing about
    whether a real conflicted refresh leaves the artifact the classifier reads.
    So the shipped `pr_refresh` bytes run against a real conflicted origin, its
    real non-zero outcome picks a real arm, the shipped classifier bytes then run
    in THAT world, and its real zero outcome picks the next arm. `fix` is the
    node that composition has to land on.

    THE CONTROL IS THE SAME CLASSIFIER IN THE SAME WORLD WITH THE BRIEF REMOVED,
    and it is load-bearing twice over. "Resolves to `fix` rather than
    `needs_human`" is a claim about a choice, so the terminal has to be reachable
    for the choice to exist -- without the control, a classifier hard-wired to
    exit zero would satisfy every assertion above it. And it is what keeps the
    new arm a POSITIVE reading: an authentication failure or an unreachable
    origin exits non-zero exactly as a conflict does and writes no brief, and
    those causes must still reach a human with their own account.
    """
    world, published, _advanced = _published_run(root=tmp_path)

    refresh = subprocess.run(
        ["bash", "-c", _pr_refresh_script(check_suite="true")],
        cwd=world.clone,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{_unarmed_forge_bin(world=world)}:/usr/local/bin:/usr/bin:/bin",
            "HOME": str(world.clone.parent / "home"),
            "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
            "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(world.clone.parent / "no-gh-refresh"),
        },
    )

    # The stage really failed, really restored, and really left the one artifact
    # the classifier routes on -- the premise every assertion below rides on.
    assert refresh.returncode != 0, refresh.stdout
    assert world.head() == published
    brief = world.state_dir() / _BRIEF_FILENAME
    assert brief.is_file()

    assert _routed(source="pr_refresh", outcome="failed") == _REPAIR_NODE

    classifier = _run_refresh_repair(world=world)
    assert classifier.returncode == 0, classifier.stderr
    assert "LIVESPEC_REFRESH_REPAIR_PENDING" in classifier.stderr
    assert _routed(source=_REPAIR_NODE, outcome="succeeded") == "fix"

    # The control: the brief gone, everything else identical.
    brief.unlink()
    absent = _run_refresh_repair(world=world)
    assert absent.returncode != 0
    assert "LIVESPEC_REFRESH_REPAIR_ABSENT" in absent.stderr
    assert _routed(source=_REPAIR_NODE, outcome="failed") == "needs_human"


def test_a_repair_round_is_budgeted_apart_from_the_review_fix_rounds() -> None:
    """The repair's two rounds are ADDED to the fix budget, not taken from review-fix.

    The accounting paragraph says both halves and each needs its own instrument.
    `fix.max_visits` must ACCOMMODATE the two repair rounds in addition to what
    its other entry paths already allow, so the value is asserted as exactly two
    apiece for the three agent-finding producers PLUS two -- an inequality would
    be satisfied by a budget widened by any amount, including one that re-opened
    the starvation the two-apiece sizing closed.

    And a refresh-repair round must consume no review-fix round. That is read as
    a REACHABILITY claim rather than from the two budgets alone: `review_fix` and
    `disposition` holding their value is equally true of a graph whose repair
    route ran through them and happened not to widen them, so the discriminating
    assertion is that no arm of the classifier reaches either node.
    """
    edges = _successors()
    producers = {
        source for source, arms in edges.items() for destination, _ in arms if destination == "fix"
    }
    budgets = {
        node: int(_node_attribute(node=node, attribute="max_visits"))
        for node in ("fix", "disposition", "review_fix")
    }

    assert _REPAIR_NODE in producers
    assert budgets["fix"] == 2 * len(producers - {_REPAIR_NODE}) + 2
    assert budgets["disposition"] == 3
    assert budgets["review_fix"] == 3
    assert {destination for destination, _ in edges[_REPAIR_NODE]}.isdisjoint(
        {"review_fix", "disposition"}
    )


def test_a_third_refresh_needing_repair_ends_at_needs_human_exhausted(
    tmp_path: Path,
) -> None:
    """The budget is two rounds, and the third says so by name with a pointer.

    The counter is seeded at the budget rather than reached by driving two real
    repairs, because what this case grades is the DECISION at the third, and two
    live rounds would make the fixture a test of the increment instead.

    THE ABSENT BRIEF IS THE LOAD-BEARING ASSERTION. The classifier routes on the
    brief's presence, so a third round that wrote one would re-enter `fix` while
    reporting exhaustion -- green-looking output over an unbounded loop. The
    reason file is asserted to name both the cause and the pre-refresh head,
    because the `needs_human` terminal reads its first line and that line is the
    only account of the run a human gets; and the head is still RESTORED, since
    the pointer names a head the preserved tree has to actually carry.
    """
    world = _world(root=tmp_path)
    world.state_dir().mkdir(parents=True, exist_ok=True)
    _ = (world.state_dir() / _REPAIR_COUNT_FILENAME).write_text("2\n", encoding="utf-8")
    janitor_head = _commit(
        cwd=world.clone,
        path=_SHARED_FILE,
        text="this run's edit\n",
        subject="feat: edit the shared file",
    )
    _ = _advance_default(world=world, path=_SHARED_FILE, text="a conflicting default edit\n")

    result = _run_publish_draft(world=world)
    reason = (world.clone / ".git" / "livespec-needs-human-reason").read_text(encoding="utf-8")

    assert result.returncode != 0, result.stdout
    assert "LIVESPEC_REFRESH_REPAIR_EXHAUSTED" in result.stderr
    assert world.state(name=_BRIEF_FILENAME) is None
    assert world.state(name=_REPAIR_COUNT_FILENAME) == "2\n"
    assert reason.splitlines()[0].startswith("refresh-repair-exhausted:")
    assert janitor_head in reason.splitlines()[0]
    assert world.head() == janitor_head


def _materialized_push_program(*, root: Path) -> Path:
    """A sandbox plugins root carrying the PRODUCTION exact-head push helper.

    Written from its own source rather than restated here, so the lease the
    republication performs is the lease the Dispatcher ships. The root is handed
    to the stage through `LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT`, which is the
    channel the stage itself resolves.
    """
    plugins_root = root / "plugins"
    plugins_root.mkdir(parents=True, exist_ok=True)
    program = plugins_root / PUBLICATION_PUSH_PROGRAM_FILENAME
    _ = program.write_text(publication_push_program_source(), encoding="utf-8")
    program.chmod(0o700)
    return plugins_root


def _forge_double(*, root: Path) -> Path:
    """A `gh` that answers the two calls a SUCCEEDING publish makes, and nothing else.

    Every pre-v146 case in this module fails before the stage reaches the forge,
    so none of them needed one. The republication arm is the first case here that
    runs to exit 0, and the forge is the only boundary it cannot reach for real:
    `pr list` answering nothing routes the stage onto `pr create`, whose printed
    URL the stage reads the number out of.
    """
    bin_dir = root / "forge-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    gh = bin_dir / "gh"
    _ = gh.write_text("\n".join(_GH_DOUBLE_LINES), encoding="utf-8")
    gh.chmod(0o755)
    return bin_dir


@dataclass(frozen=True, kw_only=True)
class _Repaired:
    """A resumed run whose conflicted `pr_refresh` its fix turn then repaired."""

    world: _World
    published_head: str
    repaired_head: str
    advanced_default: str
    plugins_root: Path
    forge_bin: Path


def _repaired_run(*, root: Path, push_program: bool) -> _Repaired:
    """Drive the real conflict, then perform the fix turn's own integration.

    The premise this clause is about cannot be arranged by hand without
    assuming it: the published head has to be a NON-ANCESTOR of the repaired
    head, and it is one only because a real rebase moved the run's commit onto
    the advanced default. So the shipped `pr_refresh` bytes run against a real
    origin to produce the conflict and the brief, and the fix turn's three
    instructed steps -- fetch the default branch, rebase onto it, resolve the
    conflicted path on its merits -- are then performed in the same clone.

    The non-ancestry is ASSERTED rather than assumed: a fixture whose repaired
    head still contained the published head would make every case below pass
    through the fast-forward arm while reporting the republication arm green.

    `push_program` is REQUIRED rather than defaulted, as every fixture parameter
    at this tier is: the absent-helper arm is what makes a plain fast-forward
    distinguishable from a lease, so a default would make one case's premise
    silently another's.
    """
    world, published, advanced = _published_run(root=root)

    refresh = subprocess.run(
        ["bash", "-c", _pr_refresh_script(check_suite="true")],
        cwd=world.clone,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(world.clone.parent / "home"),
            "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
            "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(world.clone.parent / "no-gh-refresh"),
        },
    )
    assert refresh.returncode != 0, refresh.stdout
    assert world.head() == published, "pr_refresh did not restore the published head"
    assert world.state(name=_BRIEF_FILENAME) is not None, "pr_refresh recorded no brief"

    _ = _git("fetch", "origin", _DEFAULT_BRANCH, cwd=world.clone)
    conflicted = subprocess.run(
        ["git", "rebase", f"origin/{_DEFAULT_BRANCH}"],
        cwd=world.clone,
        capture_output=True,
        text=True,
        check=False,
        env=_fixture_env(),
    )
    assert conflicted.returncode != 0, conflicted.stdout
    _ = (world.clone / _SHARED_FILE).write_text(
        "this run's edit and the default's, integrated\n", encoding="utf-8"
    )
    _ = _git("add", _SHARED_FILE, cwd=world.clone)
    _ = _git("-c", "core.editor=true", "rebase", "--continue", cwd=world.clone)
    repaired = world.head()

    contains = subprocess.run(
        ["git", "merge-base", "--is-ancestor", published, repaired],
        cwd=world.clone,
        capture_output=True,
        text=True,
        check=False,
        env=_fixture_env(),
    )
    assert contains.returncode != 0, "the repaired head still contains the published head"

    return _Repaired(
        world=world,
        published_head=published,
        repaired_head=repaired,
        advanced_default=advanced,
        plugins_root=(
            _materialized_push_program(root=root) if push_program else root / "absent-plugins"
        ),
        forge_bin=_forge_double(root=root),
    )


def _run_repaired_publish_draft(
    *, repaired: _Repaired, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """The shipped `publish_draft` bytes, with the forge double and the plugins root."""
    env = {
        "PATH": f"{repaired.forge_bin}:/usr/local/bin:/usr/bin:/bin",
        SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(repaired.plugins_root),
    }
    return _run_publish_draft(
        world=repaired.world, extra_env=env if extra_env is None else {**env, **extra_env}
    )


def _foreign_publish_tip(*, world: _World) -> str:
    """Move origin's publish branch to a head no run of this item ever published."""
    other = world.clone.parent / "foreign"
    _ = _git("clone", "--quiet", str(world.origin), str(other), cwd=world.clone.parent)
    _ = _git("switch", "--quiet", "-c", "foreign-run", cwd=other)
    tip = _commit(
        cwd=other, path="foreign.txt", text="another run's work\n", subject="feat: foreign work"
    )
    _ = _git("push", "--quiet", "--force", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=other)
    return tip


def test_a_repaired_refresh_republishes_over_this_run_s_own_published_head(
    tmp_path: Path,
) -> None:
    """The measured loss, made green: the repaired head reaches capture, leased.

    SIX INSTRUMENTS, because "it exited zero" is satisfied by a stage that
    pushed nothing at all. Origin's publish branch must carry the REPAIRED head,
    which is the whole point and the one thing the pre-v146 stage could not do;
    the publication record must name it, since `pr` compares the pull request
    head against that record and a republication the record did not follow would
    fail there instead; the stage's own sentinel must name the published head it
    leased against, so the republication is readable in a transcript rather than
    inferred from a moved ref; and the working branch must be UNMOVED, because a
    stage that rebased the repair away would publish a head the janitor never
    passed.

    THE CONSUMED BRIEF IS THE ASSERTION MOST EASILY LEFT OUT and it is what
    bounds the capability to this ONE visit: the brief is the only thing that
    distinguishes a repaired visit from an ordinary one, so a visit that left it
    behind would grant every later visit of the same run the same rewrite.

    The route is read off the graph, as everywhere in this module: the stage's
    own exit says nothing about where the graph sends it, and the clause's last
    assertion is that the repaired head reaches `proof_capture` rather than
    `needs_human`.
    """
    repaired = _repaired_run(root=tmp_path, push_program=True)
    world = repaired.world

    result = _run_repaired_publish_draft(repaired=repaired)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_REPAIR_REPUBLISH" in result.stderr
    assert repaired.published_head in result.stderr
    assert world.remote_head(ref=_BRANCH) == repaired.repaired_head
    assert world.head() == repaired.repaired_head
    assert world.state(name=PUBLISH_HEAD_STATE_FILENAME) == f"{repaired.repaired_head}\n"
    assert world.state(name=_BRIEF_FILENAME) is None
    assert _routed(source="publish_draft", outcome="succeeded") == "proof_capture"


def test_a_repair_round_may_establish_its_published_head_from_resume_provenance(
    tmp_path: Path,
) -> None:
    """The second head source the clause names, beside the control that it is needed.

    A run RESUMED from a published pull request may never have visited
    `publish_draft`, so it holds no publication record of its own and the clause
    names its validated resume provenance as the fallback. Both legs run on their
    OWN repaired world rather than on one world twice, because the enabling
    brief is CONSUMED at entry -- a second leg in the same world would be
    deciding on a brief this test wrote rather than one a stage did.

    THE CONTROL IS WHAT MAKES THE FALLBACK EVIDENCE. With the publication record
    removed and no provenance supplied the head cannot be established at all,
    and the clause requires the divergent-prior-run refusal there; without that
    leg, "the provenance leg republished" is equally consistent with a build
    that republishes over any non-ancestor tip it meets after a repair.
    """
    provenance = _repaired_run(root=tmp_path / "provenance", push_program=True)
    (provenance.world.state_dir() / PUBLISH_HEAD_STATE_FILENAME).unlink()

    resumed = _run_repaired_publish_draft(
        repaired=provenance,
        extra_env={"LIVESPEC_RESUME_PUBLISHED_HEAD": provenance.published_head},
    )

    assert resumed.returncode == 0, resumed.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_REPAIR_REPUBLISH" in resumed.stderr
    assert provenance.world.remote_head(ref=_BRANCH) == provenance.repaired_head

    unestablished = _repaired_run(root=tmp_path / "unestablished", push_program=True)
    (unestablished.world.state_dir() / PUBLISH_HEAD_STATE_FILENAME).unlink()

    refused = _run_repaired_publish_draft(repaired=unestablished)

    assert refused.returncode != 0, refused.stdout
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_FAILED" in refused.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_REPAIR_REPUBLISH" not in refused.stderr
    assert unestablished.world.remote_head(ref=_BRANCH) == unestablished.published_head


def test_publish_draft_still_refuses_a_foreign_divergent_tip_after_a_repair(
    tmp_path: Path,
) -> None:
    """The narrowing is a NARROWING: a tip this run did not publish still refuses.

    This is the sub-scenario that keeps the new arm a POSITIVE reading of the
    run's own provenance rather than a relaxation of the ancestry guard. The
    world is the republication world with origin's publish branch moved to a head
    no run of this item ever published, so the ONLY difference from the green
    case above is which sha origin carries.

    Origin's tip is asserted UNMOVED and the working branch too, because the
    clause requires the refusal to push NOTHING -- a build that leased over a
    foreign tip and then reported a failure would satisfy the exit code alone.
    """
    repaired = _repaired_run(root=tmp_path, push_program=True)
    world = repaired.world
    foreign = _foreign_publish_tip(world=world)

    result = _run_repaired_publish_draft(repaired=repaired)

    assert result.returncode != 0, result.stdout
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_FAILED" in result.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_REPAIR_REPUBLISH" not in result.stderr
    assert world.remote_head(ref=_BRANCH) == foreign
    assert world.head() == repaired.repaired_head


def test_a_repaired_visit_pushes_a_plain_fast_forward_when_it_owes_no_rewrite(
    tmp_path: Path,
) -> None:
    """The two unchanged arms of the repaired visit, proved by WITHHOLDING the helper.

    The clause keeps both pre-v146 arms: an absent remote tip and a tip that is
    an ancestor of the repaired head are each published by a plain
    fast-forward. "A plain fast-forward rather than a lease" is otherwise hard to
    observe -- both arms move the ref to the same sha -- so the discriminator is
    the exact-head push helper, WITHHELD from the sandbox plugins root. A build
    that took the lease route on either arm fails closed naming the absent
    helper, which is an assertion the moved ref cannot make on its own.

    The two arms are one case because each is the other's control for that
    discriminator: the absent-tip arm never reaches the ancestry test at all, so
    on its own it would pass against a build whose ancestry arm leased.
    """
    absent = _repaired_run(root=tmp_path / "absent-tip", push_program=False)
    _ = _git("push", "origin", "--delete", f"refs/heads/{_BRANCH}", cwd=absent.world.clone)
    assert absent.world.remote_head(ref=_BRANCH) == ""

    created = _run_repaired_publish_draft(repaired=absent)

    assert created.returncode == 0, created.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_REPAIR_REPUBLISH" not in created.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_PROGRAM_ABSENT" not in created.stderr
    assert absent.world.remote_head(ref=_BRANCH) == absent.repaired_head

    ancestor = _repaired_run(root=tmp_path / "ancestor-tip", push_program=False)
    _ = _git(
        "push",
        "--force",
        "origin",
        f"{ancestor.advanced_default}:refs/heads/{_BRANCH}",
        cwd=ancestor.world.clone,
    )
    assert ancestor.world.remote_head(ref=_BRANCH) == ancestor.advanced_default

    advanced = _run_repaired_publish_draft(repaired=ancestor)

    assert advanced.returncode == 0, advanced.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_REPAIR_REPUBLISH" not in advanced.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_PROGRAM_ABSENT" not in advanced.stderr
    assert ancestor.world.remote_head(ref=_BRANCH) == ancestor.repaired_head


def test_a_visit_following_no_repair_round_never_rewrites_the_publish_branch(
    tmp_path: Path,
) -> None:
    """Scenario 144's narrowed sub-scenario, as the republication world minus the brief.

    A `publish_draft` visit reached through a review-fix round, or through any
    other path, follows no refresh-repair round -- and it reaches the stage in
    exactly this state, because the brief is the only artifact that marks a
    repaired visit and no other route writes one. So the world here is the green
    republication world with the brief REMOVED and nothing else changed, which
    is what makes the refusal evidence about the brief rather than about
    anything else the fixture happens to carry.

    The exact-head helper is PRESENT, deliberately: the refusal has to come from
    the absent brief and not from an unavailable lease, and a world without the
    helper could not tell those apart.
    """
    repaired = _repaired_run(root=tmp_path, push_program=True)
    world = repaired.world
    (world.state_dir() / _BRIEF_FILENAME).unlink()

    result = _run_repaired_publish_draft(repaired=repaired)

    assert result.returncode != 0, result.stdout
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_FAILED" in result.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_REPAIR_REPUBLISH" not in result.stderr
    assert world.remote_head(ref=_BRANCH) == repaired.published_head
    assert world.head() == repaired.repaired_head


def test_the_fix_node_instructions_forbid_the_fix_turn_from_rewriting_any_ref() -> None:
    """The fix turn's own permission is WITHDRAWN, and the prompt says so.

    v134's prompt let the fix turn "rewrite no ref other than this run's own
    publish branch under an explicit lease", which v146 withdraws: the
    republication is `publish_draft`'s, under a lease against a head the fix turn
    cannot establish, and a fix turn that rewrote the branch itself would move it
    to a head no janitor had passed and no proof had been captured on.

    BOTH DIRECTIONS ARE GRADED, because neither is sufficient. The positive
    needle is a literal copied from the shipped prose and sits within ONE
    physical line, since the prompt is hard-wrapped and a needle straddling a
    break fails silently while the prose says exactly the thing. The absence
    needle is the superseded clause's own opening, likewise one line: without
    it, the positive assertion passes over a prompt that carries both sentences
    and so permits what the clause forbids.
    """
    prose = (_GRAPH_PATH.parent / "prompts" / "fix.md").read_text(encoding="utf-8")

    assert "and rewrite no ref at all" in prose
    assert "rewrite no ref other than" not in prose

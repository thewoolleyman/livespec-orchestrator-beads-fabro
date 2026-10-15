"""Scenario 184 — a default branch that advances between `pr_refresh` and the arming.

`SPECIFICATION/scenarios.md` Scenario 184 and `SPECIFICATION/contracts.md`
section "Definition-of-Done and Proof-of-Done stages" (v145) absorb
default-branch movement that arrives AFTER the refresh inside the run: the `pr`
stage records a refresh-route marker, the `pr_route` command node turns that
marker into an edge back to `pr_refresh`, and only a rejection the measurements
cannot attribute to an advanced default branch still fails closed.

WHY THESE CASES EXECUTE THE SHIPPED BYTES AGAINST REAL GIT AND A REAL ORIGIN.
The whole decision is three measurements and a comparison between them — the
pull request's current head, the forge's mergeability report, and the
authoritative default branch's tip read from a FETCH of origin — followed by
`git merge-base --is-ancestor`. A declaration test over the `script` attribute
cannot tell a guard that runs from dead code behind an earlier `exit`, and a
test whose git was a double would exercise the ladder while leaving the ancestry
reading — the half a reader cannot check by eye — unexercised. So each control
below builds a real bare origin, a real clone carrying the publish branch, real
commits, and advances the default branch through a SEPARATE clone so this
clone learns nothing about the movement until the stage's own fetch.

WHAT IS SIMULATED, AND WHY EACH SUBSTITUTION IS SAFE.

- `{{ inputs.X }}` is substituted here because the pinned ENGINE owns that
  templating, not this repository. The values used are the ones `workflow.toml`
  declares. Nothing else in the bytes is touched.
- `gh` is a STUB on `PATH`, because the controls turn on forge answers no real
  forge can be driven through on demand: an arming the forge REJECTS while the
  pull request stays OPEN, a head that moves between the observation and the
  arming, and a forge that cannot report the head at all. The stub records
  every argv it receives, so what the stage ASKED is itself under assertion.
- The publication-head program is NOT stubbed: each control materializes the
  genuine `proof_head_program_source()` and the stage re-enters it by the path
  the overlay names, so the proof-identity half runs its real reader over real
  record text.

THE SCRIPT BYTES ARE READ THROUGH THE CANONICAL PARSER, NEVER RETYPED, with
`parse_dot_graph` — the same reader the Dispatcher's own graph consumers use.

THE ENCLOSING RUN'S STATE IS NEVER TOUCHED: every control builds its own
throwaway origin and clone under `tmp_path`, and both stages resolve their state
directory inside THAT clone's `$GIT_DIR`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_head import (
    PROOF_HEAD_PROGRAM_FILENAME,
    proof_head_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_state import (
    PUBLICATION_STATE_GIT_PATH,
    PUBLISH_HEAD_STATE_FILENAME,
    publication_state_filenames,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    PUBLISH_HEAD_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IMPLEMENT_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

_BRANCH = "feat/bd-ib-3hpdvm"
_DEFAULT_BRANCH = "master"
_PR_NUMBER = 5184
_OWNED_FILE = "owned.txt"
_SHARED_FILE = "shared.txt"
# The forge's own wording for the rejection this scenario is about. Carried as a
# constant because two controls assert it reaches the diagnostic line VERBATIM,
# which is the clause's own word.
_REJECTION = "failed to merge: Pull request is not mergeable"

# The two state filenames this route adds, spelled here as the LITERALS the
# shipped shell spells them with — a stage script cannot import a Python
# constant, so the literal is what is actually under test. They are bound to the
# product surface by `test_the_two_new_state_files_are_declared_with_the_rest`
# below rather than imported, so a rename that moved only one of the two still
# fails here instead of passing against a constant nothing reads.
_VISIT_COUNT_FILENAME = "livespec-pr-visit-count"
_ROUTE_MARKER_FILENAME = "livespec-pr-refresh-route"

# The coverage hooks an allowlisted spawn must scrub, so no child of this file
# self-instruments and races the concurrent coverage run.
_COVERAGE_ENV_PREFIXES = ("COVERAGE_PROCESS_START", "COV_CORE_")

# The forge stub. A PROGRAM rather than an in-process mock because both the
# stage and the publication-head program it re-enters reach `gh` through `PATH`.
#
# `reject_merge` is what makes this scenario expressible: the forge rejects the
# head-bound arming while the pull request stays OPEN at the head it was bound
# to, which is exactly the shape an advanced default branch produces and which
# no head comparison can distinguish on its own.
#
# `advance_head_on` moves the branch strictly BETWEEN the observation and the
# arming, and the two unreadable-field sets make one `--json` field unanswerable,
# so the "could not measure" arms are driven rather than reasoned about.
#
# THE TWO SETS ARE NOT INTERCHANGEABLE, and the second exists because the first
# cannot reach the arm under test. `unreadable_fields` fails a field from the
# first call onward, which for `headRefOid` makes the stage refuse at its OWN
# identity check long before any arming — a refusal under a different sentinel,
# about a different question. `unreadable_after_merge` fails the field only once
# a `pr merge` has been issued, which is the real shape of a forge that answered
# the observation and then stopped answering: the arming is reached, rejected,
# and the RE-READ is what cannot be taken.
_GH_STUB = r"""#!%(python)s
import json, os, sys

state_path = os.environ["LIVESPEC_FAKE_FORGE"]


def load():
    with open(state_path) as handle:
        return json.load(handle)


def save(state):
    with open(state_path, "w") as handle:
        json.dump(state, handle)


def flag(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


argv = sys.argv[1:]
state = load()
state["calls"].append(argv)

if state.get("advance_head_on") and argv[:2] == ["pr", state["advance_head_on"]]:
    state["head"] = state.pop("advance_head_to")
    state["advance_head_on"] = None

verb = argv[1] if len(argv) > 1 else ""

if verb == "list":
    save(state)
    number = state.get("number")
    print("null" if number is None else number)
    sys.exit(0)

if verb == "view":
    field = flag(argv, "--json")
    answers = {
        "state": state["state"],
        "headRefOid": state["head"],
        "mergeStateStatus": state["mergeStateStatus"],
        "isDraft": "true" if state["isDraft"] else "false",
        "autoMergeRequest": "null" if state["autoMergeRequest"] is None else "{}",
        "mergeCommit": state["mergeCommit"] or "",
    }
    save(state)
    if field == "comments":
        print(json.dumps({"comments": state["comments"]}))
        sys.exit(0)
    armed_already = any(call[:2] == ["pr", "merge"] for call in state["calls"])
    declined = state["unreadable_fields"] + (
        state["unreadable_after_merge"] if armed_already else []
    )
    if field in declined:
        sys.stderr.write("the forge declined to report %%s\n" %% field)
        sys.exit(1)
    if field not in answers:
        sys.stderr.write("unstubbed --json field: %%s\n" %% field)
        sys.exit(2)
    print(answers[field])
    sys.exit(0)

if verb == "edit":
    save(state)
    sys.exit(0)

if verb == "ready":
    state["isDraft"] = False
    save(state)
    sys.exit(0)

if verb == "merge":
    required = flag(argv, "--match-head-commit")
    if required is not None and required != state["head"]:
        save(state)
        sys.stderr.write(
            "failed to merge: Head of pull request #%%s is not %%s\n"
            %% (state["number"], required)
        )
        sys.exit(1)
    if state["reject_merge"]:
        save(state)
        sys.stderr.write(state["reject_merge"] + "\n")
        sys.exit(1)
    state["autoMergeRequest"] = {"enabledAt": "now"}
    save(state)
    sys.exit(0)

sys.stderr.write("unstubbed gh invocation: %%s\n" %% " ".join(argv))
sys.exit(2)
"""


def _fixture_git_env() -> dict[str, str]:
    """The fixture environment, coverage-scrubbed, with an explicit git identity."""
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
        env=_fixture_git_env(),
    )


def _commit(*, cwd: Path, path: str, text: str, subject: str) -> str:
    _ = _git("config", "user.email", "t@example.invalid", cwd=cwd)
    _ = _git("config", "user.name", "Test", cwd=cwd)
    _ = (cwd / path).write_text(text, encoding="utf-8")
    _ = _git("add", path, cwd=cwd)
    _ = _git("commit", "--quiet", "-m", subject, cwd=cwd)
    return _git("rev-parse", "HEAD", cwd=cwd).stdout.strip()


def _node_script(*, node: str) -> str:
    """One shipped node's script, with only the engine's own tokens bound."""
    graph = parse_dot_graph(text=_IMPLEMENT_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script = graph.nodes[node]["script"]
    return (
        script.replace("{{ inputs.merge_mode }}", "rebase")
        .replace("{{ inputs.merge_hold }}", "false")
        .replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH)
    )


def _record(*, verdict: str, head: str) -> dict[str, str]:
    """One Proof of Done comment, in the header shape the real reader requires."""
    return {
        "body": (
            f"Proof of Done — {verdict} — run r — 2026-10-15T00:00:00Z\n"
            f"{PUBLISH_HEAD_LABEL}: {head}\n"
        )
    }


@dataclass(frozen=True, kw_only=True)
class _Route:
    """One control's throwaway world: a real origin, a real clone, a stub forge."""

    origin: Path
    clone: Path
    plugins_root: Path
    forge_state: Path
    bin_dir: Path

    def state_dir(self) -> Path:
        return self.clone / ".git" / PUBLICATION_STATE_GIT_PATH

    def head(self) -> str:
        return _git("rev-parse", "HEAD", cwd=self.clone).stdout.strip()

    def forge(self) -> dict[str, object]:
        return json.loads(self.forge_state.read_text(encoding="utf-8"))

    def state(self, *, name: str) -> str | None:
        path = self.state_dir() / name
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def merge_argvs(self) -> list[list[str]]:
        """Every `gh pr merge` argv the stage issued, in order.

        A LIST rather than an optional first hit, so a control that expects no
        arming and one that expects a bound arming read the same accessor: an
        optional accessor's empty answer is a branch no case here can take,
        which is a shape this tier's own coverage gate reads as untested code.
        """
        recorded = cast("list[list[str]]", self.forge()["calls"])
        return [call for call in recorded if call[:2] == ["pr", "merge"]]


def _build(
    *,
    root: Path,
    reject_merge: str | None = _REJECTION,
    advance_head_on: str | None = None,
    unreadable_fields: tuple[str, ...] = (),
    unreadable_after_merge: tuple[str, ...] = (),
    merge_state_status: str = "DIRTY",
) -> _Route:
    """A real origin and clone whose publish head carries a conforming proof chain.

    The defaults describe the scenario's own shape — an open, already-readied
    pull request at the head this run pushed and proved, whose arming the forge
    refuses — so each control states only the ONE departure it is about.
    """
    origin = root / "origin.git"
    _ = origin.mkdir(parents=True)
    _ = _git("init", "--bare", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=origin)
    seed = root / "seed"
    _ = seed.mkdir()
    _ = _git("init", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=seed)
    _ = _commit(cwd=seed, path=_SHARED_FILE, text="base\n", subject="chore: seed")
    _ = _git("push", "--quiet", str(origin), f"HEAD:refs/heads/{_DEFAULT_BRANCH}", cwd=seed)

    clone = root / "clone"
    _ = _git("clone", "--quiet", str(origin), str(clone), cwd=root)
    head = _commit(
        cwd=clone, path=_OWNED_FILE, text="this run's work\n", subject="feat: this run's work"
    )
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=clone)

    bin_dir = root / "bin"
    _ = bin_dir.mkdir()
    stub = bin_dir / "gh"
    _ = stub.write_text(_GH_STUB % {"python": sys.executable}, encoding="utf-8")
    stub.chmod(0o755)

    plugins_root = root / "plugins"
    _ = plugins_root.mkdir()
    _ = (plugins_root / PROOF_HEAD_PROGRAM_FILENAME).write_text(
        proof_head_program_source(), encoding="utf-8"
    )

    box = _Route(
        origin=origin,
        clone=clone,
        plugins_root=plugins_root,
        forge_state=root / "forge.json",
        bin_dir=bin_dir,
    )
    box.state_dir().mkdir(parents=True)
    _ = (box.state_dir() / PUBLISH_HEAD_STATE_FILENAME).write_text(head, encoding="utf-8")
    _ = box.forge_state.write_text(
        json.dumps(
            {
                "number": _PR_NUMBER,
                "state": "OPEN",
                "head": head,
                "mergeStateStatus": merge_state_status,
                "isDraft": False,
                "autoMergeRequest": None,
                "mergeCommit": None,
                "comments": [
                    _record(verdict=VERDICT_CAPTURED, head=head),
                    _record(verdict=VERDICT_VERIFIED, head=head),
                ],
                "reject_merge": reject_merge,
                "advance_head_on": advance_head_on,
                "advance_head_to": "2" * 40,
                "unreadable_fields": list(unreadable_fields),
                "unreadable_after_merge": list(unreadable_after_merge),
                "calls": [],
            }
        ),
        encoding="utf-8",
    )
    return box


def _advance_default(*, box: _Route) -> str:
    """Move origin's default branch, as another merge to it would.

    Performed through a SEPARATE clone so the control's own clone learns nothing
    about the movement until the stage's own fetch — which is the state a real
    dispatch is in when the default branch advances underneath it.
    """
    mover = box.clone.parent / "mover"
    _ = _git("clone", "--quiet", str(box.origin), str(mover), cwd=box.clone.parent)
    advanced = _commit(
        cwd=mover, path=_SHARED_FILE, text="moved\n", subject="feat: advance the default"
    )
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_DEFAULT_BRANCH}", cwd=mover)
    return advanced


def _env(*, box: _Route) -> dict[str, str]:
    """The child environment, EXPLICIT rather than inherited.

    The subprocess-spawn allowlist requires it, and it keeps a control honest:
    an inherited `LIVESPEC_*` from the enclosing factory run could satisfy a
    guard this control meant to exercise.
    """
    return {
        "PATH": f"{box.bin_dir}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(box.clone.parent / "home"),
        "LIVESPEC_FAKE_FORGE": str(box.forge_state),
        "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
        "LIVESPEC_PR_TITLE": "feat: a scripted publication",
        SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(box.plugins_root),
    }


def _run(*, box: _Route, node: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", _node_script(node=node)],
        cwd=box.clone,
        capture_output=True,
        text=True,
        check=False,
        env=_env(box=box),
    )


def _diagnostic(*, stderr: str) -> str:
    """The ONE line the rejected arming writes, or the empty string when it wrote none."""
    for line in stderr.splitlines():
        if line.startswith("LIVESPEC_PR_ARM_REJECTED:"):
            return line
    return ""


def test_the_two_new_state_files_are_declared_with_the_rest() -> None:
    """Both filenames join the declared set, which is what the boundary control reads.

    `publication_state_filenames` is the COMPLETE set a control asserting an
    execution boundary left the enclosing run's state intact iterates over, so a
    filename missing from it is a file that control does not cover — and nothing
    about the resulting read would say so.
    """
    declared = publication_state_filenames()

    assert _VISIT_COUNT_FILENAME in declared
    assert _ROUTE_MARKER_FILENAME in declared


def test_an_advanced_default_branch_routes_the_rejected_arming_back_to_pr_refresh(
    tmp_path: Path,
) -> None:
    """The scenario's own path: `pr` records the marker and `pr_route` routes on it.

    Both halves are asserted because either alone passes while the requirement is
    unmet. A `pr` that exits zero without recording the marker reaches the
    publish breaker and finishes the run GREEN with an unarmed pull request; a
    `pr_route` that exits non-zero on no marker would send every healthy
    publication back through a refresh it does not owe.
    """
    box = _build(root=tmp_path)
    tip = _advance_default(box=box)

    pr = _run(box=box, node="pr")

    assert pr.returncode == 0, pr.stderr
    assert "LIVESPEC_PR_REFRESH_ROUTE" in pr.stderr
    assert box.state(name=_ROUTE_MARKER_FILENAME) == "1\n"
    assert box.state(name=_VISIT_COUNT_FILENAME) == "1\n"
    # Fail-closed means fail-closed: a routed rejection armed nothing.
    assert box.forge()["autoMergeRequest"] is None

    route = _run(box=box, node="pr_route")

    assert route.returncode == 1, route.stdout
    assert "LIVESPEC_PR_ROUTE_REFRESH" in route.stderr
    # Consumed on the visit that read it, so it can never route a later one.
    assert box.state(name=_ROUTE_MARKER_FILENAME) is None
    assert tip != box.head()


def test_the_rejected_arming_names_every_measurement_it_took(tmp_path: Path) -> None:
    """One stage-output line carrying all seven values the clause enumerates.

    The forge's message is asserted VERBATIM because a diagnostic that
    paraphrased it would send an operator after the wrong fault, and the four
    measurements are asserted individually because a line naming six of seven
    reads exactly like a complete account.
    """
    box = _build(root=tmp_path)
    tip = _advance_default(box=box)
    head = box.head()

    pr = _run(box=box, node="pr")

    line = _diagnostic(stderr=pr.stderr)
    assert line, pr.stderr
    assert _REJECTION in line
    assert "pull request state: OPEN" in line
    assert "mergeability: DIRTY" in line
    assert f"pull request head: {head}" in line
    assert "head equals the verified head: equal" in line
    assert f"default branch tip: {tip}" in line
    assert "default branch tip is an ancestor of the head: no" in line


def test_a_rejection_with_no_default_branch_advance_fails_closed_naming_the_cause(
    tmp_path: Path,
) -> None:
    """An ancestor tip is NOT this scenario, so the forge's own cause is the fault.

    The negative half is the load-bearing one: the line must not claim the head
    differs, because that comparison WAS taken and found equal, and a reader
    acting on an invented mismatch would re-dispatch work whose head never moved.
    """
    box = _build(root=tmp_path)

    pr = _run(box=box, node="pr")

    assert pr.returncode == 1, pr.stdout
    assert "LIVESPEC_PR_ARM_FAILED" in pr.stderr
    line = _diagnostic(stderr=pr.stderr)
    assert "head equals the verified head: equal" in line
    assert "default branch tip is an ancestor of the head: yes" in line
    assert "differs" not in line
    assert box.state(name=_ROUTE_MARKER_FILENAME) is None


def test_a_head_that_moved_after_the_observation_fails_closed_and_routes_nothing(
    tmp_path: Path,
) -> None:
    """A moved head is an unexpected head, never a default-branch advance.

    Routing it would send `pr_refresh` after a head this run never published,
    and the refresh's own ownership test would then refuse — one node later,
    under a cause that names the wrong party.
    """
    box = _build(root=tmp_path, reject_merge=None, advance_head_on="edit")
    _ = _advance_default(box=box)

    pr = _run(box=box, node="pr")

    assert pr.returncode == 1, pr.stdout
    assert "LIVESPEC_PR_UNEXPECTED_HEAD" in pr.stderr
    line = _diagnostic(stderr=pr.stderr)
    assert "head equals the verified head: differs" in line
    assert box.state(name=_ROUTE_MARKER_FILENAME) is None


def test_an_unreportable_head_is_never_stated_as_a_mismatch(tmp_path: Path) -> None:
    """A forge that cannot report the head fails closed WITHOUT claiming anything.

    The clause forbids stating a mismatch that was not measured, and this is the
    one input whose absence makes the comparison impossible — so the line has to
    say the comparison was not taken rather than default to either answer.
    """
    box = _build(root=tmp_path, unreadable_after_merge=("headRefOid",))
    _ = _advance_default(box=box)

    pr = _run(box=box, node="pr")

    assert pr.returncode == 1, pr.stdout
    assert "LIVESPEC_PR_ARM_FAILED" in pr.stderr
    line = _diagnostic(stderr=pr.stderr)
    assert "head equals the verified head: (not measured)" in line
    assert "differs" not in line
    assert box.state(name=_ROUTE_MARKER_FILENAME) is None


def test_an_unreportable_mergeability_refuses_rather_than_routing(tmp_path: Path) -> None:
    """An unobservable measurement never becomes a route.

    The default branch HAS advanced here, so every other input says route; the
    control is that one measurement the forge declined is enough to refuse,
    because the clause forbids routing on an unobservable answer.
    """
    box = _build(root=tmp_path, unreadable_fields=("mergeStateStatus",))
    _ = _advance_default(box=box)

    pr = _run(box=box, node="pr")

    assert pr.returncode == 1, pr.stdout
    assert "LIVESPEC_PR_ARM_FAILED" in pr.stderr
    assert "mergeability: (unobservable)" in _diagnostic(stderr=pr.stderr)
    assert box.state(name=_ROUTE_MARKER_FILENAME) is None


def test_a_successful_arming_records_no_marker_and_pr_route_proceeds(tmp_path: Path) -> None:
    """The ordinary publication is unchanged, which is what makes the route safe.

    Asserted end to end rather than by inspection: a marker written on the happy
    path would send every green run back through a refresh, and a `pr_route`
    that failed on an absent marker would do the same without any marker at all.
    """
    box = _build(root=tmp_path, reject_merge=None)

    pr = _run(box=box, node="pr")

    assert pr.returncode == 0, pr.stderr
    assert "LIVESPEC_PR_READY_AND_ARMED" in pr.stderr
    assert _diagnostic(stderr=pr.stderr) == ""
    assert box.state(name=_ROUTE_MARKER_FILENAME) is None
    armings = box.merge_argvs()
    assert armings, "the stage armed nothing"
    argv = armings[0]
    assert argv[argv.index("--match-head-commit") + 1] == box.head()

    route = _run(box=box, node="pr_route")

    assert route.returncode == 0, route.stderr
    assert "LIVESPEC_PR_ROUTE_NONE" in route.stderr


def test_a_marker_left_by_an_earlier_pr_visit_can_never_route_a_later_one(
    tmp_path: Path,
) -> None:
    """The marker NAMES its visit, so a stale one is consumed without routing.

    This is the property the clause states in as many words, and it is not
    implied by consuming the marker: a `pr` that failed closed after writing one
    leaves it behind, and the next visit's `pr_route` would otherwise read it as
    its own and refresh a run whose arming was never rejected.
    """
    box = _build(root=tmp_path, reject_merge=None)
    _ = (box.state_dir() / _ROUTE_MARKER_FILENAME).write_text("1\n", encoding="utf-8")

    pr = _run(box=box, node="pr")

    assert pr.returncode == 0, pr.stderr
    # The second visit, which is what makes the stale marker stale.
    _ = (box.state_dir() / _VISIT_COUNT_FILENAME).write_text("2\n", encoding="utf-8")

    route = _run(box=box, node="pr_route")

    assert route.returncode == 0, route.stderr
    assert "LIVESPEC_PR_ROUTE_STALE_MARKER" in route.stderr
    assert box.state(name=_ROUTE_MARKER_FILENAME) is None

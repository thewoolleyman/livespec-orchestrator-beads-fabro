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

AND THEY ARE READ TWICE, BECAUSE THE TWO ENGINES DECODE THEM DIFFERENTLY
(work-item bd-ib-m4cspa). `parse_dot_graph` models the PINNED reader, which
drops the backslash from every escape it meets. A Petri-era reader decodes a
DOT escString instead, where a backslash before a backslash or a double quote
is an escape and every OTHER backslash travels on into the shell. A case
rendered the pinned way alone therefore cannot see a quoting fault that only
the strict reader produces, and that is exactly what hid the measured defect:
on hp-candidate run 01M52P4NC0JV the arming rejection reached this stage's own
diagnostic EMPTY, under `tr: extra operand`, while every case in this module
passed. So the rendering is a PARAMETER of the cases that read the formatted
rejection, and the property they assert is that ONE set of committed bytes
formats it identically on the engine the factory runs today and on the one it
is migrating to.

THE ENCLOSING RUN'S STATE IS NEVER TOUCHED: every control builds its own
throwaway origin and clone under `tmp_path`, and both stages resolve their state
directory inside THAT clone's `$GIT_DIR`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
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

# The PINNED reader's unescape, restated here as the CROSS-CHECK that binds a
# raw attribute value to the canonical parser's decoded one, never as an
# independent model of it: `_raw_node_script` keeps the raw candidate whose
# pinned decode EQUALS what `parse_dot_graph` returned, so a restatement that
# drifted from the parser leaves no candidate and fails loudly rather than
# rendering something else.
_PINNED_UNESCAPE_RE = re.compile(r"\\(.)")

# How the shipped graph declares a node's script: one attribute, on one line,
# opened by this prefix and closed by the quote that ends the line.
_SCRIPT_ATTRIBUTE_PREFIX = 'script="'

# Where the escString decode parks a backslash it has already produced, so that
# backslash cannot be re-read as the opener of the NEXT escape. A NUL can appear
# in neither the graph text nor a shell script, which is what makes it safe.
_DECODED_BACKSLASH = "\x00"

# The two renderings, named so a failure reports which engine it modelled.
_RENDERINGS = (
    pytest.param(False, id="pinned-drops-every-escapes-backslash"),
    pytest.param(True, id="petri-era-decodes-escstring-only"),
)
_OWNED_FILE = "owned.txt"
_SHARED_FILE = "shared.txt"
# The forge's own wording for the rejection this scenario is about. Carried as a
# constant because two controls assert it reaches the diagnostic line VERBATIM,
# which is the clause's own word.
_REJECTION = "failed to merge: Pull request is not mergeable"

# The forge's own wording for the rejection the measured defect LOST, carried
# across TWO LINES because the newline is what the formatting has to flatten
# and a single-line message cannot tell a working `tr` from a dead one. The
# first line is what run 01M52E8Q9QZH printed before this line existed; the
# apostrophe in it is deliberate, since a single quote inside the rejection is
# the character a re-introduced backslash-quote formatting breaks on.
_MULTILINE_REJECTION = (
    "GraphQL: This branch can't be rebased (mergePullRequest)\n"
    "failed to merge: Base branch was modified"
)
_FLATTENED_REJECTION = (
    "GraphQL: This branch can't be rebased (mergePullRequest) "
    "failed to merge: Base branch was modified"
)

# The two operands the formatting owes `tr`: the newline it translates, in the
# two-character form the shell hands `tr`, and the space it translates that to.
_TR_OPERANDS = ["\\n", " "]
# What `tr` says when it is given a THIRD, which is the measured defect's own
# first line of output.
_TR_EXTRA_OPERAND = "extra operand"

# The two state filenames this route adds, spelled here as the LITERALS the
# shipped shell spells them with — a stage script cannot import a Python
# constant, so the literal is what is actually under test. They are bound to the
# product surface by `test_the_two_new_state_files_are_declared_with_the_rest`
# below rather than imported, so a rename that moved only one of the two still
# fails here instead of passing against a constant nothing reads.
_VISIT_COUNT_FILENAME = "livespec-pr-visit-count"
_ROUTE_MARKER_FILENAME = "livespec-pr-refresh-route"

# The jq program the merge-commit read owes `jq`: a BARE field path, carrying no
# quote character of its own. A jq field path needs no quoting, and the quote
# characters a backslash-escaped spelling leaves behind are a parse error rather
# than a filter (work-item bd-ib-be5r7o).
_MERGE_COMMIT_FIELD_PATH = ".mergeCommit.oid"
# The `--json` field that read asks for, which is how the recorder attributes it.
_MERGE_COMMIT_FIELD = "mergeCommit"

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
#
# `merged_while_arming` is the race the ratified clause names: the forge rejects
# the arming command AND the pull request is already MERGED when the stage
# re-reads its state, which is the one arm that reaches the merge-commit read. It
# cannot be arranged with `reject_merge` alone, because a pull request that is
# MERGED before the stage runs takes the EARLIER already-merged branch and never
# issues an arming at all.
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
        if state["merged_while_arming"]:
            state["state"] = "MERGED"
            state["mergeCommit"] = state["merged_while_arming"]
        save(state)
        sys.stderr.write(state["reject_merge"] + "\n")
        sys.exit(1)
    state["autoMergeRequest"] = {"enabledAt": "now"}
    save(state)
    sys.exit(0)

sys.stderr.write("unstubbed gh invocation: %%s\n" %% " ".join(argv))
sys.exit(2)
"""

# A `tr` that RECORDS the operands it was handed and then delegates to the real
# one, so "exactly two operands" is MEASURED rather than inferred from the
# formatted output. It changes nothing the stage computes: a wrong operand count
# still reaches the genuine `tr` and still fails there exactly as it did before,
# which is what keeps every other case in this module reading the real thing.
_TR_RECORDER = """#!%(python)s
import json, os, sys

with open(os.environ["LIVESPEC_TR_OPERANDS"], "a") as handle:
    _ = handle.write(json.dumps(sys.argv[1:]) + "\\n")
os.execv(%(tr)r, ["tr", *sys.argv[1:]])
"""


def _real_tr() -> str:
    """The genuine `tr`, resolved BEFORE a fixture's bin directory shadows it."""
    found = shutil.which("tr")
    assert found is not None, "no tr on PATH, so the recorder has nothing to delegate to"
    return found


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


def _declared_script(*, node: str) -> str:
    """One shipped node's `script` attribute, read through the canonical parser."""
    graph = parse_dot_graph(text=_IMPLEMENT_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph.nodes[node]["script"]


def _bind_engine_tokens(*, script: str) -> str:
    """Bind the engine's OWN tokens, to the values `workflow.toml` declares."""
    return (
        script.replace("{{ inputs.merge_mode }}", "rebase")
        .replace("{{ inputs.merge_hold }}", "false")
        .replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH)
    )


def _node_script(*, node: str) -> str:
    """One shipped node's script, with only the engine's own tokens bound."""
    return _bind_engine_tokens(script=_declared_script(node=node))


def _raw_node_script(*, node: str) -> str:
    """One node's `script` value as the FILE carries it, its escapes UNDECODED.

    Attributed by DECODE rather than by position: the candidate kept is the one
    whose pinned decode equals what `parse_dot_graph` returned for this node, so
    a line read that missed the value, or sliced it wrongly, leaves no candidate
    and fails here instead of quietly rendering something else.
    """
    text = _IMPLEMENT_GRAPH.read_text(encoding="utf-8")
    declared = _declared_script(node=node)
    candidates = [
        raw
        for raw in (
            line.strip()[len(_SCRIPT_ATTRIBUTE_PREFIX) : -1]
            for line in text.splitlines()
            if line.strip().startswith(_SCRIPT_ATTRIBUTE_PREFIX)
        )
        if _PINNED_UNESCAPE_RE.sub(r"\1", raw) == declared
    ]
    assert len(candidates) == 1, f"{node}: {len(candidates)} raw script candidates, expected 1"
    return candidates[0]


def _petri_node_script(*, node: str) -> str:
    """One shipped node's script as a PETRI-ERA engine renders it.

    The raw value is decoded as a DOT escString — a backslash before a backslash
    or a double quote, and nothing else — so every other backslash reaches the
    shell exactly as the candidate engine delivers it.
    """
    raw = _raw_node_script(node=node)
    return _bind_engine_tokens(
        script=raw.replace("\\\\", _DECODED_BACKSLASH)
        .replace('\\"', '"')
        .replace(_DECODED_BACKSLASH, "\\")
    )


def _rendered_pr_script(*, petri: bool) -> str:
    """The `pr` node's script as the engine under test renders it."""
    return _petri_node_script(node="pr") if petri else _node_script(node="pr")


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
    tr_record: Path

    def tr_operands(self) -> list[list[str]]:
        """Every `tr` argv the stage issued, in order, as the recorder saw it.

        The record file is created EMPTY by `_build`, so an arm that formats no
        rejection reads an empty list through the same accessor rather than
        through a branch no case here takes.
        """
        lines = self.tr_record.read_text(encoding="utf-8").splitlines()
        return [cast("list[str]", json.loads(line)) for line in lines]

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

    def view_argvs(self, *, field: str) -> list[list[str]]:
        """Every `gh pr view --json <field>` argv the stage issued, in order.

        Keyed on the `--json` field rather than on the `--jq` operand, because
        the operand is the thing under assertion: a filter keyed on it would
        return nothing for the very spelling a case exists to reject, and an
        empty list reads as "the stage never asked" rather than as a finding.
        """
        recorded = cast("list[list[str]]", self.forge()["calls"])
        return [
            call
            for call in recorded
            if call[:2] == ["pr", "view"]
            and "--json" in call
            and call[call.index("--json") + 1] == field
        ]


def _build(
    *,
    root: Path,
    reject_merge: str | None = _REJECTION,
    advance_head_on: str | None = None,
    unreadable_fields: tuple[str, ...] = (),
    unreadable_after_merge: tuple[str, ...] = (),
    merge_state_status: str = "DIRTY",
    merged_while_arming: str | None = None,
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
    recorder = bin_dir / "tr"
    _ = recorder.write_text(
        _TR_RECORDER % {"python": sys.executable, "tr": _real_tr()}, encoding="utf-8"
    )
    recorder.chmod(0o755)

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
        tr_record=root / "tr-operands.jsonl",
    )
    _ = box.tr_record.write_text("", encoding="utf-8")
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
                "merged_while_arming": merged_while_arming,
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
        "LIVESPEC_TR_OPERANDS": str(box.tr_record),
        "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
        "LIVESPEC_PR_TITLE": "feat: a scripted publication",
        SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(box.plugins_root),
    }


def _run_rendered(*, box: _Route, script: str) -> subprocess.CompletedProcess[str]:
    """Run one already-rendered stage script in this control's own clone."""
    return subprocess.run(
        ["bash", "-c", script],
        cwd=box.clone,
        capture_output=True,
        text=True,
        check=False,
        env=_env(box=box),
    )


def _run(*, box: _Route, node: str) -> subprocess.CompletedProcess[str]:
    return _run_rendered(box=box, script=_node_script(node=node))


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


@pytest.mark.parametrize("petri", _RENDERINGS)
def test_the_arming_rejection_is_flattened_by_two_tr_operands_on_both_renderings(
    *,
    petri: bool,
    tmp_path: Path,
) -> None:
    """The formatting hands `tr` two operands, so the forge's text survives.

    THE PETRI LEG IS THE ONE THAT WAS FAILING, and it failed in the direction
    that reads as an UNEXPLAINED forge refusal rather than as a quoting bug: the
    stage still exited 1 under its own fail-closed sentinel, still printed all
    seven measurements, and named the one field an operator would act on as
    EMPTY. So the operand count is measured off the recorder rather than
    inferred, and the flattened text is asserted beside it — a line carrying the
    rejection proves nothing about the count, and a count proves nothing about
    what the line ended up carrying.

    `tr: extra operand` is asserted ABSENT because that string is the whole of
    what the measured defect emitted before the empty field, and the pinned leg
    is the control: the same bytes behave this way on the engine the factory runs
    today, which is what makes one committed formatting enough for both.
    """
    box = _build(root=tmp_path, reject_merge=_MULTILINE_REJECTION)

    pr = _run_rendered(box=box, script=_rendered_pr_script(petri=petri))

    assert pr.returncode == 1, pr.stdout
    assert "LIVESPEC_PR_ARM_FAILED" in pr.stderr
    assert _TR_EXTRA_OPERAND not in pr.stderr
    assert box.tr_operands() == [_TR_OPERANDS]
    line = _diagnostic(stderr=pr.stderr)
    assert f"forge rejection: {_FLATTENED_REJECTION} |" in line


@pytest.mark.parametrize("petri", _RENDERINGS)
def test_the_merge_commit_read_hands_jq_a_bare_field_path_on_both_renderings(
    *,
    petri: bool,
    tmp_path: Path,
) -> None:
    """One committed spelling of the merge-commit read works on BOTH engines.

    This is the `pr` node's half of the quoting family bd-ib-m4cspa opened and
    bd-ib-be5r7o closed: a single quote written backslash-escaped inside the DOT
    attribute string is not an escape, so the pinned reader drops the backslash
    while a Petri-era reader hands it to the shell, where a backslashed quote is
    a LITERAL quote character. `gh` forwards the `--jq` operand verbatim, so a
    quote-wrapped field path reaches `jq` as a program beginning with a quote
    token and jq refuses to parse it.

    THE ARM UNDER TEST IS THE ONLY ONE THAT REACHES THIS READ, and it is the
    merge-DETECTION arm: the arming command is rejected and the pull request
    turns out to have merged while it was being issued, which is the outcome the
    arming was for. A stage that cannot read the merge commit there reports no
    `MERGE_LANDED` for a pull request that landed — so the run's own record loses
    the sha of the merge it produced, on the one path where nothing downstream
    can recover it.

    The operand is read off the recorder rather than inferred from the outcome,
    for the reason the sibling case in `test_scripted_refresh_execution` gives:
    the forge double answers the field without consulting `--jq` at all, because
    it holds no JSON document to filter, so the recorded operand is the only
    instrument here that can tell the two spellings apart. The pinned leg is the
    control.
    """
    landed = "3" * 40
    box = _build(root=tmp_path, merged_while_arming=landed)

    pr = _run_rendered(box=box, script=_rendered_pr_script(petri=petri))

    assert pr.returncode == 0, pr.stderr
    assert "LIVESPEC_PR_MERGED_WHILE_ARMING" in pr.stderr
    assert f"MERGE_LANDED={landed}" in pr.stdout
    reads = box.view_argvs(field=_MERGE_COMMIT_FIELD)
    assert reads, "the stage read no merge commit"
    argv = reads[-1]
    assert argv[argv.index("--jq") + 1] == _MERGE_COMMIT_FIELD_PATH


@pytest.mark.parametrize("petri", _RENDERINGS)
def test_the_visit_count_is_recorded_as_a_bare_number_on_both_renderings(
    *,
    petri: bool,
    tmp_path: Path,
) -> None:
    """A later visit of the same run reads the recorded count back as an integer.

    The third span of the same quoting family (work-item bd-ib-be5r7o), and the
    one whose damage is not a lost diagnostic but a stage that refuses. A
    backslashed quote reaches the shell as a literal quote character and the
    `\\n` beside it as a bare `n`, so the format `printf` receives is a
    quote-wrapped literal: the state file ends up holding the count wrapped in
    quote characters with no trailing newline at all.

    THE SECOND VISIT IS WHERE THAT LANDS, which is why one run of the stage
    cannot show it. `pr` re-reads the file it wrote and requires the value to
    compare as a number; a quote-wrapped one does not, so the stage refuses under
    LIVESPEC_PR_VISIT_COUNT_UNREADABLE — on the second visit of a run whose first
    visit reported itself perfectly healthy. The count is therefore asserted on
    its BYTES after the first visit and on the second visit's own answer, since
    the bytes alone say nothing about what reads them and a successful second
    visit alone would pass for a build that never recorded a count.

    The pinned leg is the control: the same committed bytes behave this way on
    the engine the factory runs today.
    """
    box = _build(root=tmp_path, reject_merge=None)
    script = _rendered_pr_script(petri=petri)

    first = _run_rendered(box=box, script=script)

    assert first.returncode == 0, first.stderr
    assert box.state(name=_VISIT_COUNT_FILENAME) == "1\n"

    second = _run_rendered(box=box, script=script)

    assert second.returncode == 0, second.stderr
    assert "LIVESPEC_PR_VISIT_COUNT_UNREADABLE" not in second.stderr
    assert box.state(name=_VISIT_COUNT_FILENAME) == "2\n"

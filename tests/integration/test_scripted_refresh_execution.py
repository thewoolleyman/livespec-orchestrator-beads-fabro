"""Run the `pr_refresh` stage's OWN script bytes against real Git and a real remote.

WHY THIS FILE EXISTS, AND WHY IT IS NOT A DECLARATION TEST.
`test_scripted_publication_stages.py` grades which KIND of stage publishes, which
is a property of the committed payload. `test_scripted_publication_execution.py`
grades what the `pr` node DOES. Neither reaches `pr_refresh`, and `pr_refresh` is
the one stage the ratified clause grants a REWRITING capability: it rebases the
publish branch and pushes it under a lease. Every guard around that capability --
the recorded-versus-remote ownership test, the non-numeric-counter fail-closed,
the three-refresh bound, the conflict abort, the post-rebase gate, and the lease
itself -- is shell, and a substring assertion cannot tell a guard that RUNS from
one that is dead code behind an earlier `exit`.

So each control below executes the shipped bytes and then asserts what happened
to a REAL remote.

THE SCRIPT BYTES ARE READ THROUGH THE CANONICAL PARSER, NEVER RETYPED, with
`parse_dot_graph` -- the same reader the Dispatcher's own graph consumers use. A
test carrying its own copy of the recipe would pass while the shipped stage did
something else, which is the specific failure this work-item's recovery review
called out.

WHAT IS SIMULATED, AND WHY EACH SUBSTITUTION IS SAFE.

- `{{ inputs.default_branch }}` and `{{ inputs.sandbox_check_suite }}` are
  substituted here because the pinned ENGINE owns that templating, not this
  repository. The check suite is a per-repository DECLARATION -- an arbitrary
  command the governed repo names -- so standing a controlled script in for it
  is standing in for the declaration, not for the stage. Nothing else in the
  bytes is touched, and in particular the fetch, the `ls-remote`, the rebase, the
  plugin gate and the leased push all run for real.
- ORIGIN IS A REAL LOCAL BARE REPOSITORY and the clone is a real `git clone` of
  it, because the questions are about refs: whether the branch moved, whether a
  lease rejects, whether anything was pushed at all. A double cannot answer any
  of those, and the claim this file exists to establish is precisely that the
  shell reaches the right ref operations.
- THE THREE MATERIALIZED HELPERS ARE THE PRODUCTION ONES. The plugin-cache gate,
  the exact-head push program and (for the state filenames) the publication-state
  module are imported and written from their own sources, so the lease the push
  performs is the lease the Dispatcher ships rather than one restated here.

THE ENCLOSING RUN'S STATE IS NEVER TOUCHED. Each control builds its own
throwaway origin, clone and plugins root under `tmp_path`, and the stage resolves
its state directory inside THAT clone's `$GIT_DIR`. This matters more here than
anywhere else in the tree: `pr_refresh` runs `sandbox_check_suite` -- this very
suite -- as its post-rebase gate, in the same sandbox, AFTER establishing its
provenance. A control writing state at a fixed shared path would erase the live
refresh counter of the stage running it, letting the next refresh restart at one
and evade the three-refresh bound.
`test_the_refresh_execution_boundary_leaves_enclosing_run_state_intact` is the
regression control for that property.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import render_run_config_overlay
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    PLUGIN_GATE_PROGRAM_FILENAME,
    plugin_cache_gate_script,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    PUBLICATION_PUSH_PROGRAM_FILENAME,
    publication_push_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_state import (
    PUBLICATION_STATE_GIT_PATH,
    PUBLISH_HEAD_STATE_FILENAME,
    REFRESH_CHANGED_STATE_FILENAME,
    REFRESH_COUNT_STATE_FILENAME,
    publication_state_filenames,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_merge import (
    RECORD_FILE_MERGE_PROGRAM_FILENAME,
    record_file_merge_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import resume_checkout_for
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

_BRANCH = "feat/bd-ib-c3txja"
_DEFAULT_BRANCH = "master"
# The file the publish branch owns. A conflict is arranged by moving the DEFAULT
# branch's copy of this same path, which is the real shape of the conflict the
# stage must abort rather than resolve.
_OWNED_FILE = "owned.txt"
_SHARED_FILE = "shared.txt"

# The two DECLARED shared records, and the declaration that makes them so. They
# ride the seed commit beside `_SHARED_FILE` rather than a commit of their own,
# so no case in this module acquires an extra ancestor it does not use: an
# undeclared conflict still lands in `_SHARED_FILE` exactly as before.
_RECORD_JSON = "record.json"
_RECORD_MARKDOWN = "notes.md"
_DECLARATION_FILE = ".livespec.jsonc"
_DECLARATION = """{
  // JSONC, because the committed declaration the merger opens carries comments.
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "record_files": [
        {"path": "record.json", "format": "json-array", "key": ["id"]},
        {"path": "notes.md", "format": "markdown-insertions"}
      ]
    }
  }
}
"""


# The coverage hooks an allowlisted spawn must scrub, so no child of this file
# self-instruments and races the concurrent coverage run. Git itself ignores
# them, but the fixture git calls below are the only place in this module that
# inherits the parent environment at all, and the obligation is on the FILE.
_COVERAGE_ENV_PREFIXES = ("COVERAGE_PROCESS_START", "COV_CORE_")


def _fixture_git_env() -> dict[str, str]:
    """The fixture environment, coverage-scrubbed, with an explicit git identity.

    The identity is stated rather than inherited because a control must not
    depend on whatever `user.name` the executing machine carries -- the factory
    sandbox carries one that differs from a developer's, and a commit with no
    identity at all fails outright.
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
        env=_fixture_git_env(),
    )


# The PINNED reader's unescape, restated here as the CROSS-CHECK that binds a raw
# attribute value to the canonical parser's decoded one, never as an independent
# model of it: `_raw_refresh_script` keeps the raw candidate whose pinned decode
# EQUALS what `parse_dot_graph` returned, so a restatement that drifted from the
# parser leaves no candidate and fails loudly rather than rendering something
# else. The same shape `test_pr_route_base_advance_scenario184` uses for `pr`.
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


def _bind_engine_tokens(*, script: str, check_suite: str) -> str:
    """Bind the engine's OWN tokens, and nothing else the stage carries."""
    return script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH).replace(
        "{{ inputs.sandbox_check_suite }}", check_suite
    )


def _declared_refresh_script() -> str:
    """The shipped `pr_refresh` node's `script` attribute, through the canonical parser."""
    graph = parse_dot_graph(text=_IMPLEMENT_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph.nodes["pr_refresh"]["script"]


def _raw_refresh_script() -> str:
    """The `pr_refresh` `script` value as the FILE carries it, its escapes UNDECODED.

    Attributed by DECODE rather than by position: the candidate kept is the one
    whose pinned decode equals what `parse_dot_graph` returned for this node, so
    a line read that missed the value, or sliced it wrongly, leaves no candidate
    and fails here instead of quietly rendering something else.
    """
    text = _IMPLEMENT_GRAPH.read_text(encoding="utf-8")
    declared = _declared_refresh_script()
    candidates = [
        raw
        for raw in (
            line.strip()[len(_SCRIPT_ATTRIBUTE_PREFIX) : -1]
            for line in text.splitlines()
            if line.strip().startswith(_SCRIPT_ATTRIBUTE_PREFIX)
        )
        if _PINNED_UNESCAPE_RE.sub(r"\1", raw) == declared
    ]
    assert len(candidates) == 1, f"pr_refresh: {len(candidates)} raw candidates, expected 1"
    return candidates[0]


def _refresh_script(*, check_suite: str) -> str:
    """The shipped `pr_refresh` node's script, with only the engine's own tokens bound."""
    return _bind_engine_tokens(script=_declared_refresh_script(), check_suite=check_suite)


def _petri_refresh_script(*, check_suite: str) -> str:
    """The shipped `pr_refresh` node's script as a PETRI-ERA engine renders it.

    The raw value is decoded as a DOT escString -- a backslash before a backslash
    or a double quote, and nothing else -- so every other backslash reaches the
    shell exactly as the candidate engine delivers it.
    """
    return _bind_engine_tokens(
        script=_raw_refresh_script()
        .replace("\\\\", _DECODED_BACKSLASH)
        .replace('\\"', '"')
        .replace(_DECODED_BACKSLASH, "\\"),
        check_suite=check_suite,
    )


def _rendered_refresh_script(*, petri: bool, check_suite: str) -> str:
    """The `pr_refresh` node's script as the engine under test renders it."""
    return (
        _petri_refresh_script(check_suite=check_suite)
        if petri
        else _refresh_script(check_suite=check_suite)
    )


@dataclass(frozen=True, kw_only=True)
class _Refresh:
    """One control's throwaway world: a real origin, a real clone, real helpers."""

    origin: Path
    clone: Path
    plugins_root: Path
    gate_script: Path
    bin_dir: Path
    forge_state: Path

    def forge(self) -> dict[str, object]:
        return json.loads(self.forge_state.read_text(encoding="utf-8"))

    def forge_calls(self) -> list[dict[str, object]]:
        """Every argv the stub was handed, each with the clone's head at that moment."""
        return cast("list[dict[str, object]]", self.forge()["calls"])

    def disarm_heads(self) -> list[str]:
        """The clone's head at each `--disable-auto` call the stage issued."""
        return [
            str(call["head"])
            for call in self.forge_calls()
            if cast("list[str]", call["argv"])[:2] == ["pr", "merge"]
        ]

    def state_dir(self) -> Path:
        return self.clone / ".git" / PUBLICATION_STATE_GIT_PATH

    def remote_head(self, *, ref: str) -> str:
        """Origin's own answer for one ref, or the empty string when it holds none."""
        listed = subprocess.run(
            ["git", "ls-remote", "--heads", str(self.origin), f"refs/heads/{ref}"],
            check=True,
            capture_output=True,
            text=True,
            env=_fixture_git_env(),
        )
        return listed.stdout.split("\t")[0] if listed.stdout.strip() else ""

    def local_head(self) -> str:
        return _git("rev-parse", "HEAD", cwd=self.clone).stdout.strip()

    def state(self, *, name: str) -> str | None:
        path = self.state_dir() / name
        return path.read_text(encoding="utf-8") if path.is_file() else None


def _commit(*, cwd: Path, path: str, text: str, subject: str) -> str:
    """Write one file and commit it, returning the resulting head.

    Every fixture mutation in this module is this shape, and `git commit`
    refuses outright without an identity, so the `config` pair rides here rather
    than being remembered at each site.
    """
    _ = _git("config", "user.email", "t@example.invalid", cwd=cwd)
    _ = _git("config", "user.name", "Test", cwd=cwd)
    _ = (cwd / path).write_text(text, encoding="utf-8")
    _ = _git("add", path, cwd=cwd)
    _ = _git("commit", "--quiet", "-m", subject, cwd=cwd)
    return _git("rev-parse", "HEAD", cwd=cwd).stdout.strip()


def _origin_with_default(*, root: Path) -> Path:
    """A bare origin whose default branch carries the shared file."""
    origin = root / "origin.git"
    _ = origin.mkdir(parents=True)
    _ = _git("init", "--bare", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=origin)
    seed = root / "seed"
    _ = seed.mkdir()
    _ = _git("init", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=seed)
    _ = (seed / _DECLARATION_FILE).write_text(_DECLARATION, encoding="utf-8")
    _ = (seed / _RECORD_JSON).write_text('[{"id": "seed"}]\n', encoding="utf-8")
    _ = (seed / _RECORD_MARKDOWN).write_text("- seed entry\n", encoding="utf-8")
    _ = _git("add", _DECLARATION_FILE, _RECORD_JSON, _RECORD_MARKDOWN, cwd=seed)
    _ = _commit(cwd=seed, path=_SHARED_FILE, text="base\n", subject="chore: seed")
    _ = _git("push", "--quiet", str(origin), f"HEAD:refs/heads/{_DEFAULT_BRANCH}", cwd=seed)
    return origin


def _materialized_plugins_root(*, root: Path) -> Path:
    """The sandbox plugins root, carrying the three PRODUCTION helpers.

    The push program and the declared-record-file merger are written from their
    own sources and the gate from its own prepare-step body, so the lease and the
    merge the stage performs are the ones the Dispatcher ships rather than ones
    restated here.
    """
    plugins_root = root / "plugins"
    _ = plugins_root.mkdir()
    push_program = plugins_root / PUBLICATION_PUSH_PROGRAM_FILENAME
    _ = push_program.write_text(publication_push_program_source(), encoding="utf-8")
    push_program.chmod(0o700)
    merge_program = plugins_root / RECORD_FILE_MERGE_PROGRAM_FILENAME
    _ = merge_program.write_text(record_file_merge_program_source(), encoding="utf-8")
    merge_program.chmod(0o700)
    gate_script = root / "install-plugin-gate.sh"
    _ = gate_script.write_text(plugin_cache_gate_script(), encoding="utf-8")
    return plugins_root


def _build(
    *,
    root: Path,
    armed: bool = False,
    arming_unreadable: bool = False,
    disarm_fails: bool = False,
) -> _Refresh:
    """An origin carrying `master` and the publish branch, and a clone on the branch.

    The clone's HEAD is the publish branch's tip and origin's copy of that branch
    is the same object, so the recorded provenance written below is TRUE -- which
    is what makes every departure a control arranges the one thing under test.

    Running the gate's own body here also records this control's plugin pin,
    which is what makes the stage's later re-entry the ENFORCEMENT arm rather
    than a first recording.
    """
    origin = _origin_with_default(root=root)
    clone = root / "clone"
    _ = _git("clone", "--quiet", str(origin), str(clone), cwd=root)
    _ = _commit(
        cwd=clone, path=_OWNED_FILE, text="this run's work\n", subject="feat: this run's work"
    )
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=clone)
    gate_script = root / "install-plugin-gate.sh"
    bin_dir = root / "bin"
    _ = bin_dir.mkdir()
    stub = bin_dir / "gh"
    _ = stub.write_text(_GH_STUB % {"python": sys.executable}, encoding="utf-8")
    stub.chmod(0o755)
    box = _Refresh(
        origin=origin,
        clone=clone,
        plugins_root=_materialized_plugins_root(root=root),
        gate_script=gate_script,
        bin_dir=bin_dir,
        forge_state=root / "forge.json",
    )
    _ = box.forge_state.write_text(
        json.dumps(
            {
                "armed": armed,
                "arming_unreadable": arming_unreadable,
                "disarm_fails": disarm_fails,
                "calls": [],
            }
        ),
        encoding="utf-8",
    )
    box.state_dir().mkdir(parents=True)
    _ = (box.state_dir() / PUBLISH_HEAD_STATE_FILENAME).write_text(
        box.local_head(), encoding="utf-8"
    )
    _ = subprocess.run(
        ["bash", str(gate_script)],
        check=True,
        capture_output=True,
        text=True,
        env=_env(box=box),
    )
    return box


def _env(*, box: _Refresh, extra: dict[str, str] | None = None) -> dict[str, str]:
    """The child environment, EXPLICIT rather than inherited.

    The subprocess-spawn allowlist requires it, and it also keeps a control
    honest: an inherited `LIVESPEC_*` from the enclosing factory run could
    satisfy a guard the control meant to exercise -- `LIVESPEC_RESUME_PUBLISHED_
    HEAD` above all, which is the fallback the no-provenance control asserts.
    """
    env = {
        "PATH": f"{box.bin_dir}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(box.clone.parent / "home"),
        "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
        "LIVESPEC_FAKE_FORGE": str(box.forge_state),
        "LIVESPEC_FAKE_FORGE_CLONE": str(box.clone),
        SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(box.plugins_root),
    }
    return env if extra is None else {**env, **extra}


def _advance_default(*, box: _Refresh, path: str = _SHARED_FILE, text: str = "moved\n") -> str:
    """Move origin's default branch, as another merge to it would.

    Performed through a SEPARATE clone so the control's own clone learns nothing
    about the movement until the stage's own fetch -- which is the state a real
    dispatch is in when the default branch advances underneath it.
    """
    mover = box.clone.parent / f"mover-{path}-{len(text)}"
    _ = _git("clone", "--quiet", str(box.origin), str(mover), cwd=box.clone.parent)
    advanced = _commit(cwd=mover, path=path, text=text, subject=f"feat: advance {path}")
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_DEFAULT_BRANCH}", cwd=mover)
    return advanced


def _branch_clone(*, box: _Refresh, name: str) -> Path:
    """A second clone sitting on the publish branch, for a control that moves it."""
    other = box.clone.parent / name
    _ = _git("clone", "--quiet", str(box.origin), str(other), cwd=box.clone.parent)
    _ = _git("checkout", "--quiet", "-B", _BRANCH, f"origin/{_BRANCH}", cwd=other)
    return other


_PASSING_GATE = "true"
_FAILING_GATE = "false"

# The jq program the auto-merge read owes `jq`: the field piped through
# `tojson`, carrying no quote character of its own. A jq program needs no
# quoting, and the quote characters a backslash-escaped spelling leaves behind
# are a parse error rather than a filter (work-item bd-ib-be5r7o). `tojson` is
# what makes an UNARMED pull request legible: `gh`'s built-in `--jq` prints a
# JSON null as NOTHING under a bare field path, which the stage cannot tell
# from a forge that would not answer, while `tojson` renders it as the literal
# `null` the stage compares against (work-item bd-ib-fisgni).
_AUTO_MERGE_FIELD_PATH = ".autoMergeRequest|tojson"

# The first token of the non-convergence cause, which is what the reason file
# must OPEN with: a quote-wrapped format puts a quote character there instead,
# and the existing non-convergence case's `in` reading cannot see a leading one.
_NON_CONVERGED_PREFIX = "pr-refresh-non-converged:"

# The forge stub, a PROGRAM on `PATH` rather than an in-process mock because the
# stage reaches `gh` as a subprocess. It serves exactly the two calls the v145
# disarm leg makes -- the auto-merge read and the `--disable-auto` write -- and
# records both, so WHAT the stage asked the forge is itself under assertion.
#
# IT ALSO RECORDS THE CLONE'S HEAD AT EACH CALL, which is what makes "before it
# rebases" an OBSERVATION rather than an inference from the end state. A disarm
# issued after the rebase is a disarm of a pull request whose head the forge was
# holding armed for merge and which this run has already rewritten, and nothing
# in the final refs distinguishes the two orders.
_GH_STUB = r"""#!%(python)s
import json, os, subprocess, sys

state_path = os.environ["LIVESPEC_FAKE_FORGE"]
clone = os.environ["LIVESPEC_FAKE_FORGE_CLONE"]


def head():
    done = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=clone, capture_output=True, text=True, check=False
    )
    return done.stdout.strip()


with open(state_path) as handle:
    state = json.load(handle)

argv = sys.argv[1:]
state["calls"].append({"argv": argv, "head": head()})

with open(state_path, "w") as handle:
    json.dump(state, handle)

if argv[:2] == ["pr", "view"]:
    if state["arming_unreadable"]:
        sys.stderr.write("the forge declined to report autoMergeRequest\n")
        sys.exit(1)
    # Rendered the way REAL `gh --jq` renders it, measured with gh against
    # unarmed pull request 3113 and armed pull request 3154 on 2026-10-17: a
    # bare field path prints an object as compact JSON and a null as NOTHING,
    # while `|tojson` prints the literal `null`. An operand this double does not
    # model is refused rather than answered, so it can never stand in for a
    # spelling the real CLI would render differently.
    value = {"enabledAt": "now"} if state["armed"] else None
    operand = argv[argv.index("--jq") + 1]
    if operand == ".autoMergeRequest":
        print("" if value is None else json.dumps(value, separators=(",", ":")))
    elif operand == ".autoMergeRequest|tojson":
        print(json.dumps(value, separators=(",", ":")))
    else:
        sys.stderr.write("unmodelled --jq operand: %%s\n" %% operand)
        sys.exit(2)
    sys.exit(0)

if argv[:2] == ["pr", "merge"] and "--disable-auto" in argv:
    if state["disarm_fails"]:
        sys.stderr.write("failed to disable auto-merge: the forge refused\n")
        sys.exit(1)
    sys.exit(0)

sys.stderr.write("unstubbed gh invocation: %%s\n" %% " ".join(argv))
sys.exit(2)
"""


def _run(
    *,
    box: _Refresh,
    check_suite: str = _PASSING_GATE,
    extra_env: dict[str, str] | None = None,
    petri: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", _rendered_refresh_script(petri=petri, check_suite=check_suite)],
        cwd=box.clone,
        capture_output=True,
        text=True,
        check=False,
        env=_env(box=box, extra=extra_env),
    )


def test_an_advanced_default_is_rebased_gated_and_republished_under_a_lease(
    tmp_path: Path,
) -> None:
    """The one path that REWRITES, end to end, asserted on origin's own refs.

    Four things have to hold together and each is separately satisfiable while
    the requirement is unmet: origin's publish branch must now carry the rebased
    head, that head must contain the advanced default, the recorded provenance
    must have been rewritten to it (or the NEXT refresh refuses its own push as
    foreign), and the changed marker must be set (or `pr_refresh_head` routes a
    rebased head to `pr` on proof of the old one).
    """
    box = _build(root=tmp_path)
    before = box.remote_head(ref=_BRANCH)
    advanced = _advance_default(box=box)

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_REFRESH_CHANGED" in result.stderr
    republished = box.remote_head(ref=_BRANCH)
    assert republished != before, "origin still carries the pre-rebase head"
    assert republished == box.local_head()
    contains = subprocess.run(
        ["git", "merge-base", "--is-ancestor", advanced, republished],
        cwd=box.clone,
        check=False,
        capture_output=True,
        text=True,
        env=_fixture_git_env(),
    )
    assert contains.returncode == 0, "the republished head does not contain the advanced default"
    assert box.state(name=PUBLISH_HEAD_STATE_FILENAME) == f"{republished}\n"
    assert box.state(name=REFRESH_COUNT_STATE_FILENAME) == "1\n"
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) == ""


def test_an_armed_pull_request_is_disarmed_before_the_rebase(tmp_path: Path) -> None:
    """The v145 disarm: nothing armed survives into a rewritten head.

    `SPECIFICATION/contracts.md` section "Definition-of-Done and Proof-of-Done
    stages" -> "Scripted publication and proof-head integrity" (v145) requires
    this stage to read whether the run's pull request carries an auto-merge
    request and, when it does, to remove it BEFORE it rebases. What that closes
    is a merge of an unproved head: an armed pull request whose checks are green
    merges on the forge's own schedule, so a refresh that pushed a rebased head
    while the arming stood would hand the forge a tree no record names.

    THE ORDER IS OBSERVED RATHER THAN INFERRED. The stub records the clone's own
    head at each call, so the disarm is asserted to have happened while the
    clone still stood at the PRE-refresh head -- a disarm issued after the
    rebase leaves exactly the same final refs and exactly the same call list.
    """
    box = _build(root=tmp_path, armed=True)
    before = box.local_head()
    _ = _advance_default(box=box)

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_REFRESH_DISARMED" in result.stderr
    assert "LIVESPEC_PR_REFRESH_CHANGED" in result.stderr
    assert box.disarm_heads() == [before]
    # And the rebase really happened, so the disarm is not a no-op path.
    assert box.local_head() != before
    assert box.remote_head(ref=_BRANCH) == box.local_head()


@pytest.mark.parametrize("petri", _RENDERINGS)
def test_the_arming_read_hands_jq_a_bare_field_path_on_both_renderings(
    *,
    petri: bool,
    tmp_path: Path,
) -> None:
    """One committed spelling of the auto-merge read works on BOTH engines.

    THE PETRI LEG IS THE ONE THAT WAS FAILING, and it failed closed at the one
    guard that stands in front of every rewrite (work-item bd-ib-be5r7o). A DOT
    attribute string escapes a double quote and a backslash and NOTHING ELSE, so
    a backslash written in front of a single quote in the graph is not an escape:
    the pinned engine's reader drops it by accident, while a Petri-era reader
    hands it to the shell, where a backslashed quote is a LITERAL quote
    character. `gh` then forwards `'.autoMergeRequest'`, quote characters and
    all, to `jq`, which cannot parse it.

    Measured 2026-10-16 on hp-candidate :32278 under plugin v0.203.2: the
    PR-anchored resumes of `bd-ib-tixpma` (run 01M532Z6ENF0, pull request 3114)
    and `bd-ib-o6aeji` (run 01M5330YQQFQ, pull request 3113) both printed jq's
    "failed to parse jq expression (line 1, column 1)" with literal single quotes
    around the field path, then refused under
    `LIVESPEC_PR_REFRESH_ARMING_UNREADABLE` before any rebase or push -- so
    neither resume reached the refresh it was released for.

    THE EXPRESSION IS READ OFF THE RECORDER, not inferred from the outcome. The
    stub answers the field without consulting `--jq` at all, exactly as a forge
    double must (it has no JSON document to filter), so every other case in this
    module passes on both renderings while the real `gh` would reject the
    expression outright. The recorded operand is therefore the only instrument
    here that can tell the two spellings apart.

    The pinned leg is the control: the same committed bytes behave this way on
    the engine the factory runs today, which is what makes ONE spelling enough
    for both.
    """
    box = _build(root=tmp_path, armed=True)
    _ = _advance_default(box=box)

    result = _run(box=box, petri=petri)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_REFRESH_ARMING_UNREADABLE" not in result.stderr
    assert "LIVESPEC_PR_REFRESH_DISARMED" in result.stderr
    reads = [
        cast("list[str]", call["argv"])
        for call in box.forge_calls()
        if cast("list[str]", call["argv"])[:2] == ["pr", "view"]
    ]
    assert reads, "the stage read no arming"
    argv = reads[0]
    assert argv[argv.index("--jq") + 1] == _AUTO_MERGE_FIELD_PATH


def test_an_unarmed_pull_request_is_not_disarmed(tmp_path: Path) -> None:
    """The ordinary refresh issues the READ and no write at all.

    The control for the case above: without it, "the arming was removed" is
    equally consistent with a stage that issues `--disable-auto` on every
    refresh, which spends a forge write per refresh and reports a removal that
    removed nothing.

    IT IS ALSO THE CASE THAT WAS FAILING ON EVERY REAL FORGE (work-item
    bd-ib-fisgni). Under a bare `.autoMergeRequest` path `gh` prints an unarmed
    pull request's null as nothing, so the stage read it as a forge that would
    not answer and failed closed with `LIVESPEC_PR_REFRESH_ARMING_UNREADABLE`.
    Measured 2026-10-17: bd-ib-o6aeji's resume run 01M542TM46NS on
    hp-candidate, pull request 3113. This case passed throughout because its
    forge double printed `null` for any operand. The double now renders the
    operand the way `gh` does, which is what lets this case see the defect.
    """
    box = _build(root=tmp_path)
    _ = _advance_default(box=box)

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_REFRESH_ARMING_UNREADABLE" not in result.stderr
    assert "LIVESPEC_PR_REFRESH_CHANGED" in result.stderr
    assert "LIVESPEC_PR_REFRESH_DISARMED" not in result.stderr
    assert box.disarm_heads() == []
    assert [cast("list[str]", call["argv"])[:2] for call in box.forge_calls()] == [["pr", "view"]]


def test_an_unreadable_arming_fails_closed_before_any_rewrite(tmp_path: Path) -> None:
    """A forge that cannot answer is not a pull request known to be unarmed.

    The clause says the stage fails closed naming the MEASUREMENT, and the
    direction matters: proceeding on an unreadable answer is how a rebase
    rewrites the head of a pull request the forge is holding armed, which is the
    one outcome the disarm exists to prevent. Origin is asserted untouched on
    BOTH refs, because "nothing was pushed" is the claim and a stage that
    refused after its rebase would still have left the clone rewritten.
    """
    box = _build(root=tmp_path, arming_unreadable=True)
    before = box.remote_head(ref=_BRANCH)
    advanced = _advance_default(box=box)

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_REFRESH_ARMING_UNREADABLE" in result.stderr
    assert box.remote_head(ref=_BRANCH) == before
    assert box.remote_head(ref=_DEFAULT_BRANCH) == advanced
    assert box.state(name=REFRESH_COUNT_STATE_FILENAME) is None


def test_a_failed_disarm_fails_closed_before_any_rewrite(tmp_path: Path) -> None:
    """An arming that could not be REMOVED is the same hazard, named separately.

    Two sentinels rather than one because the remedies differ: an unreadable
    arming is a forge that would not answer, while a refused `--disable-auto` is
    an arming that is still standing -- and an operator reading the second has a
    pull request to disarm by hand before anything can be re-dispatched.
    """
    box = _build(root=tmp_path, armed=True, disarm_fails=True)
    before = box.remote_head(ref=_BRANCH)
    _ = _advance_default(box=box)

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_REFRESH_DISARM_FAILED" in result.stderr
    assert box.remote_head(ref=_BRANCH) == before
    assert box.state(name=REFRESH_COUNT_STATE_FILENAME) is None


def test_an_unchanged_default_owes_no_rebase_and_pushes_nothing(tmp_path: Path) -> None:
    """The common path: the publish head already contains the default, so stop.

    Asserted on the ABSENCE of the changed marker as well as on the sentinel,
    because `pr_refresh_head` reads only the marker -- a stage that reported
    unchanged while leaving a marker behind would still route to `proof_capture`.
    """
    box = _build(root=tmp_path)
    before = box.remote_head(ref=_BRANCH)

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_REFRESH_UNCHANGED" in result.stderr
    assert box.remote_head(ref=_BRANCH) == before
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None
    assert box.state(name=REFRESH_COUNT_STATE_FILENAME) is None


def test_a_foreign_remote_publish_head_is_refused_before_any_rewrite(tmp_path: Path) -> None:
    """A publish branch someone else moved is not this run's to lease over.

    The default branch is advanced TOO, so the stage would otherwise have real
    work to do: without that, a build whose ownership test never ran would exit
    on the unchanged arm and look identical to one that refused.
    """
    box = _build(root=tmp_path)
    foreign = _branch_clone(box=box, name="foreign")
    _ = _commit(
        cwd=foreign, path="foreign.txt", text="not this run\n", subject="feat: a foreign change"
    )
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=foreign)
    _ = _advance_default(box=box)
    foreign_head = box.remote_head(ref=_BRANCH)

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_REFRESH_FOREIGN_HEAD" in result.stderr
    assert box.remote_head(ref=_BRANCH) == foreign_head, "the foreign head was overwritten"
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None


def test_an_absent_remote_publish_ref_is_refused(tmp_path: Path) -> None:
    """A branch origin no longer carries is not recreated from a local tree.

    The sentinel asserted is the FETCH's -- `LIVESPEC_PR_REFRESH_ORIGIN_
    UNOBSERVABLE` -- rather than the dedicated remote-ref-unknown one, because
    the fetch names both refs and fails first. That attribution imprecision was
    raised as an ADVISORY finding on this work-item and was not accepted, so the
    control asserts what the shipped stage DOES rather than what a reworded
    version would; the load-bearing half either way is that it fails closed and
    rewrites nothing.
    """
    box = _build(root=tmp_path)
    _ = _git("push", "--quiet", "origin", "--delete", f"refs/heads/{_BRANCH}", cwd=box.clone)

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_REFRESH_ORIGIN_UNOBSERVABLE" in result.stderr
    assert box.remote_head(ref=_BRANCH) == "", "a deleted publish branch was recreated"


def test_a_run_with_no_recorded_provenance_refuses_before_touching_any_ref(
    tmp_path: Path,
) -> None:
    """With nothing recorded and no validated resume head, there is nothing to own."""
    box = _build(root=tmp_path)
    (box.state_dir() / PUBLISH_HEAD_STATE_FILENAME).unlink()
    before = box.remote_head(ref=_BRANCH)
    _ = _advance_default(box=box)

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_REFRESH_NO_PROVENANCE" in result.stderr
    assert box.remote_head(ref=_BRANCH) == before


@pytest.mark.parametrize("advance_default", [False, True])
def test_a_validated_resume_head_supplies_the_provenance_the_record_lacks(
    *,
    tmp_path: Path,
    advance_default: bool,
) -> None:
    """Resume through the Dispatcher's checkout and environment, with no saved head.

    The old control supplied the fallback variable by hand, so it passed while
    every real resume failed. Start this clone on the default branch instead,
    execute the rendered prepare step, and give the stage only the environment
    the overlay actually emits. Both refresh outcomes must accept that provenance.
    """
    box = _build(root=tmp_path)
    recorded = box.local_head()
    (box.state_dir() / PUBLISH_HEAD_STATE_FILENAME).unlink()
    if advance_default:
        _ = _advance_default(box=box)
    _ = _git("checkout", "--detach", "origin/master", cwd=box.clone)
    assert box.local_head() != recorded
    overlay = render_run_config_overlay(
        committed_text='[workflow]\ngraph = "workflow.fabro"\n[run.environment]\nid = "sandbox"\n',
        workflow_dir=tmp_path,
        token="",
        github_token="",
        siblings=None,
        resume_checkout=resume_checkout_for(
            args=argparse.Namespace(resume_head=recorded),
            branch=_BRANCH,
        ),
    )
    assert overlay is not None
    parsed = tomli.loads(overlay)
    overlay_env = parsed["environments"]["sandbox"]["env"]
    [checkout_step] = [
        step["script"]
        for step in parsed["run"]["prepare"]["steps"]
        if "git checkout --detach" in step["script"]
    ]
    prepared = subprocess.run(
        ["bash", "-c", checkout_step],
        cwd=box.clone,
        check=False,
        capture_output=True,
        text=True,
        env=_env(box=box, extra=overlay_env),
    )
    assert prepared.returncode == 0, prepared.stderr
    assert box.local_head() == recorded
    assert box.state(name=PUBLISH_HEAD_STATE_FILENAME) is None
    assert box.remote_head(ref=_BRANCH) == recorded

    result = _run(box=box, extra_env=overlay_env)

    assert result.returncode == 0, result.stderr
    outcome = "CHANGED" if advance_default else "UNCHANGED"
    assert f"LIVESPEC_PR_REFRESH_{outcome}" in result.stderr
    assert "LIVESPEC_PR_REFRESH_NO_PROVENANCE" not in result.stderr
    assert box.remote_head(ref=_BRANCH) == box.local_head()


def test_a_conflicting_rebase_is_aborted_with_no_side_chosen(tmp_path: Path) -> None:
    """A conflict preserves the run tree; it does not pick a winner.

    Three instruments, because "it exited 1" is cheap. The rebase must be ABORTED
    (no in-progress rebase directory left, which would wedge every later stage),
    HEAD must be back at the head this run published, and the conflicted file
    must carry no merge markers -- the shape a build that resolved by taking one
    side would leave.

    SINCE v134 THE SENTINEL IS THE REPAIR ONE rather than
    `LIVESPEC_PR_REFRESH_CONFLICT`: a conflicted refresh now restores its
    published head and routes to the `fix` node, and that fail-closed sentinel is
    reached only once the two-round repair budget is spent. Every property this
    case was written for is unchanged and is exactly what the repair depends on --
    the abort, the restored head and the unresolved file -- so all three are
    asserted as before. The repair's own accounting is bound in
    `test_workflow_refresh_repair_scenario176.py`.
    """
    box = _build(root=tmp_path)
    published = _commit(
        cwd=box.clone,
        path=_SHARED_FILE,
        text="this run's edit\n",
        subject="feat: edit the shared file",
    )
    _ = _git("push", "--quiet", "--force", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=box.clone)
    _ = (box.state_dir() / PUBLISH_HEAD_STATE_FILENAME).write_text(published, encoding="utf-8")
    _ = _advance_default(box=box, text="a conflicting default edit\n")

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_REFRESH_REPAIR" in result.stderr
    assert box.local_head() == published, "the aborted rebase left HEAD somewhere else"
    assert not (box.clone / ".git" / "rebase-merge").exists()
    assert not (box.clone / ".git" / "rebase-apply").exists()
    assert "<<<<<<<" not in (box.clone / _SHARED_FILE).read_text(encoding="utf-8")
    assert box.remote_head(ref=_BRANCH) == published
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None


def _published_record_conflict(
    *,
    box: _Refresh,
    path: str,
    run_text: str,
    default_text: str,
    extra: tuple[str, str] | None = None,
) -> str:
    """Publish a run edit to one record file, then advance the default branch into it.

    The two sides edit the SAME file and Git decides whether that is a conflict,
    which is the whole point of driving the shipped stage here rather than the
    merger alone: a fixture that declared a conflict could not tell a stage that
    merges declared records from one that merges whatever it is handed.
    """
    if extra is not None:
        extra_path, extra_text = extra
        _ = (box.clone / extra_path).write_text(extra_text, encoding="utf-8")
        _ = _git("add", extra_path, cwd=box.clone)
    published = _commit(
        cwd=box.clone, path=path, text=run_text, subject="feat: this run's record entry"
    )
    _ = _git("push", "--quiet", "--force", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=box.clone)
    _ = (box.state_dir() / PUBLISH_HEAD_STATE_FILENAME).write_text(published, encoding="utf-8")
    if extra is not None:
        _ = _advance_default(box=box, path=extra[0], text="a conflicting default edit\n")
    _ = _advance_default(box=box, path=path, text=default_text)
    return published


def test_a_declared_json_record_conflict_merges_and_republishes_without_repair(
    tmp_path: Path,
) -> None:
    """Scenario 200's first sub-scenario, against the shipped `pr_refresh` bytes.

    Five things have to hold together, and each is separately satisfiable while
    the requirement is unmet: the rebase must COMPLETE (a stage that resolved the
    file and left the rebase stopped publishes nothing), the merged array must
    carry both sides' entries in the ratified order, the gate must have run on
    the merged head, origin must now carry it, and NO refresh-repair round may be
    counted — which is the whole cost this item was filed to remove.
    """
    box = _build(root=tmp_path)
    _ = _published_record_conflict(
        box=box,
        path=_RECORD_JSON,
        run_text='[{"id": "seed"}, {"id": "run"}]\n',
        default_text='[{"id": "seed"}, {"id": "default"}]\n',
    )

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_RECORD_FILE_REFRESH_RESOLVED: pr_refresh" in result.stderr
    assert "LIVESPEC_REFRESH_REPAIR" not in result.stderr
    assert json.loads((box.clone / _RECORD_JSON).read_text(encoding="utf-8")) == [
        {"id": "seed"},
        {"id": "default"},
        {"id": "run"},
    ]
    assert not (box.clone / ".git" / "rebase-merge").exists()
    assert not (box.clone / ".git" / "rebase-apply").exists()
    assert box.remote_head(ref=_BRANCH) == box.local_head()
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) == ""
    assert box.state(name=REFRESH_COUNT_STATE_FILENAME) == "1\n"


def test_a_declared_json_record_merge_is_recorded_with_its_format_and_per_side_counts(
    tmp_path: Path,
) -> None:
    """The stage's own output names each file it merged, its format and both counts.

    Separate from the case above because it is a claim about the RECORD rather
    than about the tree: a stage that merged correctly and reported nothing
    leaves an operator triaging the next collision with no way to tell a merged
    refresh from one that never conflicted.
    """
    box = _build(root=tmp_path)
    _ = _published_record_conflict(
        box=box,
        path=_RECORD_JSON,
        run_text='[{"id": "seed"}, {"id": "run"}]\n',
        default_text='[{"id": "seed"}, {"id": "default"}]\n',
    )

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert (
        f"LIVESPEC_RECORD_FILE_MERGED: path={_RECORD_JSON} format=json-array "
        "default-count=2 run-count=1"
    ) in result.stderr


def test_a_declared_markdown_record_conflict_keeps_the_defaults_lines_then_the_runs(
    tmp_path: Path,
) -> None:
    """Scenario 200's second sub-scenario: both sides inserted at the same place.

    This is the `tests/integration/CLAUDE.md` collision in miniature — two runs
    each appending their own entry to the end of one registry — and the ORDER is
    asserted rather than mere containment, because a stage that kept both lines
    in the other order has resolved the conflict by rewriting the default
    branch's record rather than by extending it.
    """
    box = _build(root=tmp_path)
    _ = _published_record_conflict(
        box=box,
        path=_RECORD_MARKDOWN,
        run_text="- seed entry\n- the run's entry\n",
        default_text="- seed entry\n- the default branch's entry\n",
    )

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_RECORD_FILE_REFRESH_RESOLVED: pr_refresh" in result.stderr
    assert (box.clone / _RECORD_MARKDOWN).read_text(encoding="utf-8") == (
        "- seed entry\n- the default branch's entry\n- the run's entry\n"
    )
    assert (
        f"LIVESPEC_RECORD_FILE_MERGED: path={_RECORD_MARKDOWN} format=markdown-insertions "
        "default-count=1 run-count=1"
    ) in result.stderr
    assert box.remote_head(ref=_BRANCH) == box.local_head()


def test_a_conflict_outside_the_declared_records_merges_nothing_and_takes_repair(
    tmp_path: Path,
) -> None:
    """Scenario 200's fourth sub-scenario, and the control the merge arm needs.

    The declared record conflicts HERE TOO, so a stage that merged the paths it
    recognised and handed back only the rest would pass every assertion of the
    merge cases above while publishing a tree whose undeclared conflict nobody
    resolved. The discriminating assertion is that the record file is UNCHANGED
    on the restored head: nothing was merged, not merely nothing was pushed.
    """
    box = _build(root=tmp_path)
    published = _published_record_conflict(
        box=box,
        path=_RECORD_JSON,
        run_text='[{"id": "seed"}, {"id": "run"}]\n',
        default_text='[{"id": "seed"}, {"id": "default"}]\n',
        extra=(_SHARED_FILE, "this run's edit\n"),
    )

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_RECORD_FILE_REFRESH_RESOLVED" not in result.stderr
    assert "LIVESPEC_REFRESH_REPAIR" in result.stderr
    assert _SHARED_FILE in result.stderr
    assert box.local_head() == published
    assert box.remote_head(ref=_BRANCH) == published
    assert json.loads((box.clone / _RECORD_JSON).read_text(encoding="utf-8")) == [
        {"id": "seed"},
        {"id": "run"},
    ]
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None


def test_a_later_unmergeable_conflict_is_named_in_the_refresh_repair_brief(
    tmp_path: Path,
) -> None:
    """A resolved record conflict cannot hide the later conflict that stopped rebase.

    The first replayed commit conflicts only in a declared record and is therefore
    resolved by the merger. The second then conflicts in an undeclared file. The
    repair brief is the fix turn's work order, so it must name the conflict still
    present when resolution stopped rather than the record path the helper already
    completed.
    """
    box = _build(root=tmp_path)
    _ = _commit(
        cwd=box.clone,
        path=_RECORD_JSON,
        text='[{"id": "seed"}, {"id": "run"}]\n',
        subject="feat: add the run record",
    )
    published = _commit(
        cwd=box.clone,
        path=_SHARED_FILE,
        text="this run's undeclared edit\n",
        subject="feat: edit the shared file",
    )
    _ = _git("push", "--quiet", "--force", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=box.clone)
    _ = (box.state_dir() / PUBLISH_HEAD_STATE_FILENAME).write_text(published, encoding="utf-8")
    _ = _advance_default(
        box=box,
        path=_RECORD_JSON,
        text='[{"id": "seed"}, {"id": "default"}]\n',
    )
    _ = _advance_default(box=box, path=_SHARED_FILE, text="default's undeclared edit\n")

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_REFRESH_REPAIR" in result.stderr
    assert f"conflicted-paths: {_SHARED_FILE}" in result.stderr
    assert f"conflicted-paths: {_RECORD_JSON}" not in result.stderr
    assert box.local_head() == published
    assert box.remote_head(ref=_BRANCH) == published


def test_a_declared_record_whose_key_both_sides_changed_differently_takes_repair(
    tmp_path: Path,
) -> None:
    """Scenario 200's third sub-scenario: a declared path is not enough on its own.

    Same file, same declaration and the same Git conflict as the merge case —
    only the CONTENT differs, both sides having changed the entry keyed `seed`.
    So a stage that merged every conflict in a declared path, rather than every
    RESOLVABLE one, is green above and red only here.
    """
    box = _build(root=tmp_path)
    published = _published_record_conflict(
        box=box,
        path=_RECORD_JSON,
        run_text='[{"id": "seed", "test": "tests.run"}]\n',
        default_text='[{"id": "seed", "test": "tests.default"}]\n',
    )

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_RECORD_FILE_MERGE_REFUSED" in result.stderr
    assert "LIVESPEC_RECORD_FILE_REFRESH_RESOLVED" not in result.stderr
    assert "LIVESPEC_REFRESH_REPAIR" in result.stderr
    assert box.local_head() == published
    assert box.remote_head(ref=_BRANCH) == published
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None


def test_a_merged_record_head_the_gate_rejects_takes_repair(tmp_path: Path) -> None:
    """Scenario 200's fifth sub-scenario: the gate still decides the merged head.

    The merge is the SAME resolvable one that republishes above, so this case
    separates "the arm completed the rebase" from "the arm published": a stage
    that treated its own merge as sufficient would leave origin carrying a head
    the repository's gate refuses.
    """
    box = _build(root=tmp_path)
    published = _published_record_conflict(
        box=box,
        path=_RECORD_JSON,
        run_text='[{"id": "seed"}, {"id": "run"}]\n',
        default_text='[{"id": "seed"}, {"id": "default"}]\n',
    )

    result = _run(box=box, check_suite=_FAILING_GATE)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_RECORD_FILE_REFRESH_RESOLVED: pr_refresh" in result.stderr
    assert "LIVESPEC_REFRESH_REPAIR" in result.stderr
    assert box.local_head() == published
    assert box.remote_head(ref=_BRANCH) == published
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None


def test_a_failing_post_rebase_gate_pushes_nothing(tmp_path: Path) -> None:
    """The gate is a PRECONDITION of the push, not a report alongside it.

    The rebase has already happened when the gate runs, so the discriminating
    assertion is about ORIGIN: a build that pushed first and gated afterwards
    would leave the rebased head published and exit non-zero all the same.
    """
    box = _build(root=tmp_path)
    before = box.remote_head(ref=_BRANCH)
    _ = _advance_default(box=box)

    result = _run(box=box, check_suite=_FAILING_GATE)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_REFRESH_REPAIR" in result.stderr
    assert box.remote_head(ref=_BRANCH) == before, "a failed gate still published"
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None
    assert box.state(name=PUBLISH_HEAD_STATE_FILENAME) == before
    # The refresh COUNT does move, and that is v134's own requirement rather than
    # a relaxation of this case: the bound counts each visit that refreshed onto
    # an advanced default whether the refresh succeeded or routed to repair, so a
    # repaired refresh that left the counter alone would let a run alternate
    # repair and refresh past the bound forever.
    assert box.state(name=REFRESH_COUNT_STATE_FILENAME) == "1\n"


def test_a_remote_moving_after_observation_is_rejected_by_the_lease(tmp_path: Path) -> None:
    """The lease is what makes the one rewriting capability safe, so it is driven.

    The expected object is read BEFORE the rebase and the gate, so a check suite
    that moves origin's publish branch reproduces exactly the window the lease
    exists to close -- without needing to interleave two processes. A bare force
    push, or a lease carrying an empty expected object, would succeed here.
    """
    box = _build(root=tmp_path)
    mover = _branch_clone(box=box, name="lease-mover")
    late = _commit(
        cwd=mover, path="late.txt", text="landed mid-gate\n", subject="feat: land mid-gate"
    )
    racing_gate = box.clone.parent / "racing-gate.sh"
    _ = racing_gate.write_text(
        f'git -C "{mover}" push --quiet origin "HEAD:refs/heads/{_BRANCH}"\n',
        encoding="utf-8",
    )
    _ = _advance_default(box=box)

    result = _run(box=box, check_suite=f'bash "{racing_gate}"')

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_REFRESH_LEASE_FAILED" in result.stderr
    assert box.remote_head(ref=_BRANCH) == late
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None
    assert box.state(name=REFRESH_COUNT_STATE_FILENAME) is None


def test_a_non_numeric_refresh_counter_fails_closed(tmp_path: Path) -> None:
    """A counter nothing can compare cannot bound anything, so it refuses.

    This is the arm the node's own comment calls out as the natural coding
    error: `test "$count" -ge 3` returns 2 on a non-numeric value, which an `if`
    reads as "below the bound" -- so the plausible spelling of this guard lets a
    corrupt counter refresh forever. The control is therefore the push NOT
    happening, not merely a non-zero exit.
    """
    box = _build(root=tmp_path)
    before = box.remote_head(ref=_BRANCH)
    _ = (box.state_dir() / REFRESH_COUNT_STATE_FILENAME).write_text("many", encoding="utf-8")
    _ = _advance_default(box=box)

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_REFRESH_COUNT_UNREADABLE" in result.stderr
    assert box.remote_head(ref=_BRANCH) == before
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None


def test_the_three_refresh_bound_stops_a_fourth_refresh(tmp_path: Path) -> None:
    """Three completed refreshes is the bound, so the fourth does not rewrite.

    The control is the pair: at two the same world refreshes, at three it
    refuses. Asserting only the refusal would pass for a build that refuses
    every refresh, and asserting only the success would pass for an unbounded
    one.
    """
    bounded = _build(root=tmp_path / "bounded")
    _ = (bounded.state_dir() / REFRESH_COUNT_STATE_FILENAME).write_text("3", encoding="utf-8")
    at_bound_before = bounded.remote_head(ref=_BRANCH)
    _ = _advance_default(box=bounded)

    refused = _run(box=bounded)

    assert refused.returncode == 1, refused.stdout
    assert "LIVESPEC_PR_REFRESH_NON_CONVERGED" in refused.stderr
    assert bounded.remote_head(ref=_BRANCH) == at_bound_before
    assert bounded.state(name=REFRESH_COUNT_STATE_FILENAME) == "3"

    below = _build(root=tmp_path / "below")
    _ = (below.state_dir() / REFRESH_COUNT_STATE_FILENAME).write_text("2", encoding="utf-8")
    _ = _advance_default(box=below)

    allowed = _run(box=below)

    assert allowed.returncode == 0, allowed.stderr
    assert "LIVESPEC_PR_REFRESH_CHANGED" in allowed.stderr
    assert below.state(name=REFRESH_COUNT_STATE_FILENAME) == "3\n"


def test_a_stale_changed_marker_is_cleared_at_every_entry(tmp_path: Path) -> None:
    """A marker from an earlier refresh must not route an unchanged head onward.

    The node's own comment names this: `pr_refresh_head` reads only the marker,
    so a marker left behind by a previous refresh of the SAME run would send an
    unchanged head back through capture forever.
    """
    box = _build(root=tmp_path)
    _ = (box.state_dir() / REFRESH_CHANGED_STATE_FILENAME).write_text("stale", encoding="utf-8")

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_REFRESH_UNCHANGED" in result.stderr
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None


def test_an_absent_exact_head_push_program_fails_closed(tmp_path: Path) -> None:
    """Without the materialized helper no rewrite can be PROVEN to carry a lease.

    The stage must not fall back to an inline push, so the assertion is that
    origin is untouched after a run that had real work to do and a passing gate.
    """
    box = _build(root=tmp_path)
    before = box.remote_head(ref=_BRANCH)
    (box.plugins_root / PUBLICATION_PUSH_PROGRAM_FILENAME).unlink()
    _ = _advance_default(box=box)

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_REFRESH_PUSH_PROGRAM_ABSENT" in result.stderr
    assert box.remote_head(ref=_BRANCH) == before


def test_the_refresh_execution_boundary_leaves_enclosing_run_state_intact(
    tmp_path: Path,
) -> None:
    """Executing the refresh here cannot touch the publication state of a real run.

    THE REGRESSION CONTROL FOR THIS FILE'S OWN SAFETY, and it matters more for
    this node than for any other: `pr_refresh` runs `sandbox_check_suite` -- this
    suite -- as its post-rebase gate, in the same sandbox, AFTER establishing its
    provenance and while its refresh counter stands. A control that wrote
    publication state at a fixed shared path would erase that live counter
    mid-gate and let the next refresh restart at one, evading the three-refresh
    bound; on a gate failure it would also drop the published-head marker.
    Anchoring state to each control's own `$GIT_DIR` makes that impossible by
    construction, and this control is what proves the construction holds.

    THE SHARED-PATH LEG IS A BEFORE/AFTER COMPARISON, NOT AN ABSENCE CHECK, and
    the difference decides whether this control measures anything. Asserting
    those paths are ABSENT grades the ambient machine: a leftover from any
    earlier build fails the control while saying nothing about the boundary, and
    a clean machine passes it just as uninformatively. Comparing each path's
    bytes before against after is what actually asks whether EXECUTING THE STAGE
    touched it.

    BOTH A SUCCEEDING AND A FAILING ARM are run, because a gate failure is
    exactly when the original finding lost state.
    """
    enclosing = tmp_path / "enclosing" / ".git" / PUBLICATION_STATE_GIT_PATH
    enclosing.mkdir(parents=True)
    sentinels = {name: f"enclosing-run-{name}" for name in publication_state_filenames()}
    for name, text in sentinels.items():
        _ = (enclosing / name).write_text(text, encoding="utf-8")
    assert sentinels, "the state filename set must not be empty"

    def shared_state() -> dict[str, str | None]:
        """Each fixed shared path's bytes, or `None` where it does not exist."""
        snapshot: dict[str, str | None] = {}
        for name in publication_state_filenames():
            path = Path(os.sep) / "tmp" / name
            snapshot[name] = path.read_text(encoding="utf-8") if path.is_file() else None
        return snapshot

    before = shared_state()
    passing_box = _build(root=tmp_path / "passing")
    failing_box = _build(root=tmp_path / "failing")
    _ = _advance_default(box=passing_box)
    _ = _advance_default(box=failing_box)
    passing = _run(box=passing_box)
    failing = _run(box=failing_box, check_suite=_FAILING_GATE)

    assert passing.returncode == 0, passing.stderr
    assert failing.returncode == 1, failing.stdout
    for name, text in sentinels.items():
        path = enclosing / name
        assert path.is_file(), f"{name} was removed by a refresh execution control"
        assert path.read_text(encoding="utf-8") == text, name
    assert shared_state() == before, "a refresh execution control touched a fixed shared path"
    # The POSITIVE half: each control's own state resolved inside its own
    # `$GIT_DIR`, which is the mechanism that makes the two legs above hold. The
    # passing arm wrote a counter there and the failing arm did not, so the one
    # directory carries both answers.
    assert passing_box.state(name=REFRESH_COUNT_STATE_FILENAME) == "1\n"
    # Both boxes now record a refresh, because v134 counts the repaired visit
    # too; what this case grades is that each recorded it in its OWN clone, which
    # is the boundary under test.
    assert failing_box.state(name=REFRESH_COUNT_STATE_FILENAME) == "1\n"


def test_the_executed_bytes_are_the_committed_bytes(tmp_path: Path) -> None:
    """The substitutions stand in for the ENGINE and touch nothing else.

    Without this, every control above is equally consistent with a harness that
    rewrote the recipe into something easier to pass. Three assertions, because
    each covers a different way the extraction could drift: the executed text
    must be the committed `script` attribute apart from the two engine tokens,
    those tokens must have been present to substitute, and no other `{{ ... }}`
    may survive into the bytes a control runs.
    """
    graph = parse_dot_graph(text=_IMPLEMENT_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    committed = graph.nodes["pr_refresh"]["script"]
    assert "{{ inputs.default_branch }}" in committed
    assert "{{ inputs.sandbox_check_suite }}" in committed
    executed = _refresh_script(check_suite=_PASSING_GATE)
    assert "{{" not in executed
    assert executed == committed.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH).replace(
        "{{ inputs.sandbox_check_suite }}", _PASSING_GATE
    )
    # And the one program the stage re-enters is the production one, written from
    # its own source rather than restated: a control whose push helper was a
    # local stand-in would prove nothing about the shipped lease.
    box = _build(root=tmp_path)
    assert (box.plugins_root / PUBLICATION_PUSH_PROGRAM_FILENAME).read_text(
        encoding="utf-8"
    ) == publication_push_program_source()
    assert (box.plugins_root / PLUGIN_GATE_PROGRAM_FILENAME).is_file()
    assert sys.executable, "the control needs an interpreter to have resolved"


def _needs_human_reason_filename() -> str:
    """The reason file the committed `needs_human` terminal reads, off its own bytes.

    Derived rather than spelled, because the whole claim below is that the
    refusal writes the file the TERMINAL reads. A literal here would be a
    second account of that name, and the defect it would hide is the one this
    binding exists to catch: a rename on either side leaves the refusal writing
    a file nothing reads, at which point the terminal silently falls back to its
    generic reason and the non-convergence cause is lost from every durable
    surface.
    """
    graph = parse_dot_graph(text=_IMPLEMENT_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    terminal = graph.nodes["needs_human"]["script"]
    match = re.search(r"git rev-parse --git-path (livespec-[a-z-]+reason)", terminal)
    assert match is not None, terminal
    return match.group(1)


def _generic_terminal_reason() -> str:
    """The terminal's own fallback wording, off its own bytes.

    This is what an operator reads when no stage recorded a cause, so it is the
    exact string the non-convergence ending must NOT produce.
    """
    graph = parse_dot_graph(text=_IMPLEMENT_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    terminal = graph.nodes["needs_human"]["script"]
    match = re.search(r"reason='([^']+)'", terminal)
    assert match is not None, terminal
    return match.group(1)


def test_the_non_convergence_refusal_records_its_cause_for_the_terminal(
    tmp_path: Path,
) -> None:
    """The ratified non-convergence cause has to OUTLIVE the stage that found it.

    Scenario 184's last `pr` clause requires a run that keeps meeting an
    advanced default branch to end with "the ratified non-convergence cause",
    and the only durable surface that carries a cause is the reason file the
    `needs_human` terminal reads and the Dispatcher turns into the item's
    question. The stage's own stderr sentinel is not that surface: it scrolls
    away with the run record.

    THE PAIR IS THE POINT. At the bound the file must name non-convergence; the
    refresh-repair-exhausted arm beside it already writes one, so a case
    asserting only presence would pass for a build that wrote the WRONG arm's
    cause. And the below-bound control must write NOTHING, because a stage that
    recorded a non-convergence cause on an ordinary successful refresh would
    poison the next needs-human ending of the same run with a cause that was
    never true.

    The first line is what the terminal reads (`head -n 1`), so that is the
    line graded rather than the file.
    """
    reason_filename = _needs_human_reason_filename()
    bounded = _build(root=tmp_path / "bounded")
    _ = (bounded.state_dir() / REFRESH_COUNT_STATE_FILENAME).write_text("3", encoding="utf-8")
    _ = _advance_default(box=bounded)

    refused = _run(box=bounded)

    assert refused.returncode == 1, refused.stdout
    assert "LIVESPEC_PR_REFRESH_NON_CONVERGED" in refused.stderr
    recorded = bounded.clone / ".git" / reason_filename
    assert recorded.is_file(), sorted(p.name for p in (bounded.clone / ".git").iterdir())
    first_line = recorded.read_text(encoding="utf-8").splitlines()[0]
    assert "non-converg" in first_line, first_line
    # Not the OTHER arm's cause: that one is about a two-round repair budget and
    # points an operator at a conflict this ending never had.
    assert "refresh-repair-exhausted" not in first_line, first_line
    # And not the terminal's own fallback, which is what a lost cause looks like.
    assert _generic_terminal_reason() not in first_line, first_line

    below = _build(root=tmp_path / "below")
    _ = (below.state_dir() / REFRESH_COUNT_STATE_FILENAME).write_text("2", encoding="utf-8")
    _ = _advance_default(box=below)

    allowed = _run(box=below)

    assert allowed.returncode == 0, allowed.stderr
    assert not (below.clone / ".git" / reason_filename).is_file()


def test_the_refresh_route_visit_caps_admit_the_worst_case_the_bound_allows(
    tmp_path: Path,
) -> None:
    """No engine visit cap can abort a run before the non-convergence cause fires.

    `max_visits` ABORTS rather than routes — it emits no outcome, so no edge
    can carry the exhaustion onward — which is why the clause demands the
    ratified cause and not a cap. A cap sized below the entries the bound
    admits turns every one of those runs into a run that simply stops, with no
    terminal, no preserved reference and no ledger question.

    THE BOUND IS MEASURED, NOT RESTATED. `_bound` is probed off the shipped
    script: the counter value at which the refusal fires is the bound, so the
    arithmetic below is a function of what the stage enforces rather than of a
    number copied beside it.

    THE WORST CASE, DERIVED. A refresh ENTRY and a COUNTED refresh differ: an
    entry finding the publish head already containing the authoritative default
    exits zero and counts nothing. An uncounted entry leaves no changed marker,
    so `pr_refresh_head` sends it straight to `pr`; a counted one changes the
    head, so the proof trio runs and returns to the refresh. The `pr` to
    `pr_refresh` route then makes those uncounted entries reachable in a LOOP.
    So the longest run alternates one uncounted entry, one `pr` visit, one
    counted refresh, up to the bound, and ends on the entry that refuses:

      * `pr_refresh`      — `bound` counted + `bound + 1` uncounted + 1 refusing
      * `pr_refresh_head` — every entry but the refusing one
      * `pr` and `pr_route` — one per uncounted entry
    """
    box = _build(root=tmp_path / "probe")
    _ = (box.state_dir() / REFRESH_COUNT_STATE_FILENAME).write_text("2", encoding="utf-8")
    _ = _advance_default(box=box)
    assert _run(box=box).returncode == 0, "the probe's premise is a refresh that proceeds"
    bound = int(str(box.state(name=REFRESH_COUNT_STATE_FILENAME)).strip())

    entries = 2 * bound + 2
    required = {
        "pr_refresh": entries,
        "pr_refresh_head": entries - 1,
        "pr": bound + 1,
        "pr_route": bound + 1,
    }

    graph = parse_dot_graph(text=_IMPLEMENT_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    for node, worst_case in required.items():
        declared = graph.nodes[node].get("max_visits")
        assert declared is not None, node
        assert int(declared) >= worst_case, (node, declared, worst_case)


@pytest.mark.parametrize("petri", _RENDERINGS)
def test_the_non_convergence_reason_carries_no_quote_character_on_both_renderings(
    *,
    petri: bool,
    tmp_path: Path,
) -> None:
    """The recorded cause is the cause, on BOTH engines, with nothing wrapped round it.

    The fourth span of the same quoting family (work-item bd-ib-be5r7o). The
    non-convergence refusal writes its reason with a backslash-escaped `printf`
    format; a Petri-era reader hands the backslash to the shell, where a
    backslashed quote is a literal quote character and the `\\n` beside it is a
    bare `n`, so the format `printf` receives is a quote-wrapped literal and the
    reason file ends up holding the cause wrapped in quote characters with its
    newline turned into a trailing `n`.

    WHAT THAT COSTS IS THE DURABLE SURFACE, not the stage. The refusal still
    exits 1 under its own sentinel and the run still ends at `needs_human`, so
    nothing looks wrong; the damage is that the cause the Dispatcher turns into
    the item's recorded question arrives punctuated by stray quote characters and
    with no line ending, which is the one artifact an operator reads after the
    run record is gone.

    The file is graded on its WHOLE text rather than its first line, because the
    lost newline is exactly what a `splitlines()[0]` reading cannot see. The
    pinned leg is the control.
    """
    reason_filename = _needs_human_reason_filename()
    box = _build(root=tmp_path)
    _ = (box.state_dir() / REFRESH_COUNT_STATE_FILENAME).write_text("3", encoding="utf-8")
    _ = _advance_default(box=box)

    refused = _run(box=box, petri=petri)

    assert refused.returncode == 1, refused.stdout
    assert "LIVESPEC_PR_REFRESH_NON_CONVERGED" in refused.stderr
    recorded = box.clone / ".git" / reason_filename
    assert recorded.is_file(), sorted(p.name for p in (box.clone / ".git").iterdir())
    body = recorded.read_text(encoding="utf-8")
    assert "'" not in body, body
    assert body.startswith(_NON_CONVERGED_PREFIX), body
    assert body.endswith("\n"), body

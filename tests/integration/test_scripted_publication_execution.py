"""Run the `pr` stage's OWN script bytes against real Git and a controlled forge.

WHY THIS FILE EXISTS SEPARATELY FROM `test_scripted_publication_stages.py`.
That file grades which KIND of stage publishes, which is a property of the
committed payload and is therefore correctly read off the payload. This file
grades what the stage DOES, and a declaration test cannot reach that: a script
attribute containing the right flags is not evidence that the shell around them
reaches the flagged command, fails closed when it should, or stays idempotent on
a second run. `SPECIFICATION/contracts.md` section "Definition-of-Done and
Proof-of-Done stages" -> "Scripted publication and proof-head integrity"
requires the stage to "verify its current head against the head whose proof was
verified" and to publish only that head, and a substring check on the script
cannot distinguish a guard that runs from a guard that is dead code.

THE SCRIPT BYTES ARE READ THROUGH THE CANONICAL PARSER, NEVER RETYPED. Every
control below executes exactly what `.claude-plugin/.fabro/workflows/
implement-work-item/workflow.fabro` ships, extracted with `parse_dot_graph` --
the same reader the Dispatcher's own graph consumers use. A test that embedded
its own copy of the recipe would pass while the shipped stage did something
else, which is the specific failure the recovery review of this work-item
called out.

WHAT IS SIMULATED, AND WHY EACH SUBSTITUTION IS SAFE.

- `{{ inputs.X }}` is substituted here because the pinned ENGINE owns that
  templating, not this repository. Substituting it is standing in for Fabro,
  and the values used are the ones `workflow.toml` declares. Nothing else in
  the bytes is touched.
- `gh` is a STUB on `PATH` serving a JSON forge state, because the controls
  turn on forge TRANSITIONS -- a head that moves between observation and
  arming, a pull request already merged, one closed by a human -- and no real
  forge can be driven through those on demand. The stub records every argv it
  receives, so what the stage ASKED the forge is itself under assertion rather
  than inferred from an outcome.
- Git is REAL, in a real repository with a real `$GIT_DIR`, because the stage
  resolves its state directory through `git rev-parse --git-path` and that
  resolution is part of what is being graded.

The publication-head program is NOT stubbed: each control materializes the
genuine `proof_head_program_source()` and the stage re-enters it by the path
the overlay names, so the proof-identity half of the stage runs its real
reader over real record text.

THE ENCLOSING RUN'S STATE IS NEVER TOUCHED. Each control builds its own
throwaway repository under `tmp_path` and the stage resolves its state
directory inside THAT repository's `$GIT_DIR`, so a control cannot name the
state of a run executing it. `test_the_execution_boundary_leaves_enclosing_run_
state_intact` is the regression control for that property, because this suite
runs inside `sandbox_check_suite`, which `pr_refresh` itself invokes as its
post-rebase gate -- a fixed shared path would let this file erase the live
refresh counter of the very stage running it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import render_run_config_overlay
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_NOT_REPRODUCED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_head import (
    PROOF_HEAD_PROGRAM_FILENAME,
    proof_head_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_metadata import (
    PR_BODY_FILE_ENV_VAR,
    PR_TITLE_ENV_VAR,
    PUBLICATION_BODY_FILENAME,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_state import (
    PUBLICATION_STATE_GIT_PATH,
    PUBLISH_HEAD_STATE_FILENAME,
    publication_state_filenames,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    PUBLISH_HEAD_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import ResumeCheckout
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
_PR_NUMBER = 4242
# Two distinct full shas. The stage compares them as opaque strings, so what
# matters is only that they differ and both look like object names.
_HEAD = "1111111111111111111111111111111111111111"
_MOVED_HEAD = "2222222222222222222222222222222222222222"
_MERGE_SHA = "3333333333333333333333333333333333333333"

# The forge stub. It is a program rather than a Python mock because the stage
# reaches `gh` through `PATH` as a subprocess, and so does the publication-head
# program it re-enters -- an in-process mock would be invisible to both.
#
# `advance_head_on` is what makes the race control possible: the stage observes
# the head, establishes proof, then edits and readies before arming, so naming
# a later subcommand moves the branch strictly BETWEEN the observation and the
# arming. That is the window the exact-head requirement exists to close.
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
        "isDraft": "true" if state["isDraft"] else "false",
        "autoMergeRequest": "null" if state["autoMergeRequest"] is None else "{}",
        "mergeCommit": state["mergeCommit"] or "",
    }
    save(state)
    if field == "comments":
        print(json.dumps({"comments": state["comments"]}))
        sys.exit(0)
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
    state["autoMergeRequest"] = {"enabledAt": "now"}
    save(state)
    sys.exit(0)

sys.stderr.write("unstubbed gh invocation: %%s\n" %% " ".join(argv))
sys.exit(2)
"""


def _pr_script(*, merge_mode: str = "rebase", merge_hold: str = "false") -> str:
    """The shipped `pr` node's script, with only the engine's own tokens bound.

    Read through the canonical parser so the bytes under execution are the
    bytes under version control. The two substitutions stand in for the pinned
    engine's templating and for nothing else.
    """
    graph = parse_dot_graph(text=_IMPLEMENT_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script = graph.nodes["pr"]["script"]
    return script.replace("{{ inputs.merge_mode }}", merge_mode).replace(
        "{{ inputs.merge_hold }}", merge_hold
    )


def _record(*, verdict: str, head: str) -> dict[str, str]:
    """One Proof of Done comment, in the header shape the real reader requires."""
    return {
        "body": f"Proof of Done — {verdict} — run r — 2026-10-12T00:00:00Z\n{PUBLISH_HEAD_LABEL}: {head}\n"
    }


def _proven(*, head: str) -> list[dict[str, str]]:
    """A capture and a replay agreeing on `head` -- the conforming chain."""
    return [
        _record(verdict=VERDICT_CAPTURED, head=head),
        _record(verdict=VERDICT_VERIFIED, head=head),
    ]


class _Sandbox:
    """One control's throwaway world: a real repository, a stub forge, a program.

    Holds the paths each assertion reads back, so a control states what it
    expects rather than re-deriving where things landed.
    """

    def __init__(self, *, root: Path) -> None:
        self.repo = root / "clone"
        self.forge_state = root / "forge.json"
        self.bin_dir = root / "bin"
        self.plugins_root = root / "plugins"
        self.body_file = root / "body.md"

    def forge(self) -> dict[str, object]:
        return json.loads(self.forge_state.read_text(encoding="utf-8"))

    def merge_argv(self) -> list[str] | None:
        """The `gh pr merge` argv the stage issued, or `None` if it issued none."""
        for call in self.forge()["calls"]:  # pyright: ignore[reportUnknownVariableType]
            if isinstance(call, list) and call[:2] == ["pr", "merge"]:
                return [str(token) for token in call]
        return None

    def issued(self, *, verb: str) -> bool:
        return any(
            isinstance(call, list) and call[:2] == ["pr", verb]
            for call in self.forge()["calls"]  # pyright: ignore[reportUnknownVariableType]
        )

    def state_dir(self) -> Path:
        return self.repo / ".git" / PUBLICATION_STATE_GIT_PATH


def _sandbox(
    *,
    root: Path,
    pushed: str = _HEAD,
    comments: list[dict[str, str]] | None = None,
    pr_state: str = "OPEN",
    head: str = _HEAD,
    is_draft: bool = True,
    auto_merge: object = None,
    merge_commit: str | None = None,
    advance_head_on: str | None = None,
    advance_head_to: str = _MOVED_HEAD,
    number: int | None = _PR_NUMBER,
) -> _Sandbox:
    """Build a world the `pr` stage can run in, defaulting to the happy path.

    The defaults describe a conforming run -- an open draft whose head this run
    pushed and whose proof chain names that same head -- so each control states
    only the ONE departure it is about.
    """
    box = _Sandbox(root=root)
    box.repo.mkdir(parents=True)
    for argv in (
        ["git", "init", "--quiet", "--initial-branch=master"],
        ["git", "config", "user.email", "test@example.invalid"],
        ["git", "config", "user.name", "Test"],
    ):
        _ = subprocess.run(argv, cwd=box.repo, check=True, capture_output=True)

    box.state_dir().mkdir(parents=True)
    if pushed:
        _ = (box.state_dir() / PUBLISH_HEAD_STATE_FILENAME).write_text(pushed, encoding="utf-8")

    box.bin_dir.mkdir()
    stub = box.bin_dir / "gh"
    _ = stub.write_text(_GH_STUB % {"python": sys.executable}, encoding="utf-8")
    stub.chmod(0o755)

    box.plugins_root.mkdir()
    program = box.plugins_root / PROOF_HEAD_PROGRAM_FILENAME
    _ = program.write_text(proof_head_program_source(), encoding="utf-8")

    _ = box.forge_state.write_text(
        json.dumps(
            {
                "number": number,
                "state": pr_state,
                "head": head,
                "isDraft": is_draft,
                "autoMergeRequest": auto_merge,
                "mergeCommit": merge_commit,
                "comments": _proven(head=_HEAD) if comments is None else comments,
                "advance_head_on": advance_head_on,
                "advance_head_to": advance_head_to,
                "calls": [],
            }
        ),
        encoding="utf-8",
    )
    return box


def _run(
    *,
    box: _Sandbox,
    merge_mode: str = "rebase",
    merge_hold: str = "false",
    title: str | None = "feat: a scripted publication",
    body: str | None = None,
    resume_head: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute the stage's bytes in `box`, with an env holding only what it reads.

    The child environment is EXPLICIT rather than inherited, which the
    subprocess-spawn allowlist requires and which also keeps a control honest:
    an inherited `LIVESPEC_*` from the enclosing factory run could satisfy a
    guard this control meant to exercise.

    `title=None` withholds the key entirely rather than setting it empty, which
    is what a broken overlay projection actually looks like; the stage treats
    both the same and the absent-title control asserts the sentinel.
    """
    env = {
        "PATH": f"{box.bin_dir}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(box.repo.parent / "home"),
        "LIVESPEC_FAKE_FORGE": str(box.forge_state),
        "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
        SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(box.plugins_root),
    }
    if resume_head is not None:
        overlay = render_run_config_overlay(
            committed_text='[workflow]\ngraph = "workflow.fabro"\n[run.environment]\nid = "sandbox"\n',
            workflow_dir=box.repo,
            token="",
            github_token="",
            siblings=None,
            resume_checkout=ResumeCheckout(branch=_BRANCH, head=resume_head),
        )
        assert overlay is not None
        env.update(tomli.loads(overlay)["environments"]["sandbox"]["env"])
    if title is not None:
        env[PR_TITLE_ENV_VAR] = title
    if body is not None:
        _ = box.body_file.write_text(body, encoding="utf-8")
        env[PR_BODY_FILE_ENV_VAR] = str(box.body_file)
    return subprocess.run(
        ["bash", "-c", _pr_script(merge_mode=merge_mode, merge_hold=merge_hold)],
        cwd=box.repo,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_the_unchanged_head_is_readied_and_armed_bound_to_that_head(tmp_path: Path) -> None:
    """The success path arms auto-merge CONDITIONALLY on the proof-verified head.

    Both halves are asserted because either alone passes while the requirement
    is unmet: arming without the binding arms whatever the branch now carries,
    and a binding on some other value would reject every conforming run.
    """
    box = _sandbox(root=tmp_path)

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_READY_AND_ARMED" in result.stderr
    assert f"PR_NUMBER={_PR_NUMBER}" in result.stdout
    argv = box.merge_argv()
    assert argv is not None, "the stage armed nothing"
    assert "--match-head-commit" in argv
    assert argv[argv.index("--match-head-commit") + 1] == _HEAD
    assert box.forge()["autoMergeRequest"] is not None


def test_a_head_moving_between_observation_and_arming_is_refused(tmp_path: Path) -> None:
    """The race the exact-head requirement exists to close, driven end to end.

    The stub advances the branch on `gh pr ready` -- after the head read and
    the proof comparison, before the arming -- so every earlier check passes on
    the head this run proved while the forge then holds a different one. An
    unbound `gh pr merge` cannot tell the difference and would arm the new head
    while reporting the old one as proof-verified.

    THE SENTINEL IS THE UNEXPECTED-HEAD ONE SINCE v145 (work-item
    bd-ib-3hpdvm), which is a sharper refusal rather than a different one: the
    stage now RE-READS the head after a rejected arming, so a moved head is
    reported as the head mismatch it is instead of as the generic arming
    failure that covered every cause at once. The arming is still asserted
    below to have been issued bound to the proved head, and the moved head is
    still unarmed, which is what makes the two readings the same fail-closed.
    """
    box = _sandbox(root=tmp_path, advance_head_on="ready")

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_UNEXPECTED_HEAD" in result.stderr
    argv = box.merge_argv()
    assert argv is not None, "the stage never reached the arming command"
    assert argv[argv.index("--match-head-commit") + 1] == _HEAD
    # Fail-closed means fail-closed: the moved head is NOT armed.
    assert box.forge()["autoMergeRequest"] is None
    assert box.forge()["head"] == _MOVED_HEAD


def test_a_merge_hold_readies_the_pull_request_and_arms_nothing(tmp_path: Path) -> None:
    """A held item publishes a ready pull request and issues no merge at all."""
    box = _sandbox(root=tmp_path)

    result = _run(box=box, merge_hold="true")

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_HELD" in result.stderr
    assert "MERGE_HOLD=held" in result.stdout
    assert box.merge_argv() is None, "a held item must not reach the arming command"
    assert box.issued(verb="ready")


def test_a_hold_standing_over_an_already_armed_pull_request_fails_closed(
    tmp_path: Path,
) -> None:
    """A script must not disarm what something else armed; it stops for a human."""
    box = _sandbox(root=tmp_path, auto_merge={"enabledAt": "earlier"})

    result = _run(box=box, merge_hold="true")

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_HOLD_ARMED" in result.stderr
    assert box.merge_argv() is None


def test_an_already_merged_pull_request_is_idempotent(tmp_path: Path) -> None:
    """Re-running after the merge landed reports the landing and changes nothing.

    This is the resume case: the outcome the stage was publishing for has
    already happened, so succeeding is correct and re-readying would be a
    write against a merged pull request.
    """
    box = _sandbox(root=tmp_path, pr_state="MERGED", merge_commit=_MERGE_SHA)

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_ALREADY_MERGED" in result.stderr
    assert f"MERGE_LANDED={_MERGE_SHA}" in result.stdout
    assert not box.issued(verb="edit")
    assert not box.issued(verb="ready")
    assert box.merge_argv() is None


def test_an_already_ready_pull_request_is_not_readied_twice(tmp_path: Path) -> None:
    """Finalization is idempotent for a pull request already out of draft."""
    box = _sandbox(root=tmp_path, is_draft=False)

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_ALREADY_READY" in result.stderr
    assert not box.issued(verb="ready")
    assert box.merge_argv() is not None


def test_a_closed_unmerged_pull_request_fails_closed(tmp_path: Path) -> None:
    """What a human closed is not reopened by a script."""
    box = _sandbox(root=tmp_path, pr_state="CLOSED")

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_CLOSED_UNMERGED" in result.stderr
    assert not box.issued(verb="edit")


def test_proof_naming_another_tree_is_refused_before_any_write(tmp_path: Path) -> None:
    """A verified record from before a head change cannot publish the new head."""
    box = _sandbox(root=tmp_path, comments=_proven(head=_MOVED_HEAD))

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_PROOF_HEAD_MISMATCH" in result.stderr
    assert not box.issued(verb="edit")
    assert box.merge_argv() is None


def _commit(*, repo: Path, message: str, content: str | None = None) -> str:
    """One real commit in `repo`, changing `tracked.txt` only when `content` is given."""
    if content is not None:
        _ = (repo / "tracked.txt").write_text(content, encoding="utf-8")
        _ = subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True, capture_output=True)
    _ = subprocess.run(
        ["git", "commit", "--quiet", "--allow-empty", "-m", message],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_proof_on_an_unchanged_tree_engine_checkpoint_publishes_the_pushed_head(
    tmp_path: Path,
) -> None:
    """A record naming an unpushed, unchanged-tree checkpoint of the pushed head is that tree's proof.

    The Petri-era engine commits a checkpoint after every node, publish_draft
    included, so the clone's HEAD sits one empty commit above what the run
    pushed. Proof is a property of a TREE, so a record naming that checkpoint
    proves the pull request's head and must not be refused as another tree's.
    """
    box = _sandbox(root=tmp_path, pushed="")
    pushed = _commit(repo=box.repo, message="the work", content="delivered\n")
    checkpoint = _commit(repo=box.repo, message="fabro(run): publish_draft (success)")
    _ = (box.state_dir() / PUBLISH_HEAD_STATE_FILENAME).write_text(pushed, encoding="utf-8")
    forge = box.forge()
    forge["head"] = pushed
    forge["comments"] = _proven(head=checkpoint)
    _ = box.forge_state.write_text(json.dumps(forge), encoding="utf-8")

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_READY_AND_ARMED" in result.stderr
    argv = box.merge_argv()
    assert argv is not None, "the stage armed nothing"
    assert argv[argv.index("--match-head-commit") + 1] == pushed


def test_proof_on_a_descendant_with_a_changed_tree_is_still_refused(tmp_path: Path) -> None:
    """Only an UNCHANGED tree carries the proof across: a real later change does not."""
    box = _sandbox(root=tmp_path, pushed="")
    pushed = _commit(repo=box.repo, message="the work", content="delivered\n")
    changed = _commit(repo=box.repo, message="an unpushed change", content="different\n")
    _ = (box.state_dir() / PUBLISH_HEAD_STATE_FILENAME).write_text(pushed, encoding="utf-8")
    forge = box.forge()
    forge["head"] = pushed
    forge["comments"] = _proven(head=changed)
    _ = box.forge_state.write_text(json.dumps(forge), encoding="utf-8")

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_PROOF_HEAD_MISMATCH" in result.stderr
    assert box.merge_argv() is None


def test_a_newer_unreplayed_verdict_blocks_publication(tmp_path: Path) -> None:
    """The real reader runs here: a later `not_reproduced` supersedes the replay.

    Exercised through the STAGE rather than against the program alone, because
    the requirement is that publication stops -- which depends on the stage
    propagating the program's refusal instead of readying anyway.
    """
    box = _sandbox(
        root=tmp_path,
        comments=[*_proven(head=_HEAD), _record(verdict=VERDICT_NOT_REPRODUCED, head=_HEAD)],
    )

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_PROOF_IDENTITY_UNESTABLISHED" in result.stderr
    assert not box.issued(verb="edit")


def test_a_head_this_run_never_pushed_is_refused(tmp_path: Path) -> None:
    """Recorded provenance, not a tracking ref, decides what this run published."""
    box = _sandbox(root=tmp_path, pushed=_MERGE_SHA)

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_UNEXPECTED_HEAD" in result.stderr
    assert not box.issued(verb="edit")


def test_a_run_with_no_recorded_provenance_refuses_to_publish(tmp_path: Path) -> None:
    """No published head recorded means nothing to compare the proof against."""
    box = _sandbox(root=tmp_path, pushed="")

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_NO_PROVENANCE" in result.stderr
    assert not box.issued(verb="list")


def test_the_title_and_body_ride_as_data_through_the_forge_argv(tmp_path: Path) -> None:
    """Shell metacharacters in a title reach `gh` verbatim, expanding nothing.

    The contract keeps title and body as DATA in `LIVESPEC_PR_TITLE` and
    `LIVESPEC_PR_BODY_FILE` precisely so a rendered title cannot become shell.
    A title carrying a command substitution and a quote is the discriminating
    input: if the stage interpolated it, the recorded argv would differ from
    the bytes handed in.
    """
    hostile = 'feat: $(touch /tmp/livespec-should-not-exist) `date` "quoted" & ;'
    box = _sandbox(root=tmp_path)

    result = _run(box=box, title=hostile, body="A body\nwith lines.\n")

    assert result.returncode == 0, result.stderr
    edits = [
        call
        for call in box.forge()["calls"]  # pyright: ignore[reportUnknownVariableType]
        if isinstance(call, list) and call[:2] == ["pr", "edit"]
    ]
    assert len(edits) == 1
    argv = [str(token) for token in edits[0]]
    assert argv[argv.index("--title") + 1] == hostile
    assert argv[argv.index("--body-file") + 1] == str(box.body_file)
    assert not Path("/tmp/livespec-should-not-exist").exists()


def test_the_body_is_read_from_the_path_the_dispatcher_materializes(tmp_path: Path) -> None:
    """With no override, the stage reads the file the prepare chain wrote.

    The two ends have to agree or the body is silently lost, and the agreement
    cannot be an env value: the sandbox plugins root is not known host-side, so
    both ends resolve it by shell expansion. The control writes the body at that
    expansion's own location and withholds `LIVESPEC_PR_BODY_FILE` entirely, so
    a stage resolving any other default would report an absent body and edit the
    title alone.
    """
    box = _sandbox(root=tmp_path)
    materialized = "A body the prepare step wrote, at the path both ends resolve.\n"
    _ = (box.plugins_root / PUBLICATION_BODY_FILENAME).write_text(materialized, encoding="utf-8")

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_BODY_ABSENT" not in result.stderr
    edits = [
        [str(token) for token in call]
        for call in box.forge()["calls"]  # pyright: ignore[reportUnknownVariableType]
        if isinstance(call, list) and call[:2] == ["pr", "edit"]
    ]
    assert len(edits) == 1
    applied = Path(edits[0][edits[0].index("--body-file") + 1])
    assert applied.read_text(encoding="utf-8") == materialized


def test_an_absent_title_and_body_each_announce_themselves_and_still_publish(
    tmp_path: Path,
) -> None:
    """The regression this slice repairs, asserted in both of its halves.

    When publication became a command stage the Dispatcher-rendered shaping was
    dropped, and the fallbacks were SILENT: the pull request took the publish
    branch name as its title and kept `publish_draft`'s placeholder body, at
    exit 0, with nothing on the run record saying so. The fallbacks are retained
    deliberately -- a title and a body decide nothing about the tree, and
    failing closed over a cosmetic value would strand reviewed, proof-verified
    work -- so the assertion is that each absence is NAMED.

    Both halves in one case, because the stage takes one `gh pr edit` and the
    claim is about that single argv: a case asserting only the title sentinel
    would pass for a build that had lost the body channel entirely, and the
    argv is where "published anyway, with the fallback" is observable.
    """
    box = _sandbox(root=tmp_path)

    result = _run(box=box, title=None)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_TITLE_ABSENT" in result.stderr
    assert "LIVESPEC_PR_BODY_ABSENT" in result.stderr
    assert "LIVESPEC_PR_READY_AND_ARMED" in result.stderr
    edits = [
        [str(token) for token in call]
        for call in box.forge()["calls"]  # pyright: ignore[reportUnknownVariableType]
        if isinstance(call, list) and call[:2] == ["pr", "edit"]
    ]
    assert len(edits) == 1
    assert edits[0][edits[0].index("--title") + 1] == _BRANCH
    assert "--body-file" not in edits[0], "a placeholder body must not be applied as data"


def test_the_execution_boundary_leaves_enclosing_run_state_intact(tmp_path: Path) -> None:
    """Executing the stage here cannot touch the publication state of a real run.

    THE REGRESSION CONTROL FOR THIS FILE'S OWN SAFETY. `pr_refresh` runs
    `sandbox_check_suite` -- this suite -- as its post-rebase gate, inside the
    sandbox, AFTER establishing provenance and incrementing its refresh
    counter. A control that wrote publication state at a fixed shared path
    would erase that live counter mid-gate and let the next refresh restart at
    one, evading the three-refresh bound; it would also drop the published-head
    marker on a gate failure. Anchoring state to each control's own `$GIT_DIR`
    makes that impossible by construction, and this control is what proves the
    construction holds.

    An ENCLOSING run is simulated with its own repository carrying all three
    state files with sentinel contents, and a control is then run to completion
    in a different repository. The sentinel bytes must survive byte-for-byte --
    including the failing arm, since a gate failure is exactly when the
    original finding lost state.

    THE SHARED-PATH LEG IS A BEFORE/AFTER COMPARISON, NOT AN ABSENCE CHECK, and
    the difference decides whether this control measures anything. Asserting
    those paths are ABSENT grades the ambient machine: a leftover from any
    earlier build fails the control while saying nothing about the boundary,
    and a clean machine passes it just as uninformatively. Measured on this
    sandbox -- a stale `/tmp/livespec-publish-head` from a pre-`$GIT_DIR` build
    was present and failed the absence form, while no code in the tree writes
    that path. Comparing each path's state before and against after is what
    actually asks whether EXECUTING THE STAGE touched it.
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
    # One succeeding arm and one FAILING arm, because the finding this guards
    # against destroyed state on the failure path.
    passing_box = _sandbox(root=tmp_path / "passing")
    failing_box = _sandbox(root=tmp_path / "failing", pr_state="CLOSED")
    passing = _run(box=passing_box)
    failing = _run(box=failing_box)

    assert passing.returncode == 0, passing.stderr
    assert failing.returncode == 1, failing.stdout
    for name, text in sentinels.items():
        path = enclosing / name
        assert path.is_file(), f"{name} was removed by an execution control"
        assert path.read_text(encoding="utf-8") == text, name
    assert shared_state() == before, "an execution control touched a fixed shared path"
    # The POSITIVE half: each control's own provenance resolved inside its own
    # `$GIT_DIR`, which is the mechanism that makes the two legs above hold.
    for box in (passing_box, failing_box):
        own = box.state_dir() / PUBLISH_HEAD_STATE_FILENAME
        assert own.is_file(), "the control's own state did not resolve in its own repository"
        assert own.read_text(encoding="utf-8") == _HEAD


def test_a_resumed_pr_uses_the_overlay_head_without_a_publication_file(*, tmp_path: Path) -> None:
    """Final publication consumes the same Dispatcher provenance as pr_refresh."""
    box = _sandbox(root=tmp_path, pushed="")
    assert not (box.state_dir() / PUBLISH_HEAD_STATE_FILENAME).exists()

    result = _run(box=box, resume_head=_HEAD)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_NO_PROVENANCE" not in result.stderr
    assert "LIVESPEC_PR_READY_AND_ARMED" in result.stderr
    argv = box.merge_argv()
    assert argv is not None
    assert argv[argv.index("--match-head-commit") + 1] == _HEAD

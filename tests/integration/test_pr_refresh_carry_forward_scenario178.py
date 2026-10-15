"""Scenario 178 — a refresh carries a verified proof forward, or re-proves.

`SPECIFICATION/scenarios.md` Scenario 178 and `SPECIFICATION/contracts.md`
section "Definition-of-Done and Proof-of-Done stages" -> "Proof carry-forward
across a refresh", "The observation scope" and "The decision" (v138) put a
DETERMINISTIC classifier between a changed-head `pr_refresh` and the rest of the
run: when the incoming commits cannot have affected what the verified proof
observed, the run goes straight to `pr`, and otherwise it re-proves.

WHY THESE CASES RUN AGAINST REAL GIT AND A REAL SUBPROCESS. Every decision input
is a git reading -- a merge base, two `diff --name-only` lists, two `patch-id
--stable` values, a blob id per observed path, a `hash-object --no-filters` of a
working-tree file -- and the mechanical replay EXECUTES the step's own command.
A test that stubbed any of that out would exercise the ladder and leave the
readings, which are the half a reader cannot check by eye, unexercised. So each
case builds an actual repository, actually rebases it, and runs the materialized
program the way `pr_refresh_head` runs it, with a stubbed `gh` on PATH because
the forge is the one input that is not local.

THE DECISION IS READ OFF THE EXIT CODE, because that is all the engine gives a
command node: zero routes to `pr`, non-zero routes to `proof_capture`. The
POSTED RECORD is read off the stub's capture directory, because the record is
what survives the run and the stage output does not -- so a case asserting only
the exit code would certify a route while leaving the decision
unreconstructable.

WHY EVERY REFUSAL CASE IS THE CARRY-FORWARD FIXTURE WITH ONE INPUT MOVED. The
decision is a conjunction of seven conditions, so a refusal is only attributable
to the input it names when every other input is known to have been satisfiable.
Each case below therefore starts from `inert_refresh` -- which carries forward --
and changes exactly one thing. A bespoke fixture per refusal would pass while
refusing for an unrelated reason.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_carry_forward_program import (
    CARRY_FORWARD_PROGRAM_FILENAME,
    carry_forward_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    PUBLISH_HEAD_LABEL,
)

_DEFAULT_BRANCH = "master"
_OBSERVED = "AGENTS.md"
_SEED_BODY = "a ledger comment is binding scope\nsecond line\n"
# The observed file as the ITEM leaves it, which is what every replay runs
# against and what every captured proof below is derived from.
_ITEM_BODY = _SEED_BODY + "the item added this line\n"
# A second path the ITEM touches and no step reads, so the item-paths condition
# can be moved without also moving the observation scope. It is multi-line and
# the two sides change OPPOSITE ends of it, because a default-branch commit that
# conflicted with the item would take the refresh-repair route and never reach
# this decision at all.
_ITEM_ONLY = "plan/item-touched.md"
_ITEM_ONLY_SEED = "one\ntwo\nthree\nfour\nfive\n"
_ITEM_ONLY_AFTER_ITEM = _ITEM_ONLY_SEED.replace("five", "five changed by the item")
_ITEM_ONLY_AFTER_DEFAULT = _ITEM_ONLY_SEED.replace("one", "one changed on the default branch")
# An inert-classed path the SEED already carries, so a reproduction step may read
# it at the verified head. A path the incoming commits CREATE cannot be in the
# observation scope: its operand does not reach a file at the verified head, and
# the decision rejects the operand rather than reporting an overlap.
_SCOPED_INERT = "plan/topic/note.md"
_RECORD_URL = "https://forge.invalid/pull/7#issuecomment-99"
_IDENTITY_LINE = re.compile(r"^(?:Verified|New) patch identity: (\S+)$", re.MULTILINE)


def _git(*argv: str, cwd: Path) -> str:
    """One git command in one repository, with its stdout."""
    result = subprocess.run(
        ["git", *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _commit(*, cwd: Path, message: str) -> str:
    _git("add", "-A", cwd=cwd)
    _git("-c", "core.hooksPath=/dev/null", "commit", "-q", "--no-verify", "-m", message, cwd=cwd)
    return _git("rev-parse", "HEAD", cwd=cwd)


def _write(*, cwd: Path, path: str, text: str) -> None:
    target = cwd / path
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(text, encoding="utf-8")


def _seed(*, tmp_path: Path) -> Path:
    """A repository with a default branch, a spec root and the observed file.

    The spec root is `SPEC` rather than this repository's own `SPECIFICATION`,
    so the two inert classes derived from `.livespec.jsonc` can only be right by
    having been READ: a decision that hardcoded the fleet's spelling would pass
    every case here by accident and fail on an adopter.
    """
    repo = tmp_path / "clone"
    repo.mkdir()
    _git("init", "-q", "-b", _DEFAULT_BRANCH, cwd=repo)
    _git("config", "user.email", "factory@example.invalid", cwd=repo)
    _git("config", "user.name", "Factory", cwd=repo)
    _git("config", "commit.gpgsign", "false", cwd=repo)
    _write(cwd=repo, path=".livespec.jsonc", text='{\n  // a comment\n  "spec_root": "SPEC"\n}\n')
    _write(cwd=repo, path=_OBSERVED, text=_SEED_BODY)
    _write(cwd=repo, path=_SCOPED_INERT, text="a plan note\n")
    _write(cwd=repo, path=_ITEM_ONLY, text=_ITEM_ONLY_SEED)
    _write(cwd=repo, path="SPEC/history/v1/spec.md", text="old\n")
    _write(cwd=repo, path="SPEC/templates/one/history/v1/spec.md", text="old\n")
    _ = _commit(cwd=repo, message="seed")
    return repo


def _advance_default(*, repo: Path, paths: dict[str, str]) -> str:
    """Advance the default branch with one commit touching exactly `paths`."""
    head = _git("rev-parse", "HEAD", cwd=repo)
    _git("checkout", "-q", _DEFAULT_BRANCH, cwd=repo)
    for path, text in paths.items():
        _write(cwd=repo, path=path, text=text)
    new_base = _commit(cwd=repo, message="advance the default branch")
    _git("checkout", "-q", head, cwd=repo)
    return new_base


def _record_body(
    *,
    head: str,
    steps: Sequence[str],
    proofs: Sequence[Sequence[str]],
    reads: dict[str, str],
    working_directory: str | None = ".",
    verdict: str = "verified",
    raw_steps: Sequence[str] | None = None,
    extra_prose: Sequence[str] = (),
) -> str:
    """One `verified` record carrying the prose the decision reads.

    `raw_steps` replaces the rendered step lines with literal ones, which is how
    a step carrying two code spans or none is expressed: both are properties of
    the LINE the capture wrote, and neither is reachable through a command
    argument.
    """
    lines = [f"Proof of Done — {verdict} — run run-1 — 2026-10-15T00:00:00Z", ""]
    lines.append(f"{PUBLISH_HEAD_LABEL}: {head}")
    if working_directory is not None:
        lines.append(f"Working directory: {working_directory}")
    for path, identity in reads.items():
        lines.append(f"Read: {path} {identity}")
    lines.extend(extra_prose)
    lines.extend(["", "## Assertion 1 — the observed file says what it says.", ""])
    rendered = (
        list(raw_steps)
        if raw_steps is not None
        else [f"{index + 1}. Run `{step}`." for index, step in enumerate(steps)]
    )
    for index, line in enumerate(rendered):
        lines.extend([line, ""])
        for proof in proofs[index] if index < len(proofs) else ():
            lines.extend(["```", proof, "```", ""])
    return "\n".join(lines) + "\n"


def _worktree_identity(*, repo: Path, path: str) -> str:
    return _git("hash-object", "--no-filters", path, cwd=repo)


def _patch_identities(record: str) -> list[str]:
    """The verified and new patch identities the decision record names, in order."""
    return _IDENTITY_LINE.findall(record)


def _run_decision(
    *,
    repo: Path,
    tmp_path: Path,
    comments: list[dict[str, str]],
    previous_head: str,
    previous_base: str,
    new_base: str,
    new_head: str,
    post_fails: bool = False,
) -> tuple[int, str, str, list[str]]:
    """Run the program as `pr_refresh_head` runs it, and return the posted records."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    program = tmp_path / CARRY_FORWARD_PROGRAM_FILENAME
    _ = program.write_text(carry_forward_program_source(), encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    comments_file = tmp_path / "comments.json"
    _ = comments_file.write_text(json.dumps({"comments": comments}), encoding="utf-8")
    posted_dir = tmp_path / "posted"
    posted_dir.mkdir(exist_ok=True)
    stub = bin_dir / "gh"
    _ = stub.write_text(
        "#!/usr/bin/env python3\n"
        "import os, pathlib, sys\n"
        "argv = sys.argv[1:]\n"
        "if argv[:2] == ['pr', 'view']:\n"
        "    sys.stdout.write(pathlib.Path(os.environ['GH_COMMENTS']).read_text())\n"
        "    raise SystemExit(0)\n"
        "if argv[:2] == ['pr', 'comment']:\n"
        "    if os.environ.get('GH_POST_FAILS'):\n"
        "        sys.stderr.write('forge refused the comment')\n"
        "        raise SystemExit(1)\n"
        "    body = argv[argv.index('--body-file') + 1]\n"
        "    out = pathlib.Path(os.environ['GH_POSTED'])\n"
        "    target = out / (str(len(list(out.iterdir()))) + '.md')\n"
        "    target.write_text(pathlib.Path(body).read_text())\n"
        "    sys.stdout.write('https://forge.invalid/pull/7#issuecomment-1\\n')\n"
        "    raise SystemExit(0)\n"
        "sys.stderr.write('unexpected gh invocation: ' + repr(argv))\n"
        "raise SystemExit(2)\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    env = {
        "PATH": f"{bin_dir}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "GH_COMMENTS": str(comments_file),
        "GH_POSTED": str(posted_dir),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    if post_fails:
        env["GH_POST_FAILS"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            str(program),
            "--pull-request",
            "7",
            "--default-branch",
            _DEFAULT_BRANCH,
            "--previous-head",
            previous_head,
            "--previous-base",
            previous_base,
            "--new-base",
            new_base,
            "--new-head",
            new_head,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    posted = [path.read_text(encoding="utf-8") for path in sorted(posted_dir.iterdir())]
    return result.returncode, result.stdout, result.stderr, posted


@pytest.fixture
def inert_refresh(tmp_path: Path) -> dict[str, object]:
    """The carry-forward case: an item diff, and incoming commits beneath `plan/`.

    The item touches TWO paths, one of which no step reads, so the item-paths
    condition and the observation-scope condition can be moved independently.
    """
    repo = _seed(tmp_path=tmp_path)
    previous_base = _git("rev-parse", "HEAD", cwd=repo)
    _git("checkout", "-q", "-b", "feat/item", cwd=repo)
    _write(cwd=repo, path=_OBSERVED, text=_ITEM_BODY)
    _write(cwd=repo, path=_ITEM_ONLY, text=_ITEM_ONLY_AFTER_ITEM)
    verified_head = _commit(cwd=repo, message="the item's own change")
    new_base = _advance_default(repo=repo, paths={"plan/topic/other.md": "a plan note\n"})
    _git("checkout", "-q", "feat/item", cwd=repo)
    _git("rebase", "-q", new_base, cwd=repo)
    return {
        "repo": repo,
        "previous_base": previous_base,
        "previous_head": verified_head,
        "verified_head": verified_head,
        "new_base": new_base,
        "new_head": _git("rev-parse", "HEAD", cwd=repo),
        "step": f'grep -n "ledger comment" {_OBSERVED}',
        "proof": f"1:{_SEED_BODY.splitlines()[0]}",
        "reads": {_OBSERVED: _worktree_identity(repo=repo, path=_OBSERVED)},
    }


def _rebase_onto(*, fixture: dict[str, object], paths: dict[str, str]) -> dict[str, object]:
    """Advance the default branch with `paths` and rebase the item onto it.

    Returns a fixture whose previous base and head are the ORIGINAL ones, which
    is the state a `pr_refresh` reaches when the branch it published is refreshed
    once: the previous published head is what the run pushed before, and the
    incoming range spans everything the default branch has gained since.
    """
    repo = fixture["repo"]
    assert isinstance(repo, Path)
    new_base = _advance_default(repo=repo, paths=paths)
    _git("rebase", "-q", new_base, cwd=repo)
    moved = dict(fixture)
    moved["new_base"] = new_base
    moved["new_head"] = _git("rev-parse", "HEAD", cwd=repo)
    return moved


def _body_for(*, fixture: dict[str, object]) -> str:
    """The record body the carry-forward fixture's own proof renders to."""
    reads = fixture["reads"]
    assert isinstance(reads, dict)
    return _record_body(
        head=str(fixture["verified_head"]),
        steps=[str(fixture["step"])],
        proofs=[[str(fixture["proof"])]],
        reads=reads,
    )


def _call(
    *, fixture: dict[str, object], tmp_path: Path, **overrides: object
) -> tuple[int, str, str, list[str]]:
    """Run the decision for one fixture, with the record assembled from it."""
    repo = fixture["repo"]
    assert isinstance(repo, Path)
    steps = overrides.get("steps", [fixture["step"]])
    assert isinstance(steps, list)
    proofs = overrides.get("proofs", [[fixture["proof"]]])
    assert isinstance(proofs, list)
    reads = overrides.get("reads", fixture["reads"])
    assert isinstance(reads, dict)
    head = overrides.get("record_head", fixture["verified_head"])
    assert isinstance(head, str)
    raw_steps = overrides.get("raw_steps")
    extra = overrides.get("extra_prose", ())
    assert isinstance(extra, list | tuple)
    working = overrides.get("working_directory", ".")
    comments = overrides.get(
        "comments",
        [
            {
                "body": _record_body(
                    head=head,
                    steps=steps,
                    proofs=proofs,
                    reads=reads,
                    working_directory=None if working is None else str(working),
                    raw_steps=None if raw_steps is None else list(raw_steps),  # pyright: ignore[reportArgumentType]
                    extra_prose=list(extra),
                ),
                "url": _RECORD_URL,
            }
        ],
    )
    assert isinstance(comments, list)
    return _run_decision(
        repo=repo,
        tmp_path=tmp_path / "run",
        comments=comments,
        previous_head=str(fixture["previous_head"]),
        previous_base=str(fixture["previous_base"]),
        new_base=str(fixture["new_base"]),
        new_head=str(fixture["new_head"]),
        post_fails=bool(overrides.get("post_fails", False)),
    )


def test_a_refresh_that_brings_in_only_plan_notes_carries_a_file_read_proof_forward(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """Scenario 178's first case, end to end against real git.

    Exit zero is the whole assertion for routing: it is the edge
    `pr_refresh_head` takes to `pr`, so a decision that re-proved a refresh it
    could have carried would send the run round capture, review and replay for
    commits it cannot observe — which is the loop that killed seven runs on
    2026-10-14.

    The record is asserted FIELD BY FIELD because the clause enumerates what it
    must name, and a record that merely says `carried_forward` would satisfy
    every routing assertion while leaving the decision unreconstructable.
    """
    code, _, err, posted = _call(fixture=inert_refresh, tmp_path=tmp_path)

    assert code == 0, err
    assert len(posted) == 1
    record = posted[0]
    assert "— carried_forward —" in record
    assert "Decision: carried_forward" in record
    assert f"Verified record: {_RECORD_URL}" in record
    assert f"Verified head: {inert_refresh['verified_head']}" in record
    assert f"Previous published head: {inert_refresh['previous_head']}" in record
    assert f"New head: {inert_refresh['new_head']}" in record
    assert (
        f"Incoming range: {inert_refresh['previous_base']}..{inert_refresh['new_base']}" in record
    )
    assert "Incoming paths: plan/topic/other.md" in record
    assert f"Observation scope: {_OBSERVED}" in record
    identity = _patch_identities(record)
    assert len(identity) == 2
    assert identity[0] == identity[1]


def test_a_git_show_of_an_unchanged_file_carries_forward(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """The one production that reads the OBJECT STORE owes no read identity.

    `git show HEAD:<path>` is the only admitted command that does not read the
    working tree, so requiring a `Read:` line for it would make the production
    unusable while reporting a missing read identity — a refusal naming an input
    the record was never obliged to carry.
    """
    code, _, err, posted = _call(
        fixture=inert_refresh,
        tmp_path=tmp_path,
        steps=[f"git show HEAD:{_OBSERVED}"],
        proofs=[[_ITEM_BODY.rstrip("\n")]],
        reads={},
    )

    assert code == 0, err
    assert "— carried_forward —" in posted[0]
    assert f"Observation scope: {_OBSERVED}" in posted[0]


@pytest.mark.parametrize(
    ("step", "proof"),
    [
        (f"cat {_OBSERVED}", _ITEM_BODY.rstrip("\n")),
        (f"head -n 1 {_OBSERVED}", _ITEM_BODY.splitlines()[0]),
        (f"tail -n 1 {_OBSERVED}", _ITEM_BODY.splitlines()[-1]),
        (f"wc -l {_OBSERVED}", f"3 {_OBSERVED}"),
        (f"grep -c ledger {_OBSERVED}", "1"),
        (f"sed -n '1p' {_OBSERVED}", _ITEM_BODY.splitlines()[0]),
        (f"diff -u {_OBSERVED} {_OBSERVED}", ""),
    ],
)
def test_every_admitted_production_can_carry_a_proof_forward(
    inert_refresh: dict[str, object], tmp_path: Path, step: str, proof: str
) -> None:
    """The seven productions, each on the carry-forward path.

    A grammar tested only on refusals would pass while admitting nothing at
    all, so each production gets a case that must reach `pr`. `diff` of a file
    against itself prints nothing, which is also the control that an EMPTY
    captured proof is a real proof rather than a missing one.
    """
    reads = dict(inert_refresh["reads"]) if isinstance(inert_refresh["reads"], dict) else {}

    code, _, err, posted = _call(
        fixture=inert_refresh, tmp_path=tmp_path, steps=[step], proofs=[[proof]], reads=reads
    )

    assert code == 0, err
    assert "— carried_forward —" in posted[0]


def test_a_second_carry_forward_is_measured_against_the_verified_diff(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """A chain of carry-forwards still compares the diff that was VERIFIED.

    The previous PUBLISHED head moves to N1 while the VERIFIED head stays at V,
    so a decision that compared N2 against N1 would be measuring a diff nothing
    ever replayed. The record naming V while the previous published head is N1
    is what makes the distinction observable.
    """
    repo = inert_refresh["repo"]
    assert isinstance(repo, Path)
    first_head = inert_refresh["new_head"]
    new_base = _advance_default(repo=repo, paths={"plan/topic/second.md": "a second note\n"})
    _git("rebase", "-q", new_base, cwd=repo)
    second = dict(inert_refresh)
    second["previous_head"] = first_head
    second["previous_base"] = inert_refresh["new_base"]
    second["new_base"] = new_base
    second["new_head"] = _git("rev-parse", "HEAD", cwd=repo)

    code, _, err, posted = _call(fixture=second, tmp_path=tmp_path)

    assert code == 0, err
    assert f"Verified head: {inert_refresh['verified_head']}" in posted[0]
    assert f"Previous published head: {first_head}" in posted[0]
    assert f"New head: {second['new_head']}" in posted[0]


def test_an_incoming_change_outside_the_inert_classes_reproves(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """The conjunction's first condition, measured by changing only that input."""
    moved = _rebase_onto(fixture=inert_refresh, paths={"module.py": "value = 1\n"})

    code, _, _, posted = _call(fixture=moved, tmp_path=tmp_path)

    assert code == 1
    assert "— reproof_required —" in posted[0]
    assert "incoming-path-outside-inert-classes: module.py" in posted[0]


@pytest.mark.parametrize(
    "inert",
    ["plan/topic/note2.md", "SPEC/history/v2/spec.md", "SPEC/templates/one/history/v2/spec.md"],
)
def test_each_inert_class_is_inert(
    inert_refresh: dict[str, object], tmp_path: Path, inert: str
) -> None:
    """All three inert classes, including the per-template history the head declares.

    The template histories are enumerated AT THE HEAD BEING EXAMINED, so this is
    the positive control for that enumeration: a fixed two-class list passes the
    first two cases and re-proves the third.
    """
    moved = _rebase_onto(fixture=inert_refresh, paths={inert: "another note\n"})

    code, _, err, posted = _call(fixture=moved, tmp_path=tmp_path)

    assert code == 0, err
    assert "— carried_forward —" in posted[0]


def test_an_incoming_change_inside_the_observation_scope_reproves(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """An inert-classed path the proof READ is still a re-proof.

    `plan/topic/note.md` is beneath the plan store, so the inert test passes it;
    it is in the observation scope, so the scope test must refuse it. A decision
    checking only the classes would carry a proof forward across a change to a
    file it had read.
    """
    scoped = _SCOPED_INERT
    repo = inert_refresh["repo"]
    assert isinstance(repo, Path)
    moved = _rebase_onto(fixture=inert_refresh, paths={scoped: "the note changed\n"})
    reads = {scoped: _worktree_identity(repo=repo, path=scoped)}

    code, _, _, posted = _call(
        fixture=moved,
        tmp_path=tmp_path,
        steps=[f"cat {scoped}"],
        proofs=[["the note changed"]],
        reads=reads,
    )

    assert code == 1
    assert f"incoming-path-in-observation-scope: {scoped}" in posted[0]


def test_a_non_canonical_path_operand_is_canonicalized_before_it_is_compared(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """`./plan//topic/note.md` and `plan/topic/note.md` are ONE path.

    Without canonicalization the scope would hold a string no incoming path list
    ever spells, so the overlap test would find none and the refresh would carry
    forward across a change to the very file the proof read.
    """
    repo = inert_refresh["repo"]
    assert isinstance(repo, Path)
    moved = _rebase_onto(fixture=inert_refresh, paths={_SCOPED_INERT: "the note changed\n"})
    reads = {_SCOPED_INERT: _worktree_identity(repo=repo, path=_SCOPED_INERT)}

    code, _, _, posted = _call(
        fixture=moved,
        tmp_path=tmp_path,
        steps=[f"cat ./{_SCOPED_INERT.replace('/', '//', 1)}"],
        proofs=[["the note changed"]],
        reads=reads,
    )

    assert code == 1
    assert f"incoming-path-in-observation-scope: {_SCOPED_INERT}" in posted[0]


def test_an_incoming_change_to_an_item_path_reproves(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """A path the ITEM touches re-proves even when nothing read it.

    The item diff is what the patch identity is taken over, so a default-branch
    commit touching one of its paths changes what the item's own change means
    even where no reproduction step looked at the file.
    """
    moved = _rebase_onto(fixture=inert_refresh, paths={_ITEM_ONLY: _ITEM_ONLY_AFTER_DEFAULT})

    code, _, _, posted = _call(
        fixture=moved,
        tmp_path=tmp_path,
        steps=[f"wc -l {_OBSERVED}"],
        proofs=[[f"3 {_OBSERVED}"]],
        reads=dict(inert_refresh["reads"]) if isinstance(inert_refresh["reads"], dict) else {},
    )

    assert code == 1
    assert f"incoming-path-in-item-paths: {_ITEM_ONLY}" in posted[0]


@pytest.mark.parametrize(
    "step",
    [
        "list-plans --json",
        'grep -rn "Scenario 178" SPEC/',
        "cat plan/*/research/001.md",
        'grep -n "$(cat plan/topic/pattern.txt)" AGENTS.md',
        "cat",
        "grep -F '-fplan/topic/pattern.txt' AGENTS.md",
        "cat -",
        "sed -n '1,$p' AGENTS.md",
        "wc -z AGENTS.md",
        "diff -u AGENTS.md README.md AGENTS.md",
        "head -n many AGENTS.md",
        "grep -A many ledger AGENTS.md",
        "git log --oneline",
        "cat AGENTS.md | wc -l",
    ],
)
def test_a_step_outside_the_direct_read_grammar_reproves(
    inert_refresh: dict[str, object], tmp_path: Path, step: str
) -> None:
    """Every refusal shape Scenario 178 enumerates, and the grammar's own edges.

    Each of these reads an unbounded or unenumerable set of paths — an
    operation, a recursive read, a glob, a hidden substitution, a missing
    operand, an option-shaped pattern, a dash operand, a `$` inside a
    single-quoted sed script — so nothing can be said about whether the incoming
    commits touched one of them. The record names the STEP rather than a path,
    because there is no path to name.
    """
    code, _, _, posted = _call(
        fixture=inert_refresh, tmp_path=tmp_path, steps=[step], proofs=[["ignored"]], reads={}
    )

    assert code == 1
    assert "step-outside-direct-read-grammar: step 1" in posted[0]


def test_a_step_carrying_two_commands_reproves(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """Each step must carry EXACTLY one command, so two is outside the grammar."""
    code, _, _, posted = _call(
        fixture=inert_refresh,
        tmp_path=tmp_path,
        steps=["first"],
        proofs=[["ignored"]],
        reads={},
        raw_steps=[f"1. Run `cat {_OBSERVED}` and then `wc -l {_OBSERVED}`."],
    )

    assert code == 1
    assert "carries more than one command" in posted[0]


def test_a_step_carrying_no_command_reproves(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """A step with no code span names no command for the replay to execute."""
    code, _, _, posted = _call(
        fixture=inert_refresh,
        tmp_path=tmp_path,
        steps=["first"],
        proofs=[["ignored"]],
        reads={},
        raw_steps=["1. Look at the file and satisfy yourself that it is right."],
    )

    assert code == 1
    assert "carries no command" in posted[0]


def test_a_verified_record_with_no_numbered_step_reproves(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """An empty observation scope is not establishable from no steps at all.

    This is the arm that keeps "not establishable" apart from "empty": a scope
    read as empty would be compared against the incoming paths, find no overlap,
    and carry a proof forward that recorded nothing anyone could re-run.
    """
    code, _, _, posted = _call(
        fixture=inert_refresh, tmp_path=tmp_path, steps=[], proofs=[], reads={}, raw_steps=[]
    )

    assert code == 1
    assert "carries no numbered reproduction step" in posted[0]


@pytest.mark.parametrize("operand", ["/etc/passwd", "docs/../AGENTS.md"])
def test_a_rejected_path_operand_reproves_naming_the_operand(
    inert_refresh: dict[str, object], tmp_path: Path, operand: str
) -> None:
    """An absolute operand and a parent segment are REJECTED, not unrecognised.

    Both answers route to `proof_capture`, so the distinction buys the RECORD:
    reporting `cat docs/../AGENTS.md` as an unrecognised command would point its
    reader at the command's shape and away from the `..` segment, which is the
    whole finding.
    """
    code, _, _, posted = _call(
        fixture=inert_refresh,
        tmp_path=tmp_path,
        steps=[f"cat {operand}"],
        proofs=[["ignored"]],
        reads={},
    )

    assert code == 1
    assert "rejected-path-operand: step 1" in posted[0]


def test_a_path_read_through_a_symbolic_link_is_rejected(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """A symlinked parent makes the read reach somewhere the path does not name.

    `git ls-tree` answers NOTHING for a path under a symlink, so a check that
    only asked about the final component would read the aliasing as a missing
    file — a different finding with a different remedy.
    """
    repo = inert_refresh["repo"]
    assert isinstance(repo, Path)
    _write(cwd=repo, path="plan/sub/note.md", text="aliased\n")
    (repo / "alias").symlink_to("plan/sub")
    moved = dict(inert_refresh)
    moved["new_head"] = _commit(cwd=repo, message="add an aliased read target")

    code, _, _, posted = _call(
        fixture=moved,
        tmp_path=tmp_path,
        steps=["cat alias/note.md"],
        proofs=[["aliased"]],
        reads={"alias/note.md": "0" * 40},
    )

    assert code == 1
    assert "rejected-path-operand: step 1" in posted[0]


def test_a_record_declaring_another_working_directory_reproves(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """The replay re-runs every step from the root, so only the root form carries."""
    code, _, _, posted = _call(
        fixture=inert_refresh, tmp_path=tmp_path, working_directory="orchestrator-image"
    )

    assert code == 1
    assert "'orchestrator-image'" in posted[0]
    assert "rather than the repository root" in posted[0]


def test_a_record_declaring_no_working_directory_reproves(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """No line at all gets the same ROUTE and a different RECORD.

    The clause gives "no line" and "some other directory" one answer; only the
    second can name the directory the record stated, so a reader that collapsed
    them could not write this finding.
    """
    code, _, _, posted = _call(fixture=inert_refresh, tmp_path=tmp_path, working_directory=None)

    assert code == 1
    assert "declares the working directory nothing" in posted[0]


def test_a_rebased_diff_whose_patch_identity_differs_reproves(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """Both patch identities are named, because the finding IS their difference."""
    repo = inert_refresh["repo"]
    assert isinstance(repo, Path)
    _write(cwd=repo, path="plan/extra.md", text="the item grew a file\n")
    moved = dict(inert_refresh)
    moved["new_head"] = _commit(cwd=repo, message="the item diff changed after the refresh")

    code, _, _, posted = _call(fixture=moved, tmp_path=tmp_path)

    assert code == 1
    assert "patch-identity-differs: the verified diff is" in posted[0]
    identity = _patch_identities(posted[0])
    assert len(identity) == 2
    assert identity[0] != identity[1]


def test_a_changed_blob_on_an_observed_path_reproves(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """A whitespace-only change keeps the patch identity and moves the blob.

    `patch-id --stable` ignores whitespace, so this is the case that proves the
    blob check is not redundant with the patch check: the two identities agree
    and the observed file's bytes do not.
    """
    repo = inert_refresh["repo"]
    assert isinstance(repo, Path)
    _write(cwd=repo, path=_OBSERVED, text=_ITEM_BODY.replace("this line", "this line "))
    moved = dict(inert_refresh)
    moved["new_head"] = _commit(cwd=repo, message="whitespace on the observed path")

    code, _, _, posted = _call(fixture=moved, tmp_path=tmp_path)

    assert code == 1
    identity = _patch_identities(posted[0])
    assert identity[0] == identity[1]
    assert f"blob-identity-differs: {_OBSERVED}" in posted[0]


def test_a_missing_read_identity_reproves_naming_the_path(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """Without a recorded read identity there is nothing to compare bytes against."""
    code, _, _, posted = _call(fixture=inert_refresh, tmp_path=tmp_path, reads={})

    assert code == 1
    assert f"read-identity-missing: {_OBSERVED}" in posted[0]


def test_a_read_identity_declared_twice_with_different_values_is_missing(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """A record that cannot say which bytes it read of one file recorded no read."""
    repo = inert_refresh["repo"]
    assert isinstance(repo, Path)
    genuine = _worktree_identity(repo=repo, path=_OBSERVED)

    code, _, _, posted = _call(
        fixture=inert_refresh,
        tmp_path=tmp_path,
        reads={},
        extra_prose=[f"Read: {_OBSERVED} {genuine}", f"Read: {_OBSERVED} {'1' * 40}"],
    )

    assert code == 1
    assert f"read-identity-missing: {_OBSERVED}" in posted[0]


def test_a_read_identity_that_differs_from_the_new_head_bytes_reproves(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """The verified sandbox's own bytes, not the committed blob, are the comparison.

    A record whose read identity names a filtered or line-ending-converted
    rendering of the file points at a working tree the refreshed sandbox does
    not have, even where the patch and blob identities both hold.
    """
    code, _, _, posted = _call(
        fixture=inert_refresh, tmp_path=tmp_path, reads={_OBSERVED: "2" * 40}
    )

    assert code == 1
    assert f"read-identity-differs: {_OBSERVED}" in posted[0]


def test_a_replay_whose_output_differs_from_the_captured_proof_reproves(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """The replay is executed, so a proof that no longer prints is a finding."""
    code, _, _, posted = _call(
        fixture=inert_refresh, tmp_path=tmp_path, proofs=[["a line the file never carried"]]
    )

    assert code == 1
    assert "mechanical-replay-did-not-reproduce: step 1" in posted[0]


def test_a_replay_that_cannot_execute_reproves(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """A command that exits non-zero at the new head is treated as output that differed.

    `grep` of a pattern that no longer matches exits 1 and prints nothing, which
    is a step whose replay cannot be said to have reproduced anything — the same
    finding as output that differed, because both mean the proof is not evidence
    about this head.
    """
    code, _, _, posted = _call(
        fixture=inert_refresh,
        tmp_path=tmp_path,
        steps=[f'grep -n "a string the file never carried" {_OBSERVED}'],
        proofs=[[""]],
        reads=dict(inert_refresh["reads"]) if isinstance(inert_refresh["reads"], dict) else {},
    )

    assert code == 1
    assert "mechanical-replay-did-not-reproduce: step 1" in posted[0]


@pytest.mark.parametrize("count", [0, 2])
def test_a_captured_proof_that_is_not_one_fenced_block_reproves(
    inert_refresh: dict[str, object], tmp_path: Path, count: int
) -> None:
    """Scenario 178's outline: zero blocks and two blocks are both findings.

    A proof that cannot be attributed to a step has not said what to replay, so
    this is the fail-closed direction rather than a tolerance.
    """
    proof = _ITEM_BODY.splitlines()[0]

    code, _, _, posted = _call(
        fixture=inert_refresh,
        tmp_path=tmp_path,
        steps=[f"head -n 1 {_OBSERVED}"],
        proofs=[[proof] * count],
        reads=dict(inert_refresh["reads"]) if isinstance(inert_refresh["reads"], dict) else {},
    )

    assert code == 1
    assert f"captured-proof-not-one-fenced-block: step 1 gives {count}" in posted[0]


def test_an_unparseable_verified_record_reproves_and_names_the_unreadable_input(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """A decision input that cannot be READ routes to capture rather than guessing.

    The record is STILL posted, naming the input it could not read: the clause
    requires exactly one decision record on every changed-head refresh, and the
    condition hardest to reconstruct afterwards is exactly the one a silent
    fail-closed would leave no artifact for.
    """
    code, _, err, posted = _call(
        fixture=inert_refresh,
        tmp_path=tmp_path,
        comments=[{"body": "ordinary discussion carrying no record at all\n", "url": _RECORD_URL}],
    )

    assert code == 1
    assert "unreadable-input" in err
    assert len(posted) == 1
    assert "— reproof_required —" in posted[0]
    assert "verified Proof of Done record" in posted[0]
    assert "Verified head: unavailable" in posted[0]


def test_a_headless_verified_record_is_an_unreadable_input(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """A record naming no single full sha cannot say which tree it proved."""
    code, _, _, posted = _call(fixture=inert_refresh, tmp_path=tmp_path, record_head="not-a-sha")

    assert code == 1
    assert "publish-branch head" in posted[0]


def test_an_unresolvable_base_is_an_unreadable_input(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """A base this clone cannot resolve names the reading that failed, not a path."""
    broken = dict(inert_refresh)
    broken["previous_base"] = "f" * 40

    code, _, _, posted = _call(fixture=broken, tmp_path=tmp_path)

    assert code == 1
    assert "unreadable-input: the incoming paths" in posted[0]


def test_the_latest_verified_record_is_the_one_carried(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """A superseded verified record naming an unrelated head is not the input.

    Only `proof_verify` precedes publication, so in any conforming run the
    newest `verified` record IS this run's verification; reading an older one
    would measure the refresh against a tree a later replay had already
    replaced.
    """
    stale = _record_body(head="e" * 40, steps=[f"cat {_OBSERVED}"], proofs=[["stale"]], reads={})

    code, _, err, posted = _call(
        fixture=inert_refresh,
        tmp_path=tmp_path,
        comments=[
            {"body": stale, "url": "https://forge.invalid/pull/7#issuecomment-1"},
            {"body": _body_for(fixture=inert_refresh), "url": _RECORD_URL},
        ],
    )

    assert code == 0, err
    assert f"Verified head: {inert_refresh['verified_head']}" in posted[0]


def test_a_carry_forward_whose_record_cannot_be_posted_reproves(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """A decision nobody can read is not a decision, so it re-proves.

    Exit ONE on inputs that satisfy every carry-forward condition is the whole
    assertion: without this arm a forge outage would publish a head whose only
    evidence was a comment that never landed.
    """
    code, _, err, posted = _call(fixture=inert_refresh, tmp_path=tmp_path, post_fails=True)

    assert code == 1
    assert posted == []
    assert "LIVESPEC_CARRY_FORWARD_POST_FAILED" in err
    assert "carried_forward" in err


def test_a_reproof_required_record_that_cannot_be_posted_still_reproves(
    inert_refresh: dict[str, object], tmp_path: Path
) -> None:
    """The same outage on the other verdict routes the same way and says so."""
    moved = _rebase_onto(fixture=inert_refresh, paths={"module.py": "value = 1\n"})

    code, _, err, posted = _call(fixture=moved, tmp_path=tmp_path, post_fails=True)

    assert code == 1
    assert posted == []
    assert "LIVESPEC_CARRY_FORWARD_POST_FAILED" in err
    assert "reproof_required" in err


def test_the_decision_requires_all_six_inputs(tmp_path: Path) -> None:
    """An invocation missing one input decides nothing and says which are required."""
    program = tmp_path / CARRY_FORWARD_PROGRAM_FILENAME
    _ = program.write_text(carry_forward_program_source(), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(program), "--pull-request", "7"],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
    )

    assert result.returncode == 1
    assert "LIVESPEC_CARRY_FORWARD_USAGE" in result.stderr

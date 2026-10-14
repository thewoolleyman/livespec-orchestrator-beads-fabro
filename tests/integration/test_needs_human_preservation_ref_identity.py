"""The needs-human preservation ref is named by an identifier unique to the run.

Binds work-item bd-ib-zddbkq against SPECIFICATION/scenarios.md "Scenario 103 —
A needs-human outcome terminates the run and routes the decision to the ledger":
the terminal preserves the tree on a RUN-SCOPED ref, and that is only true while
the name it chooses cannot be shared by two runs.

BOTH ENGINES WERE WRONG, IN OPPOSITE DIRECTIONS, AND BOTH READ HEALTHY. The node
took its run id from `context.internal.run_id`. The Petri-era engine sets that
context key to the literal `petri` — measured on hp-candidate run 01M4SNYP3GT2
(2026-10-13, bd-ib-o6aeji canary 9), where the push SUCCEEDED and the preserved
tree landed on `refs/heads/needs-human/petri`, so every Petri-era needs-human
outcome named one shared ref and each one overwrote the last run's work. The
pinned engine supplies no stdin to a script node at all, so the same node
reported `LIVESPEC_NEEDS_HUMAN_NO_RUN_ID` and preserved nothing (measured on run
01M4T26F0ZERZ7TF0CAFNBJSDA, this item's own first dispatch). One engine named a
ref no run owns; the other named none.

THE PRIMARY SOURCE IS THEREFORE THE ONE WHOSE UNIQUENESS IS GUARANTEED rather
than the one the engine happens to offer: the DISPATCH'S OWN CORRELATION ID,
which the Dispatcher already projects into the sandbox clone's LOCAL git config
as `livespec.factoryRunId` (`_dispatcher_factory_provenance`). It is a uuid4
minted per dispatch before launch, so it is unique to the run on BOTH engines.
The engine's stdin value is the FALLBACK, for a clone no Dispatcher provisioned.
That order is what makes "never a shared placeholder" provable instead of
guessed: a grammar that tried to tell a real id from a placeholder would be
guessing about a value neither engine documents, and the first placeholder of a
shape it had not anticipated would be admitted silently.

THE MEASURED PLACEHOLDER IS REFUSED ON THE FALLBACK ARM TOO, which is the one
arm the ordering above does not already cover: the marker is absent only in a
clone no dispatch provisioned, and without the refusal such a clone on the
Petri-era engine would still reach `needs-human/petri`.

EVERY CASE CARRIES ITS OWN CONTROL, because each assertion has a cheap way to
pass vacuously. "The fallback named the ref" passes just as well for a node that
answered with a constant of its own, so a clone carrying NO marker must push
nothing. "The placeholder was refused" passes just as well for a node that
stopped reading stdin altogether, so a genuine engine run id must still name the
ref on that same marker-less arm. And the preserved BLOB is read back off the ref
rather than the ref alone, because a ref created at the last engine checkpoint is
present, plausible, and missing exactly the work the node exists to save.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_provenance import (
    FACTORY_RUN_ID_MARKER,
)

_WORKFLOW = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
_SCRIPT_ATTR = re.compile(r'script="(?P<value>(?:[^"\\]|\\.)*)"')
_REF_PREFIX = "refs/heads/needs-human/"
_PRESERVED = "LIVESPEC_NEEDS_HUMAN_PRESERVED"
_NO_RUN_ID = "LIVESPEC_NEEDS_HUMAN_NO_RUN_ID"
_SENTINEL = "LIVESPEC_NEEDS_HUMAN"
# The literal the Petri-era engine puts in `context.internal.run_id`, measured on
# run 01M4SNYP3GT2. It is the whole reason this module exists.
_PETRI_PLACEHOLDER = "petri"
# A real engine run id (a 26-character ULID) and a real dispatch correlation id
# (a 32-character uuid4 hex), each in the shape its own producer emits.
_ENGINE_RUN_ID = "01M4T26F0ZERZ7TF0CAFNBJSDA"
_DISPATCH_ID = "78d995fe82d5498a848bc0a461ad3a39"
_WIP = "in-progress.txt"
_WIP_BODY = "the unfinished work the preservation node exists to save\n"
_OPERATOR_NAME = "Chad Woolley"
_OPERATOR_EMAIL = "thewoolleyman@gmail.com"


def test_the_petri_placeholder_never_names_the_preservation_ref(tmp_path: Path) -> None:
    """Assertion 1: the Petri-era run names its ref by an id unique to the run."""
    work, origin = _sandbox(tmp_path=tmp_path, dispatch_id=_DISPATCH_ID)

    completed = _run_needs_human(work=work, run_id=_PETRI_PLACEHOLDER)

    assert _pushed_refs(origin=origin) == [f"{_REF_PREFIX}{_DISPATCH_ID}"], completed.stderr
    assert f"{_REF_PREFIX}{_PETRI_PLACEHOLDER}" not in completed.stderr
    assert f"{_PRESERVED}: {_REF_PREFIX}{_DISPATCH_ID}" in completed.stderr
    assert (
        _preserved_blob(origin=origin, ref=f"{_REF_PREFIX}{_DISPATCH_ID}", path=_WIP) == _WIP_BODY
    )


def test_an_engine_supplying_no_run_id_preserves_under_the_dispatch_correlation_id(
    tmp_path: Path,
) -> None:
    """Assertion 2: the pinned engine, which supplies no stdin, still preserves."""
    work, origin = _sandbox(tmp_path=tmp_path, dispatch_id=_DISPATCH_ID)

    completed = _run_needs_human(work=work, run_id=None)

    assert _pushed_refs(origin=origin) == [f"{_REF_PREFIX}{_DISPATCH_ID}"], completed.stderr
    assert f"{_PRESERVED}: {_REF_PREFIX}{_DISPATCH_ID}" in completed.stderr
    assert _NO_RUN_ID not in completed.stderr
    assert completed.returncode == 1


def test_the_placeholder_is_refused_with_no_dispatch_marker_to_fall_back_to(
    tmp_path: Path,
) -> None:
    """Assertion 3: the shared placeholder is never a ref name, on either arm.

    The ordering covers every clone a dispatch provisioned; this is the arm it
    does not cover, and the one a Petri-era run in such a clone would otherwise
    take straight to `needs-human/petri`.
    """
    work, origin = _sandbox(tmp_path=tmp_path, dispatch_id=None)

    completed = _run_needs_human(work=work, run_id=_PETRI_PLACEHOLDER)

    assert _pushed_refs(origin=origin) == [], completed.stderr
    assert _NO_RUN_ID in completed.stderr
    assert _PRESERVED not in completed.stderr
    assert completed.returncode == 1


def test_the_engine_run_id_names_the_ref_when_no_dispatch_marker_exists(tmp_path: Path) -> None:
    """Control for assertion 3: the stdin source is still alive and still read.

    Without this case, "the placeholder reached no ref" is equally consistent with
    a node that had stopped reading stdin altogether — and that node would pass
    the case above exactly as the correct one does.
    """
    work, origin = _sandbox(tmp_path=tmp_path, dispatch_id=None)

    completed = _run_needs_human(work=work, run_id=_ENGINE_RUN_ID)

    assert _pushed_refs(origin=origin) == [f"{_REF_PREFIX}{_ENGINE_RUN_ID}"], completed.stderr
    assert f"{_PRESERVED}: {_REF_PREFIX}{_ENGINE_RUN_ID}" in completed.stderr
    assert _NO_RUN_ID not in completed.stderr


def test_neither_source_available_pushes_nothing_and_says_so(tmp_path: Path) -> None:
    """Control for assertion 2: the fallback is a READING, not an invented constant.

    A node that answered with some constant of its own would satisfy assertion 2
    and leave this fixture — which demonstrably CAN carry a push, per the cases
    above — holding a ref it must not have.
    """
    work, origin = _sandbox(tmp_path=tmp_path, dispatch_id=None)

    completed = _run_needs_human(work=work, run_id=None)

    assert _pushed_refs(origin=origin) == [], completed.stderr
    assert _NO_RUN_ID in completed.stderr
    assert _PRESERVED not in completed.stderr
    assert _SENTINEL in completed.stderr
    assert completed.returncode == 1


def test_the_primary_source_reads_the_marker_the_dispatcher_declares() -> None:
    """Assertion 1's lockstep: one key name, declared once and read once.

    The Dispatcher WRITES this key from `FACTORY_RUN_ID_MARKER` and the terminal
    READS it out of a shell string the Python module cannot see, so a rename on
    either side would leave the node falling through to the stdin arm — which on
    the Petri-era engine is the placeholder, and on the pinned engine is nothing.
    The SCOPE is pinned too: `--local` is the only scope the prepare step writes,
    and a wider read would answer with some other dispatch's id, which is the
    collision this whole arm exists to refuse.
    """
    script = _node_script(node="needs_human")

    assert FACTORY_RUN_ID_MARKER == "livespec.factoryRunId"
    assert f"git config --local --get {FACTORY_RUN_ID_MARKER}" in script


def _node_script(*, node: str) -> str:
    """The node's OWN script, unescaped from the DOT attribute — never a paraphrase."""
    text = _WORKFLOW.read_text(encoding="utf-8")
    block = re.search(rf"^\s*{node}\s*\[(?P<body>.*?)^\s*\]", text, re.DOTALL | re.MULTILINE)
    assert block is not None, node
    attr = _SCRIPT_ATTR.search(block.group("body"))
    assert attr is not None, node
    unescaped = re.sub(r"\\(?P<escaped>.)", r"\g<escaped>", attr.group("value"))
    return unescaped.replace("{{ inputs.default_branch }}", "master")


def _git(repo: Path, *argv: str) -> None:
    subprocess.run(["git", *argv], cwd=str(repo), check=True, text=True, capture_output=True)


def _sandbox(*, tmp_path: Path, dispatch_id: str | None) -> tuple[Path, Path]:
    """A sandbox-shaped checkout with unfinished work and a real bare origin.

    `dispatch_id` is written to the LOCAL config exactly as the Dispatcher's
    prepare step writes it; None stands in for a clone no Dispatcher provisioned.
    """
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--quiet", "--bare", "--initial-branch=master", str(origin)],
        check=True,
        text=True,
        capture_output=True,
    )
    work = tmp_path / "work"
    work.mkdir(parents=True)
    _git(work, "init", "--quiet", "--initial-branch=master")
    _git(work, "config", "user.email", "fixture@example.invalid")
    _git(work, "config", "user.name", "Fixture")
    _git(work, "config", "commit.gpgsign", "false")
    if dispatch_id is not None:
        _git(work, "config", FACTORY_RUN_ID_MARKER, dispatch_id)
    (work / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(work, "add", "seed.txt")
    _git(work, "commit", "--quiet", "-m", "seed")
    _git(work, "remote", "add", "origin", str(origin))
    (work / _WIP).write_text(_WIP_BODY, encoding="utf-8")
    return work, origin


def _env() -> dict[str, str]:
    """The node's environment, with the FORMER run-id source stripped."""
    env = {key: value for key, value in os.environ.items() if key != "FABRO_RUN_ID"}
    env["LIVESPEC_GIT_AUTHOR_NAME"] = _OPERATOR_NAME
    env["LIVESPEC_GIT_AUTHOR_EMAIL"] = _OPERATOR_EMAIL
    return env


def _run_needs_human(*, work: Path, run_id: str | None) -> subprocess.CompletedProcess[str]:
    """Run the terminal's own script; `run_id=None` is an engine that sends no stdin."""
    return subprocess.run(
        ["sh", "-c", _node_script(node="needs_human")],
        cwd=str(work),
        env=_env(),
        check=False,
        text=True,
        capture_output=True,
        input="" if run_id is None else f"{run_id}\n",
    )


def _preserved_blob(*, origin: Path, ref: str, path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=str(origin),
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def _pushed_refs(*, origin: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)", "refs/"],
        cwd=str(origin),
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.split()

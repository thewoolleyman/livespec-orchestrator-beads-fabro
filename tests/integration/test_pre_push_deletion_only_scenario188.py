"""Scenario 188 — a push whose every ref update is a deletion skips the pre-push aggregate.

Binds `SPECIFICATION/scenarios.md` "Scenario 188" and
`SPECIFICATION/constraints.md` section "Pre-push gate refinements" (ratified at
v151): this repository's pre-push gate reads the ref updates git writes to the
hook's standard input, one `<local ref> <local object id> <remote ref> <remote
object id>` line per update, and git spells a deletion as an ALL-ZERO local
object id. When every line is such a deletion the push publishes NO TREE, so
there is nothing for the green-token probe or the `just check` aggregate to
judge — they would run against whatever happens to be checked out, a tree
unrelated to the ref being removed.

WHY THIS IS NOT THE PR-GATE-WEAKER-THAN-MASTER HOLE. A change-class predicate
that runs FEWER checks over a tree it is still PUBLISHING fails by PASSING, and
this fleet has shipped that hole once. Here nothing is published, so there is no
weaker verdict to issue: the gate is not narrowed, it is INAPPLICABLE. The
discrimination is keyed on the refs git itself names on standard input, never on
a change class read off the working tree, so there is no predicate that can rot
into a subset.

MEASURED COST OF NOT HAVING IT. The Dispatcher's post-run cleanup deletes a
run's source branch with a pure `git push ... origin :refs/heads/livespec/source/<id>`,
and that deletion ran the whole aggregate on the factory host — observed live
2026-10-16: check-pre-push, then check-skipping, then check-per-file-coverage,
then pytest. The Dispatcher holds the item's ownership lock until the push
returns, so a needs-human recovery could not resume for 60 to 100 minutes under
load (work-item bd-ib-qy5wol.1; the sibling fix for livespec-dev-tooling's own
copy is livespec-dev-tooling-r4oj47).

WHAT IS SIMULATED, AND WHY EACH SUBSTITUTION IS SAFE. The script under test is
executed as the SHIPPED BYTES — `bash dev-tooling/just-check-pre-push.sh` — with
`uv` and `just` replaced by stubs on `PATH` that record their argv. What the
script INVOKES is therefore the observable, which is the only thing that can
tell a real skip from a gate that ran and happened to pass. The `uv` stub
answers the green-token probe with a MISS (non-zero), the input shape that makes
the remainder of the path maximally observable: a token miss falls through to
the aggregate. Nothing about this repository's own tree, hooks, or ledger is
touched.

THREE HALVES ARE ASSERTED, because any one alone leaves the skip dead:

1. **The script** — the five input shapes of Scenario 188's three sub-scenarios.
2. **The lefthook wiring** — lefthook forwards a hook's standard input to a
   command ONLY when that command declares `use_stdin: true`. Without it the
   gate is handed nothing, every push reads as no-input, and the skip can never
   fire — silently, because the gate still runs and still passes.
3. **The recipe** — `just check-pre-push` must pass its own standard input
   through to the script, so a redirection in the recipe body would break the
   chain just as silently.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "dev-tooling" / "just-check-pre-push.sh"
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"
_JUSTFILE = _REPO_ROOT / "justfile"

# git's spelling of "this ref has no local object": an all-zero object id. The
# local-ref field of a deletion is the literal `(delete)`.
_ZERO_OID = "0" * 40
_LIVE_OID = "b3d4f1a90c7e25486fd1c0b8a7e6554321098765"
_OTHER_OID = "ac1e5d0f3b729648175e2c9a0d4f6b8172635409"

_SKIP_NOTICE = "only deletes refs"
_GREEN_TOKEN_PROBE = "green_token check"
_AGGREGATE = "just check-skipping check-codex-skill-picker"
_LEDGER_CONFORMANCE_STEP = "02-ledger-conformance"

# The stub `uv` answers every probe with a MISS (non-zero), which is what makes
# the unchanged path maximally observable: a token miss falls through to the
# aggregate rather than short-circuiting before it.
_UV_STUB = '#!/usr/bin/env bash\nprintf "uv %s\\n" "$*" >> "${STUB_LOG}"\nexit 1\n'
_JUST_STUB = '#!/usr/bin/env bash\nprintf "just %s\\n" "$*" >> "${STUB_LOG}"\nexit 0\n'

# The `01-check-pre-push` command, as lefthook must carry it for the hook's
# standard input to reach the script at all.
_PRE_PUSH_COMMAND = re.compile(
    r"^    01-check-pre-push:\n(?P<body>(?:      .*\n)+)",
    re.MULTILINE,
)
# The `check-pre-push` recipe body: every indented line under the target.
_PRE_PUSH_RECIPE = re.compile(
    r"^check-pre-push:\n(?P<body>(?:    .*\n)+)",
    re.MULTILINE,
)


def _run_pre_push(*, tmp_path: Path, stdin: str) -> tuple[int, str, list[str]]:
    """Run the shipped `just-check-pre-push.sh` on one hook standard-input payload.

    Returns the script's exit code, its stdout, and every command it invoked, in
    order.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    for name, body in (("uv", _UV_STUB), ("just", _JUST_STUB)):
        stub = stub_dir / name
        _ = stub.write_text(body, encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "invocations.log"
    env = os.environ.copy()
    env.update({"PATH": f"{stub_dir}{os.pathsep}{env['PATH']}", "STUB_LOG": str(log)})
    completed = subprocess.run(
        ["bash", str(_SCRIPT)],
        cwd=str(tmp_path),
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return completed.returncode, completed.stdout, invoked


def _delete_line(*, ref: str) -> str:
    """One pre-push standard-input line for a ref DELETION."""
    return f"(delete) {_ZERO_OID} {ref} {_LIVE_OID}\n"


def _update_line(*, ref: str, remote_oid: str = _OTHER_OID) -> str:
    """One pre-push standard-input line for a ref CREATE or UPDATE."""
    return f"{ref} {_LIVE_OID} {ref} {remote_oid}\n"


def test_scenario188_a_delete_only_push_skips_every_gate_and_says_why(*, tmp_path: Path) -> None:
    """A deletion publishes no tree, so NOTHING the script can run is about it."""
    code, stdout, invoked = _run_pre_push(
        tmp_path=tmp_path, stdin=_delete_line(ref="refs/heads/livespec/source/gone")
    )

    assert code == 0, f"a delete-only push must complete; stdout={stdout!r} invoked={invoked}"
    assert invoked == [], (
        f"a delete-only push must reach neither the green-token probe nor the `just check` "
        f"aggregate — there is no published tree for either to judge, and the measured "
        f"deletion held the Dispatcher's ownership lock for the whole aggregate's runtime; "
        f"invoked={invoked}"
    )
    assert _SKIP_NOTICE in stdout and "skipp" in stdout, (
        f"the skip must NARRATE itself: a gate that silently does nothing is "
        f"indistinguishable from a gate that ran and passed; stdout={stdout!r}"
    )


def test_scenario188_a_push_deleting_several_refs_at_once_still_skips(*, tmp_path: Path) -> None:
    """EVERY line being a deletion is the condition, not the first line being one."""
    stdin = _delete_line(ref="refs/heads/gone") + _delete_line(ref="refs/heads/also-gone")

    code, stdout, invoked = _run_pre_push(tmp_path=tmp_path, stdin=stdin)

    assert code == 0, f"stdout={stdout!r} invoked={invoked}"
    assert invoked == [], f"invoked={invoked}"
    assert _SKIP_NOTICE in stdout, f"stdout={stdout!r}"


def test_scenario188_a_deletion_beside_an_update_runs_the_full_gate(*, tmp_path: Path) -> None:
    """ONE published ref is a published tree — the whole gate is owed, deletions or not."""
    stdin = _delete_line(ref="refs/heads/gone") + _update_line(ref="refs/heads/feature")

    code, stdout, invoked = _run_pre_push(tmp_path=tmp_path, stdin=stdin)

    assert code == 0, f"stdout={stdout!r} invoked={invoked}"
    assert _AGGREGATE in invoked, (
        f"a push carrying any non-deletion must take the unchanged full path — narrowing it "
        f"on the mere presence of a deletion would be the PR-gate-weaker-than-master hole "
        f"this fleet has already shipped once; stdout={stdout!r} invoked={invoked}"
    )
    assert _SKIP_NOTICE not in stdout, f"stdout={stdout!r}"


def test_scenario188_an_update_only_push_runs_the_full_gate(*, tmp_path: Path) -> None:
    """The ordinary publish: the green-token probe, then the aggregate on a miss."""
    code, stdout, invoked = _run_pre_push(
        tmp_path=tmp_path, stdin=_update_line(ref="refs/heads/feature", remote_oid=_ZERO_OID)
    )

    assert code == 0, f"stdout={stdout!r} invoked={invoked}"
    assert [
        line for line in invoked if _GREEN_TOKEN_PROBE in line
    ], f"the green-token probe is the first member of the unchanged path; invoked={invoked}"
    assert _AGGREGATE in invoked, f"invoked={invoked}"


def test_scenario188_an_absent_standard_input_keeps_the_existing_path(*, tmp_path: Path) -> None:
    """No refs read is NOT "nothing to publish" — it is no evidence, so the gate runs.

    Fail-CLOSED in the only direction a mistake here is merely expensive. A
    hand-run `just check-pre-push`, a lefthook build that does not forward
    standard input, and any future transport that stops naming refs all arrive
    as emptiness; reading that as a delete-only push would skip the gate on
    EVERY push.
    """
    code, stdout, invoked = _run_pre_push(tmp_path=tmp_path, stdin="")

    assert code == 0, f"stdout={stdout!r} invoked={invoked}"
    assert _AGGREGATE in invoked, f"stdout={stdout!r} invoked={invoked}"
    assert _SKIP_NOTICE not in stdout, f"stdout={stdout!r}"


def test_lefthook_forwards_the_hook_standard_input_to_the_gate_command() -> None:
    """Without `use_stdin: true` the script is handed nothing and the skip is dead code."""
    matched = _PRE_PUSH_COMMAND.search(_LEFTHOOK.read_text(encoding="utf-8"))
    assert matched is not None, (
        f"`01-check-pre-push` must be a `pre-push` command of "
        f"{_LEFTHOOK.relative_to(_REPO_ROOT)}"
    )
    body = matched.group("body")
    assert "use_stdin: true" in body, (
        f"lefthook forwards a hook's standard input to a command ONLY when that command "
        f"declares `use_stdin: true`. Without it the gate never sees the `<local ref> "
        f"<local object id> ...` lines git writes, every push reads as no-input, and the "
        f"delete-only skip can never fire — silently, because the gate still runs and still "
        f"passes; body={body!r}"
    )
    assert "run: just check-pre-push" in body, (
        f"the command must still DELEGATE to the recipe (the toolchain-pins rule of "
        f"non-functional-requirements.md: a `run:` field invokes `just <target>` and never "
        f"shells out to an underlying tool directly); body={body!r}"
    )


def test_the_ledger_conformance_step_is_separate_and_the_skip_lives_in_the_recipe() -> None:
    """The always-run ledger step must stay out of reach of the skip.

    The ratified clause is explicit: `02-ledger-conformance` is a SEPARATE
    pre-push step this skip does not reach — a beads tenant's state is not
    tree-derived, so it is owed on a deletion-only push too. That is why the
    skip MUST live inside `just check-pre-push` and never at the lefthook level,
    where a short-circuit would take the ledger step down with it.
    """
    lefthook = _LEFTHOOK.read_text(encoding="utf-8")
    recipe = _PRE_PUSH_RECIPE.search(_JUSTFILE.read_text(encoding="utf-8"))

    assert f"{_LEDGER_CONFORMANCE_STEP}:" in lefthook, (
        f"the always-run ledger-conformance step must remain a pre-push command of "
        f"{_LEFTHOOK.relative_to(_REPO_ROOT)}"
    )
    assert _SKIP_NOTICE not in lefthook, (
        f"the deletion skip must not be expressed at the lefthook level, where it would "
        f"also skip {_LEDGER_CONFORMANCE_STEP}"
    )
    assert _SKIP_NOTICE in _SCRIPT.read_text(encoding="utf-8"), (
        f"the skip belongs inside {_SCRIPT.relative_to(_REPO_ROOT)}, the body of the "
        f"`check-pre-push` recipe"
    )
    assert recipe is not None, "the `check-pre-push` recipe must exist"
    body = recipe.group("body")
    assert "dev-tooling/just-check-pre-push.sh" in body, f"body={body!r}"
    assert "<" not in body, (
        f"the recipe must pass its own standard input THROUGH to the script; any "
        f"redirection breaks the chain as silently as a missing `use_stdin`; body={body!r}"
    )

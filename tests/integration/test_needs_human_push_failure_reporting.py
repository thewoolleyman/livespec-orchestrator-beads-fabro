"""The needs-human node reports WHY its push of the preserved tree failed.

Binds work-item bd-ib-s6bowj against `SPECIFICATION/scenarios.md` "## Scenario
103 — A needs-human outcome terminates the run and routes the decision to the
ledger": the terminal MUST preserve the run's work by reference before it
terminates, and when that preservation push fails the node's own output is the
ONLY witness to why.

Measured on hp-candidate: canary 5 (run 01M4NWARSD8T) and canary 6 (run
01M4PBFW4MP8, on v0.187.0, which already carried the bd-ib-52zt3o fix) both
ended `LIVESPEC_NEEDS_HUMAN_PUSH_FAILED` AND NOTHING ELSE. The node captured the
push command's output into a variable and then discarded it, so two occurrences
and one attempted fix left the cause undiagnosed. A marker with no cause is a
LABEL, not a finding: an operator reading it learns that a push they cannot see
failed for a reason nobody recorded, which is why the hook-gated-push lead for
these two runs had to be chased through a THIRD run's timings instead of being
read off the second one's output.

THE FIXTURE'S REFUSING `pre-receive` HOOK IS NOT A STAND-IN FOR ANY PARTICULAR
CAUSE — it is a stand-in for a push that fails with something to SAY, which is
the only premise this node's reporting duty rests on. It lives on the ORIGIN
deliberately: the node's own git writes run hookless (`-c
core.hooksPath=/dev/null`, work-item bd-ib-3vn3mu), so a LOCAL hook cannot
refuse this push at all, while a receiving-end refusal is the shape legacy run
01M4PPN7RX2M actually produced.

EVERY ABSENCE ASSERTED HERE RUNS A CONTROL FIRST, in the same fixture, through a
plain `git push`: the error text must really be in that output for the node to
have reported it, the raw output must really exceed the cap for a bound to have
bitten anything, and the credential must really be in that output for a
redaction to have removed anything. Without those controls "the secret is
absent" and "the detail is short" are equally consistent with a fixture that
never produced either, and nothing in the node's output distinguishes them.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

_WORKFLOW = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
_SCRIPT_ATTR = re.compile(r'script="(?P<value>(?:[^"\\]|\\.)*)"')
_RUN_ID = "01M4PUSHFAILUREDETAIL"
_REF = f"refs/heads/needs-human/{_RUN_ID}"
_PUSH_FAILED = "LIVESPEC_NEEDS_HUMAN_PUSH_FAILED:"
_PRESERVED = "LIVESPEC_NEEDS_HUMAN_PRESERVED:"
_SENTINEL = "LIVESPEC_NEEDS_HUMAN: "
_REASON = "loop cannot auto-resolve this work-item"
_REFUSAL = "livespec-check-suite refuses the preserved tree: three files below the coverage floor"
_SECRET = "not-a-real-credential-9f3a2b"
_CREDENTIAL_URL = f"https://x-access-token:{_SECRET}@github.com/owner/repo.git"
_REDACTED_URL = "https://REDACTED@github.com/owner/repo.git"
_BYTE_CAP = re.compile(r"head -c (?P<cap>[0-9]+)")
_FILLER_LINES = 120
_WIP = "in-progress.txt"
_WIP_BODY = "the unfinished work the preservation node exists to save\n"
_OPERATOR_NAME = "Chad Woolley"
_OPERATOR_EMAIL = "thewoolleyman@gmail.com"


def test_a_failed_preservation_push_reports_the_push_command_error_text(
    tmp_path: Path,
) -> None:
    """Assertion 1: the push-failed marker is followed by what the push actually said."""
    work, _origin = _refusing_checkout(tmp_path=tmp_path)
    _control_push_output(work=work)

    completed = _run_needs_human(work=work, run_id=_RUN_ID)

    assert _REFUSAL in _reported_push_detail(stderr=completed.stderr)


def test_the_reported_push_error_is_bounded_and_redacts_a_remote_url_credential(
    tmp_path: Path,
) -> None:
    """Assertion 2: a cap the raw output exceeds, and a credential it carries.

    Both halves are controlled against the SAME raw push output, because each
    absence asserted here is otherwise indistinguishable from a fixture that
    produced nothing to remove: a short report is evidence of a bound only
    beside an output that exceeded it, and a secret-free report is evidence of a
    redaction only beside an output that carried the secret.

    The secret is asserted absent from the WHOLE of stderr rather than from the
    reported region, because a credential that escaped into the marker line or
    past the sentinel would be just as published as one inside the detail.
    """
    work, _origin = _refusing_checkout(tmp_path=tmp_path)
    control = _control_push_output(work=work)
    assert _SECRET in control

    completed = _run_needs_human(work=work, run_id=_RUN_ID)

    detail = _reported_push_detail(stderr=completed.stderr)
    assert _SECRET not in completed.stderr
    assert _REDACTED_URL in detail
    cap = _declared_byte_cap()
    assert len(control) > cap
    assert len(detail.strip("\n")) <= cap
    assert str(cap) in _marker_line(stderr=completed.stderr)


def test_a_successful_preservation_push_names_the_ref_it_pushed(
    tmp_path: Path,
) -> None:
    """Assertion 3: on success the node says WHICH ref now carries the tree.

    The ref is read back off the origin too, because a node that merely PRINTED
    the name it intended to push would satisfy the output assertion alone.
    """
    work, origin = _checkout(tmp_path=tmp_path, name="preserved")

    completed = _run_needs_human(work=work, run_id=_RUN_ID)

    assert f"{_PRESERVED} {_REF}" in completed.stderr
    assert _pushed_refs(origin=origin) == [_REF]


def test_the_node_terminates_non_green_with_the_marker_whether_the_push_succeeded(
    tmp_path: Path,
) -> None:
    """Assertion 4: reporting is the only thing that changed about the node.

    The two legs are ONE case deliberately. "Whether or not its push succeeded"
    is a claim about the pair: either leg alone passes just as well against a
    node that terminates correctly down one arm and falls out of the other.
    """
    refused, _refused_origin = _refusing_checkout(tmp_path=tmp_path)
    pushed, _pushed_origin = _checkout(tmp_path=tmp_path, name="preserved")

    failed_push = _run_needs_human(work=refused, run_id=_RUN_ID)
    succeeded_push = _run_needs_human(work=pushed, run_id=_RUN_ID)

    assert failed_push.returncode == 1, failed_push.stderr
    assert succeeded_push.returncode == 1, succeeded_push.stderr
    assert f"{_SENTINEL}{_REASON}" in failed_push.stderr
    assert f"{_SENTINEL}{_REASON}" in succeeded_push.stderr
    assert _PUSH_FAILED in failed_push.stderr
    assert _PRESERVED in succeeded_push.stderr


def _node_script() -> str:
    """The node's OWN script, unescaped from the DOT attribute — never a paraphrase."""
    text = _WORKFLOW.read_text(encoding="utf-8")
    block = re.search(r"^\s*needs_human\s*\[(?P<body>.*?)^\s*\]", text, re.DOTALL | re.MULTILINE)
    assert block is not None
    attr = _SCRIPT_ATTR.search(block.group("body"))
    assert attr is not None
    unescaped = re.sub(r"\\(?P<escaped>.)", r"\g<escaped>", attr.group("value"))
    return unescaped.replace("{{ inputs.default_branch }}", "master")


def _run(*, argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=str(cwd), check=True, text=True, capture_output=True)


def _git(*, repo: Path, argv: list[str]) -> None:
    _run(argv=["git", *argv], cwd=repo)


def _checkout(*, tmp_path: Path, name: str) -> tuple[Path, Path]:
    """A sandbox-shaped checkout holding unfinished work, with its own bare origin."""
    origin = tmp_path / f"{name}-origin.git"
    _run(
        argv=["git", "init", "--quiet", "--bare", "--initial-branch=master", str(origin)],
        cwd=tmp_path,
    )
    work = tmp_path / name
    work.mkdir(parents=True)
    _git(repo=work, argv=["init", "--quiet", "--initial-branch=master"])
    _git(repo=work, argv=["config", "user.email", "fixture@example.invalid"])
    _git(repo=work, argv=["config", "user.name", "Fixture"])
    _git(repo=work, argv=["config", "commit.gpgsign", "false"])
    (work / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo=work, argv=["add", "seed.txt"])
    _git(repo=work, argv=["commit", "--quiet", "-m", "seed"])
    _git(repo=work, argv=["remote", "add", "origin", str(origin)])
    (work / _WIP).write_text(_WIP_BODY, encoding="utf-8")
    return work, origin


def _refusing_checkout(*, tmp_path: Path) -> tuple[Path, Path]:
    """The same checkout, against an origin that refuses the push and says why.

    The refusal line is deliberately CREDENTIAL-FREE and comes FIRST, so it
    survives both the redaction and the truncation verbatim; the filler lines
    after it carry the credential-bearing URL and the volume.
    """
    work, origin = _checkout(tmp_path=tmp_path, name="refused")
    hook = origin / "hooks" / "pre-receive"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        "#!/bin/sh\n"
        f'echo "{_REFUSAL}" >&2\n'
        "i=0\n"
        f"while test $i -lt {_FILLER_LINES}; do\n"
        f'  echo "  attempted against {_CREDENTIAL_URL} (detail line $i)" >&2\n'
        "  i=$((i+1))\n"
        "done\n"
        "exit 1\n",
        encoding="utf-8",
    )
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    return work, origin


def _control_push_output(*, work: Path) -> str:
    """Prove this fixture's push really FAILS and really has something to say."""
    completed = subprocess.run(
        ["git", "push", "origin", "HEAD:refs/heads/control"],
        cwd=str(work),
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode != 0, completed.stdout
    combined = completed.stdout + completed.stderr
    assert _REFUSAL in combined
    return combined


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["LIVESPEC_GIT_AUTHOR_NAME"] = _OPERATOR_NAME
    env["LIVESPEC_GIT_AUTHOR_EMAIL"] = _OPERATOR_EMAIL
    return env


def _run_needs_human(*, work: Path, run_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", _node_script()],
        cwd=str(work),
        env=_env(),
        check=False,
        text=True,
        capture_output=True,
        input=f"{run_id}\n",
    )


def _reported_push_detail(*, stderr: str) -> str:
    """What the node emitted BETWEEN the push-failed marker line and the sentinel.

    The marker's own line is dropped rather than included, so a bound asserted
    over this region measures the reported push output and not the fixed prose
    the node prints around it.
    """
    assert _PUSH_FAILED in stderr, stderr
    after_marker = stderr.split(_PUSH_FAILED, 1)[1]
    assert _SENTINEL in after_marker, after_marker
    before_sentinel = after_marker.split(_SENTINEL, 1)[0]
    assert "\n" in before_sentinel, before_sentinel
    return before_sentinel.split("\n", 1)[1]


def _marker_line(*, stderr: str) -> str:
    """The push-failed marker's own line, which must declare the cap it applied."""
    assert _PUSH_FAILED in stderr, stderr
    return stderr.split(_PUSH_FAILED, 1)[1].split("\n", 1)[0]


def _declared_byte_cap() -> int:
    """The node's OWN cap, read off its script — never a figure restated here.

    A literal written in this module would keep agreeing with itself after the
    node's cap moved underneath it, and the claim is that the node bounds what
    it reports, not that it bounds it at some number this module remembers.
    """
    match = _BYTE_CAP.search(_node_script())
    assert match is not None, "the needs_human script declares no `head -c <cap>` byte cap"
    return int(match.group("cap"))


def _pushed_refs(*, origin: Path) -> list[str]:
    completed = _run(
        argv=["git", "for-each-ref", "--format=%(refname)", "refs/"],
        cwd=origin,
    )
    return completed.stdout.split()

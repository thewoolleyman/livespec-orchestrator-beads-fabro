"""The needs-human terminal reports WHY its preservation push failed.

Binds work-item bd-ib-s6bowj against the SPECIFICATION/contracts.md rule that a
factory run never awaits a human (ratified v093, Scenario 103): a needs-human
outcome MUST preserve the run's work by reference before terminating, and when
that preservation cannot happen the operator has to be told what stopped it.

THE NODE CAPTURED THE PUSH'S OUTPUT AND THEN THREW IT AWAY, which is why the
same failure survived two measured occurrences and one attempted fix. On
hp-candidate (fabro 0.382.0-nightly.0 adeefec) canary 5 (run 01M4NWARSD8T) and
canary 6 (run 01M4PBFW4MP8 — on v0.187.0, which carries the bd-ib-52zt3o
credential-helper fix) both ended `LIVESPEC_NEEDS_HUMAN_PUSH_FAILED` carrying
NO cause, so each triage had to reason from the absence: a hook-gated push, an
absent credential and an unreachable origin all produce that one line, and they
have three different remedies. The marker says the preservation failed; it has
never said why.

THE SUCCESS ARM IS THE CONTROL, not decoration. "The failure arm reports the
push's error" is satisfied just as well by a node that prints a diagnosis on
EVERY ending, and the ref-naming assertion is what excludes that — so the two
arms are asserted in the same module against the same fixture shape.

THE FIXTURES ARE REAL `git push` FAILURES, never a stand-in for one. The text
under test is the push command's OWN output, so a fixture that fed the node a
string would assert that the node can echo a string — which it could do without
ever reading the push. Each case therefore runs a CONTROL push of the same kind
in the same repository first, and the node's report is compared against what
that control actually printed. Three genuine failures are used:

- an origin path that does not exist, whose error is short;
- the same with a ~3 kB path, whose error exceeds the reported bound;
- a `git://` origin carrying userinfo, which git echoes VERBATIM.

That last one is worth stating, because it is the reason the redaction is not
dead code. git 2.43 anonymizes its own `fatal: unable to access '<url>'` line,
so an https refusal hides the token — but the git-protocol host-lookup failure
prints `unable to look up x-access-token:<token>@<host>` with the userinfo
intact, and a `remote:` line is server-authored text git passes through
untouched. The pinned engine, meanwhile, embeds its token in the origin URL
(see `_dispatcher_git_credential_helper`'s module docstring), so the credential
IS in the remote URL on that path. The redaction runs BEFORE the bound for the
matching reason: bounding first can cut inside the userinfo and leave the
token's prefix standing, which reads as redacted and is not.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

_WORKFLOW = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
_SCRIPT_ATTR = re.compile(r'script="(?P<value>(?:[^"\\]|\\.)*)"')
_RUN_ID = "01M4PUSHFAILUREREPORTED"
_REF = f"refs/heads/needs-human/{_RUN_ID}"
_PUSH_FAILED = "LIVESPEC_NEEDS_HUMAN_PUSH_FAILED"
_PRESERVED = "LIVESPEC_NEEDS_HUMAN_PRESERVED"
_REASON = "LIVESPEC_NEEDS_HUMAN: "
_WIP = "in-progress.txt"
_WIP_BODY = "the unfinished work the preservation node exists to save\n"
_OPERATOR_NAME = "Chad Woolley"
_OPERATOR_EMAIL = "thewoolleyman@gmail.com"
_ABSENT_ORIGIN = "absent-origin.git"

# The reported bound, read off the marker line the node prints rather than kept
# as a private expectation: an operator reading a truncated diagnosis has to be
# told it was truncated and by how much, or they read the tail's absence as the
# push having said nothing more.
_BOUND_BYTES = 2000
_BOUND_CLAUSE = f"bounded to {_BOUND_BYTES} bytes"

# A `git://` origin carrying userinfo. git echoes this one VERBATIM — see the
# module docstring for why that makes it the fixture rather than an https URL,
# whose `unable to access` line git 2.43 anonymizes on its own.
_USERNAME = "x-access-token"
_TOKEN = "ghs_THISISTHESECRETINSTALLATIONTOKEN"
_CREDENTIAL_HOST = "127.0.0.1:9418"
_CREDENTIAL_ORIGIN = f"git://{_USERNAME}:{_TOKEN}@{_CREDENTIAL_HOST}/owner/repo.git"
_REDACTION_MARKER = "<credential-redacted>"

# A path long enough that the push's own diagnosis quoting it overruns the
# bound. The error is dominated by the path, so the length is the fixture's to
# choose; the case still asserts the overrun off the MEASURED control rather
# than trusting this number.
_LONG_SEGMENTS = 15
_LONG_SEGMENT = "p" * 200


def test_a_failed_preservation_push_reports_the_push_error_after_the_marker(
    tmp_path: Path,
) -> None:
    """Assertion 1: the output after the marker carries the push command's error text."""
    work = _sandbox(tmp_path=tmp_path, origin_url=str(tmp_path / _ABSENT_ORIGIN))
    refused = _control_push_error(work=work)
    assert "does not appear to be a git repository" in refused

    completed = _run_needs_human(work=work, run_id=_RUN_ID)

    reported = _reported_push_error(stderr=completed.stderr)
    assert reported != ""
    assert refused.rstrip("\n") in reported
    assert _PRESERVED not in completed.stderr


def test_the_node_still_terminates_non_green_with_the_needs_human_marker_after_a_failed_push(
    tmp_path: Path,
) -> None:
    """Assertion 4, failure half: reporting the cause changed nothing about the ending."""
    work = _sandbox(tmp_path=tmp_path, origin_url=str(tmp_path / _ABSENT_ORIGIN))

    completed = _run_needs_human(work=work, run_id=_RUN_ID)

    assert completed.returncode == 1
    assert f"{_REASON}loop cannot auto-resolve this work-item" in completed.stderr
    assert _PUSH_FAILED in completed.stderr


def test_the_reported_push_error_redacts_a_credential_carried_in_the_remote_url(
    tmp_path: Path,
) -> None:
    """Assertion 2, redaction half.

    The CONTROL is what makes the absence mean anything: it proves the push's
    own output DID carry the credential, so "the token is not in the report" is
    evidence of redaction rather than of a node that discarded the whole text —
    which is exactly what this node used to do, and which satisfies every
    token-absence assertion perfectly.

    The surviving `<redacted>@<host>` and `unable to look up` are asserted for
    the mirror reason: a report that redacted the WHOLE line would also carry no
    token, and would carry no diagnosis either.
    """
    work = _sandbox(tmp_path=tmp_path, origin_url=_CREDENTIAL_ORIGIN)
    leaked = _control_push_error(work=work)
    assert _TOKEN in leaked
    assert _USERNAME in leaked

    completed = _run_needs_human(work=work, run_id=_RUN_ID)

    reported = _reported_push_error(stderr=completed.stderr)
    assert _TOKEN not in completed.stderr
    assert _USERNAME not in completed.stderr
    assert f"{_REDACTION_MARKER}@{_CREDENTIAL_HOST}" in reported
    assert "unable to look up" in reported


def test_the_reported_push_error_is_bounded_in_length(tmp_path: Path) -> None:
    """Assertion 2, bound half.

    Asserted as BYTES AGAINST THE CONTROL'S OWN BYTES rather than against a
    phrase expected to survive: the report must be the leading `_BOUND_BYTES`
    of what the push printed, which says in one comparison that the bound held,
    that the text is the push's own, and that the truncation kept the head.
    A phrase-presence assertion would instead encode this git version's exact
    message lengths, and would pass for a report that rewrote the text.

    The control establishes the overrun. Without it a bounded report is
    indistinguishable from a short error reported whole, which is what the two
    cases above already exercise.
    """
    work = _sandbox(tmp_path=tmp_path, origin_url=_long_absent_origin(tmp_path=tmp_path))
    unbounded = _control_push_error(work=work).rstrip("\n").encode("utf-8")
    assert len(unbounded) > _BOUND_BYTES

    completed = _run_needs_human(work=work, run_id=_RUN_ID)

    reported = _reported_push_error(stderr=completed.stderr).rstrip("\n").encode("utf-8")
    assert len(reported) <= _BOUND_BYTES
    assert reported == unbounded[:_BOUND_BYTES].rstrip(b"\n")
    assert _BOUND_CLAUSE in completed.stderr


def test_a_successful_preservation_push_names_the_ref_it_pushed(tmp_path: Path) -> None:
    """Assertion 3, and the control for assertion 1 — read the module docstring."""
    origin = _bare_origin(tmp_path=tmp_path)
    work = _sandbox(tmp_path=tmp_path, origin_url=str(origin))

    completed = _run_needs_human(work=work, run_id=_RUN_ID)

    assert f"{_PRESERVED}: {_REF}" in completed.stderr
    assert _PUSH_FAILED not in completed.stderr
    assert _pushed_refs(origin=origin) == [_REF]
    assert completed.returncode == 1
    assert f"{_REASON}loop cannot auto-resolve this work-item" in completed.stderr


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


def _sandbox(*, tmp_path: Path, origin_url: str) -> Path:
    """A sandbox-shaped checkout holding unfinished work, pointed at one origin."""
    work = tmp_path / "work"
    work.mkdir(parents=True)
    _git(work, "init", "--quiet", "--initial-branch=master")
    _git(work, "config", "user.email", "fixture@example.invalid")
    _git(work, "config", "user.name", "Fixture")
    _git(work, "config", "commit.gpgsign", "false")
    (work / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(work, "add", "seed.txt")
    _git(work, "commit", "--quiet", "-m", "seed")
    _git(work, "remote", "add", "origin", origin_url)
    (work / _WIP).write_text(_WIP_BODY, encoding="utf-8")
    return work


def _long_absent_origin(*, tmp_path: Path) -> str:
    """An origin path that does not exist and is long enough to overrun the bound."""
    return str(tmp_path.joinpath(*([_LONG_SEGMENT] * _LONG_SEGMENTS), "absent.git"))


def _bare_origin(*, tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--quiet", "--bare", "--initial-branch=master", str(origin)],
        check=True,
        text=True,
        capture_output=True,
    )
    return origin


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["LIVESPEC_GIT_AUTHOR_NAME"] = _OPERATOR_NAME
    env["LIVESPEC_GIT_AUTHOR_EMAIL"] = _OPERATOR_EMAIL
    return env


def _run_needs_human(*, work: Path, run_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", _node_script(node="needs_human")],
        cwd=str(work),
        env=_env(),
        check=False,
        text=True,
        capture_output=True,
        input=f"{run_id}\n",
    )


def _control_push_error(*, work: Path) -> str:
    """What a push of the same kind, in the same repository, REALLY prints.

    This is what makes the report checkable against the push rather than against
    a sentence written here: the node's text is compared with these bytes.
    """
    completed = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "push", "origin", "HEAD:refs/heads/control"],
        cwd=str(work),
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode != 0, completed.stdout
    return f"{completed.stdout}{completed.stderr}"


def _reported_push_error(*, stderr: str) -> str:
    """The push output the node reported: the lines AFTER the marker line.

    Sliced at the marker and at the terminal's own reason line, so the claim
    stays the clause's own — what the node's output carries AFTER the
    push-failed marker — rather than "somewhere in stderr".
    """
    after = stderr.partition(_PUSH_FAILED)[2]
    assert after != "", stderr
    return after.partition("\n")[2].partition(_REASON)[0]


def _pushed_refs(*, origin: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)", "refs/"],
        cwd=str(origin),
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.split()

"""The materialized publication-head program, and its equality with the host reader.

The module under test ships a STDLIB-ONLY program the Dispatcher lands in the
sandbox, because the `pr` command stage has to establish the head whose proof
was captured and verified and the plugin package is not importable from a
governed clone. That makes the program a SECOND implementation of one record
format, so the load-bearing case here is the EQUALITY binding: the program's own
reader is run beside `_dispatcher_resume_anchor.published_head` over the same
bodies and must give the same answer.

WHY THE REAL PAYLOADS ARE THE CONTROL THAT MATTERS. Both committed payloads --
`fixtures/proof_records/pull-request-2538-comments.json` and
`...-2561-comments.json`, the only real records this repository has -- carry NO
publish-branch head at all, because they predate the clause that requires one.
A hand-rolled line-two reader written against the capture prompt's own wording
therefore returns nothing on 100% of real records while looking entirely
reasonable, which is the measurement that put this program here rather than a
`grep` in the node's script. The synthetic bodies beside them are what make the
equality mean something: they exercise fencing, duplicate naming, a short sha,
backticks and a case-shifted label, each of which the two readers could disagree
about and the real payloads cannot reach.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_NOT_REPRODUCED,
    proof_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_head import (
    PROOF_HEAD_PROGRAM_FILENAME,
    PROOF_HEAD_REQUIRED_VERDICTS,
    proof_head_program_path_expansion,
    proof_head_program_prepare_steps_block,
    proof_head_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    PUBLISH_HEAD_LABEL,
    published_head,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REAL_PAYLOADS = _REPO_ROOT / "tests" / "integration" / "fixtures" / "proof_records"

_SHA = "a" * 40
_OTHER_SHA = "b" * 40


def _materialized(*, tmp_path: Path) -> ModuleType:
    """The program as a module, loaded from the bytes the prepare step writes.

    Loaded from the SOURCE the Dispatcher ships rather than from a copy written
    here, so a change to the program that broke the equality cannot pass by
    leaving this test reading something else.
    """
    path = tmp_path / PROOF_HEAD_PROGRAM_FILENAME
    _ = path.write_text(proof_head_program_source(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("livespec_publication_head", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _real_bodies() -> list[str]:
    bodies: list[str] = []
    for payload in sorted(_REAL_PAYLOADS.glob("*.json")):
        data = json.loads(payload.read_text(encoding="utf-8"))
        bodies.extend(comment["body"] for comment in data["comments"])
    return bodies


_SYNTHETIC: dict[str, str] = {
    "declared": f"Proof of Done - verified - run x - t\n\n{PUBLISH_HEAD_LABEL}: {_SHA}\n",
    "backticked": f"header\n\n{PUBLISH_HEAD_LABEL}: `{_SHA}`\n",
    "case_shifted": f"header\n{PUBLISH_HEAD_LABEL.upper()}: {_SHA}\n",
    "fenced_only": f"header\n\n```\n{PUBLISH_HEAD_LABEL}: {_SHA}\n```\n",
    "two_heads": f"header\n{PUBLISH_HEAD_LABEL}: {_SHA}\n{PUBLISH_HEAD_LABEL}: {_OTHER_SHA}\n",
    "short_sha": f"header\n{PUBLISH_HEAD_LABEL}: abc123\n",
    "undeclared": "header\n\njust prose about a head\n",
    "empty": "",
}


def test_the_materialized_reader_agrees_with_the_host_reader(tmp_path: Path) -> None:
    """One format, two implementations, the same answer on every body.

    This is the whole justification for a second implementation existing. The
    synthetic cases are asserted to produce BOTH answers -- at least one head and
    at least one `None` -- because an equality that only ever compared `None` to
    `None` would hold for a reader that returns `None` unconditionally, which is
    exactly what the real payloads alone would have certified.
    """
    program = _materialized(tmp_path=tmp_path)
    bodies = {**_SYNTHETIC, **{f"real-{index}": body for index, body in enumerate(_real_bodies())}}

    answers = {
        name: (published_head(body=body), program.published_head(body))
        for name, body in bodies.items()
    }

    assert all(host == sandbox for host, sandbox in answers.values()), {
        name: pair for name, pair in answers.items() if pair[0] != pair[1]
    }
    host_answers = {host for host, _ in answers.values()}
    assert _SHA in host_answers
    assert None in host_answers


def test_no_real_record_declares_a_head_which_is_why_the_reader_is_shared(
    tmp_path: Path,
) -> None:
    """The measurement behind the design, asserted so it cannot be forgotten.

    Both committed real payloads predate the head clause, so every one of their
    records reads as headless through BOTH readers. That is why a reader keyed on
    the record's second line passes review and finds nothing in production, and
    why the `pr` stage fails closed rather than publishing when the program
    cannot establish a head.
    """
    program = _materialized(tmp_path=tmp_path)
    bodies = _real_bodies()

    assert bodies, "the committed real payloads are missing"
    assert all(published_head(body=body) is None for body in bodies)
    assert all(program.published_head(body) is None for body in bodies)


def test_the_header_parse_reads_every_verdict_the_real_records_carry(
    tmp_path: Path,
) -> None:
    """The verdict comes off the record HEADER, read on the real payloads.

    The real records carry three distinct verdicts between them, so this is a
    positive control with three hits rather than a shape assertion: a parse that
    could not match the ratified em-dash header would return `None` for all of
    them and the required-verdict arms below could never fire.
    """
    program = _materialized(tmp_path=tmp_path)

    verdicts = {program.record_verdict(body) for body in _real_bodies()}

    assert None not in verdicts
    assert set(PROOF_HEAD_REQUIRED_VERDICTS) <= verdicts
    assert program.record_verdict("not a record at all") is None
    assert program.record_verdict("") is None


def test_the_materialized_header_reader_matches_the_canonical_record_parser(
    tmp_path: Path,
) -> None:
    """A proof-looking first line is a record only under the canonical grammar."""
    program = _materialized(tmp_path=tmp_path)
    bodies = (
        f"Proof of Done — captured — run run-1 — 2026-10-09T00:00:00Z\n{PUBLISH_HEAD_LABEL}: {_SHA}\n",
        f"Proof of Done — verified — session session-1 — 2026-10-09T00:00:01Z\n{PUBLISH_HEAD_LABEL}: {_SHA}\n",
        "Proof of Done - verified - run run-1 - 2026-10-09T00:00:00Z\n",
        "Proof of Done — invented — run run-1 — 2026-10-09T00:00:00Z\n",
        "Proof of Done — verified — run-1 — 2026-10-09T00:00:00Z\n",
        "ordinary discussion\n",
        "",
    )

    for body in bodies:
        canonical = proof_records(comments=({"body": body},))
        expected = canonical[0].verdict if canonical else None
        assert program.record_verdict(body) == expected, body


def _run_program(
    *, tmp_path: Path, comments: object | None, argv: list[str]
) -> tuple[int, str, str]:
    """Run the program as the node runs it, against a stubbed `gh` on PATH.

    A stub rather than a monkeypatch, because the program reaches the forge
    through `subprocess` exactly as it will in the sandbox: patching that out
    would leave the argv it issues unexercised, and the argv is the half a
    reader cannot check by eye.
    """
    path = tmp_path / PROOF_HEAD_PROGRAM_FILENAME
    _ = path.write_text(proof_head_program_source(), encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "gh"
    if comments is None:
        body = 'printf "not json" \nexit 0\n'
    elif comments == "fails":
        body = 'printf "forge unreachable" >&2\nexit 1\n'
    else:
        payload = json.dumps({"comments": comments}).replace("'", "'\\''")
        body = f"printf '%s' '{payload}'\nexit 0\n"
    _ = stub.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
    stub.chmod(0o755)
    result = subprocess.run(
        [sys.executable, str(path), *argv],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path)},
    )
    return result.returncode, result.stdout, result.stderr


def _record(*, verdict: str, head: str | None) -> dict[str, str]:
    head_line = "" if head is None else f"\n{PUBLISH_HEAD_LABEL}: {head}"
    return {"body": f"Proof of Done — {verdict} — run r — t{head_line}\n"}


def test_both_required_verdicts_naming_one_head_print_that_head(tmp_path: Path) -> None:
    """The success path: a capture and a replay agreeing on one tree.

    Asserted on STDOUT alone, because the node captures stdout and compares it
    with the pull request's head; a program that printed the answer to stderr
    would leave the node comparing an empty string.
    """
    argv = ["--pull-request", "7"]
    for verdict in PROOF_HEAD_REQUIRED_VERDICTS:
        argv.extend(["--require", verdict])

    code, out, _ = _run_program(
        tmp_path=tmp_path,
        comments=[_record(verdict=verdict, head=_SHA) for verdict in PROOF_HEAD_REQUIRED_VERDICTS],
        argv=argv,
    )

    assert code == 0
    assert out.strip() == _SHA


def test_a_later_not_reproduced_record_invalidates_an_older_verified_head(
    tmp_path: Path,
) -> None:
    """The latest replay verdict wins even when every record names one sha."""
    argv = ["--pull-request", "7"]
    for verdict in PROOF_HEAD_REQUIRED_VERDICTS:
        argv.extend(["--require", verdict])

    code, out, err = _run_program(
        tmp_path=tmp_path,
        comments=[
            _record(verdict="captured", head=_SHA),
            _record(verdict="verified", head=_SHA),
            _record(verdict=VERDICT_NOT_REPRODUCED, head=_SHA),
        ],
        argv=argv,
    )

    assert code == 1
    assert out == ""
    assert "newer not_reproduced" in err


def test_a_newer_capture_requires_a_subsequent_replay_even_on_the_same_head(
    tmp_path: Path,
) -> None:
    """A replay before the latest capture does not verify that capture."""
    argv = ["--pull-request", "7"]
    for verdict in PROOF_HEAD_REQUIRED_VERDICTS:
        argv.extend(["--require", verdict])

    code, out, err = _run_program(
        tmp_path=tmp_path,
        comments=[
            _record(verdict="captured", head=_SHA),
            _record(verdict="verified", head=_SHA),
            _record(verdict="captured", head=_SHA),
        ],
        argv=argv,
    )

    assert code == 1
    assert out == ""
    assert "newer captured" in err


@pytest.mark.parametrize(
    ("comments", "cause"),
    [
        pytest.param(
            [_record(verdict="verified", head=_SHA)],
            "carries no captured",
            id="capture-absent",
        ),
        pytest.param(
            [_record(verdict="captured", head=_SHA)],
            "carries no verified",
            id="replay-absent",
        ),
        pytest.param(
            [_record(verdict="captured", head=None), _record(verdict="verified", head=_SHA)],
            "names no single full publish-branch head",
            id="capture-headless",
        ),
        pytest.param(
            [
                _record(verdict="captured", head=_OTHER_SHA),
                _record(verdict="verified", head=_SHA),
            ],
            "name different publish-branch heads",
            id="heads-disagree",
        ),
        pytest.param([], "carries no captured", id="no-records"),
        pytest.param("fails", "could not be asked", id="forge-unreachable"),
        pytest.param(None, "did not parse as JSON", id="unparseable"),
    ],
)
def test_every_arm_that_cannot_establish_a_head_fails_closed(
    tmp_path: Path, comments: object, cause: str
) -> None:
    """Seven ways the head cannot be established, each naming its own measurement.

    The causes are asserted individually rather than by exit code alone, because
    "the records disagree" and "the forge could not be asked" have different
    remedies -- one is a re-dispatch, the other is a wait -- and a shared message
    would make them one finding. Nothing is printed to stdout in any arm, so the
    node cannot mistake a diagnostic for a head.
    """
    argv = ["--pull-request", "7"]
    for verdict in PROOF_HEAD_REQUIRED_VERDICTS:
        argv.extend(["--require", verdict])

    code, out, err = _run_program(tmp_path=tmp_path, comments=comments, argv=argv)

    assert code == 1
    assert out == ""
    assert cause in err


def test_a_misused_invocation_refuses_rather_than_establishing_nothing(
    tmp_path: Path,
) -> None:
    """No pull request, and no required verdict, each refuse.

    The second arm matters more than it looks: an invocation naming no verdict
    would otherwise succeed vacuously over an empty requirement set and print
    nothing, which the node would read as an empty head and compare unequal --
    a refusal, but for the wrong reason and with a misleading cause.
    """
    missing_subject, _, subject_err = _run_program(
        tmp_path=tmp_path, comments=[], argv=["--require", "verified"]
    )
    missing_verdict, _, verdict_err = _run_program(
        tmp_path=tmp_path, comments=[], argv=["--pull-request", "7"]
    )

    assert missing_subject == 1
    assert "usage:" in subject_err
    assert missing_verdict == 1
    assert "nothing would be established" in verdict_err


def test_the_prepare_step_lands_a_runnable_program_under_the_shared_root(
    tmp_path: Path,
) -> None:
    """The step the overlay renders actually materializes the program.

    Run as the sandbox runs it -- the rendered TOML basic string handed to `sh`
    -- rather than asserted as text, because the heredoc delimiter is QUOTED to
    stop the shell substituting into a program that is full of dollar signs, and
    that quoting is exactly the kind of thing a text assertion passes over.
    """
    block = proof_head_program_prepare_steps_block()
    script = json.loads(block.split("script = ", 1)[1].strip())

    result = subprocess.run(
        ["sh", "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )

    landed = tmp_path / ".claude" / "plugins" / PROOF_HEAD_PROGRAM_FILENAME
    assert result.returncode == 0, result.stderr
    assert landed.is_file()
    assert landed.read_text(encoding="utf-8") == proof_head_program_source()
    # The path the NODE resolves must name the file the step just wrote; the two
    # are different expressions of one root and a divergence is invisible.
    assert proof_head_program_path_expansion().endswith(f"/{PROOF_HEAD_PROGRAM_FILENAME}")
    assert "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT" in proof_head_program_path_expansion()


def test_the_program_carries_no_livespec_import_and_one_label(tmp_path: Path) -> None:
    """Stdlib-only, and its label substituted from the owning constant.

    A governed clone has no copy of this package, so a livespec import would make
    the program unrunnable in exactly the place it runs. The label assertion is
    the other half of "one format": a literal typed twice here would drift from
    `PUBLISH_HEAD_LABEL` with nothing to catch it.
    """
    source = proof_head_program_source()

    assert "livespec_orchestrator_beads_fabro" not in source
    assert "__LABEL__" not in source
    assert f'LABEL = "{PUBLISH_HEAD_LABEL}"' in source
    _ = _materialized(tmp_path=tmp_path)


# The two verdicts that may NAME the head publication readies, spelled as
# literals and bound to the module's own constant by the case below. A Red's
# test bytes are fixed across its Red-to-Green pair, so a top-level import of a
# name this change INTRODUCES would make the Red a collection error -- which
# proves the name is absent and nothing about the behaviour.
_VERIFIED = "verified"
_CARRIED_FORWARD = "carried_forward"
_CARRIED_SHA = "c" * 40


def test_the_anchor_verdicts_are_the_two_a_record_may_name_a_publishable_head_with() -> None:
    """The literals above are the module's own, so the cases below bind the product."""
    from livespec_orchestrator_beads_fabro.commands import _dispatcher_publication_head

    assert getattr(_dispatcher_publication_head, "PROOF_HEAD_ANCHOR_VERDICTS", None) == (
        _VERIFIED,
        _CARRIED_FORWARD,
    )


def test_a_carried_forward_record_names_the_head_publication_readies(
    tmp_path: Path,
) -> None:
    """The carry-forward route's whole point, read at the stage that publishes.

    The capture and the replay both name the head they ran on, V, and neither
    can name N -- no stage ran on N. Requiring them to agree with the head being
    published is exactly the rule a `carried_forward` record supersedes, by
    carrying that verified proof forward to the head it names. A program that
    still demanded the older agreement would refuse every carried-forward
    publication while reporting a perfectly ordinary head mismatch.
    """
    argv = ["--pull-request", "7"]
    for verdict in PROOF_HEAD_REQUIRED_VERDICTS:
        argv.extend(["--require", verdict])

    code, out, err = _run_program(
        tmp_path=tmp_path,
        comments=[
            _record(verdict="captured", head=_SHA),
            _record(verdict=_VERIFIED, head=_SHA),
            _record(verdict=_CARRIED_FORWARD, head=_CARRIED_SHA),
        ],
        argv=argv,
    )

    assert code == 0, err
    assert out.strip() == _CARRIED_SHA


def test_the_latest_anchor_wins_so_a_second_carry_forward_names_the_newer_head(
    tmp_path: Path,
) -> None:
    """A chain of carry-forwards publishes the head the LAST one names."""
    argv = ["--pull-request", "7"]
    for verdict in PROOF_HEAD_REQUIRED_VERDICTS:
        argv.extend(["--require", verdict])

    code, out, err = _run_program(
        tmp_path=tmp_path,
        comments=[
            _record(verdict="captured", head=_SHA),
            _record(verdict=_VERIFIED, head=_SHA),
            _record(verdict=_CARRIED_FORWARD, head=_CARRIED_SHA),
            _record(verdict=_CARRIED_FORWARD, head=_OTHER_SHA),
        ],
        argv=argv,
    )

    assert code == 0, err
    assert out.strip() == _OTHER_SHA


def test_a_record_newer_than_the_carry_forward_supersedes_it(tmp_path: Path) -> None:
    """The superseded-verification refusal follows the ANCHOR, not the verified record.

    Anchoring that refusal on the verified record alone would make every
    carried-forward publication look superseded by its own decision record,
    which is the failure mode the other direction of this change creates.
    """
    argv = ["--pull-request", "7"]
    for verdict in PROOF_HEAD_REQUIRED_VERDICTS:
        argv.extend(["--require", verdict])

    code, out, err = _run_program(
        tmp_path=tmp_path,
        comments=[
            _record(verdict="captured", head=_SHA),
            _record(verdict=_VERIFIED, head=_SHA),
            _record(verdict=_CARRIED_FORWARD, head=_CARRIED_SHA),
            _record(verdict=VERDICT_NOT_REPRODUCED, head=_CARRIED_SHA),
        ],
        argv=argv,
    )

    assert code == 1
    assert out == ""
    assert "newer not_reproduced" in err


def test_a_headless_carry_forward_record_establishes_nothing(tmp_path: Path) -> None:
    """A decision record naming no head cannot say which tree it carried proof to."""
    argv = ["--pull-request", "7"]
    for verdict in PROOF_HEAD_REQUIRED_VERDICTS:
        argv.extend(["--require", verdict])

    code, out, err = _run_program(
        tmp_path=tmp_path,
        comments=[
            _record(verdict="captured", head=_SHA),
            _record(verdict=_VERIFIED, head=_SHA),
            _record(verdict=_CARRIED_FORWARD, head=None),
        ],
        argv=argv,
    )

    assert code == 1
    assert out == ""
    assert "names no single full publish-branch head" in err

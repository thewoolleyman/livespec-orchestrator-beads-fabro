"""The repository preflight takes the SAME spec-stated judgement the gate takes.

The Dispatcher's pre-dispatch gate composes two judgements into one verdict: the
`dod_gate` rubric, and the spec-stated judgement whose governing-heading verdict
both rides in the subject and grades check 6 (a governing heading the reference
line omits). The preflight took only the first, so check 6 could fire only at the
Dispatcher, after the whole pre-launch. Measured 2026-10-24 on bd-ib-57ss2n,
bd-ib-pziqbf and bd-ib-aehdnb: each passed the preflight on both candidate legs
and was then refused at exit 5 for a governing heading its References line
omitted (`bd-ib-tka3wb`).

WHY THIS IS A CONTENT TEST, for the reason `test_dod_preflight_shared_prompt.py`
gives: the script resolves its build from the operator host's plugin registry and
reads the live tenant, which no sandbox has, so its end-to-end behaviour is proved
on a host. What a sandbox can establish is that the committed script DELEGATES to
the gate's own primitives instead of restating them — the property that makes the
two takings unable to diverge.

THE SCOPE of every assertion is the committed bytes of
`dev-tooling/dod-preflight.sh`, and each needle is a name copied from the gate
module `_dispatcher_dod_judgement_gate.py` or from the record module's field
names, so a hit can only come from the script calling the same thing.
"""

from __future__ import annotations

from pathlib import Path

_SCRIPT = Path("dev-tooling/dod-preflight.sh")


def _script() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def test_the_preflight_takes_the_spec_stated_judgement_through_the_gates_reader() -> None:
    # `host_governing_heading_reader` is the reader the gate defaults to; a
    # preflight that built its own would be a second judgement to diverge from.
    assert "host_governing_heading_reader" in _script()


def test_the_preflight_grades_check_six_through_the_gates_own_findings() -> None:
    # `governing_heading_findings` is what `_with_governing_findings` folds into
    # the gate's verdict, so the preflight's failure names the omitted heading
    # verbatim with the same remedy the Dispatcher's refusal names.
    assert "governing_heading_findings" in _script()


def test_the_preflight_subject_carries_the_governing_verdict() -> None:
    # The gate grades its rubric over `judgement_subject(..., governing=governing)`;
    # a subject without the block is a different subject from the one the
    # Dispatcher grades.
    assert "governing=governing" in _script()


def test_the_preflight_prints_the_governing_verdict_in_the_record_form() -> None:
    # The `livespec-dod-judgement` record carries `governing-heading-kind: <kind>`
    # and one `governing-heading: <heading>` line per governing clause.
    text = _script()

    assert [
        needle
        for needle in ("governing-heading-kind: ", "governing-heading: ")
        if needle not in text
    ] == []

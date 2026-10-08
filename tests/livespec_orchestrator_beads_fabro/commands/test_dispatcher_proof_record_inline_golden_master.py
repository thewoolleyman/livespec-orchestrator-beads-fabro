"""The golden master: an under-budget inline record publishes exactly as it did.

`bd-ib-555xcd` adds a size budget, an attachment path and a digest check to every
record publisher. Its fourth assertion is the one that bounds the blast radius:
**a record under budget with inline output publishes exactly as it does today.**

WHY A COMMITTED FIXTURE AND NOT AN ASSERTION ABOUT THE SHAPE. "Publishes exactly
as it does today" is a claim about BYTES, and every cheaper way of checking it is
satisfied by output this slice could have changed. A structural assertion — the
header is there, the fence is there, the verdict line is there — passes against a
record whose blank lines moved, and a moved blank line is not cosmetic here: the
record reader splits on prose headings and tracks fences, so spacing is part of
what makes a record parseable. So the whole body is compared, byte for byte,
against bytes captured BEFORE any of this slice's code existed.

WHERE THE FIXTURE BYTES CAME FROM, which is the only thing that makes this test
worth anything. They were rendered by `render_proof_record` at commit
`d4903b49` — this run's merge base, the tip of `master` before the first commit of
this slice — by placing that commit's `scripts` tree on `sys.path` and writing the
result to `tests/fixtures/proof_record_inline_golden_master.md` unmodified. A
fixture generated from the POST-change renderer would be a transcript of whatever
the code now does and would pass by construction, which is the trap this docstring
exists to foreclose. Its recorded digest is
`sha256:105c6e3c31e0f9b18ce384cf67e09c171af2395bc92064d1613c43993540ee96` over 902
bytes; both are asserted below, so a later editor who regenerates the fixture from
current behaviour has to change a number that names a commit in order to do it.

AND THE SAME BYTES WERE CAPTURED INDEPENDENTLY AT `a521526a`, the merge base of
this item's earlier dispatch, whose published work was preserved by reference after
its `pr` stage died. The two captures are byte-identical, and `git diff a521526a
d4903b49 -- .../_dispatcher_host_record_render.py` is empty — so the eighteen
commits that landed between them did not touch the renderer, and the figures below
are a reading of the pre-change behaviour rather than of one day's master.

WHAT THE SUBJECT RECORD DELIBERATELY EXERCISES, rather than being a minimal one:

- Two assertions, so the per-assertion section boundary is in the compared bytes.
- A build identity with a release tag and an installed build, and one assertion
  with a governing scenario against one with the no-scenario statement — the two
  arms of the renderer's only conditional fields.
- A proof that CARRIES ITS OWN TRIPLE-BACKTICK FENCE, which makes the renderer
  size the wrapper to four backticks. That is the subtlest byte in the file and
  the one a careless edit to the proof-rendering branch would change first.

AND A SECOND, INDEPENDENT ASSERTION: the committed bytes are still READ correctly
by the production record reader. Byte-identity alone would be satisfied by a
record that no longer parses if the READER had changed instead of the renderer —
this slice touched both — so the pair pins the round trip rather than one half of
it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    BuildIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    NO_GOVERNING_SCENARIO,
    RecordAssertion,
    render_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_budget import (
    INLINE_PROOF_ALLOWANCE_BYTES,
    PROOF_RECORD_BUDGET_BYTES,
    measured_bytes,
    record_budget_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_HOST_VERIFIED,
    proof_records,
)

_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "proof_record_inline_golden_master.md"
)

# Captured from `master` at d4903b49, BEFORE this slice's first commit. The same
# bytes were captured at a521526a, the earlier dispatch's merge base; the renderer
# is unchanged between the two, so the figures below are the pre-change behaviour
# rather than one day's reading of it.
_MASTER_COMMIT = "d4903b493dc9b2922cc34de0ec2e07f5edf0ce8d"
_GOLDEN_DIGEST = "sha256:105c6e3c31e0f9b18ce384cf67e09c171af2395bc92064d1613c43993540ee96"
_GOLDEN_BYTES = 902

_FIRST = "The released build resolves the host mode on an operator host."
_SECOND = "A record under budget with inline output publishes exactly as it does today."


def _subject() -> str:
    """The record under test, rendered through the production renderer.

    Every field is spelled here rather than built from a helper, because a helper
    shared with another test could be changed to match a drifting renderer and this
    comparison would follow it.
    """
    return render_proof_record(
        title="Proof of Done",
        verdict=VERDICT_HOST_VERIFIED,
        identity="session 01M44GOLDENSESSION",
        timestamp="2026-10-07T12:00:00Z",
        build=BuildIdentity(release_tag="v0.173.7", installed_build="abc123def456", commit=None),
        assertions=(
            RecordAssertion(
                text=_FIRST,
                proof_mode="host_captured",
                governing_scenario=(
                    "## Scenario 136 — A host-captured assertion holds the item in acceptance"
                ),
                steps=(
                    "Run the installed entry point.",
                    "Read the mode it reports. Produces proof 01.",
                ),
                proof="$ livespec-orchestrator-beads-fabro-dispatcher --version\n0.173.7\n",
                reproduced=True,
            ),
            RecordAssertion(
                text=_SECOND,
                proof_mode="host_captured",
                governing_scenario=NO_GOVERNING_SCENARIO,
                steps=("Render a record whose proof carries its own ``` fence.",),
                proof="outer\n```\ninner fence\n```\ndone\n",
                reproduced=True,
            ),
        ),
    )


def test_the_golden_fixture_is_the_pre_change_bytes_it_claims_to_be() -> None:
    """The fixture's own provenance, asserted before anything is compared to it.

    A golden master is only evidence if the bytes are the ones they claim to be. The
    digest and size are recorded from the capture at `_MASTER_COMMIT`, so a fixture
    silently regenerated from current behaviour fails HERE — before the comparison
    below could pass against it.
    """
    assert _FIXTURE.is_file()
    payload = _FIXTURE.read_bytes()

    assert len(payload) == _GOLDEN_BYTES
    assert f"sha256:{hashlib.sha256(payload).hexdigest()}" == _GOLDEN_DIGEST
    # Named so the provenance claim is greppable from the fixture's own test.
    assert len(_MASTER_COMMIT) == 40


def test_an_under_budget_inline_record_renders_byte_for_byte_as_before() -> None:
    """The fourth Definition of Done assertion, as a byte comparison.

    The subject is rendered by today's renderer; the expectation is the file captured
    from master. Equal bytes means the budget, attachment and digest work added
    nothing to, and removed nothing from, the record an ordinary publisher produces.
    """
    assert _subject() == _FIXTURE.read_text(encoding="utf-8")


def test_the_golden_record_is_under_budget_and_earns_no_refusal() -> None:
    """It is the UNDER-BUDGET case, so the clause's precondition genuinely holds.

    Without this the byte comparison would be silent about which case it covers: a
    fixture that happened to be over budget would still compare equal while proving
    nothing about the assertion, whose subject is records that fit.
    """
    body = _subject()
    assertions = (
        RecordAssertion(
            text=_FIRST,
            proof_mode="host_captured",
            governing_scenario=None,
            steps=(),
            proof="$ livespec-orchestrator-beads-fabro-dispatcher --version\n0.173.7\n",
            reproduced=True,
        ),
    )

    assert measured_bytes(text=body) < PROOF_RECORD_BUDGET_BYTES
    # Every proof in it is inline, which is the other half of the precondition.
    assert measured_bytes(text=body) < INLINE_PROOF_ALLOWANCE_BYTES
    assert (
        record_budget_refusal(body=body, surface="post-host-record", assertions=assertions) is None
    )
    assert "Attached proof:" not in body


def test_the_golden_record_still_reads_through_the_production_reader() -> None:
    """Byte-identity plus a working round trip, because this slice touched the READER too.

    A record can be byte-perfect and still ungradeable if the reader changed, and
    the two failures are indistinguishable from the renderer's output alone. So the
    committed bytes are parsed back and each assertion's verdict recovered.
    """
    records = proof_records(
        comments=[{"body": _FIXTURE.read_text(encoding="utf-8"), "url": "https://example.test/c/1"}]
    )

    assert len(records) == 1
    assert records[0].verdict == VERDICT_HOST_VERIFIED
    assert records[0].run_id == "01M44GOLDENSESSION"
    assert records[0].reproduced(assertion=_FIRST) is True
    assert records[0].reproduced(assertion=_SECOND) is True
    # An inline record carries no attachment, so nothing is fetched to grade it.
    assert records[0].attachment(assertion=_FIRST) is None
    assert records[0].attachment(assertion=_SECOND) is None


def test_the_four_backtick_fence_the_nested_proof_forces_is_in_the_golden_bytes() -> None:
    """The subtlest byte in the fixture, named so a regeneration cannot quietly lose it.

    The second assertion's proof contains a three-backtick run, so the renderer must
    wrap it in FOUR. A wrapper of three would be closed by the proof's own fence,
    after which the rest of the proof is prose to the reader — its `#` lines would
    open new sections and the assertion's verdict would be read from whichever one
    it landed in.
    """
    payload = _FIXTURE.read_text(encoding="utf-8")

    assert "\n````\nouter\n```\ninner fence\n```\ndone\n````\n" in payload

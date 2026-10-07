"""The gate, capture, review and replay prompts under Scenarios 136, 137, 139 and 141.

Binds the `SPECIFICATION/scenarios.md` headings that govern WHAT the proof
stages are told to do — not how the graph routes them (Scenario 131 owns
that) and not how a finding reaches `fix` (Scenario 138 owns that):

- Scenario 139 — the gate reads the capability set the image publishes,
  falls back to the committed mirror, and reports a `factory_captured`
  assertion whose surface no capability provides.
- Scenario 137 — a behavioural assertion is proved by exercising the
  behaviour: the gate reports a test-existence assertion on an item whose
  deliverable is not a test, capture refuses suite-only proof and ends rather
  than substituting a double, review blocks suite-only proof, and the replay
  backstop does not call it `not_reproduced`.
- Scenario 141 — the referenced scenario governs the proof, and the captured
  record names it per assertion.
- Scenario 136 — the PROMPT half of the host-captured leg: the gate admits a
  justified `### Host-captured` assertion and preserves the pending
  released-build obligation, refuses the declarations the deliverable policy
  forbids, and the capture, review and replay stages hold a declared host
  assertion pending SEPARATELY from a human attestation while still demanding
  every `factory_captured` assertion.

WHY THE PROMPT TEXT IS THE SUBJECT. These four payloads are the deliverable:
each node is an agent reading its prompt, so the prompt IS the implementation
of the duty, exactly as `workflow.fabro` is the implementation of the routing.
The prompts are what the Dispatcher ships, read here from the committed bundle
it ships them from.

WHY EVERY NEEDLE IS READ FROM A WHITESPACE-COLLAPSED PROMPT. The payloads are
hard-wrapped, so a needle straddling a line break fails while the prose says
exactly the thing — a probe that can only fail SILENTLY. Collapsing first is
what makes these assertions able to return the other answer. The same
discipline Scenario 131's binding uses, for the same reason.

WHY THE CAPABILITY PATH IS IMPORTED RATHER THAN TYPED. A second hand-typed
copy of `/etc/livespec/sandbox-capabilities` here would let the prompt and the
code drift while this file stayed green, so the literal comes from the module
that owns it.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_capabilities import (
    BASELINE_CAPABILITY,
    PUBLISHED_CAPABILITIES_PATH,
    SANDBOX_CAPABILITIES_KEY,
    UNPUBLISHED_REPORT,
)

_PROMPTS = Path(".claude-plugin/.fabro/workflows/implement-work-item/prompts")


def _prompt(*, name: str) -> str:
    """One prompt payload with every whitespace run collapsed to a single space."""
    path = _PROMPTS / name
    assert path.is_file(), path
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def _dod_gate_check(*, number: int) -> str:
    """One numbered check of the gate prompt's six-check list, collapsed.

    WHY THE SLICE EXISTS. The closed-pair prohibition this file's Scenario 136
    cases retire — "one of exactly `factory_captured` or `human_attested`" —
    lives inside check 3 and nowhere else, so a whole-prompt probe for
    `host_captured` already passes today: check 5's remedy list names the mode
    while check 3 still refuses it. That is exactly the contradiction the
    measured `overseer-emzwpx` gate run acted on. Scoping each needle to the
    OPERATIVE numbered check is what makes these assertions able to return the
    other answer; a prompt that merely mentioned the mode somewhere else would
    fail them.
    """
    prompt = _prompt(name="dod-gate.md")
    start = prompt.index(f" {number}. **")
    return prompt[start : prompt.index(f" {number + 1}. **", start)]


def _step(*, name: str, number: int) -> str:
    """One numbered `## Step N — …` section of a capture or replay prompt, collapsed.

    Same discipline as `_dod_gate_check`, for the same reason: the stage
    prompts classify assertions in Step 1 and shape the record in Step 5, and
    a needle satisfied by the worked example at the bottom of the file would
    say nothing about the instruction the stage actually follows.
    """
    prompt = _prompt(name=name)
    start = prompt.index(f"## Step {number} —")
    return prompt[start : prompt.index(f"## Step {number + 1} —", start)]


def _review_proof_section() -> str:
    """The review prompt's proof-record section, collapsed.

    Bounded by its own H2 and the next one so a finding asserted here is one
    the reviewer reads while judging the record, not a sentence from the
    severity section that follows.
    """
    prompt = _prompt(name="review.md")
    start = prompt.index("## The captured Proof of Done is part of this review")
    return prompt[start : prompt.index("## The lens —", start)]


def _review_output_section() -> str:
    """The review prompt's required-output section, collapsed.

    A SECOND bounded slice is needed beside `_review_proof_section` because
    the two sections answer different questions, and the measured failure
    lives in the gap between them. The proof section states the rule; this
    one states what the reviewer must EMIT. A requirement to compare the
    record against the Definition of Done is satisfiable in silence when it
    appears only in the prose that states the rule, so asserting it there
    cannot distinguish a reviewer who performed the comparison from one who
    skipped it. Bounded by its own H2 and the next so a needle found here is
    part of the output contract rather than a sentence from the lens.
    """
    prompt = _prompt(name="review.md")
    start = prompt.index("## Output (required, exact)")
    return prompt[start : prompt.index("## Ending the turn —", start)]


def test_the_gate_prompt_resolves_the_capability_set_from_both_sources_in_order() -> None:
    """The published file is the authority; the committed mirror is the fallback.

    Each needle names a decision the gate cannot make without the duty: the
    published PATH (which no other prompt text mentions), the committed KEY it
    falls back to, the baseline capability an image carries whether it
    publishes a file or not, and the verbatim report string for the case where
    NEITHER source answers. The unpublished report is asserted as the exact
    token the contract fixes, because a paraphrase of it is unparseable by
    whatever later reads the gate's output.
    """
    prompt = _prompt(name="dod-gate.md")

    assert PUBLISHED_CAPABILITIES_PATH in prompt
    assert f"dispatcher.{SANDBOX_CAPABILITIES_KEY}" in prompt
    assert BASELINE_CAPABILITY in prompt
    assert UNPUBLISHED_REPORT in prompt


def test_the_gate_prompt_reads_the_capability_set_and_never_infers_it() -> None:
    """The one source the gate must NOT use is the item's own prose.

    Scenario 139's "The capability set is read, never inferred from the item"
    is the case an agent fails most plausibly: an item asserting that the
    sandbox carries something reads exactly like a capability declaration. The
    prohibition is asserted as a prohibition rather than as the absence of a
    token, because the text that satisfies it necessarily CONTAINS the words
    it forbids.
    """
    prompt = _prompt(name="dod-gate.md")

    assert "never INFER it" in prompt
    assert "is not a capability" in prompt


def test_the_gate_prompt_reports_a_mirrored_name_the_image_does_not_publish() -> None:
    """A mirror/image divergence is a CONFIGURATION finding and never fails the gate.

    Asserted together because the pair is the whole rule: naming the mismatch
    without "never fails the gate" would license a gate that rests an item on
    a configuration drift the item had no part in.
    """
    prompt = _prompt(name="dod-gate.md")

    assert "CONFIGURATION MISMATCH" in prompt
    assert "never fails the gate" in prompt


def test_the_gate_prompt_reports_a_surface_no_capability_provides() -> None:
    """The missing-capability finding, and the three remedies IN THEIR ORDER.

    The order is load-bearing rather than cosmetic — the deliverable policy
    orders the modes `factory_captured`, `host_captured`, `human_attested` and
    an assertion carries the FIRST that can prove it — so the remedies are
    asserted by POSITION in the collapsed text, not merely by presence. A
    prompt listing all three in the wrong order would pass a presence-only
    probe while telling a human to weaken a mode further than it needs.
    """
    prompt = _prompt(name="dod-gate.md")

    assert "no capability" in prompt
    add_image = prompt.index("add the capability to the sandbox image")
    host = prompt.index("declare the assertion `host_captured`")
    human = prompt.index("declare it `human_attested` only when no agent session")

    assert add_image < host < human


def test_the_gate_prompt_withholds_only_the_missing_capability_finding_when_unknown() -> None:
    """An unknown set silences THAT finding and nothing else.

    The failure this forbids is the attractive one: with no capability set, a
    gate that simply skipped its capability reasoning would also skip the
    coherence, reference and proof-mode checks that do not depend on it.
    """
    prompt = _prompt(name="dod-gate.md")

    assert "withhold this finding and only this one" in prompt


def test_the_gate_prompt_reports_a_test_existence_assertion_with_its_remedy() -> None:
    """A test-existence assertion is a finding unless the deliverable IS a test.

    The exemption is asserted alongside the finding because the pair is the
    whole rule: a prompt carrying only the finding would reject the
    legitimate case Scenario 137 names — an item whose deliverable is a new
    test module — and a prompt carrying only the exemption would reject
    nothing at all. The remedy is asserted too, since a finding naming none
    rests the item with a question nobody can act on.
    """
    prompt = _prompt(name="dod-gate.md")

    assert "test-existence assertion" in prompt
    assert "itself a test, a check or a gate" in prompt
    assert "restate it as the behaviour the tests were meant to establish" in prompt


def test_the_gate_prompt_exempts_a_delivered_state_assertion_from_that_finding() -> None:
    """A configuration or documentation deliverable names the DELIVERED STATE.

    This is the shape most often mistaken for a test-existence assertion, and
    mistaking it is expensive in the refusing direction: it rests an item
    whose assertion was exactly what the contract asks for. The
    behaviour-preserving case is the same mistake on a refactor.
    """
    prompt = _prompt(name="dod-gate.md")

    assert "DELIVERED STATE" in prompt
    assert "behaviour-preserving" in prompt


def test_the_gate_prompt_reports_a_reference_naming_only_a_non_scenario_heading() -> None:
    """Where a scenario states the behaviour, the reference must name it.

    Both halves are asserted. The finding names the governing scenario
    heading — that is what the human adds to the reference line — and the
    converse is explicit, because a prompt carrying only the finding would
    reject every legitimate contracts-heading reference for an assertion no
    scenario states.
    """
    prompt = _prompt(name="dod-gate.md")

    assert "non-scenario H2" in prompt
    assert "Name the scenario heading that governs the assertion" in prompt
    assert "valid reference for an assertion no scenario states" in prompt


def test_the_capture_prompt_exercises_the_behaviour_through_its_named_surface() -> None:
    """Capture uses the delivered artifact as a user or operator would.

    The positive duty is asserted before the prohibition, because a prompt
    that only forbade the suite would leave the stage with nothing to do
    instead of something else to do.
    """
    prompt = _prompt(name="proof-capture.md")

    assert "exercise the behaviour through the surface the assertion names" in prompt
    assert "as a user or operator would" in prompt


def test_the_capture_prompt_forbids_suite_output_as_the_proof_of_a_behaviour() -> None:
    """Suite output MUST NOT be the proof of a behavioural assertion.

    Asserted with its one permitted role — supporting evidence BESIDE a real
    exercise — because that boundary is the whole rule: a flat ban would make
    a capture drop a genuinely useful aggregate run, and a prompt mentioning
    the suite without the ban is what let four pytest output files stand as a
    whole Definition of Done's proof.
    """
    prompt = _prompt(name="proof-capture.md")

    assert "MUST NOT be the proof of a behavioural assertion" in prompt
    assert "supporting evidence beside a real exercise" in prompt


def test_the_capture_prompt_ends_needs_human_on_a_surface_it_cannot_reach() -> None:
    """An unreachable surface ENDS the run; it never gets a stand-in.

    The three substitutes are named individually rather than as "a
    substitute", because each is separately attractive at the moment it is
    reached and a capture reaching for one would produce a record that reads
    exactly like a successful one. The structured ending is asserted as the
    literal JSON object the graph routes on, since a paraphrase routes
    nowhere.
    """
    prompt = _prompt(name="proof-capture.md")

    assert "cannot be reached with the sandbox's capabilities" in prompt
    assert "a test run, a fixture or a test double" in prompt
    assert "naming the assertion and the missing capability" in prompt
    assert '{"outcome": "failed", "failure_reason":' in prompt


def test_the_capture_prompt_distinguishes_a_missing_capability_from_a_code_defect() -> None:
    """The two non-capture endings route differently, so the prompt must tell them apart.

    A missing CAPABILITY is not an implementation defect: routing it to `fix`
    would send an implementer to repair code that is perfectly correct, and
    routing a real defect to `needs_human` would rest an item a fix loop
    could have closed. The discriminator has to be stated, not inferred.
    """
    prompt = _prompt(name="proof-capture.md")

    assert "not an implementation defect" in prompt
    assert "no code change could add the capability" in prompt


def test_the_review_prompt_blocks_suite_only_proof_of_a_behavioural_assertion() -> None:
    """Suite-only proof is `[BLOCKING]`, and the route back is named.

    The severity is the assertion. This prompt's whole middle section tells
    the reviewer to DEFAULT TO ADVISORY, so a finding described without its
    severity token would be sorted advisory by exactly the instruction that
    follows it — recorded, and never gating. The route matters for the same
    reason: an advisory suite-only finding would reach `pr` with the proof
    unexercised.
    """
    prompt = _prompt(name="review.md")

    assert "test-suite output alone" in prompt
    suite_only = prompt.index("test-suite output alone")
    assert "[BLOCKING]" in prompt[suite_only : suite_only + 600]
    assert "re-enters `proof_capture`" in prompt


def test_the_review_prompt_keeps_a_suite_run_legitimate_beside_a_real_exercise() -> None:
    """The reviewer must not block a capture that ALSO ran the suite.

    Without this, the rule over-applies in the expensive direction: a record
    whose assertion was properly exercised and which attached an aggregate
    run as corroboration would be blocked for the corroboration.
    """
    prompt = _prompt(name="review.md")

    assert "beside a real exercise is not a finding" in prompt


def test_the_verify_prompt_ends_needs_human_on_suite_only_proof() -> None:
    """The replay backstop refuses BOTH verdicts, and says why.

    Both prohibitions are asserted because each failure is separately
    plausible and each is wrong in a different direction: `not_reproduced`
    sends an implementer to repair correct code, and `verified` publishes a
    proof that exercised nothing. The reason — the defect is in the RECORD,
    not in the tree — is what makes the ending derivable rather than a rule
    to memorise.
    """
    prompt = _prompt(name="proof-verify.md")

    assert "test-suite output alone" in prompt
    assert "defect is in the record and not in the tree" in prompt
    assert "MUST NOT publish `not_reproduced`" in prompt
    assert "MUST NOT publish `verified`" in prompt


def test_the_verify_prompt_does_not_let_the_backstop_swallow_a_real_non_reproduction() -> None:
    """The backstop is narrow: it fires on the record's SHAPE, not on a failure.

    A replayer that read the new ending as "anything I cannot reproduce rests
    the item" would retire the `not_reproduced` verdict altogether, and the
    fix loop with it.
    """
    prompt = _prompt(name="proof-verify.md")

    assert "is still `not_reproduced`" in prompt


def test_the_capture_record_names_the_governing_scenario_per_assertion() -> None:
    """Per assertion: the referenced heading and the scenario title its steps exercise.

    The no-scenario case is asserted beside it because the record must be
    readable as a complete statement — an assertion with the entry simply
    absent is indistinguishable from one the capture forgot to fill in.
    """
    prompt = _prompt(name="proof-capture.md")

    assert "Governing scenario" in prompt
    assert "the title of the scenario your steps exercise" in prompt
    assert "no scenario governs" in prompt


def test_the_capture_prompt_follows_the_governing_scenarios_own_steps() -> None:
    """Where a scenario governs, the reproduction steps follow its Given/When/Then.

    Scenario 141's point is that the reference is not decoration: the
    scenario's own steps are what the proof is supposed to walk, which is
    what makes a published step set comparable to the behaviour the spec
    states rather than to whatever the capture found convenient.
    """
    prompt = _prompt(name="proof-capture.md")

    assert "follow one of that heading's scenarios step for step" in prompt


def test_the_gate_prompt_directs_a_search_before_concluding_no_scenario_governs() -> None:
    """The negative verdict is the one that needs an instrument pointed at the tree.

    "No scenario states this behaviour" forecloses the finding, and nothing
    downstream re-tests it. Recollection cannot establish it, so the prompt
    directs a search of `scenarios.md` before the conclusion is reached.
    """
    prompt = _prompt(name="dod-gate.md")

    assert "Search `scenarios.md`" in prompt
    assert "before concluding none does" in prompt


def test_the_gate_prompt_accepts_the_closed_triple_of_proof_modes() -> None:
    """Check 3's enumeration is the ratified TRIPLE, and the old PAIR is gone.

    The removal is asserted, not merely the addition. A check 3 that listed
    the third mode while still carrying "one of exactly `factory_captured` or
    `human_attested`" reads as a contradiction, and an agent resolving a
    contradiction picks one arm: on the measured `overseer-emzwpx` gate run it
    picked the prohibition and rested an item whose Host-captured declaration
    was correct.
    """
    check = _dod_gate_check(number=3)

    assert "`factory_captured`, `host_captured` or `human_attested`" in check
    assert "closed triple" in check
    assert "one of exactly `factory_captured` or `human_attested`" not in check


def test_the_gate_prompt_reads_a_host_captured_sub_heading_as_that_mode() -> None:
    """The positional sub-heading is what DECLARES the mode, so check 3 must name it.

    Both sub-headings are asserted together because the rule is positional and
    symmetric: a check 3 naming only `### Human-attested` classifies every
    bullet under `### Host-captured` as `factory_captured` and then refuses it
    for a surface no sandbox provides.
    """
    check = _dod_gate_check(number=3)

    assert "`### Host-captured` sub-heading (`host_captured`)" in check
    assert "`### Human-attested` sub-heading (`human_attested`)" in check


def test_the_gate_prompt_passes_a_justified_host_captured_assertion() -> None:
    """A justified host declaration is ADMITTED, and its mode is left alone.

    The pass verdict and the preservation duty are one rule. A gate that
    admitted the item but rewrote the mode would hand the capture stage an
    assertion it cannot capture; a gate that preserved the mode but refused
    the item is the measured failure this work-item repairs.
    """
    check = _dod_gate_check(number=3)

    assert "A justified `host_captured` declaration PASSES this gate" in check
    assert "Preserve the mode exactly as declared" in check


def test_the_gate_prompt_carries_the_pending_released_build_obligation() -> None:
    """What the gate admits is an item with proof still OWED on a host.

    Scenario 136's whole point is that admitting the assertion is not waving
    it through: the factory lists it pending, the item rests in `acceptance`
    after merge, and two different session identities record and replay it
    against the released build. Each clause is asserted because dropping any
    one of them turns the admission into exactly the wave-through the scenario
    forbids.
    """
    check = _dod_gate_check(number=3)

    assert "pending the host leg" in check
    assert "rests in `acceptance` after merge" in check
    assert "records it against the released build" in check
    assert "a different session replays it" in check


def test_the_gate_prompt_reports_a_missing_reason_under_either_sub_heading() -> None:
    """The Reason requirement is SYMMETRIC across the two declaring sub-headings.

    Scenario 136's first gherkin case is a Reason-less `### Host-captured`
    sub-heading, and the asymmetric prompt could not report it: naming only
    `### Human-attested` leaves the host sub-heading's missing Reason
    unreported by the one node positioned to catch what the host-side wall
    did not.
    """
    check = _dod_gate_check(number=3)

    assert (
        "A `### Host-captured` or `### Human-attested` sub-heading carrying no "
        "non-empty `Reason:` line" in check
    )


def test_the_gate_prompt_reports_a_proof_mode_outside_the_closed_triple() -> None:
    """An unsupported mode is still a finding — widening the enumeration did not retire it.

    The word PAIR is asserted absent from check 3 as well. Leaving it would
    keep the contradiction alive one layer down: the enumeration would read
    as a triple while the finding that enforces it still described two.
    """
    check = _dod_gate_check(number=3)

    assert "A proof mode outside that closed triple" in check
    assert "closed pair" not in check


def test_the_gate_prompt_refuses_a_host_or_human_mode_the_sandbox_could_exercise() -> None:
    """The too-weak refusal reaches `host_captured`, not just `human_attested`.

    An assertion a published capability can exercise is `factory_captured`
    whichever weaker mode was declared, so a refusal naming only
    `human_attested` admits the identical mistake spelled `host_captured`.
    The capability must be NAMED, because a refusal that cannot say which
    surface would have captured it rests the item with a question nobody can
    act on.
    """
    check = _dod_gate_check(number=3)

    assert "A `host_captured` or `human_attested` assertion the sandbox could exercise" in check
    assert "name the assertion AND the sandbox capability that makes it capturable" in check


def test_the_gate_prompt_refuses_human_attested_an_agent_could_exercise_on_a_host() -> None:
    """Scenario 136's last gherkin case: the host surface makes it `host_captured`.

    This is the refusal the closed PAIR made unstatable. With only two modes
    available, an assertion no sandbox can reach had nowhere to go but
    `human_attested`, so the gate had no ground to refuse it. The finding
    names the HOST SURFACE for the same reason the one above names the
    capability — it is what tells the human which mode to write instead.
    """
    check = _dod_gate_check(number=3)

    assert (
        "A `human_attested` assertion an agent session could exercise on an operator host" in check
    )
    assert "name the assertion AND the host surface that makes it host-capturable" in check


def test_the_gate_missing_capability_remedy_no_longer_defers_host_captured() -> None:
    """Check 5's remedy is an edit the human can make NOW, not a request for future stages.

    Check 5 used to hedge its own remedy against check 3's narrower
    enumeration — "where `host_captured` is not among them, this remedy is
    the human's request for that mode's stages rather than an edit to make
    right now". That hedge is the written form of the contradiction, and it
    survives any fix confined to check 3, so it is asserted gone from check 5
    itself.
    """
    check = _dod_gate_check(number=5)

    assert "Check 3 ACCEPTS that mode" in check
    assert "is not among them" not in check
    assert "rather than an edit to make right now" not in check


def test_the_capture_prompt_classifies_a_host_captured_sub_heading() -> None:
    """Step 1's classification is where a host assertion is either seen or lost.

    Capture's parse said "every other bullet has proof mode
    `factory_captured`", so a `### Host-captured` bullet fell into the
    factory bucket and the stage would try to capture inside the sandbox the
    one thing the sandbox cannot reach. Asserted inside Step 1 so the worked
    example at the bottom of the file cannot satisfy it.
    """
    step = _step(name="proof-capture.md", number=1)

    assert "Bullets under a `### Host-captured` sub-heading have proof mode `host_captured`" in step
    assert (
        "bullets under a `### Human-attested` sub-heading have proof mode `human_attested`" in step
    )


def test_the_capture_prompt_captures_every_factory_assertion_and_no_other() -> None:
    """EVERY factory assertion, and neither of the two kinds it must not capture.

    "Only the factory ones" and "every one of them" are a pair: the first
    stops the stage reaching for a host surface it has no route to, and the
    second is what an incomplete record violates. The host exclusion carries
    its reason, so the stage can tell a host assertion from a factory one it
    merely found awkward.
    """
    step = _step(name="proof-capture.md", number=1)

    assert "You capture ONLY the `factory_captured` assertions, and you capture EVERY one" in step
    assert "You never attempt to capture a `host_captured` one" in step
    assert "an agent session on a host records it after merge" in step


def test_the_capture_record_keeps_the_host_leg_separate_from_human_attestation() -> None:
    """Two pending legs, two headings — one heading cannot stand for both.

    The legs differ in WHO owes the proof: an agent performs the host leg,
    and no agent can perform a human attestation. A record collapsing them
    misreports which is owed, and the acceptance pass reads those headings to
    decide whether an `ai-only` item may close.
    """
    step = _step(name="proof-capture.md", number=5)

    assert "pending the host leg" in step
    assert "SEPARATE heading" in step
    assert "pending human attestation" in step
    assert "neither absorbs the other" in step


def test_the_capture_prompt_denies_a_pending_host_assertion_as_an_excuse() -> None:
    """A legitimate pending host leg discharges NOTHING on the factory side.

    This is the failure the separation newly makes available: once a stage
    may legitimately leave an assertion uncaptured, "pending the host leg"
    becomes an attractive label for a factory assertion that was simply hard.
    The record then reads complete while proving less than it claims.
    """
    step = _step(name="proof-capture.md", number=1)

    assert "A pending host-captured assertion NEVER excuses an uncaptured" in step
    assert "INCOMPLETE factory proof record" in step


def test_the_verify_prompt_classifies_and_replays_every_factory_assertion() -> None:
    """The replay leg parses modes independently, so it needs the same triple.

    The replayer reads the Definition of Done itself rather than trusting the
    captured record's labels — that independence is the point of the stage —
    so a parse that knows only two modes reproduces the capture stage's bug
    one node later, on the leg meant to catch it.
    """
    step = _step(name="proof-verify.md", number=1)

    assert "Bullets under a `### Host-captured` sub-heading have proof mode `host_captured`" in step
    assert "you replay EVERY one of them" in step


def test_the_verify_record_keeps_the_host_leg_separate_from_human_attestation() -> None:
    """The replayed record carries the same two pending headings as the capture.

    The pointer and the acceptance pass index the VERIFIED record, not only
    the captured one, so a replay that merged the two legs would undo the
    separation at exactly the surface that decides whether the item closes.
    """
    step = _step(name="proof-verify.md", number=5)

    assert "pending the host leg" in step
    assert "SEPARATE heading" in step
    assert "pending human attestation" in step


def test_the_verify_prompt_rejects_an_incomplete_factory_record() -> None:
    """An uncaptured factory assertion is rejected, inside Step 4 where the verdict is chosen.

    CORRECTION — this docstring's first version was wrong, and is kept
    accurate here rather than quietly dropped. It claimed the incomplete
    record was the "same shape as the suite-only backstop beside it" and so
    earned NEITHER verdict. The ratified `proof_verify` contract does not say
    that: it mandates `verified` when every factory assertion reproduced or
    `not_reproduced` naming each that did not, and grants the needs-human
    no-verdict ending to ONE shape only — a behavioural assertion whose proof
    is test-suite output alone. An assertion with no published capture did
    not reproduce, so it is `not_reproduced` and routes to `fix`, which
    re-enters capture. The analogy was the error; the three assertions below
    were never affected by it, which is why they stand unchanged.
    `test_the_verify_prompt_keeps_the_no_verdict_ending_to_the_suite_only_shape`
    is what now pins the routing this docstring got wrong.
    """
    step = _step(name="proof-verify.md", number=4)

    assert "has NOT thereby discharged any `factory_captured` assertion" in step
    assert "INCOMPLETE factory proof record" in step
    assert "is still `not_reproduced`" in step


def test_the_review_prompt_accepts_a_host_captured_assertion_listed_as_pending() -> None:
    """A correctly-pending host assertion is complete, not a finding.

    Without this the separation over-applies in the refusing direction: the
    reviewer, told the factory must capture every assertion, would block the
    one record shape Scenario 136 requires and send a correct run back
    through a capture it cannot perform.
    """
    section = _review_proof_section()

    assert "names every `host_captured` assertion as pending the host leg" in section
    assert "never a finding on its own" in section


def test_the_review_prompt_blocks_an_incomplete_factory_record_beside_a_pending_host_leg() -> None:
    """Severity and route, on the record that hides an uncaptured factory assertion.

    The severity token is the assertion: this prompt's severity section tells
    the reviewer to DEFAULT TO ADVISORY, so a finding stated without
    `[BLOCKING]` would be sorted advisory and reach `pr` with the proof
    unexercised. The route is named for the same reason the suite-only
    finding names it — capture, not fix, is what is owed.
    """
    section = _review_proof_section()

    assert "INCOMPLETE factory proof record" in section
    incomplete = section.index("INCOMPLETE factory proof record")
    assert "[BLOCKING]" in section[incomplete : incomplete + 400]
    assert (
        "blocking even when every host-captured assertion is correctly listed as pending" in section
    )
    assert "re-enters `proof_capture`" in section


def test_the_verify_prompt_keeps_the_no_verdict_ending_to_the_suite_only_shape() -> None:
    """The needs-human no-verdict ending covers ONE shape, and the contract names which.

    The ratified `proof_verify` clause mandates `verified` when every
    `factory_captured` assertion reproduced, or `not_reproduced` naming each
    that did not, and grants the structured needs-human ending as a backstop
    to exactly one record shape: a behavioural assertion whose proof is
    test-suite output alone. Routing a MISSING capture there instead would
    be a new human-routing policy the spec does not authorise, and it costs
    the ratified recovery — `not_reproduced` reaches `fix`, which re-earns a
    janitor and re-enters `proof_capture`, so the missing capture is taken.
    A needs-human ending rests the item instead, with no route back.

    The plural heading is asserted ABSENT because that is the form the
    over-broad version took: a prompt can name the ratified route for the
    incomplete record and still offer the no-verdict ending beside it, and
    an agent reading two permissions takes the one that ends its turn.
    """
    step = _step(name="proof-verify.md", number=4)

    assert "### The one record shape that earns NEITHER verdict" in step
    assert "An INCOMPLETE factory proof record is `not_reproduced`" in step
    assert "This is the ONLY shape that earns neither" in step
    assert "Two shapes get no verdict" not in step


def test_the_review_prompt_requires_the_record_comparison_be_performed_and_shown() -> None:
    """The incomplete-record check is a performed enumeration, not a rule to remember.

    WHY THE STATED RULE WAS NOT ENOUGH, measured. `review.md` already carries
    the rule and even carries the trap — "Check the record against the
    Definition of Done's own assertion list, not against the set of
    assertions the record chose to mention" — and the stage was still
    observed APPROVING an incomplete factory proof record: the
    `review-incomplete-factory-v4b` case of this item's own capture, whose
    supplied Definition of Done carried two `factory_captured` assertions
    while the supplied record captured only the first and correctly listed
    the host and human legs as pending. Two sibling observations of the
    identical condition DID block, one of them naming the omitted assertion,
    so this is a reliability failure of a stated rule and not a missing rule.

    WHAT MAKES A PROSE RULE UNRELIABLE HERE, and therefore what this case
    asserts. The rule is satisfiable in silence: a reviewer who never
    compares the record against the Definition of Done emits output that is
    byte-indistinguishable from one who compared and found nothing wrong —
    both produce `approve` and no finding. The sibling `proof_verify` stage
    reproduces the same rule deterministically, and the difference is not
    emphasis but ARTIFACT: its record format requires a per-assertion body,
    so a skipped comparison is visible as a missing section. This case
    requires the review to carry the same shape, and requires the ABSENCE of
    the enumeration to be a defect in its own right — without that last
    clause the enumeration is merely encouraged, which is the state measured
    to fail.

    The needles are scoped to the proof section rather than the whole prompt
    because a prompt that mentioned an enumeration anywhere else — in the
    lens, or in the severity section — would satisfy a whole-file probe while
    the reviewer judging the record read nothing about it.
    """
    section = _review_proof_section()

    assert "REQUIRED, SHOWN enumeration" in section
    assert "A review that emits no coverage enumeration is itself incomplete" in section
    assert "never from the set of assertions the record chose to mention" in section


def test_the_review_output_contract_carries_the_per_assertion_coverage_enumeration() -> None:
    """The enumeration is an emitted artifact, with both answers expressible.

    WHY THE OUTPUT SECTION IS THE OPERATIVE ONE. An instruction to enumerate
    that lives only where the rule is stated leaves the reviewer's OUTPUT
    unchanged, and the output is the only thing the next stage and a human
    ever see. Requiring the enumeration in the section headed `## Output
    (required, exact)` is what converts the comparison from a private step
    into a checkable one, so this case reads the output contract and not the
    prose above it.

    WHY A LINE PER ASSERTION, INCLUDING THE PASSING ONES. An enumeration that
    listed only the uncaptured assertions would be satisfied by emitting
    nothing on the very record that motivated it — a reviewer who never
    looked would print an empty list, which is exactly what a clean record
    also produces. Requiring a line for every `factory_captured` assertion,
    in Definition of Done order, is what makes the two cases differ on the
    page. Both tokens are asserted for the same reason the severity token is
    asserted elsewhere in this file: a format that can only express `yes` is
    not a check.

    WHY THE PENDING LEGS ARE ASSERTED HERE TOO. This is the over-application
    guard, and it is the direction a new mandatory enumeration is most likely
    to break. Scenario 136 requires a correctly-pending `host_captured` or
    `human_attested` assertion to draw no finding; a coverage enumeration
    that recognised only `captured: yes` / `captured: NO` would press the
    reviewer to grade a legitimately-uncaptured host leg as missing and block
    the one record shape the scenario mandates — sending a correct run back
    through a capture no sandbox can perform. The two legs must appear on the
    enumeration under their own separate labels, and be stated not to be
    findings.
    """
    section = _review_output_section()

    assert "Factory proof coverage:" in section
    assert "captured: yes" in section
    assert "captured: NO" in section
    assert "Every `factory_captured` assertion gets a line" in section
    assert "requires a matching `[BLOCKING]` finding" in section
    assert "pending host leg" in section
    assert "pending human attestation" in section
    assert "neither is a finding on its own" in section

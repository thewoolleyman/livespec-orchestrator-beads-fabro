"""The gate, capture, review and replay prompts under Scenarios 137, 139 and 141.

Binds the three `SPECIFICATION/scenarios.md` headings ratified in v115 that
govern WHAT the proof stages are told to do — not how the graph routes them
(Scenario 131 owns that) and not how a finding reaches `fix` (Scenario 138
owns that):

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


def test_the_gate_prompt_directs_a_search_before_concluding_no_scenario_governs() -> None:
    """The negative verdict is the one that needs an instrument pointed at the tree.

    "No scenario states this behaviour" forecloses the finding, and nothing
    downstream re-tests it. Recollection cannot establish it, so the prompt
    directs a search of `scenarios.md` before the conclusion is reached.
    """
    prompt = _prompt(name="dod-gate.md")

    assert "Search `scenarios.md`" in prompt
    assert "before concluding none does" in prompt

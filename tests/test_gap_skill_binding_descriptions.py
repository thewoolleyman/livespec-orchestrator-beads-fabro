"""Guard: the six gap-operation thin bindings match the ratified naming note.

The ratified contract (`SPECIFICATION/contracts.md`) carries a Naming note on
both gap operations: `detect-impl-gaps` performs NO spec↔impl comparison — it
is a **heading-coverage enumerator, not a spec→impl comparator** — so a
returned gap-id means "this heading has no exercising test", never "this
heading's behaviour is verified absent from the implementation".

That ratification landed on the contract and the driving prose but NOT on the
thin bindings, which kept advertising `Detect spec→impl gaps`. A SKILL.md
description is not documentation a reader may skip: the harness serves it in
the skills listing every agent loads into context, so the disclaimed claim was
still the first thing any agent read about the operation. Nothing kept a
binding's front-matter in sync with the contract clause it exposes; this module
is that missing check.

It asserts BOTH directions, because only the pair is a check:

1. Every binding's description names the ratified `spec-clause enumerator`.
2. No binding's description advertises a spec-to-implementation gap
   comparison — and the detector for (2) is exercised against the literal
   pre-ratification wording, so its offending arm is proven to fire rather
   than merely never firing.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PLUGIN_ROOT = _REPO_ROOT / ".claude-plugin"

# The six thin bindings of the two gap operations, across all three runtimes.
# pi's skill namespace is flat, so its binding directories carry the full
# plugin-name prefix rather than the colon-qualified form.
_GAP_BINDINGS: dict[str, Path] = {
    "claude:detect-impl-gaps": _PLUGIN_ROOT / "skills" / "detect-impl-gaps" / "SKILL.md",
    "claude:capture-impl-gaps": _PLUGIN_ROOT / "skills" / "capture-impl-gaps" / "SKILL.md",
    "codex:detect-impl-gaps": (
        _PLUGIN_ROOT / ".codex-plugin" / "skills" / "detect-impl-gaps" / "SKILL.md"
    ),
    "codex:capture-impl-gaps": (
        _PLUGIN_ROOT / ".codex-plugin" / "skills" / "capture-impl-gaps" / "SKILL.md"
    ),
    "pi:detect-impl-gaps": (
        _PLUGIN_ROOT
        / ".pi-plugin"
        / "skills"
        / "livespec-orchestrator-beads-fabro-detect-impl-gaps"
        / "SKILL.md"
    ),
    "pi:capture-impl-gaps": (
        _PLUGIN_ROOT
        / ".pi-plugin"
        / "skills"
        / "livespec-orchestrator-beads-fabro-capture-impl-gaps"
        / "SKILL.md"
    ),
}

# The ratified naming note's own vocabulary, verbatim from the
# `detect-impl-gaps` contract in SPECIFICATION/contracts.md.
_ENUMERATOR_PHRASE = "heading-coverage enumerator"
_ENUMERATOR_CLAUSE = "heading-coverage enumerator, not a spec→impl comparator"

_DESCRIPTION_RE = re.compile(r"^description:\s*(\S.*?)\s*$", re.MULTILINE)

# The disclaimed advertisement: a spec-to-implementation GAP noun phrase, in
# any of the spellings the bindings have historically used. Deliberately keyed
# on "gap(s)" rather than on "spec→impl" alone, because the honest disclaimer
# the bindings now carry ("not a spec→impl comparator") names the comparison in
# order to deny it — a ban on the bare arrow phrase would flag the remedy.
_COMPARISON_CLAIM_RE = re.compile(
    r"spec(?:ification)?\s*(?:→|->|-to-|\s+to\s+)\s*impl(?:ementation)?\s+gaps?",
    re.IGNORECASE,
)


def _description(*, text: str) -> str:
    """The front-matter `description:` value of `text`, unquoted.

    Returns the empty string when the front-matter carries no description, so
    a malformed binding surfaces as a failed phrase assertion rather than as an
    exception from the parser.
    """
    match = _DESCRIPTION_RE.search(text)
    if match is None:
        return ""
    return match.group(1).strip().strip('"')


def _advertises_spec_impl_comparison(*, description: str) -> bool:
    """True iff `description` advertises a spec-to-implementation gap comparison."""
    return _COMPARISON_CLAIM_RE.search(description) is not None


def _comparison_offenders(*, descriptions: dict[str, str]) -> list[str]:
    """Names of the bindings whose description advertises the disclaimed comparison."""
    return sorted(
        name
        for name, description in descriptions.items()
        if _advertises_spec_impl_comparison(description=description)
    )


def _shipped_descriptions() -> dict[str, str]:
    return {
        name: _description(text=path.read_text(encoding="utf-8"))
        for name, path in _GAP_BINDINGS.items()
    }


def test_every_gap_binding_ships_on_disk() -> None:
    """The enumerated bindings exist.

    Without this guard the assertions below would pass vacuously if a binding
    were renamed or moved out from under the enumeration.
    """
    for name, path in _GAP_BINDINGS.items():
        assert path.is_file(), f"missing gap-operation binding: {name} ({path})"


def test_every_gap_binding_description_names_the_heading_coverage_enumerator() -> None:
    """Each of the six descriptions carries the ratified enumerator wording."""
    for name, description in _shipped_descriptions().items():
        assert _ENUMERATOR_PHRASE in description, f"{name} description omits the naming note"
        assert _ENUMERATOR_CLAUSE in description, f"{name} description omits the disclaimer"


def test_no_gap_binding_advertises_a_spec_impl_comparison() -> None:
    """No shipped description advertises the comparison the contract disclaims."""
    offenders = _comparison_offenders(descriptions=_shipped_descriptions())
    assert not offenders, f"bindings advertise a spec-impl comparison: {offenders}"


def test_comparison_detector_flags_the_pre_ratification_wording() -> None:
    """Negative control — the detector fires on the wording that shipped at v0.72.1.

    Each string below is the literal front-matter this guard exists to reject,
    one per runtime spelling. The clean entry is the honest disclaimer the
    bindings now carry: it names the comparison in order to deny it, and it
    MUST NOT be flagged, or the remedy would trip its own check.
    """
    candidates = {
        "claude-arrow": "Detect spec→impl gaps mechanically via the Spec Reader.",
        "ascii-arrow": "Detect spec->impl gaps mechanically via the Spec Reader.",
        "pi-spelled-out": "Detect specification-to-implementation gaps mechanically.",
        "prose-spacing": "Detect spec to impl gap sets mechanically.",
        "honest-disclaimer": (
            f"This is a {_ENUMERATOR_CLAUSE} — it never reads implementation state."
        ),
    }

    assert _comparison_offenders(descriptions=candidates) == [
        "ascii-arrow",
        "claude-arrow",
        "pi-spelled-out",
        "prose-spacing",
    ]


def test_description_reader_reports_absent_front_matter_as_empty() -> None:
    """A binding with no `description:` field yields the empty string, not an error."""
    assert _description(text="---\nname: detect-impl-gaps\n---\n\n# body\n") == ""


def test_detect_impl_gaps_when_to_use_is_check_path_anchored() -> None:
    """The Claude binding's When-to-use matches `prose/implement.md` Step 5a.

    Step 5a anchors gap-tied closure to the recorded CHECK PATH and never to
    `gap_id`; the binding used to describe the retired gap_id-anchored gate.
    """
    body = _GAP_BINDINGS["claude:detect-impl-gaps"].read_text(encoding="utf-8")

    assert "## When to use" in body
    assert "`gap_check_path`" in body
    assert "does NOT invoke this skill at" in body
    assert "`gap_id` is no longer present in the returned set" not in body

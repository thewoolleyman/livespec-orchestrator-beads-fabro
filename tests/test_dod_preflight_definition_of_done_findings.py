"""The repository preflight takes the Dispatcher's section-wall finding first.

The shell preflight reads its work-item from the live tenant and its Dispatcher
build from the operator's plugin registry, so a sandbox cannot run its complete
host path.  These committed-byte assertions instead bind the integration seam:
the preflight imports and calls the Dispatcher's pure section-wall reader, emits
its returned finding unchanged, and returns before either judgement leg starts.
"""

from __future__ import annotations

from pathlib import Path

_SCRIPT = Path("dev-tooling/dod-preflight.sh")


def _script() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def test_the_preflight_checks_the_dispatchers_definition_of_done_findings_before_judgement() -> (
    None
):
    text = _script()

    assert "definition_of_done_findings" in text
    assert "section_findings = definition_of_done_findings(item=item, cwd=repo)" in text
    assert text.index("section_findings = definition_of_done_findings") < text.index(
        "governing = host_governing_heading_reader"
    )


def test_a_section_finding_is_printed_unchanged_and_stops_before_candidate_legs() -> None:
    text = _script()

    assert '"".join(f"{finding}\\n" for finding in section_findings)' in text
    section_guard = 'if [ -s "$judgement_input.section_findings" ]; then'

    assert section_guard in text
    assert text.index(section_guard) < text.index('cat "$judgement_input.governing"')
    assert text.index(section_guard) < text.index("while read -r agent model effort; do")

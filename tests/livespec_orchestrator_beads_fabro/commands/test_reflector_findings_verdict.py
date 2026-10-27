"""Verdict parsing distinguishes empty findings from malformed replies."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands import _reflector_findings_parse


def test_structured_empty_findings_is_a_verdict_but_malformed_text_is_not() -> None:
    """Fallback continues only for a reply that is not structured findings JSON."""
    parser = getattr(_reflector_findings_parse, "parse_findings_verdict", None)
    assert callable(parser)
    assert parser(raw='{"findings": []}') == ()
    assert parser(raw="not json") is None

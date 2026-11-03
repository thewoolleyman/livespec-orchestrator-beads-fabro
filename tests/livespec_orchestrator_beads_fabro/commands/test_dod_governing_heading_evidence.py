"""A model-supplied governing-heading quote is verified against its clause."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    governing_heading_findings,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    governing_heading_verdict,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_HEADING = "## Scenario 1 — Evidence binds a governing heading"
_QUOTE = "The specification states the asserted behaviour."


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-fgjehy",
        type="bug",
        status="ready",
        title="Evidence binds a governing heading",
        description="## Definition of Done\n\n- The asserted behaviour is stated.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-03T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def test_a_verified_quote_is_rendered_in_the_omitted_heading_finding(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "scenarios.md").write_text(f"{_HEADING}\n\n{_QUOTE}\n", encoding="utf-8")
    item = _item()
    reply = (
        '{"kind": "stated", "stated_by": ["'
        + _HEADING
        + '"], "generalization_target": null, "rationale": "It is stated.", '
        '"evidence": [{"heading": "' + _HEADING + '", "quote": "' + _QUOTE + '"}]}'
    )

    verdict = governing_heading_verdict(item=item, repo=repo, run_model=lambda _prompt: reply)

    assert verdict is not None
    findings = governing_heading_findings(
        item=item,
        section=definition_of_done(description=item.description),
        verdict=verdict,
    )
    assert len(findings) == 1
    assert _QUOTE in findings[0]

    unsupported = reply.replace(
        '"evidence": [{"heading": "' + _HEADING,
        '"evidence": [{"heading": "## A different heading',
    )
    assert (
        governing_heading_verdict(item=item, repo=repo, run_model=lambda _prompt: unsupported)
        is None
    )


def test_an_uncited_or_irrelevant_clause_is_not_a_governing_heading(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    irrelevant_quote = "A different unrelated clause fact."
    _ = (spec / "scenarios.md").write_text(f"{_HEADING}\n\n{irrelevant_quote}\n", encoding="utf-8")
    item = _item()
    reply = (
        '{"kind": "stated", "stated_by": ["'
        + _HEADING
        + '"], "generalization_target": null, "rationale": "It is stated."'
    )

    for evidence in (
        "",
        ', "evidence": [{"heading": "' + _HEADING + '", "quote": "' + irrelevant_quote + '"}]',
    ):
        assert (
            governing_heading_verdict(
                item=item,
                repo=repo,
                run_model=lambda _prompt, evidence=evidence: reply + evidence + "}",
            )
            is None
        )


def test_a_quote_sharing_only_incidental_or_one_term_does_not_state_the_behaviour(
    tmp_path: Path,
) -> None:
    item = _item()
    for index, quote in enumerate(
        (
            "A governing heading is named in this clause.",
            "Evidence is gathered elsewhere entirely.",
        )
    ):
        repo = tmp_path / str(index)
        spec = repo / "SPECIFICATION"
        spec.mkdir(parents=True)
        _ = (spec / "scenarios.md").write_text(f"{_HEADING}\n\n{quote}\n", encoding="utf-8")
        reply = (
            '{"kind": "stated", "stated_by": ["'
            + _HEADING
            + '"], "generalization_target": null, "rationale": "It is stated.", '
            '"evidence": [{"heading": "' + _HEADING + '", "quote": "' + quote + '"}]}'
        )

        verdict = governing_heading_verdict(item=item, repo=repo, run_model=lambda _p, r=reply: r)

        assert verdict is None

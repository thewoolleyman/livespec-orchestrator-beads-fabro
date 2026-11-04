"""The scenario-BODY half of the filing-time Definition-of-Done advisory.

These cases bind the rule against the fixture a MEASURED miss was taken from:
that the five assertions `bd-ib-yw7otf` was filed with each name Scenario 127 as
their candidate, and that such a candidate reaches a filer under the display's
`definition-of-done finding (advisory):` leader rather than the mechanical one.
`test_dispatcher_definition_of_done_advisories.py` is the sibling module, and
what it adds is the BOUNDARY — that the body each scenario is scored on ends at
the next `## ` heading — which a single-scenario fixture cannot observe.

WHY THE FIXTURE IS READ OUT OF THE GOVERNED SPEC TREE RATHER THAN PASTED. The
five assertions below were filed and delivered on `bd-ib-yw7otf` (pull request
3187), and the gate's own refusal cited Scenario 127's sub-scenarios at
`scenarios.md:3805` and `:3818`. The claim is therefore about THAT text; a copy
taken into this file would keep passing after the scenario it names had been
rewritten, which is the stale-instrument failure where it is least visible —
the test would still be green and would no longer be about anything.

WHY EACH POSITIVE CASE CARRIES A SAME-FIXTURE CONTROL. A rule that named a
candidate for every assertion would satisfy every positive assertion here. Each
negative case is therefore the SAME description and the SAME spec tree as a case
that does report, differing in exactly the one element the rule keys on: the
reference line in one pair, and the presence of the scenario's BODY in the other.
"""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.types import WorkItem

_ADVISORIES = "livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_advisories"
_DISPLAY = "livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display"

_SCENARIOS_PATH = Path("SPECIFICATION/scenarios.md")
_HEADING_MARKER = "## "
_SCENARIO_127_MARKER = "## Scenario 127 — "
# The non-scenario H2 the refused item's reference line named, and the one this
# fixture's `contracts.md` carries so the MECHANICAL wall resolves it and the
# advisory line is the only finding the display renders.
_REFERENCE_H2 = "## Factory-configurable ACP fallback priority"

# The Definition of Done `bd-ib-yw7otf` was filed and delivered with, copied
# verbatim on 2026-10-18. They are quoted rather than read from the ledger
# because a sandbox cannot reach the tenant.
_FILED_ASSERTIONS = (
    '`_GUARD_MARKERS` in `_acp_failure_signals.py` adds "acp turn timed out" to the'
    " `node_deadline` guard class, so `non_eligible_reason` returns `node_deadline` for a"
    ' failure whose protocol message or terminal diagnostic reads "ACP turn timed out after'
    ' 345 tool call(s) and 3658 session update(s)".',
    "`classify_acp_failure` returns an `AcpNonEligibleFailure` with reason `node_deadline`"
    " for that failure even when a configured or built-in signature literal would otherwise"
    " match its text.",
    "`classify_acp_failure` returns an `AcpNonEligibleFailure` with reason `unmatched` for a"
    " signal whose `original_identity` is `implement|transient_infra|acp turn failed` and"
    " whose `protocol_message` carries no guard marker and no signature literal, so the"
    " `transient_infra` segment of the identity alone never yields an"
    " `AcpAvailabilityFailure`.",
    "A turn-timeout failure whose cause chain also carries a provider usage-limit machine"
    " code still classifies as non-eligible with reason `node_deadline`, because the guard"
    " classes outrank configured matching.",
    "`classified_release` in `_dispatcher_provider_limit_classify.py` returns `None` for a"
    ' failure whose `cause` reads "ACP turn timed out after 345 tool call(s) and 3658'
    ' session update(s)" and whose `provider_usage_limit` flag is `True`, because a'
    " non-eligible guard verdict outranks the legacy provider-usage-limit arm.",
)


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-body",
        type="task",
        status="backlog",
        title="A freshly filed task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _scenario_127_section() -> str:
    """Scenario 127's heading and body, verbatim from the governed spec tree.

    Sliced by string partition rather than by a loop over the lines, so the
    helper carries no branch an exercising case would have to cover twice.
    """
    text = _SCENARIOS_PATH.read_text(encoding="utf-8")
    _, marker, rest = text.partition(_SCENARIO_127_MARKER)
    body = rest.split(f"\n{_HEADING_MARKER}", 1)[0]
    return f"{marker}{body}\n"


def _heading_of(*, section: str) -> str:
    """One scenario section's own H2 title, with its `## ` marker removed."""
    return section.splitlines()[0][len(_HEADING_MARKER) :]


def _repo(*, tmp_path: Path, scenarios: str) -> Path:
    """A repository whose spec tree carries one scenario and the referenced H2."""
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "scenarios.md").write_text(f"# Scenarios\n\n{scenarios}", encoding="utf-8")
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_REFERENCE_H2}\n\nSome prose.\n", encoding="utf-8"
    )
    return repo


def _description(*, assertions: tuple[str, ...], references: str) -> str:
    bullets = "".join(f"- {assertion}\n" for assertion in assertions)
    return f"## Definition of Done\n\n{bullets}\nReferences: {references}\n"


def _advisory_findings(*, item: WorkItem, cwd: Path) -> tuple[str, ...]:
    module = importlib.import_module(_ADVISORIES)
    return module.advisory_definition_of_done_findings(item=item, cwd=cwd)


def _advisory_display_lines(*, item: WorkItem, cwd: Path) -> list[str]:
    module = importlib.import_module(_DISPLAY)
    prefix = module.ADVISORY_FINDING_PREFIX
    return [
        line
        for line in module.filing_display(item=item, cwd=cwd).splitlines()
        if line.startswith(prefix)
    ]


def test_each_of_the_five_filed_assertions_names_scenario_127_as_its_candidate(
    tmp_path: Path,
) -> None:
    """The measured miss, as a regression fixture.

    `bd-ib-yw7otf` passed this wall on 2026-10-17 and was then refused at
    `dod_gate` check 6, which found Scenario 127 governing all five of its
    assertions. Every match sits in that scenario's sub-scenario titles and
    steps, so the heading-only score reported nothing and the item spent a
    factory run (01M55NZ1VRGS) to learn it.
    """
    section = _scenario_127_section()
    heading = _heading_of(section=section)
    assert heading.startswith("Scenario 127 ")

    item = _item(description=_description(assertions=_FILED_ASSERTIONS, references=_REFERENCE_H2))

    findings = _advisory_findings(item=item, cwd=_repo(tmp_path=tmp_path, scenarios=section))

    assert len(findings) == len(_FILED_ASSERTIONS)
    for assertion, finding in zip(_FILED_ASSERTIONS, findings, strict=True):
        assert heading in finding
        assert assertion in finding


def test_the_same_five_assertions_naming_scenario_127_report_nothing(tmp_path: Path) -> None:
    """The control: the SAME five assertions, differing only in the reference line.

    A rule that named a candidate for every assertion would satisfy the case
    above exactly as well as a correct one does.
    """
    section = _scenario_127_section()
    item = _item(
        description=_description(
            assertions=_FILED_ASSERTIONS,
            references=_heading_of(section=section),
        )
    )

    assert _advisory_findings(item=item, cwd=_repo(tmp_path=tmp_path, scenarios=section)) == ()


def test_a_body_only_overlap_reaches_the_filer_under_the_advisory_leader(
    tmp_path: Path,
) -> None:
    """The finding is displayed, and displayed as ADVISORY.

    The kind is the whole of what the leader carries: a mechanical finding
    withholds `ready` at intake and an advisory one is forbidden to, so a
    display that rendered this one under the mechanical leader would hold the
    item out of the queue on a candidate only the gate may judge.
    """
    section = _scenario_127_section()
    item = _item(
        description=_description(assertions=(_FILED_ASSERTIONS[3],), references=_REFERENCE_H2)
    )

    lines = _advisory_display_lines(item=item, cwd=_repo(tmp_path=tmp_path, scenarios=section))

    assert len(lines) == 1
    assert _heading_of(section=section) in lines[0]


def test_the_same_scenario_stripped_of_its_body_reaches_the_bound_on_nothing(
    tmp_path: Path,
) -> None:
    """The control for the case above, and the measurement behind the whole item.

    Same assertion, same reference line, same scenario HEADING — with the body
    removed. The heading's own vocabulary does not reach the shared-term bound,
    which is precisely why the heading-only score missed this item.
    """
    section = _scenario_127_section()
    heading_only = f"{section.splitlines()[0]}\n"
    item = _item(
        description=_description(assertions=(_FILED_ASSERTIONS[3],), references=_REFERENCE_H2)
    )

    lines = _advisory_display_lines(item=item, cwd=_repo(tmp_path=tmp_path, scenarios=heading_only))

    assert lines == []

"""Integration-tier acceptance for the filing-time Definition-of-Done wall.

Binds `SPECIFICATION/scenarios.md` "Scenario 140 — Filing displays
Definition-of-Done findings and withholds ready only on a mechanical one" and the
clause it realizes, the "Authoring at filing time" sub-clause of
`SPECIFICATION/contracts.md`'s Definition-of-Done-and-Proof-of-Done section. All
six of the heading's gherkin scenarios are asserted here, plus the prose duty the
same sub-clause lays on the four filing front-ends.

WHAT RUNS AS PRODUCTION CODE. The display primitive, both halves of the host-side
wall, the intake router and its ledger writes, and the needs-attention snapshot
are all production code over the REAL store/client seam against the in-memory
`FakeBeadsClient` — the hermetic CI backend and the no-live-connection runtime
fallback. Only the spec-side `spec_next` read is stood in, because it reaches a
sibling repository this tier does not have.

WHY THE FRONT-ENDS THEMSELVES ARE ASSERTED AS ARTEFACTS. The four front-ends are
harness-neutral PROSE plus thin per-runtime bindings — there is no CLI to drive —
so the prose IS the implementation of the authoring duty, exactly as
`workflow.fabro` is the implementation of the graph routing. The prose is
hard-wrapped, so every needle is read from a whitespace-collapsed copy: a needle
straddling a line break fails while the prose says exactly the thing, which is a
probe that can only fail silently.

WHY THE SPEC TREE IS BUILT RATHER THAN READ FROM THE REPOSITORY. The wall grades a
reference line against the H2 set of the GOVERNED repository's own spec tree, and
the fixture needs a heading that resolves AND a scenario heading that does not
appear on the reference line. Building both in `tmp_path` is what makes the
advisory and mechanical legs differ in exactly one element.

WHY THE MECHANICAL AND ADVISORY LEGS ARE THE SAME FILING. They differ only in
whether the reference line resolves. Without that pairing, "the advisory item
reached `ready`" is equally consistent with a build that graded nothing, and "the
mechanical item did not" with one that withholds `ready` from everything.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display import filing_display
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.needs_attention import SpecNextOutput
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

_PROSE = Path(".claude-plugin/prose")
# The four front-ends the clause names: "`capture-work-item`,
# `capture-impl-gaps`, `groom`, and the `plan` front-end when it routes a child".
_FILING_FRONT_ENDS = (
    "capture-work-item.md",
    "capture-impl-gaps.md",
    "groom.md",
    "plan.md",
)
# Each authoring rule the sub-clause enumerates, as a verbatim substring of the
# prose. Reading the rules off the prose rather than paraphrasing them is what
# makes a silent drift in one of the four files fail here.
_AUTHORING_RULE_NEEDLES = (
    "One behavioural assertion per bullet",
    "One proof mode per assertion, chosen in order",
    "`factory_captured`, then `host_captured`, then `human_attested`",
    "sandbox capabilities the display reports",
    "Reference the scenario that governs the assertion",
    "Never state the carrier relation inside the section",
)

_RESOLVABLE_HEADING = "## Effective acceptance criteria"
_UNRESOLVABLE_HEADING = "## A heading the governed spec tree does not carry"
_SCENARIO_HEADING = (
    "## Scenario 998 — The dispatcher refuses an unresolvable workflow variant"
    " before claiming the item"
)
_GOVERNED_ASSERTION = (
    "The dispatcher refuses an unresolvable workflow variant before claiming the item."
)
_TEST_EXISTENCE_ASSERTION = "Tests prove the accept valve refuses an unverified item."
_CAPABILITIES = ("terminal", "headless_browser")


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    """Reset the process-singleton fake tenant and force the fake backend."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _prose(*, name: str) -> str:
    """One front-end's prose with every whitespace run collapsed to one space."""
    path = _PROSE / name
    assert path.is_file(), path
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _routing_config(*, repo: Path) -> StoreConfig:
    return replace(_config(), repo_root=repo)


def _section(*, assertion: str, references: str) -> str:
    return f"## Definition of Done\n\n- {assertion}\n\nReferences: {references}\n"


def _item(*, id_: str, description: str) -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status="backlog",
        title=f"{id_} title",
        description=description,
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-04T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _seed(*, id_: str, description: str, status: str = "backlog") -> WorkItem:
    item = replace(_item(id_=id_, description=description), status=status)  # pyright: ignore[reportArgumentType]
    append_work_item(path=_config(), item=item)
    return item


def _project(*, root: Path) -> Path:
    """A governed repository: the connection block, the capability mirror, the spec tree."""
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "bd",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "wip_cap": 5,
                        "sandbox_capabilities": list(_CAPABILITIES),
                    },
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    spec = root / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_RESOLVABLE_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_SCENARIO_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    return root


def _ready_checklist() -> DefinitionOfReadyChecklist:
    return DefinitionOfReadyChecklist(
        single_coherent_done=True,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    )


def _file_through_intake(*, item_id: str, repo: Path) -> str:
    return unsafe_perform_io(
        apply_intake_dor(
            path=_routing_config(repo=repo), item_id=item_id, checklist=_ready_checklist()
        ).unwrap()
    )


def _status(*, item_id: str) -> str:
    return materialize_work_items(records=read_work_items(path=_config()))[item_id].status


def _comments(*, item_id: str) -> tuple[str, ...]:
    return tuple(
        comment.text for comment in read_work_item_comments(path=_config(), work_item_id=item_id)
    )


def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
    _ = project_root
    return None


def _attention_envelope(
    *, root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> list[dict[str, object]]:
    """The needs-attention wire envelope, through the REAL command-line entry point."""
    monkeypatch.setattr(needs_attention, "spec_next", _no_spec_next)
    exit_code = needs_attention.main(
        argv=[
            "--json",
            "--project-root",
            str(root),
            "--repo-name",
            "repo",
            "--skip-hygiene",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    attention = payload["attention"]
    assert isinstance(attention, list)
    return attention


# --------------------------------------------------------------------------
# Scenario: Filing displays the parse, the modes, the capabilities and the finding.
# --------------------------------------------------------------------------


def test_filing_displays_the_parse_the_modes_the_capabilities_and_the_finding(
    tmp_path: Path,
) -> None:
    """An implement-kind item whose only assertion is a test-existence assertion."""
    repo = _project(root=tmp_path)
    item = _seed(
        id_="bd-display",
        description=_section(assertion=_TEST_EXISTENCE_ASSERTION, references=_RESOLVABLE_HEADING),
    )

    lines = filing_display(item=item, cwd=repo).splitlines()

    assert lines[0] == (
        "effective acceptance criteria: 1 gradeable assertion(s) resolved from"
        " description-definition-of-done"
    )
    assert lines[1] == (f"assertion 1 (proof mode: factory_captured): {_TEST_EXISTENCE_ASSERTION}")
    assert lines[2] == "sandbox-capabilities: terminal, headless_browser"
    assert lines[3].startswith("definition-of-done finding (advisory):")
    assert "tests prove" in lines[3]
    assert len(lines) == 4


# --------------------------------------------------------------------------
# Scenario: An advisory finding is recorded and does not withhold ready.
# --------------------------------------------------------------------------


def test_an_advisory_finding_is_recorded_as_a_comment_and_does_not_withhold_ready(
    tmp_path: Path,
) -> None:
    repo = _project(root=tmp_path)
    _ = _seed(
        id_="bd-advisory",
        description=_section(assertion=_TEST_EXISTENCE_ASSERTION, references=_RESOLVABLE_HEADING),
    )

    verdict = _file_through_intake(item_id="bd-advisory", repo=repo)

    assert verdict == "ready"
    assert _status(item_id="bd-advisory") == "ready"
    comments = _comments(item_id="bd-advisory")
    assert len(comments) == 1
    assert comments[0].startswith("definition-of-done finding (advisory):")
    assert "tests prove" in comments[0]


# --------------------------------------------------------------------------
# Scenario: A mechanical finding withholds ready.
# --------------------------------------------------------------------------


def test_a_mechanical_finding_is_filed_held_out_of_ready_and_recorded(tmp_path: Path) -> None:
    """The SAME filing, differing only in a reference line that does not resolve."""
    repo = _project(root=tmp_path)
    _ = _seed(
        id_="bd-mechanical",
        description=_section(assertion=_TEST_EXISTENCE_ASSERTION, references=_UNRESOLVABLE_HEADING),
    )

    verdict = _file_through_intake(item_id="bd-mechanical", repo=repo)

    # Filed, and NOT routed to `ready` — the clause's two halves in one assertion.
    assert verdict == "pending-approval"
    assert _status(item_id="bd-mechanical") == "pending-approval"
    comments = _comments(item_id="bd-mechanical")
    mechanical = [
        body for body in comments if body.startswith("definition-of-done finding (mechanical):")
    ]
    assert len(mechanical) == 1
    assert _UNRESOLVABLE_HEADING in mechanical[0]


# --------------------------------------------------------------------------
# Scenario: A filer who declines the section sees it reported missing.
# --------------------------------------------------------------------------


def test_a_declined_section_is_reported_missing_and_the_filing_is_not_refused(
    tmp_path: Path,
) -> None:
    """Filing stays consent-gated: the display reports, and the filing proceeds."""
    repo = _project(root=tmp_path)
    item = _seed(id_="bd-declined", description="Just prose. The filer declined the section.")

    lines = filing_display(item=item, cwd=repo).splitlines()

    assert "definition-of-done: missing" in lines[0]
    # The filing itself is not refused — it rides the success track and lands.
    result = apply_intake_dor(
        path=_routing_config(repo=repo), item_id="bd-declined", checklist=_ready_checklist()
    )
    assert is_successful(result)
    assert _status(item_id="bd-declined") == "pending-approval"


# --------------------------------------------------------------------------
# Scenario: The carrier relation is not stated inside the section.
# --------------------------------------------------------------------------


def test_a_carrier_bullet_is_a_finding_while_the_same_prose_above_the_heading_is_not(
    tmp_path: Path,
) -> None:
    """The ratified pair, asserted together because either alone proves nothing.

    A build that reported neither satisfies the second assertion; one that
    reported both satisfies the first. Only the pair discriminates.
    """
    repo = _project(root=tmp_path)
    carrier_statement = "This child carries the plan assertion about the accept valve."
    inside = _seed(
        id_="bd-carrier-inside",
        description=_section(assertion=carrier_statement, references=_SCENARIO_HEADING),
    )
    above = _seed(
        id_="bd-carrier-above",
        description=(
            f"{carrier_statement}\n"
            "\n"
            f"{_section(assertion=_GOVERNED_ASSERTION, references=_SCENARIO_HEADING)}"
        ),
    )

    inside_lines = filing_display(item=inside, cwd=repo).splitlines()
    above_lines = filing_display(item=above, cwd=repo).splitlines()

    carrier_findings = [line for line in inside_lines if "carrier map" in line]
    assert len(carrier_findings) == 1
    assert carrier_findings[0].startswith("definition-of-done finding (advisory):")
    assert "definition-of-done findings: none" in above_lines


# --------------------------------------------------------------------------
# Scenario: Ready items with an advisory finding are surfaced before dispatch.
# --------------------------------------------------------------------------


def test_needs_attention_reports_a_ready_item_carrying_an_advisory_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Driven through `needs_attention.main`, which is what an operator invokes.

    The offending item's reference line names only the generic heading while the
    fixture's scenario heading states its behaviour — the scenario's own wording.
    The control is a sibling whose reference line names that scenario: without it,
    the fact appearing is equally consistent with a lane that reports every
    `ready` item in the tenant.
    """
    root = _project(root=tmp_path)
    _ = _seed(
        id_="bd-generic-ref",
        description=_section(assertion=_GOVERNED_ASSERTION, references=_RESOLVABLE_HEADING),
        status="ready",
    )
    _ = _seed(
        id_="bd-scenario-ref",
        description=_section(assertion=_GOVERNED_ASSERTION, references=_SCENARIO_HEADING),
        status="ready",
    )

    attention = _attention_envelope(root=root, monkeypatch=monkeypatch, capsys=capsys)

    advisory = [
        row for row in attention if str(row["id"]).startswith("hygiene:advisory-definition-of-done")
    ]
    assert [row["id"] for row in advisory] == ["hygiene:advisory-definition-of-done:bd-generic-ref"]
    summary = str(advisory[0]["summary"])
    assert "bd-generic-ref" in summary
    assert _SCENARIO_HEADING[len("## ") :] in summary


# --------------------------------------------------------------------------
# The prose duty: every filing front-end states the rules and renders the display.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("front_end", _FILING_FRONT_ENDS)
def test_every_filing_front_end_states_the_authoring_rules(front_end: str) -> None:
    """Each of the four front-ends states each authoring rule the clause enumerates."""
    prose = _prose(name=front_end)

    missing = [needle for needle in _AUTHORING_RULE_NEEDLES if needle not in prose]
    assert missing == [], (front_end, missing)


@pytest.mark.parametrize("front_end", _FILING_FRONT_ENDS)
def test_every_filing_front_end_renders_the_shared_filing_display(front_end: str) -> None:
    """The display is the ONE primitive, named by each front-end rather than re-derived.

    A front-end that assembled its own display would satisfy the rules case above
    while showing a filer something different from every sibling surface.
    """
    prose = _prose(name=front_end)

    assert "_dispatcher_filing_display" in prose
    assert "filing_display(" in prose

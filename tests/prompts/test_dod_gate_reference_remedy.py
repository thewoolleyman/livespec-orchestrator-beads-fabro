"""Contract tests for the Definition-of-Done gate's References remedy."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.types import WorkItem

_REPOSITORY_ROOT = Path(__file__).parents[2]
_WORKFLOW_GRAPH = (
    _REPOSITORY_ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
)
_PROMPTS_DIRECTORY = _WORKFLOW_GRAPH.parent / "prompts"
_NODE_BLOCK = re.compile(
    r"^[ \t]*(?P<name>\w+)[ \t]*\[$(?P<body>.*?)^[ \t]*\]$",
    re.DOTALL | re.MULTILINE,
)
_PROMPT_ATTRIBUTE = re.compile(r'prompt="@prompts/(?P<filename>[\w.-]+\.md)"')
_DOD_GATE_NODE = "dod_gate"
_MULTI_REFERENCE_REMEDY = "References: ## <heading>[, ## <heading>...]"
_FILING_DISPLAY_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display"
_SPEC_HEADING = "## Effective acceptance criteria"
_SCENARIO_HEADING = (
    "## Scenario 131 — The Definition-of-Done gate admits a coherent item, "
    "refuses a malformed one host-side, and rests an incoherent one at needs-human"
)


def _dod_gate_prompt() -> Path:
    """Return the prompt file the workflow assigns to the Definition-of-Done gate."""
    graph = _WORKFLOW_GRAPH.read_text(encoding="utf-8")
    prompt_filenames = [
        match.group("filename")
        for node in _NODE_BLOCK.finditer(graph)
        if node.group("name") == _DOD_GATE_NODE
        for match in [_PROMPT_ATTRIBUTE.search(node.group("body"))]
        if match is not None
    ]

    assert prompt_filenames == ["dod-gate.md"]
    return _PROMPTS_DIRECTORY / prompt_filenames[0]


def _item(*, description: str) -> WorkItem:
    return WorkItem(
        id="bd-ib-disp-remedy",
        type="task",
        status="backlog",
        title="A freshly filed task",
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


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_SCENARIO_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    return repo


def _definition_of_done(*, references: str) -> str:
    return (
        "## Definition of Done\n"
        "\n"
        "- The accept valve refuses an item with no verified record.\n"
        "\n"
        f"References: {references}\n"
    )


def _display(*, item: WorkItem, cwd: Path) -> list[str]:
    module = importlib.import_module(_FILING_DISPLAY_MODULE)
    return module.filing_display(item=item, cwd=cwd).splitlines()


def test_dod_gate_prescribes_marker_prefixed_multi_heading_references() -> None:
    """The remedy must match the host parser's marker-delimited reference grammar."""
    prompt = _dod_gate_prompt()

    assert prompt.is_file()
    assert _MULTI_REFERENCE_REMEDY in prompt.read_text(encoding="utf-8")


def test_the_prescribed_multi_heading_reference_remedy_has_no_definition_of_done_finding(
    tmp_path: Path,
) -> None:
    """Each marker-prefixed reference resolves through the filing display."""
    item = _item(
        description=_definition_of_done(references=f"{_SPEC_HEADING}, {_SCENARIO_HEADING}")
    )

    lines = _display(item=item, cwd=_repo(tmp_path=tmp_path))

    assert lines[-1] == "definition-of-done findings: none"


def test_the_prescribed_single_heading_reference_remedy_has_no_definition_of_done_finding(
    tmp_path: Path,
) -> None:
    """The marker-prefixed form also resolves when only one heading is named."""
    item = _item(description=_definition_of_done(references=_SPEC_HEADING))

    lines = _display(item=item, cwd=_repo(tmp_path=tmp_path))

    assert lines[-1] == "definition-of-done findings: none"

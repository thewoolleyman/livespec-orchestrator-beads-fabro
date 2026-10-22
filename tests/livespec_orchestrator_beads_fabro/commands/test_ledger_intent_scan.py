"""Unit tests for the ledger-intent scan's decisions and its CLI refusals.

The integration-tier acceptance for Scenario 38 lives in
`tests/integration/test_ledger_intent_scan_scenario38.py` and drives the whole
surface. These cases cover the decisions in isolation — the cut read, the
population rule, the rendered statement — plus every refusal the subcommand
renders, which an end-to-end pass over a healthy fixture never reaches.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._ledger_intent_cut import (
    CUT_INSTANT_FIELD,
    SpecVersionCut,
    latest_spec_version_cut,
    parse_spec_version,
    spec_version_cut,
)
from livespec_orchestrator_beads_fabro.commands._ledger_intent_scan import (
    LEDGER_INTENT_KINDS,
    LedgerIntentFinding,
    finding_for,
    intent_statement,
    scan_population,
)
from livespec_orchestrator_beads_fabro.commands._orchestrator_ledger_intent import (
    judge_runner,
    run_ledger_intent_scan,
)
from livespec_orchestrator_beads_fabro.commands._orchestrator_shared import (
    CliContext,
    InjectedCliError,
)
from livespec_orchestrator_beads_fabro.commands.orchestrator import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import WorkItem
from livespec_runtime.spec_stated import SpecStatedVerdict

_ANCHOR = "bd-ib-anchor"
_STATED_VERDICT = json.dumps(
    {
        "kind": "stated",
        "stated_by": ["## A clause"],
        "generalization_target": None,
        "rationale": "the clause states it",
    }
)


def _item(**overrides: object) -> WorkItem:
    base: dict[str, object] = {
        "id": "bd-ib-one",
        "type": "task",
        "status": "backlog",
        "title": "A title",
        "description": "A description",
        "origin": "freeform",
        "gap_id": None,
        "rank": "m",
        "assignee": None,
        "depends_on": (),
        "captured_at": "2026-01-01T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
    }
    base.update(overrides)
    return WorkItem(**base)  # pyright: ignore[reportArgumentType]


def _revision(*, spec: Path, version: int, body: str) -> None:
    proposals = spec / "history" / f"v{version:03d}" / "proposed_changes"
    proposals.mkdir(parents=True)
    _ = (proposals / "topic-revision.md").write_text(body, encoding="utf-8")


def _frontmatter(*, instant: str) -> str:
    return f"---\ndecision: accept\n{CUT_INSTANT_FIELD}: {instant}\n---\n\nprose\n"


# ---------------------------------------------------------------------------
# The cut read
# ---------------------------------------------------------------------------


def test_the_cut_is_the_newest_recorded_instant_of_the_version(tmp_path: Path) -> None:
    proposals = tmp_path / "history" / "v007" / "proposed_changes"
    proposals.mkdir(parents=True)
    _ = (proposals / "a-revision.md").write_text(
        _frontmatter(instant="2026-04-01T00:00:00Z"), encoding="utf-8"
    )
    _ = (proposals / "b-revision.md").write_text(
        _frontmatter(instant="2026-05-01T00:00:00Z"), encoding="utf-8"
    )
    assert spec_version_cut(spec_root=tmp_path, version=7) == SpecVersionCut(
        version=7, instant="2026-05-01T00:00:00Z"
    )


def test_an_absent_proposals_directory_answers_no_cut(tmp_path: Path) -> None:
    assert spec_version_cut(spec_root=tmp_path, version=3) is None


def test_a_version_whose_records_record_no_instant_answers_no_cut(tmp_path: Path) -> None:
    _revision(spec=tmp_path, version=4, body="---\ndecision: accept\n---\n\nprose\n")
    assert spec_version_cut(spec_root=tmp_path, version=4) is None


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("no front matter at all\n", id="no-delimiter"),
        pytest.param("", id="empty"),
        pytest.param(f"---\n---\n{CUT_INSTANT_FIELD}: 2026-01-01T00:00:00Z\n", id="after-close"),
        pytest.param(f"---\nbare line\n{CUT_INSTANT_FIELD}:   \n---\n", id="bare-and-empty"),
        pytest.param("---\ndecision: accept\n", id="unterminated"),
    ],
)
def test_front_matter_that_records_no_usable_instant_answers_no_cut(
    tmp_path: Path, body: str
) -> None:
    _revision(spec=tmp_path, version=5, body=body)
    assert spec_version_cut(spec_root=tmp_path, version=5) is None


def test_an_empty_history_tree_answers_no_latest_cut(tmp_path: Path) -> None:
    assert latest_spec_version_cut(spec_root=tmp_path) is None


def test_the_latest_cut_is_the_newest_version_the_tree_carries(tmp_path: Path) -> None:
    _revision(spec=tmp_path, version=1, body=_frontmatter(instant="2026-01-01T00:00:00Z"))
    _revision(spec=tmp_path, version=2, body=_frontmatter(instant="2026-02-01T00:00:00Z"))
    assert latest_spec_version_cut(spec_root=tmp_path) == SpecVersionCut(
        version=2, instant="2026-02-01T00:00:00Z"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("v026", 26, id="ratified-form"),
        pytest.param("V7", 7, id="uppercase"),
        pytest.param("26", 26, id="bare-integer"),
        pytest.param("v0", None, id="zero"),
        pytest.param("", None, id="empty"),
        pytest.param("v", None, id="marker-only"),
        pytest.param("latest", None, id="word"),
        pytest.param("-3", None, id="negative"),
    ],
)
def test_the_since_version_grammar_accepts_both_spellings_and_nothing_else(
    raw: str, expected: int | None
) -> None:
    assert parse_spec_version(raw=raw) == expected


# ---------------------------------------------------------------------------
# The population rule and the statement
# ---------------------------------------------------------------------------


def test_the_population_adds_live_items_only_when_the_scan_is_unscoped() -> None:
    live = _item(id="bd-ib-live", status="backlog", captured_at="2026-01-01T00:00:00Z")
    recent = _item(id="bd-ib-recent", status="done", captured_at="2026-04-01T00:00:00Z")
    old = _item(id="bd-ib-old", status="done", captured_at="2026-01-01T00:00:00Z")
    items = [recent, old, live]
    cut = "2026-03-01T00:00:00Z"
    unscoped = scan_population(items=items, cut=cut, include_live=True)
    scoped = scan_population(items=items, cut=cut, include_live=False)
    assert [one.id for one in unscoped] == ["bd-ib-live", "bd-ib-recent"]
    assert [one.id for one in scoped] == ["bd-ib-recent"]


def test_the_statement_names_every_intent_field_including_the_unrecorded_ones() -> None:
    statement = intent_statement(
        item=_item(title="Hold the valve", description="  ", acceptance_criteria=None, reason="")
    )
    assert "Work item bd-ib-one" in statement
    assert "Title: Hold the valve" in statement
    assert statement.count("(none recorded)") == 3


def test_a_finding_carries_the_verdict_and_the_generalization_target() -> None:
    finding = finding_for(
        item=_item(),
        verdict=SpecStatedVerdict(
            kind="partial",
            stated_by=("## A clause",),
            generalization_target="## A clause",
            rationale="part of it",
        ),
    )
    assert finding == LedgerIntentFinding(
        item_id="bd-ib-one",
        kind="partial",
        stated_by=("## A clause",),
        generalization_target="## A clause",
        rationale="part of it",
    )
    assert finding is not None
    assert finding.projection()["stated_by"] == ["## A clause"]
    assert finding.kind in LEDGER_INTENT_KINDS


def test_a_stated_verdict_yields_no_finding_at_all() -> None:
    """The control for the case above: a kind outside the two drift verdicts.

    Without it a build that emitted a finding for every judged item satisfies
    the positive case exactly as well as the filter does.
    """
    assert (
        finding_for(
            item=_item(),
            verdict=SpecStatedVerdict(
                kind="stated",
                stated_by=("## A clause",),
                generalization_target=None,
                rationale="the clause states it",
            ),
        )
        is None
    )


# ---------------------------------------------------------------------------
# The subcommand's refusals and its human rendering
# ---------------------------------------------------------------------------


def _context(*, root: Path, anchor: str | None = _ANCHOR) -> CliContext:
    """A project root whose committed config optionally declares the anchor.

    `anchor=None` is the UNCONFIGURED case, which the shared writer refuses
    before touching the tenant — a different refusal from a declared anchor
    naming no live row, and the two have different remedies.
    """
    block: dict[str, object] = {"connection": {"prefix": "bd-ib"}}
    if anchor is not None:
        block["dispatcher"] = {"detection_coverage_anchor": anchor}
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": block}),
        encoding="utf-8",
    )
    spec = root / "SPECIFICATION"
    spec.mkdir()
    _ = (spec / "contracts.md").write_text("# Contracts\n\n## A clause\n\nProse.\n", "utf-8")
    return CliContext(project_root=root, spec_root=spec)


def _answering(*, text: str, exit_code: int = 0) -> list[str]:
    code = (
        "import sys\n"
        "_ = sys.stdin.read()\n"
        f"sys.stdout.write({text!r})\n"
        "sys.stderr.write('judge narration')\n"
        f"sys.exit({exit_code})\n"
    )
    return [sys.executable, "-c", code]


def test_an_unreadable_latest_cut_refuses_rather_than_scanning(tmp_path: Path) -> None:
    context = _context(root=tmp_path)
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        code = run_ledger_intent_scan(
            context=context, judge_cli=_answering(text="{}"), as_json=True
        )
    assert code == 3
    assert "cannot" in stderr.getvalue()


def _one_item_project(*, root: Path, seed_anchor: bool = True) -> CliContext:
    context = _context(root=root)
    _revision(spec=context.spec_root, version=1, body=_frontmatter(instant="2026-01-01T00:00:00Z"))
    config = resolve_store_config(cwd=root, work_items_arg=None)
    append_work_item(
        path=config,
        item=_item(id="bd-ib-aaa", captured_at="2026-06-01T00:00:00Z"),
    )
    if seed_anchor:
        # Closed and captured BEFORE the cut, so the anchor row is outside the
        # population and these cases read one judged item rather than two.
        append_work_item(
            path=config,
            item=_item(id=_ANCHOR, status="done", captured_at="2025-01-01T00:00:00Z"),
        )
    return context


def _scanned(*, context: CliContext, judge_cli: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = run_ledger_intent_scan(context=context, judge_cli=judge_cli, as_json=False)
    return code, stdout.getvalue(), stderr.getvalue()


def test_an_unreadable_verdict_exits_the_wire_shape_code_naming_the_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    context = _one_item_project(root=tmp_path)
    code, stdout, stderr = _scanned(context=context, judge_cli=_answering(text="not json"))
    assert code == 4
    assert "bd-ib-aaa" in stderr
    assert "no ledger-intent drift among 1 work-item(s)" in stdout


def test_the_human_rendering_names_the_item_the_verdict_and_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    context = _one_item_project(root=tmp_path)
    verdict = json.dumps(
        {
            "kind": "unstated",
            "stated_by": [],
            "generalization_target": None,
            "rationale": "no clause states it",
        }
    )
    code, stdout, _ = _scanned(context=context, judge_cli=_answering(text=verdict))
    assert code == 0
    assert stdout == "bd-ib-aaa  unstated  (no generalization target)\n"


def test_an_unconfigured_anchor_refuses_the_invocation_naming_the_obligation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No committed anchor: the records the contract requires cannot land."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    context = _context(root=tmp_path, anchor=None)
    _revision(spec=context.spec_root, version=1, body=_frontmatter(instant="2026-01-01T00:00:00Z"))
    code, _, stderr = _scanned(context=context, judge_cli=_answering(text=_STATED_VERDICT))
    assert code == 3
    assert "detection_coverage_anchor" in stderr


def test_a_declared_anchor_naming_no_live_row_refuses_naming_the_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control for the case above: declared, but unwritable.

    Both refuse with the same exit code, and that is the point of asserting on
    the narration: the remedies differ — provision the anchor, versus fix the
    committed id — and a build that reported one cause for both would send
    every operator down the wrong one.
    """
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    context = _one_item_project(root=tmp_path, seed_anchor=False)
    code, _, stderr = _scanned(context=context, judge_cli=_answering(text=_STATED_VERDICT))
    assert code == 3
    assert _ANCHOR in stderr
    assert "did not land" in stderr


def test_a_judge_that_exits_non_zero_raises_the_injected_cli_error() -> None:
    run = judge_runner(judge_cli=_answering(text="{}", exit_code=7))
    with pytest.raises(InjectedCliError) as excinfo:
        _ = run("a prompt")
    assert "exit 7" in excinfo.value.detail


def test_a_scoped_scan_whose_named_version_records_no_cut_refuses_naming_it(
    tmp_path: Path,
) -> None:
    """The refusal names the VERSION, which the unscoped arm cannot say."""
    context = _context(root=tmp_path)
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        code = run_ledger_intent_scan(
            context=context,
            judge_cli=_answering(text="{}"),
            since_version=26,
            as_json=True,
        )
    assert code == 3
    assert "spec version v026" in stderr.getvalue()


def test_an_unusable_since_version_value_is_a_narrated_usage_error(tmp_path: Path) -> None:
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        code = main(
            argv=[
                "ledger-intent-scan",
                "--project-root",
                str(tmp_path),
                "--judge-cli",
                json.dumps([sys.executable, "-c", "pass"]),
                "--since-version",
                "latest",
            ]
        )
    assert code == 2
    assert "--since-version requires a positive integer" in stderr.getvalue()


def test_a_judge_cli_that_is_not_an_argv_array_is_a_usage_error(tmp_path: Path) -> None:
    with contextlib.redirect_stderr(io.StringIO()):
        code = main(
            argv=[
                "ledger-intent-scan",
                "--project-root",
                str(tmp_path),
                "--judge-cli",
                "not-an-array",
            ]
        )
    assert code == 2

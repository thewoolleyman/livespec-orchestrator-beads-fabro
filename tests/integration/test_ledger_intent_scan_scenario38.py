"""Integration-tier acceptance for the ledger-intent scan (Scenario 38).

Drives `orchestrator ledger-intent-scan` end to end against the real seams
rather than against hand-built fixtures:

- the LEDGER half runs through the real store/client seam over the in-memory
  `FakeBeadsClient`, so the population the scan selects is the one a real
  tenant would hand it;
- the SPEC half reads a real on-disk spec tree, so the governing H2 headings a
  verdict may cite are the tree's own and the cut instant is read off a real
  revision record;
- the JUDGEMENT half injects a real subprocess as the spec-stated judge, so the
  verdict crosses the same wire a provider binding would.

That pairing is the point. The scan's whole claim is that an item's recorded
intent is measured against the ratified text, so a test that stubbed either the
tenant or the tree would be measuring neither.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands.orchestrator import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ANCHOR = "bd-ib-anchor"
_VALVE_HEADING = "## The dispatch valve"
_COVERAGE_HEADING = "## The coverage anchor"
# The cut of v002, the newest version the fixture tree carries.
_LATEST_CUT = "2026-03-01T00:00:00Z"
# The cut of v001, which the fixture tree also carries a revision record for.
_EARLIER_CUT = "2026-02-01T00:00:00Z"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-orch-beads-fabro",
        prefix="bd-ib",
        server_user="livespec-orch-beads-fabro",
        database="livespec-orch-beads-fabro",
        bd_path="bd",
        fake=True,
    )


def _project(*, root: Path) -> Path:
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {"detection_coverage_anchor": _ANCHOR},
                }
            }
        ),
        encoding="utf-8",
    )
    spec = root / "SPECIFICATION"
    spec.mkdir()
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_VALVE_HEADING}\n\nProse.\n\n{_COVERAGE_HEADING}\n\nProse.\n",
        encoding="utf-8",
    )
    _revision(spec=spec, version=1, cut=_EARLIER_CUT)
    _revision(spec=spec, version=2, cut=_LATEST_CUT)
    return root


def _revision(*, spec: Path, version: int, cut: str) -> None:
    proposals = spec / "history" / f"v{version:03d}" / "proposed_changes"
    proposals.mkdir(parents=True)
    _ = (proposals / "topic-revision.md").write_text(
        f"---\nproposal: topic.md\ndecision: accept\nrevised_at: {cut}\n---\n\nprose\n",
        encoding="utf-8",
    )


def _seed(*, id_: str, status: str, captured_at: str, title: str) -> None:
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=id_,
            type="task",
            status=status,  # pyright: ignore[reportArgumentType]
            title=title,
            description=f"{title} description",
            origin="freeform",
            gap_id=None,
            rank="m",
            assignee=None,
            depends_on=(),
            captured_at=captured_at,
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
        ),
    )


def _judge_cli(*, verdicts: dict[str, dict[str, object]]) -> str:
    """An injected judge answering a per-item verdict, else `stated`.

    Keyed on the work-item id the rendered intent statement carries, which is
    how one subprocess stands in for a judgement of several items.
    """
    stated = {
        "kind": "stated",
        "stated_by": [_COVERAGE_HEADING],
        "generalization_target": None,
        "rationale": "the ratified text states it",
    }
    code = (
        "import json, sys\n"
        f"verdicts = {verdicts!r}\n"
        f"stated = {stated!r}\n"
        "prompt = sys.stdin.read()\n"
        "answer = stated\n"
        "for item_id, verdict in verdicts.items():\n"
        "    if item_id in prompt:\n"
        "        answer = verdict\n"
        "        break\n"
        "sys.stdout.write(json.dumps(answer))\n"
    )
    return json.dumps([sys.executable, "-c", code])


def _run(*, root: Path, judge_cli: str, extra: list[str] | None = None) -> tuple[int, object]:
    """Invoke the subcommand, tolerating an argparse usage exit.

    The usage exit is caught rather than propagated so an unwired flag reports
    as the exit code the caller asserts on, instead of erroring the test out
    before any assertion runs.
    """
    argv = [
        "ledger-intent-scan",
        "--project-root",
        str(root),
        "--spec-target",
        str(root / "SPECIFICATION"),
        "--judge-cli",
        judge_cli,
        "--json",
        *(extra or []),
    ]
    buffer = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
        try:
            code = main(argv=argv)
        except SystemExit as exit_signal:
            code = int(exit_signal.code or 0)
    text = buffer.getvalue()
    return code, (json.loads(text) if text.strip().startswith("{") else None)


def test_the_scan_lists_the_population_with_each_verdict_and_target(tmp_path: Path) -> None:
    """Assertion 1 — every live item plus every item captured since the cut."""
    root = _project(root=tmp_path)
    _seed(
        id_="bd-ib-aaa",
        status="backlog",
        captured_at="2026-01-01T00:00:00Z",
        title="Hold the valve open while a credential rotates",
    )
    _seed(
        id_="bd-ib-bbb",
        status="done",
        captured_at="2026-06-01T00:00:00Z",
        title="Record the processed-merge frontier",
    )
    _seed(
        id_="bd-ib-ccc",
        status="done",
        captured_at="2026-02-05T00:00:00Z",
        title="Closed long before the latest cut",
    )
    verdicts: dict[str, dict[str, object]] = {
        "bd-ib-aaa": {
            "kind": "partial",
            "stated_by": [_VALVE_HEADING],
            "generalization_target": _VALVE_HEADING,
            "rationale": "the valve clause states part of it",
        },
        "bd-ib-bbb": {
            "kind": "unstated",
            "stated_by": [],
            "generalization_target": _COVERAGE_HEADING,
            "rationale": "no clause states the frontier",
        },
    }
    code, payload = _run(root=root, judge_cli=_judge_cli(verdicts=verdicts))
    assert code == 0, f"the scan did not succeed: exit {code}"
    assert isinstance(payload, dict)
    findings = payload["findings"]
    assert isinstance(findings, list)
    assert [one["item_id"] for one in findings] == ["bd-ib-aaa", "bd-ib-bbb"]
    assert [one["kind"] for one in findings] == ["partial", "unstated"]
    assert [one["generalization_target"] for one in findings] == [
        _VALVE_HEADING,
        _COVERAGE_HEADING,
    ]


def test_an_item_the_judgement_states_produces_no_finding(tmp_path: Path) -> None:
    """Assertion 2 — intent already reflected in the spec emits nothing.

    Both items are in the population and both are judged, so a scan that
    reported one finding because it judged one item would pass this case for
    the wrong reason; `scanned` is asserted to pin that down.
    """
    root = _project(root=tmp_path)
    _seed(
        id_="bd-ib-aaa",
        status="backlog",
        captured_at="2026-01-01T00:00:00Z",
        title="Behaviour the ratified text already states",
    )
    _seed(
        id_="bd-ib-bbb",
        status="backlog",
        captured_at="2026-01-01T00:00:00Z",
        title="Behaviour no clause states",
    )
    verdicts: dict[str, dict[str, object]] = {
        "bd-ib-bbb": {
            "kind": "unstated",
            "stated_by": [],
            "generalization_target": _COVERAGE_HEADING,
            "rationale": "no clause states it",
        },
    }
    code, payload = _run(root=root, judge_cli=_judge_cli(verdicts=verdicts))
    assert code == 0, f"the scan did not succeed: exit {code}"
    assert isinstance(payload, dict)
    assert payload["scanned"] == 2
    findings = payload["findings"]
    assert isinstance(findings, list)
    assert [one["item_id"] for one in findings] == ["bd-ib-bbb"]


def test_since_version_restricts_the_population_to_the_named_version_cut(
    tmp_path: Path,
) -> None:
    """Assertion 3 — the NAMED version's cut governs, and the live set does not widen it.

    Two scoped runs over one tenant, because a build that read the latest cut
    whatever the flag said would answer the `v002` case correctly and the
    `v001` case with one item too few. The live item captured before both cuts
    is what pins the clause's "only work-items captured on or after the cut":
    it is in the unscoped population and in neither scoped one.
    """
    root = _project(root=tmp_path)
    _seed(
        id_="bd-ib-aaa",
        status="backlog",
        captured_at="2026-01-01T00:00:00Z",
        title="Live, captured before either cut",
    )
    _seed(
        id_="bd-ib-bbb",
        status="done",
        captured_at="2026-02-15T00:00:00Z",
        title="Captured between the two cuts",
    )
    _seed(
        id_="bd-ib-ccc",
        status="done",
        captured_at="2026-06-01T00:00:00Z",
        title="Captured after both cuts",
    )
    unstated: dict[str, object] = {
        "kind": "unstated",
        "stated_by": [],
        "generalization_target": _COVERAGE_HEADING,
        "rationale": "no clause states it",
    }
    judge_cli = _judge_cli(
        verdicts={"bd-ib-aaa": unstated, "bd-ib-bbb": unstated, "bd-ib-ccc": unstated}
    )
    latest_code, latest = _run(root=root, judge_cli=judge_cli, extra=["--since-version", "v002"])
    assert latest_code == 0, f"the scoped scan did not succeed: exit {latest_code}"
    assert isinstance(latest, dict)
    assert latest["cut"] == _LATEST_CUT
    assert latest["scanned"] == 1
    assert [one["item_id"] for one in latest["findings"]] == ["bd-ib-ccc"]  # pyright: ignore[reportGeneralTypeIssues]
    earlier_code, earlier = _run(root=root, judge_cli=judge_cli, extra=["--since-version", "v001"])
    assert earlier_code == 0
    assert isinstance(earlier, dict)
    assert earlier["cut"] == _EARLIER_CUT
    assert earlier["scanned"] == 2
    assert [one["item_id"] for one in earlier["findings"]] == [  # pyright: ignore[reportGeneralTypeIssues]
        "bd-ib-bbb",
        "bd-ib-ccc",
    ]


def test_an_unknown_flag_is_a_usage_error_that_emits_no_envelope(tmp_path: Path) -> None:
    """The usage exit this module's own invoker tolerates, asserted rather than assumed.

    A helper that swallows an argparse exit has to be shown to swallow one:
    otherwise a later flag typo in a case above would read as a scan that
    emitted nothing rather than as an invocation the CLI refused.
    """
    root = _project(root=tmp_path)
    code, payload = _run(root=root, judge_cli=_judge_cli(verdicts={}), extra=["--frobnicate"])
    assert code == 2
    assert payload is None
